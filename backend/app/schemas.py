"""Request and response models."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_serializer, field_validator
from pydantic.alias_generators import to_camel, to_snake

Channel = Literal["web", "email", "whatsapp", "instagram", "sms", "voice", "api"]
TicketStatus = Literal["new", "open", "pending", "on_hold", "solved", "closed"]
Priority = Literal["low", "medium", "high", "urgent"]
Role = Literal["owner", "supervisor", "agent"]
AuthorType = Literal["customer", "agent", "ai", "system"]


def camelize_keys(data: dict[str, Any]) -> dict[str, Any]:
    """Convert a free form dict's keys to camelCase for the JSON surface."""
    return {to_camel(key): value for key, value in (data or {}).items()}


def snakeize_keys(data: dict[str, Any]) -> dict[str, Any]:
    """The inverse, applied to incoming settings patches."""
    return {to_snake(key): value for key, value in (data or {}).items()}


_SETTING_TYPES: dict[str, str] = {
    "greeting": "text",
    "brand_voice": "text",
    "fallback_message": "text",
    "instructions": "text",
    "business_hours": "text",
    "recording_notice": "text",
    "ai_autoreply": "flag",
    "record_calls": "flag",
    "autopilot_enabled": "flag",
    "ai_suggest_threshold": "fraction",
    "ai_autoresolve_threshold": "fraction",
    "escalate_after_ai_turns": "count",
    "autopilot_hours": "hours",
}


def _check_setting(key: str, kind: str, value: Any) -> Any:
    """One setting, checked against the shape the platform reads it as."""
    if kind == "text":
        if not isinstance(value, str):
            raise ValueError(f"{to_camel(key)} has to be text")
        return value
    if kind == "flag":
        if not isinstance(value, bool):
            raise ValueError(f"{to_camel(key)} has to be true or false")
        return value
    if kind == "fraction":
        # A bool is an int in Python, so it has to be excluded by hand.
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{to_camel(key)} has to be a number between 0 and 1")
        if not 0 <= float(value) <= 1:
            raise ValueError(f"{to_camel(key)} has to be between 0 and 1")
        return float(value)
    if kind == "count":
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"{to_camel(key)} has to be a whole number")
        if value < 0:
            raise ValueError(f"{to_camel(key)} cannot be negative")
        return value
    if kind == "hours":
        # Either a written range such as 22-6, or a list of hour numbers.
        if isinstance(value, str):
            return value
        if isinstance(value, list) and all(
            isinstance(hour, int) and not isinstance(hour, bool) for hour in value
        ):
            return value
        raise ValueError(
            f"{to_camel(key)} has to be a list of hours, or text such as 22-6"
        )
    return value


def reject_null(value: Any) -> Any:
    """Refuse an explicit null on a field the row cannot store as null."""
    if value is None:
        raise ValueError("This field cannot be null. Leave it out to keep it.")
    return value


def require_text(label: str):
    """Refuse null, and refuse a value that is only whitespace."""

    def check(value: Any) -> Any:
        reject_null(value)
        if isinstance(value, str) and not value.strip():
            raise ValueError(f"{label} cannot be empty")
        return value.strip() if isinstance(value, str) else value

    return check


def validate_settings(data: dict[str, Any]) -> dict[str, Any]:
    """Check the settings this platform reads, and leave the rest alone."""
    checked: dict[str, Any] = {}
    for key, value in (data or {}).items():
        kind = _SETTING_TYPES.get(key)
        checked[key] = value if kind is None else _check_setting(key, kind, value)
    return checked


class ApiModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
        ser_json_timedelta="float",
    )


class RegisterRequest(ApiModel):
    workspace_name: str = Field(min_length=2, max_length=200)
    name: str = Field(min_length=1, max_length=200)
    email: EmailStr
    password: str = Field(min_length=8, max_length=200)


class LoginRequest(ApiModel):
    email: EmailStr
    password: str


class UserOut(ApiModel):
    id: str
    name: str
    email: str
    role: Role
    avatar_url: Optional[str] = None
    is_active: bool = True


class AttachmentOut(ApiModel):
    """A file on a message. `url` is where to fetch it from."""

    id: str
    filename: str
    content_type: str
    size_bytes: int
    # image, audio, video or file, so the interface knows how to show it.
    kind: str
    url: str
    created_at: datetime


class AiConfigOut(ApiModel):
    """What the workspace has configured. Never the key itself."""

    provider: str = "none"
    model: str = ""
    # Used when `model` is empty, so a key on its own is enough to start.
    default_model: str = ""
    base_url: str = ""
    embedding_model: str = ""
    # Whether a key is stored, so the interface can say so without showing it.
    has_key: bool = False
    # True when environment variables decide this, which makes it read only.
    managed_by_env: bool = False
    encryption_available: bool = True
    active: bool = False


class AiConfigIn(ApiModel):
    """Set a provider. Leave `api_key` out to keep the stored one."""

    provider: Literal["none", "openai", "anthropic", "gemini"] = "none"
    model: str = Field(default="", max_length=200)
    base_url: str = Field(default="", max_length=500)
    embedding_model: str = Field(default="", max_length=200)
    api_key: Optional[str] = Field(default=None, max_length=500)


class AiTestResult(ApiModel):
    """The outcome of asking the provider to answer one trivial question."""

    ok: bool
    detail: str


class TeamMemberIn(ApiModel):
    """A new teammate. The owner sets the first password and hands it over."""

    name: str = Field(min_length=1, max_length=200)
    email: EmailStr
    password: str = Field(min_length=8, max_length=200)
    role: Role = "agent"


class TeamMemberPatch(ApiModel):
    """Change what someone may do, or switch them off without losing history."""

    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    role: Optional[Role] = None
    is_active: Optional[bool] = None


class WorkspaceOut(ApiModel):
    id: str
    name: str
    slug: str
    accent_color: str
    logo_url: Optional[str] = None
    public_key: str
    settings: dict[str, Any]

    @field_serializer("settings")
    def _camel_settings(self, value: dict[str, Any]) -> dict[str, Any]:
        return camelize_keys(value)


class SessionOut(ApiModel):
    """What the frontend needs after a successful sign in."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserOut
    workspace: WorkspaceOut


class ApiKeyOut(ApiModel):
    """Returned exactly once, at rotation. Only the hash is persisted."""

    api_key: str


class CustomerIn(ApiModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    company: Optional[str] = None
    notes: Optional[str] = None
    channel_ids: dict[str, str] = Field(default_factory=dict)


class CustomerOut(ApiModel):
    id: str
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    company: Optional[str] = None
    notes: Optional[str] = None
    channel_ids: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    last_seen_at: datetime
    # Filled in by the customers router, not stored on the row.
    total_tickets: int = 0
    open_tickets: int = 0


class MessageOut(ApiModel):
    id: str
    conversation_id: str
    author_type: AuthorType
    author_name: Optional[str] = None
    body: str
    is_private: bool = False
    meta: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    attachments: list[AttachmentOut] = Field(default_factory=list)


class MessageIn(ApiModel):
    body: str = Field(default="", max_length=20000)
    is_private: bool = False
    # Agents may reply as themselves or send an AI draft as it is.
    author_type: Literal["agent", "ai"] = "agent"
    # Ids from POST /attachments, uploaded before the message is sent.
    attachment_ids: list[str] = Field(default_factory=list)


class ConversationOut(ApiModel):
    id: str
    channel: Channel
    subject: Optional[str] = None
    status: Literal["open", "pending", "resolved", "escalated"]
    customer: Optional[CustomerOut] = None
    assigned_user_id: Optional[str] = None
    ticket_id: Optional[str] = None
    ai_handled: bool = False
    ai_turns: int = 0
    last_message_at: datetime
    created_at: datetime
    messages: list[MessageOut] = Field(default_factory=list)


class ConversationPatch(ApiModel):
    """A partial conversation update. Absent means leave alone."""

    status: Optional[Literal["open", "pending", "resolved", "escalated"]] = None
    assigned_user_id: Optional[str] = None
    subject: Optional[str] = None

    @field_validator("status", mode="before")
    @classmethod
    def _not_null(cls, value: Any) -> Any:
        return reject_null(value)


class TicketIn(ApiModel):
    subject: str = Field(min_length=1, max_length=500)
    description: str = ""
    priority: Priority = "medium"
    channel: Channel = "web"
    category: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    customer_id: Optional[str] = None
    customer_email: Optional[EmailStr] = None
    customer_name: Optional[str] = None
    assigned_user_id: Optional[str] = None


class TicketPatch(ApiModel):
    """A partial ticket update. Absent means leave alone."""

    subject: Optional[str] = Field(default=None, min_length=1, max_length=500)
    description: Optional[str] = None
    status: Optional[TicketStatus] = None
    priority: Optional[Priority] = None
    category: Optional[str] = None
    tags: Optional[list[str]] = None
    assigned_user_id: Optional[str] = None
    satisfaction: Optional[int] = Field(default=None, ge=1, le=5)

    @field_validator("subject", mode="before")
    @classmethod
    def _real_subject(cls, value: Any) -> Any:
        return require_text("A ticket subject")(value)

    @field_validator("status", "priority", "tags", "description", mode="before")
    @classmethod
    def _not_null(cls, value: Any) -> Any:
        return reject_null(value)


class TicketOut(ApiModel):
    id: str
    number: int
    subject: str
    description: str
    status: TicketStatus
    priority: Priority
    channel: Channel
    category: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    customer: Optional[CustomerOut] = None
    assigned_user_id: Optional[str] = None
    ai_handled: bool = False
    ai_confidence: Optional[float] = None
    first_response_at: Optional[datetime] = None
    sla_due_at: Optional[datetime] = None
    sla_breached: bool = False
    resolved_at: Optional[datetime] = None
    satisfaction: Optional[int] = None
    created_at: datetime
    updated_at: datetime


class ArticleIn(ApiModel):
    title: str = Field(min_length=1, max_length=300)
    body: str = ""
    summary: Optional[str] = None
    category: str = "General"
    tags: list[str] = Field(default_factory=list)
    status: Literal["draft", "published", "archived"] = "draft"
    visibility: Literal["internal", "public"] = "public"


class ArticlePatch(ApiModel):
    """A partial article update. Absent means leave alone."""

    title: Optional[str] = Field(default=None, max_length=300)
    body: Optional[str] = None
    summary: Optional[str] = None
    category: Optional[str] = Field(default=None, max_length=100)
    tags: Optional[list[str]] = None
    status: Optional[Literal["draft", "published", "archived"]] = None
    visibility: Optional[Literal["internal", "public"]] = None

    @field_validator("title", "category", mode="before")
    @classmethod
    def _real_text(cls, value: Any) -> Any:
        return require_text("An article title and category")(value)

    @field_validator("body", "tags", "status", "visibility", mode="before")
    @classmethod
    def _not_null(cls, value: Any) -> Any:
        return reject_null(value)


class ArticleOut(ApiModel):
    id: str
    title: str
    body: str
    summary: Optional[str] = None
    category: str
    tags: list[str] = Field(default_factory=list)
    status: Literal["draft", "published", "archived"]
    visibility: Literal["internal", "public"]
    version: int
    author_name: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class SearchHit(ApiModel):
    article_id: str
    title: str
    excerpt: str
    category: str
    score: float


class MacroIn(ApiModel):
    name: str = Field(min_length=1, max_length=200)
    body: str = ""
    tags: list[str] = Field(default_factory=list)


class MacroOut(MacroIn):
    id: str
    updated_at: datetime


class SlaPolicyIn(ApiModel):
    name: str = Field(min_length=1, max_length=200)
    priorities: list[Priority] = Field(default_factory=list)
    first_response_minutes: int = Field(default=60, ge=1)
    resolution_minutes: int = Field(default=1440, ge=1)
    is_active: bool = True


class SlaPolicyPatch(ApiModel):
    """A partial SLA policy update. Absent means leave alone."""

    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    priorities: Optional[list[Priority]] = None
    first_response_minutes: Optional[int] = Field(default=None, ge=1)
    resolution_minutes: Optional[int] = Field(default=None, ge=1)
    is_active: Optional[bool] = None

    _text = field_validator("name", mode="before")(require_text("A policy name"))
    _keep = field_validator("priorities", "is_active", mode="before")(reject_null)


class SlaPolicyOut(SlaPolicyIn):
    id: str


class RoutingRuleIn(ApiModel):
    name: str = Field(min_length=1, max_length=200)
    order_index: int = 0
    is_active: bool = True
    conditions: dict[str, Any] = Field(default_factory=dict)
    actions: dict[str, Any] = Field(default_factory=dict)


class RoutingRulePatch(ApiModel):
    """A partial routing rule update. Absent means leave alone."""

    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    order_index: Optional[int] = None
    is_active: Optional[bool] = None
    conditions: Optional[dict[str, Any]] = None
    actions: Optional[dict[str, Any]] = None

    _text = field_validator("name", mode="before")(require_text("A rule name"))
    _keep = field_validator("order_index", "is_active", "conditions", "actions", mode="before")(
        reject_null
    )


class RoutingRuleOut(RoutingRuleIn):
    id: str


class ChannelIn(ApiModel):
    display_name: str = ""
    is_active: bool = False
    config: dict[str, Any] = Field(default_factory=dict)


class ChannelOut(ApiModel):
    """Channel status without secrets."""

    id: str
    channel: Channel
    display_name: str
    is_active: bool
    configured_keys: list[str] = Field(default_factory=list)
    missing_keys: list[str] = Field(default_factory=list)
    webhook_url: Optional[str] = None
    last_event_at: Optional[datetime] = None


class WorkspacePatch(ApiModel):
    name: Optional[str] = None
    accent_color: Optional[str] = Field(default=None, pattern=r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")
    logo_url: Optional[str] = None
    settings: Optional[dict[str, Any]] = None

    @field_validator("settings")
    @classmethod
    def _snake_settings(cls, value: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
        return None if value is None else validate_settings(snakeize_keys(value))


class DraftRequest(ApiModel):
    conversation_id: Optional[str] = None
    # Free text question, used when drafting outside a conversation.
    question: Optional[str] = None
    tone: Optional[str] = None


class Citation(ApiModel):
    article_id: str
    title: str
    excerpt: str


class DraftOut(ApiModel):
    text: str
    confidence: float
    citations: list[Citation] = Field(default_factory=list)
    engine: str
    should_escalate: bool = False


class TapStartRequest(ApiModel):
    customer_label: str = "Caller"
    conversation_id: Optional[str] = None


class TapUtterance(ApiModel):
    speaker: Literal["customer", "agent"]
    text: str = Field(min_length=1)


class TapSuggestion(ApiModel):
    id: str
    kind: Literal["answer", "action", "warning", "question"]
    text: str
    confidence: float
    citations: list[Citation] = Field(default_factory=list)
    created_at: datetime


class TapSessionOut(ApiModel):
    id: str
    status: Literal["live", "ended"]
    call_sid: Optional[str] = None
    customer_label: str
    conversation_id: Optional[str] = None
    transcript: list[dict[str, Any]] = Field(default_factory=list)
    suggestions: list[dict[str, Any]] = Field(default_factory=list)
    summary: Optional[str] = None
    created_at: datetime
    ended_at: Optional[datetime] = None


class WidgetBootstrap(ApiModel):
    public_key: str
    workspace_name: str
    accent_color: str
    greeting: str
    logo_url: Optional[str] = None
    ai_enabled: bool


class WidgetMessageIn(ApiModel):
    session_id: Optional[str] = None
    body: str = Field(default="", max_length=4000)
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    attachment_ids: list[str] = Field(default_factory=list)


class WidgetMessageOut(ApiModel):
    session_id: str
    conversation_id: str
    reply: Optional[MessageOut] = None
    escalated: bool = False


class WidgetAttachmentOut(AttachmentOut):
    """An uploaded file, plus the session it belongs to."""

    session_id: str


class MetricPoint(ApiModel):
    date: str
    created: int
    resolved: int


class AnalyticsSummary(ApiModel):
    range_days: int
    open_tickets: int
    open_delta: float
    sla_at_risk: int
    ai_deflection: float
    ai_deflection_delta: float
    csat: float
    csat_delta: float
    median_first_response_minutes: Optional[float] = None
    series: list[MetricPoint] = Field(default_factory=list)
    channel_mix: list[dict[str, Any]] = Field(default_factory=list)
    priority_mix: list[dict[str, Any]] = Field(default_factory=list)
    open_priority_mix: list[dict[str, Any]] = Field(default_factory=list)
    top_categories: list[dict[str, Any]] = Field(default_factory=list)
    agent_leaderboard: list[dict[str, Any]] = Field(default_factory=list)
