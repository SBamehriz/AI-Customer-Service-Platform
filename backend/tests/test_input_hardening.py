"""What happens when a caller sends something the routes did not expect."""

from __future__ import annotations

from pathlib import Path

import pytest
from httpx import AsyncClient

from app.ratelimit import registrations, sign_in_accounts, sign_in_addresses


@pytest.mark.asyncio
async def test_a_null_on_a_required_ticket_field_is_refused(
    client: AsyncClient, workspace: dict
) -> None:
    made = await client.post(
        "/api/v1/tickets", headers=workspace["headers"], json={"subject": "Real"}
    )
    ticket_id = made.json()["id"]

    for field in ("subject", "status", "priority", "tags", "description"):
        response = await client.patch(
            f"/api/v1/tickets/{ticket_id}",
            headers=workspace["headers"],
            json={field: None},
        )
        assert response.status_code == 422, (field, response.status_code, response.text)

    # The nullable ones still accept it, because clearing them is meaningful.
    for field in ("category", "assignedUserId", "satisfaction"):
        response = await client.patch(
            f"/api/v1/tickets/{ticket_id}",
            headers=workspace["headers"],
            json={field: None},
        )
        assert response.status_code == 200, (field, response.text)

    kept = await client.get(f"/api/v1/tickets/{ticket_id}", headers=workspace["headers"])
    assert kept.json()["subject"] == "Real"


@pytest.mark.asyncio
async def test_a_null_on_a_required_article_field_is_refused(
    client: AsyncClient, workspace: dict
) -> None:
    made = await client.post(
        "/api/v1/knowledge",
        headers=workspace["headers"],
        json={"title": "Real", "body": "Words"},
    )
    assert made.status_code == 201, made.text
    article_id = made.json()["id"]

    for field in ("title", "body", "category", "tags", "status", "visibility"):
        response = await client.patch(
            f"/api/v1/knowledge/{article_id}",
            headers=workspace["headers"],
            json={field: None},
        )
        assert response.status_code == 422, (field, response.status_code, response.text)

    # The summary really is optional, so clearing it is allowed.
    cleared = await client.patch(
        f"/api/v1/knowledge/{article_id}",
        headers=workspace["headers"],
        json={"summary": None},
    )
    assert cleared.status_code == 200, cleared.text

    kept = await client.get(f"/api/v1/knowledge/{article_id}", headers=workspace["headers"])
    assert kept.json()["title"] == "Real"


@pytest.mark.asyncio
async def test_whitespace_is_not_a_title_or_a_subject(
    client: AsyncClient, workspace: dict
) -> None:
    ticket = await client.post(
        "/api/v1/tickets", headers=workspace["headers"], json={"subject": "Real"}
    )
    article = await client.post(
        "/api/v1/knowledge",
        headers=workspace["headers"],
        json={"title": "Real", "body": "Words"},
    )
    blank = await client.patch(
        f"/api/v1/tickets/{ticket.json()['id']}",
        headers=workspace["headers"],
        json={"subject": "   "},
    )
    assert blank.status_code == 422, blank.text
    blank = await client.patch(
        f"/api/v1/knowledge/{article.json()['id']}",
        headers=workspace["headers"],
        json={"title": "\t\n "},
    )
    assert blank.status_code == 422, blank.text


@pytest.mark.asyncio
async def test_a_tap_session_needs_a_conversation_that_exists(
    client: AsyncClient, workspace: dict
) -> None:
    """An id for a conversation that does not exist is refused, not left to the database."""
    for value in ("not-a-real-id", " ", "'; DROP TABLE users; --", "a" * 400):
        response = await client.post(
            "/api/v1/tap/sessions",
            headers=workspace["headers"],
            json={"conversationId": value},
        )
        assert response.status_code == 422, (value, response.status_code, response.text)

    # A conversation in another workspace is not this workspace's to attach to.
    other = await client.post(
        "/api/v1/auth/register",
        json={
            "workspaceName": "Elsewhere",
            "name": "Elsewhere Owner",
            "email": "elsewhere@team.example",
            "password": "another-long-password",
        },
    )
    started = await client.post(
        f"/api/v1/widget/{other.json()['workspace']['publicKey']}/messages",
        json={"body": "Hello"},
    )
    theirs = await client.post(
        "/api/v1/tap/sessions",
        headers=workspace["headers"],
        json={"conversationId": started.json()["conversationId"]},
    )
    assert theirs.status_code == 422, theirs.text

    # No conversation at all is still the ordinary case.
    plain = await client.post(
        "/api/v1/tap/sessions", headers=workspace["headers"], json={"customerLabel": "Caller"}
    )
    assert plain.status_code == 201, plain.text

    # And a real one in this workspace is accepted.
    mine = await client.post(
        f"/api/v1/widget/{workspace['workspace']['publicKey']}/messages",
        json={"body": "Hello"},
    )
    linked = await client.post(
        "/api/v1/tap/sessions",
        headers=workspace["headers"],
        json={"conversationId": mine.json()["conversationId"]},
    )
    assert linked.status_code == 201, linked.text


@pytest.mark.asyncio
async def test_guessing_a_password_runs_out_of_attempts(
    client: AsyncClient, workspace: dict
) -> None:
    """Sign in is rate limited, because checking a password is a slow hash on purpose."""
    email = workspace["user"]["email"]
    seen = set()
    for _ in range(sign_in_accounts.limit + 5):
        response = await client.post(
            "/api/v1/auth/login", json={"email": email, "password": "wrong-password"}
        )
        seen.add(response.status_code)
        if response.status_code == 429:
            break
    assert 429 in seen, seen

    blocked = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "correct-horse-battery"},
    )
    assert blocked.status_code == 429

    sign_in_accounts.reset()
    allowed = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "correct-horse-battery"},
    )
    assert allowed.status_code == 200, allowed.text


@pytest.mark.asyncio
async def test_creating_workspaces_runs_out_of_attempts(client: AsyncClient) -> None:
    """An open install would otherwise be free to fill up."""
    statuses = []
    for index in range(registrations.limit + 3):
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "workspaceName": f"Workspace {index}",
                "name": f"Owner {index}",
                "email": f"owner{index}@team.example",
                "password": "another-long-password",
            },
        )
        statuses.append(response.status_code)
    assert 201 in statuses
    assert 429 in statuses, statuses
    assert statuses.count(201) <= registrations.limit


@pytest.mark.asyncio
async def test_the_address_ceiling_is_higher_than_one_account(client: AsyncClient) -> None:
    """An office behind one address must not throttle itself by signing in."""
    assert sign_in_addresses.limit > sign_in_accounts.limit


@pytest.mark.asyncio
async def test_an_empty_assignee_means_nobody(client: AsyncClient, workspace: dict) -> None:
    """Clearing the field from a form sends an empty string, not a null."""
    key = workspace["workspace"]["publicKey"]
    started = await client.post(f"/api/v1/widget/{key}/messages", json={"body": "Hello"})
    conversation_id = started.json()["conversationId"]
    ticket = await client.post(
        "/api/v1/tickets", headers=workspace["headers"], json={"subject": "Real"}
    )

    taken = await client.patch(
        f"/api/v1/conversations/{conversation_id}",
        headers=workspace["headers"],
        json={"assignedUserId": workspace["user"]["id"]},
    )
    assert taken.status_code == 200, taken.text

    for value in ("", "   "):
        cleared = await client.patch(
            f"/api/v1/conversations/{conversation_id}",
            headers=workspace["headers"],
            json={"assignedUserId": value},
        )
        assert cleared.status_code == 200, (value, cleared.text)
        assert cleared.json()["assignedUserId"] is None

        on_ticket = await client.patch(
            f"/api/v1/tickets/{ticket.json()['id']}",
            headers=workspace["headers"],
            json={"assignedUserId": value},
        )
        assert on_ticket.status_code == 200, (value, on_ticket.text)
        assert on_ticket.json()["assignedUserId"] is None

    # Anything that is not empty still has to be somebody who is here.
    refused = await client.patch(
        f"/api/v1/conversations/{conversation_id}",
        headers=workspace["headers"],
        json={"assignedUserId": "not-a-real-user"},
    )
    assert refused.status_code == 422, refused.text


@pytest.mark.asyncio
async def test_the_shortest_common_questions_are_answered(
    client: AsyncClient, workspace: dict
) -> None:
    """A new install writes a few articles and asks the obvious questions."""
    articles = [
        ("Returns and refunds", "Returns",
         "You can return anything unused within 60 days of delivery for a full "
         "refund. Start a return from your order page and we email you a prepaid "
         "label. Refunds land on the original payment method within five working "
         "days of the parcel reaching us."),
        ("Delivery times and tracking", "Delivery",
         "Standard delivery is two to four working days. Express is next working "
         "day if you order before 2pm. Every parcel gets a tracking link by email "
         "as soon as it leaves the warehouse. Deliveries outside the mainland can "
         "take two days longer."),
        ("Boot sizing and fit", "Sizing",
         "Our boots run true to size for most people. If you are between sizes, "
         "take the larger one and wear a thicker sock. Wide fit is available on "
         "the Ridgeline and the Summit. Any boot can be exchanged once for free "
         "if the fit is wrong."),
        ("Warranty on outdoor gear", "Warranty",
         "Tents, packs and jackets carry a three year warranty against "
         "manufacturing faults. Wear from ordinary use is not covered. Send "
         "photos of the fault with your order number and we repair or replace "
         "it."),
    ]
    for title, category, body in articles:
        created = await client.post(
            "/api/v1/knowledge",
            headers=workspace["headers"],
            json={"title": title, "category": category, "body": body, "status": "published"},
        )
        assert created.status_code == 201, created.text

    settings = (
        await client.get("/api/v1/workspace", headers=workspace["headers"])
    ).json()["settings"]
    threshold = float(settings["aiSuggestThreshold"])

    async def confidence(question: str) -> tuple[float, bool]:
        response = await client.post(
            "/api/v1/conversations/draft",
            headers=workspace["headers"],
            json={"question": question},
        )
        assert response.status_code == 200, response.text
        draft = response.json()
        return draft["confidence"], draft["shouldEscalate"]

    answerable = [
        "What is your returns policy",
        "How long do I have to return something",
        "Can I get a refund on a jacket I never used",
        "How long does delivery take",
        "Do your boots run true to size",
        "Is there a warranty on tents",
    ]
    for question in answerable:
        score, escalate = await confidence(question)
        assert not escalate, question
        assert score >= threshold, f"{question} scored {score}, under the {threshold} bar"

    # And the floor still holds, so it does not answer what it cannot.
    for question in ("Can you help me refinance my houseboat mortgage",
                     "What is the capital of France"):
        score, escalate = await confidence(question)
        assert score < threshold, f"{question} scored {score} and would be answered"


@pytest.mark.asyncio
async def test_a_customer_asking_the_obvious_question_gets_an_answer(
    client: AsyncClient, workspace: dict
) -> None:
    """The same thing end to end, through the public widget path."""
    await client.post(
        "/api/v1/knowledge",
        headers=workspace["headers"],
        json={
            "title": "Returns and refunds",
            "category": "Returns",
            "body": "You can return anything unused within 60 days of delivery for a "
                    "full refund. Start a return from your order page and we email you "
                    "a prepaid label. Refunds land on the original payment method "
                    "within five working days of the parcel reaching us.",
            "status": "published",
        },
    )
    key = workspace["workspace"]["publicKey"]
    sent = await client.post(
        f"/api/v1/widget/{key}/messages", json={"body": "What is your returns policy"}
    )
    assert sent.status_code == 200, sent.text
    assert sent.json()["escalated"] is False, sent.json()
    reply = sent.json()["reply"]
    assert reply is not None, "the customer got no answer at all"
    assert "60 days" in reply["body"], reply["body"]
    assert reply["meta"]["citations"], "an answer has to carry its source"


@pytest.mark.asyncio
async def test_a_workspace_missing_a_setting_falls_back_to_the_documented_default(
    client: AsyncClient, workspace: dict
) -> None:
    """A saved workspace with no value for a key runs on the documented one."""
    from app.models import DEFAULT_WORKSPACE_SETTINGS, workspace_setting

    for key, expected in DEFAULT_WORKSPACE_SETTINGS.items():
        assert workspace_setting({}, key) == expected
        assert workspace_setting(None, key) == expected
        # A value that is saved still wins, including a falsy one.
        assert workspace_setting({key: expected}, key) == expected

    # And nothing anywhere still carries its own copy of the number.
    root = Path(__file__).resolve().parents[1] / "app"
    for path in root.rglob("*.py"):
        for number, name in (("0.55", "ai_suggest_threshold"),):
            if number in path.read_text():
                raise AssertionError(f"{path} still hardcodes {number} for {name}")


@pytest.mark.asyncio
async def test_autopilot_reads_the_threshold_a_fresh_workspace_actually_has(
    client: AsyncClient, workspace: dict
) -> None:
    """The number Settings shows is the number Autopilot uses."""
    shown = await client.get("/api/v1/workspace/autopilot", headers=workspace["headers"])
    assert shown.status_code == 200, shown.text
    from app.models import DEFAULT_WORKSPACE_SETTINGS

    assert shown.json()["confidenceThreshold"] == DEFAULT_WORKSPACE_SETTINGS[
        "ai_suggest_threshold"
    ]


@pytest.mark.asyncio
async def test_an_answer_never_starts_in_the_middle_of_a_sentence(
    client: AsyncClient, workspace: dict
) -> None:
    """A quoted passage reads as prose, not as a string that got cut."""
    body = (
        "Our boots run true to size for most people. If you are between sizes, "
        "take the larger one and wear a thicker sock. Wide fit is available on "
        "the Ridgeline and the Summit. Any boot can be exchanged once for free "
        "if the fit is wrong."
    )
    await client.post(
        "/api/v1/knowledge",
        headers=workspace["headers"],
        json={
            "title": "Boot sizing and fit",
            "category": "Sizing",
            "body": body,
            "status": "published",
        },
    )
    key = workspace["workspace"]["publicKey"]
    sent = await client.post(
        f"/api/v1/widget/{key}/messages",
        json={"body": "Do the Ridgeline boots come in a wide fit"},
    )
    assert sent.status_code == 200, sent.text
    reply = sent.json()["reply"]
    assert reply is not None, "the customer got no answer at all"

    quoted = reply["body"].split("\n\n", 1)[-1].strip()
    assert not quoted.startswith("..."), quoted
    assert quoted.startswith("Our boots run true to size"), quoted


@pytest.mark.asyncio
async def test_a_tap_suggestion_does_not_run_two_sentence_endings_together(
    client: AsyncClient, workspace: dict
) -> None:
    """A Tap suggestion reads as one sentence after its article title."""
    await client.post(
        "/api/v1/knowledge",
        headers=workspace["headers"],
        json={
            "title": "Where is my order",
            "category": "Delivery",
            "body": (
                "Every parcel gets a tracking link by email the moment it leaves "
                "the warehouse. Standard delivery is two to four working days and "
                "express is next working day. Deliveries to the islands and the "
                "highlands take two days longer than the mainland estimate shown "
                "at checkout. A parcel that has not moved for three working days "
                "counts as delayed, and we send a replacement at no cost while "
                "the carrier investigates."
            ),
            "status": "published",
        },
    )
    started = await client.post(
        "/api/v1/tap/sessions", headers=workspace["headers"], json={}
    )
    assert started.status_code in (200, 201), started.text
    session_id = started.json()["id"]

    said = await client.post(
        f"/api/v1/tap/sessions/{session_id}/utterances",
        headers=workspace["headers"],
        json={"speaker": "customer", "text": "Has my replacement been sent yet"},
    )
    assert said.status_code in (200, 201), said.text

    suggestions = said.json().get("suggestions") or []
    assert suggestions, "Tap suggested nothing at all"
    for suggestion in suggestions:
        assert ". ..." not in suggestion["text"], suggestion["text"]
        assert ".." not in suggestion["text"].replace("...", ""), suggestion["text"]


@pytest.mark.asyncio
async def test_the_rate_limits_are_configurable_and_can_be_turned_off() -> None:
    """An operator tripping their own ceiling has something to turn."""
    from app.config import settings as app_settings
    from app.ratelimit import RateLimiter, registrations, sign_in_accounts, sign_in_addresses

    assert registrations.limit == app_settings.RATE_LIMIT_REGISTRATIONS
    assert registrations.window == app_settings.RATE_LIMIT_REGISTRATIONS_WINDOW_SECONDS
    assert sign_in_accounts.limit == app_settings.RATE_LIMIT_SIGN_IN_PER_ACCOUNT
    assert sign_in_addresses.limit == app_settings.RATE_LIMIT_SIGN_IN_PER_ADDRESS

    off = RateLimiter(limit=0, window_seconds=60)
    assert all(off.allow("one caller") for _ in range(500))

    # A configured ceiling still holds, and still lets the allowed number past.
    tight = RateLimiter(limit=3, window_seconds=60)
    assert [tight.allow("one caller") for _ in range(5)] == [True, True, True, False, False]
    # A different caller has its own allowance.
    assert tight.allow("another caller") is True


@pytest.mark.asyncio
async def test_a_rejected_webhook_says_which_address_it_checked(
    client: AsyncClient, workspace: dict, caplog
) -> None:
    """A signature rejection is diagnosable rather than a mystery."""
    import logging

    connected = await client.put(
        "/api/v1/workspace/channels/voice",
        headers=workspace["headers"],
        json={
            "isActive": True,
            "config": {
                "account_sid": "ACtest",
                "auth_token": "a-twilio-auth-token",
                "from_number": "+15555550100",
            },
        },
    )
    assert connected.status_code == 200, connected.text

    workspace_id = workspace["workspace"]["id"]
    with caplog.at_level(logging.WARNING, logger="app.api.webhooks"):
        refused = await client.post(
            f"/api/v1/webhooks/voice/{workspace_id}/answer",
            data={"CallSid": "CAtest", "From": "+15555550111"},
            headers={"X-Twilio-Signature": "a signature from the wrong address"},
        )

    assert refused.status_code == 401, refused.text
    # Generic to the caller.
    assert "PUBLIC_URL" not in refused.text

    logged = "\n".join(record.getMessage() for record in caplog.records)
    assert "PUBLIC_URL" in logged, logged
    assert "/api/v1/webhooks/voice/" in logged, logged
    assert workspace_id in logged, logged


@pytest.mark.asyncio
async def test_startup_warns_while_public_url_still_points_at_localhost() -> None:
    """The operator hears about it before the first delivery, not after."""
    from app.config import DEFAULT_PUBLIC_URL
    from app.config import settings as app_settings

    assert app_settings.PUBLIC_URL == DEFAULT_PUBLIC_URL
    assert DEFAULT_PUBLIC_URL.startswith("http://localhost")


@pytest.mark.asyncio
async def test_health_answers_even_when_the_database_cannot_be_read() -> None:
    """A probe is asked how things are, so it has to answer."""
    from httpx import ASGITransport, AsyncClient

    from app.main import app

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://health"
    ) as probe:
        answered = await probe.get("/health")

    assert answered.status_code == 200, answered.text
    body = answered.json()
    assert body["status"] in ("ok", "degraded"), body
    assert "databaseReady" in body, body
    if body["status"] == "degraded":
        assert body["databaseReady"] is False, body
        # The rest of the report is still usable, which is the point.
        assert body["version"], body
        assert body["channels"], body


@pytest.mark.asyncio
async def test_a_routing_rule_can_be_changed_one_field_at_a_time(
    client: AsyncClient, workspace: dict
) -> None:
    """PATCH means partial. It used to demand the whole rule back."""
    created = await client.post(
        "/api/v1/workspace/routing",
        headers=workspace["headers"],
        json={
            "name": "Refunds go to the returns queue",
            "conditions": {"contains": "refund"},
            "actions": {"priority": "high"},
            "isActive": True,
        },
    )
    assert created.status_code in (200, 201), created.text
    rule_id = created.json()["id"]

    toggled = await client.patch(
        f"/api/v1/workspace/routing/{rule_id}",
        headers=workspace["headers"],
        json={"isActive": False},
    )
    assert toggled.status_code == 200, toggled.text
    body = toggled.json()
    assert body["isActive"] is False
    # Everything else is left alone.
    assert body["name"] == "Refunds go to the returns queue"
    assert body["conditions"] == {"contains": "refund"}
    assert body["actions"] == {"priority": "high"}

    # An empty name is still refused.
    refused = await client.patch(
        f"/api/v1/workspace/routing/{rule_id}",
        headers=workspace["headers"],
        json={"name": "   "},
    )
    assert refused.status_code == 422, refused.text


@pytest.mark.asyncio
async def test_an_sla_policy_can_be_changed_one_field_at_a_time(
    client: AsyncClient, workspace: dict
) -> None:
    """The same for SLA targets, which is where a quick edit is most likely."""
    created = await client.post(
        "/api/v1/workspace/sla",
        headers=workspace["headers"],
        json={
            "name": "Urgent work",
            "priorities": ["urgent"],
            "firstResponseMinutes": 60,
            "resolutionMinutes": 480,
        },
    )
    assert created.status_code in (200, 201), created.text
    policy_id = created.json()["id"]

    tightened = await client.patch(
        f"/api/v1/workspace/sla/{policy_id}",
        headers=workspace["headers"],
        json={"firstResponseMinutes": 30},
    )
    assert tightened.status_code == 200, tightened.text
    body = tightened.json()
    assert body["firstResponseMinutes"] == 30
    assert body["name"] == "Urgent work"
    assert body["priorities"] == ["urgent"]
    assert body["resolutionMinutes"] == 480

    # A target of zero minutes is still refused.
    refused = await client.patch(
        f"/api/v1/workspace/sla/{policy_id}",
        headers=workspace["headers"],
        json={"firstResponseMinutes": 0},
    )
    assert refused.status_code == 422, refused.text
