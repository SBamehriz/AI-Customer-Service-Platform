"""Flat tables for reporting."""

from __future__ import annotations

import csv
import io

import pytest
from httpx import AsyncClient

from app.datasets import DATASETS


def _rows(text: str) -> list[dict]:
    return list(csv.DictReader(io.StringIO(text)))


@pytest.mark.asyncio
async def test_every_dataset_downloads_as_csv(client: AsyncClient, workspace: dict) -> None:
    key = workspace["workspace"]["publicKey"]
    await client.post(f"/api/v1/widget/{key}/messages", json={"body": "Where is my order"})

    listed = await client.get("/api/v1/workspace/datasets", headers=workspace["headers"])
    assert {d["name"] for d in listed.json()["datasets"]} == set(DATASETS)

    for name in DATASETS:
        response = await client.get(
            f"/api/v1/workspace/datasets/{name}.csv", headers=workspace["headers"]
        )
        assert response.status_code == 200, f"{name}: {response.text}"
        assert response.headers["content-type"].startswith("text/csv")
        assert f"{name}-" in response.headers["content-disposition"]
        # Even an empty table has to have its header row.
        assert response.text.strip(), name
        assert len(_rows(response.text)) >= 0


@pytest.mark.asyncio
async def test_the_ticket_table_has_the_numbers_people_report_on(
    client: AsyncClient, workspace: dict
) -> None:
    key = workspace["workspace"]["publicKey"]
    await client.post(f"/api/v1/widget/{key}/messages", json={"body": "My order is late"})

    response = await client.get(
        "/api/v1/workspace/datasets/tickets.csv", headers=workspace["headers"]
    )
    rows = _rows(response.text)
    assert rows, "a conversation should have opened a ticket"
    row = rows[0]
    for column in (
        "ticket_id", "status", "priority", "channel", "created_at",
        "minutes_to_first_response", "minutes_to_resolution", "sla_breached",
    ):
        assert column in row, column
    # Booleans are written as words a spreadsheet understands.
    assert row["sla_breached"] in ("true", "false")
    # Dates sort as text because they are ISO 8601.
    assert row["created_at"][4] == "-" and "T" in row["created_at"]


@pytest.mark.asyncio
async def test_no_dataset_carries_a_secret(client: AsyncClient, workspace: dict) -> None:
    """These files get emailed around, so they must not contain credentials."""
    await client.put(
        "/api/v1/workspace/ai",
        headers=workspace["headers"],
        json={"provider": "openai", "model": "gpt-4o-mini", "apiKey": "sk-never-in-a-csv"},
    )
    for name in DATASETS:
        response = await client.get(
            f"/api/v1/workspace/datasets/{name}.csv", headers=workspace["headers"]
        )
        assert "sk-never-in-a-csv" not in response.text
        assert "password" not in response.text.lower()


@pytest.mark.asyncio
async def test_an_unknown_dataset_says_what_is_available(
    client: AsyncClient, workspace: dict
) -> None:
    response = await client.get(
        "/api/v1/workspace/datasets/nonsense.csv", headers=workspace["headers"]
    )
    assert response.status_code == 404
    assert "customers" in response.json()["detail"]


@pytest.mark.asyncio
async def test_agents_cannot_download_the_datasets(
    client: AsyncClient, workspace: dict
) -> None:
    """Every customer record in one file is a supervisor thing."""
    await client.post(
        "/api/v1/workspace/team",
        headers=workspace["headers"],
        json={"name": "A", "email": "a@data.example", "password": "long-enough-pass",
              "role": "agent"},
    )
    session = await client.post(
        "/api/v1/auth/login", json={"email": "a@data.example", "password": "long-enough-pass"}
    )
    headers = {"Authorization": f"Bearer {session.json()['accessToken']}"}
    assert (
        await client.get("/api/v1/workspace/datasets/customers.csv", headers=headers)
    ).status_code == 403
