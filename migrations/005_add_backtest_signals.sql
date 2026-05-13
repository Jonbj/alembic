-- migrations/005_add_backtest_signals.sql
CREATE TABLE IF NOT EXISTS backtest_signals (
    id                   SERIAL PRIMARY KEY,
    run_id               TEXT NOT NULL,
    symbol               TEXT NOT NULL,
    article_title        TEXT NOT NULL DEFAULT '',
    article_url          TEXT NOT NULL DEFAULT '',
    score                DOUBLE PRECISION,
    confidence           DOUBLE PRECISION,
    reasoning            TEXT,
    model_id             TEXT,
    ensemble_std         DOUBLE PRECISION,
    fallback_used        BOOLEAN NOT NULL DEFAULT FALSE,
    generated_at         TIMESTAMPTZ NOT NULL,
    forward_return_1h    DOUBLE PRECISION,
    forward_return_4h    DOUBLE PRECISION,
    forward_return_24h   DOUBLE PRECISION
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_backtest_signals_dedup
    ON backtest_signals (run_id, symbol, article_url, generated_at);

CREATE INDEX IF NOT EXISTS idx_backtest_signals_run_id
    ON backtest_signals (run_id, symbol, generated_at);

CREATE INDEX IF NOT EXISTS idx_backtest_signals_pending
    ON backtest_signals (run_id, score)
    WHERE score IS NULL;
