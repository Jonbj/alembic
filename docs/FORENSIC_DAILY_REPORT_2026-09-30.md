# Forensic Daily Report — 2026-09-30

Analisi read-only (DB `alembic-postgres-1`, log host `logs/containers/*-2026-09-30.log`, dossier `docs/evidence/dossier/2026-09-30.json`, API locale). Timezone operativo: **UTC** (`celery_app.py`); il 30/09 è in EDT, quindi RTH = 13:30–20:00 UTC. Report scritto l'2026-10-09 (analisi retrospettiva: l'API `/positions` riflette lo stato odierno, non quello del 30/09, e non è stata usata per il P&L del giorno).

## 1. Executive summary

- Pipeline end-to-end funzionante: 208 righe news → 208 segnali (63 simboli) → 24 cicli portfolio (14:07–19:52Z) → 3 BUY + 4 SELL, tutti S4, tutti **paper**, tutti fillati; nessun ordine duplicato, nessun roundtrip <30 min, nessun pyramiding.
- NAV 109.786,32 → 109.784,56 (−1,76 $, −0,002%) contro SPY −0,21% / QQQ +0,25%. P&L realizzato S4 del giorno **−21,84 $** (SPCX +19,69; HOOD −15,80; BA −18,95; NVO −6,78), S1 realizzato 0.
- I tre ingressi S4 (HOOD, BA, NVO) sono usciti dopo 1,75–2,25 h con `below_entry_gate` a punteggio ancora **positivo** (+0,294 / +0,102 / −0,028): effetto del segnale "ultimo vince" + assenza di banda ingresso/uscita (F-023, F-059, F-013); il prezzo ha poi continuato a scendere, quindi le uscite sono state favorevoli sul giorno.
- 4/4 SELL senza `signal_id` (regressione già a ledger, F-011).
- Ensemble: 37,5% dei segnali in fallback single-model (78/208), 3 FinBERT per divergenza; GLM-5.3 ineleggibile (conf <0,30) in 70/127 risposte d'ensemble. 5 timeout Ollama (90 s) in giornata, nessun blocco prolungato.
- WebSocket news Alpaca: 102 errori `connection limit exceeded` (nessun alert); ingest comunque continuo (186 righe WS).
- Un caso di fan-out errato: articolo su Northrop Grumman taggato BA → FinBERT −0,92 su BA (bloccato da SKIP_FALLBACK, nessun ordine).
- Bot token Telegram ancora in chiaro nei log (F-018); alert CRITICAL del decay monitor senza canale (F-062).

## 2. Verdict finale

**OK con warning.** Esecuzione coerente con le regole e senza violazioni di safety; i warning sono difetti strutturali già a ledger (churn per mancanza di banda, tracciabilità SELL, osservabilità alert) che non hanno prodotto perdite anomale nel giorno.

## 3. Timeline (UTC)

| Ora | Componente | Evento | Fonte |
|---|---|---|---|
| 11:48 | news ingest | primo articolo in `raw_ingested_at` (pubblicato pre-market; `fetched_at` min 13:39) | news_log |
| 13:30 | monitor | NAV 109.896 (prev close 109.786), 44 posizioni, paper | portfolio_monitor_snapshots |
| 13:39–13:50 | sentiment | burst di scoring pre-apertura (HOOD: 7 segnali 13:41–13:50 su articoli 12:15–13:02) | sentiment_signals |
| 14:07 | portfolio-cycle #1 | BUY HOOD (sent +0,307, signal 13377, fill 115,45); SKIP_STALE CVX/VALE/XLF; SKIP_PYRAMIDING SPCX | execution_decisions |
| 14:22 | ciclo | BUY BA (+0,580×1,20 → gate 0,695; fill 189,65) | idem |
| 14:37 | ciclo | BUY NVO (+0,292×1,20 → 0,350; fill 38,52); SELL SPCX (`below_entry_gate`, score +0,265, +19,69 $) | idem |
| 14:22/14:37/14:52 | stop protettivi | stop parziali (qty intera) per HOOD/BA/NVO inviati e poi cancellati all'uscita | /orders |
| 15:52 | ciclo | SELL HOOD (hold_minimum_expiry, −15,80) | trades |
| 16:07 | ciclo | SELL BA (−18,95) | trades |
| 16:52 | ciclo | SELL NVO (−6,78) | trades |
| 17:52–19:52 | cicli | nessun ordine reale; SKIP_PYRAMIDING LLY 17:52, PANW 18:52 | execution_decisions |
| 19:52 | worker | warning #161: MS (−15,4%) e WDC (−16,5%) non protetti (`sub_one_share`) | worker log |
| 20:00 | monitor | NAV 109.784,56 (−1,76), 43 posizioni | snapshots |
| 21:00 | decay monitor | 6 × DECAY CRITICAL (S1/S2/S4, Sharpe −6,60) solo log | worker log |
| 22:00 / 22:45 | worker | forward return (1122 upd.), counterfactual (956 upd., 0 errori) | worker log |

Beat/worker: nessun restart rilevato nei log del 30/09; unica anomalia di connessione = news-stream (§10).

## 4. News ingest

| Fonte | Trasporto | Righe | Note |
|---|---|---|---|
| alpaca_benzinga | ws | 186 | |
| alpaca_benzinga | rest | 4 | |
| gdelt_gkg | — | 18 | |
| **Totale** | | **208** | 123 contenuti unici (content_hash); 0 scartate (`discarded_reason` NULL), 0 timestamp futuri, 0 senza corpo, 0 senza `extraction_method` |

- Copertura: 46/96 ticker con articolo effective-timely (47,9%); 33 ticker a zero news. Volume del 29/09: 258 righe → il 30/09 (208) è nella norma.
- Fan-out: 85 mapping extra; titoli sindacati su molti ticker ("Growth Leads Sectors…" ×18, "Nasdaq 100 Climbs…" ×15).
- Entità HTML non decodificate in 142/208 righe (titolo o corpo) — F-076.
- Latenza pubblicazione→scoring: mediana 2 min, ma 38/208 segnali >30 min (pre-apertura, 13:39–13:50 sono news delle 11:48–13:02).
- Top per impatto: BA (F/A-XX $20B, +0,58) → BUY; HOOD (margine 4x, +0,307) → BUY; NVO (semaglutide CV, +0,292) → BUY; LLY (+0,698 finbert, SKIP_FALLBACK).

## 5. Performance modelli LLM

| Modello | Risposte | Eleggibili | Pol. media | Conf. media | Score medio (pol×conf) | Min / Max | Polarità 0 |
|---|---|---|---|---|---|---|---|
| glm-5.3:cloud | 207 | 57 | 0,110 | 0,322 | 0,054 | −0,47 / +0,43 | 34 |
| gpt-oss:20b-cloud | 207 | 57 | 0,056 | 0,467 | 0,040 | −0,77 / +0,77 | 47 |

- Timeout (90 s): 3 gpt-oss, 2 glm; nessun refusal/invalid-output rilevato nei log. Latenza media per modello non ricostruibile (nessuna traccia di trasporto, F-086).
- Segnali per modello: ensemble 127; single gpt-oss 73; single glm 5; finbert 3 → **fallback 81/208 = 38,9%** (non "tutti i simboli": Ollama non è mai stato giù).
- Alta varianza (ensemble_std ≥0,3): 2 segnali. Disaccordo: BA 13515 (glm +0,60 vs gpt-oss −0,85 su articolo Northrop) → FinBERT −0,92; LLY 13353 (+0,20 vs +0,80); DIS 13414 (+0,20 vs −0,40).
- Dominanza: nei 73 single-gpt-oss il segnale è interamente di gpt-oss (glm sotto soglia di confidenza); tutti esclusi dal ranking BUY (#108).
- Verifica funzionale: i modelli girano nel worker `inference` (background), mai nel loop di trading; i fallback single/FinBERT non entrano nei BUY (SKIP_FALLBACK: 38 righe). Resta F-054 (varianza mascherata: `ensemble_std` calcolato sul solo contributore eleggibile) e F-055 (output non validato per enum).
- `finbert_fallback_events`: 3 righe, tutte "ensemble divergence"; `body_chars` >0 in 3/3 (LLY 233, DIS 64, BA 459) → FinBERT ha visto parte del corpo.

## 6. Segnali finali per ticker (soglia gate 0,30; solo simboli con ordine o evento)

| Ticker | Segnale (id) | Score | Conf. | Std | Esito |
|---|---|---|---|---|---|
| HOOD | 13377 (13:50) | +0,307 | 0,63 | 0,198 | BUY 14:07; sostituito da 13390 (+0,294) → SELL 15:52 |
| BA | 13397 (14:17) | +0,580 | 0,81 | 0,177 | BUY 14:22 (gate 0,695 con velocity 1,20); sostituito da 13408 (+0,102, conf 0,45) → SELL 16:07 |
| NVO | 13399 (14:29) | +0,292 | 0,63 | 0,177 | BUY 14:37 (gate 0,350); sostituito da 13459 (−0,028) → SELL 16:52 |
| SPCX | 13370 (+0,325, 13:49) poi 13391 (+0,265) | | 0,63/0,55 | | SKIP_PYRAMIDING 14:07 (già a libro dal 29/09), SELL 14:37 |
| LLY | 13353 / 13520 | +0,698 (finbert) / +0,488 | | | SKIP_FALLBACK / SKIP_PYRAMIDING (S1 dal 15/07) |
| PANW | 13532 | +0,304 | | | SKIP_PYRAMIDING (a libro dal 14/09) |
| NOW | — | +0,199 | | | SKIP_THRESHOLD, titolo +3,13% (alpha-miss, F-009) |

Decisioni del giorno: SKIP_THRESHOLD 737, SKIP_FALLBACK 38, SKIP_STALE 3, SKIP_PYRAMIDING 3, BUY 3, SELL 4, più righe osservazionali (OBSERVE/SHADOW_LATE_ENTRY 2071, solo misura #512).

## 7. Ordini

| Ora decisione | Strategia | Ticker | Azione | Qty | Fill | Stato | Rationale / segnale | Note |
|---|---|---|---|---|---|---|---|---|
| 14:07 | S4 | HOOD | BUY | 13,0165 | 115,45 | filled | sent +0,307, peso 2% | regime_mult 0,7 |
| 14:22 | S4 | BA | BUY | 7,9136 | 189,65 | filled | +0,580×1,20 | |
| 14:37 | S4 | NVO | BUY | 39,0405 | 38,5223 | filled | +0,292×1,20 | |
| 14:37 | S4 | SPCX | SELL | 9,7544 | 151,35 | filled | below_entry_gate (+0,265) | no signal_id |
| 15:52 | S4 | HOOD | SELL | 13,0165 | 114,30 | filled | below_entry_gate (+0,294) | no signal_id |
| 16:07 | S4 | BA | SELL | 7,9136 | 187,36 | filled | below_entry_gate (+0,102) | no signal_id |
| 16:52 | S4 | NVO | SELL | 39,0405 | 38,37 | filled | below_entry_gate (−0,028) | no signal_id |

Ambiente: `broker_environment=paper` (snapshot), motore `portfolio`. Prezzo atteso non persistito → slippage non misurabile (F-015). Gli stop protettivi (qty intera: 13/7/39) risultano `canceled` all'uscita, regolare. Cicli con `orders_count>0`: 20 su 24, somma 30 contro 7 ordini reali (F-014).

## 8. PnL / rendimento

| Voce | Valore | Confidenza / fonte |
|---|---|---|
| NAV 13:30 → 20:00 | 109.786,32 → 109.784,56 (−1,76 $) | misurata, portfolio_monitor_snapshots |
| Realizzato S4 | −21,84 $ (SPCX +19,69; HOOD −15,80; BA −18,95; NVO −6,78) | misurata, trades 1036/1038/1039/1040 |
| Realizzato S1 | 0 | market_daily.jsonl |
| Costi | 1,53 + 0,83 + 0,83 + (NVO) $ — `slippage_est` = `cost_usd` (copia, F-015) | trades |
| Posizioni pre-esistenti (44) open→close | S1 −179,08 $ (35 pos.), S4 +89,69 $ (9 pos.) | dossier snapshot_apertura |
| Posizioni aperte il 30/09 | HOOD/BA/NVO: già chiuse (realizzato sopra) | trades |
| Peggiori/migliori | GM −37,1 (S1), MRK −23,2, LLY −20,3, MU −17,0; INTC +58,2 (S4), SPCX +26,0, PANW +23,1 | dossier |

Non riconciliabile al centesimo: la somma open→close (≈ −89,4 pre-esistenti − 41,5 nuovi = ≈ −131 $) non coincide con il NAV (−1,76 $) perché i marks del dossier partono dall'open e **escludono il gap overnight** (≈ +129 $ implicito, plausibile). Per chiudere il conto serve `close_prec` per posizione (query: prezzo di chiusura 29/09 × qty a libro vs NAV prev close). P&L non realizzato per ticker a fine giornata non ricostruito (richiede snapshot posizioni per data).

## 9. Correttezza buy/sell

- BUY: tutti con segnale non-fallback, ensemble a due modelli, soglia gate rispettata (HOOD 0,307≥0,30; BA 0,695≥0,30; NVO 0,350≥0,30), peso 2%, regime_mult 0,7. Nessun BUY su segnali stale (3 SKIP_STALE >4 h) o fallback.
- Pyramiding: guardia P0-05 scattata 3 volte correttamente (SPCX, LLY, PANW); nessun BUY ripetuto.
- SELL: etichetta decisione `below_entry_gate`; `exit_reason` in trades `hold_minimum_expiry` (HOOD, BA) e `portfolio_sell` (SPCX, NVO). **Avvertenza #184**: per righe pre-fix `exit_mechanism` è una stima per età; qui le 4 righe SELL riportano il motivo testuale esplicito, quindi la lettura sopra si basa sul testo, non sull'età.
- SELL con sentiment positivo (pattern A5): HOOD (+0,294), BA (+0,102), SPCX (+0,265) chiusi con score positivo ma sotto il gate d'ingresso — comportamento di design (`below_entry_gate`), non un bug di segno; è il difetto d'asimmetria F-059.
- Stop-loss: nessun stop colpito; holding minimo (1,75 h) rispettato e poi uscita immediata alla prima occasione. Max holding non rilevante. Banda di rebalance: nessuna evidenza.
- Duplicati/race: 7 ordini a timestamp distinti; nessun ordine identico nello stesso minuto. NO-ORDER: 3 BUY + 4 SELL decisioni = 7 ordini (nessun orfano). Score <0,05 con ordine: nessuno (`score`=0,02 è il peso target).
- Idempotenza Celery: nessun retry/duplicato rilevato; 24 cicli per 24 slot attesi (14:07–19:52, :07/:22/:37/:52).
- Fuori orario: nessun ordine fuori RTH. Primo ciclo alle 14:07 (finestre beat fisse UTC, F-021): 37 min di RTH senza ciclo.
- Reconciliation: ordini↔fill↔trades coerenti per le 7 righe; `run_reconcile_positions` 21:35 ok.

## 10. Anomalie

### [DAY-001] Uscite `below_entry_gate` a score positivo poco dopo l'hold minimo (churn S4)
* Tipo: Anomalia
* Area: Signal / Orders
* Evidenza:
  * file/log/tabella: execution_decisions 54009, 54563, 54676, 55025; trades 1036/1038/1039/1040
  * timestamp: 14:37, 15:52, 16:07, 16:52 UTC
  * snippet/query: `[below_entry_gate] … score=+0.294 … position closed` (HOOD); BA +0.102; segnale precedente +0,580
* Descrizione: S4 usa solo l'ultimo segnale per simbolo; un re-scoring a pochi minuti (HOOD 13377 +0,307 → 13390 +0,294; BA 0,580 → 0,102 su un secondo articolo) porta l'asset sotto il gate d'ingresso senza banda d'isteresi; l'uscita scatta alla scadenza dell'hold minimo.
* Impatto: realizzato −41,5 $ su 3 ingressi; sul giorno l'uscita è stata favorevole (drift post-uscita negativo in tutti i casi, secondo dossier) → nessun costo attribuibile.
* Severità: Medium
* Confidenza: High
* Azione consigliata: nessuna taratura (freeze); mantenere la raccolta (F-013, F-023, F-059).
* Test/monitor consigliato: contare per giorno i round-trip S4 con uscita a score ≥0 e <gate.

### [DAY-002] 4/4 SELL senza `signal_id`
* Tipo: Bug
* Area: Orders
* Evidenza: decision_signal_id_coverage (dossier): `regressions: ["SELL"]`; execution_decisions 54009/54563/54676/55025.
* Descrizione: la catena segnale→decisione→ordine è spezzata sul lato uscita; già a ledger (F-011) e registrato dalla sessione alpha-miss del 30/09.
* Impatto: audit/attribuzione dei SELL non verificabile da DB.
* Severità: Medium · Confidenza: High
* Azione consigliata: ticket di correttezza (già coperto da F-011), nessuna nuova occorrenza nel ledger per evitare doppioni.
* Test/monitor consigliato: invariante `SELL.signal_id IS NOT NULL` nel dossier con allerta.

### [DAY-003] Articolo su Northrop Grumman attribuito a BA
* Tipo: Anomalia
* Area: News / LLM
* Evidenza: finbert_fallback_events (BA, 17:44): input "Why Is Northrop Grumman Stock Falling on Wednesday?…", polarity −0,925; sentiment_signals 13515 (BA, finbert −0,766).
* Descrizione: fan-out/tag errato; gpt-oss −0,85 vs glm +0,60 → FinBERT su divergenza. Segnale scartato da SKIP_FALLBACK (18:52), quindi nessun ordine.
* Impatto: nessun costo (rischio: se fosse stato non-fallback avrebbe chiuso la posizione BA già chiusa).
* Severità: Medium · Confidenza: High
* Azione consigliata: vedi F-012/F-020 (risoluzione ticker deterministica).
* Test/monitor consigliato: contare articoli il cui titolo non cita l'emittente né un alias del ticker.

### [DAY-004] WebSocket news Alpaca: 102 × `connection limit exceeded`, nessun alert
* Tipo: Rischio
* Area: Ops / News
* Evidenza: worker-news-stream-2026-09-30.log (102 ValueError, 103 riavvii connessione, 1 "no close frame").
* Descrizione: probabile sessione WS duplicata (altra istanza/connessione zombie). L'ingest è continuato (186 righe ws) ma i log non hanno timestamp, quindi i buchi non sono quantificabili.
* Impatto: rischio di perdita news non misurabile; ricorrenza di F-085.
* Severità: Medium · Confidenza: Medium
* Azione consigliata: aggiungere timestamp al logger del news-stream e un contatore errori WS con alert.
* Test/monitor consigliato: allerta se errori WS >N/ora o assenza di articoli WS >15 min in RTH.

### [DAY-005] Telemetria ciclo: `orders_count` 30 vs 7 ordini reali
* Tipo: Bug · Area: Orders · Evidenza: portfolio_cycles 30/09 (20 cicli con orders_count>0, somma 30). Ricorrenza F-014.
* Impatto: metrica fuorviante, non operativa. Severità: Low · Confidenza: High
* Azione: già in F-014. Monitor: confronto orders_count vs ordini broker.

### [DAY-006] Bot token Telegram in chiaro nei log (httpx INFO)
* Tipo: Rischio · Area: Ops · Evidenza: worker-inference-2026-09-30.log, URL `…/bot<token>/getUpdates` ogni 5 s.
* Impatto: credenziale esposta in log persistenti; ricorrenza F-018. Severità: High · Confidenza: High
* Azione: ruotare il token e abbassare il livello httpx a WARNING (correttezza/sicurezza, non taratura).
* Monitor: grep CI sui log per `bot[0-9]+:`.

### [DAY-007] Decay monitor: 6 CRITICAL senza canale, metriche pipeline-globali identiche
* Tipo: Anomalia · Area: Ops / Risk · Evidenza: worker log 21:00:00 — S1/S2/S4 tutte "Sharpe −6,60", IC −0,017.
* Descrizione: valori identici per tre strategie = metrica globale (F-004); alert solo su log (F-062); nessuna consegna.
* Impatto: segnale di allarme non azionabile né attendibile. Severità: Medium · Confidenza: High
* Azione: vedi F-004/F-062. Monitor: test che le metriche per strategia differiscano.

### [DAY-008] Entità HTML non decodificate nei testi verso il modello
* Tipo: Bug · Area: News / LLM · Evidenza: 142/208 righe con `&#39;`/`&amp;`/`&quot;` (es. BA "What&#39;s Going On with Boeing Stock Today?"). Ricorrenza F-076.
* Impatto: rumore sul prompt; effetto sul punteggio non misurato. Severità: Medium · Confidenza: High
* Azione: già in F-076. Monitor: test sanitizer su `&#39;`.

### [DAY-009] Ineleggibilità GLM e varianza mascherata
* Tipo: Anomalia · Area: LLM
* Evidenza: llm_responses 30/09: glm ineleggibile in 70/127 risposte d'ensemble (conf media 0,21), gpt-oss 70/127; log `F-054 masked divergence …` (decine di righe, es. SPY std 0,1414 → 0,0000).
* Descrizione: il filtro d'eleggibilità riduce a un contributore e azzera `ensemble_std`; 73 segnali single-gpt-oss.
* Impatto: la varianza non è mai gate; i single-model sono esclusi dai BUY, quindi nessun ordine contaminato oggi. Severità: Medium · Confidenza: High
* Azione: vedi F-054. Monitor: persistere std su tutte le risposte.

### [DAY-010] Posizioni non protette (MS, WDC) per quantità sotto un'azione
* Tipo: Rischio · Area: Risk · Evidenza: worker log 19:52:05 "#161: MS unprotected at −15,4% (qty 0,0528, sub_one_share)", WDC −16,5% (qty 0,3347). Ricorrenza F-022.
* Impatto: perdite >15% senza stop, notional trascurabile (MS 10 $) o limitato (WDC). Severità: Low · Confidenza: High
* Azione: già in F-022.

### [DAY-011] Scoring pre-apertura con latenza alta (HOOD)
* Tipo: Anomalia · Area: News / Signal · Evidenza: HOOD articolo 13:02 → segnale 13:50 → BUY 14:07 con quota di movimento precedente 0,708 (dossier ingressi).
* Descrizione: ricorrenza di F-030/F-019; già registrata oggi dalla sessione alpha-miss (F-030, 34,75 $), nessuna nuova occorrenza.
* Severità: Medium · Confidenza: High

## 11. False positive / aree corrette

- Nessun ordine duplicato né ordini opposti ravvicinati sullo stesso ticker senza rationale; nessun pyramiding (guardia P0-05 funziona); nessun trade su segnali stale/fallback (SKIP_STALE, SKIP_FALLBACK corretti).
- Ambiente paper coerente (snapshot `paper`); nessun ordine fuori RTH; cicli completi 24/24; reconcile 21:35 ok; 0 timestamp futuri; 0 news scartate/senza campo; counterfactual 0 errori.
- Ollama non è mai stato giù (solo 5 timeout isolati); la percentuale di fallback alta è dovuta all'ineleggibilità di glm, non a un outage.
- Il "SELL con sentiment positivo" non è un bug A5 di segno: è `below_entry_gate`.

## 12. Dati mancanti / non accessibili

- Prezzo atteso al momento dell'ordine (slippage vero) — non persistito (F-015).
- Latenza per chiamata LLM e esito per modello — nessuna traccia di trasporto (F-086).
- Timestamp degli errori WS (log senza orario) → buchi di ingest non quantificabili.
- Posizioni/unrealized per ticker a fine 30/09 (l'API restituisce lo stato corrente): servirebbe `SELECT … FROM portfolio_monitor_snapshots` con dettaglio posizioni o il close del 29/09.
- Commissioni: solo stima `cost_usd` del modello costi, non da broker.

## 13. Raccomandazioni immediate

1. Ruotare il bot token Telegram e silenziare gli URL httpx (DAY-006).
2. Timestamp + contatore/alert sugli errori del news-stream WS (DAY-004).
3. Persistere `signal_id` sulle SELL (DAY-002, correttezza dell'audit).
4. Nessuna taratura di soglie/banda fino al 2026-09-28+ secondo la carta (il periodo di osservazione è formalmente scaduto: ogni modifica va decisa dall'operatore).

## 14. Test / monitor da aggiungere

- Invariante `SELL.signal_id NOT NULL` nel dossier con allerta.
- Alert su errori WS news e su assenza articoli WS >15 min in RTH.
- Test che le metriche del decay monitor siano per-strategia.
- Grep di sicurezza sui log per token bot.
- Confronto `portfolio_cycles.orders_count` vs ordini broker.

## 15. Ticket suggeriti (solo correttezza)

- T1: SELL senza `signal_id` (F-011).
- T2: News-stream WS: timestamp nei log + alert connection limit (F-085).
- T3: Redazione credenziali nei log httpx (F-018).
- T4: Decay monitor per-strategia + canale alert (F-004, F-062).

## 16. Stato sistema

- Ollama: **up** tutto il giorno; 5 timeout da 90 s (3 gpt-oss: 03:16/03:18/10:18… e 14:34, 17:38 UTC; 2 glm); downtime 0 h.
- FinBERT fallback rate: 3/208 segnali (1,4%) per divergenza; fallback complessivo (single-model + FinBERT) 81/208 = 38,9%. Su decisioni: SKIP_FALLBACK 38/788 righe decisionali non osservative (4,8%).
- Worker restart: nessuno rilevato nei log del 30/09; news-stream: 103 riavvii di connessione WS.
