"""Grounded assistance. Reply drafts, live call suggestions and summaries."""

from __future__ import annotations

import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Conversation, Message, Workspace
from . import retrieval
from .providers import get_provider

logger = logging.getLogger(__name__)

ESCALATION_FLOOR = 0.25

_ESCALATION_PHRASES = (
    # Asking for a person, in the ways people actually ask.
    "manager",
    "supervisor",
    "someone else",
    "speak to a human",
    "speak to someone",
    "talk to a human",
    "talk to a person",
    "talk to someone",
    "real person",
    "real human",
    "representative",
    "escalate",
    # Trouble, whether or not they have asked for anyone yet.
    "this is unacceptable",
    "make a complaint",
    "file a complaint",
    "cancel my account",
    "legal action",
    "refund my",
)


@dataclass(slots=True)
class Draft:
    text: str
    confidence: float
    engine: str
    citations: list[dict[str, str]] = field(default_factory=list)
    should_escalate: bool = False


def _system_prompt(workspace: Workspace, tone: Optional[str] = None) -> str:
    config = workspace.settings or {}
    voice = tone or config.get("brand_voice") or "Warm, direct and specific."
    extra = (config.get("instructions") or "").strip()
    lines = [
        f"You are a customer-support agent for {workspace.name}.",
        f"Voice: {voice}",
        "",
        "Rules:",
        "- Answer ONLY from the reference passages provided. They are the single source of truth.",
        "- If the passages do not contain the answer, say so plainly and offer to hand over to a teammate.",
        "- Never invent policy, prices, dates, order details or timelines.",
        "- Be concise: two short paragraphs at most, no preamble, no sign-off block.",
        "- Match the customer's language.",
    ]
    if extra:
        lines += ["", f"Additional instructions from the team: {extra}"]
    return "\n".join(lines)


def _format_passages(hits: Sequence[retrieval.Hit]) -> str:
    if not hits:
        return "(no matching reference passages)"
    blocks = []
    for index, hit in enumerate(hits, start=1):
        body = " ".join(hit.article.body.split())[:1200]
        blocks.append(f"[{index}] {hit.article.title}\n{body}")
    return "\n\n".join(blocks)


def _citations(hits: Sequence[retrieval.Hit], query: str) -> list[dict[str, str]]:
    return [
        {
            "articleId": hit.article.id,
            "title": hit.article.title,
            "excerpt": hit.excerpt(query),
        }
        for hit in hits
    ]


def wants_human(text: str) -> bool:
    """Heuristic escalation trigger on explicit customer requests."""
    lowered = text.lower()
    return any(phrase in lowered for phrase in _ESCALATION_PHRASES)


def conversation_query(messages: Sequence[Message], limit: int = 6) -> str:
    """Build a retrieval query from the recent customer turns."""
    customer_turns = [m.body for m in messages if m.author_type == "customer" and not m.is_private]
    return " ".join(customer_turns[-limit:])[:2000]


def _transcript(messages: Sequence[Message], limit: int = 12) -> str:
    labels = {"customer": "Customer", "agent": "Agent", "ai": "Assistant", "system": "System"}
    recent = [m for m in messages if not m.is_private][-limit:]
    return "\n".join(f"{labels.get(m.author_type, m.author_type)}: {m.body}" for m in recent)


def _passage(hit: retrieval.Hit, query: str, length: int) -> str:
    """An excerpt to sit on the same line as a lead in, such as an article title."""
    text = hit.excerpt(query, length=length)
    return text[3:].lstrip() if text.startswith("...") else text


def _fallback_text(workspace: Workspace, hits: Sequence[retrieval.Hit], query: str) -> str:
    """Answer with the best passage when no model is available."""
    config = workspace.settings or {}
    if not hits:
        return config.get("fallback_message") or "Let me bring in a teammate who can help with that."
    best = hits[0]
    return f"From the article {best.article.title}.\n\n{best.excerpt(query, length=420)}"


async def draft_reply(
    db: AsyncSession,
    workspace: Workspace,
    *,
    question: str,
    history: Optional[Sequence[Message]] = None,
    tone: Optional[str] = None,
    include_internal: bool = True,
) -> Draft:
    """Draft a grounded reply to `question`, optionally with conversation history."""
    question = (question or "").strip()
    if not question:
        return Draft(text="", confidence=0.0, engine="none", should_escalate=True)

    hits = await retrieval.search(
        db, workspace.id, question, limit=4, include_internal=include_internal
    )
    top_score = hits[0].coverage if hits else 0.0
    citations = _citations(hits, question)
    escalate = top_score < ESCALATION_FLOOR or wants_human(question)

    provider = get_provider(workspace)
    if not provider.available:
        return Draft(
            text=_fallback_text(workspace, hits, question),
            # Retrieval only answers are never presented as high confidence.
            confidence=round(min(top_score, 0.6), 2),
            engine="grounded-fallback",
            citations=citations,
            should_escalate=escalate,
        )

    prompt_parts = [f"Reference passages:\n{_format_passages(hits)}"]
    if history:
        prompt_parts.append(f"Conversation so far:\n{_transcript(history)}")
    prompt_parts.append(f"Customer's latest message:\n{question}")
    prompt_parts.append("Write the reply to send. Plain text only.")

    try:
        completion = await provider.complete(
            _system_prompt(workspace, tone), "\n\n".join(prompt_parts), max_tokens=500
        )
    except Exception as exc:  # noqa: BLE001, a failed draft must not 500
        logger.warning("LLM draft failed, using retrieval fallback: %s", exc)
        return Draft(
            text=_fallback_text(workspace, hits, question),
            confidence=round(min(top_score, 0.5), 2),
            engine="grounded-fallback",
            citations=citations,
            should_escalate=escalate,
        )

    text = completion.text.strip()
    confidence = round(min(0.35 + top_score * 0.6, 0.95), 2)
    if not text:
        escalate = True
    return Draft(
        text=text or _fallback_text(workspace, hits, question),
        confidence=confidence,
        engine=f"llm:{completion.provider}",
        citations=citations,
        should_escalate=escalate,
    )


async def draft_for_conversation(
    db: AsyncSession,
    workspace: Workspace,
    conversation: Conversation,
    *,
    tone: Optional[str] = None,
    include_internal: bool = True,
) -> Draft:
    """Draft an answer to the latest customer turn in a conversation."""
    messages = list(conversation.messages)
    latest = next(
        (m.body for m in reversed(messages) if m.author_type == "customer" and not m.is_private),
        "",
    )
    query = latest or conversation_query(messages)
    return await draft_reply(
        db,
        workspace,
        question=query,
        history=messages,
        tone=tone,
        include_internal=include_internal,
    )


_TAP_SYSTEM = """You coach a live human support agent while they are on a phone call.
You are NOT talking to the customer. You are whispering to the agent.

Rules.
- Ground every suggestion in the reference passages. Never invent policy or numbers.
- Output at most 3 suggestions, one per line, each prefixed with a tag.
  ANSWER: something the agent can say, near-verbatim.
  ACTION: a step to take in the system.
  WARNING: a risk, commitment or compliance issue to avoid.
  QUESTION: what to ask next to unblock the call.
- Keep each line under 25 words. No numbering, no preamble."""

_TAG_RE = re.compile(r"^(ANSWER|ACTION|WARNING|QUESTION)\s*[:\-]\s*(.+)$", re.IGNORECASE)


def parse_suggestions(raw: str) -> list[dict[str, str]]:
    """Turn tagged model output into structured suggestions."""
    parsed: list[dict[str, str]] = []
    for line in raw.splitlines():
        line = line.strip().lstrip("-•* ").strip()
        if not line:
            continue
        match = _TAG_RE.match(line)
        if match:
            parsed.append({"kind": match.group(1).lower(), "text": match.group(2).strip()})
        elif parsed:
            # Continuation of the previous suggestion.
            parsed[-1]["text"] = f"{parsed[-1]['text']} {line}".strip()
        else:
            parsed.append({"kind": "answer", "text": line})
    return parsed[:3]


async def tap_suggestions(
    db: AsyncSession,
    workspace: Workspace,
    *,
    transcript: Sequence[dict[str, Any]],
    latest: str,
) -> tuple[list[dict[str, Any]], list[dict[str, str]], str]:
    """Suggestions for the agent, their citations, and the engine used."""
    window = " ".join(entry.get("text", "") for entry in list(transcript)[-4:])
    query = f"{latest} {latest} {window}".strip()
    hits = await retrieval.search(db, workspace.id, query, limit=3, include_internal=True)
    citations = _citations(hits, query)
    top_score = hits[0].coverage if hits else 0.0
    confidence = round(min(0.3 + top_score * 0.6, 0.95), 2)

    provider = get_provider(workspace)
    if not provider.available:
        suggestions: list[dict[str, Any]] = []
        for hit in hits[:2]:
            suggestions.append(
                {
                    "kind": "answer",
                    "text": f"{hit.article.title}. {_passage(hit, query, 180)}",
                    "confidence": round(min(hit.coverage, 0.6), 2),
                }
            )
        if wants_human(latest):
            suggestions.insert(
                0,
                {
                    "kind": "warning",
                    "text": "Caller is asking to escalate, offer a supervisor callback.",
                    "confidence": 0.8,
                },
            )
        return suggestions, citations, "grounded-fallback"

    lines = [f"{entry.get('speaker', 'customer').title()}: {entry.get('text','')}" for entry in list(transcript)[-8:]]
    prompt = "\n".join(
        [
            f"Reference passages:\n{_format_passages(hits)}",
            "",
            "Live call transcript so far:",
            "\n".join(lines) or "(call just started)",
            "",
            f"The caller just said: {latest}",
            "",
            "Give the agent their next move.",
        ]
    )
    try:
        completion = await provider.complete(_TAP_SYSTEM, prompt, max_tokens=250, temperature=0.3)
    except Exception as exc:  # noqa: BLE001, a live call must never error out
        logger.warning("Tap suggestion failed: %s", exc)
        return (
            [{"kind": "warning", "text": "Assistant unavailable, continue manually.", "confidence": 0.0}],
            citations,
            "unavailable",
        )

    suggestions = [
        {**item, "confidence": confidence} for item in parse_suggestions(completion.text)
    ]
    return suggestions, citations, f"llm:{completion.provider}"


async def summarise_call(workspace: Workspace, transcript: Sequence[dict[str, Any]]) -> Optional[str]:
    """A short summary written after the call ends."""
    if not transcript:
        return None
    provider = get_provider(workspace)
    lines = [f"{e.get('speaker', 'customer').title()}: {e.get('text', '')}" for e in transcript]
    body = "\n".join(lines)[:6000]
    if not provider.available:
        # A fixed stand in for the opening request from a caller.
        first = next((e.get("text", "") for e in transcript if e.get("speaker") == "customer"), "")
        return f"Call summary unavailable (no AI provider). Opening request: {first[:280]}" if first else None
    try:
        completion = await provider.complete(
            "Summarise a support call in 3 bullet points: the request, what was agreed, and any follow-up owed.",
            body,
            max_tokens=220,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Call summary failed: %s", exc)
        return None
    return completion.text.strip() or None
