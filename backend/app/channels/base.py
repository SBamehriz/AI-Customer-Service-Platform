"""The channel contract."""

from __future__ import annotations

import base64
import hashlib
import hmac
from dataclasses import dataclass, field
from typing import Any, ClassVar, Optional


@dataclass(slots=True)
class InboundMessage:
    """A message from a customer, normalised across every provider."""

    channel: str
    sender_id: str
    body: str
    # Provider side thread key. Messages sharing it continue one conversation.
    thread_id: Optional[str] = None
    sender_name: Optional[str] = None
    sender_email: Optional[str] = None
    sender_phone: Optional[str] = None
    subject: Optional[str] = None
    # Provider message id, which makes webhook redelivery idempotent.
    external_id: Optional[str] = None
    attachments: list[dict[str, Any]] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)


class ChannelAdapter:
    """Base adapter. Subclasses override what their provider actually supports."""

    # Channel identifier, matching CHANNELS in models.py.
    name: ClassVar[str] = "web"
    # Readable label for the settings screen.
    label: ClassVar[str] = "Web"
    # Config keys that have to be present before the channel can be turned on.
    required_keys: ClassVar[tuple[str, ...]] = ()
    # Whether this channel receives provider webhooks.
    has_webhook: ClassVar[bool] = False
    # Whether the platform can send a message back out on this channel.
    can_send: ClassVar[bool] = False

    # inbound

    def verify_signature(self, config: dict, raw_body: bytes, headers: dict[str, str]) -> bool:
        """Reject forged webhooks. The default accepts, for channels with no signing."""
        return True

    def parse_inbound(self, payload: dict, config: dict) -> list[InboundMessage]:
        """Normalise a provider webhook body into zero or more messages."""
        raise NotImplementedError

    async def fetch_attachment(self, config: dict, ref: dict) -> Optional[tuple[bytes, str, str]]:
        """Download one file that `parse_inbound` said was on a message."""
        return None

    # outbound

    async def send(self, config: dict, *, to: str, body: str, context: dict | None = None) -> Optional[str]:
        """Deliver a reply. Returns the provider message id when available."""
        raise NotImplementedError(f"{self.name} cannot send messages")

    # helpers

    def missing_keys(self, config: dict) -> list[str]:
        return [key for key in self.required_keys if not (config or {}).get(key)]

    def is_configured(self, config: dict) -> bool:
        return not self.missing_keys(config)


def verify_hmac_sha256(secret: str, raw_body: bytes, signature: str, prefix: str = "sha256=") -> bool:
    """Constant time check of a hex HMAC SHA256 body signature, the Meta style."""
    if not secret or not signature:
        return False
    if signature.startswith(prefix):
        signature = signature[len(prefix) :]
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def verify_hmac_sha1_b64(secret: str, message: str, signature: str) -> bool:
    """Constant time check of a base64 HMAC SHA1 signature, the Twilio style."""
    if not secret or not signature:
        return False
    digest = hmac.new(secret.encode(), message.encode(), hashlib.sha1).digest()
    return hmac.compare_digest(base64.b64encode(digest).decode(), signature)
