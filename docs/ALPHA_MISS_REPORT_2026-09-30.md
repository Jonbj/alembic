# ALPHA MISS REPORT 2026-09-30

Contratto alpha_miss_prompt_v2 · dossier schema_version 3.1 · generato_il dossier 2026-10-07T08:00Z · prezzi Alpaca SIP adjustment=all · soglia_mover 0,03.

## 1. Decision card
1. 4 mover ≥3% (soglia_mover 0,03): up 2 (INTC +3,71%, NOW +3,13%), down 2 (GM −4,31%, HOOD −3,20%); dispersione σ 1,41%; SPY −0,21%, QQQ +0,25%.
2. Dei 4 mover: 2 già detenuti all'open (GM EXIT_RISK, INTC PASSIVE_EXPOSURE), 1 non azionabile long-only (HOOD), 1 miss BELOW_GATE (NOW +3,13%, score +0,199 sotto gate 0,30; active_signal_recall 0/1).
3. Book: 4 chiusure S4, net_pnl realizzato −21,84 $ (SPCX +19,69; HOOD −15,80; BA −18,95; NVO −6,78); 3 ingressi S4 del giorno tutti con mtm_eod negativo (−90,79 $ totale); 33 simboli a zero news.

## 2. Stato carta
- as_of economic_pnl.json: **2026-09-17** (generato 2026-09-18); il file non include il 09-30. A quella data: giorno **30/40**.
- Quota NO_NEWS dominante: 13/30 giorni (43,3%) contro soglia carta 0,60: soglia non superata (as_of 09-17).
- S4 economico cumulato: **−696,33 $** vs ±200 $: fuori banda (`within: false`, as_of 09-17).
- Nota: la scadenza attesa della carta (2026-09-28) è già passata; il 09-30 è il 42° giorno di borsa dal 2026-08-03 (conteggio mio dal calendario, Labor Day escluso, non dal file). Stato aggiornato al 09-30: DATA_INCOMPLETE.

## 3. Miss del giorno
| Simbolo | Return | Categoria | Campo del dossier che decide |
|---|---|---|---|
| NOW | +3,13% | (b) THIN_NEUTRAL (v2: BELOW_GATE) | `candidati_miss[0].causa = BELOW_GATE`; `max_score_own` +0,199 < `soglia_gate_usata` 0,30; segno corretto; `funnel_v2.pipeline = BELOW_GATE` |

Dettaglio NOW: un solo articolo, alpaca_benzinga 16:11Z, «ServiceNow Stock Rises Wednesday: What&#39;s Happening?» (ISSUER_SPECIFIC, CONCURRENT). Il testo dice che il titolo sale «joining a broader relief bid across the software sector»: catalizzatore di settore, non idiosincratico. Opportunità v2: entry 134,795 (open della prima barra eleggibile, 16:25Z), exit close 134,01, `accessible_opportunity_usd` −12,81, `net_opportunity_usd` −14,04; legacy `costo_usd` 68,91. Residuo vs XLK +2,49%.

Mover non-miss:
| Simbolo | Return | Stato | Campo |
|---|---|---|---|
| INTC | +3,71% | (f) CAUGHT (detenuto, PASSIVE_EXPOSURE) | `funnel_v2.righe` held_rising; `copertura_uscita` S4 ritorno_da_ingresso +18,62%, notional 1.746 $ |
| GM | −4,31% | detenuto S1, EXIT_RISK, `pipeline_uscita = STALE_EXIT_SIGNAL` | `funnel_v2.righe`: segnale 13077 del 2026-09-28, score_firmato −0,279; zero righe news in giornata |
| HOOD | −3,20% | NON_ACTIONABLE (long-only), ma S4 ha comprato alle 14:07 | `ingressi`, `funnel_v2.righe` |

Titoli tradati oggi (`ingressi`/`chiusure`):
| Simbolo | Ingresso | mtm_eod | Chiusura | pnl_net | drift_post_uscita |
|---|---|---|---|---|---|
| HOOD | S4 14:07 @115,45, entry_percentile 0,30, quota prima del segnale 0,708 | −38,40 | hold_minimum_expiry @114,30 dopo 1,75 h | −15,80 | −23,43 (uscire ha risparmiato) |
| BA | S4 14:22 @189,65, percentile 0,57, quota prima 0,40 | −28,49 | hold_minimum_expiry @187,36 dopo 1,75 h | −18,95 | −10,37 (uscire ha risparmiato) |
| NVO | S4 14:37 @38,52, percentile 0,72, denominatore_degenere true | −23,91 | portfolio_sell @38,37 dopo 2,25 h | −6,78 | −17,96 (uscire ha risparmiato) |
| SPCX | ingresso precedente (non nel blocco `ingressi`) | DATA_INCOMPLETE | portfolio_sell @151,35 dopo 23,0 h | +19,69 | −4,78 (uscire ha risparmiato) |

Giudizio breve: HOOD entrato su articoli delle 12:56–13:45Z («jumps 5%») alle 14:07Z; HOOD e BA chiusi a hold minimo; in tutti e quattro i casi il titolo è sceso dopo l'uscita.

## 4. Attività del book

<!-- alpha-miss-book:start -->
<!-- alpha-miss-book-manifest: {"schema":1,"ingressi":["HOOD","BA","NVO"],"chiusure":["SPCX","HOOD","BA","NVO"]} -->

Dati deterministici dal dossier; la prosa seguente li annota e non li sostituisce.

| Tipo | Simbolo | Strategia | Ora UTC | Prezzo | Quantità | P&L netto | Motivo / qualità |
|---|---|---|---|---:|---:|---:|---|
| IN | HOOD | S4 | 14:07 | $115.4500 | 13.0165 | — | percentile 30.33%; denominatore intraday valido |
| IN | BA | S4 | 14:22 | $189.6500 | 7.9136 | — | percentile 56.85%; denominatore intraday valido |
| IN | NVO | S4 | 14:37 | $38.5223 | 39.0405 | — | percentile 72.01%; denominatore intraday degenere: quota non interpretabile |
| OUT | SPCX | S4 | — | $151.3500 | 9.7544 | +$19.69 | portfolio_sell |
| OUT | HOOD | S4 | — | $114.3000 | 13.0165 | −$15.80 | hold_minimum_expiry |
| OUT | BA | S4 | — | $187.3600 | 7.9136 | −$18.95 | hold_minimum_expiry |
| OUT | NVO | S4 | — | $38.3700 | 39.0405 | −$6.78 | portfolio_sell |
<!-- alpha-miss-book:end -->
3 ingressi S4 (HOOD, BA, NVO, 14:07–14:37Z) e 4 chiusure S4 (SPCX, HOOD, BA, NVO); nessuna chiusura S1. Tutti e tre gli ingressi hanno chiuso la seduta sotto il fill (mtm_eod negativo); le due uscite `hold_minimum_expiry` sono arrivate dopo 1,75 h. L'unico trade positivo (SPCX +19,69) è una posizione tenuta 23 h. Il cron sostituisce questa sezione col blocco riconciliato.

## 5. Cecità lato uscita
Nessuna: `n_cieche_lato_uscita = 0`, `n_indeterminati = 0` (nessun `cieco_lato_uscita: null`). 44 posizioni, 14 con copertura nulla, 12 con perdita marcata, nessuna in entrambe le condizioni. Nota GM (S1, zero righe da 2 sedute, fonte osservata alpaca_benzinga): `ritorno_da_ingresso` −0,67% (perdita non marcata, soglia −3%), `ritorno_seduta` −4,31%: le due misure non vanno confuse.

## 6. Backstop NO_NEWS
- Mover NO_NEWS: 1 (GM −4,31%). `observed_catalysts` = [] (calendario NOT_OBSERVED; fonti FMP earnings-calendar e Alpaca Corporate Actions riuscite). Marker CALENDAR sui mover: 0/1; sui non-mover zero-news: 1/32 (3,1%).
- Volume EOD (**POST_HOC_EOD**, non è un segnale point-in-time, `valid_for_signal_evaluation: false`): GM adv_ratio 1,334; mediana surprise mover +0,334 (n=1), non-mover −0,058 (n=32). Solo descrittivo; la valutazione ex-ante è in #451.
- Copertura raw `news_log` per settore (distinta dalla effective-timely):

| Settore | ticker_with_news/universe | raw_news_coverage_rate | zero-news | mover zero-news | CALENDAR su zero-news |
|---|---|---|---|---|---|
| consumer | 7/11 | 63.6% | 4 | 1 | 0 |
| energy | 4/6 | 66.7% | 2 | 0 | 0 |
| etf_broad | 4/4 | 100.0% | 0 | 0 | 0 |
| financials | 9/14 | 64.3% | 5 | 0 | 0 |
| healthcare | 7/9 | 77.8% | 2 | 0 | 0 |
| industrials | 3/4 | 75.0% | 1 | 0 | 0 |
| materials | 1/2 | 50.0% | 1 | 0 | 0 |
| media | 2/5 | 40.0% | 3 | 0 | 0 |
| semis | 8/15 | 53.3% | 7 | 0 | 1 |
| tech | 15/21 | 71.4% | 6 | 0 | 0 |
| telecom | 3/5 | 60.0% | 2 | 0 | 0 |

## 7. Pattern osservato
Non chiaro (solo 4 mover). Lettura debole: software/tech in rialzo (NOW, INTC; ADBE +2,90%, SNOW +2,80%, PANW +2,29% sotto soglia; XLK +0,64%) contro financials/healthcare/consumer in calo (XLF −1,13%, XLV −1,35%; GM, MS −2,43%, WMT −2,70%). L'articolo NOW parla di «relief bid across the software sector». Nessuna ricorrenza dichiarabile sul solo singolo giorno.

## 8. Segnalazioni

* **[F-009]** Gate S4 0,30 scarta un segno corretto su un mover: NOW +3,13% con score +0,199.
  * esposizione: 1 mover ENTRY_OPPORTUNITY con notizia tempestiva oggi (active_signal_recall 0/1). Ledger: 23 giorni distinti su 42 sedute (da findings.json; longitudinal_panels.json non esiste).
  * evidenza contraria: la v2 dà `net_opportunity_usd` −14,04 (entry 134,795 vs close 134,01): comprare al primo ciclo eleggibile non avrebbe pagato; il movimento era già in gran parte avvenuto (articolo 16:11Z, «Rises Wednesday»).
  * non-occorrenza: nessun altro mover sotto gate oggi (INTC e GM già detenuti, HOOD non azionabile).
  * next evidence: aggregare `net_opportunity_usd` v2 sulle occorrenze F-009 (sola lettura) per separare costo lordo da costo accessibile.
  * meccanismo e fonte: §3, `candidati_miss[0]` (`max_score_own` 0,199 < `soglia_gate_usata` 0,30, segno +) e `funnel_v2.righe`.
  * costo (serie legacy): |return| × size = 0,031322 × 2.200 = 68,91 $ (congetturale); v2: accessibile −12,81 $, netto −14,04 $.

* **[F-030]** La notizia arriva a movimento già avvenuto: HOOD e BA acquistati con il movimento in gran parte fatto.
  * esposizione: 3 ingressi S4 oggi (HOOD, BA, NVO). Ledger: 23 giorni distinti, 26 occorrenze.
  * evidenza contraria: quota del movimento precedente al segnale bassa o negativa; oggi HOOD 0,708 e BA 0,40, quindi non prossime a 1.
  * non-occorrenza: NVO ha `denominatore_degenere` true, quota non interpretabile; nessun ingresso con quota ≥1.
  * next evidence: stesso conteggio su `ingressi` per `quota_nel_gap` (oggi HOOD −1,72, BA −2,68) sulle sedute del ledger, sola lettura.
  * meccanismo e fonte: `ingressi.quota_movimento_precedente_al_segnale`; articoli HOOD 12:56–13:45Z (news_log) contro ingresso 14:07Z.
  * costo: net_pnl realizzati dei trade 1038 e 1039 = 15,80 + 18,95 = 34,75 $ (NVO escluso). Alternativa scartata: usare mtm_eod (−38,40, −28,49), perché l'uscita è avvenuta prima del close e drift_post_uscita (−23,43; −10,37) mostra che tenere avrebbe perso di più.

* **[F-011]** execution_decisions.signal_id NULL sulle SELL: regressione di copertura.
  * esposizione: 4 SELL oggi, tutte senza signal_id (`by_reason_code.SELL` 0/4, `regressions = ['SELL']`). Ledger: 32 giorni distinti.
  * evidenza contraria: signal_id pieno sulle SELL; oggi 0/4, quindi il finding regge.
  * non-occorrenza: BUY 3/3, SKIP_THRESHOLD 737/737; totale 784/788 (99,49%).
  * next evidence: lettura di `execution_decisions` per le 4 SELL (id e motivazione), sola lettura.
  * meccanismo e fonte: `decision_signal_id_coverage` del dossier.
  * costo: non stimabile (catena segnale→decisione→trade non ricostruibile), null.

## 9. Appendice

### (a) Rendimenti watchlist (`mercato.rendimenti`, alto → basso)
| Simbolo | Return |
|---|---|
| INTC | +3.71% |
| NOW | +3.13% |
| ADBE | +2.90% |
| SNOW | +2.80% |
| PANW | +2.29% |
| CRM | +1.89% |
| JD | +1.14% |
| INFY | +1.13% |
| AAPL | +1.10% |
| SPCX | +1.09% |
| BP | +1.08% |
| PBR | +1.07% |
| AMZN | +1.01% |
| GOOGL | +0.93% |
| XOM | +0.87% |
| VALE | +0.83% |
| MSFT | +0.77% |
| CMCSA | +0.75% |
| AMD | +0.69% |
| SONY | +0.68% |
| XLK | +0.64% |
| CSCO | +0.64% |
| TSLA | +0.56% |
| NVDA | +0.51% |
| MRVL | +0.36% |
| QQQ | +0.25% |
| WDC | +0.22% |
| SOXX | +0.21% |
| BIDU | +0.18% |
| ROKU | +0.09% |
| TMUS | +0.06% |
| PLTR | +0.04% |
| RIO | +0.01% |
| MU | +0.00% |
| IBM | -0.03% |
| QCOM | -0.03% |
| XLE | -0.06% |
| CVX | -0.08% |
| SHEL | -0.09% |
| AMAT | -0.12% |
| TSM | -0.16% |
| BABA | -0.19% |
| SPY | -0.21% |
| VZ | -0.24% |
| DELL | -0.30% |
| T | -0.33% |
| ORCL | -0.36% |
| IWM | -0.40% |
| AXP | -0.43% |
| DIS | -0.48% |
| WFC | -0.53% |
| TXN | -0.57% |
| DB | -0.61% |
| ABBV | -0.65% |
| PFE | -0.70% |
| BA | -0.87% |
| BRK.B | -0.88% |
| BAC | -0.96% |
| C | -1.01% |
| NFLX | -1.02% |
| NVO | -1.04% |
| JNJ | -1.06% |
| AVGO | -1.10% |
| SAP | -1.12% |
| XLF | -1.13% |
| NKE | -1.23% |
| HD | -1.23% |
| ASML | -1.24% |
| JPM | -1.24% |
| MCD | -1.30% |
| UBS | -1.33% |
| XLV | -1.35% |
| ARM | -1.37% |
| SBUX | -1.54% |
| COST | -1.54% |
| AZN | -1.67% |
| GS | -1.73% |
| GE | -1.76% |
| V | -1.79% |
| ERIC | -1.82% |
| META | -1.84% |
| CAT | -1.92% |
| TM | -1.93% |
| F | -1.95% |
| RDDT | -2.01% |
| PG | -2.05% |
| UNH | -2.10% |
| NOK | -2.12% |
| MA | -2.15% |
| LLY | -2.33% |
| MS | -2.43% |
| MMM | -2.58% |
| MRK | -2.66% |
| WMT | -2.70% |
| HOOD | -3.20% |
| GM | -4.31% |

### (b) Altri finding toccati
* [F-001] supported — 33/96 simboli a zero news_log; effective-timely 46/96 coperti (47,9%).
* [F-012] supported — `mapping_fanout_extra` 85, TAG_UNCONFIRMED 104 su 208 righe (50,0%).
* [F-076] supported — entità HTML (`&#39;`) nel titolo di NOW, BA, INTC, NVO.
* [F-075] contradicted — held_at_open_rate 2/4 con INTC 1.746 $ e GM 780 $ di nozionale, nessuno sotto il 6% di uno slot.
* [F-013] not_exposed — le chiusure sono `hold_minimum_expiry` ×2 e `portfolio_sell` ×2, nessuna `below_entry_gate`.

### (c) Casi di successo
Nessun mover catturato con P&L positivo. Unica chiusura positiva: SPCX +19,69 $ (non mover, +1,09%).

### Attribuzione fonti per ticker (FASE 5)
33 ticker con `articoli_unici == 0`; `fonti_osservate` vuoto per tutti: zero resa dei provider su quel ticker, non fonte non configurata. Nessuna riga con fonte presente ma non effective-timely.

| Ticker | articoli_unici_giorno | effective_timely_articles_giorno | fonti_osservate |
|---|---|---|---|
| ARM | 0 | 0 | vuoto |
| ASML | 0 | 0 | vuoto |
| AVGO | 0 | 0 | vuoto |
| BAC | 0 | 0 | vuoto |
| BIDU | 0 | 0 | vuoto |
| BP | 0 | 0 | vuoto |
| C | 0 | 0 | vuoto |
| COST | 0 | 0 | vuoto |
| CSCO | 0 | 0 | vuoto |
| DB | 0 | 0 | vuoto |
| ERIC | 0 | 0 | vuoto |
| GM | 0 | 0 | vuoto |
| IBM | 0 | 0 | vuoto |
| INFY | 0 | 0 | vuoto |
| JD | 0 | 0 | vuoto |
| JNJ | 0 | 0 | vuoto |
| JPM | 0 | 0 | vuoto |
| MMM | 0 | 0 | vuoto |
| MRVL | 0 | 0 | vuoto |
| NFLX | 0 | 0 | vuoto |
| QCOM | 0 | 0 | vuoto |
| RDDT | 0 | 0 | vuoto |
| RIO | 0 | 0 | vuoto |
| ROKU | 0 | 0 | vuoto |
| SAP | 0 | 0 | vuoto |
| SBUX | 0 | 0 | vuoto |
| SHEL | 0 | 0 | vuoto |
| TMUS | 0 | 0 | vuoto |
| TXN | 0 | 0 | vuoto |
| UNH | 0 | 0 | vuoto |
| WDC | 0 | 0 | vuoto |
| WFC | 0 | 0 | vuoto |
| WMT | 0 | 0 | vuoto |
