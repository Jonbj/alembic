# F8 `regime_scale` — Shadow Evidence for the Flip Decision (#32)

**Date:** 2026-07-21 · **Decision deadline:** 2026-07-26 · **Issue:** #32
**Reproduce:** `docker compose exec worker python scripts/f8_regime_scale_shadow_evidence.py`

## What F8 is

The loss-feedback ratchet computes a per-strategy `feedback:regime_scale:S*`
that shrinks after losses (×0.80 per trigger, floor 0.20) and recovers on wins.
`loss_feedback.apply_regime_scale = False` means the scale is **computed and
logged but NOT applied to sizing** (shadow). The #32 decision is whether to flip
it ON (enforce the de-risk), recalibrate, or extend the shadow.

## Headline

**Do NOT flip F8 ON as-is.** Not because the de-risk points the wrong way — it
points the *right* way — but because (1) the shadow was never persisted, so the
deadline's premise ("evaluate the shadow trajectory") cannot be met from records,
and (2) the mechanism has a design flaw that makes it **self-disarm every
weekend**. Both should be fixed first; then a short instrumented shadow makes the
flip decidable on real data. The current live state already argues for de-risking
S1 specifically.

## Finding 1 — The F8 shadow was never persisted (instrumentation gap)

Unlike #61 (whipsaw) and #71 (S1 cooldown), which write a shadow annotation into
`execution_decisions.reason` that accumulates in Postgres, F8 writes only a
transient `log.info` line and a 48h-TTL Redis key. **There is no recorded
trajectory to read back.** Every claim about "what the scale did last week" has
to be reconstructed, not looked up. This alone means F8 is not in the same
flip-ready state as #83/#85.

## Finding 2 — Current live state (ground truth)

| Sleeve | Live scale | Last adjustment | Reason |
|---|---|---|---|
| **S1** | **0.512** (= 0.8³) | 2026-07-21 14:00 UTC | EWMA R −0.50 + **12 consecutive losses** |
| **S4** | **0.80** (= 0.8¹) | 2026-07-21 14:30 UTC | 4 consecutive losses |

F8 right now *wants* to cut S1 sizing to 51% and S4 to 80% — a real de-risk that
is not being applied. The "12 consecutive losses" on S1 corroborates the
independent churn analysis: **S1 momentum is the loss engine**, and F8's de-risk
is aimed at the correct sleeve.

## Finding 3 — The 48h TTL + Mon–Fri cron makes F8 reset every weekend

`run_loss_feedback_check` runs only Mon–Fri 14:00–21:00 UTC, and the scale key
carries a 48h TTL. A weekend gap (Fri close → Mon open ≈ 65h) **exceeds the TTL**,
so the key expires and the scale **resets to 1.0 every Monday**. F8 then has to
re-learn the week's losses from scratch. This is visible in the reconstruction
(scale back at 1.0 on 06-29, 07-06) and it materialised on the worst kind of day:
**Monday 2026-07-20 lost −$287 NAV with S4 freshly reset to 1.0 and S1 only
partially down (0.64)** — the de-risk lagged exactly when it was needed. Flipping
F8 ON without fixing this ships a de-risk lever that disarms itself weekly.

## Finding 4 — Directionally, the de-risk is correctly timed (but blunted)

Reconstructed daily scale vs actual NAV change (full table in the script output):

| Day | S1 | S4 | ΔNAV | |
|---|---|---|---|---|
| 06-26 | 1.00 | 0.20 | **−477** | de-risked (S4 at floor) |
| 07-16 | 0.20 | 0.64 | **−439** | de-risked (both) |
| 07-17 | 0.20 | 0.80 | −116 | de-risked (both) |
| 07-20 | 0.64 | **1.00** | **−287** | S4 reset by weekend, lagged |

Across the paper period the scale was de-risked on **9 of the down days** and only
6 up days, and every one of the four largest down days had at least one sleeve
de-risked. Σ|ΔNAV| on de-risked down days ≈ **−$1,596** vs a de-risk "drag" on up
days of only **+$234** (~7:1 in favour of the de-risk being pointed the right
way). Caveat: this is **directional, not a precise counterfactual** — applying
the scale changes which trades fire (a feedback the replay cannot model), and
ΔNAV is whole-book, not attributable to the scaled sleeves alone.

## Finding 5 — The exact trajectory is not reconstructible (validation DRIFT)

The script replays the *real* state machine (real `LossFeedback`, config, and
trade history) and then validates the endpoint against live Redis. It **does not
match**: reconstruction ends S1≈0.41 / S4≈1.0 vs live 0.512 / 0.80 — off by one
ratchet per sleeve. This is not a script bug; it is the path-dependence of a
stateful ratchet whose intermediate state was never persisted (Finding 1).
**We cannot pin down what F8 actually did — only approximate it.** That is a
strong reason not to flip on trust.

## Recommendation for #32

1. **Extend the shadow — do not flip yet.** Flipping an un-instrumented,
   self-disarming de-risk during an 8.4% drawdown is exactly the un-measured
   change QX-01 forbids.
2. **Add persistence** (small, write-only, no sizing change): record the per-cycle
   shadow scale (e.g. annotate the cycle row or a dedicated table) so a real
   trajectory accrues, matching the #61/#71 pattern. Then this evidence is a
   look-up, not a reconstruction.
3. **Fix the weekend reset** before any flip: extend the scale TTL past a
   long-weekend gap (≥ 72–96h) or refresh it on read, so F8 can sustain a
   de-risk instead of disarming every Monday.
4. **Re-review ~2 weeks out** (suggest a deadline ~2026-08-08) with recorded data.
5. **Interim, low-risk option if de-risking is wanted now:** apply the scale to
   **S1 only** (the sleeve at 0.512 with 12 consecutive losses and the churn
   losses), leaving S4 in shadow. S1 is the confirmed loss engine; S4's scale is
   milder (0.80) and its sizing risk is already addressed by the #81 lone-survivor
   cap. This isolates the highest-confidence de-risk from the un-instrumented,
   weekend-resetting parts.

*Read-only analysis. No flag was flipped and no sizing changed — the flip is the
PO decision this evidence supports.*
