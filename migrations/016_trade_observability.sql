-- migrations/016_trade_observability.sql

-- 1a. Link sentiment_signals to the news article that triggered them
ALTER TABLE sentiment_signals
    ADD COLUMN IF NOT EXISTS news_log_id BIGINT
        REFERENCES news_log(id) ON DELETE SET NULL;

-- 1b. Execution decision log (one row per symbol per tick, score > threshold only)
CREATE TABLE IF NOT EXISTS execution_decisions (
    id           BIGSERIAL PRIMARY KEY,
    tick_time    TIMESTAMPTZ NOT NULL,
    symbol       VARCHAR(20) NOT NULL,
    signal_id    BIGINT REFERENCES sentiment_signals(id) ON DELETE SET NULL,
    score        DOUBLE PRECISION NOT NULL,
    regime_mult  DOUBLE PRECISION NOT NULL,
    ema_pass     BOOLEAN NOT NULL,
    decision     VARCHAR(20) NOT NULL,
    order_id     TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_execution_decisions_tick
    ON execution_decisions (tick_time DESC);
CREATE INDEX IF NOT EXISTS idx_execution_decisions_symbol
    ON execution_decisions (symbol, tick_time DESC);

-- 1c. Per-trade P&L tracking
CREATE TABLE IF NOT EXISTS trades (
    id               BIGSERIAL PRIMARY KEY,
    symbol           VARCHAR(20) NOT NULL,
    signal_id        BIGINT REFERENCES sentiment_signals(id) ON DELETE SET NULL,
    decision_id      BIGINT REFERENCES execution_decisions(id) ON DELETE SET NULL,
    entry_order_id   TEXT NOT NULL,
    entry_price      DOUBLE PRECISION,
    entry_time       TIMESTAMPTZ NOT NULL,
    entry_notional   DOUBLE PRECISION NOT NULL,
    score            DOUBLE PRECISION NOT NULL,
    regime_mult      DOUBLE PRECISION NOT NULL,
    exit_order_id    TEXT,
    exit_price       DOUBLE PRECISION,
    exit_time        TIMESTAMPTZ,
    exit_reason      VARCHAR(20),
    qty              DOUBLE PRECISION,
    gross_pnl        DOUBLE PRECISION,
    slippage_est     DOUBLE PRECISION,
    net_pnl          DOUBLE PRECISION,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_trades_symbol
    ON trades (symbol, entry_time DESC);
CREATE INDEX IF NOT EXISTS idx_trades_open
    ON trades (symbol) WHERE exit_time IS NULL;
CREATE INDEX IF NOT EXISTS idx_trades_closed
    ON trades (exit_time DESC) WHERE exit_time IS NOT NULL;
