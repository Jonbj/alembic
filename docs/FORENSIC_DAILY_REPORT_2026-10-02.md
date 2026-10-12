# Forensic Daily Report — 2026-10-02

Sessione forense autonoma in sola lettura, eseguita il 2026-10-12. Fuso operativo **UTC** (`src/workers/celery_app.py`:
`timezone="UTC"`, `enable_utc=True`): tutti gli orari di questo report sono UTC. Seduta RTH 13:30–20:00 UTC (EDT).
Il conto è **paper**, verificato e non assunto: `ALPACA_BASE_URL=https://paper-api.alpaca.markets` nel container `worker`, e
22 istantanee su 22 di `portfolio_monitor_snapshots` hanno `broker_environment='paper'`. `execution.engine=portfolio`
(il log riporta «legacy execution worker inactive»).

Periodo di sola osservazione: il charter (`docs/evidence/OBSERVATION_CHARTER.md`) indica come scadenza attesa il
2026-09-28 e non registra né la chiusura né una proroga. Questo report quindi **non propone tarature**: i ticket
riguardano solo difetti di correttezza o di strumentazione.

Esiste già `docs/ALPHA_MISS_REPORT_2026-10-02.md`, che ha registrato per questa seduta F-001 (264,19 $), F-009 (73,62 $) e
F-036 (null). Non li registro una seconda volta: qui aggiungo la causa che quel report non vedeva (DAY-001).

---

## 1. Executive summary

- **La seduta si è interrotta alle 14:59:46 UTC.** Il link fisico della NIC dell'host (`enp6s0`) è caduto e non è più tornato. Alle 15:48:07 è partito un reboot dalla sessione GNOME, e l'host è tornato su solo alle **22:00:34**. Da 14:59 alle 20:00 (**5 h 00 min di RTH, il 77% della seduta**) non ci sono stati né news, né segnali, né cicli portfolio.
- Copertura effettiva: 4 cicli portfolio su 24 (14:07–14:52). Gli ultimi segnali sono delle 14:59:37: 78 segnali in tutto, contro 246 del 01/10.
- **Nessun alert è stato recapitato.** `broker_stale` e `market_clock` (critical) si aprono alle 15:00 e risultano «recovered» alle 22:00:53, a mercato chiuso. Telegram fallisce per DNS e il canale d'allerta gira sullo stesso host. Non esiste un watchdog esterno (DAY-001, nuovo F-094).
- Durante i 48 minuti senza rete il worker `news-stream` ha ritentato la connessione WebSocket **3.044.783 volte senza backoff**, scrivendo **6,2 GB di log** (91 M righe). Il disco è all'88% con 37 GB liberi: a quel ritmo un outage di rete di circa 5 h con l'host acceso riempirebbe il disco, cioè lo scenario di F-085 (DAY-002, nuovo F-095).
- Con il clock Alpaca irraggiungibile il ciclo portfolio restituisce `clock_unavailable` e il worker sentiment `market_closed`, con il task `succeeded` (DAY-003, F-074).
- **Nessun ordine** inviato o eseguito il 02/10, sia nel DB sia sul broker (0 ordini creati, 0 fill, 0 cancel). 0 trade aperti o chiusi.
- S4: due segnali sopra il gate (NVDA +0,435, QQQ +0,318) sono bloccati da P0-05 perché i titoli sono già a libro S1 (DAY-006, F-031). Con un hold fino alla chiusura il blocco ha evitato −32,15 $ congetturali.
- WDC (S4) a −24/−27% dall'ingresso, con segnale −0,305 sopra il gate, non può uscire: è dentro il target S1 congelato (DAY-005, F-089). L'alert #161 è rifiutato da Telegram con 400 (DAY-013).
- NAV in chiusura **110.199,99 $, +373,69 $ (+0,34%)** (Alpaca portfolio history, timbro 2026-10-03). SPY ha fatto circa +0,74% close-to-close. Con un'esposizione lorda di circa un terzo del NAV il risultato è coerente con la beta.
- Ollama è stato su fino all'outage: 0 timeout in RTH, 1 fallback FinBERT reale (MU, divergenza, verdetto dentro l'inviluppo). Il worker però ne dichiara 26 (F-078).

## 2. Verdict

**Anomalie significative.** Ordini, fill e posizioni sono coerenti e riconciliati (40 `fully_held`, 0 anomalie). Non c'è stato alcun ordine errato e il comportamento fail-closed sul clock ha impedito decisioni alla cieca.

Il processo però **non ha coperto la seduta**: 5 ore di RTH senza pipeline, senza un solo alert consegnato, e con un worker che per costruzione può saturare il disco durante un outage di rete. L'evidenza del 02/10 per S4 (copertura, miss, active recall) è quindi in gran parte un artefatto dell'outage. Va letta così e non come comportamento della strategia.

## 3. Timeline del 2026-10-02 (UTC)

| Ora | Componente | Evento | Esito | Fonte |
|---|---|---|---|---|
| 01:54–14:54 | ingest | 747 `duplicate_id` Benzinga | scartati | `news_queue_drops` |
| 07:00:55 | `detect_regime` | LLM-2 `qwen3.5:cloud` «410 Gone» → regime da LLM-1 solo | sideways ×0,7, «disagreement=False» | log inference |
| 09:28 / 11:28 | `sentiment_shadow` | SoftTimeLimit, lotto di 12 perso; **Hard time limit (840 s)** alle 09:29 e 11:29 | child ucciso, turno perso | log inference |
| 13:30:01 | alert | `portfolio_cycle_late` critical + `signal_stale` warning | rientrati 14:08 / 13:37 | `mobile_events` |
| 13:30:36 | `detect_regime` | di nuovo LLM-2 410 | sideways ×0,7 | log inference |
| 13:36:24 | sentiment | drena la coda notturna: **181 stale** (età mediana 4,9 h) + 92 not_tradable | scartati | `news_queue_drops` |
| 13:45:42 | sentiment | NKE −0,603 («Nike Posts Mixed Q1 Results») | long-only, nessuna azione | 13810 |
| 13:54:21 / 14:00:06 | sentiment | NVDA +0,468 (buyback) / +0,435 (Morgan Stanley top pick) | sopra gate | 13823 / 13845 |
| 13:58:34 | sentiment | MU: divergenza (glm 0,08 contro gpt-oss 0,60) → **FinBERT** +0,304 | `finbert_fallback_events` 1 riga, body_chars 424 | 13838 |
| 13:59:58 | sentiment | WDC −0,305 (Seagate/Toshiba HDD) | sopra gate, ribassista | 13844 |
| **14:07:00** | `portfolio-cycle` | primo ciclo (37 min dopo l'apertura). S4: NVDA → **SKIP_PYRAMIDING** (S1 a libro). WDC nel target S1 → nessuna uscita | 0 ordini inviati | decisione 59669, log r.3941 |
| 14:22 / 14:37 | `portfolio-cycle` | come sopra; #161 «WDC unprotected −24,9% / −25,2%» | Telegram **400** alle 14:37:07 | log r.4041, r.4144 |
| 14:40:34 | sentiment | QQQ +0,318 (payroll di settembre sotto le attese) | sopra gate | 13865 |
| **14:52:00** | `portfolio-cycle` | QQQ → **SKIP_PYRAMIDING** (S1 a libro dal 16/09) | ultimo ciclo effettivo | decisione 60005 |
| 14:59:37 | sentiment | ultimo segnale (NKE −0,296) | — | 13877 |
| **14:59:46** | host | **`enp6s0: NIC Link is Down`**; NetworkManager → CONNECTED_LOCAL | inizio dell'outage | journal boot −5 |
| 14:59:54 | tutti i worker | «Temporary failure in name resolution» | — | log inference/worker |
| 14:59:54–15:48 | `news-stream` | **3.044.783 tentativi di riconnessione WS** senza backoff | 6,2 GB di log | log news-stream |
| 15:00:00 | alert | `broker_stale` critical + `system:market_clock` critical | aperti; Telegram fallisce per DNS | `mobile_events`, log worker |
| 15:00–15:45 | sentiment | 4 task → `{'skipped': True, 'reason': 'market_closed'}` | **etichetta falsa** (clock irraggiungibile) | log inference |
| 15:07 / 15:22 / 15:37 | `portfolio-cycle` | `{'error': 'clock_unavailable'}`, task `succeeded` | 3 cicli persi | log worker r.4373/4548/4780 |
| **15:48:07** | host | «The system will reboot now!» (GNOME endSessionDialog) | stack fermato (Warm shutdown) | journal |
| 15:52–19:52 | — | **17 cicli portfolio mai eseguiti**, nessuna news e nessun segnale | host spento | — |
| **22:00:34** | host | nuovo boot; NIC su alle 22:00:41, docker alle 22:00:42 | stack di nuovo su (worker 22:00:48) | journal boot −4 |
| 22:00:47 | beat catch-up | `decay_check` → 7 **DECAY CRITICAL** (S1/S2/S4: stesso IC −0,019 e stesso Sharpe −6,71) | solo log | log worker |
| 22:00:52 | `portfolio-cycle` | `market_closed` (next_open 2026-10-05) | — | log worker r.5090 |
| 22:00:53 | `reconcile-positions` | 40 `fully_held`, anomalies 0 | — | log worker |
| 22:00:53 | alert | `broker_stale` / `market_clock` → recovered | mai notificati | `mobile_events` |
| 22:50:00–01 | alert | `portfolio_cycle_session_grid` (close_gap **308 min**, `alert_required: true`) | **aperto e chiuso in 1 s** | `mobile_events` |
| 23:05:00 | Telegram | primo `sendMessage` 200 OK dopo il riavvio | — | log worker r.5392 |

## 4. News ingest

### 4.1 Per fonte

| Fonte | Trasporto | Righe scorate | URL distinti | Ticker | Prima–ultima riga | Lag mediano pubbl.→riga | Fetched (stats) | Duplicati (stats) | Scartati |
|---|---|---|---|---|---|---|---|---|---|
| alpaca_benzinga | ws 74 / rest 3 | 77 | 50 | 27 | 13:36:40–14:59:37 | ws 33,2 min (dopo le 14:20: **0,6 min**), rest 82 min | 236 | **747** | 181 stale, 92 not_tradable, 747 duplicate_id |
| gdelt_gkg | — | 1 | 1 | 1 | 14:02:12 | 2,2 min | 472 | 0 | 471 no_ticker |

- Nessun timestamp futuro (0 righe con `published_at > created_at`).
- Il lag mediano WS di 33 min è un artefatto del drenaggio della coda notturna all'apertura. Dopo le 14:20 il lag WS è di 0,6 min.
- **Buco temporale: nessuna riga `news_log` dopo le 14:59:37.** La causa è l'outage, non i provider (DAY-001).
- Fan-out: 51 URL → 78 righe; 40 righe (51%) vengono da URL multi-ticker, con un massimo di 7 (DAY-011).
- Copertura: 28 ticker con almeno una news. L'alpha-miss dà 68/96 simboli di watchlist a zero news, contro 28/96 del 01/10: il salto è spiegato dall'outage.
- Sanitizzazione: 40 delle 77 righe Benzinga in `news_log` contengono entità HTML. Per il charter (riga F-076 del 2026-09-21) **questo conteggio non è il criterio**, perché Benzinga persiste il grezzo. L'unico input che ha raggiunto un modello e che è osservabile (`finbert_fallback_events`, MU) non contiene entità. Non lo conto come finding.

### 4.2 Per ticker (segnali)

| Ticker | Segnali | Ensemble | Max | Min |
|---|---|---|---|---|
| NKE | 14 | 13 | +0,072 | **−0,603** |
| NVDA | 8 | 3 | **+0,468** | −0,180 |
| SPY | 7 | 2 | +0,180 | −0,040 |
| ORCL | 5 | 5 | +0,036 | −0,189 |
| MU | 4 | 3 | +0,304 (FinBERT) | +0,075 |
| GOOGL | 4 | 2 | +0,210 | −0,040 |
| QQQ | 3 | 3 | +0,318 | +0,138 |
| WDC | 3 | 3 | +0,018 | **−0,305** |
| AVGO | 3 | 2 | +0,214 | −0,019 |

### 4.3 Top news per impatto

| Segnale | Ticker | Score | News | Esito |
|---|---|---|---|---|
| 13810 | NKE | −0,603 | «Nike Posts Mixed Q1 Results…» (pubbl. 12:02) | long-only, nessuna azione (NKE −3,64% nel giorno) |
| 13823 / 13845 | NVDA | +0,468 / +0,435 | buyback record; «Very Undemanding Valuation» (MS top pick) | SKIP_PYRAMIDING (DAY-006) |
| 13865 | QQQ | +0,318 | «Nasdaq 100 Rallies to All-Time Highs as Fed Hike Bets Cool» | SKIP_PYRAMIDING (DAY-006) |
| 13844 | WDC | −0,305 | «Why Is Seagate Technology Stock Sinking Friday?» | posizione S4 non esce (DAY-005) |
| 13838 | MU | +0,304 | «Micron's NAND Revenue Surged 526%…» (FinBERT per divergenza) | SKIP_FALLBACK; MU già a libro |
| 13817 | AVGO | +0,214 | «Broadcom Chases NVIDIA With $60 Billion Financing Plan» (fan-out) | sotto gate (F-009, già nel report alpha-miss) |

**Confidenza dell'analisi ingest:** alta per conteggi, lag e buco (DB + journal dell'host).

## 5. Performance modelli LLM

| Modello | Risposte | Eleggibili (flag) | Sotto floor 0,40 | Conf. mediana | Polarity media | Pos/Neg/Zero | Timeout RTH | Timeout giorno |
|---|---|---|---|---|---|---|---|---|
| glm-5.3:cloud | 78 | 32 | 44 (56%) | 0,35 | +0,022 | 39/30/9 | 0 | 4 (09:18–09:26) |
| gpt-oss:20b-cloud | 78 | 32 | 21 (27%) | 0,60 | +0,010 | 36/27/15 | 0 | 4 (02:20, 07:16, 09:20, 09:26) |
| FinBERT (fallback reale) | 1 | — | — | 0,48 | +0,63 | 1/0/0 | — | — |

| Percorso del segnale | Segnali | Score medio | Min / Max | Conf. media | ≥ 0,30 | std medio |
|---|---|---|---|---|---|---|
| ensemble | 52 | −0,007 | −0,603 / +0,468 | 0,44 | 7 | 0,097 |
| single gpt-oss | 24 | +0,038 | −0,240 / +0,240 | 0,54 | 0 | 0,087 |
| single glm-5.3 | 1 | 0,000 | — | 0,45 | 0 | 0 |
| FinBERT (divergenza) | 1 | +0,304 | — | 0,48 | 1 | 0 |

- **Latenza**: durata dei task `run_sentiment_worker` in RTH con lavoro da 1,8 a 113 s. Non esiste una latenza per singola chiamata (F-086).
- **Eleggibilità**: 20 dei 52 segnali ensemble hanno 0/2 risposte flaggate `eligible`, gli altri 32 ne hanno 2/2 (DAY-009, F-010).
- **Divergenza mascherata**: il log `F-054 masked divergence` compare 20 volte in RTH (71 nel giorno), fino a std 0,283 (NVDA 13:53) ridotta a 0,000 sull'unico contributore eleggibile (DAY-008).
- **Fallback FinBERT**: 1 evento reale (MU 13838, «ensemble divergence», title_chars 86 / body_chars 424, quindi FinBERT ha visto parte del corpo). Verdetto 0,633 × 0,479 = 0,304, **dentro** l'inviluppo dei due LLM sostituiti (glm 0,08, gpt-oss 0,60): F-087 non si manifesta. I task ne dichiarano 26 in RTH (DAY-010, F-078).
- **Regime**: deciso da un solo modello (LLM-2 410 Gone, DAY-007).

Verifica funzionale:
- *Validazione prima del signal store*: parsing JSON sì. Nessuna validazione semantica/grounding (F-091, oggi non osservata su segnali arrivati all'ordine).
- *Varianza alta*: non è un gate d'ingresso; il guard di divergenza è aggirato dal filtro di eleggibilità (F-054).
- *News duplicate*: dedup id/content attiva (747 duplicate_id); il fan-out fa pesare lo stesso articolo su più ticker (F-012).
- *Confidence bassa*: riduce lo score (p×c) e, sotto 0,40, esclude il modello.
- *Offline/background*: sì. Le chiamate LLM sono solo nel worker `inference`; i cicli portfolio leggono dal DB.
- *Allucinazione in decisione*: nessun ordine oggi, quindi rischio non materializzato.

## 6. Segnali finali per ticker (che hanno prodotto o bloccato un'azione)

| Ticker | Segnale | Score | Percorso | Gate 0,30 | Esito |
|---|---|---|---|---|---|
| NVDA | 13845 | +0,435 | ensemble (2/2 eligible, accordo) | sopra | SKIP_PYRAMIDING 14:07–14:37 (S1 a libro dal 01/10) |
| QQQ | 13865 | +0,318 | ensemble (std 0,212) | sopra | SKIP_PYRAMIDING 14:52 (S1 a libro dal 16/09) |
| WDC | 13844 | −0,305 | ensemble | sopra (ribassista) | posizione S4 aperta: nessuna SELL (peso S1 congelato 1,73%, DAY-005) |
| NKE | 13810 | −0,603 | ensemble | sopra (ribassista) | RANK_LONG_ONLY (corretto per design) |
| MU | 13838 | +0,304 | FinBERT | sopra | SKIP_FALLBACK (#108) |
| AMZN, AZN, DIS, LLY, TSM, VZ | — | −0,24 / +0,18 | single-model | sotto | SKIP_FALLBACK |

Esiti degli intenti S4 (`s4_intent_events`, 726 righe): CANDIDATE_OBSERVED 363, SKIP_ENTRY_FRESHNESS 174, SKIP_ENTRY_GATE 81,
SKIP_FALLBACK 68, SKIP_STALE 35, SKIP_PYRAMIDING 4, RANK_LONG_ONLY 1, **SUBMITTED 0**.
`execution_decisions`: OBSERVE_LATE_ENTRY 296, SKIP_THRESHOLD 81, SHADOW_LATE_ENTRY 67, SKIP_FALLBACK 6, SKIP_PYRAMIDING 2. Nessuna BUY/SELL.

## 7. Ordini generati/eseguiti

**Nessun ordine.** I 4 cicli effettivi hanno prodotto ciascuno un `final_order` del combiner: NVDA BUY 9,24 / 9,20 / 9,20 az.
(14:07, 14:22, 14:37) e QQQ BUY 2,90 az. (14:52), tutti di tipo `merged`. Tutti sono stati scartati da P0-05 prima dell'invio
(`submitted: 0`). Sul broker (lettura read-only `GET /v2/orders`) risultano **0 ordini creati** il 02/10 e 0 fill o cancel di
ordini preesistenti: nessuno stop GTC è scattato durante l'outage. `/api/orders` e `/api/trades` non hanno righe del 02/10.

| Ora | Strategia | Ticker | Azione | Qty | Stato | Rationale | Risk check | Anomalie |
|---|---|---|---|---|---|---|---|---|
| 14:07 / 14:22 / 14:37 | merged (S4 → combiner) | NVDA | BUY | ~9,2 | generato dal combiner, **non inviato** | 13845 +0,435 | P0-05 | DAY-006, telemetria DAY-012 |
| 14:52 | merged | QQQ | BUY | 2,90 | generato, **non inviato** | 13865 +0,318 | P0-05 | DAY-006 |

## 8. PnL / rendimento

| Voce | Valore | Fonte / note |
|---|---|---|
| Equity in chiusura 2026-10-02 | **110.199,99 $** | Alpaca portfolio history (timbro 2026-10-03 00:00, cfr. F-053) |
| Variazione giornaliera | **+373,69 $ (+0,34%)** | idem; snapshot 22:00:48 110.189,47 $ (+363,17) |
| Realizzato | **0 $** | nessuna chiusura, nessuno stop eseguito |
| Non realizzato | +373,69 $ (tutto da posizioni aperte prima del 02/10) | nessuna posizione aperta il 02/10 |
| WDC (S4) | ≈ −15,8 $ nel giorno (0,3347 az., −10,22%); −24/−27% dall'ingresso | stima su rendimento giornaliero dell'alpha-miss |
| Per strategia | non separabile in modo affidabile oggi (book misto, S4 solo WDC/PANW residui) | — |
| Commissioni | 0 $ (paper) | — |
| Slippage | n/a (nessun fill) | — |

Controfattuali (corti, fino alla chiusura del 02/10, prezzi IEX):
- NVDA BUY bloccato alle 14:07 @236,64 → chiusura 234,00: −1,12% × 2.200 $ = **−24,54 $**.
- QQQ bloccato alle 14:52 @752,20 → 749,60: −0,35% × 2.200 $ = **−7,60 $**.
- WDC uscita mancata alle 14:07 @415,935 → chiusura 415,37 (minimo 399 alle 15:00): 0,3347 × −0,565 = **−0,19 $**.

## 9. Analisi correttezza buy/sell

| Controllo | Esito |
|---|---|
| BUY solo quando consentito | sì: gate, freshness, fallback e P0-05 applicati, 0 BUY inviati |
| SELL/exit corrette | **no per WDC**: S4 con segnale −0,305 non esce perché il peso S1 congelato lo tiene (F-089) |
| Stop-loss | stop GTC sul broker attivi durante l'outage (nessuno scattato); 9 posizioni sub-one-share senza stop (#161) |
| Signal flip | WDC è un flip ribassista non eseguito (vedi sopra) |
| Max holding / hold minimo | nessuna uscita, non applicabile |
| Rebalance band | gate di ribilanciamento S1 chiuso (40 posizioni tenute), corretto |
| Ordini duplicati / identici nello stesso minuto | nessuno |
| Roundtrip < 30 min / pyramiding | nessuno; il pyramiding è stato bloccato attivamente da P0-05 |
| SELL con sentiment positivo (A5) | nessuna SELL |
| Ticker non consentiti / fuori orario | nessun ordine |
| Trade con dati stale | no: 174 SKIP_ENTRY_FRESHNESS, 35 SKIP_STALE, 181 drop stale |
| Trade con LLM non valido | no |
| Circuit breaker | non attivato. Durante l'outage il **fail-closed sul clock** ha impedito cicli alla cieca (corretto), ma con esito `succeeded` (F-074) |
| Strategia disabilitata | no |
| Paper/live | paper, verificato |
| Idempotenza retry | nessun retry rilevante; nessun doppio invio |
| Riconciliazione | 40 posizioni broker = 40 `fully_held` alle 22:00:53, 0 anomalie |
| NO-ORDER (decisione BUY/SELL senza ordine) | 0 (nessuna decisione BUY/SELL) |
| Score < 0,05 con ordine | nessuno |
| fallback su tutti i simboli | no |

`exit_mechanism`: nessuna uscita il 02/10, nessun conteggio.

## 10. Anomalie trovate

### [DAY-001] Outage di rete dell'host in RTH: 5 h di seduta senza pipeline e nessun alert recapitato

* Tipo: Anomalia
* Area: Ops
* Evidenza:
  * file/log/tabella: `journalctl -b -5` / `-b -4`; `logs/containers/worker-2026-10-02.log`; `mobile_events`; `news_log`, `sentiment_signals`, `portfolio_cycles`
  * timestamp: NIC giù 14:59:46; reboot 15:48:07; boot successivo 22:00:34
  * snippet/query: `igc 0000:06:00.0 enp6s0: NIC Link is Down` → `NetworkManager state is now CONNECTED_LOCAL`; `systemd-logind: The system will reboot now!`; `max(created_at)` di `news_log` = 14:59:37; `portfolio_cycles` = 4 righe (14:07–14:52); `mobile_events`: `broker_stale` e `market_clock` critical 15:00:00 → recovered 22:00:53
* Descrizione: la perdita del link fisico ha isolato l'host. Lo stack si è comportato in modo fail-closed (clock irraggiungibile → nessun ciclo). Gli alert critical si sono aperti, ma il loro unico canale (Telegram) gira sullo stesso host senza rete: 3 invii falliti per DNS e poi, dalle 15:48, host spento. Gli incidenti sono stati chiusi «recovered» alle 22:00, a mercato chiuso, senza che nessuno li abbia mai visti. Non esiste un watchdog esterno (heartbeat verso un servizio fuori dall'host) che segnali l'assenza di cicli in RTH. La causa della caduta del link e il motivo dei 6 h 12 min fra il reboot e il boot successivo non sono ricostruibili dai log.
* Impatto: 20 cicli su 24 persi (3 `clock_unavailable` + 17 mai eseguiti), nessuna news né segnale per 5 h di RTH. Le metriche del 02/10 (copertura 68/96 a zero news, active recall 0/2, miss SPCX/TSLA NO_NEWS nell'alpha-miss) sono in gran parte un **artefatto dell'outage**, e chi legge la serie deve saperlo. Le posizioni sono rimaste protette dagli stop GTC lato broker.
* Severità: High
* Confidenza: High
* Azione consigliata: registrare il 02/10 dalle 14:59 nel registro delle rotture del charter (sessione parziale). Ticket ops: un heartbeat esterno (dead-man switch) che segnali da fuori l'host l'assenza di `portfolio_cycles` in RTH.
* Test/monitor consigliato: dead-man switch esterno con soglia di 20 min in RTH; marcatura `session_coverage` nel dossier (cicli effettivi / attesi), così gli artefatti di outage non entrano nei denominatori.

### [DAY-002] Il worker news-stream ritenta la connessione WebSocket senza backoff: 3 M tentativi e 6,2 GB di log in 48 minuti

* Tipo: Bug
* Area: Ops
* Evidenza:
  * file/log/tabella: `logs/containers/worker-news-stream-2026-10-02.log` (6.177.883.293 byte, 91.343.604 righe); `src/connectors/alpaca_news_stream.py:9` («auto-reconnects… handled by alpaca-py internals»); `df -h /` → 88% usato, 37 GB liberi
  * timestamp: 14:59:54 → 15:48 (fine della rete / shutdown)
  * snippet/query: `3044783 × INFO starting data websocket connection` / `ERROR … [Errno -3] Temporary failure in name resolution` + traceback di ~25 righe ciascuno. Gli altri file news-stream pesano 4–200 KB al giorno
* Descrizione: la riconnessione è delegata ad alpaca-py, che riprova immediatamente (circa 1.050 tentativi al secondo) e logga un traceback completo a ogni tentativo. Non c'è backoff né rate-limit del log.
* Impatto: circa 130 MB/min di log. Con 37 GB liberi, un outage di rete di circa 5 h **con l'host acceso** (per esempio router o DNS giù di notte) riempirebbe il disco. È esattamente il guasto che il 16/09 ha abbattuto l'intero stack via Redis MISCONF (F-085), e in quel caso non si recupererebbe al ritorno della rete. Oggi l'ha evitato solo lo spegnimento dell'host. Il file da 6,2 GB è ancora su disco.
* Severità: High
* Confidenza: High
* Azione consigliata: ticket di correttezza ops. Wrapper di riconnessione con backoff esponenziale (cap 60 s) e log deduplicato o rate-limited; rotazione con tetto di dimensione per i log persistenti.
* Test/monitor consigliato: test con `getaddrinfo` che fallisce: al massimo N tentativi al minuto e al massimo M righe di log; alert sulla dimensione giornaliera dei file in `logs/containers/` (> 500 MB).

### [DAY-003] Con il clock Alpaca irraggiungibile il ciclo portfolio restituisce `clock_unavailable` e il sentiment dice `market_closed`, sempre `succeeded`

* Tipo: Rischio
* Area: Ops
* Evidenza:
  * file/log/tabella: log worker r.4373/4548/4780; log inference 15:00–15:45
  * timestamp: 15:07, 15:22, 15:37 (portfolio); 15:00, 15:15, 15:30, 15:45 (sentiment)
  * snippet/query: `run_portfolio_cycle … succeeded … {'error': 'clock_unavailable'}`; `run_sentiment_worker … succeeded … {'skipped': True, 'reason': 'market_closed'}` preceduto da `Could not fetch Alpaca market clock … NameResolutionError`
* Descrizione: il fail-closed è corretto, ma il worker sentiment etichetta un guasto come «mercato chiuso», che è un'affermazione falsa e indistinguibile da un vero skip notturno. Entrambi i task risultano riusciti.
* Impatto: chi conta i cicli o gli skip non distingue un outage da una notte. Oggi il problema era coperto dal guasto più ampio di DAY-001.
* Severità: Medium
* Confidenza: High
* Azione consigliata: solo ricorrenza (F-074). Nel ticket esistente va aggiunto il ramo sentiment (`reason='clock_unavailable'`).
* Test/monitor consigliato: test con clock che solleva un'eccezione → `reason != 'market_closed'`.

### [DAY-004] L'incidente di griglia con close_gap di 308 minuti si apre e si chiude nello stesso secondo

* Tipo: Bug
* Area: Ops
* Evidenza:
  * file/log/tabella: `mobile_events` fingerprint `pipeline:portfolio_cycle_session_grid`; log worker r.5322
  * timestamp: 22:50:00.47 → resolved 22:50:01.04
  * snippet/query: `details: {"close_gap_minutes": 307.99, "alert_required": true, "last_effective_cycle": "14:52:00"}`
* Descrizione: il job specializzato rileva correttamente la griglia mancante (5 h), ma il valutatore generico chiude l'incidente entro un secondo.
* Impatto: l'unico segnale persistito dell'outage di RTH si autoannulla e non resta un incidente aperto da leggere il giorno dopo.
* Severità: Medium
* Confidenza: High
* Azione consigliata: solo ricorrenza (F-058).
* Test/monitor consigliato: già noto (F-058).

### [DAY-005] WDC (S4) a −24/−27% con segnale −0,305 sopra il gate non esce: è nel target S1 congelato

* Tipo: Bug
* Area: Signal
* Evidenza:
  * file/log/tabella: `sentiment_signals` 13844 (−0,305, ensemble glm −0,65 / gpt-oss −0,30); `strategy_rebalance_snapshots` S1 2026-10-01 14:07: WDC weight 0,01728, in_target, held; log worker r.3942/4041/4143/4245
  * timestamp: segnale 13:59:58; cicli 14:07–14:52
  * snippet/query: `#161: WDC unprotected at -24.3% … -26.9% (qty 0.3347, status sub_one_share)`; nessuna decisione SELL WDC
* Descrizione: il combiner somma il peso S1 congelato e la regola d'uscita S4 non produce una SELL.
* Impatto: perdita trascurabile oggi (0,3347 az.): −0,19 $ fra le 14:07 e la chiusura, con un minimo intraday di −4% alle 15:00. Il meccanismo resta aperto.
* Severità: Medium
* Confidenza: High
* Azione consigliata: solo ricorrenza (F-089).
* Test/monitor consigliato: già noto.

### [DAY-006] Due segnali S4 sopra il gate (NVDA +0,435, QQQ +0,318) bloccati da P0-05 perché detenuti da S1

* Tipo: Rischio
* Area: Signal
* Evidenza:
  * file/log/tabella: `execution_decisions` 59669 (NVDA) e 60005 (QQQ); `s4_intent_events` SKIP_PYRAMIDING ×4; `portfolio_cycles.final_orders`
  * timestamp: 14:07, 14:22, 14:37 (NVDA); 14:52 (QQQ)
  * snippet/query: `P0-05 anti-pyramiding: gia' a libro dal 2026-10-01, sentiment +0.435, peso target 3.0%`
* Descrizione: comportamento noto. Il guard impedisce a S4 di entrare su simboli già detenuti da S1.
* Impatto: congetturale, con hold fino alla chiusura: NVDA −24,54 $ e QQQ −7,60 $, totale **−32,15 $**. Oggi il blocco ha evitato una perdita. Se il guard non ci fosse stato, l'outage avrebbe trascinato le due posizioni fino al 05/10 senza uscita possibile.
* Severità: Low
* Confidenza: High
* Azione consigliata: solo ricorrenza (F-031).
* Test/monitor consigliato: già noto.

### [DAY-007] Il regime è ancora deciso da un solo LLM: `qwen3.5:cloud` 410 Gone

* Tipo: Rischio
* Area: Risk
* Evidenza: log inference 07:00:55 e 13:30:36: `LLM-2 failed in regime detection: Ollama API error 410: Gone` → `sideways (×0.7), disagreement=False`
* Descrizione / Impatto: come il 01/10. Il controllo di disaccordo è falso per costruzione e il task risulta `succeeded`.
* Severità: Medium · Confidenza: High
* Azione consigliata: solo ricorrenza (F-017).
* Test/monitor consigliato: già noto.

### [DAY-008] Divergenza d'ensemble mascherata dal filtro di eleggibilità: 20 casi in RTH

* Tipo: Bug · Area: LLM
* Evidenza: log inference, 20 righe `F-054 masked divergence` fra 13:36 e 14:52 (71 nel giorno). Il massimo è NVDA alle 13:53:38 con std 0,2828 su tutte le risposte e 0,0000 sull'unico contributore eleggibile.
* Impatto: il guard di divergenza non vede questi casi. Nessuno è arrivato a un ordine.
* Severità: Medium · Confidenza: High · Azione consigliata: solo ricorrenza (F-054) · Test/monitor: già noto.

### [DAY-009] 20 dei 52 segnali ensemble con 0/2 risposte flaggate `eligible`

* Tipo: Bug · Area: LLM
* Evidenza: `llm_responses` ⋈ `sentiment_signals` (non fallback) del 02/10: eligible 0 → 20, eligible 2 → 32.
* Impatto: `eligible` non descrive i contributori reali (retry a floor 0).
* Severità: Low · Confidenza: High · Azione consigliata: solo ricorrenza (F-010) · Test/monitor: già noto.

### [DAY-010] Il worker dichiara 26 `finbert_fallbacks` contro 1 evento FinBERT reale

* Tipo: Bug · Area: LLM
* Evidenza: somma di `finbert_fallbacks` nei risultati di `run_sentiment_worker` 13–15h = 26; `finbert_fallback_events` del 02/10 = 1 riga (MU).
* Impatto: l'esito del task segnala un outage FinBERT che non c'è stato. Il tasso reale è 1/78.
* Severità: Low · Confidenza: High · Azione consigliata: solo ricorrenza (F-078) · Test/monitor: già noto.

### [DAY-011] Il 51% delle righe scorate viene da articoli fan-out multi-ticker

* Tipo: Rischio · Area: News
* Evidenza: `news_log` del 02/10: 51 URL → 78 righe, 40 da URL multi-ticker, massimo 7. L'unico segnale AVGO sopra +0,2 nasce dall'articolo «Broadcom Chases NVIDIA…» condiviso con MSFT e ORCL.
* Severità: Low · Confidenza: High · Azione consigliata: solo ricorrenza (F-012) · Test/monitor: già noto.

### [DAY-012] Telemetria del ciclo: `orders_count` = 1 su 4 cicli con 0 ordini inviati

* Tipo: Anomalia · Area: Orders
* Evidenza: `portfolio_cycles.orders_count` = 1 × 4 (NVDA ×3, QQQ); log `'final_orders': 1, 'submitted': 0`.
* Severità: Low · Confidenza: High · Azione consigliata: solo ricorrenza (F-014) · Test/monitor: già noto.

### [DAY-013] Alert #161 (WDC −25,2% senza protezione) rifiutato da Telegram con 400

* Tipo: Bug · Area: Ops
* Evidenza: log worker r.4144–4145, 14:37:07: `sendMessage "HTTP/1.1 400 Bad Request"` subito dopo `#161: WDC unprotected at -25.2%`.
* Impatto: l'unico alert di rischio di posizione della giornata non è arrivato (cfr. F-036, già registrato per il 02/10 dal report alpha-miss).
* Severità: Medium · Confidenza: High · Azione consigliata: solo ricorrenza (F-005) · Test/monitor: già noto.

### [DAY-014] Token del bot Telegram in chiaro in 12.214 righe di log

* Tipo: Rischio · Area: Ops
* Evidenza: `grep -c "api.telegram.org/bot"`: 12.211 righe nel log inference e 3 nel log worker del 02/10.
* Severità: Medium · Confidenza: High · Azione consigliata: solo ricorrenza (F-018) · Test/monitor: già noto.

### [DAY-015] Fetch del benchmark SPY fallito 204 volte, nessun alert

* Tipo: Anomalia · Area: Data
* Evidenza: log worker, 204 righe `SPY benchmark fetch failed`.
* Severità: Low · Confidenza: High · Azione consigliata: solo ricorrenza (F-016) · Test/monitor: già noto.

### [DAY-016] Il decay monitor dà S1, S2 e S4 con lo stesso IC −0,019 e lo stesso Sharpe −6,71

* Tipo: Bug · Area: Risk
* Evidenza: log worker 22:00:47 (catch-up del beat): `DECAY CRITICAL [S1]: IC dropped 154% from 0.035 to -0.019`, `[S2] … 145% from 0.042 to -0.019`, `[S4] … 168% from 0.028 to -0.019`; Sharpe −6,71 per tutte e tre.
* Severità: Low · Confidenza: High · Azione consigliata: solo ricorrenza (F-004) · Test/monitor: già noto.

### [DAY-017] 7 DECAY CRITICAL scritti solo nel log

* Tipo: Anomalia · Area: Ops
* Evidenza: 7 righe CRITICAL alle 22:00:47; `mobile_events` del 02/10 non contiene alcun fingerprint di decay.
* Severità: Low · Confidenza: High · Azione consigliata: solo ricorrenza (F-062) · Test/monitor: già noto.

### [DAY-018] Primo ciclo portfolio 37 minuti dopo l'apertura

* Tipo: Anomalia · Area: Ops
* Evidenza: primo `portfolio_cycles` alle 14:07:00; `pipeline:portfolio_cycle_late` critical 13:30:01 → 14:08:00; `session_grid.open_gap_minutes` 37,01.
* Severità: Low · Confidenza: High · Azione consigliata: solo ricorrenza (F-021) · Test/monitor: già noto.

### [DAY-019] 181 articoli accodati fuori seduta e scartati stale all'apertura

* Tipo: Anomalia · Area: News
* Evidenza: `news_queue_drops` `stale` ×181, tutti alle 13:36:24, età mediana 4,9 h.
* Severità: Low · Confidenza: High · Azione consigliata: solo ricorrenza (F-069) · Test/monitor: già noto.

### [DAY-020] `ingestion_stats_daily`: duplicates 747 contro fetched 236 per alpaca_benzinga

* Tipo: Anomalia · Area: Data
* Evidenza: `ingestion_stats_daily` 2026-10-02 alpaca_benzinga: fetched 236, queued 331, duplicates 747 (anche queued > fetched).
* Severità: Low · Confidenza: High · Azione consigliata: solo ricorrenza (F-007) · Test/monitor: già noto.

## 11. False positive o aree risultate corrette

- Paper/live: paper, verificato su env e su 22 snapshot.
- **Fail-closed sul clock**: con il broker irraggiungibile nessun ciclo ha deciso alla cieca. Al ritorno, `reconcile-positions` dà 40 `fully_held` e 0 anomalie, e i job saltati (decay, reconcile, counterfactual, forward return) sono stati recuperati dal beat alle 22:00:47.
- Stop GTC lato broker: restano attivi durante l'outage. Nessuno è scattato (verificato con `GET /v2/orders` sul 02/10).
- Nessun ordine duplicato, fuori orario, senza decisione o NO-ORDER.
- FinBERT per divergenza su MU: verdetto (+0,304) dentro l'inviluppo dei due LLM (0,08–0,60), body_chars 424. F-087 **non** si manifesta oggi.
- Entità HTML in `news_log` (40/77): per il charter non è il criterio di F-076 (Benzinga persiste il grezzo). L'input osservabile al modello (MU) è pulito. Non registrato.
- Long-only: NKE −0,603 → RANK_LONG_ONLY, corretto.
- Ollama: 0 timeout in RTH prima dell'outage; i 4+4 timeout notturni riguardano il turno off-session.

## 12. Dati mancanti o non accessibili

- Causa della caduta del link NIC e motivo dei 6 h 12 min fra il reboot (15:48) e il boot successivo (22:00): non ricostruibili dal journal.
- Latenza per singola chiamata LLM: non persistita (F-086).
- P&L per strategia: non separabile in modo affidabile in una seduta senza trade. Il WDC giornaliero è stimato dal rendimento dell'alpha-miss.
- Prezzi intraday: feed IEX (SIP non consentito), quindi i controfattuali sono approssimati.
- Segnali e decisioni che la pipeline avrebbe prodotto fra 15:00 e 20:00: inesistenti per costruzione. Il costo dell'outage non è stimabile.

## 13. Raccomandazioni immediate

1. **DAY-001 / F-094**: l'operatore registri nel charter la rottura del 02/10 (sessione coperta fino alle 14:59) e dichiari che le metriche alpha-miss del 02/10 (F-001 68/96, active recall 0/2) sono contaminate dall'outage.
2. **DAY-002 / F-095**: backoff sulla riconnessione WS e tetto ai log persistenti. Va fatto prima del prossimo outage di rete con l'host acceso. Valutare se rimuovere il file da 6,2 GB (decisione dell'operatore).
3. **DAY-001**: heartbeat esterno (dead-man switch) per i cicli in RTH; il canale Telegram sullo stesso host non copre i guasti di rete.
4. F-074: estendere il ticket al ramo sentiment (`market_closed` falso).

## 14. Test o monitor da aggiungere

- Dead-man switch esterno: assenza di `portfolio_cycles` per più di 20 min in RTH → notifica da fuori l'host.
- Test di riconnessione WS con DNS che fallisce: tasso di tentativi e di righe di log limitato.
- Alert sulla dimensione giornaliera dei file in `logs/containers/` e sullo spazio libero del disco (< 15%).
- Campo `session_coverage` (cicli effettivi / attesi) nel dossier e nel report giornaliero.
- Test: clock che solleva un'eccezione → il sentiment non restituisce `market_closed`.

## 15. Ticket tecnici suggeriti

| Ticket | Tipo | Finding |
|---|---|---|
| Heartbeat esterno / dead-man switch dei cicli RTH; alert fuori host | correttezza ops (evidenza) | F-094 |
| Backoff + rate-limit dei log nella riconnessione WS news-stream; tetto di dimensione per i log persistenti | correttezza ops | F-095 |
| Ramo sentiment: `clock_unavailable` invece di `market_closed` | strumentazione | F-074 |

## 16. Stato sistema

| Voce | Valore |
|---|---|
| Host / rete | **NIC giù 14:59:46 → host spento 15:48:07 → boot 22:00:34**. Downtime di rete in RTH: 5 h 00 min (14:59:46–20:00) |
| Ollama Cloud (glm-5.3 + gpt-oss) | **up** fino all'outage (ensemble in ogni ciclo sentiment 13:36–14:59, 0 timeout in RTH). Non raggiungibile da 14:59:54: **5 h 00 min** di RTH senza valutazione LLM, per causa locale e non del provider |
| Ollama per il regime | `kimi-k2.6:cloud` up; **`qwen3.5:cloud` 410 Gone** (2 giri su 2) |
| FinBERT fallback rate | 1/78 segnali (1,3%); 0/0 decisioni d'ordine. Segnali a modello singolo 25/78 (32%) |
| Worker restart | warm shutdown di tutti i container alle 15:48 (reboot dell'host), ripartenza 22:00:48; 2 **hard time limit** (840 s) di `sentiment_shadow` alle 09:29 e 11:29 |
| Telegram | 1 × 400 (14:37, #161 WDC), 3 invii falliti per DNS (15:07/15:22/15:37), polling in errore DNS 14:59–15:48; primo invio OK alle 23:05 |
| Alpaca | clock e trading API irraggiungibili 15:00–15:48 (lato host); nessun ordine nel giorno |
| Disco | `/` all'88% (37 GB liberi), `logs/containers` 6,3 GB, quasi tutti dal file news-stream del 02/10 |
