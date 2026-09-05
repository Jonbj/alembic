-- Migration 060: burned S4 ranking slots as a durable measurement (#429).
--
-- The two candidate-time columns are nullable only for pre-deploy rows and for
-- the fail-open case where the open-position snapshot is unavailable. No old
-- event is updated: the append-only trigger introduced by migration 050 stays
-- enabled throughout. The views derive historical values where the existing
-- disposition makes that possible, so 2026-08-27 remains queryable.

ALTER TABLE s4_intent_events
    ADD COLUMN IF NOT EXISTS held_at_rank BOOLEAN,
    ADD COLUMN IF NOT EXISTS signal_age_at_slot INTERVAL;

COMMENT ON COLUMN s4_intent_events.held_at_rank IS
    'Whether the symbol had an open position in the snapshot used by the S4 ranking cycle.';
COMMENT ON COLUMN s4_intent_events.signal_age_at_slot IS
    'decision_slot minus model_generated_at, captured before ranking.';

DROP VIEW IF EXISTS s4_burned_slot_metrics_daily;
DROP VIEW IF EXISTS s4_burned_slot_metrics;
DROP VIEW IF EXISTS s4_tradable_intent_population;
DROP VIEW IF EXISTS s4_candidate_population;

CREATE VIEW s4_candidate_population AS
SELECT *
FROM s4_intent_events
WHERE event_type = 'candidate';

CREATE VIEW s4_tradable_intent_population AS
SELECT
    candidate.*,
    disposition.event_id AS disposition_event_id,
    disposition.rank AS final_rank,
    disposition.reason_code AS final_reason_code,
    disposition.s1_state AS final_s1_state,
    disposition.anti_pyramiding AS final_anti_pyramiding
FROM s4_intent_events AS candidate
JOIN s4_intent_events AS disposition
  ON disposition.intent_id = candidate.intent_id
 AND disposition.event_type = 'disposition'
WHERE candidate.event_type = 'candidate'
  AND disposition.is_tradable IS TRUE;

CREATE VIEW s4_burned_slot_metrics AS
WITH paired AS (
    SELECT
        candidate.decision_slot,
        candidate.symbol,
        disposition.rank,
        disposition.reason_code,
        COALESCE(candidate.held_at_rank, disposition.anti_pyramiding) AS held_at_rank,
        COALESCE(
            candidate.signal_age_at_slot,
            candidate.decision_slot - candidate.model_generated_at
        ) AS signal_age_at_slot,
        (candidate.versions #>> '{ranking,n_top}')::INTEGER AS n_top,
        (candidate.versions #>> '{gate,max_signal_age_hours}')::DOUBLE PRECISION
            * INTERVAL '1 hour' AS max_signal_age
    FROM s4_intent_events AS candidate
    JOIN s4_intent_events AS disposition
      ON disposition.intent_id = candidate.intent_id
     AND disposition.event_type = 'disposition'
    WHERE candidate.event_type = 'candidate'
), per_slot AS (
    SELECT
        decision_slot,
        MAX(n_top) AS n_top,
        COUNT(*) FILTER (
            WHERE rank IS NOT NULL AND rank <= n_top
        )::INTEGER AS ranked_slots,
        COUNT(*) FILTER (
            WHERE rank IS NOT NULL AND rank <= n_top AND held_at_rank IS TRUE
        )::INTEGER AS slots_burned_by_held,
        COUNT(*) FILTER (
            WHERE rank IS NOT NULL
              AND rank <= n_top
              AND signal_age_at_slot > max_signal_age
        )::INTEGER AS slots_burned_by_stale,
        COUNT(*) FILTER (WHERE reason_code = 'SUBMITTED')::INTEGER AS orders_emitted,
        COUNT(*) FILTER (
            WHERE reason_code = 'RANK_OUTSIDE_TOP_N'
        )::INTEGER AS cut_candidates
    FROM paired
    GROUP BY decision_slot
)
SELECT
    decision_slot,
    n_top,
    ranked_slots,
    slots_burned_by_held,
    slots_burned_by_stale,
    orders_emitted,
    CASE
        WHEN orders_emitted = 0 THEN cut_candidates
        ELSE 0
    END AS candidates_cut_with_zero_orders
FROM per_slot;

CREATE VIEW s4_burned_slot_metrics_daily AS
SELECT
    (decision_slot AT TIME ZONE 'America/New_York')::DATE AS session_date,
    COUNT(*)::INTEGER AS decision_slots,
    SUM(slots_burned_by_held)::INTEGER AS slots_burned_by_held,
    SUM(slots_burned_by_stale)::INTEGER AS slots_burned_by_stale,
    SUM(candidates_cut_with_zero_orders)::INTEGER AS candidates_cut_with_zero_orders,
    COUNT(*) FILTER (
        WHERE slots_burned_by_held >= 4
    )::INTEGER AS slots_with_at_least_four_held,
    COUNT(*) FILTER (
        WHERE candidates_cut_with_zero_orders > 0
    )::INTEGER AS slots_with_candidates_cut_zero_orders
FROM s4_burned_slot_metrics
GROUP BY (decision_slot AT TIME ZONE 'America/New_York')::DATE;
