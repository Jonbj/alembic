# Forensic Daily Report — 2026-10-01

Sessione forense autonoma in sola lettura, eseguita il 2026-10-02. Fuso operativo **UTC** (`src/workers/celery_app.py`:
`timezone="UTC"`, `enable_utc=True`), quindi tutti gli orari di questo report sono UTC. Seduta RTH 13:30–20:00 UTC (EDT).
Il conto **paper** è verificato, non assunto: `ALPACA_BASE_URL=https://paper-api.alpaca.markets` nel container
`worker`, e 86 istantanee su 86 di `portfolio_monitor_snapshots` hanno `broker_environment='paper'`.
`execution.engine=portfolio` (il log riporta «legacy execution worker inactive»). Il 2026-10-01 è il primo giorno
di borsa del mese, quindi in questa seduta è scattato il **ribilanciamento mensile di S1**.

Il periodo di sola osservazione (`docs/evidence/OBSERVATION_CHARTER.md`) aveva come scadenza attesa il 2026-09-28. Il
charter su `origin/main` non registra né la chiusura né una proroga. Di conseguenza questo report **non propone
tarature**: i ticket riguardano solo difetti di correttezza o di strumentazione.

Contesto: tutti i container risultano «Up 5 days», quindi il 2026-10-01 non c'è stata alcuna ricreazione. I log
persistenti coprono l'intera giornata. Per questa data non esistono né `docs/ALPHA_MISS_REPORT_2026-10-01.md` né un
dossier o un file candidates: i costi stimati qui non sono già registrati altrove. Il ledger su `origin/main` arriva
al 2026-09-24 (più un'occorrenza del 25/09). Le sedute dal 25 al 30/09 non sono state analizzate dal ciclo forense.

---

## 1. Executive summary

- Pipeline end-to-end **funzionante**: 246 righe di news scorate (149 URL distinti, 68 ticker), 246 segnali, 24 cicli portfolio tra 14:07 e 19:52, 21 ordini inviati e 21 eseguiti, nessun reject. La riconciliazione broker↔ledger è a 40/40 con quantity_remaining coerente.
- NAV in chiusura **109.826,30 $**, pari a **+54,30 $ (+0,05%)** contro una chiusura precedente di 109.772,00 $. SPY ha fatto circa +0,23% (IEX). Il risultato è in linea con la beta, nessuna perdita anomala.
- **S1 ha ribilanciato** (40 target, congelati fino alla prossima finestra): 5 BUY nuovi (ARM, AZN, IWM, NVDA, TXN) alle 14:07 e 8 SELL `s1_weight_drop` alle 14:22, con P&L netto di vita −342,82 $. **28 rabbocchi S1 sono bloccati da P0-05** e le posizioni restano a circa metà del target (DAY-004).
- **S4: 4 round-trip nella stessa seduta** (INFY, SPCX, MSFT, HOOD), netto −26,98 $. Tutte le uscite sono `below_entry_gate`, subito dopo l'hold minimo; 3 su 4 avvengono con sentiment ancora positivo (DAY-005). Rispetto a un hold fino alla chiusura, oggi le uscite hanno fatto risparmiare 34,03 $.
- **Allucinazione entrata in decisione (DAY-001, nuovo F-091)**: il BUY MSFT nasce da una riga GDELT che contiene solo il titolo. gpt-oss ha inventato una «positive earnings surprise» (event_type `earnings`, conf 0,80) e ha dominato l'ensemble. Il razionale persistito sulla decisione è quella frase falsa.
- **Ledger P&L sbagliato su MS/UNH (DAY-002, F-048)**: la chiusura riscrive `qty` con la sola ultima tranche. Mancano −132,40 $ di realizzato dagli stop già eseguiti, e `quantity_remaining` resta a 3 e 1 su trade chiusi.
- **Regime con un solo LLM da almeno il 25/09 (DAY-003, F-017)**: `qwen3.5:cloud` risponde 410 Gone. Il detector duplica l'altro modello, il controllo di disaccordo è falso per costruzione e nessun alert parte.
- Ollama **su per tutta la seduta**: 4 timeout in RTH (11 nel giorno) e 1 JSON invalido. **0 fallback FinBERT reali**, ma 105 segnali su 246 (42,7%) sono a modello singolo e il worker li dichiara `finbert_fallbacks`.
- Le ricorrenze note restano invariate: primo ciclo alle 14:07, entità HTML nel 69% delle righe Benzinga, `decision_price` NULL, `signal_id` NULL sulle SELL, alert Telegram 400, token del bot nei log (17.282 righe), DECAY CRITICAL solo nel log.

## 2. Verdict

**OK con warning, al limite di «anomalie significative».** Il percorso ordine→fill→posizione è corretto e riconciliato, e non ci sono ordini duplicati, fuori orario o senza decisione. L'affidabilità dell'**evidenza** però ha tre problemi:

1. un segnale allucinato è arrivato fino all'ordine (DAY-001);
2. la serie realizzata di `trades` sottostima le perdite S1 (DAY-002);
3. il moltiplicatore di regime, che scala tutto il sizing, è deciso da un solo modello senza che il sistema lo dica (DAY-003).

Nessuno dei tre ha prodotto perdite rilevanti oggi.

## 3. Timeline del 2026-10-01 (UTC)

| Ora | Componente | Evento | Esito | Fonte |
|---|---|---|---|---|
| 01:31–22:31 | ingest WS | 4.230 `duplicate_id` Benzinga | scartati | `news_queue_drops` |
| 07:00:58 | `detect_regime` | LLM-2 (`qwen3.5:cloud`) «Ollama API error 410: Gone» → regime da LLM-1 solo | sideways ×0,7, «disagreement=False» | log inference r.15200 |
| 10:28:00 | `sentiment_shadow` | SoftTimeLimitExceeded, lotto di 12 item perso | il turno prosegue | log inference r.22323 |
| 13:30:01 | alert | `pipeline:portfolio_cycle_late` critical + `signal_stale` warning | rientrati 14:08 / 13:33 | `mobile_events` |
| 13:30:35 | `detect_regime` | secondo giro, di nuovo LLM-2 410 | sideways ×0,7 | log inference r.29522 |
| 13:32:27–14:17:30 | sentiment | drena la coda notturna: **198 stale** (età mediana 5,3 h) + 163 not_tradable nel giorno | scartati | `news_queue_drops` |
| 13:32:55 | sentiment | primo segnale: BA +0,371 (pubbl. 11:35) | sovrascritto alle 13:56 da +0,132 | 13555 → 13571 |
| 13:49:43 | sentiment | MU +0,424 («Micron is a Beast») | sovrascritto alle 13:57 da +0,183 (DAY-007) | 13564 → 13575 |
| **14:07:01** | `portfolio-cycle` | **primo ciclo (37 min dopo l'apertura)**. **Ribilanciamento S1**: 40 target, `spearman_signal_weight −0,46`, `cap_bound_share 0,75` | **5 BUY S1** (ARM, AZN, IWM, NVDA, TXN) eseguiti; **28 SKIP_PYRAMIDING S1** (DAY-004); isteresi su 13 simboli | decisioni 56658–56662, log r.3940 |
| 14:07:08 | stop sync | IWM: «potential wash trade detected» (lo stop viene creato a ordine BUY ancora aperto) | IWM senza stop fino alle 14:22 | log r.4004 |
| **14:22:01** | S1 → broker | **8 SELL `s1_weight_drop`** (GM, JPM, MS, SBUX, UBS, UNH, VALE, XLF) | eseguite, netto −342,82 $ di vita | decisioni 56819–56826 |
| 14:22:09 | Telegram | alert #161 (WDC −19,4% sub-one-share) | **400 Bad Request** | log worker r.4116 |
| 14:47:06 | sentiment | INFY +0,536 (GDELT, solo titolo: «Accenture Soars 23%… Infosys Jumps 8%») | sopra gate (×1,20 → 0,643) | 13630 |
| **14:52:01** | S4 → broker | **BUY INFY** 133,014 | eseguito @11,39 | 57066 / trade 1046 |
| 15:18:34 | sentiment | SPCX +0,254 × velocity 1,20 = 0,305 | appena sopra gate | 13654 |
| **15:22:01** | S4 → broker | **BUY SPCX** 9,933 | eseguito @152,24 | 57308 / 1047 |
| 15:34:29 | sentiment | **MSFT +0,353**: gpt-oss «Positive earnings surprise» su un titolo GDELT senza corpo (DAY-001) | sopra gate (0,424) | 13661 |
| **15:37:01** | S4 → broker | **BUY MSFT** 2,934 | eseguito @513,26 | 57421 / 1048 |
| 16:37:01 | S4 → broker | **SELL INFY** `below_entry_gate` su **+0,259** | eseguito @11,38 (−2,18 $) | 57894 |
| 17:03:34 | sentiment | LLY +0,306 (orforglipron) | SKIP_PYRAMIDING 17:07–17:37 (detenuta da S1) | 13722 |
| **17:22:01** | S4 → broker | **SELL MSFT** `below_entry_gate` su −0,006 (articolo OpenAI) | eseguito @514,52 (+3,39 $) | 58275 |
| 17:38–17:44 | sentiment | SPCX 0,009 (fan-out «Whale Alerts», 5 ticker), poi SPCX **+0,420 fallback** | il fallback viene ignorato (DAY-006) | 13745 / 13750 |
| **17:52:01** | S4 → broker | **BUY HOOD** 13,576 (+0,325, «Biggest Buying Binge») | eseguito @111,82 | 58531 / 1049 |
| **18:07:01** | S4 → broker | **SELL SPCX** `below_entry_gate` su +0,009 | eseguito @149,77 (−26,13 $) | 58659 |
| 18:23:52 | sentiment | HOOD −0,019 (articolo «Trump threatens Iran») sovrascrive +0,325 | — | 13770 |
| **19:37:01** | S4 → broker | **SELL HOOD** `below_entry_gate` su +0,018 | eseguito @111,73 (−2,06 $) | 59428 |
| 19:52:01 | `portfolio-cycle` | ultimo ciclo in seduta (24 cicli) | — | `portfolio_cycles` |
| 19:58:06 | alert | `system:market_clock` critical (Alpaca clock irraggiungibile) | rientrato 19:59, nessun ciclo perso | `mobile_events`, log worker |
| 20:00 | snapshot | NAV 109.829,39 $, 40 posizioni | — | `portfolio_monitor_snapshots` |
| 21:00:00 | `decay_monitor` | 7 righe **DECAY CRITICAL** (S1/S2/S4: stesso IC −0,014 e stesso Sharpe −6,63) | solo log | log worker |
| 21:35:01 | `reconcile-positions` | 40 `fully_held`, anomalies 0 | — | log worker r.6957 |
| 22:50:00–01 | alert | `portfolio_cycle_session_grid` + `held_no_news_loss:WDC` | **aperti e chiusi in 1 s** | `mobile_events` |

## 4. News ingest

### 4.1 Per fonte

| Fonte | Trasporto | Estrazione | Righe scorate | URL distinti | Ticker | Prima–ultima riga | Lag pubbl.→riga mediano / p90 | Fetched (stats) | Duplicati (stats) | Scartati |
|---|---|---|---|---|---|---|---|---|---|---|
| alpaca_benzinga | ws 222 / rest 5 | source_metadata | 227 | 130 | 68 | 13:32:36–19:59:19 | 1,3 min / 58,6 (REST: 94,6 min) | 871 | **4.230** | 198 stale, 163 not_tradable, 4.230 duplicate_id |
| gdelt_gkg | — | org_lookup | 19 | 19 | 8 | 14:16:19–19:20:21 | 3,5 min / 5,8 | 2.050 | 2 | 2.029 no_ticker, 2 duplicate_content |

- Nessun timestamp futuro (0 righe con `published_at > created_at`) e nessuna riga con `discarded_reason`.
- Fan-out: 30 URL multi-ticker generano 127 righe su 246 (51,6%), con un massimo di 16 ticker («8 Of 11 Sectors Fall In Thursday Trading») (DAY-008).
- Copertura: 68 simboli della watchlist su 96 hanno almeno una news. **12 dei 40 simboli detenuti non ne hanno nessuna**: ASML, AZN, JNJ, MRK, PANW, PBR, RIO, ROKU, SHEL, SNOW, TXN, WDC (DAY-031).
- Sanitizzazione: **156 delle 227 righe Benzinga** contengono entità HTML (`&#39;`, `&amp;`) nel titolo o nel corpo (DAY-020). GDELT: 38 risposte su input «corpo = titolo».
- Nessun buco temporale nell'ingest RTH (`ensemble_cycle_health`: da 5 a 22 cicli in ogni ora 13–19).

### 4.2 Per ticker (top 15 per segnali)

| Ticker | Segnali | Ensemble | Max | Min | Ultimo |
|---|---|---|---|---|---|
| MU | 25 | 16 | +0,424 | −0,240 | −0,120 |
| SPY | 24 | 6 | +0,161 | −0,270 | −0,100 |
| GOOGL | 13 | 8 | +0,267 | −0,103 | −0,044 |
| MSFT | 12 | 9 | +0,353 | −0,120 | −0,078 |
| AMZN | 11 | 7 | +0,260 | −0,085 | −0,085 |
| NVDA | 11 | 6 | +0,211 | −0,360 | −0,053 |
| META | 9 | 4 | +0,066 | −0,140 | +0,066 |
| GS | 7 | 3 | +0,180 | −0,360 | +0,006 |
| BA | 6 | 5 | +0,371 | −0,342 | +0,174 |
| ORCL | 5 | 2 | +0,387 | −0,240 | +0,040 |
| SPCX | 5 | 3 | +0,560 | +0,009 | +0,022 |
| NKE | 5 | 4 | +0,042 | −0,175 | −0,175 |
| INFY | 5 | 4 | +0,536 | +0,014 | +0,014 |
| QQQ | 5 | 2 | +0,189 | −0,090 | +0,040 |
| BAC | 4 | 0 | +0,020 | −0,240 | +0,020 |

### 4.3 Top news per impatto sul segnale

| Segnale | Ticker | Score | News | Esito |
|---|---|---|---|---|
| 13630 | INFY | +0,536 | GDELT «Accenture Soars 23%… Infosys Jumps 8%» (gap già avvenuto: +6,9% in apertura) | BUY 14:52, −2,18 $ (DAY-009) |
| 13661 | MSFT | +0,353 | GDELT «Microsoft's trillion-dollar quarter powered by ravenous AI trade» (solo titolo) | BUY 15:37 su un'«earnings surprise» inventata (DAY-001), +3,39 $ |
| 13654 | SPCX | +0,254 (×1,20) | «What's Going On With SpaceX Stock Thursday?» | BUY 15:22, −26,13 $ |
| 13749 | HOOD | +0,325 | «Robinhood Traders Just Went on Their Biggest Buying Binge Ever» | BUY 17:52, −2,06 $ |
| 13668 | INFY | +0,259 | «Accenture Earnings Lift Software and IT Services Stocks…» (fan-out 4) | SELL INFY su segnale positivo (DAY-005) |
| 13745 | SPCX | +0,009 | «8 Communication Services Stocks With Whale Alerts…» (fan-out 5) | SELL SPCX (DAY-005/006/008) |
| 13722 | LLY | +0,306 | «Eli Lilly's Once-Daily Weight Loss Pill Orforglipron…» | SKIP_PYRAMIDING (DAY-010) |
| 13703 | BA | −0,342 | «FAA Convening Panel on Boeing Software Glitch» | RANK_LONG_ONLY (corretto per design) |
| 13564 | MU | +0,424 | «Micron 'is a Beast'…» | sovrascritto dopo 8 min; MU comunque detenuta |

**Confidenza dell'analisi ingest:** alta per conteggi e lag (dati DB). Media per la copertura per ticker, perché la watchlist è letta da `config/trading.yaml`.

## 5. Performance modelli LLM

| Modello | Risposte | Eleggibili (flag) | Sotto floor 0,40 | Conf. mediana | Polarity media | Pos/Neg/Zero | Timeout (log, giorno / RTH) | Invalid JSON |
|---|---|---|---|---|---|---|---|---|
| glm-5.3:cloud | 245 | 67 | **172 (70,2%)** | 0,30 | +0,063 | 130/78/37 | 1 / 0 | 0 |
| gpt-oss:20b-cloud | 243 | 67 | 80 (32,9%) | 0,50 | +0,059 | 118/77/48 | 10 / 4 | 1 |
| FinBERT (fallback) | 0 | — | — | — | — | — | — | — |

| Percorso del segnale | Segnali | Score medio | Min / Max | Conf. media | ≥ 0,30 | ensemble_std medio |
|---|---|---|---|---|---|---|
| ensemble glm-5.3 + gpt-oss | 141 | +0,059 | −0,342 / +0,536 | 0,39 | 9 | 0,068 |
| single gpt-oss (`fallback_used=t`) | 97 | +0,017 | −0,360 / +0,560 | 0,53 | 6 | 0,107 |
| single glm-5.3 (`fallback_used=t`) | 8 | −0,021 | −0,140 / +0,193 | 0,41 | 0 | 0,100 |

- **Latenza** (durata dei task `run_sentiment_worker` in RTH, 122 task con lavoro): mediana 17,5 s, p90 93,1 s, massimo 186,6 s. Le chiamate Ollama non hanno una telemetria per singola chiamata (F-086), quindi la latenza per modello non è ricostruibile.
- **Disaccordo**: su 242 coppie di risposte, 19 hanno segno opposto e 11 hanno uno spread di p×c ≥ 0,30 (DAY-018). Il segnale MSFT 13661 ha std 0,21 e un modello dominante (gpt-oss p×c 0,56 contro glm 0,18).
- **Eleggibilità**: 74 dei 141 segnali ensemble hanno 0/2 risposte flaggate `eligible` (retry a floor 0, DAY-016).
- **Pesi**: `ensemble:weights:current` = glm 0,593 / gpt-oss 0,407 (source `telegram`). La media pesata riproduce 95 score ensemble su 141; 36 non sono riproducibili né con i pesi uguali né con quelli pesati per confidenza. Non riesco a verificare la formula esatta su quelle righe: lo dichiaro come area non verificata, non come difetto.
- **Enum**: `directness='management'` ×2 (GS 13627, DIS 13748) e `event_type='sector'` ×2, valori fuori dal contratto del prompt (DAY-019).
- **Fallback FinBERT reali**: 0 (`finbert_fallback_events` vuota per la data, tabella attiva dal 2026-09-14). Il task ne dichiara 105 (DAY-017).

Verifica funzionale:
- *Validazione prima del signal store*: c'è il parsing JSON (1 output invalido scartato), ma **mancano** la validazione degli enum e qualsiasi verifica di grounding fra reasoning/event_type e testo sorgente (DAY-001, DAY-019).
- *Varianza alta*: non è un gate d'ingresso (F-037/F-054). Il fallback di divergenza scatta solo con std > 0,40.
- *News duplicate*: la dedup id/content funziona (4.230 + 2). Il fan-out fa però pesare lo stesso articolo su più ticker.
- *Confidence bassa*: riduce lo score (formula p×c) e, sotto 0,40, esclude il modello dalla media pesata.
- *Offline/background*: sì. Tutte le chiamate LLM avvengono nel worker `inference`; i cicli portfolio leggono i segnali dal DB e non c'è alcuna chiamata LLM nel log `worker`.
- *Rischio di allucinazione in decisione*: **si è materializzato** (DAY-001).

## 6. Segnali finali per ticker (che hanno prodotto o bloccato un'azione)

| Ticker | Segnale | Score (× velocity) | Percorso | Gate 0,30 | Esito S4 |
|---|---|---|---|---|---|
| INFY | 13630 | +0,536 (0,643) | ensemble | sopra | SUBMITTED 14:52 |
| SPCX | 13654 | +0,254 (0,305) | ensemble | sopra (solo grazie alla velocity) | SUBMITTED 15:22 |
| MSFT | 13661 | +0,353 (0,424) | ensemble | sopra | SUBMITTED 15:37 |
| HOOD | 13749 | +0,325 (×1,0) | ensemble | sopra | SUBMITTED 17:52 |
| LLY | 13722 / 13520 (30/09) | +0,306 / +0,488 | ensemble | sopra | SKIP_PYRAMIDING (S1 a libro) 12 cicli |
| PANW | 13532 (30/09) | +0,304 | ensemble | sopra | SKIP_PYRAMIDING (S4 a libro) 24 cicli |
| ABBV | 13613 | +0,420 | single gpt-oss | sopra | SKIP_FALLBACK |
| SPCX | 13656 / 13750 | +0,560 / +0,420 | single gpt-oss | sopra | non valutati (preferenza non-fallback, DAY-006) |
| BA | 13703 | −0,342 | ensemble | sopra (ribassista) | RANK_LONG_ONLY |
| ORCL | 13560 | +0,387 | ensemble | sopra | SKIP_ENTRY_FRESHNESS (pubbl. 11:41) |

Esiti degli intenti S4 (`s4_intent_events`, 4.332 righe): CANDIDATE_OBSERVED 2.166, SKIP_ENTRY_FRESHNESS 776, SKIP_ENTRY_GATE 763, SKIP_FALLBACK 442, SKIP_STALE 125, SKIP_PYRAMIDING 36, SKIP_IDEMPOTENCY 17, **SUBMITTED 4**, RANK_LONG_ONLY 3.

## 7. Ordini generati/eseguiti

Ci sono 21 decisioni d'ordine e 21 ordini eseguiti (`filled`). Oltre a questi, 13 stop protettivi `new`/`canceled` gestiti dallo stop sync. Non ci sono reject né ordini senza decisione. Tutti gli ordini sono market, sul broker Alpaca **paper**.

| Ora decisione | Strategia | Ticker | Azione | Qty | Fill | Stato | Rationale / segnale | Risk check | Anomalie |
|---|---|---|---|---|---|---|---|---|---|
| 14:07:01 | S1 | ARM | BUY | 2,0439 | 288,54 | filled | ribilanciamento, peso 0,8% | combiner + regime ×0,7; stop 2 az. | stop parziale (DAY-024) |
| 14:07:01 | S1 | AZN | BUY | 6,3816 | 160,29 | filled | peso 1,4% | stop 6 | — |
| 14:07:01 | S1 | IWM | BUY | 3,7069 | 275,95 | filled | peso 1,4% | stop rifiutato (wash trade), creato 14:22 | DAY-024 |
| 14:07:01 | S1 | NVDA | BUY | 4,4405 | 230,36 | filled | peso 1,4% | stop 4 | — |
| 14:07:01 | S1 | TXN | BUY | 3,6564 | 279,76 | filled | peso 1,4% | stop 3 (14:22) | — |
| 14:22:01 | S1 | GM / JPM / MS / SBUX / UBS / UNH / VALE / XLF | SELL ×8 | posizione intera | 76,74 / 326,56 / 184,57 / 94,48 / 46,85 / 365,10 / 13,26 / 52,97 | filled | `s1_weight_drop` (peso target 0) dopo isteresi a 2 cicli | — | MS/UNH: ledger sbagliato (DAY-002); `signal_id` NULL (DAY-022) |
| 14:52:01 | S4 | INFY | BUY | 133,014 | 11,39 | filled | 13630 +0,536 | gate, freshness, idempotency | entrata dopo il gap (DAY-009) |
| 15:22:01 | S4 | SPCX | BUY | 9,933 | 152,24 | filled | 13654 +0,254×1,2 | idem | — |
| 15:37:01 | S4 | MSFT | BUY | 2,934 | 513,26 | filled | 13661 +0,353 | idem | **allucinazione** (DAY-001) |
| 16:37:01 | S4 | INFY | SELL | 133,014 | 11,38 | filled | `below_entry_gate`, 13668 +0,259 | hold minimo 90 min rispettato | SELL su sentiment positivo (DAY-005) |
| 17:22:01 | S4 | MSFT | SELL | 2,934 | 514,52 | filled | `below_entry_gate`, 13683 −0,006 | idem | — |
| 17:52:01 | S4 | HOOD | BUY | 13,576 | 111,82 | filled | 13749 +0,325 | idem | — |
| 18:07:01 | S4 | SPCX | SELL | 9,933 | 149,77 | filled | `below_entry_gate`, 13745 +0,009 (fan-out) | idem | DAY-005/006/008 |
| 19:37:01 | S4 | HOOD | SELL | 13,576 | 111,73 | filled | `below_entry_gate`, 13796 +0,018 | idem | DAY-005/007 |

Prezzo atteso: `decision_price` è NULL su tutte e 21 le decisioni d'ordine, quindi lo slippage non è misurabile (DAY-021).
`trades.exit_reason` registra `hold_minimum_expiry` per INFY, MSFT e HOOD, mentre la decisione dice `below_entry_gate`:
sono due etichette diverse per la stessa uscita. Non le conto come finding, ma va tenuto presente.

## 8. PnL / rendimento

| Voce | Valore | Fonte / note |
|---|---|---|
| Equity in chiusura 2026-10-01 | 109.826,30 $ | Alpaca portfolio history (timbro 2026-10-02 00:00, cfr. F-053) |
| Variazione giornaliera | **+54,30 $ (+0,049%)** | idem; SPY IEX 762,34 → 764,10 = +0,23% |
| Realizzato S1 (8 chiusure, P&L di vita) | −342,82 $ netto | `trades` 319, 583, 326, 335, 278, 266, 692, 279. **Sottostimato di −132,40 $** (stop MS/UNH esclusi, DAY-002) |
| Contributo del giorno delle chiusure S1 (uscita − chiusura 30/09) | ≈ −41,2 $ | chiusure IEX del 30/09; approssimato |
| Realizzato S4 (4 round-trip) | **−26,98 $** netto (lordo −23,40, costi modellati 3,58) | `trades` 1046–1049 |
| Non realizzato dei nuovi BUY S1 alla chiusura | ≈ +10,8 $ (ARM +7,4, AZN −16,6, IWM +11,5, NVDA +3,0, TXN +5,4) | chiusure IEX |
| Posizioni aperte prima del 01/10 (residuo) | ≈ +111 $ | per differenza, approssimato (prezzi IEX contro mark Alpaca) |
| Per ticker S4 | INFY −2,18 · MSFT +3,39 · SPCX −26,13 · HOOD −2,06 | `trades.net_pnl` |
| Commissioni | 0 $ (Alpaca paper) | i costi in `cost_usd` sono **modellati**, non addebitati |
| Slippage | non misurabile | `decision_price` NULL; `slippage_est` = `cost_usd` (F-015) |

Controfattuale di hold fino alla chiusura sulle uscite S4: INFY +4,66, MSFT +5,31, SPCX +16,59 e HOOD +7,47 $ risparmiati uscendo, in totale **34,03 $**.
Le uscite S1 delle 14:22 sono avvenute vicino al minimo del giorno: tenere fino alla chiusura avrebbe reso circa 71 $ in più.
Questo dipende dal disegno (tempistica del ribilanciamento), non è un difetto.

## 9. Analisi correttezza buy/sell

| Controllo | Esito |
|---|---|
| BUY solo quando consentito | sì: gate, freshness, fallback, idempotency e pyramiding applicati (vedi distribuzione intenti) |
| SELL/exit corrette | sì rispetto alla regola: tutte `below_entry_gate` dopo l'hold minimo. Regola senza banda (DAY-005) |
| Stop-loss | stop sincronizzati; coprono solo le azioni intere (DAY-024); 9–11 posizioni sub-one-share senza stop (WDC −19,4%) |
| Signal flip | non ci sono flip ribassisti; le uscite su segnali ~0 o positivi sono per design (F-013) |
| Hold minimo (90 min) | rispettato: uscite a 105–165 min |
| Rebalance band S1 | il ribilanciamento ha prodotto 13 ordini; **28 rabbocchi bloccati da P0-05** (DAY-004) |
| Ordini duplicati / identici nello stesso minuto | nessuno |
| Roundtrip < 30 min | nessuno (minimo 105 min) |
| Pyramiding (BUY > 3 senza SELL) | nessuno |
| SELL con sentiment positivo (A5) | **sì**: INFY +0,259, SPCX +0,009, HOOD +0,018 (DAY-005) |
| Ordini contrari ravvicinati senza rationale | no: ogni SELL ha un rationale `below_entry_gate` |
| Ticker non consentiti | nessuno, tutti in watchlist |
| Ordini fuori orario | nessuno (14:07–19:37) |
| Trade con dati stale | no: 125 SKIP_STALE + 776 SKIP_ENTRY_FRESHNESS |
| Trade con output LLM non valido | JSON invalido scartato, ma un output **semanticamente falso** è passato (DAY-001) |
| Circuit breaker | non attivato (nessuna condizione) |
| Strategia disabilitata | no; S2 non gira ma il decay monitor la valuta (DAY-028) |
| Paper/live | coerente: paper |
| Idempotenza retry | 17 SKIP_IDEMPOTENCY + 17 log SIGNAL_DUPLICATE_SKIP, nessun doppio ordine |
| Riconciliazione ordini/fill/posizioni | broker 40 = DB 40 posizioni aperte, `quantity_remaining` coerente; **trade chiusi MS/UNH incoerenti** (DAY-002) |
| NO-ORDER (decisione BUY/SELL senza ordine) | 0 su 21 |
| Score < 0,05 con ordine | solo i BUY S1, dove `score` = peso di portafoglio (0,008–0,014), non sentiment: corretto per design |
| fallback su tutti i simboli | no (Ollama su) |

`exit_mechanism`: le righe di oggi sono post-#184 (`below_entry_gate`, `s1_weight_drop` osservati nel motivo). Nessun conteggio su righe pre-fix.

## 10. Anomalie trovate

### [DAY-001] Un'«earnings surprise» inventata da gpt-oss su un titolo GDELT senza corpo apre un BUY MSFT

* Tipo: Bug
* Area: LLM
* Evidenza:
  * file/log/tabella: `sentiment_signals` 13661, `llm_responses` (signal_id 13661), `news_log` (gdelt_gkg, moneycontrol.com), `execution_decisions` 57421, `trades` 1048
  * timestamp: segnale 15:34:29, BUY 15:37:01, SELL 17:22:01
  * snippet/query: corpo = titolo («Microsoft's trillion-dollar quarter powered by ravenous AI trade»). gpt-oss: p=0,7, c=0,8, `event_type=earnings`, reasoning «Positive earnings surprise driven by AI growth boosts MSFT's revenue…». glm-5.3: p=0,4, c=0,45, `event_type=other`, «a market-cap milestone is backward-looking». Score 0,353 × 1,20 = 0,424
* Descrizione: MSFT non ha riportato utili il 01/10. Il titolo parla di capitalizzazione. gpt-oss attribuisce un evento che non c'è nel testo, con confidenza 0,80, e il suo p×c (0,56) trascina l'ensemble sopra il gate; glm da solo valeva 0,18. Il razionale persistito sulla decisione d'ordine è proprio la frase inventata. Nessun controllo confronta event_type o reasoning con il testo sorgente: il «Supervisor agent» e la verifica RAG richiesti dal CLAUDE.md non esistono sul percorso live.
* Impatto: un'allucinazione arriva all'ordine (1.506 $). Oggi il trade ha chiuso a +3,39 $, ma il canale è aperto, ed è peggiore su GDELT, dove 38 risposte su 38 hanno input di solo titolo.
* Severità: High
* Confidenza: High
* Azione consigliata: ticket di correttezza. Prima di ammettere il segnale al ranking, un controllo deterministico: event_type `earnings`/`guidance` solo se il testo contiene lessico pertinente; per input di solo titolo, cap o esclusione.
* Test/monitor consigliato: monitor giornaliero sui segnali sopra gate con `event_type` non supportato da parole chiave del testo; test con un input «trillion-dollar quarter» senza corpo.

### [DAY-002] La chiusura riscrive `trades.qty` con la sola ultima tranche: il realizzato degli stop MS/UNH sparisce e `quantity_remaining` resta > 0 su trade chiusi

* Tipo: Bug
* Area: PnL
* Evidenza:
  * file/log/tabella: `trades` 266 (MS) e 279 (UNH); ordini Alpaca `9cd77d50` (stop MS 3 az. @196,08, 2026-09-24 13:37) e `7dfce59d` (stop UNH 1 az. @376,31, 2026-09-11 18:46); `src/store/pg_store.py` (riconciliazione exit, `UPDATE trades SET … qty = %s … quantity_remaining = GREATEST(0, qty - %s)`)
  * timestamp: SELL 14:22:06/07
  * snippet/query: trade 266 `qty 0,0528, quantity_remaining 3,0000, net_pnl −2,39`; trade 279 `qty 0,5926, quantity_remaining 1,0000, net_pnl −37,43`; `exit_order_ids` contiene solo la market SELL finale
* Descrizione: alla chiusura la riconciliazione aggrega soltanto gli ordini in `exit_order_ids`, che non includono gli stop eseguiti in precedenza, e sovrascrive `qty` con la quantità di quella tranche. Nella stessa UPDATE, `quantity_remaining = GREATEST(0, qty − x)` legge il **vecchio** `qty` (3,0528 / 1,5926), per cui sui trade chiusi restano 3 e 1 azioni «residue».
* Impatto: il P&L realizzato S1 non registra −81,06 $ (MS: (196,08 − 223,10) × 3) e −51,34 $ (UNH: (376,31 − 427,65) × 1), in totale **−132,40 $**. Qualunque metrica per sleeve letta da `trades` è distorta; il resto del ledger mostra «posizioni» fantasma.
* Severità: High
* Confidenza: High
* Azione consigliata: ticket di correttezza. Includere negli exit fill gli stop eseguiti e calcolare `quantity_remaining` con il nuovo valore. Il backfill dei trade già chiusi va deciso dall'operatore.
* Test/monitor consigliato: invariante giornaliera `exit_time IS NOT NULL ⇒ quantity_remaining = 0` e Σ fill SELL broker = qty d'ingresso.

### [DAY-003] Il regime è deciso da un solo LLM da almeno il 2026-09-25: `qwen3.5:cloud` risponde 410 Gone e nessun alert parte

* Tipo: Rischio
* Area: Risk
* Evidenza:
  * file/log/tabella: `logs/containers/worker-inference-2026-10-01.log` r.15200, r.29522; `src/workers/regime.py` (ramo «LLM-2 failed … r2 = r1»); default `REGIME_LLM_MODEL_2=qwen3.5:cloud` (`src/config.py:377`, nessun override nell'env del container)
  * timestamp: 07:00:58, 13:30:35 (stesso errore il 25/09, 28/09, 29/09 e 30/09)
  * snippet/query: `LLM-2 failed in regime detection: Ollama API error 410: Gone` → `Regime detected: sideways (×0.7), disagreement=False` → task `succeeded`
* Descrizione: il modello è stato ritirato da Ollama Cloud. Il detector, quando LLM-2 fallisce, copia LLM-1 (`r2 = r1`). Il controllo di disaccordo diventa così falso per costruzione, mentre il task risulta riuscito. L'alert Telegram parte solo con dati «partial» o con entrambi i modelli giù.
* Impatto: il moltiplicatore che scala tutto il sizing (×0,7) dipende da un solo modello da almeno 5 sedute, e la serie osservata non lo dichiara.
* Severità: Medium
* Confidenza: High
* Azione consigliata: alert su fallimento persistente di un singolo modello del regime. Annotare la discontinuità nel charter. La scelta del modello sostitutivo spetta all'operatore.
* Test/monitor consigliato: contatore Redis dei fallimenti per modello di regime, con alert dopo 2 giri consecutivi.

### [DAY-004] Il ribilanciamento mensile S1 non può rabboccare: 28 posizioni restano a circa metà del target per P0-05

* Tipo: Anomalia
* Area: Risk
* Evidenza:
  * file/log/tabella: `execution_decisions` SKIP_PYRAMIDING 14:07:07 (28 righe, `signal_id` NULL); `strategy_rebalance_snapshots` rebalance_ts 2026-10-01 14:07:00.599
  * timestamp: 14:07:07
  * snippet/query: «P0-05 anti-pyramiding: gia' a libro dal 2026-07-14, peso target 1.4%, target $1482.99, posizione $67…»; NOK target 1.134,20 $ contro una posizione di 5,96 $; AMAT 1.158 contro 452; DELL 905 contro 484
* Descrizione: il guard anti-pyramiding blocca qualunque BUY su un simbolo con un trade aperto, anche il rabbocco di S1 verso il proprio target. S1 può aprire nomi nuovi e chiudere quelli usciti, ma non ridimensionare quelli già in portafoglio. Le posizioni restano congelate fino al prossimo ribilanciamento, che si bloccherà allo stesso modo.
* Impatto: S1 opera strutturalmente sottopeso rispetto al proprio disegno (circa 36 k$ investiti su 110 k$ di NAV). La serie di rendimento S1 non misura la strategia dichiarata.
* Severità: Medium
* Confidenza: High
* Azione consigliata: va deciso a design se P0-05 debba applicarsi ai rabbocchi di ribilanciamento di S1. È una questione di correttezza della misura, non di taratura.
* Test/monitor consigliato: metrica al ribilanciamento, Σ |target − posizione| bloccato da P0-05.

### [DAY-005] Quattro round-trip S4 nella stessa seduta; tre uscite su sentiment ancora positivo

* Tipo: Anomalia
* Area: Signal
* Evidenza:
  * file/log/tabella: `execution_decisions` 57894, 58275, 58659, 59428; `trades` 1046–1049
  * timestamp: 16:37, 17:22, 18:07, 19:37
  * snippet/query: «[below_entry_gate] … score=+0.259» (INFY), «+0.009» (SPCX), «+0.018» (HOOD), «−0.006» (MSFT)
* Descrizione: senza una banda fra il gate d'ingresso 0,30 e l'uscita, ogni posizione S4 esce al primo ciclo utile dopo l'hold minimo, appena l'ultimo segnale scende sotto 0,30, anche se positivo.
* Impatto: −26,98 $ realizzati. Oggi uscire ha fatto risparmiare 34,03 $ rispetto a un hold fino alla chiusura (INFY 4,66, MSFT 5,31, SPCX 16,59, HOOD 7,47). La regola produce comunque turnover puro: 8 ordini e 3,58 $ di costi modellati per 4 posizioni rimaste aperte meno di 3 ore.
* Severità: Medium
* Confidenza: High
* Azione consigliata: nessuna taratura in periodo di osservazione. Registrare la ricorrenza.
* Test/monitor consigliato: contatore giornaliero dei round-trip S4 nella stessa seduta e delle SELL con score > 0.

### [DAY-006] Il segnale fallback SPCX +0,420 viene ignorato a favore di un segnale ensemble più vecchio a +0,009

* Tipo: Anomalia
* Area: Signal
* Evidenza:
  * file/log/tabella: `sentiment_signals` 13745 (17:38, ensemble, +0,009, fan-out 5) e 13750 (17:44, single gpt-oss, +0,420); `execution_decisions` 58659
  * timestamp: 18:07:01
  * snippet/query: SELL SPCX «generated 2026-10-01 17:38 UTC, score=+0.009»
* Descrizione: `fetch_signals_for_cycle` preferisce sempre il segnale non-fallback, anche se è più vecchio e debole. L'uscita SPCX si basa su un roundup generico, mentre il segnale più recente e specifico era fortemente positivo.
* Impatto: il costo è già contato in DAY-005. È anche un caso in cui la regola ha preso la decisione giusta per la ragione sbagliata: SPCX ha chiuso a 148,10.
* Severità: Low
* Confidenza: High
* Azione consigliata: solo ricorrenza.
* Test/monitor consigliato: log del segnale effettivamente usato per ogni SELL (vedi DAY-022).

### [DAY-007] Un segnale forte viene sovrascritto da uno debole pochi minuti dopo (MU, HOOD)

* Tipo: Anomalia
* Area: Signal
* Evidenza:
  * file/log/tabella: `sentiment_signals` MU 13564 +0,424 (13:49:43) → 13575 +0,183 (13:57:10); HOOD 13749 +0,325 (17:44) → 13770 −0,019 (18:23, «As Trump Threatens Iran…») → 13796 +0,018 (19:34)
  * timestamp: vedi sopra
  * snippet/query: MU 13564 non ha alcuna riga in `s4_intent_events`
* Descrizione: S4 usa solo l'ultimo segnale per simbolo. MU era comunque detenuta (nessun effetto). HOOD è uscita su segnali macro o generici dopo l'ingresso su notizia specifica.
* Impatto: costo già contato in DAY-005.
* Severità: Medium
* Confidenza: High
* Azione consigliata: solo ricorrenza.
* Test/monitor consigliato: conteggio dei segnali ≥ 0,30 sovrascritti entro 30 min da uno < 0,30.

### [DAY-008] Gli articoli fan-out multi-ticker sono metà delle righe scorate e guidano un'uscita

* Tipo: Anomalia
* Area: News
* Evidenza:
  * file/log/tabella: `news_log` del 01/10 (149 URL → 246 righe; 30 URL multi-ticker → 127 righe, massimo 16); log `worker-news-stream`
  * timestamp: tutta la seduta
  * snippet/query: «8 Of 11 Sectors Fall In Thursday Trading» ×16; uscita SPCX su «8 Communication Services Stocks With Whale Alerts» (5 ticker); INFY esce su «Accenture Earnings Lift Software and IT Services Stocks…» (4 ticker)
* Descrizione: articoli che non riguardano direttamente l'emittente producono segnali sul ticker e determinano le uscite.
* Impatto: rumore nel segnale d'uscita; costo già contato in DAY-005.
* Severità: Medium
* Confidenza: High
* Azione consigliata: solo ricorrenza.
* Test/monitor consigliato: quota giornaliera delle righe fan-out e delle uscite generate da righe fan-out.

### [DAY-009] Ingresso INFY dopo il movimento: il titolo stesso dice «Infosys Jumps 8%»

* Tipo: Anomalia
* Area: Signal
* Evidenza:
  * file/log/tabella: `sentiment_signals` 13630 (GDELT, pubbl. 14:45, scorato 14:47); `trades` 1046; barre giornaliere IEX INFY (chiusura 30/09 10,725, apertura 01/10 11,465, chiusura 11,345)
  * timestamp: BUY 14:52 @11,39
  * snippet/query: «Accenture Soars 23%… Infosys Jumps 8%»
* Descrizione: la notizia arriva a gap già fatto (+6,9% in apertura). L'ingresso a 11,39 sta vicino al massimo del movimento, e il titolo ha poi chiuso a 11,345.
* Impatto: trade 1046 a −2,18 $ netti (misurata).
* Severità: Low
* Confidenza: High
* Azione consigliata: solo ricorrenza.
* Test/monitor consigliato: quota del movimento precedente al segnale, già nel dossier alpha-miss.

### [DAY-010] LLY +0,306 bloccato da P0-05 perché detenuto da S1

* Tipo: Anomalia
* Area: Orders
* Evidenza:
  * file/log/tabella: `s4_intent_events` SKIP_PYRAMIDING LLY (13722 ×3, 17:07–17:37; 13520 del 30/09 ×9, 14:07–16:07); `execution_decisions` SKIP_PYRAMIDING 17:07:06
  * timestamp: 17:07–17:37
  * snippet/query: `s1_state {"origin":"S1","held_by_s1":true}`
* Descrizione: un segnale S4 sopra gate su un titolo detenuto da S1 non può aumentare l'esposizione.
* Impatto: congetturale. LLY 17:00 (barra 15 min) 1.149,15 → 19:45 1.150,63 = +0,13% su 2.200 $ ≈ **2,83 $** non catturati.
* Severità: Low
* Confidenza: Medium
* Azione consigliata: solo ricorrenza.
* Test/monitor consigliato: già nel dossier.

### [DAY-011] SKIP_PYRAMIDING: 36 intenti, una sola riga in `execution_decisions`

* Tipo: Anomalia
* Area: Data
* Evidenza:
  * file/log/tabella: `s4_intent_events` (PANW 13532 ×24, LLY 13520 ×9, LLY 13722 ×3) contro `execution_decisions` S4 SKIP_PYRAMIDING = 1 (LLY 17:07)
  * timestamp: 14:07–19:52
  * snippet/query: log «P0-05 pyramiding guard: skipping BUY for PANW» ×24, «LLY» ×12
* Descrizione: la chiave di dedup senza il giorno fa sì che i segnali del 30/09 non lascino alcuna riga il 01/10.
* Impatto: costo non stimabile. La tabella delle decisioni sottoconta i blocchi.
* Severità: Low
* Confidenza: High
* Azione consigliata: solo ricorrenza.
* Test/monitor consigliato: confronto giornaliero intenti/righe.

### [DAY-012] Le posizioni S4 entrano nel nuovo target S1 e l'uscita S4 segnalata dall'isteresi non parte

* Tipo: Anomalia
* Area: Risk
* Evidenza:
  * file/log/tabella: log 14:07:07 «Exit hysteresis (2 cycles): held 13 position(s) flagged for exit: ['CSCO', 'GM', 'INTC', 'JPM', 'MRVL', 'MS', 'MU', 'QQQ', …]»; `strategy_rebalance_snapshots` CSCO/INTC/MRVL/MU/QQQ/PANW/WDC `in_target=t`; `trades` aperti con `stop_strategy='S4'`
  * timestamp: 14:07–14:22
  * snippet/query: alle 14:22 vengono vendute solo le 8 posizioni S1 a peso 0; CSCO, INTC, MRVL, MU e QQQ restano
* Descrizione: il ribilanciamento S1 ha incluso 7 posizioni S4 nel proprio target congelato per un mese. L'uscita per regola S4 resta bloccata dal peso S1, mentre trade e P&L restano attribuiti a S4.
* Impatto: costo non stimabile. Per un altro mese l'attribuzione per sleeve di 7 posizioni è ambigua.
* Severità: Medium
* Confidenza: High
* Azione consigliata: solo ricorrenza (decisione di design aperta su F-089).
* Test/monitor consigliato: conteggio delle posizioni con proprietario del trade ≠ strategia che le tiene a target.

### [DAY-013] Primo ciclo portfolio 37 minuti dopo l'apertura

* Tipo: Anomalia
* Area: Ops
* Evidenza:
  * file/log/tabella: `portfolio_cycles` (min 14:07:01); `mobile_events` `pipeline:portfolio_cycle_late` 13:30:01 → 14:08:01
  * timestamp: 13:30–14:07
  * snippet/query: 24 cicli tra 14:07 e 19:52
* Descrizione: le finestre beat a ora UTC fissa non seguono l'EDT. BA +0,371 (13:32) e MU +0,424 (13:49) nascono prima del primo ciclo e vengono sovrascritti.
* Impatto: costo non stimabile oggi (BA era già oltre la finestra di freshness, MU era detenuta).
* Severità: Medium
* Confidenza: High
* Azione consigliata: solo ricorrenza.
* Test/monitor consigliato: già attivo (`portfolio_cycle_late`).

### [DAY-014] 198 articoli WS accodati fuori seduta e scartati stale all'apertura

* Tipo: Anomalia
* Area: News
* Evidenza:
  * file/log/tabella: `news_queue_drops` `stale` 198 (13:32:27–14:17:30, età mediana 5,3 h); task 13:33:44 `skipped_stale: 185`
  * timestamp: 13:32–14:17
  * snippet/query: vedi sopra
* Descrizione: lo stream ingerisce 24/7 in una coda che si consuma solo in seduta.
* Impatto: lavoro sprecato; costo non stimabile.
* Severità: Low
* Confidenza: High
* Azione consigliata: solo ricorrenza.
* Test/monitor consigliato: `stale_drop_metrics_daily`.

### [DAY-015] `ingestion_stats_daily`: duplicates 4.230 contro fetched 871 per alpaca_benzinga

* Tipo: Anomalia
* Area: Data
* Evidenza:
  * file/log/tabella: `ingestion_stats_daily` day=2026-10-01
  * timestamp: aggiornato 22:31:42
  * snippet/query: `fetched 871, queued 576, duplicates 4230`
* Descrizione: il contatore additivo conta più volte le stesse consegne.
* Impatto: metrica di ingest inutilizzabile; costo non stimabile.
* Severità: Low
* Confidenza: High
* Azione consigliata: solo ricorrenza.
* Test/monitor consigliato: invariante `duplicates ≤ fetched` per fonte/giorno.

### [DAY-016] 74 dei 141 segnali ensemble hanno 0/2 risposte flaggate `eligible`

* Tipo: Anomalia
* Area: LLM
* Evidenza:
  * file/log/tabella: `llm_responses` join `sentiment_signals`
  * timestamp: tutta la seduta
  * snippet/query: ensemble con e=0: 74, e=2: 67; single con e=0: 105
* Descrizione: il retry a floor 0 usa contributori che il flag dichiara non eleggibili.
* Impatto: le statistiche per modello calcolate su `eligible` sono sbagliate; costo non stimabile.
* Severità: Low
* Confidenza: High
* Azione consigliata: solo ricorrenza.
* Test/monitor consigliato: già noto (F-010).

### [DAY-017] Il task sentiment dichiara 105 `finbert_fallbacks` con 0 eventi FinBERT reali

* Tipo: Anomalia
* Area: Ops
* Evidenza:
  * file/log/tabella: log inference (Σ `'finbert_fallbacks'` = 105 su 100 righe di esito); `finbert_fallback_events` 0 righe per la data
  * timestamp: tutta la seduta
  * snippet/query: `{'processed': 5, 'ensemble_success': 4, 'finbert_fallbacks': 1, …}` alle 13:33:44
* Descrizione: le letture a modello singolo sono contate come fallback FinBERT.
* Impatto: telemetria del fallback fuorviante; costo non stimabile.
* Severità: Low
* Confidenza: High
* Azione consigliata: solo ricorrenza.
* Test/monitor consigliato: già noto (F-078).

### [DAY-018] 19 coppie di risposte di segno opposto e 11 con spread ≥ 0,30, senza alcun gate di varianza

* Tipo: Rischio
* Area: LLM
* Evidenza:
  * file/log/tabella: `llm_responses` self-join per `signal_id`
  * timestamp: tutta la seduta
  * snippet/query: 242 coppie, 19 di segno opposto, 11 con |Δ p×c| ≥ 0,30; 43 segnali ensemble con `ensemble_std = 0`
* Descrizione: l'ensemble non tratta il disaccordo sotto la soglia di divergenza 0,40, come si vede nel caso MSFT (DAY-001).
* Impatto: costo non stimabile oltre DAY-001.
* Severità: Low
* Confidenza: High
* Azione consigliata: solo ricorrenza.
* Test/monitor consigliato: già noto (F-054).

### [DAY-019] Valori fuori enum persistiti: `directness='management'`, `event_type='sector'`

* Tipo: Anomalia
* Area: LLM
* Evidenza:
  * file/log/tabella: `llm_responses` 23113 (GS, signal 13627), 23355 (DIS, 13748); `event_type='sector'` ×2
  * timestamp: seduta
  * snippet/query: contratto del prompt in `src/workers/sentiment.py:305`
* Descrizione: l'output strutturato non viene validato contro l'enum.
* Impatto: 4 righe su 488; costo non stimabile.
* Severità: Low
* Confidenza: High
* Azione consigliata: solo ricorrenza.
* Test/monitor consigliato: `src/analysis/schema_drift.py` giornaliero.

### [DAY-020] Entità HTML non decodificate nel 69% delle righe Benzinga

* Tipo: Bug
* Area: News
* Evidenza:
  * file/log/tabella: `news_log` alpaca_benzinga 156/227 con `&#39;`/`&amp;`; log `worker-news-stream`
  * timestamp: seduta
  * snippet/query: «What&#39;s Going On With SpaceX Stock Thursday?» (segnale 13654, poi BUY)
* Descrizione: `sanitize_text` non decodifica le entità.
* Impatto: input al modello sporco; costo non stimabile.
* Severità: Medium
* Confidenza: High
* Azione consigliata: solo ricorrenza (fix esente dal freeze, già individuato).
* Test/monitor consigliato: conteggio giornaliero delle righe con entità.

### [DAY-021] `decision_price` NULL su tutte le decisioni d'ordine; `slippage_est` = `cost_usd`

* Tipo: Anomalia
* Area: Orders
* Evidenza:
  * file/log/tabella: `execution_decisions` BUY/SELL 21/21 con `decision_price` NULL; `trades` 1041–1049 `slippage_est = cost_usd`
  * timestamp: seduta
  * snippet/query: `count(decision_price)=0` su BUY e SELL
* Descrizione: la qualità d'esecuzione non è misurata.
* Impatto: slippage non ricostruibile; costo non stimabile.
* Severità: Medium
* Confidenza: High
* Azione consigliata: solo ricorrenza.
* Test/monitor consigliato: già noto (F-015).

### [DAY-022] `signal_id` NULL su tutte le 12 SELL

* Tipo: Anomalia
* Area: Data
* Evidenza:
  * file/log/tabella: `execution_decisions` SELL 12/12 senza `signal_id`
  * timestamp: 14:22, 16:37, 17:22, 18:07, 19:37
  * snippet/query: il segnale d'uscita si ricava solo dal testo (`generated … score=`)
* Descrizione: la catena segnale→uscita non è ricostruibile per chiave esterna.
* Impatto: audit delle uscite manuale; costo non stimabile.
* Severità: Medium
* Confidenza: High
* Azione consigliata: solo ricorrenza.
* Test/monitor consigliato: già noto (F-011).

### [DAY-023] Telemetria del ciclo: `orders_count` 102 contro 21 ordini inviati

* Tipo: Anomalia
* Area: Ops
* Evidenza:
  * file/log/tabella: `portfolio_cycles` (24 cicli, Σ orders_count 102); log 16:37:06 «Hold minimum (90 min): skipped 1 SELL order(s) for recently-bought: ['MSFT', 'SPCX']»
  * timestamp: seduta
  * snippet/query: vedi sopra
* Descrizione: il contatore misura gli ordini target, e il log dell'hold minimo elenca i candidati invece dei soli scartati.
* Impatto: costo non stimabile.
* Severità: Low
* Confidenza: High
* Azione consigliata: solo ricorrenza.
* Test/monitor consigliato: già noto (F-014).

### [DAY-024] Stop protettivi solo sulle azioni intere; IWM senza stop per 15 minuti (wash trade); WDC −19,4% senza protezione

* Tipo: Rischio
* Area: Risk
* Evidenza:
  * file/log/tabella: ordini stop 14:07–14:22 (TXN 3/3,656, IWM 3/3,707, ARM 2/2,044, NVDA 4/4,440, AZN 6/6,382); log 14:07:08 «IWM … potential wash trade detected»; 24× «#161: WDC unprotected at −19.4% (qty 0.3347, status sub_one_share)»
  * timestamp: 14:07–19:52
  * snippet/query: vedi sopra
* Descrizione: la quota frazionaria non è coperta, e lo stop viene creato nello stesso ciclo del BUY, quando l'ordine d'ingresso è ancora aperto.
* Impatto: costo non stimabile.
* Severità: Medium
* Confidenza: High
* Azione consigliata: solo ricorrenza.
* Test/monitor consigliato: già noto (F-022).

### [DAY-025] Alert Telegram #161 rifiutato con 400 Bad Request

* Tipo: Anomalia
* Area: Ops
* Evidenza:
  * file/log/tabella: `worker-2026-10-01.log` r.4116
  * timestamp: 14:22:09
  * snippet/query: «TelegramNotifier: Failed to send alert: Client error '400 Bad Request'»
* Descrizione: l'alert WDC sub-one-share non viene consegnato.
* Impatto: costo non stimabile.
* Severità: Medium
* Confidenza: High
* Azione consigliata: solo ricorrenza.
* Test/monitor consigliato: già noto (F-005).

### [DAY-026] Il token del bot Telegram è in chiaro in 17.282 righe di log

* Tipo: Rischio
* Area: Ops
* Evidenza:
  * file/log/tabella: `worker-inference-2026-10-01.log` 17.278 righe, `worker-2026-10-01.log` 4 righe
  * timestamp: tutto il giorno
  * snippet/query: `grep -c "api.telegram.org/bot[0-9]"`
* Descrizione: httpx logga a livello INFO l'URL completo.
* Impatto: credenziale esposta nei log persistenti; costo non stimabile.
* Severità: High
* Confidenza: High
* Azione consigliata: solo ricorrenza (ruotare il token è un'azione dell'operatore).
* Test/monitor consigliato: già noto (F-018).

### [DAY-027] Fetch del benchmark SPY fallito 84 volte (limite SIP), nessun alert

* Tipo: Anomalia
* Area: Data
* Evidenza:
  * file/log/tabella: `worker-2026-10-01.log`
  * timestamp: seduta
  * snippet/query: «SPY benchmark fetch failed: subscription does not permit querying recent SIP data» ×84
* Descrizione: il guasto è permanente e silenzioso.
* Impatto: costo non stimabile.
* Severità: Low
* Confidenza: High
* Azione consigliata: solo ricorrenza.
* Test/monitor consigliato: già noto (F-016).

### [DAY-028] Il decay monitor dà S1, S2 e S4 con lo stesso IC −0,014 e lo stesso Sharpe −6,63

* Tipo: Anomalia
* Area: Risk
* Evidenza:
  * file/log/tabella: `worker-2026-10-01.log` 21:00:00
  * timestamp: 21:00:00
  * snippet/query: «DECAY CRITICAL [S1]: IC dropped 141% from 0.035 to -0.014», «[S2] … 0.042 to -0.014», «[S4] … 0.028 to -0.014»
* Descrizione: confronta metriche globali della pipeline con baseline per strategia, compresa S2, che non gira.
* Impatto: costo non stimabile.
* Severità: Low
* Confidenza: High
* Azione consigliata: solo ricorrenza.
* Test/monitor consigliato: già noto (F-004).

### [DAY-029] 7 DECAY CRITICAL scritti solo nel log, nessuna riga in `mobile_events`

* Tipo: Anomalia
* Area: Ops
* Evidenza:
  * file/log/tabella: log worker 21:00; `mobile_events` del giorno (5 righe, nessuna di decay)
  * timestamp: 21:00
  * snippet/query: vedi sopra
* Descrizione: gli alert critici del decay monitor non hanno alcun canale di consegna.
* Impatto: costo non stimabile.
* Severità: Medium
* Confidenza: High
* Azione consigliata: solo ricorrenza.
* Test/monitor consigliato: già noto (F-062).

### [DAY-030] Gli incidenti di griglia e di copertura WDC si aprono e si chiudono nello stesso secondo

* Tipo: Anomalia
* Area: Ops
* Evidenza:
  * file/log/tabella: `mobile_events` `pipeline:portfolio_cycle_session_grid` 22:50:00 → 22:50:01, `coverage:held_no_news_loss:WDC` 22:50:01 → 22:50:01
  * timestamp: 22:50
  * snippet/query: vedi sopra
* Descrizione: il valutatore generico chiude gli incidenti dei job specifici.
* Impatto: costo non stimabile.
* Severità: Low
* Confidenza: High
* Azione consigliata: solo ricorrenza.
* Test/monitor consigliato: già noto (F-058).

### [DAY-031] 28 simboli della watchlist su 96 senza news, e 12 dei 40 detenuti

* Tipo: Anomalia
* Area: News
* Evidenza:
  * file/log/tabella: `news_log` del giorno contro `config/trading.yaml` `symbols.watchlist`
  * timestamp: giorno
  * snippet/query: detenuti senza news: ASML, AZN, JNJ, MRK, PANW, PBR, RIO, ROKU, SHEL, SNOW, TXN, WDC
* Descrizione: la copertura delle news resta bassa.
* Impatto: costo non stimabile.
* Severità: Low
* Confidenza: Medium
* Azione consigliata: solo ricorrenza.
* Test/monitor consigliato: già noto (F-001).

### [DAY-032] `/api/trades` restituisce una riga per ordine broker con `net_pnl` sempre nullo

* Tipo: Anomalia
* Area: Frontend
* Evidenza:
  * file/log/tabella: `GET /api/trades?limit=200`, 21 righe del 01/10
  * timestamp: —
  * snippet/query: SELL HOOD `entry_price None, exit_price 111.73, net_pnl None`; BUY HOOD `entry_price 111.82, exit_price None`
* Descrizione: l'endpoint non espone il ledger dei trade.
* Impatto: l'analisi via API non basta per il P&L; costo non stimabile.
* Severità: Low
* Confidenza: High
* Azione consigliata: solo ricorrenza.
* Test/monitor consigliato: già noto (F-084).

## 11. False positive o aree risultate corrette

- Paper/live: paper, verificato tramite env e 86 snapshot.
- Nessun ordine duplicato, nessun roundtrip < 30 min, nessun pyramiding, nessun ordine fuori orario, nessun NO-ORDER.
- Idempotenza: 17 SKIP_IDEMPOTENCY e nessun doppio invio.
- Riconciliazione delle posizioni aperte: broker 40 = DB 40 e `quantity_remaining` coerente con il broker (NOK 0,564, WDC 0,335). `reconcile-positions` 40 `fully_held`, 0 anomalie.
- Ribilanciamento S1 eseguito nella finestra prevista: chiusure differite di un ciclo dall'isteresi, come da disegno.
- Freshness e stale: 776 SKIP_ENTRY_FRESHNESS e 125 SKIP_STALE, nessun ingresso su segnali vecchi (ORCL +0,387 pubblicato alle 11:41 correttamente escluso).
- Long-only: BA −0,342 non genera short (RANK_LONG_ONLY).
- `market_clock` critical alle 19:58: rientrato in 1 min, nessun ciclo perso (24 su 24). Non lo conto come finding.
- Nessuna ricreazione di container: niente job persi per SIGTERM.
- Le righe `OBSERVE_LATE_ENTRY` (1.958) e `SHADOW_LATE_ENTRY` (208) sono misure osservazionali previste (#512), non decisioni operative.

## 12. Dati mancanti o non accessibili

- Latenza per singola chiamata e per modello: non persistita (F-086). Disponibile solo la durata dei task.
- 36 score ensemble su 141 non riproducibili con le formule di aggregazione testate (pesi uguali, 0,593/0,407, pesatura per confidenza). Servirebbe il dettaglio dei pesi effettivi per segnale.
- Prezzi di chiusura: ho usato il feed IEX (le chiusure SIP non sono consentite dall'abbonamento), quindi le cifre di P&L per differenza sono approssimate.
- Prezzo atteso al momento della decisione: assente (`decision_price` NULL), slippage non misurabile.
- Le sedute dal 25 al 30/09 non sono state analizzate dal ciclo forense: la data esatta di inizio del 410 su `qwen3.5:cloud` è ≤ 2026-09-25, ricavata dai log persistenti.

## 13. Raccomandazioni immediate

1. **DAY-001 / F-091**: aprire un ticket per un controllo di grounding deterministico su event_type/reasoning prima del ranking S4. Va almeno escluso dall'ingresso l'input di solo titolo con event_type `earnings`/`guidance`.
2. **DAY-002 / F-048**: correggere la riconciliazione degli exit (includere gli stop eseguiti, `quantity_remaining` calcolato sul nuovo `qty`). Senza questa correzione la serie realizzata per sleeve è sbagliata. Backfill e discontinuità vanno registrati nel charter dall'operatore.
3. **DAY-003 / F-017**: l'operatore deve sostituire `REGIME_LLM_MODEL_2`, registrare la discontinuità dal 25/09 e aggiungere un alert per il singolo modello di regime fallito.
4. **DAY-004**: decisione di design su P0-05 contro il ribilanciamento S1.
5. Charter: registrare l'esito della scadenza del 2026-09-28 (chiusura o proroga). Oggi non è scritto da nessuna parte.

## 14. Test o monitor da aggiungere

- Invariante `exit_time IS NOT NULL ⇒ quantity_remaining = 0` e Σ fill SELL broker = qty d'ingresso per trade.
- Test di grounding: un titolo «trillion-dollar quarter» senza corpo non deve produrre un segnale ammesso con `event_type=earnings`.
- Monitor dei fallimenti per modello di regime, con alert dopo 2 giri consecutivi.
- Metrica al ribilanciamento S1: notional bloccato da P0-05.
- Contatore dei round-trip S4 nella stessa seduta e delle SELL con score > 0.

## 15. Ticket tecnici suggeriti

| Ticket | Tipo | Finding |
|---|---|---|
| Grounding check deterministico event_type/reasoning ↔ testo sorgente prima del ranking S4 | correttezza | F-091 |
| Riconciliazione exit: includere stop eseguiti e correggere `quantity_remaining` (SQL legge il vecchio `qty`) | correttezza | F-048 |
| Regime detector: alert su modello singolo fallito; sostituzione di `qwen3.5:cloud` (410 Gone) | correttezza/ops | F-017 |
| P0-05 contro rabbocco di ribilanciamento S1 (decisione di design) | correttezza della misura | F-038 |

## 16. Stato sistema

| Voce | Valore |
|---|---|
| Ollama Cloud (pair glm-5.3 + gpt-oss) | **up** per tutta la seduta: ensemble in ogni ora 13–19 UTC; 4 timeout in RTH (gpt-oss 14:xx ×3, 19:xx ×1), 11 nel giorno, 1 JSON invalido. Downtime: 0 h |
| Ollama per il regime | `kimi-k2.6:cloud` up; **`qwen3.5:cloud` 410 Gone** (2 giri su 2) |
| FinBERT fallback rate | **0%** (0 righe in `finbert_fallback_events`, 0 su 21 decisioni d'ordine). Segnali a modello singolo: 105/246 (42,7%), nessuno arrivato a un ordine (4 BUY S4 tutti ensemble) |
| Worker restart | nessuno (tutti i container «Up 5 days») |
| Shadow sentiment | 1 SoftTimeLimitExceeded (10:28), lotto di 12 perso |
| Telegram | 1 invio fallito (400) e 3 errori di polling «Connection reset by peer» |
| Alpaca | `market_clock` irraggiungibile 19:58 per circa 1 min; 2 warning nello snapshot mobile |
