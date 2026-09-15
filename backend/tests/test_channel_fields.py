"""The credentials each channel asks for."""

from __future__ import annotations

import pathlib
import re

import pytest
from httpx import AsyncClient

from app.channels import channel_catalog, get_adapter

CHANNEL_SOURCE = pathlib.Path(__file__).resolve().parent.parent / "app" / "channels"

EXPECTED = {
    "email": {
        "required": {"smtp_host", "smtp_port", "from_address"},
        "optional": {"smtp_user", "smtp_password", "imap_host", "imap_port",
                     "imap_user", "imap_password", "imap_folder", "webhook_secret"},
    },
    "whatsapp": {
        "required": {"app_secret", "verify_token", "access_token", "phone_number_id"},
        "optional": set(),
    },
    "instagram": {
        # The same app, with the connected page rather than a phone number.
        "required": {"app_secret", "verify_token", "access_token", "page_id"},
        "optional": set(),
    },
    "sms": {
        "required": {"account_sid", "auth_token", "from_number"},
        "optional": set(),
    },
    "voice": {
        "required": {"account_sid", "auth_token", "from_number"},
        "optional": set(),
    },
}


@pytest.mark.parametrize("channel", sorted(EXPECTED))
def test_the_required_keys_match_the_provider(channel: str) -> None:
    adapter = get_adapter(channel)
    assert adapter is not None, channel
    assert set(adapter.required_keys) == EXPECTED[channel]["required"], (
        f"{channel} asks for {sorted(adapter.required_keys)}, "
        f"expected {sorted(EXPECTED[channel]['required'])}"
    )


@pytest.mark.parametrize("channel", sorted(EXPECTED))
def test_every_key_asked_for_is_actually_read(channel: str) -> None:
    """A field nobody reads is a field somebody fills in for nothing."""
    sources = "\n".join(path.read_text() for path in CHANNEL_SOURCE.glob("*.py"))
    # The webhook layer reads verify_token, so it counts too.
    sources += (CHANNEL_SOURCE.parent / "api" / "webhooks.py").read_text()

    adapter = get_adapter(channel)
    for key in adapter.required_keys:
        used = re.search(rf'''(config|live_config\(\))[^\n]*["']{key}["']''', sources)
        assert used, f"{channel} asks for {key} but nothing reads it"


@pytest.mark.asyncio
async def test_the_catalog_tells_the_interface_the_same_thing(
    client: AsyncClient, workspace: dict
) -> None:
    """The settings screen builds its form from this, so it has to agree."""
    response = await client.get(
        "/api/v1/workspace/channels/catalog", headers=workspace["headers"]
    )
    assert response.status_code == 200
    catalog = {entry["channel"]: entry for entry in response.json()}

    for channel, expected in EXPECTED.items():
        assert set(catalog[channel]["requiredKeys"]) == expected["required"], channel

    # Web chat needs nothing, which is what makes the widget one script tag.
    assert catalog["web"]["requiredKeys"] == []


def test_the_catalog_and_the_adapters_cannot_drift() -> None:
    for entry in channel_catalog():
        adapter = get_adapter(entry["channel"])
        if adapter is None:
            continue
        assert entry["requiredKeys"] == list(adapter.required_keys), entry["channel"]


@pytest.mark.asyncio
async def test_a_channel_will_not_activate_half_configured(
    client: AsyncClient, workspace: dict
) -> None:
    """Otherwise it looks connected and quietly fails on the first message."""
    response = await client.put(
        "/api/v1/workspace/channels/whatsapp",
        headers=workspace["headers"],
        json={"isActive": True, "config": {"app_secret": "only-this-one"}},
    )
    assert response.status_code == 422
    detail = response.json()["detail"]
    for missing in ("verify_token", "access_token", "phone_number_id"):
        assert missing in detail, detail
