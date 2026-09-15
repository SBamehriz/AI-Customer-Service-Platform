"""ORM models, the whole schema in one place."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from .db import Base, utcnow


def new_id() -> str:
    return uuid4().hex


class IdMixin:
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow, nullable=False
    )


DEFAULT_WORKSPACE_SETTINGS: dict[str, Any] = {
    "greeting": "Hi, how can we help today.",
    "brand_voice": "Warm, direct and specific. Never guess.",
    "fallback_message": "Let me bring in a teammate who can help with that.",
    "instructions": "",
    "ai_autoreply": True,
    "ai_suggest_threshold": 0.3,
    "ai_autoresolve_threshold": 0.9,
    "escalate_after_ai_turns": 4,
    "business_hours": "Mon-Fri, 9:00-18:00",
    "record_calls": False,
    "recording_notice": "This call may be recorded for quality and training purposes.",
    "autopilot_enabled": False,
    # Hours of the day, UTC. A range, a list, or both. "22-6" wraps midnight.
    "autopilot_hours": "",
}


def workspace_setting(settings: Optional[dict], key: str) -> Any:
    """Read one workspace setting, falling back to the default above."""
    if settings and key in settings:
        return settings[key]
    return DEFAULT_WORKSPACE_SETTINGS[key]


class Workspace(IdMixin, TimestampMixin, Base):
    """A company using the platform. Every other row is scoped to one."""

    __tablename__ = "workspaces"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    accent_color: Mapped[str] = mapped_column(String(9), default="#2563EB")
    logo_url: Mapped[Optional[str]] = mapped_column(String(500))
    settings: Mapped[dict] = mapped_column(JSON, default=lambda: dict(DEFAULT_WORKSPACE_SETTINGS))
    ai_config: Mapped[dict] = mapped_column(JSON, default=dict)
    public_key: Mapped[str] = mapped_column(String(64), unique=True, default=lambda: f"pk_{new_id()}")
    api_key_hash: Mapped[Optional[str]] = mapped_column(String(128))

    users: Mapped[list[User]] = relationship(back_populates="workspace", cascade="all, delete-orphan")

    def __repr__(self) -> str:  # pragma: no cover, debugging aid
        return f"<Workspace {self.slug}>"


class User(IdMixin, TimestampMixin, Base):
    """A member of the support team, as an owner, a supervisor or an agent."""

    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("workspace_id", "email", name="uq_user_workspace_email"),)

    workspace_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), default="agent", nullable=False)
    avatar_url: Mapped[Optional[str]] = mapped_column(String(500))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    workspace: Mapped[Workspace] = relationship(back_populates="users")


class Customer(IdMixin, TimestampMixin, Base):
    """A person contacting support, deduplicated across every channel."""

    __tablename__ = "customers"
    __table_args__ = (Index("ix_customer_workspace_email", "workspace_id", "email"),)

    workspace_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[Optional[str]] = mapped_column(String(200))
    email: Mapped[Optional[str]] = mapped_column(String(255))
    phone: Mapped[Optional[str]] = mapped_column(String(50))
    company: Mapped[Optional[str]] = mapped_column(String(200))
    channel_ids: Mapped[dict] = mapped_column(JSON, default=dict)
    notes: Mapped[Optional[str]] = mapped_column(Text)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


CHANNELS = ("web", "email", "whatsapp", "instagram", "sms", "voice", "api")


class Conversation(IdMixin, TimestampMixin, Base):
    """One continuous exchange with a customer on a single channel."""

    __tablename__ = "conversations"
    __table_args__ = (
        Index("ix_conversation_workspace_status", "workspace_id", "status"),
        Index("ix_conversation_thread", "workspace_id", "channel", "channel_thread_id"),
    )

    workspace_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    customer_id: Mapped[Optional[str]] = mapped_column(
        String(32), ForeignKey("customers.id", ondelete="SET NULL")
    )
    channel: Mapped[str] = mapped_column(String(20), default="web", nullable=False)
    channel_thread_id: Mapped[Optional[str]] = mapped_column(String(255))
    subject: Mapped[Optional[str]] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(20), default="open", nullable=False)
    assigned_user_id: Mapped[Optional[str]] = mapped_column(
        String(32), ForeignKey("users.id", ondelete="SET NULL")
    )
    ticket_id: Mapped[Optional[str]] = mapped_column(String(32), ForeignKey("tickets.id", ondelete="SET NULL"))
    ai_handled: Mapped[bool] = mapped_column(Boolean, default=False)
    ai_turns: Mapped[int] = mapped_column(Integer, default=0)
    last_message_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    customer: Mapped[Optional[Customer]] = relationship(lazy="joined")
    messages: Mapped[list[Message]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="Message.created_at",
    )


class Attachment(IdMixin, Base):
    """A file that arrived with a message, or was sent out with one."""

    __tablename__ = "attachments"
    __table_args__ = (Index("ix_attachment_message", "message_id"),)

    workspace_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    message_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(120), default="application/octet-stream")
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    storage_path: Mapped[str] = mapped_column(String(400), nullable=False)
    # web, email, whatsapp, instagram, sms, voice, agent
    source: Mapped[str] = mapped_column(String(20), default="web")
    claim_key: Mapped[Optional[str]] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class Message(IdMixin, Base):
    """A single turn. `is_private` marks internal notes never sent onward."""

    __tablename__ = "messages"
    __table_args__ = (Index("ix_message_conversation_created", "conversation_id", "created_at"),)

    conversation_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    workspace_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    # customer, agent, ai, system
    author_type: Mapped[str] = mapped_column(String(20), nullable=False)
    author_name: Mapped[Optional[str]] = mapped_column(String(200))
    author_user_id: Mapped[Optional[str]] = mapped_column(String(32))
    body: Mapped[str] = mapped_column(Text, nullable=False)
    is_private: Mapped[bool] = mapped_column(Boolean, default=False)
    # Provider message id, kept so redelivered webhooks are ignored.
    external_id: Mapped[Optional[str]] = mapped_column(String(255), index=True)
    meta: Mapped[dict] = mapped_column("metadata_json", JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    conversation: Mapped[Conversation] = relationship(back_populates="messages")


class Ticket(IdMixin, TimestampMixin, Base):
    """Durable record of a request. Conversations attach to at most one."""

    __tablename__ = "tickets"
    __table_args__ = (
        UniqueConstraint("workspace_id", "number", name="uq_ticket_workspace_number"),
        Index("ix_ticket_workspace_status", "workspace_id", "status"),
    )

    workspace_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    subject: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    customer_id: Mapped[Optional[str]] = mapped_column(
        String(32), ForeignKey("customers.id", ondelete="SET NULL")
    )
    # new, open, pending, on_hold, solved, closed
    status: Mapped[str] = mapped_column(String(20), default="new", nullable=False)
    # low, medium, high, urgent
    priority: Mapped[str] = mapped_column(String(20), default="medium", nullable=False)
    channel: Mapped[str] = mapped_column(String(20), default="web", nullable=False)
    assigned_user_id: Mapped[Optional[str]] = mapped_column(
        String(32), ForeignKey("users.id", ondelete="SET NULL")
    )
    category: Mapped[Optional[str]] = mapped_column(String(100))
    tags: Mapped[list] = mapped_column(JSON, default=list)
    ai_handled: Mapped[bool] = mapped_column(Boolean, default=False)
    ai_confidence: Mapped[Optional[float]] = mapped_column(Float)
    first_response_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    sla_due_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    sla_breached: Mapped[bool] = mapped_column(Boolean, default=False)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    satisfaction: Mapped[Optional[int]] = mapped_column(Integer)

    customer: Mapped[Optional[Customer]] = relationship(lazy="joined")


class Article(IdMixin, TimestampMixin, Base):
    """A knowledge base article, the only thing the AI is allowed to ground on."""

    __tablename__ = "articles"
    __table_args__ = (Index("ix_article_workspace_status", "workspace_id", "status"),)

    workspace_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    body: Mapped[str] = mapped_column(Text, default="")
    summary: Mapped[Optional[str]] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(100), default="General")
    tags: Mapped[list] = mapped_column(JSON, default=list)
    # draft, published, archived
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)
    # internal, public
    visibility: Mapped[str] = mapped_column(String(20), default="public", nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1)
    author_name: Mapped[Optional[str]] = mapped_column(String(200))
    embedding: Mapped[Optional[list]] = mapped_column(JSON)


class Macro(IdMixin, TimestampMixin, Base):
    """A saved reply agents can insert with one keystroke."""

    __tablename__ = "macros"

    workspace_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(Text, default="")
    tags: Mapped[list] = mapped_column(JSON, default=list)


class SlaPolicy(IdMixin, TimestampMixin, Base):
    """First response and resolution targets, applied by ticket priority."""

    __tablename__ = "sla_policies"

    workspace_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    priorities: Mapped[list] = mapped_column(JSON, default=list)
    first_response_minutes: Mapped[int] = mapped_column(Integer, default=60)
    resolution_minutes: Mapped[int] = mapped_column(Integer, default=1440)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class RoutingRule(IdMixin, TimestampMixin, Base):
    """Condition/action pairs evaluated in `order_index` order on new tickets."""

    __tablename__ = "routing_rules"

    workspace_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # For example, match on channel, or on text the message contains.
    conditions: Mapped[dict] = mapped_column(JSON, default=dict)
    # For example, raise the priority, set a category, or add tags.
    actions: Mapped[dict] = mapped_column(JSON, default=dict)


class ChannelAccount(IdMixin, TimestampMixin, Base):
    """Credentials and status for one connected channel in one workspace."""

    __tablename__ = "channel_accounts"
    __table_args__ = (UniqueConstraint("workspace_id", "channel", name="uq_channel_per_workspace"),)

    workspace_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    channel: Mapped[str] = mapped_column(String(20), nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    last_event_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    def live_config(self) -> dict:
        """The credentials, decrypted, ready to hand to an adapter."""
        from .crypto import unseal

        return {
            key: (unseal(value) or "") if isinstance(value, str) else value
            for key, value in (self.config or {}).items()
        }


class TapSession(IdMixin, TimestampMixin, Base):
    """One assisted live call, with its transcript, suggestions and outcome."""

    __tablename__ = "tap_sessions"

    workspace_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    conversation_id: Mapped[Optional[str]] = mapped_column(
        String(32), ForeignKey("conversations.id", ondelete="SET NULL")
    )
    user_id: Mapped[Optional[str]] = mapped_column(String(32), ForeignKey("users.id", ondelete="SET NULL"))
    call_sid: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    customer_label: Mapped[str] = mapped_column(String(200), default="Caller")
    status: Mapped[str] = mapped_column(String(20), default="live", nullable=False)
    # [{speaker, text, at}] appended as the call runs.
    transcript: Mapped[list] = mapped_column(JSON, default=list)
    # [{id, kind, text, sources, confidence, at, used}]
    suggestions: Mapped[list] = mapped_column(JSON, default=list)
    summary: Mapped[Optional[str]] = mapped_column(Text)
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    recording_attachment_id: Mapped[Optional[str]] = mapped_column(String(32))
    recording_seconds: Mapped[int] = mapped_column(Integer, default=0)


__all__ = [
    "CHANNELS",
    "DEFAULT_WORKSPACE_SETTINGS",
    "Article",
    "ChannelAccount",
    "Conversation",
    "Customer",
    "Macro",
    "Message",
    "RoutingRule",
    "SlaPolicy",
    "TapSession",
    "Ticket",
    "User",
    "Workspace",
    "new_id",
    "workspace_setting",
]
