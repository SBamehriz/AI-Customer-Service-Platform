"""Test fixtures."""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "test-secret-key-not-for-production")
os.environ.setdefault("LLM_PROVIDER", "none")
os.environ.setdefault("SEED_DEMO_DATA", "false")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.db import Base, engine
from app.main import app
from app.ratelimit import ALL_LIMITERS


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    return "asyncio"


@pytest_asyncio.fixture
async def client() -> AsyncClient:
    """An HTTP client bound to the app, over a freshly created schema."""
    # Each test gets its own event loop. A pooled connection belongs to the
    # loop that opened it, which asyncpg enforces and aiosqlite does not, so
    # the pool is emptied at both ends. Without this the suite only runs on
    # SQLite, and the PostgreSQL half of the portability claim goes unchecked.
    await engine.dispose()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    for limiter in ALL_LIMITERS:
        limiter.reset()

    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as http:
            yield http
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def workspace(client: AsyncClient) -> dict:
    """A registered workspace plus an authorised header set."""
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "workspaceName": "Test Outfitters",
            "name": "Ada Tester",
            "email": "ada@team.example",
            "password": "correct-horse-battery",
        },
    )
    assert response.status_code == 201, response.text
    session = response.json()
    return {
        "token": session["accessToken"],
        "headers": {"Authorization": f"Bearer {session['accessToken']}"},
        "user": session["user"],
        "workspace": session["workspace"],
    }


def twilio_signature(token: str, url: str, fields: dict[str, str]) -> str:
    """The signature Twilio would send for this callback."""
    import base64
    import hashlib
    import hmac

    message = url + "".join(f"{key}{fields[key]}" for key in sorted(fields))
    return base64.b64encode(
        hmac.new(token.encode(), message.encode(), hashlib.sha1).digest()
    ).decode()


def twilio_post(path: str, fields: dict[str, str], token: str) -> dict:
    """Arguments for a signed Twilio style POST, ready to splat into the client."""
    from urllib.parse import urlencode

    from app.config import settings

    signed_url = f"{settings.PUBLIC_URL.rstrip('/')}{path}"
    return {
        "content": urlencode(fields),
        "headers": {
            "Content-Type": "application/x-www-form-urlencoded",
            "X-Twilio-Signature": twilio_signature(token, signed_url, fields),
        },
    }
