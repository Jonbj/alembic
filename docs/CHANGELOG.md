# CHANGELOG — Alembic Trading System

Registro delle modifiche rilevanti al sistema (decisioni architetturali, nuove strategie, configurazioni).

---

## 2026-08-07

### #161 — il sistema distingue una posizione protetta da una non proteggibile
Alpaca accetta uno stop solo su almeno 1 azione intera: le 13 posizioni sotto quella soglia
(15% del libro, e **tutto** il P&L negativo: −$452 contro +$660) non erano proteggibili per
costruzione, e nulla nel sistema le distingueva dalle 35 protette. `src/portfolio/unprotected_positions.py`
classifica ogni posizione dopo la sincronizzazione degli stop frazionari (proteggibile /
protetta / perché no); oltre `risk.unprotected_position_alert_pct` (0.15) parte un WARNING
Telegram, una volta al giorno per simbolo (`SET NX` su `alert:unprotected_position:<sym>`),
più una riga di log per ciclo.

La soglia non è nuova: è il −15% già scritto nel commento `Revisit:` di `config/trading.yaml`,
che si era verificato su quattro posizioni (NOK −24.6%, MRVL −22.0%, AMAT −21.7%, WDC −15.3%)
senza che niente lo sorvegliasse. **Strumentazione, non taratura**: nessun ordine, nessuna size,
nessun gate. Decisione operatore del 2026-08-06 (opzione 3 di #161); la size minima di ingresso
≥ 1 azione è taratura e resta al 2026-09-28 (#171).

## 2026-07-27

### F8 regime_scale — gate per-strategia, evidenza dai dati registrati, leva OFF (#32, #134)
PR #135 (`9171099`) e #136 (`77d2af9`). **Nessun cambiamento di comportamento in produzione**:
`apply_regime_scale` resta `false`. Cambiano il meccanismo, la diagnostica e le conclusioni.

- **`scripts/f8_regime_scale_shadow_evidence.py` legge la tabella persistita.** Migration 040 +
  scheduler registravano `f8_regime_scale_shadow` dal 07-21, ma lo script continuava a
  ricostruire tutto per replay ignorando 138 righe reali. Traiettoria ora ibrida con
  provenienza per riga (`recorded` / `replay`); le righe di replay dal primo giorno registrato
  in poi sono scartate. **Il replay era sbagliato**: dava S1 al floor dal 07-15 (in realtà dal
  07-23) e S4 a 1.0 il 21-22/07 (in realtà 0.640 / 0.512).
- **Gate di flip scorato per strategia**, due volte (traiettoria completa vs solo-registrato),
  perché il gate in `trading.yaml` dice *observed* e un PASS che regge solo sul replay non lo è.
- **`apply_regime_scale` accetta ora `false` | `true` | lista di strategy id.** Era un bool
  globale, che imponeva "de-riska tutte le sleeve o nessuna" mentre il gate è per strategia.
  `PortfolioOrchestrator._scale_gate` normalizza; fail-safe: `None`, lista vuota o valore YAML
  non riconosciuto ⇒ shadow. `feedback_shadow[...]["applied"]` è ora per-strategia (finisce
  nella tabella: un valore globale la registrava male).
- **La leva resta OFF.** `[S4]` era il valore che il gate implicava (S4 PASS, S1 FAIL), ma #134
  ha mostrato che il gate è scorato su contatori che **contano due volte**.

### #134 — i contatori del ratchet misurano un artefatto cross-sezionale
`scripts/ratchet_reachability.py` (22 test). Analisi read-only, nessun codice di produzione toccato.

- **Il recovery è di fatto irraggiungibile.** Un down-step resetta lo stesso `last_adjustment`
  che il ramo decay legge: con un gap mediano fra down-step di 20.0h (S1) / 19.5h (S4) contro
  una finestra di 24h, **il decay è affamato su entrambe le sleeve** (21 e 17 clock resettati).
  L'unica uscita funzionante è la win streak: S4 la usa 15 volte, S1 mai in 453 tick.
- **La premessa della regola non regge.** F8 è un equity curve filter, e questa classe paga solo
  se i rendimenti dei trade sono positivamente autocorrelati. Per trade sembra di sì (S1 ac
  +0.318, S4 +0.459), ma **l'80% (S1) e l'89% (S4) delle coppie consecutive sono uscite
  simultanee dello stesso giorno**: una sleeve tiene molti nomi, quindi una giornata storta è
  letta come una streak di N perdite, una volta per posizione aperta. Aggregando a una
  osservazione per giorno di uscita, la dipendenza sparisce (S1 +0.065, S4 +0.017).
- **Conseguenze**: trigger sul 32-40% dei tick; le "10 perdite consecutive" di S1 sono ~2-3
  giornate; win streak irraggiungibile per costruzione per chi tiene più di un nome.
- **Raccomandazione**: aggregare per giorno prima di alimentare i contatori, poi ri-testare la
  premessa su quell'unità; se resta ~0, ritirare F8 a favore dei controlli di rischio di
  portafoglio già presenti (che gestiscono lo stesso rischio cross-sezionale senza dedurlo dal P&L).
- **Limite dichiarato**: n=10 (S1) e n=26 (S4) osservazioni giornaliere — il "nessuna dipendenza"
  per giorno è sotto-potenziato. Il confondente invece è strutturale, non una stima.
- **Su S1**: perde su *ogni* exit reason (9.5% win rate su 63 trade chiusi, −$869). Decisione di
  allocazione, non di taratura. Tracciata in #134.

### Documentazione riallineata
`CONTEXT.md` (voce "Regime scale" diceva "scritto ma **non consumato**" — falso dal 07-12; aggiunta
voce "Teaching trade"), `docs/ARCHITECTURE.md` (§2.9 + diagramma Phase B: TTL 48→96h, chiavi
per-strategia, nuova sotto-sezione F8 apply gate + limite #134), `docs/operations.md`, `README.md`,
`frontend/src/pages/AutoImprove.tsx` (nota "audit/legacy" rimossa, TTL 48→96h, recovery 5→3 wins,
trigger EWMA R) e `frontend/src/pages/Docs.tsx`.

---

## 2026-07-15

### S7 (PEAD) RIMOSSA dal repository — edge ALPHA-A3 confutato a decision-grade
- S7 ritirata: strategy dir `src/strategies/s7/`, `src/models/pead.py`,
  `src/workers/pead_worker.py` + `earnings_pead_worker.py`,
  `src/connectors/earnings_calendar.py`, `src/api/routes/pead_routes.py`,
  beat task `pead-ingestion` + `earnings-pead` (celery_app), config S7
  (`config/strategies.yaml`, `config/trading.yaml` stop sizing, `src/config.py`
  `PEAD_*`), API/display entries (`strategies.py` S7 dict, `system_routes.py`),
  `redis_store.py` pead methods, e test S7-specifici — tutto eliminato.
- Motivo: l'edge dichiarato di S7 (transcript tone → alpha, ALPHA-A3) confutato su
  dati reali. Tre valutazioni, tutte negative: ALPHA-A5 large-cap FAIL (drift = beta
  SPY, n=76, 2026-07-03); POC-1 small/mid INCONCLUSIVE_DATA (n=15, 2026-07-04);
  **POC-2 transcript-tone FAIL a decision-grade** (n=73, Spearman IC(tone,excess_20d)
  +0.012 vs soglia +0.10, tercile spread −0.93% invertito, split-half opposti, IC
  dentro BEAT −0.016; agreement kimi↔glm ρ=+0.858 → FAIL robusto cross-modello). La
  condizionale pre-registrata PO-5 *"Se POC-2 FAIL → REMOVE"* è attivata.
- Preservato: POC scripts + report/CSV in `reports/s7_*` (evidenza, gitignored),
  `tests/analysis/test_s7_poc_helpers.py`, DB audit history (immutable). Codice
  recuperabile da git. Guard anti re-introduzione:
  `tests/test_p0_13_strategy_containment.py::TestS7NotInOperationalRegistry`.
- Documentazione: `docs/S7_LIFECYCLE_HISTORY_2026-07-15.md` (storia completa),
  `docs/strategies.md` §S7, `docs/strategies/s7-pead.md`, `docs/ARCHITECTURE.md`,
  `docs/operations.md`, `docs/ROADMAP_DATA_ALPHA_2026-07-02.md` aggiornati.
- Costi consuntivi S7 lifecycle: FMP Starter $29 (mese 07, disdetto #23);
  POC-2 $0 (Alpha Vantage free tier); LLM: 73 kimi + 20 GLM POC-2 + 8-K idle.
- Full suite: 2796 passed, 7 skipped, 0 fail. Issue #38 chiusa con la PR di rimozione.

### Pool-leak B7/B32 — fix deployato e verificato live (pre-live blocker)
- Root cause: `_pg_stop = PostgreSQLStore()` nel check stop-loss del `portfolio_scheduler` non era mai chiuso → 1 connessione "idle in transaction" leakata per ciclo 15-min → pool maxconn=20 esaurito. Venerdì 07-14 teneva AccessShareLock su `trades` e bloccava migration 037.
- Fix A+B+C (commit `06671f7`, merge FF su main): `finally: .close()` su `_pg_stop`/`_pg`/`_pg_trades` nel scheduler; `_release_connection` ora rollback prima di `putconn`/`close` (solo su path pool/owned); `load_frozen_stop`/`fetch_open_trade_meta` chiudono la transazione read-only. 7 guard test nuovi. Full suite 2831 pass.
- Deploy: rebuild api/worker/worker-inference/beat + restart. Verificato live: `idle in transaction` = 0 (era 20), fix baked nei container (marker B7/B32 presenti).

### Stop protettivo 2% DISABILITATO su paper (decisione operatore aggressive-alpha)
- `config/trading.yaml`: `stop_loss: 0.02 → 0.0` (mode resta `fixed` → disable guard `_stop_loss_breached_symbols` ritorna `{}`), `stop_shadow_enabled: true`. Commit `1f450c6`.
- Evidence: Kimi OOS replay (`docs/stop_loss_calibration_handback_2026-07-15.md` §5) — `no_protective` cum P&L $-56 vs `fixed_2pct` $-419 (7.5x) vs `wide vol_scaled` $-561. Lo stop al 2% su rumore (07-10: PANW/WDC/DELL, 0.26-0.53σ che hanno recuperato) distruggeva alpha.
- `broker_disaster_stop` (d_hard 12-20%) resta SHADOW-only (telemetria su `stop_shadow_log`, nessun floor applicato). Verificato e2e nel worker live: posizione -10% underwater non force-closed. Revisit: se una posizione cavalca oltre -15/20% (d_hard shadow) → wire d_hard a ordine broker reale (catastrophe-only), NON rimettere il 2%.

### Kimi stop k/floor/cap calibration — handback consegnato (NON mergeato)
- Branch `stop-loss-calibration-2026-07-15` (3 commit, handback). Window 06-01→07-14, 245 trade, walk-forward 70/30.
- Finding: Round 2 girava senza stop-risk sizing → DD blow-up. Aggiunto sizing al replay → gate stabile.
- Params calibrati: S1 (k8.0/floor0.04/cap0.15), S4 (k8.0/floor0.025/cap0.12). Gate OOS 7/7 PASS ma bootstrap 71.6% (marginale). L'operatore ha scelto la via più aggressiva (no protective stop, vedi sopra) invece del wide vol_scaled. Branch resta non mergeato come fallback conservative-aggressive.

## 2026-07-14

### Stage-2 shadow mode — model comparison (sviluppo, merge 07-15 `a099719`)
- Infrastruttura shadow completa: migration 037/038 (`llm_shadow_responses`), `log_shadow_responses` writer, pool `ollama:sem:shadow` dedicato + toggle Redis arm/disarm, scoring fire-and-forget con isolamento totale dal live path, comparison module pairwise (models + pair replay), 7-day auto-report con self-disarm. Stage-2 shadow armato confronta i candidati contro la coppia live senza toccare il path produttivo.

### Fixes 2026-07-14 — merge `ff3de56` (deployed live paper)
- **WS-1**: registry-based LLM model-pair selector + canonical order (`9688afa`).
- **WS-2**: freeze full stop metadata at entry anche in fixed mode (`d4512b0`).
- **WS-3**: resync stale ensemble weights on pair swap (`3ffe2fc`).
- **WS-4**: gate ingestion + sentiment su Alpaca real-time market clock (`a06e9f0`).
- **WS-5**: multi-tranche exit reconciliation — weighted-average exit price, `exit_order_ids` (migration 037), modello `is_final` (`b18006d`, `300b4d0`).
- 10 stale-fixture failure sistemate (`66e57c2`). Deploy: merge main + rebuild + restart, migration 037 applicata al DB live. **Incidente pool leak scoperto qui** (20 conn idle-in-transaction → fix 07-15 sopra).

## 2026-07-13

### Sector exposure cap — wired nel ConstraintEnforcer (shipped disabled)
- Pass `MAX_SECTOR_EXPOSURE` cablato nel `ConstraintEnforcer` (`ea436fd`, `af140d2`, `7f3be2e`): per-sector BUY notional ≤ `max_sector_exposure × NAV`. Sector map 96 simboli / 11 gruppi.
- `max_sector_exposure: 0.0` in `trading.yaml` = DISABLED (default). Non avrebbe boundato l'incidente 07-10/07-13 (semis ~6% NAV, sotto soglia) — protezione forward, complementare a F9a. Flip operatore suggerito: 0.10.

### F6 vol-target config-driven + flip live
- `target_vol` + clamp config-driven, zero behavior change (`22c8fe5`). Replay di calibrazione read-only (`d64715d`).
- Flip live `target_vol 0.10 → 0.12` (`237e660`, pushato): vol_scale ~0.74, +4pp deployment, 0% cap breach. DEFAULT shipped resta 0.10, LIVE è 0.12.

### S4 measurement Wave 1 — merge `3591d5c`
- Forward returns multi-orizzonte (1d/3d/5d, migration 036) incl. fallback signals. Coverage fwd 97/78/63% (da 29/0/0). +2 fix review: buffer +12d, feed IEX pinned (`83de839`).

### Frontend — nginx stale-backend-IP fix
- `d3ce750`: nginx re-resolve api upstream per evitare stale backend IP (self-heal dei 502 intermittenti).

## 2026-07-12

### F9a stop-loss redesign — merge `99215ff` (vol_scaled parked)
- `StopPolicy` deep module (`src/portfolio/stop_policy.py`): freeze-at-entry, mode `fixed`|`vol_scaled`, stop-risk sizing (§6.4), per-strategy `LossFeedback` (S1↔S4 decoupled), `d_hard` broker disaster stop.
- Migration 034: 8 colonne `stop_*` su `trades` + tabelle `stop_decisions` + `stop_shadow_log` (applicata al DB live).
- Replay gate OOS = **FAIL** (bootstrap delta P&L 41.5%, threshold ≥70%). 6/7 gate favoriscono vol_scaled ma il gate bootstrap non passa. `stop_loss_mode` resta `fixed`. Calibrazione delegata a Kimi (07-15, vedi sopra).

### F5 + F8 — merge `2bf31bd`
- **F5**: bug whole-share `regime_mult` fixato (troncamento intero del moltiplicatore).
- **F8**: `feedback:regime_scale:S*` cablato nel path portfolio (orchestrator weight-merge, per-strategy) dietro flag `apply_regime_scale=false` (shadow-only). Fix decay S1 (prerequisito). Gate flip 10-14gg shadow.

### Piani + doc
- S1 momentum refinements plan (skip-month, filtro assoluto, cap-after-norm) — Sonnet handoff.
- Three-model ensemble handoff brief (deepseek 3° modello, majority-of-3).
- S4 measurement foundation plan. Doc/code drift sweep project-wide (`27435ad`).

## 2026-07-11

### Pair world — sentiment ensemble coppia live
- Ensemble swap a `glm52,gptoss` via Redis `config:sentiment_llm_models` (was "all"/kimi+glm). Candidati swap `qwen35`/`gptoss` registrati con `in_all=False` ("all" resta il set live a 2 modelli). `7d530bb`.
- Divergent raw outputs persistiti per audit (gap audit colmato). Soglia divergence 0.30→0.40 (`a77fc64`, 07-09) INEFFICACE (fallback 75-80%: disaccordo kimi⇄glm bimodale) → swap coppia è la leva, non la soglia.

### F9a stop redesign — Phase 1-6 + Round 2 (Kimi)
- Phase 1-6: migration 034, Gap A Decision Log SELL row, StopPolicy, stop-risk sizing, per-strategy feedback, replay script.
- Round 2 (Kimi): replay augmentato a 7 gate spec §10 (bar Alpaca 15-min intraday, counterfactual P&L reale, bootstrap, walk-forward, ES95/max-DD/name-dependence). Per-strategy `LossFeedback` cablato in `performance.py`. Gate FAIL.

### CI
- Ruff/mypy/pip-audit install nelle CI, migrations before tests (`43641be`). Gitleaks fix: `[extend]` + `[[allowlist]]` (`f1e2544` — prima scannava nothing).

## 2026-07-10

### Deployment fixes — merge `e7e8f6f` (capital deployment restored)
- 4 chokepoint risolti (regime_mult fallback, vol floor, ecc.): deployment restored. Risultato live: 46 entry / $37.5K day-1 (vs 3-6 entry / $5-11K pre-fix), esposizione 26.2%, zero errori.
- **S1 sparse-ticker fix** (`0b1fbdf`): drop tickers con trailing prices stale; la sleeve 50% morta era la causa (deployment 0% da 06-01 a 07-10).
- Loss-feedback gate spostato fuori dal velocity block (`e1188fe`); rolling trigger 0% disabilitato, equity fallback rimosso (`ee13c50`). S4 `min_stocks=1` (`60a7095`).

### Trace panel — strategy origin
- `edd69f1`: il drawer Trace mostra `origin_strategy` per ordini non-news.

### Model comparison Stage 1 — merge `c931d13`
- Retro screen 5 modelli candidati vs 17 labeled items. Kimi worst-accuracy+slow, GLM-5.2 good, n=17 too small to act on. Stage 2 (shadow, live traffic) = base per Stage-2 shadow mode (07-14).

### Late-day signals + Quality page fix
- `59e66e3`: strong BUY after ~20:00 UTC loggati una volta (idempotent SKIP_STALE) invece di silent drop.
- `5f9baad`: NUMERIC→JSON numbers in quality routes (fix crash Quality.tsx `.toFixed()` su Decimal serializzato come stringa).

## 2026-07-09

### Ensemble divergence + loss-feedback
- `a77fc64`: soglia divergence 0.30→0.40, recovery loss-feedback eased. (Poi riscontrato inefficace 07-11, vedi pair world.)

### Model comparison Stage 1 — design + plan
- `5f6635d` (spec), `92a2234` (plan), `afc2245`/`4c4ee35` (helpers + resumable main loop with budget tracking).

### S7 POC-2c (07-07, `1007b13`)
- Tone IC analysis + pre-registered ALPHA-A3 gate. POC-1 small/mid PEAD inconclusive (n=15<30). S7 decision PO pendente (deadline 2026-08-01).

## 2026-07-04

### S7 revival month — POC-1 primo run, POC-2 riavviato via Alpha Vantage (correzione)
- **POC-1 (small/mid PEAD):** INCONCLUSIVE_DATA — n=15 eventi con barre+liquidità, sotto il minimo n≥30 pre-registrato. Due bug di codice trovati e corretti in esecuzione (mismatch unità market-cap `_market_caps` USD grezzi vs `classify_cap` milioni; crash batch Alpaca su ticker preferred). Nessuna vera small-cap (<$2B) è sopravvissuta ai filtri barre IEX/liquidità.
- **POC-2 (transcript tone, ALPHA-A3):** riavviato in serata — i transcript FMP richiedono Ultimate ($99/mo, non acquistato), ma il piano corretto (`0e84850`) usa Alpha Vantage `EARNINGS_CALL_TRANSCRIPT` (free tier, 25 req/giorno, `ALPHAVANTAGE_API_KEY` in `.env`); il primo executor seguiva la versione pre-correzione del piano. POC-1 in ri-esecuzione su universo completo (era 600 simboli alfabetici su 6.177). Resume plan: `docs/superpowers/plans/2026-07-04-s7-revival-resume.md`.
- Report: `reports/s7_poc/S7_REVIVAL_DECISION_REPORT_2026-07-04.md` (+ dettaglio POC-1 `reports/s7_poc/POC1_smallmid_report_2026-07-04.md`). Decisione S7 (rimozione/espansione POC/upgrade Ultimate) pendente dal PO.

### Risk monitor — NAV ed esposizione reali (fix finding forense #2)
- `_fetch_account_state()` in `risk_monitor_task.py`: NAV = equity Alpaca reale (era: somma cumulativa net_pnl → NAV negativo −578$), `total_exposure` = valore lordo posizioni / equity (era: hardcoded 1.0 → falso alert "exposure 100% > 50%" ogni giorno). Broker irraggiungibile → (0, 0) con warning, niente falso alert. TDD: `tests/workers/test_risk_monitor_task.py` (5 test). Verificato end-to-end nel worker: report id=21, NAV $110.307, exposure 5,7%, 0 alert.

---

## 2026-07-03

### Sprint 1 — Functional Review Remediation (merged su main)
- **FIX-01/02**: MarketAux e RSS rimosse dal beat (net-negative: 0/20 winner, 0 news/17g); task env-gated.
- **FIX-03**: freshness event-time — skip pre-inferenza 12h→2h (`MAX_NEWS_AGE_HOURS`); `sentiment_signals.published_at` (migr. 032) gate-a l'entry S4 nel ciclo live (default `None` per gli altri caller — sell-protection/audit vedono segnali più vecchi by design).
- **EN-03**: dedup cross-source content-hash+ticker wired su tutti i punti di ingestione.
- **B13**: drawdown cap unificato — 5% da `trading.yaml`, rimosso hardcode 10% dal portfolio scheduler; doc allineate (exposure 50%, stop S4 2%).
- **B20**: `reconcile-fills-evening` puntava a `run_daily_report` → ora `run_reconcile_fills_intraday`.
- **Resolver**: enforcement conservativo ON — `NO_TRADE_NOT_TRADABLE` droppato pre-inferenza (fail-open, `RESOLVER_ENFORCE_NOT_TRADABLE`).
- **B12**: soglie reali nei gate di backtest (Sharpe ≥0.5 IS / ≥0.3 OOS; erano 0.0 tautologiche).

### S2-1 — Source P&L Funnel (merged su main)
- `ingestion_stats_daily` (migr. 033) + `news_log.{raw_ingested_at,content_hash,discarded_reason}`; contatori persistiti da ogni worker (fail-safe).
- `GET /api/quality/sources` + sezione "Source Funnel & P&L" sulla pagina Quality con verdetti alle soglie roadmap §7.4.
- Backfill conservativo `news_log_id`: 435 orfani, 0 match non ambigui (gap genuino) → bucket `unknown`.

### S7 PEAD — SHELVED (gate ALPHA-A5 FAIL conclusivo)
- Run FMP (workaround free-tier: backward-walk su `to`): 97 eventi, drift +1.96% ma **excess vs SPY +0.05% (mediana −1.07%)** = beta + 5 outlier; nessuna dose-response; small/mid non testato (n=0). Audit in `strategy_lifecycle_audit`; riapertura solo via decisione PO (universo small/mid o POC transcript-tone — FMP free tier blocca i transcript).

### Doc coherence pass
- README/ARCHITECTURE/operations/frontend-guide/API/user_guide allineati al codice (B15/B16/B19/B21-B25); beat schedule tables riscritte dalla fonte (`celery_app.py`); API key rimossa da AGENT.md; doc storici archiviati in `docs/archive/`.

---

## 2026-07-02

### Connettore GDELT DOC 2.0 — SHELVED (stesso problema del GKG: lag indexing)
- **Connettore implementato** `src/connectors/gdelt_doc.py` (`GdeltDocConnector`) + task `run_gdelt_doc_ingestion_worker` — 11 test TDD verdi.
- **SHELVED dopo mini-spike** (2026-07-02): **NON abilitare, NON aggiungere beat schedule.**
- **Root cause**: GDELT DOC 2.0 ha un lag di indexing di **≥2 giorni** (confermato: articoli più recenti nel feed = 30 giugno; oggi = 2 luglio). Il filtro `_SENTIMENT_MAX_NEWS_AGE_HOURS=12` del sentiment worker scarterebbe sempre il 100% degli articoli GDELT. Stessa causa del GKG (`gdelt_gkg.py` già dismesso per lag 24h).
- **Rilevanza bassa**: query `NVIDIA sourcelang:english` ha restituito "Eli Lilly Upgraded, Carvana Downgraded" — nessuna relazione con NVIDIA. Full-text search loose, peggiore di `org_lookup`.
- **Rate limit**: 5s/request per IP; burst → ban multi-ora. 96 simboli × 6s ≈ 10 min/ciclo.
- **Fonti attive**: `alpaca_benzinga` + `marketaux` coprono il need di freschezza e diversificazione. GDELT DOC non aggiunge valore.

### Fonti — MarketAux fix lag (bug connector) → riattivata diversificazione
- **Root cause**: MarketAux era silente (news di ~13 giorni fa, skippate dallo skip freschezza 12h). Non era un ritardo del free tier — il `fetch()` live non passava `sort`/`published_after`, quindi l'API restituiva il default (articoli vecchi). Test live: con `sort=published_on` MarketAux serve news di **oggi**.
- **Fix**: `fetch()` ora richiede `sort=published_on` + `published_after=(ora−12h)` + `filter_entities=true` → news fresche, on-topic, entity-tagged. Riattiva una **seconda fonte fresca e diversificata** (5000+ testate) accanto ad alpaca_benzinga → riduce il rischio di single-source/polarizzazione.

---

## 2026-07-01

### Fix da analisi e2e del 2026-07-01 (giornata +$68, ma 3 affinamenti)
- **SKIP_STALE meno rumoroso**: la lookback a 96h del ciclo ri-scansiona segnali vecchi ogni 15 min → un segnale di 40h (es. INTC 0.451 di ~2gg prima) veniva loggato ogni ciclo come "appena scaduto" (94% dei 399 SKIP_STALE di ieri). Ora `_record_stale_drops` logga solo i segnali scaduti *da poco* (entro `_STALE_LOG_RECENT_BUFFER_H`=1h da max_age). (`b2c0f54`)
- **Floor order-gate a 0.30**: quando `feedback:entry_threshold` scade (TTL 48h), il gate cadeva al prefiltro `min_score 0.10` → segnali deboli tradavano (SPCX 0.180). Ora fa floor al `loss_feedback.threshold_baseline` (0.30). (`b2c0f54`)
- **Reversal non si fida dei fallback**: `_sentiment_reversal_sells` forzava un SELL leggendo solo lo score, anche su un **FinBERT fallback** (parte quando l'ensemble diverge → inaffidabile). Es. SPCX venduto su fallback −0.573 → perdita −20.23. Ora ignora i segnali `fallback_used`. Fix generale (tutte le posizioni).
- **Nota fonti** (side-effect): lo skip freschezza (24h→12h) ha silenziato GDELT e MarketAux perché le loro news sono intrinsecamente vecchie (GDELT ~24h+ lag GKG, MarketAux ~9 giorni). Resta solo alpaca_benzinga (fresco+pulito). Da decidere consapevolmente + indagare il lag MarketAux.

### Fonti — Finnhub aggiunto poi SHELVED dopo mini-spike
- **Analisi fonti** (via ricerca): principio "explicit tagging > NER > none". Aggiunto `FinnhubNewsConnector` (company-news US, ticker taggati dalla fonte, free tier) + breakdown precision per `extraction_method` nell'harness (`validate_ticker_sentiment.py`) per decidere data-driven su GDELT.
- **Mini-spike (verdict: SHELVE)**: un fetch reale ha prodotto **2115 articoli/fetch** (5,5× il throughput del worker ~16/h → flood) con **rilevanza larga** (news generiche/listicle/competitor taggate all'azienda, es. "Best CD rates" → GS, "31 Single-Stock ETFs" → TSM; ~40-60% issuer-specific). Conclusione: il *ticker* è pulito (source-tagged, no NER nostro) ma la *rilevanza* no → non è un win e floodderebbe la coda.
- **Azione**: Finnhub **shelved** — schedule beat rimossa + guard `FINNHUB_INGESTION_ENABLED` (default off). Connector/task/test restano pronti. Riabilitare SOLO con cap per-simbolo + filtro rilevanza.
- **Reframe**: il collo di bottiglia reale è il **throughput del worker**, non il numero di fonti. La leva è rilevanza/precisione per articolo, non volume.

---

## 2026-06-30

### Operations Navigation + Auto-Improve Gate Counterfactuals
- **Frontend**: `Config`, `Admin` e `System` sono unificati nella nuova pagina `Operations` con tab dedicate; i vecchi URL fanno redirect verso `Operations?tab=...`. La sidebar segue il flusso operativo: Overview → Operations → News → Signals → Quality → Trading → Performance → Strategies → Auto-Improve → ricerca/strumenti.
- **Auto-Improve**: Phase B è presentata come feedback gate. La pagina distingue la soglia effettivamente applicata dal portfolio scheduler da `regime_scale`, che resta legacy/audit finché non viene cablato nel sizing portfolio.
- **Counterfactual**: Phase C include `SKIP_THRESHOLD` oltre a `SKIP_EMA` e `SKIP_CAP`; restano esclusi `SKIP_STALE`, `SKIP_FALLBACK` e `SKIP_POSITION`.
- **Docs**: aggiornata documentazione API, architettura, user guide e frontend operator guide per riflettere Operations e i nuovi counterfactual gate.

### S4 dev-doc punti 1-3 (da `docs/archive/2026-06-07-oneoff/S4_TICKER_SENTIMENT_DEV_INSTRUCTIONS_2026-06-30.md`)
- **(1) Soglie unificate + documentate**: `docs/strategies.md` riscritto col vero chain di gating live (freshness → prefiltro ranker `min_score 0.10`/`min_confidence 0.30` → **order gate** `feedback:entry_threshold` 0.30/dyn → ranking top-N), con tabella "Threshold map" che distingue i 3 concetti e segna il gate legacy `score>0.30 AND EMA20` come INATTIVO sotto `engine=portfolio`. Commento di chiarezza in `S4Config` (min_score = prefiltro, non order threshold). Corretti anche i modelli ensemble nel doc (Kimi+GLM-5.2 cloud, non Qwen/locale).
- **(2) Resolver in SHADOW (Fase A)**: nuovo `news_resolved_entities` (migr. 031) + `src/connectors/resolver_shadow.py` + `pg_store.write_resolved_entity`. Il worker sentiment calcola e **persiste** la risoluzione ticker deterministica (decision/confidence/ambiguity/directness/tradable + evidenze) per ogni news, **senza gating** del signal live (offline, fail-safe, flag `RESOLVER_SHADOW_ENABLED`). Prepara la misura precision resolver vs `news_labels`.
- **(3) Decision Log — `SKIP_STALE`**: i signal **forti** (|score| ≥ min_score) scartati per età (> max_age 4h) vengono registrati in `execution_decisions` (`decision=SKIP_STALE`, reason con età+score), così si vede quando si "perde" un segnale buono per scadenza. Frontend: label + help aggiornati.

### Signals page — evidenzia i segnali sopra soglia
- **Feat**: la colonna Score della pagina Signals evidenzia in **verde ✓** i segnali con `|score| ≥ soglia feedback gate` (soglia live da `/feedback/status`, default 0.35); legenda con la soglia corrente. Colpo d'occhio su quali segnali superano il gate senza incrociare Auto-Improve.

### Decision Log — visibilità signal scartati al feedback gate
- **Feat**: i signal scartati dal feedback gate S4 (score < soglia) vengono ora registrati in `execution_decisions` con `decision=SKIP_THRESHOLD` e `reason` (es. "score 0.180 < feedback threshold 0.350"). Prima sparivano senza traccia → nei giorni senza trade il Decision Log era vuoto e non si distingueva "valutati e scartati" da "nessun signal". Nuovo helper `_record_gate_drops` (fail-safe); frontend: label + help aggiornati (`SKIP_THRESHOLD`).

### Sentiment Worker — skip news stantie + drenaggio backlog (e2e fix)
- **Root cause** (diagnosi e2e): `news:queue` è FIFO e il worker (4 item/run, ~16/h) era **~13 giorni indietro** (item più vecchio 17 giu). Generava signal su news di 2 settimane fa con `generated_at=now()` → sentiment stantio iniettato nel ciclo live come se fosse fresco, tutto troppo debole per superare il feedback gate. Sintomo osservato: "signal con data di oggi ma nessun decision log".
- **Fix**: il worker ora pesca finché non ha **4 item freschi**, saltando senza chiamata LLM gli item più vecchi di `_SENTIMENT_MAX_NEWS_AGE_HOURS` (24h), con cap `_MAX_QUEUE_SCAN_PER_RUN=5000`. Gli item saltati vengono scartati da `news:processing` (anche nel ramo all-stale, altrimenti la crash-recovery li ri-accodava in loop). 5 test su `_is_stale_news`. (`28638f9`)
- **Risultato live**: backlog drenato **9309 → 835** in ~3 run (saltati ~8500 item vecchi); item più vecchio in coda ora ~24h invece di 13 giorni; il worker processa di nuovo news recenti.
- **Nota residua**: throughput ~16 signal/h (latenza LLM) < ingestion → la coda fresca si processa parzialmente e gli item invecchiati >24h vengono ora saltati. Da approfondire separatamente.

### Signal Selection — ensemble non sovrascritto da fallback FinBERT
- **Fix**: `fetch_signals_for_cycle` ora preferisce il segnale **ensemble** più recente al FinBERT fallback nella finestra 4h (`ORDER BY symbol, fallback_used ASC, generated_at DESC`). Prima si prendeva solo il più recente per simbolo, quindi un fallback debole generato dopo un ensemble forte lo sovrascriveva (es. AMKR +0.638 alle 15:16 → +0.009 fallback alle 15:48), facendo cadere il simbolo sotto soglia. Il fallback si usa solo se non c'è ensemble nella finestra. (`10c7836`)

### Watchlist S4 — +5 simboli (91 → 96)
- Aggiunti **ROKU, RDDT, HOOD, WDC, SPCX**: nomi off-watchlist con segnali ensemble forti **ricorrenti** su 14g (es. ROKU 4×≥0.35 avg 0.38), prima non tradabili perché il ciclo portfolio carica solo i simboli in watchlist. Il sentiment per questi nomi era già calcolato via estrazione entity/cashtag dalle news. Correttezza estrazione non ancora validata su QX-01 — rivedere dopo l'annotazione. (`38be96b`)

### Qualità & misurazione (QX-01 / QX-02) + igiene dati
- Golden label set: tabella `news_labels`, sampling stratificato (148), **UI Labeling blind** (`/labeling`), forward-return da Alpaca historical, harness `validate_ticker_sentiment.py`; **dashboard Quality** (`/quality`). (`9d21215`, `537471f`, `0dcf4da`)
- Igiene dati: QS-06 (`eligible` reale), QS-07 (backtest/live parity), QT-03 (`news_log.extraction_method`), QS-09 (backfill `news_log_id`), QS-10 (logging strutturato fallimenti ensemble), QS-03 (agreement→confidence, dietro flag). Dettaglio e stato in `docs/S4_NEWS_PIPELINE_RND_BACKLOG_2026-06-29.md`.

### Sentiment Worker — Observability Ollama semaphore
- **Feat**: notifica Telegram rate-limited (max 1 ogni 30 min) quando tutti i modelli ensemble vanno in timeout (`raw_outputs=[]`). Il messaggio include il comando di recovery esatto.
  - Nuova funzione `_maybe_notify_ollama_timeout()` in `src/workers/sentiment.py`.
  - `run_inference` ora usa reasoning `"FinBERT fallback (Ollama timeout)"` vs `"FinBERT fallback (ensemble divergence)"` per distinguere i due scenari.
  - 6 test TDD in `tests/workers/test_ollama_timeout_alert.py`.
- **Fix**: auto-recovery del semaphore Redis se tutti gli slot sono stati perduti (`LLEN==0`). Il worker li ripristina all'avvio del task successivo senza intervento manuale (sicuro: `worker-inference` ha `concurrency=1`).
  - Nuova funzione `_recover_ollama_semaphore_if_leaked()` in `src/workers/sentiment.py`.
  - 5 test TDD in `tests/workers/test_ollama_sem_recovery.py`.
- **Fix**: slot semaphore Ollama ridotti da 3 → 2 (ensemble ha 2 modelli; max 2 call parallele per item).
- **Root cause analisi** (2026-06-29 ore 21:xx UTC): Ollama API era UP ma il semaphore Redis era a 0/3 slot per leak da task killati da `SoftTimeLimitExceeded` (4 item × 270s/item > soft_limit 600s). Recovery manuale eseguito (`DEL ollama:sem ollama:sem:init`), ora automatico.

### Documentazione
- Aggiunta review qualitativa estrazione ticker + sentiment: `docs/TICKER_SENTIMENT_QUALITY_REVIEW_2026-06-30.md`

---

## 2026-06-29

### Portfolio Scheduler — Anti-stale-ranker-sell guard
- **Bug fix**: posizioni con segnale fresco positivo venivano vendute quando `CrossSectionalRanker` ritornava `{}` pesi per vincolo `min_stocks=2` (es. solo 1 segnale a forza positiva tra i 2 che passano il gate assoluto). L'orchestratore interpretava `merged_weights={}` come "sell all" per le posizioni correnti.
  - Root cause: il gate `abs(score) >= threshold` ammette segnali negativi (es. MU -0.4185) che passano il gate ma vengono scartati dal ranker long-only (`strength = score*confidence <= 0`). Con 1 candidato positivo < `min_stocks=2` il ranker ritorna vuoto.
  - Fix: nuovo `_fresh_signal_protected_symbols()` — protegge le posizioni aperte con segnale fresco >= threshold da SELL senza attributazione di strategy.
  - 8 test TDD aggiunti in `tests/workers/test_protected_sell.py`.
- **Fix**: falso alert Telegram "Execution fill divergence: 0/0 orders submitted" su cicli idle (nessun ordine pianificato). Il check viene ora saltato quando `final_count==0`.

### LLM Ensemble
- **Qwen3.5 sostituito da GLM-5.2**: Qwen3.5 estraeva ticker in modo aggressivo (es. MU da notizia macro); GLM-5.2 ha reasoning long-horizon migliore per analisi macroeconomica.
- Ensemble attivo: Kimi K2.6 + GLM-5.2 (2 modelli); fallback weights `{kimi-k2.6:cloud: 0.50, glm-5.2:cloud: 0.50}`.

---

## 2026-06-17

### Documentazione
- Riorganizzazione completa docs/: archiviate ~25 file obsoleti in `docs/archive/`
- Aggiornati: ARCHITECTURE.md, strategies.md, operations.md, API.md, CLAUDE.md, DECISIONS.md
- Creati: docs/strategies/s7-pead.md, docs/CHANGELOG.md, docs/llm-config.md

---

## 2026-06-16

### Modifiche
- **Worker split**: separato `worker-inference` (concurrency=1, queue `inference`) da `worker` (concurrency=4, queue `celery`) per isolare FinBERT/Ollama
- **Redis cycle lock**: aggiunto `SET portfolio:cycle:lock NX EX 840` in `portfolio_scheduler.py` per prevenire run concorrenti
- **Hold minimum 30 min**: filtro SELL su simboli comprati negli ultimi 30 minuti (previene roundtrip S4→S1)
- **FinBERT int8 quantization**: `torch.quantization.quantize_dynamic` applicato al load di FinBERT (~50% RAM reduction)
- **Daily analysis script**: `scripts/daily_analysis.sh` con cron 14:30 CEST lun-ven, output su Telegram

### LLM Ensemble
- DeepSeek-V4-Pro rimosso (OOM + latency eccessiva)
- GLM-5.1 rimosso (IC inferiore a Kimi K2.6 in A/B test)
- **Attivi**: Kimi K2.6, Qwen3.5

---

## 2026-06-15

### Code Review
- Review completa del codebase: vedi `archive/2026-06-p0-p2-controlled-paper-history/02_external_reviews/CODE_REVIEW_FULL_2026-06-15.md` (archived 2026-06-23)
- Identificati 13 fix prioritari ora tracciati in `docs/superpowers/plans/2026-06-16-master-roadmap.md`

---

## 2026-06-07

### Nuova Strategia
- **S7 PEAD** aggiunto: classifica 8-K filing SEC via Ollama, cattura Post-Earnings Announcement Drift
- Allocazione target: 15%
- Worker: `src/workers/pead_worker.py`
- Beat task: `pead-ingestion` (queue `inference`, ogni 30 min 14:05-21:35 UTC)

---

## 2026-06-06

### Bug Fix (P0/P1)
- Connection leak in PostgreSQL store: aggiunto `finally: pg.close()` in tutti i task Celery
- `asyncio.run()` in contesto async: sostituito con `await` corretto
- N+1 queries: batch query per simboli multipli
- Race condition PostgreSQL: aggiunto `FOR UPDATE` su operazioni critiche
- Vedi `archive/2026-06-p0-p2-controlled-paper-history/02_external_reviews/CODE_REVIEW_FULL_2026-06-15.md` per lista completa (archived 2026-06-23)

---

## 2026-05-26

### Backtest
- Completato backtest GKG novembre 2025 (run-id: gkg-nov25-v1)
- IC/ICIR analizzato; S2 disabilitata definitivamente (OOS IC = −0.55, tutti i gate falliti)

---

## 2026-05-18

### Frontend
- Dashboard React aggiunta: Overview, Signals, Trades, Performance, LLM, Admin
- Backend FastAPI: routes per trades, signals, decisions, performance, analytics

---

## 2026-05-13

### Infrastruttura
- GDELT GKG bulk ingestion implementata (`src/connectors/gdelt_gkg.py`)
- A/B test GDELT completato: GKG > standard per IC (~15% improvement)
- Multi-asset news-driven pipeline completata

---

## 2026-05-03

### Foundation
- Sistema LLM Alpha Miner implementato (pipeline offline)
- FinBERT sentiment + Ollama ensemble (4 modelli, poi ridotti a 2)
- Backtrader backtesting framework
- Celery + Redis + PostgreSQL stack operativo
- Portfolio Orchestrator (Phase G): weight-then-order multi-strategy cycle
