"""Encryption for the secrets the platform stores on your behalf."""

from __future__ import annotations

import base64
import hashlib
import logging
from typing import Optional

from .config import settings

logger = logging.getLogger(__name__)

try:  # pragma: no cover, exercised by whichever branch the host supports
    from cryptography.fernet import Fernet, InvalidToken

    AVAILABLE = True
except Exception:  # noqa: BLE001, a broken native build raises more than ImportError
    Fernet = None  # type: ignore[assignment]
    InvalidToken = Exception  # type: ignore[assignment,misc]
    AVAILABLE = False

_SALT = b"ucsp.credential.encryption.v1"

_MARKER = "enc:v1:"


def _fernet():
    """A Fernet built from SECRET_KEY."""
    derived = hashlib.scrypt(
        settings.SECRET_KEY.encode("utf-8"),
        salt=_SALT,
        n=2**14,
        r=8,
        p=1,
        dklen=32,
    )
    return Fernet(base64.urlsafe_b64encode(derived))


def seal(value: str) -> str:
    """Encrypt a secret for storage. An empty value stays empty."""
    if not value or not AVAILABLE:
        return value
    token = _fernet().encrypt(value.encode("utf-8")).decode("ascii")
    return f"{_MARKER}{token}"


def unseal(value: str) -> Optional[str]:
    """Decrypt a stored secret."""
    if not value:
        return None
    if not value.startswith(_MARKER):
        return value
    if not AVAILABLE:
        logger.warning(
            "A stored credential is encrypted but the cryptography package is "
            "not usable here, so it cannot be read. Install it, or set the "
            "credential through an environment variable instead."
        )
        return None
    try:
        return _fernet().decrypt(value[len(_MARKER) :].encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError):
        logger.warning(
            "A stored credential could not be decrypted. That happens when "
            "SECRET_KEY changes, because the old value can no longer be read. "
            "Enter the credential again under Settings."
        )
        return None


def is_sealed(value: str) -> bool:
    """Whether a stored value is already encrypted."""
    return bool(value) and value.startswith(_MARKER)
