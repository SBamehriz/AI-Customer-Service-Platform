"""Snapshots and exports."""

from __future__ import annotations

import json
import sqlite3

import pytest
from httpx import AsyncClient

from app import backup


@pytest.mark.asyncio
async def test_export_has_the_data_and_none_of_the_secrets(
    client: AsyncClient, workspace: dict
) -> None:
    secret = "twilio-token-should-never-appear"
    await client.put(
        "/api/v1/workspace/channels/sms",
        headers=workspace["headers"],
        json={"isActive": False, "config": {"account_sid": "AC1", "auth_token": secret,
                                            "from_number": "+15550100"}},
    )
    await client.put(
        "/api/v1/workspace/ai",
        headers=workspace["headers"],
        json={"provider": "openai", "model": "gpt-4o-mini", "apiKey": "sk-also-secret"},
    )
    await client.post(
        "/api/v1/knowledge",
        headers=workspace["headers"],
        json={"title": "Returns", "body": "Sixty days.", "status": "published"},
    )
    await client.post(
        "/api/v1/tickets", headers=workspace["headers"], json={"subject": "Where is my order"}
    )
    key = workspace["workspace"]["publicKey"]
    await client.post(f"/api/v1/widget/{key}/messages", json={"body": "Is my parcel moving"})

    response = await client.get("/api/v1/workspace/export", headers=workspace["headers"])
    assert response.status_code == 200
    assert "attachment" in response.headers.get("content-disposition", "")

    raw = response.text
    assert secret not in raw, "a channel credential leaked into the export"
    assert "sk-also-secret" not in raw, "the provider key leaked into the export"

    body = response.json()
    assert body["formatVersion"] == 1
    # A real workspace has customers, and the export has to survive them.
    assert body["customers"], "the widget message should have created a customer"
    assert "channelIds" in body["customers"][0]
    assert body["workspace"]["name"] == "Test Outfitters"
    assert any(a["title"] == "Returns" for a in body["articles"])
    assert any(t["subject"] == "Where is my order" for t in body["tickets"])
    assert body["users"], "the team should be in the export"
    assert all("password" not in json.dumps(u) for u in body["users"])
    # Channel names travel, values do not.
    assert body["channels"][0]["configuredKeys"] == ["account_sid", "auth_token", "from_number"]


@pytest.mark.asyncio
async def test_agents_cannot_export_the_workspace(
    client: AsyncClient, workspace: dict
) -> None:
    """An export is every customer record in one file."""
    await client.post(
        "/api/v1/workspace/team",
        headers=workspace["headers"],
        json={"name": "A", "email": "a@export.example", "password": "long-enough-pass",
              "role": "agent"},
    )
    session = await client.post(
        "/api/v1/auth/login",
        json={"email": "a@export.example", "password": "long-enough-pass"},
    )
    headers = {"Authorization": f"Bearer {session.json()['accessToken']}"}
    assert (await client.get("/api/v1/workspace/export", headers=headers)).status_code == 403
    assert (await client.get("/api/v1/workspace/backups", headers=headers)).status_code == 403


def test_a_snapshot_is_a_working_database(tmp_path, monkeypatch) -> None:
    """A byte copy of a live SQLite file can be torn. This uses the backup API."""
    source = tmp_path / "live.db"
    connection = sqlite3.connect(source)
    connection.execute("CREATE TABLE notes (id INTEGER PRIMARY KEY, body TEXT)")
    connection.executemany("INSERT INTO notes (body) VALUES (?)", [(f"row {i}",) for i in range(50)])
    connection.commit()
    connection.close()

    monkeypatch.setattr(backup, "database_path", lambda: source)
    monkeypatch.setattr(backup, "BACKUP_DIR", tmp_path / "backups")

    path = backup.take_snapshot()
    assert path is not None and path.exists()

    restored = sqlite3.connect(path)
    assert restored.execute("SELECT count(*) FROM notes").fetchone()[0] == 50
    assert restored.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    restored.close()


def test_old_snapshots_are_pruned(tmp_path, monkeypatch) -> None:
    """Otherwise a daily copy of the database quietly fills the disk."""
    source = tmp_path / "live.db"
    sqlite3.connect(source).close()
    monkeypatch.setattr(backup, "database_path", lambda: source)
    monkeypatch.setattr(backup, "BACKUP_DIR", tmp_path / "backups")
    monkeypatch.setattr(backup, "KEEP_SNAPSHOTS", 3)

    for index in range(6):
        (tmp_path / "backups").mkdir(exist_ok=True)
        (tmp_path / "backups" / f"ucsp-2020010{index}T000000Z.db").write_bytes(b"")
    backup.take_snapshot()

    kept = sorted((tmp_path / "backups").glob("ucsp-*.db"))
    assert len(kept) == backup.KEEP_SNAPSHOTS


def test_postgresql_installs_report_snapshots_as_unsupported(monkeypatch) -> None:
    """The snapshot is a SQLite feature, and saying so beats pretending."""
    from app.config import settings

    monkeypatch.setattr(settings, "DATABASE_URL", "postgresql+asyncpg://u:p@host/db")
    assert backup.database_path() is None


@pytest.mark.asyncio
async def test_the_export_survives_a_full_workspace(client: AsyncClient) -> None:
    """A workspace with one ticket in it exercises almost nothing."""
    from sqlalchemy import select

    from app.backup import export_workspace
    from app.db import async_session_maker
    from app.models import Workspace
    from app.seed import load_fixture, seed

    async with async_session_maker() as db:
        await seed(db, load_fixture())
        await db.commit()
        workspace = await db.scalar(select(Workspace).limit(1))
        payload = await export_workspace(db, workspace.id)

    for table in (
        "users", "customers", "articles", "macros", "slaPolicies",
        "routingRules", "tickets", "conversations", "messages", "tapSessions",
    ):
        assert payload[table], f"{table} came back empty from a seeded workspace"

    # It has to survive being written out, which is the whole point.
    text = json.dumps(payload)
    assert "password_hash" not in text and "passwordHash" not in text
    assert "demo1234" not in text
    assert "api_key" not in text and "apiKey" not in text
