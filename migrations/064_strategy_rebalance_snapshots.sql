-- Migration 064: snapshot persistente dei ribilanciamenti di strategia (#489).
--
-- Redis conserva soltanto l'ultimo target S1 e lo sovrascrive al mese
-- successivo. Questa tabella append-only rende osservabili segnale, target e
-- stato del portafoglio nel momento esatto in cui la strategia decide. Non e'
-- letta dal path di esecuzione e non modifica alcun parametro di strategia.

CREATE TABLE IF NOT EXISTS strategy_rebalance_snapshots (
    id                      BIGSERIAL PRIMARY KEY,
    strategy_id             TEXT NOT NULL,
    rebalance_ts            TIMESTAMPTZ NOT NULL,
    symbol                  TEXT NOT NULL,
    signal_z                DOUBLE PRECISION,
    weight                  DOUBLE PRECISION NOT NULL CHECK (weight >= 0),
    in_target               BOOLEAN NOT NULL,
    held                    BOOLEAN NOT NULL,
    position_market_value   DOUBLE PRECISION,
    target_notional         DOUBLE PRECISION NOT NULL CHECK (target_notional >= 0),
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (strategy_id, rebalance_ts, symbol)
);

CREATE INDEX IF NOT EXISTS idx_strategy_rebalance_snapshots_lookup
    ON strategy_rebalance_snapshots (strategy_id, rebalance_ts DESC);

COMMENT ON TABLE strategy_rebalance_snapshots IS
    'Una riga per simbolo a ogni decisione di ribilanciamento; misura append-only #489.';
