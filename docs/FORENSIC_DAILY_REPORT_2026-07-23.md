# Forensic Daily Report — 2026-07-23

Analista: Claude (sessione autonoma read-only) · Generato: 2026-07-24
Timezone operativo: **UTC** (`celery_app.py`: `timezone="UTC"`, `enable_utc=True` — non ambiguo).
Fonti: PostgreSQL `trading` (query dirette — API REST inaccessibile, JWT invalido anche oggi, vedi §12), log Docker `worker`/`worker-inference`/`beat` (finestra disponibile: nessun restart container dal 2026-07-22 12:13:54 UTC → copre l'intera giornata di mercato del 07-23 senza buchi), `docker exec` su Redis per verifica stato kill-switch corrente, lettura codice sorgente per verificare i meccanismi osservati nei log.

---

## 1. Executive Summary

Giornata di mercato regolare: 198 news ingerite (2 fonti attive), 200 sentiment signal generati, **13 decisioni execution non-SKIP** (7 BUY, 6 SELL) su 269 valutazioni totali. Ollama **100% disponibile, zero timeout** (miglior giorno recente). Nessun ordine live: S1=`supervised_paper`, S4=`paper`, `constraints_fired: []` su tutti i 24 cicli — nessun breccia automatica di rischio. Due meccanismi di sicurezza recentemente introdotti sono stati **verificati funzionanti dal vivo per la prima volta**: (1) il reversal-cooldown cross-strategy (#68) ha correttamente bloccato 2 tentativi di BUY S1 su IWM dopo una forced-sell per sentiment reversal di S4 sullo stesso simbolo; (2) il fix #59 (blocco BUY su segnale fallback) tiene — l'unico segnale FinBERT-fallback della giornata (META, score −0.268) non ha mai generato un ordine. Persistono però tre problemi noti non risolti da ieri: (1) `mobile_alert_task` fallisce ancora **100% (480/480)** per il secondo giorno consecutivo — bug strutturale non fixato; (2) la posizione orfana WDC (#373, aperta 07-21) è ora al **terzo giorno** senza riconciliazione, e oggi il meccanismo di exit-hysteresis l'ha ri-flaggata per l'uscita alle 16:37 senza però completare una terza SELL; (3) il ratchet di loss-feedback su S1 si è ri-applicato sulla stessa evidenza stale (EWMA R −0.55, 11 loss, −$178.68) due volte nello stesso giorno (14:00 e 18:30), riducendo ulteriormente regime_scale 0.26→0.21→0.20. Nuovo elemento: alle 21:37–21:38 UTC (post-market) sono comparsi in sequenza un'attivazione kill-switch, tre INSERT di trade di test (`TEST_STOP_1/2/3`, poi rimossi senza traccia di DELETE in audit_log) e una riga di ingestion-stats per `reuters` nonostante RSS sia disabilitato — pattern coerente con un test manuale dell'operatore su un ambiente non isolato dalla tabella `trades` di produzione, che ricalca un problema già visto l'11/07. PnL realizzato giornaliero: **−$50.88 netto** su 6 chiusure (5 S4, 1 S1 cross-strategy-exit).

**Verdict: OK con warning.**

---

## 2. Verdict Finale

**OK con warning** — la pipeline end-to-end (news→sentiment→segnale→decisione→ordine→fill→posizione) ha funzionato correttamente, i guardrail chiave hanno operato come previsto e due protezioni introdotte di recente (#68 reversal-cooldown cross-strategy, #59 blocco BUY-su-fallback) sono state osservate in azione dal vivo con esito positivo. Il downgrade da "OK" a "OK con warning" è dovuto a: un bug noto già Critical ieri (mobile alert) ancora non fixato dopo 24h, una posizione orfana (WDC) che ha ora accumulato 3 giorni senza riconciliazione con segnali di stallo crescente, un pattern di test manuale che ha toccato direttamente la tabella `trades` di produzione senza audit trail completo, e mancata consegna di notifiche Telegram su eventi di rischio. Nessuno di questi ha causato ordini scorretti verso il broker né violazioni dei constraint di rischio configurati.

---

## 3. Timeline 2026-07-23 (UTC)

| Ora UTC | Componente | Evento |
|---|---|---|
| 14:00:00 | `loss-feedback-check` | S1: EWMA R −0.55, 11 consecutive losses, rolling P&L −$178.68 → threshold 0.30→0.00, regime_scale 0.26→0.21 |
| 14:00:00 | `loss-feedback-check` | S4 decay: threshold 0.45→0.40 dopo 24h senza trigger |
| 14:00:00 | `mobile-alert-evaluation` | Primo di 480 fallimenti consecutivi della giornata (`HTTPException 503 Cache unavailable`) |
| 14:00:00 | Telegram | Invio alert loss-feedback S1 fallito (400 Bad Request) |
| 14:15–19:46 | `run-news-ingestion` / `run-alpaca-ingestion` | Ingest continuo gdelt_gkg (103) + alpaca_benzinga (95) |
| 14:15–19:46 | `sentiment-worker` | ~24 cicli, 200 sentiment_signals scritti (glm-5.2 + gpt-oss), 1 hard fallback FinBERT (META) |
| 14:22:00 | `execution_decisions` #3805 | BUY NOW (S4 news, sentiment +0.600, peso 2.0%) → trade #405 @ $97.19 |
| 15:22:00 | `execution_decisions` #3868/#3869 | BUY TSLA (sentiment +0.510) + BUY INFY (sentiment +0.380) → trade #406, #407 |
| 16:07:00 | `execution_decisions` #3918 | BUY TXN (sentiment +0.362) → trade #408 |
| 16:15–16:16 | `sentiment_signals` | TSLA riceve due segnali quasi opposti a 60s di distanza: −0.60 (EPS miss) poi +0.52 (commento Musk su CapEx) |
| 16:37:07 | worker | "Exit hysteresis (2 cycles): held 1 position(s) flagged for exit: ['WDC']" — 3° tentativo di uscita WDC, non completato oggi |
| 17:07:00 | `execution_decisions` #3979/#3980 | SELL INFY + SELL TSLA (`[whipsaw]`, shadow would_suppress=True, flag OFF → eseguite) → chiudono #407 (+$7.82), #406 (+$6.59) |
| 17:07:10 | worker | "Failed to sync protective stop for INFY" — insufficient qty (race con SELL appena eseguita) |
| 17:52:00 | `execution_decisions` #4015/#4016 | BUY INFY (sentiment +0.381, nuovo segnale) + SELL TXN (`[whipsaw]`) → trade #409, chiude #408 (−$11.75) |
| 17:52:09 | worker | "Failed to sync protective stop for INFY" — potential wash trade detected |
| 18:30:00 | `loss-feedback-check` | S1: **stessa evidenza identica** delle 14:00 (EWMA −0.55, 11 loss, −$178.68) → regime_scale 0.21→0.20 |
| 18:30:00 | `loss-feedback-check` | S4 recovery (17:30 in realtà, vedi nota): 3 win consecutive → threshold 0.40→0.35, scale 0.64→0.80 |
| 18:30:00 | Telegram | Invio alert loss-feedback S1 fallito di nuovo (400 Bad Request) |
| 18:37:00 | `execution_decisions` #4046 | SELL NOW (`[expired]` S4 signal age 4.4h>4h) → chiude #405 (**−$49.69**, la perdita maggiore della giornata) |
| 19:22:00 | worker | "Sentiment reversal: IWM score=−0.390 < threshold=−0.35 — forced exit" → SELL forzata cross-strategy su posizione S1 |
| 19:22:11 | worker | "Forced sell submitted for IWM (sentiment reversal)" — chiude trade #371 (aperto 07-21 da S1), **−$7.05** |
| 19:37:00 | `execution_decisions` #4058 | BUY IWM tentato da S1 momentum → **bloccato**, "Reversal cooldown: skipping BUY for IWM" (decisione registrata, ordine mai sottomesso) |
| 19:37:00 | `execution_decisions` #4059 | SELL INFY (`[whipsaw]`) → chiude #409 (+$3.20) |
| 19:52:01 | `execution_decisions` #4064 | BUY IWM ritentato da S1 → bloccato di nuovo dal reversal cooldown |
| 19:52–21:59 | `mobile-alert-evaluation` | Prosegue il fallimento 1/min fino a fine giornata (480/480 totali) |
| 21:37:13 | `audit_log` #5584 | `KILLSWITCH_ACTIVATE` — "manual operator halt via API" (post-market, nessun ciclo portfolio attivo in quel momento) |
| 21:37:14–15 | `audit_log` #5585/#5586 | UPDATE risk-config con `reason: "test-deep-merge-verified"` |
| 21:37:42 | `audit_log` #5587–5589 | INSERT diretti in `trades` (id 410–412, symbol `TEST_STOP_1/2/3`, `entry_order_id: test-order-N`) |
| 21:38:44 | `ingestion_stats_daily` | Riga `reuters` scritta fuori schedule (RSS ingestion disabilitata via env var, non schedulata in beat) |
| 22:30:00 | `risk-monitor` | risk_reports#41: NAV $109,881.95 (−$91.34 vs ieri), drawdown 0.098989, herfindahl 1.0, exposure 25.8% |
| (successivo) | — | Trade 410–412 (`TEST_STOP_*`) non più presenti in `trades` al momento dell'audit (07-24) — **nessun audit_log DELETE associato** |

---

## 4. Tabella News Ingest

| Fonte | Count (news_log) | Prima news | Ultima news | Discarded | Extraction method |
|---|---|---|---|---|---|
| gdelt_gkg | 103 | 15:00:11 | 19:46:07 | 0 | org_lookup |
| alpaca_benzinga | 95 | 14:15:10 | 19:30:21 | 0 | source_metadata |
| **Totale** | **198** | 14:15:10 | 19:46:07 | 0 | — |

- Duplicati cross-provider su `(content_hash, ticker)`: **0**.
- News con `published_at > fetched_at` (timestamp futuro): 0. News stale (>48h): 0. `published_at`/`body_snippet`/`raw_sentiment` NULL: 0.
- News fuori market hours dichiarate (13:30–20:00 UTC): 0, ma vedi [DAY-006 storico] — la finestra effettiva inizia alle 14:15, non 13:30 (gap DST già noto, non ri-aperto qui).
- `news_log_id` NULL su sentiment_signals: 0 (ogni segnale è tracciabile a una news).
- Segnali multipli sulla stessa news+ticker: 2 casi isolati (news 4764→TXN x2, news 4794→MSFT x2) — probabile doppia elaborazione dello stesso item in cicli sentiment consecutivi, non un duplicato di ingest.

**⚠️ Gap funnel non spiegato (vedi [DAY-006]):** `ingestion_stats_daily` per il 07-23 riporta `alpaca_benzinga: fetched=481, queued=302, duplicates=1936` e `gdelt_gkg: fetched=2012, queued=153, duplicates=50, discarded_no_ticker=1835`. Il valore "queued" (item effettivamente pushati su Redis per elaborazione LLM) è **~3x superiore** al conteggio finale in `news_log` (302 vs 95 per benzinga; 153 vs 103 per gdelt). Il pattern è identico nei 4 giorni precedenti verificati (07-20..07-22), quindi non è specifico di oggi ma una caratteristica strutturale non ancora spiegata da nessun contatore disponibile.

**Top ticker per volume news:** MS(32), GOOGL(15), TSLA(14), MSFT(11), MU(9), INFY(9), NOK(8), TSM(8), SPCX(7), GS(7).

**Top news per impatto sul segnale (|score| più alto):** GOOGL 0.66 ("AI Waitlist $514B", 14:15, conf 0.825), TSM 0.64 (profit +77%, 19:45, conf 0.80), TSLA −0.60 (EPS miss, 16:15, conf 0.85), SPCX 0.595 (Cathie Wood ARK pivot, 17:45, conf 0.85), TSLA +0.5228 (Musk CapEx comment, **16:16, un minuto dopo il −0.60 sopra** — vedi §5), INFY 0.56 (Q1 results, 16:00, conf 0.80).

**Confidenza analisi: High** (dati completi, nessun NULL, query dirette su tabella sorgente; il gap "queued vs stored" resta un'ambiguità aperta, confidenza Medium su quella specifica osservazione).

---

## 5. Tabella Performance Modelli LLM

| model_id | Risposte | Ineligible (conf&lt;0.4) | Avg polarity | Avg confidence | Min/Max polarity |
|---|---|---|---|---|---|
| glm-5.2:cloud | 200 | 138 (69.0%) | 0.044 | 0.321 | −0.8 / 0.8 |
| gpt-oss:20b-cloud | 200 | 103 (51.5%) | 0.041 | 0.407 | −0.6 / 0.8 |

**Composizione ensemble finale (`sentiment_signals.model_id`), 200 righe:**

| model_id (contributori) | Count | % | Avg score | Avg confidence |
|---|---|---|---|---|
| ensemble:glm-5.2+gpt-oss (entrambi eleggibili) | 148 | 74.0% | 0.040 | 0.364 |
| ensemble:gpt-oss:20b-cloud (solo) | 43 | 21.5% | 0.029 | 0.479 |
| ensemble:glm-5.2:cloud (solo) | 8 | 4.0% | 0.071 | 0.669 |
| finbert (hard fallback) | 1 | 0.5% | −0.268 | 0.423 |

- **Timeout Ollama**: **0** — miglior giornata osservata recentemente (07-22 ne aveva 1). Nessun errore/eccezione in `worker-inference` per l'intera giornata (52.010 righe di log, 0 ERROR/timeout/refusal).
- **Refusal/invalid JSON**: nessuna evidenza.
- **Disagreement massimo** (ensemble_std): MU 0.389 (19:00, score 0.19 conf 0.5), TSM 0.332 (16:30), GOOGL 0.318 (15:31), TSLA 0.283 (14:45), NOW 0.283 (14:15) — nessuno supera la soglia di scarto (0.30 costruttore in alcuni casi sì, ma nessun fallback attivato da divergenza pura oggi tranne quello FinBERT già isolato).
- **Caso di disaccordo direzionale reale (non solo tra modelli ma tra news consecutive)**: TSLA 16:15:44 score −0.60 (EPS miss, ensemble) seguito 42s dopo da TSLA 16:16:26 score +0.5228 (commento Musk, ensemble) — due notizie legittimamente diverse, non un bug del modello, ma segnala quanto il segnale S4 su base singola-news possa oscillare nello spazio di un minuto. Il ciclo portfolio successivo (16:22) non ha generato un ordine su TSLA basato su nessuno dei due (il segnale attivo per S4 in quel momento restava quello delle 15:22 che aveva già aperto la posizione).

**Verifica funzionale:**
- Output LLM validato prima del signal store: **sì** (`eligible = confidence >= 0.4`), scritto anche se ineligible per audit.
- Gestione varianza alta: **sì**, meccanismo presente; oggi mai raggiunta la soglia di scarto per varianza pura.
- News duplicate pesano più volte: solo 2 casi isolati di re-processing stesso news_log_id+symbol (§4), impatto trascurabile.
- Confidence bassa riduce il peso: confermato per costruzione (`score = polarity × confidence`).
- Chiamata offline/background: confermato, `worker-inference` (queue `inference`, concorrenza 1), mai nel loop di esecuzione.
- Rischio hallucination diretta in trading: mitigato; l'unico segnale hard-fallback (FinBERT, META, score −0.268) **non ha mai generato una decisione BUY/SELL** — verificato con query diretta (0 righe `execution_decisions` con `fallback_used=true` collegato).

**Confidenza analisi: High.**

---

## 6. Tabella Segnali Finali per Ticker (top 12 per volume)

| Symbol | N | Avg score | Min | Max | Avg confidence | Avg ensemble_std |
|---|---|---|---|---|---|---|
| MS | 32 | 0.001 | −0.08 | 0.10 | 0.299 | 0.012 |
| GOOGL | 15 | 0.113 | −0.30 | 0.66 | 0.532 | 0.118 |
| TSLA | 14 | −0.118 | −0.60 | 0.5228 | 0.588 | 0.077 |
| MSFT | 11 | −0.007 | −0.09 | 0.285 | 0.419 | 0.069 |
| MU | 9 | 0.157 | 0.00 | 0.42 | 0.492 | 0.076 |
| INFY | 9 | 0.220 | −0.216 | 0.56 | 0.621 | 0.075 |
| TSM | 8 | 0.160 | 0.00 | 0.64 | 0.442 | 0.064 |
| NOK | 8 | 0.086 | −0.033 | 0.56 | 0.319 | 0.031 |
| SPCX | 7 | 0.080 | −0.045 | 0.595 | 0.343 | 0.056 |
| GS | 7 | −0.008 | −0.09 | 0.055 | 0.375 | 0.020 |
| NVDA | 6 | 0.017 | −0.158 | 0.30 | 0.383 | 0.077 |
| DB | 5 | 0.000 | −0.04 | 0.04 | 0.300 | 0.000 |

Ticker che hanno effettivamente generato una decisione BUY/SELL non-SKIP: **NOW, TSLA, INFY, TXN, IWM** (S4 news-driven + S1 momentum su IWM). Tutti gli altri segnali del giorno (MS, GOOGL, MSFT, MU, TSM, NOK, SPCX, GS, NVDA, DB, ecc.) sono rimasti sotto soglia (`SKIP_THRESHOLD`) o non hanno un peso di portfolio assegnato.

---

## 7. Tabella Ordini Generati/Eseguiti

`execution_decisions` 2026-07-23: **269 totali** → 256 `SKIP_THRESHOLD`, 7 BUY, 6 SELL. `constraints_fired: []` su tutti i 24 `portfolio_cycles` registrati.

| Tick time | Strategia | Symbol | Azione | Order ID | Rationale | Trade | Esito |
|---|---|---|---|---|---|---|---|
| 14:22:00 | S4 | NOW | BUY | e976f2f3… | sentiment +0.600, peso 2.0% | #405 @ $97.19 | chiuso 18:37, **−$49.69** |
| 15:22:00 | S4 | TSLA | BUY | e4e70ca2… | sentiment +0.510, peso 2.0% | #406 @ $320.52 | chiuso 17:07, **+$6.59** |
| 15:22:00 | S4 | INFY | BUY | c15bafd0… | sentiment +0.380, peso 2.0% | #407 @ $10.56 | chiuso 17:07, **+$7.82** |
| 16:07:00 | S4 | TXN | BUY | adeff6a8… | sentiment +0.362, peso 2.0% | #408 @ $283.08 | chiuso 17:52, **−$11.75** |
| 17:07:00 | S4 | INFY | SELL (whipsaw) | cffdd337… | weight 0%, shadow would_suppress | chiude #407 | fill $10.65 |
| 17:07:00 | S4 | TSLA | SELL (whipsaw) | 6cf35e13… | weight 0%, shadow would_suppress | chiude #406 | fill $322.33 |
| 17:52:00 | S4 | INFY | BUY | b06efb25… | sentiment +0.381 (nuovo segnale), peso 2.0% | #409 @ $10.67 | chiuso 19:37, **+$3.20** |
| 17:52:00 | S4 | TXN | SELL (whipsaw) | 52ad40f3… | weight 0%, shadow would_suppress | chiude #408 | fill $280.50 |
| 18:37:00 | S4 | NOW | SELL (expired) | e7915f7e… | segnale scaduto age=4.4h>4h | chiude #405 | fill $93.35 |
| 19:22:00 | S4 (cross) | IWM | SELL (reversal) | 96dddcc3… | sentiment reversal score −0.390<−0.35, forced exit | chiude #371 (S1) | fill $291.52, **−$7.05** |
| 19:37:00 | S1 | IWM | BUY | *(nessuno)* | S1 momentum, peso 1.3% — **bloccato da reversal cooldown** | — | NO-ORDER (corretto) |
| 19:37:00 | S4 | INFY | SELL (whipsaw) | 90107387… | weight 0%, shadow would_suppress | chiude #409 | fill $10.72, **+$3.20** |
| 19:52:01 | S1 | IWM | BUY | *(nessuno)* | S1 momentum — bloccato di nuovo | — | NO-ORDER (corretto) |

Tutti gli `order_id` reali sono univoci (0 duplicati). Nessuna race condition (0 decisioni identiche stesso `tick_time`+`symbol`+`decision`). Paper/live confermato: S1=`supervised_paper`, S4=`paper` (`strategy_lifecycle`), `config/trading.yaml` → `execution.engine: portfolio`.

**Confidenza analisi: High.**

---

## 8. Tabella PnL / Rendimento

| Metrica | Valore | Fonte |
|---|---|---|
| PnL realizzato (trade chiusi il 07-23) | **−$50.88 netto** (lordo −$44.13, costi $6.75) | `trades` (6 chiusure) |
| PnL per strategia | S4: −$43.83 netto (NOW −49.69, TSLA +6.59, INFY +7.82, TXN −11.75, INFY +3.20) · S1 (cross-exit): −$7.05 (IWM) | `trades.stop_strategy` |
| PnL mark-to-market giornaliero (book intero, 43 posizioni) | NAV $109,881.95 (07-22: $109,973.29) → **−$91.34** | `risk_reports#41` |
| PnL non realizzato per singolo ticker | **non calcolabile** | nessuna tabella prezzi/posizioni in Postgres, API `/api/positions` inaccessibile (JWT) |
| Slippage stimato | uguale a `cost_usd` per riga (range $0.16–$2.51) | `trades.slippage_est` |
| Costi/commissioni totali | $6.75 sui 6 trade chiusi | `trades.cost_usd` |
| combined_drawdown | 0.098989 (vs 0.093765 ieri — variazione reale stavolta, non stale) | `risk_reports#41` |
| herfindahl_index | 1.000000 (identico da ≥4 giorni — bug noto #75, non ri-aperto) | `risk_reports#41` |
| total_exposure | 25.82% (vs 26.58% ieri) | `risk_reports#41` |

**Nota importante:** il PnL realizzato da `trades` (−$50.88) e il PnL mark-to-market del book (−$91.34) misurano cose diverse — il secondo include la rivalutazione delle 43 posizioni aperte, non solo le 6 chiuse oggi. **Notevole**: tutte e 5 le nuove entry S4 di oggi sono state chiuse lo stesso giorno (0 posizioni S4 aperte oggi sono sopravvissute a fine giornata) — coerente con l'evidenza citata nel codice (`whipsaw_damping.py`, issue #61: gli exit intraday storicamente performano peggio di quelli overnight, −$0.77 medio vs +$2.64), anche se oggi il mix intraday è stato in realtà leggermente positivo su 3 delle 5 chiusure whipsaw/expired (+$6.59, +$7.82, +$3.20) e negativo su 2 (−$49.69 NOW-expired, −$11.75 TXN-whipsaw).

**Confidenza analisi: High** su dati DB; **Medium** su eventuali riflessi della finestra di test 21:37-21:38 nel calcolo NAV delle 22:30 (non verificabile se le 3 trade di test erano ancora presenti al momento del calcolo).

---

## 9. Analisi Correttezza Buy/Sell

| Check | Esito |
|---|---|
| BUY solo se consentito | ✅ nessuna BUY su segnale fallback (fix #59 verificato: META fallback mai entrato in decisione) |
| SELL/exit corretti | ✅ expired (NOW, age>4h), whipsaw (INFY x2, TSLA, TXN), sentiment_reversal (IWM) — tutti con rationale tracciato |
| Stop-loss rispettati | ⚠️ cancel-before-sell funziona sempre, ma il **ri-sync** del protective stop post-SELL è fallito 3 volte su INFY (insufficient qty / wash trade) — vedi [DAY-009] |
| Signal flip rispettato | ✅ nessun flip contraddittorio nello stesso ciclo |
| Max holding / signal expiry | ✅ NOW chiuso correttamente a 4.4h > max_age 4h |
| Rebalance band / anti-whipsaw | ⚠️ 4 exit classificate "whipsaw" con shadow `would_suppress=True` (flag OFF di default) — se il flag fosse ON, questi 4 SELL sarebbero stati ritardati di un ciclo; esito misto oggi (3 profittevoli, 1 in perdita), non ancora conclusivo per la decisione di flip |
| Ordini duplicati | ✅ nessuno (order_id univoci, nessuna race sullo stesso tick_time) |
| Ordini contrari ravvicinati senza rationale | ✅ tutti con rationale esplicito (whipsaw/expired/reversal), nessuno senza motivazione |
| Ticker non consentiti | ✅ nessuno |
| Ordini fuori orario | ✅ tutti 14:22–19:52 UTC |
| Trade su dati stale | ✅ guardia attiva (AZN/SPCX scartati per sparse/stale-tailed, 24 occorrenze) |
| Trade su LLM output non valido | ✅ nessuno |
| Circuit breaker attivo → blocco trade | N/A — kill-switch attivato solo post-market (21:37), nessun ciclo portfolio bloccato oggi |
| Strategia disabilitata → blocco | N/A (S2 disabled, S7 research — non toccate) |
| Paper/live coerente | ✅ confermato |
| Idempotenza retry Celery | ✅ `P1-S4: signal_id=X already fired today — skipping (SIGNAL_DUPLICATE_SKIP)` ha bloccato correttamente 6 tentativi di doppia elaborazione dello stesso segnale (INFY x3, TSLA, TXN, generico) |
| Reconciliation ordini↔fill↔posizioni | ❌ **ancora fallita per WDC #373** (giorno 3, vedi [DAY-002]); ✅ per tutti gli altri 6 trade chiusi oggi |
| **Nuovo — reversal cooldown cross-strategy (#68)** | ✅ **verificato dal vivo**: 2 tentativi BUY S1 su IWM bloccati correttamente dopo forced-sell S4 sullo stesso simbolo |

---

## 10. Anomalie Trovate

### [DAY-001] `mobile_alert_task`: 100% failure rate per il secondo giorno consecutivo, nessun fix applicato

- Tipo: Bug (recidivo — già segnalato ieri come Critical)
- Area: Ops / Frontend (mobile monitoring)
- Evidenza:
  - file/log/tabella: log `worker`; `src/api/deps.py:30`; `src/mobile_monitoring/builder.py:93`
  - timestamp: 2026-07-23 14:00:00 → 21:59:00 (480 esecuzioni, 0 successi)
  - snippet: `HTTPException(status_code=503, detail='Cache unavailable')` ripetuto identico a ieri
- Descrizione: stessa root cause identificata nel report del 07-22 (`MobileSnapshotBuilder` chiama `get_redis_store()` da `src.api.deps`, dependency FastAPI-only mai inizializzata nel processo worker Celery). Nessun intervento risulta applicato nelle 24h successive alla segnalazione.
- Impatto: zero notifiche push mobile per il secondo giorno di fila.
- Severità: Critical (dominio mobile monitoring; nessun impatto sul trading core)
- Confidenza: High
- Azione consigliata: come ieri — iniettare un client Redis dedicato al worker invece del default FastAPI-only; il fatto che sia ancora identico dopo 24h suggerisce che la segnalazione di ieri non sia stata ancora vista/processata da un operatore.
- Test/monitor consigliato: alert sul tasso di successo del task < 100% su finestra 1h (se questo monitor esistesse, avrebbe già suonato 2 volte).

### [DAY-002] Trade WDC #373: terzo giorno consecutivo orfano, exit-hysteresis ri-triggerata ma non completata

- Tipo: Bug (recidivo, in peggioramento)
- Area: Orders / Broker / Data
- Evidenza:
  - file/log/tabella: `trades` id=373; log worker 2026-07-23 16:37:07
  - timestamp: entry 07-21 16:37:01; SELL#1 07-21 18:22 (`bf7fe4b8…`); SELL#2 07-22 16:22 (`87132adc…`); oggi 16:37:07 "Exit hysteresis (2 cycles): held 1 position(s) flagged for exit: ['WDC']" — nessuna terza SELL generata
  - snippet: `sentiment_signals` per WDC oggi = **0 righe** (il ticker non riceve più segnali freschi, eppure il sistema tenta ancora di valutarne l'uscita)
- Descrizione: la trade #373 resta con `exit_time`/`exit_price`/`exit_reason` tutti NULL nonostante 2 ordini SELL già registrati in `exit_order_ids` nei giorni precedenti. Oggi il meccanismo di exit-hysteresis l'ha rilevata come "flagged for exit" per il 2° ciclo consecutivo interno al suo contatore (richiede 2 cicli per confermare), ma il log non mostra una terza SELL effettivamente sottomessa nella giornata — il ciclo di conferma sembra essersi interrotto o essere ripartito da zero.
- Impatto: posizione fantasma/ambigua nel DB per 3 giorni; guardia pyramiding blocca correttamente ogni ri-BUY, ma lo stato reale a mercato resta sconosciuto senza accesso al broker.
- Severità: **High** (elevata da ieri per persistenza e nuovo segnale di comportamento anomalo del meccanismo di hysteresis)
- Confidenza: Medium (comportamento DB/log solido, causa esatta dell'interruzione dell'hysteresis non verificata nel codice in questa sessione)
- Azione consigliata: verifica manuale prioritaria dello stato broker per i due order_id pendenti; eseguire `reconcile_fills` mirato; se confermato chiuso, correggere manualmente `trades.exit_*`; se ancora aperto, capire perché l'hysteresis non ha completato la 3ª SELL.
- Test/monitor consigliato: alert automatico su trade con `exit_order_ids` non vuoto ma `exit_time IS NULL` da >24h (soglia raggiunta e superata 2 volte per WDC).

### [DAY-003] Trade di test (`TEST_STOP_1/2/3`) inseriti direttamente nella tabella `trades` di produzione, poi rimossi senza traccia in audit_log

- Tipo: Rischio (governance / integrità audit trail) — recidivo di pattern noto (test rows leaked in `trades` prod, 07-11)
- Area: Data / Ops
- Evidenza:
  - file/log/tabella: `audit_log` id 5587–5589 (INSERT, table_name=`trades`, record_id 410/411/412); verifica attuale: `SELECT * FROM trades WHERE id IN (410,411,412)` → 0 righe
  - timestamp: 2026-07-23 21:37:42 UTC (INSERT); rimozione avvenuta in un momento non tracciato tra allora e l'audit del 07-24
  - snippet: `{"score": 0.02, "symbol": "TEST_STOP_1", "entry_notional": 1000.0, "entry_order_id": "test-order-1"}`
- Descrizione: subito dopo un'attivazione manuale del kill-switch (21:37:13) e un test di merge della configurazione di rischio (`reason: "test-deep-merge-verified"`), tre righe di trade sintetiche sono state inserite direttamente in `trades` — la stessa tabella che alimenta PnL, esposizione, pyramiding guard e risk_reports. Le righe non esistono più al momento dell'audit, ma **nessun record `audit_log` di tipo DELETE** ne documenta la rimozione, esattamente come nell'incidente dell'11/07 già in memoria di progetto.
- Impatto: se la rimozione fosse avvenuta dopo il calcolo di `risk_reports#41` (22:30:00, cioè ~53 minuti dopo l'insert), NAV/exposure/herfindahl di quel report potrebbero includere $3.000 di notional fittizio; il gap di 3 ID nella sequenza (`409→413`) è di per sé innocuo ma conferma manipolazione diretta della tabella fuori dal codepath applicativo standard.
- Severità: Medium (nessun impatto confermato su ordini reali; alto se ripetuto in orario di mercato o senza pulizia)
- Confidenza: Medium (evidenza INSERT solida via audit_log; timing esatto della rimozione e impatto su risk_reports#41 non verificabili)
- Azione consigliata: usare un ambiente/DB isolato per i test che toccano `risk`/`trades`, mai la tabella di produzione; se il testing diretto su prod è necessario, avvolgerlo in una transazione con INSERT+DELETE auditati esplicitamente, non una cancellazione manuale fuori-audit.
- Test/monitor consigliato: trigger DB che impedisca o alerti su INSERT in `trades` con `entry_order_id` che matcha pattern `test-*`; alert su gap non spiegati nella sequenza `trades.id`.

### [DAY-004] Cluster di attività manuale post-market (kill-switch + test + ingest fuori schedule) a 21:37–21:38 UTC

- Tipo: Ambiguità / Rischio operativo
- Area: Ops
- Evidenza:
  - file/log/tabella: `audit_log` 5584–5589; `ingestion_stats_daily` riga `reuters` aggiornata 21:38:44
  - timestamp: 2026-07-23 21:37:13 → 21:38:44 UTC
  - snippet: `KILLSWITCH_ACTIVATE {"reason": "manual operator halt via API", "source": "api"}` senza dettaglio ulteriore sull'operatore o lo scopo
- Descrizione: in un arco di 90 secondi post-market compaiono, in sequenza: attivazione kill-switch, due UPDATE di configurazione rischio marcati esplicitamente come test, tre INSERT di trade sintetiche (vedi [DAY-003]), e una scrittura di statistiche di ingestion per `reuters` — fonte la cui ingestione è **disabilitata** (`RSS_INGESTION_ENABLED` non settato/`"0"` nel container; il task non è nemmeno registrato nello schedule di `beat`). Il pattern è coerente con un operatore che esegue test manuali di feature (config merge, RSS connector, stop sync) direttamente contro i servizi live, non con un'anomalia della pipeline automatica.
- Impatto: nessun impatto diretto sul trading di giornata (i cicli portfolio erano già terminati alle 19:52). Impatto potenziale: se questi test toccano tabelle condivise con la pipeline live (vedi [DAY-003]) senza isolamento, il rischio di contaminare dati di produzione è reale e ricorrente.
- Severità: Low (per l'impatto osservato oggi) / Medium (per il pattern ricorrente)
- Confidenza: Medium (inferenza da correlazione temporale, non da un log esplicito che dichiari "questo è un test")
- Azione consigliata: se sono effettivamente test dell'operatore, spostarli su un ambiente/DB di staging; se non lo sono, indagare chi/cosa ha eseguito queste azioni alle 21:37 di sera.
- Test/monitor consigliato: nessuno specifico oltre a quanto già raccomandato in [DAY-003].

### [DAY-005] Loss-feedback ratchet S1: doppia riduzione sulla stessa evidenza stale, stesso pattern di ieri

- Tipo: Rischio (recidivo)
- Area: Risk
- Evidenza:
  - file/log/tabella: log worker, `loss-feedback-check`
  - timestamp: 14:00:00 e 18:30:00
  - snippet: entrambe le righe **identiche**: `EWMA R -0.55, 11 consecutive losses, rolling P&L $-178.68`; prima riduzione `regime_scale 0.26→0.21`, seconda (4.5h dopo) `0.21→0.20` — nessuna nuova trade S1 chiusa nel frattempo (l'unica chiusura S1-correlata, IWM, avviene alle 19:22, dopo entrambi i trigger)
- Descrizione: stesso comportamento già segnalato in [DAY-005] del report 07-22 — il cooldown interno (4h) scade e il sistema ri-applica una penalizzazione basata sulle stesse statistiche stale, senza nuova evidenza di perdita.
- Impatto: de-risking cumulativo di S1 (0.26→0.21→0.20, ulteriore −23%) su un solo episodio di perdita non aggiornato.
- Severità: Medium
- Confidenza: Medium (comportamento osservato 2 giorni di fila, causa esatta nel codice non ri-verificata oggi)
- Azione consigliata: verificare se `run_loss_feedback_check` richiede evidenza fresca prima di un secondo taglio nella stessa loss-episode (stessa raccomandazione di ieri, non ancora implementata).
- Test/monitor consigliato: come da report precedente.

### [DAY-006] Gap sistematico "queued" (Redis) vs righe effettive in `news_log` — persistente su ≥4 giorni

- Tipo: Ambiguità
- Area: Data / News
- Evidenza:
  - file/log/tabella: `ingestion_stats_daily` vs `news_log`, 07-20→07-23
  - timestamp: ogni giorno lavorativo osservato
  - snippet: 07-23 `alpaca_benzinga: queued=302` vs `news_log count=95` (−68%); `gdelt_gkg: queued=153` vs `count=103` (−33%); stesso ordine di grandezza 07-20/07-21/07-22
- Descrizione: "queued" (`src/workers/ingestion.py`) conta gli item pushati su Redis per elaborazione LLM; solo una frazione arriva effettivamente a essere scritta in `news_log`. Non è spiegato da "duplicates" o "discarded_no_ticker" (contati a monte, prima del push). Possibili spiegazioni non verificate: fan-out multi-ticker per articolo conteggiato come "queued" multiplo ma collassato dalla unique constraint `(url, ticker)` a scrittura; oppure item che scadono in coda prima di essere consumati dal sentiment worker.
- Impatto: se la seconda ipotesi fosse vera, si perderebbero notizie realmente rilevanti senza alcun contatore di "discarded" a testimoniarlo — un vero e proprio *failure silenzioso* nella terminologia richiesta da questo audit.
- Severità: Medium
- Confidenza: Low-Medium (pattern consistente ma root cause non isolata nel codice in questa sessione)
- Azione consigliata: instrumentare il consumer Redis→news_log con un contatore esplicito di "consumed_ok" vs "expired_in_queue" vs "rejected_at_write" per chiudere il gap.
- Test/monitor consigliato: alert se `queued − stored` supera una soglia percentuale stabile nel tempo (richiede prima la baseline sopra).

### [DAY-007] Righe `ingestion_stats_daily` per `reuters` nonostante RSS ingestion disabilitata

- Tipo: Ambiguità
- Area: Ops / Data
- Evidenza:
  - file/log/tabella: `ingestion_stats_daily` (righe `reuters` 07-21/07-22/07-23); `src/workers/ingestion.py:733` (`if RSS_INGESTION_ENABLED=="0": return skipped`); `celery_app.py:162` (RSS commentata dallo schedule dal 07-03)
  - timestamp: `updated_at` 07-21 23:43:05, 07-22 08:31:12, 07-23 21:38:44 — orari irregolari, fuori sia dall'orario di mercato sia da qualunque cadenza a 15 min
  - snippet: env `RSS_INGESTION_ENABLED` non settato nel container `worker` (default `"0"`); 0 log "RSS" nel worker per il 07-23
- Descrizione: nessuna evidenza che `run_rss_ingestion_worker` sia in esecuzione tramite lo scheduler automatico (disabilitato per feed morti, FIX-02); le righe osservate sono quindi quasi certamente scritte da invocazioni manuali/ad-hoc del connettore, non dalla pipeline live. **0 righe reuters sono mai arrivate in `news_log`** in nessuno dei 3 giorni osservati.
- Impatto: nessuno sulla pipeline live (correttamente disabilitata); rischio di confusione se qualcuno legge `ingestion_stats_daily` credendo che reuters sia una fonte attiva.
- Severità: Low
- Confidenza: Medium
- Azione consigliata: nessuna urgente; se il testing del connettore reuters è intenzionale, isolarlo da `ingestion_stats_daily` di produzione (es. prefisso `source` diverso, tipo `reuters_test`).
- Test/monitor consigliato: nessuno specifico.

### [DAY-008] Notifiche Telegram su eventi di rischio non consegnate (400 Bad Request)

- Tipo: Bug
- Area: Ops / Alerting
- Evidenza:
  - file/log/tabella: log worker, `TelegramNotifier`
  - timestamp: 14:00:00,391 e 18:30:00,264 — entrambe immediatamente dopo un trigger di loss-feedback
  - snippet: `Client error '400 Bad Request' for url 'https://api.telegram.org/bot.../sendMessage'`
- Descrizione: entrambi i tentativi di notifica Telegram per i due trigger di loss-feedback S1 della giornata sono falliti con 400 (probabile problema di formattazione del messaggio o `chat_id` non valido, non di rete/autenticazione dato che è un 400 non un 401/timeout).
- Impatto: l'operatore non riceve notifica quando un de-risking automatico significativo (regime_scale −23% cumulativo oggi) viene applicato — gap nella catena "log errori → alert" richiesta da questo audit.
- Severità: Medium
- Confidenza: High (log espliciti, 2/2 falliti)
- Azione consigliata: validare il payload inviato a `sendMessage` (lunghezza, caratteri speciali/Markdown non escaped sono la causa più comune di 400 su questa API); aggiungere log del payload esatto in caso di fallimento per diagnosi rapida.
- Test/monitor consigliato: test di integrazione che invia un messaggio Telegram reale (o mock HTTP) per ogni tipo di alert supportato, incluso il formato specifico di loss-feedback.

### [DAY-009] Protective stop non risincronizzato 3 volte su INFY (insufficient qty / wash trade detected)

- Tipo: Anomalia
- Area: Orders / Broker
- Evidenza:
  - file/log/tabella: log worker, "Failed to sync protective stop for INFY"
  - timestamp: 17:07:10, 17:52:09, 19:37:08
  - snippet: `"insufficient qty available for order (requested: 114, available: 0)"` (x2) e `"potential wash trade detected. use complex orders", "reject_reason":"opposite side market/stop order exists"` (x1)
- Descrizione: ogni volta che INFY viene scambiato oggi (SELL 17:07, BUY 17:52, SELL 19:37), il successivo tentativo di sincronizzazione del protective stop viene rifiutato da Alpaca perché un ordine di segno opposto è ancora "in volo" (market order appena sottomesso non ancora liquidato/qty non ancora libera). Il sistema logga il fallimento come WARNING e prosegue (`errors` array nel riepilogo "Fractional protective stop sync"), senza un retry esplicito nello stesso ciclo.
- Impatto: la posizione INFY può restare temporaneamente priva di stop protettivo nella finestra tra un ordine e la sincronizzazione riuscita del successivo (probabilmente pochi minuti fino al ciclo successivo, ma non verificato quando la sync sia effettivamente riuscita).
- Severità: Medium
- Confidenza: Medium (pattern chiaro nei log, ma non è verificato se un retry al ciclo successivo abbia effettivamente ripristinato lo stop prima di un eventuale movimento avverso)
- Azione consigliata: verificare se esiste già un retry al ciclo successivo (15 min dopo) e se sì, quantificare la finestra di esposizione; se non esiste, aggiungere un retry a breve intervallo per i soli fallimenti "insufficient qty"/"wash trade" (transitori per natura).
- Test/monitor consigliato: alert se un simbolo con posizione aperta resta senza protective stop attivo per più di N minuti dopo un trade.

### [DAY-010] Endpoint API REST ancora inaccessibile (JWT scaduto) — secondo giorno consecutivo

- Tipo: Ambiguità / Rischio operativo (recidivo)
- Area: Ops / Data
- Evidenza:
  - file/log/tabella: risposta HTTP diretta
  - timestamp: 2026-07-24 (inizio sessione)
  - snippet: `{"detail":"Invalid or expired JWT token"}` su tutti gli endpoint richiesti con il token fornito
- Descrizione: stesso problema di ieri, non risolto.
- Impatto: impossibile verificare se anche i consumer legittimi (frontend/mobile) sperimentano lo stesso problema.
- Severità: Low (per l'audit)
- Confidenza: High
- Azione consigliata: rigenerare/investigare la policy di scadenza del token usato per l'audit.
- Test/monitor consigliato: alert su tasso di 401/403 anomalo sull'API pubblica.

---

## 11. False Positive / Aree Corrette

- **Reversal cooldown cross-strategy (#68) verificato dal vivo per la prima volta**: 2 tentativi di BUY S1 su IWM bloccati correttamente dopo la forced-sell per sentiment reversal eseguita da S4 sullo stesso simbolo — la decisione "BUY" viene comunque registrata in `execution_decisions` (con `order_id` vuoto) per motivi di audit, ma l'ordine reale non è mai stato sottomesso. Corretta distinzione decisione↔ordine, esattamente come richiesto da questo audit.
- **Fix #59 (blocco BUY su fallback) tiene**: l'unico segnale FinBERT-fallback della giornata (META) non è mai stato usato per generare una decisione BUY o SELL (verificato via query diretta `fallback_used=true`).
- **SIGNAL_DUPLICATE_SKIP (P1-S4) funziona**: 6 tentativi di doppia elaborazione dello stesso `signal_id` bloccati correttamente.
- **Nessuna SELL con sentiment positivo** (bug A5) trovata.
- **Nessun roundtrip <30 min**, nessun ordine duplicato/race sullo stesso minuto, nessuna news con timestamp futuro o stale.
- **Ollama 100% disponibile, 0 timeout** — il miglior giorno osservato di recente.
- **Cross-strategy risk control funzionante**: la sentiment-reversal SELL su IWM ha chiuso correttamente una posizione aperta da S1, confermando che il meccanismo opera a livello di portfolio e non solo all'interno della strategia che lo genera (per design, `#68`).
- **Nessun constraint di rischio automatico attivato** (`constraints_fired: []` su tutti i 24 cicli).
- **Guardia dati stale S1** attiva (AZN/SPCX scartati 24 volte).
- **Cancel-before-sell (#69) funziona** su ogni SELL eseguita oggi.

---

## 12. Dati Mancanti o Non Accessibili

| Dato | Motivo | Query/azione che servirebbe |
|---|---|---|
| Stato reale ordini Alpaca per WDC (`bf7fe4b8…`, `87132adc…`) | API `/api/orders` inaccessibile (JWT); nessuna chiamata diretta al broker in questa sessione read-only | Rigenerare JWT o interrogare Alpaca direttamente (fuori scope) |
| PnL non realizzato per singolo ticker sulle 43 posizioni aperte | Nessuna tabella prezzi/posizioni in Postgres | `/api/positions` (richiede JWT) o snapshot prezzi Alpaca |
| Momento esatto di rimozione delle trade `TEST_STOP_1/2/3` (id 410-412) | Nessun audit_log DELETE associato | Verificare log applicativi o snapshot DB più granulari, se esistenti |
| Root cause del gap "queued vs stored" nel funnel news | Richiede instrumentazione aggiuntiva del consumer Redis, non presente oggi | Aggiungere contatori "consumed_ok"/"expired_in_queue" come da [DAY-006] |
| Causa esatta dei 400 Bad Request su Telegram | Payload esatto del messaggio non loggato | Aggiungere logging del payload sendMessage in caso di errore |
| Chi/cosa ha eseguito le azioni manuali delle 21:37 UTC | `audit_log.user_id`/`ip_address` non popolati per quelle righe (verificare) | Verificare se il campo `user_id`/`ip_address` era popolato e perché non riportato nella query eseguita |

---

## 13. Raccomandazioni Immediate

1. **Fixare `mobile_alert_task`** — ora al secondo giorno di failure 100%, stessa causa nota da ieri [DAY-001].
2. **Escalation su WDC #373** — terzo giorno orfano, verificare stato broker con priorità prima che si accumuli un quarto giorno [DAY-002].
3. **Isolare i test manuali da `trades`/`risk` di produzione** — il pattern del 07-11 si è ripetuto il 07-23 [DAY-003]/[DAY-004].
4. **Investigare i 400 Bad Request su Telegram** — l'operatore non sta ricevendo alert su eventi di risk-management reali [DAY-008].
5. Verificare se `run_loss_feedback_check` necessita di un guard "evidenza fresca" prima di un secondo taglio nella stessa loss-episode [DAY-005] — raccomandazione ripetuta da ieri, non ancora implementata.

---

## 14. Test o Monitor da Aggiungere

- Alert su trade con `exit_order_ids` non vuoto ma `exit_time IS NULL` da >24h (avrebbe già suonato 2 volte per WDC).
- Alert sul tasso di successo di `run_mobile_alert_evaluation` (deve essere ~100%, non 0%).
- Trigger/alert su INSERT in `trades` con pattern `entry_order_id ILIKE 'test-%'` o gap non spiegati nella sequenza id.
- Alert su fallimento invio Telegram per notifiche risk-critical (loss-feedback, kill-switch, drawdown).
- Monitor sul gap "queued" vs righe effettive in `news_log` per fonte/giorno, dopo aver aggiunto l'instrumentazione mancante.
- Monitor su simboli con posizione aperta e protective stop non sincronizzato da >N minuti.
- Contatore/dashboard per gli esiti dell'anti-whipsaw shadow mode (streak raggiunti, would-be-suppressed vs eseguiti, PnL comparato) per accumulare evidenza verso la decisione di flip del flag `s4_anti_whipsaw_damping_enabled`.

---

## 15. Ticket Tecnici Suggeriti (Remediation, non patch)

1. **Bug — mobile_alert_task 100% failure, recidivo giorno 2**: stessa causa di ieri, non ancora fixata. Area: Ops/Mobile. Severità: Critical.
2. **Bug/Rischio — WDC trade #373, giorno 3 orfano**: reconciliation ordini↔fill fallita, exit-hysteresis ri-triggerata senza completamento. Area: Orders/Broker. Severità: High.
3. **Rischio — test manuali su tabella `trades` di produzione senza audit trail completo**: pattern ricorrente (07-11, 07-23). Area: Data/Ops. Severità: Medium.
4. **Bug — notifiche Telegram su eventi di rischio non consegnate (400)**: root cause non nota, payload non loggato. Area: Ops/Alerting. Severità: Medium.
5. **Rischio — loss-feedback ratchet su evidenza stale, recidivo**: possibile doppio/triplo taglio di regime_scale sulla stessa loss-episode. Area: Risk. Severità: Medium.
6. **Ambiguità — gap "queued vs stored" nel funnel di ingest news, persistente su ≥4 giorni**: instrumentazione mancante per escludere un failure silenzioso. Area: Data/News. Severità: Medium.
7. **Anomalia minore — protective stop non risincronizzato 3x su INFY** in finestre post-trade. Area: Orders/Broker. Severità: Medium.
8. **Bug minore (già tracciato, #75)** — herfindahl_index degenere, non ri-analizzato oggi in dettaglio.
9. **Osservazione positiva da capitalizzare** — reversal cooldown #68 e fix #59 verificati funzionanti dal vivo: candidati per un test di regressione automatizzato che fissi questo comportamento (oggi verificato solo per osservazione di log/DB, non da un test).

---

## 16. Stato Sistema

| Metrica | Valore |
|---|---|
| Ollama up/down | **Up 100%** per l'intera giornata — 0 timeout, 0 errori su 52.010 righe di log `worker-inference` (miglior giorno osservato recentemente) |
| FinBERT hard-fallback rate | 1/200 sentiment_signals = **0.5%** |
| Tasso "ineligible" per modello (conf&lt;0.4) | glm-5.2: 69.0% · gpt-oss: 51.5% — 74.0% delle signal sono vero ensemble a 2 modelli |
| Worker restart events | **0** dal 07-22 12:13:54 UTC — copertura log completa e continua per tutto il 07-23 |
| Altri container | `beat`, `api`, `worker-inference`, `frontend`, `postgres`, `redis` — nessun restart aggiuntivo rilevato |
| Kill-switch manuale | Attivato 1 volta il 07-23 alle 21:37:13 UTC, **post-market** (nessun ciclo portfolio impattato); ulteriori attivazioni osservate il 07-24 mattina (fuori scope di questo report) |
| mobile_alert_task success rate | **0% (0/480)** per il secondo giorno consecutivo — vedi [DAY-001] |
| Posizioni aperte a fine giornata | 43 (44 ieri, +5 nuove entry S4, −6 chiusure) |
