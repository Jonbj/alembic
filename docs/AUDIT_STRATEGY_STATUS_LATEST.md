# Alembic Strategy Audit — 2026-08-03T21:37:51Z

## Status

- **Stack**: OK — all 7 containers Up (api, worker, worker-inference, beat, frontend, postgres healthy, redis healthy)
- **Strategy allocations**: OK — S1 enabled alloc=0.50 blocked; S4 enabled alloc=0.10 blocked; S2/S3 disabled; S7 absent; enabled sum=0.60 ≤ 1.0
- **Flag freeze (03/08→28/09)**: OK — all 11 committed flags match (engine=portfolio, stop_loss=0.0, stop_loss_mode=fixed, stop_shadow=on, s4_anti_whipsaw=off, s1_reentry_cooldown=off, s4_fixed_slot_sizing=on, max_sector_exposure=0.0, killswitch_recovery=on, max_portfolio_exposure=0.50, max_position_pct=0.10). No freeze violation.
- **Redis pair**: OK — `config:sentiment_llm_models` = `glm52,gptoss` (not `all`)
- **Operator halt**: CLEAR — `system:halted_by_operator` empty
- **Redis state keys**: OK — `ensemble:weights:current` and `qc:sizing_multiplier` both present
- **Last-30min activity**: signals=0, trades=0, cycles=0 (flat — Monday 21:37 UTC, post-close; not anomalous by itself)
- **S4 long-only (24h)**: OK — 0 trades with sentiment signal & score<0
- **Forensic freshness**: DRIFT (known) — latest `FORENSIC_DAILY_REPORT_2026-07-31.md`; today is 2026-08-03. Friday is never analyzed (known weekend off-by-one bug), so the missing 07-31 Friday report is expected, not a new anomaly.
- **Stop shadow (24h)**: 1181 rows, **15 `d_hard_breached`** — all on **NOK / S1**, adverse excursion 20.86–22.99%
- **Fallback counters (24h)**: `consecutive_fallback`=0 (last_increment 2026-08-03 15:30 UTC) — no ensemble-divergence spike

## Verdict: AMBER

Stack healthy, config clean, freeze intact, pair correct, halt clear, no S4 long-only violation. The single amber item is the **d_hard shadow breach cluster on NOK/S1 (15 events, 20–23% adverse, 24h)** — this is precisely the revisit-condition `trading.yaml` documents:

> Revisit: if any position rides past -15/20% (d_hard shadow), wire d_hard to a real broker order (catastrophe-only), NOT the 2% noise stop.

No action is taken by the audit (read-only; out-of-freeze anyway until 28/09). This is surfaced for the operator: the shadow log is now showing the condition the project said would trigger the d_hard catastrophe-stop decision. Concentrated in a single name (NOK), so likely a position that was held through a large adverse move rather than a broad portfolio event.

## Changes since last run
First run.