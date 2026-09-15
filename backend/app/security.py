"""Password hashing, tokens and the FastAPI auth dependencies."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import settings
from .db import get_db
from .models import User, Workspace

# Password hashing

_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1
_DK_LEN = 32


def hash_password(password: str) -> str:
    """Return scrypt$N$r$p$salt$hash, with every binary part base64url encoded."""
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode(), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=_DK_LEN
    )
    return "$".join(
        ["scrypt", str(_SCRYPT_N), str(_SCRYPT_R), str(_SCRYPT_P), _b64(salt), _b64(digest)]
    )


def verify_password(password: str, stored: str) -> bool:
    """Constant time check that never raises on a malformed stored value."""
    try:
        scheme, n, r, p, salt_b64, hash_b64 = stored.split("$")
        if scheme != "scrypt":
            return False
        expected = _unb64(hash_b64)
        actual = hashlib.scrypt(
            password.encode(),
            salt=_unb64(salt_b64),
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(expected),
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


# API keys


API_KEY_PREFIX = "sk_"


def generate_api_key() -> str:
    """A workspace secret key. Shown once when it is issued, then only stored hashed."""
    return f"{API_KEY_PREFIX}{secrets.token_urlsafe(32)}"


def hash_api_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


# JSON web tokens, HS256


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def create_access_token(subject: str, workspace_id: str, role: str) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": subject,
        "ws": workspace_id,
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.ACCESS_TOKEN_TTL_MINUTES)).timestamp()),
    }
    header = _b64(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
    body = _b64(json.dumps(payload, separators=(",", ":")).encode())
    signing_input = f"{header}.{body}".encode()
    signature = hmac.new(settings.SECRET_KEY.encode(), signing_input, hashlib.sha256).digest()
    return f"{header}.{body}.{_b64(signature)}"


def decode_token(token: str) -> Optional[dict[str, Any]]:
    """Return the payload, or None if the token is malformed, forged or expired."""
    try:
        header_b64, body_b64, signature_b64 = token.split(".")
        signing_input = f"{header_b64}.{body_b64}".encode()
        expected = hmac.new(settings.SECRET_KEY.encode(), signing_input, hashlib.sha256).digest()
        if not hmac.compare_digest(expected, _unb64(signature_b64)):
            return None
        payload = json.loads(_unb64(body_b64))
    except (ValueError, TypeError, json.JSONDecodeError):
        return None
    if payload.get("exp", 0) < datetime.now(UTC).timestamp():
        return None
    return payload


# FastAPI dependencies

bearer_scheme = HTTPBearer(auto_error=False)

CredentialsDep = Annotated[Optional[HTTPAuthorizationCredentials], Depends(bearer_scheme)]
DbDep = Annotated[AsyncSession, Depends(get_db)]

_UNAUTHORISED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Not authenticated",
    headers={"WWW-Authenticate": "Bearer"},
)


async def workspace_from_api_key(db: AsyncSession, key: str) -> Optional[Workspace]:
    """Look up the workspace a secret API key belongs to."""
    result = await db.execute(select(Workspace).where(Workspace.api_key_hash == hash_api_key(key)))
    return result.scalar_one_or_none()


async def _user_for_api_key(db: AsyncSession, key: str) -> Optional[User]:
    """Resolve a secret API key to the workspace owner it acts as."""
    workspace = await workspace_from_api_key(db, key)
    if workspace is None:
        return None
    result = await db.execute(
        select(User)
        .where(User.workspace_id == workspace.id, User.is_active.is_(True))
        # Owner first, so a key never silently gets less access than intended.
        .order_by(User.role != "owner", User.created_at)
        .limit(1)
    )
    return result.scalar_one_or_none()


async def user_for_socket(token: str) -> Optional[User]:
    """Resolve a WebSocket handshake token to the account behind it."""
    from .db import async_session_maker

    payload = decode_token(token)
    if payload is None:
        return None
    workspace_id = payload.get("ws", "")
    async with async_session_maker() as db:
        user = await db.get(User, payload.get("sub", ""))
        if user is None or not user.is_active or user.workspace_id != workspace_id:
            return None
        return user


async def current_user(credentials: CredentialsDep, db: DbDep) -> User:
    """Resolve the caller from a bearer token."""
    if credentials is None:
        raise _UNAUTHORISED

    token = credentials.credentials
    if token.startswith(API_KEY_PREFIX):
        user = await _user_for_api_key(db, token)
        if user is None:
            raise _UNAUTHORISED
        return user

    payload = decode_token(token)
    if payload is None:
        raise _UNAUTHORISED
    user = await db.get(User, payload.get("sub", ""))
    if user is None or not user.is_active:
        raise _UNAUTHORISED
    return user


CurrentUser = Annotated[User, Depends(current_user)]


def require_role(*roles: str):
    """Restrict a route to the given roles. Owner always passes."""

    async def _guard(user: CurrentUser) -> User:
        if user.role != "owner" and user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires one of {', '.join(roles)}",
            )
        return user

    return _guard


async def require_owner(user: CurrentUser) -> User:
    """Restrict a route to the workspace owner."""
    if user.role != "owner":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only an owner can do this.",
        )
    return user


DOWNLOAD_TTL_SECONDS = 60 * 60


def sign_download(attachment_id: str) -> str:
    """A short lived token that authorises one file."""
    expires = int(time.time()) + DOWNLOAD_TTL_SECONDS
    payload = f"{attachment_id}.{expires}"
    signature = hmac.new(
        settings.SECRET_KEY.encode(), payload.encode(), hashlib.sha256
    ).digest()
    return f"{expires}.{_b64(signature)}"


def verify_download(attachment_id: str, token: str) -> bool:
    """Whether this token authorises this exact file, and is still valid."""
    if not token or "." not in token:
        return False
    expires_raw, _, signature_b64 = token.partition(".")
    try:
        expires = int(expires_raw)
    except ValueError:
        return False
    if expires < time.time():
        return False
    expected = hmac.new(
        settings.SECRET_KEY.encode(), f"{attachment_id}.{expires}".encode(), hashlib.sha256
    ).digest()
    try:
        return hmac.compare_digest(expected, _unb64(signature_b64))
    except Exception:  # noqa: BLE001, a malformed token is simply invalid
        return False


def is_manager(user: User) -> bool:
    """Whether this person can change what the workspace tells customers."""
    return user.role in ("owner", "supervisor")


Manager = Annotated[User, Depends(require_role("supervisor"))]

# Anything that grants owner level power or can remove an owner.
Owner = Annotated[User, Depends(require_owner)]
