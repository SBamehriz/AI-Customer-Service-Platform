"""FastAPI application entry point."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import backup
from .ai.providers import get_provider
from .api import router as api_router
from .channels import ADAPTERS
from .config import BACKEND_DIR, DEFAULT_PUBLIC_URL, settings
from .db import close_db, init_db
from .realtime import hub
from .security import user_for_socket

logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# How often the optional IMAP poller checks the shared mailbox.
EMAIL_POLL_SECONDS = 60

# How often the scheduled Autopilot pass wakes up. It only acts during the
# hours a workspace allows, and it never takes a second turn on a thread
# without a customer reply in between, so waking often is safe.
AUTOPILOT_POLL_SECONDS = 900


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    if settings.SEED_DEMO_DATA:
        from .seed import demo_data_present, seed_if_empty

        await seed_if_empty()
        app.state.demo_data = await demo_data_present()
        if app.state.demo_data:
            logger.warning(
                "Demo data is loaded and its accounts share a password that is "
                "published in the README. Never expose this install to the "
                "internet. Set SEED_DEMO_DATA=false and use a fresh database "
                "for anything real."
            )
    else:
        app.state.demo_data = False

    if settings.SECRET_KEY_IS_EPHEMERAL:
        logger.warning(
            "SECRET_KEY is unset, so a new one was generated for this process. "
            "Sessions will not survive a restart, and running more than one "
            "worker will reject every token. Set SECRET_KEY before deploying."
        )

    if settings.PUBLIC_URL == DEFAULT_PUBLIC_URL:
        logger.warning(
            "PUBLIC_URL is still %s. It is the address webhooks are built from "
            "and the address their signatures are checked against, so WhatsApp, "
            "Instagram, SMS and voice deliveries are rejected until it is the "
            "public address of this install. Web chat and email are unaffected.",
            DEFAULT_PUBLIC_URL,
        )

    provider = get_provider()
    logger.info(
        "%s v%s ready | db=%s | ai=%s",
        settings.APP_NAME,
        settings.APP_VERSION,
        "sqlite" if settings.is_sqlite else "postgresql",
        f"{provider.name}:{provider.model}" if provider.available else "disabled (retrieval only)",
    )

    poller = asyncio.create_task(_poll_email_forever())
    autopilot_task = asyncio.create_task(_run_autopilot_forever())
    snapshots = asyncio.create_task(backup.snapshot_forever(settings.BACKUP_INTERVAL_HOURS))
    try:
        yield
    finally:
        for task in (poller, snapshots, autopilot_task):
            task.cancel()
        for task in (poller, snapshots, autopilot_task):
            with suppress(asyncio.CancelledError):
                await task
        await close_db()


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description=(
        "Source available unified customer service platform. One inbox across "
        "web, email, WhatsApp, Instagram, SMS and voice, with grounded AI "
        "assistance."
    ),
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.WIDGET_ALLOW_ANY_ORIGIN else settings.CORS_ORIGINS,
    allow_credentials=not settings.WIDGET_ALLOW_ANY_ORIGIN,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.get("/health", tags=["system"])
async def health() -> JSONResponse:
    """Liveness probe, also used by the frontend to detect API mode."""
    from .seed import install_state

    provider = get_provider()
    try:
        state = await install_state()
        database_ready = True
    except Exception:
        logger.exception("The database could not be read while answering /health")
        state = {"demoData": False, "configured": False}
        database_ready = False

    return JSONResponse(
        {
            "status": "ok" if database_ready else "degraded",
            "version": settings.APP_VERSION,
            "database": "sqlite" if settings.is_sqlite else "postgresql",
            "databaseReady": database_ready,
            "ai": {
                "enabled": provider.available,
                "provider": provider.name,
                "model": provider.model if provider.available else None,
            },
            "channels": sorted(ADAPTERS),
            "demoData": state["demoData"],
            "configured": state["configured"],
        }
    )


@app.websocket("/ws")
async def workspace_events(websocket: WebSocket, token: str = "") -> None:
    """Live workspace event stream for the agent app."""
    user = await user_for_socket(token)
    if user is None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    workspace_id = user.workspace_id

    await websocket.accept()
    await hub.join(workspace_id, websocket)
    try:
        await websocket.send_json({"event": "connected", "data": {"workspaceId": workspace_id}})
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception as exc:  # noqa: BLE001
        logger.debug("Workspace socket closed: %s", exc)
    finally:
        await hub.leave(workspace_id, websocket)


FRONTEND_DIST = BACKEND_DIR.parent / "dist"

if FRONTEND_DIST.is_dir():
    app.mount(
        "/assets",
        StaticFiles(directory=FRONTEND_DIST / "assets"),
        name="assets",
    )

    @app.get("/{path:path}", include_in_schema=False)
    async def serve_frontend(path: str, request: Request) -> FileResponse:
        """Serve a built file, falling back to index.html for client routes."""
        candidate = (FRONTEND_DIST / path).resolve()
        if path and FRONTEND_DIST in candidate.parents and candidate.is_file():
            return FileResponse(candidate)
        index = FRONTEND_DIST / "index.html"
        if not index.is_file():
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Frontend is not built")
        return FileResponse(index)
else:
    logger.info("No dist/ directory, run `npm run build` to serve the UI from this process")


async def _run_autopilot_forever() -> None:
    """Check every workspace on a timer, and run the ones the hour allows."""
    from sqlalchemy import select

    from .db import async_session_maker
    from .models import Workspace
    from .services import autopilot

    while True:
        await asyncio.sleep(AUTOPILOT_POLL_SECONDS)
        try:
            async with async_session_maker() as db:
                workspaces = list(
                    (await db.execute(select(Workspace))).scalars()
                )
                for workspace in workspaces:
                    if not autopilot.should_run_now(workspace.settings or {}):
                        continue
                    await autopilot.run_once(db, workspace, trigger="schedule")
                await db.commit()
        except Exception:
            logger.exception("Scheduled autopilot pass failed")


async def _poll_email_forever() -> None:
    """Pull mail from any workspace that configured IMAP."""
    from sqlalchemy import select

    from .channels.email import EmailAdapter
    from .db import async_session_maker
    from .models import ChannelAccount, Workspace
    from .services import ingest

    adapter = EmailAdapter()
    while True:
        try:
            await asyncio.sleep(EMAIL_POLL_SECONDS)
            async with async_session_maker() as db:
                accounts = (
                    await db.execute(
                        select(ChannelAccount).where(
                            ChannelAccount.channel == "email",
                            ChannelAccount.is_active.is_(True),
                        )
                    )
                ).scalars()
                for account in accounts:
                    config = account.live_config()
                    if not config.get("imap_host"):
                        continue
                    workspace = await db.get(Workspace, account.workspace_id)
                    if workspace is None:
                        continue
                    for message in await adapter.fetch_imap(config):
                        if await ingest.already_ingested(
                            db, workspace.id, message.external_id
                        ):
                            continue
                        await ingest.ingest(db, workspace, message)
                    account.last_event_at = ingest.utcnow()
                await db.commit()
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001, one bad mailbox must not stop the loop
            logger.warning("Email poll cycle failed: %s", exc)
