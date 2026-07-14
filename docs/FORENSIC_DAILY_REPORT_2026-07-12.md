# Forensic Daily Report — 2026-07-12

Analista: Trading Systems Forensic Analyst + Senior Backend Engineer + Quant Operations Reviewer (sessione autonoma, read-only)
Generato: 2026-07-13, ~12:30–13:30 UTC (invocazione cron `30 14 * * 1-5` → 14:30 CEST)
Timezone operativo: **UTC**, esplicito in `src/workers/celery_app.py:51` (`timezone="UTC", enable_utc=True`) — nessuna ambiguità sul dato grezzo.
Market hours nominali: 13:30–20:00 UTC (NYSE 9:30–16:00 ET, orario estivo EDT). Finestra operativa configurata nei cron pipeline: 14:00–21:00 UTC (buffer ±30 min). **Ambiguità minore trovata**: i commenti in `celery_app.py` (righe 5, 66, 129, 200) etichettano questa finestra come "= 9am-4pm ET", che è corretto solo sotto EST (UTC-5, inverno); a luglio (EDT, UTC-4) 14:00–21:00 UTC corrisponde a 10:00–17:00 ET, non 9:00–16:00. Il crontab stesso è in UTC puro e non è affetto da DST — è solo il commento a essere stale/fuorviante (vedi [DAY-008]).

---

## 1. Executive Summary

Il 2026-07-12 è una **domenica**: nessuna riga in `news_log`, `sentiment_signals`, `llm_responses`, `execution_decisions`, `trades`, `portfolio_cycles`, `ingestion_stats_daily`, `stop_decisions`, `stop_shadow_log`, `weight_update_log`, `fallback_counters`. Questo è **comportamento corretto**: tutti i job pipeline-critici (`sentiment-worker`, ingest news/GDELT, `portfolio-cycle`, `regime-detector`) sono gated `day_of_week="1-5"` in `celery_app.py`. Gli unici job che girano 7/7 (`decay-monitor` 21:00 UTC, `risk-monitor` 22:30 UTC) hanno prodotto output regolare ma basato su dati fermi a venerdì 07-10.

**Il vero finding della giornata è a monte, nell'automazione stessa che genera questi report**: lo script `scripts/daily_analysis.sh` è schedulato via crontab di sistema `30 14 * * 1-5` (feriali) ma calcola `DATE_TARGET=$(date -d "yesterday")`. Di lunedì, "ieri" è domenica — un giorno strutturalmente vuoto — mentre **venerdì (l'ultimo giorno di mercato reale) non viene mai analizzato**: l'inventario dei report esistenti conferma zero report generati per un venerdì in 5 settimane di storico (`docs/FORENSIC_DAILY_REPORT_2026-07-{02,05,07,08,09}.md` = gio/dom/mar/mer/gio). Questo report stesso ne è la prova vivente. Vedi [DAY-001].

Findings secondari: (a) log Docker del giorno persi di nuovo — i container `worker/worker-inference/api/beat` sono stati ricreati 2026-07-13 07:43:28 UTC per il deploy F6/frontend, azzerando il buffer log per il 07-12 (pattern ricorrente, già visto 07-08→07-09→07-10); (b) 3 righe di test (`TEST_STOP_1/2/3`, notional $1000, score 0.02) sono state inserite nella tabella **di produzione** `trades` sabato 2026-07-11 22:55:07 UTC e poi rimosse senza traccia auditata (il trigger di audit su `trades` registra solo INSERT, mai DELETE/UPDATE — 99/99 righe storiche sono INSERT); (c) il `decay-monitor` continua a confrontare per S1/S2/S4 lo **stesso** valore attuale globale (IC/hit-rate/Sharpe/drawdown non sono per-strategia nella query, commento esplicito nel codice) contro baseline diverse, producendo 2 alert CRITICAL identici×3 strategie senza alcun dispatch verso Telegram/PagerDuty (solo `log.critical`, e quel log per il 07-12 è tra quelli persi). NAV/posizioni sostanzialmente piatte nel weekend (nessun trade, nessuna violazione).

## 2. Verdict Finale

**OK con warning** per la giornata target in sé (comportamento corretto, nessuna anomalia trading), mai **anomalie significative** per il processo di monitoraggio che la produce: l'automazione forense quotidiana ha un bug strutturale (off-by-one sul weekend) che le impedisce sistematicamente di coprire i venerdì, e gli alert CRITICAL del weekend (decay-monitor) non hanno alcun canale di notifica indipendente dai log persi. Nessun rischio per capitale/esecuzione rilevato per il 07-12.

---

## 3. Timeline del 2026-07-12 (UTC)

| Ora UTC | Componente | Evento | Stato | Fonte |
|---|---|---|---|---|
| 00:00–23:59 | `sentiment-worker`, `run-news-ingestion` (benzinga+GDELT), `portfolio-cycle`, `regime-detector`, `loss-feedback-check` | Nessuna esecuzione — gate `crontab(day_of_week="1-5")` | Atteso (domenica) | `src/workers/celery_app.py` righe 70,85,90,116,126,134,145,167,187,205,221,229 |
| 21:00:00.06 | `decay_monitor_task.run_decay_check` (gira 7/7, no gate weekday) | 12 righe inserite in `decay_reports` (S1/S2/S4 × 4 metriche); IC e Sharpe **CRITICAL** per tutte e 3 le strategie, hit_rate/max_drawdown NORMAL | ⚠️ CRITICAL (dato stale, vedi [DAY-005]) | `decay_reports` id 409–420 |
| 22:30:00.64 | `risk_monitor` (gira 7/7) | Snapshot: NAV 110.077,71 USD, exposure 26,23%, drawdown combinato 5,45%, `alerts=[]` | OK | `risk_reports` id 30 |
| 22:00 (schedulato) | `forward_return_worker` (gira 7/7) | Nessun nuovo segnale del 07-12 da processare (0 righe); backlog 07-09/07-10 resta a 0/294 e 0/261 forward_return popolati | Invariato da report precedenti | `sentiment_signals` |
| — | Log container `worker/worker-inference/api/beat` | **Persi**: container ricreati 2026-07-13 07:43:28 UTC (deploy commit `237e660`/`d3ce750`), buffer log azzerato | Non verificabile oltre DB | `docker inspect`, `git log` |

**Nota metodologica**: la timeline è ricostruita interamente da Postgres (`decay_reports`, `risk_reports`, `sentiment_signals`, `trades`) + Redis + API REST, perché i log container del giorno non esistono più (container recreate il giorno dopo). Nessun evento di rete/Alpaca è stato osservato (mercato chiuso, nessun ordine).

---

## 4. Tabella News Ingest

| Fonte | Righe in `news_log` (07-12) |
|---|---|
| alpaca_benzinga | 0 |
| gdelt_gkg | 0 |

Nessuna news ingerita: `run-news-ingestion`/`run-alpaca-ingestion`/GDELT sono gated `day_of_week="1-5"` (righe 129, 145 di `celery_app.py`), coerente con l'assenza totale di righe. Ultimo item pre-weekend: **2026-07-10 21:47:12 UTC** (`news_log`, `sentiment_signals`). Nessun timestamp futuro/campo mancante da verificare — non ci sono righe.

**Confidenza: Alta** (assenza confermata sia da conteggio DB sia da gate esplicito nel codice — due fonti indipendenti concordanti).

---

## 5. Tabella Performance Modelli LLM

| Modello | Richieste 07-12 |
|---|---|
| glm-5.2:cloud | 0 |
| kimi-k2.6:cloud | 0 |

Zero chiamate ensemble/FinBERT nel giorno (nessun segnale da valutare). Ultima attività: 2026-07-10, 64 risposte glm-5.2 + 64 kimi-k2.6 (pari, coerente con ensemble bilanciato quel giorno). `llm_budget`: ultimo giorno con spesa registrata 2026-07-10 (0,3052 USD cumulativo, `budget_exhausted=false`). `fallback_counters.consecutive_fallback = 0` dal 2026-07-10 21:47 (reset da un successo ensemble, invariato nel weekend).

**Nota di configurazione (non verificabile per il 07-12, nessuna chiamata da cui dedurlo)**: la chiave Redis `config:sentiment_llm_models` legge attualmente `"all"`, non la coppia esplicita `glm52,gptoss` indicata come live al 2026-07-11 nella documentazione interna. Le 128 risposte dell'ultimo giorno attivo (07-10) usano comunque glm-5.2+kimi. Non è possibile stabilire da qui se/quando la chiave sia stata modificata o azzerata — segnalato come dato da verificare, non come anomalia del 07-12.

**Confidenza: Alta** sull'assenza di chiamate; **Bassa** sulla nota di configurazione (fuori scope temporale della giornata).

---

## 6. Tabella Segnali Finali per Ticker

Nessun segnale generato il 07-12 (0 righe `sentiment_signals`). Nessuna soglia valutata, nessuna decisione presa. Tabella non applicabile.

---

## 7. Tabella Ordini Generati/Eseguiti

Nessun ordine generato, inviato o eseguito il 07-12 (0 righe `execution_decisions`, `trades`; API `/orders` non mostra alcun ordine datato 07-11 o 07-12 — l'ultimo ordine risale al 2026-07-10). `execution.engine=portfolio` confermato invariato da configurazione; nessuna violazione paper/live possibile in assenza di ordini.

---

## 8. Tabella PnL/Rendimento

| Metrica | Venerdì 07-10 EOD (risk_reports id 28) | Weekend 07-11/07-12 (risk_reports id 29/30, identici) | Δ |
|---|---|---|---|
| NAV | 110.099,21 USD | 110.077,71 USD | **-21,50 USD (-0,02%)** |
| Exposure | 26,24% | 26,23% | ~invariato |
| Drawdown combinato | 5,4494% | 5,4494% | invariato |

Nessun trade nel weekend → il delta NAV (-21,50 USD) non è PnL realizzato/non realizzato da attività, ma **drift di valorizzazione weekend lato Alpaca** (marcatura fine settimana su prezzi/dividendi, non da nuove posizioni). Non inventiamo l'attribuzione esatta: per confermarla servirebbe l'endpoint Alpaca account-activities per il weekend, non interrogato in questa sessione (read-only, fuori dagli endpoint indicati).

Posizioni correnti (interrogate ora, lunedì pre-apertura — riflettono ancora l'ultima marcatura disponibile, non un evento specifico del 07-12): 40 simboli, market value totale **28.747,21 USD**, PnL non realizzato aggregato **-105,69 USD**. Maggiori variazioni: MU -17,84 (-5,52%), SOXX -13,43 (-2,43%), MRVL -12,81 (-4,18%), AMAT -12,24 (-2,71%), ASML -11,97 (-2,06%); miglior performer BP +19,17 (+2,97%).

**Dati mancanti**: nessun accesso in questa sessione a slippage/commissioni granulari per-trade del weekend (non pertinente, zero trade) né a un breakdown PnL per strategia specifico del 07-12 (tabella `trades` non ha righe quel giorno da cui derivarlo).

---

## 9. Analisi Correttezza Buy/Sell

Non applicabile nel merito (zero ordini il 07-12) — tutti i controlli richiesti (stop-loss rispettati, signal flip, max holding, rebalance band, duplicati, ordini fuori orario, dati stale, LLM non valido, circuit breaker, idempotenza, riconciliazione) sono **vacuously true** per assenza di eventi. L'unico controllo con esito concreto: **nessun ordine è stato generato fuori dal gate weekday** — verificato sia lato DB (0 righe) sia lato codice (`day_of_week="1-5"` su tutti i task che potrebbero generare ordini: `portfolio-cycle`, `run-execution`, `loss-feedback-check`). Nessuna violazione trovata.

---

## 10. Anomalie Trovate

### [DAY-001] Automazione forensic giornaliera: bug off-by-one sul weekend — i venerdì non vengono mai analizzati

* Tipo: Bug
* Area: Ops
* Evidenza:
  * file/log/tabella: `scripts/daily_analysis.sh` (riga `DATE_TARGET=$(date -d "yesterday" +%Y-%m-%d)`), crontab utente (`30 14 * * 1-5 .../daily_analysis.sh`), `logs/daily_analysis_2026-07-13.log`
  * timestamp: cron avviato 2026-07-13T12:30:01Z, target calcolato `2026-07-12`
  * snippet/query: inventario `docs/FORENSIC_DAILY_REPORT_*.md` → date presenti 2026-07-02 (gio), 2026-07-05 (dom), 2026-07-07 (mar), 2026-07-08 (mer), 2026-07-09 (gio); **nessun venerdì in 5 settimane**
* Descrizione: il cron di sistema gira solo nei giorni feriali (1-5, lun-ven), ma calcola sempre "ieri" come target. Di lunedì "ieri" è domenica (giorno strutturalmente vuoto lato trading); di conseguenza il venerdì — l'ultimo vero giorno di mercato della settimana, quello con più probabilità di chiusure di posizione a fine settimana, stop-loss, rebalance pre-weekend — non viene **mai** coperto da un run dedicato. Il gap si è già materializzato prima: 2026-07-05 (report esistente) copre un'altra domenica con lo stesso meccanismo, e il gap del 07-03 (venerdì, mai analizzato) è collegato al buco pipeline multi-giorno già documentato nel report del 07-05.
* Impatto: un'intera classe di giornate di mercato (tutti i venerdì) è invisibile al processo di audit automatico. Se un'anomalia si manifesta o si aggrava proprio di venerdì (es. chiusure pre-weekend, stop-loss multipli, rebalance di fine settimana), l'unico modo per scoprirla è un controllo umano manuale o l'inferenza indiretta dal report del lunedì successivo (che oggi guarda alla domenica, non al venerdì).
* Severità: High
* Confidenza: High
* Azione consigliata: cambiare la logica di calcolo di `DATE_TARGET` per usare "l'ultimo giorno di mercato" invece di "ieri" — es. se `date -d yesterday` cade di sabato o domenica, retrocedere al venerdì precedente; oppure aggiungere esplicitamente un run il sabato che analizzi il venerdì appena chiuso (il crontab attuale esclude sabato/domenica: `1-5`). Alternativa più semplice: aggiungere una seconda entry crontab il sabato mattina con lo stesso script, così sabato analizza venerdì e lunedì analizza domenica (accettando che la domenica resti quasi sempre vuota, ma senza più saltare il venerdì).
* Test/monitor consigliato: aggiungere un controllo settimanale (es. script separato) che verifichi come inventario `docs/FORENSIC_DAILY_REPORT_*.md` copra tutti i 5 giorni feriali della settimana precedente, e alert se manca un venerdì (o qualunque feriale).

### [DAY-002] Righe di test inserite nella tabella di produzione `trades` senza traccia di rimozione auditata

* Tipo: Anomalia
* Area: Data / Ops
* Evidenza:
  * file/log/tabella: `audit_log` id 5399-5401, tabella `trades`
  * timestamp: 2026-07-11 22:55:07 UTC (sabato, fuori dal giorno target ma scoperto durante questo sweep)
  * snippet/query: `audit_log.details` = `{"score": 0.02, "symbol": "TEST_STOP_1", "entry_notional": 1000.0, "entry_order_id": "test-order-1"}` (e `TEST_STOP_2`/`TEST_STOP_3` analoghe, `record_id` 290/291/292); `SELECT count(*), max(id) FROM trades` → 288 righe, max id 289 (le righe 290-292 non esistono più); `SELECT action, count(*) FROM audit_log WHERE table_name='trades'` → 99/99 righe sono `INSERT`, **zero** `DELETE`/`UPDATE` mai registrati per questa tabella
* Descrizione: 3 righe con simboli e `entry_order_id` chiaramente fittizi (`TEST_STOP_*`, `test-order-N`) sono state scritte nella tabella `trades` sull'istanza Postgres condivisa (`alembic-postgres-1`, la stessa che alimenta dashboard/API/report), presumibilmente da una suite di test (naming coerente con lo sviluppo stop-loss in corso sul branch `stop-loss-redesign` — tabelle `stop_decisions`/`stop_shadow_log` sono infatti nuove). Le righe sono state successivamente rimosse, ma il trigger di audit su `trades` cattura solo INSERT: non esiste alcuna riga DELETE/UPDATE nella storia della tabella, quindi la rimozione stessa non è auditabile né il meccanismo (DELETE esplicita? TRUNCATE? script di cleanup?) è ricostruibile da qui.
* Impatto: (a) mancanza di isolamento test/produzione sul DB condiviso — un bug nel cleanup del test (o un test lasciato a metà) potrebbe lasciare `TEST_*` permanentemente in `trades`, contaminando PnL/exposure/audit reali; (b) il gap nell'audit trigger (INSERT-only su `trades`) significa che **qualunque** cancellazione di una riga di trade reale — non solo di test — non lascerebbe traccia, il che è un problema di auditabilità più ampio del singolo incidente.
* Severità: Medium
* Confidenza: High (evidenza diretta in audit_log + conteggio trades)
* Azione consigliata: (1) verificare con il branch `stop-loss-redesign` se la sua suite di test punta a `alembic-postgres-1` invece che a un DB/container di test isolato, e correggere la configurazione dei test; (2) estendere il trigger di audit su `trades` (e idealmente sulle altre tabelle finanziarie) per catturare anche `DELETE`/`UPDATE`, non solo `INSERT`.
* Test/monitor consigliato: query periodica di sanity-check (`SELECT count(*) FROM trades WHERE symbol LIKE 'TEST%' OR entry_order_id LIKE 'test%'`) da eseguire come parte del report giornaliero o di un healthcheck CI; alert se >0.

### [DAY-003] Log Docker del 2026-07-12 persi — pattern ricorrente da almeno 3 settimane

* Tipo: Anomalia (ricorrente)
* Area: Ops
* Evidenza:
  * file/log/tabella: `docker inspect -f '{{.State.StartedAt}}'` per `alembic-worker-1`/`worker-inference-1`/`api-1`/`beat-1` → `2026-07-13T07:43:28Z`; `alembic-frontend-1` → `2026-07-13T07:26:17Z`; `git log` mostra commit `237e660`/`d3ce750`/`22c8fe5` alle 07:09–07:36 UTC del 07-13 (deploy F6 vol-target + fix nginx frontend)
  * timestamp: 2026-07-13 07:26–07:43 UTC (giorno successivo al target)
  * snippet/query: `docker compose logs worker --since 60h 2>&1 | grep "2026-07-12"` → 0 righe
* Descrizione: i container applicativi sono stati ricreati la mattina del 07-13 per un deploy legittimo (F6 flip `target_vol` 0.10→0.12, fix nginx), il che azzera il buffer di log Docker per il container precedente. Poiché il giorno target (07-12) non aveva comunque attività pipeline, l'impatto pratico oggi è basso, ma il pattern (log del giorno persi al primo redeploy successivo) è lo stesso già segnalato nei report del 07-08/07-09/07-10 ed è strutturale: qualunque anomalia intraday non ancora finita in una tabella Postgres/audit_log diventa irrecuperabile non appena c'è un redeploy il giorno dopo.
* Impatto: nessuna perdita di informazione trading-rilevante per il 07-12 specificamente (zero attività), ma conferma che il sistema non ha ancora una persistenza dei log applicativi indipendente dal ciclo di vita del container (es. driver di logging esterno, spedizione a un log aggregator).
* Severità: Medium
* Confidenza: High
* Azione consigliata: configurare un logging driver Docker persistente (es. `json-file` con `max-size`/`max-file` già a posto ma copiato su volume esterno, oppure spedizione a un aggregator leggero) così i log sopravvivono ai `docker compose up -d --force-recreate`.
* Test/monitor consigliato: controllo settimanale che confronti `docker inspect StartedAt` con la copertura temporale dei log recuperabili; alert se il gap supera 24h.

### [DAY-004] Nessuna attività pipeline il 2026-07-12 — comportamento corretto (domenica)

* Tipo: Corretto
* Area: Data
* Evidenza:
  * file/log/tabella: `src/workers/celery_app.py` righe 70,85,90,116,126,134,145,167,187,205,221,229 (`day_of_week="1-5"`); conteggi 0 su `news_log`, `sentiment_signals`, `llm_responses`, `execution_decisions`, `trades`, `portfolio_cycles`, `ingestion_stats_daily`, `stop_decisions`, `stop_shadow_log`, `weight_update_log`, `fallback_counters` per l'intervallo `[2026-07-12 00:00, 2026-07-13 00:00)`
  * timestamp: —
* Descrizione: tutti i job che potrebbero generare news/segnali/decisioni/ordini sono esplicitamente gated ai giorni feriali. L'assenza totale di righe è la conferma diretta che il gate funziona come da codice, non un fallimento silenzioso.
* Impatto: nessuno — è il comportamento atteso.
* Severità: Low
* Confidenza: High
* Azione consigliata: nessuna.
* Test/monitor consigliato: nessuno specifico (già coperto da [DAY-001], che verifica la copertura del report stesso).

### [DAY-005] `decay-monitor` confronta lo stesso valore aggregato globale contro baseline diverse per S1/S2/S4 — alert CRITICAL non davvero indipendenti per strategia

* Tipo: Bug (pre-esistente, non introdotto il 07-12)
* Area: Risk
* Evidenza:
  * file/log/tabella: `src/workers/decay_monitor_task.py`, funzione `_fetch_actual_metrics` — commento esplicito nel codice: *"Metrics are pipeline-global (no strategy_id column in the table)"*; query IC/hit-rate su `sentiment_signals` e Sharpe/drawdown su `portfolio_daily_state` **senza filtro per strategia**
  * timestamp: 2026-07-12 21:00:00 UTC
  * snippet/query: `decay_reports` id 409-420 → `actual_value` per `ic` = 0.004996792162564116 e per `sharpe` = -3.260253341770345, **identici byte-per-byte** su tutte e 3 le righe S1/S2/S4; stesso pattern confermato su 2026-07-10 (id 385-396, trading day), quindi non è un artefatto della domenica
* Descrizione: il job calcola un'unica metrica IC/hit-rate/Sharpe/drawdown a livello di intero portafoglio e la confronta contro 3 baseline diverse (S1: ic 0.035, S2: 0.042, S4: 0.028 — da `_BASELINES` nel codice), producendo 3 `decay_score` diversi ma da un solo dato in ingresso realmente indipendente. Il risultato — CRITICAL su IC e Sharpe per tutte e 3 le strategie simultaneamente — è garantito matematicamente muoversi in lockstep, indipendentemente dalla performance reale di ciascuna strategia presa singolarmente. Un operatore che legga 3 alert CRITICAL distinti potrebbe ragionevolmente concludere che tutte e 3 le strategie stiano degradando in modo indipendente, quando in realtà è un solo segnale di qualità pipeline-wide triplicato.
* Impatto: falsa impressione di ampiezza del problema (3 strategie in CRITICAL vs 1 segnale reale); nessun impatto diretto su esecuzione (il job non blocca trading, solo logga/registra). Aggravato dal fatto che l'unico canale di notifica è `log.critical(...)` (nessun Telegram/PagerDuty in questo task) e i log Docker del 07-12 sono persi ([DAY-003]) — quindi l'alert CRITICAL di ieri è oggi visibile solo interrogando `decay_reports` direttamente.
* Severità: Medium
* Confidenza: High
* Azione consigliata: aggiungere una colonna `strategy_id` a `sentiment_signals`/estendere `portfolio_daily_state` per calcolare IC/Sharpe/hit-rate/drawdown realmente per-strategia; nel frattempo, documentare esplicitamente nel report/alert che il valore è pipeline-wide e non per-strategia, per evitare letture fuorvianti.
* Test/monitor consigliato: assert nei test del decay monitor che `actual_value` differisca per strategia quando i dati sottostanti lo permettono; instradare gli alert CRITICAL anche a un canale persistente (Telegram/DB dedicato) indipendente dai log container.

### [DAY-006] NAV/posizioni piatte nel weekend — nessuna anomalia, drift di valorizzazione minimo

* Tipo: Corretto
* Area: PnL
* Evidenza:
  * file/log/tabella: `risk_reports` id 28 (07-10, NAV 110.099,21) vs id 29/30 (07-11/07-12, NAV 110.077,71, identici tra loro)
  * timestamp: 2026-07-10 22:30 → 2026-07-12 22:30 UTC
* Descrizione: variazione di -21,50 USD (-0,02%) tra l'EOD di venerdì e gli snapshot del weekend, senza alcun trade nel mezzo (0 righe `trades` 07-11/07-12). Compatibile con marcatura weekend lato broker (dividendi/adeguamento prezzi), non con attività di trading.
* Impatto: nessuno.
* Severità: Low
* Confidenza: Medium (il delta è piccolo e plausibile, ma la causa esatta — dividendo vs timing della marcatura — non è stata verificata via endpoint Alpaca account-activities, fuori scope di questa sessione)
* Azione consigliata: nessuna azione immediata; se il pattern si ripete con delta più ampi, verificare `account_activities` Alpaca per isolare la causa.
* Test/monitor consigliato: nessuno specifico.

### [DAY-007] Backlog `forward_return` ancora a zero per 07-09 e 07-10

* Tipo: Ambiguità (pre-esistente)
* Area: Data
* Evidenza:
  * file/log/tabella: `sentiment_signals` — 07-09: 0/294 con `forward_return` popolato; 07-10: 0/261; per contro 07-06/07/08 mostrano recupero parziale (4/109, 18/294, 13/227)
  * timestamp: verificato 2026-07-13 12:30 UTC
* Descrizione: il worker `forward_return` (schedulato 22:00 UTC, gira 7/7) non ha ancora popolato i ritorni forward per gli ultimi 2 giorni di mercato con dati potenzialmente maturi (07-10 richiede la chiusura di lunedì 07-13, non ancora avvenuta al momento del check — plausibile; ma 07-09 richiederebbe solo la chiusura di venerdì 07-10, **già disponibile**, e risulta comunque a zero). Non è un problema introdotto il 07-12 (che non ha comunque segnali), ma resta un gap aperto già segnalato nel report del 07-09 e non ancora chiuso.
* Impatto: alimenta l'IC quasi-zero usato dal decay-monitor ([DAY-005]) e dal ribilanciamento pesi LLM, con rischio di continuare a operare su dati di qualità degradata.
* Severità: Medium
* Confidenza: Medium (non è stato ispezionato il codice del worker in questa sessione, solo l'evidenza dai dati)
* Azione consigliata: verificare il worker `forward_return` per capire perché 07-09 (dati di prezzo disponibili) non è stato processato.
* Test/monitor consigliato: alert se `forward_return` resta NULL per righe più vecchie di N+2 giorni di mercato rispetto alla loro `created_at`.

### [DAY-008] Commenti DST-incoerenti in `celery_app.py` (ambiguità documentale, non funzionale)

* Tipo: Ambiguità
* Area: Ops
* Evidenza:
  * file/log/tabella: `src/workers/celery_app.py` righe 5, 66, 129, 200 — es. *"Sentiment Worker every 15 min during market hours (Mon-Fri 14:00-21:00 UTC = 9am-4pm ET)"*
  * timestamp: —
* Descrizione: 14:00-21:00 UTC in orario legale estivo (EDT, UTC-4, vigente a luglio) corrisponde a 10:00-17:00 ET, non "9am-4pm ET" (che varrebbe solo sotto EST invernale, UTC-5). Il crontab è comunque espresso in UTC puro (`enable_utc=True`), quindi **non c'è alcun bug funzionale**: la finestra 14:00-21:00 UTC copre correttamente e con margine la sessione NYSE reale (13:30-20:00 UTC) tutto l'anno. È solo il commento esplicativo ad essere stale/derivato da un'assunzione EST-invariante.
* Impatto: rischio che un futuro intervento "a naso" sul crontab, fidandosi del commento invece di ricalcolare da UTC, introduca un errore reale (es. restringere la finestra pensando sia già allineata a EDT).
* Severità: Low
* Confidenza: High
* Azione consigliata: correggere i commenti per riferirsi solo a UTC ("14:00-21:00 UTC, copre 13:30-20:00 UTC NYSE con 30 min di margine ±"), eliminando il riferimento a un orario ET fisso che varia con la DST.
* Test/monitor consigliato: nessuno (fix documentale).

---

## 11. False Positive o Aree Risultate Corrette

* **Assenza totale di attività il 07-12** — verificata come comportamento by-design (gate `day_of_week="1-5"`), non un fallimento silenzioso. Confermato da doppia fonte (conteggio DB + lettura codice).
* **Nessuna violazione paper/live, nessun kill-switch, nessun pyramiding, nessun ordine fuori orario** — vacuously true per assenza di ordini, ma il gate stesso che lo garantisce è stato letto e confermato nel codice, non solo assunto.
* **NAV/posizioni weekend** — il piccolo delta (-21,50 USD) inizialmente potrebbe sembrare un'anomalia PnL; verificato che non corrisponde ad alcun trade e ricade nella normale marcatura weekend (vedi [DAY-006]).
* **Redis `regime:current`** — ancora valorizzato e coerente (`sideways`, multiplier 0.7, rilevato 2026-07-10T13:30:49Z, ultimo run feriale prima del weekend); nessun dato stale anomalo, semplicemente non aggiornato nel weekend (corretto, `regime-detector` è gated feriali).

## 12. Dati Mancanti o Non Accessibili

* **Log applicativi container del 07-12**: fisicamente persi (container ricreati 07-13 07:43 UTC). Impossibile confermare/escludere errori interni non finiti in una tabella Postgres.
* **Causa esatta del delta NAV weekend (-21,50 USD)**: servirebbe l'endpoint Alpaca `account/activities` (dividendi, corporate actions) per il 07-11/07-12, non interrogato in questa sessione.
* **Storico esatto della chiave Redis `config:sentiment_llm_models`**: legge `"all"` ora; non verificabile se/quando sia cambiata rispetto alla coppia `glm52,gptoss` indicata come live al 07-11 nella documentazione interna (nessuna chiamata LLM nel weekend da cui dedurlo).
* **Meccanismo esatto di rimozione delle righe di test `TEST_STOP_*`** ([DAY-002]): non ricostruibile, l'audit trigger su `trades` non cattura DELETE.

## 13. Raccomandazioni Immediate

1. Correggere `scripts/daily_analysis.sh` per usare "ultimo giorno di mercato" invece di "ieri" come `DATE_TARGET` ([DAY-001]) — priorità più alta perché mina la copertura dell'intero processo di audit.
2. Verificare l'isolamento test/produzione del branch `stop-loss-redesign` rispetto a `alembic-postgres-1` ([DAY-002]).
3. Configurare persistenza dei log Docker indipendente dal ciclo di vita del container ([DAY-003]).

## 14. Test/Monitor da Aggiungere

* Controllo settimanale di copertura dei report forensi (tutti i 5 feriali presenti in `docs/FORENSIC_DAILY_REPORT_*.md`).
* Sanity-check periodico anti-contaminazione (`symbol LIKE 'TEST%'` su `trades`/tabelle finanziarie).
* Alert su gap tra `docker inspect StartedAt` e copertura log recuperabile > 24h.
* Assert che il decay-monitor produca `actual_value` differenziati per strategia quando i dati lo permettono.
* Alert su `forward_return` NULL oltre N+2 giorni di mercato dalla creazione del segnale.

## 15. Ticket Tecnici Suggeriti

* **TICKET-A** (High): Fix off-by-one weekend in `scripts/daily_analysis.sh` — vedi [DAY-001].
* **TICKET-B** (Medium): Isolamento DB test vs produzione per la suite `stop-loss-redesign` + estensione audit trigger `trades` a DELETE/UPDATE — vedi [DAY-002].
* **TICKET-C** (Medium): Persistenza log Docker (logging driver esterno) — vedi [DAY-003].
* **TICKET-D** (Medium): Decay-monitor per-strategia reale (schema + query) — vedi [DAY-005].
* **TICKET-E** (Medium): Investigare backlog `forward_return` fermo su 07-09 nonostante dati di prezzo disponibili — vedi [DAY-007].
* **TICKET-F** (Low): Bonifica commenti DST in `celery_app.py` — vedi [DAY-008].

## 16. Stato Sistema

* **Ollama (glm-5.2/kimi-k2.6 via ollama.com)**: nessuna chiamata il 07-12 (giorno non di mercato) → uptime/downtime non misurabile per questa data. Ultimo giorno con chiamate: 07-10, 64+64 risposte, nessun timeout/errore rilevato nei conteggi (pari tra i due modelli).
* **FinBERT fallback rate**: N/A per il 07-12 (0 decisioni). Ultimo valore noto: dai report precedenti, ~72-80% capacity-driven (non per divergenza) nei giorni feriali recenti.
* **Worker restart events**: `worker`, `worker-inference`, `api`, `beat` ricreati 2026-07-13 07:43:28 UTC (deploy F6 + fix frontend, commit `237e660`/`d3ce750`); `frontend` ricreato 07:26:17 UTC. Nessun restart verificabile **durante** il 07-12 stesso (log di quel periodo persi, ma nessun commit/deploy risulta datato 07-11/07-12 da `git log`, quindi nessun redeploy pianificato in quella finestra). `postgres`/`redis` non riavviati da 2026-07-07 (5+ giorni di uptime continuo).

---

*Fine report. Nessuna modifica al codice, nessun commit, nessun ordine, nessun worker avviato in questa sessione. Solo lettura (SQL SELECT, API GET, `docker logs`/`inspect`, lettura file).*
