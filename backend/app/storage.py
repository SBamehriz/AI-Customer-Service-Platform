"""Where uploaded and received files are kept."""

from __future__ import annotations

import logging
import mimetypes
import re
from datetime import UTC
from pathlib import Path
from typing import Optional

from .config import BACKEND_DIR

logger = logging.getLogger(__name__)

ATTACHMENT_DIR = BACKEND_DIR / "data" / "attachments"

MAX_BYTES = 25 * 1024 * 1024

IMAGE_TYPES = frozenset(
    {"image/png", "image/jpeg", "image/gif", "image/webp", "image/heic", "image/heif"}
)
AUDIO_TYPES = frozenset({"audio/mpeg", "audio/mp4", "audio/ogg", "audio/wav", "audio/webm"})
DOCUMENT_TYPES = frozenset(
    {
        "application/pdf",
        "text/plain",
        "text/csv",
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.ms-excel",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/zip",
    }
)
ALLOWED_TYPES = IMAGE_TYPES | AUDIO_TYPES | DOCUMENT_TYPES | frozenset({"video/mp4", "video/webm"})

BLOCKED_EXTENSIONS = frozenset(
    {
        ".exe", ".com", ".scr", ".pif", ".msi", ".msp", ".cpl", ".dll", ".sys",
        ".drv", ".ocx", ".bat", ".cmd", ".ps1", ".psm1", ".vbs", ".vbe", ".wsf",
        ".wsh", ".js", ".jse", ".hta", ".jar", ".app", ".dmg", ".pkg", ".deb",
        ".rpm", ".apk", ".sh", ".bash", ".zsh", ".csh", ".run", ".bin", ".elf",
        ".so", ".dylib", ".lnk", ".reg", ".scf", ".inf", ".gadget", ".py",
        ".pyc", ".pyw", ".pl", ".rb", ".php", ".ps2", ".msc", ".jnlp",
    }
)

_EXECUTABLE_MAGIC = (
    b"MZ",
    b"\x7fELF",
    b"\xca\xfe\xba\xbe",
    b"\xcf\xfa\xed\xfe",
    b"\xce\xfa\xed\xfe",
    b"\xfe\xed\xfa\xcf",
    b"\xfe\xed\xfa\xce",
    b"#!",
)

_SAFE_NAME = re.compile(r"[^A-Za-z0-9._ -]+")


def is_allowed(content_type: str) -> bool:
    return (content_type or "").split(";")[0].strip().lower() in ALLOWED_TYPES


def has_blocked_name(filename: str) -> bool:
    """Whether this name makes the file executable somewhere."""
    return Path(clean_filename(filename)).suffix.lower() in BLOCKED_EXTENSIONS


def looks_executable(payload: bytes) -> bool:
    """Whether these bytes start like a program rather than a document."""
    head = bytes(payload[:8])
    return any(head.startswith(magic) for magic in _EXECUTABLE_MAGIC)


def rejection_reason(filename: str, content_type: str, payload: bytes) -> Optional[str]:
    """Why this file is not accepted, or None when it is."""
    if not is_allowed(content_type):
        return f"{content_type} is not a file type this platform accepts."
    if has_blocked_name(filename):
        return (
            f"{clean_filename(filename, content_type)} is a program, which this "
            "platform does not accept whatever type it is sent as."
        )
    if looks_executable(payload):
        return "That file is a program, which this platform does not accept."
    return None


def clean_filename(name: str, content_type: str = "") -> str:
    """A display name that is safe to put in a header and in the interface."""
    name = (name or "").replace("\\", "/").split("/")[-1].strip()
    name = _SAFE_NAME.sub("_", name).strip("._ ") or "file"
    if "." not in name:
        guessed = mimetypes.guess_extension(content_type.split(";")[0].strip()) if content_type else None
        name = f"{name}{guessed or ''}"
    return name[:120]


def _extension_for(content_type: str, filename: str) -> str:
    """Pick the extension from the type we accepted, not from the name given."""
    guessed = mimetypes.guess_extension((content_type or "").split(";")[0].strip().lower())
    if guessed:
        return guessed
    suffix = Path(clean_filename(filename)).suffix
    return suffix if len(suffix) <= 10 else ""


def build_path(workspace_id: str, attachment_id: str, content_type: str, filename: str) -> Path:
    """Where this file will live. Created from ids, never from user input."""
    from datetime import datetime

    now = datetime.now(UTC)
    relative = Path(workspace_id) / f"{now:%Y}" / f"{now:%m}"
    return relative / f"{attachment_id}{_extension_for(content_type, filename)}"


def absolute(storage_path: str) -> Optional[Path]:
    """Resolve a stored path, refusing anything that escapes the directory."""
    root = ATTACHMENT_DIR.resolve()
    candidate = (root / storage_path).resolve()
    if candidate != root and root not in candidate.parents:
        logger.error("Refused an attachment path outside the store, %s", storage_path)
        return None
    return candidate


def write(storage_path: str, payload: bytes) -> None:
    target = absolute(storage_path)
    if target is None:
        raise ValueError("Refused to write outside the attachment directory")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(payload)


def read(storage_path: str) -> Optional[bytes]:
    source = absolute(storage_path)
    if source is None or not source.exists():
        return None
    return source.read_bytes()


def remove(storage_path: str) -> None:
    target = absolute(storage_path)
    if target is not None and target.exists():
        try:
            target.unlink()
        except OSError:  # pragma: no cover, a locked file
            logger.warning("Could not delete attachment file %s", storage_path)


def kind_of(content_type: str) -> str:
    """A coarse bucket the interface uses to decide how to show something."""
    base = (content_type or "").split(";")[0].strip().lower()
    if base in IMAGE_TYPES:
        return "image"
    if base in AUDIO_TYPES:
        return "audio"
    if base.startswith("video/"):
        return "video"
    return "file"
