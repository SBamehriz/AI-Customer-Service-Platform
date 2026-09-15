"""Tap AI, live call assistance."""

from __future__ import annotations

import logging
from contextlib import suppress
from typing import Optional

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect, status
from sqlalchemy import select

from ..ai import assist
from ..db import async_session_maker, utcnow
from ..models import Conversation, TapSession, Workspace, new_id
from ..realtime import hub
from ..schemas import TapSessionOut, TapStartRequest, TapUtterance
from ..security import CurrentUser, DbDep, user_for_socket

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tap", tags=["tap"])

MIN_UTTERANCE_CHARS = 12


async def _get_session(db, workspace_id: str, session_id: str) -> TapSession:
    session = await db.get(TapSession, session_id)
    if session is None or session.workspace_id != workspace_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tap session not found")
    return session


def _require_live(session: TapSession) -> None:
    """An ended call is a finished record, so nothing more is added to it."""
    if session.status != "live":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "This call has ended, so nothing more can be added to it. Start a "
            "new session for a new call.",
        )


@router.post("/sessions", response_model=TapSessionOut, status_code=status.HTTP_201_CREATED)
async def start_session(payload: TapStartRequest, user: CurrentUser, db: DbDep) -> TapSessionOut:
    """Open a live call. A conversation id ties the call to a thread in the inbox."""
    conversation_id = payload.conversation_id or None
    if conversation_id is not None:
        conversation = await db.get(Conversation, conversation_id)
        if conversation is None or conversation.workspace_id != user.workspace_id:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "There is no conversation in this workspace with that id.",
            )

    session = TapSession(
        workspace_id=user.workspace_id,
        user_id=user.id,
        conversation_id=conversation_id,
        customer_label=payload.customer_label,
        status="live",
        transcript=[],
        suggestions=[],
    )
    db.add(session)
    await db.flush()
    return TapSessionOut.model_validate(session)


@router.get("/sessions", response_model=list[TapSessionOut])
async def list_sessions(user: CurrentUser, db: DbDep, limit: int = 20) -> list[TapSessionOut]:
    sessions = (
        await db.execute(
            select(TapSession)
            .where(TapSession.workspace_id == user.workspace_id)
            .order_by(TapSession.created_at.desc())
            .limit(limit)
        )
    ).scalars()
    return [TapSessionOut.model_validate(session) for session in sessions]


@router.get("/sessions/{session_id}", response_model=TapSessionOut)
async def get_session(session_id: str, user: CurrentUser, db: DbDep) -> TapSessionOut:
    return TapSessionOut.model_validate(await _get_session(db, user.workspace_id, session_id))


@router.post("/sessions/{session_id}/utterances", response_model=TapSessionOut)
async def add_utterance(
    session_id: str, payload: TapUtterance, user: CurrentUser, db: DbDep
) -> TapSessionOut:
    """Append a transcript line over HTTP, for clients not using the socket."""
    session = await _get_session(db, user.workspace_id, session_id)
    _require_live(session)
    workspace = await db.get(Workspace, user.workspace_id)
    if workspace is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Workspace not found")
    await _append(db, workspace, session, payload.speaker, payload.text)
    return TapSessionOut.model_validate(session)


@router.post("/sessions/{session_id}/end", response_model=TapSessionOut)
async def end_session(session_id: str, user: CurrentUser, db: DbDep) -> TapSessionOut:
    session = await _get_session(db, user.workspace_id, session_id)
    if session.status != "live":
        return TapSessionOut.model_validate(session)
    workspace = await db.get(Workspace, user.workspace_id)
    session.status = "ended"
    session.ended_at = utcnow()
    if workspace is not None:
        session.summary = await assist.summarise_call(workspace, session.transcript or [])
    await db.flush()
    return TapSessionOut.model_validate(session)


async def _append(
    db, workspace: Workspace, session: TapSession, speaker: str, text: str
) -> list[dict]:
    """Record one line and, for customer turns, generate suggestions."""
    text = text.strip()
    if not text:
        return []

    entry = {"id": new_id(), "speaker": speaker, "text": text, "at": utcnow().isoformat() + "Z"}
    session.transcript = [*(session.transcript or []), entry]
    await db.flush()

    await hub.publish(
        workspace.id, "tap.transcript", {"sessionId": session.id, "entry": entry}
    )

    if speaker != "customer" or len(text) < MIN_UTTERANCE_CHARS:
        return []

    suggestions, citations, engine = await assist.tap_suggestions(
        db, workspace, transcript=session.transcript or [], latest=text
    )
    if not suggestions:
        return []

    stamped = [
        {
            "id": new_id(),
            "kind": item.get("kind", "answer"),
            "text": item.get("text", ""),
            "confidence": item.get("confidence", 0.0),
            "citations": citations,
            "engine": engine,
            "at": utcnow().isoformat() + "Z",
        }
        for item in suggestions
        if item.get("text")
    ]
    session.suggestions = [*(session.suggestions or []), *stamped]
    await db.flush()

    await hub.publish(
        workspace.id, "tap.suggestion", {"sessionId": session.id, "suggestions": stamped}
    )
    return stamped


async def route_voice_transcript(
    db, workspace: Workspace, call_sid: Optional[str], speaker: str, text: str
) -> None:
    """Feed a telephony transcript line into the live session for that call."""
    session = None
    if call_sid:
        session = await db.scalar(
            select(TapSession)
            .where(
                TapSession.workspace_id == workspace.id,
                TapSession.status == "live",
                TapSession.call_sid == call_sid,
            )
            .order_by(TapSession.created_at.desc())
        )
    else:
        session = await db.scalar(
            select(TapSession)
            .where(
                TapSession.workspace_id == workspace.id,
                TapSession.status == "live",
                TapSession.call_sid.is_(None),
            )
            .order_by(TapSession.created_at.desc())
        )
    if session is None:
        session = TapSession(
            workspace_id=workspace.id,
            call_sid=call_sid,
            customer_label=call_sid or "Caller",
            status="live",
            transcript=[],
            suggestions=[],
        )
        db.add(session)
        await db.flush()
    await _append(db, workspace, session, speaker, text)


@router.websocket("/{session_id}/stream")
async def tap_stream(websocket: WebSocket, session_id: str, token: str = "") -> None:
    """Bidirectional stream for one live call."""
    user = await user_for_socket(token)
    if user is None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    workspace_id = user.workspace_id

    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_json()
            speaker = data.get("speaker", "customer")
            text = (data.get("text") or "").strip()
            if not text:
                continue
            if speaker not in ("customer", "agent"):
                speaker = "customer"

            async with async_session_maker() as db:
                session = await db.get(TapSession, session_id)
                if session is None or session.workspace_id != workspace_id:
                    await websocket.send_json({"type": "error", "message": "Session not found"})
                    break
                if session.status != "live":
                    await websocket.send_json(
                        {"type": "error", "message": "This call has ended"}
                    )
                    break
                workspace = await db.get(Workspace, workspace_id)
                if workspace is None:
                    break
                suggestions = await _append(db, workspace, session, speaker, text)
                await db.commit()

            await websocket.send_json({"type": "transcript", "speaker": speaker, "text": text})
            if suggestions:
                await websocket.send_json({"type": "suggestions", "suggestions": suggestions})
    except WebSocketDisconnect:
        return
    except Exception as exc:  # noqa: BLE001, a live call must fail quietly
        logger.warning("Tap stream error: %s", exc)
        with suppress(RuntimeError):
            await websocket.close()
