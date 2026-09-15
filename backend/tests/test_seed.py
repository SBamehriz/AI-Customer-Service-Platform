"""The demo fixture must load cleanly. It is the first thing anyone sees."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from app.db import async_session_maker
from app.models import Article, Conversation, Message, TapSession, Ticket, User
from app.seed import load_fixture, seed


@pytest.mark.asyncio
async def test_fixture_seeds_a_complete_workspace(client: AsyncClient) -> None:
    fixture = load_fixture()
    async with async_session_maker() as db:
        workspace = await seed(db, fixture)
        await db.commit()

        assert workspace.name == fixture["workspace"]["name"]
        assert workspace.public_key.startswith("pk_")

        counts = {
            model.__name__: int(
                await db.scalar(select(func.count()).select_from(model)) or 0
            )
            for model in (User, Article, Conversation, Message, Ticket, TapSession)
        }
        assert counts["User"] == len(fixture["users"])
        assert counts["Article"] == len(fixture["articles"])
        assert counts["Conversation"] == len(fixture["conversations"])
        assert counts["TapSession"] == len(fixture["tapSessions"])
        # Handwritten threads plus 90 days of backfilled history.
        assert counts["Ticket"] > len(fixture["conversations"]) + 100
        assert counts["Message"] > 20


@pytest.mark.asyncio
async def test_seeded_users_can_sign_in(client: AsyncClient) -> None:
    fixture = load_fixture()
    async with async_session_maker() as db:
        await seed(db, fixture)
        await db.commit()

    account = fixture["users"][0]
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": account["email"], "password": account["password"]},
    )
    assert response.status_code == 200, response.text
    assert response.json()["user"]["role"] == "owner"


@pytest.mark.asyncio
async def test_seeded_knowledge_answers_a_seeded_question(client: AsyncClient) -> None:
    """Retrieval over the real fixture, not a toy corpus."""
    fixture = load_fixture()
    async with async_session_maker() as db:
        await seed(db, fixture)
        await db.commit()

    account = fixture["users"][0]
    token = (
        await client.post(
            "/api/v1/auth/login",
            json={"email": account["email"], "password": account["password"]},
        )
    ).json()["accessToken"]
    headers = {"Authorization": f"Bearer {token}"}

    hits = (
        await client.get(
            "/api/v1/knowledge/search",
            headers=headers,
            params={"q": "how long do I have to return unused gear"},
        )
    ).json()
    assert hits[0]["title"] == "Returns and exchanges"


@pytest.mark.asyncio
async def test_seeded_analytics_have_history(client: AsyncClient) -> None:
    fixture = load_fixture()
    async with async_session_maker() as db:
        await seed(db, fixture)
        await db.commit()

    account = fixture["users"][0]
    token = (
        await client.post(
            "/api/v1/auth/login",
            json={"email": account["email"], "password": account["password"]},
        )
    ).json()["accessToken"]

    body = (
        await client.get(
            "/api/v1/analytics/summary",
            headers={"Authorization": f"Bearer {token}"},
            params={"rangeDays": 30},
        )
    ).json()
    assert body["openTickets"] > 0
    assert body["csat"] > 0
    assert sum(point["created"] for point in body["series"]) > 0
    assert body["agentLeaderboard"]

    charted = sum(point["created"] for point in body["series"])
    by_channel = sum(entry["value"] for entry in body["channelMix"])
    by_priority = sum(entry["value"] for entry in body["priorityMix"])
    assert charted == by_channel == by_priority, (charted, by_channel, by_priority)

    backlog = sum(entry["value"] for entry in body["openPriorityMix"])
    assert backlog == body["openTickets"], (backlog, body["openTickets"])
