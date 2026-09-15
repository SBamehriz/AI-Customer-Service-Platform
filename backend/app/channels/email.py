"""Email, both directions, using only the standard library."""

from __future__ import annotations

import asyncio
import email
import imaplib
import logging
import smtplib
from email.message import EmailMessage
from email.utils import formataddr, make_msgid, parseaddr
from typing import Any, Optional

from .base import ChannelAdapter, InboundMessage

logger = logging.getLogger(__name__)


class EmailAdapter(ChannelAdapter):
    name = "email"
    label = "Email"
    required_keys = ("smtp_host", "smtp_port", "from_address")
    has_webhook = True
    can_send = True

    # inbound

    def verify_signature(self, config: dict, raw_body: bytes, headers: dict[str, str]) -> bool:
        """Inbound relays authenticate with a shared secret in the X-Webhook-Token header."""
        expected = (config or {}).get("webhook_secret", "")
        if not expected:
            return True
        import hmac

        provided = headers.get("x-webhook-token") or headers.get("X-Webhook-Token") or ""
        return hmac.compare_digest(expected, provided)

    def parse_inbound(self, payload: dict, config: dict) -> list[InboundMessage]:
        """Normalise the three common inbound parse shapes into one message."""
        sender_raw = (
            payload.get("From")
            or payload.get("from")
            or payload.get("sender")
            or payload.get("FromFull", {}).get("Email", "")
        )
        name, address = parseaddr(str(sender_raw))
        body = (
            payload.get("TextBody")
            or payload.get("text")
            or payload.get("body-plain")
            or payload.get("plain")
            or ""
        ).strip()
        subject = payload.get("Subject") or payload.get("subject") or ""
        if not address or not body:
            return []

        headers = payload.get("Headers") or {}
        references = (
            payload.get("References")
            or payload.get("references")
            or (headers.get("References") if isinstance(headers, dict) else None)
            or ""
        )
        in_reply_to = (
            payload.get("InReplyTo")
            or payload.get("in-reply-to")
            or (headers.get("In-Reply-To") if isinstance(headers, dict) else None)
            or ""
        )
        thread_id = _root_reference(str(references), str(in_reply_to)) or address

        return [
            InboundMessage(
                channel=self.name,
                sender_id=address.lower(),
                sender_name=name or None,
                sender_email=address.lower(),
                subject=subject or None,
                body=_strip_quoted_reply(body),
                thread_id=thread_id,
                external_id=payload.get("MessageID") or payload.get("Message-Id") or payload.get("message-id"),
                meta={"to": payload.get("To") or payload.get("to")},
            )
        ]

    async def fetch_imap(self, config: dict, limit: int = 25) -> list[InboundMessage]:
        """Pull unread mail from a shared mailbox."""
        if not all(config.get(key) for key in ("imap_host", "imap_user", "imap_password")):
            return []
        return await asyncio.to_thread(self._fetch_imap_sync, config, limit)

    def _fetch_imap_sync(self, config: dict, limit: int) -> list[InboundMessage]:
        messages: list[InboundMessage] = []
        try:
            with imaplib.IMAP4_SSL(config["imap_host"], int(config.get("imap_port", 993))) as client:
                client.login(config["imap_user"], config["imap_password"])
                client.select(config.get("imap_folder", "INBOX"))
                status, data = client.search(None, "UNSEEN")
                if status != "OK":
                    return []
                for uid in (data[0].split() or [])[:limit]:
                    status, raw = client.fetch(uid, "(RFC822)")
                    if status != "OK" or not raw or not isinstance(raw[0], tuple):
                        continue
                    parsed = email.message_from_bytes(raw[0][1])
                    normalised = self._from_rfc822(parsed)
                    if normalised:
                        messages.append(normalised)
                    # Marking as seen is what stops the next poll ingesting it again.
                    client.store(uid, "+FLAGS", "\\Seen")
        except (imaplib.IMAP4.error, OSError) as exc:
            logger.warning("IMAP poll failed: %s", exc)
        return messages

    def _from_rfc822(self, parsed: email.message.Message) -> Optional[InboundMessage]:
        name, address = parseaddr(parsed.get("From", ""))
        if not address:
            return None
        body = _plain_text_part(parsed)
        files = _attachment_parts(parsed)
        # An email that is only a photo or a scanned PDF is still a message.
        if not body and not files:
            return None
        thread_id = _root_reference(parsed.get("References", ""), parsed.get("In-Reply-To", ""))
        return InboundMessage(
            channel=self.name,
            sender_id=address.lower(),
            sender_name=name or None,
            sender_email=address.lower(),
            subject=parsed.get("Subject") or None,
            body=_strip_quoted_reply(body),
            thread_id=thread_id or address.lower(),
            external_id=parsed.get("Message-ID"),
            attachments=files,
        )

    # outbound

    async def send(self, config: dict, *, to: str, body: str, context: dict | None = None) -> Optional[str]:
        return await asyncio.to_thread(self._send_sync, config, to, body, context or {})

    def _send_sync(self, config: dict, to: str, body: str, context: dict[str, Any]) -> Optional[str]:
        message = EmailMessage()
        message["Subject"] = context.get("subject") or "Re: your request"
        message["From"] = formataddr((context.get("from_name") or "Support", config["from_address"]))
        message["To"] = to
        message_id = make_msgid()
        message["Message-ID"] = message_id
        # Threading headers keep the reply in the customer's existing thread.
        if context.get("thread_id"):
            message["In-Reply-To"] = context["thread_id"]
            message["References"] = context["thread_id"]
        message.set_content(body)

        host = config["smtp_host"]
        port = int(config.get("smtp_port", 587))
        try:
            if port == 465:
                server: smtplib.SMTP = smtplib.SMTP_SSL(host, port, timeout=20)
            else:
                server = smtplib.SMTP(host, port, timeout=20)
            with server:
                if port != 465:
                    server.starttls()
                if config.get("smtp_user"):
                    server.login(config["smtp_user"], config.get("smtp_password", ""))
                server.send_message(message)
        except (smtplib.SMTPException, OSError) as exc:
            logger.warning("SMTP send failed: %s", exc)
            return None
        return message_id


def _attachment_parts(parsed: email.message.Message) -> list[dict]:
    """Files carried by an email."""
    if not parsed.is_multipart():
        return []
    parts: list[dict] = []
    for part in parsed.walk():
        if part.get_content_maintype() == "multipart":
            continue
        disposition = str(part.get("Content-Disposition", ""))
        filename = part.get_filename()
        if "attachment" not in disposition and not filename:
            continue
        payload = part.get_payload(decode=True)
        if not payload:
            continue
        parts.append(
            {
                "inline_bytes": payload,
                "filename": filename or "attachment",
                "content_type": part.get_content_type(),
            }
        )
    return parts


def _plain_text_part(parsed: email.message.Message) -> str:
    if parsed.is_multipart():
        for part in parsed.walk():
            if part.get_content_type() == "text/plain" and "attachment" not in str(
                part.get("Content-Disposition", "")
            ):
                payload = part.get_payload(decode=True) or b""
                return payload.decode(part.get_content_charset() or "utf-8", "replace")
        return ""
    payload = parsed.get_payload(decode=True) or b""
    return payload.decode(parsed.get_content_charset() or "utf-8", "replace")


def _root_reference(references: str, in_reply_to: str) -> Optional[str]:
    """The first id in References, which is the thread root, else In-Reply-To."""
    for candidate in (references or "").split():
        if candidate.startswith("<"):
            return candidate
    stripped = (in_reply_to or "").strip()
    return stripped or None


# Lines that start a quoted reply. Everything after them is the old thread.
_QUOTE_MARKERS = ("-----Original Message-----", "________________________________")


def _strip_quoted_reply(body: str) -> str:
    """Drop the quoted history so agents read the new content, not the thread."""
    lines: list[str] = []
    for line in body.splitlines():
        stripped = line.strip()
        if any(stripped.startswith(marker) for marker in _QUOTE_MARKERS):
            break
        if stripped.startswith("On ") and stripped.endswith("wrote:"):
            break
        if stripped.startswith(">"):
            continue
        lines.append(line)
    return "\n".join(lines).strip() or body.strip()
