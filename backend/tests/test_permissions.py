"""Who may change what."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


async def _member(client: AsyncClient, workspace: dict, role: str, email: str) -> dict:
    """Add a teammate and sign in as them."""
    created = await client.post(
        "/api/v1/workspace/team",
        headers=workspace["headers"],
        json={"name": role.title(), "email": email, "password": "another-long-password", "role": role},
    )
    assert created.status_code == 201, created.text
    session = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": "another-long-password"}
    )
    assert session.status_code == 200, session.text
    token = session.json()["accessToken"]
    return {"headers": {"Authorization": f"Bearer {token}"}, "user": created.json()}


@pytest.fixture
async def agent(client: AsyncClient, workspace: dict) -> dict:
    return await _member(client, workspace, "agent", "agent@team.example")


@pytest.fixture
async def supervisor(client: AsyncClient, workspace: dict) -> dict:
    return await _member(client, workspace, "supervisor", "sup@team.example")


async def _article(client: AsyncClient, headers: dict, **fields) -> dict:
    body = {"title": "Returns", "body": "You have 30 days.", **fields}
    response = await client.post("/api/v1/knowledge", headers=headers, json=body)
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.asyncio
async def test_agent_cannot_publish_an_article(client: AsyncClient, agent: dict) -> None:
    """A published article is what the assistant quotes, so publishing is review."""
    response = await client.post(
        "/api/v1/knowledge",
        headers=agent["headers"],
        json={"title": "New policy", "body": "Anything goes.", "status": "published"},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_agent_cannot_rewrite_a_published_article(
    client: AsyncClient, workspace: dict, agent: dict
) -> None:
    """This is the one that matters. Rewriting live policy changes every answer."""
    article = await _article(client, workspace["headers"], status="published")
    response = await client.patch(
        f"/api/v1/knowledge/{article['id']}",
        headers=agent["headers"],
        json={"body": "Returns are now refused."},
    )
    assert response.status_code == 403

    unchanged = await client.get(f"/api/v1/knowledge/{article['id']}", headers=agent["headers"])
    assert unchanged.json()["body"] == "You have 30 days."


@pytest.mark.asyncio
async def test_agent_cannot_promote_their_own_draft(client: AsyncClient, agent: dict) -> None:
    draft = await _article(client, agent["headers"])
    assert draft["status"] == "draft"
    response = await client.patch(
        f"/api/v1/knowledge/{draft['id']}",
        headers=agent["headers"],
        json={"status": "published"},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_agent_cannot_delete_an_article(
    client: AsyncClient, workspace: dict, agent: dict
) -> None:
    article = await _article(client, workspace["headers"], status="published")
    response = await client.delete(
        f"/api/v1/knowledge/{article['id']}", headers=agent["headers"]
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_agents_still_draft_and_supervisors_publish(
    client: AsyncClient, agent: dict, supervisor: dict
) -> None:
    """The workflow has to work, or the restriction is just an obstacle."""
    draft = await _article(client, agent["headers"], title="Customers keep asking")
    revised = await client.patch(
        f"/api/v1/knowledge/{draft['id']}",
        headers=agent["headers"],
        json={"body": "Clearer notes from the front line."},
    )
    assert revised.status_code == 200

    published = await client.patch(
        f"/api/v1/knowledge/{draft['id']}",
        headers=supervisor["headers"],
        json={"status": "published"},
    )
    assert published.status_code == 200
    assert published.json()["status"] == "published"

    removed = await client.delete(
        f"/api/v1/knowledge/{draft['id']}", headers=supervisor["headers"]
    )
    assert removed.status_code == 204


@pytest.mark.asyncio
async def test_agent_cannot_delete_a_ticket(
    client: AsyncClient, workspace: dict, agent: dict
) -> None:
    """Tickets are the customer record, so destroying one is not routine work."""
    ticket = await client.post(
        "/api/v1/tickets", headers=agent["headers"], json={"subject": "Where is my order"}
    )
    assert ticket.status_code == 201
    response = await client.delete(
        f"/api/v1/tickets/{ticket.json()['id']}", headers=agent["headers"]
    )
    assert response.status_code == 403

    survived = await client.get(
        f"/api/v1/tickets/{ticket.json()['id']}", headers=workspace["headers"]
    )
    assert survived.status_code == 200


@pytest.mark.asyncio
async def test_agents_do_not_write_shared_macros(
    client: AsyncClient, workspace: dict, agent: dict
) -> None:
    """A macro is workspace wide and goes to customers verbatim."""
    refused = await client.post(
        "/api/v1/workspace/macros",
        headers=agent["headers"],
        json={"name": "Thanks", "body": "Thank you for waiting.", "tags": []},
    )
    assert refused.status_code == 403

    mine = await client.post(
        "/api/v1/workspace/macros",
        headers=workspace["headers"],
        json={"name": "Thanks", "body": "Thank you for waiting.", "tags": []},
    )
    assert mine.status_code == 201
    # Agents still read them, because inserting one is the point of the feature.
    listed = await client.get("/api/v1/workspace/macros", headers=agent["headers"])
    assert listed.status_code == 200
    assert [macro["name"] for macro in listed.json()] == ["Thanks"]

    for method in (client.patch, client.delete):
        response = await method(
            f"/api/v1/workspace/macros/{mine.json()['id']}",
            headers=agent["headers"],
            **({"json": {"name": "Edited", "body": "", "tags": []}} if method is client.patch else {}),
        )
        assert response.status_code == 403


@pytest.mark.asyncio
async def test_channel_catalog_needs_a_session(client: AsyncClient) -> None:
    """It names the credentials each provider wants, so it is not anonymous."""
    assert (await client.get("/api/v1/workspace/channels/catalog")).status_code == 401


@pytest.mark.asyncio
async def test_agent_cannot_add_teammates(client: AsyncClient, agent: dict) -> None:
    response = await client.post(
        "/api/v1/workspace/team",
        headers=agent["headers"],
        json={"name": "Me again", "email": "alt@team.example", "password": "long-enough-pass"},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_supervisor_cannot_mint_an_owner(client: AsyncClient, supervisor: dict) -> None:
    """Otherwise a supervisor makes an owner on an address they control."""
    response = await client.post(
        "/api/v1/workspace/team",
        headers=supervisor["headers"],
        json={
            "name": "Backdoor",
            "email": "backdoor@team.example",
            "password": "long-enough-pass",
            "role": "owner",
        },
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_supervisor_cannot_promote_themselves(
    client: AsyncClient, supervisor: dict
) -> None:
    response = await client.patch(
        f"/api/v1/workspace/team/{supervisor['user']['id']}",
        headers=supervisor["headers"],
        json={"role": "owner"},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_the_last_owner_cannot_be_stood_down(
    client: AsyncClient, workspace: dict
) -> None:
    """A workspace with no owner can never be configured again."""
    owner_id = workspace["user"]["id"]
    demote = await client.patch(
        f"/api/v1/workspace/team/{owner_id}", headers=workspace["headers"], json={"role": "agent"}
    )
    assert demote.status_code == 403

    off = await client.patch(
        f"/api/v1/workspace/team/{owner_id}",
        headers=workspace["headers"],
        json={"isActive": False},
    )
    assert off.status_code == 403


@pytest.mark.asyncio
async def test_owner_manages_the_team(client: AsyncClient, workspace: dict, agent: dict) -> None:
    """The whole point of roles is being able to hand them out."""
    promoted = await client.patch(
        f"/api/v1/workspace/team/{agent['user']['id']}",
        headers=workspace["headers"],
        json={"role": "supervisor"},
    )
    assert promoted.status_code == 200
    assert promoted.json()["role"] == "supervisor"

    off = await client.patch(
        f"/api/v1/workspace/team/{agent['user']['id']}",
        headers=workspace["headers"],
        json={"isActive": False},
    )
    assert off.status_code == 200

    # A switched off account cannot sign in, and the history stays put.
    denied = await client.post(
        "/api/v1/auth/login",
        json={"email": "agent@team.example", "password": "another-long-password"},
    )
    assert denied.status_code == 401
    assert len((await client.get("/api/v1/workspace/team", headers=workspace["headers"])).json()) == 2


@pytest.mark.asyncio
async def test_a_duplicate_email_is_refused(client: AsyncClient, workspace: dict) -> None:
    body = {"name": "Twice", "email": "twice@team.example", "password": "long-enough-pass"}
    assert (
        await client.post("/api/v1/workspace/team", headers=workspace["headers"], json=body)
    ).status_code == 201
    assert (
        await client.post("/api/v1/workspace/team", headers=workspace["headers"], json=body)
    ).status_code == 409
