"""Datasets, for the tools a business already uses."""

from __future__ import annotations

import csv
import io
from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from typing import Any, Optional

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Conversation, Customer, Message, TapSession, Ticket, User

# The tables on offer, in the order they are most useful.
DATASETS = ("customers", "tickets", "conversations", "messages", "agents", "calls")


_FORMULA_STARTERS = ("=", "+", "-", "@", "\t", "\r")


def _as_text(value: str) -> str:
    """Make a value that a spreadsheet would run into one it will show."""
    return f"'{value}" if value.startswith(_FORMULA_STARTERS) else value


def _cell(value: Any) -> str:
    """One value, written the way a spreadsheet and a warehouse both expect."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, datetime):
        # Naive datetimes are UTC everywhere in this platform, see the model.
        moment = value if value.tzinfo else value.replace(tzinfo=UTC)
        return moment.astimezone(UTC).replace(microsecond=0).isoformat()
    if isinstance(value, str):
        return _as_text(value)
    return str(value)


def to_csv(headers: list[str], rows: Iterable[Iterable[Any]]) -> str:
    buffer = io.StringIO()
    # Excel reads \r\n most reliably, and every other tool accepts it.
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(headers)
    for row in rows:
        writer.writerow([_cell(value) for value in row])
    return buffer.getvalue()


async def build(db: AsyncSession, workspace_id: str, name: str) -> tuple[list[str], list[list[Any]]]:
    """Rows for one dataset. Raises ValueError for an unknown name."""
    builder: Optional[Callable] = _BUILDERS.get(name)
    if builder is None:
        raise ValueError(f"Unknown dataset {name}")
    return await builder(db, workspace_id)


async def _customers(db: AsyncSession, workspace_id: str):
    headers = [
        "customer_id", "name", "email", "phone", "company", "channels", "created_at",
        "total_tickets", "open_tickets", "solved_tickets",
        "average_satisfaction", "first_seen_at", "last_seen_at",
    ]
    rows = []
    customers = (
        await db.execute(
            select(Customer)
            .where(Customer.workspace_id == workspace_id)
            .order_by(Customer.created_at)
        )
    ).scalars()

    for customer in customers:
        stats = (
            await db.execute(
                select(
                    func.count(Ticket.id),
                    func.sum(case((Ticket.status.in_(("solved", "closed")), 1), else_=0)),
                    func.avg(Ticket.satisfaction),
                    func.min(Ticket.created_at),
                    func.max(Ticket.created_at),
                ).where(Ticket.customer_id == customer.id)
            )
        ).one()
        total, solved, satisfaction, first, last = stats
        rows.append(
            [
                customer.id,
                customer.name,
                customer.email,
                customer.phone,
                customer.company,
                ", ".join(sorted((customer.channel_ids or {}).keys())),
                customer.created_at,
                total or 0,
                (total or 0) - (solved or 0),
                solved or 0,
                round(float(satisfaction), 2) if satisfaction is not None else "",
                first,
                last,
            ]
        )
    return headers, rows


async def _tickets(db: AsyncSession, workspace_id: str):
    headers = [
        "ticket_id", "number", "subject", "status", "priority", "channel", "category",
        "customer_id", "customer_email", "assigned_user_id", "assigned_to",
        "ai_handled", "satisfaction", "created_at", "first_response_at", "resolved_at",
        "sla_due_at", "sla_breached",
        "minutes_to_first_response", "minutes_to_resolution",
    ]
    rows = []
    result = await db.execute(
        select(Ticket, Customer.email, User.name)
        .where(Ticket.workspace_id == workspace_id)
        .outerjoin(Customer, Customer.id == Ticket.customer_id)
        .outerjoin(
            User,
            (User.id == Ticket.assigned_user_id) & (User.workspace_id == workspace_id),
        )
        .order_by(Ticket.created_at)
    )
    for ticket, email, agent in result:
        rows.append(
            [
                ticket.id, ticket.number, ticket.subject, ticket.status, ticket.priority,
                ticket.channel, ticket.category, ticket.customer_id, email,
                ticket.assigned_user_id, agent, ticket.ai_handled, ticket.satisfaction,
                ticket.created_at, ticket.first_response_at, ticket.resolved_at,
                ticket.sla_due_at, ticket.sla_breached,
                _minutes(ticket.created_at, ticket.first_response_at),
                _minutes(ticket.created_at, ticket.resolved_at),
            ]
        )
    return headers, rows


async def _conversations(db: AsyncSession, workspace_id: str):
    headers = [
        "conversation_id", "ticket_id", "customer_id", "channel", "status", "subject",
        "assigned_user_id", "created_at", "last_message_at",
        "messages", "customer_messages", "agent_messages", "ai_messages",
    ]
    counts = dict(
        (
            await db.execute(
                select(Message.conversation_id, func.count(Message.id))
                .where(Message.workspace_id == workspace_id)
                .group_by(Message.conversation_id)
            )
        ).all()
    )
    by_author: dict[tuple[str, str], int] = {
        (conversation_id, author): total
        for conversation_id, author, total in (
            await db.execute(
                select(Message.conversation_id, Message.author_type, func.count(Message.id))
                .where(Message.workspace_id == workspace_id)
                .group_by(Message.conversation_id, Message.author_type)
            )
        ).all()
    }

    rows = []
    conversations = (
        await db.execute(
            select(Conversation)
            .where(Conversation.workspace_id == workspace_id)
            .order_by(Conversation.created_at)
        )
    ).scalars()
    for conversation in conversations:
        rows.append(
            [
                conversation.id, conversation.ticket_id, conversation.customer_id,
                conversation.channel, conversation.status, conversation.subject,
                conversation.assigned_user_id, conversation.created_at,
                conversation.last_message_at,
                counts.get(conversation.id, 0),
                by_author.get((conversation.id, "customer"), 0),
                by_author.get((conversation.id, "agent"), 0),
                by_author.get((conversation.id, "ai"), 0),
            ]
        )
    return headers, rows


async def _messages(db: AsyncSession, workspace_id: str):
    headers = [
        "message_id", "conversation_id", "author_type", "author_name", "is_private",
        "characters", "confidence", "engine", "created_at",
    ]
    rows = []
    messages = (
        await db.execute(
            select(Message)
            .where(Message.workspace_id == workspace_id)
            .order_by(Message.created_at)
        )
    ).scalars()
    for message in messages:
        meta = message.meta or {}
        rows.append(
            [
                message.id, message.conversation_id, message.author_type, message.author_name,
                message.is_private, len(message.body or ""),
                meta.get("confidence", ""), meta.get("engine", ""), message.created_at,
            ]
        )
    return headers, rows


async def _agents(db: AsyncSession, workspace_id: str):
    headers = [
        "user_id", "name", "email", "role", "is_active", "created_at",
        "tickets_assigned", "tickets_solved", "average_satisfaction",
        "replies_sent", "median_minutes_to_first_response",
    ]
    rows = []
    members = (
        await db.execute(
            select(User).where(User.workspace_id == workspace_id).order_by(User.created_at)
        )
    ).scalars()

    for member in members:
        tickets = list(
            (
                await db.execute(
                    select(Ticket).where(
                        Ticket.workspace_id == workspace_id,
                        Ticket.assigned_user_id == member.id,
                    )
                )
            ).scalars()
        )
        replies = await db.scalar(
            select(func.count(Message.id)).where(
                Message.workspace_id == workspace_id,
                Message.author_user_id == member.id,
                Message.is_private.is_(False),
            )
        )
        solved = [t for t in tickets if t.status in ("solved", "closed")]
        ratings = [t.satisfaction for t in tickets if t.satisfaction is not None]
        responses = sorted(
            value
            for value in (_minutes(t.created_at, t.first_response_at) for t in tickets)
            if value != ""
        )
        rows.append(
            [
                member.id, member.name, member.email, member.role, member.is_active,
                member.created_at, len(tickets), len(solved),
                round(sum(ratings) / len(ratings), 2) if ratings else "",
                replies or 0,
                responses[len(responses) // 2] if responses else "",
            ]
        )
    return headers, rows


async def _calls(db: AsyncSession, workspace_id: str):
    headers = [
        "session_id", "customer_label", "status", "created_at", "updated_at",
        "transcript_lines", "suggestions", "recording_seconds", "has_recording",
    ]
    rows = []
    sessions = (
        await db.execute(
            select(TapSession)
            .where(TapSession.workspace_id == workspace_id)
            .order_by(TapSession.created_at)
        )
    ).scalars()
    for session in sessions:
        rows.append(
            [
                session.id, session.customer_label, session.status, session.created_at,
                session.updated_at,
                len(session.transcript or []), len(session.suggestions or []),
                session.recording_seconds or 0,
                bool(session.recording_attachment_id),
            ]
        )
    return headers, rows


def _minutes(start, end) -> Any:
    """Whole minutes between two moments, or empty when it never happened."""
    if start is None or end is None:
        return ""
    return round((end - start).total_seconds() / 60)


_BUILDERS = {
    "customers": _customers,
    "tickets": _tickets,
    "conversations": _conversations,
    "messages": _messages,
    "agents": _agents,
    "calls": _calls,
}
