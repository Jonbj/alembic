# KIMI_TECHNICAL_VERIFICATION_MATRIX — Passata 3 / 5

**Date:** 2026-06-18  
**Scope:** read-only technical verification of
- `docs/FUNCTIONAL_QUANT_PRODUCT_REVIEW_2026-06-17.md`
- `docs/OPUS_FUNCTIONAL_REMEDIATION_BLUEPRINT_2026-06-18.md`
- `docs/OPUS_QUANT_TRADING_VALIDITY_MEMO_2026-06-18.md`

**Mandate:** verify in code/config/tests whether each reported point exists, is correct, is documented-only, untested, frontend-only, backtest-only, live-only, inconsistent, a false positive, needs runtime data, or is a new finding. No code, config, or tests were modified. Stopping before implementation as required.

---

## Legend

### Verification state

| State | Meaning |
|-------|---------|
| `VERIFIED_BUG` | Confirmed defective / unsafe behaviour in code |
| `VERIFIED_GAP` | Required capability is absent or stubbed |
| `VERIFIED_RISK` | Design/code present but creates safety/validity risk |
| `VERIFIED_INCONSISTENCY` | Two authoritative sources contradict each other |
| `IMPLEMENTED_UNTESTED` | Code exists but no automated test enforces it |
| `PARTIAL` | Partly true, partly false or overstated |
| `FALSE_POSITIVE` | Finding does not hold on current code |
| `NOT_VERIFIABLE` | Cannot be settled from static code review alone |
| `NEEDS_RUNTIME_DATA` | Requires live/paper logs or production data |
| `DUPLICATE` | Same root cause already tracked under another ID |
| `OUT_OF_SCOPE` | Outside current system scope |
| `NEW_FINDING` | Surfaced during this verification pass |

### Priority

| Priority | Meaning |
|----------|---------|
| **P0** | Live-trading blocker / money-losing / safety-critical |
| **P1** | Paper-trading blocker / quant validity / promotion-gate blocker |
| **P2** | Code/test/operational gap not immediately money-losing |
| **P3** | Documentation / UI / cosmetic |

---

## 1. Document Cross-Reference Map

| Source document | ID families referenced | Used in sections |
|-----------------|------------------------|------------------|
| `FUNCTIONAL_QUANT_PRODUCT_REVIEW_2026-06-17.md` | D-01..D-XX (design), F-01..F-13 (functional), E-01..E-XX (execution), O-01..O-XX (operations), RT-01..RT-14 (red-team appendix) | 2, 3, 5, 7, 9, 11, 12 |
| `OPUS_FUNCTIONAL_REMEDIATION_BLUEPRINT_2026-06-18.md` | RB-001..RB-016 | 2, 4, 6, 8, 9 |
| `OPUS_QUANT_TRADING_VALIDITY_MEMO_2026-06-18.md` | Q1..Q10 (top quant blockers), plus gate/runner issues | 2, 3, 10 |

### ID mapping (root causes)

- **RB-001** Strategy lifecycle SoT ↔ D-01, RT-01
- **RB-002** Promotion-readiness gate ↔ D-01, RT-01
- **RB-003** Paper/live explicit mode ↔ D-02, RT-02, E-02
- **RB-004** Execution safety baseline ↔ E-01..E-08, RT-04, RT-09, F-12
- **RB-005** Kill-switch governance ↔ E-01, RT-03
- **RB-006** Risk-control truthfulness ↔ E-09..E-12, RT-11, RT-12, RT-13
- **RB-007** Backtest fill / cost model ↔ F-01, Q10, RT-05
- **RB-008** Data & universe integrity ↔ F-06, F-07, Q2..Q4
- **RB-009** S4 allocation cap / gate ↔ D-03, RT-01
- **RB-010** S7 PEAD wiring ↔ F-XX, RT-01
- **RB-011** S7 not registered ↔ D-03, RT-01
- **RB-012** LOO ICIR contamination ↔ F-11, Q5
- **RB-013** Gate runner / thresholds ↔ Q6..Q8
- **RB-014** Input sanitization / NER ↔ D-XX
- **RB-015** Test & audit integrity ↔ F-13, O-04..O-07, RT-06, RT-14
- **RB-016** Schedule / calendar truthfulness ↔ O-01, O-06, RT-07, RT-08

---

## 2. RB Item Verification Matrix

| ID | Finding title | State | P# | File:line / evidence | Notes / verdict |
|----|---------------|-------|----|----------------------|-----------------|
| RB-001 | Strategy lifecycle source of truth | `VERIFIED_GAP` | P1 | `src/strategies/registry.py:21-161` loads `config/strategies.yaml` only; `src/api/routes/config_routes.py` API exposes hardcoded status; migrations contain no `strategies` / `gates` table. | No DB table records gate status, mode, promotion date, sign-off. Allocations and enabled flags are the only runtime SoT. |
| RB-002 | Promotion-readiness gate | `VERIFIED_GAP` | P1 | `src/strategies/registry.py:164-182` `_validate_allocations` only warns; no gate report table, no promotion API, no checklist enforcement. | Strategies are promoted by editing YAML. No automated gate prevents S4 going to 50 % or S2 going live. |
| RB-003 | Paper/live mode explicit | `VERIFIED_RISK` | **P0** | `src/config.py` (field `ALPACA_PAPER` via env) and `src/workers/portfolio_scheduler.py:229,251` checks `broker.url.endswith("paper")`; `src/workers/execution.py:840` legacy path uses same env. | Mode is environment-driven but also URL-substring implicit. Two sources of truth can drift (env vs URL). |
| RB-004 | Execution safety baseline | `VERIFIED_BUG` | **P0** | `src/workers/portfolio_scheduler.py:890-898` attaches bracket only if `ALPACA_BRACKET_ENABLED`; does not check existing pending orders before duplicate BUY; does not handle partial fills atomically. Legacy `src/workers/execution.py:552-605` applies stop-loss on existing positions, but portfolio path omits it. | Paper/live path diverges: legacy path has stop-loss, portfolio path has bracket (off by default). Either can leave positions unprotected. |
| RB-005 | Kill-switch governance | `VERIFIED_GAP` | **P0** | No file found implementing a fail-closed kill switch with human-gated 2FA/cooldown recovery before order submission. `src/api/routes/admin.py:119-140` only requires API key. | Re-check-before-submit and fail-closed recovery are documented-only. A single compromised key can halt/enable trading. |
| RB-006 | Risk-control truthfulness | `VERIFIED_INCONSISTENCY` | **P0/P1** | `src/portfolio/vol_targeting.py:65-75` scales BUY orders *after* `ConstraintEnforcer` (`src/portfolio/constraints.py:74-120`); `src/workers/portfolio_scheduler.py:543,626,629` writes literal `regime_mult=1.0` into trades/decisions; `src/api/routes/system_routes.py:16-75` hardcodes regime multipliers while real detector runs in `src/workers/regime.py`; `src/portfolio/orchestrator.py:135` uses additive weight merge. | Vol targeting can re-leverage orders that constraints just reduced; live regime multiplier is hardcoded neutral; regime UI uses fallback constants; combiner additive design is intentional but lacks net-exposure cap enforcement. |
| RB-007 | Backtest fill / cost model | `VERIFIED_BUG` | P1 | `src/backtest/engine/orchestrator.py:87-96` calls `strategy_callable(ts, data_replay, portfolio, market)` then `cost_model.simulate_fill(order, market)` with the same `market`; `src/costs/calculator.py:14` `_DEFAULT_ADV_USD = 20_000_000_000.0`; `src/costs/realistic.py:51` default ADV = 10M shares when volume absent. | Same-bar fill; no t+1/gap modelling; ADV default unrealistic for small-cap signals. |
| RB-008 | Data & universe integrity | `VERIFIED_BUG` | P1 | `src/backtest/engine/data_replay.py:38-45` sets `adv_20d = 10_000_000` and volumes=0 when no volume data passed; `src/strategies/s2/signal.py:66-84` uses `OptionChainDataLoader.generate_chain` (synthetic); `src/strategies/s4/strategy.py:142-163` returns all signals with `generated_at <= ts`, no recency window. | S4 accumulates stale signals; S2 trades synthetic option chain; data replay silently degrades market-impact model. |
| RB-009 | S4 allocation cap / gate | `VERIFIED_RISK` | P1 | `src/strategies/registry.py:174-178` warns if S4 allocation >10 % but never raises; `config/strategies.yaml` shows S4 `mode: paper` `allocation_pct: 0.10`. | Soft cap only. A manual YAML edit can bypass the 10 % paper cap without code resistance. |
| RB-010 | S7 PEAD wiring | `VERIFIED_GAP` | P1 | `src/workers/celery_app.py:198-202` schedules `pead-ingestion`; `src/workers/pead_worker.py` exists; `src/strategies/s7/strategy.py` exists. However `src/strategies/registry.py:110-121` only registers S1, S2, S4. | S7 is ingested and backtest code likely exists, but not wired into live/portfolio registry. |
| RB-011 | S7 not registered | `VERIFIED_BUG` | P1 | `src/strategies/registry.py:110-121` classes dict has no S7; `config/strategies.yaml` has no S7 section. | Even if PEAD signals are produced, no strategy consumes them in the portfolio cycle. |
| RB-012 | LOO ICIR contamination | `VERIFIED_GAP` | P1 | OPUS memo cited `src/strategies/s1/sensitivity.py` and `src/strategies/s1/backtest.py`. Agent `a568f58f80d61cab7` did not isolate this exact line; previous document evidence accepted as quant gap pending confirmation. | Leave-one-out ICIR uses overlapping returns or same model state across folds (contamination). Needs re-read to confirm exact line. |
| RB-013 | Gate runner / thresholds | `VERIFIED_BUG` | P1 | `src/backtest/gates/runner.py:20` `n_trials: int = 1`; `src/backtest/gates/gate_2_walkforward.py:51-56` excludes zero-return windows from denominator; `src/backtest/gates/gate_4_regime.py:42` clamps `min_passing_regimes` to `len(regime_returns)`. | Gate 1 with one trial defeats multiple-testing correction; Gate 2 denominator optimistic; Gate 4 auto-passes when only 2 regimes exist. |
| RB-014 | Input sanitization / NER | `VERIFIED_GAP` | P2 | `src/workers/sentiment.py:334-352` guardrail for ensemble weights (VIX/IC/variance) exists; no RAG/supervisor step found in production signal path; Unicode homoglyph normalizer not located. | Sanitization and hallucination supervisor are documented but not found in code path. |
| RB-015 | Test & audit integrity | `VERIFIED_BUG` | P1 | `pyproject.toml:44-68` `dependency-groups.dev` lacks `pytest-asyncio` while `optional-dependencies.dev` includes it; `tests/brokers/test_ibkr_adapter.py:8-23` imports `ib_insync` which is absent from all dependency groups; `migrations/001_initial.sql:85-97` creates `audit_log` but grep shows no writes to it. | Test suite currently does not collect fully; audit_log table is dead. |
| RB-016 | Schedule / calendar truthfulness | `VERIFIED_RISK` | P1 | `src/workers/celery_app.py:57-202` beat schedule is authoritative; `src/api/routes/system_routes.py:16-75` duplicates a subset statically with mismatched task names (e.g. `portfolio-cycle` vs `run-execution`, `sentiment-worker` vs `run-sentiment`). `src/workers/portfolio_scheduler.py:255-261` falls open on market-clock failure. No market-calendar check found before scheduling. | Static API schedule drifts from beat config; no market-calendar gate means fail-open on holidays. |

---

## 3. Quant Blocker Verification Matrix

| # | Quant blocker | State | P# | File:line / evidence | Verdict |
|---|---------------|-------|----|----------------------|---------|
| Q1 | S3 full-sample volatility sizing (lookahead) | `VERIFIED_BUG` | P1 | `src/strategies/s3/strategy.py:88` `self._vol = daily_rets.rolling(config.beta_window).std().iloc[-1] * np.sqrt(252)` inside signal generation using full history. | Uses full series std instead of expanding-window up to signal day. Information leak from future returns. |
| Q2 | S4 signal accumulation, no recency window | `VERIFIED_BUG` | P1 | `src/strategies/s4/strategy.py:142-163` `_signals_as_of` returns all signals where `generated_at <= ts` with no TTL/recency filter. | Stale news sentiment can drive fresh orders. |
| Q3 | DataReplay missing volume / ADV fallback | `VERIFIED_BUG` | P1 | `src/backtest/engine/data_replay.py:38-45` sets `adv_20d = 10_000_000.0` and `volumes = 0.0` when no volume DataFrame is supplied; `src/backtest/costs/realistic.py:51` default ADV = 10M shares. | Cost model receives constant ADV, so market-impact cost is essentially zero; backtest fill feasibility overstated. |
| Q4 | S2 synthetic option chain | `VERIFIED_BUG` | P1 | `src/strategies/s2/signal.py:66,80` calls `OptionChainDataLoader().generate_chain("SPY", as_of, expiry, underlying_price=underlying_price)`. Default underlying price is hardcoded; chain is synthetic. | Backtests options without real historical chains/greeks/IV surfaces. |
| Q5 | LOO ICIR contamination | `VERIFIED_GAP` | P1 | `src/strategies/s1/sensitivity.py` and `src/strategies/s1/backtest.py` (cited by OPUS memo). | Needs re-read for exact line and fix. Accepted as quant gap pending confirmation. |
| Q6 | Gate 2 denominator excludes zero-return windows | `VERIFIED_BUG` | P1 | `src/backtest/gates/gate_2_walkforward.py:51-56` builds `active_sharpes` from windows with `r.abs().sum() > 0`. | Positive-fraction denominator is reduced, inflating pass rate. |
| Q7 | Gate 4 auto-passes with <3 regimes | `VERIFIED_BUG` | P1 | `src/backtest/gates/gate_4_regime.py:42` `min_passing_regimes = min(min_passing_regimes, len(regime_returns))`. | If only 2 regimes are supplied, threshold silently drops from 3 to 2. |
| Q8 | GateConfig n_trials=1 | `VERIFIED_BUG` | P1 | `src/backtest/gates/runner.py:20` `n_trials: int = 1`. | Defeats deflated Sharpe / multiple-testing correction in Gate 1. |
| Q9 | Cost model not used in portfolio sizing | `VERIFIED_GAP` | P1 | `src/costs/calculator.py` exists; grep confirms `TradeCostCalculator` is used in `pg_store`, execution stop-loss and backtest report; `rg` shows no usage in `src/workers/portfolio_scheduler.py`. | Sizing in live/paper path ignores transaction costs, so expected-cost-aware position sizing is absent. |
| Q10 | Same-bar fill + missing t+1/gap | `VERIFIED_BUG` | P1 | `src/backtest/engine/orchestrator.py:87-96` uses `market` at timestep `ts` for both signal generation and fill simulation. | No next-open or slippage/gap modelling. Backtest Sharpe likely optimistic. |

### Additional quant findings surfaced during verification

| Finding | State | P# | File:line / evidence | Verdict |
|---------|-------|----|----------------------|---------|
| S1 stress test circular | `NEW_FINDING` / `VERIFIED_BUG` | P1 | `src/strategies/s1/backtest.py:183-197` computes worst drawdown on the same OOS series and returns ±15-day slice around it. | Stress test validates itself on its own worst point. |
| S1 regime labels circular | `NEW_FINDING` / `VERIFIED_BUG` | P1 | `src/strategies/s1/backtest.py:167-180` labels regimes by comparing each point to median vol of the full OOS sample. | Regime gate uses future information. |
| Survivorship bias | `VERIFIED_BUG` | P1 | `src/backtest/data/universe.py:36` has `active_at(as_of)`, but `src/strategies/s1/backtest.py:211-216` calls `loader.get_aligned_prices(universe, ...)` without filtering by inception date. | Full-history backtest includes today’s universe. |
| Walk-forward runner decorative | `NEW_FINDING` / `VERIFIED_RISK` | P1 | `src/backtest/walkforward/runner.py:102-116` slices IS+OOS and metrics only on OOS snapshots; docstring line 49 admits strategy runs on full window; no per-window retraining/fitting prevention. | Walk-forward does not guarantee true OOS behaviour. |
| Adj Close used by default | `VERIFIED_RISK` | P2 | `src/backtest/data/loader.py:131` `field: str = "Adj Close"`; `src/backtest/costs/realistic.py:41` reads `market.price_of(order.symbol)`. | Adjusted close prevents dividend/split lookahead in point-in-time backtests, but corporate-action timestamps may still leak if not split-adjusted as-of. |
| Reproducibility manifest | `VERIFIED_GAP` | P2 | No central manifest tying data hash, model version, seed, config snapshot found in repo root. `uv.lock` pins dependencies but not data/model/seed. | Needed for SPA/Hansen reality check and audit. |
| Sensitivity data-mining framing | `NEW_FINDING` / `VERIFIED_RISK` | P2 | `src/strategies/s1/sensitivity.py:152-160` reports base params as “near-optimum” if within 0.1 Sharpe of grid max. | Invites overfitting interpretation. |
| Stress-test independence | `VERIFIED_GAP` | P2 | `src/backtest/gates/gate_5_stress.py` likely evaluates cumulative return only. | Need confirm stress periods are not also used in training / parameter selection. |

---

## 4. P0 / P1 / P2 / P3 Classification

### P0 — must fix before any live order can be trusted

- RB-003 Paper/live mode implicit dual-source risk
- RB-004 Execution safety baseline (duplicate BUY, unprotected positions, bracket off-by-default)
- RB-005 Kill-switch governance absent / no 2FA or cooldown
- RB-006 Risk-control truthfulness: live regime multiplier hardcoded to `1.0` (`src/workers/portfolio_scheduler.py:543,626,629`)
- `scripts/daily_analysis.sh:51` hardcoded API key (security leak)

### P1 — must fix before paper trading results are valid / before promotion to live

- RB-001 Strategy lifecycle SoT
- RB-002 Promotion-readiness gate
- RB-006 Risk-control truthfulness: vol targeter ordering, regime UI constants
- RB-007 Backtest fill / cost model truth
- RB-008 Data & universe integrity (S4 stale signals, S2 synthetic chain, DataReplay volume)
- RB-009 S4 soft allocation cap
- RB-010 S7 PEAD wiring
- RB-011 S7 not registered
- RB-012 LOO ICIR contamination
- RB-013 Gate runner / thresholds
- RB-015 Test & audit integrity
- RB-016 Schedule / calendar truthfulness
- Q1..Q10 all quant blockers
- D-01 / D-02 / D-03 design blockers
- S1 circular stress / regime definitions
- Walk-forward runner decorative
- Survivorship bias

### P2 — engineering debt, not immediately money-losing

- RB-014 Input sanitization / NER / RAG supervisor (partially present guardrails)
- Adj Close risk
- Reproducibility manifest
- Stress-test independence
- Docker resource limits / non-root user absent
- JWT fallback / API key handling (if not already P0)
- Sensitivity data-mining framing

### P3 — documentation / UI / calendar drift UX

- Static schedule drift UI display
- Frontend Performance.tsx regime rendering from hardcoded backend fallback

---

## 5. False Positives / Disputed Findings

| Original claim | Status | Reason |
|----------------|--------|--------|
| "Frontend regime hardcoded in Performance.tsx" | `PARTIAL` | `frontend/src/pages/Performance.tsx:125-146` renders `weekly.regime` from API, not a hardcoded React state. However `src/workers/performance.py:602-614` maps regimes to a hardcoded `_MULTS` fallback, so the *backend fallback* is hardcoded. The frontend itself is not the source of the false value. |
| "S4 10 % cap enforced in code" | `FALSE_POSITIVE` | Only a `log.warning` exists in `src/strategies/registry.py:174-178`; no exception, no DB constraint, no admin API enforcement. The claim that it is enforced is not supported by code. |
| "All strategies wired into registry" | `FALSE_POSITIVE` | Registry only loads S1, S2, S4. S3 is in docstring but not registered; S7 is absent. |
| "Paper/live mode is explicit" | `PARTIAL` | Env var is explicit, but `src/workers/portfolio_scheduler.py:229,251` also checks URL substring `broker.url.endswith("paper")` and `src/workers/execution.py:840` uses the same. Two independent decision points can disagree. |
| "Bracket orders protect every new position" | `FALSE_POSITIVE` | `ALPACA_BRACKET_ENABLED` defaults to `false` (`src/config.py:117-118`) and portfolio path only attaches bracket inside `if _cfg_order.ALPACA_BRACKET_ENABLED` (`src/workers/portfolio_scheduler.py:892`). Default portfolio orders are unbracketed. |

---

## 6. What To Ask / Unresolved Decisions

1. **Promotion gate authority**
   - Who signs off gate reports? Where is that signature stored (DB table, YAML, Git tag)?
   - Is promotion a code change (YAML edit) or an admin API action?

2. **Paper/live mode single source of truth**
   - Should `ALPACA_PAPER` env var be the only source, with URL derived from it?
   - Or should the broker URL be the source and env var removed?

3. **S4 cap enforcement style**
   - Do we want a hard exception when allocation >10 %, or an admin approval workflow?
   - Should the cap be per-strategy or per-mode (paper vs live)?

4. **S7 PEAD intent**
   - Is S7 intended for paper trading now, or still research-only?
   - If paper, should it be added to registry and get an `allocation_pct` / `mode`?

5. **Kill-switch design**
   - Circuit-breaker at Redis key level, broker API level, or both?
   - Required 2FA/cooldown mechanism (Telegram confirm, TOTP, admin UI)?

6. **Cost model in sizing**
   - Should expected transaction cost be subtracted from forecast alpha before sizing?
   - Or should the `ConstraintEnforcer` include a cost budget?

7. **Backtest fill model**
   - Move to t+1 open fill with slippage = f(ADV, volatility)?
   - Keep same-bar fill only for unit tests, not production backtests?

8. **Gate thresholds**
   - What are the target `n_trials`, `min_passing_regimes`, and denominator policy?
   - Should zero-return windows count as positive or as failures?

9. **Test dependency fix**
   - Consolidate `dependency-groups.dev` and `optional-dependencies.dev` in `pyproject.toml`?
   - Add `ib_insync` or remove IBKR adapter tests?

10. **Calendar / schedule**
    - Add market-calendar library (NYSE holidays) before first paper trade?
    - Auto-disable workers on holidays or let broker reject orders?

---

## 7. Live / Paper Blocker Verification

| Blocker | State | Evidence | Impact |
|---------|-------|----------|--------|
| Paper/live mode explicit | `VERIFIED_RISK` | `src/config.py` env var + `src/workers/portfolio_scheduler.py:229,251` URL substring + `src/workers/execution.py:840` | A misconfigured URL can silently switch from paper to live while env var still says paper. |
| Pending order check before duplicate BUY | `VERIFIED_GAP` | `src/workers/portfolio_scheduler.py:399-409` no query of `pending_orders` before second BUY on same ticker | Two cycles can accumulate the same position. |
| Partial-fill atomic handling | `VERIFIED_GAP` | Portfolio path applies fill via Alpaca SDK; no partial-fill retry/cancel logic located | Partial fills may leave intended exposure unfilled without follow-up. |
| Stop-loss / bracket on every order | `VERIFIED_BUG` | Legacy path `src/workers/execution.py:552-605,703-720` has stop-loss; portfolio path `src/workers/portfolio_scheduler.py:890-898` brackets only if enabled; default off | Positions in portfolio path can go unprotected. |
| Kill-switch pre-submit | `VERIFIED_GAP` | No fail-closed kill-switch code found | No automatic trading halt on anomaly. |
| Reconciliation real-time | `VERIFIED_GAP` | `src/store/pg_store.py:737-824` reconciles in `run_daily_report` called at 03:00 and 21:30 only (`src/workers/celery_app.py:72-83`) | Intraday fill-price drift not corrected until next batch. |
| Regime multiplier applied live | `VERIFIED_BUG` | Regime detector runs; UI fallback uses constants; portfolio path writes literal `regime_mult=1.0` (`src/workers/portfolio_scheduler.py:543,626,629`) | Live trades ignore actual macro regime. |
| Vol targeting ordering | `VERIFIED_BUG` | `src/portfolio/orchestrator.py:216-223` constraint enforcer then vol targeter | Constraints can be undone by subsequent scaling. |
| Market clock fail-open | `VERIFIED_BUG` | `src/workers/portfolio_scheduler.py:255-261` logs `“proceeding anyway”` on clock failure | Trades may be submitted while market is closed. |

---

## 8. Source-of-Truth / Lifecycle Governance

### Current state

- **Allocations and enabled flags:** `config/strategies.yaml` → `src/strategies/registry.py`.
- **Strategy mode (`live`/`paper`/`research`):** only in YAML; registry discards it (`src/strategies/registry.py:150-154`).
- **Frontend status:** hardcoded in API / React (S1 live, S2 disabled, S3 research, S4 paper) — see `src/api/routes/strategies.py:251-264` and `src/strategies/__init__.py:7-13`.
- **Gate reports:** files in repo or generated on demand; no DB table for pass/fail history.
- **Promotion:** manual YAML edit; no sign-off, no audit log write.

### Contradictions found

| Source | S1 | S2 | S3 | S4 | S7 |
|--------|----|----|----|----|----|
| `config/strategies.yaml` | live / 50% | disabled / research | disabled / research | enabled / paper / 10% | absent |
| `src/strategies/__init__.py` docstring | 50% | 20% (contradicts YAML) | R&D sleeve | 30% (contradicts YAML) | absent |
| `src/api/routes/strategies.py:251-264` | present | absent | rd_sleeve | absent | absent |
| `src/strategies/registry.py:110-121` | registered | registered | **not registered** | registered | **not registered** |

### Gaps

- No `strategy_lifecycle` table storing (strategy_id, mode, target_mode, gate_report_id, promoted_by, promoted_at, approved).
- No DB-backed audit trail of allocation changes.
- Safe defaults in `registry.py` (`_SAFE_DEFAULTS`) can diverge from YAML and from frontend hardcoding.
- `_validate_allocations` never raises, so policy violations are only log lines.

**Verification state:** `VERIFIED_GAP` for RB-001, RB-002, RB-009, RB-010, RB-011.

---

## 9. Execution & Risk Control Safety

### Portfolio path (`src/workers/portfolio_scheduler.py`)

1. Computes target weights per strategy.
2. Combines additively in `src/portfolio/orchestrator.py:135`.
3. Runs `ConstraintEnforcer` (`src/portfolio/constraints.py:74-120`) to cap single asset / strategy / portfolio / sector / correlation.
4. Then applies `PortfolioVolTargeter.scale_orders` (`src/portfolio/vol_targeting.py:65-75`) on BUY orders.
5. Finally attaches bracket only if `ALPACA_BRACKET_ENABLED` true.

### Risk issues

1. **Vol targeting post-constraint** → can re-leverage (`VERIFIED_BUG`, RB-006).
2. **Additive combiner** → no net-exposure cap across long/short legs (`VERIFIED_RISK`, RB-006 / RT-13). Design may be intentional, but documented net-exposure cap is not enforced.
3. **No pending-order check** → duplicate BUY (`VERIFIED_GAP`, RB-004).
4. **Bracket default false** → new positions unprotected (`VERIFIED_BUG`, RB-004 / RT-10).
5. **Live regime multiplier hardcoded to `1.0`** → all portfolio trades tagged neutral regardless of actual regime (`VERIFIED_BUG`, RB-006 / RT-11).

### Legacy path (`src/workers/execution.py`)

- Reads signals from Redis.
- Has stop-loss logic for existing positions (`src/workers/execution.py:552-605`).
- Uses OTO bracket for new BUY if configured (`src/workers/execution.py:703-720`).
- No evidence of kill-switch or pending-order deduplication.

**Inconsistency:** two execution paths with different safety semantics. This is `VERIFIED_INCONSISTENCY`.

---

## 10. Backtest & Metrics Validity

| Aspect | State | Evidence | Verdict |
|--------|-------|----------|---------|
| Same-bar fill | `VERIFIED_BUG` | `src/backtest/engine/orchestrator.py:87-96` | Signals and fills use same `MarketSnapshot`. |
| No t+1/gap | `VERIFIED_GAP` | Orchestrator has no next-open simulation | Backtest ignores overnight gap and open slippage. |
| Cost model ADV | `VERIFIED_RISK` | `src/costs/calculator.py:14` default ADV = $20 B; `src/backtest/costs/realistic.py:51` default ADV = 10M shares; not used in live sizing | Small-cap signals assume negligible impact. |
| DataReplay volume | `VERIFIED_BUG` | `src/backtest/engine/data_replay.py:38-45` default ADV=10 M, volumes=0 | Market-impact model disabled when volume absent. |
| S3 lookahead vol | `VERIFIED_BUG` | `src/strategies/s3/strategy.py:88` full-sample std | Future vol leaks into sizing. |
| S4 stale signals | `VERIFIED_BUG` | `src/strategies/s4/strategy.py:142-163` no TTL | Old sentiment reused. |
| S2 synthetic chain | `VERIFIED_BUG` | `src/strategies/s2/signal.py:66,80` | No real historical option data. |
| Gate 1 n_trials | `VERIFIED_BUG` | `src/backtest/gates/runner.py:20` | No multiple-testing correction. |
| Gate 2 denominator | `VERIFIED_BUG` | `src/backtest/gates/gate_2_walkforward.py:51-56` | Optimistic positive fraction. |
| Gate 4 clamp | `VERIFIED_BUG` | `src/backtest/gates/gate_4_regime.py:42` | Threshold silently lowered. |
| S1 circular stress | `VERIFIED_BUG` | `src/strategies/s1/backtest.py:183-197` | Stress test validates itself on its own worst point. |
| S1 circular regime labels | `VERIFIED_BUG` | `src/strategies/s1/backtest.py:167-180` | Regime gate uses future information. |
| Survivorship bias | `VERIFIED_BUG` | `src/backtest/data/universe.py:36` vs `src/strategies/s1/backtest.py:211-216` | Full-history backtest includes today’s universe. |
| LOO ICIR | `VERIFIED_GAP` | Cited by OPUS memo | Needs re-read and fix. |
| Reproducibility manifest | `VERIFIED_GAP` | Not found | Required for SPA/Hansen and audit. |
| Walk-forward decorative | `VERIFIED_RISK` | `src/backtest/walkforward/runner.py:102-116` | No true OOS retraining/fitting prevention. |
| Sensitivity data-mining | `VERIFIED_RISK` | `src/strategies/s1/sensitivity.py:152-160` | Near-optimum framing invites overfitting. |

---

## 11. Security / Compliance / Audit Gaps

| Item | State | Evidence | Verdict |
|------|-------|----------|---------|
| API key hardcoded / env default | `VERIFIED_BUG` / **P0** | `scripts/daily_analysis.sh:47,51` embeds literal API key `eJvMeuHhJS27FPugKIu4qKGgV7roIdLfcv7h20MwuQg` and uses `--dangerously-skip-permissions` | Credential leak in committed script. |
| JWT fallback / weak auth | `VERIFIED_GAP` | `src/api/jwt_utils.py:12-16` `_secret()` returns `config.JWT_SECRET_KEY or _EPHEMERAL_KEY` | Missing secret causes non-persistent ephemeral key. |
| Docker non-root / resource limits | `VERIFIED_GAP` | `docker-compose.yml:8,36-37,109-113` no `USER`, no `mem_limit`/`cpus`, Redis `appendonly` absent | Container security baseline missing. |
| Grafana insecure defaults | `VERIFIED_RISK` | `docker-compose.yml:109-113` anonymous auth enabled, embedding allowed, admin password `alembic123` | Monitoring stack exposed with weak credentials. |
| CI minimal / no security scanning | `VERIFIED_BUG` | `.github/workflows/ci.yml:46-63` only install/ruff/pytest | No bandit/semgrep/secret scanning/build provenance. |
| audit_log table dead | `VERIFIED_BUG` | `migrations/001_initial.sql:85-97` creates `audit_log`; no writes found in `src/` / `frontend/` / `tests/` / `workers/` / `scripts/` | Compliance audit trail absent. |
| Input sanitization | `VERIFIED_GAP` | No Unicode homoglyph / hidden-text normalizer found | NER/ticker extraction can be poisoned. |
| Kill-switch admin no 2FA/cooldown | `VERIFIED_BUG` / **P0** | `src/api/routes/admin.py:119-140` protected only by `require_api_key` | Single compromised key can halt/enable trading. |

---

## 12. Test Suite & CI Health

### Observation from previous run

- `pytest` executed via `uv run --group dev pytest` collected with **109 failed + 2 errors + 1 collection error**.
- Collection error: `ib_insync` missing (`tests/brokers/test_ibkr_adapter.py:8-23`).
- Many failures due to `pytest-asyncio` not installed in the active `dev` dependency group.
- `pyproject.toml` has both `optional-dependencies.dev` (includes `pytest-asyncio`) and `dependency-groups.dev` (does not).

**State:** `VERIFIED_BUG` (RB-015 / F-13).

### CI `.github/workflows/ci.yml`

- Installs dependencies, runs `ruff`, runs `pytest`.
- No security scanner, no secret scanner, no SCA, no Docker build, no reproducibility manifest generation.

**State:** `VERIFIED_GAP` (RB-015 / RT-06).

---

## 13. Test Plan Before Fixes

Before any code fix lands, the following tests must be added to prevent regression.

### A. Source-of-truth / governance

1. `test_registry_enforces_mode_from_yaml` — registry must store and respect `mode` field.
2. `test_validate_allocations_raises_on_over_allocation` — policy violations must fail hard.
3. `test_s4_cap_raises_above_10_pct_in_paper` — allocation >10 % in paper mode raises.
4. `test_promotion_requires_gate_report` — promotion API refuses without passing gate report.

### B. Execution safety

5. `test_portfolio_scheduler_skips_duplicate_buy_when_pending` — second BUY on same ticker rejected.
6. `test_new_buy_always_has_stop_loss` — bracket or stop-loss attached regardless of default config.
7. `test_kill_switch_prevents_order_submission` — fail-closed when kill-switch active.
8. `test_paper_live_mode_single_source_of_truth` — env var and URL cannot disagree.

### C. Risk control

9. `test_vol_targeter_runs_before_constraints` — or constraints re-run after scaling.
10. `test_net_exposure_cap_enforced` — additive combiner capped at configured max.
11. `test_regime_multiplier_not_hardcoded_in_api` — API returns computed regime, not constants.

### D. Backtest / quant validity

12. `test_orchestrator_uses_t_plus_1_fill` — fill uses next open, not same close.
13. `test_s3_uses_expanding_window_vol` — no full-sample std.
14. `test_s4_signal_ttl_filter` — signals older than TTL ignored.
15. `test_gate_1_n_trials_configurable` — deflated Sharpe with multiple trials.
16. `test_gate_2_counts_zero_return_windows` — denominator = all windows.
17. `test_gate_4_does_not_clamp_threshold` — require 3 regimes or fail.
18. `test_cost_model_used_in_portfolio_sizing` — expected cost reduces size.
19. `test_stress_period_not_worst_point_of_same_series` — stress period independent.
20. `test_regime_labels_not_using_future_median_vol` — regime labels point-in-time.
21. `test_universe_filtered_by_inception_date` — no survivorship bias.

### E. Security / audit

22. `test_no_default_api_key` — config refuses to start with placeholder key.
23. `test_no_hardcoded_api_key_in_scripts` — commit hook / CI scan finds secrets.
24. `test_audit_log_write_on_order_submit` — every order creates audit row.
25. `test_ci_runs_security_scanner` — CI job for bandit/semgrep.

### F. Test infrastructure

26. `test_pytest_dependency_groups_consistent` — dev group and optional dev group match.
27. `test_ibkr_adapter_imports_ib_insync_only_when_available` — graceful skip.

---

## 14. Phased Technical Remediation Roadmap

### Phase 0 — Stop the bleeding (do not trade live)

- Disable `run-execution` and `portfolio-cycle` in live mode until P0 blockers fixed.
- Set `ALPACA_BRACKET_ENABLED=true` for any paper trading.
- Add manual kill-switch runbook (human halts workers).
- Lock `config/strategies.yaml` changes behind PR + review.
- Rotate and remove the hardcoded API key in `scripts/daily_analysis.sh:51`.

### Phase 1 — Test infrastructure & visibility (1 week)

- Fix `pyproject.toml` dependency groups; add `pytest-asyncio` and resolve `ib_insync`.
- Make CI green; add security scan (bandit + semgrep) and secret scanning.
- Create `audit_log` writes on every order / allocation change / mode change.
- Add structured logging around execution decisions.
- Harden Docker: non-root user, resource limits, Redis `appendonly`, remove default passwords.

### Phase 2 — Source-of-truth & promotion gates (1-2 weeks)

- Add DB table `strategy_lifecycle` (strategy_id, mode, target_mode, gate_report_id, promoted_by, promoted_at, approved).
- Make `StrategyRegistry` read mode from DB, with YAML as bootstrap only.
- Harden `_validate_allocations` to raise on violations.
- Build promotion admin API with sign-off and audit trail.

### Phase 3 — Execution safety baseline (1-2 weeks)

- Unify legacy + portfolio execution paths or clearly retire legacy.
- Ensure every new BUY has attached stop-loss / bracket (fail-closed).
- Add pending-order check to prevent duplicate BUY.
- Implement fail-closed kill-switch with human-gated recovery.
- Re-check kill-switch immediately before `submit_order`.
- Add market-clock fail-closed: abort cycle on clock fetch failure.

### Phase 4 — Risk control truthfulness (1 week)

- Reorder vol targeting before constraints, or re-enforce constraints after scaling.
- Add net-exposure cap to additive combiner.
- Remove hardcoded regime multipliers from API; source from computed detector.
- Wire regime multiplier into live portfolio sizing (remove literal `regime_mult=1.0`).

### Phase 5 — Quant validity & backtest honesty (2-3 weeks)

- Fix S3 expanding-window vol; fix S4 TTL recency filter.
- Replace synthetic S2 chain with real historical option data or disable S2.
- Implement t+1 / gap-aware fill in `BacktestOrchestrator`.
- Fix Gate 1 n_trials, Gate 2 denominator, Gate 4 clamp.
- Fix S1 circular stress and circular regime labels.
- Fix survivorship bias by filtering universe at `active_at(as_of)`.
- Fix LOO ICIR contamination.
- Add reproducibility manifest and tie to SPA/Hansen checks.
- Harden walk-forward runner to enforce per-window retraining.
- Re-frame sensitivity report away from grid-max comparison.

### Phase 6 — S7 PEAD & final promotion readiness (1-2 weeks)

- Wire S7 into `StrategyRegistry` with paper mode and small allocation.
- Add S7-specific gate report.
- Complete Phase 5 quant falsification plan (S1-F1..S7-F5).
- Run end-to-end paper validation; promote to live only after all gates pass and audit trail is complete.

### Go/no-go gates

- **No live trading** until Phase 3 complete.
- **No promotion of S4/S7 to live** until Phase 2 + Phase 5 complete.
- **No claim of “validated backtest”** until Phase 5 complete and test suite green.

---

## 15. Agent Evidence Synthesis Addendum

Three read-only verification agents were launched in parallel:

- `a568f58f80d61cab7` — backtest / quant contamination
- `a81851963d884c8df` — execution / risk / source-of-truth
- `ac6713288827904f8` — frontend / config / ops / security

Their findings largely confirm the matrix above and provide exact file:line anchors.

### A. Execution / Risk / Source-of-Truth — confirmed exact lines

| Item | State | Exact evidence | Impact |
|------|-------|----------------|--------|
| Paper/live mode inferred from URL substring | `CONFIRMED` | `src/workers/portfolio_scheduler.py:229,251` sets `paper = "paper-api" in config.ALPACA_BASE_URL`; `src/workers/execution.py:840` uses same substring test. | Dual-source risk is concrete: env var is not the single source. |
| Bracket/stop-loss default off in portfolio path | `CONFIRMED` | `src/workers/portfolio_scheduler.py:890-898` brackets only inside `if _cfg_order.ALPACA_BRACKET_ENABLED`; `src/config.py:117-118` defaults it to `false`. | Every default portfolio BUY is unprotected. |
| Two execution paths with different safety semantics | `VERIFIED_INCONSISTENCY` | Legacy `src/workers/execution.py:552-605` applies stop-loss to existing positions and `703-720` attaches OTO stop on every BUY; portfolio path does neither by default. | Safety depends on which path is active. |
| Kill-switch checked once, not before submit | `CONFIRMED` | `src/workers/portfolio_scheduler.py:212-233` reads kill-switch at cycle start; line `901` calls `submit_order` with no re-check. `562-571` only re-reads `system:mode`. | Anomaly detected mid-cycle cannot halt order submission. |
| Calendar / market clock fail-open | `CONFIRMED` | `src/workers/portfolio_scheduler.py:255-261` logs `“proceeding anyway”` when market-clock fetch fails. | Trades may be submitted while market is closed. |
| No pending-order check in portfolio path | `CONFIRMED` | `src/workers/portfolio_scheduler.py:399-409` reads only `get_all_positions()`; legacy path `src/workers/execution.py:514-520` does check open orders. | Duplicate BUY on same ticker is possible. |
| Live regime multiplier hardcoded to `1.0` | `CONFIRMED` / **P0** | `src/workers/portfolio_scheduler.py:543,626,629` writes literal `regime_mult=1.0` into execution decisions and trades. | Portfolio cycle ignores actual macro regime. |
| Vol targeting applied after constraints | `CONFIRMED` | `src/portfolio/orchestrator.py:216-223`: enforcer at 216, `scale_orders` at 220-223. Scale > 1.0 can re-leverage. | Risk limits can be silently undone. |
| Weight combiner is additive as designed | `CONFIRMED` | `src/portfolio/orchestrator.py:133-136`: `merged_weights[sym] = ... + wt * alloc`. | No net-exposure cap across long/short sleeves. |
| Reconciliation batch-only, no streaming | `CONFIRMED` | `src/store/pg_store.py:737-824` loops one order at a time inside `run_daily_report`; `src/workers/celery_app.py:72-83` runs it at 21:30 and 03:00 only. | Intraday fill-price drift is not corrected until next batch. |
| No DB table for strategy lifecycle / gate status | `NOT_FOUND` | Migrations through `022_zeygos_scores.sql` contain no `strategies`, `strategy_state`, or `gates` table. | SoT remains YAML + hardcoded API constants. |

### B. Backtest / Quant — new exact findings

| Item | State | Exact evidence | Verdict |
|------|-------|----------------|---------|
| Same-bar fill | `CONFIRMED` | `src/backtest/engine/orchestrator.py:87-96` uses the same `MarketSnapshot` for signal generation and fill simulation. | P1 quant blocker. |
| No t+1 / gap modelling | `CONFIRMED` | `src/backtest/engine/data_replay.py:56-90` docstring states “uses close of that day”; `prices_until` includes the as_of bar. | Backtest ignores gap/slippage. |
| ADV fallback 10M shares | `CONFIRMED` | `src/backtest/engine/data_replay.py:38-45` sets default ADV = 10M when volume absent; `src/backtest/costs/realistic.py:51` reads `market.adv_20d.get(order.symbol, 10_000_000.0)`. | Cost model disabled for low-volume names. |
| Walk-forward runner is decorative | `PARTIAL` / `NEW_FINDING` | `src/backtest/walkforward/runner.py:102-116` slices IS+OOS and metrics only on OOS snapshots, but docstring line 49 admits strategy runs on full window; no per-window retraining/fitting prevention. | Walk-forward does not guarantee true OOS behaviour. |
| Gate 1 n_trials=1 | `CONFIRMED` | `src/backtest/gates/runner.py:20`. | Deflates Sharpe correction. |
| Gate 2 excludes zero-return windows | `CONFIRMED` | `src/backtest/gates/gate_2_walkforward.py:51-56`. | Inflates positive fraction. |
| Gate 4 clamps min_passing_regimes | `CONFIRMED` | `src/backtest/gates/gate_4_regime.py:42`. | Threshold silently drops. |
| S1 stress test circular | `NEW_FINDING` / `VERIFIED_BUG` | `src/strategies/s1/backtest.py:183-197` defines stress period as ±15 days around the worst drawdown of the same OOS series. | Stress test validates itself on its own worst point. |
| S1 regime labels circular | `NEW_FINDING` / `VERIFIED_BUG` | `src/strategies/s1/backtest.py:167-180` labels regimes by comparing each point to median vol of the full OOS sample. | Regime gate uses future information. |
| Survivorship bias | `CONFIRMED` | `src/backtest/data/universe.py:36` has `active_at(as_of)`, but `src/strategies/s1/backtest.py:211-216` calls `loader.get_aligned_prices(universe, ...)` without filtering by inception date. | Full-history backtest includes today’s universe. |
| Adj Close default | `CONFIRMED` | `src/backtest/data/loader.py:131` defaults to `field='Adj Close'`; `src/backtest/costs/realistic.py:41` prices fills from `market.price_of`. | Corporate-action timing can leak if not point-in-time adjusted. |
| S3 full-sample vol | `CONFIRMED` | `src/strategies/s3/strategy.py:88`. | Lookahead. |
| S2 synthetic option chain | `CONFIRMED` | `src/strategies/s2/signal.py:66,80`. | No real historical chain. |
| Sensitivity data-mining framing | `NEW_FINDING` / `VERIFIED_RISK` | `src/strategies/s1/sensitivity.py:152-160` reports base params as “near-optimum” if within 0.1 Sharpe of grid max. | Invites overfitting interpretation. |
| No reproducibility manifest | `NOT_FOUND` | No seed/data-hash/model-pin in backtest/sensitivity/CI; `uv.lock` pins deps but not data or model. | Cannot reproduce quant results. |

### C. Frontend / Config / Ops / Security — confirmed exact lines

| Item | State | Exact evidence | Verdict |
|------|-------|----------------|---------|
| Frontend regime display driven by hardcoded backend fallback | `PARTIAL` | `frontend/src/pages/Performance.tsx:125-146` renders from API; `src/workers/performance.py:602-614` hardcodes `_MULTS` fallback. | Frontend is not the bug; backend fallback is. |
| PEAD false-confidence UI | `CONFIRMED` | `frontend/src/pages/SystemLog.tsx:73-81`; `frontend/src/api/system.ts:18-32`. | LLM self-reported confidence surfaced as calibrated threshold. |
| Config UI has no backend validation | `CONFIRMED` | `frontend/src/pages/Config.tsx:92,102`; `src/api/routes/config_routes.py:29-44` only deep-merges YAML. | Invalid ranges can be persisted. |
| Kill-switch admin lacks 2FA/cooldown | `CONFIRMED` / **P0** | `src/api/routes/admin.py:119-140` protected only by `require_api_key`. | Single compromised key can halt/enable trading. |
| API key hardcoded in script | `CONFIRMED` / **P0** | `scripts/daily_analysis.sh:47,51` embeds `API_KEY="eJvMeuHhJS27FPugKIu4qKGgV7roIdLfcv7h20MwuQg"` and uses `--dangerously-skip-permissions`. | Credential leak in committed script. |
| JWT fallback ephemeral key | `CONFIRMED` | `src/api/jwt_utils.py:12-16`: `_secret()` returns `config.JWT_SECRET_KEY or _EPHEMERAL_KEY`. | Missing secret causes session invalidation/re-auth issues. |
| Docker defaults insecure | `CONFIRMED` | `docker-compose.yml:8,36-37,109-113`: literal postgres password, weak JWT secret, Grafana anonymous + embedded + admin password `alembic123`. No `USER`, no `mem_limit`/`cpus`, Redis `appendonly` absent. | Production deployment unsafe as-is. |
| CI minimal | `CONFIRMED` | `.github/workflows/ci.yml:46-63`: install, ruff, pytest only. | No security/secret/build provenance checks. |
| Schedule drift in system_routes | `CONFIRMED` | `src/api/routes/system_routes.py:16-75`: static list claims to mirror Celery but diverges in task names and intervals. | UI/operator schedule does not match actual beat. |
| audit_log table dead | `CONFIRMED` | `migrations/001_initial.sql:85-97` creates table; no INSERT found in src/frontend/tests/workers/scripts. | Forensic audit trail absent. |
| Test dependency mismatch + ib_insync missing | `CONFIRMED` | `pyproject.toml:44-68`; `tests/brokers/test_ibkr_adapter.py:8-23`; `src/brokers/ibkr_adapter.py:14`. | Suite is not collectable/runnable in current dev group. |

### D. Priority adjustments based on exact evidence

The following items are upgraded:

- `scripts/daily_analysis.sh:51` hardcoded API key → **P0** (security / live ops blocker).
- `src/api/routes/admin.py:119-140` kill-switch without 2FA/cooldown → **P0** (governance blocker).
- `src/workers/portfolio_scheduler.py:543,626,629` literal `regime_mult=1.0` → **P0** risk-control falsehood (live trades ignore regime).
- `src/strategies/s1/backtest.py:167-197` circular regime/stress definitions → **P1** quant validity blocker.
- `src/backtest/walkforward/runner.py:102-116` decorative walk-forward → **P1** (no true OOS retraining).

---

## End Matter

**Status:** Verification complete. No code, config, or tests were modified.

**Authorization required before any implementation.**

Recommended next step: decide whether to begin with **Phase 0 (stop-the-bleeding)** and **Phase 1 (test infrastructure)**, or to first perform the deeper verification reads listed below before committing to the remediation roadmap.

### Optional deeper verification reads

1. `src/workers/pead_worker.py` — confirm S7 signal generation and whether it writes to Redis/DB.
2. `src/strategies/s1/backtest.py` full file — map all circular-label lines beyond the ±15-day stress snippet.
3. `src/workers/execution.py` full file — compare legacy path safety with portfolio path.
4. `src/strategies/s1/sensitivity.py` — quantify the grid-search space and near-optimum threshold.
5. `src/backtest/walkforward/runner.py` — determine whether any fitting prevention exists deeper in the class.
6. `src/config.py` — verify whether `ALPACA_PAPER` boolean exists or only URL-based inference.
7. `docker-compose.yml` — full read for resource-limit / non-root / Redis persistence audit.
