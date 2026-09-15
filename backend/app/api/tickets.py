"""Ticketing. The durable record behind every conversation."""

from __future__ import annotations

from typing import Annotated, Optional

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import String, cast, func, or_, select

from ..db import utcnow
from ..models import Customer, Ticket
from ..realtime import hub
from ..schemas import CustomerOut, TicketIn, TicketOut, TicketPatch
from ..security import CurrentUser, DbDep, Manager
from ..services import ingest

router = APIRouter(prefix="/tickets", tags=["tickets"])


def like_pattern(search: str) -> str:
    """A case insensitive contains pattern, with the wildcards made literal."""
    escaped = (
        search.lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    )
    return f"%{escaped}%"


def _to_out(ticket: Ticket) -> TicketOut:
    data = TicketOut.model_validate(ticket)
    if ticket.customer is not None:
        data.customer = CustomerOut.model_validate(ticket.customer)
    return data


@router.get("", response_model=list[TicketOut])
async def list_tickets(
    user: CurrentUser,
    db: DbDep,
    status_filter: Annotated[Optional[list[str]], Query(alias="status")] = None,
    priority: Annotated[Optional[list[str]], Query()] = None,
    channel: Optional[str] = None,
    assigned: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = Query(default=100, ge=1, le=500),
) -> list[TicketOut]:
    statement = (
        select(Ticket)
        .where(Ticket.workspace_id == user.workspace_id)
        .order_by(Ticket.created_at.desc())
        .limit(limit)
    )
    if status_filter:
        statement = statement.where(Ticket.status.in_(status_filter))
    if priority:
        statement = statement.where(Ticket.priority.in_(priority))
    if channel:
        statement = statement.where(Ticket.channel == channel)
    if assigned == "me":
        statement = statement.where(Ticket.assigned_user_id == user.id)
    elif assigned == "unassigned":
        statement = statement.where(Ticket.assigned_user_id.is_(None))
    elif assigned:
        statement = statement.where(Ticket.assigned_user_id == assigned)

    if search:
        needle = like_pattern(search)
        matching_customers = select(Customer.id).where(
            Customer.workspace_id == user.workspace_id,
            or_(
                func.lower(func.coalesce(Customer.name, "")).like(needle, escape="\\"),
                func.lower(func.coalesce(Customer.email, "")).like(needle, escape="\\"),
            ),
        )
        statement = statement.where(
            or_(
                func.lower(Ticket.subject).like(needle, escape="\\"),
                cast(Ticket.number, String).like(needle, escape="\\"),
                Ticket.customer_id.in_(matching_customers),
            )
        )

    tickets = list((await db.execute(statement)).scalars().unique())
    return [_to_out(ticket) for ticket in tickets]


@router.post("", response_model=TicketOut, status_code=status.HTTP_201_CREATED)
async def create_ticket(payload: TicketIn, user: CurrentUser, db: DbDep) -> TicketOut:
    assignee = await _assignee(db, user.workspace_id, payload.assigned_user_id)
    customer: Optional[Customer] = None
    if payload.customer_id:
        customer = await db.get(Customer, payload.customer_id)
        if customer is not None and customer.workspace_id != user.workspace_id:
            customer = None
    elif payload.customer_email:
        email = payload.customer_email.lower()
        customer = await db.scalar(
            select(Customer).where(
                Customer.workspace_id == user.workspace_id, Customer.email == email
            )
        )
        if customer is None:
            customer = Customer(
                workspace_id=user.workspace_id,
                name=payload.customer_name or email,
                email=email,
                last_seen_at=utcnow(),
            )
            db.add(customer)
            await db.flush()

    ticket = Ticket(
        workspace_id=user.workspace_id,
        number=await ingest.next_ticket_number(db, user.workspace_id),
        subject=payload.subject,
        description=payload.description,
        customer_id=customer.id if customer else None,
        status="new",
        priority=payload.priority,
        channel=payload.channel,
        category=payload.category,
        tags=payload.tags,
        assigned_user_id=assignee,
    )
    ticket.customer = customer
    db.add(ticket)
    await db.flush()
    await ingest.apply_sla(db, user.workspace_id, ticket)
    await db.flush()

    await hub.publish(user.workspace_id, "ticket.created", {"ticketId": ticket.id, "number": ticket.number})
    return _to_out(ticket)


@router.get("/{ticket_id}", response_model=TicketOut)
async def get_ticket(ticket_id: str, user: CurrentUser, db: DbDep) -> TicketOut:
    ticket = await db.get(Ticket, ticket_id)
    if ticket is None or ticket.workspace_id != user.workspace_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ticket not found")
    return _to_out(ticket)


@router.patch("/{ticket_id}", response_model=TicketOut)
async def update_ticket(
    ticket_id: str, payload: TicketPatch, user: CurrentUser, db: DbDep
) -> TicketOut:
    ticket = await db.get(Ticket, ticket_id)
    if ticket is None or ticket.workspace_id != user.workspace_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ticket not found")

    updates = payload.model_dump(exclude_unset=True)
    if "assigned_user_id" in updates:
        updates["assigned_user_id"] = await _assignee(
            db, user.workspace_id, updates["assigned_user_id"]
        )
    for field, value in updates.items():
        setattr(ticket, field, value)

    if updates.get("status") in ("solved", "closed") and ticket.resolved_at is None:
        ticket.resolved_at = utcnow()
    if updates.get("status") not in ("solved", "closed") and "status" in updates:
        ticket.resolved_at = None

    await db.flush()
    await hub.publish(user.workspace_id, "ticket.updated", {"ticketId": ticket.id, **updates})
    return _to_out(ticket)


async def _assignee(db, workspace_id: str, user_id: Optional[str]) -> Optional[str]:
    """Check an assignee before it is written, or say why it cannot be."""
    if not (user_id or "").strip():
        return None
    user_id = user_id.strip()
    eligible = await ingest.eligible_assignee(db, workspace_id, user_id)
    if eligible is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "That person is not someone in this workspace who can be assigned work.",
        )
    return eligible


@router.delete("/{ticket_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_ticket(ticket_id: str, user: Manager, db: DbDep) -> None:
    ticket = await db.get(Ticket, ticket_id)
    if ticket is None or ticket.workspace_id != user.workspace_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ticket not found")
    await db.delete(ticket)
