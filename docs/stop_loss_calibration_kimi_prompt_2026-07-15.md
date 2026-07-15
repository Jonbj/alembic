# Kimi Autonomous Run — Stop-Loss k/floor/cap Calibration

**Date:** 2026-07-15
**Owner of context:** you (Kimi 2.7-code) — you implemented the F9a stop-loss redesign on 2026-07-11 (`docs/stop_loss_kimi_handback.md`) and ran the Round 2 replay gate, which FAILED.
**Branch:** create `stop-loss-calibration-2026-07-15` from `main` (do NOT work on `main`).
**Spec:** `docs/superpowers/plans/2026-07-11-stop-loss-redesign.md` (§6.4 stop-risk sizing, §6.5 k calibration, §10 gates).
**Read-only constraint:** the replay script never writes to the DB. You may edit `config/trading.yaml` stop params + `scripts/replay_stop_loss.py` on your branch to test variants, but **DO NOT flip the live flag** and **DO NOT merge to main** — operator sign-off required after you report.

---

## 1. Situation (read this first)

The vol-scaled stop is **implemented, merged to `main`, and DISABLED**. Live trading still runs `stop_loss_mode: fixed` at 2% — the same stop that caused the 2026-07-10 noise stop-outs (S1 momentum: PANW/WDC/DELL, 2% = 0.26-0.53σ, move >2% in 65-72% of days). Your job is to **recalibrate k/floor/cap per strategy so the OOS replay gate PASSES**, enabling an operator to flip `vol_scaled` live.

Your Round 2 (2026-07-11) gate verdict was FAIL. The numbers (OOS, test 63 trades):

| Gate | Round 2 OOS | Threshold | Pass? |
|---|---|---|---|
| false-stop reduction vs fixed 2% | 100.0% | ≥ 40% | ✅ |
| median net P&L (vol vs fixed) | -0.99 vs -1.31 | vol > fixed | ✅ |
| **bootstrap delta P&L positive** | **42.5%** | **≥ 70%** | ❌ |
| **max DD delta** | **-0.4857** | **≤ 0.10** | ❌ (vol_scaled worsened DD) |
| ES95 delta vs base | -20.13 | not materially worse | borderline |
| open-stop risk vs budget | 50.4 bp / 100 bp | within | ✅ |
| name-dependence top-2 | 21.7% | ≤ 50% | ✅ |

**Diagnosis:** the stop is **too wide**. false-stop reduction is 100% (it almost never fires on noise — good) but the stops that DO fire lose too much money → bootstrap can't separate from fixed 2% and the portfolio DD gets worse. The lever is **k and cap** (too high → wide d_init → big $ loss per stop), combined with **stop-risk sizing** (§6.4: a wider stop MUST size down qty so $ risk per position is bounded). If stop-risk sizing wasn't active in Round 2, that alone explains the DD blow-up.

## 2. Current parameters (config/trading.yaml, lines 169-178)

```yaml
stop_loss: 0.02
stop_loss_mode: fixed           # fixed | vol_scaled (ship: fixed)  <- DO NOT change to vol_scaled
stop_strategy_params:
  S1:   {k: 3.5, floor: 0.06, cap: 0.12}
  S4:   {k: 2.0, floor: 0.03, cap: 0.08}
  S7:   {k: 2.5, floor: 0.04, cap: 0.10}
  default: {k: 3.0, floor: 0.04, cap: 0.12}
stop_sigma_lookback_fast: 20
stop_sigma_lookback_slow: 63
stop_sigma_ewma_floor_ratio: 0.8
```

## 3. Goal

Find, per strategy (S1, S4, S7, default), a `(k, floor, cap)` triple such that **the OOS (walk-forward test set) replay gate PASSES all 7 checks**, with the bootstrap delta P&L ≥ 70% and max DD delta ≤ 0.10 as the hard gates. Prefer the **tightest stop that still achieves ≥40% false-stop reduction** (don't over-widen just to dodge noise — that's what broke Round 2).

## 4. Calibration method (spec §6.5)

`k_strat` should be calibrated on each strategy's **MAE (Maximum Adverse Excursion) distribution of WINNING trades**: `k = quantile_q( σ_entry / MAE_trade )`. Concretely:

1. From the replay's per-trade data, for each strategy isolate **winning trades** (real outcome profitable / recovered).
2. Compute `MAE_trade` (worst adverse drawdown before recovery, in price terms → as fraction of entry).
3. Compute `σ_entry` (sigma_eff at entry, the replay already has it).
4. `ratio = σ_entry / MAE_trade` per winning trade → take the q-th quantile as `k_strat` (start with q=0.5 median, then sweep q ∈ {0.4, 0.5, 0.6, 0.7}).
5. `floor`/`cap` bound `d_init = clip(k·σ, floor, cap)`; set `floor` from the noise floor (the 2% that stopped out PANW/WDC was 0.26-0.53σ, so floor must be ABOVE the typical noise excursion but below the MAE of winners) and `cap` from the worst acceptable single-stop $ loss given stop-risk sizing.

## 5. Stop-risk sizing (spec §6.4 — MUST be active)

A wider stop on the same notional = bigger $ loss. Size down so monetary risk per position is bounded:

```
Notional(sym, strat) ≤ NAV · B_strat / ( d_init + gap_buffer )
```
- `B_strat` = per-position loss budget in bp of NAV (start 10-15 bp; e.g. 12 bp)
- aggregate open-stop risk per sleeve ≤ 75-100 bp (config `stop_risk_budget_bp_aggregate`)
- `gap_buffer` = max(0.5%, 95th-pct adverse gap for the symbol)

**Verify stop-risk sizing is wired and active in the replay** (`src/workers/portfolio_scheduler.py` order-sizing path, after vol-targeter, before submit). If Round 2 ran without it, that is the primary DD fix — re-run with it on before blaming k.

## 6. How to run the replay (read-only, idempotent)

```bash
cd /home/stefano/Documents/Projects/Alembic
export $(grep -E '^(DATABASE_URL|ALPACA_API_KEY|ALPACA_SECRET_KEY|ALPACA_BASE_URL)=' .env)
.venv/bin/python scripts/replay_stop_loss.py \
    --start 2026-06-01 --end 2026-07-14 \
    --bars-csv data/daily_close.csv --mode report --nav-est 110000
```

- Extend `--end` to **2026-07-14** (Round 2 stopped at 07-11) — more closed trades = more robust OOS sample. ~3 extra trading days.
- Baseline is `fixed_2pct`. Candidate variants the script already supports: `vol_scaled` (uses config k), `vol_scaled_k25`, fixed_3pct/5pct/7pct, and a k-sweep. Use the k-sweep to scan `k` per strategy.
- The script simulates from Alpaca 15-min bars, NOT from stored `stop_*` metadata, so the partial-metadata pre-WS-2 trades are fine.
- Gate evaluation is `scripts/replay_stop_loss.py::_gate_check` (7 checks). Report ALL 7 per candidate, full sample AND OOS.

## 7. Constraints (non-negotiable)

1. **DO NOT set `stop_loss_mode: vol_scaled` in the live config.** Ship stays `fixed`. You're calibrating, not enabling.
2. **DO NOT merge to `main`.** Work on `stop-loss-calibration-2026-07-15`. Operator decides merge + flip after reviewing your numbers.
3. **DO NOT force a flip if the gate fails again.** If no `(k, floor, cap)` passes OOS, report that honestly — the answer may be "vol-scaled stop doesn't help this book with current strategies" and the fix is elsewhere (e.g. the 2% stop is actually fine and the 07-10 losses were a regime/sizing problem, not a stop problem). Do not ship a marginal-pass.
4. Read-only on the DB and Alpaca. No live orders.
5. End every run with a handback doc (§8).

## 8. Deliverables — write `docs/stop_loss_calibration_handback_2026-07-15.md`

Structure:
1. **What you ran** — replay command, window, sample size (train/test split), strategies covered.
2. **Was stop-risk sizing active in Round 2?** — yes/no with evidence; if no, that's finding #1.
3. **Calibration results** — per strategy: the best `(k, floor, cap)` and the q-quantile used; the MAE-distribution stats that justified it.
4. **Gate table** — for the best candidate, all 7 gates, full sample + OOS, with numbers. **PASS or FAIL** verdict explicit.
5. **If PASS:** the exact `config/trading.yaml` diff to apply on flip (params only, `stop_loss_mode` stays `fixed` in the diff — operator flips the mode line), + the canary recommendation (start S1 10% paper per §4 runbook).
6. **If FAIL:** which gates failed, why, and your recommendation (recalibrate further / abandon vol-scaled for this book / different lever).
7. Commits on your branch (hashes + messages).

## 9. Success criteria

- OOS gate **PASS on all 7 checks** with a defensible `(k, floor, cap)` per strategy, OR
- A clear, evidenced **FAIL verdict** explaining why vol-scaled doesn't beat fixed 2% OOS for this book and what the real lever is.

Either is a successful outcome. A forced marginal-pass is not.

---

Context files to read before starting:
- `docs/stop_loss_kimi_handback.md` (your own Round 2 handback — §8 numbers, §3 design decisions, §6 commits)
- `docs/superpowers/plans/2026-07-11-stop-loss-redesign.md` (§6.4, §6.5, §10 gates)
- `scripts/replay_stop_loss.py` (the replay + `_gate_check` + variants + k-sweep)
- `src/portfolio/stop_policy.py` (the live StopPolicy — `freeze()`, `vol_scaled` path)
- `config/trading.yaml` lines 169-178 (current params)

Hand off the result in `docs/stop_loss_calibration_handback_2026-07-15.md`. The operator will review and decide whether to flip `vol_scaled` live.