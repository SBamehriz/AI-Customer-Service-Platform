"""Recording calls."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.channels.twilio import DEFAULT_RECORDING_NOTICE, VoiceAdapter

from .conftest import twilio_post


def test_recording_is_off_unless_it_is_turned_on() -> None:
    twiml = VoiceAdapter.answer_twiml("Thanks for calling", "https://example.test/action")
    assert "<Record" not in twiml
    assert "Gather" in twiml, "the call still has to work with recording off"


def test_a_recorded_call_always_announces_itself() -> None:
    """There is no way to get a recording without the notice being played."""
    twiml = VoiceAdapter.answer_twiml(
        "Thanks for calling",
        "https://example.test/action",
        record=True,
        recording_callback="https://example.test/recording",
        notice="This call may be recorded.",
    )
    assert "<Start><Recording" in twiml
    assert "This call may be recorded." in twiml
    # The notice comes before the recording starts, not after it.
    assert twiml.index("This call may be recorded.") < twiml.index("<Start><Recording")
    assert "recordingStatusCallback=" in twiml


def test_the_twiml_escapes_what_it_is_given() -> None:
    """The greeting is workspace controlled, so it must not be able to inject."""
    twiml = VoiceAdapter.answer_twiml(
        '</Say><Hangup/><Say>"gotcha" & more', "https://example.test/a?b=1&c=2"
    )
    assert "<Hangup/>" not in twiml
    assert "&amp;" in twiml


@pytest.mark.asyncio
async def test_the_answer_endpoint_follows_the_workspace_setting(
    client: AsyncClient, workspace: dict
) -> None:
    workspace_id = workspace["workspace"]["id"]
    await client.put(
        "/api/v1/workspace/channels/voice",
        headers=workspace["headers"],
        json={
            "isActive": True,
            "config": {"account_sid": "AC1", "auth_token": "secret", "from_number": "+15550100"},
        },
    )
    path = f"/api/v1/webhooks/voice/{workspace_id}/answer"
    call = {"CallSid": "CA1", "From": "+15550119"}

    quiet = await client.post(path, **twilio_post(path, call, "secret"))
    assert quiet.status_code == 200, quiet.text
    assert "<Record" not in quiet.text

    saved = await client.patch(
        "/api/v1/workspace",
        headers=workspace["headers"],
        json={"settings": {"recordCalls": True, "recordingNotice": "We record calls."}},
    )
    assert saved.status_code == 200

    recorded = await client.post(path, **twilio_post(path, call, "secret"))
    assert "<Start><Recording" in recorded.text
    assert "We record calls." in recorded.text


@pytest.mark.asyncio
async def test_the_answer_endpoint_refuses_an_unsigned_caller(
    client: AsyncClient, workspace: dict
) -> None:
    """The instructions it returns name this workspace's callbacks."""
    workspace_id = workspace["workspace"]["id"]
    await client.put(
        "/api/v1/workspace/channels/voice",
        headers=workspace["headers"],
        json={
            "isActive": True,
            "config": {"account_sid": "AC1", "auth_token": "secret", "from_number": "+15550100"},
        },
    )
    path = f"/api/v1/webhooks/voice/{workspace_id}/answer"

    missing = await client.post(path, data={"CallSid": "CA1"})
    assert missing.status_code == 401

    wrong = await client.post(
        path, data={"CallSid": "CA1"}, headers={"X-Twilio-Signature": "invalid"}
    )
    assert wrong.status_code == 401


@pytest.mark.asyncio
async def test_a_correctly_signed_recording_callback_is_accepted(
    client: AsyncClient, workspace: dict
) -> None:
    """The recording route verified a header nothing ever set."""
    workspace_id = workspace["workspace"]["id"]
    await client.put(
        "/api/v1/workspace/channels/voice",
        headers=workspace["headers"],
        json={
            "isActive": True,
            "config": {"account_sid": "AC1", "auth_token": "secret", "from_number": "+15550100"},
        },
    )
    await client.patch(
        "/api/v1/workspace",
        headers=workspace["headers"],
        json={"settings": {"recordCalls": True, "recordingNotice": "We record calls."}},
    )

    path = f"/api/v1/webhooks/voice/{workspace_id}/recording"
    fields = {
        "CallSid": "CAqa1",
        "RecordingSid": "REqa1",
        "RecordingUrl": "https://api.twilio.test/qa-inert",
        "RecordingDuration": "20",
    }
    accepted = await client.post(path, **twilio_post(path, fields, "secret"))
    assert accepted.status_code == 204, accepted.text

    refused = await client.post(
        path, data=fields, headers={"X-Twilio-Signature": "invalid"}
    )
    assert refused.status_code == 403


def test_recording_cannot_start_without_something_to_say() -> None:
    """An empty notice would be a silent Say and then a recording."""
    twiml = VoiceAdapter.answer_twiml(
        "Thanks for calling",
        "https://example.test/action",
        record=True,
        recording_callback="https://example.test/recording",
        notice="   ",
    )
    assert "<Say voice=\"Polly.Joanna\"></Say>" not in twiml
    assert DEFAULT_RECORDING_NOTICE in twiml
    assert twiml.index(DEFAULT_RECORDING_NOTICE) < twiml.index("<Start><Recording")


@pytest.mark.asyncio
async def test_recording_cannot_be_turned_on_with_a_blank_notice(
    client: AsyncClient, workspace: dict
) -> None:
    """Recording somebody without telling them is illegal in a lot of places."""
    blank = await client.patch(
        "/api/v1/workspace",
        headers=workspace["headers"],
        json={"settings": {"recordCalls": True, "recordingNotice": "   "}},
    )
    assert blank.status_code == 422, blank.text

    await client.patch(
        "/api/v1/workspace",
        headers=workspace["headers"],
        json={"settings": {"recordCalls": True, "recordingNotice": "We record calls."}},
    )
    cleared = await client.patch(
        "/api/v1/workspace",
        headers=workspace["headers"],
        json={"settings": {"recordingNotice": ""}},
    )
    assert cleared.status_code == 422, cleared.text


@pytest.mark.asyncio
async def test_an_unsigned_recording_callback_is_refused(
    client: AsyncClient, workspace: dict
) -> None:
    """Otherwise anyone could post a URL and have the platform fetch it."""
    workspace_id = workspace["workspace"]["id"]
    await client.patch(
        "/api/v1/workspace",
        headers=workspace["headers"],
        json={"settings": {"recordCalls": True}},
    )
    await client.put(
        "/api/v1/workspace/channels/voice",
        headers=workspace["headers"],
        json={
            "isActive": True,
            "config": {"account_sid": "AC1", "auth_token": "secret", "from_number": "+15550100"},
        },
    )
    response = await client.post(
        f"/api/v1/webhooks/voice/{workspace_id}/recording",
        data={"RecordingUrl": "https://evil.example/steal", "CallSid": "CA1"},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_media_is_only_fetched_from_twilio(monkeypatch) -> None:
    """A URL out of a webhook body never sends credentials somewhere else."""
    import httpx as real_httpx

    from app.channels import twilio as twilio_module
    from app.channels.twilio import SmsAdapter, VoiceAdapter

    def refuse(*args, **kwargs):
        raise AssertionError("a request was made for a URL that is not Twilio's")

    monkeypatch.setattr(twilio_module.httpx, "AsyncClient", refuse)
    assert real_httpx is not None

    config = {"account_sid": "ACtest", "auth_token": "a-token", "from_number": "+15555550100"}
    refused = [
        "http://169.254.169.254/latest/meta-data/iam/security-credentials/",
        "https://169.254.169.254/latest/meta-data/",
        "http://localhost:8000/api/v1/workspace",
        "https://attacker.example.com/collect",
        # A host that merely ends with the right letters is not the right host.
        "https://api.twilio.com.attacker.example.com/x",
        "https://nottwilio.com/x",
        # Plain HTTP to the real host would send the credentials in the clear.
        "http://api.twilio.com/2010-04-01/Accounts/ACtest/Media/ME1",
        "",
        "not a url at all",
    ]
    for url in refused:
        assert await SmsAdapter().fetch_attachment(config, {"url": url}) is None, url
        assert await VoiceAdapter().fetch_recording(config, url) is None, url


def test_the_twilio_host_check_accepts_the_real_media_hosts() -> None:
    """The addresses Twilio actually serves media and recordings from."""
    from app.channels.twilio import _is_twilio_url

    for url in (
        "https://api.twilio.com/2010-04-01/Accounts/ACtest/Messages/MM1/Media/ME1",
        "https://media.twiliocdn.com/ACtest/abcdef",
        "https://s3-external-1.twiliocdn.com/recording.mp3",
    ):
        assert _is_twilio_url(url), url
