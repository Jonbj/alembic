-- #358: separa un timeout da un errore di parsing nei dati del confronto Stage-2.
-- Prima erano entrambi parse_error=TRUE con reasoning NULL, e distinguerli
-- richiedeva di ispezionare a mano la distribuzione delle latenze — motivo per
-- cui un 100% di timeout e' rimasto invisibile per sei settimane.

ALTER TABLE llm_shadow_responses
    ADD COLUMN IF NOT EXISTS failure_reason TEXT;

COMMENT ON COLUMN llm_shadow_responses.failure_reason IS
    'NULL su successo; "timeout" oppure "error:<Tipo>" su fallimento (#358). '
    'Le righe precedenti al 2026-08-25 restano NULL anche quando parse_error e '
    'TRUE: NULL qui significa "non classificato", non "successo" — usare '
    'parse_error per sapere se la riga e'' valida.';

CREATE INDEX IF NOT EXISTS idx_shadow_failure_reason
    ON llm_shadow_responses (model_id, failure_reason)
    WHERE parse_error;
