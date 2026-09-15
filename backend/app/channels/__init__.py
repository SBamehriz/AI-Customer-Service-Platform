"""Channel registry."""

from __future__ import annotations

from .base import ChannelAdapter, InboundMessage
from .email import EmailAdapter
from .meta import InstagramAdapter, WhatsAppAdapter
from .twilio import SmsAdapter, VoiceAdapter
from .web import ApiAdapter, WebAdapter

ADAPTERS: dict[str, ChannelAdapter] = {
    adapter.name: adapter
    for adapter in (
        WebAdapter(),
        EmailAdapter(),
        WhatsAppAdapter(),
        InstagramAdapter(),
        SmsAdapter(),
        VoiceAdapter(),
        ApiAdapter(),
    )
}


def get_adapter(channel: str) -> ChannelAdapter | None:
    return ADAPTERS.get(channel)


def channel_catalog() -> list[dict]:
    """What the settings UI needs to render the channel list."""
    return [
        {
            "channel": adapter.name,
            "label": adapter.label,
            "requiredKeys": list(adapter.required_keys),
            "hasWebhook": adapter.has_webhook,
            "canSend": adapter.can_send,
        }
        for adapter in ADAPTERS.values()
    ]


__all__ = [
    "ADAPTERS",
    "ChannelAdapter",
    "InboundMessage",
    "channel_catalog",
    "get_adapter",
]
