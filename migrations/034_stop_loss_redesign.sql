-- Migration 034: Stop-Loss Redesign (F9a)
-- Freeze-at-entry stop params on each trade row. Pre-migration open trades keep NULLs
-- and fall back to the legacy fixed-2% StopPolicy path.
-- All DDL is idempotent (IF NOT EXISTS).

ALTER TABLE trades
    ADD COLUMN IF NOT EXISTS stop_strategy      TEXT,
    ADD COLUMN IF NOT EXISTS stop_mode          TEXT,              -- fixed | vol_scaled
    ADD COLUMN IF NOT EXISTS stop_vol_at_entry  DOUBLE PRECISION,  -- sigma_eff frozen at entry
    ADD COLUMN IF NOT EXISTS stop_k             DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS stop_floor         DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS stop_cap           DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS stop_d_init        DOUBLE PRECISION,  -- clipped protective distance
    ADD COLUMN IF NOT EXISTS stop_vol_source    TEXT;              -- bars_df | last_good | asset_median | tier | default

-- One row per actual protective-stop fire (low volume; actual closes).
CREATE TABLE IF NOT EXISTS stop_decisions (
    id              BIGSERIAL PRIMARY KEY,
    trade_id        BIGINT REFERENCES trades(id),
    symbol          TEXT NOT NULL,
    strategy        TEXT,
    mode            TEXT NOT NULL,              -- fixed | vol_scaled
    entry_price     DOUBLE PRECISION,
    observed_price  DOUBLE PRECISION,
    trigger_price   DOUBLE PRECISION,
    d_init          DOUBLE PRECISION,
    vol_at_entry    DOUBLE PRECISION,
    sigma_eff       DOUBLE PRECISION,
    k               DOUBLE PRECISION,
    floor           DOUBLE PRECISION,
    cap             DOUBLE PRECISION,
    price_source    TEXT,                       -- market.prices | bid | ...
    vol_source      TEXT,                       -- see fallback hierarchy
    exit_order_id   TEXT,
    cycle_ts        TIMESTAMPTZ NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS stop_decisions_symbol_ts ON stop_decisions(symbol, cycle_ts);

-- Per-cycle shadow log (high volume; only when risk.stop_shadow_enabled=true).
-- Logs BOTH fixed and vol_scaled triggers for every held position each cycle.
CREATE TABLE IF NOT EXISTS stop_shadow_log (
    id                       BIGSERIAL PRIMARY KEY,
    cycle_ts                 TIMESTAMPTZ NOT NULL,
    symbol                   TEXT NOT NULL,
    strategy                 TEXT,
    entry_price              DOUBLE PRECISION,
    observed_price           DOUBLE PRECISION,
    vol_at_entry             DOUBLE PRECISION,
    sigma_eff                DOUBLE PRECISION,
    vol_source               TEXT,
    d_init_fixed             DOUBLE PRECISION,  -- legacy fixed (risk.stop_loss)
    trigger_fixed            DOUBLE PRECISION,
    would_breach_fixed       BOOLEAN,
    d_init_vol_scaled        DOUBLE PRECISION,
    trigger_vol_scaled       DOUBLE PRECISION,
    would_breach_vol_scaled  BOOLEAN,
    created_at               TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS stop_shadow_symbol_ts ON stop_shadow_log(symbol, cycle_ts);
