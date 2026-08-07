# Alembic — Residual Risk Register

**Last updated:** 2026-06-21 (P2-05 closed — R-01, R-02, R-03 resolved)  
**Scope:** Known risks that remain open after P0/P1/P2-01 through P2-04 completion  
**Owner:** Maintainer team  
**Review cadence:** Update at start of each P-phase; reassess before any paper→live promotion

---

## Risk Table

| ID | Risk | Severity | Likelihood | Status | Owner | Mitigation |
|----|------|----------|------------|--------|-------|------------|
| R-01 | **P2-05-A: Idempotency fail-open on Redis down** | HIGH | Medium | **Closed** (P2-05, 2026-06-21) | Maintainer | Fixed: `_get_fired_signal_ids()` returns `None`; caller skips all S4 BUYs fail-closed |
| R-02 | **P2-05-B: Net exposure cap not wired** | HIGH | Medium | **Closed** (P2-05, 2026-06-21) | Maintainer | Fixed: `_load_risk_config()` reads from trading.yaml; passed to `ConstraintEnforcer` |
| R-03 | **P2-05-C: VolTargeter re-violates cap** | HIGH | Low-Medium | **Closed** (P2-05, 2026-06-21) | Maintainer | Fixed: vol_targeter runs before enforcer in orchestrator; enforcer is last word |
| R-04 | **CI soft gates** — `mypy`, `pip-audit`, `gitleaks` run with `continue-on-error: true`; type errors, dependency CVEs, and secret scans are informational only | MEDIUM | Medium | Open (P3 scope) | Maintainer | Monitor CI output; address CVEs per `pip-audit` report; enable hard-fail after dedicated pass |
| R-05 | **LLM divergence degradation ratio warning** — if both Kimi K2.6 and Qwen3.5 consistently diverge (std > 0.30), ALL inferences fall back to FinBERT; no alert fires if this is the persistent state | MEDIUM | Low | Open | Maintainer | `max_consecutive_fallbacks=3` config exists but alert path not validated end-to-end |
| R-06 | **S3 production readiness** — S3 (Cross-Sectional Momentum) is in `research` mode; its allocation is set to 0% but its code has not been through the same forensic pass as S1 | MEDIUM | Low | Open | Maintainer | Do not promote S3 before a dedicated code review |
| R-07 | **Controlled paper trading not started** — no live-market data has flowed through the production stack; all validation is against historical data and paper-simulated order flow | HIGH | N/A (known gap) | Open — preflight runbook complete; dry-run executed (3 blockers found + fixed: BUG-5 admin.py bytes/str, BUG-6 cockpit dual-path); PO sign-off + strategy approval governance remaining | Maintainer | Runbook: `docs/archive/2026-06-p2-milestone/CONTROLLED_PAPER_PREFLIGHT_RUNBOOK_2026-06-21.md`; engineering blockers BUG-5/BUG-6 closed 2026-06-22 |
| R-08 | **Live trading not authorized** — `GLOBAL_LIVE_PROMOTION_ENABLED = False`; any path that sets it True without completing all prerequisites constitutes an unauthorized promotion | CRITICAL | Depends on operator | Not authorized | PO + Maintainer | Hard-coded False; promotion gate enforced in code; see `src/strategies/promotion.py` |
| R-09 | **yfinance reliability** — EMA20 and drawdown cap both depend on yfinance, which has documented data quality issues | MEDIUM | Low-Medium | Open (backlog) | Maintainer | Consider switching to Alpaca market data API for price feeds |
| R-10 | **Telegram bot token rotation** — no rotation mechanism; leaked token could allow unauthorized approve/reject of weight updates | MEDIUM | Low | Open (backlog) | Maintainer | `TELEGRAM_ALLOWED_USER_IDS` limits blast radius; periodic manual rotation recommended |
| R-11 | **Redis flush resets kill-switch** — Redis restart or `FLUSHALL` silently clears `killswitch_active`; system resumes trading without operator confirmation | HIGH | Low | Open (backlog) | Maintainer | Monitor Redis persistence; use `appendonly yes` in production |
| R-12 | **S7 wiring risk — RISOLTO 2026-07-15** — S7 (PEAD) è stata *rimossa dal repo*, non solo lasciata scollegata: strategia, worker, route, task del beat e config eliminati. Il rischio di wiring accidentale non esiste più; resta un test di guardia contro la re-introduzione (`tests/test_p0_13_strategy_containment.py`). | — | — | Chiuso | Maintainer | Storia: `docs/S7_LIFECYCLE_HISTORY_2026-07-15.md` |
| R-13 | **Pyramiding — position idempotency not implemented** — 21 symbols accumulated multiple open positions (up to 17 per symbol, $76K total notional) in paper stack Jun 16-18; idempotency check guards signal_id duplication but not symbol-already-open | HIGH | High (confirmed occurring) | Open | Maintainer | Implement position manager: skip BUY if symbol already in open trades table. Tracked in `project_execution_requirements.md` |
| R-14 | **`entry_time` NULL on all closed trades** — trade record creation does not populate `entry_time` at fill; all 41 closed trades have NULL entry_time; blocks P&L roundtrip analysis and postmortem pipeline | HIGH | Confirmed | Open | Maintainer | Fix trade record insert in `src/store/pg_store.py` to write `entry_time` at order fill |
| R-15 | **Postmortem pipeline never executed** — `postmortem_diagnosis` is NULL on all 200 trade records; pipeline is either not scheduled or blocked by R-14 (NULL entry_time) | MEDIUM | Confirmed | Open | Maintainer | Unblocked once R-14 fixed; verify Celery beat schedule for postmortem task |

---

## P2-05 Detail (R-01, R-02, R-03)

These three items are a single implementation ticket (P2-05 Execution Edge Cases) that must be resolved before controlled paper trading is authorized.

| Sub-item | File | Line | Description |
|----------|------|------|-------------|
| P2-05-A | `src/workers/portfolio_scheduler.py` | ~738 | `_get_fired_signal_ids()` returns `set()` on Redis error (fail-open) |
| P2-05-B | `src/workers/portfolio_scheduler.py` | ~450 | `ConstraintEnforcer()` instantiated without `net_exposure_cap` kwarg |
| P2-05-C | `src/workers/portfolio_scheduler.py` + `src/portfolio/vol_targeting.py` | ~520 | `PortfolioVolTargeter` runs after `enforce()` and can re-violate the cap |

---

## Closed Risks (for reference)

| ID | Risk | Closed in | Commit |
|----|------|-----------|--------|
| CR-01 | PG connection pool leak | P0 forensic pass | `c4ab1b6` |
| CR-02 | Ensemble weights not read from Redis | P0 forensic pass | `c4ab1b6` |
| CR-03 | LOO ICIR per-model data source wrong | P0 forensic pass | `c4ab1b6` |
| CR-04 | Execution idempotency (in-flight orders) | P0 forensic pass | `c4ab1b6` |
| CR-05 | Kill-switch no TTL / no halted_by_operator flag | P0 forensic pass | `c4ab1b6` |
| CR-06 | Regime default fail-open (1.0×) | P0 forensic pass | `c4ab1b6` |
| CR-07 | Portfolio concentration cap absent | P0 forensic pass | `c4ab1b6` |
| CR-08 | API authentication on public endpoints | P0 forensic pass | `c4ab1b6` |
| CR-09 | SentimentWorker in-flight queue (lmove) | P0 forensic pass | `c4ab1b6` |
| CR-10 | Weight guardrail mean-ICIR floor | P0 forensic pass | `c4ab1b6` |
| CR-11 | S7 accidentally wired in orchestrator | P0-13 | `6d86d3f` |
| CR-12 | S1 in live mode without 90-day paper period | P0-01 demoted | `cb1d43a` |
| CR-13 | P2-05-A: idempotency fail-open on Redis down | P2-05 | `55cbf56` |
| CR-14 | P2-05-B: net exposure cap not wired from config | P2-05 | `55cbf56` |
| CR-15 | P2-05-C: VolTargeter re-violates cap after enforce() | P2-05 | `55cbf56` |
