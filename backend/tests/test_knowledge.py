"""Knowledge base CRUD, retrieval ranking and grounded drafting."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.ai.assist import parse_suggestions, wants_human
from app.ai.retrieval import bm25_scores, cosine, tokenize

ARTICLES = [
    {
        "title": "Returns and exchanges",
        "body": "Unused gear can be returned within 60 days of delivery for a full refund. "
        "Worn gear is eligible for exchange or store credit within the same window.",
        "category": "Orders",
        "status": "published",
        "tags": ["returns", "refund"],
    },
    {
        "title": "Shipping times",
        "body": "Standard ground shipping is free over 75 dollars and arrives in 3 to 5 business days. "
        "Express shipping arrives in 2 business days.",
        "category": "Orders",
        "status": "published",
        "tags": ["shipping"],
    },
    {
        "title": "Internal escalation policy",
        "body": "Escalate refund disputes over 300 dollars to a supervisor immediately.",
        "category": "Internal",
        "status": "published",
        "visibility": "internal",
        "tags": ["internal"],
    },
]


def test_tokenizer_drops_stopwords() -> None:
    assert tokenize("How do I return the jacket?") == ["return", "jacket"]


def test_bm25_ranks_the_relevant_document_first() -> None:
    docs = [
        "returns and exchanges unused gear 60 days refund",
        "shipping times ground express business days",
    ]
    scores = bm25_scores("refund for an unused jacket", docs)
    assert scores[0] > scores[1]


def test_bm25_is_empty_for_an_empty_query() -> None:
    assert bm25_scores("", ["anything"]) == [0.0]
    assert bm25_scores("refund", []) == []


def test_excerpt_starts_at_a_sentence() -> None:
    """Excerpts get quoted to customers, so they must not begin mid sentence."""
    from app.ai.retrieval import _window

    body = (
        "You can return unused gear within 60 days of delivery for a full refund. "
        "Refunds are issued within 5 business days of the item reaching our warehouse. "
        "Worn gear can be exchanged within the same window."
    )
    # An offset landing inside the second sentence should back up to its start.
    excerpt = _window(body, 90, 120)
    assert excerpt.startswith("...Refunds are issued")
    assert "  " not in excerpt

    # From the very beginning there is nothing to trim.
    opening = _window(body, 0, 40)
    assert opening.startswith("You can return")
    assert opening.endswith("...")


def test_excerpt_ends_at_a_sentence() -> None:
    """An answer that stops on a dangling clause reads worse than a shorter one."""
    from app.ai.retrieval import _window

    body = (
        "You can return unused gear within 60 days of delivery for a full refund. "
        "Refunds are issued within 5 business days of the item reaching our warehouse. "
        "Manufacturing defects are covered for 12 months, however normal wear is not."
    )
    # A window that would otherwise stop inside the last clause backs up.
    excerpt = _window(body, 0, 200)
    assert excerpt.endswith("warehouse.")
    assert "however" not in excerpt

    # A window covering the whole article keeps it and adds no ellipsis.
    whole = _window(body, 0, len(body) + 50)
    assert whole == body
    assert not whole.endswith("...")


def test_excerpt_never_splits_a_word() -> None:
    body = "alpha bravo charlie delta echo foxtrot golf hotel india juliett kilo lima"
    excerpt = _window_words(body)
    for word in excerpt.replace("...", " ").split():
        assert word in body.split(), word


def _window_words(body: str) -> str:
    from app.ai.retrieval import _window

    return _window(body, 17, 30)


def test_cosine_handles_degenerate_vectors() -> None:
    assert cosine([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)
    assert cosine([], [1.0]) == 0.0
    assert cosine([0.0, 0.0], [1.0, 1.0]) == 0.0


def test_escalation_phrases_are_detected() -> None:
    assert wants_human("I want to speak to a human right now")
    assert wants_human("Put me through to your manager")
    assert not wants_human("When does my order ship?")


def test_suggestion_parsing() -> None:
    parsed = parse_suggestions(
        "ANSWER: Returns are 60 days.\nWARNING: Do not promise a date.\nACTION: Ask for the order number."
    )
    assert [item["kind"] for item in parsed] == ["answer", "warning", "action"]
    assert parsed[0]["text"] == "Returns are 60 days."


def test_suggestion_parsing_tolerates_untagged_output() -> None:
    parsed = parse_suggestions("Just say the returns window is 60 days.")
    assert parsed[0]["kind"] == "answer"
    assert parse_suggestions("") == []


async def _seed_articles(client: AsyncClient, workspace: dict) -> None:
    for article in ARTICLES:
        response = await client.post(
            "/api/v1/knowledge", headers=workspace["headers"], json=article
        )
        assert response.status_code == 201, response.text


@pytest.mark.asyncio
async def test_article_crud(client: AsyncClient, workspace: dict) -> None:
    created = await client.post(
        "/api/v1/knowledge",
        headers=workspace["headers"],
        json={"title": "Draft article", "body": "Body text", "status": "draft"},
    )
    assert created.status_code == 201
    article_id = created.json()["id"]
    assert created.json()["version"] == 1

    patched = await client.patch(
        f"/api/v1/knowledge/{article_id}",
        headers=workspace["headers"],
        json={"body": "Revised body", "status": "published"},
    )
    # Editing content bumps the version so the change is visible in the UI.
    assert patched.json()["version"] == 2
    assert patched.json()["status"] == "published"

    assert (
        await client.delete(f"/api/v1/knowledge/{article_id}", headers=workspace["headers"])
    ).status_code == 204
    assert (
        await client.get(f"/api/v1/knowledge/{article_id}", headers=workspace["headers"])
    ).status_code == 404


@pytest.mark.asyncio
async def test_search_ranks_by_relevance(client: AsyncClient, workspace: dict) -> None:
    await _seed_articles(client, workspace)
    response = await client.get(
        "/api/v1/knowledge/search", headers=workspace["headers"], params={"q": "refund unused jacket"}
    )
    assert response.status_code == 200
    hits = response.json()
    assert hits, "expected at least one hit"
    assert hits[0]["title"] == "Returns and exchanges"
    assert hits[0]["excerpt"]


@pytest.mark.asyncio
async def test_search_route_is_not_shadowed_by_the_id_route(
    client: AsyncClient, workspace: dict
) -> None:
    """The search route must not be read as a request for an article by id."""
    response = await client.get(
        "/api/v1/knowledge/search", headers=workspace["headers"], params={"q": "anything"}
    )
    assert response.status_code == 200
    assert isinstance(response.json(), list)


@pytest.mark.asyncio
async def test_draft_is_grounded_and_cites_sources(client: AsyncClient, workspace: dict) -> None:
    """With no LLM configured, drafting still answers from the knowledge base."""
    await _seed_articles(client, workspace)
    response = await client.post(
        "/api/v1/conversations/draft",
        headers=workspace["headers"],
        json={"question": "Can I get a refund on unused gear?"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["engine"] == "grounded-fallback"
    assert "Returns and exchanges" in body["text"]
    assert body["citations"][0]["title"] == "Returns and exchanges"
    assert 0 < body["confidence"] <= 0.6


@pytest.mark.asyncio
async def test_draft_escalates_when_nothing_matches(client: AsyncClient, workspace: dict) -> None:
    await _seed_articles(client, workspace)
    response = await client.post(
        "/api/v1/conversations/draft",
        headers=workspace["headers"],
        json={"question": "Do you sponsor competitive underwater basket weaving teams?"},
    )
    body = response.json()
    assert body["shouldEscalate"] is True
    assert body["citations"] == []


@pytest.mark.asyncio
async def test_categories_are_deduplicated(client: AsyncClient, workspace: dict) -> None:
    await _seed_articles(client, workspace)
    categories = (
        await client.get("/api/v1/knowledge/categories", headers=workspace["headers"])
    ).json()
    assert categories == ["Internal", "Orders"]


@pytest.mark.asyncio
async def test_coverage_is_absolute_not_relative(client: AsyncClient, workspace: dict) -> None:
    """Confidence has to mean something, or escalation can never fire."""
    from sqlalchemy import select

    from app.ai import retrieval
    from app.db import async_session_maker
    from app.models import Workspace

    for title, body in [
        ("Returns and exchanges", "Unused gear can be returned within 60 days for a full refund."),
        ("Shipping times", "Express delivery arrives in two business days for a flat fee."),
        ("Warranty", "Manufacturing defects are covered for twelve months from delivery."),
    ]:
        created = await client.post(
            "/api/v1/knowledge",
            headers=workspace["headers"],
            json={"title": title, "body": body, "status": "published"},
        )
        assert created.status_code == 201

    async with async_session_maker() as db:
        ws = await db.scalar(
            select(Workspace).where(Workspace.id == workspace["workspace"]["id"])
        )
        strong = await retrieval.search(db, ws.id, "how long is the warranty on defects")
        weak = await retrieval.search(db, ws.id, "can I get a mortgage")

        assert strong, "a covered question must retrieve something"
        # Both would report a ranking score of 1.0, which is the whole problem.
        assert strong[0].score == 1.0
        assert strong[0].coverage > 0.4
        assert not weak, "nothing in the base answers this, so it must return nothing"


@pytest.mark.asyncio
async def test_a_small_knowledge_base_still_answers(
    client: AsyncClient, workspace: dict
) -> None:
    """A new install has a handful of articles, and it has to work then too."""
    from sqlalchemy import select

    from app.ai import retrieval
    from app.db import async_session_maker
    from app.models import Workspace

    created = await client.post(
        "/api/v1/knowledge",
        headers=workspace["headers"],
        json={
            "title": "Returns and exchanges",
            "body": "Unused gear can be returned within 60 days of delivery for a full refund.",
            "status": "published",
        },
    )
    assert created.status_code == 201

    async with async_session_maker() as db:
        ws = await db.scalar(
            select(Workspace).where(Workspace.id == workspace["workspace"]["id"])
        )
        hits = await retrieval.search(db, ws.id, "I want to return an unused jacket")
        assert hits, "one article is still a knowledge base"
        assert hits[0].coverage > 0.15


@pytest.mark.asyncio
async def test_a_question_matches_an_article_in_a_different_tense(
    client: AsyncClient, workspace: dict
) -> None:
    """The most common support question there is, and it used to score zero."""
    from sqlalchemy import select

    from app.ai import retrieval
    from app.db import async_session_maker
    from app.models import Workspace

    await client.post(
        "/api/v1/knowledge",
        headers=workspace["headers"],
        json={
            "title": "Returns and exchanges",
            "body": "Unused gear can be returned within 60 days of delivery for a full refund.",
            "status": "published",
        },
    )

    async with async_session_maker() as db:
        ws = await db.scalar(
            select(Workspace).where(Workspace.id == workspace["workspace"]["id"])
        )
        hits = await retrieval.search(db, ws.id, "how long do I have to return something")
        assert hits, "a question about returns found nothing in an article about returns"
        assert hits[0].coverage > 0.25


def test_the_stemmer_agrees_with_itself() -> None:
    """It does not have to be linguistically right, it has to be consistent."""
    from app.ai.retrieval import stem

    for first, second in [
        ("return", "returned"), ("return", "returns"), ("ship", "shipping"),
        ("ship", "shipped"), ("cancel", "cancelled"), ("policy", "policies"),
        ("exchange", "exchanges"), ("box", "boxes"), ("watch", "watches"),
        ("arrive", "arrived"), ("warranty", "warranties"), ("address", "addresses"),
    ]:
        assert stem(first) == stem(second), f"{first} and {second} should match"

    for word in ("bed", "gas", "was", "its", "box", "yes", "less"):
        assert stem(word) == word, word
