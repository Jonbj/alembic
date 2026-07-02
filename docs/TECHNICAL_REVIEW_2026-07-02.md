# Alembic — Independent Full-Stack Technical Review

**Review date:** 2026-07-02  
**Reviewer:** Kimi (independent senior engineer)  
**Scope:** Full-stack review of the Alembic LLM-based algorithmic trading system: frontend, backend, data layer, workers, tests, documentation, DevEx, security, performance.  
**Mode:** Read-only. No code changes, no live execution, no orders placed.

---

## A. Executive Summary

**Overall state: QUASI PRONTO — può andare in maintenance/integrazione controllata, ma NON è pronto per rilascio autonomo senza mitigazioni.**

Il progetto ha un'architettura ragionevole che rispetta il vincolo fondamentale "Alpha Miner": gli LLM non sono nel hot path di esecuzione, i segnali sono pre-computati in Redis/PG (`src/workers/sentiment.py`, `src/workers/portfolio_scheduler.py`). Il codice è coperto da un grande numero di test (≈2400), e le gate di CI bloccano su ruff/pytest/coverage. Tuttavia ci sono classi di problemi ricorrenti che ne impediscono il rilascio fiducioso:

1. **Incoerenza documentazione ↔ codice.** `README.md` e `docs/ARCHITECTURE.md` dicono ancora che P2-05 è "pending", mentre il codice lo ha implementato. `AGENT.md` contiene una API key di esempio hardcoded. L'API strategie (`src/api/routes/strategies.py`) mostra metriche S1 stale e `status: "validated"` mentre la config dice `supervised_paper`/`promotion_blocked=true`. README descrive il legacy `ExecutionWorker` mentre il percorso attivo è `PortfolioOrchestrator`.
2. **Rischi di sicurezza concreti.** Deriving paper/live mode dall'URL Alpaca (`src/api/deps.py:51`), JWT fallback a chiave effimera per-processo (`src/api/jwt_utils.py:12-16`), token JWT senza `iss`/`aud`/`jti`/`nbf`, assenza di rate limiting, e secret leakage potenziale tramite `AGENT.md` e log.
3. **Problemi operazionali nel percorso di esecuzione.** Il kill-switch disattivato riporta sempre `mode: "paper"` (`src/api/routes/admin.py:212`), sovrascrivendo lo stato precedente. `_execution_engine()` in `src/api/routes/trading.py:104` hardcoded il path Docker `/app/config/trading.yaml`. Il beat task `reconcile-fills-evening` punta alla funzione sbagliata (`run_daily_report`).
4. **Numeri di risk management incoerenti.** Drawdown cap è 10% in docs, 5% in config e 10% hardcoded nel portfolio scheduler; max exposure documentato 95% ma config 50%; S4 stop-loss documentato 5% ma config 2%. Questi valori sono fondamentali per la sicurezza del capitale e devono avere un'unica fonte di verità.
5. **Ensemble LLM e modelli regime non allineati.** README dice Kimi + Qwen3.5; il sentiment reale è Kimi + GLM-5.2; la regime detection usa Qwen3.5 e `src/workers/regime.py` non supporta GLM-5.2.
6. **Frontend: XSS Critical, token storage, lint failure.** Contenuti esterni e LLM output (news, reasoning, labeling) sono renderizzati senza sanitizzazione (`src/pages/News.tsx`, `src/pages/LLM.tsx`, `src/pages/Signals.tsx`, `src/pages/Labeling.tsx`) → rischio XSS. Il JWT è persistito in `sessionStorage` (`frontend/src/store/index.ts:41`). Il frontend ha 9 lint errors / 5 warnings. Componenti monolitici (Performance 935 linee, Docs 554), stili inline ovunque, polling aggressivo su Overview.
7. **Frontend sottodimensionato in test e types.** C'è un solo file di test (`frontend/src/tests/f0_safety_hygiene.test.tsx`). Lo store e l'Admin page non conoscono il modo `dry_run` supportato dal backend. La type `Mode` è duplicata/fragile.
8. **Quality debt e dead code.** File vuoto `=0.11` in root, pool DB globale con criticità note (memoria), codice auto-generato apparentemente corretto ma con edge case non testati (divisone per volatilità zero, implied vol convergence non garantita, ecc.).
9. **Race condition e ordering nel portfolio scheduler.** Lock Redis TTL (840 s) inferiore alla cadenza beat (15 min); `_mark_signal_fired()` invocato prima della conferma Alpaca; righe `trades` scritte dopo `submit_order()`. Questi difetti possono generare cicli sovrapposti, segnali S4 persi e ordini orfani.
10. **Worker/Celery operational fragility.** `LLMBudgetTracker` mantiene un row lock PostgreSQL senza chiudere la transazione; i limiti di tempo Celery possono killare task Ollama; solo il sentiment task usa `acks_late`; `workers.yaml` non viene caricato e le costanti di trading sono hardcoded; il poller Telegram ricrea l'event loop in modo incoerente.

**Giudizio sintetico:** Il modulo è *mantenibile* e *integrabile* in un flusso controllato, ma richiede una passata di hardening su documentazione, sicurezza, allineamento FE/BE, numeri di risk, coerenza worker/store/Celery, frontend (XSS/lint/token storage) e test FE prima di qualsiasi esposizione a capitali reali o anche paper non supervisionato.

**Nuovo tema critico emerso dalla review worker/store/Celery:** race condition e ordering nel portfolio scheduler. Il lock Redis ha TTL più breve della cadenza beat, l'idempotenza S4 viene marcata prima della conferma Alpaca, e le righe trade vengono scritte dopo l'invio dell'ordine. Questi problemi possono causare cicli sovrapposti, segnali persi, ordini orfani e duplicati.

---

## B. Findings Prioritizzati

### B1. Documentazione e API surface non allineate alla realtà del codice

**Severità:** High  
**Area:** documentazione / backend / integrazione  
**File:** `README.md:27`, `docs/ARCHITECTURE.md:618`, `docs/P2_STATUS_2026-06-21.md:55`, `src/api/routes/strategies.py:55-140`, `AGENT.md:38`, `CONTRIBUTING.md:43`

**Descrizione:**
- `README.md:27` elenca P2-05 come **Pending**, ma il codice e `docs/P2_STATUS_2026-06-21.md` lo dichiarano completato.
- `docs/ARCHITECTURE.md:618` dice ancora "P2-05 Pending Safety Items (NOT_IMPLEMENTED — blocks Kimi P2 Acceptance Audit)".
- `src/api/routes/strategies.py` hardcoded S1 con `status: "validated"`, `oos_sharpe: 0.5128`, `annual_return: 0.07`, `max_drawdown: 0.15`. `config/strategies.yaml:14-25` invece dice `mode: supervised_paper`, `promotion_blocked: true` e la stessa API non aggiorna questi valori.
- `docs/P2_STATUS_2026-06-21.md:55` dice S2 = `paper`; `config/strategies.yaml:26-30` e migration `025_strategy_lifecycle.sql:30` lo segnano `disabled`/`research` con 0% allocation.
- `AGENT.md:38` mostra una X-API-Key esplicita (`eJvMeuHhJS27FPugKIu4qKGgV7roIdLfcv7h20MwuQg`) che potrebbe essere reale.
- `CONTRIBUTING.md:43` dice "All 1700+ tests must pass" — il conteggio attuale è 2386.

**Impatto concreto:** Un operatore che legge README o chiama `/api/strategies` può credere che S1 sia validato e pronto per paper/live, mentre in realtà è demoted, promotion-blocked e supervisionato. In un sistema di trading questo è un rischio di autorizzazione grave.

**Raccomandazione:**
1. Sincronizzare README/ARCHITECTURE con lo stato di P2 e aggiungere una nota sulla data dell'ultimo aggiornamento.
2. Rendere `src/api/routes/strategies.py` dinamico: leggere `mode`/`promotion_blocked` da `strategy_lifecycle` e `allocation_pct` da `StrategyRegistry`; aggiungere un campo `data_quality_warning` per le metriche backtest stale.
3. Rimuovere o anonimizzare la API key in `AGENT.md`.
4. Correggere il conteggio test in `CONTRIBUTING.md` e/o renderlo generico.

---

### B2. Sicurezza: derivazione paper/live dall'URL e JWT fragile

**Severità:** Critical  
**Area:** sicurezza / backend  
**File:** `src/api/deps.py:44-52`, `src/config.py:127-134`, `src/api/jwt_utils.py:12-39`  
**✅ FIX APPLICATO 2026-07-02** — `get_alpaca_trading_client` ora usa `config.ALPACA_PAPER_MODE` invece di `ALPACA_BASE_URL.startswith(...)`. JWT e rate limiting restano in backlog (P1).

**Descrizione:**
- `src/config.py:131-132` dichiara esplicitamente: "Single source of truth for paper vs live trading mode... Workers must read this field; never derive mode from ALPACA_BASE_URL substring."
- Tuttavia `src/api/deps.py:51` fa esattamente questo:
  ```python
  paper=config.ALPACA_BASE_URL.startswith("https://paper"),
  ```
  Se un operatore imposta `ALPACA_BASE_URL=https://live-api.alpaca.markets` ma dimentica `ALPACA_PAPER_MODE=false`, il dependency factory passa `paper=True` e le chiamate API vanno a un endpoint live senza l'intenzione esplicita.
- `src/api/jwt_utils.py:12-16` definisce `_EPHEMERAL_KEY = secrets.token_hex(32)` al momento dell'import del modulo. Se `JWT_SECRET_KEY` non è impostato, ogni processo worker avrà una chiave diversa; un token generato dall'API non sarà validato dagli worker. `main.py` alza un errore nello startup, ma il fallback esiste e la chiave è globale al modulo, non al processo.
- I JWT non hanno `iss`, `aud`, `jti`, `nbf` e usano semplicemente `sub`. Non c'è revoca, non c'è refresh token, scadenza di default 24h (`config.py:102`).

**Impatto concreto:** Risk di inviare ordini live invece che paper se la config non è coerente; risk di autenticazione instabile o bypassabile se JWT_SECRET_KEY non è settato; nessun meccanismo di revoca token in caso di compromissione.

**Raccomandazione:**
- Usare **solo** `config.ALPACA_PAPER_MODE` in `get_alpaca_trading_client`; rimuovere la derivazione dall'URL. Aggiungere un log/alert esplicito all'avvio che mostri `paper_mode` e `base_url`.
- Rimuovere completamente il fallback a chiave effimera: se `JWT_SECRET_KEY` manca, rifiutare l'avvio (già fatto in `main.py`, ma va propagato anche ai worker e ai test).
- Aggiungere claim `jti` e un endpoint di revoke/blacklist oppure, meglio, switchare a session-side short-lived token + refresh.
- Implementare rate limiting (es. `slowapi` o middleware custom) sugli endpoint di login, killswitch e mode change.

---

### B3. Kill-switch: disattivazione ripristina sempre `paper`, perdita dello stato precedente

**Severità:** High  
**Area:** backend / sicurezza  
**File:** `src/api/routes/admin.py:210-212`

**Descrizione:**
```python
store.deactivate_killswitch()
store.deactivate_operator_halt()
store.set_mode("paper")
```
Se il sistema era in `backtest`, `dry_run` o `semi_auto` prima dell'attivazione del killswitch, alla disattivazione viene forzato in `paper`. Questo è un cambiamento di stato implicito e pericoloso.

**Impatto concreto:** Un operatore che riattiva il sistema dopo un halt potrebbe ritrovarsi in paper trading senza averlo esplicitamente richiesto, o viceversa potrebbe aspettarsi backtest e ottenere paper.

**Raccomandazione:** Salvare il modo precedente in Redis prima di `set_mode("halted")` (es. `mode:before_halt`) e ripristinarlo alla disattivazione. Se non esiste lo snapshot, defaultare a `paper` ma loggare un warning esplicito.

---

### B4. Path hardcoded `/app/config/trading.yaml` nel backend

**Severità:** Medium  
**Area:** backend / devops  
**File:** `src/api/routes/trading.py:103-108`

**Descrizione:** La funzione `_execution_engine()` apre direttamente `/app/config/trading.yaml`. Questo funziona solo nel container Docker; in sviluppo locale o in test il file è in `config/trading.yaml` e la lettura fallisce silenziosamente, tornando `legacy_sentiment`.

**Impatto concreto:** Incongruenza tra comportamento in dev e in produzione; la UI potrebbe mostrare informazioni sbagliate sull'engine attivo.

**Raccomandazione:** Usare `Path(__file__).resolve().parents[3] / "config" / "trading.yaml` (come in `src/api/routes/signals.py:17`) oppure centralizzare la risoluzione del path di config in `src/config.py`.

---

### B5. Frontend: XSS Critical, token storage insecure, lint failure

**Severità:** Critical (XSS); High (token storage, lint)  
**Area:** frontend / sicurezza / qualità codice  
**File:** `src/pages/News.tsx:113-114`, `src/pages/LLM.tsx:88-89`, `src/pages/Signals.tsx` (reasoning fields), `src/pages/Labeling.tsx:113-114`, `src/store/index.ts:41`, `eslint.config.js` / `package.json`

**Descrizione:**
- Contenuti esterni e LLM output vengono renderizzati direttamente come children React senza sanitizzazione:
  - `src/pages/News.tsx`: titoli/body snippet dei news feed.
  - `src/pages/LLM.tsx`: reasoning dei modelli.
  - `src/pages/Signals.tsx`: campo reasoning del segnale.
  - `src/pages/Labeling.tsx`: testo delle news da etichettare.
  Questo è un XSS surface: notizie, output LLM o input di labeling potrebbero contenere script.
- Il JWT token viene persistito in `sessionStorage` (`src/store/index.ts:41`) tramite Zustand persist. `sessionStorage` è accessibile a qualsiasi script in caso di XSS, quindi il token può essere esfiltrato.
- Manca una Content Security Policy in `index.html`.
- `npm run lint` al momento fallisce con 9 errors / 5 warnings (`ApiKeyModal.tsx`, importi inutilizzati, `useEffect` con setState, ecc.).

**Impatto concreto:** Un payload XSS in un titolo di news o in output LLM può rubare il token JWT, impersonare l'operatore, attivare il kill-switch o cambiare modalità operativa. Un frontend con lint failure non può considerarsi pronto per produzione.

**Raccomandazione:**
1. Sanitizzare tutti i testi esterni e LLM con DOMPurify prima del rendering; trattare l'output LLM come untrusted.
2. Aggiungere una CSP strict (`default-src 'self'`, niente `unsafe-inline`/`unsafe-eval`).
3. Considerare spostare il token in un `httpOnly`, `SameSite=Strict` cookie (richiede cambio BE/FE) o almeno ridurre la durata e aggiungere refresh.
4. Correggere tutti i lint errors; far fallire la CI su lint failure.

---

### B5b. Frontend: un solo test, type Mode duplicata, dry_run non riconosciuto

**Severità:** High  
**Area:** frontend / test / integrazione  
**File:** `frontend/src/tests/f0_safety_hygiene.test.tsx`, `frontend/src/store/index.ts:4`, `frontend/src/pages/Admin.tsx:16`, `frontend/src/App.tsx`

**Descrizione:**
- L'intero frontend ha **un solo file di test** con 8 test. Non ci sono test per componenti condivisi, API client, hook, routing, error boundary, o pagine individuali.
- `frontend/src/store/index.ts:4` dichiara `type Mode = 'backtest' | 'paper' | 'semi_auto' | 'full_auto' | 'halted'`.
- `frontend/src/pages/Admin.tsx:16` ridichiara `const MODES = ['backtest', 'paper', 'semi_auto', 'full_auto', 'halted'] as const` e `type Mode = typeof MODES[number]`.
- Il backend accetta anche `dry_run` (`src/api/routes/admin.py:23`: `_VALID_MODES = frozenset({..., "dry_run"})`). Il frontend non lo conosce, quindi una chiamata a `GET /api/admin/mode` che restituisce `dry_run` può rompere tipi/logica UI.

**Impatto concreto:** Alto rischio di regressioni visive/UX; incongruenza di tipo tra FE e BE; modalità operative non gestite consistentemente.

**Raccomandazione:**
1. Estrarre `Mode` in un file di types condiviso (`frontend/src/types/system.ts`) e importarlo in store, Admin, App.
2. Aggiungere `dry_run` o rimuoverlo dal backend se non serve.
3. Aggiungere test per: `apiFetch` (errori 401/403/429/500), `ReadinessBanner`, `ErrorBoundary`, una pagina rappresentativa (`Overview` o `Strategies`).

---

### B6. API client frontend: gestione errori grezza e side effect nella chiamata

**Severità:** Medium  
**Area:** frontend / sicurezza / UX  
**File:** `frontend/src/api/client.ts:12-29`

**Descrizione:**
- `apiFetch` fa `window.location.href = '/login'` inline in caso di 401/403, senza flusso di logout pulito. Se vengono effettuate chiamate in parallelo, tutte forzeranno redirect multipli.
- Non c'è retry policy centralizzata: solo il generic `QueryClient` retry di 3 volte.
- Non c'è meccanismo di refresh token.
- URL relativi (`fetch(path)`) funzionano grazie al proxy Vite in dev, ma in produzione dipendono dal mount statico in `src/api/main.py:63-65`.

**Impatto concreto:** Esperienza utente instabile; risk di redirect loop; nessuna gestione graceful del token scaduto.

**Raccomandazione:** Implementare un interceptor/response handler centralizzato che invalidi la query e reindirizzi una sola volta; aggiungere refresh token o short-lived token; usare URL assoluti configurabili per produzione.

---

### B7. PostgreSQL connection pool globale e potenziale leak

**Severità:** Critical  
**Area:** backend / performance / sicurezza  
**File:** `src/store/pg_store.py:24-42`, `src/workers/portfolio_scheduler.py` (uso del pool)

**Descrizione:** `src/store/pg_store.py:25` dichiara `_db_pool: pool.ThreadedConnectionPool | None = None` come globale. La memoria del progetto (memoria `project_github_issues.md`) menziona esplicitamente "pool leak" come uno dei 4 issue CRITICAL aperti prima del paper trading. In molti punti (es. API routes) `PostgreSQLStore` viene istanziato via `Depends(get_pg_store)` che fa `yield pg` e chiude, ma nei worker Celery la connessione può non essere restituita correttamente in caso di eccezione o di fork del processo worker.

**Impatto concreto:** Esaurimento del pool (max 20 connessioni), crash o stallo dei worker, perdita di cicli di portfolio, ordini mancati.

**Raccomandazione:**
- Sostituire `psycopg2.pool.ThreadedConnectionPool` con `psycopg2.pool.SimpleConnectionPool` o, meglio, con SQLAlchemy connection pool / asyncpg per tracciamento migliore.
- Aggiungere `getconn()`/`putconn()` sempre in `try/finally` e controllare che `close()` restituisca la connessione al pool.
- Aggiungere metriche/alert sul numero di connessioni aperte.

---

### B8. Assenza di rate limiting e CORS non esplicito

**Severità:** High  
**Area:** sicurezza / backend  
**File:** `src/api/main.py:28-33`, `src/api/auth.py`

**Descrizione:** L'app FastAPI non configura CORS e non implementa rate limiting. Endpoint come `POST /api/admin/killswitch`, `POST /api/admin/mode`, `POST /api/auth/login` sono protetti solo da autenticazione statica o JWT, senza difesa da brute force.

**Impatto concreto:** Attacco brute force su API key o password; DoS via chiamate ripetute ai worker; esposizione accidentale se CORS è lasciato al default.

**Raccomandazione:** Aggiungere `CORSMiddleware` esplicito con origini allowlistate e implementare rate limiting per login, killswitch e mode change (es. `slowapi` con Redis come backend).

---

### B9. `SentimentResult.model_dump_json` sovrascrive il metodo Pydantic in modo fragile

**Severità:** Medium  
**Area:** backend / qualità codice  
**File:** `src/models/signals.py:20-35`

**Descrizione:** La classe ridefinisce `model_dump_json()` con una firma diversa (`def model_dump_json(self) -> str`) rispetto al metodo Pydantic v2 (`model_dump_json(self, *, indent=None, include=None, exclude=None, ...)`). Il `type: ignore[override]` lo conferma. Se altro codice chiama `result.model_dump_json(exclude=...)` o `round_trip=True`, fallisce.

**Impatto concreto:** Incompatibilità con Pydantic v2; bug silenziosi se il metodo viene chiamato con argomenti.

**Raccomandazione:** Usare `model_config = ConfigDict(json_encoders={datetime: ...})` o una `field_serializer` per `generated_at`, oppure implementare `model_dump_json` con la firma corretta di Pydantic v2 e delegare alla serializzazione custom solo quando necessario.

---

### B10. Edge case numerici non gestiti in S1 signal e option pricing

**Severità:** Medium  
**Area:** backend / qualità codice / test  
**File:** `src/strategies/s1/signal.py:62-66`, `src/options/pricing.py:35-47`, `src/options/pricing.py:160-178`

**Descrizione:**
- In `compute_signal`, `vol_norm = lb_ret / rolling_vol` non controlla esplicitamente vol=0 o vol≈0; il `nan_mask` cattura NaN ma non Infiniti.
- In `black_scholes_price`, per `T <= 0` restituisce payoff intrinseco, ma non gestisce `sigma <= 0` per `T > 0`.
- `implied_vol` ha una fallback bisection con 100 iterazioni e un test di tolleranza finale `tol * 1000` che potrebbe restituire vol con precisione bassa.

**Impatto concreto:** Segnali NaN/Inf propagati nel portfolio; prezzi opzione non validi; convergenza numerica non garantita.

**Raccomandazione:** Aggiungere guardie esplicite per volatilità zero/sigma non positivo e test unitari per questi edge case.

---

### B11. File spuri e dead code

**Severità:** Low  
**Area:** devops / qualità codice  
**File:** `/home/stefano/Documents/Projects/Alembic/=0.11`

**Descrizione:** Esiste un file vuoto chiamato `=0.11` nella root del repository, probabilmente generato da un comando shell errato. Non è in `.gitignore` e non ha alcuna funzione.

**Impatto concreto:** Confusione per i developer, rumore nel repository.

**Raccomandazione:** Rimuoverlo e aggiungere un check CI per file con nomi strani.

---

### B12. Tests: alcuni test sembrano superficiali o legati all'implementazione

**Severità:** Medium  
**Area:** test  
**File:** `tests/workers/test_p2_05_execution_edge_cases.py`, vari test gate

**Descrizione:**
- Alcuni test verificano solo che una funzione ritorni `None` su Redis error, ma non verificano l'intero flusso del portfolio cycle con Redis mockato.
- I gate di backtest hanno threshold molto bassi (`min_sharpe=0.0`, `min_oos_sharpe=0.0`), quindi i test passano quasi tautologicamente. Questo è un problema di business/validazione, non di codice.

**Impatto concreto:** Fiducia eccessiva nella robustezza; regressioni sottili potrebbero non essere catturate.

**Raccomandazione:** Aggiungere integration test end-to-end per il portfolio cycle con Redis mockato, Alpaca mockato e DB di test. Alzare i threshold dei gate solo dopo evidenza statistica, ma documentare chiaramente che sono conservativi.

---

### B13. Drawdown cap incoerente: 10% docs vs 5% config vs 10% hardcoded scheduler

**Severità:** High  
**Area:** documentazione / backend / esecuzione  
**File:** `README.md` (Phase 4 Known Limitations), `docs/operations.md` (Monitoring Alerts), `config/trading.yaml` (`risk.portfolio_drawdown: 0.05`), `src/workers/portfolio_scheduler.py` (`_MAX_DRAWDOWN_PCT = 0.10`), `src/workers/execution.py` (`_load_risk_params`)

**Descrizione:** README e operations.md dicono che il daily loss cap è 10%. `config/trading.yaml` lo fissa a 5%. Il vecchio `ExecutionWorker` legge il valore di config (5%), mentre il percorso attivo `portfolio_scheduler` hard-coda 10% e non legge `trading.yaml`. Quindi i due path di order submission usano cap diversi.

**Impatto concreto:** Cap non uniforme; rischio di superare il 5% nel path attivo mentre la documentazione e il legacy path credono che il limite sia più basso (o viceversa). Incoerenza pericolosa per il risk management.

**Raccomandazione:** Centralizzare il drawdown cap in un'unica chiave di config, leggerla in entrambi i worker, e aggiornare i documenti al valore unico scelto.

---

### B14. Max portfolio exposure: documentato 95%, config 50%

**Severità:** High  
**Area:** documentazione / backend / risk  
**File:** `docs/strategies.md` (Constraint Enforcement table), `docs/ARCHITECTURE.md` §2.4, `config/trading.yaml` (`risk.max_portfolio_exposure: 0.50`), `src/workers/portfolio_scheduler.py` (`_load_risk_config`)

**Descrizione:** I documenti strategici descrivono un'esposizione massima del 95% del NAV. Invece `config/trading.yaml` e il risk config loader dello scheduler usano 50%.

**Impatto concreto:** Il deploy reale è molto più conservativo di quanto documentato. Una strategia progettata per usare fino al 95% di esposizione colpisce un cap del 50% silenziosamente, con risultati di backtest/paper non allineati alle aspettative.

**Raccomandazione:** Scegliere il cap di produzione intenzionale e allineare config e documentazione; se 50% è deliberato, correggere le tabelle di riferimento strategico.

---

### B15. Ensemble LLM attuale (Kimi + GLM-5.2) non allineato con README e regime detection

**Severità:** High  
**Area:** documentazione / backend / integrazione  
**File:** `README.md` (Tech Stack, Phase 2), `docs/strategies.md` (S4 LLM Ensemble), `src/llm/model_registry.py` (`_MODELS`), `config/workers.yaml` (`regime.llm_model_2: qwen3.5:cloud`), `src/config.py` (`REGIME_LLM_MODEL_2` default), `src/workers/regime.py` (`_make_llm_client` registry)

**Descrizione:** Il sentiment pipeline attivo usa `kimi-k2.6:cloud` + `glm-5.2:cloud`. README dice ancora Kimi + Qwen3.5; strategies.md dice che Qwen è stato sostituito da GLM-5.2 ma non aggiorna README. La regime detection è configurata per usare `qwen3.5:cloud` come secondo modello, e `src/workers/regime.py` non include nemmeno `glm-5.2:cloud` nel suo client registry, quindi cambiare la config a GLM-5.2 per regime farebbe crashare il task.

**Impatto concreto:** Documentazione fuorviante sui modelli attivi e costi. Incoerenza operativa tra sentiment e regime; risk di crash del regime detector se si tenta di allineare i modelli.

**Raccomandazione:** Aggiornare README e strategies.md a Kimi + GLM-5.2 per sentiment; decidere se anche regime deve passare a GLM-5.2 (e aggiungerlo al registry di `regime.py`) o documentare esplicitamente che regime usa ancora Qwen3.5.

---

### B16. Execution engine di default è `portfolio`, ma README descrive il legacy `ExecutionWorker`

**Severità:** High  
**Area:** documentazione / architettura  
**File:** `README.md` (Phase 4 Execution Engine), `config/trading.yaml` (`execution.engine: portfolio`), `src/workers/portfolio_scheduler.py` (`_load_execution_engine`), `src/workers/execution.py` (`_load_execution_engine`)

**Descrizione:** README mostra il flusso legacy per-symbol con gating `score > 0.3` e `price > EMA20` nell'`ExecutionWorker`. In realtà `execution.engine` di default è `portfolio`, quindi `run-execution` esce subito e solo `portfolio-cycle` invia ordini tramite `PortfolioOrchestrator`.

**Impatto concreto:** Nuovi lettori/operatori fraintendono come vengono generati gli ordini e quali gate di sicurezza si applicano.

**Raccomandazione:** Riscrittura di README Phase 4 per descrivere il percorso attivo `PortfolioOrchestrator`, segnando chiaramente il legacy sentiment path come inattivo di default.

---

### B17. S7 PEAD: documentazione dice 15% allocation, config 0%

**Severità:** Medium  
**Area:** documentazione / backend  
**File:** `docs/strategies.md` (S7 header), `docs/ARCHITECTURE.md` §2.5, `config/strategies.yaml` (S7 block)

**Descrizione:** I documenti dicono che S7 ha `allocation_pct: 0.15` in config ma non è wired nell'orchestratore. Il `config/strategies.yaml` reale ha `enabled: false`, `allocation_pct: 0.00`, `mode: research`.

**Impatto concreto:** Operatori potrebbero credere che il 15% del capitale sia destinato a PEAD; in realtà è allocato 0%.

**Raccomandazione:** Allineare i documenti con `config/strategies.yaml`, oppure — se 15% è l'allocazione di ricerca intenzionale — aggiornare la config.

---

### B18. S4 stop-loss: documentato 5%, config 2%

**Severità:** Medium  
**Area:** documentazione / backend  
**File:** `docs/strategies.md` (S4 Key Parameters), `config/trading.yaml` (`risk.stop_loss: 0.02`), `src/workers/portfolio_scheduler.py` (`_load_risk_config`)

**Descrizione:** La tabella parametri S4 elenca `stop_loss_pct: 0.05`. Il risk config live carica `stop_loss: 0.02` da `trading.yaml`.

**Impatto concreto:** Posizioni reali vengono stopate prima di quanto la documentazione strategica implichi.

**Raccomandazione:** Aggiornare la tabella S4 a 2% o cambiare la config se 5% è il valore di produzione voluto.

---

### B19. `/api/system/scheduler` restituisce schedule non allineato al Celery beat reale

**Severità:** Medium  
**Area:** backend / operator surface  
**File:** `src/api/routes/system_routes.py` (`_SCHEDULE`), `src/workers/celery_app.py` (`beat_schedule`)

**Descrizione:** L'endpoint restituisce cron obsoli/errati per diversi task: `rss-ingestion` dichiarato `*/30 * * * *` ma reale `*/15 14-21 * * 1-5`; `sec-edgar-ingestion` dichiarato ogni ora ma commentato nel beat; `risk-monitor` dichiarato `*/30 14-21` ma gira alle 22:30 giornaliera; `counterfactual-worker` dichiarato Mon-Fri 22:45 ma gira daily; mancano `forward-return-worker`, `reconcile-fills-intraday`, `loss-feedback-check`, `regime-detector-premarket`.

**Impatto concreto:** La cockpit surface dà una visione imprecisa di quando i task girano, complicando il debugging operativo.

**Raccomandazione:** Generare `_SCHEDULE` dalla stessa fonte del beat schedule o mantenerlo sincronizzato manualmente con un test che fallisce se diverge.

---

### B20. `reconcile-fills-evening` beat task punta alla funzione sbagliata

**Severità:** Medium  
**Area:** backend / operazioni  
**File:** `src/workers/celery_app.py` (lines 80–84), `docs/operations.md` (Celery Beat Schedule)

**Descrizione:** L'entry beat `reconcile-fills-evening` ha `"task": "src.workers.performance.run_daily_report"`. La funzione corretta per la reconciliazione serale non viene chiamata; invece il daily report viene rilanciato alle 21:30.

**Impatto concreto:** La reconciliazione EOD dei fill è assente; fill serali potrebbero non essere riconciliati fino al daily report successivo.

**Raccomandazione:** Correggere l'entry per puntare alla funzione di reconciliazione serale corretta (es. `src.workers.performance.run_reconcile_fills_evening` se esiste, altrimenti crearla).

---

### B21. Portfolio cycle gira ogni 15 minuti, documentato come hourly

**Severità:** Medium  
**Area:** documentazione / operazioni  
**File:** `README.md` (Celery Beat Schedule, Phase G), `docs/operations.md`, `src/workers/celery_app.py` (`portfolio-cycle` schedule `7,22,37,52`)

**Descrizione:** I documenti descrivono il portfolio cycle come orario. Il beat schedule reale esegue a `:07, :22, :37, :52` durante gli orari di mercato (~ogni 15 minuti, sfasato rispetto al sentiment).

**Impatto concreto:** Operatori potrebbero sottostimare la frequenza del cycle e la frequenza attesa degli ordini.

**Raccomandazione:** Aggiornare tutte le tabelle beat schedule alla cadenza 15-minuti e spiegare l'offset.

---

### B22. Decay monitor gira daily alle 21:00 UTC, documentato monthly

**Severità:** Medium  
**Area:** documentazione / operazioni  
**File:** `README.md`, `docs/operations.md`, `docs/ARCHITECTURE.md` §6, `src/workers/celery_app.py` (`decay-monitor`)

**Descrizione:** I documenti dicono che `decay-monitor` gira monthly il 1° alle 23:00. Lo schedule reale è daily alle 21:00 UTC con un commento che indica "paper-trading temporary setting".

**Impatto concreto:** Operatori non si aspettano report giornalieri di decay; la documentazione non riflette la modifica temporanea intenzionale.

**Raccomandazione:** Aggiornare i documenti per riflettere lo schedule giornaliero durante la validazione paper e il piano di ritorno a monthly.

---

### B23. Runbook kill-switch punta a endpoint inesistente

**Severità:** Medium  
**Area:** documentazione / operazioni  
**File:** `docs/operations.md` (Runbook: Kill-Switch Active), `src/api/routes/admin.py`

**Descrizione:** `docs/operations.md` dice di usare `POST /api/admin/killswitch/recover` con OTP. Il flusso reale è `POST /api/admin/killswitch/recovery-token` seguito da `DELETE /api/admin/killswitch?confirm_token=...`.

**Impatto concreto:** Un operatore che segue il runbook letteralmente ottiene 404.

**Raccomandazione:** Aggiornare il runbook al flusso recovery-token + DELETE corretto.

---

### B24. `FRONTEND_OPERATOR_GUIDE.md` suggerisce `redis-cli DEL killswitch_active`, in contraddizione con il runbook

**Severità:** Medium  
**Area:** documentazione / sicurezza  
**File:** `docs/FRONTEND_OPERATOR_GUIDE.md` §3.2, `docs/operations.md` (Kill-Switch Runbook)

**Descrizione:** Il frontend guide mostra `redis-cli DEL killswitch_active` come metodo accettabile per disattivare manualmente. Il runbook delle operazioni dice esplicitamente di non cancellare via `redis-cli` senza il flusso API OTP.

**Impatto concreto:** Operatori possono bypassare audit trail e cooldown.

**Raccomandazione:** Rimuovere l'esempio di `DEL` manuale dal frontend guide.

---

### B25. SENTIMENT_REVERSAL_EXIT_THRESHOLD override a -0.35 in docker-compose senza documentazione

**Severità:** Low  
**Area:** devops / documentazione  
**File:** `docker-compose.yml` (worker / worker-inference env), `src/config.py` (default `-0.20`)

**Descrizione:** `src/config.py` defaulta il reversal threshold a `-0.20`; `docker-compose.yml` lo imposta a `-0.35` per entrambi i worker senza alcuna documentazione.

**Impatto concreto:** Comportamento diverso tra dev bare-metal e Docker deploy.

**Raccomandazione:** Documentare l'override in `docs/operations.md` o spostarlo in `config/trading.yaml`.

---

### B26. Portfolio cycle Redis lock TTL inferiore alla cadenza beat

**Severità:** Critical  
**Area:** backend / esecuzione / concorrenza  
**File:** `src/workers/portfolio_scheduler.py:657-664`, `780-789`, `799-809`  
**✅ FIX APPLICATO 2026-07-02** — TTL portato da 840s a 1200s (20 min). Lock ora usa UUID come valore; il `finally` cancella tramite script Lua atomico che verifica il token — non può cancellare il lock di un ciclo concorrente.

**Descrizione:** Il lock Redis del ciclo portfolio ha TTL di 840 secondi (14 minuti) mentre il Celery beat lo schedula ogni 15 minuti. Se un ciclo dura più di 14 minuti, il lock scade prima che il task finisca; il `finally` cancella poi la chiave, potenzialmente rimuovendo il lock di un secondo ciclo appena iniziato.

**Impatto concreto:** Due cicli portfolio possono sovrapporsi, leggere le stesse posizioni Alpaca e inviare ordini duplicati o conflittuali.

**Raccomandazione:** Impostare TTL a almeno un intero intervallo di schedule più margine (es. 1200 s), memorizzare un token univoco nel valore del lock e fare in modo che `finally` cancelli solo il lock di proprietà di questo task.

---

### B27. S4 signal idempotency marcata prima della conferma broker

**Severità:** High  
**Area:** backend / esecuzione  
**File:** `src/workers/portfolio_scheduler.py:1299-1328`, `1364-1428`  
**✅ FIX APPLICATO 2026-07-02** — `_mark_signal_fired` rimosso dal loop decision logging. I signal_id S4 vengono ora raccolti in `_pending_s4_fires` e marcati fired solo dopo che `_submit_portfolio_orders` li conferma tramite `_submitted_buy_symbols`.

**Descrizione:** `_mark_signal_fired()` viene chiamato durante il decision logging, prima di `_submit_portfolio_orders()`. Se la sottomissione viene saltata (dry-run, halted, broker reject, kill-switch re-check, validazione quantità/fractionable), il segnale risulta comunque registrato come fired.

**Impatto concreto:** Un segnale BUY S4 valido può essere "consumato" senza mai arrivare ad Alpaca; la posizione è persa per la sessione.

**Raccomandazione:** Spostare `_mark_signal_fired()` a dopo il ritorno di `submit_order()` con un `order_id` confermato, e solo per ordini S4 BUY effettivamente sottomessi.

---

### B28. Righe trade DB scritte dopo la sottomissione Alpaca (orphan orders)

**Severità:** High  
**Area:** backend / esecuzione / integrità dati  
**File:** `src/workers/portfolio_scheduler.py:1474-1615`  
**✅ FIX APPLICATO 2026-07-02** — I trade BUY vengono ora scritti in DB immediatamente dopo `_submit_portfolio_orders`, tramite blocco `_buy_orders_to_write`. Il batch finale skippa i BUY già scritti (`_written_buy_order_ids`) ma mantiene il backfill del `decision_order_id`. SELL e stop-loss restano nel batch (rischio orphan basso per i SELLs).

**Descrizione:** `trading_client.submit_order()` viene eseguito prima della scrittura di `open_trade()` / `record_trade_exit()`. Se la scrittura DB fallisce, Alpaca detiene la posizione ma Alembic non ha la corrispondente riga `trades`.

**Impatto concreto:** Il guard anti-pyramiding del ciclo successivo non vede la posizione e può ri-acquistare lo stesso ticker.

**Raccomandazione:** Persistere la riga decision/trade in stato pending *prima* della sottomissione, poi aggiornare `order_id` dopo la conferma Alpaca.

---

### B29. Legacy execution worker invia bracket orders con quantità frazionarie

**Severità:** High  
**Area:** backend / esecuzione / Alpaca  
**File:** `src/workers/execution.py:721-730`

**Descrizione:** `qty = round(notional / price, 4)` viene passato a `MarketOrderRequest` con `OrderClass.OTO` e `StopLossRequest`. Il portfolio scheduler ha già imparato che Alpaca rifiuta le gambe bracket su ordini frazionari/notionali.

**Impatto concreto:** Con `execution.engine=legacy_sentiment`, gli ordini BUY per simboli fractionable possono essere rifiutati da Alpaca pur essendo considerati consumati dal sistema, lasciando posizioni senza protezione.

**Raccomandazione:** Riutilizzare il lookup fractionable-symbol e il fallback a interi condivisi da `_submit_portfolio_orders()`, oppure disabilitare il legacy engine in produzione.

---

### B30. Kill-switch / mode check non atomico rispetto alla sottomissione ordini

**Severità:** High  
**Area:** backend / esecuzione / sicurezza  
**File:** `src/workers/portfolio_scheduler.py:835-856`, `1445-1479`

**Descrizione:** Il ciclo controlla il kill-switch all'inizio, poi dopo una lunga sequenza (fetch dati, orchestratore, decision logging) apre una nuova connessione Redis per un check finale `_is_ks_active_failclosed()` prima della sottomissione.

**Impatto concreto:** Time-of-check/time-of-use race: un halt o un kill-switch per drawdown può attivarsi dopo il check finale ma prima che gli ordini market siano in volo.

**Raccomandazione:** Minimizzare il gap tra il check finale del kill-switch e la sottomissione; trattare il check come parte del loop di sottomissione e abortire immediatamente su qualsiasi failure Redis/KS.

---

### B31. `LLMBudgetTracker.check_budget` mantiene un row lock senza chiudere la transazione

**Severità:** High  
**Area:** backend / worker / PostgreSQL  
**File:** `src/llm/budget.py:110-142`

**Descrizione:** `SELECT ... FOR UPDATE` su `llm_budget` viene eseguito senza `commit()` o `rollback()`; la connessione torna al pool tenendo il lock.

**Impatto concreto:** Altri worker si bloccano sulla stessa riga; esaurimento del pool; la connessione può essere riutilizzata mentre tiene ancora il lock.

**Raccomandazione:** Aggiungere `conn.commit()` (o `rollback()`) prima di ritornare, oppure usare una singola connessione/transaction per `check_budget` → inference → `record_spending`.

---

### B32. Dimensionamento pool DB e rischio esaurimento connessioni PostgreSQL

**Severità:** High  
**Area:** backend / worker / PostgreSQL  
**File:** `src/store/pg_store.py:28-42`, `117-126`

**Descrizione:** `ThreadedConnectionPool(maxconn=20)` viene creato per ogni processo Python; ogni worker process (inference queue, default queue, news_stream, beat, FastAPI) ha il proprio pool. Il fallback crea connessioni dirette quando il pool è esaurito.

**Impatto concreto:** Il numero totale di connessioni può superare il `max_connections` di default di PostgreSQL (100), causando `OperationalError` o stalli.

**Raccomandazione:** Documentare un connection budget, ridurre `maxconn` in base alla concurrency, abilitare limiti di overflow, considerare PgBouncer in produzione.

---

### B33. Limiti di tempo Celery possono killare task Ollama pesanti

**Severità:** High  
**Area:** backend / worker / Celery  
**File:** `src/workers/celery_app.py:53-54`

**Descrizione:** `task_time_limit=660` s e `task_soft_time_limit=600` s globali. `detect_regime` e `run_pead_ingestion_worker` chiamano Ollama LLM e possono superare il limite hard.

**Impatto concreto:** Task regime killed lascia `regime:current` stale; lo scheduler usa fallback conservativo ×0.2 senza alert. Task PEAD killed lascia 8-K filings non processati.

**Raccomandazione:** Sovrascrivere i limiti per i task Ollama, o impostare un limite globale sufficiente per il percorso di inferenza più lento.

---

### B34. Solo il task sentiment usa `acks_late`

**Severità:** High  
**Area:** backend / worker / Celery  
**File:** `src/workers/celery_app.py:45-55`, `src/workers/sentiment.py:377`

**Descrizione:** `task_acks_late=True` è impostato solo su `run_sentiment_worker`. Regime, PEAD, decay monitor, risk monitor, retention e performance task fanno ack on receipt.

**Impatto concreto:** Se un worker viene killato durante uno di questi task, i task sono persi e non riprovati; Redis/DB possono rimanere half-updated.

**Raccomandazione:** Impostare `task_acks_late=True` e `task_reject_on_worker_lost=True` globalmente per tutti i task long-running o stateful.

---

### B35. News stream enqueua un task sentiment per ogni articolo WebSocket

**Severità:** Medium  
**Area:** backend / worker / news  
**File:** `src/workers/news_stream.py:65`

**Descrizione:** Ogni articolo news in arrivo da Alpaca chiama `run_sentiment_worker.delay()`. Il worker schedulato gira già ogni 15 minuti e processa al massimo 4 articoli freschi.

**Impatto concreto:** Un burst di news può accodare centinaia di task ridondanti, inondando il broker e la coda inference.

**Raccomandazione:** Debounce del trigger (es. un `apply_async(countdown=30)` ogni N secondi) e lasciare che lo worker schedulato svuoti la coda.

---

### B36. Stop-loss cooldown fetch dentro il loop per-ordine

**Severità:** Medium  
**Area:** backend / esecuzione / Redis  
**File:** `src/workers/portfolio_scheduler.py:2005-2013`

**Descrizione:** `_get_stop_loss_cooldown_symbols()` apre una nuova connessione Redis e scansiona chiavi per ogni ordine BUY.

**Impatto concreto:** N round-trip per ciclo; il set di cooldown può cambiare tra gli ordini; un errore transitorio Redis blocca silenziosamente un singolo BUY.

**Raccomandazione:** Recuperare il set di cooldown una sola volta per ciclo prima della sottomissione.

---

### B37. Sentiment batch processing effettivamente seriale

**Severità:** Medium  
**Area:** backend / worker / sentiment  
**File:** `src/workers/sentiment.py:299-315`

**Descrizione:** `process_news_batch` usa `asyncio.Semaphore(1)` con `asyncio.gather`, quindi i 4 articoli per run vengono processati uno alla volta.

**Impatto concreto:** Collo di bottiglia nella pipeline; news fresche possono invecchiare oltre lo stale cutoff prima di essere processate.

**Raccomandazione:** Aumentare batch size/concurrency e proteggere il singleton FinBERT con un lock, oppure allineare il volume di ingestion al throughput dimostrato.

---

### B38. Broad exception swallowing nasconde failure in produzione

**Severità:** Medium  
**Area:** backend / worker / robustezza  
**File:** `src/workers/execution.py:268-281`, `src/workers/portfolio_scheduler.py:1047-1048`, `src/workers/sentiment.py:268-270` (esempi)

**Descrizione:** Molte funzioni worker catturano `Exception` e loggano solo warning/debug, proseguendo.

**Impatto concreto:** Outage Redis, degradazione broker o failure del notifier diventano silenziose mentre il sistema smette di tradare/alertare.

**Raccomandazione:** Distinguere errori transitori da fatali; emettere log/metriche CRITICAL per failure infrastrutturali.

---

### B39. Redis read-modify-write non atomici

**Severità:** Medium  
**Area:** backend / store / Redis  
**File:** `src/store/redis_store.py:105-112`, `252-271`, `338-368`

**Descrizione:** `append_signal_history`, `increment_fallback_counter` e `log_divergence` eseguono comandi multipli Redis senza pipeline/Lua.

**Impatto concreto:** Un crash tra comandi può lasciare chiavi senza TTL, troncare liste in modo errato, o triggerare alert fallback duplicati.

**Raccomandazione:** Avvolgere le sequenze RMW in `pipeline().execute()` o usare script Lua.

---

### B40. `RedisStore.get_mode()` ritorna `bytes` invece di `str`

**Severità:** Medium  
**Area:** backend / store / Redis  
**File:** `src/store/redis_store.py:640-642`

**Descrizione:** Il client Redis interno è creato senza `decode_responses=True`, quindi `get_mode()` ritorna `bytes`.

**Impatto concreto:** Endpoint admin che confrontano la mode con string literals si comportano in modo errato.

**Raccomandazione:** Decodificare in `get_mode()` o inizializzare lo store client con `decode_responses=True`.

---

### B41. `workers.yaml` non viene caricato; impostazioni duplicate e a rischio drift

**Severità:** Medium  
**Area:** backend / config  
**File:** `config/workers.yaml` vs `src/config.py:161-218`

**Descrizione:** `config/workers.yaml` contiene soglie non lette dall'applicazione; i worker usano `src/config.py` invece.

**Impatto concreto:** Operatori che modificano `workers.yaml` si aspettano che le modifiche abbiano effetto, ma il sistema live le ignora.

**Raccomandazione:** Fare in modo che `src/config.py` carichi `workers.yaml` come fonte di verità, oppure rimuovere il file.

---

### B42. Molte costanti di trading sono hardcoded e ignorano `config/trading.yaml`

**Severità:** Medium  
**Area:** backend / worker / config  
**File:** `src/workers/execution.py:53-57`, `src/workers/portfolio_scheduler.py:663-664`, `1958-2059`

**Descrizione:** `execution.py` hardcoded `ENTRY_THRESHOLD`, `MAX_CYCLE_NOTIONAL_PCT`, `EMA_PERIOD`; `portfolio_scheduler.py` hardcoded `_MIN_ORDER_NOTIONAL=100.0` e `_HOLD_MINIMUM_MINUTES=90` nonostante esistano impostazioni YAML.

**Impatto concreto:** Il tuning operativo richiede modifiche al codice e redeploy.

**Raccomandazione:** Caricare tutte le costanti di esecuzione da `config/trading.yaml` con default sicuri, e loggare i valori effettivi all'avvio.

---

### B43. Engine di default diverso tra legacy e portfolio path

**Severità:** Medium  
**Area:** backend / worker / config  
**File:** `src/workers/execution.py:60-69`, `src/workers/portfolio_scheduler.py:317-326`

**Descrizione:** Se `trading.yaml` non può essere letto, `execution.py` defaulta a `legacy_sentiment` mentre `portfolio_scheduler.py` defaulta a `portfolio`.

**Impatto concreto:** Problemi di parsing/permessi YAML possono abilitare silenziosamente il motore sbagliato.

**Raccomandazione:** Usare un singolo helper in `src/config.py` con un unico default.

---

### B44. Stop-loss sintetico dipende dallo snapshot prezzi del ciclo

**Severità:** Medium  
**Area:** backend / esecuzione / risk  
**File:** `src/workers/portfolio_scheduler.py:1093-1101`, `1481-1502`, `1954-2060`

**Descrizione:** Le violazioni stop-loss sono rilevate dallo snapshot `market.prices` del ciclo e sottomesse come market SELL; i BUY frazionabili non hanno stop lato broker.

**Impatto concreto:** Un ciclo mancato, crash o gap-down open lascia posizioni frazionabili senza protezione.

**Raccomandazione:** Allegare stop-loss lato broker dove Alpaca lo supporta, o eseguire un monitor indipendente di stop-loss più stretto.

---

### B45. Telegram poller ricrea l'event loop async dentro un task Celery sincrono

**Severità:** Low  
**Area:** backend / worker / Telegram  
**File:** `src/workers/telegram_poller.py:364-365`

**Descrizione:** Il poller usa un pattern incoerente per eseguire codice async dentro un task Celery sincrono.

**Impatto concreto:** Rischio di loop già running o comportamenti non deterministici.

**Raccomandazione:** Usare `src.workers._async_utils.run_async()` in modo consistente.

---

### B46. `DATABASE_URL.replace("+asyncpg", "")` è fragile

**Severità:** Low  
**Area:** backend / worker / URL parsing  
**File:** `src/workers/execution.py:861`, `src/workers/portfolio_scheduler.py:2181`

**Descrizione:** La conversione manuale dello schema URL per psycopg2 è basata su string replace.

**Impatto concreto:** URL con parametri o schemi diversi potrebbero non essere gestiti correttamente.

**Raccomandazione:** Usare un URL parser appropriato o affidarsi all'URL `postgresql://` già validato.

---

### B47. Nessun runtime paper/live trading guard all'avvio

**Severità:** Low  
**Area:** backend / config / operational safety  
**File:** `src/config.py:122-134`

**Descrizione:** Manca un check all'avvio che logghi e avvisi sulla modalità effettiva (paper/live) e verifichi opzionalmente il dominio della base URL Alpaca.

**Impatto concreto:** Un operatore può non accorgersi che il sistema è in live mode finché non invia ordini reali.

**Raccomandazione:** Aggiungere un guard all'avvio che logghi in modo evidente la modalità e faccia un alert esplicito in live mode.

---

### B48. Risk monitor approssima NAV dalla P&L cumulativa

**Severità:** Low  
**Area:** backend / worker / risk  
**File:** `src/workers/risk_monitor_task.py:83-85`

**Descrizione:** `_fetch_strategy_data` calcola `nav` come somma di `portfolio_daily_state.net_pnl`, che è la P&L netta cumulativa, non il NAV dell'account.

**Impatto concreto:** Drawdown, Sharpe ed esposizione usano il denominatore sbagliato.

**Raccomandazione:** Usare l'equity reale dell'account da Alpaca o una fonte dedicata `portfolio_value`.

---

## C. Mismatch tra codice e documentazione

| # | Documentazione dice | Codice dice | Stato |
|---|----------------------|-------------|-------|
| 1 | `README.md:27`: P2-05 Pending | `docs/P2_STATUS_2026-06-21.md:17`: P2-05 Complete/ACCEPTED; codice implementato | Incoerente |
| 2 | `docs/ARCHITECTURE.md:618`: P2-05 NOT_IMPLEMENTED, blocks audit | Codice implementato e test passano | Incoerente |
| 3 | `src/api/routes/strategies.py:59`: S1 `validated`, Sharpe 0.51, return 7%, DD 15% | `config/strategies.yaml:17`: S1 `supervised_paper`, `promotion_blocked: true` | Incoerente |
| 4 | `docs/P2_STATUS_2026-06-21.md:56`: S2 `paper` | `config/strategies.yaml:29`: S2 `research`, `enabled: false` | Incoerente |
| 5 | `AGENT.md:38`: API key `eJvMeuHhJS27FPugKIu4qKGgV7roIdLfcv7h20MwuQg` | `.env.example:6`: usa una key diversa da 32 char | Potenziale leak/stale doc |
| 6 | `AGENT.md:26`: modalità `full_auto`/`semi_auto` descritte come live | `src/strategies/promotion.py:27`: `GLOBAL_LIVE_PROMOTION_ENABLED=False`; live non autorizzato | Incoerente con autorizzazione |
| 7 | `CONTRIBUTING.md:43`: "1700+ tests" | 2386 tests passano | Stale |
| 8 | `src/config.py:131`: "never derive mode from ALPACA_BASE_URL" | `src/api/deps.py:51`: `paper=config.ALPACA_BASE_URL.startswith("https://paper")` | Contraddizione diretta |
| 9 | `docs/strategies.md:27`: S1 `supervised_paper` | `src/api/routes/strategies.py:59`: S1 `validated` | Incoerente |
| 10 | `docker-compose.yml:30`: API su port 8000, mappato su 8001 | `AGENT.md:32`: Base URL `http://localhost:8001` | Coerente, ma da notare che Vite dev proxy è su 8001 |
| 11 | README/operations: drawdown cap 10% | `config/trading.yaml`: 0.05; scheduler hardcoded 0.10 | Incoerente (B13) |
| 12 | `docs/strategies.md`: max exposure 95% | `config/trading.yaml`: 0.50 | Incoerente (B14) |
| 13 | README: ensemble Kimi + Qwen3.5 | Codice: sentiment Kimi + GLM-5.2; regime usa Qwen3.5 | Incoerente (B15) |
| 14 | README Phase 4: legacy ExecutionWorker | `config/trading.yaml`: `execution.engine: portfolio` | Incoerente (B16) |
| 15 | `docs/strategies.md`: S7 allocation 15% | `config/strategies.yaml`: S7 0% disabled | Incoerente (B17) |
| 16 | `docs/strategies.md`: S4 stop-loss 5% | `config/trading.yaml`: 0.02 | Incoerente (B18) |
| 17 | `src/api/routes/system_routes.py`: scheduler table | `src/workers/celery_app.py`: beat schedule reale | Stale (B19) |
| 18 | `reconcile-fills-evening` beat task | Mappa a `run_daily_report` invece della funzione serale | Bug (B20) |
| 19 | README/operations: portfolio cycle hourly | Beat: ogni 15 min | Incoerente (B21) |
| 20 | README/operations: decay monitor monthly | Beat: daily 21:00 UTC | Incoerente (B22) |
| 21 | `docs/operations.md`: `POST /api/admin/killswitch/recover` | API reale: `/recovery-token` + `DELETE` | Endpoint inesistente (B23) |
| 22 | `docs/FRONTEND_OPERATOR_GUIDE.md`: `redis-cli DEL killswitch_active` | Runbook: non usare `redis-cli` | Contraddizione (B24) |
| 23 | `src/config.py`: reversal threshold default -0.20 | `docker-compose.yml`: override -0.35 | Override non documentato (B25) |
| 24 | `CONTRIBUTING.md`: 1700+ tests | 2386 tests passano | Stale |
| 25 | `AGENT.md`: API key esempio | Potenziale secret leak | Stale/rischio |
| 26 | `docs/ARCHITECTURE.md`: known gaps (vol targeting, trades table) | Codice: implementato | Stale |
| 27 | `README.md`: `docker-compose up -d` | Moderno: `docker compose up -d` | Stale |
| 28 | `docs/strategies.md` vs `config/strategies.yaml`: S1 demotion date | 2026-06-18 vs 2026-06-19 | Incoerente |

---

## D. Problemi probabilmente introdotti dalla generazione AI

### D1. Duplicazione di type e logica

- `Mode` type è definita sia in `frontend/src/store/index.ts` che in `frontend/src/pages/Admin.tsx` — classico pattern di copia-incolla AI.
- Molte pagine frontend condividono stili inline ripetuti anziché usare componenti/CSS condivisi.

### D2. Codice plausibile ma fragile

- `src/api/routes/admin.py:210-212` (kill-switch resume to paper) è logicamente plausibile ma non considera lo stato precedente.
- `src/api/deps.py:51` è un one-liner che sembra ragionevole ma viola la policy dichiarata.
- `src/models/signals.py:20-35` sovrascrive un metodo Pydantic con una firma semplificata — plausibile, ma rompe la compatibilità.

### D3. Hardcoded path e valori

- `src/api/routes/trading.py:104` hardcoded `/app/config/trading.yaml`.
- `src/api/routes/admin.py:212` hardcoded `"paper"`.
- `frontend/src/App.tsx:24` hardcoded retry policy senza considerare 429/500.
- `src/workers/portfolio_scheduler.py:663-664` hardcoded `_MIN_ORDER_NOTIONAL=100.0`.
- `src/workers/execution.py:53-57` hardcoded `ENTRY_THRESHOLD`, `MAX_CYCLE_NOTIONAL_PCT`, `EMA_PERIOD`.

### D4. Test superficiali / generati per far passare la CI

- Il frontend ha un solo file di test; i test sono "safety hygiene" piuttosto che copertura funzionale reale.
- Alcuni test backend verificano solo la presenza/assenza di stringhe nei file sorgente (es. `expect(src).not.toContain('/promote')`), non il comportamento runtime.

### D5. Commenti/commenti inutili

- Commenti tipo `# FIX: Use parameterized query...` in `src/store/pg_store.py:51-54` indicano codice vecchio trasformato, non necessari nella versione finale.
- `AGENT.md` contiene copy promozionale non allineata alla realtà operativa.

---

## E. Refactor Consigliati

### Immediato (prima di qualsiasi merge/release)

1. **Allineare documentazione e API surface strategie** (B1)
   - File: `README.md`, `docs/ARCHITECTURE.md`, `src/api/routes/strategies.py`, `docs/P2_STATUS_2026-06-21.md`.
2. **Sicurezza: JWT e paper/live mode** (B2)
   - Rimuovere fallback chiave JWT, usare solo `ALPACA_PAPER_MODE`, aggiungere rate limiting/CORS.
3. **Fix kill-switch resume** (B3)
   - Salvare/ripristinare mode precedente.
4. **Rimuovere path hardcoded** (B4)
   - Centralizzare risoluzione config path.
5. **Frontend: XSS, token storage, lint failure, type Mode, test base** (B5, B5b)
   - Sanitizzare testi esterni/LLM con DOMPurify; aggiungere CSP strict in `index.html`.
   - Correggere tutti i lint errors e far fallire CI su lint failure.
   - Spostare/abbassare durata token JWT (valutare `httpOnly` cookie).
   - Estrarre type `Mode` condiviso, aggiungere `dry_run`, aggiungere test per `apiFetch`, `ReadinessBanner`, almeno una pagina.
6. **Allineare i numeri di risk management** (B13, B14, B18, B20)
   - Drawdown cap, max portfolio exposure e S4 stop-loss devono avere un'unica fonte di verità condivisa tra config, codice e documentazione.
   - Correggere `reconcile-fills-evening` perché punti alla funzione di reconciliazione serale corretta.
7. **Allineare documentazione modelli LLM e registry regime** (B15, B16)
   - README e strategies.md devono riflettere Kimi + GLM-5.2 per sentiment.
   - Decidere modello per regime detection e aggiungerlo al registry di `src/workers/regime.py` se necessario.
   - Riscrittura README Phase 4 per descrivere il percorso `portfolio` attivo.
8. **Correggere runbook kill-switch e scheduler endpoint** (B19, B23, B24)
   - Allineare `/api/system/scheduler` con il beat schedule reale o generarlo dinamicamente.
   - Aggiornare `docs/operations.md` al flusso recovery-token + DELETE.
   - Rimuovere l'esempio `redis-cli DEL killswitch_active` dalla frontend guide.

### Breve termine (prima di paper trading)

9. **Fix portfolio scheduler race/ordering** (B26, B27, B28, B30)
    - Aumentare TTL lock Redis a >= 1200 s e tokenizzare il lock value.
    - Spostare `_mark_signal_fired()` dopo conferma Alpaca.
    - Scrivere trade row pending prima di `submit_order()` e aggiornare `order_id` dopo.
    - Ridurre gap tra ultimo check kill-switch e sottomissione; abortire su failure.
10. **Pool PostgreSQL e connection lifecycle** (B7, B32)
    - Audit e refactor della gestione pool, soprattutto nei worker Celery; documentare connection budget.
11. **Aggiungere rate limiting e CORS esplicito** (B8)
12. **Fix `SentimentResult.model_dump_json`** (B9)
13. **Aggiungere edge case test per S1/options** (B10)
14. **Rimuovere dead code e file spuri** (B11)
15. **Refactor componenti frontend monolitici e migliorare UX** (B5b, B6)
    - Spezzare `Performance.tsx`/`Docs.tsx`/`Strategies.tsx`; standardizzare lingua e componenti UI condivisi; ridurre polling aggressivo su `Overview`; gestire stati error/empty/loading.
    - Migliorare `apiFetch` con response handler centralizzato, evitando redirect multipli.
16. **Celery robustness** (B33, B34)
    - `task_acks_late=True` per task long-running/stateful; limiti di tempo adeguati per Ollama.

### Medio termine (backlog)

17. Refactor dello styling frontend da inline a CSS/utility class condivisi.
18. Implementare refresh token e session management più robusto.
19. Estrarre una libreria di tipi/contract condivisi tra frontend e backend (OpenAPI-generated client).
20. Aumentare la coverage dei test di integrazione end-to-end con broker mockato.
21. Aggiungere bundle analyzer e budget per il frontend.
22. Implementare test end-to-end FE/BE con broker e Redis mockati.
23. Centralizzare loading costanti trading da `config/trading.yaml` (B42); unificare default engine (B43).
24. Atomizzare RMW Redis con pipeline/Lua (B39); correggere `RedisStore.get_mode()` (B40).
25. Debounce news stream trigger (B35); fix Telegram poller loop (B45); fix risk monitor NAV (B48).

---

## F. Test Mancanti Prioritari

1. **Frontend:**
   - `apiFetch`: gestione 401/403/429/500, single redirect, JSON parsing error, retry/timeout.
   - `ReadinessBanner`: stati ready/degraded/blocked/closed, refresh ogni 30s.
   - `LoginPage`: submit, errore credenziali, redirect post-login.
   - `Overview`: rendering con dati mock, stati vuoti, errori query, resilienza a dati mancanti.
   - `Admin`: kill-switch activation/deactivation flow completo con recovery token; modalità `dry_run` gestita.
   - `News`/`LLM`/`Signals`/`Labeling`: verificare sanitizzazione contenuti esterni/LLM (DOMPurify) e assenza di `dangerouslySetInnerHTML`.
   - Routing e protezione rotte.
   - Componenti condivisi: `ErrorBoundary`, `DataTable`, `KPICard`.

2. **Backend - sicurezza:**
   - `require_api_key`: JWT valido, JWT scaduto, API key corretta, API key errata, assenza di entrambe.
   - `login`: brute-force throttling (se implementato), password hash corretto.
   - `get_alpaca_trading_client`: verifica che `paper` dipenda solo da `ALPACA_PAPER_MODE`.
   - `deactivate_killswitch`: ripristino mode precedente.

3. **Backend - esecuzione / worker:**
   - Portfolio cycle end-to-end con Redis mockato, DB di test, Alpaca mockato.
   - Idempotency S4 con Redis up/down; verificare che `_mark_signal_fired()` avvenga solo dopo ordine confermato.
   - Constraint enforcer con vol targeter e cap.
   - Broker reject callback.
   - Lock Redis TTL e tokenizzazione (B26); cicli sovrapposti.
   - Trade row pending → submit → update `order_id` (B28); orphan orders.
   - Kill-switch check atomico rispetto a sottomissione (B30).
   - News stream debounce (B35).
   - `LLMBudgetTracker` transaction lifecycle (B31).

4. **Backend - edge case numerici:**
   - `compute_signal` con volatilità zero, prezzi flat, un solo ticker.
   - `black_scholes_price` con T=0, sigma=0.
   - `implied_vol` con prezzi arbitraggio e degenerate input.

5. **Integration FE/BE:**
   - Verificare che ogni endpoint chiamato dal frontend esista e ritorni lo schema atteso.
   - Verificare che i tipi TypeScript del frontend combacino con i modelli Pydantic del backend.
   - Verificare modalità `dry_run` e consistenza dei valori di `Mode` tra FE/BE.
   - Verificare che la CSP e la sanitizzazione frontend non blocchino rendering legittimo di reasoning LLM.
6. **Worker / Store / Celery:**
   - Lock TTL e tokenizzazione; acks late; time limit Ollama; `workers.yaml` load; `get_mode()` returns str.
   - Pool sizing e connection budget; `LLMBudgetTracker` lock release.
   - RMW Redis atomici; news stream debounce; Telegram poller loop consistency.

---

## G. Checklist Finale di Readiness

### Blocca il rilascio (do not release without fix)

- [ ] Allineare README/ARCHITECTURE/P2_STATUS con lo stato reale di P2.
- [ ] Correggere `src/api/routes/strategies.py` per riflettere `mode`/`promotion_blocked` reali e aggiungere warning su metriche stale.
- [ ] Rimuovere/anonimizzare API key in `AGENT.md`.
- [x] **Fix `get_alpaca_trading_client` per usare solo `ALPACA_PAPER_MODE`. ✅ 2026-07-02 (B2)**
- [ ] Rimuovere fallback chiave JWT effimera o rifiutare avvio se `JWT_SECRET_KEY` manca.
- [ ] Fix kill-switch resume per ripristinare il mode precedente.
- [ ] Audit e fix della gestione del pool PostgreSQL (critical issue pre-live).
- [ ] Allineare i numeri di risk management (drawdown cap, max portfolio exposure, S4 stop-loss) in un'unica fonte di verità (config + codice + docs).
- [ ] Correggere `reconcile-fills-evening` beat task per puntare alla funzione serale corretta.
- [ ] Allineare documentazione modelli LLM (README, strategies.md) con il sentiment reale (Kimi + GLM-5.2); allineare registry regime e decidere modello regime.
- [ ] Correggere runbook kill-switch (`docs/operations.md`) al flusso recovery-token + DELETE reale.
- [ ] Correggere `/api/system/scheduler` affinché rifletta il Celery beat schedule attuale.
- [x] **Portfolio scheduler: fix TTL lock Redis 840s→1200s e tokenizzare il lock value. ✅ 2026-07-02 (B26)**
- [x] **Portfolio scheduler: spostare `_mark_signal_fired()` dopo conferma Alpaca. ✅ 2026-07-02 (B27)**
- [x] **Portfolio scheduler: scrivere righe trade BUY immediatamente dopo `submit_order()`. ✅ 2026-07-02 (B28)**
- [ ] **LLMBudgetTracker: chiudere transazione `FOR UPDATE` prima di ritornare (B31).**
- [ ] **Celery: impostare `task_acks_late=True` per tutti i task long-running/stateful (B34).**
- [ ] **Frontend: sanitizzare contenuti esterni/LLM con DOMPurify e aggiungere CSP (B5).**
- [ ] **Frontend: correggere lint errors/warnings e far fallire CI su lint failure (B5b).**

### Consigliato sistemare prima del merge

- [ ] Aggiungere CORS esplicito e rate limiting.
- [ ] Centralizzare type `Mode` nel frontend e aggiungere `dry_run` se necessario.
- [ ] Aggiungere almeno 5-10 test frontend significativi.
- [ ] Fix `SentimentResult.model_dump_json` compatibile Pydantic v2.
- [ ] Rimuovere path hardcoded `/app/config/trading.yaml`.
- [ ] Rimuovere file vuoto `=0.11`.
- [ ] Correggere CONTRIBUTING.md test count.
- [ ] Rimuovere esempio `redis-cli DEL killswitch_active` da `docs/FRONTEND_OPERATOR_GUIDE.md`.
- [ ] Documentare override `SENTIMENT_REVERSAL_EXIT_THRESHOLD=-0.35` in `docker-compose.yml` o spostarlo in config.
- [ ] Spostare token JWT da `sessionStorage` a soluzione più sicura o abbreviarne durata.
- [ ] Refactor componenti monolitici frontend e standardizzare lingua/copy.
- [ ] Impostare limiti Celery adeguati per task Ollama (regime/PEAD) (B33).
- [ ] Debounce news stream trigger per evitare storm di task sentiment (B35).
- [ ] Rendere atomici i read-modify-write Redis con pipeline/Lua (B39).
- [ ] Distinguere errori transitori vs fatali e loggare CRITICAL per failure infrastrutturali (B38).
- [ ] Caricare costanti trading da `config/trading.yaml` invece di hardcoded (B42).
- [ ] Unificare il default engine tra legacy e portfolio scheduler (B43).

### Può andare in backlog

- [ ] Refactor styling frontend da inline a design system condiviso.
- [ ] Refresh token / session management avanzato.
- [ ] OpenAPI-generated client per allineamento FE/BE.
- [ ] Aumentare threshold gate backtest dopo evidenza statistica.
- [ ] Metriche e alert sul pool DB.
- [ ] Riscrittura README Phase 4 per descrivere il percorso `PortfolioOrchestrator` attivo.
- [ ] Bundle analyzer e budget per il frontend.
- [ ] Test end-to-end FE/BE con broker e Redis mockati.
- [ ] Correggere `workers.yaml` non caricato o rimuoverlo.
- [ ] Fix `RedisStore.get_mode()` per ritornare `str`.
- [ ] Refactor `DATABASE_URL.replace` fragile in execution/portfolio scheduler.
- [ ] Fix Telegram poller per usare `run_async()` consistente.
- [ ] Correggere risk monitor per usare NAV reale da Alpaca invece di P&L cumulativa.

---

## H. Conclusione

Alembic è un sistema con una buona architettura di base e un imponente sforzo di test, ma presenta un debito documentale, di sicurezza, di allineamento frontend/backend, di coerenza dei parametri di risk, di robustezza worker/Celery e di qualità del frontend che ne impedisce il rilascio con fiducia. La maggior parte dei problemi sono risolvibili con refactor mirati. I rischi più alti sono: (1) documentazione/API surface fuorviante combinata con autorizzazioni di trading, (2) parametri di risk management con valori discordanti tra config, codice e documentazione, (3) XSS e token storage nel frontend, (4) race condition e ordering nel portfolio scheduler (lock TTL, mark-fired, trade row ordering), (5) sicurezza della modalità paper/live e del pool DB, (6) robustezza Celery e gestione transazioni LLM. Prima di qualsiasi esposizione a capitali reali (anche paper) queste classi di problemi devono essere risolte e verificate con test end-to-end.
