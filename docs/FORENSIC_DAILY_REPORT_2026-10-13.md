# Forensic daily report — 2026-10-13 (martedì)

Analisi read-only eseguita il 2026-10-26. Timezone operativo: UTC (`celery_app.py`); DST USA in vigore (EDT), RTH = 13:30–20:00 UTC. Fonti: DB `trading` (solo SELECT), API REST locale, `logs/containers/{worker,beat,api}-2026-10-13.log`, `logs/deploy_reconcile_2026-10-13.log`, Redis (sola lettura), `ALPHA_MISS_REPORT_2026-10-13.md`, `market_daily.jsonl`. **Non esistono `worker-inference-2026-10-13.log` né `worker-news-stream-2026-10-13.log`, né alcun log container del 10-14.** I log esistenti terminano con l'ultima riga alle 16:08Z (worker 16:08:37, beat 16:08:07) benché i file risultino modificati alle 18:09–18:16.

## 1. Executive summary

- **Seduta senza pipeline: 0 news_log, 0 sentiment_signals, 0 llm_responses, 0 finbert_fallback_events, 0 execution_decisions, 0 portfolio_cycles, 0 ordini, 0 snapshot di monitoraggio.** Nessun ordine è stato generato, inviato o fillato (API `/orders`, `/trades`, `/decisions` senza righe del 10-13; il dossier alpha-miss conferma che Alpaca non registra ordini, nemmeno stop).
- **Terza seduta consecutiva senza consumatore `inference`** (assente dal 10-08 16:20Z; F-096). Lo stesso giorno si aggiunge un secondo guasto indipendente.
- **Redis MISCONF alle 11:03:12Z** (RDB non persistibile, disco host al 95%): il worker principale muore con `Unrecoverable error` e non riceve più task. Il processo resta in loop di reconnect (24/100 tentativi alle 16:08) e **riparte solo il 2026-10-15 16:10:03Z** (log `worker-2026-10-15.log`): ~53 h di worker morto, container "Up" per tutto il periodo (F-085).
- Il beat continua a emettere task nel vuoto: 4.388 errori `Couldn't apply scheduled task` fra 11:03 e 16:08 (3.656 `poll-telegram-updates`), inclusi 9 `portfolio-cycle`, 9 `run-execution`, 9 `sentiment-worker`, 9 `run-news-ingestion`, 9 `run-alpaca-ingestion` falliti.
- **Prima, dalle 06:14 alle 11:03Z, DNS irraggiungibile** (`NameResolutionError` su `paper-api.alpaca.markets` e `data.alpaca.markets`, ~660 warning/ora, 4 h 49 min) e `git fetch origin main` fallito alle 06:20/08:20/10:20/12:20. Nessun alert recapitato (0 sendMessage Telegram, 0 `mobile_notification_deliveries`; F-094).
- 39 posizioni detenute (S1 + S4) senza gestione per l'intera seduta: nessun ciclo, nessuna uscita per segnale, nessuna riconciliazione fill. Gli stop GTC restano al broker e non risultano fillati. Il libro ha subito il mercato: equity Alpaca 110.183,38 $ (−189,26 $ close-to-close, dal dossier; non verificato su altra fonte).
- Mover detenuti in calo (AMAT −6,69%, JNJ −5,73%, C −5,60%, MU −3,62%, CAT −3,33%) senza possibilità di reazione; 3 ENTRY_OPPORTUNITY NO_NEWS (INFY, ORCL, ERIC) non catturabili. Costo già stimato nell'alpha-miss (F-096: 288,65 $).
- Ledger: 0 finding nuovi, 5 esistenti riconfermati (F-085, F-096, F-094, F-027, F-001); costi non ricontati.

## 2. Verdict finale

**Processo non affidabile** (e per le fasi di decisione/ordini **non verificabile** a valle: non esistono eventi da verificare). Il layer di esecuzione non ha prodotto alcun ordine su dati invalidi, quindi non c'è violazione di safety osservabile. Ma la catena news→segnale→decisione→ordine è assente per l'intera seduta e il sistema non ha emesso alcun alert. La seduta va annotata come discontinuità nella serie osservata (3ª seduta senza sentiment e 1ª seduta con 0 cicli portfolio dal 2026-10-13, ripresa piena 2026-10-16); la registrazione nel charter spetta all'operatore (nessuna delle sedute è ad oggi registrata come rottura).

## 3. Timeline (UTC)

| Ora | Componente | Evento | Fonte |
|---|---|---|---|
| 00:00 | worker/beat | Regolare: mobile snapshot/alert/news-queue-census ogni minuto/5 min | worker/beat log |
| 00:00–06:13 | worker | SPY benchmark fetch fallisce (limite SIP, F-016) | worker log |
| 03:00 | performance-daily | Report giornaliero OK (IC 0,2914, ICIR 20,355), 0 fill riconciliati | worker log |
| 03:30 | retention | 0 righe cancellate | worker log |
| 05:55 | ingestion_stats_daily | Ultimo update del giorno: alpaca_benzinga fetched 26, queued 34, duplicates 107 | DB |
| 06:14 | rete | Inizio `NameResolutionError` verso Alpaca (clock/account/positions/orders) | worker log |
| 06:20 | ops | `git fetch origin main` fallito (anche 08:20, 10:20, 12:20) | deploy_reconcile |
| 11:03:00 | rete | Ultimo DNS warning (44 nell'ora 11) | worker log |
| 11:03:12 | worker | CRITICAL `Unrecoverable error: MISCONF`; il worker rientra in "recovery" e non consuma più task | worker log |
| 11:03:15 | beat | Primo `Message Error: Couldn't apply scheduled task` | beat log |
| 13:30 | beat | `regime-detector-premarket` emesso, mai eseguito | beat log |
| 14:00–16:07 | beat | Emessi (e falliti) 9 portfolio-cycle (14:07…16:07), 9 run-execution, 9 sentiment-worker, 9 ingestion, 8 reconcile-fills | beat log |
| 16:08 | worker | Reconnect 24/100 (backoff 32 s); ultima riga dei log disponibili | worker log |
| 20:00 | — | Nessuno snapshot `portfolio_monitor_snapshots` (ultimo 10-12 20:00, NAV 110.374,61) | DB |
| 22:20 | deploy_reconcile | "Già allineato a ec987cd5" | log |
| 10-15 16:10:03 | worker | Ripartenza: "Connected to redis", "ready" | worker-2026-10-15.log |

## 4. Tabella news ingest

| Fonte | fetched | queued | duplicates | discard_no_ticker | discard_stale | parse_fail | news_log creati |
|---|---:|---:|---:|---:|---:|---:|---:|
| alpaca_benzinga | 26 | 34 | 107 | 0 | 0 | 0 | 0 |
| gdelt_gkg | — (nessuna riga) | — | — | — | — | — | 0 |

`ingestion_stats_daily` per il 10-13 ha una sola riga (aggiornata 05:55:54Z, flusso WebSocket; `news-stream` log assente). `news_log`: **0 righe** per `created_at`, `fetched_at` del 10-13 (10-08: 160; 10-16: 205: nessuna riga fra i due). Coda `news_queue_census` a oggi: 1.652 messaggi, oldest 137,8 h (campione 10-26 13:30Z, non del 10-13). Tabella per ticker, top news, ticker ambiguity, timestamp futuri, sanitizzazione: **non valutabili** (nessuna news del giorno nel DB).

## 5. Tabella performance modelli LLM

| Modello | Richieste | Successi | Errori/timeout | Latenza | Note |
|---|---:|---:|---:|---|---|
| glm52 (Redis `config:sentiment_llm_models` = `glm52,gptoss`, letto oggi) | 0 | 0 | n/d | n/d | nessun `llm_responses` |
| gptoss | 0 | 0 | n/d | n/d | idem |
| FinBERT fallback | 0 | 0 | — | — | 0 righe `finbert_fallback_events` |

Nessun ciclo sentiment eseguito (9 `sentiment-worker` + 13 `sentiment-shadow-offsession` emessi dal beat, nessuno consumato). Tasso FinBERT fallback: non misurabile (0/0). Ollama up/down: **non determinabile** (nessuna chiamata, nessun log inference). Verifiche funzionali sul validatore, dedup, varianza, hallucination: non eseguibili per assenza di output; vedi F-054/F-055/F-087 (già in ledger).

## 6. Tabella segnali finali per ticker

Nessun segnale generato il 10-13 (`sentiment_signals` 0 righe; l'API `/signals` non ha righe fra 10-08 e 10-16). I segnali stantii usati dal dossier per i mover detenuti sono del 10-07/10-08 (AMAT 14786 +0,039, JNJ 14768 +0,090, C 14703 +0,250, MU 14808 −0,829, CAT 14644 −0,205).

## 7. Tabella ordini generati/eseguiti

Nessuno: `execution_decisions` 0, `portfolio_cycles` 0 (24 il 10-12), `trades` entry/exit del 10-13 0, ordini API 0, stop fill 0. NO-ORDER, roundtrip, pyramiding, SELL con sentiment positivo, score < 0,05 con ordini, ordini identici nello stesso minuto: **non applicabili** (nessun ordine).

## 8. Tabella PnL/rendimento

| Voce | Valore | Fonte / limite |
|---|---|---|
| PnL realizzato 10-13 | 0,00 $ | 0 uscite; dossier `book.realizzato` 0,0 |
| PnL non realizzato / variazione equity | −189,26 $ (110.372,64 → 110.183,38) | `ALPHA_MISS_REPORT` e `market_daily.jsonl` (equity Alpaca timbrata 10-14T00:00Z); non ricalcolato qui |
| Book open→close (39 posizioni) | +55,29 $ (S1 −85,94, S4 +141,23) | dossier `snapshot_apertura` |
| PnL per ticker | mancante | serve prezzo di chiusura 10-12/10-13 per posizione (barre Alpaca; `/api/positions` oggi riflette il 10-26) |
| Per strategia | S1 −85,94 / S4 +141,23 (open→close) | idem |
| Slippage / costi | 0 (nessun fill) | — |
| SPY / QQQ | −0,012% / −0,331% | `market_daily.jsonl` |
| Posizioni aperte prima / il 10-13 | 39 / 0 | — |

Il gap overnight non è scomponibile da DB: lo snapshot 10-12 20:00 dà NAV 110.374,61 e l'equity timbrata nel dossier 110.372,64: scarto di 1,97 $ non spiegato (non-finding: fonti diverse). Mancano snapshot del 10-13 (`portfolio_monitor_snapshots` 0 righe); query utile: barre giornaliere Alpaca 10-12/10-13 × quantità in `trades` aperti.

## 9. Analisi correttezza buy/sell

- Niente BUY/SELL: nessuna violazione di cooldown, pyramiding, stop-loss, signal flip o holding period osservabile.
- Corretto per omissione: nessun ordine su dati stale o LLM invalido (nessuna decisione).
- **Non corretto per assenza**: 5 posizioni in calo marcato (AMAT, JNJ, C, MU, CAT) non hanno potuto essere rivalutate; JNJ e C avevano earnings in giornata. Gli stop GTC non risultano scattati (nessun fill).
- Idempotenza Celery: i task emessi dal beat non sono stati consegnati (errore al publish), quindi non c'è doppia esecuzione; alla ripartenza del worker (10-15 16:10) la coda `inference` conteneva 15.677 messaggi (stato 10-26, non misura del 10-15). Non verificato se i task della seduta vengano riprocessati fuori finestra.
- Reconciliation: non verificabile per il 10-13. Allo stato corrente `trades` ha 38 aperti e il broker 38 posizioni, stessi simboli (BA entrato il 10-20, una posizione chiusa in seguito); ARM broker 0,0439 az. vs `trades` 2,0439 (stop GTC del 10-12 non registrato, F-048).
- Paper/live: broker `alpaca_paper` (snapshot 10-12); nessun ordine live.

## 10. Anomalie trovate

### [DAY-001] Redis MISCONF abbatte il worker principale; il worker non riparte per ~53 h e nessun alert
* Tipo: Bug / Rischio
* Area: Ops
* Evidenza:
  * file/log/tabella: `worker-2026-10-13.log` righe 6255+ (CRITICAL), `beat-2026-10-13.log` (4.388 ERROR), `worker-2026-10-15.log` ("ready" 16:10:04)
  * timestamp: 2026-10-13 11:03:12Z → 2026-10-15 16:10:03Z
  * snippet/query: `Unrecoverable error: ResponseError("MISCONF Redis is configured to save RDB snapshots…")`; `docker ps` worker "Up"; `SELECT count(*) FROM portfolio_cycles WHERE timestamp::date='2026-10-13'` = 0
* Descrizione: disco host al 95% (Redis ha già fallito per spazio il 18/06, 26/06, 13/08). `stop-writes-on-bgsave-error yes` blocca le scritture; il worker muore ma il container resta "Up", quindi nessun restart. Il beat continua a pubblicare e fallire. Lo stack è in "recovery" fino a intervento manuale il 10-15. Ricorrenza di F-085.
* Impatto: 0 cicli portfolio, 0 execution_decisions, 0 snapshot di monitoraggio nella seduta; 39 posizioni non gestite. Libro esposto al mercato (−189,26 $).
* Severità: High
* Confidenza: High
* Azione consigliata: ticket correttezza (non taratura): healthcheck del worker che fallisce se non consuma, alert su disco > 90%, e alert su MISCONF fuori da Redis/Telegram (canale indipendente).
* Test/monitor consigliato: monitor `portfolio_cycle_late` su canale che non dipenda da Redis/Celery; healthcheck docker su `celery inspect ping`.

### [DAY-002] Terza seduta senza worker-inference
* Tipo: Bug
* Area: LLM / Ops
* Evidenza:
  * file/log/tabella: assenza di `worker-inference-2026-10-13.log`; `news_log`, `sentiment_signals`, `llm_responses`, `finbert_fallback_events` = 0 righe del 10-13
  * timestamp: intera giornata (assente dal 10-08 16:20Z)
  * snippet/query: `SELECT count(*) FROM llm_responses WHERE generated_at::date='2026-10-13'` → 0; 9 `sentiment-worker` emessi dal beat
* Descrizione: il consumatore della coda `inference` non è attivo; si ripresenta F-096. Il beat accoda comunque.
* Impatto: segnale assente; mover NO_NEWS (INFY, ORCL, ERIC); costo già nell'alpha-miss (288,65 $).
* Severità: High
* Confidenza: High
* Azione consigliata: già coperto da F-096; il remediation richiede il riavvio automatico del consumatore.
* Test/monitor consigliato: allarme su `queue_depth` crescente con `n_consumers=0`.

### [DAY-003] Outage DNS 06:14–11:03Z senza alert, riconciliazione deploy fallita
* Tipo: Anomalia
* Area: Ops / Broker
* Evidenza:
  * file/log/tabella: `worker-2026-10-13.log` (3.100+ warning `NameResolutionError`), `deploy_reconcile_2026-10-13.log`
  * timestamp: 06:14:00 → 11:03:00Z; 06:20/08:20/10:20/12:20 fetch falliti
  * snippet/query: `Mobile snapshot: could not read market clock … NameResolutionError`
* Descrizione: pre-market e fino a 2 h dopo la fine della finestra di rete l'host non risolve DNS; l'ultimo warning coincide al secondo con il primo guasto Redis (11:03:00 vs 11:03:12): la correlazione fra i due eventi non è determinabile dai log. Il canale Telegram non poteva partire. Ricorrenza di F-094 (rete/host).
* Impatto: monitor mobile cieco (clock/account/positions/orders); nessun ordine in pre-market, quindi costo non stimabile.
* Severità: Medium
* Confidenza: High (evento) / Low (causa comune con DAY-001)
* Azione consigliata: indagare causa del guasto di rete e dello spazio disco.
* Test/monitor consigliato: dead-man switch esterno.

### [DAY-004] Log container incompleti: inference/news-stream del 10-13 e tutti i log del 10-14 mancanti
* Tipo: Non verificabile
* Area: Ops
* Evidenza:
  * file/log/tabella: `ls logs/containers | grep 2026-10-1[3-5]`
  * timestamp: 10-13 e 10-14
  * snippet/query: worker-inference/news-stream 10-13 assenti; nessun file del 10-14; worker/beat terminano 16:08Z con mtime 18:09
* Descrizione: la persistenza dei log (F-027) è incompleta proprio nei giorni di guasto. Non è determinabile il comportamento del worker dopo le 16:08 né se l'ingestion WebSocket fosse viva.
* Impatto: la verifica delle fasi LLM, news e restart è limitata.
* Severità: Medium
* Confidenza: High
* Azione consigliata: rotazione log con exit-code e dimensione, scritta fuori dal volume che si riempie.
* Test/monitor consigliato: controllo giornaliero "un file per servizio per giorno".

### [DAY-005] Copertura news nulla sull'intera watchlist
* Tipo: Anomalia
* Area: News
* Evidenza:
  * file/log/tabella: `market_daily.jsonl` (`watchlist_zero_news` 96); `news_log` 0 righe
  * timestamp: 2026-10-13
  * snippet/query: `SELECT count(*) FROM news_log WHERE created_at::date='2026-10-13'` → 0
* Descrizione: 96/96 simboli senza articoli: conseguenza di DAY-002, non scopertura delle fonti. Ricorrenza di F-001.
* Impatto: la serie NO_NEWS (quota > 0,6) è gonfiata da un guasto, non da copertura.
* Severità: Medium
* Confidenza: High
* Azione consigliata: annotare la seduta come rottura nel charter (operatore).
* Test/monitor consigliato: separare in `market_daily` NO_NEWS da `PIPELINE_DOWN`.

## 11. False positive o aree risultate corrette

- Nessun ordine fuori orario, duplicato, senza segnale o senza risk check: nessun ordine.
- Beat: nessun task schedulato duplicato; frequenza 15 min per portfolio-cycle rispettata fino al guasto.
- `performance-daily` (03:00) e `retention` (03:30) hanno eseguito regolarmente prima dei guasti.
- `deploy_reconcile`: "Già allineato a ec987cd5" alle 14:20, 18:20, 20:20; i 4 fallimenti sono la conseguenza del DNS (non un difetto di deploy).
- Il regime: `regime:current` esiste oggi (TTL 205.221 s), ma il `regime-detector` delle 13:30 non è stato eseguito; la presenza del valore al 10-13 non è determinabile.

## 12. Dati mancanti o non accessibili

- Log container post-16:08Z, worker-inference e news-stream del 10-13, tutto il 10-14.
- Redis log del 10-13 (`docker logs alembic-redis-1` senza righe per la data; il log contiene solo eventi di altre date).
- Prezzi di chiusura per posizione e PnL per ticker (query: barre 1D Alpaca × `trades` aperti al 10-12).
- Stato posizioni a fine giornata del 10-13 (le API riflettono il 10-26).
- Causa del DNS e del riempimento disco (non ricostruibile).

## 13. Raccomandazioni immediate

1. Nessuna taratura proposta: restano ammessi solo difetti di correttezza (monitoraggio, healthcheck, alert).
2. Liberare/monitorare lo spazio disco host (95%) e configurare alert di soglia indipendenti da Redis/Celery.
3. Healthcheck del worker che fallisca su `Unrecoverable error` o perdita del consumer, con riavvio automatico (oggi container "Up" ma morto).
4. Alert out-of-band (Telegram o mail con timeout) quando `portfolio_cycle_late`, `queue_depth` senza consumatori o MISCONF persistono più di 15 min in RTH.
5. Registrare nel charter le sedute 10-09, 10-12, 10-13, 10-14, 10-15 come rottura della serie (operatore).

## 14. Test o monitor da aggiungere

- Test che il worker esca con codice non zero su `MISCONF` così che Docker lo riavvii.
- Monitor "task emessi dal beat vs task ricevuti dal worker" per `portfolio-cycle`/`sentiment-worker`.
- Controllo giornaliero di completezza dei log container per servizio.
- `market_daily`: campo `pipeline_down` distinto da `NO_NEWS`.

## 15. Ticket tecnici suggeriti

- **T1** Healthcheck + auto-restart del worker (F-085, DAY-001).
- **T2** Alert di disco e MISCONF su canale indipendente (F-085/F-094).
- **T3** Supervisione di `worker-inference` con riavvio automatico (F-096).
- **T4** Persistenza dei log fuori dal disco che si riempie (F-027).
- **T5** `market_daily`: distinguere guasto di pipeline da assenza di news (F-001).

## 16. Stato sistema

- Ollama: up/down **non determinabile** (nessuna chiamata, nessun log inference). Downtime consumatore sentiment: 24 h (10-13), ~5 giorni cumulati dal 10-08.
- Worker principale: morto 11:03:12Z 10-13 → 16:10:03Z 10-15 (~53 h). Beat sempre attivo. Redis: bgsave ok oggi, MISCONF attivo il 10-13 per almeno 11:03–16:08Z (fine intervallo non osservabile).
- Rete: DNS irraggiungibile 06:14–11:03Z (4 h 49 min).
- FinBERT fallback rate: 0/0 decisioni (nessuna decisione).
- Worker restart events il 10-13: nessuno riuscito (un ingresso in "recovery" alle 11:03:16, con reconnect 24/100 alle 16:08).
- Ledger aggiornato: F-085, F-096, F-094, F-027, F-001 (nessun finding nuovo).
