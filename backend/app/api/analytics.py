"""Operational analytics, computed from live rows rather than a warehouse."""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Sequence
from datetime import timedelta
from statistics import median
from typing import Optional

from fastapi import APIRouter, Query
from sqlalchemy import select

from ..db import utcnow
from ..models import Conversation, Ticket, User
from ..schemas import AnalyticsSummary, MetricPoint
from ..security import CurrentUser, DbDep

router = APIRouter(prefix="/analytics", tags=["analytics"])

OPEN_STATES = ("new", "open", "pending", "on_hold")


def _pct_change(current: float, previous: float) -> float:
    """Percentage change, guarding the divide by zero at a cold start."""
    if previous == 0:
        return 0.0 if current == 0 else 100.0
    return round((current - previous) / previous * 100, 1)


@router.get("/summary", response_model=AnalyticsSummary)
async def summary(
    user: CurrentUser,
    db: DbDep,
    range_days: int = Query(default=30, alias="rangeDays", ge=1, le=365),
) -> AnalyticsSummary:
    now = utcnow()
    window_start = now - timedelta(days=range_days)
    # The immediately preceding window of the same length, for the deltas.
    previous_start = window_start - timedelta(days=range_days)

    tickets: Sequence[Ticket] = list(
        (
            await db.execute(select(Ticket).where(Ticket.workspace_id == user.workspace_id))
        ).scalars()
    )
    current = [t for t in tickets if t.created_at >= window_start]
    previous = [t for t in tickets if previous_start <= t.created_at < window_start]

    open_now = [t for t in tickets if t.status in OPEN_STATES]
    open_then = _open_at(tickets, window_start)

    at_risk = [
        t
        for t in open_now
        if t.sla_due_at is not None and t.first_response_at is None and t.sla_due_at <= now + timedelta(hours=2)
    ]

    series = _build_series(tickets, window_start, range_days)

    return AnalyticsSummary(
        range_days=range_days,
        open_tickets=len(open_now),
        open_delta=_pct_change(len(open_now), open_then),
        sla_at_risk=len(at_risk),
        ai_deflection=_deflection(current),
        ai_deflection_delta=round(_deflection(current) - _deflection(previous), 1),
        csat=_csat(current),
        csat_delta=round(_csat(current) - _csat(previous), 1),
        median_first_response_minutes=_median_first_response(current),
        series=series,
        channel_mix=_mix(current, lambda t: t.channel),
        priority_mix=_mix(current, lambda t: t.priority),
        open_priority_mix=_mix(open_now, lambda t: t.priority),
        top_categories=_mix(current, lambda t: t.category or "Uncategorised")[:6],
        agent_leaderboard=await _leaderboard(db, user.workspace_id, current),
    )


def _open_at(tickets: Sequence[Ticket], moment) -> int:
    """How many tickets were open at `moment`."""
    return sum(
        1
        for ticket in tickets
        if ticket.created_at <= moment and (ticket.resolved_at is None or ticket.resolved_at > moment)
    )


def _deflection(tickets: Sequence[Ticket]) -> float:
    """Share of tickets the AI resolved without a human reply."""
    if not tickets:
        return 0.0
    handled = sum(1 for t in tickets if t.ai_handled and t.status in ("solved", "closed"))
    return round(handled / len(tickets) * 100, 1)


def _csat(tickets: Sequence[Ticket]) -> float:
    """Average rating as a percentage of the 5 point scale."""
    rated = [t.satisfaction for t in tickets if t.satisfaction]
    if not rated:
        return 0.0
    return round(sum(rated) / len(rated) / 5 * 100, 1)


def _median_first_response(tickets: Sequence[Ticket]) -> Optional[float]:
    deltas = [
        (t.first_response_at - t.created_at).total_seconds() / 60
        for t in tickets
        if t.first_response_at is not None and t.first_response_at >= t.created_at
    ]
    return round(median(deltas), 1) if deltas else None


def _build_series(tickets: Sequence[Ticket], start, days: int) -> list[MetricPoint]:
    created: Counter[str] = Counter()
    resolved: Counter[str] = Counter()
    for ticket in tickets:
        if ticket.created_at >= start:
            created[ticket.created_at.date().isoformat()] += 1
        if ticket.resolved_at is not None and ticket.resolved_at >= start:
            resolved[ticket.resolved_at.date().isoformat()] += 1

    points: list[MetricPoint] = []
    last = (start + timedelta(days=days)).date()
    day = start.date()
    while day <= last:
        key = day.isoformat()
        points.append(MetricPoint(date=key, created=created.get(key, 0), resolved=resolved.get(key, 0)))
        day += timedelta(days=1)
    return points


def _mix(tickets: Sequence[Ticket], key) -> list[dict]:
    counts = Counter(key(ticket) for ticket in tickets)
    total = sum(counts.values()) or 1
    return [
        {"label": label, "value": value, "share": round(value / total * 100, 1)}
        for label, value in counts.most_common()
    ]


async def _leaderboard(db, workspace_id: str, tickets: Sequence[Ticket]) -> list[dict]:
    """Per agent solved counts, response times and CSAT over the window."""
    members = {
        member.id: member.name
        for member in (
            await db.execute(select(User).where(User.workspace_id == workspace_id))
        ).scalars()
    }
    solved: Counter[str] = Counter()
    responses: dict[str, list[float]] = defaultdict(list)
    ratings: dict[str, list[int]] = defaultdict(list)

    for ticket in tickets:
        agent_id = ticket.assigned_user_id
        if not agent_id or agent_id not in members:
            continue
        if ticket.status in ("solved", "closed"):
            solved[agent_id] += 1
        if ticket.first_response_at and ticket.first_response_at >= ticket.created_at:
            responses[agent_id].append(
                (ticket.first_response_at - ticket.created_at).total_seconds() / 60
            )
        if ticket.satisfaction:
            ratings[agent_id].append(ticket.satisfaction)

    rows = []
    for agent_id, name in members.items():
        if not (solved[agent_id] or responses[agent_id]):
            continue
        rows.append(
            {
                "userId": agent_id,
                "name": name,
                "solved": solved[agent_id],
                "medianFirstResponseMinutes": round(median(responses[agent_id]), 1)
                if responses[agent_id]
                else None,
                "csat": round(sum(ratings[agent_id]) / len(ratings[agent_id]) / 5 * 100, 1)
                if ratings[agent_id]
                else None,
            }
        )
    rows.sort(key=lambda row: row["solved"], reverse=True)
    return rows[:8]


@router.get("/workload")
async def workload(user: CurrentUser, db: DbDep) -> dict:
    """Live queue depth, what the team is sitting on right now."""
    conversations = list(
        (
            await db.execute(
                select(Conversation).where(Conversation.workspace_id == user.workspace_id)
            )
        ).scalars()
    )
    by_channel = Counter(c.channel for c in conversations if c.status in ("open", "escalated"))
    return {
        "openConversations": sum(1 for c in conversations if c.status == "open"),
        "escalated": sum(1 for c in conversations if c.status == "escalated"),
        "unassigned": sum(
            1 for c in conversations if c.assigned_user_id is None and c.status != "resolved"
        ),
        "byChannel": [{"label": label, "value": value} for label, value in by_channel.most_common()],
    }
