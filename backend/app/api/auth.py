"""Registration, sign in, session and API key management."""

from __future__ import annotations

import re

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import func, select

from ..config import settings
from ..db import utcnow
from ..models import DEFAULT_WORKSPACE_SETTINGS, User, Workspace
from ..ratelimit import registrations, sign_in_accounts, sign_in_addresses
from ..schemas import (
    ApiKeyOut,
    LoginRequest,
    RegisterRequest,
    SessionOut,
    UserOut,
    WorkspaceOut,
)
from ..security import (
    CurrentUser,
    DbDep,
    Owner,
    create_access_token,
    generate_api_key,
    hash_api_key,
    hash_password,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["auth"])

_SLUG_RE = re.compile(r"[^a-z0-9]+")

_TOO_MANY = HTTPException(
    status.HTTP_429_TOO_MANY_REQUESTS,
    "Too many attempts. Wait a few minutes and try again.",
)


def _caller(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def slugify(name: str) -> str:
    return _SLUG_RE.sub("-", name.lower()).strip("-") or "workspace"


async def unique_slug(db, base: str) -> str:
    slug = base
    suffix = 2
    while await db.scalar(select(Workspace.id).where(Workspace.slug == slug)):
        slug = f"{base}-{suffix}"
        suffix += 1
    return slug


def _session(user: User, workspace: Workspace) -> SessionOut:
    return SessionOut(
        access_token=create_access_token(user.id, workspace.id, user.role),
        expires_in=settings.ACCESS_TOKEN_TTL_MINUTES * 60,
        user=UserOut.model_validate(user),
        workspace=WorkspaceOut.model_validate(workspace),
    )


@router.post("/register", response_model=SessionOut, status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterRequest, request: Request, db: DbDep) -> SessionOut:
    """Create a workspace and its first user, who becomes the owner."""
    if not registrations.allow(_caller(request)):
        raise _TOO_MANY
    email = payload.email.lower()
    workspace = Workspace(
        name=payload.workspace_name,
        slug=await unique_slug(db, slugify(payload.workspace_name)),
        settings=dict(DEFAULT_WORKSPACE_SETTINGS),
    )
    db.add(workspace)
    await db.flush()

    user = User(
        workspace_id=workspace.id,
        email=email,
        name=payload.name,
        password_hash=hash_password(payload.password),
        role="owner",
        last_login_at=utcnow(),
    )
    db.add(user)
    await db.flush()
    return _session(user, workspace)


MAX_LOGIN_CANDIDATES = 10


@router.post("/login", response_model=SessionOut)
async def login(payload: LoginRequest, request: Request, db: DbDep) -> SessionOut:
    """Sign in."""
    email = payload.email.lower()
    if not sign_in_addresses.allow(_caller(request)) or not sign_in_accounts.allow(email):
        raise _TOO_MANY

    candidates = list(
        (
            await db.execute(
                select(User)
                .where(func.lower(User.email) == email)
                .order_by(User.created_at)
                .limit(MAX_LOGIN_CANDIDATES)
            )
        ).scalars()
    )

    matched = next(
        (user for user in candidates if verify_password(payload.password, user.password_hash)),
        None,
    )
    if matched is None:
        if not candidates:
            verify_password(payload.password, hash_password("placeholder"))
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password")
    if not matched.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password")

    workspace = await db.get(Workspace, matched.workspace_id)
    if workspace is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Workspace not found")
    matched.last_login_at = utcnow()
    await db.flush()
    return _session(matched, workspace)


@router.get("/me", response_model=SessionOut)
async def me(user: CurrentUser, db: DbDep) -> SessionOut:
    """Rebuild a session from a stored token on app boot."""
    workspace = await db.get(Workspace, user.workspace_id)
    if workspace is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Workspace not found")
    return _session(user, workspace)


@router.post("/api-key", response_model=ApiKeyOut)
async def rotate_api_key(db: DbDep, user: Owner) -> ApiKeyOut:
    """Issue a new workspace API key, invalidating the previous one."""
    workspace = await db.get(Workspace, user.workspace_id)
    if workspace is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Workspace not found")
    key = generate_api_key()
    workspace.api_key_hash = hash_api_key(key)
    await db.flush()
    return ApiKeyOut(api_key=key)
