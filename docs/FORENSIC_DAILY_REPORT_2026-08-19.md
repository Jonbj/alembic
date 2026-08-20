# Forensic Daily Report — 2026-08-19

Analista: sessione autonoma Claude (Trading Systems Forensic Analyst + Senior Backend Engineer + Quant Operations Reviewer).
Modalità: read-only. Nessun ordine inviato, nessuna pipeline rieseguita, nessuna patch di codice applicata.
Timezone operativo: **UTC**, confermato in `src/workers/celery_app.py:51` (`timezone="UTC"`). Nessuna ambiguità di fuso trovata nel codice; il difetto strutturale di allineamento DST (F-021) è documentato al §10.
Finestre usate in questo report: pre-market = prima delle 13:30 UTC; market hours = 13:30–20:00 UTC (NYSE 9:30–16:00 ET, confermato dai `portfolio_monitor_snapshots` che iniziano/finiscono lì); post-market = dopo le 20:00 UTC; batch giornalieri = task Celery schedulati (21:00 decay, 22:30 risk).

Nota di accesso: il bearer token fornito nel protocollo (`Authorization: Bearer <token>`) è stato **verificato di nuovo oggi** e restituisce ancora `403 Invalid or expired JWT token` su tutti gli endpoint (ricorrenza F-041, §10 [DAY-517]). Dati ricostruiti via query dirette a Postgres, come da fallback già previsto dal protocollo, con conferma incrociata via `X-API-Key` sull'API REST per orders/positions.

## 1. Executive summary

Book paper (`alpaca_paper`) per tutta la giornata, nessun halt operatore, gate S4 al valore di design 0,30 (nessuna deroga attiva). 3 BUY (HOOD, HD, NFLX) tutti da articoli ticker-specifici dedicati (nessun fan-out sul money path oggi), 2 SELL (TSLA overnight da 08-18, HD stesso giorno), entrambe `below_entry_gate`. La SELL di HD è uscita su segnale **positivo** (+0,173, sotto il gate ma non invertito) — pattern noto (F-013), costo verificato zero (drift post-uscita −0,54 $). Nessuna violazione di correttezza sul money path: gate rispettato, anti-pyramiding ha bloccato 9 tentativi con traccia esplicita in `execution_decisions` (non più silenzioso, comportamento atteso dal fix di metà agosto), nessun ordine duplicato, nessun ordine fuori orario, nessun trade su dati stale o con output LLM non validato, drawdown (0,49%) e gross exposure (32,6%) ben dentro i limiti (5%/50%). Due ordini SELL "orfani" nel log ordini (HOOD, NFLX, senza `signal_id`/`decision_id`) sono risultati **stop protettivi GTC broker-side legittimi** (meccanismo #62/#63), non anomalie — falso positivo verificato e documentato al §11. NAV −79,85 $ (110.179,29 → 110.099,44 sul book paper), quasi interamente coerente con `market_daily.jsonl` (realizzato +38,35, MTM −118,20, somma −79,85, match esatto): seconda giornata di rout su semiconduttori/hardware (WDC −6,87%, INTC −4,02%, AMD −3,71%, AMAT −3,53%) su posizioni già detenute da settimane, controtendenza pharma e un fronte software/SaaS nuovo. Tredici difetti già noti dal ledger sono ricorsi (F-002, F-003, F-004, F-007, F-011, F-012, F-013, F-014, F-015, F-019, F-020, F-021, F-025, F-027, F-028, F-039, F-041): nessuno nuovo, tutti di osservabilità/misura tranne il pattern strutturale su F-025 (WDC, ora quasi interamente ridotta da stop successivi ma ancora tecnicamente aperta da 30 giorni sotto preserve-stale). Novità di lettura: la ricreazione dei container di oggi (2026-08-20 08:20 UTC, non ancora avvenuta al momento in cui la giornata era in corso) ha comunque azzerato **ogni** log Docker del 19/08 prima che questa sessione potesse leggerli (F-027), quindi ogni affermazione su latenza/errori/timeout LLM di questo report viene dal solo DB.

## 2. Verdict finale

**OK con warning.**

Il processo end-to-end (news → segnale → decisione → ordine → fill → posizione) ha funzionato correttamente e in modo verificabile dal DB per tutta la giornata. I warning riguardano esclusivamente lo strato di osservabilità/misura (risk_reports, decay_reports, audit trail signal_id, log dei container, contatori di ingest, tabelle toccate da test) e un pattern strutturale già noto su S4 (nessun orizzonte di uscita per posizioni tiepidamente positive) — nessun difetto nuovo, nessuno con impatto misurato sul money path di oggi.

## 3. Timeline del 2026-08-19 (UTC)

| Ora | Componente | Evento | Fonte |
|---|---|---|---|
| 06:05:45–06:07:51 | test suite (sospetta) | 8 INSERT su `trades` (id 740-743, 745-748, batch da 4+4 con id 744 mancante) senza `symbol`/`entry_time` valorizzati in audit; righe non più presenti in `trades` e zero `DELETE` mai registrati in `audit_log` — ricorrenza F-039 | `audit_log`, `trades` |
| 06:08:50 | ingestion_stats_daily | riga fantasma `source='reuters'` (fetched=4, queued=4) — ricorrenza F-028, stesso timestamp/finestra della contaminazione test su `trades` | `ingestion_stats_daily` |
| 12:52:50 | news ingest | prima news pubblicata della giornata (pre-market) | `news_log.published_at` |
| 13:30:00 | portfolio_monitor | primo snapshot NAV=110.466,25, nav_change_today=+286,96, 48 posizioni | `portfolio_monitor_snapshots` |
| 13:30:00–13:30:01 | mobile_events | incidente CRITICAL "Ciclo di portafoglio in ritardo" + WARNING "Segnali sentiment in ritardo", entrambi `recovered` al primo ciclo (14:07) — falso allarme strutturale quotidiano, ricorrenza F-021 | `mobile_events` |
| 14:00:31 | sentiment worker | primo segnale della giornata (170 segnali totali nella sessione, ultimo alle 19:45:29) | `sentiment_signals` |
| 14:07:00 | execution | primo ciclo `portfolio_cycles`/`execution_decisions`, **37 minuti dopo l'apertura NYSE (13:30 UTC in EDT)** — ricorrenza F-021 | `execution_decisions`, `portfolio_cycles` |
| 15:52:00 | execution | **SELL TSLA** — `below_entry_gate` (score −0,042), posizione aperta il 08-18 alle 16:37, roundtrip 23h15m, net_pnl +34,44 $ | `execution_decisions` id 12080 → `trades` id 739 |
| 16:07:00 | execution | **BUY HOOD** — sentiment +0,350 (ensemble), articolo dedicato "Why Is Robinhood Stock Surging on Wednesday?", peso target 2,0% | `execution_decisions` id 12102 → `trades` id 749 |
| 16:22:10 | portfolio_scheduler | stop protettivo GTC creato per HOOD (qty floor 18, sync #62/#63) — resta `new`/resting a fine giornata (posizione ancora aperta) | orders API |
| 16:37:00 | execution | **BUY HD** — sentiment +0,542, articolo dedicato "These Analysts Revise Their Forecasts On Home Depot After Q2 Earnings", peso 2,0% | `execution_decisions` id 12147 → `trades` id 750 |
| 16:52:09 | portfolio_scheduler | stop protettivo GTC creato per HD (qty floor 5) — cancellato alle 18:22 quando la posizione chiude via decisione | orders API |
| 17:07:00 | execution | **BUY NFLX** — sentiment +0,389, articolo dedicato "What's Going On With Netflix Stock Wednesday?", peso 2,0% | `execution_decisions` id 12198 → `trades` id 751 |
| 17:22:06 | portfolio_scheduler | stop protettivo GTC creato per NFLX (qty floor 22, sync #62/#63) — resta `new`/resting a fine giornata | orders API |
| 18:22:00 | execution | **SELL HD** — `below_entry_gate`, nuovo segnale delle 18:00 con score **+0,173 (positivo)** sotto il gate: roundtrip 105 min, net_pnl +3,91 $, drift post-uscita −0,54 $ (costo 0,00 verificato) — ricorrenza F-013 | `execution_decisions` id 12323 → `trades` id 750 |
| 20:01:00 | portfolio_monitor | ultimo snapshot NAV=110.099,44, nav_change_today=−79,85, 49 posizioni, gross_exposure 32,6%, drawdown 0,49% | `portfolio_monitor_snapshots` |
| 20:00:04 | mobile_events | incidente CRITICAL "Dati broker non aggiornati", `recovered` | `mobile_events` |
| 21:00:00 | decay_monitor | `decay_reports`: 12 righe, valori actual IDENTICI su S1/S2/S4 (ricorrenza F-004) | `decay_reports` |
| 22:30:00 | risk_monitor | `risk_reports` id 68: combined_drawdown 1,24% vs per_strategy portfolio.drawdown 17,75% → ALERT falso "17.8% exceeds 10%"; nav=110.175,95 contro 110.099,44 dell'ultimo snapshot (scarto 76,51 $, il più ampio degli ultimi 4 giorni osservati) — ricorrenza F-003 | `risk_reports` |
| 2026-08-20 08:20–09:10 | infra | container worker/api/worker-inference/beat **ricreati** (redeploy); ogni log Docker del 19/08 irrecuperabile prima che questa sessione potesse leggerlo — ricorrenza F-027 | `docker inspect` |

Nessuna news con timestamp futuro, nessun buco intraday nei 5-minute snapshot (13:30→20:01, cadenza regolare, gap massimo 6 minuti dovuto al solo ultimo campione).

## 4. Tabella news ingest

| Fonte | Fetched | Queued | Duplicates | Discarded (no ticker) | Landed in `news_log` |
|---|---|---|---|---|---|
| alpaca_benzinga | 636 | 340 | **2.762** (4,3× fetched — F-007) | 0 | 89 |
| gdelt_gkg | 1.829 | 109 | 31 | 1.700 | 81 |
| reuters (fantasma, F-028) | 4 | 4 | 0 | 1 | 0 |
| **Totale reale** | 2.465 | 449 | — | 1.700 | **170** |

- Copertura watchlist: 56 ticker distinti su 96 (40 a copertura zero, 42%) — dentro la banda 38-57% osservata dal 31/07 (F-001, tracciata separatamente dal cron alpha-miss, occorrenza 08-19 già presente nel ledger a 488,23 $).
- Latenza mediana `created_at − published_at`: 84,2 min (alpaca_benzinga, n=89) e 75,4 min (gdelt_gkg, n=81), contro `MAX_NEWS_AGE_HOURS=2,0h` (120 min) — l'83-70% della finestra di freschezza già consumata alla nascita del segnale, in linea con la serie storica (F-019).
- 33 righe (14 MS, 15 GS, 4 DB) su società terze attribuite via `extraction_method=org_lookup` perché la banca compare come casa di analisi/underwriter nel boilerplate (F-020); campione verificato titolo per titolo, solo 1 delle 33 righe (un pezzo su Goldman Sachs che compra azioni Shiprocket) riguarda davvero la banca.
- Nessuna news con timestamp futuro, nessun campo obbligatorio mancante, nessun `parse_fail`.
- Money path pulito da fan-out oggi: le 3 news che hanno originato i BUY (HOOD, HD, NFLX) sono tutte articoli mono-ticker dedicati (`content_hash` non condiviso con altri ticker) — vedi §11.

## 5. Tabella performance modelli LLM

| Model_id | Fallback | N | Score medio | Confidence media | Note |
|---|---|---|---|---|---|
| ensemble:glm-5.2:cloud+gpt-oss:20b-cloud | No | 123 (72,4%) | +0,051 | 0,320 | Ensemble dual-model |
| single:gpt-oss:20b-cloud | Sì | 42 (24,7%) | +0,030 | 0,493 | Un modello sotto floor confidence |
| single:glm-5.2:cloud | Sì | 5 (2,9%) | 0,000 | 0,520 | Un modello sotto floor confidence |
| **Totale** | — | **170** | — | — | 0 righe `model_id ILIKE '%finbert%'` — FinBERT mai invocato oggi |

- `llm_responses`: glm-5.2 eligible=true su 36/170 (21,2%), gpt-oss eligible=true su 36/169; il campo `eligible` non è una soglia di confidenza pulita (fenomeno noto, non ri-registrato oggi perché non associato a F-010).
- Nessun errore/timeout osservabile: **i log Docker del 19/08 sono stati azzerati dal redeploy del 20/08 prima che questa sessione potesse leggerli** (F-027) — latenza per-chiamata e conteggio retry non verificabili, solo dal DB.
- 5 righe `SKIP_FALLBACK` (BRK.B, MRK, C, PLTR, PFE): segnale single-model esclusi dal ranking BUY per assenza di ensemble (#108), comportamento per design.
- Nessuna evidenza di ensemble variance elevata sfociata in un ordine: i tre BUY del giorno hanno `ensemble_std` non anomalo rispetto alla soglia 0,30 usata da `postmortem.py` (F-037, non ri-registrato oggi — nessun caso ≥0,25 fra i BUY).
- Validazione a monte confermata: `sentiment_signals.news_log_id` è popolato su 170/170 righe (0 segnali orfani), e nessun `(news_log_id, symbol)` produce più di un segnale (0 duplicati) — l'anello news→segnale è integro e non genera segnali multipli dalla stessa notizia.
- Chiamate LLM offline/background confermate: nessuna chiamata sincrona nel loop di esecuzione, tutte le decisioni leggono da `sentiment_signals` pre-calcolato.

## 6. Tabella segnali finali per ticker (money path)

| Ticker | Ora segnale | Score | Modello | Sopra gate 0,30? | Esito |
|---|---|---|---|---|---|
| HOOD | 16:07 | +0,350 | ensemble | Sì | BUY (peso 2,0%) |
| HD | 16:37 | +0,542 | ensemble | Sì | BUY (peso 2,0%) |
| NFLX | 17:07 | +0,389 | ensemble | Sì | BUY (peso 2,0%) |
| TSLA | 15:30 | −0,042 | — | No | SELL (below_entry_gate, posizione 08-18) |
| HD | 18:00 | +0,173 | — | No (ma segno positivo) | SELL (below_entry_gate) |
| PFE | 19:45 | +0,120 | fallback | No | Miss NO_NEWS-adiacente, già in F-009 (79,93 $ 08-19) |
| AVGO | 14:00-16:00 | −0,158 (ultimo) | mix | No | Miss, segno corretto sotto gate, costo 0,00 verificato (F-009) |
| 9 simboli (TSLA, MRVL×2, UNH, WDC, GOOGL, MRK, XOM, PANW) | vari | >0,30 | — | Sì | SKIP_PYRAMIDING — già a libro S1/legacy, traccia esplicita in `execution_decisions` |

## 7. Tabella ordini generati/eseguiti

| Ora | Symbol | Side | Qty | Prezzo fill | Stato | Decision_id | Trade_id | Note |
|---|---|---|---|---|---|---|---|---|
| 15:52:11 | TSLA | SELL | 3,783452 | 346,37 | filled | 11654* | 739 | below_entry_gate, entry 08-18 |
| 16:07:09 | HOOD | BUY | 18,648487 | 98,46 | filled | 12102 | 749 | S4 news-driven |
| 16:22:10 | HOOD | SELL (stop GTC) | 18 | — | **new** (resting) | — | — | protettivo #62/#63, non un ordine "target" |
| 16:37:09 | HD | BUY | 5,357575 | 343,48 | filled | 12147 | 750 | S4 news-driven |
| 16:52:09 | HD | SELL (stop GTC) | 5 | — | canceled | — | — | protettivo, cancellato al close decisione |
| 17:07:09 | NFLX | BUY | 22,938986 | 80,31 | filled | 12198 | 751 | S4 news-driven |
| 17:22:06 | NFLX | SELL (stop GTC) | 22 | — | **new** (resting) | — | — | protettivo #62/#63 |
| 18:22:10 | HD | SELL | 5,357575 | 344,40 | filled | 12147 | 750 | below_entry_gate |

*`decision_id` sull'ordine SELL TSLA riportato dall'API è quello di **entry** persistito su `trades.decision_id` (limite di schema, non un errore: la decisione di uscita reale è `execution_decisions` id 12080, cfr. §3).

`portfolio_cycles`: 24 cicli, `orders_count` somma 108 contro 8 ordini realmente inviati al broker (rapporto 13,5:1) — il campo conta gli ordini target del combiner prima dei guard, non i submitted (ricorrenza F-014).

## 8. Tabella PnL/rendimento

| Voce | Valore |
|---|---|
| NAV apertura (13:30, ≈ chiusura 08-18 rettificata overnight) | 110.179,29 $ |
| NAV chiusura (20:01) | 110.099,44 $ |
| Variazione NAV giornaliera | **−79,85 $ (−0,07%)** |
| Realizzato (2 trade chiusi: TSLA +34,44, HD +3,91) | **+38,35 $** |
| MTM su book esistente | **−118,20 $** |
| SPY (return giorno) | +0,21% |
| QQQ (return giorno) | −0,20% |
| Gross exposure fine giornata | 32,6% (limite 50%) |
| Drawdown corrente fine giornata | 0,49% (limite 5%) |

Fonte incrociata: `market_daily.jsonl` riga 2026-08-19 (equity 110.099,44, realizzato 38,35, mtm −118,20, somma −79,85) coincide esattamente con la ricostruzione da `trades`+`portfolio_monitor_snapshots`. Nessun dato mancante su questa sezione.

MTM negativo trainato da 2° giorno consecutivo di rout semiconduttori/hardware (WDC −6,87%, INTC −4,02%, AMD −3,71%, AMAT −3,53%, tutte posizioni aperte da settimane, non nuovi ingressi), parzialmente compensato da pharma (LLY +4,46%, ABBV +2,72%) e software/SaaS (NOW, CRM, ADBE, HOOD, NFLX tutti positivi). I due nuovi ingressi con entry_percentile sopra la mediana mobile 20gg (HOOD 0,866, NFLX 0,722) hanno chiuso la giornata in perdita mark-to-market (−50,16 e −2,06 $) nonostante i titoli sottostanti fossero positivi sul giorno — pattern già tracciato su F-030 (costo misurato 52,22 $, occorrenza già presente nel ledger per l'08-19). L'unico ingresso sotto mediana (HD, percentile 0,229) è l'unico chiuso in utile lo stesso giorno.

Slippage: non misurabile separatamente dal costo modellato — `trades.slippage_est` è identico bit-per-bit a `cost_usd` su entrambe le chiusure di oggi (TSLA 0,254149…, HD 1,018966…), ricorrenza F-015.

## 9. Analisi correttezza buy/sell

- **BUY generati solo quando consentito**: sì, tutti e 3 sopra gate 0,30 di design, nessuna deroga attiva, `regime_mult`=1 (nessuno scaling di regime oggi).
- **SELL/exit generati correttamente**: sì. TSLA e HD chiusi via `below_entry_gate`, meccanismo documentato e coerente con `exit_mechanism` scritto esplicitamente in `execution_decisions` (non dedotto per età — vedi avvertenza #184, non applicabile a queste due righe perché il campo è popolato direttamente).
- **Stop-loss rispettati**: sì, meccanismo broker-side GTC attivo su tutte e 3 le nuove posizioni (§11); nessuno stop scattato oggi.
- **Signal flip rispettato**: nessun caso di flip di segno con ordine conseguente oggi.
- **SELL su sentiment positivo (pattern A5)**: 1 caso, HD alle 18:22 (score +0,173). Verificato **non è un bug**: è la regola `below_entry_gate` che azzera il peso quando il segnale fresco, pur positivo, scende sotto la soglia d'ingresso attiva — stesso meccanismo già registrato su altre giornate con segno negativo (F-013); qui il segno è positivo per la prima volta in questa forma osservata di recente, costo verificato zero.
- **Max holding days**: nessuna violazione osservabile; WDC resta un'eccezione strutturale nota (F-025, vedi §10).
- **Rebalance band**: nessuna banda fra gate d'ingresso e uscita per design (F-013, taratura congelata).
- **Ordini duplicati**: nessuno — 8 ordini totali, tutti a timestamp `submitted_at` distinti.
- **Ordini contrari ravvicinati senza rationale**: nessuno oltre al pattern noto F-013 (già spiegato sopra).
- **Ordini su ticker non consentiti**: nessuno, tutti i 3 BUY su simboli watchlist.
- **Ordini fuori orario**: nessuno; primo ordine 15:52, ultimo 18:22, tutti dentro 13:30-20:00.
- **Trade su dati stale**: nessuno; 2 `SKIP_STALE` (IWM, QQQ) correttamente scartati.
- **Trade con LLM output non valido**: nessuno rilevabile; nessun `eligible=false` isolato è entrato in un ordine BUY (i 3 BUY sono tutti ensemble non-fallback).
- **Circuit breaker attivo**: no, nessun halt operatore (`system:halted_by_operator` vuoto).
- **Strategia disabilitata**: S2 correttamente `disabled` in `strategy_lifecycle`, nessun trade S2; S1/S4 `paper`/`supervised_paper`, coerente.
- **Paper/live coerente**: `broker_environment`/`mode` = `paper` su tutti gli 83 snapshot del giorno.
- **Idempotenza Celery**: nessuna evidenza di doppio invio per lo stesso ciclo (8 ordini distinti, nessun order_id ripetuto).
- **Reconciliation ordini/fill/posizioni**: coerente — le 3 BUY e 2 SELL filled corrispondono 1:1 a righe `trades`, le posizioni API riflettono le quantità nette attese.

## 10. Anomalie trovate

### [DAY-501] Posizioni legacy senza `stop_strategy`: tredicesima sessione consecutiva

* Tipo: Osservazione
* Area: PnL / Data
* Evidenza:
  * file/log/tabella: `trades`
  * timestamp: 2026-08-19
  * snippet/query: `SELECT symbol FROM trades WHERE exit_time IS NULL AND stop_strategy IS NULL` → BAC, GOOGL, GS, MS, PBR, RIO, ROKU, SPY, UBS, UNH, XLE (tutte entrate 2026-07-10)
* Descrizione: le stesse 11 posizioni legacy, invariate dal 07-31, restano senza `stop_strategy`/`stop_mode` popolati. Nessuna di esse è un mover del giorno.
* Impatto: qualunque split P&L S1/S4 (domanda di uscita n.2 della carta) esclude sistematicamente questa fetta del libro.
* Severità: Low
* Confidenza: High
* Azione consigliata: nessuna nuova — F-002 già tracciato, congelato dalla carta come difetto di misura non di correttezza esecutiva.
* Test/monitor consigliato: nessuno aggiuntivo oltre a quanto già proposto sulle occorrenze precedenti.

### [DAY-502] risk_reports: doppia cifra di drawdown + scarto NAV più ampio della serie recente

* Tipo: Difetto
* Area: Risk
* Evidenza:
  * file/log/tabella: `risk_reports` id 68
  * timestamp: 2026-08-19 22:30:00
  * snippet/query: `combined_drawdown=0.012429` (1,24%) vs `per_strategy_metrics->portfolio->drawdown=0.1775` (17,75%) che genera l'ALERT "17.8% exceeds 10%"; `nav=110.175,95` contro l'ultimo `portfolio_monitor_snapshots.nav=110.099,44` delle 20:01 — scarto 76,51 $
* Descrizione: ricorrenza esatta della doppia cifra di drawdown già tracciata (F-003). Novità quantitativa: lo scarto fra il NAV di `risk_reports` e l'ultimo snapshot intraday è il più ampio degli ultimi 4 giorni confrontabili (+7,10 il 08-14, +4,65 il 08-17, −16,16 il 08-18, **+76,51 oggi**).
* Impatto: nessun ordine dipende da questo record; l'ALERT giornaliero resta rumore che desensibilizza rispetto a un drawdown vero.
* Severità: Medium
* Confidenza: High
* Azione consigliata: nessuna nuova — F-003 già ha ticket TK-G/TK-R7 aperti.
* Test/monitor consigliato: alert su scarto NAV risk_reports vs ultimo snapshot > soglia (es. 50 $) per isolare la causa della doppia fonte di prezzo EOD.

### [DAY-503] decay_reports: metriche pipeline-globali identiche su S1/S2/S4, inclusa la disabilitata S2

* Tipo: Difetto
* Area: Risk
* Evidenza:
  * file/log/tabella: `decay_reports`
  * timestamp: 2026-08-19 21:00:00
  * snippet/query: hit_rate 0,2957, ic 0,02124, max_drawdown 0,1194, sharpe −6,032 identici su tutte e tre le righe; S1 CRITICAL su hit_rate e sharpe, S2 (mai un trade) CRITICAL su hit_rate/sharpe
* Descrizione: ricorrenza invariata di F-004 — `_fetch_actual_metrics` non filtra per `strategy_id`.
* Impatto: il monitor di decadimento non può distinguere S1 da S4, che è esattamente la domanda che la carta chiede di rispondere.
* Severità: Medium
* Confidenza: High
* Azione consigliata: nessuna nuova, F-004 già tracciato.
* Test/monitor consigliato: già proposto sulle occorrenze precedenti.

### [DAY-504] ingestion_stats_daily: duplicati Benzinga 4,3× il fetched

* Tipo: Osservazione
* Area: Data
* Evidenza:
  * file/log/tabella: `ingestion_stats_daily`
  * timestamp: 2026-08-19
  * snippet/query: alpaca_benzinga fetched=636, duplicates=2.762
* Descrizione: ricorrenza F-007, verificata indipendente: 170 righe reali in `news_log`, dedup per `content_hash` funziona (26 hash duplicati = fan-out multi-ticker legittimo, non contatore rotto).
* Impatto: il contatore non è utilizzabile come metrica di copertura news.
* Severità: Low
* Confidenza: High
* Azione consigliata: nessuna nuova, F-007 già tracciato (TK-K/T-06).
* Test/monitor consigliato: già proposto.

### [DAY-505] execution_decisions.signal_id NULL su 98% delle righe

* Tipo: Difetto
* Area: Signal
* Evidenza:
  * file/log/tabella: `execution_decisions`
  * timestamp: 2026-08-19
  * snippet/query: 500 righe totali, 10 con `signal_id` valorizzato (3 BUY su 3, 7 SKIP_PYRAMIDING su 9); SELL, SKIP_FALLBACK, SKIP_STALE, SKIP_THRESHOLD sempre NULL
* Descrizione: ricorrenza F-011, in linea con la serie (98,3% l'08-17, 99,0% l'08-18). Il ramo d'ingresso resta risolto dal fix #123/PR#234 (BUY 3/3); i rami di uscita/scarto restano NULL per costruzione.
* Impatto: la catena segnale→decisione→trade sulle uscite resta ricostruibile solo per testo libero del `reason`.
* Severità: Low
* Confidenza: High
* Azione consigliata: nessuna nuova, F-011 già tracciato.
* Test/monitor consigliato: già proposto.

### [DAY-506] Fan-out multi-ticker: 45,3% delle righe scorate da articoli condivisi fra ticker

* Tipo: Difetto
* Area: News
* Evidenza:
  * file/log/tabella: `news_log`
  * timestamp: 2026-08-19
  * snippet/query: 26 `content_hash` condivisi su 119 articoli distinti, 77/170 righe scorate (45,3%)
* Descrizione: ricorrenza F-012, in linea con la serie discendente (51%→66%→53%→55%→51,5%→48,8%→46,5%→45,6%→**45,3%**). Nota positiva: nessuno dei 3 BUY di oggi origina da un articolo fan-out (§4, §11).
* Impatto: metà della copertura apparente della watchlist non riguarda il ticker a cui è attribuita; nessun impatto sul money path di oggi.
* Severità: Low
* Confidenza: High
* Azione consigliata: nessuna nuova, F-012 già tracciato.
* Test/monitor consigliato: già proposto.

### [DAY-507] SELL su sentiment positivo (below_entry_gate su HD, score +0,173)

* Tipo: Corretto (verificato non-bug)
* Area: Signal / Orders
* Evidenza:
  * file/log/tabella: `execution_decisions` id 12323
  * timestamp: 2026-08-19 18:22:00
  * snippet/query: reason `[below_entry_gate] ... score=+0.173`; `trades` id 750 net_pnl +3,91, drift_post_uscita −0,54 (dossier)
* Descrizione: la SELL è generata perché il segnale fresco, pur positivo, cade sotto la soglia d'ingresso attiva (0,30), non perché il sentiment sia invertito — stesso meccanismo di F-013 già osservato con segno negativo su altre giornate.
* Impatto: nessuno di correttezza; costo economico verificato zero (l'uscita ha marginalmente anticipato un calo).
* Severità: Low
* Confidenza: High
* Azione consigliata: nessuna, comportamento per design (banda gate/uscita è taratura, congelata dalla carta).
* Test/monitor consigliato: nessuno aggiuntivo.

### [DAY-508] portfolio_cycles.orders_count: 108 target contro 8 ordini realmente inviati

* Tipo: Difetto
* Area: Orders
* Evidenza:
  * file/log/tabella: `portfolio_cycles`
  * timestamp: 2026-08-19
  * snippet/query: 24 cicli, sum(orders_count)=108, 8 ordini reali (rapporto 13,5:1)
* Descrizione: ricorrenza F-014, il campo conta gli ordini target del combiner prima dei guard (pyramiding, hold-minimum), non i submitted.
* Impatto: la metrica di attività del sistema è sbagliata di un fattore 13,5x; nessun impatto P&L.
* Severità: Low
* Confidenza: High
* Azione consigliata: nessuna nuova, F-014 già tracciato (TK-R11: campo `orders_submitted` distinto).
* Test/monitor consigliato: già proposto.

### [DAY-509] trades.slippage_est identico a cost_usd

* Tipo: Difetto
* Area: PnL
* Evidenza:
  * file/log/tabella: `trades` id 739, 750
  * timestamp: 2026-08-19
  * snippet/query: TSLA slippage_est=cost_usd=0,254149…; HD slippage_est=cost_usd=1,018966…
* Descrizione: ricorrenza esatta di F-015 su entrambe le chiusure del giorno.
* Impatto: la qualità di esecuzione non è misurata da nessuna colonna del DB.
* Severità: Low
* Confidenza: High
* Azione consigliata: nessuna nuova, F-015 già tracciato (TK-J).
* Test/monitor consigliato: già proposto.

### [DAY-510] Latenza ingestione news: mediana 75-84 minuti

* Tipo: Difetto
* Area: News
* Evidenza:
  * file/log/tabella: `news_log`
  * timestamp: 2026-08-19
  * snippet/query: alpaca_benzinga mediana 84,2 min (n=89), gdelt_gkg 75,4 min (n=81), max 117,0/106,0 min
* Descrizione: ricorrenza F-019, dentro la banda storica (75-105 min).
* Impatto: 70-83% della finestra di freschezza (120 min) consumata alla nascita del segnale; nessun costo isolabile oggi (i 3 BUY hanno comunque superato il gate).
* Severità: Low
* Confidenza: High
* Azione consigliata: nessuna nuova, F-019 già tracciato.
* Test/monitor consigliato: già proposto.

### [DAY-511] org_lookup attribuisce a MS/GS/DB articoli su società terze

* Tipo: Difetto
* Area: News
* Evidenza:
  * file/log/tabella: `news_log`
  * timestamp: 2026-08-19
  * snippet/query: MS 14 righe, GS 15, DB 4 (33 totali via `org_lookup`); verificate titolo per titolo, 32/33 su società non correlate (Sysco, Lithium Argentina, Anthropic, Moderna/Baidu, Nebius, ecc.), 1/33 legittima (Goldman Sachs/Shiprocket)
* Descrizione: ricorrenza F-020.
* Impatto: nessun ordine ne è nato oggi (nessuna riga sopra gate); la copertura apparente della watchlist resta gonfiata.
* Severità: Low
* Confidenza: High
* Azione consigliata: nessuna nuova, F-020 già tracciato.
* Test/monitor consigliato: già proposto.

### [DAY-512] Finestra beat UTC fissa ignora il DST: 37 minuti di sessione scoperti

* Tipo: Difetto
* Area: Ops
* Evidenza:
  * file/log/tabella: `execution_decisions`, `portfolio_cycles`
  * timestamp: 2026-08-19 14:07:00
  * snippet/query: primo ciclo 14:07:00 UTC contro apertura NYSE 13:30 UTC (EDT)
* Descrizione: ricorrenza F-021, con il consueto falso allarme auto-risolto in `mobile_events` (13:30:00-13:30:01).
* Impatto: 37 minuti di sessione senza ingest/scoring/cicli ogni giorno feriale per ~8 mesi l'anno; nessun mover isolabile nella finestra persa oggi.
* Severità: Low
* Confidenza: High
* Azione consigliata: nessuna nuova, F-021 già tracciato.
* Test/monitor consigliato: già proposto.

### [DAY-513] WDC: posizione S4 aperta da 30 giorni sotto preserve-stale, ora quasi interamente ridotta da stop successivi

* Tipo: Difetto
* Area: Signal / Risk
* Evidenza:
  * file/log/tabella: `trades` id 373, positions API
  * timestamp: 2026-08-19 (entry 2026-07-21)
  * snippet/query: age 29g 20h contro `max_signal_age_hours=4`; qty residua 0,334697 (era 2,981065 all'ingresso), unrealized_pl −31,43 $
* Descrizione: ricorrenza F-025. Novità di lettura rispetto alle occorrenze precedenti (22 giorni l'08-12): la posizione non è più intatta come allora — i fill successivi dello stop protettivo a quantità intera (F-022, floor `math.floor`) hanno ridotto la size nozionale dell'88% nel frattempo, lasciando solo un residuo frazionario ancora "aperto" e ancora ri-ammesso ogni ciclo da `_preserve_stale_signals_for_open_positions`. Il meccanismo di protezione ha parzialmente compensato il difetto di uscita, ma non lo ha chiuso: il residuo resta indefinitamente vivo.
* Impatto: qualunque statistica di holding period S4 sul libro attuale resta distorta da questa posizione; impatto P&L oggi piccolo per costruzione (qty residua minima).
* Severità: Medium
* Confidenza: High
* Azione consigliata: nessuna nuova, F-025 già tracciato; segnalare la nuova osservazione (riduzione parziale via stop) come contesto utile alla chiusura del ticket.
* Test/monitor consigliato: alert su posizioni S4 aperte > 24h nonostante `max_signal_age_hours=4` (già raccomandato).

### [DAY-514] Log Docker del 19/08 azzerati dal redeploy del 20/08 prima della lettura

* Tipo: Difetto
* Area: Ops
* Evidenza:
  * file/log/tabella: `docker inspect`
  * timestamp: 2026-08-20 08:20-09:10 UTC
  * snippet/query: `Created`=`StartedAt`=2026-08-20T09:10:41Z su worker/api/worker-inference/beat (ricreazione, non riavvio); `docker compose logs worker --since 48h` non contiene righe precedenti a questo timestamp
* Descrizione: ricorrenza F-027, decima occorrenza. Continuità DB totale (24/24 cicli, 83/83 snapshot, nessun buco) contro zero log applicativi per l'intera giornata.
* Impatto: latenza/errori/timeout LLM, retry, eccezioni non propagate non verificabili per il 19/08; ogni affermazione di questo report viene dal solo DB.
* Severità: Medium
* Confidenza: High
* Azione consigliata: nessuna nuova, F-027 già tracciato (P0, TK-R2).
* Test/monitor consigliato: già proposto (logging persistente su storage esterno al container).

### [DAY-515] ingestion_stats_daily: riga fantasma `source='reuters'` da test contro il DB di produzione

* Tipo: Difetto
* Area: Data
* Evidenza:
  * file/log/tabella: `ingestion_stats_daily`
  * timestamp: 2026-08-19 06:08:50 UTC
  * snippet/query: `source='reuters'`, fetched=4, queued=4, discarded_no_ticker=1; zero righe `news_log.source='reuters'` in tutta la storia del DB; nessun task RSS/reuters in `celery_app.py`
* Descrizione: ricorrenza F-028, stesso orario/finestra pre-market della contaminazione trades registrata su [DAY-516] — compatibile con un'unica esecuzione della suite di test avvenuta stamattina presto contro `DATABASE_URL` di produzione.
* Impatto: contamina i contatori di ingest usati come evidenza; nessun ordine coinvolto.
* Severità: Low
* Confidenza: High
* Azione consigliata: nessuna nuova, F-028 già tracciato (TK-H).
* Test/monitor consigliato: già proposto (guardia ambiente in `conftest.py`).

### [DAY-516] 8 righe `trades` inserite e cancellate pre-market senza audit trail della cancellazione

* Tipo: Difetto
* Area: Data / Risk
* Evidenza:
  * file/log/tabella: `audit_log`, `trades`
  * timestamp: 2026-08-19 06:05:45–06:07:51 UTC
  * snippet/query: `audit_log` id 12255-12262, `action='INSERT'`, `table_name='trades'`, `record_id` 740-743 e 745-748 (744 mancante), `new_value->>'symbol'` vuoto; `SELECT * FROM trades WHERE id BETWEEN 740 AND 748` → 0 righe; `SELECT action FROM audit_log WHERE table_name='trades'` → solo `INSERT` (487 righe totali, mai un `DELETE`)
* Descrizione: ricorrenza esatta di F-039 (prima occorrenza 08-14), stesso pattern a batch di 4 con un id "buco" per batch, stesso orario pre-market compatibile con l'esecuzione di `tests/store/test_pg_store_stop_methods.py` contro il DB live, che esegue `DELETE FROM trades WHERE symbol = %s` in SQL grezzo bypassando l'audit.
* Descrizione impatto: nessun trade reale toccato (id sintetici, mai presenti negli export API/positions di oggi); il rischio è di integrità futura — l'invariante "P0-12: no unaudited trades can exist" protegge solo gli INSERT, non le DELETE.
* Severità: Medium
* Confidenza: High
* Azione consigliata: nessuna nuova, F-039 già tracciato; la co-occorrenza con [DAY-515] rafforza l'ipotesi di un'unica run di test contro produzione stamattina.
* Test/monitor consigliato: guardia ambiente su `DATABASE_URL` nei test, audit trail anche sui `DELETE`.

### [DAY-517] Bearer token del protocollo forense rifiutato su tutti gli endpoint REST

* Tipo: Difetto
* Area: Ops
* Evidenza:
  * file/log/tabella: API `/api/decisions`
  * timestamp: 2026-08-20 (verifica di questa sessione)
  * snippet/query: `curl -H "Authorization: Bearer <token>"` → `403 {"detail":"Invalid or expired JWT token"}`; lo stesso token con `X-API-Key: <token>` → `200 OK`
* Descrizione: ricorrenza esatta F-041, verificata di nuovo (non solo assunta da memoria di sessioni precedenti).
* Impatto: nessuno sul trading; impatto sul protocollo di analisi, mitigato dal fallback DB diretto già previsto.
* Severità: Low
* Confidenza: High
* Azione consigliata: nessuna nuova, F-041 già tracciato; aggiornare le istruzioni curl del protocollo cron per usare `X-API-Key`.
* Test/monitor consigliato: nessuno aggiuntivo.

## 11. False positive o aree risultate corrette

- **Ordini SELL "orfani" (HOOD, NFLX) senza signal_id/decision_id**: a prima vista sembravano ordini generati senza segnale/decisione (uno dei pattern esplicitamente richiesti dal protocollo). Verificati come **stop protettivi GTC broker-side legittimi**, creati dal meccanismo di sync `_sync_fractional_protective_stops` (#62/#63) un ciclo dopo l'ingresso, a quantità intera floor (18 su 18,648487 per HOOD, 22 su 22,938986 per NFLX), `time_in_force=GTC` (non `DAY`, nessun rischio di scadenza a fine sessione). Il gemello su HD (qty floor 5) è stato correttamente **cancellato** quando la posizione decisionale si è chiusa alle 18:22, dimostrando che la sincronizzazione gestisce anche il ciclo di vita in uscita.
- **Ticker BRKB**: zero righe oggi; le 7 righe news su Berkshire sono correttamente `BRK.B` — F-032 resta chiuso (fix #226 tenuto).
- **SKIP_PYRAMIDING silenzioso (ex F-031)**: le 9 righe di oggi riportano tutte reason esplicita con score e data di ingresso della posizione che blocca — il guard non è più silenzioso, comportamento confermato dal fix osservato dall'11/08 in poi.
- **Money path libero da fan-out**: i 3 BUY di oggi nascono tutti da articoli mono-ticker dedicati, non da articoli su società terze (a differenza di molte occorrenze storiche di F-012).
- **Nessuna violazione long-only, nessun ordine fuori orario, nessun duplicato, nessuna eccezione di risk limit**: verificato su tutte le fonti disponibili (DB + API).

## 12. Dati mancanti o non accessibili

- **Log Docker dell'intera giornata 19/08**: azzerati dal redeploy del 20/08 08:20-09:10 UTC prima che questa sessione potesse leggerli (F-027, [DAY-514]). Latenza per-chiamata LLM, conteggio retry, eccezioni non propagate: non verificabili, solo dal DB.
- **Bearer token API** (`Authorization: Bearer`): non funzionante come da protocollo, aggirato con `X-API-Key` (F-041, [DAY-517]).
- **Slippage reale**: non calcolabile, `trades.slippage_est` è una copia di `cost_usd` (F-015).
- **Attribuzione P&L per strategia sulle 11 posizioni legacy**: `stop_strategy` NULL (F-002).

## 13. Raccomandazioni immediate

Nessuna azione immediata richiesta sul money path: tutte le anomalie di oggi sono ricorrenze già tracciate nel ledger, di sola osservabilità/misura, congelate dalla carta di osservazione. Unica nota operativa: verificare se la suite `tests/store/test_pg_store_stop_methods.py` (e il test RSS gemello) puntano ancora a `DATABASE_URL` di produzione — la co-occorrenza [DAY-515]/[DAY-516] di stamattina suggerisce che il problema è ancora attivo un mese dopo la prima segnalazione (F-028/F-039).

## 14. Test o monitor da aggiungere

- Alert su scarto NAV `risk_reports` vs ultimo `portfolio_monitor_snapshots` > soglia in dollari (nuovo dettaglio emerso oggi su [DAY-502]).
- Guardia ambiente (`DATABASE_URL` != produzione) nei test che scrivono su `trades`/`ingestion_stats_daily`.
- Audit trail anche sui `DELETE`, non solo sugli `INSERT`.
- Tutti gli altri monitor già raccomandati sulle occorrenze precedenti dei finding ricorrenti (F-003, F-004, F-007, F-011, F-012, F-014, F-015, F-019, F-020, F-021, F-025, F-027).

## 15. Ticket tecnici suggeriti

Nessun ticket nuovo: tutte le anomalie di oggi appartengono a finding già aperti nel ledger (F-002, F-003, F-004, F-007, F-011, F-012, F-013, F-014, F-015, F-019, F-020, F-021, F-025, F-027, F-028, F-039, F-041), tutti già muniti di ticket o esplicitamente congelati dalla carta come taratura.

## 16. Stato sistema

- **Ollama Cloud**: UP al 100% per tutta la sessione osservabile da DB — 0 righe `model_id ILIKE '%finbert%'` in `sentiment_signals` (FinBERT mai invocato), 170/170 segnali generati da glm-5.2/gpt-oss (ensemble o single). Downtime: 0h (non verificabile da log per il redeploy, ma l'assenza totale di fallback FinBERT è una prova indiretta forte).
- **FinBERT fallback rate**: 0% delle decisioni (0 righe su 170 segnali, 0 su 500 execution_decisions).
- **Fallback single-model rate** (un solo LLM cloud disponibile per news, non FinBERT): 47/170 segnali (27,6%) — nella banda storica.
- **Worker restart events durante la sessione 19/08**: 0 — 24/24 cicli portfolio a cadenza 15 min esatti, 83/83 snapshot a cadenza 5 min (gap massimo 6 min), nessuna discontinuità. Il redeploy che ha azzerato i log è avvenuto il mattino successivo (20/08, 08:20-09:10 UTC), fuori dalla sessione di trading analizzata.
