"""SMS and voice through Twilio."""

from __future__ import annotations

import logging
from typing import Optional
from urllib.parse import urlparse

import httpx

from .base import ChannelAdapter, InboundMessage, verify_hmac_sha1_b64

logger = logging.getLogger(__name__)

API_ROOT = "https://api.twilio.com/2010-04-01"

_ALLOWED_MEDIA_HOSTS = ("api.twilio.com", "media.twiliocdn.com", "twiliocdn.com")


def _is_twilio_url(url: str) -> bool:
    """Whether a URL is one of Twilio's own, over TLS."""
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    if parsed.scheme != "https":
        return False
    host = (parsed.hostname or "").lower()
    return any(
        host == allowed or host.endswith(f".{allowed}") for allowed in _ALLOWED_MEDIA_HOSTS
    )

DEFAULT_RECORDING_NOTICE = (
    "This call may be recorded for quality and training purposes."
)


def _mms_media(payload: dict) -> list[dict]:
    """Pictures on an MMS."""
    try:
        count = int(payload.get("NumMedia") or 0)
    except (TypeError, ValueError):
        return []
    refs = []
    for index in range(min(count, 10)):
        url = payload.get(f"MediaUrl{index}")
        if url:
            refs.append(
                {"url": url, "content_type": payload.get(f"MediaContentType{index}", "")}
            )
    return refs


class _TwilioAdapter(ChannelAdapter):
    required_keys = ("account_sid", "auth_token", "from_number")
    has_webhook = True

    def verify_signature(self, config: dict, raw_body: bytes, headers: dict[str, str]) -> bool:
        """Validate the X-Twilio-Signature header over the full URL plus sorted params."""
        token = (config or {}).get("auth_token", "")
        signature = headers.get("x-twilio-signature") or headers.get("X-Twilio-Signature") or ""
        url = headers.get("x-webhook-url", "")
        if not token or not signature or not url:
            return False
        params = _parse_form(raw_body)
        message = url + "".join(f"{key}{params[key]}" for key in sorted(params))
        return verify_hmac_sha1_b64(token, message, signature)


class SmsAdapter(_TwilioAdapter):
    name = "sms"
    label = "SMS"
    can_send = True

    def parse_inbound(self, payload: dict, config: dict) -> list[InboundMessage]:
        body = (payload.get("Body") or "").strip()
        sender = payload.get("From") or ""
        media = _mms_media(payload)
        # A picture message with no text is still worth delivering.
        if not sender or (not body and not media):
            return []
        return [
            InboundMessage(
                channel=self.name,
                sender_id=sender,
                sender_phone=sender,
                body=body,
                thread_id=sender,
                external_id=payload.get("MessageSid"),
                attachments=media,
                meta={"to": payload.get("To")},
            )
        ]

    async def fetch_attachment(self, config: dict, ref: dict) -> Optional[tuple[bytes, str, str]]:
        """Download one MMS image. The media URL needs the account credentials."""
        url = (ref or {}).get("url", "")
        if not _is_twilio_url(url):
            if url:
                logger.warning("Refused to fetch media from outside Twilio, %s", url)
            return None
        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                response = await client.get(
                    url, auth=(config["account_sid"], config["auth_token"])
                )
                response.raise_for_status()
        except (httpx.HTTPError, KeyError) as error:
            logger.warning("Could not fetch Twilio media %s, %s", url, error)
            return None
        content_type = (
            ref.get("content_type") or response.headers.get("content-type", "application/octet-stream")
        ).split(";")[0]
        extension = content_type.split("/")[-1] if "/" in content_type else "bin"
        return response.content, f"mms-{url.rsplit('/', 1)[-1]}.{extension}", content_type

    async def send(self, config: dict, *, to: str, body: str, context: dict | None = None) -> Optional[str]:
        sid = config["account_sid"]
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(
                f"{API_ROOT}/Accounts/{sid}/Messages.json",
                auth=(sid, config["auth_token"]),
                data={"To": to, "From": config["from_number"], "Body": body},
            )
        if response.status_code >= 400:
            logger.warning("SMS send failed %s: %s", response.status_code, response.text[:300])
            return None
        return response.json().get("sid")


class VoiceAdapter(_TwilioAdapter):
    name = "voice"
    label = "Voice"
    can_send = False

    def parse_inbound(self, payload: dict, config: dict) -> list[InboundMessage]:
        """Turn a speech recognition callback into one transcript line."""
        text = (payload.get("SpeechResult") or payload.get("TranscriptionText") or "").strip()
        sender = payload.get("From") or ""
        if not text or not sender:
            return []
        return [
            InboundMessage(
                channel=self.name,
                sender_id=sender,
                sender_phone=sender,
                body=text,
                thread_id=payload.get("CallSid") or sender,
                external_id=payload.get("TranscriptionSid") or payload.get("CallSid"),
                meta={
                    "call_sid": payload.get("CallSid"),
                    "confidence": payload.get("Confidence"),
                    "transcript_line": True,
                },
            )
        ]

    @staticmethod
    def answer_twiml(
        greeting: str,
        action_url: str,
        *,
        record: bool = False,
        recording_callback: str = "",
        notice: str = "",
    ) -> str:
        """TwiML that greets the caller and streams speech back to the platform."""
        parts = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            "<Response>",
        ]
        if record:
            spoken = (notice or "").strip() or DEFAULT_RECORDING_NOTICE
            parts.append(f'<Say voice="Polly.Joanna">{_escape_xml(spoken)}</Say>')
            parts.append(
                '<Start><Recording '
                f'recordingStatusCallback="{_escape_xml(recording_callback)}" '
                'recordingStatusCallbackMethod="POST" '
                'recordingStatusCallbackEvent="completed" '
                '/></Start>'
            )
        parts.append(f'<Say voice="Polly.Joanna">{_escape_xml(greeting)}</Say>')
        parts.append(
            f'<Gather input="speech" speechTimeout="auto" '
            f'action="{_escape_xml(action_url)}" method="POST"></Gather>'
        )
        parts.append("</Response>")
        return "".join(parts)

    async def fetch_recording(self, config: dict, url: str) -> Optional[tuple[bytes, str, str]]:
        """Download a finished recording."""
        if not _is_twilio_url(url):
            if url:
                logger.warning("Refused to fetch a recording from outside Twilio, %s", url)
            return None
        try:
            async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
                response = await client.get(
                    f"{url}.mp3", auth=(config["account_sid"], config["auth_token"])
                )
                response.raise_for_status()
        except (httpx.HTTPError, KeyError) as error:
            logger.warning("Could not fetch the call recording, %s", error)
            return None
        return response.content, f"call-{url.rsplit('/', 1)[-1]}.mp3", "audio/mpeg"


def _parse_form(raw_body: bytes) -> dict[str, str]:
    from urllib.parse import parse_qsl

    return dict(parse_qsl(raw_body.decode("utf-8", "ignore"), keep_blank_values=True))


def _escape_xml(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


__all__ = ["SmsAdapter", "VoiceAdapter"]
