-- Migration 059: per-cycle ensemble health metric (#427).
--
-- One row per SentimentWorker Celery run, capturing the empirical breakdown
-- of how signals were produced:
--   - n_ensemble: signals backed by >=2 models (the design path).
--   - n_single:   signals backed by exactly 1 model ("single:<model>" — partial
--                 outage, #111/#128; still gated for trading trust but not a
--                 full breaker trigger).
--   - n_finbert:  signals backed by FinBERT only (full ensemble outage; the
--                 #128 sizing breaker increments here).
--
-- Aggregate row == len(items) so the three counts must always be consistent
-- with len(results) the worker already returns — the worker writes the row
-- in the same try/finally that produces the dict, so a divergence is a bug.
--
-- Persistence rationale (#427): container logs do not survive restart, and the
-- 2026-08-26/27 outage forensics had to be reconstructed from sentiment_signals
-- plus the divergence log; without this table, "what fraction of the session
-- ran on FinBERT?" is a per-row SQL query each time. A pre-aggregated cycle
-- row turns that into a single range scan, surfaces it on /api/quality/
-- ensemble_health, and gives the existing /quality KPI cards a stable source.
--
-- Backfill: none. sentiment_signals.generated_at remains the canonical
-- per-signal record; this table is a derived rollup written by the worker as
-- it goes. Rows from before the deploy simply don't exist ("not measured",
-- not "zero"), matching the #324/#351/#352 discontinuity pattern.

CREATE TABLE IF NOT EXISTS ensemble_cycle_health (
    id              BIGSERIAL PRIMARY KEY,
    cycle_started_at TIMESTAMPTZ NOT NULL,
    cycle_ended_at   TIMESTAMPTZ NOT NULL,
    n_ensemble       INTEGER NOT NULL CHECK (n_ensemble >= 0),
    n_single         INTEGER NOT NULL CHECK (n_single >= 0),
    n_finbert        INTEGER NOT NULL CHECK (n_finbert >= 0),
    aggregate        INTEGER NOT NULL CHECK (aggregate >= 0),
    rth              BOOLEAN NOT NULL,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chk_ensemble_cycle_health_totals
        CHECK (n_ensemble + n_single + n_finbert = aggregate),
    CONSTRAINT chk_ensemble_cycle_health_window
        CHECK (cycle_ended_at >= cycle_started_at)
);

CREATE INDEX IF NOT EXISTS idx_ensemble_cycle_health_started_at
    ON ensemble_cycle_health (cycle_started_at DESC);

CREATE INDEX IF NOT EXISTS idx_ensemble_cycle_health_rth_started_at
    ON ensemble_cycle_health (cycle_started_at DESC)
    WHERE rth;

COMMENT ON TABLE ensemble_cycle_health IS
    'Per-cycle (one Celery run of run_sentiment_worker) count of full-ensemble '
    'vs single-model vs FinBERT signals (#427). Pure observability rollup — '
    'not read by execution, sizing, or any money-path code. Rows before the '
    'deploy date are absent (= not measured), not zero.';
