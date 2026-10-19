# Forensic daily report — 2026-10-06 (martedì)

Analisi read-only. Timezone operativo: UTC (celery_app.py); DST USA in vigore (EDT): RTH = 13:30–20:00 UTC, quindi le finestre beat a UTC fisso (F-021) restano la fonte di ambiguità. Fonti: DB `trading` (SELECT), API REST locale, `logs/containers/*-2026-10-06.log`, `docs/evidence/dossier/2026-10-06.json`.

## 1. Executive summary

- Pipeline end-to-end funzionante: 262 righe news (134 articoli) → 262 segnali → 6 ordini S4 (3 BUY, 3 SELL), tutti filled, paper (`broker_environment=paper`), nessun ordine duplicato, nessun roundtrip < 30 min, nessun BUY ripetuto > 3.
- **Outage dell'ensemble Ollama 15:42–16:55 UTC (~73 min)**: quota esaurita (HTTP 429) su entrambi i modelli → 48 segnali FinBERT. Il motivo persistito dice "Ollama timeout" ma la causa è 429 quota exhausted; nessun alert recapitato (log-only).
- Fallback complessivo: 151/262 segnali (57,6%) con `fallback_used=true` (48 FinBERT + 7 single-glm + 96 single-gpt-oss). Solo 111 segnali sono ensemble a due modelli.
- Il fallback ha avuto un effetto sul portafoglio: BA chiusa alle 16:52 per `fallback_filtered` (segnale +0,396 vecchio di 22,8 h, escluso come fallback); l'uscita si è rivelata favorevole (drift post-uscita −7,9 $).
- Trade chiusi: SPCX +58,70 $, BA −17,79 $, AVGO −11,32 $ (netto). Totale realizzato su trade chiusi il 06/10: **+29,59 $**. NAV +320,75 $ (+0,29%) a 20:00 UTC vs SPY +0,55%.
- Churn S4 su SPCX: SELL 16:07 (segnale conf 0,15 score 0,000 che ha sovrascritto due segnali rialzisti 0,37/0,41) e BUY 18:37; AVGO comprato con 147% del movimento già avvenuto e chiuso dopo 1h45 da un segnale generico di settore (−0,025).
- Rete host/Alpaca intermittente 15:42–15:53 (Telegram `Network is unreachable`, barre Alpaca e clock non raggiungibili) senza alert.
- Decay monitor: 6 CRITICAL alle 21:00 (S1/S2/S4), solo log; nessun canale (F-062).
- Il token del bot Telegram è ancora in chiaro nei log (17.266 righe httpx, F-018).
- Nessun difetto di correttezza nuovo che invalidi l'evidenza; 12 finding esistenti riconfermati, 1 nuovo (etichetta causale errata del fallback).

## 2. Verdict finale

**OK con warning** — esecuzione coerente con le regole S4 e riconciliata ordini/trade/posizioni; warning per outage Ollama non segnalato (e mal etichettato), fallback al 57,6%, copertura news 47,9%.

## 3. Timeline (UTC)

| Ora | Componente | Evento | Fonte |
|---|---|---|---|
| 05:35 | worker-inference | 8 errori Telegram polling (connection reset) | log |
| 07:00 | worker-inference | regime detection: LLM-2 Ollama 410 Gone (2 occorrenze); regime finale SIDEWAYS ×0,7 | log |
| 08:20, 10:16 | worker-inference | 9 timeout gpt-oss (90 s), 6 timeout glm-5.3 | log |
| 13:30 | snapshot | NAV 110.513,51 $, prev close 110.376,05, 41 posizioni, gross 34,3%, cash 72.592,50 | portfolio_monitor_snapshots |
| 13:32 | ingest | primo articolo Benzinga WS, ensemble attivo | news_log / ensemble_cycle_health |
| 14:07 | portfolio-cycle | primo ciclo RTH (37 min dopo l'open): 10 SKIP_PYRAMIDING nel giorno, 1 SKIP_STALE (ARM, segnale 19,9 h) | execution_decisions |
| 15:18–17:30 | ingest | 8 articoli GDELT (1.787 recuperati, 1.779 senza ticker) | news_log / ingestion_stats_daily |
| 15:42 | LLM | **Inizio 429 quota exhausted** su glm-5.3 e gpt-oss; 48 FinBERT fallback fino alle 16:55 | worker-inference, finbert_fallback_events |
| 15:42–15:53 | rete | Alpaca data/clock e Telegram irraggiungibili (barre SPCX, "could not read market clock" 15:51) | worker log |
| 16:07 | execution | SELL SPCX (below_entry_gate, segnale 15:34 score 0,000 conf 0,15), stop protettivo cancellato prima della vendita; fill 173,785 | execution_decisions 63481, orders |
| 16:22 | LLM | FinBERT SPCX −0,831 conf 0,88 (etichetta "Ollama timeout") | sentiment_signals 14268 |
| 16:52 | execution | SELL BA (fallback_filtered), fill 190,80 | decisione 63808 |
| 16:55 | LLM | fine outage; ensemble riprende | finbert_fallback_events |
| 17:52 | execution | BUY AVGO 1.573 $ (segnale 17:46 +0,311, gate 0,373); fill 379,957 | decisione 64252 |
| 18:07 | stop | stop protettivo AVGO qty 4 (su 4,139) | orders |
| 18:37 | execution | BUY NOW e BUY SPCX (~1.574 $ ciascuno, gate 0,408/0,486) | decisioni 64602/64601 |
| 18:52 | stop | stop NOW qty 11 (su 11,51) e SPCX qty 9 (su 9,16) | orders |
| 19:37 | execution | SELL AVGO (below_entry_gate, segnale 19:32 −0,025 conf 0,25); fill 377,43 | decisione 65061 |
| 20:00 | snapshot | NAV 110.696,80 $ (+320,75), unrealized 2.559,89 | snapshot |
| 21:00 | decay monitor | 6 CRITICAL (S1/S2/S4), solo log | worker log |
| 22:00–22:45 | batch | forward-return worker (1033 aggiornati, 0 errori), counterfactual worker (945/857) | worker log |

## 4. News ingest

| Fonte | Righe news_log | Ticker | WS | Fetched (stats) | Queued | Duplicati (stats) | Scartate no-ticker | Scartate stale |
|---|---|---|---|---|---|---|---|---|
| alpaca_benzinga | 254 | 60 | 254 | 943 | 606 | 5.615 | 0 | 129 |
| gdelt_gkg | 8 | 7 | 0 | 1.787 | 8 | 0 | 1.779 | 0 |

- 262 righe, 134 articoli unici (133 URL), fan-out ×1,96; 99 ISSUER_SPECIFIC, 163 TAG_UNCONFIRMED (62%); effective_timely_coverage 46/96 ticker = **47,9%**.
- Volume orario 25–47 righe/h dalle 13 alle 19 UTC, nessun buco. Nessun timestamp futuro (`published_at > fetched_at` = 0), nessun `discarded_reason` valorizzato, 0 parse_fail.
- Top ticker: GOOGL 23, NVDA 21, SPY 21, MSFT 17, AMZN 13, META 13. SPY/QQQ (ETF) generano segnali non tradabili.
- `ingestion_stats_daily.duplicates` (5.615) > `fetched` (943) per alpaca_benzinga: contatore incoerente (F-007).

## 5. Performance modelli LLM

Fonte: `llm_responses` (2026-10-06).

| Modello | Risposte | `eligible=true` | Polarity media | Confidence media | Score medio | |pol|>0,5 | Errori log |
|---|---|---|---|---|---|---|---|
| glm-5.3:cloud | 210 | 45 | +0,073 | 0,303 | +0,037 | 6 | 429 (48) + timeout 90 s (6) |
| gpt-oss:20b-cloud | 212 | 45 | +0,045 | 0,450 | +0,030 | 15 | 429 (48) + timeout 90 s (9) |
| finbert (fallback) | 48 segnali | — | score medio +0,187 | 0,544 | — | — | — |

- Accordo: 208 coppie, differenza media |Δpolarity| 0,113, 0 disaccordi ≥ 0,8, 2 inversioni di segno con Δ ≥ 0,4.
- Segnali: 262; 131 con |score| < 0,05; |score| ≥ 0,30: 13 ensemble e 23 fallback (FinBERT/single) — la quota di segnali forti dal fallback (64%) è anomala.
- Per segnali con news duplicate: nessun `news_log_id` con più segnali; la stessa notizia fan-out su più ticker produce segnali distinti per ticker (F-012).
- LLM chiamati solo nei worker `inference` (Celery), non nel loop di trading; le decisioni leggono segnali già persistiti.
- Latenza media per modello: **non ricostruibile** (nessuna traccia di trasporto, F-086).

## 6. Segnali finali per ticker (selezione)

| Ticker | N | Score medio | Max | Min | Esito |
|---|---|---|---|---|---|
| GOOGL | 23 | −0,022 | 0,18 | −0,83 | min FinBERT/fallback; nessun ordine |
| NVDA | 21 | +0,130 | 0,71 | −0,18 | max 0,71; nessun ordine (gate/late-entry) |
| MRVL | 7 | +0,365 | 0,68 | 0,00 | SKIP_PYRAMIDING ×2 (già a libro 16/09) |
| MU | 7 | +0,174 | 0,68 | 0,01 | SKIP_PYRAMIDING (a libro 17/09) |
| SPCX | 8 | +0,023 | 0,40 | −0,83 | SELL 16:07, BUY 18:37 |
| AVGO | — | — | 0,418 (FinBERT) | −0,240 | BUY 17:52, SELL 19:37 |
| BA | — | — | 0,396 (05/10) | 0,061 | SELL 16:52 |

Decisioni del giorno: 1.563 OBSERVE_LATE_ENTRY, 612 SKIP_THRESHOLD, 314 SHADOW_LATE_ENTRY, 58 SKIP_FALLBACK, 10 SKIP_PYRAMIDING, 1 SKIP_STALE, 3 BUY, 3 SELL (2.564 righe, 23 minuti-ciclo distinti).

## 7. Ordini

| Ora | Strategia | Ticker | Azione | Qty | Fill | Stato | Segnale/rationale | Anomalie |
|---|---|---|---|---|---|---|---|---|
| 16:07 | S4 | SPCX | SELL | 9,281 | 173,785 | filled | below_entry_gate, segnale 15:34 score 0 | decisione senza signal_id; segnale più recente sovrascrive i forti (F-023) |
| 16:52 | S4 | BA | SELL | 8,064 | 190,80 | filled | fallback_filtered | motivo cita come "fallback" un segnale ensemble vecchio |
| 17:52 | S4 | AVGO | BUY | 4,139 | 379,957 | filled | +0,311 × 1,20 → gate 0,373 | movimento precedente 147% (F-030) |
| 18:37 | S4 | NOW | BUY | 11,510 | 136,76 | filled | +0,340 × 1,20 → gate 0,408 | movimento precedente 347% |
| 18:37 | S4 | SPCX | BUY | 9,162 | 171,80 | filled | +0,405 × 1,20 → gate 0,486 | rientro 2h30 dopo SELL (F-013) |
| 19:37 | S4 | AVGO | SELL | 4,139 | 377,43 | filled | below_entry_gate, segnale 19:32 −0,025 conf 0,25 | uscita da segnale generico di settore (F-008) |

Ordini stop broker (3 cancellati, 1 per posizione): AVGO qty 4/4,139, SPCX 9/9,16, NOW 11/11,51 (copertura parziale, F-022). Stop cancellati prima della vendita; nessun stop scattato.

## 8. PnL / rendimento

| Trade | Ticker | Apertura | PnL lordo | Costi | PnL netto | Tipo |
|---|---|---|---|---|---|---|
| 1054 | SPCX | 05/10 | +60,33 | 1,63 | **+58,70** | realizzato, aperto prima del 06/10 |
| 1053 | BA | 05/10 | −16,93 | 0,86 | **−17,79** | realizzato, aperto prima |
| 1055 | AVGO | 06/10 | −10,46 | 0,87 | **−11,32** | realizzato, aperto il 06/10 |
| 1056 | SPCX | 06/10 | aperto a EOD (mtm +1,10) | — | chiuso 07/10: −40,59 | non realizzato il 06/10 |
| 1057 | NOW | 06/10 | aperto a EOD (mtm +13,93) | — | chiuso 07/10: +13,06 | non realizzato il 06/10 |

- Realizzato 06/10 su trade chiusi: +29,59 $ netto (tutto S4). NAV +320,75 $ (+0,29%) vs SPY +0,55%; il resto è unrealized sulle 41 posizioni S1/legacy (beta, non attribuibile a difetti).
- Drift post-uscita (dossier): SPCX −17,31, BA −7,90, AVGO −6,71 → le tre uscite hanno evitato perdite.
- Slippage: `trades.slippage_est` è una copia di `cost_usd` (F-015), quindi non misurato. Fill price = prezzo di decisione in tutti gli ordini.
- Non disponibile: PnL per ticker delle 41 posizioni S1 (richiede close 05/10 per posizione), query: `portfolio_monitor_snapshots` + barre Alpaca daily.

## 9. Correttezza buy/sell

- BUY consentiti: 3/3 con gate ≥ 0,30 (0,373/0,408/0,486), ensemble a due modelli, segnale < 4 h, nessun BUY su fallback. OK.
- SELL: 3/3 coerenti con la regola (below_entry_gate ×2, fallback_filtered ×1). Nessuna uscita per stop-loss, max holding o rebalance band. `hold_minimum_expiry` su AVGO dopo 1h45 conforme al minimo di tenuta.
- Pyramiding: 10 SKIP_PYRAMIDING corretti (BA, XLE, SPCX, MRVL ×2, TSM ×2, AMD ×2, MU) ma bloccano ingressi S4 su titoli già detenuti da S1/legacy (F-031/F-089).
- Nessun SELL con sentiment positivo: SELL BA ha come "score" citato +0,396 ma la decisione è di filtro fallback, non di segnale positivo (vedi DAY-001).
- Nessun ordine duplicato, nessun ordine nello stesso minuto, nessun ordine a score < 0,05 (BUY a 0,020 = peso target 2% in `score`, segnale 0,311–0,405), nessun NO-ORDER (6 decisioni BUY/SELL ↔ 6 ordini), nessun ordine fuori orario.
- Riconciliazione: 6 ordini filled ↔ 5 trade (1053–1057, trade 1054 chiusa il 06/10) coerenti; cash 72.592,50 → 72.585,47 (−7,03) coerente con acquisti 4.721 e vendite 4.714.
- `exit_mechanism`: etichette pre-#184 non rilevanti oggi (righe del 06/10 successive al fix; i motivi riportano il meccanismo esplicito).
- Paper/live: tutti gli snapshot `paper` / `alpaca_paper`.
- Non verificato: circuit breaker (nessuna evidenza di attivazione), stato `strategy_lifecycle`.

## 10. Anomalie

### [DAY-001] Motivo di exit `fallback_filtered` cita un segnale ensemble come "FinBERT fallback"

* Tipo: Anomalia
* Area: Signal
* Evidenza:
  * file/log/tabella: execution_decisions id 63808; sentiment_signals id 14068, 14271
  * timestamp: 2026-10-06 16:52
  * snippet/query: reason "S4 signal excluded ... as FinBERT fallback, #108 (age=22.8h ..., generated 2026-10-05 18:03 UTC, score=+0.396)"; il segnale 14068 ha `fallback_used=false`, model ensemble; l'unico fallback BA è 14271 (16:31, +0,061 FinBERT)
* Descrizione: la posizione BA è stata chiusa perché il segnale più recente era FinBERT e quello ensemble era già oltre max_age; il testo attribuisce invece il fallback al segnale ensemble vecchio.
* Impatto: le analisi causali (alpha-miss, dossier) leggono un motivo fuorviante; correlato a F-056/F-060.
* Severità: Low
* Confidenza: Medium
* Azione consigliata: far citare nel motivo l'id e il modello del segnale effettivamente escluso.
* Test/monitor consigliato: test che il segnale citato in `reason` sia quello con `fallback_used=true`.

### [DAY-002] Outage ensemble Ollama (429 quota exhausted) 15:42–16:55 etichettato "timeout", nessun alert (F-049, F-086)

* Tipo: Anomalia
* Area: LLM / Ops
* Evidenza:
  * file/log/tabella: worker-inference-2026-10-06.log (48+48 righe "rate limit (429) ... quota exhausted"); finbert_fallback_events (48 righe, reason "Ollama timeout"); ensemble_cycle_health 1644–1671
  * timestamp: 15:42:53 → 16:55:15 UTC
  * snippet/query: `select reason,count(*) from finbert_fallback_events where created_at::date='2026-10-06'`
* Descrizione: entrambi i modelli hanno risposto 429 per ~73 min; tutti i segnali del periodo sono FinBERT (23 con |score| ≥ 0,30, tra cui SPCX −0,831 conf 0,88). Il motivo persistito dice "timeout", cancella la distinzione tra quota e latenza. Nessun alert recapitato.
* Impatto: SKIP_FALLBACK e uscita BA indotta dal fallback; la serie osservata mescola quota-esaurita e timeout.
* Severità: Medium
* Confidenza: High
* Azione consigliata: persistere `reason` reale (429 vs timeout); alert quando il tasso di fallback supera una soglia (monitoraggio, non taratura).
* Test/monitor consigliato: alert se ≥ N fallback consecutivi da 429.

### [DAY-003] Fallback al 57,6% dei segnali; 96 single-model gpt-oss (F-078, F-087)

* Tipo: Rischio
* Area: LLM
* Evidenza:
  * file/log/tabella: sentiment_signals 2026-10-06
  * timestamp: intera giornata
  * snippet/query: `count(*) filter (where fallback_used)` = 151 / 262 (48 finbert, 7 single glm, 96 single gpt-oss)
* Descrizione: solo 111 segnali sono ensemble a due modelli; i single-model hanno `fallback_used=true` e sono scartati dall'ingresso (58 SKIP_FALLBACK) ma non dall'uscita.
* Impatto: copertura segnali di ingresso ridotta; definizione di "fallback FinBERT" resta ambigua.
* Severità: Medium
* Confidenza: High
* Azione consigliata: separare contatori FinBERT e single-model nella telemetria.
* Test/monitor consigliato: metrica giornaliera fallback_rate per tipo.

### [DAY-004] Churn S4 su SPCX e uscita AVGO da segnale generico

* Tipo: Anomalia
* Area: Signal / Orders
* Evidenza:
  * file/log/tabella: decisioni 63481, 64601, 65061; sentiment_signals 14226, 14366
  * timestamp: 16:07, 18:37, 19:37
  * snippet/query: SPCX SELL su segnale 15:34 (conf 0,15, "Musk political appointment") dopo segnali 0,37/0,41; AVGO SELL su −0,025 conf 0,25 ("Sector sentiment mildly negative")
* Descrizione: segnali a bassissima confidenza sovrascrivono segnali forti (solo ultimo segnale per simbolo) e chiudono posizioni (F-013/F-023/F-059/F-008).
* Impatto: cicli SELL→BUY; le tre uscite del giorno sono state comunque favorevoli (drift negativo), quindi nessun costo misurato oggi.
* Severità: Low
* Confidenza: High
* Azione consigliata: registrare come occorrenza di F-013/F-023; nessuna taratura (freeze).
* Test/monitor consigliato: misura ricorrenza churn nel dossier.

### [DAY-005] Segnale di ingresso tardivo: AVGO/NOW/SPCX acquistati dopo il movimento (F-030)

* Tipo: Anomalia
* Area: Signal
* Evidenza:
  * file/log/tabella: dossier 2026-10-06 `ingressi`
  * timestamp: 17:52, 18:37
  * snippet/query: quota_movimento_precedente_al_segnale AVGO 1,47, NOW 3,47, SPCX 2,41; AVGO mtm_eod −17,16
* Descrizione: la notizia è arrivata quando il movimento era già pagato; AVGO chiuso a −11,32 $.
* Impatto: perdita misurata su trade 1055.
* Severità: Low
* Confidenza: High
* Azione consigliata: occorrenza F-030.
* Test/monitor consigliato: già coperto da late_entry_joint_distribution.

### [DAY-006] Rete intermittente 15:42–15:53 senza alert (F-094)

* Tipo: Anomalia
* Area: Ops
* Evidenza:
  * file/log/tabella: worker-2026-10-06.log 15:42:12 (barre SPCX), 15:51:08 (clock); worker-inference 15:43:29, 15:52–15:53 ("Network is unreachable")
  * timestamp: 15:42–15:53
  * snippet/query: `grep "Network is unreachable"`
* Descrizione: coincide con l'inizio dell'outage LLM; non è chiaro se il 429 e la rete siano correlati.
* Impatto: cicli 15:37–15:52 potrebbero aver letto dati stantii; nessuna decisione eseguita in quel periodo.
* Severità: Low
* Confidenza: Medium
* Azione consigliata: occorrenza F-094.
* Test/monitor consigliato: alert off-host (heartbeat esterno).

### [DAY-007] Copertura e qualità ingest: 47,9% copertura, 62% TAG_UNCONFIRMED, GDELT 0,4% di resa, contatore duplicates > fetched (F-001, F-007, F-012)

* Tipo: Anomalia
* Area: News
* Evidenza:
  * file/log/tabella: ingestion_stats_daily 2026-10-06; dossier `copertura_articoli`
  * timestamp: giornata
  * snippet/query: alpaca_benzinga fetched 943 / duplicates 5.615; gdelt fetched 1.787 / discarded_no_ticker 1.779
* Descrizione: contatori incoerenti e copertura bassa riconfermati.
* Impatto: osservabilità del volume reale.
* Severità: Low
* Confidenza: High
* Azione consigliata: occorrenze F-001/F-007/F-012.
* Test/monitor consigliato: invariante duplicates ≤ fetched.

### [DAY-008] Alert CRITICAL del decay monitor e token Telegram nei log (F-062, F-018)

* Tipo: Rischio
* Area: Ops
* Evidenza:
  * file/log/tabella: worker-2026-10-06.log 21:00:00 (6 CRITICAL); worker-inference (17.266 righe httpx con bot token)
  * timestamp: 21:00; giornata
  * snippet/query: "DECAY CRITICAL [S4]: Sharpe below 50% of baseline: -3.24 vs 0.80"
* Descrizione: gli alert vanno solo a log; il bot token resta in chiaro.
* Impatto: segnali di degrado non recapitati; credenziale esposta nei log.
* Severità: Medium
* Confidenza: High
* Azione consigliata: occorrenze F-062/F-018; ruotare il token e redigere l'URL.
* Test/monitor consigliato: log scrubbing in CI.

## 11. Aree risultate corrette

- BUY solo con ensemble a due modelli, segnale fresco e gate ≥ 0,30.
- Nessun ordine duplicato, nessun roundtrip < 30 min, nessun BUY ripetuto, nessun NO-ORDER.
- Cash/ordini/trade riconciliati; stop cancellati prima della vendita.
- Nessun timestamp futuro, nessuna news scartata silenziosamente (`discarded_reason` assente), nessun parse_fail.
- Le tre uscite hanno evitato perdite (drift negativo).

## 12. Dati mancanti o non accessibili

- Latenza LLM per modello (nessuna traccia, F-086).
- PnL giornaliero per ticker delle 41 posizioni S1/legacy (servono close del 05/10).
- Restart dei worker: log senza evidenza chiara (3 corrispondenze generiche), non determinato.
- Stato circuit breaker e `strategy_lifecycle` non verificati.
- `/api/decisions`, `/api/signals`, `/api/trades` non interrogati (DB più completo).

## 13. Raccomandazioni immediate

1. Persistere la causa reale del fallback (429 vs timeout) — correttezza dell'evidenza.
2. Alert per outage Ollama e tasso di fallback (monitoraggio).
3. Ruotare e redigere il token Telegram nei log.
4. Nessuna taratura fino al 2026-09-28 (già scaduto) — il charter va verificato.

## 14. Test o monitor da aggiungere

- Test: segnale citato in `reason` = segnale effettivamente escluso (DAY-001).
- Monitor: fallback_rate per tipo (FinBERT/single), 429 consecutivi, heartbeat di rete.
- Invariante `duplicates ≤ fetched`.

## 15. Ticket tecnici suggeriti

- T1: `finbert_fallback_events.reason` deve riportare 429 vs timeout (estende F-086).
- T2: alert off-host per outage LLM/rete (F-049, F-094).
- T3: redazione token Telegram nei log (F-018).

## 16. Stato sistema

- Ollama: parzialmente giù 15:42–16:55 UTC (~1,2 h) per 429; timeout sporadici alle 08:20 e 10:16.
- FinBERT fallback rate: 48/262 segnali = 18,3% (FinBERT); fallback totale 151/262 = 57,6%.
- Worker restart: non determinato dai log del giorno.
- Telegram polling: errori 05:35 e 15:43–15:53.
