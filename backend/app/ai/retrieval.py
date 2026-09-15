"""Knowledge base retrieval."""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..models import Article
from .providers import get_provider

_WORD_RE = re.compile(r"[a-z0-9']+")

_STOPWORDS = frozenset(
    """a an and are as at be been but by can cant could did do does doesnt for from
    get got had has have how i im in is it its many me much my no not of on or our
    so than that the their them then there these they this to too very was we were
    what when where which who why will with would you your""".split()
)

_COVERAGE_MIDPOINT = 2.2

_MIN_TERM_WEIGHT = 1.2

_LEXICAL_WEIGHT = 0.6
_SEMANTIC_WEIGHT = 0.4


_VERB_SUFFIXES = ("ingly", "edly", "ing", "ied", "ed", "ly")

_STEM_FLOOR = 5

_ES_PLURAL_ENDINGS = ("ses", "xes", "zes", "ches", "shes")


def stem(word: str) -> str:
    """Reduce a word to a rough root, so tenses and plurals match."""
    if len(word) < _STEM_FLOOR:
        return word

    if word.endswith("ies") and len(word) > 4:
        return word[:-3] + "y"
    if word.endswith(_ES_PLURAL_ENDINGS):
        word = word[:-2]
    elif word.endswith("s") and not word.endswith("ss"):
        word = word[:-1]

    if len(word) < _STEM_FLOOR:
        return word

    for suffix in _VERB_SUFFIXES:
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            root = word[: -len(suffix)]
            # A doubled consonant from "shipped" or "planning" collapses.
            if len(root) > 3 and root[-1] == root[-2] and root[-1] not in "aeiou":
                root = root[:-1]
            return root

    if len(word) >= _STEM_FLOOR and word.endswith("e"):
        return word[:-1]
    return word


def tokenize(text: str) -> list[str]:
    """Words worth matching on, lowercased, stopped and stemmed."""
    return [
        stem(word)
        for word in _WORD_RE.findall(text.lower())
        if word not in _STOPWORDS
    ]


@dataclass(slots=True)
class Hit:
    article: Article
    score: float
    coverage: float = 0.0

    def excerpt(self, query: str, length: int = 240) -> str:
        """A window of the body around the first query term, else the opening."""
        body = " ".join(self.article.body.split())
        if not body:
            return self.article.summary or ""

        lowered = body.lower()
        position = -1
        for term in tokenize(query):
            position = lowered.find(term)
            if position != -1:
                break

        if position == -1 or position < length:
            start = 0
        else:
            start = max(0, position - length // 3)
        return _window(body, start, length)


_SENTENCE_LOOKBACK = 160


def _window(body: str, start: int, length: int) -> str:
    """Cut a readable window out of a body of text."""
    if start > 0:
        sentence = _sentence_start(body, start)
        if sentence is not None:
            start = sentence
        else:
            space = body.find(" ", start)
            start = start if space == -1 else space + 1

    whole_sentence = False
    end = start + length
    if end < len(body):
        sentence = _sentence_end(body, start, end)
        if sentence is not None:
            end = sentence
            whole_sentence = True
        else:
            space = body.rfind(" ", start, end)
            end = end if space <= start else space

    prefix = "..." if start > 0 else ""
    suffix = "..." if end < len(body) and not whole_sentence else ""
    return f"{prefix}{body[start:end].strip()}{suffix}"


def _sentence_start(body: str, position: int) -> int | None:
    """Index just after the nearest sentence end before `position`, if close."""
    floor = max(0, position - _SENTENCE_LOOKBACK)
    best = max(body.rfind(f"{mark} ", floor, position) for mark in ".!?")
    return best + 2 if best != -1 else None


def _sentence_end(body: str, start: int, position: int) -> int | None:
    """Index just after the last sentence that finishes inside the window."""
    floor = max(start, position - _SENTENCE_LOOKBACK)
    best = max(body.rfind(f"{mark} ", floor, position) for mark in ".!?")
    if best == -1:
        if position >= len(body) and body[position - 1 : position] in ".!?":
            return position
        return None
    return best + 1


def _document_text(article: Article) -> str:
    """Title and summary repeat so matches there outrank body only matches."""
    return " ".join(
        [
            article.title,
            article.title,
            article.summary or "",
            " ".join(article.tags or []),
            article.category or "",
            article.body,
        ]
    )


def bm25_scores(query: str, documents: Sequence[str], k1: float = 1.5, b: float = 0.75) -> list[float]:
    """Standard BM25 over an in memory corpus."""
    terms = tokenize(query)
    if not terms or not documents:
        return [0.0] * len(documents)

    tokenized = [tokenize(doc) for doc in documents]
    lengths = [len(doc) or 1 for doc in tokenized]
    avg_length = sum(lengths) / len(lengths)
    frequencies = [Counter(doc) for doc in tokenized]

    document_frequency = Counter()
    for counts in frequencies:
        for term in set(terms):
            if counts[term]:
                document_frequency[term] += 1

    total = len(documents)
    scores = [0.0] * total
    for index, counts in enumerate(frequencies):
        score = 0.0
        for term in terms:
            frequency = counts[term]
            if not frequency:
                continue
            n_q = document_frequency[term]
            idf = math.log(1 + (total - n_q + 0.5) / (n_q + 0.5))
            norm = frequency * (k1 + 1)
            denom = frequency + k1 * (1 - b + b * lengths[index] / avg_length)
            score += idf * norm / denom
        scores[index] = score
    return scores


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _normalise(values: Iterable[float]) -> list[float]:
    values = list(values)
    peak = max(values, default=0.0)
    if peak <= 0:
        return [0.0] * len(values)
    return [value / peak for value in values]


async def embed_query(query: str) -> Optional[list[float]]:
    if not settings.EMBEDDING_MODEL:
        return None
    try:
        vectors = await get_provider().embed([query])
    except Exception:  # noqa: BLE001, retrieval must degrade, never fail hard
        return None
    return vectors[0] if vectors else None


async def embed_article(article: Article) -> Optional[list[float]]:
    """Compute and attach an article's embedding, if a model is configured."""
    if not settings.EMBEDDING_MODEL:
        return None
    text = f"{article.title}\n\n{article.summary or ''}\n\n{article.body}"[:8000]
    try:
        vectors = await get_provider().embed([text])
    except Exception:  # noqa: BLE001, indexing does not have to succeed
        return None
    return vectors[0] if vectors else None


async def search(
    db: AsyncSession,
    workspace_id: str,
    query: str,
    *,
    limit: int = 5,
    include_internal: bool = True,
    min_score: float = 0.05,
    min_coverage: float = 0.15,
) -> list[Hit]:
    """Rank published articles for a query. Returns at most `limit` hits."""
    query = (query or "").strip()
    if not query:
        return []

    statement = select(Article).where(
        Article.workspace_id == workspace_id,
        Article.status == "published",
    )
    if not include_internal:
        statement = statement.where(Article.visibility == "public")

    articles = list((await db.execute(statement)).scalars())
    if not articles:
        return []

    documents = [_document_text(article) for article in articles]
    lexical = _normalise(bm25_scores(query, documents))

    semantic = [0.0] * len(articles)
    vector = await embed_query(query)
    if vector:
        semantic = _normalise(
            cosine(vector, article.embedding or []) if article.embedding else 0.0
            for article in articles
        )
        blended = [
            _LEXICAL_WEIGHT * lex + _SEMANTIC_WEIGHT * sem
            for lex, sem in zip(lexical, semantic, strict=True)
        ]
    else:
        blended = lexical

    coverage = _coverage_scores(query, documents)
    hits = [
        Hit(article=article, score=round(score, 4), coverage=cover)
        for article, score, cover in zip(articles, blended, coverage, strict=True)
        if score >= min_score
    ]
    hits = [hit for hit in hits if hit.coverage >= min_coverage]
    hits.sort(key=lambda hit: hit.score, reverse=True)
    return hits[:limit]


def _coverage_scores(query: str, documents: Sequence[str]) -> list[float]:
    """How much of the question each document actually covers, from 0 to 1."""
    terms = list(dict.fromkeys(tokenize(query)))
    if not terms or not documents:
        return [0.0] * len(documents)

    present = [set(tokenize(doc)) for doc in documents]
    total = len(documents)
    weights = {}
    for term in terms:
        seen = sum(1 for words in present if term in words)
        # Same shape as the BM25 idf, so the two agree on what is informative.
        idf = math.log(1 + (total - seen + 0.5) / (seen + 0.5))
        weights[term] = max(idf, _MIN_TERM_WEIGHT)

    scores = []
    for words in present:
        matched = sum(weights[term] for term in terms if term in words)
        scores.append(round(matched / (matched + _COVERAGE_MIDPOINT), 4))
    return scores
