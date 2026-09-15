"""Seed the sample workspace from fixtures/demo.json."""

from __future__ import annotations

import json
import logging
from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import BACKEND_DIR
from .db import async_session_maker, utcnow
from .models import (
    Article,
    Conversation,
    Customer,
    Macro,
    Message,
    RoutingRule,
    SlaPolicy,
    TapSession,
    Ticket,
    User,
    Workspace,
    new_id,
)
from .security import hash_password

logger = logging.getLogger(__name__)

FIXTURE_PATH = BACKEND_DIR.parent / "fixtures" / "demo.json"


class _Random:
    """A tiny linear congruential generator."""

    def __init__(self, seed: int = 20240917) -> None:
        self._state = seed

    def next(self) -> float:
        self._state = (self._state * 1103515245 + 12345) % 2147483648
        return self._state / 2147483648

    def below(self, upper: int) -> int:
        return int(self.next() * upper)

    def between(self, low: int, high: int) -> int:
        return low + self.below(high - low + 1)

    def pick(self, items: list) -> Any:
        return items[self.below(len(items))]

    def weighted(self, items: list, weights: list[int]) -> Any:
        total = sum(weights)
        target = self.next() * total
        cumulative = 0.0
        for item, weight in zip(items, weights, strict=True):
            cumulative += weight
            if target <= cumulative:
                return item
        return items[-1]


def load_fixture() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


async def seed_if_empty() -> bool:
    """Populate the demo workspace unless the database already has one."""
    if not FIXTURE_PATH.exists():
        logger.warning("Demo fixture missing at %s, skipping seed", FIXTURE_PATH)
        return False

    async with async_session_maker() as db:
        if await db.scalar(select(Workspace.id).limit(1)):
            return False
        await seed(db, load_fixture())
        await db.commit()
    logger.info("Seeded demo workspace from %s", FIXTURE_PATH.name)
    return True


async def demo_data_present() -> bool:
    """Whether this database holds the demo workspace from the fixture."""
    if not FIXTURE_PATH.exists():
        return False
    slug = load_fixture()["workspace"].get("slug")
    async with async_session_maker() as db:
        return bool(await db.scalar(select(Workspace.id).where(Workspace.slug == slug)))


async def install_state() -> dict[str, bool]:
    """What is actually in this database, rather than what was asked for."""
    slug = load_fixture()["workspace"].get("slug") if FIXTURE_PATH.exists() else None
    async with async_session_maker() as db:
        has_workspace = bool(await db.scalar(select(Workspace.id).limit(1)))
        demo = bool(
            slug and await db.scalar(select(Workspace.id).where(Workspace.slug == slug))
        )
    return {"demoData": demo, "configured": has_workspace}


async def seed(db: AsyncSession, fixture: dict) -> Workspace:
    """Insert the whole fixture. This assumes an empty database."""
    now = utcnow()
    rng = _Random()

    spec = fixture["workspace"]
    workspace = Workspace(
        name=spec["name"],
        slug=spec["slug"],
        accent_color=spec.get("accentColor", "#2563EB"),
        settings=_snake_settings(spec.get("settings", {})),
    )
    db.add(workspace)
    await db.flush()

    users: dict[str, User] = {}
    for entry in fixture.get("users", []):
        user = User(
            workspace_id=workspace.id,
            name=entry["name"],
            email=entry["email"].lower(),
            password_hash=hash_password(entry["password"]),
            role=entry["role"],
        )
        db.add(user)
        users[entry["key"]] = user
    await db.flush()

    customers: dict[str, Customer] = {}
    for entry in fixture.get("customers", []):
        customer = Customer(
            workspace_id=workspace.id,
            name=entry.get("name"),
            email=(entry.get("email") or "").lower() or None,
            phone=entry.get("phone"),
            company=entry.get("company") or None,
            channel_ids=entry.get("channelIds", {}),
            last_seen_at=now - timedelta(hours=rng.between(1, 96)),
        )
        db.add(customer)
        customers[entry["key"]] = customer
    await db.flush()

    articles: dict[str, Article] = {}
    for entry in fixture.get("articles", []):
        article = Article(
            workspace_id=workspace.id,
            title=entry["title"],
            body=entry["body"],
            summary=entry.get("summary"),
            category=entry.get("category", "General"),
            tags=entry.get("tags", []),
            status=entry.get("status", "published"),
            visibility=entry.get("visibility", "public"),
            author_name=entry.get("author", "Priya Raman"),
            version=entry.get("version", 1),
            created_at=now - timedelta(days=rng.between(30, 200)),
            updated_at=now - timedelta(days=rng.between(1, 29)),
        )
        db.add(article)
        articles[entry["key"]] = article

    for entry in fixture.get("macros", []):
        db.add(Macro(workspace_id=workspace.id, name=entry["name"], body=entry["body"], tags=entry.get("tags", [])))

    for entry in fixture.get("slaPolicies", []):
        db.add(
            SlaPolicy(
                workspace_id=workspace.id,
                name=entry["name"],
                priorities=entry["priorities"],
                first_response_minutes=entry["firstResponseMinutes"],
                resolution_minutes=entry["resolutionMinutes"],
                is_active=entry.get("isActive", True),
            )
        )

    for entry in fixture.get("routingRules", []):
        db.add(
            RoutingRule(
                workspace_id=workspace.id,
                name=entry["name"],
                order_index=entry.get("orderIndex", 0),
                is_active=entry.get("isActive", True),
                conditions=entry.get("conditions", {}),
                actions=entry.get("actions", {}),
            )
        )
    await db.flush()

    ticket_number = await _seed_conversations(db, workspace, fixture, users, customers, articles, now, rng)
    await _seed_history(db, workspace, fixture, users, customers, now, rng, ticket_number)
    await _seed_tap(db, workspace, fixture, users, articles, now)
    await db.flush()
    return workspace


async def _seed_conversations(
    db: AsyncSession,
    workspace: Workspace,
    fixture: dict,
    users: dict[str, User],
    customers: dict[str, Customer],
    articles: dict[str, Article],
    now,
    rng: _Random,
) -> int:
    """Create the handwritten threads, each with the ticket it opened."""
    number = 1
    for entry in fixture.get("conversations", []):
        customer = customers.get(entry["customer"])
        started = now - timedelta(hours=entry.get("startedHoursAgo", 4))
        assignee = users.get(entry.get("assignee") or "")

        conversation = Conversation(
            workspace_id=workspace.id,
            customer_id=customer.id if customer else None,
            channel=entry["channel"],
            channel_thread_id=_thread_id(entry["channel"], customer),
            subject=entry["subject"],
            status=entry["status"],
            assigned_user_id=assignee.id if assignee else None,
            created_at=started,
            last_message_at=started,
        )
        db.add(conversation)
        await db.flush()

        ai_turns = 0
        first_response_at = None
        for raw in entry.get("messages", []):
            at = now - timedelta(hours=float(raw.get("hoursAgo", 0)))
            author_type = raw["author"]
            meta: dict[str, Any] = {"channel": entry["channel"]}
            if raw.get("confidence") is not None:
                meta["confidence"] = raw["confidence"]
                meta["engine"] = "demo"
            if raw.get("cites"):
                meta["citations"] = [
                    {
                        "articleId": articles[key].id,
                        "title": articles[key].title,
                        "excerpt": (articles[key].summary or articles[key].body)[:200],
                    }
                    for key in raw["cites"]
                    if key in articles
                ]
            if author_type == "ai":
                ai_turns += 1
            if author_type in ("ai", "agent") and first_response_at is None and not raw.get("private"):
                first_response_at = at

            db.add(
                Message(
                    conversation_id=conversation.id,
                    workspace_id=workspace.id,
                    author_type=author_type,
                    author_name=raw.get("name") or _default_author(author_type, customer),
                    author_user_id=assignee.id if author_type == "agent" and assignee else None,
                    body=raw["body"],
                    is_private=bool(raw.get("private")),
                    meta=meta,
                    created_at=at,
                )
            )
            conversation.last_message_at = max(conversation.last_message_at, at)

        conversation.ai_turns = ai_turns
        conversation.ai_handled = ai_turns > 0

        resolved = entry["status"] == "resolved"
        ticket = Ticket(
            workspace_id=workspace.id,
            number=number,
            subject=entry["subject"],
            description=next((m["body"] for m in entry.get("messages", []) if m["author"] == "customer"), ""),
            customer_id=customer.id if customer else None,
            status="solved" if resolved else ("open" if entry["status"] != "pending" else "pending"),
            priority=entry.get("priority", "medium"),
            channel=entry["channel"],
            category=entry.get("category"),
            tags=entry.get("tags", []),
            assigned_user_id=assignee.id if assignee else None,
            ai_handled=ai_turns > 0,
            ai_confidence=next(
                (m["confidence"] for m in reversed(entry.get("messages", [])) if m.get("confidence")), None
            ),
            first_response_at=first_response_at,
            sla_due_at=started + timedelta(minutes=_sla_minutes(entry.get("priority", "medium"))),
            resolved_at=conversation.last_message_at if resolved else None,
            satisfaction=rng.between(4, 5) if resolved else None,
            created_at=started,
            updated_at=conversation.last_message_at,
        )
        db.add(ticket)
        await db.flush()
        conversation.ticket_id = ticket.id
        number += 1

    await db.flush()
    return number


async def _seed_history(
    db: AsyncSession,
    workspace: Workspace,
    fixture: dict,
    users: dict[str, User],
    customers: dict[str, Customer],
    now,
    rng: _Random,
    start_number: int,
) -> None:
    """Backfill closed tickets so the analytics charts have real history."""
    spec = fixture.get("historicalTickets")
    if not spec:
        return

    agents = [user for key, user in users.items() if key != "owner"]
    customer_list = list(customers.values())
    number = start_number

    for day_offset in range(spec["days"], 0, -1):
        # Weekends are quieter, which is what makes the trend line look real.
        day = now - timedelta(days=day_offset)
        weekday = day.weekday()
        volume = rng.between(spec["perDayMin"], spec["perDayMax"])
        if weekday >= 5:
            volume = max(1, volume // 2)

        for _ in range(volume):
            created = day + timedelta(hours=rng.between(7, 19), minutes=rng.below(60))
            priority = rng.weighted(spec["priorities"], spec["priorityWeights"])
            channel = rng.weighted(spec["channels"], spec["channelWeights"])
            agent = rng.pick(agents) if agents else None
            ai_handled = rng.next() < spec["aiHandledRate"]
            awaiting = day_offset <= 7 and rng.next() < 0.22
            resolved = False if awaiting else rng.next() < spec["resolveRate"]

            sla_minutes = _sla_minutes(priority)
            first_response = None if awaiting else created + timedelta(minutes=rng.between(2, 180))
            resolved_at = (
                first_response + timedelta(minutes=rng.between(20, 2400))
                if resolved and first_response
                else None
            )

            db.add(
                Ticket(
                    workspace_id=workspace.id,
                    number=number,
                    subject=rng.pick(spec["subjects"]),
                    description="",
                    customer_id=rng.pick(customer_list).id if customer_list else None,
                    status="solved" if resolved else ("new" if awaiting else rng.pick(["open", "pending"])),
                    priority=priority,
                    channel=channel,
                    category=rng.pick(spec["categories"]),
                    tags=[],
                    assigned_user_id=agent.id if agent else None,
                    ai_handled=ai_handled,
                    ai_confidence=round(0.5 + rng.next() * 0.45, 2) if ai_handled else None,
                    first_response_at=first_response,
                    sla_due_at=created + timedelta(minutes=sla_minutes),
                    sla_breached=bool(
                        first_response
                        and (first_response - created).total_seconds() / 60 > sla_minutes
                    ),
                    resolved_at=resolved_at,
                    satisfaction=rng.between(3, 5) if resolved and rng.next() < spec["ratedRate"] else None,
                    created_at=created,
                    updated_at=resolved_at or first_response or created,
                )
            )
            number += 1


async def _seed_tap(
    db: AsyncSession,
    workspace: Workspace,
    fixture: dict,
    users: dict[str, User],
    articles: dict[str, Article],
    now,
) -> None:
    """Recreate a finished Tap AI call, transcript and suggestions intact."""
    agent = users.get("agent3") or next(iter(users.values()), None)
    for entry in fixture.get("tapSessions", []):
        started = now - timedelta(hours=entry.get("startedHoursAgo", 6))
        step = timedelta(seconds=45)

        transcript = [
            {
                "id": new_id(),
                "speaker": line["speaker"],
                "text": line["text"],
                "at": (started + step * index).isoformat() + "Z",
            }
            for index, line in enumerate(entry.get("transcript", []))
        ]
        suggestions = [
            {
                "id": new_id(),
                "kind": item["kind"],
                "text": item["text"],
                "confidence": item["confidence"],
                "engine": "demo",
                "citations": [
                    {
                        "articleId": articles[key].id,
                        "title": articles[key].title,
                        "excerpt": (articles[key].summary or articles[key].body)[:200],
                    }
                    for key in item.get("cites", [])
                    if key in articles
                ],
                "at": (started + step * (index + 1)).isoformat() + "Z",
            }
            for index, item in enumerate(entry.get("suggestions", []))
        ]

        db.add(
            TapSession(
                workspace_id=workspace.id,
                user_id=agent.id if agent else None,
                customer_label=entry["customerLabel"],
                status=entry.get("status", "ended"),
                transcript=transcript,
                suggestions=suggestions,
                summary=entry.get("summary"),
                created_at=started,
                ended_at=started + timedelta(minutes=entry.get("durationMinutes", 10)),
            )
        )


_SLA_MINUTES = {"urgent": 15, "high": 60, "medium": 240, "low": 240}


def _sla_minutes(priority: str) -> int:
    return _SLA_MINUTES.get(priority, 240)


def _thread_id(channel: str, customer: Customer | None) -> str:
    if customer is None:
        return new_id()
    ids = customer.channel_ids or {}
    return ids.get(channel) or customer.email or customer.phone or new_id()


def _default_author(author_type: str, customer: Customer | None) -> str:
    if author_type == "customer":
        return (customer.name if customer else None) or "Customer"
    if author_type == "ai":
        return "AI Assistant"
    if author_type == "system":
        return "System"
    return "Agent"


def _snake_settings(settings: dict) -> dict:
    """The fixture is camelCase for the frontend, workspace settings are snake."""
    mapping = {
        "greeting": "greeting",
        "brandVoice": "brand_voice",
        "fallbackMessage": "fallback_message",
        "instructions": "instructions",
        "aiAutoreply": "ai_autoreply",
        "aiSuggestThreshold": "ai_suggest_threshold",
        "aiAutoresolveThreshold": "ai_autoresolve_threshold",
        "escalateAfterAiTurns": "escalate_after_ai_turns",
        "businessHours": "business_hours",
    }
    return {mapping.get(key, key): value for key, value in settings.items()}
