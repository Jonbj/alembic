-- migrations/031_news_resolved_entities.sql
-- Resolver SHADOW (Fase A): persist the deterministic ticker-resolution verdict for each
-- news candidate WITHOUT gating the live signal. Lets us measure resolver precision vs
-- news_labels before any enforcement (QX-01). Additive; never read by the hot path.

CREATE TABLE IF NOT EXISTS news_resolved_entities (
    id                    BIGSERIAL PRIMARY KEY,
    news_log_id           BIGINT,
    url                   TEXT,
    candidate_ticker      TEXT NOT NULL,         -- the extracted ticker fed to the resolver
    extraction_method     TEXT,                  -- source_metadata | cashtag | org_lookup | regex

    -- Resolver verdict (src/connectors/ticker_resolver.py)
    decision              TEXT NOT NULL,         -- RESOLVED | NO_TRADE_*
    resolved_ticker       TEXT,
    resolution_confidence DOUBLE PRECISION,
    ambiguity_margin      DOUBLE PRECISION,
    directness            TEXT,
    tradable              BOOLEAN,
    exchange              TEXT,
    figi                  TEXT,

    -- Evidence used (for audit / debugging the verdict)
    source_ticker_match   BOOLEAN,
    alias_match           BOOLEAN,
    sec_openfigi_match    BOOLEAN,
    llm_agreement         BOOLEAN,

    created_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_news_resolved_decision ON news_resolved_entities (decision);
CREATE INDEX IF NOT EXISTS idx_news_resolved_candidate ON news_resolved_entities (candidate_ticker);
CREATE INDEX IF NOT EXISTS idx_news_resolved_created ON news_resolved_entities (created_at);
