"""LLM per-model response endpoint."""
from typing import Annotated

from fastapi import APIRouter, Depends

from src.api.deps import get_pg_store
from src.store.pg_store import PostgreSQLStore

router = APIRouter(prefix="/api/llm")


@router.get("/feedback")
def get_llm_feedback(
    pg: Annotated[PostgreSQLStore, Depends(get_pg_store)],
    limit: int = 50,
    ticker: str | None = None,
    model_id: str | None = None,
) -> list[dict]:
    """Return per-model LLM outputs for processed articles."""
    return pg.get_llm_feedback(limit=min(limit, 200), ticker=ticker, model_id=model_id)
