"""Working the queue on its own."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..ai import assist
from ..models import Conversation, Message, Ticket, Workspace, utcnow, workspace_setting
from ..realtime import hub

logger = logging.getLogger(__name__)

MAX_PER_RUN = 25

QUIET_MINUTES = 5


async def run_once(
    db: AsyncSession, workspace: Workspace, *, limit: int = MAX_PER_RUN, trigger: str = "manual"
) -> dict[str, Any]:
    """One pass over the waiting queue. Returns what it did, in plain counts."""
    settings = workspace.settings or {}
    threshold = float(workspace_setting(settings, "ai_suggest_threshold"))

    cutoff = utcnow() - timedelta(minutes=QUIET_MINUTES)
    waiting = list(
        (
            await db.execute(
                select(Conversation)
                .where(
                    Conversation.workspace_id == workspace.id,
                    Conversation.status.in_(("open", "escalated")),
                    # Nobody has picked it up, so nobody is mid reply.
                    Conversation.assigned_user_id.is_(None),
                    Conversation.last_message_at <= cutoff,
                )
                .options(selectinload(Conversation.messages))
                .order_by(Conversation.last_message_at)
                .limit(limit)
            )
        ).scalars()
    )

    result = {
        "lookedAt": len(waiting),
        "answered": 0,
        "escalated": 0,
        "skipped": 0,
        "trigger": trigger,
        "ranAt": utcnow().replace(microsecond=0).isoformat() + "Z",
        "details": [],
    }

    for conversation in waiting:
        messages = [m for m in conversation.messages if not m.is_private]
        if not messages:
            result["skipped"] += 1
            continue

        ticket = (
            await db.get(Ticket, conversation.ticket_id) if conversation.ticket_id else None
        )
        if ticket is not None and ticket.assigned_user_id:
            result["skipped"] += 1
            continue

        last = messages[-1]
        if last.author_type != "customer":
            result["skipped"] += 1
            continue
        # And we do not take a second turn without a reply in between.
        if any(m.author_type == "ai" and m.created_at > last.created_at for m in messages):
            result["skipped"] += 1
            continue

        draft = await assist.draft_for_conversation(
            db, workspace, conversation, include_internal=False
        )

        if draft.should_escalate or draft.confidence < threshold:
            if conversation.status != "escalated":
                conversation.status = "escalated"
                db.add(
                    Message(
                        conversation_id=conversation.id,
                        workspace_id=workspace.id,
                        author_type="system",
                        author_name="Autopilot",
                        body="Autopilot looked at this and left it for a person.",
                        meta={"autopilot": True, "confidence": draft.confidence},
                    )
                )
            result["escalated"] += 1
            result["details"].append(
                {"conversationId": conversation.id, "action": "escalated",
                 "confidence": draft.confidence}
            )
            continue

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
                # Marked, so nobody mistakes a scheduled answer for a live one.
                "autopilot": True,
                "trigger": trigger,
            },
        )
        db.add(reply)
        conversation.last_message_at = utcnow()
        conversation.ai_turns += 1
        conversation.ai_handled = True
        if ticket is not None:
            ticket.ai_handled = True
            ticket.ai_confidence = draft.confidence
            if ticket.first_response_at is None:
                ticket.first_response_at = utcnow()
                if ticket.sla_due_at and ticket.first_response_at > ticket.sla_due_at:
                    ticket.sla_breached = True
            if ticket.status == "new":
                ticket.status = "pending"
        await db.flush()

        from . import ingest

        await ingest.deliver(db, workspace, conversation, reply)
        result["answered"] += 1
        result["details"].append(
            {"conversationId": conversation.id, "action": "answered",
             "confidence": draft.confidence}
        )

    await db.flush()
    if result["answered"] or result["escalated"]:
        await hub.publish(workspace.id, "autopilot.ran", result)
    logger.info(
        "Autopilot %s pass for %s, looked at %s, answered %s, escalated %s",
        trigger, workspace.slug, result["lookedAt"], result["answered"], result["escalated"],
    )
    return result


def hours_from_setting(value: Any) -> set[int]:
    """Parse the configured hours into a set of 0 to 23."""
    if isinstance(value, list):
        return {int(hour) % 24 for hour in value if str(hour).strip().lstrip("-").isdigit()}
    text = str(value or "").strip()
    if not text:
        return set()
    hours: set[int] = set()
    for part in text.replace(" ", "").split(","):
        if "-" in part:
            start, _, end = part.partition("-")
            if start.isdigit() and end.isdigit():
                first, last = int(start) % 24, int(end) % 24
                hours.update(
                    range(first, last + 1)
                    if first <= last
                    else list(range(first, 24)) + list(range(0, last + 1))
                )
        elif part.isdigit():
            hours.add(int(part) % 24)
    return hours


def should_run_now(settings: dict, now: Optional[datetime] = None) -> bool:
    """Whether the schedule says to run in the current hour."""
    if not settings.get("autopilot_enabled"):
        return False
    hours = hours_from_setting(workspace_setting(settings, "autopilot_hours"))
    if not hours:
        return False
    moment = now or datetime.now(UTC)
    return moment.hour in hours
