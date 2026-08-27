-- #374: la proiezione P0 corrente deve essere l'ultima scritta, non una a caso.
--
-- `s4_exit_policy_current` sceglieva con
-- `ORDER BY observed_at DESC, <priorita' di status> DESC, event_id DESC`.
-- Due proiezioni dello stesso identico close runtime — quella sbagliata e la
-- sua correzione — condividono `observed_at` (l'ora dell'uscita, non l'ora in
-- cui l'abbiamo osservata) e `status`, quindi il pareggio si rompeva su
-- `event_id DESC`: un UUID v5, cioe' un ordine arbitrario. Una correzione
-- poteva perdere contro la riga che correggeva.
--
-- `created_at DESC` rende il criterio quello vero: a parita' di evento di
-- mercato vince la proiezione scritta piu' di recente. Resta dopo la priorita'
-- di status, cosi' uno snapshot OPEN non scavalca un CLOSED dello stesso
-- istante solo perche' riscritto dopo.
--
-- La tabella resta append-only: nessuna riga viene modificata o cancellata.

DROP VIEW IF EXISTS s4_p0_residuals;
DROP VIEW IF EXISTS s4_p0_validation;
DROP VIEW IF EXISTS s4_exit_policy_current;

CREATE VIEW s4_exit_policy_current AS
SELECT DISTINCT ON (intent_id, policy_id) *
FROM s4_exit_policy_events
ORDER BY
    intent_id,
    policy_id,
    observed_at DESC,
    CASE status
        WHEN 'CLOSED' THEN 4
        WHEN 'RISK_EXITED' THEN 4
        WHEN 'OPEN' THEN 3
        WHEN 'TRIGGERED' THEN 2
        ELSE 1
    END DESC,
    created_at DESC,
    event_id DESC;

CREATE VIEW s4_p0_validation AS
SELECT
    COALESCE(d0, observed_at::date) AS lifecycle_date,
    COUNT(*) AS total,
    COUNT(*) FILTER (WHERE comparable) AS comparable,
    COUNT(*) FILTER (WHERE NOT comparable) AS residual,
    COUNT(*) FILTER (WHERE comparable)::DOUBLE PRECISION
        / NULLIF(COUNT(*), 0) AS coverage
FROM s4_exit_policy_current
WHERE policy_id = 'P0'
GROUP BY COALESCE(d0, observed_at::date);

CREATE VIEW s4_p0_residuals AS
SELECT
    COALESCE(d0, observed_at::date) AS lifecycle_date,
    reason_code,
    residual.divergence_reason,
    COUNT(*) AS lifecycle_count
FROM s4_exit_policy_current
JOIN LATERAL unnest(divergence_reasons) AS residual(divergence_reason) ON TRUE
WHERE policy_id = 'P0' AND NOT comparable
GROUP BY COALESCE(d0, observed_at::date), reason_code, residual.divergence_reason;
