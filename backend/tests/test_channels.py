"""Channel adapters and the shared ingest pipeline."""

from __future__ import annotations

import hashlib
import hmac
import json

import pytest
from httpx import AsyncClient

from app.channels import ADAPTERS, get_adapter
from app.channels.email import EmailAdapter, _strip_quoted_reply
from app.channels.meta import InstagramAdapter, WhatsAppAdapter
from app.channels.twilio import SmsAdapter, VoiceAdapter


def test_every_channel_is_registered() -> None:
    assert set(ADAPTERS) == {"web", "email", "whatsapp", "instagram", "sms", "voice", "api"}


def test_whatsapp_parses_a_text_message() -> None:
    payload = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "contacts": [{"wa_id": "15550142", "profile": {"name": "Elena"}}],
                            "messages": [
                                {
                                    "from": "15550142",
                                    "id": "wamid.abc",
                                    "type": "text",
                                    "text": {"body": "Where is my order?"},
                                }
                            ],
                        }
                    }
                ]
            }
        ]
    }
    messages = WhatsAppAdapter().parse_inbound(payload, {})
    assert len(messages) == 1
    assert messages[0].body == "Where is my order?"
    assert messages[0].sender_name == "Elena"
    assert messages[0].sender_phone == "+15550142"
    assert messages[0].external_id == "wamid.abc"


def test_whatsapp_ignores_status_only_deliveries() -> None:
    """Delivery receipts carry no `messages` key and must produce nothing."""
    payload = {"entry": [{"changes": [{"value": {"statuses": [{"status": "delivered"}]}}]}]}
    assert WhatsAppAdapter().parse_inbound(payload, {}) == []


def test_instagram_skips_our_own_echoes() -> None:
    payload = {
        "entry": [
            {
                "messaging": [
                    {"sender": {"id": "123"}, "message": {"mid": "m1", "text": "hi", "is_echo": True}},
                    {"sender": {"id": "123"}, "message": {"mid": "m2", "text": "real question"}},
                ]
            }
        ]
    }
    messages = InstagramAdapter().parse_inbound(payload, {"page_id": "999"})
    assert [m.body for m in messages] == ["real question"]


def test_meta_signature_verification() -> None:
    adapter = WhatsAppAdapter()
    body = b'{"entry":[]}'
    secret = "app-secret"
    signature = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

    assert adapter.verify_signature({"app_secret": secret}, body, {"x-hub-signature-256": signature})
    assert not adapter.verify_signature({"app_secret": secret}, body, {"x-hub-signature-256": "sha256=bad"})
    # No configured secret means we cannot prove the sender, so refuse.
    assert not adapter.verify_signature({}, body, {"x-hub-signature-256": signature})


def test_sms_parses_a_twilio_form_post() -> None:
    messages = SmsAdapter().parse_inbound(
        {"Body": "Wrong size boots", "From": "+15550119", "MessageSid": "SM1"}, {}
    )
    assert messages[0].body == "Wrong size boots"
    assert messages[0].thread_id == "+15550119"


def test_voice_only_yields_lines_with_speech() -> None:
    adapter = VoiceAdapter()
    assert adapter.parse_inbound({"From": "+1555", "CallSid": "CA1"}, {}) == []
    lines = adapter.parse_inbound(
        {"From": "+1555", "CallSid": "CA1", "SpeechResult": "I need to return a jacket"}, {}
    )
    assert lines[0].meta["transcript_line"] is True


def test_voice_twiml_escapes_the_greeting() -> None:
    twiml = VoiceAdapter.answer_twiml('Welcome to "Gear & Co"', "https://example.com/hook")
    assert "&amp;" in twiml and "&quot;" in twiml
    assert "<Gather" in twiml


def test_email_parses_a_postmark_payload() -> None:
    messages = EmailAdapter().parse_inbound(
        {
            "From": "Elena Farrow <elena@example.com>",
            "Subject": "Return request",
            "TextBody": "I would like to return a jacket.",
            "References": "<root@example.com> <second@example.com>",
            "MessageID": "<new@example.com>",
        },
        {},
    )
    assert messages[0].sender_email == "elena@example.com"
    assert messages[0].sender_name == "Elena Farrow"
    # Threading uses the root of References so the whole chain stays together.
    assert messages[0].thread_id == "<root@example.com>"


def test_email_strips_the_quoted_history() -> None:
    body = "Thanks, that works.\n\nOn Tue, 3 Jun 2025, Support wrote:\n> Your refund is processed"
    assert _strip_quoted_reply(body) == "Thanks, that works."


def test_email_keeps_body_when_everything_looks_quoted() -> None:
    """A message that is only a quote must not become empty."""
    assert _strip_quoted_reply("> just this") == "> just this"


def test_web_adapter_needs_a_session() -> None:
    adapter = get_adapter("web")
    assert adapter is not None
    assert adapter.parse_inbound({"body": "hello"}, {}) == []
    assert adapter.parse_inbound({"body": "hello", "sessionId": "web_1"}, {})


def test_missing_keys_are_reported() -> None:
    adapter = WhatsAppAdapter()
    assert set(adapter.missing_keys({})) == set(adapter.required_keys)
    assert adapter.missing_keys(
        {"app_secret": "a", "verify_token": "b", "access_token": "c", "phone_number_id": "d"}
    ) == []


@pytest.mark.asyncio
async def test_whatsapp_webhook_creates_conversation_and_ticket(
    client: AsyncClient, workspace: dict
) -> None:
    secret = "app-secret"
    connect = await client.put(
        "/api/v1/workspace/channels/whatsapp",
        headers=workspace["headers"],
        json={
            "displayName": "Support line",
            "isActive": True,
            "config": {
                "app_secret": secret,
                "verify_token": "verify-me",
                "access_token": "token",
                "phone_number_id": "1234",
            },
        },
    )
    assert connect.status_code == 200, connect.text

    payload = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "contacts": [{"wa_id": "15550142", "profile": {"name": "Elena"}}],
                            "messages": [
                                {
                                    "from": "15550142",
                                    "id": "wamid.e2e",
                                    "type": "text",
                                    "text": {"body": "My jacket arrived damaged"},
                                }
                            ],
                        }
                    }
                ]
            }
        ]
    }
    raw = json.dumps(payload).encode()
    signature = "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()

    workspace_id = workspace["workspace"]["id"]
    response = await client.post(
        f"/api/v1/webhooks/whatsapp/{workspace_id}",
        content=raw,
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": signature},
    )
    assert response.status_code == 200, response.text
    assert response.json()["ingested"] == 1

    conversations = (await client.get("/api/v1/conversations", headers=workspace["headers"])).json()
    assert len(conversations) == 1
    assert conversations[0]["channel"] == "whatsapp"
    assert conversations[0]["customer"]["name"] == "Elena"

    tickets = (await client.get("/api/v1/tickets", headers=workspace["headers"])).json()
    assert len(tickets) == 1
    # The "damaged" routing rule is not seeded in tests, so priority stays default.
    assert tickets[0]["channel"] == "whatsapp"


@pytest.mark.asyncio
async def test_twilio_signature_is_checked_against_the_public_url(
    client: AsyncClient, workspace: dict
) -> None:
    """Twilio signs the URL it called, which is the public one, not the internal one."""
    import base64
    import hmac as hmac_module
    from urllib.parse import urlencode

    from app.config import settings

    token = "twilio-auth-token"
    await client.put(
        "/api/v1/workspace/channels/sms",
        headers=workspace["headers"],
        json={
            "isActive": True,
            "config": {"account_sid": "AC1", "auth_token": token, "from_number": "+15550100"},
        },
    )

    workspace_id = workspace["workspace"]["id"]
    path = f"/api/v1/webhooks/sms/{workspace_id}"
    fields = {"From": "+15550119", "Body": "Wrong size boots", "MessageSid": "SM1"}
    body = urlencode(fields)

    signed_url = f"{settings.PUBLIC_URL.rstrip('/')}{path}"
    message = signed_url + "".join(f"{key}{fields[key]}" for key in sorted(fields))
    signature = base64.b64encode(
        hmac_module.new(token.encode(), message.encode(), hashlib.sha1).digest()
    ).decode()

    response = await client.post(
        path,
        content=body,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "X-Twilio-Signature": signature,
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["ingested"] == 1


@pytest.mark.asyncio
async def test_webhook_rejects_a_bad_signature(client: AsyncClient, workspace: dict) -> None:
    await client.put(
        "/api/v1/workspace/channels/whatsapp",
        headers=workspace["headers"],
        json={
            "isActive": True,
            "config": {
                "app_secret": "s",
                "verify_token": "v",
                "access_token": "a",
                "phone_number_id": "p",
            },
        },
    )
    response = await client.post(
        f"/api/v1/webhooks/whatsapp/{workspace['workspace']['id']}",
        content=b"{}",
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": "sha256=wrong"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_redelivered_webhook_is_ignored(client: AsyncClient, workspace: dict) -> None:
    """Providers retry, so the same provider message id must not post twice."""
    secret = "s"
    await client.put(
        "/api/v1/workspace/channels/whatsapp",
        headers=workspace["headers"],
        json={
            "isActive": True,
            "config": {
                "app_secret": secret,
                "verify_token": "v",
                "access_token": "a",
                "phone_number_id": "p",
            },
        },
    )
    payload = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "messages": [
                                {"from": "15550001", "id": "wamid.dupe", "type": "text", "text": {"body": "hello there"}}
                            ]
                        }
                    }
                ]
            }
        ]
    }
    raw = json.dumps(payload).encode()
    signature = "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    url = f"/api/v1/webhooks/whatsapp/{workspace['workspace']['id']}"
    headers = {"Content-Type": "application/json", "X-Hub-Signature-256": signature}

    first = await client.post(url, content=raw, headers=headers)
    second = await client.post(url, content=raw, headers=headers)
    assert first.json()["ingested"] == 1
    assert second.json()["ingested"] == 0

    conversations = (await client.get("/api/v1/conversations", headers=workspace["headers"])).json()
    assert len(conversations) == 1


@pytest.mark.asyncio
async def test_channel_cannot_activate_while_credentials_are_missing(
    client: AsyncClient, workspace: dict
) -> None:
    response = await client.put(
        "/api/v1/workspace/channels/whatsapp",
        headers=workspace["headers"],
        json={"isActive": True, "config": {"app_secret": "only-one"}},
    )
    assert response.status_code == 422
    assert "missing" in response.json()["detail"]


@pytest.mark.asyncio
async def test_channel_secrets_are_never_returned(client: AsyncClient, workspace: dict) -> None:
    await client.put(
        "/api/v1/workspace/channels/sms",
        headers=workspace["headers"],
        json={
            "isActive": True,
            "config": {"account_sid": "AC1", "auth_token": "super-secret", "from_number": "+1555"},
        },
    )
    body = (await client.get("/api/v1/workspace/channels", headers=workspace["headers"])).text
    assert "super-secret" not in body
    assert "auth_token" in body  # the key name is listed, the value is not
