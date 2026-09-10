-- Migration 067: per-event runtime evidence of FinBERT fallbacks (#544).
--
-- One row per full FinBERT fallback (ensemble timeout, divergence, or budget
-- exhausted — model_id='finbert' in sentiment_signals), capturing:
--   - finbert_input: the exact 512-char string FinBERT classified at runtime,
--     with title prepended per the #399 companion fix. This is the evidence
--     the #453 measurement could not produce: its runtime confirmation ("did
--     the fallback actually receive title+body?") had to be deferred because
--     the string existed nowhere except container logs.
--   - title_chars/body_chars: the chars from each component actually present
--     in the capped input (separator excluded), so "title/body included" is
--     checkable without re-deriving the join and truncation rules.
--   - polarity/confidence: the outcome of the FinBERT classification.
--
-- Persistence rationale (#544): `docker logs` dies with the container, and
-- deploy_reconcile.sh rebuilds the backend on every push to main — so the
-- evidence windows of past sessions kept being destroyed (08-26, 09-08
-- 15-16Z per the #453 report). The daily durable logs (#407) cover stdout,
-- but the runtime FinBERT input was never logged at all; a per-event DB row
-- makes the confirmation independent of container lifecycles and joinable
-- with sentiment_signals (signal_id) for the exact news item.
--
-- The other events the issue lists are already persisted elsewhere:
-- Ollama outage windows → ensemble_cycle_health (059, #427); portfolio_cycles
-- INSERT failures → 066 (#469). This table closes the remaining gap.
--
-- Backfill: none. Events before the deploy date are absent (= not measured,
-- not "zero"), matching the #324/#351/#352 discontinuity pattern.

CREATE TABLE IF NOT EXISTS finbert_fallback_events (
    id             BIGSERIAL PRIMARY KEY,
    signal_id      BIGINT,
    symbol         TEXT NOT NULL,
    reason         TEXT NOT NULL,
    title_chars    INTEGER NOT NULL CHECK (title_chars >= 0),
    body_chars     INTEGER NOT NULL CHECK (body_chars >= 0),
    finbert_input  TEXT NOT NULL,
    polarity       DOUBLE PRECISION NOT NULL,
    confidence     DOUBLE PRECISION NOT NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chk_finbert_fallback_input_cap
        CHECK (char_length(finbert_input) <= 512)
);

CREATE INDEX IF NOT EXISTS idx_finbert_fallback_events_created_at
    ON finbert_fallback_events (created_at DESC);

CREATE INDEX IF NOT EXISTS idx_finbert_fallback_events_signal_id
    ON finbert_fallback_events (signal_id);

COMMENT ON TABLE finbert_fallback_events IS
    'Per-event runtime evidence of full FinBERT fallbacks (#544): the exact '
    'string FinBERT classified (title+body, 512-char cap) and its outcome. '
    'Pure observability — not read by execution, sizing, or any money-path '
    'code. Rows before the deploy date are absent (= not measured), not zero.';
