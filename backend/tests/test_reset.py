"""Clearing a workspace back to empty."""

from __future__ import annotations

import io

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.db import async_session_maker
from app.models import Attachment, Conversation, Customer, Ticket, User


async def _fill(client: AsyncClient, workspace: dict) -> None:
    key = workspace["workspace"]["publicKey"]
    await client.post(f"/api/v1/widget/{key}/messages", json={"body": "Where is my order"})
    await client.post(
        "/api/v1/knowledge",
        headers=workspace["headers"],
        json={"title": "Returns", "body": "Sixty days.", "status": "published"},
    )
    await client.post(
        "/api/v1/attachments",
        headers=workspace["headers"],
        files={"file": ("photo.png", io.BytesIO(b"\x89PNG\r\n\x1a\n" + b"0" * 40), "image/png")},
    )


@pytest.mark.asyncio
async def test_reset_clears_the_traffic_and_keeps_the_team(
    client: AsyncClient, workspace: dict
) -> None:
    await _fill(client, workspace)
    await client.post(
        "/api/v1/workspace/team",
        headers=workspace["headers"],
        json={"name": "Sam", "email": "sam@team.example", "password": "long-enough-pass"},
    )

    response = await client.post(
        "/api/v1/workspace/reset",
        headers=workspace["headers"],
        json={"confirm": "Test Outfitters"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["ok"] is True

    async with async_session_maker() as db:
        assert (await db.execute(select(Conversation))).scalars().all() == []
        assert (await db.execute(select(Ticket))).scalars().all() == []
        assert (await db.execute(select(Customer))).scalars().all() == []
        assert (await db.execute(select(Attachment))).scalars().all() == []
        # The team is still there, which is the point of keeping it.
        assert len((await db.execute(select(User))).scalars().all()) == 2

    # The workspace itself survives, so you can keep working in it.
    profile = await client.get("/api/v1/workspace", headers=workspace["headers"])
    assert profile.status_code == 200
    assert profile.json()["name"] == "Test Outfitters"
    assert (await client.get("/api/v1/knowledge", headers=workspace["headers"])).json() == []


@pytest.mark.asyncio
async def test_reset_can_also_clear_the_team(client: AsyncClient, workspace: dict) -> None:
    """Starting completely fresh, except for whoever is doing it."""
    await client.post(
        "/api/v1/workspace/team",
        headers=workspace["headers"],
        json={"name": "Sam", "email": "sam@team.example", "password": "long-enough-pass"},
    )
    response = await client.post(
        "/api/v1/workspace/reset",
        headers=workspace["headers"],
        json={"confirm": "Test Outfitters", "keepTeam": False},
    )
    assert response.status_code == 200

    remaining = await client.get("/api/v1/workspace/team", headers=workspace["headers"])
    # Only the person who did it, who would otherwise be locked out.
    assert [u["email"] for u in remaining.json()] == [workspace["user"]["email"]]


@pytest.mark.asyncio
async def test_the_wrong_name_does_not_delete_anything(
    client: AsyncClient, workspace: dict
) -> None:
    """This is not a button anyone should be able to hit by accident."""
    await _fill(client, workspace)
    response = await client.post(
        "/api/v1/workspace/reset",
        headers=workspace["headers"],
        json={"confirm": "test outfitters"},
    )
    assert response.status_code == 400
    assert "Test Outfitters" in response.json()["detail"]

    async with async_session_maker() as db:
        assert (await db.execute(select(Conversation))).scalars().all() != []


@pytest.mark.asyncio
async def test_agents_cannot_reset_the_workspace(
    client: AsyncClient, workspace: dict
) -> None:
    await client.post(
        "/api/v1/workspace/team",
        headers=workspace["headers"],
        json={"name": "A", "email": "a@reset.example", "password": "long-enough-pass",
              "role": "agent"},
    )
    session = await client.post(
        "/api/v1/auth/login",
        json={"email": "a@reset.example", "password": "long-enough-pass"},
    )
    headers = {"Authorization": f"Bearer {session.json()['accessToken']}"}
    response = await client.post(
        "/api/v1/workspace/reset", headers=headers, json={"confirm": "Test Outfitters"}
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_one_workspace_reset_leaves_others_alone(
    client: AsyncClient, workspace: dict
) -> None:
    """Deleting by workspace id, not deleting everything in the table."""
    await _fill(client, workspace)
    other = await client.post(
        "/api/v1/auth/register",
        json={
            "workspaceName": "Neighbour Co",
            "name": "Nia",
            "email": "nia@neighbour.example",
            "password": "correct-horse-battery",
        },
    )
    headers = {"Authorization": f"Bearer {other.json()['accessToken']}"}
    await client.post(
        "/api/v1/knowledge",
        headers=headers,
        json={"title": "Theirs", "body": "Not yours.", "status": "published"},
    )

    await client.post(
        "/api/v1/workspace/reset",
        headers=workspace["headers"],
        json={"confirm": "Test Outfitters"},
    )

    theirs = await client.get("/api/v1/knowledge", headers=headers)
    assert [a["title"] for a in theirs.json()] == ["Theirs"]
