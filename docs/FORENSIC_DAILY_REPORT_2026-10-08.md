# Forensic daily report — 2026-10-08 (giovedì)

Analisi read-only eseguita il 2026-10-21. Timezone operativo: UTC (`celery_app.py`); DST USA in vigore (EDT): RTH = 13:30–20:00 UTC; le finestre beat a UTC fisso restano fonte di ambiguità (F-021). Fonti: DB `trading` (solo SELECT), API REST locale, `logs/containers/*-2026-10-08.log` (worker, worker-inference, beat, api, worker-news-stream), `logs/deploy_reconcile_2026-10-08.log`, `docs/evidence/dossier/2026-10-08.json`, `market_daily.jsonl`, `ALPHA_MISS_REPORT_2026-10-08.md`.

## 1. Executive summary

- **La pipeline di valutazione si è fermata a metà seduta in due tempi.** Dalle 15:21Z Ollama Cloud risponde `429 quota exhausted` su **entrambi** i modelli (glm-5.3 e gpt-oss): ultima risposta LLM 15:23:26Z, poi 100% FinBERT (43 segnali, 15:06–16:15). Alle **16:20:12Z** `worker-inference` va in *warm shutdown* e non riparte: zero segnali 16:20→20:00 (3h40m di RTH) e oltre (F-096, che ora ha qui il primo avvistamento).
- LLM assenti in RTH per 4h37m (15:23→20:00) su 6h30m = 71%. La causa dello shutdown non è ricostruibile: nessun deploy (riconciliatore «Già allineato a 5463d279» alle 16:20:02), journal host vuoto. Due restart improvvisi (senza riga di shutdown) di worker e worker-inference anche alle 10:36Z e 12:56Z.
- Coda news: `news_queue_census` passa da 3 (16:30) a **326** (23:30); `ingestion_stats_daily` benzinga queued 729 contro 151 righe `news_log`. L'ingest WS ha continuato, il consumo no.
- Alert: un incidente `pipeline:signal_stale` (warning) si apre in `mobile_events` alle 16:39, ma `mobile_notification_deliveries` è vuota e non c'è alcun Telegram. Nessun alert sul 429 né sullo shutdown.
- Safety rispettata: nessun segnale fallback è diventato ordine (43 SKIP_FALLBACK, 16 sopra 0,30, fra cui −0,72 su 12 ticker da un solo articolo macro).
- Ordini: 3 BUY S4 (PLTR, SPCX 14:37; SAP 15:07) su 3 segnali ensemble ≥ 0,30, più 1 SELL SPCX alle 16:22 (`below_entry_gate`). Tutto paper, tutto in RTH, niente duplicati.
- PnL realizzato S4 **−24,03 $** (SPCX, trade 1060). NAV 110.523,94 → 110.265,37 (−258,57 $, −0,234%) contro SPY −0,42% e QQQ −1,34%.
- SPCX è stato chiuso per un segnale +0,275 arrivato 4 minuti dopo il +0,370 d'ingresso (F-023). L'uscita ha evitato ~27,86 $ rispetto a tenere fino al close.
- Copertura effective-timely 38/96 (39,6%), 40 ticker senza news. Il token Telegram è in chiaro in 11.778 righe di log. 6 DECAY CRITICAL scritti solo nel log.
- 0 finding nuovi; 18 finding esistenti riconfermati (F-096 retrodatato al 2026-10-08).

## 2. Verdict finale

**Anomalie significative.** Le regole di esecuzione hanno funzionato (ordini coerenti, fallback esclusi, riconciliazione OK). Però la valutazione LLM è mancata per il 71% della RTH: prima per esaurimento della quota del provider, poi per l'arresto del consumatore della coda. Nessuno dei due eventi è arrivato a un canale d'allerta. Il pomeriggio del 2026-10-08 non contiene evidenza di sentiment, quindi non è confrontabile con le altre sedute.

## 3. Timeline (UTC)

| Ora | Componente | Evento | Fonte |
|---|---|---|---|
| 00:02 | mobile_alert | incidente `broker_stale` critical, rientrato 00:03 | mobile_events |
| 00:16–12:26 | worker-inference (shadow) | 13 giri shadow off-session; 10:27 (743 s, 43 item) e 12:26 (676 s, 40 item) sono i più pesanti | worker-inference log |
| 08:20 | deploy reconcile | d3cb2ced → 5463d279, solo doc/test, nessun rebuild | deploy_reconcile log |
| 10:34:47 → 10:36:04 | worker + worker-inference | **restart senza riga di shutdown** (banner Celery, «Connected to redis») | log righe 22941/23004 |
| 12:55:28 → 12:56:49 | worker + worker-inference | **secondo restart improvviso** | log righe 28399/28462 |
| 13:30 | mobile_alert | `portfolio_cycle_late` critical + `signal_stale` warning (pre-apertura, finestra beat UTC: F-021) | mobile_events |
| 13:38:30 | ingest/sentiment | prima news Benzinga e primo segnale (ensemble attivo) | news_log, sentiment_signals |
| 14:07 | portfolio-cycle | primo ciclo (37 min dopo l'open); SKIP_STALE CAT/IWM/XLK | execution_decisions |
| 14:23 / 14:33 / 14:58 | sentiment | PLTR +0,392, SPCX +0,370, SAP +0,354 (ensemble) | sentiment_signals 14701/14717/14743 |
| 14:37 | portfolio-cycle | BUY PLTR (201,05) e SPCX (165,94), peso 2% | orders, trades 1059/1060 |
| 14:37:24 | sentiment | SPCX +0,275 (ensemble, conf 0,50) sovrascrive il +0,370 | sentiment_signals 14719 |
| 14:52 | portfolio-cycle | stop protettivi PLTR 7 / SPCX 9 (interi); Telegram 400 sull'alert #161 WDC −26,3% | orders, worker log |
| 15:07 | portfolio-cycle | BUY SAP (207,90) | orders, trade 1061 |
| 15:06 | sentiment | primo fallback FinBERT (MS) | finbert_fallback_events |
| **15:21–15:23** | Ollama Cloud | **429 «quota exhausted» su glm-5.3 e gpt-oss**; ultima risposta LLM 15:23:26 | log; llm_responses |
| 15:23–16:15 | sentiment | 21 cicli solo FinBERT (n_ensemble = 0) | ensemble_cycle_health |
| 15:23:37 | sentiment | articolo «8 Of 11 Sectors Fall… As Energy Leads» → FinBERT −0,72 su 12 ticker (XLE incluso) | finbert_fallback_events |
| 15:22 | portfolio-cycle | stop protettivo SAP 7 | orders |
| 16:07 | portfolio-cycle | isteresi di uscita SPCX (2 cicli) | worker log 4881 |
| 16:15:24 | sentiment | **ultimo segnale della giornata** (AMD, FinBERT) | sentiment_signals |
| **16:20:12** | worker-inference | **«worker: Warm shutdown (MainProcess)», nessun riavvio** | log riga 36320 |
| 16:22 | portfolio-cycle | SELL SPCX (`below_entry_gate`, +0,275), stop cancellato, fill 163,63 | orders, trade 1060 |
| 16:31 | snapshot | degradazione «signal activity aging», poi «stale» fino alle 19:55 | portfolio_monitor_snapshots |
| 16:39 | mobile_alert | `pipeline:signal_stale` warning aperto (rientrato solo il 10-16 13:33) | mobile_events |
| 16:30–23:30 | news queue | queue_depth 3 → 326 (beat emette 22 `run_sentiment_worker` mai ricevuti) | news_queue_census, beat log |
| 17:22 | portfolio-cycle | Telegram 400 sull'alert #161 WDC −28,4% / NOK −15,0% | worker log |
| 17:52 | portfolio-cycle | SKIP_STALE ARM (−0,312, 4,0 h) | execution_decisions |
| 19:52 | portfolio-cycle | ultimo ciclo RTH (24/24 cicli 14:07–19:52) | worker log |
| 20:00 | snapshot | NAV 110.265,37 $, 41 posizioni, gross 34,2% | portfolio_monitor_snapshots |
| 21:00 | decay monitor | 6 DECAY CRITICAL (S1/S2/S4), solo log | worker log |
| 22:50 | held_news_loss_alert | NOK e WDC (dopo il close) | mobile_events |
| 23:05 | worker | report giornaliero Telegram 200 | worker log |

## 4. News ingest

| Fonte | Righe news_log | Hash distinti | Ticker | Finestra | fetched / queued / duplicates / stale | Timestamp futuri |
|---|---|---|---|---|---|---|
| alpaca_benzinga | 151 | 77 | 54 | 13:38–16:15 | 974 / 729 / **5.472** / 167 | 0 |
| gdelt_gkg (org_lookup) | 9 | 9 | 4 | 15:04–16:00 | 2.517 / 32 / 2 (no_ticker 2.483) | 0 |

Righe per ora: 13h 22, 14h 71, 15h 56, 16h 11, poi **zero fino a fine giornata**. Ci sono 86 URL distinti su 160 righe (fan-out 1,86): ISSUER_SPECIFIC 74, TAG_UNCONFIRMED 86. Mediana created−published 30,1 min; nessuna riga oltre 2 h, nessun timestamp futuro, nessun corpo vuoto. 35 titoli contengono entità HTML (F-076, raw persistito; il prompt passa da `sanitize_text`). Copertura effective-timely 38/96 (39,6%), 40 ticker a zero righe (32 il 10-07). Il calo dopo le 16:20 non è un guasto del provider: l'ingest WS ha continuato, perché la coda è cresciuta fino a 326 item. Ha smesso solo il consumatore.

Ticker più presenti: NVDA 12, GOOGL 11, SPY 11, MSFT 11, SPCX 11, AMZN 10, GS 6. Confidenza: alta sulle righe a DB; media sul contatore duplicates (incoerente per F-007).

## 5. Performance modelli LLM

| Modello | Risposte | Eleggibili | polarity media | \|pol\| media | conf media | score medio | \|score\|≥0,3 | Ultima risposta | Errori (log) |
|---|---|---|---|---|---|---|---|---|---|
| glm-5.3:cloud | 112 | 22 | 0,052 | 0,180 | 0,306 | 0,025 | 3 | 15:22:00 | 8 timeout + **42 × 429** |
| gpt-oss:20b-cloud | 115 | 22 | 0,026 | 0,187 | 0,453 | 0,017 | 9 | 15:23:26 | 6 timeout + **42 × 429** |
| FinBERT (fallback) | 43 | — | — | — | 0,656 | −0,200 (\|·\| 0,406) | 28 | 16:15:23 | — |

Segnali per tipo (160): ensemble 62 (conf 0,355, std 0,075), single gpt-oss 50, single glm 5, FinBERT 43 (26,9%). Fallback totale 109/160 = 68,1%. Per ora i fallback sono 13h 9/22, 14h 35/71, 15h 43/56, 16h 11/11. Disaccordo fra i due modelli (110 coppie): 9 di segno opposto, 5 con |Δscore| ≥ 0,3, |Δ| medio 0,079. 106 righe di log «F-054 masked divergence», ensemble_std 0,000 con un solo eleggibile (F-054): fino a 0,566 su NVDA e 0,424 su SPCX. La latenza per modello non è persistita (F-086).

Fallback FinBERT (`finbert_fallback_events`, 43 righe). Il `reason` è sempre «Ollama timeout», ma dalle 15:23 l'errore reale nel log è il 429 (F-086). Su 41 righe su 43 `body_chars` > 0, quindi FinBERT ha visto parte del corpo; MS e SONY hanno title_chars = body_chars, cioè corpo uguale al titolo. Un solo articolo macro («8 Of 11 Sectors Fall In Thursday Trading As Energy Leads», 19 ticker) produce polarity −0,90 / conf 0,80 su 12 simboli: MRK, NFLX, NVDA, ORCL, QQQ, SPY, WMT, XLE, XLF, XLK, XLV, XOM. Per XLE è il segno sbagliato rispetto al titolo, ed è fuori dall'inviluppo dei modelli (F-087, F-012). Nessuno di questi segnali ha prodotto ordini.

Verifica funzionale: l'output è validato per schema JSON, ma enum e Unicode non sono normalizzati (F-055, non riosservato oggi). L'ensemble non usa la varianza come gate (F-037). Le news fan-out pesano su più ticker (F-012). Confidence bassa riduce lo score (score = polarity × confidence). Gli LLM girano solo nel worker-inference, mai nel ciclo portfolio. Hallucination: il rischio resta il fan-out, perché il fallback FinBERT è escluso dagli ingressi (#108).

## 6. Segnali finali per ticker (top)

| Ticker | N | Score medio | Max | Min | Fallback | Non-fallback ≥ 0,30 |
|---|---|---|---|---|---|---|
| NVDA | 12 | −0,035 | 0,392 | −0,829 | 10 | 0 |
| SPY | 11 | −0,096 | 0,120 | −0,720 | 8 | 0 |
| MSFT | 11 | 0,039 | 0,392 | −0,224 | 7 | 0 |
| GOOGL | 11 | 0,121 | 0,392 | −0,030 | 5 | 0 |
| SPCX | 11 | 0,076 | 0,392 | −0,829 | 8 | 1 (0,370) |
| AMZN | 10 | 0,036 | 0,338 | −0,180 | 3 | 0 |
| GS | 6 | 0,036 | 0,341 | −0,420 | 4 | 0 |
| PLTR | 4 | 0,202 | 0,392 | 0,120 | 2 | 1 (0,392) |
| SAP | 1 | 0,354 | 0,354 | 0,354 | 0 | 1 (0,354) |

Segnali non-fallback con |score| ≥ 0,30: PLTR +0,392, SPCX +0,370, SAP +0,354, ARM −0,312 (ribassista, book long-only, scaduto in SKIP_STALE alle 17:52). Decisioni del giorno: OBSERVE_LATE_ENTRY 1.867, SKIP_THRESHOLD 523, SHADOW_LATE_ENTRY 240, SKIP_FALLBACK 43 (16 sopra 0,30), SKIP_STALE 4, BUY 3, SELL 1. regime_mult 0,7 e velocity multiplier presenti nelle reason. Combiner e cap: peso 2% per slot S4. Circuit breaker: nessuno attivo; il breaker del fallback resta inerte (F-049).

## 7. Ordini

| Ora | Strategia | Ticker | Azione | Qty | Fill | Stato | Motivo / segnale | Anomalie |
|---|---|---|---|---|---|---|---|---|
| 14:37:08 | S4 | PLTR | BUY (notional) | 7,9693 | 201,05 | filled | sig 14701 +0,392, dec 68363 | — |
| 14:37:08 | S4 | SPCX | BUY (notional) | 9,6552 | 165,9445 | filled | sig 14717 +0,370, dec 68364 | sovrascritto 4 min dopo |
| 14:52:09 | S4 | PLTR | SELL stop | 7 | — | canceled (poi) | stop protettivo | copre 87,8%, +15 min |
| 14:52:09 | S4 | SPCX | SELL stop | 9 | — | canceled 16:22 | stop protettivo | copre 93,2%, +15 min |
| 15:07:11 | S4 | SAP | BUY (notional) | 7,6717 | 207,90 | filled | sig 14743 +0,354, dec 68604 | — |
| 15:22:08 | S4 | SAP | SELL stop | 7 | — | canceled (poi) | stop protettivo | copre 91,2%, +15 min |
| 16:22:13 | S4 | SPCX | SELL | 9,6552 | 163,63 | filled | `below_entry_gate`, sig 14719 +0,275, dec 69200 | decisione con signal_id NULL; ordine con decision_id = 68364 (BUY) |

Broker: Alpaca paper (`broker_environment=paper`, `mode=paper` su tutti gli snapshot). Tutti gli ordini sono in RTH. Nessun ordine identico nello stesso minuto, nessun ordine senza decisione (gli stop sono di sistema, quindi decision_id NULL). Prezzo atteso non persistito, quindi lo slippage non è calcolabile (F-015).

## 8. PnL / rendimento

| Voce | Valore |
|---|---|
| Realizzato S4 | **−24,03 $** (SPCX trade 1060: gross −22,35, costi 1,69) |
| Realizzato S1 | 0,00 $ |
| Da posizioni aperte prima del 10-08 | 0 realizzato; variazione non realizzata ≈ −236 $ (derivata: unrealized 2.397,04 → 2.160,86, include gli ingressi del giorno) |
| Da posizioni aperte il 10-08 | SPCX −24,03 realizzato; mark EOD dal dossier: PLTR −18,09 $, SAP +34,52 $ |
| Costi (cost_usd, già nel net) | 1,69 $ (SPCX); PLTR 0,89 / SAP 0,88 si realizzano alla chiusura del 10-12 |
| NAV 10-07 20:00 → 10-08 20:00 | 110.523,94 → 110.265,37 = −258,57 $ (−0,234%) |
| SPY / QQQ | −0,42% / −1,34% |
| Chiusure successive (fuori giornata) | PLTR +47,53 $ (10-12), SAP +70,08 $ (10-12) |

Non calcolabile senza altre query: PnL non realizzato per ticker (servono il close del 10-07 e del 10-08 per 41 posizioni, da barre daily Alpaca) e lo slippage (F-015).

## 9. Correttezza buy/sell

- BUY: i 3 ingressi corrispondono esattamente ai 3 segnali ensemble non-fallback ≥ 0,30. Peso 2% e anti-pyramiding attivo: SHEL saltato 4 volte, ma solo nel log e senza decisione persistita, perché il suo score era sotto soglia. Ingresso PLTR con `quota_nel_gap` 1,05, ma il denominatore è degenere e la quota non è interpretabile.
- SELL: SPCX ha seguito il percorso previsto. Hold minimum di 90 min (SELL saltato dalle 14:52 alle 15:52), poi isteresi di 2 cicli (16:07), poi uscita alle 16:22. `trades.exit_reason = hold_minimum_expiry` è l'etichetta diagnostica di #430: l'uscita è avvenuta al primo beat dopo l'hold minimo. Il trigger reale è `below_entry_gate`, letto dalla reason della decisione. Il trigger è un segnale +0,275 più recente del +0,370 d'ingresso (F-023/F-059). Non è il bug A5 (SELL con sentiment positivo per errore di segno): è l'asimmetria fra gate e uscita.
- `exit_mechanism`: l'uscita del 10-08 è etichettata dal testo del motivo (post-fix #184), quindi non è una stima per età.
- Nessun roundtrip < 30 min (SPCX 105 min). Nessun BUY ripetuto. Nessun ordine contrario ravvicinato senza rationale.
- Dati stale: SKIP_STALE applicato (CAT/IWM/XLK/ARM). Dopo le 16:20 nessun nuovo ingresso perché non c'erano segnali nuovi; le posizioni sono rimaste ferme in preserve-stale. Fail-safe corretto, ma nessuno è stato avvisato.
- LLM non valido o assente: i segnali fallback sono esclusi dagli ingressi (43 SKIP_FALLBACK). Nessun SELL causato da fallback: il −0,72/−0,83 FinBERT su posizioni detenute non ha attivato il reversal.
- Paper/live coerente. Retry Celery: nessuna duplicazione (160 news / 160 segnali; SIGNAL_DUPLICATE_SKIP SAP alle 17:22).
- Reconciliation: 7 ordini ↔ 3 trade (1 chiuso) ↔ posizioni 39 → 41 (+PLTR, +SPCX, +SAP, −SPCX), coerente con gli snapshot (41 alle 15:00, 42 alle 15:30, 41 alle 16:30).

## 10. Anomalie

### [DAY-001] worker-inference in warm shutdown alle 16:20Z senza riavvio: 3h40m di RTH senza scoring, coda in crescita, nessun alert recapitato

* Tipo: Bug
* Area: Ops
* Evidenza:
  * file/log/tabella: `logs/containers/worker-inference-2026-10-08.log` riga 36320; beat log; `news_queue_census`; `mobile_events`; `mobile_notification_deliveries`; `docker ps`
  * timestamp: 2026-10-08 16:20:12Z (ultimo task), restart improvvisi 10:34:47→10:36:04 e 12:55:28→12:56:49
  * snippet/query: `worker: Warm shutdown (MainProcess)`; 22 `run_sentiment_worker` emessi dal beat dopo le 16:20 e mai ricevuti; queue_depth 3 (16:30) → 326 (23:30); `mobile_events` `pipeline:signal_stale` warning aperto 16:39, `recovered` il 10-16 13:33; `mobile_notification_deliveries` 0 righe; deploy reconcile 16:20:02 «Già allineato»
* Descrizione: il consumatore della coda `inference` si arresta in modo ordinato. La causa non è nei log, nel riconciliatore o nel journal. Il container non riparte: `alembic-worker-inference-1` non compare neanche fra i container attivi oggi. I due restart della mattina non hanno riga di shutdown (arresto brusco). L'unico segnale di guasto è un incidente warning senza canale di consegna.
* Impatto: zero segnali dalle 16:20 in poi; il pomeriggio del 10-08 è perso per l'evidenza S4. In giornata nessun mover rialzista con news in coda è stato identificato (HD NO_NEWS, ADBE sotto gate), quindi il costo non è stimabile.
* Severità: Critical
* Confidenza: High (sull'arresto), Low (sulla causa)
* Azione consigliata: ticket di correttezza: restart policy `unless-stopped` verificata per worker-inference e alert su assenza del consumatore (F-096).
* Test/monitor consigliato: watchdog su `celery inspect ping` della coda `inference` e su queue_depth crescente con zero `sentiment_signals` in RTH.

### [DAY-002] Quota Ollama Cloud esaurita su entrambi i modelli dalle 15:21Z: 100% FinBERT, nessun alert

* Tipo: Anomalia
* Area: LLM
* Evidenza:
  * file/log/tabella: worker-inference log (84 righe `Ollama rate limit (429) … quota exhausted`); `llm_responses`; `ensemble_cycle_health`
  * timestamp: 15:21:32 primo ciclo con n_ensemble 0; ultima risposta 15:23:26
  * snippet/query: `MAX(generated_at)` glm 15:22:00, gpt-oss 15:23:26; 21 cicli 15:23–16:15 con n_ensemble = 0 e n_single = 0
* Descrizione: la quota del provider finisce in RTH. Il giro shadow off-session della mattina (10:27, 743 s, 43 item; 12:26, 676 s, 40 item) consuma la stessa quota, ma l'attribuzione non è misurabile. Il breaker del fallback non ha consumatori (F-049). Dei 3 `sendMessage` 200 del worker-inference (14:22, 15:11, 15:48) il contenuto non è loggato, quindi non è verificabile se uno fosse l'alert del breaker.
* Impatto: 43 segnali FinBERT, tutti esclusi dagli ingressi. Nessun ordine causato. Valutazione LLM persa per 57 min prima dello shutdown.
* Severità: High
* Confidenza: High
* Azione consigliata: registrare. Separare la quota shadow da quella live richiede una decisione dell'operatore (non è una taratura di strategia).
* Test/monitor consigliato: alert al primo 429 «quota exhausted» in RTH.

### [DAY-003] Il 429 viene registrato come «timeout»

* Tipo: Bug
* Area: Data
* Evidenza: `finbert_fallback_events.reason = 'FinBERT fallback (Ollama timeout)'` su 43/43 righe; log «All ensemble models timed out for SBUX» subito dopo due 429 (15:48:30)
* Descrizione: la causa reale del fallback è persa nella tabella che dovrebbe documentarla (F-086).
* Impatto: uptime ed errori del provider non misurabili dal DB.
* Severità: Medium
* Confidenza: High
* Azione consigliata: persistere `kind` (timeout/rate_limit/error) nell'evento.
* Test/monitor consigliato: test che un 429 produca reason ≠ timeout.

### [DAY-004] FinBERT su un articolo macro fan-out: −0,72 su 12 ticker, segno opposto al titolo per XLE

* Tipo: Rischio
* Area: LLM
* Evidenza: `finbert_fallback_events` 15:23:37–15:25:51, input «8 Of 11 Sectors Fall In Thursday Trading As Energy Leads», 19 ticker nell'articolo; SKIP_FALLBACK −0,720 su MRK/ORCL/WMT/XLE/XLF/XLK/XLV/XOM alle 15:37 e su QQQ alle 18:22
* Descrizione: con verdetto polarity −0,90 / conf 0,80, molto più forte dei modelli sostituiti, un articolo generico diventa un segnale forte su 12 simboli (F-087, F-012).
* Impatto: nessun ordine (fallback esclusi). Contamina IC e statistiche di segnale.
* Severità: Medium
* Confidenza: High
* Azione consigliata: registrare.
* Test/monitor consigliato: contare i segnali FinBERT con |score| ≥ 0,3 da articoli con più di 5 ticker.

### [DAY-005] SPCX chiuso da un segnale più recente e più debole (+0,275 su +0,370)

* Tipo: Anomalia
* Area: Signal
* Evidenza: sentiment_signals 14717 (14:33, +0,370) → 14719 (14:37:24, +0,275); execution_decisions 68474…69193 SKIP_THRESHOLD 0,275; 69200 SELL `below_entry_gate`; trade 1060 −24,03 $
* Descrizione: S4 usa solo l'ultimo segnale per simbolo (F-023). Un secondo articolo arrivato 4 minuti dopo l'ingresso ha portato il titolo sotto il gate, e l'uscita è scattata appena finiti hold minimum e isteresi.
* Impatto: controfattuale corto. Senza sovrascrittura, SPCX tenuto fino al close = mtm_eod −51,89 $ (dossier) contro −24,03 $ realizzati. Il difetto ha evitato 27,86 $ (costo −27,86 $).
* Severità: Medium
* Confidenza: High
* Azione consigliata: nessuna taratura in freeze; registrare.
* Test/monitor consigliato: contare le uscite causate da un segnale arrivato meno di 30 min dopo quello d'ingresso.

### [DAY-006] Alert #161 su posizioni non proteggibili rifiutati da Telegram (400)

* Tipo: Anomalia
* Area: Ops
* Evidenza: worker log 14:52:10 e 17:22:11, `TelegramNotifier: Failed to send alert: Client error '400 Bad Request'` dopo `#161: WDC unprotected at -26.3%` / `-28.4%`, `NOK unprotected at -15.0%`
* Descrizione: l'alert viene generato ma non consegnato (F-005). L'alert «held_news_loss» è stato recapitato solo alle 22:50, dopo il close.
* Impatto: perdita del punto di decisione su WDC/NOK. Costo già contato in F-036 dall'alpha-miss del giorno.
* Severità: Medium
* Confidenza: High
* Azione consigliata: correggere l'escape del messaggio (vedi #591).
* Test/monitor consigliato: contatore di sendMessage ≠ 200.

### [DAY-007] Copertura e qualità ingest

* Tipo: Anomalia
* Area: News
* Evidenza: `ingestion_stats_daily` benzinga duplicates 5.472 > fetched 974; dossier `copertura_articoli`: 38/96, TAG_UNCONFIRMED 86/160, fan-out extra 74; 40 ticker a zero righe
* Descrizione: contatore duplicates incoerente (F-007), copertura bassa (F-001), metà delle righe da fan-out (F-012).
* Impatto: metriche di ingest non interpretabili.
* Severità: Medium
* Confidenza: High
* Azione consigliata: registrare.
* Test/monitor consigliato: invariante duplicates ≤ fetched.

### [DAY-008] Decay CRITICAL senza canale; token Telegram nei log

* Tipo: Rischio
* Area: Ops
* Evidenza: worker log 21:00:00 (6 righe `DECAY CRITICAL`); 11.773 righe nel worker-inference e 5 nel worker con l'URL `api.telegram.org/bot<token>` (non riportato)
* Descrizione: F-062, F-018.
* Impatto: alert non recapitati; credenziale esposta nei file di log persistiti.
* Severità: High (token), Medium (decay)
* Confidenza: High
* Azione consigliata: ruotare il token e alzare il livello del logger httpx.
* Test/monitor consigliato: grep CI per `bot[0-9]+:`.

### [DAY-009] Entità HTML nei titoli persistiti

* Tipo: Bug
* Area: News
* Evidenza: 35 titoli `news_log` del 10-08 con `&amp;`/`&#39;`/`&quot;`/`&rsquo;`
* Descrizione: il path Benzinga persiste il grezzo (F-076). Il prompt passa da `sanitize_text`, quindi questo conteggio non misura il fix (vedi charter 2026-09-21).
* Impatto: basso per lo scoring; sporca la serie raw.
* Severità: Low
* Confidenza: High
* Azione consigliata: registrare.
* Test/monitor consigliato: verifica su `finbert_fallback_events.finbert_input` (oggi 0 entità HTML nei 43 `finbert_input` completi).

### [DAY-010] Stop protettivi parziali e tardivi su PLTR/SPCX/SAP

* Tipo: Rischio
* Area: Risk
* Evidenza: /api/orders: stop PLTR 7 su 7,97, SPCX 9 su 9,66 (14:52), SAP 7 su 7,67 (15:22), tutti 15 min dopo l'ingresso
* Descrizione: F-022.
* Impatto: un ciclo senza stop; copertura 87,8–93,2%.
* Severità: Low
* Confidenza: High
* Azione consigliata: registrare.
* Test/monitor consigliato: tempo ingresso→stop < 1 ciclo.

### [DAY-011] Divergenza d'ensemble mascherata dal filtro di eleggibilità

* Tipo: Rischio
* Area: LLM
* Evidenza: 106 righe `F-054 masked divergence` (es. NVDA 0,5657, SPCX 0,4243, GS 0,2828 con 1 eleggibile → ensemble_std 0,000)
* Descrizione: F-054. Varianza mai usata come gate (F-037).
* Impatto: nessun ordine causato oggi.
* Severità: Low
* Confidenza: High
* Azione consigliata: registrare.
* Test/monitor consigliato: contare i segnali ≥ 0,30 con std mascherata ≥ 0,3.

### [DAY-012] SELL SPCX senza signal_id; l'ordine punta alla decisione d'ingresso

* Tipo: Bug
* Area: Data
* Evidenza: execution_decisions 69200 (`signal_id` NULL); /api/orders SELL SPCX 16:22 con `decision_id = 68364` (BUY)
* Descrizione: F-011.
* Impatto: catena segnale→decisione→ordine d'uscita non ricostruibile senza log.
* Severità: Medium
* Confidenza: High
* Azione consigliata: ticket di correttezza (propagare signal_id/decision_id del SELL).
* Test/monitor consigliato: copertura signal_id = 100% per i SELL.

### [DAY-013] Primo ciclo portfolio alle 14:07: incidente `portfolio_cycle_late` critical alle 13:30

* Tipo: Ambiguità
* Area: Ops
* Evidenza: `mobile_events` 85bd4a7c (13:30:00 → 14:08:00); primo `run_portfolio_cycle` alle 14:07
* Descrizione: le finestre beat in UTC fisso ignorano l'EDT: si perdono i primi 37 min di RTH (F-021).
* Impatto: nessun segnale ≥ 0,30 prima delle 14:07 oggi (il primo, PLTR, arriva alle 14:23), quindi nessun costo.
* Severità: Low
* Confidenza: High
* Azione consigliata: registrare.
* Test/monitor consigliato: già presente (l'incidente).

## 11. Aree corrette

- Esclusione dei fallback dagli ingressi: 43 SKIP_FALLBACK, nessun ordine da FinBERT anche con 100% di fallback.
- Fail-safe in assenza di segnali: nessun ingresso né uscita guidati da dati mancanti dopo le 16:20; SKIP_STALE applicato.
- Hold minimum, isteresi e cancellazione dello stop prima del SELL hanno funzionato come documentato.
- Nessun ordine duplicato, fuori orario o senza decisione; nessun BUY ripetuto; nessun roundtrip < 30 min; SIGNAL_DUPLICATE_SKIP attivo.
- Riconciliazione ordini/trade/posizioni coerente; 24/24 cicli portfolio in RTH; snapshot senza buchi; paper coerente.
- Nessun timestamp futuro; nessun segnale senza news (160/160).

## 12. Dati mancanti

- Causa dello shutdown delle 16:20 e dei restart delle 10:36/12:56: journal host vuoto, eventi Docker non persistiti.
- Contenuto della coda dopo le 16:20 (326 item): non persistito; la coda Redis attuale è di oggi.
- Contenuto dei 3 `sendMessage` 200 del worker-inference (alert breaker o altro): non loggato.
- Latenza LLM per modello (F-086). PnL non realizzato per ticker (servono le barre daily Alpaca). Slippage (F-015).

## 13. Raccomandazioni immediate

1. Verificare oggi lo stato di `worker-inference`: non compare in `docker ps` al 2026-10-21. Il report alpha-miss del 10-21 indica ancora 0 righe `news_log`.
2. Ruotare il token Telegram e alzare il livello del logger httpx (F-018).
3. Dare un canale di consegna agli incidenti `pipeline:signal_stale` e al 429 del provider.
4. Nessuna taratura: le proposte sopra sono strumentazione e correttezza.

## 14. Test / monitor da aggiungere

- Watchdog della coda `inference`: ping del consumer, queue_depth crescente con zero segnali in RTH.
- Alert al primo 429 «quota exhausted».
- `finbert_fallback_events.reason` che distingua rate-limit da timeout.
- Invariante duplicates ≤ fetched; grep dei token nei log.

## 15. Ticket suggeriti

- Correttezza/Ops: riavvio automatico e alert per l'assenza di worker-inference (F-096).
- Correttezza: causa reale del fallback persistita (F-086).
- Correttezza: signal_id/decision_id sul SELL (F-011).
- Ops: rotazione del token e redazione dei log (F-018); canale per i CRITICAL (F-062).

## 16. Stato sistema

- Ollama: up 13:38–15:21Z; **down per quota (429) dalle 15:21Z**, poi nessun consumatore dalle 16:20Z. Downtime LLM in RTH ≈ 4h37m (15:23→20:00) su 6h30m. Timeout 90 s: 14 sull'intera giornata (8 glm, 6 gpt-oss), 84 righe 429.
- FinBERT fallback: 43/160 segnali = 26,9% (in senso stretto); fallback totale 109/160 = 68,1%. Decisioni: 43 SKIP_FALLBACK su 2.681 righe del giorno (1,6%).
- Worker restart: 10:36Z e 12:56Z (worker + worker-inference, senza riga di shutdown); warm shutdown definitivo di worker-inference alle 16:20:12Z. SoftTimeLimit: 0.
- Telegram: 2 sendMessage 400 (worker), 4 da 200; 5 `Connection reset by peer` nel polling.
