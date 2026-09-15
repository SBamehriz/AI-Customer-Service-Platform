"""Uploading and serving files."""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import Response
from sqlalchemy import select

from .. import storage
from ..models import Attachment, Conversation, Message, new_id
from ..ratelimit import widget_uploads
from ..schemas import AttachmentOut, MessageOut, WidgetAttachmentOut
from ..security import (
    CredentialsDep,
    CurrentUser,
    DbDep,
    current_user,
    sign_download,
    verify_download,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["attachments"])


def _out(attachment: Attachment) -> AttachmentOut:
    return AttachmentOut(
        id=attachment.id,
        filename=attachment.filename,
        content_type=attachment.content_type,
        size_bytes=attachment.size_bytes,
        kind=storage.kind_of(attachment.content_type),
        # Signed, because a browser cannot put a header on an img tag.
        url=f"/api/v1/attachments/{attachment.id}?t={sign_download(attachment.id)}",
        created_at=attachment.created_at,
    )


async def store_upload(
    db,
    workspace_id: str,
    upload: UploadFile,
    source: str,
    message_id: Optional[str] = None,
    claim_key: Optional[str] = None,
) -> Attachment:
    """Validate and save one uploaded file. Shared by every entry point."""
    content_type = (upload.content_type or "application/octet-stream").split(";")[0].strip()
    filename = upload.filename or "file"

    payload = await upload.read()
    if len(payload) > storage.MAX_BYTES:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            f"That file is larger than the {storage.MAX_BYTES // (1024 * 1024)} MB limit.",
        )
    if not payload:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "That file is empty.")

    reason = storage.rejection_reason(filename, content_type, payload)
    if reason:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, reason)

    return await store_bytes(
        db,
        workspace_id=workspace_id,
        payload=payload,
        filename=filename,
        content_type=content_type,
        source=source,
        message_id=message_id,
        claim_key=claim_key,
    )


async def store_bytes(
    db,
    *,
    workspace_id: str,
    payload: bytes,
    filename: str,
    content_type: str,
    source: str,
    message_id: Optional[str] = None,
    claim_key: Optional[str] = None,
) -> Attachment:
    """Save bytes we already hold, which is how channel media arrives."""
    attachment_id = new_id()
    relative = storage.build_path(workspace_id, attachment_id, content_type, filename)
    storage.write(str(relative), payload)

    attachment = Attachment(
        id=attachment_id,
        workspace_id=workspace_id,
        message_id=message_id,
        filename=storage.clean_filename(filename, content_type),
        content_type=content_type,
        size_bytes=len(payload),
        storage_path=str(relative),
        source=source,
        claim_key=claim_key,
    )
    db.add(attachment)
    await db.flush()
    return attachment


async def messages_out(db, messages) -> list[MessageOut]:
    """Serialise messages with their files, in one query rather than N."""
    rows = list(messages)
    if not rows:
        return []
    found = (
        await db.execute(
            select(Attachment)
            .where(Attachment.message_id.in_([m.id for m in rows]))
            .order_by(Attachment.created_at)
        )
    ).scalars()

    by_message: dict[str, list[AttachmentOut]] = {}
    for attachment in found:
        by_message.setdefault(attachment.message_id, []).append(_out(attachment))

    result = []
    for message in rows:
        item = MessageOut.model_validate(message)
        item.attachments = by_message.get(message.id, [])
        result.append(item)
    return result


def agent_claim_key(user_id: str) -> str:
    """The claim key on a file uploaded from the composer."""
    return f"user:{user_id}"


def visitor_claim_key(session_id: str) -> str:
    """The claim key on a file uploaded from the widget or the portal."""
    return f"session:{session_id}"


async def resolve_claimable(
    db, workspace_id: str, ids: list[str], claim_key: str
) -> list[Attachment]:
    """The files behind these ids, or a refusal naming the ones that are not."""
    if not ids:
        return []
    wanted = list(dict.fromkeys(ids))
    rows = list(
        (
            await db.execute(
                select(Attachment).where(
                    Attachment.id.in_(wanted),
                    Attachment.workspace_id == workspace_id,
                    Attachment.message_id.is_(None),
                    Attachment.claim_key == claim_key,
                )
            )
        ).scalars()
    )
    found = {attachment.id for attachment in rows}
    missing = [value for value in wanted if value not in found]
    if missing:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"No uploaded file to attach for {', '.join(missing)}. Upload the "
            "file again and send it with this message.",
        )
    return rows


async def claim_for_message(
    db, workspace_id: str, message_id: str, ids: list[str], claim_key: str
) -> list[Attachment]:
    """Point already uploaded files at the message that is being sent."""
    rows = await resolve_claimable(db, workspace_id, ids, claim_key)
    for attachment in rows:
        attachment.message_id = message_id
    await db.flush()
    return rows


@router.post(
    "/attachments", response_model=AttachmentOut, status_code=status.HTTP_201_CREATED
)
async def upload(user: CurrentUser, db: DbDep, file: UploadFile = File(...)) -> AttachmentOut:
    """An agent attaches a file, before the message that carries it is sent."""
    return _out(
        await store_upload(
            db,
            user.workspace_id,
            file,
            source="agent",
            claim_key=agent_claim_key(user.id),
        )
    )


@router.post(
    "/widget/{public_key}/attachments",
    response_model=WidgetAttachmentOut,
    status_code=status.HTTP_201_CREATED,
)
async def widget_upload(
    public_key: str,
    request: Request,
    db: DbDep,
    file: UploadFile = File(...),
    session_id: str = Form(default="", alias="sessionId"),
) -> WidgetAttachmentOut:
    """A customer attaches a file in the web chat or the embedded widget."""
    from .widget import _workspace

    workspace = await _workspace(db, public_key)
    address = request.client.host if request.client else "unknown"
    if not widget_uploads.allow(f"{workspace.id}:{address}"):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Too many uploads, please wait a moment before sending another file.",
        )
    session = session_id.strip() or f"web_{new_id()}"
    stored = await store_upload(
        db,
        workspace.id,
        file,
        source="web",
        claim_key=visitor_claim_key(session),
    )
    return WidgetAttachmentOut(**_out(stored).model_dump(), session_id=session)


@router.get("/attachments/{attachment_id}")
async def download(
    attachment_id: str,
    db: DbDep,
    credentials: CredentialsDep,
    t: str = "",
) -> Response:
    """Serve a file to someone who may see it."""
    attachment = await db.get(Attachment, attachment_id)
    if attachment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Attachment not found")

    if t and verify_download(attachment_id, t):
        return _serve(attachment)

    if credentials is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Sign in, or use a link from the interface.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = await current_user(credentials, db)
    if attachment.workspace_id != user.workspace_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Attachment not found")
    return _serve(attachment)


@router.get("/widget/{public_key}/sessions/{session_id}/attachments/{attachment_id}")
async def widget_download(
    public_key: str, session_id: str, attachment_id: str, db: DbDep
) -> Response:
    """Serve a file back to the customer whose own session it belongs to."""
    from .widget import _workspace

    workspace = await _workspace(db, public_key)
    attachment = await db.get(Attachment, attachment_id)
    if attachment is None or attachment.workspace_id != workspace.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Attachment not found")

    owner = await db.scalar(
        select(Conversation.id)
        .join(Message, Message.conversation_id == Conversation.id)
        .where(
            Message.id == attachment.message_id,
            Message.is_private.is_(False),
            Conversation.workspace_id == workspace.id,
            Conversation.channel == "web",
            Conversation.channel_thread_id == session_id,
        )
        .limit(1)
    )
    if owner is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Attachment not found")
    return _serve(attachment)


def _serve(attachment: Attachment) -> Response:
    payload = storage.read(attachment.storage_path)
    if payload is None:
        raise HTTPException(
            status.HTTP_410_GONE,
            "The record of this file is here but the file itself is missing from disk.",
        )
    kind = storage.kind_of(attachment.content_type)
    disposition = "inline" if kind in ("image", "audio", "video") else "attachment"
    return Response(
        content=payload,
        media_type=attachment.content_type,
        headers={
            "Content-Disposition": f'{disposition}; filename="{attachment.filename}"',
            "Content-Security-Policy": "default-src 'none'; sandbox",
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, max-age=3600",
        },
    )
