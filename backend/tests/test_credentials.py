"""Credentials the platform holds on your behalf."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app import crypto
from app.db import async_session_maker
from app.models import ChannelAccount, Workspace


def test_a_sealed_value_does_not_contain_the_secret() -> None:
    sealed = crypto.seal("sk-live-abcdef123456")
    assert "abcdef123456" not in sealed
    assert crypto.is_sealed(sealed)
    assert crypto.unseal(sealed) == "sk-live-abcdef123456"


def test_plain_values_written_before_encryption_still_read() -> None:
    """Upgrading an existing install must not lock anyone out of their own keys."""
    assert crypto.unseal("plain-old-value") == "plain-old-value"
    assert not crypto.is_sealed("plain-old-value")


def test_a_changed_secret_key_reads_as_missing_not_as_a_crash() -> None:
    """Rotating SECRET_KEY makes stored credentials unreadable, by design."""
    sealed = crypto.seal("sk-live-abcdef123456")
    from app.config import settings

    original = settings.SECRET_KEY
    try:
        settings.SECRET_KEY = "a-completely-different-key"
        assert crypto.unseal(sealed) is None
    finally:
        settings.SECRET_KEY = original
    assert crypto.unseal(sealed) == "sk-live-abcdef123456"


@pytest.mark.asyncio
async def test_channel_secrets_are_encrypted_in_the_database(
    client: AsyncClient, workspace: dict
) -> None:
    """The point of all this. A copy of the file must not hand over the keys."""
    secret = "super-secret-twilio-token"
    saved = await client.put(
        "/api/v1/workspace/channels/sms",
        headers=workspace["headers"],
        json={
            "isActive": False,
            "config": {
                "account_sid": "AC123",
                "auth_token": secret,
                "from_number": "+15550100",
            },
        },
    )
    assert saved.status_code == 200, saved.text
    # The response names the keys but never the values.
    assert "auth_token" in saved.json()["configuredKeys"]
    assert secret not in saved.text

    async with async_session_maker() as db:
        account = await db.scalar(
            select(ChannelAccount).where(ChannelAccount.channel == "sms")
        )
        assert account is not None
        stored = account.config["auth_token"]
        assert secret not in stored, "the raw token is sitting in the database"
        assert crypto.is_sealed(stored)
        # And the adapters still get something they can use.
        assert account.live_config()["auth_token"] == secret


@pytest.mark.asyncio
async def test_saving_one_field_keeps_the_others(
    client: AsyncClient, workspace: dict
) -> None:
    """Config is merged, so a partial save must not wipe the rest."""
    await client.put(
        "/api/v1/workspace/channels/sms",
        headers=workspace["headers"],
        json={
            "isActive": False,
            "config": {"account_sid": "AC123", "auth_token": "tok", "from_number": "+1"},
        },
    )
    await client.put(
        "/api/v1/workspace/channels/sms",
        headers=workspace["headers"],
        json={"isActive": False, "config": {"from_number": "+15559999"}},
    )
    async with async_session_maker() as db:
        account = await db.scalar(
            select(ChannelAccount).where(ChannelAccount.channel == "sms")
        )
        live = account.live_config()
        assert live["auth_token"] == "tok", "an untouched secret was lost"
        assert live["from_number"] == "+15559999"


@pytest.mark.asyncio
async def test_provider_key_is_stored_encrypted_and_never_returned(
    client: AsyncClient, workspace: dict
) -> None:
    key = "sk-proj-do-not-leak-me"
    saved = await client.put(
        "/api/v1/workspace/ai",
        headers=workspace["headers"],
        json={"provider": "openai", "model": "gpt-4o-mini", "apiKey": key},
    )
    assert saved.status_code == 200, saved.text
    body = saved.json()
    assert body["hasKey"] is True
    assert body["provider"] == "openai"
    assert key not in saved.text, "the key came back to the browser"

    read = await client.get("/api/v1/workspace/ai", headers=workspace["headers"])
    assert key not in read.text

    async with async_session_maker() as db:
        ws = await db.scalar(
            select(Workspace).where(Workspace.id == workspace["workspace"]["id"])
        )
        assert key not in ws.ai_config["api_key"]
        assert crypto.unseal(ws.ai_config["api_key"]) == key


@pytest.mark.asyncio
async def test_saving_settings_without_a_key_keeps_the_stored_one(
    client: AsyncClient, workspace: dict
) -> None:
    """The interface never holds the secret, so it cannot send it back."""
    await client.put(
        "/api/v1/workspace/ai",
        headers=workspace["headers"],
        json={"provider": "openai", "model": "gpt-4o-mini", "apiKey": "sk-keep-me"},
    )
    changed = await client.put(
        "/api/v1/workspace/ai",
        headers=workspace["headers"],
        json={"provider": "openai", "model": "gpt-4o"},
    )
    assert changed.status_code == 200
    assert changed.json()["hasKey"] is True

    async with async_session_maker() as db:
        ws = await db.scalar(
            select(Workspace).where(Workspace.id == workspace["workspace"]["id"])
        )
        assert crypto.unseal(ws.ai_config["api_key"]) == "sk-keep-me"
        assert ws.ai_config["model"] == "gpt-4o"


@pytest.mark.asyncio
async def test_choosing_none_clears_the_key(client: AsyncClient, workspace: dict) -> None:
    await client.put(
        "/api/v1/workspace/ai",
        headers=workspace["headers"],
        json={"provider": "openai", "model": "gpt-4o-mini", "apiKey": "sk-remove-me"},
    )
    cleared = await client.put(
        "/api/v1/workspace/ai", headers=workspace["headers"], json={"provider": "none"}
    )
    assert cleared.json()["hasKey"] is False
    assert cleared.json()["active"] is False


@pytest.mark.asyncio
async def test_agents_cannot_read_or_set_the_provider(
    client: AsyncClient, workspace: dict
) -> None:
    """It is a workspace wide credential with a bill attached."""
    created = await client.post(
        "/api/v1/workspace/team",
        headers=workspace["headers"],
        json={
            "name": "Agent",
            "email": "agent@keys.example",
            "password": "long-enough-password",
            "role": "agent",
        },
    )
    assert created.status_code == 201
    session = await client.post(
        "/api/v1/auth/login",
        json={"email": "agent@keys.example", "password": "long-enough-password"},
    )
    headers = {"Authorization": f"Bearer {session.json()['accessToken']}"}

    assert (await client.get("/api/v1/workspace/ai", headers=headers)).status_code == 403
    assert (
        await client.put(
            "/api/v1/workspace/ai", headers=headers, json={"provider": "openai"}
        )
    ).status_code == 403
