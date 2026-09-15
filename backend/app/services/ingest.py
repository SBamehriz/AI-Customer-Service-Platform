"""The one path every inbound message takes, whatever channel it came from."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..ai import assist
from ..channels import InboundMessage, get_adapter
from ..db import utcnow
from ..models import (
    ChannelAccount,
    Conversation,
    Customer,
    Message,
    RoutingRule,
    SlaPolicy,
    Ticket,
    User,
    Workspace,
    workspace_setting,
)
from ..realtime import hub

logger = logging.getLogger(__name__)


async def resolve_customer(db: AsyncSession, workspace_id: str, inbound: InboundMessage) -> Customer:
    """Find the person behind a message, or create them."""
    email = (inbound.sender_email or "").lower().strip() or None
    phone = (inbound.sender_phone or "").strip() or None

    if email:
        found = await db.scalar(
            select(Customer).where(Customer.workspace_id == workspace_id, Customer.email == email)
        )
        if found:
            return await _touch(db, found, inbound)

    if phone:
        found = await db.scalar(
            select(Customer).where(Customer.workspace_id == workspace_id, Customer.phone == phone)
        )
        if found:
            return await _touch(db, found, inbound)

    candidates = (
        await db.execute(select(Customer).where(Customer.workspace_id == workspace_id))
    ).scalars()
    for candidate in candidates:
        if (candidate.channel_ids or {}).get(inbound.channel) == inbound.sender_id:
            return await _touch(db, candidate, inbound)

    customer = Customer(
        workspace_id=workspace_id,
        name=inbound.sender_name or email or phone or _anonymous_label(inbound.channel),
        email=email,
        phone=phone,
        channel_ids={inbound.channel: inbound.sender_id},
        last_seen_at=utcnow(),
    )
    db.add(customer)
    await db.flush()
    return customer


async def _touch(db: AsyncSession, customer: Customer, inbound: InboundMessage) -> Customer:
    """Record this channel identity on a known customer and mark them seen."""
    ids = dict(customer.channel_ids or {})
    if ids.get(inbound.channel) != inbound.sender_id:
        ids[inbound.channel] = inbound.sender_id
        customer.channel_ids = ids
    if not customer.email and inbound.sender_email:
        customer.email = inbound.sender_email.lower()
    if not customer.phone and inbound.sender_phone:
        customer.phone = inbound.sender_phone
    if (not customer.name or customer.name in _ANONYMOUS_LABELS.values()) and inbound.sender_name:
        customer.name = inbound.sender_name
    customer.last_seen_at = utcnow()
    await db.flush()
    return customer


async def eligible_assignee(
    db: AsyncSession, workspace_id: str, user_id: Optional[str]
) -> Optional[str]:
    """The id, if it belongs to someone in this workspace who can still work."""
    if not user_id:
        return None
    member = await db.get(User, user_id)
    if member is None or member.workspace_id != workspace_id or not member.is_active:
        return None
    return member.id


def _rule_matches(conditions: dict[str, Any], ticket: Ticket, body: str) -> bool:
    """All conditions must hold. Unknown keys make a rule inert, not crashy."""
    lowered = body.lower()
    for key, expected in (conditions or {}).items():
        if key == "channel" and ticket.channel != expected:
            return False
        if key == "priority" and ticket.priority != expected:
            return False
        if key == "contains" and str(expected).lower() not in lowered:
            return False
        if key == "any_of":
            terms = [str(term).lower() for term in expected or []]
            if terms and not any(term in lowered for term in terms):
                return False
    return True


async def apply_routing(db: AsyncSession, workspace_id: str, ticket: Ticket, body: str) -> None:
    """Run active rules in order. Every match applies, and later ones win."""
    rules = (
        await db.execute(
            select(RoutingRule)
            .where(RoutingRule.workspace_id == workspace_id, RoutingRule.is_active.is_(True))
            .order_by(RoutingRule.order_index)
        )
    ).scalars()

    for rule in rules:
        if not _rule_matches(rule.conditions or {}, ticket, body):
            continue
        actions = rule.actions or {}
        if priority := actions.get("priority"):
            ticket.priority = priority
        if category := actions.get("category"):
            ticket.category = category
        if assignee := actions.get("assign_user_id"):
            eligible = await eligible_assignee(db, workspace_id, assignee)
            if eligible is None:
                logger.warning(
                    "Routing rule %s names a user who is not in this workspace", rule.name
                )
            else:
                ticket.assigned_user_id = eligible
        if tags := actions.get("add_tags"):
            merged = list(dict.fromkeys([*(ticket.tags or []), *tags]))
            ticket.tags = merged


async def apply_sla(db: AsyncSession, workspace_id: str, ticket: Ticket) -> None:
    """Set the first response deadline from the policy covering this priority."""
    policies = (
        await db.execute(
            select(SlaPolicy).where(
                SlaPolicy.workspace_id == workspace_id, SlaPolicy.is_active.is_(True)
            )
        )
    ).scalars()
    for policy in policies:
        if ticket.priority in (policy.priorities or []):
            ticket.sla_due_at = ticket.created_at + timedelta(minutes=policy.first_response_minutes)
            return


async def next_ticket_number(db: AsyncSession, workspace_id: str) -> int:
    highest = await db.scalar(
        select(func.max(Ticket.number)).where(Ticket.workspace_id == workspace_id)
    )
    return int(highest or 0) + 1


async def find_conversation(
    db: AsyncSession, workspace_id: str, inbound: InboundMessage
) -> Optional[Conversation]:
    """Continue an open thread on the same channel, if there is one."""
    if not inbound.thread_id:
        return None
    return await db.scalar(
        select(Conversation)
        .where(
            Conversation.workspace_id == workspace_id,
            Conversation.channel == inbound.channel,
            Conversation.channel_thread_id == inbound.thread_id,
            Conversation.status.in_(("open", "pending", "escalated")),
        )
        .order_by(Conversation.last_message_at.desc())
    )


async def already_ingested(
    db: AsyncSession, workspace_id: str, external_id: Optional[str]
) -> bool:
    """Providers retry webhooks, so the same provider id must not post twice."""
    if not external_id:
        return False
    existing = await db.scalar(
        select(Message.id).where(
            Message.workspace_id == workspace_id, Message.external_id == external_id
        )
    )
    return existing is not None


async def ingest(
    db: AsyncSession,
    workspace: Workspace,
    inbound: InboundMessage,
    *,
    auto_reply: Optional[bool] = None,
) -> tuple[Conversation, Message, Optional[Message]]:
    """Persist an inbound message and, when enabled, the AI's reply."""
    settings_map = workspace.settings or {}
    customer = await resolve_customer(db, workspace.id, inbound)
    conversation = await find_conversation(db, workspace.id, inbound)
    is_new_conversation = conversation is None

    if conversation is None:
        conversation = Conversation(
            workspace_id=workspace.id,
            customer_id=customer.id,
            channel=inbound.channel,
            channel_thread_id=inbound.thread_id,
            subject=inbound.subject or _derive_subject(inbound.body),
            status="open",
            last_message_at=utcnow(),
        )
        conversation.customer = customer
        db.add(conversation)
        await db.flush()

    message = Message(
        conversation_id=conversation.id,
        workspace_id=workspace.id,
        author_type="customer",
        author_name=customer.name,
        body=inbound.body,
        external_id=inbound.external_id,
        meta={"channel": inbound.channel, **(inbound.meta or {})},
    )
    db.add(message)
    conversation.last_message_at = utcnow()
    if conversation.status == "resolved":
        conversation.status = "open"
    await db.flush()

    await _store_attachments(db, workspace, conversation, message, inbound)

    ticket = await _ensure_ticket(db, workspace, conversation, customer, inbound, is_new_conversation)

    await hub.publish(
        workspace.id,
        "conversation.created" if is_new_conversation else "message.created",
        {"conversationId": conversation.id, "messageId": message.id, "channel": inbound.channel},
    )

    should_reply = (
        workspace_setting(settings_map, "ai_autoreply") if auto_reply is None else auto_reply
    )
    reply: Optional[Message] = None
    if should_reply:
        reply = await _auto_reply(db, workspace, conversation, ticket, inbound)

    return conversation, message, reply


async def _store_attachments(db, workspace, conversation, message, inbound) -> None:
    """Save the files that came with an inbound message."""
    from .. import storage
    from ..api.attachments import store_bytes
    from ..channels import get_adapter

    refs = list(inbound.attachments or [])
    if not refs:
        return

    adapter = get_adapter(inbound.channel)
    account = await db.scalar(
        select(ChannelAccount).where(
            ChannelAccount.workspace_id == workspace.id,
            ChannelAccount.channel == inbound.channel,
        )
    )
    config = account.live_config() if account else {}

    for ref in refs[:10]:
        try:
            payload = ref.get("inline_bytes")
            if payload is not None:
                filename = ref.get("filename", "attachment")
                content_type = ref.get("content_type", "application/octet-stream")
            else:
                if adapter is None:
                    continue
                fetched = await adapter.fetch_attachment(config, ref)
                if fetched is None:
                    continue
                payload, filename, content_type = fetched

            if len(payload) > storage.MAX_BYTES:
                logger.info("Skipped an oversized inbound %s attachment", inbound.channel)
                continue
            reason = storage.rejection_reason(filename, content_type, payload)
            if reason:
                logger.info(
                    "Skipped an inbound %s attachment, %s", inbound.channel, reason
                )
                continue

            await store_bytes(
                db,
                workspace_id=workspace.id,
                payload=payload,
                filename=filename,
                content_type=content_type,
                source=inbound.channel,
                message_id=message.id,
            )
        except Exception:
            logger.exception("Could not store an inbound attachment on %s", inbound.channel)


async def _ensure_ticket(
    db: AsyncSession,
    workspace: Workspace,
    conversation: Conversation,
    customer: Customer,
    inbound: InboundMessage,
    is_new_conversation: bool,
) -> Optional[Ticket]:
    """Open a ticket for a new thread, and leave an existing one alone."""
    if conversation.ticket_id:
        return await db.get(Ticket, conversation.ticket_id)
    if not is_new_conversation:
        return None

    ticket = Ticket(
        workspace_id=workspace.id,
        number=await next_ticket_number(db, workspace.id),
        subject=conversation.subject or _derive_subject(inbound.body),
        description=inbound.body,
        customer_id=customer.id,
        status="new",
        priority="medium",
        channel=inbound.channel,
        tags=[],
    )
    ticket.customer = customer
    db.add(ticket)
    await db.flush()

    await apply_routing(db, workspace.id, ticket, inbound.body)
    await apply_sla(db, workspace.id, ticket)
    conversation.ticket_id = ticket.id
    if ticket.assigned_user_id and conversation.assigned_user_id is None:
        conversation.assigned_user_id = ticket.assigned_user_id
    await db.flush()

    await hub.publish(workspace.id, "ticket.created", {"ticketId": ticket.id, "number": ticket.number})
    return ticket


async def _auto_reply(
    db: AsyncSession,
    workspace: Workspace,
    conversation: Conversation,
    ticket: Optional[Ticket],
    inbound: InboundMessage,
) -> Optional[Message]:
    """Answer with AI when the knowledge base actually covers the question."""
    settings_map = workspace.settings or {}
    max_turns = int(workspace_setting(settings_map, "escalate_after_ai_turns"))
    if conversation.ai_turns >= max_turns:
        await _escalate(db, workspace, conversation, ticket, "AI turn limit reached")
        return None

    history = list(
        (
            await db.execute(
                select(Message)
                .where(Message.conversation_id == conversation.id)
                .order_by(Message.created_at)
            )
        ).scalars()
    )
    draft = await assist.draft_reply(
        db,
        workspace,
        question=inbound.body,
        history=history,
        # Customers must never be shown internal only articles.
        include_internal=False,
    )

    threshold = float(workspace_setting(settings_map, "ai_suggest_threshold"))
    if draft.should_escalate or draft.confidence < threshold or not draft.text:
        await _escalate(db, workspace, conversation, ticket, "Below confidence threshold")
        return None

    reply = Message(
        conversation_id=conversation.id,
        workspace_id=workspace.id,
        author_type="ai",
        author_name="AI Assistant",
        body=draft.text,
        meta={
            "confidence": draft.confidence,
            "engine": draft.engine,
            "citations": draft.citations,
        },
    )
    db.add(reply)
    conversation.ai_turns += 1
    conversation.ai_handled = True
    conversation.last_message_at = utcnow()
    if ticket is not None:
        ticket.ai_handled = True
        ticket.ai_confidence = draft.confidence
        if ticket.first_response_at is None:
            ticket.first_response_at = utcnow()
        if ticket.status == "new":
            ticket.status = "pending"
    await db.flush()

    await deliver(db, workspace, conversation, reply)
    await hub.publish(
        workspace.id,
        "message.created",
        {"conversationId": conversation.id, "messageId": reply.id, "authorType": "ai"},
    )
    return reply


async def _escalate(
    db: AsyncSession,
    workspace: Workspace,
    conversation: Conversation,
    ticket: Optional[Ticket],
    reason: str,
) -> None:
    """Hand the thread to a human and leave a note saying why."""
    conversation.status = "escalated"
    db.add(
        Message(
            conversation_id=conversation.id,
            workspace_id=workspace.id,
            author_type="system",
            author_name="System",
            body=f"Escalated to a human agent, {reason}.",
            is_private=True,
            meta={"reason": reason},
        )
    )
    if ticket is not None and ticket.status == "new":
        ticket.status = "open"
    await db.flush()
    await hub.publish(
        workspace.id,
        "conversation.updated",
        {"conversationId": conversation.id, "status": "escalated", "reason": reason},
    )


async def deliver(
    db: AsyncSession, workspace: Workspace, conversation: Conversation, message: Message
) -> bool:
    """Push a reply back out on the channel it arrived on."""
    if message.is_private:
        return False
    adapter = get_adapter(conversation.channel)
    if adapter is None or not adapter.can_send:
        return False

    account = await db.scalar(
        select(ChannelAccount).where(
            ChannelAccount.workspace_id == workspace.id,
            ChannelAccount.channel == conversation.channel,
            ChannelAccount.is_active.is_(True),
        )
    )
    if account is None or not adapter.is_configured(account.live_config()):
        logger.info("No active %s account, reply stored but not delivered", conversation.channel)
        return False

    customer = await db.get(Customer, conversation.customer_id) if conversation.customer_id else None
    recipient = _recipient_for(conversation, customer)
    if not recipient:
        return False

    try:
        external_id = await adapter.send(
            account.live_config(),
            to=recipient,
            body=message.body,
            context={
                "subject": conversation.subject,
                "thread_id": conversation.channel_thread_id,
                "from_name": workspace.name,
            },
        )
    except Exception as exc:  # noqa: BLE001, a provider outage must not lose the message
        logger.warning("Delivery on %s failed: %s", conversation.channel, exc)
        return False

    if external_id:
        message.external_id = external_id
        await db.flush()
    account.last_event_at = utcnow()
    return bool(external_id)


def _recipient_for(conversation: Conversation, customer: Optional[Customer]) -> Optional[str]:
    channel = conversation.channel
    ids = (customer.channel_ids or {}) if customer else {}
    if channel == "email":
        return (customer.email if customer else None) or ids.get("email")
    if channel in ("sms", "voice", "whatsapp"):
        return ids.get(channel) or (customer.phone if customer else None)
    if channel == "instagram":
        return ids.get("instagram")
    return None


_ANONYMOUS_LABELS = {
    "web": "Website visitor",
    "api": "API contact",
    "voice": "Caller",
}


def _anonymous_label(channel: str) -> str:
    """A readable stand in when a channel gives us no name, email or number."""
    return _ANONYMOUS_LABELS.get(channel, "Unknown")


def _derive_subject(body: str, limit: int = 80) -> str:
    """First sentence of the message, used when a channel carries no subject."""
    flat = " ".join((body or "").split())
    if not flat:
        return "New conversation"
    for terminator in (". ", "? ", "! "):
        index = flat.find(terminator)
        if 0 < index <= limit:
            return flat[: index + 1].strip()
    return flat[:limit] + ("..." if len(flat) > limit else "")
