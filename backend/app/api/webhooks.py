"""Inbound channel webhooks."""

from __future__ import annotations

import json
import logging
from urllib.parse import parse_qsl

from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlalchemy import select

from ..channels import get_adapter
from ..config import settings
from ..models import ChannelAccount, TapSession, Workspace
from ..security import DbDep
from ..services import ingest
from .tap import route_voice_transcript

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


async def _account(db, workspace_id: str, channel: str) -> tuple[Workspace, ChannelAccount]:
    workspace = await db.get(Workspace, workspace_id)
    if workspace is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Workspace not found")
    account = await db.scalar(
        select(ChannelAccount).where(
            ChannelAccount.workspace_id == workspace_id, ChannelAccount.channel == channel
        )
    )
    if account is None or not account.is_active:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"{channel} is not connected")
    return workspace, account


@router.get("/{channel}/{workspace_id}")
async def verify_webhook(channel: str, workspace_id: str, request: Request, db: DbDep) -> Response:
    """Meta's one time subscription handshake."""
    _, account = await _account(db, workspace_id, channel)
    params = request.query_params
    expected = account.live_config().get("verify_token", "")
    if params.get("hub.mode") == "subscribe" and expected and params.get("hub.verify_token") == expected:
        return Response(content=params.get("hub.challenge", ""), media_type="text/plain")
    raise HTTPException(status.HTTP_403_FORBIDDEN, "Verification failed")


@router.post("/{channel}/{workspace_id}")
async def receive_webhook(channel: str, workspace_id: str, request: Request, db: DbDep) -> Response:
    """Accept a provider delivery and ingest every message it carries."""
    adapter = get_adapter(channel)
    if adapter is None or not adapter.has_webhook:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No webhook for channel {channel}")

    workspace, account = await _account(db, workspace_id, channel)
    raw = await request.body()

    headers = _signed_headers(request)

    config = account.live_config()
    if not adapter.verify_signature(config, raw, headers):
        _log_rejection(request, f"{channel} inbound", workspace_id)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid signature")

    payload = _parse_body(raw, headers.get("content-type", ""))
    messages = adapter.parse_inbound(payload, config)

    # Voice is transcript rather than messages, so it feeds the live assistant.
    if channel == "voice":
        for message in messages:
            await route_voice_transcript(
                db, workspace, message.meta.get("call_sid"), "customer", message.body
            )
        account.last_event_at = ingest.utcnow()
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    ingested = 0
    for message in messages:
        if await ingest.already_ingested(db, workspace.id, message.external_id):
            continue
        await ingest.ingest(db, workspace, message)
        ingested += 1

    account.last_event_at = ingest.utcnow()
    return Response(
        content=json.dumps({"received": len(messages), "ingested": ingested}),
        media_type="application/json",
    )


@router.post("/voice/{workspace_id}/answer")
async def voice_answer(workspace_id: str, request: Request, db: DbDep) -> Response:
    """TwiML played when a call connects, wiring speech back to this platform."""
    from ..channels.twilio import VoiceAdapter

    workspace, account = await _account(db, workspace_id, "voice")
    raw = await request.body()
    if not VoiceAdapter().verify_signature(
        account.live_config(), raw, _signed_headers(request)
    ):
        _log_rejection(request, "voice answer", workspace_id)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid signature")

    config = workspace.settings or {}
    greeting = config.get("greeting", "Thanks for calling. How can we help?")
    action = f"{settings.PUBLIC_URL}/api/v1/webhooks/voice/{workspace_id}"
    record = bool(config.get("record_calls"))
    return Response(
        content=VoiceAdapter.answer_twiml(
            greeting,
            action,
            record=record,
            recording_callback=f"{settings.PUBLIC_URL}/api/v1/webhooks/voice/{workspace_id}/recording",
            notice=config.get(
                "recording_notice",
                "This call may be recorded for quality and training purposes.",
            ),
        ),
        media_type="application/xml",
    )


@router.post("/voice/{workspace_id}/recording")
async def voice_recording(workspace_id: str, request: Request, db: DbDep) -> Response:
    """Twilio posts here once a recording is ready, after the call ends."""
    from ..channels.twilio import VoiceAdapter
    from .attachments import store_bytes

    workspace, account = await _account(db, workspace_id, "voice")
    if not bool((workspace.settings or {}).get("record_calls")):
        # Somebody turned recording off between the call starting and ending.
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    raw = await request.body()
    adapter = VoiceAdapter()
    config = account.live_config()
    if not adapter.verify_signature(config, raw, _signed_headers(request)):
        _log_rejection(request, "call recording", workspace_id)
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Signature check failed")

    form = _parse_form(raw)
    url = form.get("RecordingUrl", "")
    fetched = await adapter.fetch_recording(config, url)
    if fetched is None:
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    payload, filename, content_type = fetched
    call_sid = form.get("CallSid", "")
    session = await db.scalar(
        select(TapSession)
        .where(TapSession.workspace_id == workspace.id, TapSession.call_sid == call_sid)
        .order_by(TapSession.created_at.desc())
        .limit(1)
    ) if call_sid else None
    attachment = await store_bytes(
        db,
        workspace_id=workspace.id,
        payload=payload,
        filename=filename,
        content_type=content_type,
        source="voice",
    )
    if session is not None:
        session.recording_attachment_id = attachment.id
        session.recording_seconds = int(form.get("RecordingDuration") or 0)
    logger.info("Stored a call recording for %s, call %s", workspace.slug, call_sid)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _parse_form(raw_body: bytes) -> dict[str, str]:
    """Twilio posts form encoded bodies, and the signature covers the raw one."""
    return dict(parse_qsl(raw_body.decode("utf-8", "ignore"), keep_blank_values=True))


def _log_rejection(request: Request, what: str, workspace_id: str) -> None:
    """Say enough for an operator to fix a rejected callback."""
    logger.warning(
        "Rejected a %s callback for workspace %s. The signature was checked "
        "against %s, which has to be the address configured at the provider. "
        "Set PUBLIC_URL if that is not the public address of this install.",
        what,
        workspace_id,
        _public_request_url(request),
    )


def _signed_headers(request: Request) -> dict[str, str]:
    """Headers in the shape every adapter reads them."""
    headers = {key.lower(): value for key, value in request.headers.items()}
    headers["x-webhook-url"] = _public_request_url(request)
    return headers


def _public_request_url(request: Request) -> str:
    """The URL a provider believes it called."""
    if not settings.PUBLIC_URL:
        return str(request.url)
    query = f"?{request.url.query}" if request.url.query else ""
    return f"{settings.PUBLIC_URL.rstrip('/')}{request.url.path}{query}"


def _parse_body(raw: bytes, content_type: str) -> dict:
    """Providers send JSON or form encoded bodies. Normalise both to a dict."""
    if "application/json" in content_type:
        try:
            parsed = json.loads(raw.decode("utf-8", "replace") or "{}")
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {"data": parsed}
    return dict(parse_qsl(raw.decode("utf-8", "replace"), keep_blank_values=True))
