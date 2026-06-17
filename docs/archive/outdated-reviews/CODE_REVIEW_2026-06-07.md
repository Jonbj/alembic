# Code Review Completa - Alembic - 2026-06-07

Documento generato dopo le ultime modifiche al progetto, con focus sia funzionale sia di codice.

La review include anche una valutazione esplicita del modello di autenticazione attuale: assenza di login, API key inserita nel frontend e persistenza client-side.

## Scope della review

Sono stati considerati:

- backend FastAPI e route admin/trading/signals/performance/strategies;
- frontend React/Vite e gestione della API key;
- worker di esecuzione legacy e portfolio scheduler;
- orchestrator portfolio, constraints e strategie S1/S4;
- storage PostgreSQL/Redis;
- migration SQL;
- configurazioni `trading.yaml`, `strategies.yaml`, `cost_model.yaml`;
- documentazione tecnica e deployment;
- test disponibili e coerenza test/docs/codice.

Verifiche eseguite:

- `python -m compileall src`: passato.
- `npm run build` in `frontend`: passato.
- `pytest` non eseguibile in questo ambiente per dipendenze mancanti (`fastapi`, `pandas`). Quindi la review e' principalmente statica, con build frontend e compile Python.

## Executive summary

Le ultime modifiche migliorano alcuni punti importanti, in particolare:

- kill switch piu' coerente con GET/POST/DELETE;
- `stop_loss` non piu' hardcoded nel loop principale;
- route strategies ora protette da API key;
- `news_recent` corretto su `fetched_at`;
- alcuni path config resi assoluti;
- prime basi per trade cost breakdown e reportistica cost-aware.

Restano pero' criticita' rilevanti:

- il modello di autenticazione non e' adatto a una dashboard operativa/admin se esposta oltre una macchina locale fidata;
- la superficie Docker espone servizi sensibili;
- il deployment documentato applica solo la migration iniziale, mentre il codice richiede schema fino alla `019`;
- il motore attivo e' `portfolio`, ma molta osservabilita', analytics e feedback leggono ancora tabelle legacy;
- S1/S4 possono bypassare la frequenza di rebalance;
- S4 sembra sottopesata di un fattore 10;
- `close_trade` ha ancora rischi di concorrenza e P&L nullo;
- test e documentazione sono disallineati rispetto all'autenticazione reale.

## Priorita consigliata

| Priorita | Area | Issue |
| --- | --- | --- |
| P0 | Security/Auth | Sostituire API key raw nel frontend con login/sessione o protezione reverse proxy |
| P0 | Security/Deployment | Chiudere porte DB/Redis/Grafana/API e rimuovere default credentials |
| P1 | Deployment/DB | Applicare tutte le migration in modo ordinato e idempotente |
| P1 | Trading/Observability | Allineare portfolio engine con `trades`, `execution_decisions`, analytics e feedback |
| P1 | Portfolio logic | Ripristinare enforcement della frequenza di rebalance |
| P1 | Strategy sizing | Correggere doppia scalatura S4 |
| P2 | Trading storage | Rendere `close_trade` row-safe e non ambiguo |
| P2 | Frontend | Correggere stato UI su 403/errore auth |
| P2 | Tests/Docs | Riallineare documentazione, auth matrix e test |
| P3 | Cleanup | Path relativi residui, Redis close, metriche net-of-costs piu' precise |

---

# Findings dettagliati

## CR-01 - High - Autenticazione fragile: API key raw nel frontend, nessun login reale

### Evidenza

Backend:

- `src/api/auth.py`
  - usa `APIKeyHeader(name="X-API-Key")`;
  - confronta il valore ricevuto con `settings.ADMIN_API_KEY`;
  - restituisce `403` su chiave assente o invalida.
- `src/config.py`
  - `ADMIN_API_KEY` e' una singola chiave globale;
  - validator richiede almeno 32 caratteri.

Frontend:

- `frontend/src/store/index.ts`
  - persiste `apiKey` nello store Zustand;
  - usa `sessionStorage`.
- `frontend/src/api/client.ts`
  - legge `apiKey` dallo store;
  - la invia in header `X-API-Key`.
- `frontend/src/components/layout/ApiKeyModal.tsx`
  - input password per inserire la chiave;
  - salva la chiave lato client.

### Valutazione

La chiave non sembra hardcoded nel bundle frontend. Questo e' positivo.

Pero' il modello resta debole per una dashboard che puo' eseguire azioni operative:

- non c'e' identita utente;
- non c'e' login server-side;
- non c'e' session expiration controllata dal server;
- non c'e' logout server-side;
- non ci sono ruoli o scope;
- non c'e' distinzione tra lettura, admin e azioni trading/destructive;
- la chiave admin e' accessibile a JavaScript durante la sessione;
- un XSS o una dependency compromessa puo' leggere la chiave;
- l'utente deve reinserire la chiave dopo chiusura sessione/browser, cosa scomoda ma non risolve il problema di sicurezza.

Il fatto che "a ogni rebuild devo mettere l'api key nel frontend" e' probabilmente dovuto alla persistenza in `sessionStorage`, non al rebuild in se'. `sessionStorage` vive finche' resta viva la sessione browser/tab; se il tab o browser viene chiuso, la key si perde.

Passare a `localStorage` migliorerebbe la UX ma peggiorerebbe la sicurezza, perche' la chiave resterebbe persistente e leggibile da JS piu' a lungo.

### Impatto

Se l'app e' usata solo su localhost o dietro una VPN privata, il rischio e' medio.

Se l'app e' raggiungibile da rete esterna o da altri utenti nella LAN, il rischio diventa alto:

- una API key condivisa equivale ad accesso admin globale;
- non e' possibile revocare un singolo utente;
- non e' possibile sapere chi ha attivato kill switch o cambiato modalita;
- la UI espone controlli sensibili senza session model robusto.

### Fix consigliato

Implementare uno di questi due modelli.

Opzione A, consigliata per prodotto operativo:

- aggiungere `POST /api/auth/login`;
- validare credenziali server-side;
- creare sessione server-side o JWT breve firmato;
- impostare cookie `HttpOnly`, `Secure`, `SameSite=Lax` o `Strict`;
- aggiungere `GET /api/auth/me`;
- aggiungere `POST /api/auth/logout`;
- spostare l'auth frontend da header manuale a cookie automatico;
- introdurre ruoli/scope:
  - `viewer`: dashboard read-only;
  - `operator`: kill switch, mode, llm models;
  - `admin`: config e operazioni distruttive;
- audit log delle azioni admin.

Opzione B, accettabile per homelab/private tool:

- mettere tutta la UI dietro reverse proxy con Basic Auth, Tailscale, Cloudflare Access o Authelia;
- non esporre l'API direttamente;
- rimuovere o ridurre il modal API key;
- mantenere `ADMIN_API_KEY` solo per chiamate interne o automazioni.

### Acceptance criteria

- Nessuna raw admin key leggibile da JavaScript.
- La UI funziona senza reinserimento manuale della key dopo ogni rebuild.
- Login/logout testabili.
- Azioni admin richiedono ruolo adeguato.
- Test che verificano:
  - accesso anonimo negato;
  - login valido;
  - cookie HttpOnly presente;
  - viewer non puo' usare kill switch;
  - operator puo' usare kill switch;
  - logout invalida la sessione.

---

## CR-02 - High - Superficie Docker esposta e credenziali default

### Evidenza

`docker-compose.yml` espone:

- Postgres su host: `5432:5432`;
- Redis su host: `6379:6379`;
- API su host: `8001:8000`;
- frontend su host: `3000:80`;
- Grafana su host: `3001:3000`.

Inoltre:

- Postgres usa credenziali default `trading/trading`;
- Redis non ha password;
- Grafana ha anonymous enabled;
- Grafana admin password e' hardcoded.

### Impatto

Questa configurazione e' comoda in sviluppo, ma pericolosa se usata in produzione o su una macchina raggiungibile:

- accesso diretto al database;
- accesso diretto a Redis, con possibilita di leggere/modificare stato operativo;
- Grafana anonima puo' esporre metriche sensibili;
- API accessibile direttamente aggira eventuali protezioni applicate solo al frontend.

### Fix consigliato

Separare profili dev/prod:

- `docker-compose.dev.yml` con porte esposte localmente;
- `docker-compose.prod.yml` senza porte DB/Redis pubbliche;
- esporre solo reverse proxy su `80/443`;
- usare Docker internal network per API, Postgres e Redis;
- password via secret/env non committati;
- disabilitare Grafana anonymous;
- ruotare `GF_SECURITY_ADMIN_PASSWORD`;
- aggiungere TLS;
- se necessario, mettere IP allowlist o VPN.

### Acceptance criteria

- In profilo prod, `postgres` e `redis` non hanno `ports`.
- Grafana anonymous disabled.
- Password non hardcoded nel compose.
- API non esposta direttamente se c'e' reverse proxy.
- Documentazione deploy aggiornata con checklist sicurezza.

---

## CR-03 - High - Fresh deploy probabilmente rotto: documentazione applica solo migration `001`

### Evidenza

`docs/deployment.md` documenta l'applicazione di sola `migrations/001_initial.sql`.

Il repository contiene migration successive fino alla `019`, e il codice attuale usa entita introdotte dopo la `001`, per esempio:

- `trades`;
- `execution_decisions`;
- campi analytics;
- campi cost breakdown aggiunti da `migrations/019_trade_cost_breakdown.sql`.

`src/store/pg_store.py` aggiorna colonne come:

- `exit_price`;
- `exit_time`;
- `gross_pnl`;
- `net_pnl`;
- `fees_usd`;
- `slippage_usd`;
- `regulatory_fees_usd`;
- `total_cost_usd`;
- `cost_bps`.

### Impatto

Un ambiente nuovo puo' partire con schema incompleto:

- API trading analytics falliscono;
- close trade fallisce per colonne mancanti;
- report settimanali falliscono o producono dati nulli;
- test/integration deploy non rappresentano lo stato reale dell'app.

### Fix consigliato

Implementare una procedura migration vera:

- tabella `schema_migrations`;
- runner che applica tutte le migration in ordine;
- migration idempotenti o almeno tracciate;
- comando documentato, ad esempio `make migrate`;
- esecuzione automatica controllata in deploy;
- test su database vuoto.

### Acceptance criteria

- Fresh DB + migration runner porta schema alla versione `019`.
- Avvio API non fallisce su database fresco migrato.
- Test integration verifica presenza colonne `trades` cost breakdown.
- `docs/deployment.md` non cita piu' solo `001_initial.sql`.

---

## CR-04 - High - Motore attivo `portfolio`, ma observability e feedback leggono ancora legacy `trades`

### Evidenza

Configurazione:

- `config/trading.yaml`
  - `execution.engine: portfolio`.

Portfolio scheduler:

- `src/workers/portfolio_scheduler.py`
  - produce ordini via portfolio orchestrator;
  - persiste principalmente in `portfolio_cycles`;
  - non sembra popolare in modo equivalente `trades` ed `execution_decisions`.

Analytics e feedback:

- `src/api/routes/trading.py`
  - endpoint trades/analytics/counterfactual leggono `trades` ed `execution_decisions`.
- `src/workers/performance.py`
  - `run_loss_feedback_check` legge trade chiusi da `trades`.

Documentazione:

- `docs/ARCHITECTURE.md`
  - riconosce known gap su feedback loop blind rispetto a S1/portfolio flow.

### Impatto

Il sistema puo' mostrare una falsa sensazione di osservabilita completa:

- la dashboard trades puo' essere vuota o parziale;
- analytics e postmortem possono rappresentare solo il vecchio engine;
- feedback loop puo' non reagire alle perdite prodotte dal motore portfolio;
- report cash drag/regime possono usare dati stale o assenti.

### Fix consigliato

Scegliere una delle due architetture.

Opzione A, unificare eventi trading:

- introdurre una tabella/event stream comune, ad esempio `orders`, `fills`, `positions`, `execution_decisions`;
- fare scrivere sia legacy sia portfolio scheduler nello stesso modello osservabile;
- aggiungere campo `engine`, `strategy_id`, `cycle_id`, `decision_id`.

Opzione B, separare esplicitamente:

- endpoint analytics portfolio dedicati;
- feedback loop su `portfolio_cycles` e posizioni reali;
- dashboard che dichiara chiaramente quale engine sta visualizzando.

La soluzione migliore e' A: una pipeline unica di osservabilita e feedback.

### Acceptance criteria

- Un portfolio cycle genera record osservabili per decision/order/fill.
- Le API `/api/trading/*` mostrano anche ordini generati dal portfolio engine.
- `run_loss_feedback_check` usa il motore attivo o una vista normalizzata.
- Test integration: dato un portfolio order chiuso in perdita, il feedback loop lo considera.

---

## CR-05 - High - Frequenza di rebalance bypassata per S1/S4

### Evidenza

Celery schedula il portfolio cycle ogni ora.

Nel portfolio flow:

- `src/workers/portfolio_scheduler.py` crea nuove istanze strategia;
- `src/portfolio/orchestrator.py` chiama direttamente `compute_target_weights()`;
- i metodi interni `_should_rebalance` di S1/S4 non vengono usati nel percorso effettivo.

S1/S4 hanno logica di rebalance propria:

- S1 ha gate su rebalance;
- S4 ha gate su rebalance;
- ma l'orchestrator bypassa questi gate.

### Impatto

Le strategie possono essere ricalcolate ogni ora anche se erano progettate per rebalance meno frequenti:

- turnover piu' alto;
- costi piu' alti;
- segnali meno stabili;
- performance live diversa da backtest/documentazione;
- maggiore rischio di overtrading.

### Fix consigliato

Rendere la frequenza di rebalance parte del contratto strategia.

Possibili approcci:

- aggiungere metodo pubblico `should_rebalance(now, state)` nel protocollo strategia;
- l'orchestrator deve interrogare il gate prima di chiamare `compute_target_weights`;
- persistire `last_rebalance_at` per strategia, non solo in memoria;
- se non e' tempo di rebalance, riusare target weights precedenti o ritornare no-op.

### Acceptance criteria

- Test: S1 non ribilancia se chiamata due volte nello stesso intervallo non valido.
- Test: S4 non ribilancia fuori schedule.
- Test: orchestrator rispetta `should_rebalance`.
- Metriche/report mostrano quando una strategia e' stata skipped per rebalance gate.

---

## CR-06 - Medium - S4 probabilmente sottopesata: doppia scalatura 10% * 10%

### Evidenza

`config/strategies.yaml` dice che le strategie devono restituire pesi sleeve-locali e che l'orchestrator scala per `allocation_pct`.

Configurazione S4:

- allocation globale S4: `0.10`;
- `src/strategies/s4/config.py` contiene `bucket_pct: 0.10`;
- `src/strategies/s4/ranking.py` calcola `per_ticker_weight = bucket_pct / n`;
- `src/portfolio/orchestrator.py` moltiplica poi ancora per `allocation_pct`.

### Impatto

Se S4 dovrebbe rappresentare il 10% del portafoglio, l'implementazione sembra portarla all'1%:

- S4 ha impatto molto minore del previsto;
- backtest/live possono divergere;
- allocazioni documentate non corrispondono al comportamento reale;
- le constraint per strategia diventano poco interpretabili.

### Fix consigliato

Decidere il contratto:

- se le strategie restituiscono pesi sleeve-locali, S4 deve distribuire il 100% della sua sleeve, quindi `per_ticker_weight = 1.0 / n`;
- se S4 vuole investire solo una frazione della propria sleeve, rinominare `bucket_pct` in modo esplicito, ad esempio `sleeve_invested_pct`, e documentare che allocation effettiva e' `allocation_pct * sleeve_invested_pct`.

Per coerenza con `strategies.yaml`, consigliato il primo approccio.

### Acceptance criteria

- Test: con allocation S4 10% e 5 ticker, peso totale S4 combinato = 10%.
- Test: pesi strategy-locali S4 sommano a 1.0 prima della scalatura orchestrator.
- Documentazione aggiornata sul contratto dei pesi.

---

## CR-07 - Medium - Toggle Economy/Full Ensemble puo' mostrare stato falso su errore auth

### Evidenza

`frontend/src/components/layout/Sidebar.tsx` usa `fetch('/api/admin/llm-models')` direttamente.

Il codice:

- invia `X-API-Key`;
- non verifica `res.ok`;
- se la fetch si risolve, aggiorna comunque lo store con `setLlmModels(next)`.

### Impatto

Se la API key e' assente, scaduta o invalida:

- backend risponde 403;
- frontend puo' comunque mostrare il nuovo stato;
- l'utente crede di aver cambiato modalita;
- lo stato UI diverge dallo stato server.

### Fix consigliato

- usare il client comune `apiFetch`;
- gestire esplicitamente 403;
- aggiornare lo store solo dopo risposta OK;
- in caso di errore, mostrare toast/banner e ripristinare stato precedente;
- considerare optimistic update solo con rollback robusto.

### Acceptance criteria

- Test frontend: su risposta 403, `llmModels` non cambia.
- Test frontend: su risposta 200, `llmModels` cambia.
- Messaggio chiaro se API key non valida.

---

## CR-08 - Medium - `close_trade` usa `SKIP LOCKED`, ma aggiorna per `symbol`

### Evidenza

`src/store/pg_store.py`:

- prefetch con `SELECT ... FOR UPDATE SKIP LOCKED`;
- poi update con `WHERE symbol = %s AND exit_time IS NULL`.

Il lock viene preso su una riga specifica, ma l'update non usa l'identificativo della riga lockata.

### Impatto

In presenza di concorrenza o piu' trade aperti sullo stesso simbolo:

- una riga lockata puo' essere saltata dalla prefetch;
- l'update successivo puo' comunque aspettare o aggiornare la riga sbagliata;
- costi e P&L possono essere calcolati con notional/qty zero;
- se ci sono piu' righe aperte, l'update per simbolo e' ambiguo.

### Fix consigliato

Rendere la chiusura trade row-based:

- prefetch deve selezionare anche `id`;
- update deve fare `WHERE id = %s`;
- se nessuna riga e' disponibile perche' lockata, ritornare stato esplicito `locked/no_open_trade`;
- opzionale: constraint o indice parziale se si vuole al massimo un trade aperto per simbolo.

### Acceptance criteria

- Test: due chiamate concorrenti a `close_trade` sullo stesso simbolo non aggiornano la stessa riga due volte.
- Test: con due trade aperti stesso simbolo, si chiude solo la riga selezionata.
- Test: se la riga e' lockata, il metodo non calcola costi su notional zero.

---

## CR-09 - Medium - P&L puo' restare `NULL` quando `trades.qty` e' `NULL`

### Evidenza

`close_trade` ora puo' ricevere `qty` e `notional`, ma la query SQL calcola gross/net P&L usando la colonna `qty` della tabella `trades`.

Se `trades.qty` e' `NULL`, le espressioni:

- `(exit_price - entry_price) * qty`;
- net/gross P&L;

possono restare `NULL`.

### Impatto

La fix recente migliora i casi in cui `qty` e' gia' persistito, ma non risolve completamente:

- trade aperti senza qty;
- ordini by-notional senza fill quantity;
- dati legacy;
- report/analytics che vedono P&L nullo.

### Fix consigliato

Alla chiusura:

- se `qty` DB e' null ma `qty` argomento e' disponibile, aggiornare `trades.qty`;
- calcolare P&L con `COALESCE(trades.qty, $passed_qty)`;
- meglio ancora: registrare fill quantity reale dall'esecuzione broker e rendere `qty` obbligatoria per i trade chiusi.

### Acceptance criteria

- Test: trade aperto con `qty NULL`, chiuso passando `qty`, produce P&L non null.
- Test: trade senza qty e senza fill non produce P&L fittizio, ma stato errore/unknown esplicito.
- Report non confonde P&L unknown con P&L zero.

---

## CR-10 - Medium - Fail-open tra legacy engine e portfolio scheduler

### Evidenza

`src/workers/execution.py`:

- se non riesce a leggere `trading.yaml`, defaulta a `legacy_sentiment`.

`src/workers/portfolio_scheduler.py`:

- se non riesce a leggere `trading.yaml`, defaulta a `portfolio`.

### Impatto

In caso di errore file/config:

- i due worker possono prendere decisioni diverse;
- entrambi possono considerarsi attivi;
- il sistema puo' tradare in uno stato non configurato correttamente.

Per un sistema di trading, questo dovrebbe essere fail-closed, non fail-open.

### Fix consigliato

- centralizzare lettura engine in un helper unico;
- se config non leggibile, sollevare errore e non tradare;
- loggare evento critico;
- opzionale: attivare kill switch automatico su config invalid.

### Acceptance criteria

- Test: config mancante -> worker legacy non opera.
- Test: config mancante -> portfolio scheduler non opera.
- Test: config invalida -> errore esplicito e nessun ordine generato.

---

## CR-11 - Medium - Constraints perdono provenance strategia usando `strategy_id="merged"`

### Evidenza

`src/portfolio/orchestrator.py` crea ordini combinati con `strategy_id="merged"`.

`src/portfolio/constraints.py` applica cap per strategia usando `strategy_id`, ma riceve `"merged"` invece di `S1`, `S4`, ecc.

La documentazione architetturale riconosce questo come known gap.

### Impatto

Le constraint per strategia possono non essere realmente applicate:

- esposizione S1/S4 non misurata correttamente;
- cap per allocation non affidabile;
- audit per strategia perso;
- difficile spiegare da quale strategia arriva un ordine.

### Fix consigliato

Mantenere provenance multi-strategy:

- ordine combinato con `components`;
- ogni component contiene `strategy_id`, peso originale, contributo al peso finale;
- constraints applicate prima per strategia e poi sul merged order;
- persistenza della provenance in DB.

### Acceptance criteria

- Test: ordine derivato da S1 e S4 conserva entrambi i contributi.
- Test: cap S1 viene applicato anche dopo merge.
- API/debug mostra breakdown per strategia.

---

## CR-12 - Medium - Invarianti allocation solo loggate, non enforced

### Evidenza

`config/strategies.yaml` dichiara che alcune invarianti sono enforced a startup.

`src/strategies/registry.py` pero' valida allocation e sembra limitarsi a loggare warning, senza bloccare startup.

### Impatto

Configurazioni incoerenti possono arrivare in runtime:

- allocation totale diversa da 100%;
- strategie abilitate ma non contabilizzate;
- rischio di esposizione inattesa;
- documentazione piu' forte del comportamento reale.

### Fix consigliato

- trasformare warning critici in errori;
- introdurre modalita `strict_config_validation`;
- fallire startup in prod;
- permettere warning solo in dev/test se necessario.

### Acceptance criteria

- Test: allocation totale != 1.0 in strict mode blocca startup.
- Test: allocation valida passa.
- Documentazione aggiornata se si decide di non enforce.

---

## CR-13 - Low/Medium - Docs e test auth disallineati

### Evidenza

`docs/API.md` descrive alcune route come pubbliche, ma il codice le protegge con `require_api_key`, per esempio:

- signals;
- performance;
- strategies;
- trading.

Alcuni test hanno docstring/assertioni ancora orientate a "no auth", ma un fixture autouse bypassa `require_api_key`, quindi non verificano davvero il comportamento di auth.

### Impatto

- un developer puo' credere che endpoint siano pubblici quando non lo sono;
- test possono passare anche se auth reale e' rotta;
- frontend puo' gestire male 403/401;
- review future piu' difficili.

### Fix consigliato

- aggiornare auth matrix in `docs/API.md`;
- aggiungere test senza override auth per verificare 403;
- aggiungere test con API key valida;
- allineare frontend a `403`, non solo `401`.

### Acceptance criteria

- Per ogni router esiste test auth missing/invalid/valid.
- Docs indicano esattamente route pubbliche/protette.
- Frontend mostra messaggio corretto su 403.

---

## CR-14 - Low/Medium - `portfolio:value` puo' essere stale con engine `portfolio`

### Evidenza

Il legacy execution worker aggiorna Redis `portfolio:value`.

Il portfolio scheduler legge account Alpaca, ma non sembra aggiornare lo stesso valore Redis.

Il report settimanale usa `portfolio:value` per sezioni come:

- capital efficiency;
- cash drag;
- regime dollar ceiling.

### Impatto

Con `execution.engine=portfolio`:

- `portfolio:value` puo' essere assente;
- oppure puo' contenere valore stale scritto dal legacy worker;
- cash drag e capital efficiency possono risultare errati o unknown.

### Fix consigliato

- spostare aggiornamento portfolio value in un servizio condiviso;
- chiamarlo da entrambi gli engine;
- associare timestamp al valore;
- report deve ignorare valori troppo vecchi.

### Acceptance criteria

- Portfolio scheduler aggiorna `portfolio:value` con timestamp.
- Report mostra warning se valore stale.
- Test: in engine portfolio, capital efficiency usa valore aggiornato.

---

## CR-15 - Low - `TradeCostCalculator` usa path config relativo

### Evidenza

`src/costs/calculator.py` usa default path `Path("config/cost_model.yaml")`.

Questo funziona se il processo parte dalla root repo, ma e' fragile se:

- test partono da altra working directory;
- modulo viene importato da script esterno;
- worker viene lanciato con cwd differente.

### Impatto

Cost model non caricato, fallback inatteso, stop loss/costi diversi da config.

### Fix consigliato

- risolvere path da `__file__` verso root progetto;
- oppure passare config path da settings centralizzato;
- loggare chiaramente il file effettivamente caricato.

### Acceptance criteria

- Test: calculator funziona anche se cwd non e' repo root.
- Log iniziale mostra path assoluto del cost model.

---

## CR-16 - Low - Net IC nel backtest sottrae costi parziali

### Evidenza

`src/backtest/report.py` introduce campi `ic_*_net`.

La logica net-of-costs sottrae `cost_bps / 10000`, ma il calcolo runtime di `total_cost_usd` include anche componenti regulatory fee.

### Impatto

Probabilmente piccolo, ma se `ic_net` viene usato come metrica decisionale ufficiale:

- backtest e live accounting non sono perfettamente allineati;
- costi regolatori possono essere ignorati nella metrica net.

### Fix consigliato

- definire una semantica unica per `cost_bps`;
- decidere se include o esclude regulatory fees;
- documentare;
- usare la stessa formula nel cost calculator e nel backtest report.

### Acceptance criteria

- Test: net IC usa la stessa definizione di costo del runtime.
- Docs metriche indicano cosa e' incluso in `cost_bps`.

---

## CR-17 - Low - `run_loss_feedback_check` crea RedisStore senza chiusura esplicita

### Evidenza

`src/workers/performance.py` crea `RedisStore()`.

Nel `finally` chiude `pg`, ma non sembra chiudere RedisStore.

`src/store/redis_store.py` espone metodo `close()`.

### Impatto

Rischio contenuto, ma nel tempo puo' produrre:

- connessioni persistenti non necessarie;
- leak in worker long-running;
- comportamento non pulito in test.

### Fix consigliato

- chiudere `store.close()` nel `finally`;
- se possibile usare context manager.

### Acceptance criteria

- Test/mocking verifica chiamata a `close()`.
- Nessun warning di connessioni aperte nei test.

---

# Piano operativo consigliato per Claude Code

## Fase 1 - Security baseline

Obiettivo: rendere l'app sicura da esporre almeno dietro una rete privata controllata.

Task:

1. Introdurre modello login/sessione oppure reverse proxy auth documentato.
2. Rimuovere la necessita di inserire API key raw nella UI.
3. Aggiungere ruoli minimi: viewer/operator/admin.
4. Correggere gestione 403 nel frontend.
5. Chiudere porte DB/Redis in compose prod.
6. Disabilitare Grafana anonymous.
7. Aggiornare `docs/deployment.md`.

Output atteso:

- endpoint auth;
- test auth;
- UI senza API key modal admin raw;
- compose prod piu' sicuro;
- documentazione aggiornata.

## Fase 2 - Migration e deploy

Obiettivo: un ambiente nuovo deve arrivare allo schema corretto.

Task:

1. Implementare migration runner.
2. Tracciare migration applicate.
3. Applicare `001` -> `019` in ordine.
4. Aggiungere comando `make migrate` o equivalente.
5. Aggiornare documentazione deploy.
6. Test su database vuoto.

Output atteso:

- fresh deploy riproducibile;
- schema completo;
- nessuna istruzione manuale obsoleta.

## Fase 3 - Allineare portfolio engine e observability

Obiettivo: cio' che tradano S1/S4 nel portfolio engine deve essere visibile e usato da analytics/feedback.

Task:

1. Definire modello comune decision/order/fill/trade.
2. Far scrivere il portfolio scheduler in `execution_decisions` o vista equivalente.
3. Collegare ordini portfolio a trade lifecycle.
4. Aggiornare API analytics.
5. Aggiornare feedback loop per leggere engine attivo o vista normalizzata.
6. Aggiornare report settimanale.

Output atteso:

- dashboard coerente con engine `portfolio`;
- feedback loop non blind rispetto a S1/S4;
- trade analytics affidabili.

## Fase 4 - Correggere logica portfolio/strategie

Obiettivo: far coincidere comportamento live, configurazione e documentazione.

Task:

1. Aggiungere contratto `should_rebalance`.
2. Persistire `last_rebalance_at` per strategia.
3. Correggere S4 double scaling.
4. Preservare provenance strategia negli ordini merged.
5. Enforce invarianti allocation in strict mode.

Output atteso:

- S1/S4 rispettano schedule;
- S4 pesa quanto configurato;
- constraints per strategia verificabili;
- config invalida blocca startup in prod.

## Fase 5 - Hardening storage trade

Obiettivo: `close_trade` deve essere corretto e robusto in concorrenza.

Task:

1. Selezionare trade aperto con `id`.
2. Aggiornare usando `WHERE id = $id`.
3. Gestire caso lock/no row esplicitamente.
4. Usare `qty` passato se DB qty e' null, oppure fallire in modo esplicito.
5. Aggiungere test concorrenza.

Output atteso:

- nessun update ambiguo per simbolo;
- P&L non nullo quando qty reale disponibile;
- comportamento esplicito quando mancano fill data.

---

# Note specifiche sull'API key nel frontend

L'attuale implementazione non mette la key nel bundle, quindi non e' il caso peggiore.

Pero' resta un pattern scomodo e poco adatto a una console admin:

- l'utente copia/incolla un segreto tecnico;
- il segreto vive nel runtime JS;
- non ci sono sessioni;
- non c'e' audit per utente;
- non esistono ruoli;
- la UX si rompe quando `sessionStorage` viene perso.

Raccomandazione finale:

- non passare a `localStorage` come soluzione definitiva;
- usare sessione server-side con cookie HttpOnly;
- oppure proteggere tutta l'app con reverse proxy/VPN e trattarla come internal tool.

---

# Stato complessivo

Il progetto mostra progressi reali sulle issue precedenti, ma le ultime modifiche hanno anche reso piu' evidente una transizione architetturale non ancora completata:

- legacy execution engine;
- portfolio engine;
- trade observability;
- feedback loop;
- analytics/reporting;

non sono ancora pienamente unificati.

La priorita' tecnica non dovrebbe essere aggiungere altri report, ma chiudere il triangolo:

1. cio' che decide il portfolio engine;
2. cio' che viene eseguito;
3. cio' che viene osservato, misurato e usato per feedback.

Finche' questi tre livelli non usano lo stesso modello dati, la dashboard puo' apparire completa ma raccontare solo una parte del sistema reale.

