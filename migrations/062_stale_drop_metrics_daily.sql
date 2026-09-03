-- Migration 060: daily stale-drop measurement and alert decision (#432).
--
-- The source events remain news_queue_drops and ingestion_stats_daily. This
-- rollup makes the time series durable across container restarts and records
-- the two causally distinct groups: articles already outside the age window
-- when fetched, and articles that crossed it while waiting in the queue.
-- It is observability only and is never read by sentiment or execution.

CREATE TABLE IF NOT EXISTS stale_drop_metrics_daily (
    day                         DATE NOT NULL,
    source                      VARCHAR(50) NOT NULL,
    queued                      INTEGER NOT NULL CHECK (queued >= 0),
    stale_drops                 INTEGER NOT NULL CHECK (stale_drops >= 0),
    already_stale_at_fetch      INTEGER NOT NULL CHECK (already_stale_at_fetch >= 0),
    went_stale_in_queue         INTEGER NOT NULL CHECK (went_stale_in_queue >= 0),
    unclassified_stale          INTEGER NOT NULL CHECK (unclassified_stale >= 0),
    stale_drop_share            DOUBLE PRECISION CHECK (stale_drop_share >= 0),
    avg_fetch_latency_hours     DOUBLE PRECISION,
    avg_queue_wait_hours        DOUBLE PRECISION,
    max_news_age_hours          DOUBLE PRECISION NOT NULL CHECK (max_news_age_hours > 0),
    alert_threshold             DOUBLE PRECISION NOT NULL CHECK (alert_threshold >= 0),
    alert_required              BOOLEAN NOT NULL,
    measured_at                 TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (day, source),
    CHECK (
        already_stale_at_fetch + went_stale_in_queue + unclassified_stale
        = stale_drops
    )
);

CREATE INDEX IF NOT EXISTS idx_stale_drop_metrics_alerts
    ON stale_drop_metrics_daily (day DESC)
    WHERE alert_required;

COMMENT ON TABLE stale_drop_metrics_daily IS
    'Daily per-source stale-drop share and cause split (#432); observability only.';
