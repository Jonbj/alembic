-- Migration 066: trial ledger append-only del trial exit S4 (#299, criterio 5).
--
-- Ogni variante valutata dal valutatore confirmatory su una finestra resta
-- registrata, con il ruolo che aveva al momento della valutazione. Alla
-- decision analysis la molteplicita' esplorata dev'essere ricostruibile dal
-- database, non dalla memoria di chi ha guardato il report: e' l'unica difesa
-- contro una diagnostica che torna come confirmatory su un campione che non
-- e' piu' out-of-sample.
--
-- Il report e' idempotente per costruzione: `ledger_id` e' il fingerprint
-- uuid5 di (finestra, variante), quindi rieseguire la stessa finestra non
-- aggiunge righe ne' molteplicita'. Nessun parametro di taratura vive qui,
-- e la tabella non e' letta dal path di esecuzione.

CREATE TABLE IF NOT EXISTS s4_trial_ledger (
    ledger_id     UUID PRIMARY KEY,
    window_start  DATE NOT NULL,
    window_end    DATE NOT NULL,
    variant       TEXT NOT NULL,
    role          TEXT NOT NULL CHECK (role IN ('confirmatory', 'diagnostic')),
    notes         TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (window_start, window_end, variant, role)
);

CREATE INDEX IF NOT EXISTS idx_s4_trial_ledger_window
    ON s4_trial_ledger (window_start, window_end);

CREATE OR REPLACE FUNCTION prevent_s4_trial_ledger_mutation()
RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 's4_trial_ledger is append-only';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS s4_trial_ledger_append_only ON s4_trial_ledger;
CREATE TRIGGER s4_trial_ledger_append_only
    BEFORE UPDATE OR DELETE ON s4_trial_ledger
    FOR EACH ROW EXECUTE FUNCTION prevent_s4_trial_ledger_mutation();

COMMENT ON TABLE s4_trial_ledger IS
    'Varianti viste dal valutatore confirmatory per finestra; append-only #299.';