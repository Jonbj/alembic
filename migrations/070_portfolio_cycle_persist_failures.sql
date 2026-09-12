-- Migration 066: forensic ledger for failed portfolio_cycles inserts (#469).
--
-- On 2026-09-01, thirty-two INSERT attempts on portfolio_cycles were rolled
-- back between the 15:37 and 15:52 UTC cycles; the only surviving trace was
-- the gap in the id sequence, because _persist_cycle_result swallowed the
-- error and the container logs did not survive the next restart (#407).
-- This append-only table records every failed attempt with its error class
-- and the cycle payload, so a blind cycle is reconstructible without the logs.
-- Observability only: nothing in sentiment or execution reads it.

CREATE TABLE IF NOT EXISTS portfolio_cycle_persist_failures (
    id              BIGSERIAL PRIMARY KEY,
    failed_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    cycle_timestamp TIMESTAMPTZ,
    orders_count    INTEGER,
    error_class     VARCHAR(40) NOT NULL,
    error_message   TEXT,
    payload         JSONB
);

CREATE INDEX IF NOT EXISTS idx_portfolio_cycle_persist_failures_at
    ON portfolio_cycle_persist_failures (failed_at DESC);

COMMENT ON TABLE portfolio_cycle_persist_failures IS
    'Append-only ledger of failed portfolio_cycles inserts, with error class and cycle payload (#469); observability only.';