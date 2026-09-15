"""The unified inbox. Conversations and messages across every channel."""

from __future__ import annotations

from typing import Annotated, Optional

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import selectinload

from ..ai import assist
from ..db import utcnow
from ..models import Conversation, Customer, Message, Ticket, Workspace
from ..realtime import hub
from ..schemas import (
    Citation,
    ConversationOut,
    ConversationPatch,
    DraftOut,
    DraftRequest,
    MessageIn,
    MessageOut,
)
from ..security import CurrentUser, DbDep
from ..services import ingest
from .attachments import agent_claim_key, claim_for_message, messages_out, resolve_claimable
from .tickets import like_pattern

router = APIRouter(prefix="/conversations", tags=["conversations"])


async def _load(db, workspace_id: str, conversation_id: str) -> Conversation:
    conversation = await db.scalar(
        select(Conversation)
        .where(Conversation.id == conversation_id, Conversation.workspace_id == workspace_id)
        .options(selectinload(Conversation.messages))
    )
    if conversation is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")
    return conversation


async def _to_out(db, conversation: Conversation, *, with_messages: bool = True) -> ConversationOut:
    data = ConversationOut.model_validate(conversation)
    data.messages = await messages_out(db, conversation.messages) if with_messages else []
    return data


@router.get("", response_model=list[ConversationOut])
async def list_conversations(
    user: CurrentUser,
    db: DbDep,
    status_filter: Annotated[Optional[str], Query(alias="status")] = None,
    channel: Optional[str] = None,
    assigned: Annotated[Optional[str], Query(description="'me' or a user id")] = None,
    search: Optional[str] = None,
    limit: int = Query(default=50, ge=1, le=200),
) -> list[ConversationOut]:
    """Newest first conversation list. Messages are omitted, so fetch one to read it."""
    statement = (
        select(Conversation)
        .where(Conversation.workspace_id == user.workspace_id)
        .options(selectinload(Conversation.messages))
        .order_by(Conversation.last_message_at.desc())
        .limit(limit)
    )
    if status_filter:
        statement = statement.where(Conversation.status == status_filter)
    if channel:
        statement = statement.where(Conversation.channel == channel)
    if assigned == "me":
        statement = statement.where(Conversation.assigned_user_id == user.id)
    elif assigned:
        statement = statement.where(Conversation.assigned_user_id == assigned)

    if search:
        needle = like_pattern(search)
        said_it = select(Message.conversation_id).where(
            Message.workspace_id == user.workspace_id,
            func.lower(Message.body).like(needle, escape="\\"),
        )
        named_them = select(Customer.id).where(
            Customer.workspace_id == user.workspace_id,
            func.lower(func.coalesce(Customer.name, "")).like(needle, escape="\\"),
        )
        statement = statement.where(
            or_(
                func.lower(func.coalesce(Conversation.subject, "")).like(needle, escape="\\"),
                Conversation.id.in_(said_it),
                Conversation.customer_id.in_(named_them),
            )
        )

    conversations = list((await db.execute(statement)).scalars().unique())

    results = []
    for conversation in conversations:
        item = await _to_out(db, conversation, with_messages=False)
        # The list shows a preview line, so send just the latest message.
        if conversation.messages:
            item.messages = await messages_out(db, conversation.messages[-1:])
        results.append(item)
    return results


@router.get("/{conversation_id}", response_model=ConversationOut)
async def get_conversation(conversation_id: str, user: CurrentUser, db: DbDep) -> ConversationOut:
    return await _to_out(db, await _load(db, user.workspace_id, conversation_id))


@router.patch("/{conversation_id}", response_model=ConversationOut)
async def update_conversation(
    conversation_id: str, payload: ConversationPatch, user: CurrentUser, db: DbDep
) -> ConversationOut:
    conversation = await _load(db, user.workspace_id, conversation_id)
    updates = payload.model_dump(exclude_unset=True)
    if "assigned_user_id" in updates:
        wanted = (updates["assigned_user_id"] or "").strip() or None
        if wanted is None:
            updates["assigned_user_id"] = None
        else:
            eligible = await ingest.eligible_assignee(db, user.workspace_id, wanted)
            if eligible is None:
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_CONTENT,
                    "That person is not someone in this workspace who can be assigned work.",
                )
            updates["assigned_user_id"] = eligible
    for field, value in updates.items():
        setattr(conversation, field, value)

    ticket = (
        await db.get(Ticket, conversation.ticket_id) if conversation.ticket_id else None
    )
    if ticket is not None:
        if updates.get("status") == "resolved" and ticket.status not in ("solved", "closed"):
            ticket.status = "solved"
            ticket.resolved_at = utcnow()
        elif (
            updates.get("status") in ("open", "pending", "escalated")
            and ticket.status in ("solved", "closed")
        ):
            ticket.status = "open"
            ticket.resolved_at = None
        if "assigned_user_id" in updates:
            ticket.assigned_user_id = updates["assigned_user_id"]
    await db.flush()
    await hub.publish(
        user.workspace_id,
        "conversation.updated",
        {"conversationId": conversation.id, **updates},
    )
    return await _to_out(db, conversation)


@router.post("/{conversation_id}/messages", response_model=MessageOut, status_code=201)
async def send_message(
    conversation_id: str, payload: MessageIn, user: CurrentUser, db: DbDep
) -> MessageOut:
    """Post an agent reply or an internal note, and deliver it on the channel."""
    if not payload.body.strip() and not payload.attachment_ids:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Write something, or attach a file."
        )
    conversation = await _load(db, user.workspace_id, conversation_id)
    workspace = await db.get(Workspace, user.workspace_id)
    await resolve_claimable(
        db, user.workspace_id, payload.attachment_ids, agent_claim_key(user.id)
    )

    message = Message(
        conversation_id=conversation.id,
        workspace_id=user.workspace_id,
        author_type=payload.author_type,
        author_name=user.name,
        author_user_id=user.id,
        body=payload.body,
        is_private=payload.is_private,
    )
    db.add(message)
    if not payload.is_private:
        conversation.last_message_at = utcnow()
        if conversation.status == "escalated":
            conversation.status = "open"
        if conversation.assigned_user_id is None:
            # Replying is the act of taking ownership.
            conversation.assigned_user_id = user.id
    await db.flush()

    if not payload.is_private and conversation.ticket_id:
        ticket = await db.get(Ticket, conversation.ticket_id)
        if ticket:
            if ticket.first_response_at is None:
                ticket.first_response_at = utcnow()
                if ticket.sla_due_at and ticket.first_response_at > ticket.sla_due_at:
                    ticket.sla_breached = True
            if ticket.status == "new":
                ticket.status = "open"
            if ticket.assigned_user_id is None:
                ticket.assigned_user_id = user.id

    await claim_for_message(
        db,
        user.workspace_id,
        message.id,
        payload.attachment_ids,
        agent_claim_key(user.id),
    )

    delivered = False
    if workspace is not None and not payload.is_private:
        delivered = await ingest.deliver(db, workspace, conversation, message)
    if delivered:
        message.meta = {**(message.meta or {}), "delivered": True}
        await db.flush()

    await hub.publish(
        user.workspace_id,
        "message.created",
        {"conversationId": conversation.id, "messageId": message.id, "authorType": payload.author_type},
    )
    return (await messages_out(db, [message]))[0]


@router.post("/{conversation_id}/draft", response_model=DraftOut)
async def draft_reply(conversation_id: str, user: CurrentUser, db: DbDep) -> DraftOut:
    """Ask the assistant for a grounded reply to the latest customer message."""
    conversation = await _load(db, user.workspace_id, conversation_id)
    workspace = await db.get(Workspace, user.workspace_id)
    if workspace is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Workspace not found")

    draft = await assist.draft_for_conversation(db, workspace, conversation)
    return DraftOut(
        text=draft.text,
        confidence=draft.confidence,
        engine=draft.engine,
        should_escalate=draft.should_escalate,
        citations=[Citation.model_validate(citation) for citation in draft.citations],
    )


@router.post("/draft", response_model=DraftOut)
async def draft_freeform(payload: DraftRequest, user: CurrentUser, db: DbDep) -> DraftOut:
    """Draft an answer to an arbitrary question, without a conversation."""
    workspace = await db.get(Workspace, user.workspace_id)
    if workspace is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Workspace not found")
    if not payload.question:
        raise HTTPException(422, "A question is required")

    draft = await assist.draft_reply(db, workspace, question=payload.question, tone=payload.tone)
    return DraftOut(
        text=draft.text,
        confidence=draft.confidence,
        engine=draft.engine,
        should_escalate=draft.should_escalate,
        citations=[Citation.model_validate(citation) for citation in draft.citations],
    )


@router.get("/stats/overview")
async def inbox_stats(user: CurrentUser, db: DbDep) -> dict[str, int]:
    """Counts for the inbox filter rail."""
    base = select(func.count(Conversation.id)).where(Conversation.workspace_id == user.workspace_id)
    return {
        "open": int(await db.scalar(base.where(Conversation.status == "open")) or 0),
        "escalated": int(await db.scalar(base.where(Conversation.status == "escalated")) or 0),
        "pending": int(await db.scalar(base.where(Conversation.status == "pending")) or 0),
        "mine": int(await db.scalar(base.where(Conversation.assigned_user_id == user.id)) or 0),
        "unassigned": int(await db.scalar(base.where(Conversation.assigned_user_id.is_(None))) or 0),
    }
