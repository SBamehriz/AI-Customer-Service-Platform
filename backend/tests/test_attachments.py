"""Files arriving and being served."""

from __future__ import annotations

import io

import pytest
from httpx import AsyncClient

from app import storage

PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


async def _upload(client: AsyncClient, workspace: dict, name="photo.png", ctype="image/png", data=PNG):
    return await client.post(
        "/api/v1/attachments",
        headers=workspace["headers"],
        files={"file": (name, io.BytesIO(data), ctype)},
    )


@pytest.mark.asyncio
async def test_an_agent_can_attach_a_file_to_a_reply(
    client: AsyncClient, workspace: dict
) -> None:
    key = workspace["workspace"]["publicKey"]
    started = await client.post(
        f"/api/v1/widget/{key}/messages", json={"body": "My jacket arrived torn"}
    )
    conversation_id = started.json()["conversationId"]

    uploaded = await _upload(client, workspace)
    assert uploaded.status_code == 201, uploaded.text
    attachment = uploaded.json()
    assert attachment["kind"] == "image"
    assert attachment["filename"] == "photo.png"

    sent = await client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        headers=workspace["headers"],
        json={"body": "Here is the replacement label", "attachmentIds": [attachment["id"]]},
    )
    assert sent.status_code == 201, sent.text
    assert [a["id"] for a in sent.json()["attachments"]] == [attachment["id"]]

    # And it comes back on the conversation, not just on the send response.
    thread = await client.get(
        f"/api/v1/conversations/{conversation_id}", headers=workspace["headers"]
    )
    carried = [m for m in thread.json()["messages"] if m["attachments"]]
    assert carried and carried[0]["attachments"][0]["filename"] == "photo.png"


@pytest.mark.asyncio
async def test_a_message_can_be_only_a_file(client: AsyncClient, workspace: dict) -> None:
    """Sending a photo with no words is a normal thing to do."""
    key = workspace["workspace"]["publicKey"]
    started = await client.post(f"/api/v1/widget/{key}/messages", json={"body": "Hello"})
    conversation_id = started.json()["conversationId"]
    attachment = (await _upload(client, workspace)).json()

    sent = await client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        headers=workspace["headers"],
        json={"body": "", "attachmentIds": [attachment["id"]]},
    )
    assert sent.status_code == 201

    empty = await client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        headers=workspace["headers"],
        json={"body": "   "},
    )
    assert empty.status_code == 422, "a message with neither text nor a file is nothing"


@pytest.mark.asyncio
async def test_executables_are_refused(client: AsyncClient, workspace: dict) -> None:
    """This is the one route that accepts bytes from strangers."""
    response = await _upload(
        client, workspace, name="payload.exe", ctype="application/x-msdownload", data=b"MZ..."
    )
    assert response.status_code == 415


@pytest.mark.asyncio
async def test_an_empty_file_is_refused(client: AsyncClient, workspace: dict) -> None:
    response = await _upload(client, workspace, data=b"")
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_a_filename_cannot_escape_the_store(
    client: AsyncClient, workspace: dict
) -> None:
    """Filenames are attacker controlled on every channel."""
    response = await _upload(client, workspace, name="../../../../etc/passwd.png")
    assert response.status_code == 201
    assert "/" not in response.json()["filename"]
    assert ".." not in response.json()["filename"]


@pytest.mark.asyncio
async def test_files_are_scoped_to_their_workspace(client: AsyncClient, workspace: dict) -> None:
    """A file from one workspace must not be readable from another."""
    attachment = (await _upload(client, workspace)).json()

    other = await client.post(
        "/api/v1/auth/register",
        json={
            "workspaceName": "Somebody Else",
            "name": "Eve",
            "email": "eve@elsewhere.example",
            "password": "correct-horse-battery",
        },
    )
    headers = {"Authorization": f"Bearer {other.json()['accessToken']}"}

    assert (
        await client.get(f"/api/v1/attachments/{attachment['id']}", headers=headers)
    ).status_code == 404
    mine = await client.get(
        f"/api/v1/attachments/{attachment['id']}", headers=workspace["headers"]
    )
    assert mine.status_code == 200
    assert mine.content == PNG


@pytest.mark.asyncio
async def test_downloads_are_not_rendered_in_our_origin(
    client: AsyncClient, workspace: dict
) -> None:
    """A document from a stranger must not run as a page."""
    document = await _upload(
        client, workspace, name="notes.pdf", ctype="application/pdf", data=b"%PDF-1.4 fake"
    )
    served = await client.get(
        f"/api/v1/attachments/{document.json()['id']}", headers=workspace["headers"]
    )
    assert served.headers["content-disposition"].startswith("attachment;")
    assert served.headers["x-content-type-options"] == "nosniff"
    assert "sandbox" in served.headers["content-security-policy"]

    image = await _upload(client, workspace)
    shown = await client.get(
        f"/api/v1/attachments/{image.json()['id']}", headers=workspace["headers"]
    )
    assert shown.headers["content-disposition"].startswith("inline;")


@pytest.mark.asyncio
async def test_a_customer_can_attach_a_file_in_the_widget(
    client: AsyncClient, workspace: dict
) -> None:
    key = workspace["workspace"]["publicKey"]
    uploaded = await client.post(
        f"/api/v1/widget/{key}/attachments",
        files={"file": ("receipt.png", io.BytesIO(PNG), "image/png")},
    )
    assert uploaded.status_code == 201, uploaded.text
    attachment = uploaded.json()
    assert attachment["sessionId"]

    sent = await client.post(
        f"/api/v1/widget/{key}/messages",
        json={
            "sessionId": attachment["sessionId"],
            "body": "Here is the receipt",
            "attachmentIds": [attachment["id"]],
        },
    )
    assert sent.status_code == 200, sent.text
    session_id = sent.json()["sessionId"]
    assert session_id == attachment["sessionId"]

    # The customer can read their own file back with their session id.
    theirs = await client.get(
        f"/api/v1/widget/{key}/sessions/{session_id}/attachments/{attachment['id']}"
    )
    assert theirs.status_code == 200

    # Somebody else's session id gets nothing.
    assert (
        await client.get(
            f"/api/v1/widget/{key}/sessions/web_not_yours/attachments/{attachment['id']}"
        )
    ).status_code == 404

    # And it shows in the agent inbox.
    history = await client.get(f"/api/v1/widget/{key}/sessions/{session_id}")
    assert any(m["attachments"] for m in history.json())


@pytest.mark.asyncio
async def test_a_file_cannot_be_stolen_by_guessing_its_id(
    client: AsyncClient, workspace: dict
) -> None:
    """Claiming is restricted to unclaimed files this caller uploaded."""
    key = workspace["workspace"]["publicKey"]
    attachment = (await _upload(client, workspace)).json()

    first = await client.post(f"/api/v1/widget/{key}/messages", json={"body": "One"})
    conversation_id = first.json()["conversationId"]
    await client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        headers=workspace["headers"],
        json={"body": "Mine", "attachmentIds": [attachment["id"]]},
    )
    again = await client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        headers=workspace["headers"],
        json={"body": "Trying again", "attachmentIds": [attachment["id"]]},
    )
    assert again.status_code == 422, again.text


def test_the_storage_layer_refuses_to_leave_its_directory() -> None:
    assert storage.absolute("../../../etc/passwd") is None
    assert storage.absolute("ws/2026/09/file.png") is not None


@pytest.mark.asyncio
async def test_a_signed_link_works_without_a_header(
    client: AsyncClient, workspace: dict
) -> None:
    """A browser cannot put an Authorization header on an img tag."""
    attachment = (await _upload(client, workspace)).json()
    # The url handed to the interface already carries its own permission.
    assert "?t=" in attachment["url"]

    served = await client.get(attachment["url"])
    assert served.status_code == 200
    assert served.content == PNG


@pytest.mark.asyncio
async def test_a_signed_link_is_scoped_to_one_file(
    client: AsyncClient, workspace: dict
) -> None:
    """Otherwise one link would open every file in the workspace."""
    first = (await _upload(client, workspace, name="one.png")).json()
    second = (await _upload(client, workspace, name="two.png")).json()
    token = first["url"].split("?t=")[1]

    assert (await client.get(f"/api/v1/attachments/{second['id']}?t={token}")).status_code == 401
    assert (await client.get(f"/api/v1/attachments/{first['id']}?t={token}")).status_code == 200


@pytest.mark.asyncio
async def test_an_expired_or_tampered_link_is_refused(
    client: AsyncClient, workspace: dict
) -> None:
    from app.security import sign_download

    attachment = (await _upload(client, workspace)).json()
    good = sign_download(attachment["id"])

    assert (await client.get(f"/api/v1/attachments/{attachment['id']}?t=nonsense")).status_code == 401
    tampered = good[:-4] + "AAAA"
    assert (
        await client.get(f"/api/v1/attachments/{attachment['id']}?t={tampered}")
    ).status_code == 401

    expired = "1000000000.abcdef"
    assert (
        await client.get(f"/api/v1/attachments/{attachment['id']}?t={expired}")
    ).status_code == 401


@pytest.mark.asyncio
async def test_no_link_and_no_header_is_refused(client: AsyncClient, workspace: dict) -> None:
    attachment = (await _upload(client, workspace)).json()
    assert (await client.get(f"/api/v1/attachments/{attachment['id']}")).status_code == 401
