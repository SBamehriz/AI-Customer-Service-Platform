"""Workspace configuration. Profile, team, automation and channel connections."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Response, status
from fastapi.responses import JSONResponse
from pydantic import Field
from sqlalchemy import delete, func, select

from .. import backup, crypto, datasets, storage
from ..ai.providers import DEFAULT_MODELS, forget_workspace_providers, get_provider
from ..channels import channel_catalog, get_adapter
from ..config import settings as app_settings
from ..models import (
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
    workspace_setting,
)
from ..schemas import (
    AiConfigIn,
    AiConfigOut,
    AiTestResult,
    ApiModel,
    ChannelIn,
    ChannelOut,
    MacroIn,
    MacroOut,
    RoutingRuleIn,
    RoutingRuleOut,
    RoutingRulePatch,
    SlaPolicyIn,
    SlaPolicyOut,
    SlaPolicyPatch,
    TeamMemberIn,
    TeamMemberPatch,
    UserOut,
    WorkspaceOut,
    WorkspacePatch,
)
from ..security import CurrentUser, DbDep, Manager, hash_password
from ..services import autopilot

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/workspace", tags=["workspace"])


@router.get("", response_model=WorkspaceOut)
async def get_workspace(user: CurrentUser, db: DbDep) -> WorkspaceOut:
    workspace = await db.get(Workspace, user.workspace_id)
    if workspace is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Workspace not found")
    return WorkspaceOut.model_validate(workspace)


@router.patch("", response_model=WorkspaceOut)
async def update_workspace(payload: WorkspacePatch, user: Manager, db: DbDep) -> WorkspaceOut:
    workspace = await db.get(Workspace, user.workspace_id)
    if workspace is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Workspace not found")
    updates = payload.model_dump(exclude_unset=True)
    if "settings" in updates and updates["settings"] is not None:
        # Merge rather than replace, so a partial save cannot drop other keys.
        merged = {**(workspace.settings or {}), **updates.pop("settings")}
        _check_recording_notice(merged)
        workspace.settings = merged
    for field, value in updates.items():
        if value is not None:
            setattr(workspace, field, value)
    await db.flush()
    return WorkspaceOut.model_validate(workspace)


def _check_recording_notice(merged: dict) -> None:
    """Recording a call is only allowed with something to say first."""
    if not merged.get("record_calls"):
        return
    if not str(merged.get("recording_notice") or "").strip():
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Call recording needs a recording notice. There is no way to record "
            "without one.",
        )


@router.get("/team", response_model=list[UserOut])
async def list_team(user: CurrentUser, db: DbDep) -> list[UserOut]:
    members = (
        await db.execute(
            select(User).where(User.workspace_id == user.workspace_id).order_by(User.name)
        )
    ).scalars()
    return [UserOut.model_validate(member) for member in members]


async def _member(db, workspace_id: str, user_id: str) -> User:
    member = await db.get(User, user_id)
    if member is None or member.workspace_id != workspace_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Team member not found")
    return member


def _may_set_owner(actor: User, role: Optional[str]) -> None:
    """Only an owner hands out the owner role."""
    if role == "owner" and actor.role != "owner":
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Only an owner can make someone else an owner.",
        )


async def _last_owner_guard(db, workspace_id: str, member: User) -> None:
    """Refuse a change that would leave the workspace with no active owner."""
    if member.role != "owner":
        return
    remaining = await db.scalar(
        select(func.count(User.id)).where(
            User.workspace_id == workspace_id,
            User.role == "owner",
            User.is_active.is_(True),
            User.id != member.id,
        )
    )
    if not remaining:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "This is the last owner. Make someone else an owner first.",
        )


@router.post("/team", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def add_member(payload: TeamMemberIn, user: Manager, db: DbDep) -> UserOut:
    """Add a teammate and set their first password."""
    _may_set_owner(user, payload.role)
    email = payload.email.lower()
    clash = await db.scalar(
        select(User.id).where(
            User.workspace_id == user.workspace_id, func.lower(User.email) == email
        )
    )
    if clash:
        raise HTTPException(status.HTTP_409_CONFLICT, "That email is already on this team")

    member = User(
        workspace_id=user.workspace_id,
        email=email,
        name=payload.name,
        password_hash=hash_password(payload.password),
        role=payload.role,
    )
    db.add(member)
    await db.flush()
    return UserOut.model_validate(member)


@router.patch("/team/{user_id}", response_model=UserOut)
async def update_member(
    user_id: str, payload: TeamMemberPatch, user: Manager, db: DbDep
) -> UserOut:
    """Change a teammate's name, role, or whether they can sign in."""
    member = await _member(db, user.workspace_id, user_id)
    updates = payload.model_dump(exclude_unset=True)

    if member.id == user.id and ("role" in updates or updates.get("is_active") is False):
        # Otherwise one wrong click locks the workspace out of its own settings.
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "You cannot change your own role or switch off your own account.",
        )
    _may_set_owner(user, updates.get("role"))
    if member.role == "owner" and user.role != "owner":
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Only an owner can change another owner."
        )
    if updates.get("role", member.role) != "owner" or updates.get("is_active") is False:
        await _last_owner_guard(db, user.workspace_id, member)

    for field, value in updates.items():
        setattr(member, field, value)
    await db.flush()
    return UserOut.model_validate(member)


def _ai_config_out(workspace: Workspace) -> AiConfigOut:
    config = workspace.ai_config or {}
    env_managed = app_settings.llm_enabled
    if env_managed:
        return AiConfigOut(
            provider=app_settings.LLM_PROVIDER,
            model=app_settings.LLM_MODEL,
            base_url=app_settings.LLM_BASE_URL,
            embedding_model=app_settings.EMBEDDING_MODEL,
            default_model=DEFAULT_MODELS.get(app_settings.LLM_PROVIDER, ""),
            has_key=True,
            managed_by_env=True,
            encryption_available=crypto.AVAILABLE,
            active=True,
        )
    has_key = bool(crypto.unseal(config.get("api_key", "")))
    provider = config.get("provider", "none")
    return AiConfigOut(
        provider=provider,
        model=config.get("model", ""),
        default_model=DEFAULT_MODELS.get(provider, ""),
        base_url=config.get("base_url", ""),
        embedding_model=config.get("embedding_model", ""),
        has_key=has_key,
        managed_by_env=False,
        encryption_available=crypto.AVAILABLE,
        active=has_key and config.get("provider", "none") != "none",
    )


@router.get("/ai", response_model=AiConfigOut)
async def get_ai_config(user: Manager, db: DbDep) -> AiConfigOut:
    """What model this workspace uses. The key is never returned."""
    workspace = await db.get(Workspace, user.workspace_id)
    if workspace is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Workspace not found")
    return _ai_config_out(workspace)


@router.put("/ai", response_model=AiConfigOut)
async def set_ai_config(payload: AiConfigIn, user: Manager, db: DbDep) -> AiConfigOut:
    """Point the workspace at a provider, and store the key encrypted."""
    if app_settings.llm_enabled:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "A provider is set through environment variables on this server, "
            "so it cannot be changed here. Clear LLM_PROVIDER to manage it "
            "from Settings instead.",
        )

    workspace = await db.get(Workspace, user.workspace_id)
    if workspace is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Workspace not found")

    current = dict(workspace.ai_config or {})
    if payload.api_key is not None:
        # An empty string is an explicit clear, which is different from absent.
        current["api_key"] = crypto.seal(payload.api_key.strip())
    if payload.provider == "none":
        current["api_key"] = ""

    current.update(
        provider=payload.provider,
        model=payload.model.strip(),
        base_url=payload.base_url.strip(),
        embedding_model=payload.embedding_model.strip(),
    )
    # Reassigned rather than mutated, so SQLAlchemy sees the JSON column change.
    workspace.ai_config = current
    await db.flush()
    forget_workspace_providers()
    return _ai_config_out(workspace)


@router.post("/ai/test", response_model=AiTestResult)
async def test_ai_config(user: Manager, db: DbDep) -> AiTestResult:
    """Ask the configured provider one trivial question."""
    workspace = await db.get(Workspace, user.workspace_id)
    if workspace is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Workspace not found")

    provider = get_provider(workspace)
    if not provider.available:
        return AiTestResult(ok=False, detail="No provider is configured yet.")
    try:
        completion = await provider.complete(
            system="Reply with the single word ready.",
            prompt="Are you there?",
            max_tokens=16,
        )
    except Exception as error:  # noqa: BLE001, the provider raises whatever it likes
        return AiTestResult(ok=False, detail=_provider_error(error))
    if not (completion.text or "").strip():
        return AiTestResult(ok=False, detail="The provider replied with nothing.")
    return AiTestResult(ok=True, detail=f"{provider.name} answered using {provider.model}.")


def _provider_error(error: Exception) -> str:
    """Turn whatever the provider raised into something worth acting on."""
    text = str(error) or error.__class__.__name__
    lowered = text.lower()

    if "401" in text or "unauthor" in lowered or "invalid api key" in lowered:
        return "The provider rejected that key. Check it was copied whole and has not been revoked."
    if "403" in text or "forbidden" in lowered:
        return (
            "The provider accepted the key but refused the request. That usually means "
            "billing is not set up, the key has no access to this model, or the network "
            "blocks outbound calls."
        )
    if "429" in text or "rate limit" in lowered or "quota" in lowered:
        return "The provider is rate limiting or out of quota. Try again shortly."
    if "404" in text or ("model" in lowered and "not found" in lowered):
        return "The provider does not recognise that model name. Check it against their model list."
    if "timeout" in lowered or "timed out" in lowered:
        return "The provider did not answer in time. It may be slow, or unreachable from here."
    if "connect" in lowered or "dns" in lowered or "name resolution" in lowered:
        return "Could not reach the provider. Check the base URL and whether this server can make outbound calls."
    if any(part in lowered for part in ("certificate", "ssl", "tls")):
        return "The TLS connection to the provider failed. Check the base URL and any proxy in front of it."
    return f"The provider returned an error. {text[:180]}"


@router.post("/autopilot/run")
async def run_autopilot(user: Manager, db: DbDep) -> dict:
    """Work the waiting queue once, now, and report what happened."""
    workspace = await db.get(Workspace, user.workspace_id)
    if workspace is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Workspace not found")
    return await autopilot.run_once(db, workspace, trigger="manual")


@router.get("/autopilot")
async def autopilot_status(user: Manager, db: DbDep) -> dict:
    """Whether it is on, when it runs, and whether it can answer anything."""
    workspace = await db.get(Workspace, user.workspace_id)
    if workspace is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Workspace not found")
    settings = workspace.settings or {}
    hours = sorted(autopilot.hours_from_setting(workspace_setting(settings, "autopilot_hours")))
    return {
        "enabled": bool(settings.get("autopilot_enabled")),
        "hours": hours,
        "runningNow": autopilot.should_run_now(settings),
        "confidenceThreshold": float(workspace_setting(settings, "ai_suggest_threshold")),
        "modelConnected": get_provider(workspace).available,
        "maxPerRun": autopilot.MAX_PER_RUN,
    }


class _ResetRequest(ApiModel):
    """Deleting everything is easy to do by accident, so it is spelled out."""

    confirm: str = Field(description="Type the workspace name exactly to confirm.")
    # Keep the team and the workspace settings, and clear only the traffic.
    keep_team: bool = True


@router.post("/reset")
async def reset_workspace(payload: _ResetRequest, user: Manager, db: DbDep) -> dict:
    """Clear this workspace back to empty, keeping the workspace itself."""
    workspace = await db.get(Workspace, user.workspace_id)
    if workspace is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Workspace not found")
    if payload.confirm.strip() != workspace.name:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f'Type the workspace name exactly, "{workspace.name}", to confirm.',
        )
    if not payload.keep_team and user.role != "owner":
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Only an owner can clear the team. Reset with keepTeam true instead.",
        )

    # Taken before anything is deleted, so this is undoable.
    if backup.database_path() is not None:
        await asyncio.to_thread(backup.take_snapshot)

    removed: dict[str, int] = {}

    files = list(
        (
            await db.execute(
                select(Attachment).where(Attachment.workspace_id == user.workspace_id)
            )
        ).scalars()
    )
    archive = await asyncio.to_thread(
        backup.archive_attachments, [attachment.storage_path for attachment in files]
    )
    for attachment in files:
        storage.remove(attachment.storage_path)
    removed["attachments"] = len(files)

    # Messages hang off conversations, which cascade, so they go first.
    conversation_ids = list(
        (
            await db.execute(
                select(Conversation.id).where(Conversation.workspace_id == user.workspace_id)
            )
        ).scalars()
    )
    if conversation_ids:
        await db.execute(
            delete(Message).where(Message.conversation_id.in_(conversation_ids))
        )

    for model in (Attachment, TapSession, Conversation, Ticket, Customer, Article):
        result = await db.execute(
            delete(model).where(model.workspace_id == user.workspace_id)
        )
        removed[model.__tablename__] = result.rowcount or 0

    if not payload.keep_team:
        result = await db.execute(
            delete(User).where(
                User.workspace_id == user.workspace_id,
                User.id != user.id,
                ~((User.role == "owner") & (User.is_active.is_(True))),
            )
        )
        removed["users"] = result.rowcount or 0

    await db.flush()
    logger.warning(
        "Workspace %s was reset by %s, removed %s", workspace.slug, user.email, removed
    )
    return {"ok": True, "removed": removed, "attachmentArchive": archive}


@router.get("/export")
async def export_everything(user: Manager, db: DbDep) -> JSONResponse:
    """Download the whole workspace as plain JSON."""
    payload = await backup.export_workspace(db, user.workspace_id)
    stamp = payload["exportedAt"][:10]
    slug = payload["workspace"]["slug"]
    return JSONResponse(
        payload,
        headers={
            "Content-Disposition": f'attachment; filename="{slug}-{stamp}.json"',
        },
    )


@router.get("/datasets")
async def list_datasets(user: Manager) -> dict:
    """The tables on offer, for anyone building a report or a pipeline."""
    return {
        "datasets": [
            {
                "name": name,
                "url": f"/api/v1/workspace/datasets/{name}.csv",
                "description": description,
            }
            for name, description in (
                ("customers", "One row per person, with their volume and satisfaction."),
                ("tickets", "One row per ticket, with resolution times and SLA outcomes."),
                ("conversations", "One row per thread, with channel and message counts."),
                ("messages", "One row per turn, for your own analysis."),
                ("agents", "One row per team member, with workload and results."),
                ("calls", "One row per Tap AI call, with recording length."),
            )
        ]
    }


@router.get("/datasets/{name}.csv")
async def download_dataset(name: str, user: Manager, db: DbDep) -> Response:
    """One dataset as CSV."""
    try:
        headers, rows = await datasets.build(db, user.workspace_id, name)
    except ValueError:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"No dataset called {name}. Available, {', '.join(datasets.DATASETS)}.",
        ) from None

    stamp = datetime.now(UTC).strftime("%Y-%m-%d")
    return Response(
        content=datasets.to_csv(headers, rows),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{name}-{stamp}.csv"'},
    )


@router.get("/backups")
async def list_backups(user: Manager) -> dict:
    """Snapshots taken so far, and where they are on disk."""
    path = backup.database_path()
    return {
        "supported": path is not None,
        "directory": str(backup.BACKUP_DIR),
        "intervalHours": app_settings.BACKUP_INTERVAL_HOURS,
        "keep": backup.KEEP_SNAPSHOTS,
        "snapshots": backup.list_snapshots(),
        "attachmentArchives": backup.list_attachment_archives(),
    }


@router.post("/backups/attachments/{name}/restore")
async def restore_attachment_archive(name: str, user: Manager, db: DbDep) -> dict:
    """Put the files from an archive back on disk."""
    try:
        restored = await asyncio.to_thread(backup.restore_attachments, name)
    except FileNotFoundError:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, f"There is no attachment archive called {name}."
        ) from None
    logger.warning("Attachment archive %s was restored by %s", name, user.email)
    return {"ok": True, "name": name, "restored": restored}


@router.post("/backups", status_code=status.HTTP_201_CREATED)
async def create_backup(user: Manager) -> dict:
    """Take a snapshot now, without waiting for the timer."""
    if backup.database_path() is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Snapshots are for the built in SQLite database. This install uses "
            "PostgreSQL, so back it up with your database tooling instead.",
        )
    path = await asyncio.to_thread(backup.take_snapshot)
    if path is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "There is no database file to copy yet")
    return {"name": path.name, "snapshots": backup.list_snapshots()}


@router.get("/macros", response_model=list[MacroOut])
async def list_macros(user: CurrentUser, db: DbDep) -> list[MacroOut]:
    macros = (
        await db.execute(
            select(Macro).where(Macro.workspace_id == user.workspace_id).order_by(Macro.name)
        )
    ).scalars()
    return [MacroOut.model_validate(macro) for macro in macros]


@router.post("/macros", response_model=MacroOut, status_code=status.HTTP_201_CREATED)
async def create_macro(payload: MacroIn, user: Manager, db: DbDep) -> MacroOut:
    """Add a saved reply."""
    macro = Macro(workspace_id=user.workspace_id, **payload.model_dump())
    db.add(macro)
    await db.flush()
    return MacroOut.model_validate(macro)


@router.patch("/macros/{macro_id}", response_model=MacroOut)
async def update_macro(macro_id: str, payload: MacroIn, user: Manager, db: DbDep) -> MacroOut:
    macro = await _owned(db, Macro, macro_id, user.workspace_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(macro, field, value)
    await db.flush()
    return MacroOut.model_validate(macro)


@router.delete("/macros/{macro_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_macro(macro_id: str, user: Manager, db: DbDep) -> None:
    await db.delete(await _owned(db, Macro, macro_id, user.workspace_id))


@router.get("/sla", response_model=list[SlaPolicyOut])
async def list_sla(user: CurrentUser, db: DbDep) -> list[SlaPolicyOut]:
    policies = (
        await db.execute(select(SlaPolicy).where(SlaPolicy.workspace_id == user.workspace_id))
    ).scalars()
    return [SlaPolicyOut.model_validate(policy) for policy in policies]


@router.post("/sla", response_model=SlaPolicyOut, status_code=status.HTTP_201_CREATED)
async def create_sla(payload: SlaPolicyIn, user: Manager, db: DbDep) -> SlaPolicyOut:
    policy = SlaPolicy(workspace_id=user.workspace_id, **payload.model_dump())
    db.add(policy)
    await db.flush()
    return SlaPolicyOut.model_validate(policy)


@router.patch("/sla/{policy_id}", response_model=SlaPolicyOut)
async def update_sla(policy_id: str, payload: SlaPolicyPatch, user: Manager, db: DbDep) -> SlaPolicyOut:
    policy = await _owned(db, SlaPolicy, policy_id, user.workspace_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(policy, field, value)
    await db.flush()
    return SlaPolicyOut.model_validate(policy)


@router.delete("/sla/{policy_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_sla(policy_id: str, user: Manager, db: DbDep) -> None:
    await db.delete(await _owned(db, SlaPolicy, policy_id, user.workspace_id))


@router.get("/routing", response_model=list[RoutingRuleOut])
async def list_routing(user: CurrentUser, db: DbDep) -> list[RoutingRuleOut]:
    rules = (
        await db.execute(
            select(RoutingRule)
            .where(RoutingRule.workspace_id == user.workspace_id)
            .order_by(RoutingRule.order_index)
        )
    ).scalars()
    return [RoutingRuleOut.model_validate(rule) for rule in rules]


@router.post("/routing", response_model=RoutingRuleOut, status_code=status.HTTP_201_CREATED)
async def create_routing(payload: RoutingRuleIn, user: Manager, db: DbDep) -> RoutingRuleOut:
    rule = RoutingRule(workspace_id=user.workspace_id, **payload.model_dump())
    db.add(rule)
    await db.flush()
    return RoutingRuleOut.model_validate(rule)


@router.patch("/routing/{rule_id}", response_model=RoutingRuleOut)
async def update_routing(
    rule_id: str, payload: RoutingRulePatch, user: Manager, db: DbDep
) -> RoutingRuleOut:
    rule = await _owned(db, RoutingRule, rule_id, user.workspace_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(rule, field, value)
    await db.flush()
    return RoutingRuleOut.model_validate(rule)


@router.delete("/routing/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_routing(rule_id: str, user: Manager, db: DbDep) -> None:
    await db.delete(await _owned(db, RoutingRule, rule_id, user.workspace_id))


@router.get("/channels/catalog")
async def catalog(user: CurrentUser) -> list[dict]:
    """Every channel the build supports, and what each one needs configured."""
    return channel_catalog()


@router.get("/channels", response_model=list[ChannelOut])
async def list_channels(user: CurrentUser, db: DbDep) -> list[ChannelOut]:
    """Connection status per channel. Credentials are never returned."""
    accounts = {
        account.channel: account
        for account in (
            await db.execute(
                select(ChannelAccount).where(ChannelAccount.workspace_id == user.workspace_id)
            )
        ).scalars()
    }
    results: list[ChannelOut] = []
    for entry in channel_catalog():
        channel = entry["channel"]
        account = accounts.get(channel)
        adapter = get_adapter(channel)
        config = account.live_config() if account else {}
        results.append(
            ChannelOut(
                id=account.id if account else "",
                channel=channel,
                display_name=(account.display_name if account else "") or entry["label"],
                is_active=bool(account and account.is_active),
                configured_keys=sorted(key for key, value in config.items() if value),
                missing_keys=adapter.missing_keys(config) if adapter else [],
                webhook_url=(
                    f"{app_settings.PUBLIC_URL}/api/v1/webhooks/{channel}/{user.workspace_id}"
                    if entry["hasWebhook"]
                    else None
                ),
                last_event_at=account.last_event_at if account else None,
            )
        )
    return results


@router.put("/channels/{channel}", response_model=ChannelOut)
async def upsert_channel(
    channel: str, payload: ChannelIn, user: Manager, db: DbDep
) -> ChannelOut:
    """Connect or update a channel."""
    adapter = get_adapter(channel)
    if adapter is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Unknown channel: {channel}")

    account = await db.scalar(
        select(ChannelAccount).where(
            ChannelAccount.workspace_id == user.workspace_id, ChannelAccount.channel == channel
        )
    )
    if account is None:
        account = ChannelAccount(workspace_id=user.workspace_id, channel=channel)
        db.add(account)

    merged = {**account.live_config(), **payload.config}
    kept = {key: value for key, value in merged.items() if value != ""}
    account.config = {
        key: crypto.seal(value) if isinstance(value, str) else value
        for key, value in kept.items()
    }
    account.display_name = payload.display_name or account.display_name or adapter.label

    missing = adapter.missing_keys(kept)
    if payload.is_active and missing:
        raise HTTPException(
            422,
            f"Cannot activate {channel}: missing {', '.join(missing)}",
        )
    account.is_active = payload.is_active
    await db.flush()

    return ChannelOut(
        id=account.id,
        channel=channel,
        display_name=account.display_name,
        is_active=account.is_active,
        configured_keys=sorted(key for key, value in kept.items() if value),
        missing_keys=missing,
        webhook_url=(
            f"{app_settings.PUBLIC_URL}/api/v1/webhooks/{channel}/{user.workspace_id}"
            if adapter.has_webhook
            else None
        ),
        last_event_at=account.last_event_at,
    )


async def _owned(db, model, record_id: str, workspace_id: str):
    record = await db.get(model, record_id)
    if record is None or record.workspace_id != workspace_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"{model.__name__} not found")
    return record
