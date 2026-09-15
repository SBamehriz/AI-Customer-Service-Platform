"""Authentication, tokens and access control."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.security import create_access_token, decode_token, hash_password, verify_password


def test_password_round_trip() -> None:
    stored = hash_password("correct-horse-battery")
    assert stored.startswith("scrypt$")
    assert verify_password("correct-horse-battery", stored)
    assert not verify_password("wrong-password", stored)


def test_password_hashes_are_salted() -> None:
    """Two hashes of one password must differ, or the salt is not doing its job."""
    assert hash_password("same") != hash_password("same")


def test_malformed_hash_is_rejected_not_raised() -> None:
    assert not verify_password("anything", "not-a-real-hash")
    assert not verify_password("anything", "")


def test_token_round_trip() -> None:
    token = create_access_token("user-1", "ws-1", "agent")
    payload = decode_token(token)
    assert payload is not None
    assert payload["sub"] == "user-1"
    assert payload["ws"] == "ws-1"
    assert payload["role"] == "agent"


def test_tampered_token_is_rejected() -> None:
    header, body, signature = create_access_token("user-1", "ws-1", "agent").split(".")
    # Swap the payload but keep the original signature.
    forged = f"{header}.{body[:-4]}AAAA.{signature}"
    assert decode_token(forged) is None
    assert decode_token("garbage") is None


@pytest.mark.asyncio
async def test_register_creates_owner(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "workspaceName": "Northwind Gear",
            "name": "Sam Owner",
            "email": "sam@northwind.example",
            "password": "a-long-enough-password",
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["user"]["role"] == "owner"
    assert body["workspace"]["slug"] == "northwind-gear"
    assert body["workspace"]["publicKey"].startswith("pk_")


@pytest.mark.asyncio
async def test_login_and_me(client: AsyncClient, workspace: dict) -> None:
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "ada@team.example", "password": "correct-horse-battery"},
    )
    assert login.status_code == 200
    token = login.json()["accessToken"]

    me = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["user"]["email"] == "ada@team.example"


@pytest.mark.asyncio
async def test_login_rejects_bad_password(client: AsyncClient, workspace: dict) -> None:
    response = await client.post(
        "/api/v1/auth/login", json={"email": "ada@team.example", "password": "nope"}
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_protected_route_needs_a_token(client: AsyncClient) -> None:
    assert (await client.get("/api/v1/tickets")).status_code == 401
    assert (
        await client.get("/api/v1/tickets", headers={"Authorization": "Bearer nonsense"})
    ).status_code == 401


@pytest.mark.asyncio
async def test_api_key_is_returned_once(client: AsyncClient, workspace: dict) -> None:
    response = await client.post("/api/v1/auth/api-key", headers=workspace["headers"])
    assert response.status_code == 200
    assert response.json()["apiKey"].startswith("sk_")


@pytest.mark.asyncio
async def test_api_key_authenticates_normal_routes(client: AsyncClient, workspace: dict) -> None:
    """A workspace key has to work on the routes the docs tell people to call."""
    key = (
        await client.post("/api/v1/auth/api-key", headers=workspace["headers"])
    ).json()["apiKey"]
    headers = {"Authorization": f"Bearer {key}"}

    created = await client.post(
        "/api/v1/tickets",
        headers=headers,
        json={"subject": "Raised from a script", "priority": "high", "channel": "api"},
    )
    assert created.status_code == 201, created.text

    listed = await client.get("/api/v1/tickets", headers=headers)
    assert listed.status_code == 200
    assert [ticket["subject"] for ticket in listed.json()] == ["Raised from a script"]


@pytest.mark.asyncio
async def test_api_key_acts_as_the_workspace_owner(client: AsyncClient, workspace: dict) -> None:
    key = (
        await client.post("/api/v1/auth/api-key", headers=workspace["headers"])
    ).json()["apiKey"]
    me = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {key}"})
    assert me.status_code == 200
    assert me.json()["user"]["role"] == "owner"


@pytest.mark.asyncio
async def test_rotating_a_key_invalidates_the_old_one(
    client: AsyncClient, workspace: dict
) -> None:
    first = (
        await client.post("/api/v1/auth/api-key", headers=workspace["headers"])
    ).json()["apiKey"]
    second = (
        await client.post("/api/v1/auth/api-key", headers=workspace["headers"])
    ).json()["apiKey"]
    assert first != second

    stale = await client.get("/api/v1/tickets", headers={"Authorization": f"Bearer {first}"})
    assert stale.status_code == 401
    fresh = await client.get("/api/v1/tickets", headers={"Authorization": f"Bearer {second}"})
    assert fresh.status_code == 200


@pytest.mark.asyncio
async def test_unknown_api_key_is_rejected(client: AsyncClient, workspace: dict) -> None:
    response = await client.get(
        "/api/v1/tickets", headers={"Authorization": "Bearer sk_not_a_real_key"}
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_api_keys_do_not_cross_workspaces(client: AsyncClient, workspace: dict) -> None:
    """A key must only ever reach the workspace it was issued for."""
    await client.post(
        "/api/v1/tickets", headers=workspace["headers"], json={"subject": "Belongs to A"}
    )
    other = await client.post(
        "/api/v1/auth/register",
        json={
            "workspaceName": "Other Co",
            "name": "Bee",
            "email": "bee@other.example",
            "password": "another-long-password",
        },
    )
    other_key = (
        await client.post(
            "/api/v1/auth/api-key",
            headers={"Authorization": f"Bearer {other.json()['accessToken']}"},
        )
    ).json()["apiKey"]

    listed = await client.get(
        "/api/v1/tickets", headers={"Authorization": f"Bearer {other_key}"}
    )
    assert listed.json() == []


@pytest.mark.asyncio
async def test_workspaces_are_isolated(client: AsyncClient, workspace: dict) -> None:
    """A ticket in one workspace must be invisible to another."""
    await client.post(
        "/api/v1/tickets",
        headers=workspace["headers"],
        json={"subject": "Private to workspace A", "description": ""},
    )

    other = await client.post(
        "/api/v1/auth/register",
        json={
            "workspaceName": "Other Co",
            "name": "Bee",
            "email": "bee@other.example",
            "password": "another-long-password",
        },
    )
    other_headers = {"Authorization": f"Bearer {other.json()['accessToken']}"}

    listing = await client.get("/api/v1/tickets", headers=other_headers)
    assert listing.status_code == 200
    assert listing.json() == []
