"""The built in web channels, the embeddable widget and the hosted portal."""

from __future__ import annotations

from .base import ChannelAdapter, InboundMessage


class WebAdapter(ChannelAdapter):
    name = "web"
    label = "Web chat & widget"
    required_keys = ()
    has_webhook = False
    can_send = False

    def parse_inbound(self, payload: dict, config: dict) -> list[InboundMessage]:
        body = (payload.get("body") or "").strip()
        session_id = payload.get("sessionId") or payload.get("session_id") or ""
        if not body or not session_id:
            return []
        return [
            InboundMessage(
                channel=self.name,
                sender_id=session_id,
                sender_name=payload.get("name"),
                sender_email=payload.get("email"),
                body=body,
                thread_id=session_id,
                meta={"page": payload.get("page"), "referrer": payload.get("referrer")},
            )
        ]


class ApiAdapter(ChannelAdapter):
    """Messages pushed in by a customer's own backend using its API key."""

    name = "api"
    label = "API"
    required_keys = ()
    has_webhook = False
    can_send = False

    def parse_inbound(self, payload: dict, config: dict) -> list[InboundMessage]:
        body = (payload.get("body") or "").strip()
        sender = payload.get("senderId") or payload.get("sender_id") or payload.get("email") or ""
        if not body or not sender:
            return []
        return [
            InboundMessage(
                channel=self.name,
                sender_id=str(sender),
                sender_name=payload.get("name"),
                sender_email=payload.get("email"),
                subject=payload.get("subject"),
                body=body,
                thread_id=payload.get("threadId") or str(sender),
                external_id=payload.get("externalId"),
            )
        ]
