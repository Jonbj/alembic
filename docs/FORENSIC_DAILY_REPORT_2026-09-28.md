# Forensic Daily Report — 2026-09-28

Sessione forense autonoma, sola lettura (eseguita il 2026-10-07). Fuso operativo **UTC** (`src/workers/celery_app.py`, `timezone="UTC"`, `enable_utc=True`): tutti i timestamp sono UTC. Seduta RTH 13:30–20:00 UTC (EDT, lunedì).
Conto **paper** verificato, non assunto: `portfolio_monitor_snapshots.broker_environment='paper'` su 87/87 istantanee del giorno (0 non-paper). `execution.engine=portfolio`.

Periodo di **sola osservazione** (`docs/evidence/OBSERVATION_CHARTER.md`, scadenza 2026-09-28 = giorno analizzato): nessuna taratura proposta; i ticket riguardano solo difetti di correttezza o strumentazione.

**Nota sul ledger.** `findings.json` conteneva già 3 occorrenze del 28/09 scritte dal ciclo alpha-miss (F-013 NVDA, F-059 COST, F-089 INTC, fonte `ALPHA_MISS_REPORT_2026-09-28.md`). Gli stessi eventi sono qui riportati con `costo_usd: null` per **non contarli due volte**; il costo resta quello dell'alpha-miss.

---

## 1. Executive summary

- Pipeline end-to-end funzionante: 250 righe news (239 Benzinga + 11 GDELT; 148 articoli unici) → 250 segnali su 62 simboli → 24 cicli portfolio (14:07–19:52) → **1 BUY e 2 SELL S4, tutti `filled`** sul conto paper, più 8 SKIP_PYRAMIDING, 2 SKIP_REVERSAL_OWNER, 51 SKIP_FALLBACK, 1 SKIP_STALE.
- Nessun ordine fuori orario, duplicato, round-trip < 30 min, pyramiding > 3, né ordine privo di rationale. Cap/stop applicati; riconciliazione ordini↔fill↔trades OK (3 fill = 3 trade).
- NAV 109.984,27 → 109.762,17 $ (snapshot 20:00): **−222,10 $, −0,20%** contro SPY **−0,74%**. Realizzato S4 (2 uscite su posizioni del 25/09): **+32,72 $ netto** (NVDA +27,98, COST +4,74). Posizione aperta il 28/09 (NVDA 1034): MTM a fine seduta −8,45 $; chiusa il 29/09 a −3,90 $ netto.
- Ollama raggiungibile tutta la seduta: **26 timeout a 90 s** (gpt-oss 14, glm-5.3 12), nessun blackout. FinBERT reale usato in **9 eventi** (6 timeout, 3 divergenza) = 3,6% dei segnali; il flag `fallback_used` è true su 125/250 (50%) per F-078 (include letture a modello singolo).
- Il percorso del denaro è corretto, ma 3 decisioni su 3 dipendono da difetti noti: **NVDA venduta 14:52 su −0,006** (F-023, articolo Anthropic che sovrascrive +0,405) e **ricomprata 18:22 a 230,18** (+1,06 $/az sopra, F-013); **COST liquidata** da lettura FinBERT fallback +0,040 (F-059); INTC S4 (−5,67%) senza uscita per F-089.
- Nuovo difetto di correttezza: **F-092** — l'approvazione pesi ensemble via Telegram (05:35) viola `weight_update_log_source_check` (`source='telegram'` non ammesso): pesi scritti in Redis ma audit non persistito.
- Segreti in chiaro nei log: bot token Telegram (17.269 righe `getUpdates`) e **api_key FRED** nell'URL dell'errore 500 del regime (F-018).
- `/api/trades` riporta NVDA 1032 con gross −6,98 $ contro +28,28 $ del ledger e COST senza P&L (F-084).

## 2. Verdict

**Anomalie significative.**

Ordini coerenti con il codice, riconciliati e solo paper; ma le decisioni del giorno poggiano su difetti non corretti (F-023, F-059, F-089, F-088-pesi), l'audit dei pesi è rotto (F-092) e i log espongono segreti (F-018). Nulla richiede di fermare il sistema; nessun difetto di correttezza *nuovo* tocca l'evidenza oltre F-092.

**Avvertenza `exit_mechanism` (#184).** I 2 SELL del 28/09 hanno `exit_mechanism` **osservato** nel testo del motivo (`fallback_filtered` COST, `below_entry_gate` NVDA): post-fix, non stima per età. `trades.exit_reason='portfolio_sell'` su entrambi è un vocabolario diverso e non va letto come meccanismo.

---

## 3. Timeline del 2026-09-28 (UTC)

| Ora | Componente | Evento | Esito | Fonte |
|---|---|---|---|---|
| 00:00–13:29 | `worker-news-stream` / sentiment | WS Benzinga 24/7; dispatch sentiment `market_closed` (~72 dispatch) | news non scorate | `worker-inference` log, F-069 |
| 05:35:33 | `telegram_poller` | Approve pesi → `CheckViolation weight_update_log_source_check` (source='telegram') | audit non scritto | `worker-inference` log, **F-092** |
| 07:00:05 | `detect_regime` | FRED VIXCLS `500 Internal Server Error`; URL con api_key in log; task `succeeded: None` | nessun alert | `worker-inference` log, F-017/F-018 |
| 13:30:01 | alert | `portfolio_cycle_late` critical + `signal_stale` warning | rientrati (prima griglia 14:07) | `mobile_events` (ricorrente, già noto) |
| 13:30 | snapshot | NAV 109.856,40 (prev close 109.984,27), 45 posizioni | paper | `portfolio_monitor_snapshots` |
| 13:34:18 | `run_sentiment_worker` | **237 news > 2h saltate senza inferenza**; primo ciclo 300 s per 8 articoli | ok | log, F-069/F-030 |
| 13:52:13 | ensemble | MCD −0,813: divergenza → FinBERT (−0,94, conf 0,86) | fallback | `finbert_fallback_events` |
| 13:58 | segnale | COST +0,040 FinBERT fallback (non in ranking, #108) | — | `sentiment_signals` |
| 14:07:04 | portfolio-cycle #1 | SKIP_PYRAMIDING ABBV (+0,338), NVDA (+0,405) | nessun ordine | `execution_decisions` 48526/48527 |
| 14:22:00 | portfolio-cycle | **SELL COST** 1,612 az @924,90 `fallback_filtered`, `signal_id` NULL | filled 14:22:07 | decisione 48626, trade 1033 |
| 14:23 | segnale | NVDA −0,006 (articolo Anthropic) sovrascrive +0,405 | — | F-023 |
| 14:52:00 | portfolio-cycle | **SELL NVDA** 6,606 az @229,123 `below_entry_gate`, `signal_id` NULL; stop protettivo annullato prima | filled 14:52:06 | decisione 48841, trade 1032 |
| 14:52, 15:52 | portfolio-cycle | SKIP_REVERSAL_OWNER SPY (−0,366), SNOW (−0,378): posizioni S1 | nessun ordine | #182 |
| 17:22–18:07 | portfolio-cycle | SKIP_PYRAMIDING XLE, PANW, ABBV, XLE | nessun ordine | decisioni 49903/50015/50240/50241 |
| 17:52 | portfolio-cycle | SKIP_STALE AMAT (4,1h > 4h) | nessun ordine | decisione 50091 |
| 18:12:51 | segnale | NVDA +0,405 (buyback record), ensemble non-fallback | — | segnale 13053 |
| 18:22:00 | portfolio-cycle | **BUY NVDA** 6,3995 az @230,18, velocity ×1,20 → gate 0,486, peso 2,0% | filled 18:22:04 | decisione 50352, trade 1034 |
| 18:37:04 | portfolio-cycle / stop sync | `SIGNAL_DUPLICATE_SKIP` 13053; stop frazionario creato 18:37:05 (sell qty 6, 93,8%) | stop 15 min dopo il fill | log, F-022 |
| 18:52–19:37 | portfolio-cycle | SKIP_PYRAMIDING NVDA (posizione aperta) | nessun ordine | P0-05 |
| 19:52:01 | portfolio-cycle #24 | ultimo ciclo con ordini-target; 20:07+ `skipped` | — | `portfolio_cycles` |
| 20:00 | snapshot | NAV 109.762,17 (−222,10), 44 posizioni, unrealized 1.527,98 | paper | `portfolio_monitor_snapshots` |
| 21:00 | decay monitor | DECAY CRITICAL S1/S2/S4 (Sharpe −7,x, IC −) solo `log.critical` | nessun canale | log, F-062 |
| 22:50 | alert | "Griglia portfolio-cycle fuori seduta" + copertura assente CSCO/NOK/VALE | recovered | `mobile_events` |
| 23:40 | `ingestion_stats_daily` | chiusura contatori giornalieri | — | tabella |

Restart worker: **nessuno** rilevato nei log del 28/09 (nessun Warm/Cold shutdown, nessun WorkerLost).

## 4. Tabella news ingest

| Fonte | fetched | queued | duplicati | scartate no-ticker | scartate stale | righe in `news_log` | URL unici | ticker | primo/ultimo | lag mediano |
|---|---|---|---|---|---|---|---|---|---|---|
| alpaca_benzinga | 1.004 | 544 | 4.734 | 0 | 237 | 239 | 138 | 60 | 13:34 / 19:57 | 8,4 min (max 1,94 h) |
| gdelt_gkg | 1.746 | 11 | 2 | 1.733 | 0 | 11 | 11 | 9 | 14:28 / 19:18 | 4,2 min (max 0,47 h) |

- Trasporto Benzinga: 235 `ws`, 4 `rest`. 0 `discarded_reason`, 0 `published_at` futuro, 0 body mancanti, 0 parse_fail.
- `duplicates` (4.734) > `fetched` (1.004) per `alpaca_benzinga`: artefatto contabile noto (F-007), non perdita di dati.
- Duplicati: 37 gruppi `content_hash` ripetuti (139 righe) = fan-out multi-ticker, non duplicati reali; **0** coppie `(news_log_id, symbol)` con più segnali.
- Copertura effective-timely (dossier): 49/96 ticker (51,0%); 121 mapping ISSUER_SPECIFIC vs 129 TAG_UNCONFIRMED su 250 (fan-out extra 102).
- Distribuzione oraria (righe): 13h 30 · 14h 61 · 15h 43 · 16h 19 · 17h 58 · 18h 21 · 19h 18. Buco 16:00–16:59 e 18:00-19:00 (19/21 righe): flusso Benzinga reale basso, non failure (0 errori fonte).
- Titoli con entità HTML grezze (`Fed&#39;s`, `Iran&#39;s`) nel titolo salvato in `news_log`: cosa riceve il modello non è verificabile da qui (F-076 già aperto).

Top news per impatto sul segnale: MCD −0,813 (FinBERT, "Is This the Bottom for McDonalds?"), ASML +0,560 (fallback, "Nvidia's AI Boom … Dutch Company"), BRK.B −0,490 (fallback), PANW +0,422 (non-fallback, BTIG), NVDA +0,405 (buyback, ×2: 12850 alle 13:44 e 13053 alle 18:12), XLE +0,408 (Hormuz).

Confidenza analisi ingest: **alta** (tabelle dirette), salvo il contenuto effettivo inviato al modello.

## 5. Tabella performance modelli LLM

| Modello | risposte | pol. media | conf. media | score medio | pol>0,3 / <−0,3 / neutra | timeout 90 s | `eligible=false` |
|---|---|---|---|---|---|---|---|
| glm-5.3:cloud | 238 | −0,017 | 0,336 (0,1–0,7) | −0,008 | 19 / 29 / 190 | 12 | 169 (71%) |
| gpt-oss:20b-cloud | 238 | −0,059 | 0,479 (0,2–0,8) | −0,031 | 20 / 42 / 176 | 14 | 169 (71%) |
| FinBERT (fallback reale) | 9 eventi | — | — | — | 6 timeout Ollama, 3 divergenza | — | — |

- Latenza media: **non misurabile** (nessuna traccia di trasporto, F-086).
- Distribuzione timeout per ora: 14h 8, 15h 5, 17h 5, 19h 5, altre 3 (11h, 13h, 22h). Nessun periodo continuo → nessun blackout Ollama (0 h di downtime).
- Accordo tra modelli su 232 coppie: 18 di segno opposto, 3 con |Δpol| ≥ 0,8; nessuna con |Δpol| ≥ 1,0. Ensemble_std > 0,3 su 7 segnali.
- `eligible=false` 71% = mislabel noto (F-010: retry a floor 0 non propagato), non rifiuto reale.
- Pesi ensemble effettivi: vedi F-088/F-092 (approvazione 05:35 non auditata).
- Fallback FinBERT: `fallback_used=true` su **125/250 (50%)**, ma solo 9 eventi in `finbert_fallback_events` e 6 segnali fallback senza risposta LLM; il resto sono letture a modello singolo etichettate fallback (F-078). Fallback "su tutti i simboli in un periodo": **no**.
- Segnali sopra gate 0,30: 28, di cui 12 fallback (esclusi dal ranking S4, #108).
- Validazione: output strutturato salvato senza validazione enum (F-055); varianza alta non è gate d'ingresso (F-037) ma rimanda a FinBERT oltre soglia (3 casi MCD/F/GM, F-087). LLM solo background (worker-inference), mai nel loop di trading: confermato.
- Hallucination: nessun caso di evento inventato rilevato oggi (cfr. F-091 del 25/09 su GDELT).

## 6. Tabella segnali finali per ticker (selezione, sopra gate o con decisione)

| Ticker | Segnale (id, ora) | Score | Fallback | Decisione |
|---|---|---|---|---|
| NVDA | 12850 13:44 | +0,405 | no | SKIP_PYRAMIDING 14:07 (posizione S4 aperta dal 25/09) |
| NVDA | 12888 14:23 | −0,006 | — | **SELL 14:52** below_entry_gate (F-023) |
| NVDA | 13053 18:12 | +0,405 (×1,20 → 0,486) | no | **BUY 18:22**; SKIP_PYRAMIDING 18:52 |
| COST | 12866 13:58 | +0,040 | sì (FinBERT) | **SELL 14:22** fallback_filtered |
| ABBV | 12841 / 13043 | +0,338 / +0,354 | no | SKIP_PYRAMIDING (a libro dal 06/08, $764 vs target $2.960) |
| XOM | 12878 | +0,337 | no | SKIP_PYRAMIDING (dal 13/07) |
| XLE | 12996 / 13046 | +0,408 / +0,304 | no | SKIP_PYRAMIDING ×2 (dal 31/08) |
| PANW | 13019 | +0,422 | no | SKIP_PYRAMIDING (dal 14/09) |
| SPY | 12922 / 13021 | −0,366 / −0,420 | sì (13021) | SKIP_REVERSAL_OWNER (S1) |
| SNOW | 12967 | −0,378 | — | SKIP_REVERSAL_OWNER (S1) |
| AMAT | 12853 | −0,219 | — | SKIP_STALE 17:52 (4,1h) |
| MCD | 12859 / 13063 | −0,813 / −0,420 | sì | nessun ordine; 13063 da articolo su Alphabet (fan-out) |
| ASML | 12964 | +0,560 | sì | nessun ordine (fallback escluso) |
| BRK.B | 12913 | −0,490 | sì | nessun ordine |

Totali decisioni: OBSERVE_LATE_ENTRY 1.559 · SKIP_THRESHOLD 726 · SHADOW_LATE_ENTRY 206 · SKIP_FALLBACK 51 · SKIP_PYRAMIDING 8 · SKIP_REVERSAL_OWNER 2 · SKIP_STALE 1 · SELL 2 · BUY 1 (791 righe nel dossier; 2 senza `signal_id` = i SELL).

## 7. Tabella ordini generati/eseguiti

| Ora decisione | Strategia | Ticker | Azione | Qty | Prezzo atteso | Fill | Stato | Rationale / segnale | Risk check | Anomalie |
|---|---|---|---|---|---|---|---|---|---|---|
| 14:22:00 | S4 | COST | SELL | 1,612325 | `decision_price` non registrato | 924,90 (14:22:07) | filled | `[fallback_filtered]` FinBERT +0,040, peso 0% (dec. 48626) | cap/ranking #108 | `signal_id` NULL (F-011); uscita su lettura fallback (F-059) |
| 14:52:00 | S4 | NVDA | SELL | 6,606414 | non registrato | 229,123027 (14:52:06) | filled | `[below_entry_gate]` −0,006 (dec. 48841); stop annullato prima | gate attivo 0,30 | `signal_id` NULL (F-011); sovrascrittura (F-023) |
| 18:22:00 | S4 | NVDA | BUY | 6,399513 (≈$1.473) | non registrato | 230,18 (18:22:04) | filled | sentiment +0,405 × velocity 1,20 → 0,486; peso 2,0% (dec. 50352, segnale 13053) | gate, velocity, regime_mult, P0-05 | ricompra +1,06 $/az sopra la vendita (F-013) |
| 18:37:05 | stop sync | NVDA | stop SELL | 6 | — | — | canceled (poi, prima della SELL del 29/09) | stop frazionario creato 15 min dopo il fill | — | copre 93,8% (F-022) |

Nessun ordine duplicato, identico nello stesso minuto, o contrario nello stesso intervallo senza rationale (NVDA SELL 14:52 / BUY 18:22 distano 3h30). `portfolio_cycles.orders_count` somma 88 su 24 cicli ma gli ordini reali sono 3 (F-014).

## 8. Tabella PnL/rendimento

| Voce | Valore | Nota |
|---|---|---|
| NAV 13:30 → 20:00 | 109.856,40 → 109.762,17 | prev close 109.984,27 |
| Variazione giornata | **−222,10 $ (−0,20%)** | SPY −0,74%, QQQ −1,07% (SIP daily) |
| Realizzato S4 | **+32,72 $ netto** (+33,84 lordo, costi 1,12) | trade 1032 NVDA +27,98; 1033 COST +4,74 |
| Realizzato su posizioni aperte prima del 28/09 | +32,72 $ | entrambi i trade del 25/09 |
| Realizzato su posizioni aperte il 28/09 | 0 | NVDA 1034 ancora aperta a fine seduta |
| Non realizzato NVDA 1034 | −8,45 $ (MTM EOD, dossier) | chiusa 29/09 14:22 a 229,6169: −3,90 $ netto (trade 1034) |
| Slippage | **non misurabile**: `slippage_est == cost_usd` (0,299 / 0,818 / 0,296) | F-015 |
| Commissioni/costi | cost_usd 0,30 + 0,82 + 0,30 | modello di costo, non fill reali |
| PnL per strategia | S4 sopra; S1/legacy: non separabile dal solo NAV | query: `trades` per `stop_strategy` + `positions` snapshot |

Il resto della variazione NAV (−222 $) viene da ~44 posizioni S1/legacy e S4 residue in una seduta di beta negativo (META −4,8%, QCOM −7,2%, ARM −8,7%, INTC −5,7%): beta di mercato, non difetto. La scomposizione per strategia dell'MTM non è disponibile oggi (richiederebbe `positions` con `origin_strategy` a open/close). `/api/trades` non è affidabile per questo scopo (F-084).

## 9. Analisi correttezza buy/sell

- **BUY NVDA 18:22**: segnale non-fallback 0,405 sopra gate, nessuna posizione aperta (la precedente chiusa 14:52), peso 2,0%, `regime_mult` applicato. Coerente. Il BUY ricompra però lo stesso titolo già venduto per effetto di F-023, con perdita di prezzo di ~6,8 $ (già in F-013).
- **SELL NVDA 14:52**: `below_entry_gate` formalmente corretto (−0,006 < 0,30), ma poggia su un articolo macro/ticker non pertinente che sovrascrive il segnale forte (F-023/F-012). Corretto per codice, sbagliato per prodotto.
- **SELL COST 14:22**: segnale FinBERT +0,040 escluso dal ranking → peso 0% → vendita. Pattern A5 tecnicamente presente (SELL con sentimento positivo) ma di natura nota (F-059), non bug nuovo.
- Stop-loss: stop annullato prima di ogni SELL (log 14:52:04 "Cancelled 1 protective stop(s) for NVDA before SELL"); nuovo stop su BUY creato 15 min dopo e solo su 6/6,3995 az (F-022).
- Signal flip / banda di rebalance / max holding: nessun caso attivato oggi. Ore di tenuta: COST 68,5 h, NVDA 70,0 h (il 25/09→28/09 copre il weekend).
- Idempotenza: `SIGNAL_DUPLICATE_SKIP` su segnale 13053 alle 18:37 e P0-05 su 18:52–19:37 → nessun doppio ordine; zero retry Celery anomali.
- Nessun trade con dati stale (SKIP_STALE AMAT corretto a 4,1h), nessun trade con LLM output non valido, nessun ordine su ticker non in watchlist, nessun ordine fuori orario, nessun circuit breaker attivo.
- Paper/live: coerente (paper su 87/87 snapshot).
- Riconciliazione: 3 fill broker ↔ 3 trade ↔ 3 decisioni; **2 SELL senza signal_id** (F-011) rompono la catena segnale→decisione.
- Pattern specifici: round-trip < 30 min: nessuno · BUY ripetuto > 3: nessuno · NO-ORDER (decisione senza ordine per BUY/SELL): nessuno · score < 0,05 con ordine: la colonna `score` (peso) vale 0,020/0,000 ma `signal_score`=0,405 (F-073, non è un segnale debole) · ordini identici nello stesso minuto: nessuno.

## 10. Anomalie trovate

### [DAY-001] NVDA venduta su −0,006 e ricomprata 3h30 dopo a prezzo più alto

* Tipo: Anomalia
* Area: Signal
* Evidenza:
  * file/log/tabella: `execution_decisions` 48841 (SELL) e 50352 (BUY); `trades` 1032/1034; API `/api/orders`
  * timestamp: 14:23 segnale −0,006; 14:52:00 SELL @229,123; 18:22:00 BUY @230,18
  * snippet/query: `SELECT id,tick_time,decision,reason FROM execution_decisions WHERE symbol='NVDA' AND tick_time::date='2026-09-28'`
* Descrizione: il segnale +0,405 (buyback) delle 13:44 è sovrascritto alle 14:23 da un articolo su Anthropic con −0,006; S4 legge solo l'ultimo segnale e vende. Alle 18:12 un secondo articolo sul buyback riporta +0,405 e S4 ricompra.
* Impatto: round-trip inutile: 1,06 $/az × 6,4 = ~6,8 $ di prezzo + costi (già conteggiato in F-013 dall'alpha-miss).
* Severità: Medium
* Confidenza: High
* Azione consigliata: nessuna taratura (freeze); mantenere la registrazione nei finding F-023/F-013.
* Test/monitor consigliato: contatore giornaliero SELL→BUY sullo stesso simbolo con intervallo < 6h.

### [DAY-002] COST liquidata da una lettura FinBERT fallback positiva (+0,040)

* Tipo: Anomalia
* Area: Signal
* Evidenza:
  * file/log/tabella: `execution_decisions` 48626 (`[fallback_filtered]`), `sentiment_signals` 12866
  * timestamp: 13:58 segnale; 14:22:00 SELL @924,90
  * snippet/query: `SELECT reason FROM execution_decisions WHERE id=48626`
* Descrizione: un segnale fallback positivo, escluso dal ranking (#108), azzera il peso target e produce una vendita. Pattern A5 (SELL con sentimento positivo).
* Impatto: uscita non motivata da un segnale ribassista; drift post-uscita −3,19 $ già contato da alpha-miss (F-059).
* Severità: Medium
* Confidenza: High
* Azione consigliata: registrare nel finding esistente.
* Test/monitor consigliato: allarme su SELL con `exit_mechanism='fallback_filtered'`.

### [DAY-003] Entrambi i SELL con `signal_id` NULL

* Tipo: Anomalia
* Area: Data
* Evidenza:
  * file/log/tabella: dossier `decision_signal_id_coverage` (SELL: 0/2 con signal_id, `must_be_full`)
  * timestamp: 14:22 e 14:52
  * snippet/query: `SELECT id,signal_id FROM execution_decisions WHERE decision='SELL' AND tick_time::date='2026-09-28'`
* Descrizione: la catena segnale→decisione è interrotta sulle uscite; il segnale causante si ricostruisce solo dal testo del motivo.
* Impatto: auditabilità ridotta, joins errati per le analisi.
* Severità: Medium
* Confidenza: High
* Azione consigliata: ticket di correttezza (F-011 già aperto).
* Test/monitor consigliato: check giornaliero sulla copertura signal_id per decisione.

### [DAY-004] `/api/trades` riporta P&L sbagliato per i trade chiusi

* Tipo: Bug
* Area: PnL
* Evidenza:
  * file/log/tabella: `/api/trades?limit=200` vs `trades`
  * timestamp: exit 14:52:06 / 14:22:07
  * snippet/query: API NVDA 1032 `gross_pnl=-6,9828`, `net_pnl=-6,9828`; DB `gross_pnl=+28,2815`, `net_pnl=+27,9826`; COST gross/net `null` (DB +5,56/+4,74)
* Descrizione: l'endpoint espone una riga per ordine broker, non il ledger dei trade (F-084).
* Impatto: ogni consumatore dell'API legge un P&L del giorno sbagliato (segno compreso).
* Severità: High
* Confidenza: High
* Azione consigliata: ticket di correttezza (F-084 già aperto).
* Test/monitor consigliato: test di riconciliazione somma P&L API = somma `trades.net_pnl`.

### [DAY-005] `fallback_used` vero su 125/250 segnali, FinBERT reale solo 9 volte

* Tipo: Anomalia
* Area: LLM
* Evidenza:
  * file/log/tabella: `sentiment_signals.fallback_used`, `finbert_fallback_events`
  * timestamp: intera seduta
  * snippet/query: `SELECT count(*) FILTER (WHERE fallback_used) FROM sentiment_signals WHERE generated_at::date='2026-09-28'` → 125; eventi = 9
* Descrizione: il flag include letture a modello singolo; i contatori e il filtro #108 trattano come FinBERT segnali che non lo sono (F-078).
* Impatto: la metrica "fallback rate" e il ranking S4 sono distorti (12 segnali sopra gate esclusi).
* Severità: Medium
* Confidenza: High
* Azione consigliata: ticket di correttezza (F-078 già aperto).
* Test/monitor consigliato: assert `fallback_used` ⇒ riga in `finbert_fallback_events`.

### [DAY-006] Segreti in chiaro nei log (bot token Telegram, api_key FRED)

* Tipo: Rischio
* Area: Ops
* Evidenza:
  * file/log/tabella: `logs/containers/worker-inference-2026-09-28.log` (17.269 righe `getUpdates` con il token), `worker-2026-09-28.log` 07:00:05 (URL FRED con `api_key=`)
  * timestamp: continuo; 07:00:05
  * snippet/query: `grep -a -c 'api.telegram.org/bot' …` ; `grep -a 'api_key=' …`
* Descrizione: httpx a livello INFO logga URL completi; oggi anche la chiave FRED esce nel messaggio d'errore 500.
* Impatto: esposizione di credenziali nei log persistenti sull'host.
* Severità: High
* Confidenza: High
* Azione consigliata: ruotare token e chiave; redigere gli URL nel logger.
* Test/monitor consigliato: scansione dei log per `bot\d+:` e `api_key=`.

### [DAY-007] L'approvazione dei pesi via Telegram viola `weight_update_log_source_check`

* Tipo: Bug
* Area: LLM
* Evidenza:
  * file/log/tabella: `worker-inference-2026-09-28.log` 05:35:33; `src/workers/telegram_poller.py:424-432,505`; `migrations/003_extend_source_check.sql` (ammessi: suggestion, override, expired, auto_apply, freeze)
  * timestamp: 05:35:33
  * snippet/query: `CheckViolation … weight_update_log_source_check … Failing row contains (23, …, telegram, …)`
* Descrizione: il codice scrive `source='telegram'` (e `rejected_via_telegram`) ma il vincolo non li ammette. I pesi sono applicati su Redis (riga 424) prima che l'INSERT di audit fallisca (riga 432). Il fallimento è solo loggato.
* Impatto: pesi ensemble cambiati da un operatore senza traccia di audit; ogni futura approvazione/rifiuto Telegram fallisce allo stesso modo. Tocca la correttezza dell'evidenza (quali pesi hanno prodotto quali segnali).
* Severità: High
* Confidenza: High
* Azione consigliata: ticket di correttezza (migrazione del vincolo o allineamento del codice) e verifica manuale dei pesi correnti.
* Test/monitor consigliato: test di integrazione che esegue tutti i `source` usati nel codice contro lo schema reale.

### [DAY-008] Ollama: 26 timeout a 90 s senza traccia di trasporto

* Tipo: Anomalia
* Area: LLM
* Evidenza:
  * file/log/tabella: `worker-inference-2026-09-28.log` ("ensemble model failed … Ollama timeout (90s)"), `finbert_fallback_events`
  * timestamp: 11h–22h (picchi 14h, 15h, 17h, 19h)
  * snippet/query: gpt-oss 14, glm-5.3 12; 6 fallback "Ollama timeout"
* Descrizione: nessun blackout, ma i timeout non sono misurabili come tasso né latenza: i log sono l'unica traccia.
* Impatto: tasso di errore e uptime Ollama non ricostruibili; 6 segnali scorati da FinBERT.
* Severità: Low
* Confidenza: Medium
* Azione consigliata: registrare nel finding esistente (F-086).
* Test/monitor consigliato: tabella di trasporto con esito/latenza per chiamata.

### [DAY-009] 237 articoli notturni saltati come stale alla prima esecuzione

* Tipo: Anomalia
* Area: News
* Evidenza:
  * file/log/tabella: `worker-inference-2026-09-28.log` 13:34:18; `ingestion_stats_daily.discarded_stale=237`
  * timestamp: 13:34:18
  * snippet/query: "Skipped 237 stale news items (> 2h old) without inference"
* Descrizione: il dispatch sentiment è `market_closed` tutta la notte; al primo ciclo utile le news accumulate vengono scartate per età. Il primo ciclo ha impiegato 300 s per 8 articoli.
* Impatto: copertura pre-apertura nulla; segnali disponibili solo dopo il movimento (F-030).
* Severità: Medium
* Confidenza: High
* Azione consigliata: nessuna taratura; registrare in F-069.
* Test/monitor consigliato: conteggio giornaliero news scartate stale al primo ciclo vs mover del gap.

### [DAY-010] Segnali ticker-specifici da articoli fan-out/macro (MCD, SPY)

* Tipo: Anomalia
* Area: News
* Evidenza:
  * file/log/tabella: `sentiment_signals` 13063, 13021 + `news_log`
  * timestamp: 18:47:54 · 17:34:41
  * snippet/query: MCD −0,420 da "Alphabet To Rally More Than 16%? …"; SPY −0,420 da "Fed's Cook Says Productivity Gains From AI …"
* Descrizione: titoli su altro soggetto producono un segnale su un ticker senza pertinenza; 129/250 mapping sono TAG_UNCONFIRMED.
* Impatto: oggi nessun ordine derivato, ma inquinano la serie del segnale più recente per simbolo.
* Severità: Low
* Confidenza: High
* Azione consigliata: registrare in F-012.
* Test/monitor consigliato: quota giornaliera segnali da mapping non ISSUER_SPECIFIC.

### [DAY-011] SKIP_PYRAMIDING su 4 simboli con segnale rialzista sopra gate

* Tipo: Anomalia
* Area: Orders
* Evidenza:
  * file/log/tabella: `execution_decisions` 48526, 48627, 49903, 50015, 50240, 50241
  * timestamp: 14:07–18:07
  * snippet/query: ABBV (+0,338/+0,354, $764 vs target $2.960), XOM (+0,337), XLE (+0,408/+0,304), PANW (+0,422)
* Descrizione: il guard anti-pyramiding blocca gli ingressi S4 su simboli già detenuti da S1/legacy; il segnale non porta mai esposizione S4.
* Impatto: esposizione S4 sotto il target di design; evidenza S4 non confrontabile.
* Severità: Medium
* Confidenza: High
* Azione consigliata: registrare in F-031.
* Test/monitor consigliato: contare SKIP_PYRAMIDING con signal_score > gate e esposizione/target < 50%.

### [DAY-012] Stop protettivo creato 15 min dopo il fill e su 6 az su 6,3995

* Tipo: Anomalia
* Area: Risk
* Evidenza:
  * file/log/tabella: `/api/orders` (sell qty 6 submitted 18:37:05, canceled); worker log 18:37:05 "Fractional protective stop sync: created 1"
  * timestamp: BUY 18:22:04 → stop 18:37:05
  * snippet/query: qty 6 vs 6,399513
* Descrizione: nessuno stop tra 18:22 e 18:37 e residuo frazionario di 0,3995 az (~92 $) mai coperto.
* Impatto: esposizione senza protezione 15 min; copertura 93,8%.
* Severità: Low
* Confidenza: High
* Azione consigliata: registrare in F-022.
* Test/monitor consigliato: verifica copertura stop = qty entro 1 ciclo dal fill.

### [DAY-013] Rilevazione regime: FRED 500 e task `succeeded`

* Tipo: Anomalia
* Area: Ops
* Evidenza:
  * file/log/tabella: `worker-2026-09-28.log` 07:00:05
  * timestamp: 07:00:05
  * snippet/query: "Failed to fetch macro data for regime detection: Server error '500 Internal Server Error'" poi "succeeded in 5.4s: None"
* Descrizione: il guasto è assorbito, nessun alert; il `regime_mult` del giorno non è tracciabile alla sua fonte.
* Impatto: dimensionamento del BUY NVDA dipende da un regime potenzialmente stantio.
* Severità: Medium
* Confidenza: Medium
* Azione consigliata: registrare in F-017.
* Test/monitor consigliato: alert se `detect_regime` restituisce None.

### [DAY-014] `slippage_est` copia di `cost_usd` su tutti i trade del giorno

* Tipo: Anomalia
* Area: PnL
* Evidenza:
  * file/log/tabella: `trades` 1032/1033/1034
  * timestamp: —
  * snippet/query: slippage_est = cost_usd (0,2989 / 0,8177 / 0,2955)
* Descrizione: nessuna qualità di esecuzione misurata (anche `decision_price` NULL).
* Impatto: slippage reale non stimabile.
* Severità: Low
* Confidenza: High
* Azione consigliata: registrare in F-015.
* Test/monitor consigliato: assert slippage_est ≠ cost_usd.

### [DAY-015] `llm_responses.eligible=false` sul 71% delle risposte

* Tipo: Anomalia
* Area: LLM
* Evidenza:
  * file/log/tabella: `llm_responses`
  * timestamp: intera seduta
  * snippet/query: 169/238 per ciascun modello
* Descrizione: il flag è mislabellato (retry a floor 0, F-010); la quota non indica rifiuti reali.
* Impatto: ogni analisi di eleggibilità dai dati grezzi è sbagliata.
* Severità: Medium
* Confidenza: Medium
* Azione consigliata: registrare in F-010.
* Test/monitor consigliato: confronto `eligible` con motivo di scarto nel worker.

### [DAY-016] DECAY CRITICAL su S1/S2/S4 senza alcun canale

* Tipo: Rischio
* Area: Ops
* Evidenza:
  * file/log/tabella: `worker-2026-09-28.log` (21:00): 7 righe CRITICAL (S1 IC/Sharpe, S2 IC/Sharpe/drawdown +6,3 pp, S4 IC/Sharpe −7,x); `mobile_events` senza voce decay
  * timestamp: 21:00
  * snippet/query: "DECAY CRITICAL [S4]: Sharpe below N% of baseline: -7.N vs 0.N"
* Descrizione: gli allarmi restano solo nel log; metriche pipeline-globali contro baseline per strategia (F-004).
* Impatto: allarmi non azionabili e probabilmente spuri.
* Severità: Low
* Confidenza: High
* Azione consigliata: registrare in F-062.
* Test/monitor consigliato: ogni CRITICAL deve produrre un mobile_event.

### [DAY-017] INTC S4 (−5,67%) senza uscita di regola S4

* Tipo: Anomalia
* Area: Signal
* Evidenza:
  * file/log/tabella: trade 1007; segnale 12988 −0,184 non-fallback delle 16:56 (da ALPHA_MISS_REPORT_2026-09-28 §8)
  * timestamp: 16:56
  * snippet/query: posizione S4 nei pesi target congelati di S1
* Descrizione: l'uscita S4 non può scattare (F-089). Costo −9,44 $ già contato dall'alpha-miss.
* Impatto: posizione mantenuta contro segnale ribassista fresco.
* Severità: Medium
* Confidenza: Medium
* Azione consigliata: registrare in F-089.
* Test/monitor consigliato: contare posizioni S4 con segnale fresco < −gate e nessuna SELL.

## 11. False positive o aree risultate corrette

- Nessun ordine fuori orario, duplicato, round-trip < 30 min, pyramiding, o su ticker non consentito.
- Nessun segnale futuro; 0 `discarded_reason`; 0 `parse_fail`; nessun segnale duplicato per `(news_log_id, symbol)`.
- 37 gruppi `content_hash` duplicati = fan-out multi-ticker legittimo, non doppio peso.
- `duplicates > fetched` Benzinga = artefatto contabile (F-007).
- SKIP_STALE AMAT a 4,1h: guard corretto. SKIP_REVERSAL_OWNER SPY/SNOW: precedenza #182 rispettata.
- `portfolio_cycle_late` 13:30:01 recovered 14:08: ricorrente, già noto, nessun ordine mancante.
- Il realizzato positivo (+32,72 $) non rende le due uscite funzionalmente giuste (DAY-001/002).

## 12. Dati mancanti o non accessibili

- Latenza per modello: non tracciata (F-086).
- `decision_price` NULL: slippage reale non calcolabile; query: `SELECT decision_price FROM execution_decisions WHERE order_id IS NOT NULL`.
- P&L per strategia delle ~44 posizioni S1/legacy: richiede snapshot posizioni per `origin_strategy`.
- NAV a chiusura ufficiale (20:00 snapshot usato); NAV a fine after-hours non disponibile.
- Contenuto esatto inviato al modello (sanificazione HTML, F-076): non verificabile da DB.
- Pesi ensemble effettivi dopo il tentativo di approvazione 05:35: da leggere da Redis `ensemble:weights:current` (non interrogato).

## 13. Raccomandazioni immediate

1. Verificare i pesi ensemble in Redis e correggere il vincolo `weight_update_log_source_check` (DAY-007).
2. Ruotare bot token Telegram e chiave FRED e redigere gli URL nei log httpx (DAY-006).
3. Correggere `/api/trades` perché legga il ledger dei trade (DAY-004).
4. Non usare `fallback_used` come metrica di FinBERT finché F-078 non è chiuso.

## 14. Test o monitor da aggiungere

- Test di integrazione: ogni valore `source` scritto nel codice è ammesso dal CHECK.
- Scansione log per credenziali (`bot\d+:`, `api_key=`).
- Riconciliazione somma `net_pnl` API vs DB; copertura `signal_id` per decisione.
- Alert su `detect_regime` che ritorna None; ogni CRITICAL decay → mobile_event.

## 15. Ticket tecnici suggeriti

| Ticket | Tipo | Finding |
|---|---|---|
| Estendere `weight_update_log_source_check` (o allineare il codice) e rendere fatale la mancata scrittura dell'audit dopo `set_ensemble_weights` | correttezza | F-092 |
| Redazione segreti nel logger httpx; rotazione token/chiavi | sicurezza | F-018 |
| `/api/trades` = ledger `trades` | correttezza | F-084 |
| `signal_id` obbligatorio sulle uscite S4 | correttezza | F-011 |
| `fallback_used` = solo FinBERT reale | correttezza | F-078 |

Nessun ticket di taratura (charter).

## 16. Stato sistema

- **Ollama**: up tutta la seduta; 0 h di downtime; 26 timeout isolati (gpt-oss 14, glm-5.3 12).
- **FinBERT fallback rate**: reale 9/250 segnali = **3,6%** (6 timeout, 3 divergenza); dichiarato dal flag 125/250 = 50% (F-078).
- **Worker restart**: nessuno nei log del 28/09.
- Errori log: worker 7 ERROR, worker-inference 13 (10 Telegram `Connection reset`, 1 approvazione pesi, 1 FRED 500, 1 `poll_telegram_updates`), api/beat/news-stream 0.
- Cicli portfolio: 24 (14:07–19:52), tutti `succeeded`; 3 ordini reali.
