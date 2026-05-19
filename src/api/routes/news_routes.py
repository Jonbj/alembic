"""News log endpoint."""
from typing import Annotated

from fastapi import APIRouter, Depends

from src.api.deps import get_pg_store
from src.store.pg_store import PostgreSQLStore

router = APIRouter(prefix="/api/news")


@router.get("/recent")
def get_news_recent(
    pg: Annotated[PostgreSQLStore, Depends(get_pg_store)],
    limit: int = 100,
    ticker: str | None = None,
    source: str | None = None,
) -> list[dict]:
    """Return recent news articles processed by the sentiment pipeline."""
    return pg.get_news_recent(limit=min(limit, 500), ticker=ticker, source=source)
