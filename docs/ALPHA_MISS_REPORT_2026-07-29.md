# Alpha Miss Report — 2026-07-29 (mercoledì)

Scope: solo i 96 simboli in `config/trading.yaml` → `symbols.watchlist`. Rendimenti Alpaca daily
bars (`StockHistoricalDataClient`, feed IEX, close 2026-07-29 vs close 2026-07-28). Dati Alembic
da `alembic-postgres-1` (trades, execution_decisions, sentiment_signals, news_log,
portfolio_cycles) e `alembic-redis-1` (stato gate feedback). Nessuna modifica al codice o al
sistema — solo lettura. Tutti i 96 simboli hanno barre disponibili per entrambe le date, nessun
gap dati sui prezzi.

## 1. Executive summary

- Soglia mover: **|return| ≥ 3%** — coerente con i report precedenti, punto in cui il rendimento
  giornaliero esce dalla banda di rumore tipica della watchlist (la maggioranza dei nomi oggi sta
  in ±2.5%).
- **29/96 mover rilevanti** (7 al rialzo, 22 al ribasso) — giornata ad alta dispersione, guidata
  da un forte sell-off dei semiconduttori/hardware e da un selloff diffuso nei financials, in parte
  compensato da un rialzo nel software enterprise/SaaS.
- **4/29 mover catturati** (SNOW, BA, NVDA, CAT — quest'ultimi due con esito negativo/misto).
  **25/29 mancati**.
- Causa prevalente dei miss: **NO_NEWS** (12/25, 48%) — copertura news zero. Seguono
  **THIN_NEUTRAL** (7/25, 28% — segnale presente ma troppo debole su tutti i modelli) e
  **FILTERED** (6/25, 24% — segnale di magnitudine sufficiente esisteva ma era prodotto solo dal
  modello fallback e scartato dalla regola #108, che vieta un BUY basato su un singolo segnale
  fallback).
- **Nessun caso WRONG_SIGN puro** (nessun segnale di ensemble forte con segno opposto al prezzo).
- 24 cicli di portfolio, cadenza 15 min regolare tutto il giorno (14:07→19:52 UTC), nessun gap.
- **Finding degno di nota (non un limite noto, sembra un gap di instrumentation)**: `SKIP_THRESHOLD`
  in `execution_decisions` è passato da 146 (07-27) e 250 (07-28) righe a **zero** il 07-29. Causa
  identificata nel codice: `_get_feedback_threshold` ricade su `S4Config().min_score` (0.1) quando
  la chiave Redis `feedback:entry_threshold:S4` è assente, e la condizione
  `_fb_threshold > s4_config.min_score` (0.1 > 0.1) è falsa — l'intero gate/logging si
  autodisattiva. Una costante `_ENTRY_THRESHOLD_BASELINE` (0.30) esiste apposta per evitare questo
  fallback ma non è mai referenziata altrove nel file — codice morto. Nessun impatto di trading
  osservato (il prefiltro ranker min_score/min_confidence resta comunque attivo), ma la visibilità
  del Decision Log su "perché nessun trade" sparisce ogni volta che il ratchet è a baseline.
  Segnalo, non filo io un'issue.

## 2. Tabella completa rendimenti (96 simboli)

| Simbolo | Return % | Catturato |
|---|---:|:---:|
| ADBE | +5.71% | no |
| NOW | +4.72% | no |
| SNOW | +4.72% | **sì** |
| BP | +4.00% | no |
| CRM | +3.84% | no |
| SAP | +3.81% | no |
| TM | +3.42% | no |
| PBR | +2.88% | no |
| SONY | +2.53% | no |
| SHEL | +2.50% | no |
| XOM | +2.39% | no |
| CVX | +2.31% | no |
| INFY | +2.27% | no |
| RIO | +2.22% | no |
| F | +2.11% | **sì** |
| XLE | +1.90% | no |
| NFLX | +1.74% | no |
| CMCSA | +1.69% | no |
| JD | +1.40% | no |
| NVO | +1.25% | no |
| SBUX | +1.14% | no |
| WMT | +1.01% | no |
| ROKU | +0.97% | no |
| GOOGL | +0.81% | no |
| COST | +0.77% | no |
| V | +0.65% | **sì** |
| NKE | +0.53% | no |
| AZN | +0.41% | no |
| DB | +0.38% | no |
| BIDU | +0.38% | no |
| ABBV | +0.17% | no |
| MA | +0.08% | no |
| RDDT | -0.14% | no |
| BABA | -0.16% | no |
| VALE | -0.34% | no |
| PLTR | -0.38% | no |
| JNJ | -0.38% | no |
| UBS | -0.40% | no |
| WDC | -0.41% | no |
| IBM | -0.41% | no |
| PFE | -0.42% | no |
| TMUS | -0.42% | no |
| DIS | -0.42% | no |
| MCD | -0.50% | no |
| AAPL | -0.52% | no |
| BRK.B | -0.60% | no |
| XLV | -0.61% | no |
| MSFT | -0.62% | no |
| LLY | -0.89% | no |
| GM | -0.95% | no |
| META | -1.00% | no |
| MRK | -1.09% | no |
| PANW | -1.47% | no |
| AXP | -1.51% | no |
| SPY | -1.52% | no |
| XLF | -1.56% | no |
| IWM | -1.62% | no |
| AMZN | -1.70% | no |
| ORCL | -1.75% | no |
| HD | -1.79% | no |
| PG | -1.85% | no |
| UNH | -1.93% | no |
| ASML | -1.94% | no |
| ERIC | -1.96% | no |
| TXN | -1.97% | no |
| VZ | -2.01% | no |
| QQQ | -2.04% | **sì** |
| MMM | -2.45% | no |
| BAC | -2.47% | no |
| XLK | -2.66% | no |
| AVGO | -2.66% | no |
| CSCO | -2.71% | no |
| T | -2.94% | no |
| TSLA | -2.95% | no |
| SPCX | -3.34% | no |
| BA | -3.38% | **sì** |
| WFC | -3.46% | no |
| JPM | -3.46% | no |
| HOOD | -3.50% | no |
| NVDA | -3.53% | **sì** |
| GE | -3.56% | no |
| MS | -3.98% | no |
| C | -4.03% | no |
| QCOM | -4.40% | no |
| TSM | -4.47% | no |
| INTC | -5.02% | no |
| GS | -5.07% | no |
| SOXX | -5.40% | no |
| AMD | -5.58% | no |
| NOK | -5.67% | no |
| DELL | -5.73% | no |
| MRVL | -6.29% | no |
| CAT | -6.97% | **sì** |
| AMAT | -8.28% | no |
| ARM | -8.28% | no |
| MU | -9.96% | no |

(F, QQQ, V hanno scambi il 07-29 ma sono sotto soglia |3%| — non classificati come mover, elencati
come "sì" per completezza.)

## 3. Tabella dei miss classificati (mover ≥3%, non catturati)

| Simbolo | Return % | Categoria | Evidenza |
|---|---:|---|---|
| ADBE | +5.71% | NO_NEWS | 0 righe `news_log` il 07-29 |
| NOW | +4.72% | NO_NEWS | 0 righe `news_log` il 07-29 |
| CRM | +3.84% | NO_NEWS | 0 righe `news_log` il 07-29 |
| SAP | +3.81% | NO_NEWS | 0 righe `news_log` il 07-29 |
| WFC | -3.46% | NO_NEWS | 0 righe `news_log` il 07-29 |
| GE | -3.56% | NO_NEWS | 0 righe `news_log` il 07-29 |
| C | -4.03% | NO_NEWS | 0 righe `news_log` il 07-29 |
| QCOM | -4.40% | NO_NEWS | 0 righe `news_log` il 07-29 |
| SOXX | -5.40% | NO_NEWS | 0 righe `news_log` il 07-29 (ETF settoriale semis, nessuna copertura news per costruzione) |
| DELL | -5.73% | NO_NEWS | 0 righe `news_log` il 07-29 |
| MRVL | -6.29% | NO_NEWS | 0 righe `news_log` il 07-29 |
| ARM | -8.28% | NO_NEWS | 0 righe `news_log` il 07-29 |
| BP | +4.00% | THIN_NEUTRAL | 1 articolo, score ensemble = 0.000, confidence 0.20 |
| TM | +3.42% | THIN_NEUTRAL | 1 articolo, score ensemble = 0.000, confidence 0.15 |
| JPM | -3.46% | THIN_NEUTRAL | 1 articolo, score +0.007 (segno irrilevante, ampiezza trascurabile), confidence 0.25 |
| TSM | -4.47% | THIN_NEUTRAL | 8 articoli, 7 letture ensemble/fallback tutte in banda ±0.12, mai sopra min_score 0.1 in modo consistente |
| INTC | -5.02% | THIN_NEUTRAL | 2 articoli, score ~0.000/-0.010, confidence 0.20-0.225 |
| NOK | -5.67% | THIN_NEUTRAL | 2 articoli, score 0.000/-0.053, confidence 0.225-0.325 |
| HOOD | -3.50% | THIN_NEUTRAL | 3 articoli, score max 0.09 (fallback, sotto min_score 0.1), resto ~0 — troppo debole per essere "wrong sign" pieno |
| AMAT | -8.28% | FILTERED | fallback `single:gpt-oss:20b-cloud` score -0.1925 conf 0.55 (18:01) qualificherebbe min_score/min_confidence ma è escluso da BUY ranking per regola #108 (`portfolio_scheduler.py:3103-3109`, "no BUY su segnale fallback-only"); ensemble non-fallback restava ~0 tutto il giorno |
| AMD | -5.58% | FILTERED | fallback score -0.15 conf 0.6 (19:46) escluso da #108; ensemble non-fallback ~0 tutto il giorno |
| GS | -5.07% | FILTERED | 2 fallback qualificanti (-0.125 conf 0.5 alle 16:31, -0.22 conf 0.55 alle 17:31) esclusi da #108; ensemble non-fallback ~0 su 14 riletture |
| MS | -3.98% | FILTERED | 3 fallback qualificanti, **segno prevalentemente positivo** (0.165 conf 0.55, 0.42 conf 0.7 ×2) contro un ribasso -3.98% — #108 li esclude comunque, quindi in questo caso la regola ha *evitato* un ipotetico BUY a segno sbagliato; ensemble non-fallback restava ~0 |
| SPCX | -3.34% | FILTERED | fallback -0.20 conf 0.4 (17:01) escluso da #108; ensemble ~0 |
| MU | -9.96% | FILTERED | il mover più forte del giorno. 20 articoli, letture fallback fortemente divergenti ed escluse da #108: due positive (0.42 conf 0.6, 0.2275 conf 0.65 — segno sbagliato) e tre negative (-0.36, -0.18, -0.12, conf 0.6) nello stesso pomeriggio; ensemble non-fallback restava vicino a zero (±0.09) senza mai superare min_score in modo stabile. Zero righe in `execution_decisions` per l'intera giornata |

**Nota metodologica**: nessuna riga `SKIP_THRESHOLD` esiste il 07-29 (vedi §1/§6), quindi le
classificazioni THIN_NEUTRAL/FILTERED sopra sono ricostruite direttamente da `sentiment_signals`
(punteggio, confidence, `fallback_used`) e dal codice della regola #108, non dal Decision Log —
che quel giorno non registra alcun evento di scarto per soglia/fallback.

## 4. Titoli catturati: esito

| Simbolo | Strategia | Entry | Exit | Net P&L | Exit reason | Note |
|---|---|---|---|---:|---|---|
| SNOW | S4 | 07-29 14:37 @ 284.04 | posizione ancora aperta | — | — | BUY su sentiment ensemble reale +0.542 (conf 0.775), il segnale più forte e più pulito del giorno; nessuna uscita entro la sessione |
| BA | S4 | 07-28 14:07 @ 220.35 | 07-29 14:22 @ 213.82 | **-$37.80** | portfolio_sell (segnale S4 scaduto, age 24.3h > max 4h) | posizione aperta il giorno prima, l'uscita non è guidata dal ribasso del 07-29 in sé ma dalla scadenza del segnale + rebalance; nessuna news nuova per BA il 07-29 |
| NVDA | S4 | 07-29 15:07 @ 192.78 | 07-29 17:22 @ 192.93 | **+$0.73** | portfolio_sell (whipsaw: "S4 signal present but not driving allocation") | entrato su sentiment debole (+0.10), uscito 2h15 dopo quasi a pari prezzo — timing neutro, non ha catturato il ribasso -3.53% del titolo (anzi lo ha mancato per intero, essendo dentro solo a metà giornata) |
| CAT | S1 | 07-14 14:07 @ 945.14 (posizione pre-esistente) | 07-29 18:52 @ 792.26 | **-$125.94** | sentiment_reversal (score -0.510 < soglia -0.35) | posizione S1 aperta da 15 giorni, liquidata in perdita nel pomeriggio del giorno peggiore (-6.97%) — timing subottimale (l'uscita arriva a mercato già ampiamente sceso, non in anticipo). **Nota comportamentale**: subito dopo la SELL, S1 ha tentato 4 ri-acquisti consecutivi (19:07→19:52, "S1 momentum", weight 1.2%) tutti con `order_id` vuoto in `execution_decisions` — decisi ma mai eseguiti, scartati a valle (probabile constraint di portafoglio/anti-churn) |

## 5. Pattern osservato

Rotazione settoriale abbastanza netta, non casuale:
- **Semiconduttori/hardware in vendita pesante**: 12 dei 22 mover negativi appartengono al bucket
  `semis` del sector map (MU -9.96%, ARM -8.28%, AMAT -8.28%, CAT -6.97%*, MRVL -6.29%, DELL
  -5.73%, NOK -5.67%, AMD -5.58%, SOXX -5.40%, GS -5.07%**, INTC -5.02%, TSM -4.47%, QCOM -4.40%).
  (*CAT è industrials nel sector map ma muove in linea col gruppo semis quel giorno; **GS è
  financials, non semis — la sovrapposizione qui è temporale non settoriale.)
- **Financials in vendita marcata**: 5 dei 22 mover negativi sono nel bucket `financials` (GS
  -5.07%, C -4.03%, MS -3.98%, WFC -3.46%, JPM -3.46%) — un secondo cluster distinto dai semis,
  stesso giorno.
- **Software enterprise/SaaS in acquisto**: 3 dei 7 mover positivi sono `tech`/SaaS (ADBE +5.71%,
  NOW +4.72%, CRM +3.84%; SNOW +4.72% è staging/data cloud, stesso tema). SAP (+3.81%) rinforza il
  tema a livello ADR europeo.
- **Energy leggermente positivo**: BP +4.00% è il mover energy più forte; XOM/CVX/SHEL/PBR sono
  positivi ma sotto soglia 3%, coerenti con lo stesso segno.

In sintesi: giornata con vendita pesante su semis + financials, compensata da un acquisto
enterprise-software/SaaS — una rotazione "growth-hardware out, enterprise-SaaS + energy in" più
marcata della rotazione vista il 07-28 (che era già semis-down/SaaS-up, ma senza il secondo
cluster financials).

## 6. Confronto con i report precedenti

- **NO_NEWS resta la causa di miss dominante ogni giorno analizzato finora** (07-27: 50%, 07-28:
  citato come principale, 07-29: 48%) — non è un'anomalia di giornata, è un gap di copertura
  strutturale della watchlist che si ripete.
- Il tema "rotazione semiconduttori↔software enterprise" è **lo stesso identificato il 07-28**
  (11/15 mover negativi semis, 6/11 positivi tech/SaaS quel giorno) — oggi il pattern si ripete e
  si aggrava (12/22 semis negativi) con l'aggiunta di un cluster financials che il 07-28 non era
  presente. Merita attenzione se continua: la watchlist attuale sembra strutturalmente esposta a
  rotazioni settoriali ricorrenti hardware/software.
- Il 07-28 il report aveva segnalato un'anomalia isolata su ADBE (segnale ensemble reale sotto
  soglia ma zero righe `execution_decisions`, mentre altri simboli comparabili avevano
  `SKIP_THRESHOLD`). Oggi quell'anomalia si generalizza: **zero** righe `SKIP_THRESHOLD` per
  **qualsiasi** simbolo, con causa ora identificata a livello di codice (§1, §7) — non è più solo
  un'osservazione isolata su ADBE, è un comportamento sistemico del gate quando il ratchet è a
  baseline.
- Il 07-28 c'erano "4 simboli FILTERED by design (esclusione fallback #108...)" senza dettaglio;
  oggi lo stesso meccanismo (#108) spiega 6 miss su 25 con evidenza puntuale per ciascuno (§3) —
  stesso meccanismo, stessa giornata-tipo ad alta dispersione con molta copertura news di bassa
  qualità (solo fallback, niente ensemble convergente).

## 7. Nota su bug vs limiti noti

- **#108 (esclusione BUY su segnale fallback-only)**: comportamento intenzionale e documentato nel
  codice, non un bug. Ha funzionato come da design il 07-29, e in almeno un caso (MS) ha
  probabilmente evitato un BUY a segno sbagliato basato su un singolo modello fallback discorde
  dall'ensemble.
- **Sparizione totale di `SKIP_THRESHOLD` il 07-29** (§1, §6): questo *non* sembra un limite noto
  o una scelta di design — la costante `_ENTRY_THRESHOLD_BASELINE` (0.30) esiste nel codice
  proprio per evitare che il gate ricada al floor `min_score` (0.1), ma non è mai usata altrove nel
  file (`grep` conferma zero altri riferimenti). Il risultato osservato è che il gate/logging si
  autodisattiva silenziosamente quando la chiave Redis `feedback:entry_threshold:S4` è assente —
  ricostruito da codice + dati, non da log applicativi (nessuna riga "gate-dropped" nei log worker
  del 07-29). Non ha (per quanto verificabile) cambiato l'esito dei trade — il prefiltro ranker
  min_score/min_confidence resta comunque attivo indipendentemente — ma toglie visibilità
  diagnostica sul "perché nessun trade" ogni volta che il ratchet è a baseline. Segnalo il fatto;
  la decisione se aprire un'issue è dell'operatore.
