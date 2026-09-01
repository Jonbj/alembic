-- Migration 058: daily fit of effective portfolio cycles to the real session (#428).
--
-- One row per Alpaca session makes the open/close coverage observable across
-- container restarts. The source cycles are the rows already persisted in
-- portfolio_cycles: market-closed and other pre-flight skips never reach that
-- table, so they cannot be mistaken for effective cycles.

CREATE TABLE IF NOT EXISTS portfolio_session_grid_metrics (
    session_date            DATE NOT NULL,
    session_open            TIMESTAMPTZ NOT NULL,
    session_close           TIMESTAMPTZ NOT NULL,
    first_effective_cycle   TIMESTAMPTZ,
    last_effective_cycle    TIMESTAMPTZ,
    open_gap_minutes        DOUBLE PRECISION,
    close_gap_minutes       DOUBLE PRECISION,
    threshold_minutes       DOUBLE PRECISION NOT NULL,
    alert_required          BOOLEAN NOT NULL,
    measured_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (session_date),
    CHECK (session_close > session_open),
    CHECK (open_gap_minutes IS NULL OR open_gap_minutes >= 0),
    CHECK (close_gap_minutes IS NULL OR close_gap_minutes >= 0),
    CHECK (threshold_minutes > 0)
);
