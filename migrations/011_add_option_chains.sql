-- migrations/011_add_option_chains.sql
-- Option chain historical storage for VRP backtesting.
--
-- Primary use: synthetic SPY option chains priced via Black-Scholes (offline mode).
-- Secondary use: live chains ingested from IBKR when TWS is connected.
--
-- Design notes:
--   - UNIQUE(symbol, trade_date, expiry, strike, "right") enables idempotent ON CONFLICT DO NOTHING
--   - idx_option_chains_lookup covers the hot query: chain at (symbol, trade_date)
--   - BRIN on trade_date for efficient multi-year range scans
--   - source distinguishes 'synthetic' (Black-Scholes) from 'ibkr' (live data)

CREATE TABLE IF NOT EXISTS option_chains (
    id               BIGSERIAL PRIMARY KEY,
    symbol           VARCHAR(20)        NOT NULL,
    trade_date       DATE               NOT NULL,
    expiry           DATE               NOT NULL,
    strike           DOUBLE PRECISION   NOT NULL,
    "right"          CHAR(1)            NOT NULL CHECK ("right" IN ('C', 'P')),
    bid              DOUBLE PRECISION,
    ask              DOUBLE PRECISION,
    mid              DOUBLE PRECISION,
    volume           BIGINT,
    open_interest    BIGINT,
    implied_vol      DOUBLE PRECISION,
    delta            DOUBLE PRECISION,
    gamma            DOUBLE PRECISION,
    theta            DOUBLE PRECISION,
    vega             DOUBLE PRECISION,
    underlying_price DOUBLE PRECISION,
    multiplier       INTEGER            NOT NULL DEFAULT 100,
    source           VARCHAR(20)        NOT NULL DEFAULT 'synthetic',
    created_at       TIMESTAMPTZ        NOT NULL DEFAULT now(),

    CONSTRAINT uq_option_chain_row
        UNIQUE (symbol, trade_date, expiry, strike, "right")
);

-- Fast lookup: chain at specific date (< 1s requirement)
CREATE INDEX IF NOT EXISTS idx_option_chains_lookup
    ON option_chains (symbol, trade_date);

-- Range scan over multi-year history
CREATE INDEX IF NOT EXISTS idx_option_chains_date_brin
    ON option_chains USING BRIN (trade_date);

-- Expiry-based queries (e.g. retrieve all options expiring on a given date)
CREATE INDEX IF NOT EXISTS idx_option_chains_expiry
    ON option_chains (symbol, expiry);

COMMENT ON TABLE option_chains IS
    'Historical EOD option chain snapshots. Synthetic (Black-Scholes) and live (IBKR) sources.';
COMMENT ON COLUMN option_chains."right" IS
    'C = call, P = put';
COMMENT ON COLUMN option_chains.source IS
    'synthetic = Black-Scholes priced; ibkr = live IBKR data';
