"""News log endpoint."""
from typing import Annotated

from fastapi import APIRouter, Depends

from src.api.auth import require_api_key
from src.api.deps import get_pg_store
from src.store.pg_store import PostgreSQLStore

router = APIRouter(prefix="/api/news", dependencies=[Depends(require_api_key)])


@router.get("/recent")
def get_news_recent(
    pg: Annotated[PostgreSQLStore, Depends(get_pg_store)],
    limit: int = 100,
    ticker: str | None = None,
    source: str | None = None,
) -> list[dict]:
    """Return recent news articles processed by the sentiment pipeline."""
    return pg.get_news_recent(limit=min(limit, 500), ticker=ticker, source=source)


@router.get("/source-quality")
def get_news_source_quality(
    pg: Annotated[PostgreSQLStore, Depends(get_pg_store)],
    days: int = 30,
) -> list[dict]:
    """Return per-source quality and downstream conversion metrics."""
    return pg.get_news_source_quality(days=min(max(days, 1), 365))
