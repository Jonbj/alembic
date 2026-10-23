# Forensic daily report — 2026-10-12 (lunedì)

Analisi read-only eseguita il 2026-10-23. Timezone operativo: UTC (`celery_app.py`). DST USA in vigore (EDT), quindi RTH = 13:30–20:00 UTC. Il Columbus Day non chiude il mercato azionario (seduta regolare, confermata da 24 cicli portfolio e dai fill). Fonti: DB `trading` (solo SELECT), API REST locale, `logs/containers/{worker,beat,api}-2026-10-12.log`, `logs/deploy_reconcile_2026-10-12.log`, Redis (sola scansione chiavi), `ALPHA_MISS_REPORT_2026-10-12.md` (dossier 3.1). **Non esistono `worker-inference-2026-10-12.log` né `worker-news-stream-2026-10-12.log`.**

## 1. Executive summary

- **Seconda seduta intera senza valutazione sentiment.** `worker-inference` è assente dal warm shutdown del 2026-10-08 16:20Z e rientra solo il 10-16. Il 10-12 registra 0 righe `news_log`, 0 `sentiment_signals`, 0 `llm_responses` e 0 `finbert_fallback_events`. La coda news (`news_queue_census`) passa da 1.154 a **1.819** (oldest ~105 h). Il beat ha accodato 32 `sentiment-worker`, 15 shadow, 2 regime e 17.280 `poll-telegram-updates` su una coda senza consumatore.
- **Effetto a valle:** alle 15:22 tutti i segnali S4 superano il lookback di 96 h, che è tempo di parete e include il weekend. Il log riporta «S4: no signals in DB for last 96 hours». PLTR (14:52) e SAP (15:22) vengono vendute con `[no_signal]`, senza contro-segnale. Realizzato S4 +117,61 $, ma con un drift post-uscita di +20,31 $ lasciato sul tavolo (F-024).
- Le altre 5 posizioni S4 (WDC, CSCO, XLE, PANW, MRVL) non possono uscire per la stessa regola, perché stanno nei pesi S1 congelati («S1: rebalance gate closed — holding 39»; F-089). Lo stesso evento produce quindi esiti diversi a seconda di dove sta il peso.
- **Regime scaduto:** `regime:current` (TTL 72 h dal 10-08 13:30) manca per tutta la seduta. Il fallback deterministico vale ×0,20 con `vix=absent` su 300/300 decisioni. Nessun BUY, quindi costo nullo, ma il sizing è degradato in silenzio (F-017).
- Lo stop GTC di ARM (2 azioni) si è fillato alle 18:49:25 @253,85. Nessun `reconcile-fills-intraday` successivo lo registra (updated 0), e trade 1041 resta senza exit_time e net_pnl: una perdita realizzata di 69,38 $ fuori dal ledger (F-048, costo già nell'alpha-miss).
- Alert: 5 sendMessage Telegram → 400 (ensemble weights 04:00 ×2, #161 WDC/AMAT 14:07, NOK 16:52) e 2 → 200. `mobile_notification_deliveries` = 0. Token bot in chiaro in 12 righe di log.
- NAV paper 110.636,07 → 110.374,61 (**−261,46 $, −0,236%**) contro SPY −0,06% e QQQ −0,70%. Book all'open −248,15 $ (S1 −50,96, S4 −197,19).
- Ledger: 0 finding nuovi, 15 esistenti riconfermati.

## 2. Verdict finale

**Processo non affidabile** sulla catena news→sentiment→segnale: per la seconda seduta consecutiva il segnale non esiste. Il layer di esecuzione non ha generato ordini da dati invalidi: niente BUY su segnali stale o fallback, niente ordini fuori orario, riconciliazione EOD 39/39. Ha però prodotto due uscite S4 causate solo dall'invecchiamento dei segnali durante l'outage, e ha mancato la registrazione di uno stop fillato. La seduta va annotata come discontinuità nella serie osservata (2026-10-08 16:20Z → 2026-10-16 13:32Z); la registrazione nel charter spetta all'operatore.

## 3. Timeline (UTC)

| Ora | Componente | Evento | Fonte |
|---|---|---|---|
| 00:00 | news queue | queue_depth 1.154, oldest 82 h | news_queue_census |
| 00:00–23:59 | beat | 17.280 poll-telegram, 32 sentiment-worker, 15 shadow su `inference`, **nessun consumatore** | beat log; assenza log worker-inference |
| 00:20–20:20 | deploy reconcile | 08:20 e 14:20 «solo documentazione o test, nessun rebuild» (4346fdab→2fb95552→ec987cd5) | deploy_reconcile log |
| 03:00 / 03:30 | worker | daily report OK; retention sweep 0 righe | worker log |
| 04:00 | weight updater | «ensemble anti-predictive: mean ICIR −0,051 < −0,05 (gpt-oss 0,021, glm-5.3 −0,123) — weight update frozen»; Telegram 400 ×2 | worker log 1239-1252 |
| 07:00 / 13:30 | beat | regime-detector(-premarket) accodati su `inference`, mai eseguiti | beat log |
| 13:30 | mobile_alert | `portfolio_cycle_late` critical, rientrato 14:08 (F-021) | mobile_events |
| 13:30 | snapshot | NAV 110.644,94, 41 posizioni, gross 34,5% | portfolio_monitor_snapshots |
| 14:00–19:45 | ingest REST | alpaca: 24 run, 14 accodati; GDELT/news: 24 run, 19 accodati (quasi tutto discarded no-ticker) | worker log |
| 14:07 | portfolio-cycle | «S4: dropped 8/8 stale signals (age > 4h)»; **P0-09 regime absent → ×0,20**; CombinedOrder BUY PLTR/SAP → P0-05 skip; #161 9/41 unprotectable; Telegram 400 ×2 | worker log 3941-3966 |
| 14:52:05 | portfolio-cycle | «Cancelled 1 protective stop for PLTR»; SELL PLTR 7,9693 `[no_signal]` → fill 14:52:07 @207,125 | worker log 4276; /api/orders; trades 1059 |
| 15:22:04 | portfolio-cycle | «S4: no signals in DB for last 96 hours»; stop SAP cancellato; SELL SAP 7,6717 → fill 15:22:08 @217,15 | worker log 4466-4475; trades 1061 |
| 15:37–19:52 | portfolio-cycle | 0 ordini; S4 vuota; S1 held 39 | portfolio_cycles |
| 16:52 | #161 | WDC −29,4%, AMAT −16,0%, NOK −15,1% unprotected → Telegram 400 | worker log 5046-5051 |
| 18:49:25 | broker | stop GTC ARM 17ac2b8c (2 az., da 10-01) fillato @253,85 | /api/orders |
| 18:52 → | portfolio-cycle | #161 10/39 unprotectable (ARM ora residuo 0,0439) | worker log 5807 |
| 18:57–21:57 | reconcile-fills | `updated 0` a ogni giro: lo stop ARM non viene registrato | worker log |
| 20:00 | snapshot | NAV 110.374,61 (−261,46), 39 posizioni, cash 76.332,19 | snapshots |
| 20:07–21:52 | portfolio-cycle | «Market closed», skip | worker log |
| 21:00 | decay monitor | 3 DECAY CRITICAL (S1/S2/S4, IC −0,003), solo log | worker log 6562-6564 |
| 21:35 | reconcile-positions-eod | fully_held 39, anomalies 0 | worker log 6766 |
| 21:40 / 23:05 | Telegram | 2 sendMessage 200 (report) | worker log |
| 22:00 / 22:45 | forward/counterfactual | updated 934 / 38 (segnali precedenti) | worker log |
| 22:30 | risk-monitor | n_alerts 0, exposure 0,308, drawdown 0,0198 | worker log 7040 |
| 22:50 | held_news_loss_alert | AMAT, ARM, NOK, WDC; session_grid open_gap 37,0 min | worker log 7134; mobile_events |
| 23:05 | duplicate-signals-alert | duplicated_news_log 13, alerted 1 (storico) | worker log 7205 |
| 23:50 | news queue | 1.819, oldest ~106 h, dead_letter 0 | news_queue_census |

## 4. News ingest

| Fonte | Righe news_log | fetched / queued / duplicates / no_ticker | Note |
|---|---|---|---|
| alpaca_benzinga | **0** | 1.130 / 646 / **6.234** / 0 | duplicates 5,5× fetched (F-007); poller REST 14 accodati, il resto dal WS (log news-stream assente) |
| gdelt_gkg | **0** | 1.715 / 19 / 2 / 1.694 | 99% scartato no-ticker |
| coda (`news_queue_census`) | — | 1.154 → 1.819 (+665) | nessuna estrazione; dead_letter 0 |

Copertura effective-timely 0/96, causata dal consumatore assente e non dai provider. Per ticker: 96/96 a zero (lista in ALPHA_MISS §6). Non verificabili per assenza di righe: duplicati cross-provider, ambiguità ticker, sanitizzazione, timestamp futuri, top news per impatto. Il contenuto della coda non è persistito. Confidenza: alta sull'assenza; il contatore duplicates non è affidabile.

## 5. Performance modelli LLM

| Modello | Richieste | Successi | Errori/timeout | Invalid | Latenza | Distribuzione score |
|---|---|---|---|---|---|---|
| glm-5.3:cloud | 0 | 0 | — | — | — | — |
| gpt-oss:20b-cloud | 0 | 0 | — | — | — | — |
| FinBERT | 0 righe `finbert_fallback_events` | — | — | — | — | — |

Nessuna inferenza, quindi niente da calcolare su disaccordo, dominanza o confidence. Il weight updater delle 04:00 ha congelato i pesi per ICIR medio −0,051 (glm-5.3 −0,123), misurato su segnali precedenti: è un guard funzionante, non un evento del giorno. Verifica funzionale: gli LLM restano fuori dal trading loop (24 cicli portfolio senza di loro) e nessun output LLM del giorno è entrato in decisione.

## 6. Segnali finali per ticker

Nessun segnale generato il 10-12. Tutti gli intent S4 (282 candidati) poggiano su segnali del 10-08 con età tra 3g21h e 4g00h. Disposizioni: SKIP_FALLBACK 126, SKIP_ENTRY_FRESHNESS 124, SKIP_ENTRY_GATE 16, SKIP_STALE 10, SKIP_PYRAMIDING 6.

| Ticker | Decisioni (`execution_decisions`) | signal_id | Nota |
|---|---|---|---|
| PLTR | OBSERVE_LATE_ENTRY ×2, SKIP_PYRAMIDING (log), **SELL** 14:52 | 14701 → NULL sulla SELL | lookback 96 h superato |
| SAP | OBSERVE_LATE_ENTRY ×4, SKIP_PYRAMIDING (log ×4), **SELL** 15:22 | 14743 → NULL sulla SELL | idem |
| PANW | SKIP_THRESHOLD ×5 (score 0,005), OBSERVE ×5 | 14756 | resta a libro via peso S1 (F-089) |
| MU / META / AMD / SOXX / AAPL / … | OBSERVE_LATE_ENTRY | 14801–14811 | segnali 10-08, nessun ingresso |

Totale decisioni: 300 (OBSERVE_LATE_ENTRY 260, SHADOW_LATE_ENTRY 22, SKIP_THRESHOLD 16, SELL 2); signal_id valorizzato 298/300 (mancano le 2 SELL, F-011). regime_mult 0,2 su 300/300. Circuit breaker: nessuno attivo.

## 7. Ordini

| Decisione | Strategia | Ticker | Azione | Qty | Prezzo atteso | Fill | Stato | Broker | Rationale / risk check | Anomalie |
|---|---|---|---|---|---|---|---|---|---|---|
| 14:52:05 (dec 73225) | S4 | PLTR | SELL (close) | 7,969261 | n/d (MARKET) | 207,125173 @14:52:07 | filled | Alpaca paper | `[no_signal]` weight 0; stop protettivo cancellato prima | uscita senza contro-segnale (F-024); signal_id NULL |
| 15:22:05 (dec 73306) | S4 | SAP | SELL (close) | 7,671717 | n/d | 217,15 @15:22:08 | filled | Alpaca paper | idem | idem |
| stop del 10-01 14:22 | S1 | ARM | SELL (stop GTC 253,92) | 2 | 253,92 | 253,85 @18:49:25 | filled | Alpaca paper | stop protettivo #161 | non registrato su trades (F-048); /api/trades lo etichetta `portfolio_sell` (F-084) |

`portfolio_cycles.orders_count` somma 8 (BUY PLTR/SAP target 14:07–14:52 + 2 SELL), con 2 ordini inviati (F-014). BUY bloccati correttamente da P0-05. Nessun ordine rejected o duplicato. Ambiente: `broker_environment=paper`, `mode=paper` su 80/80 snapshot; `run-execution` legacy skip «engine=portfolio» ×32.

## 8. PnL / rendimento

| Voce | Valore |
|---|---|
| Realizzato S4 (ledger) | PLTR +47,53 (trade 1059, 96 h), SAP +70,08 (trade 1061) = **+117,61 $** |
| Realizzato S1 (non a ledger) | ARM stop 2 az.: (253,85 − 288,54) × 2 = **−69,38 $** (trade 1041 senza exit) |
| NAV prev close → 20:00 | 110.636,07 → 110.374,61 = **−261,46 $ (−0,236%)**; Alpaca equity 110.372,64 (−263,43) |
| Book detenuto all'open (dossier) | −248,15 $ (S1 −50,96; S4 −197,19); peggiori PANW −68,14, MRVL −55,07 |
| Unrealized (snapshot) | 2.537,92 (13:30) → 2.218,29 (20:00) |
| Posizioni aperte il 10-12 | nessuna |
| Costi | cost_usd modellato 0,885 (PLTR) + 0,882 (SAP); commissioni Alpaca paper 0 |
| Slippage | non misurato: `slippage_est` = `cost_usd` (F-015); ordini MARKET senza prezzo atteso persistito |
| Drift post-uscita | PLTR +14,94, SAP +5,37 (chiusura sopra il prezzo d'uscita) |
| SPY / QQQ / XLK | −0,06% / −0,70% / −1,22% |

Il NAV è sotto SPY a causa del book semis (MU, ARM, MRVL, PANW, WDC tutti tra −2,6% e −4,2%). È beta di settore, non un difetto di esecuzione.

## 9. Correttezza buy/sell

- **BUY**: nessuno. I target PLTR/SAP sono stati bloccati da P0-05 (già a libro). Nessun ingresso su segnali stale o fallback (SKIP_FALLBACK 126, FRESHNESS 124): fail-safe corretto.
- **SELL PLTR/SAP**: coerenti con la regola implementata (peso S4 = 0 quando non c'è segnale entro 96 h) ma non con l'intento. Non c'è contro-segnale, il lookback è in tempo di parete (il weekend consuma 48 h su 96) e la causa a monte è l'outage del consumatore. Il motivo `[no_signal]` è esplicito e auditabile. Holding ~96 h, P&L positivo; trade funzionalmente discutibile ma redditizio (F-024).
- **Asimmetria**: le altre 5 posizioni S4 nello stesso stato non sono uscite perché coperte dal peso S1 congelato (F-089).
- **Stop-loss**: lo stop ARM ha funzionato lato broker. Lato ledger non è registrato (F-048). 9–10 posizioni su 39–41 non sono proteggibili, perché lo stop copre solo la parte intera (F-022): WDC −29,4%, AMAT −16,0%, NOK −15,1% senza stop.
- **`exit_mechanism`**: le chiusure del giorno sono `portfolio_sell` con motivo testuale esplicito `[no_signal]`, cioè post-fix #184 osservato. Non sono state conteggiate etichette `expired`/`whipsaw` dedotte per età.
- Nessun roundtrip < 30 min, nessun BUY ripetuto, nessun ordine identico nello stesso minuto, nessun ordine fuori orario (cicli 20:07+ skip), nessun ordine con score < 0,05 (le SELL hanno score nullo per costruzione `[no_signal]`), nessuna SELL con sentiment positivo fresco (A5 non pertinente).
- NO-ORDER: 260 OBSERVE e 22 SHADOW sono osservazionali per design (#512); i CombinedOrder BUY non inviati sono P0-05.
- Idempotenza: una SELL per simbolo, stop cancellato una volta prima della SELL.
- Riconciliazione: EOD fully_held 39, anomalies 0. Coerente con 41 − 2. Il residuo ARM 0,0439 compare come posizione intera di trade 1041 con qty 2,0439: il riconciliatore non vede la discrepanza di quantità (F-048).

## 10. Anomalie

### [DAY-001] worker-inference assente per l'intera seduta: zero news scorate, coda a 1.819, nessun alert recapitato

* Tipo: Bug
* Area: Ops
* Evidenza:
  * file/log/tabella: assenza `logs/containers/worker-inference-2026-10-12.log`; `beat-2026-10-12.log`; `news_queue_census`; `news_log`; `sentiment_signals`; `llm_responses`; `finbert_fallback_events`; `mobile_notification_deliveries`
  * timestamp: 00:00–23:59; incidente `Segnali sentiment in ritardo` aperto 10-08 16:39, recovered 10-16 13:33
  * snippet/query: `count(*)` del 10-12 = 0 su news_log, sentiment_signals, llm_responses (generated_at), finbert_fallback_events; queue_depth 1.154 → 1.819, oldest ~106 h; beat: 32 sentiment-worker, 15 shadow, 17.280 poll-telegram su `inference`; deploy reconcile 08:20/14:20 senza rebuild
* Descrizione: continuazione di F-096 per la seconda seduta. L'unico incidente aperto è un warning senza consegna (0 deliveries).
* Impatto: seduta senza sentiment. META +3,38% è NO_NEWS per costruzione; 5 EXIT_RISK su segnali stantii; innesca DAY-002 e DAY-003. Costo già stimato nell'occorrenza ALPHA_MISS dello stesso giorno (74,36 $), qui non ricontato.
* Severità: Critical
* Confidenza: High
* Azione consigliata: ticket di correttezza: restart policy e watchdog del consumatore `inference` (F-096); discontinuità nel charter (operatore).
* Test/monitor consigliato: critical recapitato fuori host se in RTH queue_depth cresce e `sentiment_signals` resta a zero per più di 30 min.

### [DAY-002] Uscite S4 PLTR/SAP forzate dall'invecchiamento in tempo di parete durante l'outage

* Tipo: Rischio
* Area: Signal
* Evidenza:
  * file/log/tabella: `execution_decisions` 73225/73306; `trades` 1059/1061; worker log 4466 «S4: no signals in DB for last 96 hours»
  * timestamp: 14:52:05, 15:22:05
  * snippet/query: reason «[no_signal] Portfolio rebalance: weight 0.0% — no S4 signal found in DB»; segnali 14701/14743 del 10-08, età ~96 h di cui 48 h di weekend
* Descrizione: F-024. La chiusura non viene da un contro-segnale ma dal lookback a orologio. Con il consumatore assente, ogni posizione S4-only esce automaticamente 96 h dopo il suo ultimo segnale.
* Impatto: attribuita. Il drift post-uscita fino al close è PLTR +14,94 $ + SAP +5,37 $ = **20,31 $** (controfattuale corto: tenere fino al close del 10-12, dossier `drift_post_uscita`).
* Severità: Medium
* Confidenza: Medium
* Azione consigliata: registrare (nessuna taratura del lookback durante il freeze). Annotare le due uscite come prodotte dall'outage nella serie S4.
* Test/monitor consigliato: tag sulle SELL `[no_signal]` emesse mentre `signal_stale` è aperto.

### [DAY-003] Regime scaduto: fallback ×0,20 con VIX assente su tutta la seduta, regime-detector mai eseguito

* Tipo: Rischio
* Area: Risk
* Evidenza: worker log, 29 righe «P0-09: regime:current absent — deterministic VIX fallback ×0.20 (vix=absent)» dalle 14:07; `execution_decisions.regime_mult` 0,2 su 300/300; beat accoda `regime-detector` 13:30 e `-premarket` 07:00 su `inference`
* Descrizione: F-017. La chiave da 72 h del 10-08 13:30 è scaduta il 10-11. Il fallback è conservativo, ma il degrado non viene segnalato e la causa (task su coda morta) non è visibile.
* Impatto: nessun BUY, quindi nessun costo. In una seduta con ingressi il sizing sarebbe stato ridotto al 20% senza alert.
* Severità: Low
* Confidenza: High
* Azione consigliata: registrare.
* Test/monitor consigliato: età di `regime:current` e fonte del multiplier nello snapshot; warning se fallback attivo in RTH.

### [DAY-004] Stop GTC ARM fillato e non registrato nel ledger

* Tipo: Bug
* Area: PnL
* Evidenza: /api/orders 17ac2b8c filled 18:49:25 @253,85 qty 2; `trades` 1041 exit_time/exit_price/net_pnl NULL, qty 2,043876; reconcile-fills 18:57–21:57 `updated 0`. Al momento dell'analisi `quantity_remaining` vale 0,0439 con l'id dello stop in `exit_order_ids`, ma la data di scrittura non è ricostruibile dai log del giorno.
* Descrizione: F-048. Il realizzato S1 della seduta risulta 0 invece di −69,38 $.
* Impatto: misurata −69,38 $ fuori ledger, già contata nell'alpha-miss del giorno; qui non ricontata.
* Severità: Medium
* Confidenza: High
* Azione consigliata: correttezza: scrittura delle uscite parziali/stop su trades (F-048).
* Test/monitor consigliato: invariante giornaliera Σ fill sell broker = Σ uscite su trades per simbolo.

### [DAY-005] Posizioni S4 nei pesi S1 congelati non escono per la stessa regola che chiude PLTR/SAP

* Tipo: Rischio
* Area: Orders
* Evidenza: worker log «Strategy S1: rebalance gate closed — holding 39 position(s)»; «merged_weights=41 symbols»; trades S4 aperti 373 WDC, 830 CSCO, 922 XLE, 1001 PANW, 1005 MRVL senza SELL nonostante S4 vuota dalle 15:22
* Descrizione: F-089. Nello stesso stato (nessun segnale S4) escono solo le posizioni S4-only.
* Impatto: esposizione cieca su PANW −68,14 $ e MRVL −55,07 $ di seduta. Costo non stimabile: non c'è un controfattuale per cui uscire sarebbe stato giusto.
* Severità: Low
* Confidenza: Medium
* Azione consigliata: registrare.
* Test/monitor consigliato: conteggio posizioni S4 coperte da peso S1 per ciclo.

### [DAY-006] Alert non recapitati: 5 Telegram 400, 0 deliveries mobile, token in chiaro

* Tipo: Anomalia
* Area: Ops
* Evidenza: worker log 04:00:00 e 04:00:11 (ensemble weights / tastiera approvazione), 14:07:09 ×2 (#161 WDC −29,2%, AMAT −16,5%), 16:52:05 (NOK −15,1%), tutti 400; 2 × 200 (21:40, 23:05); `mobile_notification_deliveries` 0 righe; 12 righe con `api.telegram.org/bot<token>`
* Descrizione: F-005 e F-018. Gli alert di rischio intraday non arrivano; arrivano solo i report.
* Impatto: nessun punto di decisione in RTH sulle posizioni non protette.
* Severità: Medium
* Confidenza: High
* Azione consigliata: escape del messaggio (#591); ruotare il token e redigerlo dai log.
* Test/monitor consigliato: contatore sendMessage ≠ 200; grep CI per `bot[0-9]+:`.

### [DAY-007] Stop non piazzabili su 9–10 posizioni frazionarie

* Tipo: Rischio
* Area: Risk
* Evidenza: worker log 14:07:09 «9/41 unprotectable», 18:52 «10/39» (entra ARM); WDC qty 0,3347 a −29,4%
* Descrizione: F-022.
* Impatto: perdita senza stop su WDC/AMAT/NOK.
* Severità: Low
* Confidenza: High
* Azione consigliata: registrare.
* Test/monitor consigliato: nozionale non protetto per giorno.

### [DAY-008] Telemetria e osservabilità: duplicates > fetched, orders_count, benchmark SPY, DECAY CRITICAL, /api/trades, slippage, signal_id

* Tipo: Anomalia
* Area: Data
* Evidenza: `ingestion_stats_daily` alpaca_benzinga duplicates 6.234 contro fetched 1.130 (F-007); sum(orders_count) 8 contro 2 inviati (F-014); 84 × «SPY benchmark fetch failed: subscription does not permit querying recent SIP data» (F-016); 3 DECAY CRITICAL alle 21:00 solo log (F-062); /api/trades: 3 righe per ordine, ARM stop etichettato `portfolio_sell`, gross_pnl null, regime_mult 1,0 (F-084); trades 1059/1061 slippage_est = cost_usd (F-015); SELL con signal_id NULL 2/2 (F-011)
* Descrizione: difetti noti riosservati.
* Impatto: metriche operative non interpretabili senza incrocio.
* Severità: Low
* Confidenza: High
* Azione consigliata: registrare.
* Test/monitor consigliato: invariante duplicates ≤ fetched; orders_sent separato.

### [DAY-009] Finestra beat UTC fissa: primo ciclo 37 min dopo l'open

* Tipo: Ambiguità
* Area: Ops
* Evidenza: `mobile_events` `portfolio_cycle_late` critical 13:30 → 14:08; session_grid open_gap 37,01 min, close_gap 7,99 min
* Descrizione: F-021.
* Impatto: nessuno oggi (nessun segnale fresco).
* Severità: Low
* Confidenza: High
* Azione consigliata: registrare.
* Test/monitor consigliato: già presente.

## 11. Aree corrette

- Nessun BUY su segnali stale o fallback; P0-05 attivo.
- Stop protettivi cancellati prima di ogni SELL (PLTR, SAP): nessun rischio di short da stop orfano.
- Guard «Market closed» su ingest e cicli fuori RTH; `run-execution` legacy correttamente skip.
- Paper coerente su tutti gli snapshot; riconciliazione EOD 39/39 senza anomalie (eccetto la quantità ARM, DAY-004).
- Freeze dei pesi ensemble su ICIR anti-predittivo: guard attivo, nessuna auto-applicazione.
- signal_id presente su 298/300 decisioni.
- API: 0 errori nel log.

## 12. Dati mancanti

- Log di worker-inference e worker-news-stream del 10-12 (inesistenti); eventi Docker sulla mancata ripartenza non persistiti.
- Contenuto della coda (1.819 elementi): non persistito, quindi non si possono ricostruire le news per ticker né l'impatto potenziale.
- Stato di Ollama Cloud: nessuna chiamata, non osservabile (F-086).
- Prezzo atteso degli ordini MARKET: non persistito, quindi slippage non calcolabile. Query utile: barre 1-min Alpaca su PLTR 14:52 e SAP 15:22 contro il fill.
- Data di scrittura di `trades.quantity_remaining` per trade 1041: nessun audit trail.

## 13. Raccomandazioni immediate

1. Watchdog e restart di worker-inference (F-096), con alert critical recapitato fuori host (F-094).
2. Charter (operatore): discontinuità 2026-10-08 16:20Z → 2026-10-16 13:32Z, con le uscite PLTR/SAP del 10-12 marcate come prodotte dall'outage.
3. Correggere la registrazione degli stop fillati su trades (F-048): è un difetto di correttezza del P&L osservato.
4. Ruotare il token Telegram (F-018).
5. Nessuna taratura (lookback, soglie, fallback regime): restano fuori perimetro: la sessione opera in regime di sola osservazione (OBSERVATION_CHARTER).

## 14. Test / monitor da aggiungere

- Consumatore `inference` vivo: ping più lunghezza della lista Redis `inference`.
- RTH con zero `sentiment_signals` per più di 30 min → critical consegnato.
- Fonte e età del regime multiplier nello snapshot.
- Invariante fill broker = uscite su trades per simbolo e giorno.
- Tag delle SELL `[no_signal]` emesse durante un incidente `signal_stale` aperto.

## 15. Ticket suggeriti

- Correttezza/Ops: restart policy, watchdog e alert per worker-inference; separare regime e poller Telegram dalla coda di inferenza (decisione operatore) — F-096/F-017.
- Correttezza: le uscite parziali e i fill di stop scritti su trades e riconciliati — F-048.
- Correttezza della misura: marcare nella serie S4 le uscite generate da assenza di segnale durante un outage — F-024/F-096.
- Ops: canale per DECAY CRITICAL (F-062); redazione dei log (F-018); escape Telegram (F-005).

## 16. Stato sistema

- Ollama: **non chiamato** per l'intera giornata (consumatore assente). Downtime LLM effettivo 24 h, di cui 6h30m su 6h30m di RTH.
- FinBERT fallback: 0 eventi; fallback rate non definito (0 decisioni su segnali del giorno).
- Worker restart: worker-inference assente tutto il giorno, nessun restart. Worker principale stabile: 3.359 task ricevuti, nessun SoftTimeLimit e nessun WorkerLost. Deploy reconcile 08:20/14:20 senza rebuild.
- Telegram: 5 × 400, 2 × 200. Mobile deliveries: 0.
