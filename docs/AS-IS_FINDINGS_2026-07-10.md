# Alembic — AS-IS Functional Findings

**Date:** 2026-07-10
**Method:** `/grill-with-docs` — relentless interview (AS-IS reconstruction, not design) cross-referencing stated intent against code. Five-bucket categorization:
1. **Intenzionale** — code and intent agree
2. **Ambiguo** — intent unclear, code doesn't evidently decide
3. **Contraddizione codice↔dominio** — code does something contradicting the domain model
4. **Requisito non implementato** — declared but absent in code
5. **Implementato ma non documentato** — code does something undocumented

**Scope:** the active order path (`execution.engine=portfolio`). Citations are `file:line`.

---

## Central finding: a self-reinforcing underdeployment loop

The book sits at ~5% deployment (vs ~50% design) **not because of one lever but because several non-calibrated conservativisms multiply**, and the loss-feedback ratchet closes the loop:

```
regime_mult 0.2 fallback  (F4, non-calibrated)
   × regime_mult skips whole-share  (F5, bug — only bites on fractionable)
   × vol-targeter floor 0.5  (F6, target_vol=0.10 non-calibrated < realized vol)
   × stop 2% → frequent noise stop-outs  (F9a, non-calibrated)
        → each stop-out is a recorded loss
        → loss-feedback ratchet (F3) raises entry_threshold (hard gate)
        → fewer symbols pass the entry gate
        → fewer entries → underdeployment deepens
```

The de-risking levers that *could* reduce this asymmetry are themselves not wired in the portfolio path: `feedback:regime_scale` is orphaned (F8) and the sector/correlation constraint passes are no-ops (F11). So the system can only react to losses by *blocking new entries*, never by *scaling down existing exposure* — which feeds more stop-outs, which feeds the ratchet.

**Net:** the underdeployment is emergent composition, not a single misconfiguration. Fixing it requires calibrating the levers (regime fallback, `target_vol`, stop-loss) *and* wiring at least one exposure-reduction lever in the portfolio path.

---

## Findings

### F1 — S4 EMA20 trend filter removed from the portfolio path
- **Buckets:** (1) intenzionale + (5) implementato/non-documentato (the removal isn't documented)
- **Code:** the portfolio path has **no** `price > EMA20` filter; `execution_decisions.ema_pass` is hardcoded `True` (`portfolio_scheduler.py:1439`). The EMA20 gate exists **only** in the legacy path (`execution.py:668-687`).
- **Docs say otherwise:** ARCHITECTURE.md §2.5 and `s4/__init__.py:5` describe the gate as "score > 0.3 AND price > EMA20".
- **Intent (confirmed):** intentionally removed — the portfolio path uses cross-sectional ranking + event-time gate + feedback threshold instead; the per-symbol EMA gate doesn't fit the weight-then-order model. Docs are stale.

### F2 — Event-time gate ≤2h applies only to entry; sell-protection is permissive; NULL passes
- **Bucket:** (1) intenzionale
- **Code:** `fetch_signals_for_cycle(news_age_hours=2)` filters `published_at ≤ 2h` **only** at S4 entry (`portfolio_scheduler.py:2003`). `_sentiment_reversal_sells` (`:2314`) reads `signal:{sym}:sentiment` from Redis **without** the `published_at` filter — a signal based on 3h-old news can't trigger a BUY but its score can force a sentiment-reversal SELL. `published_at IS NULL` (legacy rows) passes the gate.
- **Intent (confirmed):** both intentional — entry is conservative (act only on fresh news), exit-for-protection is permissive (use any signal to protect capital); NULL pass-through avoids breaking pre-migration-032 signals.

### F3 — feedback `entry_threshold` is a hard binary gate
- **Bucket:** (1) intenzionale
- **Code:** signals with `abs(score) < feedback:entry_threshold` (default 0.30) are dropped and logged `SKIP_THRESHOLD` (`portfolio_scheduler.py:2107-2147`); survivors go to cross-sectional ranking (`s4/ranking.py`, `min_score` 0.10). The threshold (0.30) is the binding gate.
- **Implication:** when the ratchet raises the threshold (e.g. to 0.55), S4 may have **zero** admissible symbols → the sleeve empties for that cycle. It is a switch, not a gradual resize.

### F4 — regime multiplier 0.2 fallback → underdeployment
- **Bucket:** (2) ambiguo / **da sistemare**
- **Code:** BUY notional `= price × qty × regime_mult` (`portfolio_scheduler.py:2234`); `regime_mult` from `regime:current`, fallback `macro:vix:latest` → VIX map → **final fallback 0.2** when regime is absent (`:252`).
- **Status:** user-confirmed problem area. When `regime:current` is absent (before 07:00 UTC run, or Redis cleared) the system anchors to ×0.2 even in calm markets. **Fallback handling is "da capire meglio".**

### F5 — regime_mult does not scale whole-share orders (bug)
- **Buckets:** (3) contraddizione codice↔dominio + (5) non-documentato
- **Code:** `notional = price × qty × regime_mult` (`:2234`) scales the order **only for fractionable symbols** (`:2251-2257` submit `notional=…`). For **whole-share** (`:2258-2266`) the order submits `qty = max(1, int(order.quantity))` — the **unscaled** target qty; regime_mult only enters the `< $100` skip-check, not the order.
- **Consequence:** the regime throttle bites on fractionable symbols but is a skip-gate-only on whole-share. A whole-share symbol with target $600 and regime ×0.2 passes the $120 check then **submits $600 full**.
- **Intent (confirmed):** **bug** — side effect of the P1-B whole-share fallback bypassing the scaling. To fix.

### F6 — vol-targeter `target_vol=0.10` non-calibrated → floors at 0.5
- **Bucket:** (2) ambiguo / **da sistemare**
- **Code:** vol-targeter is **active** (`portfolio_scheduler.py:1135`, `target_vol=0.10`); `scale = 0.10 / estimated_vol` clamped `[0.5, 2.0]` (`vol_targeting.py:54-63`). With US equity realized vol ~15-20%, scale floors at **0.5**, halving all BUY orders.
- **Composition:** `NAV × target_wt(0.6) × vol_scale(0.5) × regime_mult(0.2) ≈ 0.06` → matches observed ~5%.
- **Intent (confirmed):** `target_vol=0.10` **not intentionally calibrated** — a "safe" default never tuned to realized book vol. To fix.

### F7 — vol-targeter uses universe equal-weight returns, not strategy holdings
- **Bucket:** (2) ambiguo
- **Code:** `estimated_vol` from `bars_df.pct_change().mean(axis=1)` — equal-weight returns of the **whole universe**, not the strategy's holdings (`portfolio_scheduler.py:1144-1146`). It is a market-environment throttle, not a strategy-vol throttle.
- **Intent:** **unknown** (author unsure). Left open as a decision to make.

### F8 — loss-feedback has no exposure-reduction lever in the portfolio path
- **Buckets:** (1) intenzionale (known-incomplete) + (4) nota di non-implementato
- **Code:** `performance.py` writes both `feedback:entry_threshold` and `feedback:regime_scale` on trigger (`1607-1608`, `1728-1729`). The portfolio path reads **only** `feedback:entry_threshold` (`portfolio_scheduler.py:583,592,2107`); `regime_scale` is written but **never read** in portfolio mode (only the legacy path reads it, `execution.py:465`).
- **Consequence:** after losing streaks the system can only become more selective at entry; **it cannot scale down existing positions**. ARCHITECTURE.md §2.9 admits `regime_scale` is "not sizing-authoritative until explicitly wired".
- **Intent (confirmed):** intentional as known-incomplete state; de-risking of existing positions is not implemented in the portfolio path.

### F9 — stop-loss 2% non-calibrated + same-day re-entry cooldown
- **Buckets:** (2) stop non-calibrato + (1) cooldown intenzionale + (2) effetto composto sistemico
- **Code:** stop-loss `price ≤ entry × (1 − 0.02)` → forced full SELL (`portfolio_scheduler.py:536-577`, `trading.yaml:153`). Stop-out writes `stop_loss_today:{sym}` (TTL to midnight) → **blocks re-BUY** same day (`:1305`, `:2221`). Sentiment-reversal exit at score < −0.20 (`config.py:184`). Hold-minimum 90min + exit hysteresis 2 cycles bypass for stop-loss/reversal.
- **Intent (confirmed):** (a) **2% not calibrated** (too tight for equities, primary ratchet trigger) — to fix; (b) cooldown **intentional anti-churn**. Composite effect (tight stop → lockout → losses → ratchet → fewer entries → underdeploy) **not put in conto** → systemic (2).

### F10 — idempotency: S4 fail-closed fired-signal dedup; S1 continuous rebalance
- **Bucket:** (1) intenzionale
- **Code:** S4 BUYs skipped if `signal_id` already in `s4:fired_signals:{date}` (`portfolio_scheduler.py:476-498`); **fail-closed** (Redis down → all S4 BUYs skipped, P2-05-A). S1 is MONTHLY continuous rebalance whose delta-ordering is "naturally idempotent" (`orchestrator.py:2159`) → no fired-signal gate. Both share the pyramiding guard P0-05 (skip BUY if open trade, fail-closed on DB down, `:1243`, `:2210`).
- **Operational note:** a Redis/DB blip during market hours → zero new entries, by design.

### F11 — ConstraintEnforcer sector + correlation passes are no-ops in the live path
- **Buckets:** (4) requisito non implementato + (5) non-documentato
- **Code:** `ConstraintEnforcer` constructed with only `max_portfolio_exposure` and `max_single_asset_pct` (`portfolio_scheduler.py:1131-1134`) — **no `sector_map`, no `strategy_returns`**. `_enforce_sector_exposure` returns early (`constraints.py:258-259`) and `_enforce_correlation_cluster` returns early (`:299-300`).
- **Consequence:** 2 of the 5 advertised passes are **dead code** in the live path: the per-sector 25% NAV cap and the correlated-cluster de-risking never bind. Notable: the correlation pass needs `strategy_returns` — the same data the vol-targeter *does* receive (`:1152`) but the enforcer doesn't (wiring gap).
- **Intent (pending confirmation):** recommended "deliberately deferred / not-implemented" — `sector_map` needs a sector-classification source never wired; correlation has a wiring gap. The "5-pass" enforcer is advertised (ARCHITECTURE.md §2.4) but 2/5 are no-ops.

### F12 — approval gate fail-open on absent lifecycle row
- **Buckets:** (1) intenzionale (documented) + (3) contraddizione codice↔dominio
- **Code:** `_filter_approved_strategies` (`portfolio_scheduler.py:87-147`): row absent → **admitted with warning** (fail-open "legacy strategy"); row `approved=False` → excluded (fail-closed); DB error → excluded.
- **Inconsistency:** the safety invariant "live trading not authorized for any strategy" is defeated for unseeded strategies — a new strategy added to `config/strategies.yaml` without a seeded `strategy_lifecycle` row runs by default. The gate only protects strategies that *have* a row.
- **Intent (confirmed):** AS-IS fail-open was intentional (backward-compat for pre-lifecycle strategies). User lean: **move to fail-closed-on-absent** ("altrimenti non ha senso") — recorded as **da sistemare** (align gate with invariant). Not implemented during grilling.

### F13 — Zeygos universe filter is dead code (future feature)
- **Buckets:** (4) requisito non implementato + (5) non-documentato
- **Code:** ingestion is **live** — `telegram_poller.py` ingests Zeygos PDFs (filename contains "zeygos") via `parse_zeygos_pdf` → upsert to `zeygos_scores` (`pg_store.py:2394`) → OK/KO reply. Consumption is **defined but never called**: `_apply_zeygos_filter` (`portfolio_scheduler.py:1788`) intersects S4 symbols with `zeygos_scores` where `score_finale ≥ 65` (`fetch_zeygos_universe`, `pg_store.py:2427`), fail-open on no-data/all-filtered/error. Grep confirms no call site in the file.
- **Consequence:** the `zeygos_scores` table populates but feeds nothing in the live cycle; the S4 universe is not filtered by Zeygos even when data exists.
- **Intent (confirmed):** **oversight/TODO — Zeygos is a future feature.** Ingestion built ahead of consumption (forward-looking scaffolding).

---

## Summary table

| # | Ramo | Bucket | Status |
|---|---|---|---|
| F1 | S4 EMA20 rimosso | (1)+(5) | intenzionale, doc stale |
| F2 | event-time ≤2h solo entrata | (1) | intenzionale |
| F3 | feedback entry_threshold hard gate | (1) | ratchet→svuota sleeve |
| F4 | regime_mult 0.2 fallback underdeploy | (2) | **da sistemare** |
| F5 | regime_mult no-scala whole-share | (3)+(5) | **bug** |
| F6 | vol-targeter target_vol=0.10 | (2) | **da sistemare** |
| F7 | vol-targeter usa rendimenti universo | (2) | ambiguo (decisione aperta) |
| F8 | loss-feedback no de-risking in portfolio | (1)+(4) | noto-incompleto |
| F9 | stop 2% + cooldown | (2)+(1)+(2) | composto sistemico |
| F10 | idempotency S4/S1 | (1) | intenzionale |
| F11 | ConstraintEnforcer sector+correlation no-op | (4)+(5) | **pending** (deferred?) |
| F12 | approval gate fail-open on absent row | (1)+(3) | **da sistemare** (lean: fail-closed-on-absent) |
| F13 | Zeygos universe filter dead code | (4)+(5) | oversight/TODO (future feature) |

**"Da sistemare" set (non-calibrated/bug):** F4, F5, F6, F9a, F12 — plus the systemic composition (central finding) and the open decision F7 and the pending-confirmation F11. F13 is future-feature scaffolding (not a defect to fix now).

**Glossary captured in:** `CONTEXT.md` (root).