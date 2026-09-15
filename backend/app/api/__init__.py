"""API v1 router."""

from fastapi import APIRouter

from . import (
    analytics,
    attachments,
    auth,
    conversations,
    customers,
    knowledge,
    tap,
    tickets,
    webhooks,
    widget,
    workspace,
)

router = APIRouter(prefix="/api/v1")

for module in (
    auth,
    attachments,
    conversations,
    tickets,
    customers,
    knowledge,
    analytics,
    workspace,
    tap,
    widget,
    webhooks,
):
    router.include_router(module.router)

__all__ = ["router"]
