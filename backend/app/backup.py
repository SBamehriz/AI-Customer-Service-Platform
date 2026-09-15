"""Keeping the data safe, and keeping it yours."""

from __future__ import annotations

import asyncio
import logging
import sqlite3
import zipfile
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from . import storage
from .config import BACKEND_DIR, settings
from .models import (
    Article,
    Attachment,
    ChannelAccount,
    Conversation,
    Customer,
    Macro,
    Message,
    RoutingRule,
    SlaPolicy,
    TapSession,
    Ticket,
    User,
    Workspace,
)

logger = logging.getLogger(__name__)

BACKUP_DIR = BACKEND_DIR / "data" / "backups"

KEEP_SNAPSHOTS = 14


def database_path() -> Optional[Path]:
    """The SQLite file behind this install, or None on PostgreSQL."""
    if not settings.is_sqlite:
        return None
    url = settings.DATABASE_URL
    _, _, tail = url.partition(":///")
    if not tail or tail == ":memory:":
        return None
    path = Path(tail)
    return path if path.is_absolute() else (BACKEND_DIR / path)


def take_snapshot() -> Optional[Path]:
    """Copy the database to a timestamped file. Safe to run while serving."""
    source = database_path()
    if source is None or not source.exists():
        return None

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    target = BACKUP_DIR / f"ucsp-{_stamp()}.db"

    live = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
    try:
        copy = sqlite3.connect(target)
        try:
            live.backup(copy)
        finally:
            copy.close()
    finally:
        live.close()

    _prune()
    logger.info("Database snapshot written to %s", target)
    return target


ARCHIVE_SUFFIX = "-attachments.zip"


def _stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def archive_attachments(storage_paths: Iterable[str]) -> Optional[str]:
    """Copy these attachment files into a zip in the backup directory."""
    paths = [path for path in storage_paths if path]
    if not paths:
        return None

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    target = BACKUP_DIR / f"ucsp-{_stamp()}{ARCHIVE_SUFFIX}"
    written = 0
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for relative in paths:
            source = storage.absolute(relative)
            if source is None or not source.exists():
                continue
            archive.write(source, arcname=relative)
            written += 1

    if not written:
        target.unlink(missing_ok=True)
        return None
    logger.info("Archived %s attachment files to %s", written, target)
    return target.name


def list_attachment_archives() -> list[dict[str, Any]]:
    """Archives taken so far, newest first."""
    if not BACKUP_DIR.exists():
        return []
    rows = []
    for path in sorted(BACKUP_DIR.glob(f"ucsp-*{ARCHIVE_SUFFIX}"), reverse=True):
        stat = path.stat()
        rows.append(
            {
                "name": path.name,
                "bytes": stat.st_size,
                "takenAt": datetime.fromtimestamp(stat.st_mtime, UTC)
                .replace(microsecond=0)
                .isoformat()
                .replace("+00:00", "Z"),
            }
        )
    return rows


def restore_attachments(name: str) -> int:
    """Put an archive's files back, and say how many were written."""
    known = {row["name"] for row in list_attachment_archives()}
    if name not in known:
        raise FileNotFoundError(name)

    written = 0
    with zipfile.ZipFile(BACKUP_DIR / name) as archive:
        for member in archive.infolist():
            if member.is_dir():
                continue
            target = storage.absolute(member.filename)
            if target is None:
                logger.error("Refused an archive entry outside the store, %s", member.filename)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.read(member))
            written += 1
    logger.info("Restored %s attachment files from %s", written, name)
    return written


def _prune() -> None:
    """Keep the newest snapshots and delete the rest."""
    snapshots = sorted(BACKUP_DIR.glob("ucsp-*.db"))
    for stale in snapshots[:-KEEP_SNAPSHOTS]:
        try:
            stale.unlink()
        except OSError:  # pragma: no cover, a locked or already gone file
            logger.warning("Could not remove old snapshot %s", stale)


def list_snapshots() -> list[dict[str, Any]]:
    """Newest first, for the interface and for anyone poking at the API."""
    if not BACKUP_DIR.exists():
        return []
    rows = []
    for path in sorted(BACKUP_DIR.glob("ucsp-*.db"), reverse=True):
        stat = path.stat()
        rows.append(
            {
                "name": path.name,
                "bytes": stat.st_size,
                "takenAt": datetime.fromtimestamp(stat.st_mtime, UTC)
                .replace(microsecond=0)
                .isoformat()
                .replace("+00:00", "Z"),
            }
        )
    return rows


async def snapshot_forever(interval_hours: int) -> None:
    """Take a snapshot on a timer for as long as the process runs."""
    if interval_hours <= 0 or database_path() is None:
        return
    while True:
        await asyncio.sleep(interval_hours * 3600)
        try:
            await asyncio.to_thread(take_snapshot)
        except Exception:
            logger.exception("Scheduled snapshot failed")


def _iso(value) -> Optional[str]:
    """A stored timestamp as ISO 8601 in UTC."""
    if not value:
        return None
    if value.tzinfo is not None:
        value = value.astimezone(UTC).replace(tzinfo=None)
    return value.replace(microsecond=0).isoformat() + "Z"


def _now_iso() -> str:
    return _iso(datetime.now(UTC)) or ""


async def export_workspace(db: AsyncSession, workspace_id: str) -> dict[str, Any]:
    """The whole workspace as plain JSON, without any secret."""
    workspace = await db.get(Workspace, workspace_id)
    if workspace is None:
        raise ValueError("Workspace not found")

    async def rows(model, order=None):
        statement = select(model).where(model.workspace_id == workspace_id)
        if order is not None:
            statement = statement.order_by(order)
        return list((await db.execute(statement)).scalars())

    users = await rows(User, User.created_at)
    customers = await rows(Customer, Customer.created_at)
    articles = await rows(Article, Article.created_at)
    macros = await rows(Macro, Macro.created_at)
    slas = await rows(SlaPolicy, SlaPolicy.created_at)
    routing = await rows(RoutingRule, RoutingRule.created_at)
    tickets = await rows(Ticket, Ticket.created_at)
    conversations = await rows(Conversation, Conversation.created_at)
    tap_sessions = await rows(TapSession, TapSession.created_at)
    channels = await rows(ChannelAccount, ChannelAccount.created_at)

    conversation_ids = [c.id for c in conversations]
    messages = []
    if conversation_ids:
        messages = list(
            (
                await db.execute(
                    select(Message)
                    .where(Message.conversation_id.in_(conversation_ids))
                    .order_by(Message.created_at)
                )
            ).scalars()
        )

    attachments = list(
        (
            await db.execute(
                select(Attachment)
                .where(Attachment.workspace_id == workspace_id)
                .order_by(Attachment.created_at)
            )
        ).scalars()
    )
    files_by_message: dict[str, list[str]] = {}
    for attachment in attachments:
        if attachment.message_id:
            files_by_message.setdefault(attachment.message_id, []).append(attachment.id)

    return {
        "$comment": (
            "Full export of one workspace from the Unified Customer Service "
            "Platform. Plain JSON on purpose, so it outlives this project. "
            "Passwords and credentials are not included."
        ),
        "exportedAt": _now_iso(),
        "formatVersion": 1,
        "workspace": {
            "id": workspace.id,
            "name": workspace.name,
            "slug": workspace.slug,
            "accentColor": workspace.accent_color,
            "settings": workspace.settings or {},
        },
        "users": [
            {
                "id": u.id,
                "name": u.name,
                "email": u.email,
                "role": u.role,
                "isActive": u.is_active,
                "createdAt": _iso(u.created_at),
            }
            for u in users
        ],
        "customers": [
            {
                "id": c.id,
                "name": c.name,
                "email": c.email,
                "phone": c.phone,
                "company": c.company,
                "channelIds": c.channel_ids or {},
                "notes": c.notes,
                "lastSeenAt": _iso(c.last_seen_at),
                "createdAt": _iso(c.created_at),
            }
            for c in customers
        ],
        "articles": [
            {
                "id": a.id,
                "title": a.title,
                "summary": a.summary,
                "body": a.body,
                "category": a.category,
                "tags": a.tags or [],
                "status": a.status,
                "visibility": a.visibility,
                "authorName": a.author_name,
                "version": a.version,
                "createdAt": _iso(a.created_at),
                "updatedAt": _iso(a.updated_at),
            }
            for a in articles
        ],
        "macros": [
            {"id": m.id, "name": m.name, "body": m.body, "tags": m.tags or []} for m in macros
        ],
        "slaPolicies": [
            {
                "id": s.id,
                "name": s.name,
                "priorities": s.priorities or [],
                "firstResponseMinutes": s.first_response_minutes,
                "resolutionMinutes": s.resolution_minutes,
                "isActive": s.is_active,
            }
            for s in slas
        ],
        "routingRules": [
            {
                "id": r.id,
                "name": r.name,
                "conditions": r.conditions or {},
                "actions": r.actions or {},
                "orderIndex": r.order_index,
                "isActive": r.is_active,
            }
            for r in routing
        ],
        "tickets": [
            {
                "id": t.id,
                "number": t.number,
                "subject": t.subject,
                "description": t.description,
                "tags": t.tags or [],
                "status": t.status,
                "priority": t.priority,
                "channel": t.channel,
                "category": t.category,
                "customerId": t.customer_id,
                "assignedUserId": t.assigned_user_id,
                "aiHandled": t.ai_handled,
                "satisfaction": t.satisfaction,
                "createdAt": _iso(t.created_at),
                "firstResponseAt": _iso(t.first_response_at),
                "resolvedAt": _iso(t.resolved_at),
                "slaDueAt": _iso(t.sla_due_at),
            }
            for t in tickets
        ],
        "conversations": [
            {
                "id": c.id,
                "customerId": c.customer_id,
                "ticketId": c.ticket_id,
                "channel": c.channel,
                "status": c.status,
                "subject": c.subject,
                "assignedUserId": c.assigned_user_id,
                "createdAt": _iso(c.created_at),
                "lastMessageAt": _iso(c.last_message_at),
            }
            for c in conversations
        ],
        "messages": [
            {
                "id": m.id,
                "conversationId": m.conversation_id,
                "authorType": m.author_type,
                "authorName": m.author_name,
                "body": m.body,
                "isPrivate": m.is_private,
                "meta": m.meta or {},
                "attachmentIds": files_by_message.get(m.id, []),
                "createdAt": _iso(m.created_at),
            }
            for m in messages
        ],
        "attachments": [
            {
                "id": a.id,
                "messageId": a.message_id,
                "filename": a.filename,
                "contentType": a.content_type,
                "sizeBytes": a.size_bytes,
                "source": a.source,
                "storagePath": a.storage_path,
                "createdAt": _iso(a.created_at),
            }
            for a in attachments
        ],
        "tapSessions": [
            {
                "id": t.id,
                "customerLabel": t.customer_label,
                "status": t.status,
                "transcript": t.transcript or [],
                "suggestions": t.suggestions or [],
                "summary": t.summary,
                "createdAt": _iso(t.created_at),
            }
            for t in tap_sessions
        ],
        # Names only. The values stay encrypted in the database where they live.
        "channels": [
            {
                "channel": c.channel,
                "displayName": c.display_name,
                "isActive": c.is_active,
                "configuredKeys": sorted((c.config or {}).keys()),
            }
            for c in channels
        ],
    }
