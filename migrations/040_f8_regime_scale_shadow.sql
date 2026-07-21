-- 040_f8_regime_scale_shadow.sql
-- #32: persist the per-cycle F8 regime_scale shadow. Previously the shadow was
-- only logged + kept in a 48h-TTL Redis key, so no trajectory survived for the
-- flip decision (the deadline's "evaluate the shadow trajectory" could only be
-- reconstructed, not looked up). One row per scaled strategy per cycle. Written
-- whenever a non-identity scale is in play, regardless of apply_regime_scale.
SET lock_timeout = '2s';

CREATE TABLE IF NOT EXISTS f8_regime_scale_shadow (
    id              BIGSERIAL PRIMARY KEY,
    cycle_ts        TIMESTAMPTZ NOT NULL,
    strategy        TEXT NOT NULL,
    scale           DOUBLE PRECISION,
    unscaled_weight DOUBLE PRECISION,
    scaled_weight   DOUBLE PRECISION,
    applied         BOOLEAN,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_f8_shadow_strategy_time
    ON f8_regime_scale_shadow (strategy, cycle_ts DESC);
