"""Customer records, one row per person, however many channels they use."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select

from ..db import utcnow
from ..models import Customer, Ticket
from ..schemas import CustomerIn, CustomerOut, TicketOut
from ..security import CurrentUser, DbDep
from .tickets import like_pattern

router = APIRouter(prefix="/customers", tags=["customers"])


async def _with_counts(db, customer: Customer) -> CustomerOut:
    """Attach ticket totals, which live on tickets rather than the customer row."""
    total = await db.scalar(
        select(func.count(Ticket.id)).where(Ticket.customer_id == customer.id)
    )
    open_count = await db.scalar(
        select(func.count(Ticket.id)).where(
            Ticket.customer_id == customer.id,
            Ticket.status.notin_(("solved", "closed")),
        )
    )
    data = CustomerOut.model_validate(customer)
    data.total_tickets = int(total or 0)
    data.open_tickets = int(open_count or 0)
    return data


@router.get("", response_model=list[CustomerOut])
async def list_customers(
    user: CurrentUser,
    db: DbDep,
    search: Optional[str] = None,
    limit: int = Query(default=100, ge=1, le=500),
) -> list[CustomerOut]:
    statement = (
        select(Customer)
        .where(Customer.workspace_id == user.workspace_id)
        .order_by(Customer.last_seen_at.desc())
        .limit(limit)
    )
    if search:
        pattern = like_pattern(search)
        statement = statement.where(
            func.lower(func.coalesce(Customer.name, "")).like(pattern, escape="\\")
            | func.lower(func.coalesce(Customer.email, "")).like(pattern, escape="\\")
            | func.lower(func.coalesce(Customer.company, "")).like(pattern, escape="\\")
        )
    customers = list((await db.execute(statement)).scalars())
    return [await _with_counts(db, customer) for customer in customers]


@router.post("", response_model=CustomerOut, status_code=status.HTTP_201_CREATED)
async def create_customer(payload: CustomerIn, user: CurrentUser, db: DbDep) -> CustomerOut:
    customer = Customer(
        workspace_id=user.workspace_id,
        name=payload.name,
        email=payload.email.lower() if payload.email else None,
        phone=payload.phone,
        company=payload.company,
        notes=payload.notes,
        channel_ids=payload.channel_ids,
        last_seen_at=utcnow(),
    )
    db.add(customer)
    await db.flush()
    return await _with_counts(db, customer)


@router.get("/{customer_id}", response_model=CustomerOut)
async def get_customer(customer_id: str, user: CurrentUser, db: DbDep) -> CustomerOut:
    customer = await db.get(Customer, customer_id)
    if customer is None or customer.workspace_id != user.workspace_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Customer not found")
    return await _with_counts(db, customer)


@router.patch("/{customer_id}", response_model=CustomerOut)
async def update_customer(
    customer_id: str, payload: CustomerIn, user: CurrentUser, db: DbDep
) -> CustomerOut:
    customer = await db.get(Customer, customer_id)
    if customer is None or customer.workspace_id != user.workspace_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Customer not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(customer, field, value.lower() if field == "email" and value else value)
    await db.flush()
    return await _with_counts(db, customer)


@router.get("/{customer_id}/tickets", response_model=list[TicketOut])
async def customer_tickets(customer_id: str, user: CurrentUser, db: DbDep) -> list[TicketOut]:
    customer = await db.get(Customer, customer_id)
    if customer is None or customer.workspace_id != user.workspace_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Customer not found")
    tickets = (
        await db.execute(
            select(Ticket)
            .where(Ticket.customer_id == customer_id)
            .order_by(Ticket.created_at.desc())
        )
    ).scalars()
    return [TicketOut.model_validate(ticket) for ticket in tickets]
