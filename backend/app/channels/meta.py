"""WhatsApp Business and Instagram Direct, both on the Meta Graph API."""

from __future__ import annotations

import logging
from typing import Any, Optional

import httpx

from .base import ChannelAdapter, InboundMessage, verify_hmac_sha256

logger = logging.getLogger(__name__)

GRAPH_VERSION = "v21.0"
GRAPH_URL = f"https://graph.facebook.com/{GRAPH_VERSION}"


class _MetaAdapter(ChannelAdapter):
    has_webhook = True
    can_send = True

    def verify_signature(self, config: dict, raw_body: bytes, headers: dict[str, str]) -> bool:
        secret = (config or {}).get("app_secret", "")
        if not secret:
            return False
        signature = headers.get("x-hub-signature-256") or headers.get("X-Hub-Signature-256") or ""
        return verify_hmac_sha256(secret, raw_body, signature)

    async def _graph_post(self, path: str, token: str, payload: dict) -> Optional[str]:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(
                f"{GRAPH_URL}/{path}",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json=payload,
            )
        if response.status_code >= 400:
            logger.warning("%s send failed %s: %s", self.name, response.status_code, response.text[:300])
            return None
        data = response.json()
        messages = data.get("messages") or []
        if messages:
            return messages[0].get("id")
        return data.get("message_id") or data.get("id")


class WhatsAppAdapter(_MetaAdapter):
    name = "whatsapp"
    label = "WhatsApp Business"
    required_keys = ("app_secret", "verify_token", "access_token", "phone_number_id")

    def parse_inbound(self, payload: dict, config: dict) -> list[InboundMessage]:
        results: list[InboundMessage] = []
        for entry in payload.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                # Contacts carry the display name, so index them by wa_id first.
                names = {
                    contact.get("wa_id"): (contact.get("profile") or {}).get("name")
                    for contact in value.get("contacts", [])
                }
                for message in value.get("messages", []):
                    body = _extract_text(message)
                    media = _media_refs(message)
                    # A photo with no caption is still a message worth having.
                    if not body and not media:
                        continue
                    sender = message.get("from", "")
                    results.append(
                        InboundMessage(
                            channel=self.name,
                            sender_id=sender,
                            sender_name=names.get(sender),
                            sender_phone=f"+{sender}" if sender and not sender.startswith("+") else sender,
                            body=body,
                            # WhatsApp has no thread, so the contact is the thread.
                            thread_id=sender,
                            external_id=message.get("id"),
                            attachments=media,
                            meta={"type": message.get("type"), "timestamp": message.get("timestamp")},
                        )
                    )
        return results

    async def fetch_attachment(self, config: dict, ref: dict) -> Optional[tuple[bytes, str, str]]:
        """Pull one WhatsApp media file down."""
        token = (config or {}).get("access_token", "")
        media_id = (ref or {}).get("media_id", "")
        if not token or not media_id:
            return None
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                lookup = await client.get(
                    f"{GRAPH_URL}/{media_id}",
                    headers={"Authorization": f"Bearer {token}"},
                )
                lookup.raise_for_status()
                described = lookup.json()
                url = described.get("url")
                if not url:
                    return None
                # The download needs the token too, this is not a public URL.
                download = await client.get(url, headers={"Authorization": f"Bearer {token}"})
                download.raise_for_status()
        except httpx.HTTPError as error:
            logger.warning("Could not fetch WhatsApp media %s, %s", media_id, error)
            return None

        content_type = (
            ref.get("content_type")
            or described.get("mime_type")
            or download.headers.get("content-type", "application/octet-stream")
        ).split(";")[0]
        name = ref.get("filename") or f"{ref.get('kind', 'file')}-{media_id}"
        return download.content, name, content_type

    async def send(self, config: dict, *, to: str, body: str, context: dict | None = None) -> Optional[str]:
        return await self._graph_post(
            f"{config['phone_number_id']}/messages",
            config["access_token"],
            {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": to.lstrip("+"),
                "type": "text",
                "text": {"preview_url": False, "body": body},
            },
        )


class InstagramAdapter(_MetaAdapter):
    name = "instagram"
    label = "Instagram Direct"
    required_keys = ("app_secret", "verify_token", "access_token", "page_id")

    def parse_inbound(self, payload: dict, config: dict) -> list[InboundMessage]:
        results: list[InboundMessage] = []
        page_id = str((config or {}).get("page_id", ""))
        for entry in payload.get("entry", []):
            for event in entry.get("messaging", []):
                message = event.get("message") or {}
                text = message.get("text")
                # Echoes are our own outbound messages coming back.
                if not text or message.get("is_echo"):
                    continue
                sender = str((event.get("sender") or {}).get("id", ""))
                if not sender or sender == page_id:
                    continue
                results.append(
                    InboundMessage(
                        channel=self.name,
                        sender_id=sender,
                        body=text,
                        thread_id=sender,
                        external_id=message.get("mid"),
                        meta={"timestamp": event.get("timestamp")},
                    )
                )
        return results

    async def send(self, config: dict, *, to: str, body: str, context: dict | None = None) -> Optional[str]:
        return await self._graph_post(
            f"{config['page_id']}/messages",
            config["access_token"],
            {"recipient": {"id": to}, "message": {"text": body}},
        )


def _media_refs(message: dict[str, Any]) -> list[dict[str, Any]]:
    """Media on a WhatsApp message, recorded as ids to fetch later."""
    refs: list[dict[str, Any]] = []
    for kind in ("image", "video", "document", "audio", "sticker", "voice"):
        part = message.get(kind)
        if isinstance(part, dict) and part.get("id"):
            refs.append(
                {
                    "media_id": part["id"],
                    "kind": kind,
                    "filename": part.get("filename") or "",
                    "content_type": part.get("mime_type") or "",
                }
            )
    return refs


def _extract_text(message: dict[str, Any]) -> str:
    """Pull readable text out of the several WhatsApp message shapes."""
    kind = message.get("type")
    if kind == "text":
        return (message.get("text") or {}).get("body", "")
    if kind == "button":
        return (message.get("button") or {}).get("text", "")
    if kind == "interactive":
        interactive = message.get("interactive") or {}
        for key in ("button_reply", "list_reply"):
            if key in interactive:
                return interactive[key].get("title", "")
    # Media arrives with an optional caption. The file itself is fetched later.
    for key in ("image", "video", "document", "audio"):
        if key in message:
            return (message[key] or {}).get("caption", "") or f"[{key} attachment]"
    return ""
