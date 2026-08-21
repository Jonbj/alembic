# Forensic Daily Report — 2026-08-20

Analista: sessione autonoma Claude (Trading Systems Forensic Analyst + Senior Backend Engineer + Quant Operations Reviewer).
Modalità: read-only. Nessun ordine inviato, nessuna pipeline rieseguita, nessuna patch di codice applicata.
Timezone operativo: **UTC**, confermato in `src/workers/celery_app.py:51` (`timezone="UTC"`). Nessuna ambiguità di fuso nel codice; il difetto strutturale di allineamento DST (F-021) è documentato al §10.
Finestre usate in questo report: pre-market = prima delle 13:30 UTC; market hours = 13:30–20:00 UTC (NYSE 9:30–16:00 ET, confermato dai `portfolio_monitor_snapshots` che iniziano/finiscono lì); post-market = dopo le 20:00 UTC; batch giornalieri = task Celery schedulati (21:00 decay, 22:30 risk).

Nota di accesso: il bearer token fornito nel protocollo (`Authorization: Bearer <token>`) è stato verificato di nuovo oggi e restituisce ancora `403 Invalid or expired JWT token` su tutti gli endpoint (ricorrenza F-041). Dati ricostruiti via query dirette a Postgres, con conferma incrociata via `X-API-Key` sull'API REST per orders/positions.

## 1. Executive summary

Book paper (`alpaca_paper`) per tutta la giornata, nessun halt operatore, gate S4 al valore di design 0,30 (Redis `feedback:entry_threshold:S4`=0,3, nessuna deroga attiva), coppia LLM live `glm52,gptoss` invariata. 4 BUY (NVDA, WMT, NOW, AVGO) tutti sopra gate, 4 SELL, tutte e quattro le entrate della giornata **chiuse nella stessa sessione** (NVDA, WMT, NOW) o aperte da ieri e chiuse stamattina (HOOD): nessuna posizione S4 di oggi è sopravvissuta oltre le 20:00. Correttezza formale del money path intatta: nessun ordine fuori orario sui cicli regolari, nessun duplicato, nessuna violazione long-only, nessun trade su dati stale o LLM non validato, drawdown reale (0,72%) e gross exposure (31,5%) ben dentro i limiti (5%/50%). **Anomalia nuova e genuina**: un ordine BUY su **KO** (non in watchlist) è stato sottomesso al broker paper alle 08:35:51 UTC — 5h prima della prima news del giorno e del primo ciclo `portfolio_cycles` (14:07) — con **zero** riscontro in `execution_decisions`, `sentiment_signals`, `news_log` o `trades`; cancellato 6 secondi dopo, tracciato solo da `mobile_events`. Coincide con la finestra di redeploy dei container osservata ieri (08:20–09:10 UTC). Nessun fill, costo $0 verificato, ma è un ordine arrivato al broker senza alcuna catena segnale→decisione — nuovo finding F-042. Seconda anomalia rilevante: il BUY su WMT (16:37, sentiment +0,318 da un articolo PR sui rimborsi tariffari) è nato da un segnale con **ensemble_std=0,318**, sopra la soglia di divergenza 0,30 mai usata come gate (F-037) — un'ora dopo un articolo sui risultati Q2 ribalta il segnale a −0,704 e la posizione viene chiusa via `sentiment_reversal`; costo netto verificato $0 (+2,38 $) solo perché il prezzo si era già mosso prima dell'ingresso, ma la sequenza (news negativa delle 14:15 sugli utili, poi ignorata, poi articolo PR positivo alle 16:30 usato per il BUY) è una ricorrenza diretta di F-023. NOW chiude dopo 1h45 con l'`exit_mechanism='whipsaw'` e un flag `anti_whipsaw_shadow: would_suppress=True` che segnala come lo stesso sistema, in modalità shadow, avrebbe bloccato quest'uscita se il meccanismo fosse attivo — costo reale −19,60 $. NAV −245,52 $ (110.099,44 → 109.853,92 sul book paper: realizzato −78,57 su 4 round-trip S4, MTM −166,95), in linea con `market_daily.jsonl`. Giornata di rotazione settoriale (semiconduttori +, banche e WMT −9,16% su utili Q2 deboli). Tredici difetti già noti dal ledger ricorrono (F-003, F-004, F-007, F-011, F-012, F-013, F-014, F-015, F-019, F-020*, F-021, F-023, F-027, F-037, F-041); F-001 e F-002 sono già stati aggiornati oggi dal cron alpha-miss parallelo (non ri-toccati qui per evitare doppio conteggio). *F-020 idem.

## 2. Verdict finale

**OK con warning.**

Il processo end-to-end (news → segnale → decisione → ordine → fill → posizione) ha funzionato correttamente e in modo verificabile dal DB per i 4 cicli di trading effettivi. L'unico punto che eccede il consueto profilo "solo osservabilità" è l'ordine KO (§10, [DAY-601]): un ordine ha raggiunto il broker paper senza passare per nessuna tabella di decisione interna — non ha causato danno (canceled, mai fillato) ma è una violazione della garanzia "nessun ordine senza decisione tracciata" che il protocollo chiede esplicitamente di verificare. Tutti gli altri warning sono ricorrenze già tracciate, di sola osservabilità/misura o taratura congelata dalla carta.

## 3. Timeline del 2026-08-20 (UTC)

| Ora | Componente | Evento | Fonte |
|---|---|---|---|
| ~08:20–09:10 (dedotto, F-027) | infra | redeploy container (osservato indirettamente: nessun log del 20/08 sopravvive al successivo redeploy del 21/08 08:20) | `docker inspect` |
| **08:35:51** | broker (paper) | **BUY KO sottomesso** — nessuna riga in `execution_decisions`/`sentiment_signals`/`news_log`/`trades`, KO non è in watchlist, zero cicli `portfolio_cycles` in corso a quest'ora | orders API, `mobile_events` |
| 08:35:57 | mobile_events | evento `order:...:canceled` — "Ordine canceled per KO", `details.reason=null` | `mobile_events` |
| 13:30:00 | portfolio_monitor | primo snapshot NAV=110.081,02, nav_change_today=−10,99, 49 posizioni, gross_exposure 32,6% | `portfolio_monitor_snapshots` |
| 13:30:00–13:30:01 | mobile_events | falso allarme quotidiano "Ciclo di portafoglio in ritardo" + "Segnali sentiment in ritardo", `recovered` al primo ciclo — ricorrenza F-021 | `mobile_events` |
| 14:00:29 | sentiment worker | primo segnale della giornata (148 totali, ultimo 19:45:59) | `sentiment_signals` |
| 14:07:00 | execution | primo ciclo `portfolio_cycles`, **37 minuti dopo l'apertura NYSE** (13:30 UTC in EDT) — ricorrenza F-021 | `execution_decisions` |
| 14:15 | news ingest | earnings miss WMT ("US Sales Growth Hits Weakest Pace Since 2020") — sentiment −0,248, sotto gate, nessun ordine | `news_log` id 8407, `sentiment_signals` id 8407 |
| 14:22:00 | execution | **SELL HOOD** — `exit_mechanism='unknown'`, posizione aperta 08-19 16:07, segnale stale 22,4h ri-ammesso da FIX-D senza contro-segnale: "the mechanism that zeroed it is not recorded" (nota esplicita a #184, non è una mislabel per età) | `execution_decisions` id 12480 → `trades` id 749 |
| 15:22:00 | execution | **BUY NVDA** — sentiment +0,321 (ensemble), articolo dedicato su un accordo multibillion-dollar GPU | `execution_decisions` id 12563 → `trades` id 752 |
| 15:37:11 | portfolio_scheduler | stop protettivo GTC creato per NVDA (qty floor 8) | orders API |
| 16:30:27 | sentiment worker | **WMT** segnata +0,318 da articolo PR sui rimborsi tariffari — **ensemble_std=0,318, sopra soglia divergenza 0,30 (F-037), nessun gate** | `sentiment_signals` id 8472 |
| 16:37:00 | execution | **BUY WMT** — peso 2,0%, articolo PR sui rimborsi tariffari, WMT già −9% da news delle 14:15 non riconsiderata (F-023) | `execution_decisions` id 12716 → `trades` id 753 |
| 16:52:00 | execution | **BUY NOW** — sentiment +0,464, articolo listicle "Software's AI Panic Is Fading" (3 ticker condivisi: ADBE/NOW/SNOW, F-012) + upgrade BofA | `execution_decisions` id 12748 → `trades` id 754 |
| 17:07:00 | execution | **BUY AVGO** — sentiment +0,469, articolo "Broadcom's AI Competition Fears Look Overblown" (8 ticker condivisi via fan-out: AAPL/AMD/ARM/AVGO/BABA/GOOGL/META/MRVL, F-012 — contenuto genuinamente su AVGO) | `execution_decisions` id 12780 → `trades` id 755 |
| 17:07:00 | execution | **SELL NVDA** — `below_entry_gate`, segnale fresco score +0,035 (age 1,1h), roundtrip 1h45, net −1,03 | `execution_decisions` id 12781 → `trades` id 752 |
| 17:30:07 | sentiment worker | WMT segnata −0,704 (conf 0,85) da articolo su calo azionario post-Q2 | `sentiment_signals` id 8497 |
| 17:37:00 | execution | **SELL WMT** — `sentiment_reversal: score −0,704 < soglia −0,35`, roundtrip 60 min, net +2,38 | `execution_decisions` id 12846 → `trades` id 753 |
| 18:15:18 | sentiment worker | **MRK fallback FinBERT** — reasoning "FinBERT fallback (ensemble divergence)", ensemble_std sottostante 0,3536 | `sentiment_signals` id 8524 |
| 18:37:00 | execution | **SELL NOW** — `exit_mechanism='whipsaw'`: "signal reached the portfolio engine fresh and is not driving a position — rank cutoff/min_score/portfolio constraint", **`anti_whipsaw_shadow: would_suppress=True, streak=1/2`**, roundtrip 1h45, net −19,60 | `execution_decisions` id 12961 → `trades` id 754 |
| 20:00:00 | portfolio_monitor | ultimo snapshot NAV=109.853,92, nav_change_today=−238,09 (vs prev_close 110.092,01), 49 posizioni, gross_exposure 31,5%, drawdown 0,72% | `portfolio_monitor_snapshots` |
| 21:00:00 | decay_monitor | `decay_reports`: 12 righe, actual identici S1/S2/S4, CRITICAL su hit_rate/sharpe anche per S2 mai tradata — ricorrenza F-004 | `decay_reports` |
| 22:30:00 | risk_monitor | `risk_reports` id: combined_drawdown 1,24% vs per_strategy portfolio.drawdown 17,75% → ALERT falso "17.8% exceeds 10%"; nav=109.825,70 vs ultimo snapshot 109.853,92 (scarto −28,22) — ricorrenza F-003 | `risk_reports` |
| AVGO resta aperta a fine giornata (nessuna exit) | | | `trades` id 755 |

Nessuna news con timestamp futuro (verificato: 0 righe `published_at > created_at + 1h`), nessun buco intraday nei 5-minute snapshot (13:30→20:00, 86 righe, cadenza regolare).

## 4. Tabella news ingest

| Fonte | Fetched | Queued | Duplicates | Discarded (no ticker) | Landed in `news_log` |
|---|---|---|---|---|---|
| alpaca_benzinga | 628 | 330 | **2.848** (4,5× fetched — F-007) | 0 | 90 |
| gdelt_gkg | 1.937 | 91 | 12 | 1.842 | 58 |
| **Totale** | 2.565 | 421 | — | 1.842 | **148** |

- Copertura watchlist: 55 ticker distinti su 96 (41 a copertura zero, 43%) — dentro la banda 38-57% osservata dal 31/07 (F-001, già aggiornata oggi dal cron alpha-miss).
- Latenza mediana `created_at − published_at`: 72,5 min (alpaca_benzinga, n=90, max 117,6) e 75,6 min (gdelt_gkg, n=58, max 105,8), contro `MAX_NEWS_AGE_HOURS=2,0h` — 60-63% della finestra di freschezza consumata alla nascita del segnale, in linea con la serie storica (F-019).
- 58 righe (19 MS, 6 DB, 6 MU, 5 DIS, 5 GS, 3 TM, + 13 minori) attribuite via `extraction_method=org_lookup`; campione MS verificato titolo per titolo il 08-20 dal cron alpha-miss: 19/19 righe su società terze (Honeywell Aerospace, Aegon, Cencora, RTX, Birkenstock) — ricorrenza esatta F-020 (già aggiornata oggi da quel cron).
- Fan-out multi-ticker: 21 `content_hash` condivisi coprono **68/148 righe (46%)** — in linea con il trend discendente ma ancora quasi metà della copertura apparente. Il gruppo più ampio (13 ticker: AAPL, AMAT, AVGO, COST, DELL, GOOGL, MA, META, MRVL, MU, NVDA, V, WDC) e un secondo da 8 ticker (AAPL, AMD, ARM, AVGO, BABA, GOOGL, META, MRVL — "Broadcom's AI Competition Fears Look Overblown") sono entrambi articoli reali su un singolo emittente/tema riletti su tutti i ticker citati nel testo, non spam — ma **2 dei 4 BUY di oggi (NOW, AVGO) nascono da articoli fan-out** (F-012), a differenza dell'08-19 dove nessuno dei 3 BUY lo faceva.
- Nessuna news con timestamp futuro, nessun campo obbligatorio mancante, nessun `parse_fail`.
- Nessun `discarded_reason` popolato su alcuna riga atterrata (0/148).

## 5. Tabella performance modelli LLM

| Model_id | Fallback | N | Score medio | Confidence media | Note |
|---|---|---|---|---|---|
| ensemble:glm-5.2:cloud+gpt-oss:20b-cloud | No | 103 (69,6%) | +0,021 | 0,316 | Ensemble dual-model |
| single:gpt-oss:20b-cloud | Sì | 41 (27,7%) | −0,002 | 0,507 | Un modello sotto floor confidence |
| single:glm-5.2:cloud | Sì | 3 (2,0%) | −0,060 | 0,600 | Un modello sotto floor confidence |
| finbert | Sì | 1 (0,7%) | +0,264 | 0,459 | **MRK**, esplicitamente "FinBERT fallback (ensemble divergence)" — ensemble_std sottostante 0,3536 |
| **Totale** | — | **148** | — | — | |

- `llm_responses`: glm-5.2 eligible=true 30/148 (20,3%), gpt-oss eligible=true 30/148 (20,3%) — stesso fenomeno noto, non associato a F-010 oggi.
- Nessun errore/timeout osservabile a livello di log: **i log Docker del 20/08 non sono sopravvissuti al successivo redeploy del 21/08 08:20 UTC** (F-027) — latenza per-chiamata e conteggio retry non verificabili, solo dal DB.
- Ensemble variance: 2 righe con `ensemble_std ≥ 0,30` (soglia divergenza citata da F-037) su 103 non-fallback (1,9%) — MRK (0,3536, correttamente deviato a FinBERT) e **WMT alle 16:30 (0,318, NON deviato, generatore diretto del BUY delle 16:37)**. La divergenza non è mai un gate d'ingresso (F-037, ricorrenza oggi): stesso giorno, due segnali sopra soglia, trattamento incoerente (uno fallback, uno ensemble pieno usato per un ordine reale).
- Validazione a monte confermata: `sentiment_signals.news_log_id` popolato su 148/148 righe (0 orfani), 0 coppie `(news_log_id, symbol)` duplicate — l'anello news→segnale non genera segnali multipli dalla stessa notizia.
- Prompt DK-CoT confermato in produzione: i `reason` dei BUY riportano esplicitamente casi Bull/Bear (es. NVDA "Bull: the new multibillion-dollar deal... Bear: minimal downside risk...").
- Chiamate LLM offline/background confermate: nessuna chiamata sincrona nel loop di esecuzione, tutte le decisioni leggono da `sentiment_signals` pre-calcolato.

## 6. Tabella segnali finali per ticker (money path)

| Ticker | Ora segnale | Score | ensemble_std | Sopra gate 0,30? | Esito |
|---|---|---|---|---|---|
| NVDA | 15:07 | +0,321 | — | Sì | BUY 15:22 (peso 2,0%) |
| WMT | 16:30 | +0,318 | **0,318** | Sì | BUY 16:37 (peso 2,0%) |
| NOW | 16:45 | +0,464 | — | Sì | BUY 16:52 (peso 2,0%) |
| AVGO | 17:01 | +0,469 | — | Sì | BUY 17:07 (peso 2,0%) |
| NVDA | 16:00 | +0,035 | — | No | SELL below_entry_gate (posizione stessa giornata) |
| WMT | 17:30 | −0,704 | — | No (reversal) | SELL sentiment_reversal |
| NOW | 18:00 | +0,251 | — | No (rank/whipsaw) | SELL whipsaw (anti_whipsaw_shadow would_suppress=True) |
| HOOD | 08-19 16:00 (stale) | +0,350 | — | n/a | SELL exit_mechanism=unknown, FIX-D re-ammesso senza contro-segnale |
| BP | — (NO_NEWS) | — | — | — | Miss, mover +3,22%, costo $70,94 (F-001, già in ledger oggi) |
| GE | — (NO_NEWS) | — | — | — | Posizione S1 detenuta, mover −3,25%, copertura zero anche in uscita (F-001) |
| MS | 17:30 | +0,143 (debole) | — | No | Posizione legacy detenuta, mover −3,16%, 19/19 news via org_lookup su terzi (F-020) |
| 8 simboli (UNH, WDC, NFLX×2, NVDA, MRVL, XOM, AMAT) | vari | >0,30 | — | Sì | SKIP_PYRAMIDING — già a libro S1/legacy, traccia esplicita |
| SOXX | −0,263 | — | — | — | SKIP_STALE (4,1h > max 4h) |
| ARM | +0,180 | — | — | — | SKIP_FALLBACK, single-model esclusa dal ranking (#108) |

## 7. Tabella ordini generati/eseguiti

| Ora | Symbol | Side | Qty | Prezzo fill | Stato | Decision_id | Trade_id | Note |
|---|---|---|---|---|---|---|---|---|
| **08:35:51** | **KO** | **BUY** | — | — | **canceled** | — | — | **Nessuna decisione/segnale associato — F-042** |
| 14:22:14 | HOOD | SELL | 18,648487 | 95,28 | filled | 12480 | 749 | exit_mechanism=unknown (#184) |
| 15:22:10 | NVDA | BUY | 8,595977 | 217,238836 | filled | 12563 | 752 | S4 news-driven |
| 15:37:11 | NVDA | SELL (stop GTC) | 8 | — | canceled | — | — | protettivo, cancellato alla chiusura decisionale |
| 16:37:09 | WMT | BUY | 17,950959 | 103,79 | filled | 12716 | 753 | S4 news-driven, ensemble_std 0,318 |
| 16:52:09 | WMT | SELL (stop GTC) | 17 | — | canceled | — | — | protettivo, cancellato alla chiusura |
| 16:52:09 | NOW | BUY | 14,279128 | 130,80 | filled | 12748 | 754 | S4 news-driven, articolo fan-out 3 ticker |
| 17:07:10 | NOW | SELL (stop GTC) | 14 | — | canceled | — | — | protettivo, cancellato alla chiusura |
| 17:07:10 | NVDA | SELL | 8,595977 | 217,16302 | filled | 12781 | 752 | below_entry_gate |
| 17:07:10 | AVGO | BUY | 5,136012 | 363,13 | filled | 12780 | 755 | S4 news-driven, articolo fan-out 8 ticker |
| 17:22:09 | AVGO | SELL (stop GTC) | 5 | — | new (resting) | — | — | protettivo, posizione ancora aperta a fine giornata |
| 17:37:13 | WMT | SELL | 17,950959 | 103,98 | filled | 12846 | 753 | sentiment_reversal |
| 18:37:12 | NOW | SELL | 14,279128 | 129,50 | filled | 12961 | 754 | whipsaw + anti_whipsaw_shadow flag |

`portfolio_cycles`: 24 cicli, `orders_count` somma 119 contro 12 ordini realmente inviati al broker (13 con KO, rapporto ~9,9:1) — il campo conta gli ordini target del combiner prima dei guard, non i submitted (ricorrenza F-014).

## 8. Tabella PnL/rendimento

| Voce | Valore |
|---|---|
| NAV apertura (13:30) | 110.081,02 $ |
| NAV chiusura (20:00) | 109.853,92 $ |
| Variazione NAV giornaliera (`nav_change_today`, vs prev_close 110.092,01) | **−238,09 $ (−0,22%)** |
| Realizzato (4 trade chiusi: NVDA −1,03, WMT +2,38, NOW −19,60, HOOD −60,32) | **−78,57 $** |
| MTM su book esistente (per differenza) | ≈ **−159,52 $** (market_daily.jsonl riporta −166,95, scarto ≈7,4 $ non riconciliato — variante minore, non isolata come nuovo finding) |
| SPY (return giorno) | −0,84% |
| QQQ (return giorno) | −0,72% |
| Gross exposure fine giornata | 31,5% (limite 50%) |
| Drawdown corrente fine giornata (snapshot reale) | 0,72% (limite 5%) |
| Drawdown "ALERT" da `risk_reports` (falso, F-003) | 17,75% |

Fonte incrociata: `market_daily.jsonl` riga 2026-08-20 (equity 109.853,92, realizzato −78,57, mtm −166,95, somma −245,52) — la somma coincide con l'equity solo assumendo un NAV di riferimento diverso da `nav_change_today` (110.092,01 −245,52 = 109.846,49 ≠ 109.853,92). Scarto ≈7,43 $ tra le due ricostruzioni del giorno; troppo piccolo per meritare nuovo finding isolato ma coerente con la famiglia di incoerenze di misura già tracciata (F-003).

Rotazione settoriale: semiconduttori in controtendenza positiva (MRVL +5,79%, MU +3,97%, TSM/AVGO/AMD/SOXX tutti positivi) mentre l'indice ampio è debole (SPY −0,84%, QQQ −0,72%) e il comparto bancario cede in blocco (MS −3,16%, JPM/BAC/GS/WFC/C/AXP tutti negativi). WMT −9,16% è un evento idiosincratico isolato su utili Q2 deboli.

Le 4 posizioni S4 aperte e chiuse in giornata (o chiuse stamattina) hanno un netto di −78,57 $, trainato quasi interamente da HOOD (−60,32, posizione aperta dal 08-19). Le 3 vere posizioni intraday (NVDA, WMT, NOW) sommano −18,25 $ (NVDA −1,03, WMT +2,38, NOW −19,60).

Slippage: non misurabile separatamente dal costo modellato — `trades.slippage_est` è identico bit-per-bit a `cost_usd` su tutte le 4 chiusure di oggi, ricorrenza F-015.

11 posizioni legacy senza `stop_strategy` (BAC, GOOGL, GS, MS, PBR, RIO, ROKU, SPY, UBS, UNH, XLE, tutte entrate 07-10) restano fuori da qualunque split S1/S4 — 14a sessione consecutiva, F-002 già aggiornata oggi dal cron alpha-miss.

## 9. Analisi correttezza buy/sell

- **BUY generati solo quando consentito**: sì, tutti e 4 sopra gate 0,30 di design (0,321/0,318/0,464/0,469), nessuna deroga attiva, `regime_mult`=1.
- **SELL/exit generati correttamente**: sì per il meccanismo formale — `below_entry_gate` (NVDA), `sentiment_reversal` (WMT), `whipsaw` (NOW), `unknown` esplicito con causa dichiarata (HOOD, #184). Nessuna mislabel per età: tutti i 4 record hanno `exit_mechanism`/reason popolati direttamente dalla decisione, non dedotti.
- **Stop-loss rispettati**: sì, meccanismo broker-side GTC attivo su tutte le nuove posizioni (§11); nessuno stop scattato per prezzo oggi, tutte le uscite sono decisionali.
- **Signal flip rispettato**: sì — WMT è l'unico flip di segno (+0,318 → −0,704) e ha prodotto correttamente un SELL via `sentiment_reversal`.
- **SELL su sentiment positivo (pattern A5)**: nessuno oggi (a differenza dell'08-19).
- **Max holding days**: nessuna violazione osservabile oggi; WDC resta eccezione strutturale nota (F-025), non movimentata oggi.
- **Rebalance band**: nessuna banda fra gate d'ingresso e uscita per design (F-013, taratura congelata).
- **Ordini duplicati**: nessuno fra i 12 ordini regolari; l'ordine KO è un'anomalia di provenienza, non un duplicato.
- **Ordini contrari ravvicinati senza rationale**: NVDA (BUY 15:22 → SELL 17:07, 1h45) e NOW (BUY 16:52 → SELL 18:37, 1h45) hanno rationale esplicito nel `reason` (below_entry_gate, whipsaw) — pattern noto F-013, non un bug isolato.
- **Ordini su ticker non consentiti**: **KO non è in watchlist** (verificato: 0 occorrenze in `execution_decisions`/`sentiment_signals`/`news_log` in tutta la storia del DB) — vedi [DAY-601].
- **Ordini fuori orario**: l'ordine KO delle 08:35:51 è **fuori dalla finestra di mercato e fuori da ogni ciclo regolare** (primo ciclo reale alle 14:07) — vedi [DAY-601]. Tutti gli altri 12 ordini sono dentro 14:22-18:37.
- **Trade su dati stale**: 1 `SKIP_STALE` (SOXX, 4,1h) correttamente scartato; HOOD è un caso di segnale stale **ri-ammesso da FIX-D** e correttamente chiuso con `exit_mechanism=unknown` (non è un trade "su dati stale", è la chiusura di una posizione il cui segnale era stale).
- **Trade con LLM output non valido**: nessuno rilevabile nei 4 BUY (tutti ensemble non-fallback); da segnalare che **1 segnale (WMT) sopra soglia di divergenza ensemble non è stato deviato a fallback** pur avendo `ensemble_std`=0,318 — F-037.
- **Circuit breaker attivo**: no, `system:halted_by_operator` non impostato in Redis.
- **Strategia disabilitata**: S2 correttamente `disabled`, nessun trade S2; S1/S4 `paper`, coerente.
- **Paper/live coerente**: `broker_environment`/`mode` = `paper` su tutti gli 86 snapshot del giorno.
- **Idempotenza Celery**: nessuna evidenza di doppio invio per lo stesso ciclo sui 12 ordini regolari; l'ordine KO non è collegabile a nessun ciclo, quindi non è classificabile come "doppio invio" — è un ordine di origine ignota.
- **Reconciliation ordini/fill/posizioni**: coerente sui 4 BUY/4 SELL regolari — corrispondono 1:1 a righe `trades`; le posizioni API riflettono le quantità nette attese (AVGO ancora aperta). L'ordine KO **non riconcilia con nulla**: nessuna posizione KO, nessun trade KO, mai fillato.

## 10. Anomalie trovate

### [DAY-601] Ordine BUY su KO senza segnale, decisione o trade associato — fuori orario, fuori watchlist

* Tipo: Bug
* Area: Orders / Ops
* Evidenza:
  * file/log/tabella: orders API (`GET /api/orders`), `mobile_events`
  * timestamp: 2026-08-20 08:35:51 UTC (submitted), 08:35:57 (canceled, osservato da mobile_events)
  * snippet/query: `{"id":"24b237ab-d0de-47d2-a948-507cdff0ae8b","symbol":"KO","side":"buy","status":"canceled","submitted_at":"2026-08-20T08:35:51...","signal_id":null,"decision_id":null,"news_log_id":null,"trade_id":null}`; `SELECT * FROM execution_decisions WHERE symbol='KO'` → 0 righe in tutta la storia; `SELECT * FROM sentiment_signals WHERE symbol='KO'` → 0 righe; `SELECT * FROM news_log WHERE ticker='KO'` → 0 righe; KO non compare in `config/trading.yaml` (watchlist); primo ciclo `portfolio_cycles` del giorno alle 14:07, 5h32m dopo l'ordine
* Descrizione: un ordine BUY per KO ha raggiunto il broker paper alle 08:35:51 UTC, prima di qualunque news, segnale, ciclo di portafoglio o apertura di mercato del giorno, su un simbolo che non è mai stato toccato dal sistema (zero righe in qualunque tabella applicativa, in tutta la storia del DB, per questo ticker). L'unico riscontro è l'evento `mobile_events` che conferma la cancellazione 6 secondi dopo con `reason: null` — anche il monitor esterno non conosce la causa. Il timing coincide con la finestra di redeploy dei container osservata il mattino del 20/08 (08:20-09:10 UTC, dal report dell'08-19), ma i log applicativi di quella finestra non sono sopravvissuti al redeploy successivo del 21/08 (F-027), quindi la causa esatta non è verificabile da questa sessione: ipotesi plausibile ma non confermata è una redelivery Celery at-least-once di un task residuo dal riavvio del worker.
* Impatto: nessun impatto P&L (ordine mai fillato). Impatto di correttezza: dimostra che esiste almeno un percorso per cui un ordine raggiunge il broker senza passare per `execution_decisions`/`sentiment_signals` — l'invariante "nessun ordine senza una decisione tracciata" non è garantita end-to-end. Se un ordine simile fosse stato eseguito invece che cancellato, sarebbe stata una posizione aperta senza alcuna traccia di rationale, segnale o strategia di appartenenza.
* Severità: High
* Confidenza: High (evidenza diretta su 3 fonti indipendenti: orders API, mobile_events, assenza totale in ogni tabella di decisione), Medium sulla causa radice (non verificabile per i log mancanti)
* Azione consigliata: aprire un'issue per instrumentare l'origine di ogni ordine sottomesso al broker (es. tag obbligatorio `source_task_id`/`decision_id` a livello di client Alpaca, rifiuto lato codice di ordini senza provenienza tracciata) e verificare se esiste un percorso di startup/reconciliation che possa sottomettere ordini; controllare se altri simboli fuori watchlist hanno mai generato ordini simili in passato.
* Test/monitor consigliato: alert immediato su qualunque ordine con `signal_id`/`decision_id` nulli sottomesso al broker (non solo sugli stop protettivi noti, che sono l'unica eccezione legittima già mappata); alert su ordini sottomessi fuori dalle finestre `portfolio_cycles` attese.

### [DAY-602] ensemble_std sopra soglia di divergenza (0,318) non gating l'ingresso su WMT, poi reversal in un'ora

* Tipo: Difetto
* Area: LLM / Signal
* Evidenza:
  * file/log/tabella: `sentiment_signals` id 8472, `execution_decisions` id 12716 → 12846
  * timestamp: 2026-08-20 16:30:27 (segnale), 16:37:00 (BUY), 17:30:07 (segnale reversal), 17:37:00 (SELL)
  * snippet/query: `ensemble_std=0.31819805153394637` su WMT id 8472 (score +0,318, confidence 0,7); stesso giorno MRK id 8524 con `ensemble_std=0.3536` è correttamente deviato a `model_id='finbert'`, WMT no
* Descrizione: ricorrenza F-037 — la divergenza fra i due modelli dell'ensemble non è mai un gate d'ingresso, solo letta a posteriori dal postmortem. Oggi il caso è diretto: il segnale usato per il BUY WMT aveva una divergenza sopra la soglia (0,30) usata altrove nello stesso giorno per deviare MRK a FinBERT, ma non è stato deviato — un'ora dopo un nuovo articolo (sui risultati Q2, non collegato all'ensemble std) ha ribaltato il segnale a −0,704 e la posizione è stata chiusa in perdita di prezzo (ma guadagno netto +2,38 $ per timing fortuito).
* Impatto: costo verificato $0 su questo caso specifico (il prezzo si era già mosso prima dell'ingresso), ma il meccanismo resta strutturalmente esposto: un ingresso con alta divergenza fra i due modelli non riceve nessun trattamento diverso da un ingresso con pieno accordo.
* Severità: Medium
* Confidenza: High
* Azione consigliata: nessuna nuova, F-037 già tracciato; segnalare come evidenza aggiuntiva del ticket esistente.
* Test/monitor consigliato: già proposto sulle occorrenze precedenti (gate su `ensemble_std` all'ingresso, non solo lettura postmortem).

### [DAY-603] BUY WMT ignora un segnale negativo delle stesse ore su un articolo di utili, sostituito da un PR positivo (F-023)

* Tipo: Difetto
* Area: Signal
* Evidenza:
  * file/log/tabella: `sentiment_signals` id 8407 (14:15, score −0,248, "Weakest Pace Since 2020"), id 8472 (16:30, score +0,318, "Tariff Refund To Keep Prices Low")
  * timestamp: 2026-08-20 14:15:21 → 16:30:27 → 16:37:00 (BUY)
  * snippet/query: due articoli WMT nella stessa giornata, il primo (pre-market, sotto gate) correttamente negativo sugli utili deboli, il secondo (PR minore sui rimborsi tariffari) positivo e sopra gate — S4 usa solo l'ultimo segnale per simbolo, quindi il secondo sostituisce il primo senza alcuna memoria del contesto
* Descrizione: ricorrenza F-023 in una forma diversa dalle precedenti — non un segnale forte sovrascritto da uno debole pochi secondi dopo, ma un segnale correttamente negativo (coerente con un titolo già in calo per utili deboli) sostituito 2h15m dopo da un segnale positivo generato da un comunicato PR secondario, senza che il sistema tenga conto del fatto che il titolo era già sceso pesantemente nel frattempo (conferma nell'articolo delle 17:15 "Walmart Shares Drop After Q2 Results", pubblicato prima ancora della SELL).
* Impatto: costo verificato $0 sul trade di oggi (net +2,38 $), ma il pattern espone il sistema al rischio di comprare in mezzo a un crollo guidato da notizie reali, sulla sola base dell'articolo più recente indipendentemente dal contesto price-action/notizie concorrenti dello stesso giorno.
* Severità: Medium
* Confidenza: High
* Azione consigliata: nessuna nuova, F-023 già tracciato.
* Test/monitor consigliato: già proposto (finestra di consolidamento multi-segnale invece di "solo l'ultimo").

### [DAY-604] SELL NOW via whipsaw con flag shadow "would_suppress=True" non applicato

* Tipo: Difetto
* Area: Orders / Risk
* Evidenza:
  * file/log/tabella: `execution_decisions` id 12961
  * timestamp: 2026-08-20 18:37:00
  * snippet/query: reason `[whipsaw] ... rank cutoff, min_score or a portfolio constraint ... [anti_whipsaw_shadow: would_suppress=True, streak=1/2]`; posizione aperta 16:52, chiusa 18:37 (1h45), `trades` id 754 net −19,60
  * `trades` id 754: entry 130,80, exit 129,50, net_pnl −19,60
* Descrizione: il sistema ha una logica di soppressione anti-whipsaw in modalità **shadow** (non applicata alle decisioni reali) che avrebbe bloccato questa uscita se attiva. La posizione NOW, aperta da un segnale sopra gate (+0,464) e chiusa 1h45 dopo per un vincolo di ranking del portfolio (non un segnale contrario), è esattamente il tipo di churn che il meccanismo shadow è progettato per intercettare — ma la conferma "would_suppress=True" arriva solo dopo che l'ordine è già stato eseguito, con una perdita reale.
* Impatto: −19,60 $ misurati su questo trade; il meccanismo esiste già in codice ma non è ancora in produzione, quindi il costo si ripete a ogni occorrenza dello stesso pattern finché resta shadow-only.
* Severità: Medium
* Confidenza: High (costo misurato direttamente da `trades.net_pnl`)
* Azione consigliata: **nessuna proposta di flip** — l'attivazione del meccanismo anti-whipsaw è una modifica di taratura/comportamento, non un difetto di correttezza secondo il test della carta di osservazione (§ Cosa è esente): non corregge un dato sbagliato, cambia una decisione di trading. Registrare la ricorrenza per quantificare il costo cumulato della shadow-window, decisione di flip resta all'operatore al 28/09.
* Test/monitor consigliato: dashboard che sommi il P&L dei soli round-trip con `anti_whipsaw_shadow.would_suppress=True`, per stimare il beneficio atteso di un eventuale flip.

### [DAY-605] Fan-out multi-ticker entra nel money path: 2 dei 4 BUY di oggi nascono da articoli condivisi

* Tipo: Difetto
* Area: News / Signal
* Evidenza:
  * file/log/tabella: `news_log`, `sentiment_signals`
  * timestamp: 2026-08-20 16:45-17:07
  * snippet/query: NOW (id 8478) condivide `content_hash` con ADBE/SNOW (articolo listicle "Software's AI Panic Is Fading"); AVGO (id 8491) condivide `content_hash` con AAPL/AMD/ARM/BABA/GOOGL/META/MRVL (articolo "Broadcom's AI Competition Fears Look Overblown", genuinamente su AVGO ma riletto su 7 altri ticker citati nel testo)
* Descrizione: ricorrenza F-012, con novità rispetto all'08-19 (dove nessuno dei 3 BUY nasceva da fan-out): oggi 2 BUY su 4 originano da articoli condivisi. Il caso AVGO è meno preoccupante (l'articolo è realmente su Broadcom), il caso NOW è un listicle generico applicato identicamente a 3 ticker.
* Impatto: nessun costo isolabile attribuibile specificamente al fan-out (la perdita NOW di −19,60 $ è spiegata da whipsaw, non da attribuzione errata del ticker); resta il rischio strutturale che lo stesso articolo generi segnali indipendenti per ticker solo menzionati nel testo.
* Severità: Low
* Confidenza: High
* Azione consigliata: nessuna nuova, F-012 già tracciato.
* Test/monitor consigliato: già proposto.

### [DAY-606] risk_reports: doppia cifra di drawdown (1,24% vs 17,75% vs 0,72% reale)

* Tipo: Difetto
* Area: Risk
* Evidenza:
  * file/log/tabella: `risk_reports`, 2026-08-20 22:30:00
  * timestamp: 2026-08-20 22:30:00
  * snippet/query: `combined_drawdown=0.012429` (1,24%, invariato dal 07-31) vs `per_strategy_metrics->portfolio->drawdown=0.1775` (17,75%) → ALERT "17.8% exceeds 10%"; `current_drawdown` reale da `portfolio_monitor_snapshots` delle 20:00 = 0,72%; nav=109.825,70 vs ultimo snapshot 109.853,92 (scarto −28,22 $, contenuto rispetto alla serie recente)
* Descrizione: ricorrenza esatta F-003.
* Impatto: nessun ordine dipende da questo record; l'ALERT quotidiano resta rumore.
* Severità: Medium
* Confidenza: High
* Azione consigliata: nessuna nuova, F-003 già tracciato.
* Test/monitor consigliato: già proposto.

### [DAY-607] decay_reports: metriche pipeline-globali identiche su S1/S2/S4, inclusa S2 mai tradata

* Tipo: Difetto
* Area: Risk
* Evidenza:
  * file/log/tabella: `decay_reports`, 2026-08-20 21:00:00
  * timestamp: 2026-08-20 21:00:00
  * snippet/query: hit_rate 0,2919, ic 0,0223, max_drawdown 0,1194, sharpe −6,027 identici su tutte e tre le righe; S1 CRITICAL su hit_rate/sharpe, S2 (mai un trade) CRITICAL su hit_rate/sharpe, S4 WARNING/CRITICAL
* Descrizione: ricorrenza F-004.
* Impatto: il monitor di decadimento non può distinguere S1 da S4.
* Severità: Medium
* Confidenza: High
* Azione consigliata: nessuna nuova, F-004 già tracciato.
* Test/monitor consigliato: già proposto.

### [DAY-608] execution_decisions.signal_id NULL su 608/617 righe (98,5%)

* Tipo: Difetto
* Area: Signal
* Evidenza:
  * file/log/tabella: `execution_decisions`
  * timestamp: 2026-08-20
  * snippet/query: 617 righe totali, 9 con `signal_id` valorizzato (4 BUY su 4, 5 SKIP_PYRAMIDING su 8)
* Descrizione: ricorrenza F-011, in linea con la serie.
* Impatto: la catena segnale→decisione→trade sulle uscite resta ricostruibile solo per testo libero del `reason`.
* Severità: Low
* Confidenza: High
* Azione consigliata: nessuna nuova, F-011 già tracciato.
* Test/monitor consigliato: già proposto.

### [DAY-609] ingestion_stats_daily: duplicati Benzinga 4,5× il fetched

* Tipo: Osservazione
* Area: Data
* Evidenza:
  * file/log/tabella: `ingestion_stats_daily`
  * timestamp: 2026-08-20
  * snippet/query: alpaca_benzinga fetched=628, duplicates=2.848
* Descrizione: ricorrenza F-007.
* Impatto: il contatore non è utilizzabile come metrica di copertura news.
* Severità: Low
* Confidenza: High
* Azione consigliata: nessuna nuova, F-007 già tracciato.
* Test/monitor consigliato: già proposto.

### [DAY-610] trades.slippage_est identico a cost_usd

* Tipo: Difetto
* Area: PnL
* Evidenza:
  * file/log/tabella: `trades` id 749, 752, 753, 754
  * timestamp: 2026-08-20
  * snippet/query: tutte e 4 le chiusure hanno `slippage_est == cost_usd` bit-per-bit
* Descrizione: ricorrenza F-015.
* Impatto: la qualità di esecuzione non è misurata da nessuna colonna del DB.
* Severità: Low
* Confidenza: High
* Azione consigliata: nessuna nuova, F-015 già tracciato.
* Test/monitor consigliato: già proposto.

### [DAY-611] portfolio_cycles.orders_count: 119 target contro 12 ordini realmente inviati (+1 anomalo)

* Tipo: Difetto
* Area: Orders
* Evidenza:
  * file/log/tabella: `portfolio_cycles`
  * timestamp: 2026-08-20
  * snippet/query: 24 cicli, sum(orders_count)=119, 12 ordini regolari inviati (rapporto ~9,9:1)
* Descrizione: ricorrenza F-014.
* Impatto: la metrica di attività del sistema è sbagliata di un fattore ~10x; nessun impatto P&L.
* Severità: Low
* Confidenza: High
* Azione consigliata: nessuna nuova, F-014 già tracciato.
* Test/monitor consigliato: già proposto.

### [DAY-612] Latenza ingestione news: mediana 72-76 minuti

* Tipo: Difetto
* Area: News
* Evidenza:
  * file/log/tabella: `news_log`
  * timestamp: 2026-08-20
  * snippet/query: alpaca_benzinga mediana 72,5 min (n=90), gdelt_gkg 75,6 min (n=58)
* Descrizione: ricorrenza F-019.
* Impatto: 60-63% della finestra di freschezza (120 min) consumata alla nascita del segnale.
* Severità: Low
* Confidenza: High
* Azione consigliata: nessuna nuova, F-019 già tracciato.
* Test/monitor consigliato: già proposto.

### [DAY-613] Finestra beat UTC fissa ignora il DST: 37 minuti di sessione scoperti

* Tipo: Difetto
* Area: Ops
* Evidenza:
  * file/log/tabella: `execution_decisions`, `portfolio_cycles`
  * timestamp: 2026-08-20 14:07:00
  * snippet/query: primo ciclo 14:07:00 UTC contro apertura NYSE 13:30 UTC (EDT)
* Descrizione: ricorrenza F-021, col consueto falso allarme auto-risolto in `mobile_events`.
* Impatto: 37 minuti di sessione senza ingest/scoring/cicli ogni giorno feriale per ~8 mesi l'anno.
* Severità: Low
* Confidenza: High
* Azione consigliata: nessuna nuova, F-021 già tracciato.
* Test/monitor consigliato: già proposto.

### [DAY-614] Log Docker del 20/08 azzerati dal redeploy del 21/08 prima della lettura

* Tipo: Difetto
* Area: Ops
* Evidenza:
  * file/log/tabella: `docker inspect`
  * timestamp: 2026-08-21 08:20:10 UTC (StartedAt worker/api/worker-inference/beat)
  * snippet/query: `docker compose logs worker --since 48h` non contiene righe precedenti al 21/08; 1.061 righe totali, tutte post-restart
* Descrizione: ricorrenza F-027, con impatto diretto su [DAY-601]: impossibile verificare la causa radice dell'ordine KO.
* Impatto: latenza/errori/timeout LLM, retry, eccezioni non propagate non verificabili per il 20/08; ogni affermazione di questo report viene dal solo DB.
* Severità: Medium (elevata oggi dal collegamento diretto con [DAY-601])
* Confidenza: High
* Azione consigliata: nessuna nuova, F-027 già tracciato (P0, TK-R2) — la ricorrenza di oggi rafforza la priorità.
* Test/monitor consigliato: già proposto (logging persistente su storage esterno al container).

### [DAY-615] Bearer token del protocollo forense rifiutato su tutti gli endpoint REST

* Tipo: Difetto
* Area: Ops
* Evidenza:
  * file/log/tabella: API `/api/positions`
  * timestamp: 2026-08-21 (verifica di questa sessione)
  * snippet/query: `Authorization: Bearer <token>` → `403 Invalid or expired JWT token`; stesso token con `X-API-Key` → `200 OK`
* Descrizione: ricorrenza F-041.
* Impatto: nessuno sul trading; impatto sul protocollo di analisi, mitigato dal fallback DB/`X-API-Key`.
* Severità: Low
* Confidenza: High
* Azione consigliata: nessuna nuova, F-041 già tracciato.
* Test/monitor consigliato: nessuno aggiuntivo.

## 11. False positive o aree risultate corrette

- **Ordini SELL "orfani" (protettivi GTC su NVDA, WMT, NOW)** senza `signal_id`/`decision_id`: verificati come stop protettivi GTC broker-side legittimi (meccanismo #62/#63), correttamente cancellati quando la posizione decisionale si è chiusa. AVGO resta `new`/resting, coerente con la posizione ancora aperta.
- **HOOD SELL exit_mechanism='unknown'**: a prima vista sembra una mislabel del bug #184, ma il testo del reason dichiara esplicitamente "the mechanism that zeroed it is not recorded, so this exit is NOT a signal expiry, see #184" — è il comportamento *corretto* post-fix (etichetta onesta invece di dedurre per età), non una ricorrenza del difetto originale.
- **SKIP_PYRAMIDING non silenzioso**: le 8 righe di oggi riportano tutte reason esplicita con score e data di ingresso della posizione che blocca.
- **Nessuna violazione long-only, nessun ordine fuori orario sui cicli regolari, nessun duplicato**: verificato su tutte le fonti disponibili (DB + API) per i 12 ordini regolari.
- **Prompt DK-CoT rispettato**: i `reason` dei BUY riportano Bull/Bear case espliciti, coerente con lo standard di prompt engineering richiesto.
- **MRK correttamente deviato a FinBERT su alta divergenza ensemble**: dimostra che il meccanismo di fallback per varianza alta *esiste e funziona* — il problema (F-037) è che non è applicato in modo consistente (WMT stessa giornata, stessa soglia superata, nessun fallback).

## 12. Dati mancanti o non accessibili

- **Log Docker dell'intera giornata 20/08**: azzerati dal redeploy del 21/08 08:20 UTC prima che questa sessione potesse leggerli (F-027, [DAY-614]). Impedisce di verificare la causa radice dell'ordine KO ([DAY-601]).
- **Bearer token API**: non funzionante come da protocollo, aggirato con `X-API-Key` (F-041, [DAY-615]).
- **Slippage reale**: non calcolabile, `trades.slippage_est` è una copia di `cost_usd` (F-015).
- **Attribuzione P&L per strategia sulle 11 posizioni legacy**: `stop_strategy` NULL (F-002, già aggiornata oggi dal cron alpha-miss).
- **Scarto di ~7,43 $ fra `nav_change_today` e la ricostruzione `market_daily.jsonl`** (§8): non abbastanza materiale da isolare come nuovo finding, ma non riconciliato in questa sessione.

## 13. Raccomandazioni immediate

- **[DAY-601] merita attenzione operativa**, non solo di ledger: un ordine ha raggiunto il broker paper senza alcuna decisione tracciata. Su un ambiente paper l'impatto è nullo, ma lo stesso percorso su un ambiente live sottometterebbe un ordine reale senza audit trail. Raccomando di verificare, appena i log tornano disponibili dopo il prossimo redeploy, se lo stesso pattern si ripete in finestre di startup dei container.
- Nessun'altra azione immediata sul money path: le restanti anomalie sono ricorrenze già tracciate nel ledger, di sola osservabilità/misura o taratura congelata dalla carta.

## 14. Test o monitor da aggiungere

- Alert su qualunque ordine sottomesso al broker con `signal_id`/`decision_id` nulli, esclusi solo gli stop protettivi GTC noti (nuovo, da [DAY-601]).
- Alert su ordini sottomessi fuori dalle finestre `portfolio_cycles` attese (nuovo, da [DAY-601]).
- Gate (non solo lettura postmortem) su `ensemble_std` all'ingresso — già raccomandato da F-037, rafforzato dall'occorrenza WMT di oggi.
- Dashboard P&L cumulato sui round-trip con `anti_whipsaw_shadow.would_suppress=True`, per quantificare il beneficio atteso di un eventuale flip del meccanismo (da [DAY-604]).
- Tutti gli altri monitor già raccomandati sulle occorrenze precedenti dei finding ricorrenti (F-003, F-004, F-007, F-011, F-012, F-014, F-015, F-019, F-021, F-023, F-027, F-041).

## 15. Ticket tecnici suggeriti

- **Nuovo (F-042, [DAY-601])**: istrumentare l'origine di ogni ordine sottomesso al broker (tag obbligatorio decisione/task all'atto della submission) e indagare — quando i log saranno disponibili — se esiste un percorso di startup/reconciliation dei container che può sottomettere ordini senza passare da `execution_decisions`.
- Tutte le altre anomalie di oggi appartengono a finding già aperti nel ledger (F-003, F-004, F-007, F-011, F-012, F-013, F-014, F-015, F-019, F-020, F-021, F-023, F-027, F-037, F-041), tutti già muniti di ticket o esplicitamente congelati dalla carta come taratura.

## 16. Stato sistema

- **Ollama Cloud**: UP al 100% per tutta la sessione osservabile da DB — 147/148 segnali generati da glm-5.2/gpt-oss (ensemble o single), 1 fallback FinBERT esplicito per alta divergenza (non per indisponibilità Ollama). Downtime Ollama: 0h (non verificabile da log per il redeploy, ma coerente con l'assenza di fallback di massa).
- **FinBERT fallback rate**: 1/148 segnali (0,7%, 1/617 execution_decisions) — unico caso della giornata, per divergenza ensemble non per outage.
- **Fallback single-model rate** (un solo LLM cloud disponibile, non FinBERT): 44/148 segnali (29,7%) — nella banda storica.
- **Worker restart events durante la sessione 20/08**: non verificabile dai log (azzerati, F-027); indirettamente, il redeploy osservato è avvenuto durante la finestra pre-market (~08:20-09:10), coincidente con l'ordine anomalo KO ([DAY-601]) — continuità DB totale durante l'orario di mercato (24/24 cicli attesi presenti, 86/86 snapshot, nessun buco).
