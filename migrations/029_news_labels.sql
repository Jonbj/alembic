-- migrations/029_news_labels.sql
-- Golden label set (QX-01) for measuring ticker extraction + sentiment quality.
--
-- One row per distinct ARTICLE (url), NOT per (url, ticker): the human annotates the
-- article once and lists ALL ground-truth tickers, so extraction precision/recall is
-- measured per article. extracted_tickers holds the system's tickers for comparison
-- (never shown during blind annotation). Forward returns are populated automatically
-- from Alpaca historical bars (point-in-time from published_at). Read-only / offline:
-- never used in the hot execution path (Alpha Miner preserved).

CREATE TABLE IF NOT EXISTS news_labels (
    label_id              BIGSERIAL PRIMARY KEY,
    url                   TEXT NOT NULL UNIQUE,
    source                TEXT,
    title                 TEXT,
    body_snippet          TEXT,
    published_at          TIMESTAMPTZ,
    extracted_tickers     TEXT[] NOT NULL DEFAULT '{}',  -- system extraction (for comparison)

    status                TEXT NOT NULL DEFAULT 'pending',  -- pending | labeled
    annotator_id          TEXT,
    label_date            TIMESTAMPTZ,

    -- Ground truth (human, blind): annotator does not see extracted_tickers.
    gt_tickers            TEXT[],                            -- [] = not company-specific
    gt_relevance          TEXT,                              -- company_specific|sector|macro|irrelevant
    gt_sentiment_dir      TEXT,                              -- positive|negative|neutral
    gt_sentiment_strength DOUBLE PRECISION,                  -- [-1, 1]
    gt_rationale          TEXT,
    text_adequacy         TEXT,                              -- full|headline_only|insufficient

    -- Forward returns (auto, Alpaca historical; point-in-time from published_at).
    forward_return_1h     DOUBLE PRECISION,
    forward_return_1d     DOUBLE PRECISION,
    forward_return_2d     DOUBLE PRECISION,
    price_source          TEXT,

    created_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_news_labels_status ON news_labels (status);
