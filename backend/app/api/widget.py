"""Public endpoints for the embeddable widget and the hosted customer portal."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from ..ai.providers import get_provider
from ..channels import get_adapter
from ..models import Conversation, Workspace, new_id, workspace_setting
from ..ratelimit import widget_addresses, widget_messages
from ..schemas import (
    MessageOut,
    WidgetBootstrap,
    WidgetMessageIn,
    WidgetMessageOut,
)
from ..security import DbDep
from ..services import ingest
from .attachments import claim_for_message, messages_out, resolve_claimable, visitor_claim_key

router = APIRouter(prefix="/widget", tags=["widget"])


# Lets the hosted portal find its workspace without being handed a key.
DEFAULT_KEY = "default"


async def _workspace(db, public_key: str) -> Workspace:
    if public_key == DEFAULT_KEY:
        rows = (await db.execute(select(Workspace).limit(2))).scalars().all()
        if len(rows) == 1:
            return rows[0]
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "This install has more than one workspace, so a workspace key is required",
        )

    workspace = await db.scalar(select(Workspace).where(Workspace.public_key == public_key))
    if workspace is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown workspace key")
    return workspace


@router.get("/{public_key}/config", response_model=WidgetBootstrap)
async def bootstrap(public_key: str, db: DbDep) -> WidgetBootstrap:
    """Branding and greeting, fetched once when the widget loads."""
    workspace = await _workspace(db, public_key)
    config = workspace.settings or {}
    return WidgetBootstrap(
        public_key=workspace.public_key,
        workspace_name=workspace.name,
        accent_color=workspace.accent_color,
        greeting=workspace_setting(config, "greeting"),
        logo_url=workspace.logo_url,
        ai_enabled=get_provider(workspace).available,
    )


@router.post("/{public_key}/messages", response_model=WidgetMessageOut)
async def post_message(
    public_key: str, payload: WidgetMessageIn, request: Request, db: DbDep
) -> WidgetMessageOut:
    """Send a customer message and return the AI reply when there is one."""
    workspace = await _workspace(db, public_key)
    session_id = payload.session_id or f"web_{new_id()}"

    address = request.client.host if request.client else "unknown"
    over_session = not widget_messages.allow(f"{workspace.id}:{session_id}")
    over_address = not widget_addresses.allow(f"{workspace.id}:{address}")
    if over_session or over_address:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Too many messages, please wait a moment before sending another.",
        )

    await resolve_claimable(
        db, workspace.id, payload.attachment_ids, visitor_claim_key(session_id)
    )

    adapter = get_adapter("web")
    if adapter is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Web channel unavailable")
    inbound = adapter.parse_inbound(
        {
            "sessionId": session_id,
            "body": payload.body or ("Sent a file" if payload.attachment_ids else ""),
            "name": payload.name,
            "email": payload.email,
        },
        {},
    )
    if not inbound:
        raise HTTPException(422, "Empty message")

    conversation, inbound_message, reply = await ingest.ingest(db, workspace, inbound[0])
    await claim_for_message(
        db,
        workspace.id,
        inbound_message.id,
        payload.attachment_ids,
        visitor_claim_key(session_id),
    )
    return WidgetMessageOut(
        session_id=session_id,
        conversation_id=conversation.id,
        reply=(await messages_out(db, [reply]))[0] if reply else None,
        escalated=conversation.status == "escalated",
    )


@router.get("/{public_key}/sessions/{session_id}", response_model=list[MessageOut])
async def session_messages(public_key: str, session_id: str, db: DbDep) -> list[MessageOut]:
    """Replay a widget thread. Internal notes are never exposed here."""
    workspace = await _workspace(db, public_key)
    conversation = await db.scalar(
        select(Conversation)
        .where(
            Conversation.workspace_id == workspace.id,
            Conversation.channel == "web",
            Conversation.channel_thread_id == session_id,
        )
        .options(selectinload(Conversation.messages))
        .order_by(Conversation.last_message_at.desc())
    )
    if conversation is None:
        return []
    return await messages_out(
        db, [message for message in conversation.messages if not message.is_private]
    )
