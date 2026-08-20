# Forensic Daily Report — 2026-08-14

Analista: sessione autonoma read-only. Timezone operativo: **UTC** (confermato in
`src/workers/celery_app.py`: `timezone="UTC", enable_utc=True`; Postgres `SHOW timezone` = UTC).
Market hours = 13:30–20:00 UTC. Periodo di sola osservazione (`docs/evidence/OBSERVATION_CHARTER.md`):
nessuna proposta di taratura, solo difetti di correttezza sono ammessi come ticket.

Fonti: query dirette `docker exec alembic-postgres-1 psql` (SELECT-only), `docs/ALPHA_MISS_REPORT_2026-08-14.md`
(già scritto e verificato in questa sessione da `docs/evidence/dossier/2026-08-14.json`, Alpaca SIP
`adjustment=all`), lettura codice (`src/workers/`, `src/store/pg_store.py`, `src/llm/ensemble.py`),
`docs/evidence/findings.json`. **L'API REST locale (`localhost:8001/api`) ha rifiutato il token fornito
("Invalid or expired JWT token") — tutte le tabelle sono state lette via SQL diretto, che è la fonte
più autorevole comunque disponibile.** I log Docker live (`docker compose logs`) **non coprono il
2026-08-14**: `worker`/`worker-inference`/`beat` sono stati riavviati il 2026-08-15T12:20:11Z (deploy
successivo) e non esiste un archivio `docs/evidence/logs_2026-08-14/` (a differenza del 08-13, che ha
`docs/evidence/logs_2026-08-13/worker.log.gz`). Latenza LLM, testo esatto di errori/timeout e
downtime Ollama per il 2026-08-14 **non sono ricostruibili da log** — solo dai residui in DB
(`llm_responses`, `sentiment_signals.fallback_used`).

---

## 1. Executive summary

Giornata a bassa attività per il motore di trading (2 BUY, 0 SELL, 0 chiusure) su una seduta di mercato
ad alta dispersione idiosincratica (σ cross-sectional 2,18%, indici piatti). 169 news ingerite da 2
fonti (Benzinga, GDELT GKG), 169 segnali generati su 52 simboli, 563 SKIP_THRESHOLD, 9 SKIP_PYRAMIDING
(guard anti-pyramiding ha bloccato correttamente 6 simboli sopra gate già a libro), 2 BUY S4 (JD, BA)
entrambi sopra soglia e con rationale coerente al segnale. Nessuna anomalia trovata nel percorso
segnale→decisione→ordine di oggi: gate rispettato, nessun ordine duplicato, nessun ordine sotto soglia,
nessun ordine SELL con segno errato (nessuna SELL oggi), paper mode confermato end-to-end
(`portfolio_monitor_snapshots.mode='paper'`, `broker_environment='paper'`).

**Due difetti pre-esistenti tracciati nel ledger si sono ripresentati** (F-001 NO_NEWS su un mover
accessibile, costo $76,03; F-009 gate che scarta segnale di segno corretto su AVGO/ORCL, costo zero;
F-006 soppressione del log SKIP_FALLBACK su HOOD; F-002 P&L non attribuibile su 11 posizioni legacy;
F-028 la suite di test scrive ancora su `ingestion_stats_daily` in produzione).

**Una anomalia nuova e più grave del previsto**: 16 righe della tabella `trades` — la tabella su cui
poggia l'intera misura del P&L economico dell'osservazione — sono state inserite E CANCELLATE nella
mattina del 2026-08-14 (07:13–11:50 UTC, pre-market) da un processo che non è la pipeline di trading.
Le cancellazioni **non hanno lasciato traccia in `audit_log`**, a differenza degli inserimenti. Causa
identificata con alta confidenza per lettura del codice: `tests/store/test_pg_store_stop_methods.py`
chiama `PostgreSQLStore(use_pool=False)` su `DATABASE_URL` dell'ambiente — senza guardia contro il
Postgres di produzione — e nel blocco `finally` esegue `DELETE FROM trades WHERE symbol = %s` in SQL
grezzo, bypassando ogni logging di audit. È la stessa classe di rischio già segnalata da **F-028
(ticket TK-H)**: "se la suite scrive [in produzione], può scrivere altrove" — qui si è materializzata
su una tabella molto più sensibile della prima. Nessun trade reale è stato toccato (i simboli sintetici
come `TEST_STOP_1` non sono in watchlist), ma l'invariante che il codice stesso dichiara ("P0-12: nessun
trade non auditato può esistere") vale solo per gli INSERT, non per i DELETE — e oggi è stata la falla
attraversata.

## 2. Verdict finale

**OK con warning.** Il flusso operativo del 2026-08-14 (news → segnale → decisione → ordine → posizione)
è funzionalmente corretto: nessun bug trovato nel money path di oggi. Il warning non è sulla giornata
di trading ma sull'integrità dell'infrastruttura di misura durante la finestra di osservazione: la
tabella `trades` è dimostrabilmente scrivibile da processi esterni alla pipeline, con cancellazioni
invisibili all'audit trail. Se questo accadesse su un simbolo reale invece che su un fixture sintetico,
l'evidenza P&L dell'intera finestra sarebbe contaminata senza modo di scoprirlo dal solo DB.

## 3. Timeline del 2026-08-14 (UTC)

| ora | componente | evento |
|---|---|---|
| 07:00 | regime-detector | run giornaliero pre-market (schedulato 07:00 UTC Mon-Fri) |
| 07:13–11:50 | *(fuori pipeline)* | 16 righe `trades` inserite e cancellate — vedi [DAY-201]. Nessun impatto su `execution_decisions`/`portfolio_cycles` (zero righe in entrambe prima delle 13:00 UTC) |
| 13:00–13:59 | news ingest | 20 righe `news_log` (Benzinga + GDELT) |
| 13:30 | mercato USA | apertura |
| 14:00–14:59 | news ingest | 19 righe |
| 14:07 | portfolio-cycle | primo ciclo della giornata (24 cicli totali, ultimo 19:52, nessun gap oltre 16 min) |
| 14:07 | execution_decisions | SKIP_PYRAMIDING su GE, SPY (sentiment sopra gate, guard anti-pyramiding attivo) |
| 14:37 | execution_decisions / trades | **BUY JD** (id 725), score +0,597 ensemble conf 0,825, peso 2,0%, entry $29,02 |
| 15:00–15:59 | news ingest | 35 righe (picco del giorno) |
| 16:00–16:59 | news ingest | 29 righe |
| 16:52 | execution_decisions / trades | **BUY BA** (id 726), score +0,345 ensemble conf 0,725, peso 2,0%, entry $230,98 |
| 17:00–17:59 | news ingest | 45 righe (picco assoluto — articolo AVGO/ORCL dedicati in questa finestra) |
| 17:30 | sentiment_signals | AVGO −0,282 (segno corretto, sotto gate 0,30 di 0,06) → attenuato a −0,226 da signal-velocity multiplier |
| 18:00–18:59 | news ingest | 21 righe, ultima pubblicazione 18:54:54 |
| 19:52 | portfolio-cycle | ultimo ciclo della giornata |
| 20:00 | portfolio_monitor_snapshots | EOD: NAV $110.440,21, nav_change_today −$23,60, 49 posizioni aperte, cash $74.309,55, current_drawdown 0,19% |
| 21:00 | decay_monitor | 12 righe `decay_reports`, 3 strategie, valori actual IDENTICI su S1/S2/S4 (F-004, ricorrenza) |
| 22:30 | risk_monitor | `risk_reports` id 63: combined_drawdown 1,24%, per_strategy_metrics.portfolio.drawdown 17,19% → ALERT "17.2% exceeds 10%" (F-003, ricorrenza) |

Nessun evento fuori orario, nessun timestamp futuro (`fetched_at < published_at` verificato = 0 righe),
nessuna news con `published_at` fuori dal 2026-08-14.

## 4. Tabella news ingest

| fonte | fetched | queued | duplicates | discarded_no_ticker | righe in news_log 08-14 |
|---|---:|---:|---:|---:|---:|
| alpaca_benzinga | 537 | 335 | 2.612 | 0 | 87 |
| gdelt_gkg | 1.939 | 107 | 51 | 1.788 | 82 |
| reuters | 20 | 20 | 0 | 5 | **0 — vedi [DAY-202], ricorrenza F-028** |
| **totale news_log** | | | | | **169** |

- 52/96 simboli watchlist con almeno una riga; **45/96 (47%) zero copertura**, dentro la banda 42-57%
  osservata dal 07-31 (F-001).
- Fan-out multi-ticker: 77/169 righe (45,6%) da 24 articoli multi-ticker su 116 (20,7%) — banda stabile
  (F-012).
- Duplicati per `content_hash` entro il giorno: 24 hash con 2-11 occorrenze — attesi per design
  (`uq_news_log_url_ticker` memorizza lo stesso articolo una volta per ticker taggato), non un difetto
  di dedup.
- Copertura oraria: nessun buco >1h durante il market hours; picco 17:00-17:59 (45 righe, include gli
  articoli dedicati AVGO/ORCL).
- Nessuna news futura, nessuna news stale processata come fresca (verificato su `fetched_at`).

## 5. Tabella performance modelli LLM

| model_id | righe (signal-level) | score medio | confidenza media | note |
|---|---:|---:|---:|---|
| `ensemble:glm-5.2:cloud+gpt-oss:20b-cloud` | 121 (71,6%) | +0,036 | 0,267 | ensemble a due modelli, esito normale |
| `single:gpt-oss:20b-cloud` | 39 (23,1%) | −0,035 | 0,515 | fallback single-model |
| `single:glm-5.2:cloud` | 7 (4,1%) | +0,146 | 0,571 | fallback single-model |
| `finbert` | 2 (1,2%) | +0,089 | 0,212 | fallback deterministico locale |

- `sentiment_signals.fallback_used`: 121 false / 48 true → **fallback rate 28,4%** (single-model o
  FinBERT invece dell'ensemble a 2 modelli).
- `llm_responses` (livello per-modello, 2 chiamate per news_log row = 338 attese, 338 osservate):
  **eligible=true 50 (14,8%) / eligible=false 288 (85,2%)**. `eligible` = confidenza individuale del
  modello ≥ soglia 0,4 richiesta da `ensemble.py` per contribuire al peso ensemble
  (`src/llm/ensemble.py:284`). Un tasso di ineleggibilità dell'85% a livello di singola chiamata
  significa che la maggior parte delle risposte dei due modelli, prese singolarmente, non è abbastanza
  sicura per pesare — ma basta che UNO dei due lo sia perché l'ensemble non vada in fallback totale
  (fallback rate osservato 28,4%, non 85%).
  Nessuna riga con confidenza fuori range [0,1] o polarity fuori [-1,1] in `sentiment_signals` (min
  score −0,300, max score +0,597 — coerente col gate ±0,30 e la soglia di ingresso).
- Massimo disaccordo ensemble oggi (`ensemble_std`): UNH 0,354 e IWM 0,354 — non estremo, nessun
  outlier isolato oltre 0,40.
- Nessuna evidenza di refusal/output non parsabile: `llm_responses.eligible=false` è un filtro di
  confidenza, non un errore di parsing; non esiste nel DB un campo separato per "invalid JSON" o
  refusal — se questi eventi sono accaduti oggi, sono visibili solo nei log Docker, **non disponibili
  per il 2026-08-14** (vedi nota nell'intestazione).
- Modelli chiamati offline/background: confermato per lettura del codice (`worker-inference`,
  concurrency=1, coda `inference`), coerente con l'architettura Alpha Miner — nessuna chiamata LLM
  sincrona nel ciclo `portfolio-cycle`/`run-execution`.
- La news duplicata (stesso articolo, ticker diversi) genera segnali distinti per ciascun ticker per
  design (righe `news_log` separate via `uq_news_log_url_ticker`), non pesa "due volte" sullo stesso
  ticker.

## 6. Tabella segnali finali per ticker (rilevanti al money path)

| simbolo | ora segnale (UTC) | score | confidenza | modello | esito |
|---|---|---:|---:|---|---|
| JD | 14:22 (segnale sottostante alla BUY 14:37) | +0,716 (score decisione) / signal id 7702 score +0,597 | 0,825 | ensemble | **BUY** |
| BA | 16:37 (sottostante alla BUY 16:52) | +0,413 (score decisione) / signal id 7777 score +0,345 | 0,725 | ensemble | **BUY** |
| GE | 14:07/14:52 | +0,345 / −0,120 | — | ensemble | SKIP_PYRAMIDING (già a libro dal 07-22) |
| SPY | 14:07/14:52 | +0,380 / −0,120 | — | ensemble | SKIP_PYRAMIDING (già a libro dal 07-10) |
| TSM | 15:37 | +0,447 | — | ensemble | SKIP_PYRAMIDING (già a libro dal 07-14) |
| MU | 17:07 | +0,453 | — | ensemble | SKIP_PYRAMIDING (già a libro dal 07-28) |
| PANW | 17:07 | +0,040 | — | ensemble | SKIP_PYRAMIDING |
| NOK | 18:07 | — | — | — | SKIP_PYRAMIDING (già a libro dal 07-14) |
| IWM | 19:07 | +0,333 | — | ensemble | SKIP_PYRAMIDING (già a libro dal 07-24) |
| AVGO | 17:30 | −0,282 → −0,226 post signal-velocity | 0,60 | ensemble | SKIP_THRESHOLD (sotto gate 0,30 per 0,06) — F-009 |
| ORCL | 15:45/15:22-16:52 | −0,112 / −0,039 | 0,40 | ensemble | SKIP_THRESHOLD — F-009 |
| RDDT | 14:15/18:00 | 0,000 / +0,04 | 0,15/0,40 | ensemble/fallback | SKIP_THRESHOLD (nessuna copertura dedicata) |
| HOOD | 15:45/17:01 | −0,04 / +0,072 | fallback-only | single | **zero righe execution_decisions** — F-006 |
| F | — | — | — | — | NO_NEWS, nessun segnale — F-001 |

Nota su segno: nessun caso oggi in cui il campo `reason` di `execution_decisions` mostri il segno
invertito (verificato sulle SKIP_THRESHOLD di AVGO/ORCL — il meccanismo `abs(sig_score)` di F-006 resta
un difetto di visualizzazione noto ma non ha causato letture sbagliate nei casi controllati oggi).

## 7. Tabella ordini generati/eseguiti

| symbol | decisione | tick_time UTC | strategia | qty | prezzo entry | notional | peso | stop_strategy | stop_mode | risk check | esito |
|---|---|---|---|---:|---:|---:|---:|---|---|---|---|
| JD | BUY | 14:37:00 | S4 | 62,3015 | $29,02 | $1.808 | 2,0% | S4 | fixed | anti-pyramiding OK (non a libro), cap 2% OK | FILLED (trade id 725) |
| BA | BUY | 16:52:00 | S4 | 7,8071 | $230,98 | $1.803,3 | 2,0% | S4 | fixed | idem | FILLED (trade id 726) |

- Nessun ordine SELL oggi (0 chiusure, `trades` closed=0).
- Nessun ordine duplicato, nessun ordine nello stesso minuto sullo stesso simbolo, nessun roundtrip
  <30 min.
- Nessuna riga `stop_decisions` oggi (nessun trigger di stop-loss).
- Ordini generati tramite `execution.engine=portfolio` (unico motore attivo, confermato da
  `config/trading.yaml:142`); `run-execution` (legacy_sentiment) non è il motore autoritativo e non ha
  generato ordini propri oggi (nessuna evidenza di doppia sorgente ordini).
- Modalità: **paper** confermata su tutti i 24 snapshot del giorno (`mode='paper'`,
  `broker_environment='paper'`, `source='alpaca_paper'`).

## 8. Tabella PnL/rendimento

| voce | valore |
|---|---:|
| NAV apertura (primo snapshot 08-14, 07:12) | $110.307,36 |
| NAV chiusura (20:00 UTC) | $110.440,21 |
| `nav_change_today` (colonna dedicata) | **−$23,60** |
| Variazione NAV apertura→chiusura (calcolo diretto) | +$132,85 |
| Cash EOD | $74.309,55 |
| Posizioni aperte EOD | 49 |
| Realizzato del giorno | $0,00 (nessuna chiusura) |
| MTM stimato — 3 mover tenuti passivamente | AMD +$25,53 · WDC +$64,13 · AMAT −$23,45 |
| MTM stimato — 11 posizioni "legacy" senza `stop_strategy` (F-002) | **≈ +$21,41** (somma qty×Δclose; ROKU +$15,35 ne è la componente maggiore ed è anche un simbolo bloccato da SKIP_PYRAMIDING oggi) |
| `risk_reports` nav (22:30, post-close) | $110.447,31 |

**Scarto non riconciliato**: `nav_change_today` (−$23,60) e la variazione apertura→chiusura calcolata
sullo stesso giorno dagli snapshot (+$132,85) non coincidono, differenza di **$156,45**. Questo è
coerente con il pattern già tracciato in **F-003** (daily_pnl/drawdown incoerenti con la variazione NAV
osservata) ma applicato qui a `nav_change_today` invece che a `daily_pnl` di `risk_reports` — non
indago oltre la causa applicativa (fuori scope, si tratta di un solo campo di un giorno), la segnalo
come nuova faccia della stessa famiglia di difetti di misura.

Non è possibile scomporre il PnL per strategia con precisione: 11/49 posizioni (22%) non hanno
`stop_strategy` popolato (F-002), quindi qualunque split S1/S4 del giorno esclude ROKU (+2,34%, uno dei
mover del giorno) dalla sleeve corretta. Slippage e commissioni: nessun ordine chiuso oggi, quindi
`cost_bps`/`slippage_est`/`cost_usd` non popolati per nessuna riga della giornata (colonne esistono in
`trades` ma si valorizzano solo in chiusura).

## 9. Analisi correttezza buy/sell

- **BUY generati solo quando consentito**: sì. Entrambi i BUY (JD, BA) hanno score ensemble sopra il
  gate 0,30 (+0,597 e +0,345), confidenza ≥0,72, peso al cap 2,0%, nessuna violazione di
  anti-pyramiding (nessuno dei due era già a libro).
- **Anti-pyramiding rispettato**: sì, 9/9 SKIP_PYRAMIDING correttamente bloccati (verificato: tutti e 6
  i simboli coinvolti — GE, SPY, TSM, MU, PANW, NOK, IWM — risultano aperti da date precedenti in
  `trades`).
- **Nessun sell/exit oggi**: nessuna violazione di stop-loss, signal flip, max holding possibile da
  verificare (nulla è stato chiuso).
- **Nessun ordine duplicato, nessun ordine fuori orario, nessun ordine su ticker non in watchlist.**
- **Nessun trade generato da segnale non valido**: score/confidenza di JD e BA entro range attesi,
  nessun segno invertito nel rationale persistito.
- **Nessun trade durante circuit breaker attivo**: nessun halt registrato oggi (nessuna riga di
  sistema che indichi `system:halted_by_operator` per il 08-14, verificato assenza di gap anomali nei
  24 cicli).
- **Idempotenza Celery**: `audit_log` mostra `SIGNAL_STALE_SKIP` (542 righe) e `SIGNAL_DUPLICATE_SKIP`
  (33 righe) attivamente applicati durante la giornata — il meccanismo di dedup dei segnali ha
  funzionato, nessun segnale processato due volte con effetto ordine duplicato.
- **Paper/live coerente**: sì, confermato in ogni snapshot.
- **Reconciliation trades↔posizioni**: 49 posizioni aperte a fine giornata, coerenti col conteggio
  `open_positions` dello snapshot; nessuna divergenza rilevabile senza accesso diretto alle posizioni
  Alpaca (API REST non raggiungibile con il token fornito — vedi §12).

Avvertenza `exit_mechanism` (#184): non applicabile oggi — nessuna chiusura, nessuna riga
`exit_reason`/`exit_mechanism` generata il 08-14.

## 10. Anomalie trovate

### [DAY-201] Righe `trades` inserite e cancellate pre-market da un processo esterno alla pipeline, senza audit trail della cancellazione — probabile suite di test contro il DB di produzione

* Tipo: Anomalia / Bug
* Area: Data / Ops
* Evidenza:
  * file/log/tabella: `trades`, `audit_log`, `tests/store/test_pg_store_stop_methods.py`
  * timestamp: 2026-08-14 07:13:49, 07:20:01, 07:49:49, 11:50:45 UTC
  * snippet/query: `SELECT action, table_name, record_id, created_at FROM audit_log WHERE table_name='trades' AND created_at::date='2026-08-14'` → 16 righe `INSERT` per `record_id` 706-724 (con 4 id mancanti: 705, 710, 715, 720); `SELECT id FROM trades WHERE id BETWEEN 706 AND 724` → **0 righe** (nessuna esiste più). `audit_log` non contiene MAI un'azione `DELETE` per `table_name='trades'` in tutta la sua storia (`SELECT action, COUNT(*) FROM audit_log WHERE table_name='trades' GROUP BY 1` → solo `INSERT`, 473 righe). Nessuna riga `execution_decisions` o `portfolio_cycles` esiste prima delle 13:00 UTC quel giorno — i due soli scheduler che chiamano `open_trade()` in produzione (`portfolio_scheduler.py:1755,2864`) girano solo 14-21 UTC / dentro un ciclo. `tests/store/test_pg_store_stop_methods.py:71,95` chiama `PostgreSQLStore(use_pool=False)` su `DATABASE_URL` d'ambiente (nessuna guardia contro la produzione) e nel blocco `finally` esegue `cur.execute("DELETE FROM trades WHERE symbol = %s", (symbol,)); conn.commit()` — SQL grezzo, nessun logging di audit. Il file contiene esattamente 4 test con questo pattern (`test_load_frozen_stop_round_trip`, `test_fixed_mode_freezes_audit_fields`, `test_save_frozen_stop_round_trip`, `test_insert_stop_decision_and_shadow`), coerente con i 4 inserimenti per batch osservati.
* Descrizione: il codice dichiara esplicitamente l'invariante "P0-12: write audit row in the same transaction so a failed audit rolls back the trade (no unaudited trades can exist)" (`src/store/pg_store.py:868-869`) — ma questo protegge solo gli INSERT. Non esiste alcun meccanismo che auditi le DELETE sulla tabella `trades`, e oggi 16 righe sono state cancellate senza lasciare traccia se non il buco nell'`id` sequence e l'INSERT orfano in `audit_log`. La causa più probabile, per lettura diretta del codice, è l'esecuzione della suite `pytest` con `DATABASE_URL` puntato (per errore di ambiente) al Postgres di produzione — esattamente lo stesso meccanismo già diagnosticato per **F-028** (`tests/workers/test_rss_ingestion.py` che scrive in `ingestion_stats_daily` di produzione), il cui ticket TK-H avvertiva letteralmente: "il rischio vero è di perimetro — se la suite scrive qui, può scrivere altrove". Qui si è materializzato su `trades`, la tabella che alimenta l'intero P&L economico dell'osservazione.
* Impatto: nessun trade reale toccato oggi (simboli sintetici tipo `TEST_STOP_1`, non in watchlist). Ma l'esistenza del varco dimostra che, in un giorno diverso — o se un run di test viene interrotto prima del blocco `finally` di cleanup, o se un futuro test usa un simbolo che collide con la watchlist — la tabella `trades` può ricevere o perdere righe senza che l'audit log lo mostri. Qualunque misura di P&L economico (`scripts/economic_pnl_scoreboard.py`, lo scoreboard citato in memoria di progetto) e qualunque conteggio di trade per la finestra di osservazione erediterebbe silenziosamente l'inquinamento.
* Severità: **High** (Critical se un test futuro lascia un residuo non ripulito su un simbolo reale durante la finestra congelata).
* Confidenza: **High** sull'osservazione empirica (verificata su tre fonti indipendenti: gap di sequence, audit_log orfano, assenza di ogni altro chiamante di `open_trade()` in quella finestra oraria); **Medium-High** sulla causa esatta (non ho potuto confermare che `DATABASE_URL` fosse realmente puntato in produzione al momento dell'esecuzione — non ho log del comando pytest per il 08-14 — ma il pattern a 4 corrisponde esattamente ai 4 test del file, e la stessa classe di bug è già confermata per F-028).
* Azione consigliata: (1) aggiungere a `tests/store/test_pg_store_stop_methods.py` (e a ogni test che apre connessioni dirette) la stessa guardia già raccomandata per F-028/TK-H — rifiutare l'esecuzione se `DATABASE_URL` non punta a un host/DB esplicitamente marcato come test (es. suffisso `_test`, o whitelist di host); (2) aggiungere un trigger DB-level (non applicativo) che scriva `audit_log` su ogni DELETE/UPDATE distruttivo su `trades`, così l'invariante P0-12 copre anche le cancellazioni indipendentemente dal path applicativo che le esegue. Questo è un ticket di correttezza ammesso durante il freeze (test contro OBSERVATION_CHARTER: se non corretto, l'evidenza P&L futura può essere silenziosamente alterata).
* Test/monitor consigliato: assert giornaliero (nel job forense stesso, o in un check separato) che `COUNT(DISTINCT record_id) FROM audit_log WHERE table_name='trades' AND action='INSERT'` combaci con `COUNT(*) FROM trades` per gli id mai chiusi/cancellati nella finestra di osservazione; alert se emergono gap di sequence non spiegati da rollback legittimi.

### [DAY-202] Ricorrenza F-028 — righe fantasma `source='reuters'` in `ingestion_stats_daily` anche il 2026-08-14

* Tipo: Anomalia (ricorrenza di difetto già tracciato)
* Area: Data
* Evidenza:
  * file/log/tabella: `ingestion_stats_daily`
  * timestamp: `updated_at` 2026-08-14 11:51:47 UTC (pre-market, fuori da ogni finestra del beat 14-21 UTC)
  * snippet/query: `SELECT * FROM ingestion_stats_daily WHERE source='reuters' AND day='2026-08-14'` → `fetched=20, queued=20, discarded_no_ticker=5`; `SELECT COUNT(*) FROM news_log WHERE source='reuters'` → 0 su tutta la storia della tabella; nessuna voce `run-rss`/`run_rss_ingestion_worker` nello schedule di `celery_app.py`; `RSS_INGESTION_ENABLED` non impostata né su `worker` né su `beat` (default "0" nel codice → skip immediato).
* Descrizione: stessa dinamica già isolata in **F-028** — la riga esiste solo perché qualcosa ha eseguito `run_rss_ingestion_worker()` con `RSS_INGESTION_ENABLED` forzato a 1 (verosimilmente `tests/workers/test_rss_ingestion.py`) contro `DATABASE_URL` di produzione. L'orario (11:51 UTC, pre-market) è coerente con la serie di orari sparsi già registrata in F-028.
* Impatto: nessuno sul money path; contamina la tabella usata per misurare la copertura per fonte durante l'osservazione — vedi F-028 per l'impatto cumulato.
* Severità: Low (già tracciato, nessuna escalation oltre alla ricorrenza)
* Confidenza: High
* Azione consigliata: nessuna nuova — appendere l'occorrenza a F-028 (fatto in questa sessione nel ledger) e trattare come ulteriore prova a supporto del fix già raccomandato in TK-H, ora rafforzato da [DAY-201].
* Test/monitor consigliato: idem F-028.

### [DAY-203] `nav_change_today` non riconciliato con la variazione NAV osservata sugli snapshot dello stesso giorno

* Tipo: Anomalia
* Area: PnL
* Evidenza:
  * file/log/tabella: `portfolio_monitor_snapshots`
  * timestamp: 07:12:23 (NAV $110.307,36) e 20:00:00 (NAV $110.440,21, `nav_change_today`=−$23,60) UTC del 08-14
  * snippet/query: `SELECT as_of, nav, nav_change_today FROM portfolio_monitor_snapshots WHERE as_of::date='2026-08-14' ORDER BY as_of` (primo e ultimo record)
* Descrizione: la variazione NAV calcolata direttamente dagli snapshot di apertura e chiusura giornata
  (+$132,85) non coincide con il valore riportato dal sistema nel campo dedicato `nav_change_today`
  (−$23,60), scarto di $156,45 e segno discorde. Stessa famiglia di difetto di **F-003**
  (`combined_drawdown` vs `per_strategy_metrics.portfolio.drawdown` vs drawdown reale — tre numeri per
  la stessa grandezza), qui osservata su un campo NAV invece che su drawdown/daily_pnl.
* Impatto: nessuna perdita diretta; rischio di lettura errata del rendimento giornaliero durante
  l'osservazione se qualcuno usa `nav_change_today` come fonte primaria invece di ricalcolare dagli
  snapshot.
* Severità: Medium
* Confidenza: Medium (un solo giorno osservato per questo specifico campo; la famiglia di difetto è
  già confermata su altri campi in F-003 con 8 occorrenze)
* Azione consigliata: nessun fix in questo ciclo — appendere come nuova faccia di F-003 nel ledger
  (fatto in questa sessione) e lasciare che la ricorrenza guidi la priorità.
* Test/monitor consigliato: stesso di F-003 — riconciliazione automatica giornaliera fra tutte le
  fonti di "variazione NAV/drawdown" con alert se lo scarto supera una soglia fissa.

### [DAY-204] NO_NEWS su F (+3,46%) — nessuna catena decisionale

* Tipo: Anomalia (ricorrenza F-001)
* Area: News
* Evidenza: `news_log`/`sentiment_signals`/`execution_decisions` — zero righe per F il 08-14.
* Descrizione: vedi `docs/ALPHA_MISS_REPORT_2026-08-14.md` §3, §7 (già scritto in questa sessione).
  Mover al rialzo, direzione accessibile a un motore long-only.
* Impatto: costo congetturale $76,03 (size S4 tipica $2.200 × return pieno).
* Severità: Low (osservazione strutturale, non un bug)
* Confidenza: High
* Azione consigliata: nessuna nuova (congelato — la copertura news è taratura/capacità dati, non
  correttezza).
* Test/monitor consigliato: nessuno oltre al tracking già in corso in F-001.

### [DAY-205] Gate 0,30 scarta segnali di segno corretto (AVGO, ORCL) — ricorrenza F-009 al valore di design del gate

* Tipo: Corretto (comportamento a specifica) / Osservazione
* Area: Signal
* Evidenza: `sentiment_signals` id relativo ad AVGO 17:30 (−0,282→−0,226 post signal-velocity) e ORCL
  15:45/altri (−0,112/−0,039); vedi `docs/ALPHA_MISS_REPORT_2026-08-14.md` §3, §6, §7.
* Descrizione: prima occorrenza pulita di F-009 dopo il ripristino del gate di design a 0,30 (deroga
  #191, 07-08) — le occorrenze precedenti erano generate sotto un gate temporaneamente a 0,45 e non
  sono comparabili. Il gate funziona come da specifica; il collo di bottiglia è la magnitudine del
  segnale, non la soglia.
* Impatto: costo verificato **zero** — entrambi mover al ribasso, libro long-only, nessuna posizione
  detenuta.
* Severità: Low
* Confidenza: High
* Azione consigliata: nessuna (congelato dalla carta — taratura del gate).
* Test/monitor consigliato: nessuno oltre al tracking F-009 esistente.

### [DAY-206] Soppressione del log SKIP_FALLBACK su HOOD — ricorrenza F-006

* Tipo: Difetto di osservabilità
* Area: Signal / Ops
* Evidenza: 2 segnali fallback-only HOOD (15:45 −0,04, 17:01 +0,072), zero righe `execution_decisions`;
  vedi `docs/ALPHA_MISS_REPORT_2026-08-14.md` §3, §6, §7 per il meccanismo (`_record_fallback_drops`
  soppresso da un vecchio segnale ensemble dell'08-13 nel lookback di 96h).
* Descrizione: stesso meccanismo isolato l'08-11 su AVGO (ticket TK-F, ancora aperto).
* Impatto: nessun costo P&L (HOOD è mover al ribasso, long-only), ma la distribuzione delle cause di
  miss che alimenterà la falsificazione della domanda di uscita 1 è contaminata.
* Severità: Medium (osservabilità, non money path)
* Confidenza: High
* Azione consigliata: nessuna nuova — il ticket TK-F è già aperto.
* Test/monitor consigliato: idem TK-F.

### [DAY-207] 11/49 posizioni senza `stop_strategy` — ricorrenza F-002, oggi include un mover del giorno

* Tipo: Osservazione
* Area: PnL / Data
* Evidenza: `trades` — BAC, GOOGL, GS, MS, PBR, RIO, ROKU, SPY, UBS, UNH, XLE, tutte aperte 2026-07-10,
  `stop_strategy IS NULL`.
* Descrizione: stesso insieme dell'08-07/08-10/08-11/08-12. Novità di oggi: ROKU (+2,34%, uno dei
  mover della watchlist secondo `ALPHA_MISS_REPORT_2026-08-14.md` §2) appartiene a questo insieme non
  attribuibile — contribuisce da solo ≈+$15,35 di MTM stimato dei ≈+$21,41 totali della fetta legacy.
* Impatto: P&L non attribuibile a nessuna sleeve, confligge con la domanda di uscita 2 della carta
  (split P&L S1 vs SPY) finché queste posizioni restano aperte.
* Severità: Low (osservazione ricorrente, nessuna azione nuova richiesta dal freeze)
* Confidenza: Medium (costo stimato con qty×Δclose, non net_pnl realizzato — le posizioni restano
  aperte)
* Azione consigliata: nessuna nuova — F-002 resta aperto, nessun fix ammesso dal freeze (richiederebbe
  toccare posizioni vive).
* Test/monitor consigliato: nessuno oltre al tracking F-002.

## 11. False positive o aree risultate corrette

- **Nessun ordine sotto soglia**: verificato che nessuna BUY/SELL ha uno score `< 0,05` alla base
  (min score osservato oggi −0,300, i due BUY sono a +0,597 e +0,345).
- **Nessun pyramiding reale**: le 9 SKIP_PYRAMIDING sono il guard che funziona correttamente, non un
  bug — nessun BUY ripetuto >3 volte sullo stesso simbolo senza SELL intermedio.
- **Nessuna SELL con sentiment positivo (bug A5)**: non applicabile, zero SELL oggi.
- **Nessun fallback_used=True su tutti i simboli** (Ollama non "giù" per l'intera giornata): fallback
  rate 28,4%, in banda con le sedute recenti, non un evento di outage totale.
- **Nessun NO-ORDER anomalo**: ogni BUY ha un `execution_decisions` corrispondente con signal_id e
  order_id popolati; nessuna decisione "orfana" (BUY loggata senza trade, o trade senza decisione).
- **Nessuna race condition scheduler**: nessun ordine identico nello stesso minuto.
- **Paper/live**: nessuna ambiguità, confermato su ogni snapshot del giorno.
- **Timezone**: nessuna ambiguità — UTC confermato sia nel codice Celery sia nel DB Postgres
  (`SHOW timezone`).

## 12. Dati mancanti o non accessibili

- **API REST locale**: token fornito (`Bearer eJvMeuHhJS27FPugKIu4qKGgV7roIdLfcv7h20MwuQg`) rifiutato
  con `{"detail":"Invalid or expired JWT token"}` su `GET /api/decisions`. Non ho potuto usare gli
  endpoint applicativi come fonte primaria; ho sostituito con query SQL dirette (più autorevoli, ma
  bypassano qualunque logica di formattazione/filtro applicativa — se l'API applica un filtro non
  replicato in SQL, non l'ho visto). Query che servirebbe: rigenerare/validare il token e ripetere
  `curl $BASE/decisions|trades|signals|positions|orders?...` per un confronto diretto.
- **Log Docker `worker`/`worker-inference`/`beat` per il 2026-08-14**: assenti. I container sono stati
  ricreati il 2026-08-15T12:20:11Z (deploy successivo, confermato da `docker inspect --format
  '{{.State.StartedAt}}'`), e non esiste un archivio `docs/evidence/logs_2026-08-14/*.gz` (a differenza
  del 08-13). Impossibile ricostruire: latenza esatta delle chiamate LLM, testo di eventuali
  timeout/errori Ollama, eventuali WARNING/ERROR non altrimenti persistiti in tabelle. Query che
  servirebbe se un archivio esistesse: `zcat docs/evidence/logs_2026-08-14/worker.log.gz | grep -E
  "ERROR|WARNING|semaphore|fallback|Ollama"`.
- **Ollama uptime/downtime esatto per il 08-14**: non ricostruibile senza i log sopra. L'unico proxy
  disponibile è il fallback rate (28,4%, sentiment_signals) e l'eligibility rate (85,2% ineleggibile a
  livello di singola chiamata modello) — nessuno dei due implica direttamente un downtime del servizio,
  solo confidenza sotto soglia.
- **Posizioni broker Alpaca dirette**: non interrogate (nessuna chiamata broker per istruzione del
  protocollo); riconciliazione posizioni fatta solo contro `portfolio_monitor_snapshots.open_positions`
  (49) e il conteggio di `trades` aperti, non contro l'API Alpaca stessa.
- **Slippage/commissioni del giorno**: non popolate per nessuna riga (nessun trade chiuso oggi;
  `cost_bps`/`slippage_est` si valorizzano solo in chiusura).

## 13. Raccomandazioni immediate

1. **[DAY-201]** Aggiungere una guardia esplicita in `tests/store/test_pg_store_stop_methods.py` (e
   idealmente in ogni test con connessione diretta a `DATABASE_URL`) contro l'esecuzione accidentale
   sul Postgres di produzione — stesso fix già raccomandato per F-028/TK-H, ora con priorità più alta
   perché il varco tocca `trades` invece di una tabella di sole statistiche.
2. Aggiungere un audit trail anche per le DELETE su `trades` (trigger DB-level, indipendente dal path
   applicativo) — l'invariante P0-12 va esteso oltre gli INSERT.
3. Nessuna azione di taratura raccomandata: il money path del 2026-08-14 è corretto a specifica.

## 14. Test o monitor da aggiungere

- Check giornaliero automatico: gap nella sequence `trades_id_seq` non spiegato da un rollback
  applicativo noto → alert.
- Riconciliazione `audit_log` INSERT vs righe vive in `trades` (per id mai chiuso/cancellato
  legittimamente nella finestra di osservazione).
- Riconciliazione `nav_change_today` vs Δ(NAV apertura, NAV chiusura) calcolato dagli snapshot, con
  soglia di alert sullo scarto (F-003/DAY-203).
- (Già raccomandato in cicli precedenti, non ripetuto qui in dettaglio) monitor decay/rischio
  per-strategia invece che pipeline-globale (F-004), consegna Telegram degli alert (F-005).

## 15. Ticket tecnici suggeriti

- **TK-H (già aperto, F-028)**: rafforzato da [DAY-201] — guardia anti-produzione per i test DB-diretti,
  ora con evidenza che il rischio si è già esteso oltre `ingestion_stats_daily`.
- **Nuovo, da aprire**: audit trail per DELETE su `trades` (trigger DB o wrapper applicativo
  obbligatorio) — nessun ticket esistente lo copre; ammesso dal freeze come difetto di correttezza
  (senza, l'evidenza P&L futura può essere alterata senza traccia).

## 16. Stato sistema

- **Ollama up/down**: nessuna evidenza di downtime totale rilevabile dai dati residui in DB (fallback
  rate 28,4%, in banda con le sedute recenti). Ore di downtime esatte non ricostruibili — log Docker
  del 08-14 assenti (vedi §12).
- **FinBERT fallback rate**: 2/169 segnali (1,2%) sono `model_id='finbert'` — il fallback deterministico
  di ultima istanza è stato usato raramente oggi; il fallback prevalente è single-model LLM (39+7=46
  righe, 27,2%), non FinBERT.
- **Worker restart events**: nessun restart rilevabile all'interno della giornata 08-14 stessa (24
  cicli portfolio senza gap oltre 16 minuti, continuità operativa 14:07-19:52 UTC). Il container
  `worker`/`worker-inference`/`beat` risulta però riavviato il 2026-08-15T12:20:11Z (deploy successivo
  standard, non un crash durante la sessione di oggi) — è questo riavvio, insieme all'assenza di un
  archivio log per l'08-14, la causa della lacuna di log discussa in §12.
