-- Migration 025: strategy_lifecycle — single source of truth for strategy mode/state.
--
-- Each row tracks one strategy's current governance state. This table is the
-- canonical source; config/strategies.yaml is the bootstrap seed only.
--
-- mode values: 'live' | 'supervised_paper' | 'paper' | 'research' | 'disabled'
-- target_mode: desired next state (pending approval); NULL when no transition pending
-- gate_report_id: references the backtest run whose gates must pass before promotion
-- promoted_by / promoted_at: who approved the last mode change and when
-- approved: explicit human sign-off (True = gates passed + human approved)

CREATE TABLE IF NOT EXISTS strategy_lifecycle (
    strategy_id     TEXT        NOT NULL PRIMARY KEY,
    mode            TEXT        NOT NULL DEFAULT 'paper'
                    CHECK (mode IN ('live', 'supervised_paper', 'paper', 'research', 'disabled')),
    target_mode     TEXT        NULL
                    CHECK (target_mode IS NULL OR target_mode IN ('live', 'supervised_paper', 'paper', 'research', 'disabled')),
    gate_report_id  TEXT        NULL,
    promoted_by     TEXT        NULL,
    promoted_at     TIMESTAMPTZ NULL,
    approved        BOOLEAN     NOT NULL DEFAULT FALSE,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Seed with current known strategy states (matches config/strategies.yaml at 2026-06-19).
-- ON CONFLICT DO NOTHING preserves any manually-set state if re-run.
INSERT INTO strategy_lifecycle (strategy_id, mode, approved, promoted_by)
VALUES
    ('S1', 'supervised_paper', FALSE, 'bootstrap'),
    ('S2', 'disabled',         TRUE,  'bootstrap'),
    ('S4', 'paper',            FALSE, 'bootstrap')
ON CONFLICT (strategy_id) DO NOTHING;
