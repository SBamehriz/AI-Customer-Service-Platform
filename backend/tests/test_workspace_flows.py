"""Tickets, the inbox, the widget, Tap AI and analytics, end to end."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_ticket_numbers_increment_per_workspace(client: AsyncClient, workspace: dict) -> None:
    numbers = []
    for index in range(3):
        response = await client.post(
            "/api/v1/tickets",
            headers=workspace["headers"],
            json={"subject": f"Issue {index}", "description": "..."},
        )
        assert response.status_code == 201
        numbers.append(response.json()["number"])
    assert numbers == [1, 2, 3]


@pytest.mark.asyncio
async def test_creating_a_ticket_by_email_creates_the_customer(
    client: AsyncClient, workspace: dict
) -> None:
    response = await client.post(
        "/api/v1/tickets",
        headers=workspace["headers"],
        json={
            "subject": "Broken zip",
            "customerEmail": "new.person@example.com",
            "customerName": "New Person",
        },
    )
    assert response.status_code == 201
    assert response.json()["customer"]["email"] == "new.person@example.com"

    customers = (await client.get("/api/v1/customers", headers=workspace["headers"])).json()
    assert [c["email"] for c in customers] == ["new.person@example.com"]


@pytest.mark.asyncio
async def test_resolving_a_ticket_stamps_and_clears_resolved_at(
    client: AsyncClient, workspace: dict
) -> None:
    ticket_id = (
        await client.post(
            "/api/v1/tickets", headers=workspace["headers"], json={"subject": "To resolve"}
        )
    ).json()["id"]

    solved = await client.patch(
        f"/api/v1/tickets/{ticket_id}", headers=workspace["headers"], json={"status": "solved"}
    )
    assert solved.json()["resolvedAt"] is not None

    reopened = await client.patch(
        f"/api/v1/tickets/{ticket_id}", headers=workspace["headers"], json={"status": "open"}
    )
    assert reopened.json()["resolvedAt"] is None


@pytest.mark.asyncio
async def test_sla_due_date_follows_the_policy(client: AsyncClient, workspace: dict) -> None:
    await client.post(
        "/api/v1/workspace/sla",
        headers=workspace["headers"],
        json={
            "name": "Urgent",
            "priorities": ["urgent"],
            "firstResponseMinutes": 15,
            "resolutionMinutes": 120,
        },
    )
    ticket = (
        await client.post(
            "/api/v1/tickets",
            headers=workspace["headers"],
            json={"subject": "Escalating fast", "priority": "urgent"},
        )
    ).json()
    assert ticket["slaDueAt"] is not None


@pytest.mark.asyncio
async def test_ticket_filters(client: AsyncClient, workspace: dict) -> None:
    await client.post(
        "/api/v1/tickets",
        headers=workspace["headers"],
        json={"subject": "Urgent thing", "priority": "urgent", "channel": "email"},
    )
    await client.post(
        "/api/v1/tickets",
        headers=workspace["headers"],
        json={"subject": "Calm thing", "priority": "low", "channel": "web"},
    )

    urgent = (
        await client.get(
            "/api/v1/tickets", headers=workspace["headers"], params={"priority": "urgent"}
        )
    ).json()
    assert [t["subject"] for t in urgent] == ["Urgent thing"]

    by_channel = (
        await client.get("/api/v1/tickets", headers=workspace["headers"], params={"channel": "web"})
    ).json()
    assert [t["subject"] for t in by_channel] == ["Calm thing"]

    searched = (
        await client.get("/api/v1/tickets", headers=workspace["headers"], params={"search": "calm"})
    ).json()
    assert len(searched) == 1


@pytest.fixture(autouse=True)
def _clear_rate_limits():
    """Each test starts with a full allowance."""
    from app.ratelimit import widget_addresses, widget_messages

    widget_messages.reset()
    widget_addresses.reset()
    yield
    widget_messages.reset()
    widget_addresses.reset()


@pytest.mark.asyncio
async def test_widget_config_is_public(client: AsyncClient, workspace: dict) -> None:
    key = workspace["workspace"]["publicKey"]
    response = await client.get(f"/api/v1/widget/{key}/config")
    assert response.status_code == 200
    assert response.json()["workspaceName"] == "Test Outfitters"
    # No provider in tests, so the widget is told AI is off.
    assert response.json()["aiEnabled"] is False


@pytest.mark.asyncio
async def test_portal_finds_the_only_workspace_without_a_key(
    client: AsyncClient, workspace: dict
) -> None:
    """The hosted portal serves people who are not signed in."""
    response = await client.get("/api/v1/widget/default/config")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["publicKey"] == workspace["workspace"]["publicKey"]
    assert body["workspaceName"] == "Test Outfitters"


@pytest.mark.asyncio
async def test_default_lookup_needs_a_key_when_there_are_several(
    client: AsyncClient, workspace: dict
) -> None:
    """With more than one workspace, guessing would be wrong."""
    await client.post(
        "/api/v1/auth/register",
        json={
            "workspaceName": "Second Co",
            "name": "Bee",
            "email": "bee@second.example",
            "password": "another-long-password",
        },
    )
    response = await client.get("/api/v1/widget/default/config")
    assert response.status_code == 404
    assert "workspace key is required" in response.json()["detail"]


@pytest.mark.asyncio
async def test_widget_rejects_an_unknown_key(client: AsyncClient) -> None:
    assert (await client.get("/api/v1/widget/pk_nope/config")).status_code == 404


@pytest.mark.asyncio
async def test_widget_message_creates_a_conversation_and_replays(
    client: AsyncClient, workspace: dict
) -> None:
    key = workspace["workspace"]["publicKey"]
    first = await client.post(
        f"/api/v1/widget/{key}/messages",
        json={"body": "Do you ship to Canada?", "name": "Visitor"},
    )
    assert first.status_code == 200
    session_id = first.json()["sessionId"]
    assert session_id.startswith("web_")

    # The same session id continues the same thread.
    second = await client.post(
        f"/api/v1/widget/{key}/messages",
        json={"sessionId": session_id, "body": "Specifically to Ontario."},
    )
    assert second.json()["conversationId"] == first.json()["conversationId"]

    replay = await client.get(f"/api/v1/widget/{key}/sessions/{session_id}")
    bodies = [message["body"] for message in replay.json()]
    assert "Do you ship to Canada?" in bodies
    assert "Specifically to Ontario." in bodies


@pytest.mark.asyncio
async def test_widget_messages_are_rate_limited(client: AsyncClient, workspace: dict) -> None:
    """The one unauthenticated write path must not accept unlimited traffic."""
    from app.ratelimit import widget_messages

    key = workspace["workspace"]["publicKey"]
    session_id = "web_flooder"

    statuses = []
    for index in range(widget_messages.limit + 2):
        response = await client.post(
            f"/api/v1/widget/{key}/messages",
            json={"sessionId": session_id, "body": f"message {index}"},
        )
        statuses.append(response.status_code)

    assert statuses[0] == 200
    assert 429 in statuses, statuses


@pytest.mark.asyncio
async def test_rotating_session_ids_still_hit_a_ceiling(
    client: AsyncClient, workspace: dict
) -> None:
    """The session id comes from the client, so it cannot be the only limit."""
    from app.ratelimit import widget_addresses

    key = workspace["workspace"]["publicKey"]

    statuses = []
    for index in range(widget_addresses.limit + 2):
        # A new session id every time, which defeats the per session window.
        response = await client.post(
            f"/api/v1/widget/{key}/messages",
            json={"sessionId": f"web_rotating_{index}", "body": f"message {index}"},
        )
        statuses.append(response.status_code)

    assert statuses[0] == 200
    assert 429 in statuses, statuses


@pytest.mark.asyncio
async def test_accent_colour_must_be_a_colour(client: AsyncClient, workspace: dict) -> None:
    """It is interpolated into the widget stylesheet, so it cannot be free text."""
    bad = await client.patch(
        "/api/v1/workspace",
        headers=workspace["headers"],
        json={"accentColor": "red} body{display:none"},
    )
    assert bad.status_code == 422

    good = await client.patch(
        "/api/v1/workspace", headers=workspace["headers"], json={"accentColor": "#10B981"}
    )
    assert good.status_code == 200
    assert good.json()["accentColor"] == "#10B981"


@pytest.mark.asyncio
async def test_widget_replay_hides_internal_notes(client: AsyncClient, workspace: dict) -> None:
    key = workspace["workspace"]["publicKey"]
    started = await client.post(f"/api/v1/widget/{key}/messages", json={"body": "Question here"})
    session_id = started.json()["sessionId"]
    conversation_id = started.json()["conversationId"]

    await client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        headers=workspace["headers"],
        json={"body": "Internal: check their order history", "isPrivate": True},
    )

    replay = (await client.get(f"/api/v1/widget/{key}/sessions/{session_id}")).json()
    assert all("Internal:" not in message["body"] for message in replay)


@pytest.mark.asyncio
async def test_agent_reply_assigns_and_starts_the_response_clock(
    client: AsyncClient, workspace: dict
) -> None:
    key = workspace["workspace"]["publicKey"]
    started = await client.post(f"/api/v1/widget/{key}/messages", json={"body": "Help please"})
    conversation_id = started.json()["conversationId"]

    reply = await client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        headers=workspace["headers"],
        json={"body": "On it now."},
    )
    assert reply.status_code == 201

    conversation = (
        await client.get(f"/api/v1/conversations/{conversation_id}", headers=workspace["headers"])
    ).json()
    assert conversation["assignedUserId"] == workspace["user"]["id"]

    ticket_id = conversation["ticketId"]
    ticket = (await client.get(f"/api/v1/tickets/{ticket_id}", headers=workspace["headers"])).json()
    assert ticket["firstResponseAt"] is not None
    assert ticket["status"] == "open"


@pytest.mark.asyncio
async def test_resolving_a_conversation_solves_its_ticket(
    client: AsyncClient, workspace: dict
) -> None:
    key = workspace["workspace"]["publicKey"]
    started = await client.post(f"/api/v1/widget/{key}/messages", json={"body": "One more thing"})
    conversation_id = started.json()["conversationId"]

    await client.patch(
        f"/api/v1/conversations/{conversation_id}",
        headers=workspace["headers"],
        json={"status": "resolved"},
    )
    conversation = (
        await client.get(f"/api/v1/conversations/{conversation_id}", headers=workspace["headers"])
    ).json()
    ticket = (
        await client.get(f"/api/v1/tickets/{conversation['ticketId']}", headers=workspace["headers"])
    ).json()
    assert ticket["status"] == "solved"


@pytest.mark.asyncio
async def test_uncovered_question_escalates_to_a_human(
    client: AsyncClient, workspace: dict
) -> None:
    """With an empty knowledge base the AI must hand over, not improvise."""
    key = workspace["workspace"]["publicKey"]
    response = await client.post(
        f"/api/v1/widget/{key}/messages", json={"body": "Do you rent snowmobiles by the week?"}
    )
    assert response.json()["escalated"] is True
    assert response.json()["reply"] is None


@pytest.mark.asyncio
async def test_inbox_stats(client: AsyncClient, workspace: dict) -> None:
    key = workspace["workspace"]["publicKey"]
    await client.post(f"/api/v1/widget/{key}/messages", json={"body": "First question"})
    stats = (
        await client.get("/api/v1/conversations/stats/overview", headers=workspace["headers"])
    ).json()
    assert stats["escalated"] >= 1
    assert stats["unassigned"] >= 1


@pytest.mark.asyncio
async def test_tap_session_records_transcript_and_suggests(
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

    session = await client.post(
        "/api/v1/tap/sessions", headers=workspace["headers"], json={"customerLabel": "Caller"}
    )
    assert session.status_code == 201
    session_id = session.json()["id"]

    updated = await client.post(
        f"/api/v1/tap/sessions/{session_id}/utterances",
        headers=workspace["headers"],
        json={"speaker": "customer", "text": "I want to return an unused jacket, is that possible?"},
    )
    body = updated.json()
    assert len(body["transcript"]) == 1
    assert body["suggestions"], "a covered question should produce a suggestion"
    assert body["suggestions"][0]["citations"]


@pytest.mark.asyncio
async def test_tap_ignores_short_fragments(client: AsyncClient, workspace: dict) -> None:
    """'A filler noise should be transcribed but must not trigger a suggestion."""
    session_id = (
        await client.post("/api/v1/tap/sessions", headers=workspace["headers"], json={})
    ).json()["id"]

    body = (
        await client.post(
            f"/api/v1/tap/sessions/{session_id}/utterances",
            headers=workspace["headers"],
            json={"speaker": "customer", "text": "mm-hm"},
        )
    ).json()
    assert len(body["transcript"]) == 1
    assert body["suggestions"] == []


@pytest.mark.asyncio
async def test_tap_agent_turns_do_not_suggest(client: AsyncClient, workspace: dict) -> None:
    session_id = (
        await client.post("/api/v1/tap/sessions", headers=workspace["headers"], json={})
    ).json()["id"]
    body = (
        await client.post(
            f"/api/v1/tap/sessions/{session_id}/utterances",
            headers=workspace["headers"],
            json={"speaker": "agent", "text": "Let me look that up for you right now."},
        )
    ).json()
    assert body["suggestions"] == []


@pytest.mark.asyncio
async def test_tap_session_can_be_ended(client: AsyncClient, workspace: dict) -> None:
    session_id = (
        await client.post("/api/v1/tap/sessions", headers=workspace["headers"], json={})
    ).json()["id"]
    ended = await client.post(
        f"/api/v1/tap/sessions/{session_id}/end", headers=workspace["headers"]
    )
    assert ended.json()["status"] == "ended"
    assert ended.json()["endedAt"] is not None


@pytest.mark.asyncio
async def test_analytics_summary_on_an_empty_workspace(
    client: AsyncClient, workspace: dict
) -> None:
    """A brand new workspace must render, not divide by zero."""
    response = await client.get("/api/v1/analytics/summary", headers=workspace["headers"])
    assert response.status_code == 200
    body = response.json()
    assert body["openTickets"] == 0
    assert body["csat"] == 0
    # A 30 day window starts partway through a day, so it touches 31 dates.
    assert len(body["series"]) == 31


@pytest.mark.asyncio
async def test_analytics_counts_open_tickets(client: AsyncClient, workspace: dict) -> None:
    for index in range(4):
        await client.post(
            "/api/v1/tickets", headers=workspace["headers"], json={"subject": f"T{index}"}
        )
    body = (
        await client.get(
            "/api/v1/analytics/summary", headers=workspace["headers"], params={"rangeDays": 7}
        )
    ).json()
    assert body["openTickets"] == 4
    assert body["rangeDays"] == 7
    assert len(body["series"]) == 8
    assert body["channelMix"][0]["label"] == "web"
    assert sum(point["created"] for point in body["series"]) == 4


@pytest.mark.asyncio
async def test_workload_endpoint(client: AsyncClient, workspace: dict) -> None:
    key = workspace["workspace"]["publicKey"]
    await client.post(f"/api/v1/widget/{key}/messages", json={"body": "A question"})
    body = (await client.get("/api/v1/analytics/workload", headers=workspace["headers"])).json()
    assert body["escalated"] >= 1
    assert body["unassigned"] >= 1
    assert body["byChannel"]


@pytest.mark.asyncio
async def test_macro_crud(client: AsyncClient, workspace: dict) -> None:
    created = await client.post(
        "/api/v1/workspace/macros",
        headers=workspace["headers"],
        json={"name": "Return started", "body": "Your label is on the way."},
    )
    assert created.status_code == 201
    macro_id = created.json()["id"]

    listed = (await client.get("/api/v1/workspace/macros", headers=workspace["headers"])).json()
    assert len(listed) == 1

    assert (
        await client.delete(f"/api/v1/workspace/macros/{macro_id}", headers=workspace["headers"])
    ).status_code == 204


@pytest.mark.asyncio
async def test_workspace_settings_are_camel_case_on_the_wire(
    client: AsyncClient, workspace: dict
) -> None:
    """Settings are an open dict, so the alias generator does not reach them."""
    body = (await client.get("/api/v1/workspace", headers=workspace["headers"])).json()
    settings = body["settings"]
    assert "brandVoice" in settings
    assert "aiAutoreply" in settings
    assert "escalateAfterAiTurns" in settings
    assert not any("_" in key for key in settings), settings


@pytest.mark.asyncio
async def test_workspace_settings_round_trip(client: AsyncClient, workspace: dict) -> None:
    """A camelCase patch must come back camelCase and keep its value."""
    patched = await client.patch(
        "/api/v1/workspace",
        headers=workspace["headers"],
        json={"settings": {"aiAutoreply": False, "escalateAfterAiTurns": 7}},
    )
    settings = patched.json()["settings"]
    assert settings["aiAutoreply"] is False
    assert settings["escalateAfterAiTurns"] == 7

    reread = (await client.get("/api/v1/workspace", headers=workspace["headers"])).json()
    assert reread["settings"]["aiAutoreply"] is False
    assert reread["settings"]["escalateAfterAiTurns"] == 7


@pytest.mark.asyncio
async def test_workspace_settings_merge_rather_than_replace(
    client: AsyncClient, workspace: dict
) -> None:
    original = (await client.get("/api/v1/workspace", headers=workspace["headers"])).json()
    assert original["settings"]["greeting"]

    patched = await client.patch(
        "/api/v1/workspace",
        headers=workspace["headers"],
        json={"settings": {"brandVoice": "Terse and technical"}},
    )
    settings = patched.json()["settings"]
    assert settings["brandVoice"] == "Terse and technical"
    # The untouched key survives the partial save.
    assert settings["greeting"] == original["settings"]["greeting"]


@pytest.mark.asyncio
async def test_routing_rule_ordering(client: AsyncClient, workspace: dict) -> None:
    for index, name in enumerate(["Second", "First"]):
        await client.post(
            "/api/v1/workspace/routing",
            headers=workspace["headers"],
            json={"name": name, "orderIndex": 1 - index, "conditions": {}, "actions": {}},
        )
    rules = (await client.get("/api/v1/workspace/routing", headers=workspace["headers"])).json()
    assert [rule["name"] for rule in rules] == ["First", "Second"]


@pytest.mark.asyncio
async def test_channel_catalog_lists_every_channel(client: AsyncClient, workspace: dict) -> None:
    catalog = (
        await client.get("/api/v1/workspace/channels/catalog", headers=workspace["headers"])
    ).json()
    assert {entry["channel"] for entry in catalog} == {
        "web",
        "email",
        "whatsapp",
        "instagram",
        "sms",
        "voice",
        "api",
    }


@pytest.mark.asyncio
async def test_health_reports_configuration(client: AsyncClient) -> None:
    from app.config import settings

    body = (await client.get("/health")).json()
    assert body["status"] == "ok"
    # The suite runs on both, so this checks it reports the one in use.
    assert body["database"] == ("sqlite" if settings.is_sqlite else "postgresql")
    assert body["databaseReady"] is True
    assert body["ai"]["enabled"] is False
    assert "whatsapp" in body["channels"]


@pytest.mark.asyncio
async def test_limiter_keeps_counting_past_its_cleanup_threshold() -> None:
    """The limiter only forgets a caller once their window has fully passed."""
    from app.ratelimit import RateLimiter

    limiter = RateLimiter(limit=5, window_seconds=60)
    for index in range(20_000):
        limiter.allow(f"one-off-{index}")

    allowed = sum(limiter.allow("steady-caller") for _ in range(50))
    assert allowed == limiter.limit


@pytest.mark.asyncio
async def test_limiter_forgets_callers_that_have_gone_quiet() -> None:
    """Otherwise the map grows for as long as the process lives."""
    import time

    from app.ratelimit import RateLimiter

    limiter = RateLimiter(limit=5, window_seconds=0.05)
    for index in range(500):
        limiter.allow(f"visitor-{index}")
    assert len(limiter._hits) == 500

    time.sleep(0.1)
    limiter._sweep(time.monotonic())
    assert limiter._hits == {}
