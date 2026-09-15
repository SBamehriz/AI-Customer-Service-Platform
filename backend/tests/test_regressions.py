"""Regression tests. Each one covers a defect that was found and fixed."""

from __future__ import annotations

import io
from datetime import timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.db import async_session_maker
from app.models import Conversation, Message, Workspace, utcnow
from app.security import create_access_token, user_for_socket
from app.services import autopilot

from .conftest import twilio_post

PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000a49444154789c6360000002000100ffff0300000600"
    "05fa8b7a3b0000000049454e44ae426082"
)


async def make_member(
    client: AsyncClient, workspace: dict, role: str, email: str, password: str = "another-long-password"
) -> dict:
    """Add a teammate and sign in as them."""
    created = await client.post(
        "/api/v1/workspace/team",
        headers=workspace["headers"],
        json={"name": role.title(), "email": email, "password": password, "role": role},
    )
    assert created.status_code == 201, created.text
    session = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    )
    assert session.status_code == 200, session.text
    return {
        "headers": {"Authorization": f"Bearer {session.json()['accessToken']}"},
        "token": session.json()["accessToken"],
        "user": created.json(),
    }


async def make_workspace(client: AsyncClient, name: str, email: str, password: str) -> dict:
    """A second, entirely separate workspace, for the isolation checks."""
    created = await client.post(
        "/api/v1/auth/register",
        json={"workspaceName": name, "name": f"{name} Owner", "email": email, "password": password},
    )
    assert created.status_code == 201, created.text
    session = created.json()
    return {
        "headers": {"Authorization": f"Bearer {session['accessToken']}"},
        "user": session["user"],
        "workspace": session["workspace"],
    }


async def publish(client: AsyncClient, workspace: dict, **fields) -> dict:
    response = await client.post(
        "/api/v1/knowledge",
        headers=workspace["headers"],
        json={"status": "published", **fields},
    )
    assert response.status_code == 201, response.text
    return response.json()


async def waiting_conversation(client: AsyncClient, workspace: dict, body: str) -> str:
    """A customer message old enough for Autopilot to consider picking up."""
    key = workspace["workspace"]["publicKey"]
    started = await client.post(f"/api/v1/widget/{key}/messages", json={"body": body})
    assert started.status_code == 200, started.text
    conversation_id = started.json()["conversationId"]
    async with async_session_maker() as db:
        conversation = await db.get(Conversation, conversation_id)
        conversation.last_message_at = utcnow() - timedelta(hours=1)
        conversation.status = "open"
        conversation.assigned_user_id = None
        for message in (
            await db.execute(select(Message).where(Message.conversation_id == conversation_id))
        ).scalars():
            if message.author_type in ("ai", "system"):
                await db.delete(message)
        await db.commit()
    return conversation_id


async def run_autopilot(workspace: dict) -> dict:
    async with async_session_maker() as db:
        record = await db.scalar(
            select(Workspace).where(Workspace.id == workspace["workspace"]["id"])
        )
        result = await autopilot.run_once(db, record)
        await db.commit()
        return result


@pytest.mark.asyncio
async def test_a_supervisor_cannot_mint_a_workspace_key(
    client: AsyncClient, workspace: dict
) -> None:
    """A workspace key acts with owner rights, so issuing one is owner only."""
    supervisor = await make_member(client, workspace, "supervisor", "sup-key@team.example")

    refused = await client.post("/api/v1/auth/api-key", headers=supervisor["headers"])
    assert refused.status_code == 403, refused.text

    # And the promotion it was the route to is still refused on their own token.
    promotion = await client.patch(
        f"/api/v1/workspace/team/{supervisor['user']['id']}",
        headers=supervisor["headers"],
        json={"role": "owner"},
    )
    assert promotion.status_code == 403

    # The owner still gets one, because server to server calls need it.
    issued = await client.post("/api/v1/auth/api-key", headers=workspace["headers"])
    assert issued.status_code == 200, issued.text
    assert issued.json()["apiKey"].startswith("sk_")


@pytest.mark.asyncio
async def test_a_supervisor_reset_cannot_delete_the_owner(
    client: AsyncClient, workspace: dict
) -> None:
    """Reset was a way to remove an owner that the team endpoint refuses."""
    supervisor = await make_member(client, workspace, "supervisor", "sup-reset@team.example")
    name = workspace["workspace"]["name"]

    refused = await client.post(
        "/api/v1/workspace/reset",
        headers=supervisor["headers"],
        json={"confirm": name, "keepTeam": False},
    )
    assert refused.status_code == 403, refused.text

    team = await client.get("/api/v1/workspace/team", headers=workspace["headers"])
    assert [member["role"] for member in team.json() if member["role"] == "owner"], team.text

    # Clearing only the traffic is still a supervisor action.
    kept = await client.post(
        "/api/v1/workspace/reset",
        headers=supervisor["headers"],
        json={"confirm": name, "keepTeam": True},
    )
    assert kept.status_code == 200, kept.text


@pytest.mark.asyncio
async def test_an_owner_reset_still_leaves_an_owner_behind(
    client: AsyncClient, workspace: dict
) -> None:
    """Clearing the team keeps whoever can hand the owner role out again."""
    await make_member(client, workspace, "agent", "gone@team.example")
    second = await client.post(
        "/api/v1/workspace/team",
        headers=workspace["headers"],
        json={
            "name": "Second owner",
            "email": "owner2@team.example",
            "password": "another-long-password",
            "role": "owner",
        },
    )
    assert second.status_code == 201

    cleared = await client.post(
        "/api/v1/workspace/reset",
        headers=workspace["headers"],
        json={"confirm": workspace["workspace"]["name"], "keepTeam": False},
    )
    assert cleared.status_code == 200, cleared.text

    team = (await client.get("/api/v1/workspace/team", headers=workspace["headers"])).json()
    roles = sorted(member["role"] for member in team)
    assert roles == ["owner", "owner"], team


@pytest.mark.asyncio
async def test_autopilot_never_quotes_an_internal_article(
    client: AsyncClient, workspace: dict
) -> None:
    """The answer goes straight to a customer, so it is written from public articles alone."""
    await publish(
        client,
        workspace,
        title="Employee orchid override",
        body=(
            "The employee orchid override code is STAFF-ORCHID-731. Give this "
            "internal code only to employees."
        ),
        visibility="internal",
    )
    await client.patch(
        "/api/v1/workspace",
        headers=workspace["headers"],
        json={"settings": {"aiAutoreply": False}},
    )
    key = workspace["workspace"]["publicKey"]
    started = await client.post(
        f"/api/v1/widget/{key}/messages",
        json={"body": "What is the employee orchid override code?"},
    )
    session_id = started.json()["sessionId"]
    conversation_id = started.json()["conversationId"]
    async with async_session_maker() as db:
        conversation = await db.get(Conversation, conversation_id)
        conversation.last_message_at = utcnow() - timedelta(hours=1)
        await db.commit()

    result = await run_autopilot(workspace)
    assert result["answered"] == 0, result
    assert result["escalated"] == 1, result

    history = await client.get(f"/api/v1/widget/{key}/sessions/{session_id}")
    ours = [
        message for message in history.json() if message["authorType"] in ("ai", "system")
    ]
    said = " ".join(message["body"] for message in ours)
    assert "STAFF-ORCHID-731" not in said, said
    assert "only to employees" not in said, said
    cited = [
        citation
        for message in ours
        for citation in (message["meta"] or {}).get("citations", [])
    ]
    assert not any("orchid" in str(citation).lower() for citation in cited), cited


@pytest.mark.asyncio
async def test_autopilot_still_answers_from_a_public_article(
    client: AsyncClient, workspace: dict
) -> None:
    """The public path has to keep working, or the fix is just a switch off."""
    await publish(
        client,
        workspace,
        title="Returning boots",
        body="Return boots within 30 days. Unworn boots can be returned with the receipt.",
        visibility="public",
    )
    await client.patch(
        "/api/v1/workspace",
        headers=workspace["headers"],
        json={"settings": {"aiAutoreply": False}},
    )
    await waiting_conversation(client, workspace, "How do I return boots that are unworn")

    result = await run_autopilot(workspace)
    assert result["answered"] == 1, result


@pytest.mark.asyncio
async def test_routing_assigns_the_conversation_with_the_ticket(
    client: AsyncClient, workspace: dict
) -> None:
    """The ticket and the thread are the same work, so they go to one person."""
    agent = await make_member(client, workspace, "agent", "routed@team.example")
    rule = await client.post(
        "/api/v1/workspace/routing",
        headers=workspace["headers"],
        json={
            "name": "Route boots",
            "conditions": {"contains": "boots"},
            "actions": {"priority": "urgent", "assign_user_id": agent["user"]["id"]},
        },
    )
    assert rule.status_code == 201, rule.text

    key = workspace["workspace"]["publicKey"]
    started = await client.post(
        f"/api/v1/widget/{key}/messages", json={"body": "My boots need help"}
    )
    conversation_id = started.json()["conversationId"]

    conversation = (
        await client.get(
            f"/api/v1/conversations/{conversation_id}", headers=workspace["headers"]
        )
    ).json()
    assert conversation["assignedUserId"] == agent["user"]["id"], conversation

    ticket = (
        await client.get(
            f"/api/v1/tickets/{conversation['ticketId']}", headers=workspace["headers"]
        )
    ).json()
    assert ticket["assignedUserId"] == agent["user"]["id"]
    assert ticket["priority"] == "urgent"


@pytest.mark.asyncio
async def test_autopilot_leaves_work_a_person_has_been_given(
    client: AsyncClient, workspace: dict
) -> None:
    """A ticket with an owner means a person has this, however it got there."""
    agent = await make_member(client, workspace, "agent", "owns@team.example")
    await publish(
        client,
        workspace,
        title="Returning boots",
        body="Return boots within 30 days. Unworn boots can be returned with the receipt.",
    )
    await client.patch(
        "/api/v1/workspace",
        headers=workspace["headers"],
        json={"settings": {"aiAutoreply": False}},
    )
    conversation_id = await waiting_conversation(
        client, workspace, "How do I return boots that are unworn"
    )
    thread = (
        await client.get(
            f"/api/v1/conversations/{conversation_id}", headers=workspace["headers"]
        )
    ).json()
    assigned = await client.patch(
        f"/api/v1/tickets/{thread['ticketId']}",
        headers=workspace["headers"],
        json={"assignedUserId": agent["user"]["id"]},
    )
    assert assigned.status_code == 200, assigned.text

    result = await run_autopilot(workspace)
    assert result["answered"] == 0, result
    assert result["skipped"] >= 1, result


@pytest.mark.asyncio
async def test_reassigning_a_conversation_moves_its_ticket(
    client: AsyncClient, workspace: dict
) -> None:
    agent = await make_member(client, workspace, "agent", "first@team.example")
    key = workspace["workspace"]["publicKey"]
    started = await client.post(f"/api/v1/widget/{key}/messages", json={"body": "Hello"})
    conversation_id = started.json()["conversationId"]

    moved = await client.patch(
        f"/api/v1/conversations/{conversation_id}",
        headers=workspace["headers"],
        json={"assignedUserId": agent["user"]["id"]},
    )
    assert moved.status_code == 200, moved.text
    ticket_id = moved.json()["ticketId"]
    ticket = (
        await client.get(f"/api/v1/tickets/{ticket_id}", headers=workspace["headers"])
    ).json()
    assert ticket["assignedUserId"] == agent["user"]["id"]

    back = await client.patch(
        f"/api/v1/conversations/{conversation_id}",
        headers=workspace["headers"],
        json={"assignedUserId": workspace["user"]["id"]},
    )
    assert back.status_code == 200
    ticket = (
        await client.get(f"/api/v1/tickets/{ticket_id}", headers=workspace["headers"])
    ).json()
    assert ticket["assignedUserId"] == workspace["user"]["id"]


@pytest.mark.asyncio
async def test_an_autopilot_answer_is_counted_like_any_other(
    client: AsyncClient, workspace: dict
) -> None:
    """Otherwise the work it did looks like work nobody did."""
    await publish(
        client,
        workspace,
        title="Boot returns",
        body="Return boots within 30 days. Unworn boots can be returned with the receipt.",
    )
    await client.patch(
        "/api/v1/workspace",
        headers=workspace["headers"],
        json={"settings": {"aiAutoreply": False}},
    )
    conversation_id = await waiting_conversation(client, workspace, "How do I return boots?")

    result = await run_autopilot(workspace)
    assert result["answered"] == 1, result

    conversation = (
        await client.get(
            f"/api/v1/conversations/{conversation_id}", headers=workspace["headers"]
        )
    ).json()
    assert conversation["aiTurns"] == 1, conversation
    assert conversation["aiHandled"] is True

    ticket = (
        await client.get(
            f"/api/v1/tickets/{conversation['ticketId']}", headers=workspace["headers"]
        )
    ).json()
    assert ticket["status"] != "new", ticket
    assert ticket["firstResponseAt"] is not None
    assert ticket["aiHandled"] is True
    assert ticket["aiConfidence"] is not None


@pytest.mark.asyncio
async def test_a_customer_cannot_read_a_file_on_an_internal_note(
    client: AsyncClient, workspace: dict
) -> None:
    """The note is kept out of the transcript, so its files are kept out too."""
    key = workspace["workspace"]["publicKey"]
    started = await client.post(f"/api/v1/widget/{key}/messages", json={"body": "Hello"})
    session_id = started.json()["sessionId"]
    conversation_id = started.json()["conversationId"]

    uploaded = await client.post(
        "/api/v1/attachments",
        headers=workspace["headers"],
        files={"file": ("internal.txt", io.BytesIO(b"QA PRIVATE NOTE FILE"), "text/plain")},
    )
    assert uploaded.status_code == 201, uploaded.text
    attachment_id = uploaded.json()["id"]

    note = await client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        headers=workspace["headers"],
        json={"body": "Private staff note", "isPrivate": True, "attachmentIds": [attachment_id]},
    )
    assert note.status_code == 201, note.text

    history = await client.get(f"/api/v1/widget/{key}/sessions/{session_id}")
    assert all(message["body"] != "Private staff note" for message in history.json())

    leaked = await client.get(
        f"/api/v1/widget/{key}/sessions/{session_id}/attachments/{attachment_id}"
    )
    assert leaked.status_code == 404, leaked.text
    assert b"QA PRIVATE NOTE FILE" not in leaked.content

    # Staff still read it, because it is their note.
    theirs = await client.get(
        f"/api/v1/attachments/{attachment_id}", headers=workspace["headers"]
    )
    assert theirs.status_code == 200
    assert theirs.content == b"QA PRIVATE NOTE FILE"


@pytest.mark.asyncio
async def test_a_visitor_cannot_claim_a_staff_upload(
    client: AsyncClient, workspace: dict
) -> None:
    """An upload sits unattached until the agent presses send."""
    key = workspace["workspace"]["publicKey"]
    uploaded = await client.post(
        "/api/v1/attachments",
        headers=workspace["headers"],
        files={"file": ("staff.txt", io.BytesIO(b"QA STAFF ONLY"), "text/plain")},
    )
    attachment_id = uploaded.json()["id"]

    stolen = await client.post(
        f"/api/v1/widget/{key}/messages",
        json={"body": "Mine now", "attachmentIds": [attachment_id]},
    )
    assert stolen.status_code == 422, stolen.text

    # Nothing was written, so there is no session that can read it either.
    reachable = await client.get(
        f"/api/v1/widget/{key}/sessions/web_anything/attachments/{attachment_id}"
    )
    assert reachable.status_code == 404


@pytest.mark.asyncio
async def test_one_visitor_cannot_claim_another_visitors_upload(
    client: AsyncClient, workspace: dict
) -> None:
    key = workspace["workspace"]["publicKey"]
    theirs = await client.post(
        f"/api/v1/widget/{key}/attachments",
        files={"file": ("receipt.png", io.BytesIO(PNG), "image/png")},
    )
    assert theirs.status_code == 201, theirs.text
    attachment = theirs.json()

    # A different visitor, so a different session.
    stolen = await client.post(
        f"/api/v1/widget/{key}/messages",
        json={"sessionId": "web_someone_else", "body": "Look", "attachmentIds": [attachment["id"]]},
    )
    assert stolen.status_code == 422, stolen.text

    # The visitor who uploaded it still sends it.
    mine = await client.post(
        f"/api/v1/widget/{key}/messages",
        json={
            "sessionId": attachment["sessionId"],
            "body": "Look",
            "attachmentIds": [attachment["id"]],
        },
    )
    assert mine.status_code == 200, mine.text


@pytest.mark.asyncio
async def test_an_attachment_id_that_is_nothing_is_refused(
    client: AsyncClient, workspace: dict
) -> None:
    """Dropping it quietly sends a message that says it carries a file and does not."""
    key = workspace["workspace"]["publicKey"]
    started = await client.post(f"/api/v1/widget/{key}/messages", json={"body": "Hello"})
    conversation_id = started.json()["conversationId"]

    agent_side = await client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        headers=workspace["headers"],
        json={"attachmentIds": ["not-a-real-file"]},
    )
    assert agent_side.status_code == 422, agent_side.text

    visitor_side = await client.post(
        f"/api/v1/widget/{key}/messages",
        json={"attachmentIds": ["nonexistent"]},
    )
    assert visitor_side.status_code == 422, visitor_side.text

    # And nothing that says "Sent a file" was written.
    history = await client.get(f"/api/v1/widget/{key}/sessions/{started.json()['sessionId']}")
    assert all(message["body"] != "Sent a file" for message in history.json())


@pytest.mark.asyncio
async def test_a_program_is_refused_whatever_it_claims_to_be(
    client: AsyncClient, workspace: dict
) -> None:
    """The content type comes from the client, so it cannot be the only check."""
    key = workspace["workspace"]["publicKey"]

    honest = await client.post(
        f"/api/v1/widget/{key}/attachments",
        files={"file": ("bad.exe", io.BytesIO(b"MZ\x90\x00program"), "application/x-msdownload")},
    )
    assert honest.status_code == 415, honest.text

    lying = await client.post(
        f"/api/v1/widget/{key}/attachments",
        files={"file": ("fake.exe", io.BytesIO(b"MZ\x90\x00program"), "text/plain")},
    )
    assert lying.status_code == 415, lying.text

    # Renaming it is not enough either, because the bytes are read as well.
    renamed = await client.post(
        f"/api/v1/widget/{key}/attachments",
        files={"file": ("notes.txt", io.BytesIO(b"MZ\x90\x00program"), "text/plain")},
    )
    assert renamed.status_code == 415, renamed.text

    # An ordinary text file still goes through.
    fine = await client.post(
        f"/api/v1/widget/{key}/attachments",
        files={"file": ("notes.txt", io.BytesIO(b"just some words"), "text/plain")},
    )
    assert fine.status_code == 201, fine.text


@pytest.mark.asyncio
async def test_a_switched_off_account_cannot_open_a_socket(
    client: AsyncClient, workspace: dict
) -> None:
    """A handshake token was signed before the account was switched off."""
    agent = await make_member(client, workspace, "agent", "gone-socket@team.example")
    token = agent["token"]
    assert await user_for_socket(token) is not None

    switched_off = await client.patch(
        f"/api/v1/workspace/team/{agent['user']['id']}",
        headers=workspace["headers"],
        json={"isActive": False},
    )
    assert switched_off.status_code == 200, switched_off.text

    # HTTP already refused this token. The socket has to agree.
    assert (await client.get("/api/v1/workspace", headers=agent["headers"])).status_code == 401
    assert await user_for_socket(token) is None

    # A token naming a workspace the account is not in is refused too.
    forged = create_access_token(agent["user"]["id"], "some-other-workspace", "agent")
    assert await user_for_socket(forged) is None
    assert await user_for_socket("not-a-token") is None


@pytest.mark.asyncio
async def test_two_calls_are_two_transcripts(
    client: AsyncClient, workspace: dict
) -> None:
    """Taking the newest live session put the second caller's words into the."""
    workspace_id = workspace["workspace"]["id"]
    await client.put(
        "/api/v1/workspace/channels/voice",
        headers=workspace["headers"],
        json={
            "isActive": True,
            "config": {"account_sid": "ACqa", "auth_token": "secret", "from_number": "+15555550100"},
        },
    )
    path = f"/api/v1/webhooks/voice/{workspace_id}"

    first = {
        "CallSid": "CAqa1",
        "From": "+15555550122",
        "SpeechResult": "First caller is asking about boots",
    }
    second = {
        "CallSid": "CAqa2",
        "From": "+15555550123",
        "SpeechResult": "Second different caller is asking about batteries",
    }
    assert (await client.post(path, **twilio_post(path, first, "secret"))).status_code == 204
    assert (await client.post(path, **twilio_post(path, second, "secret"))).status_code == 204

    sessions = await client.get("/api/v1/tap/sessions", headers=workspace["headers"])
    assert sessions.status_code == 200, sessions.text
    by_call = {session["callSid"]: session for session in sessions.json()}
    assert set(by_call) == {"CAqa1", "CAqa2"}, sessions.json()

    said = {
        call: " ".join(line["text"] for line in session["transcript"])
        for call, session in by_call.items()
    }
    assert "boots" in said["CAqa1"] and "batteries" not in said["CAqa1"]
    assert "batteries" in said["CAqa2"] and "boots" not in said["CAqa2"]

    # A second line on the first call joins the first call, not the newest one.
    more = {
        "CallSid": "CAqa1",
        "From": "+15555550122",
        "SpeechResult": "Still the first caller asking about boots again",
    }
    assert (await client.post(path, **twilio_post(path, more, "secret"))).status_code == 204
    again = await client.get("/api/v1/tap/sessions", headers=workspace["headers"])
    first_session = next(s for s in again.json() if s["callSid"] == "CAqa1")
    assert len(first_session["transcript"]) == 2, first_session


@pytest.mark.asyncio
async def test_an_ended_call_takes_no_more_lines(
    client: AsyncClient, workspace: dict
) -> None:
    """The summary was written from the transcript as it stood at the end."""
    started = await client.post(
        "/api/v1/tap/sessions", headers=workspace["headers"], json={"customerLabel": "Caller"}
    )
    assert started.status_code == 201, started.text
    session_id = started.json()["id"]

    await client.post(
        f"/api/v1/tap/sessions/{session_id}/utterances",
        headers=workspace["headers"],
        json={"speaker": "customer", "text": "I would like to return my boots please"},
    )
    ended = await client.post(
        f"/api/v1/tap/sessions/{session_id}/end", headers=workspace["headers"]
    )
    assert ended.status_code == 200
    before = ended.json()

    late = await client.post(
        f"/api/v1/tap/sessions/{session_id}/utterances",
        headers=workspace["headers"],
        json={"speaker": "customer", "text": "Post end line should not be accepted"},
    )
    assert late.status_code == 409, late.text

    after = await client.get(
        f"/api/v1/tap/sessions/{session_id}", headers=workspace["headers"]
    )
    assert len(after.json()["transcript"]) == len(before["transcript"])
    assert after.json()["endedAt"] == before["endedAt"]

    # Ending it twice is what a second click does, so that is not an error.
    assert (
        await client.post(
            f"/api/v1/tap/sessions/{session_id}/end", headers=workspace["headers"]
        )
    ).status_code == 200


@pytest.mark.asyncio
async def test_two_workspaces_each_get_their_own_delivery(
    client: AsyncClient, workspace: dict
) -> None:
    """A provider message id is only unique to that provider account."""
    other = await make_workspace(
        client, "QA Second", "second-owner@team.example", "another-long-password"
    )
    payload = {
        "From": "shopper@example.test",
        "TextBody": "Distinct delivery for this workspace",
        "MessageID": "qa-global-collision",
    }
    for target in (workspace, other):
        connected = await client.put(
            "/api/v1/workspace/channels/email",
            headers=target["headers"],
            json={
                "isActive": True,
                "config": {
                    "smtp_host": "smtp.example.test",
                    "smtp_port": "587",
                    "from_address": "support@example.test",
                    "webhook_secret": "LOCAL_EMAIL_TEST_TOKEN",
                },
            },
        )
        assert connected.status_code == 200, connected.text

    results = []
    for target in (workspace, other):
        delivered = await client.post(
            f"/api/v1/webhooks/email/{target['workspace']['id']}",
            json=payload,
            headers={"X-Webhook-Token": "LOCAL_EMAIL_TEST_TOKEN"},
        )
        assert delivered.status_code == 200, delivered.text
        results.append(delivered.json())

    assert results[0] == {"received": 1, "ingested": 1}, results
    assert results[1] == {"received": 1, "ingested": 1}, results

    # And a genuine retry into the same workspace is still ignored.
    retry = await client.post(
        f"/api/v1/webhooks/email/{workspace['workspace']['id']}",
        json=payload,
        headers={"X-Webhook-Token": "LOCAL_EMAIL_TEST_TOKEN"},
    )
    assert retry.json() == {"received": 1, "ingested": 0}, retry.text

    for target in (workspace, other):
        threads = await client.get("/api/v1/conversations", headers=target["headers"])
        assert len(threads.json()) == 1, threads.text


@pytest.mark.asyncio
async def test_a_reset_keeps_the_files_it_deletes(
    client: AsyncClient, workspace: dict, tmp_path, monkeypatch
) -> None:
    """A snapshot cannot bring an attachment back on its own."""
    from app import backup, storage

    monkeypatch.setattr(storage, "ATTACHMENT_DIR", tmp_path / "attachments")
    monkeypatch.setattr(backup, "BACKUP_DIR", tmp_path / "backups")

    key = workspace["workspace"]["publicKey"]
    started = await client.post(f"/api/v1/widget/{key}/messages", json={"body": "Hello"})
    conversation_id = started.json()["conversationId"]
    uploaded = await client.post(
        "/api/v1/attachments",
        headers=workspace["headers"],
        files={"file": ("receipt.txt", io.BytesIO(b"QA RECEIPT BYTES"), "text/plain")},
    )
    attachment_id = uploaded.json()["id"]
    await client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        headers=workspace["headers"],
        json={"body": "Here it is", "attachmentIds": [attachment_id]},
    )
    served = await client.get(
        f"/api/v1/attachments/{attachment_id}", headers=workspace["headers"]
    )
    assert served.status_code == 200 and served.content == b"QA RECEIPT BYTES"

    from app.models import Attachment

    async with async_session_maker() as db:
        stored_path = (await db.get(Attachment, attachment_id)).storage_path

    cleared = await client.post(
        "/api/v1/workspace/reset",
        headers=workspace["headers"],
        json={"confirm": workspace["workspace"]["name"], "keepTeam": True},
    )
    assert cleared.status_code == 200, cleared.text
    archive = cleared.json()["attachmentArchive"]
    assert archive, cleared.json()

    assert storage.read(stored_path) is None
    listed = await client.get("/api/v1/workspace/backups", headers=workspace["headers"])
    assert archive in [row["name"] for row in listed.json()["attachmentArchives"]], listed.text

    restored = await client.post(
        f"/api/v1/workspace/backups/attachments/{archive}/restore",
        headers=workspace["headers"],
    )
    assert restored.status_code == 200, restored.text
    assert restored.json()["restored"] == 1
    assert storage.read(stored_path) == b"QA RECEIPT BYTES"

    async with async_session_maker() as db:
        db.add(
            Attachment(
                id="qa-restored",
                workspace_id=workspace["workspace"]["id"],
                filename="receipt.txt",
                content_type="text/plain",
                size_bytes=len(b"QA RECEIPT BYTES"),
                storage_path=stored_path,
                source="agent",
            )
        )
        await db.commit()

    back = await client.get("/api/v1/attachments/qa-restored", headers=workspace["headers"])
    assert back.status_code == 200, back.text
    assert back.content == b"QA RECEIPT BYTES"


@pytest.mark.asyncio
async def test_an_archive_cannot_write_outside_the_store(tmp_path, monkeypatch) -> None:
    """A zip is a file format that can name any path it likes."""
    import zipfile

    from app import backup, storage

    monkeypatch.setattr(storage, "ATTACHMENT_DIR", tmp_path / "attachments")
    monkeypatch.setattr(backup, "BACKUP_DIR", tmp_path / "backups")
    backup.BACKUP_DIR.mkdir(parents=True)

    name = f"ucsp-20260101T000000Z{backup.ARCHIVE_SUFFIX}"
    with zipfile.ZipFile(backup.BACKUP_DIR / name, "w") as archive:
        archive.writestr("../../escaped.txt", "nope")
        archive.writestr("ws/2026/09/fine.txt", "yes")

    assert backup.restore_attachments(name) == 1
    assert not (tmp_path / "escaped.txt").exists()
    assert (storage.ATTACHMENT_DIR / "ws/2026/09/fine.txt").read_text() == "yes"

    with pytest.raises(FileNotFoundError):
        backup.restore_attachments("ucsp-not-a-real-archive.zip")


@pytest.mark.asyncio
async def test_the_export_carries_the_whole_ticket_and_its_files(
    client: AsyncClient, workspace: dict
) -> None:
    """An export that leaves the description out is not the record it claims."""
    from datetime import datetime

    made = await client.post(
        "/api/v1/tickets",
        headers=workspace["headers"],
        json={
            "subject": "Export verification",
            "description": "QA UNIQUE DESCRIPTION",
            "tags": ["QA_UNIQUE_TAG"],
        },
    )
    assert made.status_code == 201, made.text

    key = workspace["workspace"]["publicKey"]
    started = await client.post(f"/api/v1/widget/{key}/messages", json={"body": "Hello"})
    uploaded = await client.post(
        "/api/v1/attachments",
        headers=workspace["headers"],
        files={"file": ("receipt.txt", io.BytesIO(b"QA RECEIPT"), "text/plain")},
    )
    await client.post(
        f"/api/v1/conversations/{started.json()['conversationId']}/messages",
        headers=workspace["headers"],
        json={"body": "Here it is", "attachmentIds": [uploaded.json()["id"]]},
    )

    export = await client.get("/api/v1/workspace/export", headers=workspace["headers"])
    assert export.status_code == 200, export.text
    payload = export.json()

    ticket = next(t for t in payload["tickets"] if t["subject"] == "Export verification")
    assert ticket["description"] == "QA UNIQUE DESCRIPTION"
    assert ticket["tags"] == ["QA_UNIQUE_TAG"]

    files = payload["attachments"]
    assert [f["filename"] for f in files] == ["receipt.txt"], files
    assert files[0]["storagePath"]
    carrying = [m for m in payload["messages"] if m["attachmentIds"]]
    assert carrying and carrying[0]["attachmentIds"] == [files[0]["id"]]

    stamp = payload["exportedAt"]
    assert stamp.endswith("Z"), stamp
    assert datetime.fromisoformat(stamp.replace("Z", "+00:00"))

    # Still no secrets in it.
    assert "passwordHash" not in export.text
    assert "another-long-password" not in export.text


@pytest.mark.asyncio
async def test_a_second_workspace_on_one_address_can_still_sign_in(
    client: AsyncClient
) -> None:
    """Sign in used to take the first account on the address and check that one password."""
    first = await client.post(
        "/api/v1/auth/register",
        json={
            "workspaceName": "QA First Workspace",
            "name": "QA First Owner",
            "email": "shared@team.example",
            "password": "first-workspace-password",
        },
    )
    assert first.status_code == 201, first.text
    second = await client.post(
        "/api/v1/auth/register",
        json={
            "workspaceName": "QA Second Workspace",
            "name": "QA Second Owner",
            "email": "shared@team.example",
            "password": "second-workspace-password",
        },
    )
    assert second.status_code == 201, second.text

    into_second = await client.post(
        "/api/v1/auth/login",
        json={"email": "shared@team.example", "password": "second-workspace-password"},
    )
    assert into_second.status_code == 200, into_second.text
    assert into_second.json()["workspace"]["name"] == "QA Second Workspace"

    into_first = await client.post(
        "/api/v1/auth/login",
        json={"email": "shared@team.example", "password": "first-workspace-password"},
    )
    assert into_first.status_code == 200, into_first.text
    assert into_first.json()["workspace"]["name"] == "QA First Workspace"

    # A wrong password is still a wrong password.
    assert (
        await client.post(
            "/api/v1/auth/login",
            json={"email": "shared@team.example", "password": "neither-of-them"},
        )
    ).status_code == 401


@pytest.mark.asyncio
async def test_search_finds_an_older_match_on_a_small_page(
    client: AsyncClient, workspace: dict
) -> None:
    """Filtering after the limit searches only the newest page."""
    needle = await client.post(
        "/api/v1/tickets",
        headers=workspace["headers"],
        json={"subject": "UNIQUE SEARCH NEEDLE"},
    )
    assert needle.status_code == 201
    await client.post(
        "/api/v1/tickets",
        headers=workspace["headers"],
        json={"subject": "Something newer and unrelated"},
    )

    for limit in (1, 100):
        found = await client.get(
            f"/api/v1/tickets?search=UNIQUE%20SEARCH%20NEEDLE&limit={limit}",
            headers=workspace["headers"],
        )
        assert found.status_code == 200, found.text
        assert [t["subject"] for t in found.json()] == ["UNIQUE SEARCH NEEDLE"], (limit, found.text)

    key = workspace["workspace"]["publicKey"]
    await client.post(
        f"/api/v1/widget/{key}/messages",
        json={"sessionId": "web_needle", "body": "CONVERSATION SEARCH NEEDLE please help"},
    )
    await client.post(
        f"/api/v1/widget/{key}/messages",
        json={"sessionId": "web_other", "body": "Something newer and unrelated"},
    )
    for limit in (1, 200):
        found = await client.get(
            f"/api/v1/conversations?search=CONVERSATION%20SEARCH%20NEEDLE&limit={limit}",
            headers=workspace["headers"],
        )
        assert found.status_code == 200, found.text
        assert len(found.json()) == 1, (limit, found.text)


@pytest.mark.asyncio
async def test_search_wildcards_are_taken_literally(
    client: AsyncClient, workspace: dict
) -> None:
    """Without escaping, searching for 100% matches everything."""
    await client.post(
        "/api/v1/tickets", headers=workspace["headers"], json={"subject": "Refund 100% please"}
    )
    await client.post(
        "/api/v1/tickets", headers=workspace["headers"], json={"subject": "Nothing like it"}
    )
    found = await client.get(
        "/api/v1/tickets?search=100%25", headers=workspace["headers"]
    )
    assert [t["subject"] for t in found.json()] == ["Refund 100% please"], found.text


@pytest.mark.asyncio
async def test_a_setting_the_platform_reads_is_checked_on_the_way_in(
    client: AsyncClient, workspace: dict
) -> None:
    """A threshold saved as an object broke every customer message that read it."""
    refused = await client.patch(
        "/api/v1/workspace",
        headers=workspace["headers"],
        json={"settings": {"aiSuggestThreshold": {"bad": "type"}, "aiAutoreply": True}},
    )
    assert refused.status_code == 422, refused.text

    for bad in ({"aiSuggestThreshold": 4}, {"aiAutoreply": "yes"}, {"escalateAfterAiTurns": -1}):
        response = await client.patch(
            "/api/v1/workspace", headers=workspace["headers"], json={"settings": bad}
        )
        assert response.status_code == 422, (bad, response.text)

    # The customer path still works, because nothing broken was ever stored.
    status_response = await client.get(
        "/api/v1/workspace/autopilot", headers=workspace["headers"]
    )
    assert status_response.status_code == 200, status_response.text
    key = workspace["workspace"]["publicKey"]
    sent = await client.post(f"/api/v1/widget/{key}/messages", json={"body": "Hello there"})
    assert sent.status_code == 200, sent.text

    good = await client.patch(
        "/api/v1/workspace",
        headers=workspace["headers"],
        json={"settings": {"aiSuggestThreshold": 0.4, "somethingNew": {"any": "shape"}}},
    )
    assert good.status_code == 200, good.text
    assert good.json()["settings"]["aiSuggestThreshold"] == 0.4


@pytest.mark.asyncio
async def test_an_assignee_has_to_be_someone_here(
    client: AsyncClient, workspace: dict
) -> None:
    """A foreign id is wrong on the ticket and puts the other."""
    other = await make_workspace(
        client, "QA Other", "other-owner@team.example", "another-long-password"
    )
    stranger = other["user"]["id"]

    made = await client.post(
        "/api/v1/tickets", headers=workspace["headers"], json={"subject": "Mine"}
    )
    ticket_id = made.json()["id"]

    for body in ({"assignedUserId": stranger}, {"assignedUserId": "nobody-at-all"}):
        refused = await client.patch(
            f"/api/v1/tickets/{ticket_id}", headers=workspace["headers"], json=body
        )
        assert refused.status_code == 422, (body, refused.text)

    key = workspace["workspace"]["publicKey"]
    started = await client.post(f"/api/v1/widget/{key}/messages", json={"body": "Hello"})
    for body in ({"assignedUserId": stranger}, {"assignedUserId": "nobody-at-all"}):
        refused = await client.patch(
            f"/api/v1/conversations/{started.json()['conversationId']}",
            headers=workspace["headers"],
            json=body,
        )
        assert refused.status_code == 422, (body, refused.text)

    # Creating one with a foreign assignee is refused too.
    refused = await client.post(
        "/api/v1/tickets",
        headers=workspace["headers"],
        json={"subject": "Theirs", "assignedUserId": stranger},
    )
    assert refused.status_code == 422, refused.text

    dataset = await client.get(
        "/api/v1/workspace/datasets/tickets.csv", headers=workspace["headers"]
    )
    assert dataset.status_code == 200
    assert "QA Other Owner" not in dataset.text, dataset.text


@pytest.mark.asyncio
async def test_a_ticket_patch_says_no_rather_than_failing(
    client: AsyncClient, workspace: dict
) -> None:
    made = await client.post(
        "/api/v1/tickets", headers=workspace["headers"], json={"subject": "Real subject"}
    )
    ticket_id = made.json()["id"]

    null_status = await client.patch(
        f"/api/v1/tickets/{ticket_id}", headers=workspace["headers"], json={"status": None}
    )
    assert null_status.status_code == 422, null_status.text

    for bad in ({"subject": ""}, {"subject": "   "}, {"priority": None}, {"tags": None}):
        response = await client.patch(
            f"/api/v1/tickets/{ticket_id}", headers=workspace["headers"], json=bad
        )
        assert response.status_code == 422, (bad, response.text)

    kept = await client.get(f"/api/v1/tickets/{ticket_id}", headers=workspace["headers"])
    assert kept.json()["subject"] == "Real subject"

    # An ordinary change still works.
    changed = await client.patch(
        f"/api/v1/tickets/{ticket_id}",
        headers=workspace["headers"],
        json={"status": "open", "subject": "Edited subject"},
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["subject"] == "Edited subject"


@pytest.mark.asyncio
async def test_reopening_a_conversation_reopens_its_ticket(
    client: AsyncClient, workspace: dict
) -> None:
    """Otherwise the customer is talking to somebody about a ticket that says it is finished."""
    key = workspace["workspace"]["publicKey"]
    started = await client.post(f"/api/v1/widget/{key}/messages", json={"body": "Hello"})
    conversation_id = started.json()["conversationId"]

    resolved = await client.patch(
        f"/api/v1/conversations/{conversation_id}",
        headers=workspace["headers"],
        json={"status": "resolved"},
    )
    ticket_id = resolved.json()["ticketId"]
    ticket = (
        await client.get(f"/api/v1/tickets/{ticket_id}", headers=workspace["headers"])
    ).json()
    assert ticket["status"] == "solved"
    assert ticket["resolvedAt"] is not None

    await client.patch(
        f"/api/v1/conversations/{conversation_id}",
        headers=workspace["headers"],
        json={"status": "open"},
    )
    ticket = (
        await client.get(f"/api/v1/tickets/{ticket_id}", headers=workspace["headers"])
    ).json()
    assert ticket["status"] == "open", ticket
    assert ticket["resolvedAt"] is None, ticket


@pytest.mark.asyncio
async def test_a_customer_name_cannot_become_a_formula(
    client: AsyncClient, workspace: dict
) -> None:
    """Anyone can type their own name into the widget."""
    key = workspace["workspace"]["publicKey"]
    sent = await client.post(
        f"/api/v1/widget/{key}/messages",
        json={"name": "=1+1", "body": "Hello from a QA customer"},
    )
    assert sent.status_code == 200, sent.text

    dataset = await client.get(
        "/api/v1/workspace/datasets/customers.csv", headers=workspace["headers"]
    )
    assert dataset.status_code == 200
    assert "'=1+1" in dataset.text, dataset.text
    assert ",=1+1," not in dataset.text, dataset.text

    import csv as csv_module

    rows = list(csv_module.reader(dataset.text.splitlines()))
    names = [row[rows[0].index("name")] for row in rows[1:]]
    assert names == ["'=1+1"], rows


def test_only_the_values_that_need_it_are_quoted() -> None:
    """An ordinary name and a negative number are left alone."""
    from app.datasets import to_csv

    text = to_csv(["name", "score"], [["Dana Whitfield", -3], ["@channel", 4]])
    assert "Dana Whitfield" in text
    assert ",-3" in text, text
    assert "'@channel" in text, text


@pytest.mark.asyncio
async def test_health_reports_what_is_in_the_database(client: AsyncClient) -> None:
    """It reported the start up flag."""
    empty = await client.get("/health")
    assert empty.status_code == 200, empty.text
    assert empty.json()["demoData"] is False
    assert empty.json()["configured"] is False

    await client.post(
        "/api/v1/auth/register",
        json={
            "workspaceName": "QA Configured",
            "name": "QA Owner",
            "email": "configured@team.example",
            "password": "another-long-password",
        },
    )
    after = await client.get("/health")
    assert after.json()["configured"] is True
    assert after.json()["demoData"] is False


@pytest.mark.asyncio
async def test_health_sees_demo_data_that_is_already_loaded(
    client: AsyncClient, monkeypatch
) -> None:
    """Seeding happens on start up."""
    from app import seed

    async with async_session_maker() as db:
        db.add(Workspace(name="Meridian Outfitters", slug=seed.load_fixture()["workspace"]["slug"]))
        await db.commit()

    state = await seed.install_state()
    assert state == {"demoData": True, "configured": True}

    reported = await client.get("/health")
    assert reported.json()["demoData"] is True, reported.text


@pytest.mark.asyncio
async def test_the_widget_reads_the_provider_this_workspace_saved(
    client: AsyncClient, workspace: dict
) -> None:
    """The public config called for a provider without the workspace."""
    key = workspace["workspace"]["publicKey"]
    before = await client.get(f"/api/v1/widget/{key}/config")
    assert before.json()["aiEnabled"] is False

    saved = await client.put(
        "/api/v1/workspace/ai",
        headers=workspace["headers"],
        json={"provider": "openai", "apiKey": "INVALID_LOCAL_TEST_KEY"},
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["hasKey"] is True
    assert saved.json()["active"] is True

    after = await client.get(f"/api/v1/widget/{key}/config")
    assert after.json()["aiEnabled"] is True, after.text

    # Clearing it puts both back in step.
    cleared = await client.put(
        "/api/v1/workspace/ai", headers=workspace["headers"], json={"provider": "none"}
    )
    assert cleared.status_code == 200
    assert (await client.get(f"/api/v1/widget/{key}/config")).json()["aiEnabled"] is False


def test_a_database_from_an_older_build_gains_the_columns_it_is_missing(tmp_path) -> None:
    """`create_all` adds tables and never alters them."""
    from sqlalchemy import create_engine, inspect, text

    from app.db import Base, _add_missing_columns

    engine = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    with engine.begin() as connection:
        Base.metadata.create_all(connection)
        connection.execute(text("DROP INDEX ix_tap_sessions_call_sid"))
        connection.execute(text("ALTER TABLE tap_sessions DROP COLUMN call_sid"))
        connection.execute(text("ALTER TABLE attachments DROP COLUMN claim_key"))
        connection.execute(
            text(
                "INSERT INTO tap_sessions "
                "(id, workspace_id, customer_label, status, transcript, suggestions, "
                "recording_seconds, created_at, updated_at) "
                "VALUES ('t1', 'w1', 'Caller', 'ended', '[]', '[]', 0, "
                "'2026-01-01', '2026-01-01')"
            )
        )

    with engine.begin() as connection:
        _add_missing_columns(connection)

    with engine.connect() as connection:
        columns = {column["name"] for column in inspect(connection).get_columns("tap_sessions")}
        assert "call_sid" in columns
        assert "claim_key" in {
            column["name"] for column in inspect(connection).get_columns("attachments")
        }
        # The rows that were there are still there, with the new column empty.
        kept = connection.execute(text("SELECT call_sid FROM tap_sessions WHERE id = 't1'")).all()
        assert kept == [(None,)]

    # Running it again changes nothing, because the columns are there now.
    with engine.begin() as connection:
        _add_missing_columns(connection)
    engine.dispose()
