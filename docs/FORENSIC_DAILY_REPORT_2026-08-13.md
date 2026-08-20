# Forensic Daily Report — 2026-08-13

Timezone operativo: **UTC** (confermato in codice, `src/workers/celery_app.py:51-52`, `timezone="UTC", enable_utc=True`). Nessuna ambiguità.
Sessione NYSE 2026-08-13: 13:30–20:00 UTC (mercato in EDT).

Periodo di osservazione (carta `docs/evidence/OBSERVATION_CHARTER.md`): giorno 8/40 dal 2026-08-03. Deroga rilevante alla data di analisi: **#236 deployato il 2026-08-14T08:20 UTC** (dopo la chiusura del giorno qui analizzato) — quindi il 2026-08-13 è ancora **pre-fix** sul difetto QS-07/FIX-D (vedi DAY-001).

## 1. Executive summary

Giornata operativa regolare, nessun blocco strutturale. News ingest 193 righe (99 Benzinga + 94 GDELT), 24 cicli di portfolio da 14:07 a 19:52 UTC, nessun errore broker, nessun ordine duplicato o fuori orario, nessuna evidenza di outage Ollama (budget LLM speso regolarmente, fallback 15-40%/ora). 1 BUY (META), 3 SELL (SPCX, CSCO, META) su 556 decisioni totali (540 SKIP_THRESHOLD). PnL realizzato giornata: **-$66.17** (SPCX -54.02, CSCO -18.97, META +6.82); NAV +$6.70 (110460.04→110466.74), drawdown reale ~0.16%. Trovata una **istanza pre-fix del bug #236** (SPCX venduta senza contro-segnale per il filtro QS-07 che annullava FIX-D — corretto il giorno dopo). Un secondo trade (META) chiuso in anticipo per un articolo macro generico multi-ticker che ha sovrascritto il segnale ticker-specifico che aveva causato l'ingresso — costo attribuito $16.86. Persistono i difetti di misura già noti e ricorrenti (drawdown triplo-incoerente, decay_monitor non per-strategia, signal_id NULL, log del giorno spariti col redeploy di oggi). Nuovo gap isolato oggi: il classificatore delle cause di miss del dossier non distingue "segnale fallback sopra soglia ma escluso dal ranking" da "causa ignota" (NFLX, PLTR → NON_CLASSIFICATO).

## 2. Verdict finale

**OK con warning.** Nessun rischio di sicurezza/esecuzione, nessun ordine indebito, nessuna violazione paper/live o long-only. I warning sono: (a) un difetto di correttezza reale ma già corretto il giorno successivo (#236), (b) diversi difetti di sola osservabilità/misura ricorrenti che continuano a corrompere le metriche di rischio e decadimento usate per sorvegliare il periodo di osservazione.

## 3. Timeline del 2026-08-13 (UTC)

| Ora | Componente | Evento |
|---|---|---|
| 12:49:56 | News ingest | Prima riga `news_log` (pre-market) |
| 13:30:00 | Portfolio monitor | Snapshot apertura: NAV 110427.06, 49 posizioni, drawdown 0.18% |
| 13:30:01 | Beat scheduler | Nessun ciclo portfolio ancora attivo (crontab `hour='14-21'` = EST, non EDT — F-021) |
| 14:01:31 | Sentiment pipeline | Primo `sentiment_signals` della giornata |
| 14:07:00 | Portfolio scheduler | **Primo ciclo portfolio**, 37 min dopo l'apertura reale (13:30 EDT) |
| 14:22:11 | Execution | **SELL SPCX** (id 9842) — FIX-D aveva riammesso il segnale stale, il filtro QS-07 lo ha rieliminato per età: uscita senza contro-segnale (pre-fix #236) |
| 14:22–18:52 | Execution | 8 righe `SKIP_PYRAMIDING` (MU, CSCO, AMD, IWM, NOK, PANW, QQQ, XLK) — segnali S4 sopra gate ma simbolo già a libro S1/legacy |
| 15:22–18:52 | Execution | 3 righe `SKIP_FALLBACK` (PBR, AZN, WDC) — segnale single-model escluso dal ranking BUY |
| 16:37:11 | Execution | **BUY META** (id 10039), score ensemble +0.531, notizia ticker-specifica su AI infra/Muse AI |
| 16:45:30 | Sentiment pipeline | Segnale META successivo score 0.000 (ensemble), da articolo macro multi-ticker pubblicato prima ma processato dopo |
| 17:52:14 | Execution | **SELL CSCO** (id 10180) — `sentiment_reversal`, score -0.520 < soglia -0.35 (posizione S1 dal 07-15, chiusa da segnale S4) |
| 18:22:15 | Execution | **SELL META** (id 10236) — `below_entry_gate`, segnale sceso a 0.000 dopo 1h45 di tenuta |
| 19:22:10 | Execution | `SKIP_STALE` SOXX (segnale 4.1h > max_age 4h) |
| 19:52:08 | Portfolio scheduler | Ultimo ciclo portfolio del giorno (24 cicli totali, cadenza regolare) |
| 20:00:00 | Portfolio monitor | Snapshot chiusura: NAV 110466.74, 47 posizioni, drawdown reale 0.16% |
| 21:00:00 | Decay monitor | 12 righe `decay_reports`, valori identici S1/S2/S4, 3× CRITICAL su sharpe |
| 22:30:01 | Risk monitor | `risk_reports` id 62: combined_drawdown 1.24%, ALERT su drawdown 17.2% (terza cifra incoerente con lo 0.16% reale) |
| 2026-08-14 08:20:11 | Ops (fuori giornata) | Redeploy worker/worker-inference per #236 — i log Docker del 2026-08-13 non esistono più al momento di questa analisi |

## 4. Tabella news ingest

| Fonte | Righe `news_log` (13/08) | `fetched` (ingestion_stats_daily) | `duplicates` (contatore) | Note |
|---|---|---|---|---|
| alpaca_benzinga | 99 | 737 | 3261 (4.4× fetched) | Contatore additivo cross-run, non affidabile stand-alone (F-007, ricorrente) |
| gdelt_gkg | 94 | 2015 | 48 (+1837 `discarded_no_ticker`) | La maggioranza dello scarto GDELT è "nessun ticker", non duplicato |

- Totale righe `news_log` 2026-08-13: **193**, 56 ticker distinti, finestra pubblicazione 12:49:56–17:55:57 UTC.
- Nessun `discarded_reason` valorizzato sulle 193 righe finali (0 su 193).
- Nessuna news con timestamp futuro (`published_at > fetched_at`): 0 righe.
- Latenza ingest (`fetched_at - published_at`): min 5m35s, media 1h18m33s, max 1h59m43s — dentro la finestra di entry-freshness 2.0h documentata in F-019, ma la assorbe quasi per intero.
- Copertura watchlist: **41/96 simboli (43%) a zero news** (dossier deterministico `docs/evidence/dossier/2026-08-13.json`), dentro la banda 40-57% osservata dal 07-31.
- Mover ≥3% del giorno: 14 (11 up, 3 down). Dei 9 candidati miss classificati dal dossier: 4 NO_NEWS (ADBE +4.54%, CRM +4.16%, TMUS +3.53%, RDDT +3.04%), 2 THIN_NEUTRAL (JD, HOOD), 1 BELOW_GATE (TSLA), 2 NON_CLASSIFICATO (NFLX, PLTR — vedi DAY-003).

## 5. Tabella performance modelli LLM

| Modello | Righe `llm_responses` | `eligible=true` | Polarity media | Confidence media | Note |
|---|---|---|---|---|---|
| glm-5.2:cloud | 193 | 37 (19%) | 0.089 | 0.261 | `eligible=false` = filtro di rilevanza (motivazione testuale), non errore |
| gpt-oss:20b-cloud | 193 | 37 (19%) | 0.063 | 0.395 | idem |

| `sentiment_signals.model_id` | Righe | Fallback | Score medio | Confidence media |
|---|---|---|---|---|
| ensemble:glm-5.2:cloud+gpt-oss:20b-cloud | 138 (72%) | 0 | 0.054 | 0.309 |
| single:gpt-oss:20b-cloud | 46 (24%) | 46 | 0.041 | 0.528 |
| single:glm-5.2:cloud | 9 (5%) | 9 | 0.080 | 0.522 |

- Nessun errore/timeout esplicito osservabile: **log Docker del 13/08 non esistono più** (redeploy #236 il 14/08 08:20 UTC — F-027, DAY-011); verifica fatta solo via DB.
- `llm_budget` per il 2026-08-13: $0.2268 spesi, 113.620 token input / 14.361 output, `budget_exhausted=false` — nessun segnale di rate-limit o esaurimento budget.
- Fallback rate per ora: 6/27 (14h), 13/38 (15h), 10/40 (16h), 14/35 (17h), 7/23 (18h), 5/30 (19h) — **15-40% ogni ora, mai 100%**: nessuna evidenza di outage Ollama esteso.
- Ogni riga `sentiment_signals` porta esattamente 1 `news_log_id`: nessuna evidenza di doppio conteggio della stessa notizia in più segnali (193 news → 193 signal, 1:1).
- Validazione pre-signal-store: l'output passa da `llm_responses.eligible` (filtro di rilevanza testuale) prima di aggregare in `sentiment_signals`; i modelli sono chiamati da worker Celery in background (queue `inference`), mai nel ciclo di trading — coerente col vincolo architetturale.

## 6. Tabella segnali finali per ticker (movers con segnale)

| Ticker | Return | News | Segnale max (non-fallback) | Causa miss / esito |
|---|---|---|---|---|
| JD | -7.31% | 2 | 0.0 / 0.0 | THIN_NEUTRAL |
| NFLX | +5.43% | 4 | 0.138 (14:15); 0.36 fallback (17:00) | NON_CLASSIFICATO — vedi DAY-003 |
| WDC | +7.31% | — | 0.120 fallback | SKIP_FALLBACK |
| HOOD | +4.70% | 1 | 0.013 | THIN_NEUTRAL |
| PLTR | +4.66% | 1 | 0.385 fallback | NON_CLASSIFICATO — vedi DAY-003 |
| ADBE | +4.54% | 0 | — | NO_NEWS |
| CRM | +4.16% | 0 | — | NO_NEWS |
| TSLA | +3.80% | 5 | -0.15 fallback (16:00) | BELOW_GATE |
| TMUS | +3.53% | 0 | — | NO_NEWS |
| RDDT | +3.04% | 0 | — | NO_NEWS |
| META | +2.78% | multiple | +0.531 → BUY (16:37) → 0.000 (16:45) | Tradato, uscita anticipata — DAY-002 |
| CSCO | -8.40% | — | -0.520 (17:52) | Tradato — SELL sentiment_reversal (posizione S1) |
| SPCX | -3.33% | — | (segnale +0.628 del 08-12, riammesso da FIX-D) | Tradato — SELL forzata da bug pre-fix — DAY-001 |

## 7. Tabella ordini generati/eseguiti

| Timestamp | Strategia | Ticker | Azione | Qty | Prezzo | Stato | Rationale | Anomalia |
|---|---|---|---|---|---|---|---|---|
| 14:22:11 | S4 | SPCX | SELL | 8.294553788 | 142.15085 | filled (`portfolio_sell`) | FIX-D riammette, QS-07 rielimina → peso 0 | **Sì — DAY-001** |
| 16:37:11 | S4 | META | BUY | 3.044219599 | 587.07 | filled | Sentiment +0.531, notizia AI infra | No |
| 17:52:14 | S1 | CSCO | SELL | 6.818458065 | 112.46 | filled (`sentiment_reversal`) | Score -0.520 < soglia -0.35 (cross-strategy — F-033) | Attribuzione, non esecuzione |
| 18:22:15 | S4 | META | SELL | 3.044219599 | 589.43 | filled (`portfolio_sell`) | Segnale sceso a 0.000, `below_entry_gate` | **Sì — DAY-002** |

Nessun ordine con `order_id` duplicato nello stesso minuto; tutti i 4 BUY/SELL hanno `order_id` popolato (nessuna decisione orfana, nessun NO-ORDER); tutti dentro l'orario di mercato 13:30-20:00 UTC.

## 8. Tabella PnL/rendimento

| Simbolo | Strategia | Entry | Exit | Qty | Net PnL | Cost bps | Drift post-uscita |
|---|---|---|---|---|---|---|---|
| SPCX | S4 | 148.36 (08-12) | 142.15085 | 8.294553788 | **-$54.02** | 20.25 | -$7.14 (prezzo ha continuato a scendere) |
| CSCO | S1 | 115.18 (07-15) | 112.46 | 6.818458065 | **-$18.97** | 5.20 | +$6.89 (prezzo risalito dopo l'uscita) |
| META | S4 | 587.07 | 589.43 | 3.044219599 | **+$6.82** | 1.80 | +$16.86 (MTM a EOD se tenuta) |

- **PnL realizzato del giorno: -$66.17** (somma dei 3 trade chiusi).
- NAV: 110460.04 (chiusura 08-12) → 110466.74 (chiusura 08-13) = **+$6.70**.
- Unrealized PnL: $1299.84 (13:30) → $1408.66 (20:00) = +$108.82 sul book aperto.
- Realizzato (-66.17) + variazione unrealized (+108.82) = +$42.65, contro un NAV change di +$6.70: scarto di ~$36 non riconciliato con i soli dati disponibili in questa sessione (possibili commissioni/costi non isolati, o timing dei mark-to-market fra snapshot). **Non stimabile oltre questo con le query disponibili** — servirebbe la riconciliazione cash+posizioni broker↔DB completa (issue #121, nota in memoria come classe di problema aperta).
- Posizioni aperte: 49 (apertura) → 47 (chiusura); coerente con 2 chiusure nette (SPCX, CSCO) e un roundtrip META (+1/-1).

## 9. Analisi correttezza buy/sell

- **BUY generati solo quando consentito**: sì — l'unico BUY (META) ha score sopra gate (0.531 > 0.30), non-fallback, nessuna posizione preesistente sul simbolo.
- **Sell/exit corretti**: CSCO segue la regola `sentiment_reversal` come documentato (score sotto soglia -0.35); META segue `below_entry_gate` come documentato; **SPCX è l'eccezione**: la SELL non ha contro-segnale, ed è generata da un difetto noto e già corretto il giorno dopo (#236) — vedi DAY-001.
- **Signal flip rispettato**: sì per CSCO (segnale esplicitamente negativo).
- **Niente ordini duplicati**: verificato, 0 `order_id` ripetuti.
- **Niente ordini fuori orario**: verificato, tutte le decisioni BUY/SELL cadono 14:22–18:22 UTC, dentro 13:30-20:00.
- **Niente trade su dati stale non gestiti**: SOXX correttamente SKIP_STALE (4.1h > 4h max_age); SPCX è l'eccezione strutturale nota (FIX-D riammette ma QS-07 rielimina).
- **Anti-pyramiding**: 8 blocchi `SKIP_PYRAMIDING` con motivazione esplicita e peso non allocato — la traccia in `execution_decisions` **è presente** (comportamento corretto, vedi §11).
- **Paper/live coerente**: nessuna evidenza di route verso broker live in questa analisi (nessun accesso diretto ad Alpaca in questa sessione, solo DB); non verificabile oltre da questa sessione senza credenziali broker.
- **Idempotenza Celery**: nessuna decisione o trade duplicato nello stesso ciclo; non verificabile in dettaglio senza i log del giorno (spariti — F-027).
- **exit_mechanism (#184) — avvertenza applicata**: la SELL SPCX riporta `[unknown]` nel testo del `reason` (non `expired`/`whipsaw`), quindi **non** è un caso pre-fix-#184 da rietichettare per età; il testo stesso dichiara "the mechanism that zeroed it is not recorded, see #184", cioè il sistema già segnala l'incertezza sul meccanismo. Nessun'altra riga del giorno usa `exit_mechanism` derivato per età.

## 10. Anomalie trovate

### [DAY-001] SELL SPCX senza contro-segnale — istanza pre-fix del bug #236 (QS-07 annulla FIX-D)

* Tipo: Bug (corretto il giorno successivo)
* Area: Signal / Orders
* Evidenza:
  * file/log/tabella: `execution_decisions` id 9842; `trades` id 703; `src/strategies/s4/strategy.py:164-183` (pre-fix), commit `60c6ae0` (fix #236, deploy 2026-08-14T08:20 UTC)
  * timestamp: 2026-08-13 14:22:11 UTC
  * snippet: `[unknown] S4 signal was stale but FIX-D re-admitted it this cycle — open position, no counter-signal — and the weight is 0 anyway: the mechanism that zeroed it is not recorded, see #184 (age=19.6h vs max_age=4h, generated 2026-08-12 18:45 UTC, score=+0.628)`
* Descrizione: FIX-D aveva riammesso il segnale SPCX (stale ma posizione aperta, nessun contro-segnale). Il filtro QS-07 dentro `_signals_as_of` lo ha rieliminato comunque per età, azzerando il peso e forzando la vendita senza alcun segnale contrario. Il fix (#236) è stato deployato il 2026-08-14, cioè **dopo** questo trade — il 2026-08-13 è quindi nella finestra pre-fix.
* Impatto: net_pnl -$54.02, ma `drift_post_uscita` = -$7.14 (il prezzo ha continuato a scendere dopo l'uscita), quindi il controfattuale (tenere la posizione) sarebbe stato **peggiore**, non migliore. Il difetto di correttezza è reale (vendita senza rationale) ma il costo di questa specifica occorrenza è nullo/negativo.
* Severità: High (difetto di correttezza sulla logica di uscita) / costo economico: nullo su questa occorrenza
* Confidenza: High (misurata da DB + confermata dal messaggio di commit del fix)
* Azione consigliata: nessuna — già corretta da #236, deployata il 2026-08-14. Verificare nei prossimi report che non ricompaia.
* Test/monitor consigliato: nel prossimo controllo di metà periodo (~08-28), contare le uscite `[unknown]`/`fix_d_preserved` post-2026-08-14 per confermare che siano scese a zero.
* Ledger: **F-035** (occorrenza 2026-08-13 aggiunta)

### [DAY-002] Articolo macro multi-ticker sovrascrive il segnale che aveva causato il BUY su META, uscita anticipata

* Tipo: Bug (meccanismo noto, ricorrente — F-008)
* Area: Signal / LLM
* Evidenza:
  * file/log/tabella: `sentiment_signals` id 7595 (BUY trigger) e 7601 (overwrite); `news_log` id 7595 ("What Is Going on With Meta Platforms Stock on Thursday?", pubblicato 15:41) e 7601 ("Smart Money Sells #1 Dow Stock; Hidden Inflation In PPI; Applied Materials Earnings To Tell A Key AI Story", pubblicato 15:35 ma processato/scored più tardi); `trades` id 704
  * timestamp: segnale trigger 16:30:31, overwrite 16:45:30, BUY 16:37:11, SELL 18:22:15
* Descrizione: Il BUY nasce da una notizia META-specifica (score ensemble 0.442-0.531). 15 minuti dopo, un articolo generico multi-ticker (macro/PPI/AI infra, che nomina META di striscio) produce uno score 0.000 sullo stesso simbolo. La strategia S4 usa solo l'ultimo segnale per simbolo (meccanismo noto — F-023), quindi il segnale specifico viene sovrascritto e la posizione esce dopo 1h45 per `below_entry_gate`.
* Impatto: net_pnl realizzato +$6.82, ma `mtm_eod` (dossier) = +$24.05: tenendo la posizione fino a chiusura il guadagno sarebbe stato **3.5× superiore**. Costo attribuito = 24.05 - 6.82 = **$16.86**, controfattuale corto (stessa giornata, stesso strumento, stessa size).
* Severità: Medium
* Confidenza: High (misurata da DB, meccanismo già isolato nel codice in occorrenze precedenti)
* Azione consigliata: nessuna in questa finestra (la regola "ultimo segnale vince" è congelata, non tarabile durante l'osservazione).
* Test/monitor consigliato: continuare a contare le occorrenze di F-008/F-023 per la sintesi di fine periodo — soglia attribuita ≥$250 e ≥5 giorni distinti (carta §Soglie).
* Ledger: **F-008** (occorrenza 2026-08-13 aggiunta, $16.86)

### [DAY-003] Il classificatore delle cause di miss del dossier non distingue "fallback sopra soglia escluso dal ranking" da "causa ignota"

* Tipo: Ambiguità (difetto di misura)
* Area: Data
* Evidenza:
  * file/log/tabella: `docs/evidence/dossier/2026-08-13.json` → `candidati_miss` (NFLX, PLTR, causa `NON_CLASSIFICATO`); `sentiment_signals` id 7521 (NFLX, +0.36, fallback, 17:00) e relativo per PLTR (+0.385, fallback, 17:15)
  * timestamp: NFLX segnale 17:00, PLTR segnale 17:15
* Descrizione: Entrambi i simboli hanno un segnale single-model **sopra il gate 0.30** (NFLX 0.36, PLTR 0.385), ma i segnali fallback sono esclusi dal ranking BUY per design (congelato). Il classificatore causale del dossier non ha una categoria per questo caso (distinta da NO_NEWS, THIN_NEUTRAL, BELOW_GATE) e li etichetta `NON_CLASSIFICATO`, indistinguibile da un vero buco di classificazione.
* Impatto: la domanda di uscita n.1 della carta si falsifica su "NO_NEWS resta la causa dominante in ≥60% dei giorni" — un bucket `NON_CLASSIFICATO` che in realtà è "escluso per design" inquina quel conteggio. Coerente con l'issue #208 già in coda roadmap ("il dossier non classifica la causa dei miss").
* Severità: Medium (misura, non esecuzione)
* Confidenza: Medium (il meccanismo di esclusione fallback è confermato da altre righe `SKIP_FALLBACK` dello stesso giorno con testo esplicito, ma non ho verificato il codice del classificatore del dossier in questa sessione)
* Azione consigliata: aggiungere una categoria esplicita (es. `FALLBACK_EXCLUDED`) al classificatore — è correzione di STRUMENTAZIONE, non tocca il comportamento di trading, quindi non è taratura.
* Test/monitor consigliato: contare la frequenza di `NON_CLASSIFICATO` nelle prossime settimane; se resta ricorrente rafforza la priorità di #208.
* Ledger: **F-039 (nuovo)**

### [DAY-004] risk_reports: tre cifre di drawdown incompatibili nello stesso record, ALERT sul valore sbagliato

* Tipo: Bug (ricorrente — F-003)
* Area: Risk
* Evidenza:
  * file/log/tabella: `risk_reports` id 62, 2026-08-13 22:30:01
  * snippet: `combined_drawdown=0.012429` (1.24%) vs `per_strategy_metrics.portfolio.drawdown=0.1719` (17.2%, genera l'ALERT) vs `portfolio_monitor_snapshots.current_drawdown` reale a chiusura = 0.001621 (0.16%)
* Descrizione: Ottava occorrenza consecutiva dello stesso pattern (dal 07-31). Il valore `combined_drawdown` è statico/congelato (identico da settimane), l'alert usa una terza fonte che non corrisponde al drawdown reale osservato dai monitor.
* Impatto: l'alert quotidiano ("drawdown 17.2% exceeds 10%") è rumore sistematico — desensibilizza rispetto a un drawdown vero.
* Severità: Medium
* Confidenza: High
* Azione consigliata: nessuna in questa finestra (correzione di codice, ma non tocca il comportamento di trading — valutabile come remediation ticket post-osservazione).
* Test/monitor consigliato: nessuno nuovo, il pattern è già tracciato (TK-G, TK-R7).
* Ledger: **F-003** (occorrenza 2026-08-13 aggiunta)

### [DAY-005] decay_reports: metriche identiche su S1/S2/S4, S2 (mai tradata) riceve CRITICAL

* Tipo: Bug (ricorrente — F-004)
* Area: Risk
* Evidenza:
  * file/log/tabella: `decay_reports`, 2026-08-13 21:00:00
  * snippet: `actual_value` identico per le tre strategie su tutte e 4 le metriche (hit_rate 0.328, ic 0.0219, max_drawdown 0.115, sharpe -6.987), confrontato contro 3 baseline diverse → CRITICAL su sharpe per tutte e tre
* Descrizione: `_fetch_actual_metrics` non filtra per `strategy_id`; S2 è disabilitata (0% allocazione, morta da audit 2026-08-04) e riceve comunque alert CRITICAL come se fosse viva.
* Impatto: il meccanismo di sorveglianza del decadimento — su cui la carta si appoggia per le domande di uscita — non distingue S1 da S4.
* Severità: Medium
* Confidenza: High
* Azione consigliata: nessuna in questa finestra.
* Test/monitor consigliato: nessuno nuovo (già TK-R8).
* Ledger: **F-004** (occorrenza 2026-08-13 aggiunta)

### [DAY-006] Copertura news: 41/96 simboli a zero notizie, 4 mover puri NO_NEWS

* Tipo: Osservazione (ricorrente — F-001)
* Area: News
* Evidenza:
  * file/log/tabella: `docs/evidence/dossier/2026-08-13.json` → `mercato.watchlist_zero_news=41`, `candidati_miss`
  * snippet: ADBE +4.54% (0 news), CRM +4.16% (0 news), TMUS +3.53% (0 news), RDDT +3.04% (0 news)
* Descrizione: Stessa banda 40-57% osservata dal 07-31; tutti e quattro i mover puri NO_NEWS sono al rialzo (book long-only, quindi tradabili in teoria).
* Impatto: alpha mancato congetturale, size S4 tipica $2200: ADBE 99.82 + CRM 91.61 + TMUS 77.62 + RDDT 66.95 = **$336.00**
* Severità: Low (congetturale)
* Confidenza: Medium (nessun trade avvenuto, size ipotetica)
* Azione consigliata: nessuna in questa finestra (taratura fonti dati congelata).
* Test/monitor consigliato: nessuno nuovo.
* Ledger: **F-001** (occorrenza 2026-08-13 aggiunta, $336.00)

### [DAY-007] Contatore duplicati ingestion_stats_daily 4.4× il fetched (alpaca_benzinga)

* Tipo: Osservazione (ricorrente — F-007)
* Area: Data
* Evidenza:
  * file/log/tabella: `ingestion_stats_daily`, day=2026-08-13, source=alpaca_benzinga: fetched=737, duplicates=3261
* Descrizione: Contatore additivo cross-run (`src/store/pg_store.py:369`), non verificabile indipendentemente contro conteggi per-ciclo (log spariti). `news_log` finale non mostra segni di problemi di dedup (0 righe scartate).
* Impatto: nessuno sui dati finali; riduce l'affidabilità del contatore come metrica stand-alone.
* Severità: Low
* Confidenza: Medium
* Azione consigliata: nessuna in questa finestra.
* Test/monitor consigliato: nessuno nuovo.
* Ledger: **F-007** (occorrenza 2026-08-13 aggiunta)

### [DAY-008] execution_decisions.signal_id NULL su 546/556 righe (98.2%)

* Tipo: Osservazione (ricorrente — F-011)
* Area: Data
* Evidenza:
  * file/log/tabella: `execution_decisions`, 2026-08-13: 556 righe totali, 546 con `signal_id IS NULL`
* Descrizione: La maggioranza delle righe (soprattutto `SKIP_THRESHOLD`, 540/556) non porta il riferimento al segnale valutato; la catena segnale→decisione non è ricostruibile per chiave esterna sulla quasi totalità dei casi.
* Impatto: analisi forensi (come questa) devono ricostruire il collegamento per simbolo+timestamp invece che per chiave, con margine di errore.
* Severità: Low
* Confidenza: High
* Azione consigliata: nessuna in questa finestra.
* Test/monitor consigliato: nessuno nuovo.
* Ledger: **F-011** (occorrenza 2026-08-13 aggiunta)

### [DAY-009] Log Docker del 2026-08-13 non più disponibili (redeploy del 2026-08-14 per #236)

* Tipo: Ambiguità (ricorrente — F-027)
* Area: Ops
* Evidenza:
  * file/log/tabella: `docker inspect alembic-worker-1` → `StartedAt=2026-08-14T08:20:11Z`; `docker compose logs worker --since 48h` → 0 righe con prefisso `2026-08-13`
* Descrizione: Il worker e worker-inference sono stati riavviati il 2026-08-14 alle 08:20 UTC per il deploy del fix #236, cancellando tutti i log Docker della giornata analizzata. Questa analisi si basa quindi solo su DB (nessuna verifica incrociata via log per errori/timeout/retry Celery).
* Impatto: riduce la profondità verificabile di questo stesso report (fasi 4 "log errori" e 7 "idempotenza Celery" non verificabili oltre il DB).
* Severità: Medium (limita l'auditabilità)
* Confidenza: High
* Azione consigliata: nessuna in questa finestra (persistenza log è remediation strutturale, non taratura).
* Test/monitor consigliato: nessuno nuovo (F-027 già tracciato).
* Ledger: **F-027** (occorrenza 2026-08-13 aggiunta)

### [DAY-010] SELL CSCO con motivazione S4 (sentiment_reversal) su posizione detenuta da S1

* Tipo: Osservazione (ricorrente — F-033)
* Area: PnL
* Evidenza:
  * file/log/tabella: `trades` id 334, `stop_strategy='S1'`, `exit_reason='sentiment_reversal'`
* Descrizione: La regola `sentiment_reversal` è globale (itera su tutte le posizioni Alpaca senza filtro di strategia), quindi una decisione S4-style chiude una posizione S1. Il P&L resta attribuito a S1 anche se la decisione di uscita non è sua.
* Impatto: contaminazione di attribuzione (non di esecuzione) sulla serie realizzata S1, rilevante per la domanda di uscita n.2 della carta.
* Severità: Low (misura, non P&L)
* Confidenza: High
* Azione consigliata: nessuna in questa finestra.
* Test/monitor consigliato: nessuno nuovo.
* Ledger: **F-033** (occorrenza 2026-08-13 aggiunta)

### [DAY-011] Beat/portfolio scheduler in UTC fisso (EST): primi 37 minuti di sessione EDT scoperti

* Tipo: Bug (ricorrente — F-021)
* Area: Ops
* Evidenza:
  * file/log/tabella: `execution_decisions` primo ciclo 14:07:00 vs apertura mercato 13:30:00 UTC; `celery_app.py` crontab `hour='14-21'`
* Descrizione: 24 cicli regolari da 14:07 a 19:52, nessun gap >16 min; nessun ciclo eseguito dopo la chiusura (buon segno rispetto ad altre occorrenze storiche). Il buco dei primi 37 minuti resta strutturale.
* Impatto: non stimabile per oggi — nessun segnale utile nato prima delle 14:01.
* Severità: Low
* Confidenza: High
* Azione consigliata: nessuna in questa finestra.
* Test/monitor consigliato: nessuno nuovo.
* Ledger: **F-021** (occorrenza 2026-08-13 aggiunta)

### [DAY-012] Anti-pyramiding: 8 blocchi SKIP_PYRAMIDING su segnali S4 sopra gate, costo non stimato per assenza di barre intraday

* Tipo: Osservazione (ricorrente — F-031)
* Area: Signal
* Evidenza:
  * file/log/tabella: `execution_decisions` id 9843, 9859, 9879, 10124, 10208, 10237, 10260, 10284 (MU, CSCO, AMD, IWM, NOK, PANW, QQQ, XLK)
* Descrizione: La traccia in `execution_decisions` **è presente** con motivazione esplicita ("P0-05 anti-pyramiding... peso non allocato X%"), confermando che il difetto originario di F-031 ("nessuna traccia") non descrive più il comportamento attuale (dal 08-11). Il blocco stesso resta regola di design congelata.
* Impatto: non stimato in questa sessione — servirebbe query sui prezzi intraday Alpaca ai timestamp dei segnali (non eseguita per limiti di tempo di questa sessione).
* Severità: Low
* Confidenza: Low (costo non calcolato)
* Azione consigliata: nessuna in questa finestra.
* Test/monitor consigliato: nessuno nuovo.
* Ledger: **F-031** (occorrenza 2026-08-13 aggiunta, costo null)

## 11. False positive o aree risultate corrette

- **Anti-pyramiding (P0-05)**: il blocco lascia traccia esplicita in `execution_decisions` con peso non allocato — il vecchio sospetto "nessuna traccia" (titolo originale F-031) **non descrive più il presente** dal 2026-08-11.
- **Nessun ordine fuori orario**: tutte le decisioni BUY/SELL cadono dentro 13:30-20:00 UTC.
- **Nessun ordine duplicato**: 0 `order_id` ripetuti nello stesso minuto o altrove.
- **Nessuna evidenza di outage Ollama**: fallback rate 15-40%/ora, mai 100%; budget LLM regolarmente speso.
- **Nessuna news futura o fuori sequenza**: 0 righe con `published_at > fetched_at + 1min`.
- **Cost model su SPCX/CSCO/META**: tutti e tre hanno un tier esplicito in `cost_model.yaml` (non ricadono nel default 20bps del difetto F-034).
- **exit_mechanism**: la SELL SPCX del giorno è già etichettata `[unknown]` in modo trasparente (non `expired`/`whipsaw` per errore di stima) — l'avvertenza #184 non si applica falsamente qui.

## 12. Dati mancanti o non accessibili

- **API REST locale**: il token Bearer fornito ha restituito `Invalid or expired JWT token` su tutti gli endpoint (`/decisions`, `/trades`, `/positions`). Compensato con query dirette al DB Postgres (dati equivalenti o superiori in dettaglio).
- **Log Docker worker/worker-inference del 2026-08-13**: assenti, cancellati dal redeploy del 2026-08-14T08:20 UTC per #236 (F-027, DAY-009). Nessuna verifica incrociata di errori/retry/timeout via log per questa giornata.
- **Riconciliazione broker↔DB** (posizioni, cash): non eseguita in questa sessione (richiede accesso Alpaca diretto, fuori scope read-only-DB); lo scarto ~$36 fra realizzato+unrealized e nav_change (§8) resta non spiegato con i dati disponibili.
- **Barre intraday per i simboli bloccati da SKIP_PYRAMIDING**: non interrogate; costo di quell'occorrenza (DAY-012) resta non stimato.
- **Codice del classificatore causale del dossier**: non letto in questa sessione; l'ipotesi su NON_CLASSIFICATO (DAY-003) è dedotta dai dati, non confermata da lettura di codice.

## 13. Raccomandazioni immediate

Nessuna azione di taratura è ammessa in questa finestra di osservazione. Le uniche azioni compatibili con la carta sono di correttezza/strumentazione, già segnalate nei finding sopra: nessuna richiede intervento immediato (il difetto con impatto reale, #236, è già stato corretto e deployato).

## 14. Test o monitor da aggiungere

- Contatore post-2026-08-14 delle uscite `[unknown]`/`fix_d_preserved` per confermare l'efficacia di #236 nel tempo (si aggancia a DAY-001/F-035).
- Nessun nuovo monitor proposto oltre quelli già in coda (TK-G, TK-R7, TK-R8, TK-A, TK-I, TK-F) per gli altri finding ricorrenti.

## 15. Ticket tecnici suggeriti

Nessun ticket nuovo oltre **F-039** (classificatore causale del dossier, categoria mancante per segnali fallback esclusi per design — correzione di strumentazione, non tocca il comportamento di trading, quindi ammissibile durante il freeze). Gli altri finding del giorno sono ricorrenze di ticket già aperti (vedi ledger).

## 16. Stato sistema

- **Ollama**: nessuna evidenza di downtime. Budget LLM regolarmente utilizzato ($0.2268, 113.620 token input), fallback rate 15-40%/ora (mai 100%).
- **FinBERT fallback rate**: non distinguibile da questa analisi — i "fallback" osservati in `sentiment_signals` sono single-model LLM (glm-5.2 o gpt-oss), non FinBERT deterministico; nessuna riga con `model_id` riconducibile a FinBERT nel campione del giorno.
- **Worker restart events**: `alembic-worker-1` e `alembic-worker-inference-1` riavviati il **2026-08-14T08:20:11 UTC** (fuori dalla giornata analizzata, per il deploy di #236) — nessun restart rilevato *durante* il 2026-08-13 dai dati disponibili (impossibile confermare via log, assenti).

---

*Report generato in sessione autonoma read-only. Nessun file di codice modificato, nessun ordine inviato, nessuna pipeline live rieseguita.*
