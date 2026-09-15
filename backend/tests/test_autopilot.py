"""Working the queue on its own."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.db import async_session_maker
from app.models import Conversation, Message, Workspace, utcnow
from app.services import autopilot


def test_the_schedule_understands_how_people_write_hours() -> None:
    assert sorted(autopilot.hours_from_setting("9-17")) == list(range(9, 18))
    assert sorted(autopilot.hours_from_setting([9, 10])) == [9, 10]
    assert sorted(autopilot.hours_from_setting("0,6-8,23")) == [0, 6, 7, 8, 23]
    # Overnight is the obvious thing to want, so a wrapping range works.
    assert sorted(autopilot.hours_from_setting("22-2")) == [0, 1, 2, 22, 23]
    assert autopilot.hours_from_setting("") == set()
    assert autopilot.hours_from_setting("nonsense") == set()


def test_it_only_runs_when_it_is_both_on_and_scheduled() -> None:
    at_ten = datetime(2026, 1, 1, 10, tzinfo=UTC)
    assert autopilot.should_run_now({"autopilot_enabled": True, "autopilot_hours": "9-17"}, at_ten)
    assert not autopilot.should_run_now(
        {"autopilot_enabled": True, "autopilot_hours": "18-23"}, at_ten
    )
    # On with no hours set does nothing, rather than running all day.
    assert not autopilot.should_run_now({"autopilot_enabled": True}, at_ten)
    assert not autopilot.should_run_now({"autopilot_hours": "9-17"}, at_ten)


async def _waiting_conversation(client: AsyncClient, workspace: dict, body: str) -> str:
    """A customer message old enough for autopilot to consider."""
    key = workspace["workspace"]["publicKey"]
    started = await client.post(f"/api/v1/widget/{key}/messages", json={"body": body})
    conversation_id = started.json()["conversationId"]
    async with async_session_maker() as db:
        conversation = await db.get(Conversation, conversation_id)
        conversation.last_message_at = utcnow() - timedelta(hours=1)
        conversation.status = "open"
        conversation.assigned_user_id = None
        # Clear any live autoreply, so the customer is the one waiting.
        for message in (
            await db.execute(
                select(Message).where(Message.conversation_id == conversation_id)
            )
        ).scalars():
            if message.author_type == "ai":
                await db.delete(message)
        await db.commit()
    return conversation_id


async def _run(workspace: dict) -> dict:
    async with async_session_maker() as db:
        ws = await db.scalar(
            select(Workspace).where(Workspace.id == workspace["workspace"]["id"])
        )
        result = await autopilot.run_once(db, ws)
        await db.commit()
        return result


@pytest.mark.asyncio
async def test_it_answers_what_the_knowledge_base_covers(
    client: AsyncClient, workspace: dict
) -> None:
    await client.post(
        "/api/v1/knowledge",
        headers=workspace["headers"],
        json={
            "title": "Returns and exchanges",
            "body": "Unused gear can be returned within 60 days of delivery for a full refund.",
            "status": "published",
        },
    )
    conversation_id = await _waiting_conversation(
        client, workspace, "I want to return an unused jacket, how long do I have"
    )

    result = await _run(workspace)
    assert result["lookedAt"] >= 1
    assert result["answered"] == 1, result

    thread = await client.get(
        f"/api/v1/conversations/{conversation_id}", headers=workspace["headers"]
    )
    replies = [m for m in thread.json()["messages"] if m["authorType"] == "ai"]
    assert replies, "it should have written something"
    # Marked, so nobody mistakes a scheduled answer for a live one.
    assert replies[-1]["meta"]["autopilot"] is True
    assert replies[-1]["meta"]["citations"], "an answer has to carry its source"


@pytest.mark.asyncio
async def test_it_leaves_what_it_cannot_answer(client: AsyncClient, workspace: dict) -> None:
    """The whole point is that it does not guess."""
    conversation_id = await _waiting_conversation(
        client, workspace, "Can you help me apply for a mortgage on a houseboat"
    )
    result = await _run(workspace)
    assert result["answered"] == 0
    assert result["escalated"] == 1

    thread = await client.get(
        f"/api/v1/conversations/{conversation_id}", headers=workspace["headers"]
    )
    assert thread.json()["status"] == "escalated"
    assert not [m for m in thread.json()["messages"] if m["authorType"] == "ai"]


@pytest.mark.asyncio
async def test_it_never_touches_a_conversation_somebody_owns(
    client: AsyncClient, workspace: dict
) -> None:
    """An assigned conversation has a person mid reply on the other side."""
    await client.post(
        "/api/v1/knowledge",
        headers=workspace["headers"],
        json={"title": "Returns", "body": "Sixty days for a full refund.", "status": "published"},
    )
    conversation_id = await _waiting_conversation(client, workspace, "How long for returns")
    async with async_session_maker() as db:
        conversation = await db.get(Conversation, conversation_id)
        conversation.assigned_user_id = workspace["user"]["id"]
        await db.commit()

    result = await _run(workspace)
    assert result["lookedAt"] == 0
    assert result["answered"] == 0


@pytest.mark.asyncio
async def test_it_does_not_take_two_turns_in_a_row(
    client: AsyncClient, workspace: dict
) -> None:
    """Otherwise a customer who never replies gets answered every hour."""
    await client.post(
        "/api/v1/knowledge",
        headers=workspace["headers"],
        json={
            "title": "Returns and exchanges",
            "body": "You can return unused gear within 60 days of delivery for a full refund.",
            "status": "published",
        },
    )
    await _waiting_conversation(
        client, workspace, "I want to return an unused jacket, how long do I have"
    )

    first = await _run(workspace)
    assert first["answered"] == 1

    second = await _run(workspace)
    assert second["answered"] == 0, "it answered the same waiting customer twice"


@pytest.mark.asyncio
async def test_a_fresh_message_is_left_alone(client: AsyncClient, workspace: dict) -> None:
    """Somebody may be typing a reply right now."""
    key = workspace["workspace"]["publicKey"]
    await client.post(f"/api/v1/widget/{key}/messages", json={"body": "Just arrived"})
    result = await _run(workspace)
    assert result["lookedAt"] == 0


@pytest.mark.asyncio
async def test_the_button_and_the_status_are_supervisor_only(
    client: AsyncClient, workspace: dict
) -> None:
    status_response = await client.get("/api/v1/workspace/autopilot", headers=workspace["headers"])
    assert status_response.status_code == 200
    assert status_response.json()["enabled"] is False

    await client.post(
        "/api/v1/workspace/team",
        headers=workspace["headers"],
        json={"name": "A", "email": "a@auto.example", "password": "long-enough-pass",
              "role": "agent"},
    )
    session = await client.post(
        "/api/v1/auth/login", json={"email": "a@auto.example", "password": "long-enough-pass"}
    )
    headers = {"Authorization": f"Bearer {session.json()['accessToken']}"}
    assert (await client.get("/api/v1/workspace/autopilot", headers=headers)).status_code == 403
    assert (await client.post("/api/v1/workspace/autopilot/run", headers=headers)).status_code == 403


@pytest.mark.asyncio
async def test_the_run_result_is_camel_case(client: AsyncClient, workspace: dict) -> None:
    """The API is camelCase, and this route returns a plain dict."""
    response = await client.post(
        "/api/v1/workspace/autopilot/run", headers=workspace["headers"]
    )
    assert response.status_code == 200
    body = response.json()
    assert "lookedAt" in body and "ranAt" in body
    assert "looked_at" not in body and "ran_at" not in body
