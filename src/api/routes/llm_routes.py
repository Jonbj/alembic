"""LLM per-model response endpoint."""
from typing import Annotated

from fastapi import APIRouter, Depends

from src.api.auth import require_api_key
from src.api.deps import get_pg_store, get_redis_store
from src.llm.model_registry import sentiment_model_payload
from src.store.pg_store import PostgreSQLStore
from src.store.redis_store import RedisStore

router = APIRouter(prefix="/api/llm", dependencies=[Depends(require_api_key)])


@router.get("/feedback")
def get_llm_feedback(
    pg: Annotated[PostgreSQLStore, Depends(get_pg_store)],
    limit: int = 50,
    ticker: str | None = None,
    model_id: str | None = None,
) -> list[dict]:
    """Return per-model LLM outputs for processed articles."""
    return pg.get_llm_feedback(limit=min(limit, 200), ticker=ticker, model_id=model_id)


@router.get("/models")
def get_llm_models(
    redis: Annotated[RedisStore, Depends(get_redis_store)],
) -> dict:
    """Return the current sentiment model registry and active selection."""
    return sentiment_model_payload(redis.get_llm_models() or "all")
