# Forensic Daily Report — 2026-07-27 (lunedì)

Analista: sessione Claude autonoma (Trading Systems Forensic Analyst + Senior Backend Engineer +
Quant Operations Reviewer). Modalità: read-only, nessuna modifica a codice/DB/ordini.

Timezone operativo: **UTC**, confermato in `src/workers/celery_app.py` (`timezone="UTC"`,
`enable_utc=True`). Il commento del beat schedule dice "Sentiment Worker every 15 min... 14:00-21:00
UTC = 9am-4pm ET" — impreciso (9:30am-4pm ET in DST = 13:30-20:00 UTC), ma è solo il bound esterno
del cron; il gating effettivo usa `src/workers/market_clock.is_market_open()` che interroga
`Alpaca TradingClient.get_clock().is_open` in tempo reale (corretto per DST/festivi). **Nessuna
ambiguità funzionale**: i 24 cicli portfolio del giorno (14:07→19:52 UTC) sono coerenti con
l'orario reale di mercato più un offset di avvio di ~37 min, pattern identico al 07-24 (già
verificato non-anomalo in `docs/ALPHA_MISS_REPORT_2026-07-27.md`).

Ambiente: **paper trading** confermato per tutte le righe reali di `portfolio_monitor_snapshots`
(`broker_environment='paper'`, `source='alpaca_paper'`). `execution.engine=portfolio` (i cicli
loggano `strategies_run=["S1","S4"]`, coerente con CLAUDE.md).

## 1. Executive summary

- Pipeline end-to-end (news → LLM → segnale → decisione → ordine → fill → posizione) ha
  funzionato correttamente per la maggioranza del giorno: 8 BUY e 6 SELL generati, tutti
  riconciliati 1:1 con righe `trades` aperte/chiuse, nessun ordine orfano, nessun NO-ORDER gap.
- **Bug critico confermato, con evidenza live dello stesso giorno**: il gate di freschezza
  entry-only ha forzato la chiusura di 3 posizioni detenute (AXP, DIS, NOW) alle 14:22 UTC solo
  perché il loro segnale S4 aveva `published_at` scaduto — non un segnale contrario. Bug #150,
  già diagnosticato e fixato su branch dedicato lo stesso giorno del report (commit `6e33a34`,
  non ancora confermato deployato su `main`/live).
- **Contaminazione test-in-prod**: un test suite (verosimilmente stop-loss/mobile) ha eseguito
  killswitch ON/OFF 4 volte e inserito trade sintetici `TEST_STOP_*` direttamente contro
  API/DB di produzione alle 10:06-10:37 UTC (e di nuovo alle 20:09-20:11 UTC). Le righe `trades`
  si sono auto-pulite, ma 7 righe sintetiche in `portfolio_monitor_snapshots` sono rimaste
  (39 storiche totali).
- L'anti-whipsaw guard è **solo shadow** (non blocca): 3 SELL del giorno mostrano
  `would_suppress=True` ma sono comunque eseguiti, con 2 round-trip in perdita netta
  (NVDA -$15.49, ORCL -$7.86).
- PnL realizzato netto del giorno: **+$88.75**, ma interamente spiegato dalle 3 chiusure
  #150-indotte (+$110.43 combinato); i trade "as-designed" del giorno (NVDA/AXP/ORCL) nettano
  **-$21.69**. NAV di fine giornata (ultima riga reale, 20:00 UTC): $109,595.71, variazione
  giornaliera -$141.21, drawdown 0.47% (limite 5%), esposizione lorda 30.7% (limite 50%) — nessun
  breach di risk limit.
- Nessuna evidenza di downtime totale Ollama; fallback rate 36.1% (61/169 segnali single-model),
  in linea con il pattern storico noto (confidenza media glm-5.2 0.272, sotto soglia 0.4).
- **Log Docker non disponibili per il 07-27**: tutti i container applicativi sono stati
  ricreati il 07-28 mattina — impossibile verificare timeout/retry a livello di log; ricostruito
  via tabelle DB (`audit_log`, `fallback_counters`, `llm_responses`).

## 2. Verdict finale

**ANOMALIE SIGNIFICATIVE (non bloccanti)**

Motivazione: la pipeline operativa ha eseguito correttamente sul piano meccanico (riconciliazione
ordini/fill/posizioni pulita, nessun risk-limit violato, idempotenza verificata, nessun dato futuro
o corrotto), ma è stato confermato un bug capital-affecting (forced-exit di posizioni detenute,
#150) che si è manifestato 3 volte nello stesso giorno, più un pattern ricorrente di
contaminazione test-in-prod. Nessuno dei due ha causato un danno grave *quel* giorno (le uscite
#150 sono state casualmente profittevoli), ma entrambi rappresentano rischio latente non
trascurabile se ripetuti in condizioni di mercato meno favorevoli.

## 3. Timeline del 2026-07-27 (UTC)

| Ora UTC | Fase | Evento | Fonte |
|---|---|---|---|
| 01:21:51 | Overnight | Monitor snapshot pre-market: NAV 109,807.54, unrealized +424.75, 48 posizioni aperte | `portfolio_monitor_snapshots` |
| 10:06:14–10:06:29 | Pre-market | KILLSWITCH_ACTIVATE ×2 ("manual operator halt via API") + UPDATE config "test-deep-merge-verified" | `audit_log` id 5674-5679 |
| 10:08:32–10:08:46 | Pre-market | INSERT 6 trade sintetici `TEST_STOP_1/2/3` (score 0.02, notional $1000, order id riusati) | `audit_log` id 5680-5685 |
| 10:07:55–10:36:34 | Pre-market | 5 righe sintetiche in `portfolio_monitor_snapshots` (fixture MSFT qty=12.3456, `broker_environment` NULL) | `portfolio_monitor_snapshots` |
| 10:21:25–10:32:42 | Pre-market | KILLSWITCH_ACTIVATE ×2 aggiuntivi + altri 6 trade `TEST_STOP_*` sintetici | `audit_log` id 5686-5700 |
| 13:30:00 | Market open | Primo snapshot reale post-apertura: NAV 109,871.91, unrealized +488.47 | `portfolio_monitor_snapshots` |
| 14:01:49 | Ingest/LLM | Primi `llm_responses`/`sentiment_signals` del giorno | `llm_responses`, `sentiment_signals` |
| 14:07:00 | Decisione | Ciclo portfolio #1/24: BUY MMM, XLF (S1 momentum, peso 1.2%) | `execution_decisions` |
| 14:22:00 | Decisione | Ciclo #2: BUY NVDA (S4, score +0.345, "OpenAI financing"); BUY VZ (S1); **SELL AXP, DIS, NOW "[no_signal]"** — bug #150, vedi [DAY-001] | `execution_decisions` |
| 14:37:05 | Idempotenza | `SIGNAL_DUPLICATE_SKIP` su NVDA (signal 5132) — guard funziona correttamente | `audit_log` id 5705 |
| 16:07:00 | Decisione | SELL NVDA "[whipsaw]" (`would_suppress=True`, eseguito comunque) — chiusura round-trip 1h45m, -$15.49 netti | `execution_decisions`, `trades` id 497 |
| 16:52:00 | Decisione | BUY AXP (S4 +0.617, earnings beat); BUY ORCL (S4 +0.588, "$7B Pentagon contract") | `execution_decisions` |
| 18:22:00 | Decisione | BUY NVDA re-entry (S4 +0.368, "$1.5B Blackwell contract") — aperta a fine giornata | `execution_decisions`, `trades` id 500 |
| 18:37:05 | Decisione/Idempotenza | `SIGNAL_DUPLICATE_SKIP` NVDA (signal 5252); SELL AXP e ORCL "[whipsaw]" (shadow, eseguiti) — ORCL -$7.86, AXP +$1.66 | `audit_log` id 5709, `execution_decisions` |
| 19:07:00 | Decisione | BUY CRM (S4 +0.560, "$1.6B VA contract") — aperta a fine giornata | `execution_decisions`, `trades` id 501 |
| 19:45:19 | Ingest/LLM | Ultimo `llm_responses`/`sentiment_signals`; `llm_budget` giornata: $0.187, 94,435 token input | `llm_budget`, `llm_responses` |
| 19:52:00 | Decisione | Ultimo (24°) ciclo portfolio del giorno | `portfolio_cycles` |
| 20:00:00 | EOD | Ultimo snapshot reale: NAV 109,595.71, variazione -$141.21, unrealized +$186.32, drawdown 0.47%, 50 posizioni aperte | `portfolio_monitor_snapshots` |
| 20:08:49–20:11:23 | Post-market | Altre 2 righe sintetiche in `portfolio_monitor_snapshots` + 2 trade `TEST_STOP_1` (auto-cancellati) — stessa contaminazione test | `audit_log` id 5711-5714, `portfolio_monitor_snapshots` |
| 21:16:09 | Ingest | `ingestion_stats_daily` per fonte `reuters` aggiornato tardi, fuori dalla finestra di mercato — vedi [DAY-006] | `ingestion_stats_daily` |

## 4. Tabella news ingest

| Fonte | Fetched | Queued (→Redis) | Duplicates | Discarded no-ticker | In `news_log` (07-27) | Note |
|---|---|---|---|---|---|---|
| alpaca_benzinga | 744 | 402 | 3,337¹ | 0 | 79 | ¹ contatore duplicati cumulativo/non giornaliero apparente — vedi nota sotto |
| gdelt_gkg | 1,633 | 141 | 28 | 1,495 | 86 | Il grosso dei 1,633 fetched è scartato per assenza ticker riconosciuto (org_lookup) |
| reuters | 36 | 36 | 0 | 9 | **0** | Nessuna riga mai arrivata in `news_log` — vedi [DAY-006] |
| **Totale** | 2,413 | 579 | 3,365 | 1,504 | **165** | |

Note:
- `news_log` (165 righe: 86 gdelt_gkg + 79 alpaca_benzinga) è **molto inferiore** a "queued" (579).
  Causa identificata nel codice (`src/workers/sentiment.py`): il worker consuma la coda Redis
  `news:queue` a **batch di 12 item/ciclo** (`_SENTIMENT_BATCH_SIZE=12`) durante le finestre di
  mercato — un limite di throughput deliberato (rate-limit LLM/costo), non un errore. La coda
  Redis ha oggi (07-28) un backlog residuo di 119 item, confermando che il drenaggio è più lento
  dell'afflusso in giornate di news pesanti.
- `alpaca_benzinga` mostra `duplicates=3337 > fetched=744`: il contatore sembra cumulativo o
  conteggiare deduplica per singolo ticker su articoli multi-tag, non chiaramente giornaliero —
  segnalato come ambiguità di strumentazione, non verificato a fondo (fuori scope read-only).
- Nessun timestamp futuro, nessuna news con `published_at > fetched_at` trovata.
- Nessuna vera duplicazione di contenuto cross-provider (gdelt vs alpaca_benzinga) sulle 165 righe;
  le uniche 2 URL con >1 riga sono fan-out multi-ticker dello stesso articolo (by design, vincolo
  UNIQUE `(url, ticker)`), non un bug.
- Copertura per ticker (top): MU 19, MS 18, GS 10, NVDA 9, INFY 7, GOOGL/DB/MSFT 6.
- `extraction_method`: `org_lookup` (gdelt, 86) vs `source_metadata` (alpaca_benzinga cashtag, 79).

**Top news per impatto sul segnale** (score assoluto più alto tra i segnali che hanno generato un
ordine):
| Simbolo | Score | Titolo/estratto | Esito |
|---|---|---|---|
| CRM | +0.560 | "$1.6B VA contract" | BUY 19:07, aperta EOD |
| AXP | +0.617 | Earnings beat, profit reinvestment | BUY 16:52 → SELL 18:37 whipsaw, +$1.66 |
| ORCL | +0.588 | "$7B Pentagon contract" | BUY 16:52 → SELL 18:37 whipsaw, -$7.86 |
| NVDA | +0.345 / +0.368 | OpenAI financing deal / "$1.5B Blackwell contract" | round-trip -$15.49, poi re-entry aperta EOD |

Confidenza analisi ingest: **Alta** (dati diretti da `news_log`/`ingestion_stats_daily`).

## 5. Tabella performance modelli LLM

| Model | Risposte (llm_responses) | Avg polarity | Avg confidence | Ineligible (conf&lt;0.4) | Fallback single-model (segnali) |
|---|---|---|---|---|---|
| glm-5.2:cloud | 169 | +0.038 | 0.272 | 140 (82.8%) | 11 |
| gpt-oss:20b-cloud | 167 | +0.041 | 0.405 | 138 (82.6%) | 50 |
| **Ensemble (entrambi eligible)** | 108 segnali | — | — | — | — |

- `sentiment_signals` totali 07-27: **169** (108 ensemble veri, 61 fallback single-model = 36.1%
  fallback rate). In linea con il pattern storico ricorrente (memoria: 49-86% fallback in altre
  giornate) — oggi relativamente meno grave.
- `fallback_counters.consecutive_fallback` = 0, ultimo reset 19:45:19 UTC del 07-27 → **nessuna
  striscia lunga di fallback consecutivo**, coerente con un Ollama funzionante ma a bassa
  confidenza intermittente, non un'interruzione totale.
- Range score/confidence: score min -0.36, max +0.56, media +0.029; confidence media 0.393;
  `ensemble_std` medio 0.041 (basso in aggregato, ma con outlier — vedi sotto).
- Nessun timeout/errore rilevabile in `reasoning` (0 righe con testo vuoto o contenente
  "timeout"/"error") — ma questo controllo non sostituisce i log applicativi, non disponibili
  per il giorno (vedi §12).
- **Disaccordo elevato osservato**: GOOGL, MU, WDC, ORCL, NVDA con `ensemble_std` 0.32-0.39 in
  singole letture — GOOGL in particolare oscilla da score +0.467 (15:15 UTC) a +0.078 (18:15 UTC)
  nello stesso giorno.
- Score estremi: TM -0.36 (single-model fallback), NVDA -0.33 (single-model fallback, poi -0.24 e
  MU -0.30 in ensemble) sul lato negativo; CRM +0.56, AXP +0.51, ORCL +0.49 sul lato positivo
  (tutti ensemble, coerenti con notizie specifiche e concrete).
- **Validazione pre-signal-store**: confermata — `eligible` flag applicato per-modello
  (`confidence >= 0.4`), l'ensemble scarta i modelli non eleggibili prima di calcolare
  score/confidence pesati (`src/llm/ensemble.py`); se nessun modello è eleggibile scatta il
  fallback single-model, mai un valore non validato.
- **Rischio hallucination diretto in decisione**: mitigato solo in parte. Il caso RDDT del giorno
  precedente/adiacente (documentato in `ALPHA_MISS_REPORT_2026-07-27.md` §3, score -0.095 su un
  articolo che descriveva esplicitamente un rally in corso) mostra che un errore di polarità può
  attraversare l'intera pipeline fino a `execution_decisions` come `SKIP_THRESHOLD` — non ha
  generato un ordine solo perché sotto soglia (0.30), non per un secondo controllo di coerenza.
  Non risulta un supervisor/secondo-LLM di cross-check nel path osservato.

Confidenza analisi LLM: **Alta** per volumi/eligibility (dati diretti DB); **Media** per
latenza/timeout (nessun dato di durata disponibile in `llm_responses`, log assenti).

## 6. Tabella segnali finali per ticker (simboli con BUY/SELL il 07-27)

| Simbolo | Strategia | Signal score (S4) / peso (S1) | Decisione | Ora |
|---|---|---|---|---|
| MMM | S1 momentum | peso 1.2% | BUY | 14:07 |
| XLF | S1 momentum | peso 1.2% | BUY | 14:07 |
| VZ | S1 momentum | peso 1.2% | BUY | 14:22 |
| NVDA | S4 news | +0.345 | BUY | 14:22 |
| NVDA | S4 news | score=0 (scaduto, whipsaw) | SELL | 16:07 |
| AXP | S4 news | signal precedente (07-24), scaduto | SELL "[no_signal]" (bug #150) | 14:22 |
| DIS | S4 news | signal precedente (07-24), scaduto | SELL "[no_signal]" (bug #150) | 14:22 |
| NOW | S4 news | signal precedente (07-24, +0.81), scaduto | SELL "[no_signal]" (bug #150) | 14:22 |
| AXP | S4 news | +0.617 | BUY | 16:52 |
| ORCL | S4 news | +0.588 | BUY | 16:52 |
| NVDA | S4 news | +0.368 | BUY (re-entry) | 18:22 |
| AXP | S4 news | -0.075 (whipsaw) | SELL | 18:37 |
| ORCL | S4 news | +0.049 (whipsaw) | SELL | 18:37 |
| CRM | S4 news | +0.560 | BUY | 19:07 |

`execution_decisions` totali: 160 (146 SKIP_THRESHOLD, 8 BUY, 6 SELL). Nessun `HOLD` esplicito
distinto — SKIP_THRESHOLD copre sia i segnali sotto soglia (0.30) sia i simboli senza segnale.

Confidenza: **Alta**.

## 7. Tabella ordini generati/eseguiti

| Trade ID | Simbolo | Entry time | Entry price | Exit time | Exit price | Exit reason | Qty | Note |
|---|---|---|---|---|---|---|---|---|
| 494 | MMM | 14:07:00 | 177.74 | — (aperta) | — | — | 4.129 | S1, mark-to-close ~+0.25% |
| 495 | XLF | 14:07:00 | 57.00 | — (aperta) | — | — | 12.876 | S1 |
| 496 | VZ | 14:22:00 | 47.23 | — (aperta) | — | — | 15.220 | S1 |
| 497 | NVDA | 14:22:00 | 200.38 | 16:07:00 | 197.927 | portfolio_sell (whipsaw) | 6.213 | -$15.49 netti |
| 426 | AXP | 07-24 18:37 | 323.05 | **14:22:00** | 332.50 | portfolio_sell (bug #150) | 3.819 | +$35.41 netti |
| 427 | DIS | 07-24 18:37 | 95.19 | **14:22:00** | 96.55 | portfolio_sell (bug #150) | 12.961 | +$16.95 netti |
| 425 | NOW | 07-24 18:37 | 98.20 | **14:22:00** | 102.88 | portfolio_sell (bug #150) | 12.563 | +$58.07 netti |
| 498 | AXP | 16:52:00 | 333.72 | 18:37:00 | 334.347 | portfolio_sell (whipsaw) | 3.742 | +$1.66 netti |
| 499 | ORCL | 16:52:00 | 120.16 | 18:37:00 | 119.47 | portfolio_sell (whipsaw) | 10.393 | -$7.86 netti |
| 500 | NVDA | 18:22:00 | 196.35 | — (aperta) | — | — | 6.360 | riapertura post round-trip |
| 501 | CRM | 19:07:00 | 176.09 | — (aperta) | — | — | 7.058 | entrata tardiva vs close 173.55 |

Tutti gli ordini sono `alpaca_paper` (paper trading). Nessun REJECTED/CANCELLED osservabile in DB
(non esiste una tabella `orders` con stato distinto da `trades`/`execution_decisions` in questo
schema — vedi §12). Reconciliazione: 8 BUY decision ↔ 8 righe `trades` aperte; 6 SELL decision ↔
6 righe `trades` chiuse il 07-27 — **nessun gap NO-ORDER, nessun ordine orfano**.

Confidenza: **Alta**.

## 8. Tabella PnL/rendimento

| Metrica | Valore | Fonte |
|---|---|---|
| PnL realizzato netto (trade chiusi 07-27) | **+$88.75** | somma `net_pnl` trades 425,426,427,497,498,499 |
| — di cui da chiusure bug #150 (AXP/DIS/NOW) | +$110.43 | idem |
| — di cui da trade "as-designed" (NVDA/AXP/ORCL) | **-$21.69** | idem |
| NAV apertura (previous_close_equity) | $109,736.92 | `portfolio_monitor_snapshots` |
| NAV ultima rilevazione reale (20:00 UTC) | $109,595.71 | idem |
| Variazione NAV giornaliera (`nav_change_today`) | **-$141.21** | idem |
| Unrealized PnL fine giornata | +$186.32 | idem |
| Esposizione lorda fine giornata | 30.7% (limite 50%) | idem |
| Drawdown corrente fine giornata | 0.47% (limite 5%) | idem |
| Posizioni aperte fine giornata | 50 | idem, riconciliato con `trades WHERE exit_time IS NULL` |
| Costi/slippage stimati (6 trade chiusi) | ~$3.65 totali (`cost_usd`/`slippage_est` combinati) | `trades.cost_usd` |

Nota: `nav_change_today` (-$141.21) include sia il realizzato (+$88.75) sia la variazione
mark-to-market delle 50 posizioni aperte (comprese quelle aperte prima del 07-27) — la differenza
implicita (~-$230) è variazione unrealized sul book esistente, **non ricalcolata autonomamente da
prezzi tick-by-tick** in questa sessione (ci si affida al campo `unrealized_pnl` del sistema,
input fidato ma non riverificato contro Alpaca raw quotes). Nessun dato di prezzo mancante
rilevato per i simboli tradati.

Confidenza: **Alta** per i numeri aggregati NAV/drawdown/esposizione (fonte diretta,
multi-campionamento ogni 5 min); **Media** per l'attribuzione realized/unrealized per singolo
simbolo (derivata, non da un ledger P&L per-symbol dedicato).

## 9. Analisi correttezza buy/sell

| Controllo | Esito | Note |
|---|---|---|
| BUY solo quando consentito (score/soglia rispettati) | ✅ OK | Tutti gli 8 BUY hanno `signal_score`≥0.30 (S4) o motivazione S1 valida |
| SELL/exit generati correttamente | ⚠️ Parziale | 3/6 SELL causati da bug #150 (forced-exit non intenzionale), non da una vera decisione di uscita |
| Stop-loss rispettati | ❔ Non verificabile | `stop_decisions` = 0 righe dal 07-13 in poi — vedi [DAY-006] |
| Signal flip rispettato | ✅ OK | Nessun caso di SELL su sentiment positivo (bug A5) trovato |
| Max holding days | ✅ OK (nessuna violazione osservata) | Posizioni più vecchie (dal 07-10) ancora aperte, ma nessuna regola di holding-max esplicita violata nei dati |
| Rebalance band rispettata | ✅ OK | Nessuna anomalia di peso oltre i cap (esposizione max 31.8% intraday, limite 50%) |
| Nessun ordine duplicato | ✅ OK | Nessuna riga `execution_decisions` duplicata per stesso simbolo/decisione/minuto |
| Nessun ordine contrario ravvicinato senza rationale | ⚠️ Parziale | NVDA/AXP/ORCL round-trip in ~1h45m con rationale esplicito "[whipsaw]" ma **guard shadow-only**, non blocca — vedi [DAY-004] |
| Nessun ordine su ticker non consentiti | ✅ OK | Tutti i simboli tradati sono in watchlist |
| Nessun ordine fuori orario | ✅ OK | Tutti i 24 cicli/14 decisioni BUY/SELL nella finestra 14:07-19:52 UTC |
| Nessun trade su dati stale | ⚠️ Parziale | Il bug #150 è esattamente un caso di "stale gestito male" (dato scaduto → forced exit anziché hold) |
| Nessun trade con LLM output non valido | ✅ OK | `eligible` flag applicato correttamente prima dell'ensemble |
| Nessun trade con circuit breaker attivo | ✅ OK | I 4 KILLSWITCH_ACTIVATE del giorno sono tutti pre-market (10:06-10:37 UTC), nessuna decisione BUY/SELL coincide con una finestra di halt attivo |
| Nessun trade con strategia disabilitata | ✅ OK | S1/S4 `approved=true` in `strategy_lifecycle` |
| Paper/live coerente | ✅ OK | Tutte le righe reali `broker_environment='paper'` |
| Idempotenza su retry Celery | ✅ OK | 2× `SIGNAL_DUPLICATE_SKIP` catturati correttamente (NVDA) |
| Reconciliation ordini/fill/posizioni | ✅ OK | 8 BUY↔8 trade aperti, 6 SELL↔6 trade chiusi, `open_positions=50` coerente con `trades` |

## 10. Anomalie trovate

### [DAY-001] Entry-freshness gate forza la chiusura di posizioni detenute (bug #150)

- Tipo: Bug (già fixato su branch, non confermato deployato)
- Area: Signal / Orders
- Evidenza:
  * file/log/tabella: `execution_decisions` id relativi a SELL AXP/DIS/NOW; `src/workers/portfolio_scheduler.py` (pre-fix); commit `6e33a34`
  * timestamp: 2026-07-27 14:22:00 UTC
  * snippet/query: `reason = '[no_signal] Portfolio rebalance: weight 0.0% — no S4 signal found in DB (signal may be older than the lookback window or never generated).'` — per NOW il segnale reale era **+0.81 del 07-24, mai contraddetto**, semplicemente più vecchio di `news_age_hours`.
- Descrizione: `fetch_signals_for_cycle` applicava lo stesso bound di freschezza (`news_age_hours`)
  sia al path di nuova entrata sia al path di hold/exit delle posizioni S4 già aperte,
  contraddicendo il proprio docstring. Una posizione detenuta il cui unico segnale aveva
  `published_at` vecchio veniva esclusa **prima** che FIX-D
  (`_preserve_stale_signals_for_open_positions`) potesse valutarla, e finiva chiusa come "nessun
  segnale" anche con uno score storico forte e mai invertito.
- Impatto: 3 posizioni (AXP, DIS, NOW) chiuse senza una vera ragione di trading. Oggi tutte e 3 in
  profitto (+$110.43 combinato), ma NOW ha lasciato sul tavolo ~2.6 punti di ulteriore rialzo
  (uscita 102.88, chiusura giornaliera 105.53) — la stessa dinamica potrebbe forzare un'uscita in
  perdita in una giornata sfavorevole.
- Severità: **Critical** (capital-affecting, sistemico — colpisce ogni posizione S4 con notizie
  non recenti)
- Confidenza: **High** (commit di fix esistente con causa-radice identica, live-verificato dallo
  stesso autore/data del bug)
- Azione consigliata: verificare che il commit `6e33a34` (branch `fix/150-entry-freshness-gate-holds`)
  sia mergeato su `main` e **deployato in live** (i container sono stati ricreati il 07-28 mattina,
  ma non è confermato da quale branch/immagine); eseguire un audit retroattivo di quante altre
  chiusure storiche siano riconducibili allo stesso pattern "[no_signal]" su posizioni detenute.
- Test/monitor consigliato: alert quando una SELL su posizione S4 aperta ha `reason` contenente
  `no_signal` e lo score dell'ultimo segnale noto era positivo e mai contraddetto; test di
  regressione già aggiunto nel commit (`tests/workers/test_entry_freshness_gate.py`) — verificarne
  l'esecuzione in CI.

### [DAY-002] Test suite eseguito contro API/DB di produzione (killswitch + trade sintetici)

- Tipo: Anomalia operativa / Rischio
- Area: Ops / Risk
- Evidenza:
  * file/log/tabella: `audit_log` id 5674-5700, 5711-5714
  * timestamp: 2026-07-27 10:06:14–10:37:03 UTC e 20:09:19–20:11:51 UTC
  * snippet/query: `{"reason": "manual operator halt via API", "source": "api"}` ×4 KILLSWITCH_ACTIVATE; `{"reason": "test-deep-merge-verified", ...}` su `UPDATE config`; `INSERT trades symbol=TEST_STOP_1/2/3, entry_notional=1000.0, entry_order_id="test-order-1"` (ripetuto identico più volte)
- Descrizione: un test suite (nome/pattern coerente con test di stop-loss e deep-merge della
  config) ha eseguito attivazioni/disattivazioni del killswitch e inserito trade sintetici
  ripetutamente contro l'ambiente live, non un DB di test isolato. Le righe `trades` sono state
  ripulite dal test stesso (0 righe `TEST_STOP%` residue), ma il pattern si è ripetuto 2 volte
  nello stesso giorno.
- Impatto: nessun danno diretto oggi (finestre fuori mercato/pre-market), ma il killswitch tocca
  uno stato realmente condiviso col motore di esecuzione — se eseguito durante l'orario di mercato
  (13:30-20:00 UTC) interromperebbe il trading reale. Pattern ricorrente già osservato in memoria
  operativa (righe test in `trades` prod il 07-11).
- Severità: **High**
- Confidenza: **High**
- Azione consigliata: isolare il test suite (stop-loss/mobile integration test) da API/DB di
  produzione — ambiente/DB dedicato o mock del killswitch; audit se questo pattern si ripete con
  cadenza regolare (cron di test?).
- Test/monitor consigliato: alert immediato su ogni `KILLSWITCH_ACTIVATE` con `source=api` fuori da
  un runbook operatore noto; guardia CI/pre-deploy che impedisca ai test di puntare a
  `DATABASE_URL`/API di produzione.

### [DAY-003] Contaminazione persistente in `portfolio_monitor_snapshots` (fixture di test non ripulita)

- Tipo: Bug / Data quality
- Area: Data / Ops
- Evidenza:
  * file/log/tabella: `portfolio_monitor_snapshots`
  * timestamp: 2026-07-27 10:07:55, 10:08:14, 10:22:38, 10:32:13, 10:36:34, 20:08:49, 20:11:23 UTC
  * snippet/query: righe con `broker_environment` NULL, `nav=110307.36` fisso, `pipeline_health` contenente fixture `{"symbol":"MSFT","qty":12.3456,"current_price":505.0,...}` — valori chiaramente sintetici (quantità con precisione a 4 decimali non realistica)
- Descrizione: lo stesso test-run di [DAY-002] scrive anche in `portfolio_monitor_snapshots`
  (probabilmente via l'endpoint mobile-bundle), e queste righe **non vengono ripulite** a
  differenza di `trades`. 39 righe storiche totali nel DB, 7 solo il 07-27.
- Impatto: qualunque lettura grezza della curva NAV/equity (dashboard, script di analisi) intercetta
  valori piatti/fittizi da $110,307.36 intervallati ai dati reali — rischio di conclusioni errate
  se non si filtra su `broker_environment='paper'`/`source='alpaca_paper'`.
- Severità: **Medium**
- Confidenza: **High**
- Azione consigliata: purge delle 39 righe storiche contaminate; aggiungere un vincolo (schema o
  applicativo) che impedisca l'inserimento di snapshot senza `broker_environment` valido in prod.
- Test/monitor consigliato: check giornaliero "% righe con broker_environment NULL in
  portfolio_monitor_snapshots" con soglia 0.

### [DAY-004] Anti-whipsaw guard in sola modalità shadow — round-trip in perdita non prevenuti

- Tipo: Rischio / Ambiguità di design
- Area: Signal / Orders / Risk
- Evidenza:
  * file/log/tabella: `execution_decisions`
  * timestamp: 2026-07-27 16:07:00, 18:37:00 UTC
  * snippet/query: `[anti_whipsaw_shadow: would_suppress=True, streak=1/2]` su SELL NVDA (16:07), AXP e ORCL (18:37) — tutte eseguite nonostante il flag
- Descrizione: il meccanismo di anti-whipsaw rileva correttamente pattern di inversione rapida del
  segnale ma è cablato solo in modalità shadow (logging, non enforcement) — coerente con il pattern
  "shadow-only" già documentato per altre feature (F8 regime scale, vedi memoria progetto).
- Impatto: 2 dei 3 round-trip rilevati come whipsaw sono chiusi in perdita netta (NVDA -$15.49,
  ORCL -$7.86); solo AXP marginalmente positivo (+$1.66). Se il guard fosse enforcing, queste
  perdite sarebbero state potenzialmente evitate (o quantomeno posticipate a un segnale più
  stabile).
- Severità: **Medium**
- Confidenza: **High**
- Azione consigliata: decisione dell'operatore — promuovere il guard a enforcing dopo revisione
  della shadow-evidence accumulata, oppure documentare esplicitamente perché resta shadow-only.
- Test/monitor consigliato: report periodico su "shadow would_suppress rate" vs P&L dei trade che
  sarebbero stati soppressi, per costruire il caso dati alla decisione.

### [DAY-005] Colonna `score` in `trades`/`execution_decisions` sovraccaricata di significato

- Tipo: Ambiguità / Rischio di audit
- Area: Data / Ops
- Evidenza:
  * file/log/tabella: `src/workers/portfolio_scheduler.py:2500` (`"score": order.allocation_weight`) vs `signal_score` (es. riga 2491)
  * timestamp: n/a (strutturale)
  * snippet/query: trade NVDA id 497: `score=0.02` (= peso di allocazione 2%), `signal_score=0.345` (= vero sentiment score)
- Descrizione: il campo `score` in `trades`/`execution_decisions` contiene il **peso di
  allocazione di portafoglio**, non lo score di sentiment/momentum — il vero segnale è in
  `signal_score` (S4) o va dedotto dal testo `reason` (S1). Durante questa stessa sessione
  l'ambiguità ha quasi generato un falso positivo ("score < 0.05 ha generato ordini").
- Impatto: rischio concreto di misinterpretazione in audit futuri, dashboard, o controlli
  automatici basati sul nome colonna.
- Severità: **Low**
- Confidenza: **High**
- Azione consigliata: rinominare `score`→`allocation_weight` (o documentare esplicitamente nello
  schema/commento SQL) per disambiguare da `signal_score`.
- Test/monitor consigliato: n/a (fix di naming/documentazione)

### [DAY-006] `reuters` risulta "fetched/queued" ma non produce mai righe in `news_log`

- Tipo: Anomalia / Bug sospetto
- Area: News / Data
- Evidenza:
  * file/log/tabella: `ingestion_stats_daily` (reuters: fetched=36, queued=36, discarded_no_ticker=9) vs `news_log` (0 righe `source='reuters'`, oggi e storicamente — `SELECT DISTINCT source` non include mai `reuters`)
  * timestamp: 2026-07-27, `updated_at` 21:16:09 UTC (fuori dalla finestra standard di mercato/ingest)
  * snippet/query: vedi §4
- Descrizione: la fonte `reuters` (via `src/connectors/rss.py`) riporta metriche di ingest
  regolari ma **non ha mai** prodotto una riga in `news_log`, né oggi né in passato — sospetto un
  mismatch fra il tag sorgente usato nelle statistiche e quello effettivamente scritto a valle, o
  una rottura silenziosa nel path di elaborazione specifico per questa fonte. Anche l'orario di
  aggiornamento (21:16 UTC, dopo la chiusura di mercato 20:00 UTC) è fuori pattern rispetto ad
  alpaca_benzinga/gdelt_gkg (19:45 UTC).
- Impatto: possibile gap di copertura news sistemico e silenzioso per questa fonte — non misurabile
  in termini di segnali persi senza ulteriore indagine nel codice.
- Severità: **Medium**
- Confidenza: **Medium** (pattern chiaro nei dati, causa-radice non verificata nel codice per
  restare in ambito read-only)
- Azione consigliata: verificare `src/connectors/rss.py` e il consumer che scrive `news_log` per la
  fonte reuters; se il connector è di fatto morto, disabilitarlo esplicitamente (come già fatto per
  MarketAux via `MARKETAUX_INGESTION_ENABLED`) per evitare di contare metriche fantasma.
- Test/monitor consigliato: alert se una fonte riporta `queued > 0` in `ingestion_stats_daily` ma
  0 righe corrispondenti in `news_log` nello stesso giorno.

### [DAY-007] `stop_decisions` silenzioso da 2 settimane

- Tipo: Ambiguità / Rischio
- Area: Risk / Ops
- Evidenza:
  * file/log/tabella: `stop_decisions`
  * timestamp: ultima riga 2026-07-14 17:52:05 UTC (22 righe totali, tutte 07-13/07-14)
  * snippet/query: `SELECT count(*), max(cycle_ts) FROM stop_decisions` → 22, 2026-07-14
- Descrizione: nessuna riga di audit per le decisioni di stop-loss dal 07-14 al 07-27 incluso.
  Nessun `exit_reason='stop_loss'` osservato tra i trade chiusi il 07-27 (tutte le uscite sono
  `portfolio_sell`), quindi è plausibile che semplicemente non sia scattato alcuno stop — ma senza
  righe di audit non è possibile distinguere "nessuno stop necessario" da "il logging si è rotto"
  dopo il redesign F9a di metà luglio.
- Impatto: perdita di osservabilità su un controllo di rischio esplicitamente richiesto da
  CLAUDE.md ("Guardrails / Fallbacks").
- Severità: **Low** (nessuna evidenza di stop mancato, solo di logging assente)
- Confidenza: **Medium**
- Azione consigliata: verificare nel codice se il path di valutazione stop-loss sta ancora
  scrivendo su `stop_decisions` dopo le modifiche di metà luglio (redesign F9a).
- Test/monitor consigliato: alert se `stop_decisions` non riceve righe per >N giorni di trading
  con posizioni aperte.

## 11. False positive / aree risultate corrette

- Nessun **roundtrip < 30 min** (i round-trip osservati sono ~1h45m).
- Nessuna **pyramiding** (NVDA ha 2 BUY ma correttamente separati da una SELL nel mezzo).
- Nessuna **SELL con sentiment positivo** (bug A5) — 0 righe trovate.
- Nessun **ordine duplicato nello stesso minuto** (controllo su symbol+decision+minute, 0 righe).
- Nessun **NO-ORDER gap**: ogni BUY/SELL in `execution_decisions` ha una riga `trades`
  corrispondente.
- Nessuna **news con timestamp futuro** o `published_at > fetched_at`.
- **Idempotenza Celery/duplicati segnale**: 2 casi di `SIGNAL_DUPLICATE_SKIP` correttamente
  intercettati (NVDA, signal 5132 e 5252) — nessun doppio ordine generato.
- **Risk limits rispettati** tutto il giorno: esposizione lorda max 31.8% (limite 50%), drawdown
  max 0.62% (limite 5%).
- **Paper/live coerente**: tutte le righe reali `broker_environment='paper'`.
- **Validazione LLM pre-signal-store** confermata a livello di codice (`eligible` flag, soglia
  confidenza 0.4 prima dell'ensemble).
- **Cadenza portfolio-cycle** regolare: 24 cicli, nessun gap interno >16 min.
- **Score threshold S4 rispettata**: tutti gli 8 BUY con `signal_score`≥0.30 o motivazione S1
  valida — nessun ordine sotto soglia.

## 12. Dati mancanti o non accessibili

- **API REST locale** (`/api/decisions`, `/trades`, `/signals`, `/positions`, `/orders`): tutte le
  richieste con il bearer token fornito nel prompt hanno restituito **403 "Invalid or expired JWT
  token"**; anche `ADMIN_API_KEY` letto dall'ambiente del container non ha funzionato (l'endpoint
  richiede evidentemente un JWT firmato, non una chiave statica). Analisi svolta interamente via
  query dirette `psql` su Postgres, che copre lo stesso dominio dati (e in alcuni casi di più, es.
  `portfolio_monitor_snapshots`, `audit_log`) — non considero questo un blocco all'analisi, ma la
  route di auth API andrebbe verificata/documentata per sessioni future.
- **Log Docker (`worker`, `worker-inference`, `beat`, `api`)**: tutti e 4 i container sono stati
  **ricreati il 2026-07-28** tra le 09:45 e le 10:46 UTC (verificato via `docker inspect
  StartedAt`), quindi `docker compose logs --since 48h` non copre **alcuna parte** del 2026-07-27.
  Impossibile verificare da log: timeout Ollama puntuali, retry Celery, eventi di crash/restart
  avvenuti *durante* il 07-27, latenza per singola chiamata LLM. Ricostruito parzialmente via
  `fallback_counters`, `audit_log`, `llm_responses` — copertura sufficiente per volumi/tassi, non
  per eventi puntuali.
- **Latenza LLM**: nessuna colonna di durata/timestamp-richiesta in `llm_responses` — impossibile
  calcolare la latenza media per modello.
- **Tabella `orders` con stato REJECTED/CANCELLED esplicito**: non esiste nello schema attuale;
  lo stato ordine è implicito in `trades`/`execution_decisions`. Nessun reject osservato, ma non
  posso escludere reject silenziosi non propagati al DB.
- **Unrealized PnL per singolo simbolo**: non ricalcolato da quotazioni tick-by-tick indipendenti;
  ci si è affidati al campo di sistema `unrealized_pnl` (fidato ma non riverificato contro dati
  prezzo grezzi Alpaca).

## 13. Raccomandazioni immediate

1. Confermare che il fix #150 (`6e33a34`, branch `fix/150-entry-freshness-gate-holds`) sia
   mergeato su `main` e **deployato in live** — verificare da quale branch/commit è stata costruita
   l'immagine ricreata il 07-28 mattina.
2. Isolare il test suite che genera KILLSWITCH_ACTIVATE + trade `TEST_STOP_*` dall'ambiente di
   produzione (DB/API dedicati ai test).
3. Ripulire le 39 righe sintetiche in `portfolio_monitor_snapshots` e aggiungere un guard che
   impedisca scritture senza `broker_environment` valido in prod.
4. Decidere (operatore) se promuovere l'anti-whipsaw guard a enforcing, sulla base dell'evidenza
   shadow accumulata.
5. Verificare il path `reuters` (ingest riportato ma mai in `news_log`) — disabilitare
   esplicitamente se morto, o fixare se rotto.
6. Verificare perché `stop_decisions` non riceve righe dal 07-14.

## 14. Test o monitor da aggiungere

- Alert su `KILLSWITCH_ACTIVATE` con `source=api` durante 13:30-20:00 UTC (orario di mercato).
- Alert su righe `portfolio_monitor_snapshots`/`trades` con simboli/pattern da test (es.
  `TEST_%`, o `broker_environment` NULL) in ambiente prod.
- Alert su SELL con `reason` contenente `no_signal` su una posizione S4 aperta il cui ultimo
  segnale noto era positivo e mai contraddetto (regressione del bug #150).
- Report periodico shadow "would_suppress" dell'anti-whipsaw guard vs P&L realizzato dei trade
  interessati.
- Alert se una fonte in `ingestion_stats_daily` ha `queued > 0` ma 0 righe in `news_log` lo stesso
  giorno.
- Alert se `stop_decisions` non riceve righe per >N giorni di trading con posizioni S1/S4 aperte.
- Persistenza dei log container attraverso i restart (volume montato o log shipping esterno).

## 15. Ticket tecnici suggeriti

1. Verificare/completare il deploy del fix #150 su main/live.
2. Isolare test suite stop-loss/mobile da DB/API di produzione (root cause DAY-002/DAY-003).
3. Purge righe sintetiche storiche in `portfolio_monitor_snapshots` (39 righe) + guard futuro.
4. Decisione operatore: promuovere anti-whipsaw guard da shadow a enforcing.
5. Investigare il gap `reuters` (ingest riportato, mai in `news_log`).
6. Investigare il silenzio di `stop_decisions` dal 07-14.
7. Rinominare/documentare `trades.score` → chiarire distinzione da `signal_score`.
8. Fixare/documentare l'autenticazione JWT per l'endpoint API usato dalle sessioni forensi
   automatizzate (attualmente 403 con il bearer token fornito).
9. Persistere i log dei container applicativi attraverso i restart (volume o log shipping).

## 16. Stato sistema

- **Ollama**: nessuna evidenza di downtime totale. `fallback_counters.consecutive_fallback=0`
  (ultimo reset 19:45:19 UTC del 07-27); fallback rate 36.1% (61/169 segnali single-model),
  guidato principalmente da confidenza media glm-5.2 (0.272) sotto soglia eligibility (0.4) —
  comportamento intermittente di bassa confidenza, non un'interruzione. **Ore di downtime: non
  misurabili con precisione** senza log applicativi del giorno (vedi §12).
- **FinBERT fallback rate**: nessuna evidenza nei dati DB che FinBERT (fallback deterministico
  finale) sia stato invocato il 07-27 — il "fallback" osservato è single-model LLM cloud, non
  FinBERT. Non verificabile con certezza assoluta senza log (nessun contatore FinBERT-specifico
  trovato in DB).
- **Worker restart events**: `worker`, `worker-inference`, `beat`, `api` risultano **ricreati il
  2026-07-28** (09:45-10:46 UTC) — cioè **dopo** il giorno analizzato, non durante. Nessuna
  evidenza DB (gap nei 24 cicli portfolio, buchi nei segnali) di un restart avvenuto *durante* il
  07-27: i 24 cicli attesi sono tutti presenti con cadenza regolare.
