"""The knowledge base, which is the source every AI answer is grounded in."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from ..ai import retrieval
from ..models import Article
from ..schemas import ArticleIn, ArticleOut, ArticlePatch, SearchHit
from ..security import CurrentUser, DbDep, Manager, is_manager

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


async def _get(db, workspace_id: str, article_id: str) -> Article:
    article = await db.get(Article, article_id)
    if article is None or article.workspace_id != workspace_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Article not found")
    return article


@router.get("/search", response_model=list[SearchHit])
async def search_articles(
    user: CurrentUser,
    db: DbDep,
    q: str = Query(min_length=1),
    limit: int = Query(default=5, ge=1, le=20),
) -> list[SearchHit]:
    """Rank published articles for a query, the same way the AI does."""
    hits = await retrieval.search(db, user.workspace_id, q, limit=limit)
    return [
        SearchHit(
            article_id=hit.article.id,
            title=hit.article.title,
            excerpt=hit.excerpt(q),
            category=hit.article.category,
            score=hit.score,
        )
        for hit in hits
    ]


@router.get("/categories", response_model=list[str])
async def list_categories(user: CurrentUser, db: DbDep) -> list[str]:
    rows = await db.execute(
        select(Article.category).where(Article.workspace_id == user.workspace_id).distinct()
    )
    return sorted({row for row in rows.scalars() if row})


@router.get("", response_model=list[ArticleOut])
async def list_articles(
    user: CurrentUser,
    db: DbDep,
    status_filter: Optional[str] = Query(default=None, alias="status"),
    category: Optional[str] = None,
) -> list[ArticleOut]:
    statement = (
        select(Article)
        .where(Article.workspace_id == user.workspace_id)
        .order_by(Article.updated_at.desc())
    )
    if status_filter:
        statement = statement.where(Article.status == status_filter)
    if category:
        statement = statement.where(Article.category == category)
    return [ArticleOut.model_validate(a) for a in (await db.execute(statement)).scalars()]


@router.post("", response_model=ArticleOut, status_code=status.HTTP_201_CREATED)
async def create_article(payload: ArticleIn, user: CurrentUser, db: DbDep) -> ArticleOut:
    """Write a new article. Agents get a draft, supervisors can publish."""
    fields = payload.model_dump()
    if fields.get("status") == "published" and not is_manager(user):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Publishing an article is a supervisor action. Save it as a draft "
            "and ask a supervisor to review it.",
        )
    article = Article(
        workspace_id=user.workspace_id,
        author_name=user.name,
        **fields,
    )
    db.add(article)
    await db.flush()
    await _reindex(db, article)
    return ArticleOut.model_validate(article)


@router.get("/{article_id}", response_model=ArticleOut)
async def get_article(article_id: str, user: CurrentUser, db: DbDep) -> ArticleOut:
    return ArticleOut.model_validate(await _get(db, user.workspace_id, article_id))


@router.patch("/{article_id}", response_model=ArticleOut)
async def update_article(
    article_id: str, payload: ArticlePatch, user: CurrentUser, db: DbDep
) -> ArticleOut:
    """Revise an article. A published one is live to customers, so it is locked."""
    article = await _get(db, user.workspace_id, article_id)
    updates = payload.model_dump(exclude_unset=True)
    if not is_manager(user):
        if article.status == "published":
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                "This article is published, so the assistant is already quoting "
                "it to customers. Only a supervisor can change it.",
            )
        if updates.get("status") == "published":
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                "Publishing an article is a supervisor action.",
            )
    for field, value in updates.items():
        setattr(article, field, value)
    # Any content edit is a new version, so agents can see what changed when.
    if {"title", "body", "summary"} & updates.keys():
        article.version += 1
        await _reindex(db, article)
    await db.flush()
    return ArticleOut.model_validate(article)


@router.delete("/{article_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_article(article_id: str, user: Manager, db: DbDep) -> None:
    """Remove an article for good. Supervisors only."""
    await db.delete(await _get(db, user.workspace_id, article_id))


async def _reindex(db, article: Article) -> None:
    """Refresh the cached embedding. It does nothing unless a model is configured."""
    vector = await retrieval.embed_article(article)
    if vector:
        article.embedding = vector
        await db.flush()
