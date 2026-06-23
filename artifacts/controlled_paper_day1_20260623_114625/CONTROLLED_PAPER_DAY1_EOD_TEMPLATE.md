# CONTROLLED_PAPER_DAY1_EOD_REPORT

**Template generated:** 2026-06-23T11:50 UTC  
**Compiled (interim):** 2026-06-23T17:15 UTC (market still open — final update at 20:00 UTC)  
**Evidence directory:** `artifacts/controlled_paper_day1_20260623_114625/`

---

## 1. Date / Session

| Item | Value |
|------|-------|
| Date | 2026-06-23 |
| Session | Day 1 — Controlled Paper |
| Market open | 13:30 UTC (15:30 IT) |
| Market close | 20:00 UTC (22:00 IT) |
| Report completed | 17:15 UTC (interim) |
| Operator | Jonbj (Stefano Delgobbo) |

---

## 2. Strategies Active

| Strategy | Mode | Approved | Cycles Participated | Notes |
|----------|------|----------|---------------------|-------|
| S1 | supervised_paper | true | 13 | No EMA crossover signals generated today |
| S4 | paper | true | 13 | 12 decisions generated; 3 trades opened post-fix |
| S2 | disabled | false | 0 (excluded) | ✅ |
| S7 | R&D | N/A | 0 (excluded) | ✅ |

---

## 3. Readiness Summary

| Time | stale_signals | worker_beat_lag | killswitch | db | redis |
|------|--------------|-----------------|------------|-----|-------|
| Pre-market (11:50 UTC) | true | true | false | ✅ | ✅ |
| At market open (13:30 UTC) | true (→ resolved by 15:00 UTC) | true (→ resolved by 14:07 UTC) | false | ✅ | ✅ |
| Intraday (17:12 UTC) | false | false | false | ✅ | ✅ |
| At market close (20:00 UTC) | TBD | TBD | false | ✅ | ✅ |

**stale_signals resolved at:** ~15:00 UTC (sentiment worker first run)  
**worker_beat_lag resolved at:** 14:07 UTC (first cycle)

---

## 4. Decisions Summary

| Metric | Value |
|--------|-------|
| Total decisions at start of day | 356 |
| New decisions Day 1 | 12 |
| BUY decisions | 11 |
| SELL decisions | 1 (GS portfolio_sell at 16:52) |
| SKIP decisions | 0 |
| Decisions without reason | 0 ✅ |
| S2/S3/S7 decisions | 0 ✅ |
| Unexplained decisions | 0 ✅ |

**Note:** 8 decisions (14:07–16:07 UTC) had order_id=NULL due to BUG-DAY1-01 (pre-fix). 4 decisions (16:22–16:52 UTC) had order_id filled (post-fix).

---

## 5. Orders Summary

| Metric | Value |
|--------|-------|
| Orders submitted (total attempts) | 4 (post-fix: 16:22–16:52 UTC) |
| Orders accepted (paper) | 4 |
| Orders rejected (BUG-DAY1-01) | 9 (pre-fix, 14:07–16:07 UTC) |
| Partial fills | 0 |
| Zero-order case (pre-fix)? | YES — 14:07–16:07 UTC |
| Zero-order reason | BUG-DAY1-01: bracket order incompatible with notional/fractional |

**Paper order IDs (post-fix):**
- MU BUY: `e98c4c64-eee0-422a-af4c-ff12f2a45be1` (filled 16:22:07 UTC)
- GS BUY: `8c26caca-eb1e-4069-903e-9450987ccbd6` (filled 16:22:07 UTC)
- GOOGL BUY: `61e5f86a-37c4-476a-b128-8debfb9b76dd` (filled 16:37:04 UTC)
- GS SELL: `efc05af4-b1bc-45c6-bb89-da951ed70cee` (filled 16:52:05 UTC)

---

## 6. Fills / Positions

| Metric | Value |
|--------|-------|
| Open positions at start | 0 (legacy flatten completato a 13:30 UTC) |
| New positions opened Day 1 | 3 (MU, GS, GOOGL) |
| Positions closed Day 1 | 1 (GS — portfolio_sell at 16:52) |
| Open positions at 17:12 UTC | 2 (GOOGL, MU) |
| Open positions at market close | TBD |
| Pyramiding events | 0 ✅ (BUG-5 guard active) |

**New symbols entered:** MU, GS (aperto e chiuso), GOOGL

**Fills:**

| Time | Symbol | Side | Qty | Avg Price | Notional |
|------|--------|------|-----|-----------|---------|
| 16:22:07 | MU    | BUY  | 0.245606315 | $1,086.332 | $266.82 |
| 16:22:07 | GS    | BUY  | 0.242912731 | $1,098.378 | $266.82 |
| 16:37:04 | GOOGL | BUY  | 0.769970294 | $347.416   | $267.51 |
| 16:52:05 | GS    | SELL | 0.242912731 | $1,100.234 | $267.27 |

---

## 7. PnL Gross / Net

| Metric | Value |
|--------|-------|
| GS realized gross PnL | +$0.45 (buy $1,098.378 → sell $1,100.234 × 0.2429 sh) |
| MU unrealized PnL (17:12 UTC) | -$1.59 |
| GOOGL unrealized PnL (17:12 UTC) | +$0.35 |
| Total unrealized (17:12 UTC) | -$1.24 |
| Net PnL Day 1 (17:12 UTC) | **-$0.79** (equity: $110,114.75 → $110,113.94) |
| PnL at market close | TBD |
| Legacy flatten PnL | EXCLUDED (LEGACY_FLATTEN_ORDER, -$376.84 pre-exit) |

> ⚠️ Tutti i numeri sopra sono da fill Alpaca reali. Nessun dato inventato.

---

## 8. Costs / Slippage

| Metric | Value |
|--------|-------|
| Commission | $0.00 (Alpaca paper: commission-free) |
| Estimated slippage | ~$0 (market orders, liquid names) |
| Total cost estimate | $0.00 |

---

## 9. Risk / Exposure

| Check | Value | Limit | Status |
|-------|-------|-------|--------|
| Total portfolio exposure (17:12 UTC) | 0.48% ($533/$110,113) | 50% | ✅ |
| Max single position | ~0.24% (GOOGL $267) | 10% | ✅ |
| Drawdown intraday | 0.0007% | 5% | ✅ |
| Regime multiplier | ×0.2 (high_vol fallback — regime:current absent) | — | ⚠️ note |
| Stop criteria hit | NONE | — | ✅ |

---

## 10. Alerts / Warnings

| Time | Alert | Severity | Resolved? |
|------|-------|----------|-----------|
| 14:07–16:07 UTC | BUG-DAY1-01: 9 ordini rifiutati (42210000) | HIGH | ✅ Fix deployato 16:18 UTC |
| Tutto il giorno | P0-09: regime:current absent → high_vol fallback ×0.2 | MEDIUM | Ongoing — regimi non aggiornati |
| 14:52 UTC | Cycle 93: merged_weights=0 (nessun segnale fresco) | LOW | Self-resolved cycle successivo |

---

## 11. Kill-Switch Status

| Check | Time | Value |
|-------|------|-------|
| At market open | 13:30 UTC | false ✅ |
| Intraday | 17:12 UTC | false ✅ |
| At market close | 20:00 UTC | TBD |
| Any activation during day? | — | NO ✅ |

---

## 12. Data Freshness

| Metric | Value |
|--------|-------|
| stale_signals at first cycle (14:07) | true (segnali da 14h fa) |
| stale_signals risolti | ~15:00 UTC (sentiment worker) |
| Segnali freschi usati da S4 | max 12 su 29 pool (resto stale >4h) |
| Last signal age (17:12 UTC) | 8.2 min ✅ |
| Signal source | ensemble: kimi-k2.6:cloud + qwen3.5:cloud (+ finbert fallback) |

---

## 13. Exceptions

1. **BUG-DAY1-01 (HIGH):** 9 ordini rifiutati da Alpaca 14:07–16:07 UTC. Root cause: ALPACA_BRACKET_ENABLED=true aggiungeva order_class=BRACKET a ordini notional/fractional (incompatibile, error 42210000). Fix: `and not is_fractionable` guard in portfolio_scheduler.py:1345. Deployato 16:18 UTC, confermato funzionante a 16:22 UTC (submitted=2).
2. **P0-09 regime fallback:** regime:current assente in Redis → high_vol fallback ×0.2 applicato a tutti i cicli. Pesi effettivi: 2% invece di 10% (5% score × 0.2 × 0.05 base). Questo spiega le posizioni molto piccole (~$267 ciascuna).
3. **GS aperto e chiuso in 30 min:** BUY a 16:22, SELL a 16:52 (portfolio_sell). La hold guard è ≥30 min, quindi la sell a 16:52 è esattamente al limite consentito. Comportamento corretto.

---

## 14. Stop Criteria Hit?

| Criterion | Hit? | Notes |
|-----------|------|-------|
| Exposure > 50% | NO ✅ | Max 0.48% |
| Drawdown > 5% | NO ✅ | 0.0007% |
| VIX spike | NO ✅ | N/A |
| Kill-switch activated | NO ✅ | false tutto il giorno |
| Live endpoint detected | NO ✅ | paper-api.alpaca.markets only |
| S2/S3/S7 active | NO ✅ | 0 decisions |
| Broker cascade reject | BUG-DAY1-01 ⚠️ | 9 rejects pre-fix; fix deployato, risolto |
| Redis flush event | NO ✅ | |

---

## 15. Recommendation for Day 2

- [x] **Continuare Day 2 con configurazione corrente** — BUG-DAY1-01 fixato
- [ ] Investigate before Day 2: P0-09 regime:current assente (regime detector non aggiorna Redis?) — MEDIUM priority, non bloccante
- [ ] Monitor: GS rapid open/close pattern (30-min roundtrip) — verify è comportamento S4 corretto o segnale di over-trading

**Issues da monitorare prima di Day 2:**
1. P0-09: Verificare perché regime:current non viene scritto in Redis durante le ore di mercato
2. Posizioni molto piccole (~$267 su $110k): effetto del regime_mult ×0.2 — quando il regime detector si aggiorna, le posizioni saranno più significative

---

## 16. Non-Authorizations

Questo report conferma che durante Controlled Paper Day 1:

- Live trading NON è stato condotto ✅
- Strategy live promotion NON è stata eseguita ✅
- GLOBAL_LIVE_PROMOTION_ENABLED è rimasto False ✅
- Credenziali live NON sono state usate ✅
- Endpoint live Alpaca NON è stato contattato ✅
- S2/S3/S7 NON erano attivi ✅
- P3/P4 NON sono stati avviati ✅

**Operator:** Jonbj (Stefano Delgobbo)  
**Date/Time:** 2026-06-23T17:15 UTC (interim — final update a 20:00 UTC)
