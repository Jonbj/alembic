"""Golden label set (QX-01) annotation endpoints — offline/admin only.

Blind annotation: GET /next returns the article text WITHOUT the system's extracted
tickers (so the annotator's ground truth is unbiased). POST saves the human judgment.
Never in the hot execution path (Alpha Miner preserved).
"""
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from src.api.auth import require_api_key

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/labeling", dependencies=[Depends(require_api_key)])

_RELEVANCE = {"company_specific", "sector", "macro", "irrelevant"}
_DIRECTION = {"positive", "negative", "neutral"}


class LabelSubmit(BaseModel):
    gt_tickers: list[str] = Field(default_factory=list)  # [] = not company-specific
    gt_relevance: str
    gt_sentiment_dir: str
    gt_sentiment_strength: float = Field(ge=-1.0, le=1.0)
    gt_rationale: str = ""
    text_adequacy: str | None = None
    annotator_id: str = "operator"


def _store():
    from src.store.pg_store import PostgreSQLStore
    return PostgreSQLStore()


@router.get("/progress")
def progress() -> dict:
    """Labeled / pending / total counts."""
    with _store() as store:
        with store._get_connection().cursor() as cur:
            cur.execute(
                "SELECT status, COUNT(*) FROM news_labels GROUP BY status"
            )
            counts = {row[0]: row[1] for row in cur.fetchall()}
    labeled = counts.get("labeled", 0)
    pending = counts.get("pending", 0)
    return {"labeled": labeled, "pending": pending, "total": labeled + pending}


@router.get("/next")
def next_item() -> dict:
    """Next pending article to annotate — BLIND (no extracted tickers)."""
    with _store() as store:
        with store._get_connection().cursor() as cur:
            cur.execute(
                """SELECT label_id, source, title, body_snippet, published_at, text_adequacy
                   FROM news_labels WHERE status = 'pending'
                   ORDER BY (text_adequacy = 'full') DESC, label_id LIMIT 1"""
            )
            row = cur.fetchone()
    if row is None:
        return {"done": True}
    return {
        "done": False,
        "label_id": row[0],
        "source": row[1],
        "title": row[2],
        "body_snippet": row[3],
        "published_at": row[4].isoformat() if row[4] else None,
        "text_adequacy": row[5],
    }


@router.post("/{label_id}")
def submit(label_id: int, body: LabelSubmit) -> dict:
    """Save the human ground-truth for one article; marks it labeled."""
    if body.gt_relevance not in _RELEVANCE:
        raise HTTPException(422, f"gt_relevance must be one of {sorted(_RELEVANCE)}")
    if body.gt_sentiment_dir not in _DIRECTION:
        raise HTTPException(422, f"gt_sentiment_dir must be one of {sorted(_DIRECTION)}")
    with _store() as store:
        conn = store._get_connection()
        with conn.cursor() as cur:
            cur.execute(
                """UPDATE news_labels
                   SET gt_tickers=%s, gt_relevance=%s, gt_sentiment_dir=%s,
                       gt_sentiment_strength=%s, gt_rationale=%s,
                       text_adequacy=COALESCE(%s, text_adequacy),
                       annotator_id=%s, label_date=%s, status='labeled'
                   WHERE label_id=%s AND status='pending'
                   RETURNING label_id""",
                ([t.strip().upper() for t in body.gt_tickers], body.gt_relevance,
                 body.gt_sentiment_dir, body.gt_sentiment_strength, body.gt_rationale,
                 body.text_adequacy, body.annotator_id,
                 datetime.now(timezone.utc), label_id),
            )
            updated = cur.fetchone()
        conn.commit()
    if updated is None:
        raise HTTPException(404, "label not found or already labeled")
    return {"label_id": label_id, "status": "labeled"}
