# FRONTEND_IMPACT_AND_CUSTOMER_JOURNEY_REVIEW

Data: 2026-06-21 · Modalità: read-only · Scope: AS-IS frontend vs delta backend P0/P1/P2, customer journey, operator surface.

> **Premessa di verità.** Tre fonti verificate per codice: `frontend/src/` (16 pagine, 13 API client), `src/api/routes/` (endpoint reali), `docs/`. Le contraddizioni interne emerse sono riportate esplicite, non nascoste.

---

## 1. Executive Summary

Alembic ha costruito in P0/P1/P2 un **strato di governance, safety e observability backend considerevole** — promotion gate fail-closed, readiness con 8 flag, execution decisions con `reason`, S4 idempotency, validation truth (PIT/walk-forward/LOO ICIR), historical stress gates, degradation ratio, cockpit alerts, divergence checks, edge cases P2-05. **Il backend sa molto più di quanto il frontend comunichi.**

Il frontend attuale è una **console di osservazione di trading** (P&L, posizioni, segnali, ordini, pesi LLM, config) con due soli controlli reali — kill-switch e operating mode — e una sola azione di governance (approve ensemble weights). Mancano quasi completamente le superfici che giustificherebbero operare in paper con fiducia:

- **Nessuna UI readiness/cockpit** — `GET /api/system/readiness` non è nemmeno chiamato. L'operatore non vede se il sistema è degraded/blocked.
- **Nessuna UI strategy governance** — `mode`, `promotion_blocked`, `gate_report_id`, `last_validation`, `degradation_ratio`, `historical_stress` non sono esposti; i 3 endpoint `promote/approve/demote` **esistono nel backend ma non sono cablati** nel frontend.
- **Nessun news-to-trade trace** — la catena news → signal → decision → order → fill → exit → PnL è spezzata in pagine sconnesse, senza join.
- **Order lifecycle superficiale** — status come badge; niente reject reason, partial-fill, stop-loss leg.
- **Attribution assente** — PnL per strategia / signal source / news item non esiste; gli endpoint `analytics/by-symbol` e `by-dimension` sono definiti nel client API ma **mai wired a una pagina** (codice morto).
- **"Perché ho comprato X" non è spiegato** — il `reason` di `/api/decisions` è free-text troncato; niente `why-trade`/`why-skip` strutturato.

Tre contraddizioni interne aggravano la fiducia: (1) README dice P2-05 *Pending*, P2_STATUS/Audit dicono *CLOSED*; (2) `GET /api/strategies` hardcoda S1 `status:"validated"` Sharpe 0.51 mentre `config/strategies.yaml` la ha *DEMOTED a supervised_paper, promotion_blocked*; (3) Docs.tsx è HTML statico con claim hardcoded che possono divergere dalla realtà (es. S2 "OOS Sharpe −0.55").

**Verdetto AS-IS:** il frontend attuale **non è sufficiente per operare controlled paper con chiarezza né per auditare un trade end-to-end**. Buona parte del gap è **frontend-only** (le API readiness, portfolio/status, promote/approve/demote, analytics esistono già); il resto richiede **backend enrichment** (gate_report_id/degradation_ratio/historical_stress esposti, divergence/alerts/fallback-rate endpoint, why-trade/why-skip strutturato, PnL by strategy).

**Stop point:** non propongo live trading, non propongo promotion, non propongo di avviare controlled paper senza le condizioni elencate in §11. Non ho modificato file.

---

## 2. Frontend AS-IS Inventory

Stack: React + react-router-dom + TanStack Query + Zustand + Recharts + TanStack Virtual. Auth JWT in sessionStorage, `apiFetch` aggiunge Bearer e logout su 401/403. Router: `App.tsx`, 15 route protette + `/login`.

| Page / Component | Route | Purpose | Data Source / API | Shows What | Missing Context | User Action |
|---|---|---|---|---|---|---|
| Overview | `/` | Dashboard P&L/posizioni/segnali | `/api/signals`, `/api/positions`, `/api/performance/pnl?period=6M` | KPI P&L, bar monthly P&L, tab posizioni, ultimi 10 segnali | Nessun readiness, governance, cockpit alert, attribution per strategia/news | Read-only |
| Signals | `/signals` | Segnali LLM + Decision Log | `/api/signals`, `/api/decisions?limit=100&symbol=` | Tab signals (ticker/dir/score/conf/model/fallback/time); tab decisions (time/symbol/weight/decision/order_id/**reason free-text**) | why-trade/why-skip non strutturati; niente blocked-reason codificato, strategy, order intent, health-state-at-decision | Filtri testo/dir |
| Trading | `/trading` | Posizioni/ordini/fills Alpaca | `/api/positions`, `/api/orders?limit=200`, `/api/trades?status=all` | 3 tab: positions, orders (status badge), fills espandibili | **Niente lifecycle** submitted→accepted→rejected→partial→filled; niente reject/partial detail, stop-loss leg, idempotency skip, realized vs unrealized | Filtro symbol |
| Trades | `/trades` | Storico filled | `/api/trades?status=&limit=200` | Symbol/side/fill/qty/notional/filled_at + order_id | Niente exit lifecycle, realized P&L per trade, stop-loss leg. **`api/analytics.ts` by-symbol/by-dimension definiti ma pagina non li usa** (pag 93 righe, tab Analytics rimosso) | Filtri status/symbol |
| Performance | `/performance` | P&L storico + Weekly Report | `/api/performance/pnl`, `/api/trades/summary?days=30`, `/api/performance/weekly` | Cumulative/equity, monthly summary, trade activity, cost analysis, capital efficiency, regime, feedback loop, infra cost/breakeven, pesi LLM | Attribution solo **aggregato portfolio**; cost_drag annualizzato calcolato lato FE; niente divergence/fallback rate | Toggle periodo/tab |
| Strategies | `/strategies` | Validazione S1/S3/S4/S7 | `/api/strategies`, `/:id`, `/:id/backtest`, `/:id/gates`, `/:id/sensitivity` | KPI + DataSourceBadge, equity+drawdown, gates table (PASS/FAIL), sensitivity heatmap, params, universe chips | **gate_report_id, historical stress separato, degradation ratio, last validation assenti**; niente promotion gate/lifecycle/promotion status; niente promote/demote. Selezione default hardcoded `'s1'`; claims hardcoded nei HelpButton | Dropdown strategia |
| Backtest | `/backtest` | Run backtest LLM | `/api/backtest/runs`, `/:runId/summary`, `/bucket_analysis`, `/model_ic`, `/symbol_ic`, `/pnl_curve` | KPI IC/ICIR/hit, bucket chart, P&L curve, IC by model/symbol | Niente readiness, stress per run, attribution per news. `backtestApi.signals` definito ma non usato | Toggle buckets/threshold |
| News | `/news` | Articoli per fonte | `/api/news/recent?limit=200&ticker=&source=` | Title/source/ticker/sentiment/time; expand: body, url, raw score | **Nessun news-to-trade trace**; niente fallback rate per fonte | Filtri ticker/source |
| LLM | `/llm` | Feedback modelli + pesi | `/api/llm/feedback`, `/api/weights/current`, `POST /api/weights/approve` | Feedback tab; weights active vs proposed (PENDING APPROVAL) | Approvazione pesi = **unica governance action** (ensemble, non strategy promotion) | **MUTAZIONE** approve weights |
| Config | `/config` | Watchlist + risk params | `GET/POST /api/config` | Watchlist editor; slider Max Drawdown 1–20%; Stop Loss 0.01–0.5; JSON read-only | **Safety surface**: drawdown 20%, stop-loss 50%, nessun guardrail UI visibile, niente double-confirm | **MUTAZIONE** save config |
| Admin | `/admin` | Kill switch + mode | `/api/admin/killswitch` (GET/POST/DELETE), `/api/admin/mode` (GET/POST) | Kill switch card; mode radio (backtest/paper/semi_auto/full_auto/halted) | Niente cockpit alert; mode switch diretto a `full_auto` senza gate/promotion | **MUTAZIONE** killswitch + mode |
| AutoImprove | `/auto-improve` | Phase B feedback + Phase C counterfactual | `/api/feedback/status`, `/api/trades/analytics/counterfactual?days=7` | Phase B card (threshold/regime scale/status); Phase C tabella skip per decision type | Niente strategy intervention timeline strutturata; Phase B solo adjustment corrente | Read-only |
| Docs | `/docs` | Guida statica | nessuna | HTML statico: strategie, pipeline, gate, stop-loss, staleness | **Tutto hardcoded** — può divergere dalla realtà | Read-only |
| DashboardPage | `/dashboard` | Embed Grafana | iframe `:3001` | 3 tab Grafana (overview/risk/decay) | Tutto delegato a Grafana; nessuna integrazione dati FE | Switch tab |
| SystemLog | `/system` | Scheduler, activity, PEAD | `/api/system/scheduler`, `/api/system/activity?limit=80`, `/api/pead/signals` | Scheduler (last_run + stale >3h), activity log (type/time/event/detail), PEAD signals | **Niente readiness, Redis/DB health, beat lag metric, divergence, fallback rate**; stale solo su last_run worker | Read-only |
| Login | `/login` | Auth JWT | `POST /api/auth/login` | Form | — | Login |

**API client (`frontend/src/api/`):** `client, admin, analytics, backtest, config, llm, news, performance, positions, signals, strategies, system, trades`.

**Endpoint definiti nel client MA non wired a nessuna pagina (codice morto):** `analytics.ts` (`by-symbol`, `by-dimension`), `backtest.ts` (`/signals`). Inoltre `trades/postmortem/{trade_id}` e `/portfolio/status` **esistono nel backend ma non hanno client né pagina**.

**Badge condivisi:** `ModeBadge` (stato locale da `/api/admin/status`, polling 15s); `DirectionBadge`; `KPICard`; `DataTable`; `HelpButton`; `ErrorBoundary`. `DataSourceBadge` e `GateBadge` sono **locali a Strategies.tsx**, non condivisi. `ApiKeyModal` è stub vuoto legacy.

**Safety surface mutante (da vincolare):** Config (slider drawdown 20%, stop-loss 50%, save immediato); Admin (switch diretto `full_auto`, kill-switch con reason opzionale); LLM (approve weights irreversibile); Sidebar (toggle economy/full ensemble → 1 solo modello).

---

## 3. Backend P0/P1/P2 Delta vs Frontend Surface

Legenda FE Visible: ✅ sì · ⚠️ parziale · ❌ no. "Operator Can Act?" = può fare qualcosa nell'UI oggi.

| Backend Capability | Backend impl? | API esposta? | FE Visible? | Operator Act? | Gap | Priority |
|---|---|---|---|---|---|---|
| Readiness 8 flag (redis/db/killswitch/stale/beat) | ✅ `cockpit.py:43` | ✅ `GET /api/system/readiness` | ❌ | ❌ | Endpoint pronto, FE non lo chiama; manca summary ready/degraded/blocked + reason | **F0** |
| Readiness summary (ready/degraded/blocked+reason) | ❌ | ❌ | ❌ | ❌ | Da derivare backend o FE; oggi operatore deduce da 8 bool | F0 |
| Execution decisions log | ✅ `pg_store.py:296` | ✅ `/api/decisions`, `/api/system/decisions` | ⚠️ (reason free-text in Signals) | ❌ | Manca why-trade/why-skip strutturato, news_id, health-state-at-decision, order_intent, cap/idempotency/lifecycle/freshness, stop-loss-leg | **F0** |
| Beat scheduler | ✅ | ✅ `/api/system/scheduler` | ✅ SystemLog | ❌ | Stale solo >3h last_run; niente beat lag metric dalla readiness | F1 |
| Activity log unificato | ✅ | ✅ `/api/system/activity` | ✅ SystemLog | ❌ | Fallback count solo in detail free-text; niente cockpit alerts | F1 |
| Portfolio status (mode/approved) | ✅ `portfolio.py:44` | ✅ `/portfolio/status` | ❌ | ❌ | Endpoint pronto, FE non chiama; manca promotion_status/lifecycle_state/promotion_blocked/gate_report_id/last_validation | **F0** |
| Portfolio promotion_blocked/lifecycle/gate_report_id | ⚠️ (in DB/registry, non in API) | ❌ | ❌ | ❌ | Dato esiste in `strategy_lifecycle` ma non ritornato da GET | F0 (BE) |
| Exposure / net-exposure cap violation | ⚠️ (`constraints.py` enforce) | ❌ | ❌ | ❌ | Enforce interno non esposto; niente cap-violation feed | F1 (BE) |
| Cycle history | ✅ | ✅ `/portfolio/cycle-history` | ❌ | ❌ | Non usato in FE | F2 |
| Strategies list governance fields | ⚠️ hardcode S1/S3 | ✅ `/api/strategies` | ⚠️ (no governance) | ❌ | NO mode/approved/promotion_blocked/gate_report_id/last_validation/degradation_ratio/historical_stress | **F0** (BE+FE) |
| Strategy gates | ⚠️ hardcode | ✅ `/api/strategies/:id/gates` | ✅ Strategies | ❌ | NO gate_report_id/last_validation/degradation_ratio/historical_stress_status | F0 (BE) |
| Promote / Approve / Demote | ✅ `promotion.py` fail-closed | ✅ `POST /api/strategies/:id/{promote\|approve\|demote}` | ❌ | ❌ | **Endpoint pronti, FE non li cabla** | **F0** (FE-only) |
| Orders lifecycle (Alpaca) | ✅ | ✅ `/api/orders` | ⚠️ (status badge) | ❌ | Niente reject reason/partial-fill qty/stop-loss leg/audit trail | **F0** |
| Positions | ✅ | ✅ `/api/positions` | ✅ Trading | ❌ | Niente governance fields | F1 |
| Trades (gross/net/slippage per trade) | ✅ | ✅ `/api/trades` | ⚠️ Trades | ❌ | Realized P&L per trade non evidenziato; niente holding-vs-thesis | F1 |
| PnL by symbol | ✅ | ✅ `/api/trades/analytics/by-symbol` | ❌ | ❌ | **Client definito, nessuna pagina lo usa** | F1 (FE-only) |
| PnL by dimension (regime/hour/score/holdtime) | ✅ | ✅ `/api/trades/analytics/by-dimension` | ❌ | ❌ | **Client definito, nessuna pagina lo usa** | F1 (FE-only) |
| PnL by strategy / signal source / news source | ❌ | ❌ | ❌ | ❌ | Non implementato | F2 (BE) |
| Counterfactual | ✅ | ✅ `/api/trades/analytics/counterfactual` | ✅ AutoImprove | ❌ | OK ma aggregato per decision type | F2 |
| Trade postmortem | ✅ | ✅ `/api/trades/postmortem/{id}` | ❌ | ❌ | Endpoint pronto, FE non lo usa | F1 (FE-only) |
| Feedback loop status | ✅ | ✅ `/api/feedback/status` | ✅ AutoImprove | ❌ | Solo adjustment corrente, non storico | F2 |
| Kill-switch (status/activate/deactivate/recovery-token) | ✅ `admin.py:112-209` | ✅ | ✅ Admin | ✅ | OK; manca OTP/recovery-token UI, cooldown visibile | F0 (FE polish) |
| Operating mode | ✅ | ✅ `/api/admin/mode` | ✅ Admin | ✅ | Switch `full_auto` senza gate — safety risk | **F0** |
| Alerts (active/historical, severity, impacted, runbook) | ❌ | ❌ | ❌ | ❌ | Non esiste endpoint | F1 (BE) |
| Divergence paper/backtest/live | ⚠️ (check interno + Telegram) | ❌ | ❌ | ❌ | Solo alert Telegram; niente feed per FE | F1 (BE) |
| Fallback rate (dedicata) | ⚠️ (count in activity detail) | ❌ | ❌ | ❌ | Solo free-text "Fallbacks: N" | F1 (BE) |
| Redis writable/MISCONF | ✅ flag | ✅ readiness | ❌ | ❌ | Pronto, non visualizzato | F0 (FE-only) |
| Stale signals / beat lag | ✅ flag | ✅ readiness | ❌ | ❌ | Pronto, non visualizzato | F0 (FE-only) |

**Conclusione delta:** la maggior parte del gap **readiness/promote/portfolio-status/analytics/postmortem** è **frontend-only** (le API ci sono). Richiede invece **backend enrichment**: governance fields in `/api/strategies*` (gate_report_id/degradation_ratio/last_validation/historical_stress), endpoint `alerts`, `divergence`, `fallback-rate`, why-trade/why-skip strutturato + news_id + health-state-at-decision in `decisions`, order reject/partial/stop-loss-leg, PnL by strategy/signal/news.

---

## 4. Current Customer / Operator Journey Analysis

### Journey A — News → Signal → Decision → Order — **PARTIAL (CONFUSING)**
News page: articolo + sentiment + raw score. **Ma niente join a signal.** Signals page: signal (ticker/dir/score/conf/model/fallback) + decision log (reason free-text troncato). Trading: ordine. **Il thread news→signal→decision→order è spezzato in 3 pagine senza chiave di join esposta** (`signal_id` esiste ma non è navigabile; `news_id` non esiste). Freshness del segnale non mostrata. Blocked-reason (idempotency/stale/cap/approval/kill-switch) non codificato.

### Journey B — Order → Fill → Position → Stop-loss — **PARTIAL**
Trading mostra ordini con `status` (badge filled/canceled). **Niente transizione** accepted→rejected→partial→filled, niente reject reason, niente partial-fill qty/avg price, **niente stop-loss leg**, niente broker pending-duplicate skip. Fill espandibile con order_id ma senza audit trail.

### Journey C — Position → Exit/Sell → PnL — **PARTIAL**
Trades ha `exit_reason`, `gross_pnl`, `slippage_est`, `net_pnl` per trade. **Realized vs unrealized non separati chiaramente; niente holding period vs thesis attesa; niente costi aggregati per trade; niente attribution a news/momentum/risk.**

### Journey D — Strategy Attribution — **NOT_VISIBLE**
Niente PnL per strategia, niente combiner decision, niente conflitto BUY/SELL tra strategie, niente "quale strategia ha agito quando/perché/con che confidence/peso". AutoImprove mostra solo adjustment corrente Phase B.

### Journey E — System Health / Readiness — **NOT_VISIBLE (CONFUSING)**
L'operatore vede kill-switch + mode (Admin, badge sidebar). **Non vede readiness, non vede cockpit alerts, non vede se il sistema è degraded o sta saltando trade per safety.** "Posso fidarsi dei segnali?" non è rispondibile dall'UI.

---

## 5. Clarity Scorecard

| # | Question | Risponde oggi? | Dove | Missing | Severity |
|---|---|---|---|---|---|
| 1 | Perché Alembic ha comprato questo titolo? | ❌ | Signals (reason free-text) | why-trade strutturato, news_id, strategy, health-at-decision | **Critical** |
| 2 | Quale news/evento ha generato il segnale? | ❌ | — | join news→signal non esposta | **Critical** |
| 3 | Quale strategia ha agito? | ❌ | — | niente strategy nelle decisions | High |
| 4 | Quale modello/score/confidence ha contribuito? | ⚠️ | Signals, LLM | per-decision, non aggregato al trade | Medium |
| 5 | Perché un trade è stato saltato? | ⚠️ | Signals (SKIP_*+reason) | reason free-text, niente blocked-reason codificato | High |
| 6 | Il sistema era healthy quando ha deciso? | ❌ | — | health-state-at-decision non registrato/non mostrato | **Critical** |
| 7 | Rispettava cap/lifecycle/approval/freshness/idempotency? | ❌ | — | check columns non esposte | High |
| 8 | Stop-loss creato? | ❌ | — | stop-loss leg non tracciato | High |
| 9 | Ordine accettato/rifiutato/parziale? | ⚠️ | Trading (status badge) | reject reason, partial-fill, lifecycle | High |
| 10 | Quanto ha reso al netto dei costi? | ⚠️ | Trades (gross/net/slippage per trade) | per-trade realized chiaro, attribution no | Medium |
| 11 | Quale strategia è profittevole? | ❌ | — | PnL by strategy non implementato | **Critical** |
| 12 | Movimenti news vs momentum vs risk? | ❌ | — | attribution per fonte | High |
| 13 | Quali alert erano attivi in quel momento? | ❌ | — | niente alerts, niente timestamp cross-ref | High |
| 14 | Audit trail end-to-end? | ❌ | — | catena spezzata | **Critical** |
| 15 | Cosa fare come operatore? | ❌ | — | niente operator inbox/runbook/action | High |

**Score:** 0 CLEAR, 5 PARTIAL, 10 NOT_VISIBLE. Le 5 domande Critical (1, 2, 6, 11, 14) sono i blocchi di auditabilità.

---

## 6. Proposed Frontend Information Architecture

### 6.1 System Readiness Dashboard (nuova, `/readiness` o in Overview)
Banner ready/degraded/blocked + 8 flag cockpit (redis_healthy, redis_writeable/MISCONF, db_healthy, killswitch_active, stale_signals, worker_beat_lag, last_signal_age_minutes, last_cycle_age_minutes) + last worker beat + kill-switch status + **operator next action** (link runbook). Sorgente: `GET /api/system/readiness` (FE-only). Colore semantico: HTTP 200 ma flag unhealthy → stato degraded esplicito.

### 6.2 Strategy Governance Dashboard (estende `/strategies`)
Tabella: strategy · mode · approved · promotion_blocked · gate_report_id · last_validation · degradation_ratio · historical_stress_status · eligible paper? · eligible promotion? · reason if blocked. Azioni: promote / approve / demote (endpoint pronti). Sorgente: `/api/strategies` arricchito + `/portfolio/status` (BE enrichment per governance fields; FE-only per le azioni).

### 6.3 Execution Decisions / Why Trade / Why Skip (nuova, o tab in Signals)
Tabella: timestamp · strategy · symbol · action · decision · **reason strutturato (why-trade/why-skip)** · signal_id · news_id · order_id · health_state_at_decision · cap/idempotency/lifecycle/freshness checks. Sorgente: `/api/decisions` arricchito (BE enrichment).

### 6.4 News-to-Trade Trace (nuova, `/trace/:news_id` o drill-down)
Timeline: news item · ingestion time · freshness · ticker match · sentiment/LLM score · strategy signal · portfolio decision · broker order · fill · exit · PnL. Chiave di join `signal_id`/`news_id`. Sorgente: join FE di `/api/news`, `/api/signals`, `/api/decisions`, `/api/trades` (alcuni campi richiedono BE).

### 6.5 Order Lifecycle View (estende `/trading`)
Per ordine: submitted → accepted → rejected → partial fill → filled → stop-loss → cancelled → exit/sell + broker response + audit events. Sorgente: `/api/orders` arricchito (reject reason/partial/stop-loss leg BE).

### 6.6 Profitability Attribution (nuova, `/attribution`)
P&L gross/net · cost/slippage · by strategy · by symbol · by signal source · by news source · by holding period · by regime · by decision reason. Sorgente: `analytics/by-symbol`, `by-dimension` (FE-only, già definiti) + **PnL by strategy/signal/news (BE nuovo)**.

### 6.7 Alerts / Operator Inbox (nuova, `/alerts`)
Active/historical · severity · impacted strategy/symbol · runbook link · action taken · resolved. Sorgente: **endpoint alerts nuovo (BE)**.

### 6.8 Paper Program Dashboard (nuova, `/paper-program`)
Daily paper PnL · divergence paper/backtest/live · skipped trades · rejects/partials · alerts · kill criteria · giorni completati /90 · evidence pack export. Sorgente: divergence endpoint (BE nuovo) + readiness + decisions.

---

## 7. Proposed Customer Journeys

| # | Journey | Entry UI | Schermate/campi | API necessarie | Gap attuali | Implementazione |
|---|---|---|---|---|---|---|
| 1 | "Perché Alembic ha comprato X" | Trade/position → "Perché" | decision row (strategy, reason, score, news_id, health) | `/api/decisions` + news join | why-trade strutturato, news_id, health-at-decision | BE enrichment + FE drill-down |
| 2 | "Perché non ha comprato X" | Signals/decisions → SKIP filter | SKIP_EMA/SKIP_CAP/... + reason + checks | `/api/decisions` | blocked-reason codificato, checks columns | BE enrichment + FE tab |
| 3 | "Una news ha prodotto profitto?" | News → trace → PnL | news→signal→trade→net PnL | news, signals, trades join | join non esposto | FE join + (news_id BE) |
| 4 | "Quale strategia genera valore" | Attribution dashboard | PnL by strategy | **PnL by strategy (BE nuovo)** | non implementato | BE + FE |
| 5 | "Sistema operativo o degraded?" | Readiness banner | 8 flag + next action | `/api/system/readiness` (pronto) | FE non chiama | **FE-only** |
| 6 | "Rivedere posizione nascita→chiusura" | Position → lifecycle | order→fill→exit→PnL + postmortem | `/api/orders`, `/api/trades`, `/api/trades/postmortem` (pronto) | lifecycle, postmortem non wired | FE + (reject/partial BE) |
| 7 | "Posso iniziare controlled paper?" | Paper Program dashboard | readiness all-green + decisions solo paper + kill rehearsal + PO sign-off + giorni/90 | readiness, decisions, divergence (BE) | divergence endpoint mancante | BE + FE |
| 8 | "Audit di un trade" | Trade → audit trail | news→signal→decision→order→fill→exit→PnL + health | tutte le precedenti | catena spezzata | BE enrichment + FE |

---

## 8. API / Data Requirements

| Frontend Need | Existing API | Missing Field | New API? | BE change? | Priority |
|---|---|---|---|---|---|
| Readiness banner | `GET /api/system/readiness` | summary ready/degraded/blocked + reason | No (derivable FE) o mini-BE | Opzionale | F0 |
| Strategy governance fields | `/api/strategies`, `/portfolio/status` | mode/approved/promotion_blocked/gate_report_id/last_validation/degradation_ratio/historical_stress | No (arricchire GET) | **Sì** | F0 |
| Promote/approve/demote | `POST /api/strategies/:id/{promote\|approve\|demote}` | — | No | No | F0 (FE-only) |
| Why-trade/why-skip strutturato | `/api/decisions` | reason strutturato, news_id, strategy, health-at-decision, order_intent, checks | No (arricchire) | **Sì** | F0 |
| Cockpit flags UI | `/api/system/readiness` | — | No | No | F0 (FE-only) |
| News-to-trade join | news, signals, decisions, trades | news_id su decision/signal | No (parziale) | **Sì** (news_id) | F0/F1 |
| Order reject/partial/stop-loss | `/api/orders` | reject_reason, partial_fill, stop-loss_leg | No (arricchire) | **Sì** | F0/F1 |
| PnL by symbol/dimension | `/api/trades/analytics/by-symbol,by-dimension` | — | No | No | F1 (FE-only) |
| PnL by strategy/signal/news | — | tutto | **Sì** | **Sì** | F2 |
| Alerts inbox | — | tutto | **Sì** | **Sì** | F1 |
| Divergence feed | — (interno+Telegram) | endpoint | **Sì** | **Sì** | F1 |
| Fallback rate | (in activity detail) | endpoint/serie | **Sì** | **Sì** | F1 |
| Trade postmortem | `/api/trades/postmortem/{id}` | — | No | No | F1 (FE-only) |
| Exposure cap violation | (enforce interno) | endpoint | **Sì** | **Sì** | F1 |

**Split:** FE-only = readiness banner, cockpit flags UI, promote/approve/demote, analytics by-symbol/by-dimension, postmortem, kill-switch polish. BE enrichment = governance fields in strategies API, why-trade/why-skip strutturato + news_id, order reject/partial/stop-loss, alerts, divergence, fallback-rate, PnL by strategy, exposure cap.

---

## 9. Prioritized Frontend Backlog

### F0 — Required before controlled paper (operare in paper con chiarezza)

| ID | Title | User Value | BE Dep | FE Scope | Acceptance Criteria | Priority |
|---|---|---|---|---|---|---|
| F0-01 | Readiness Dashboard + banner | vede stato sistema | No | New page + global banner | 8 flag + ready/degraded/blocked + next action; HTTP 200 ma unhealthy → degraded | F0 |
| F0-02 | Strategy Governance table | vede mode/promotion_blocked/gate_report_id | **Sì** (governance fields) | Extend Strategies | mode, approved, promotion_blocked, gate_report_id, last_validation, reason if blocked | F0 |
| F0-03 | Promote/Approve/Demote UI | azione governance | No (endpoint pronti) | Extend Strategies | 3 azioni cablate, fail-closed su PromotionBlockedError, audit | F0 |
| F0-04 | Why-Trade/Why-Skip structured table | capisce decisioni | **Sì** (enrich decisions) | New tab | strategy, reason strutturato, news_id, health-at-decision, checks | F0 |
| F0-05 | Order lifecycle + reject/partial + stop-loss | audit ordini | **Sì** | Extend Trading | lifecycle states, reject reason, partial qty, stop-loss leg | F0 |
| F0-06 | Reconcile strategy API truth | niente false "validated" | **Sì** | BE+FE | `/api/strategies` riflette mode/promotion_blocked reale; rimuovere hardcode S1 Sharpe 0.51 | F0 |
| F0-07 | Guardrail su Config/Admin safety surface | niente indebolimento accidentale | No (BE opz) | FE | conferma su stop-loss>10%/drawdown>10%; blocca `full_auto` se promotion gate fail-closed | F0 |
| F0-08 | De-hardcode Docs.tsx | niente claims divergenti | No | FE | claims da API, non HTML statico | F0 |

### F1 — Strongly recommended before 90-day paper (auditabilità/efficienza)

| ID | Title | BE Dep | FE Scope | AC | Priority |
|---|---|---|---|---|---|
| F1-01 | News-to-Trade Trace | Sì (news_id) | New page | timeline news→signal→decision→order→fill→exit→PnL | F1 |
| F1-02 | Profitability Attribution (by symbol/dimension wired) | No | New page | usa analytics esistenti; by-strategy quando BE pronto | F1 |
| F1-03 | Alerts / Operator Inbox | **Sì** | New page | active/historical, severity, impacted, runbook link | F1 |
| F1-04 | Divergence feed UI | **Sì** | Extend readiness/paper | paper/backtest/live divergence visible | F1 |
| F1-05 | Fallback rate + beat lag metrics | **Sì** (fallback) / No (beat) | Extend SystemLog | rate storico, non solo free-text | F1 |
| F1-06 | Trade postmortem UI | No | Extend Trades | drill-down postmortem_diagnosis | F1 |
| F1-07 | Exposure cap-violation indicator | **Sì** | Extend Trading | cap violation visible | F1 |
| F1-08 | Kill-switch OTP/recovery-token + cooldown UI | No | Extend Admin | recovery-token flow, cooldown visibile | F1 |

### F2 — Before live reconsideration

| ID | Title | BE Dep | FE Scope | Priority |
|---|---|---|---|---|
| F2-01 | PnL by strategy/signal source/news source | **Sì** | Attribution | F2 |
| F2-02 | Paper Program Dashboard (divergence, giorni/90, evidence pack, kill criteria) | **Sì** | New page | F2 |
| F2-03 | Cycle history + portfolio governance drill-down | No | New/extend | F2 |
| F2-04 | Audit trail end-to-end export (evidence pack) | **Sì** | New | F2 |
| F2-05 | Strategy intervention timeline (combiner, conflitti BUY/SELL, confidence) | **Sì** | New | F2 |

### F3 — Nice to have / later
Dashboard Grafana unificata, feedback loop storico, counterfactual per-trade, sensitivity multi-strategy comparison, multi-account view.

---

## 10. UX Copy / Labeling Guidelines

- **Mai "production" / "live ready"** per R&D. Usa `R&D`.
- Distingui: `paper` · `supervised_paper` · `R&D` · `promotion_blocked` (ognuno con tooltip: cosa significa, cosa è permesso).
- **"HTTP 200 but degraded"**: spiegare — "L'API risponde ma alcuni flag sono unhealthy: il sistema opera in modalità degradata. Dettagli nei flag." Non verde pieno.
- **"Blocked by safety"**: "Decisione non eseguita per vincolo di safety: [kill-switch / cap / lifecycle / freshness / idempotency]. Nessun ordine inviato."
- **"Skipped by idempotency"**: "Segnale già processato per questo ticker in posizione — ignorato (no pyramiding)."
- **"Rejected by broker"**: "Ordine rifiutato dal broker: [reason]. Nessun fill."
- **Gross vs net PnL**: etichettare sempre "Gross (pre-costi)" e "Net (post-spread/impact/fee)"; mostrare cost drag esplicito.
- **"Validated"** bandito se `promotion_blocked=true` o `mode!=approved`; usa lo stato reale del lifecycle.
- **DataSourceBadge**: chiarire "LIVE = metrica da esecuzione paper reale; BACKTEST = metrica storica" — non implica capitale reale.

---

## 11. Risks If Not Implemented

1. **Falsa sicurezza in paper**: operatore vede "validated" Sharpe 0.51 e mode senza sapere che S1 è `supervised_paper`/`promotion_blocked` → decisioni su dati non autorizzati.
2. **Audit impossibile**: senza why-trade strutturato + news-to-trade trace, un trade anomalo non è ricostruibile → impossibile learning/debug.
3. **Degraded invisibile**: readiness non esposta → il sistema può operare con Redis MISCONF / stale signals / beat lag senza che l'operatore lo sappia.
4. **Safety surface abusiva**: Config slider 20%/50% + Admin `full_auto` diretto → indebolimento accidentale dei risk controls.
5. **Attribution cieca**: senza PnL by strategy non si sa quale sleeve genera/perde valore → nessuna base per ripromuovere o ritirare.
6. **Contraddizioni documentali non riconciliate** (README P2-05 Pending vs P2_STATUS CLOSED; `/api/strategies` hardcode vs config) → PO sign-off bloccato, controlled paper non parte.
7. **Controlled paper prematuro**: senza divergence feed + paper program dashboard + kill criteria visibili, i 90 giorni non sono verificabili.

---

## 12. Recommended Implementation Sequence

1. **F0-01 + F0-08** (FE-only, zero BE): readiness dashboard + de-hardcode Docs → fiducia nello stato corrente.
2. **F0-06** (BE): riconcilia `/api/strategies` con `strategy_lifecycle` reale (rimuovi hardcode S1).
3. **F0-02 + F0-03** (BE governance fields + FE actions): strategy governance table + promote/approve/demote.
4. **F0-04 + F0-05** (BE enrichment + FE): why-trade/why-skip strutturato + order lifecycle/reject/partial/stop-loss.
5. **F0-07**: guardrail safety surface.
6. **F1-01..F1-08** in parallelo dove FE-only (analytics, postmortem, kill polish) prima del BE-dependent.
7. **F2** solo dopo riconciliazione doc + PO sign-off + dry-run paper all-green.

Dipendenza bloccante: **controlled paper non parte finché** readiness all-green è visibile (F0-01), strategy API truth riconciliato (F0-06), decisions solo paper verificabili (F0-04), kill-switch rehearsal (F1-08) e PO sign-off.

---

## 13. Stop Point

Non ho modificato file (al di fuori di questo documento di report esplicitamente richiesto). Questa è una review read-only del frontend, della customer journey e dell'operator surface. Nessuna modifica frontend/backend è stata implementata. Nessuna strategia è stata promossa, nessun controlled paper avviato, nessun live trading proposto.

---

## Appendice A — Contraddizioni interne emerse (da riconciliare prima del PO sign-off)

- **P2-05 status (CRITICA):** `README.md` (linea 27 + Pre-Live Blockers) dice *Pending / NOT YET RESOLVED*; `docs/ARCHITECTURE.md` §8 dice *NOT_IMPLEMENTED — blocks Kimi P2 Acceptance Audit*; `docs/P2_STATUS_2026-06-21.md` dice *COMPLETE/ACCEPTED*; `docs/RESIDUAL_RISK_REGISTER.md` dice R-01/02/03 *Closed*; `docs/P2_ACCEPTANCE_AUDIT_2026-06-21.md` dice P2-05 *ACCEPTED* (18 test dedicati passano).
- **Kimi P2 Audit status:** README linea 28 "Not yet authorized (blocked on P2-05)"; P2_STATUS "Authorized — requires PO sign-off"; P2_ACCEPTANCE_AUDIT verdetto `P2_ACCEPTED_WITH_RUNTIME_MONITORING` (audit completato). Contraddizione tripla.
- **Badge test count README:** "2353 passing" vs 2386 effettivi (P2_STATUS/Audit).
- **S2 strategy mode:** `P2_STATUS_2026-06-21.md` S2 = `paper`; `config/strategies.yaml` + migration 025 S2 = `disabled`/`research` 0%; `ARCHITECTURE.md` §2.5 "Disabled (research), OOS Sharpe −0.55, all gates failed".
- **S1 strategy status API:** `src/api/routes/strategies.py` hardcode `status: "validated"`, OOS Sharpe 0.5128, annual return 7%, maxDD 15%; `config/strategies.yaml` `mode: supervised_paper`, `promotion_blocked: true` (DEMOTED 2026-06-19); `reports/s1_backtest/summary.json` snapshot 2026-05-30 (stale). L'API pubblica non riflette la verità di autorizzazione.
- **`POST /api/admin/killswitch` body:** API.md sezione admin curl senza body; FRONTEND_OPERATOR_GUIDE §1.5 `{"active": true}`.
- **Endpoint killswitch/recover con OTP:** operations.md runbook lo invoca; API.md non lo documenta. Contratto API mancante per azione operatore critica.
- **`GET /api/strategies`:** codice esiste ed è pubblico; API.md non lo elenca; FRONTEND_OPERATOR_GUIDE dice `Strategies.tsx` usa solo `/api/config`.
- **P2-05 indicato come bloccante stale:** FRONTEND_OPERATOR_GUIDE §4 e operations.md "P2-05 must be resolved first" — stale (P2-05 chiuso); blocker reale = riconciliazione doc + dry-run + PO sign-off.
- **Doc runbook referenziato inesistente:** API.md rimanda a `docs/RUNBOOK_OPERATOR_COCKPIT.md`; il file non esiste — solo sezione in operations.md.
- **docs/API.md stale:** changelog fermo v5.0.0; 7+ endpoint documentati non esistono (`/api/signals/history`, `/api/performance/positions`, `/api/portfolio/cycles`, `/api/portfolio/risk`, `/api/portfolio/decay`, `/api/backtest/runs/{id}/report`, `/api/pead/events`); path portfolio sbagliato (`/api/portfolio/*` vs reale `/portfolio/*`); `GET /api/health` docs mentono (503+redis/pg vs reale `{"status":"ok","mode":"backtest"}`); endpoint implementati non documentati (`/portfolio/*`, `/api/strategies/*` con promote/approve/demote, `/api/system/scheduler|activity`, killswitch recovery-token, `/api/auth/*`, `/api/performance/weekly`, backtest `bucket_analysis/model_ic/symbol_ic/pnl_curve`, trades `analytics/counterfactual|by-symbol|by-dimension|postmortem`).

## Appendice B — Endpoint backend NOT chiamati dal frontend (FE-only quick win)

- `GET /api/system/readiness` — pronto, non chiamato (nessun client in `src/api/`).
- `GET /portfolio/status` (mode/approved) — pronto, non chiamato.
- `POST /api/strategies/:id/promote|approve|demote` — pronti, non cablati.
- `GET /api/trades/analytics/by-symbol|by-dimension` — client `analytics.ts` definito, nessuna pagina lo usa (codice morto).
- `GET /api/trades/postmortem/{id}` — pronto, non cablato.

## Appendice C — Capability che richiedono backend enrichment (non FE-only)

- Governance fields in `/api/strategies*`: `mode`, `approved`, `promotion_blocked`, `gate_report_id`, `last_validation`, `degradation_ratio`, `historical_stress_status` (esistono in `strategy_lifecycle` table + `StrategyRegistry`, non ritornati da GET).
- `decisions` enrichment: `why_trade`/`why_skip` strutturato, `news_id`, `strategy`, `health_state_at_decision_time`, `order_intent`, cap/idempotency/lifecycle/freshness check columns, stop-loss-leg status.
- Endpoint `alerts` (active/historical, severity, impacted, runbook) — non esiste.
- Endpoint `divergence` (paper/backtest/live) — solo check interno + Telegram.
- Endpoint `fallback-rate` (serie storica) — solo count free-text in activity.
- Endpoint `exposure` / cap-violation — enforce interno non esposto.
- `PnL by strategy / signal source / news source` — non implementato.
- Order reject reason / partial-fill detail / stop-loss leg — non esposti.