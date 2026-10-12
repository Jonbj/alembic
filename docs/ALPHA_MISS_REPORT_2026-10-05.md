# Alpha-miss report 2026-10-05

(prompt alpha_miss_prompt_v2, dossier schema 3.1 generato il 2026-10-12T08:00:36Z; prezzi Alpaca SIP, adjustment=all)

## 1. Decision card
1. 7 mover |ret|>=3% su 96 simboli (5 su, 2 giù); 4 già a libro all'open (held_at_open_rate 4/7). Unico mover d'ingresso catturato: SPCX +7,63% (S4, eod_net_pnl +35,14 $ sulla prima tranche).
2. Miss d'ingresso 2: BABA +4,68% (THIN_NEUTRAL, unico articolo GDELT di confronto, score 0,0) e BIDU +3,17% (NO_NEWS, zero righe news_log); active_signal_recall 1/2.
3. Le 3 uscite S4 per hold_minimum_expiry (VALE, SPCX, TSLA, 1,75 h) hanno realizzato +8,23 $ e lasciato drift_post_uscita +40,27 $: in tutti e tre i casi il segnale d'ingresso era stato sostituito da uno più debole su un altro articolo.

## 2. Stato carta
as_of economic_pnl.json: **2026-09-17** (generato 2026-09-18). Non copre le sedute dal 2026-09-18 al 2026-10-05: i numeri seguenti sono quelli dichiarati nel file, non stimati.
- Giorno 30/40 (al 2026-09-17).
- Quota NO_NEWS dominante: 13/30 giorni; soglia carta 0,6; superata: no.
- S4 economico cumulato -696,33 $ contro ±200 $: fuori banda (within=false). S1 +664,95 $ (delta vs SPY -279,03 $); BOOK -66,22 $.

## 3. Miss del giorno

| Simbolo | Return | Categoria | Campo del dossier che decide |
|---|---|---|---|
| BABA | +4,68% | (b) THIN_NEUTRAL | `candidati_miss[BABA].max_score_own` = 0,0 (< thin 0,05), news_count 1. Il dossier dà `causa` OFF_TOPIC e `funnel_v2` pipeline=WRONG_SIGN con score_firmato 0,0: uno zero non è un segno opposto, quindi in legacy è THIN_NEUTRAL |
| BIDU | +3,17% | (a) NO_NEWS | `candidati_miss[BIDU].news_count` = 0; `funnel_v2` pipeline=NO_RELEVANT_NEWS, rilevanza 0 in tutte le classi |

Conteggi: NO_NEWS 1, THIN_NEUTRAL 1, WRONG_SIGN 0, FILTERED 0, OUT_OF_STRATEGY_SCOPE 0. Nessun FILTERED: le guard_decisions su BABA sono soltanto SKIP_THRESHOLD (15:22–17:07); su BIDU non ce n'è nessuna.

Testo degli articoli (evidenza qualitativa, dati non fidati): BABA ha una sola riga, GDELT 15:15 UTC, "Alibaba vs. Uber Technologies: Which Stock Is a Better Buy in 2026?", con corpo uguale al titolo: è un pezzo di confronto, non un catalizzatore. BIDU non ha nessuna riga. JD (+2,25%, sotto soglia) ha anche lui zero righe: il rialzo delle ADR cinesi non ha nessuna notizia di gruppo nel dataset.

Mover catturati (in portafoglio o tradati, 5):

| Simbolo | Return | Stato | Esito (dal dossier) |
|---|---|---|---|
| SPCX | +7,63% | CAUGHT, 2 ingressi S4 (15:22, 18:37) | 1ª tranche uscita a 167,82 dopo 1,75 h per hold_minimum_expiry, pnl_net +4,53 $, drift_post_uscita +30,62 $; 2ª tranche aperta a fine seduta, mtm_eod +35,31 $; entry_percentile 0,62/0,63 |
| PBR | +11,50% | S1 detenuta (PASSIVE_EXPOSURE, held_rising) | passive_pnl open→close +6,34 $ (23,98→24,14): quasi tutto il movimento è nel gap. Il segnale S4 +0,4632 (14:32) viene bloccato da SKIP_PYRAMIDING alle 14:37 |
| WDC | +6,34% | S4 detenuta (PASSIVE_EXPOSURE) | ritorno_da_ingresso -19,59%; nello snapshot d'apertura qty_open è 0,0, mentre in copertura_uscita qty è 0,3347: la discrepanza interna già vista il 10-02 persiste |
| NOK | -3,77% | S1 detenuta (EXIT_RISK, STALE_EXIT_SIGNAL) | residuo 0,564 azioni, notional 5,75 $; ultimo segnale del 2026-10-01 (+0,2136) |
| MRK | -3,30% | S1 detenuta (EXIT_RISK, EXIT_WRONG_SIGN) | passive_pnl -26,37 $. Il segnale -0,1150 sull'articolo Vaxcyte (12:55, studio Fase 3 VAX-31 di un concorrente) viene sostituito dal +0,2311 sull'alzata di target JPM (16:00) |

## 4. Attività del book

<!-- alpha-miss-book:start -->
<!-- alpha-miss-book-manifest: {"schema":1,"ingressi":["VALE","SPCX","TSLA","BA","SPCX"],"chiusure":["INTC","VALE","SPCX","TSLA"]} -->

Dati deterministici dal dossier; la prosa seguente li annota e non li sostituisce.

| Tipo | Simbolo | Strategia | Ora UTC | Prezzo | Quantità | P&L netto | Motivo / qualità |
|---|---|---|---|---:|---:|---:|---|
| IN | VALE | S4 | 14:22 | $14.0600 | 111.0868 | — | percentile 17.28%; denominatore intraday valido |
| IN | SPCX | S4 | 15:22 | $167.1568 | 9.3525 | — | percentile 61.64%; denominatore intraday valido |
| IN | TSLA | S4 | 16:22 | $377.6300 | 4.1352 | — | percentile 76.26%; denominatore intraday valido |
| IN | BA | S4 | 18:07 | $192.9000 | 8.0642 | — | percentile 40.10%; denominatore intraday valido |
| IN | SPCX | S4 | 18:37 | $167.2851 | 9.2812 | — | percentile 62.56%; denominatore intraday valido |
| OUT | INTC | S4 | — | $117.2500 | 14.5237 | +$230.00 | sentiment_reversal |
| OUT | VALE | S4 | — | $14.0400 | 111.0868 | −$3.10 | hold_minimum_expiry |
| OUT | SPCX | S4 | — | $167.8165 | 9.3525 | +$4.53 | hold_minimum_expiry |
| OUT | TSLA | S4 | — | $379.3500 | 4.1352 | +$6.80 | hold_minimum_expiry |
<!-- alpha-miss-book:end -->
5 ingressi S4 (VALE, SPCX ×2, TSLA, BA) e 4 chiusure S4. La chiusura rilevante è INTC: sentiment_reversal dopo 455,5 h, pnl_net +230,00 $, drift_post_uscita -15,40 $ (cioè un'uscita prima di un ulteriore calo). Le altre tre chiusure (VALE -3,10 $, SPCX +4,53 $, TSLA +6,80 $) sono uscite per hold_minimum_expiry a 1,75 h dall'ingresso. VALE è entrata a mercato già esteso: quota_nel_gap 2,46, vs_apertura -63,32 $. I tre BUY hanno signal_id, mentre 3 dei 4 SELL ne sono privi: `decision_signal_id_coverage` segnala `regressions: ["SELL"]`.

## 5. Cecita' lato uscita
2 posizioni con `cieco_lato_uscita: true` su 40 (n_indeterminati 0, quindi nessun null):

| Ticker | Strategia | ritorno_da_ingresso | ritorno_seduta | sedute_consecutive_senza_righe | fonti_osservate_finestra |
|---|---|---|---|---|---|
| AMAT | S1 | -8,68% | +0,41% | 2 | alpaca_benzinga, gdelt_gkg |
| NOK | S1 | -12,97% | -3,77% | 2 | alpaca_benzinga, gdelt_gkg |

Notional cieco 470,53 $. Entrambe sono ancora aperte e nessuna è uscita nella seduta: ritorno_da_ingresso è misurato al close. AMAT oggi è salita; la sua perdita è tutta accumulata prima. Le perdite marcate non cieche sono C -3,36%, PFE -4,46% e WDC -19,59%, tutte con righe news nella seduta.

## 6. Backstop NO_NEWS
I mover NO_NEWS nella popolazione zero_news sono BIDU (+3,17%) e NOK (-3,77%, detenuta). `observed_catalysts` è vuoto per entrambi e il calendario è NOT_OBSERVED: nessun marker CALENDAR (calendar mover_observed 0/2, non-mover 0/27; fonti FMP earnings-calendar e Alpaca Corporate Actions entrambe riuscite).
Volume EOD (POST_HOC_EOD, valid_for_signal_evaluation=false): surprise mediana -0,293 sui 2 mover contro -0,168 sui 27 non-mover. È una misura sull'intera seduta, quindi non era disponibile prima del movimento e non se ne ricava né una soglia né un tasso di falsi positivi (la valutazione ex-ante è in #451).
Popolazione zero_news: 29 (2 mover, 27 non-mover).

Copertura raw di `news_log` per settore (diversa dalla copertura effective-timely di `copertura_articoli.per_settore`):

| Settore | ticker_with_news/universe | raw_news_coverage_rate | mover zero-news | calendario osservato zero-news |
|---|---|---|---|---|
| consumer | 7/11 | 63,6% | 0 | 0 |
| energy | 5/6 | 83,3% | 0 | 0 |
| etf_broad | 4/4 | 100,0% | 0 | 0 |
| financials | 12/14 | 85,7% | 0 | 0 |
| healthcare | 9/9 | 100,0% | 0 | 0 |
| industrials | 2/4 | 50,0% | 0 | 0 |
| materials | 1/2 | 50,0% | 0 | 0 |
| media | 4/5 | 80,0% | 0 | 0 |
| semis | 10/15 | 66,7% | 0 | 0 |
| tech | 12/21 | 57,1% | 1 | 0 |
| telecom | 1/5 | 20,0% | 1 | 0 |

Per confronto, la copertura effective-timely (`copertura_articoli.per_settore`) è 46/96 complessiva; telecom 0/5, tech 7/21.

### Attribuzione fonti per ticker (#511)
29 ticker con `articoli_unici == 0` e `fonti_osservate` vuoto. Per tutti `blind_set.per_ticker` riporta articoli_unici_giorno 0 ed effective_timely_articles_giorno 0, cioè nessuna resa da alcuna fonte (non è il caso "fonte presente ma non utile"): AMAT, ASML, BIDU, DB, DELL, ERIC, F, GE, GM, HD, IBM, INFY, JD, MMM, MRVL, NOK, NOW, PANW, PG, RIO, ROKU, SAP, SHEL, SNOW, SONY, T, TXN, UBS, VZ.
Con `fonti_osservate` non vuoto ma effective-timely a zero si trovano per esempio AAPL: alpaca_benzinga ha reso 3 righe, nessuna effective-timely (TAG_UNCONFIRMED). In `blind_set.ticker_allerta_zero_articoli` (soglia 5 sedute) ci sono BIDU, ERIC, MMM, RIO, ROKU, SHEL, TXN.

## 7. Pattern osservato
Due temi distinti, entrambi di natura geografica e macro più che di singolo emittente:
- **Brasile**: rally dopo il primo turno elettorale (EWZ +13–14% secondo gli articoli benzinga). Ne fanno parte PBR +11,50% e VALE +2,83% (sotto soglia, ma tradata).
- **ADR cinesi**: BABA +4,68%, BIDU +3,17%, JD +2,25%, senza notizie di gruppo nel dataset.

SPCX +7,63% si muove su note di analisti (Morgan Stanley, Bernstein). Il lato debole è isolato: NOK, e MRK su notizia di un concorrente (Vaxcyte). Il tema Brasile non compare nei report del 10-01 e del 10-02; le ADR cinesi il 10-02 erano in calo (BABA -1,49%, BIDU -1,48%). Nessun pattern ricorrente verificabile oltre il singolo giorno.

## 8. Segnalazioni
Denominatori: longitudinal_panels.json non esiste; i conteggi vengono dalle occorrenze di findings.json (occorrenze registrate, non giorni distinti verificati).

* **[F-023]** In tutti e tre gli ingressi S4 chiusi nella seduta, il segnale che ha generato il BUY è stato sostituito entro 13–30 minuti da un segnale più debole su un articolo diverso. Il ciclo successivo ha quindi voluto vendere ed è uscito alla scadenza dell'hold minimum (90 min). Occorrenze registrate prima di oggi: 27.
  - esposizione: 5 ingressi S4; 3 chiusi in giornata, tutti e 3 esposti. VALE 0,49 (13913) → 0,2383 (13937, pezzo macro "Brazilian Stocks Rally", 14:35). SPCX 0,372 (13973) → 0,12 fallback (13979, articolo TSMC/Intel, 15:22). TSLA 0,3712 (13997) → 0,0046 (14028, pezzo "Brazil's Election", 16:45). Dalle guard_decisions, i cicli successivi leggono proprio 13937 e 14028 (SKIP_THRESHOLD). Il worker log mostra "Hold minimum (90 min): skipped 1 SELL" su VALE dalle 14:37 e su SPCX alle 15:37.
  - evidenza contraria: se il finding fosse falso, i SELL corrisponderebbero a un segnale ribassista o a un taglio di rank su un candidato più forte. Invece i 3 SELL non hanno signal_id e i segnali sostitutivi sono positivi ma sotto il gate, non di inversione.
  - non-occorrenza: l'uscita INTC è un vero reversal (-0,375, signal 13917) con drift_post_uscita -15,40 $, cioè un'uscita corretta. La seconda tranche SPCX (18:37) e BA (18:07) sono rimaste aperte a fine seduta.
  - next evidence: join read-only, sulle sedute archiviate, fra SELL hold_minimum_expiry e il signal_id letto nel primo ciclo dopo il BUY, per contare quanti SELL seguono una sostituzione con un segnale sotto gate e confrontarne il drift_post_uscita.
  - meccanismo e fonte: §4. `chiusure[].exit_reason`/`drift_post_uscita`, `aggregati.ore_tenuta_s4` (bucket 105 min: n 3, pnl_net +8,23, drift +40,27), `guard_decisions[].signal_id`. Coinvolge anche il fan-out (F-012): il pezzo sul Brasile è taggato TSLA.
  - costo: somma di drift_post_uscita = 12,22 + 30,62 − 2,56 = 40,27 $ (dossier, qty × (close − exit)). Congetturale.
  - alternative scartate: rank-out per capienza top-N. Non regge, perché le guard_decisions per VALE e TSLA dopo l'ingresso sono SKIP_THRESHOLD sul nuovo signal_id, cioè sotto gate, e non RANKED_OUT.
* **[F-031]** PBR +11,50%: il segnale S4 +0,4632 (signal 13935, sopra il gate e col segno giusto) viene bloccato da SKIP_PYRAMIDING alle 14:37 perché il simbolo è detenuto da S1. Occorrenze registrate: 31.
  - esposizione: 5 SKIP_PYRAMIDING nella seduta (LLY, PBR, TSM, XLK, ABBV); l'unico su un mover è PBR.
  - evidenza contraria: se il finding fosse falso, ci sarebbe un BUY S4 su PBR o un blocco di altro tipo. Il dossier riporta 1 SKIP_PYRAMIDING e 13 SKIP_THRESHOLD su PBR, nessun BUY.
  - non-occorrenza: VALE, che è sullo stesso tema ma non è detenuta da S1, è stata comprata alle 14:22.
  - next evidence: rendimento dal tick dello SKIP_PYRAMIDING al close sui 31 casi archiviati (counterfactual_return_1h è nelle guard_decisions).
  - meccanismo e fonte: §3, `guard_decisions[PBR]` decision SKIP_PYRAMIDING signal_id 13935; `snapshot_apertura[PBR]` open 23,98, close 24,14.
  - costo: limite superiore 2200 × (24,14 − 23,98)/23,98 = 14,68 $ (dall'open; l'ingresso effettivo sarebbe stato alle 14:37, quindi il costo reale è ≤). Congetturale. Il +11,50% close-to-close era quasi tutto nel gap e non era accessibile.
  - alternative scartate: "il movimento era comunque inaccessibile". Vale per il gap, ma non spiega il blocco: la regola si è attivata per la detenzione S1, non per il prezzo.
* **[F-001]** 29/96 simboli a zero righe news_log; BIDU è un mover NO_NEWS ed è in allerta zero-articoli da ≥5 sedute. Occorrenze registrate: 43.
  - esposizione: 96 simboli; 29 a zero news (era 68/96 il 10-02); effective-timely 46/96; telecom raw 1/5.
  - evidenza contraria: se il finding fosse falso, BIDU avrebbe righe con una rilevanza qualsiasi. Invece `funnel_v2` rilevanza è 0 su tutte le classi e `fonti_osservate` è vuoto.
  - non-occorrenza: healthcare 9/9 ed etf_broad 4/4 in raw; BABA, nello stesso tema, ha almeno una riga GDELT.
  - next evidence: serie read-only di `blind_set.per_ticker` per BIDU/JD/ERIC/MMM/RIO/ROKU/SHEL/TXN sulle sedute archiviate, per distinguere un ticker strutturalmente non servito dai provider da un'assenza episodica.
  - meccanismo e fonte: §6, `no_news_backstop.per_sector`, `copertura_articoli.blind_set.ticker_allerta_zero_articoli`.
  - costo: 2200 × 0,031665 = 69,66 $ (congetturale, legacy; dossier accessible 14,00 $, net 11,67 $).
  - alternative scartate: "nessuna notizia esisteva". Non è verificabile, e il co-movimento con BABA e JD suggerisce un driver di gruppo che nessuna fonte ha reso.

## 9. Appendice
### (a) Rendimenti watchlist (`mercato.rendimenti`)

| # | Simbolo | Return |
|---|---|---|
| 1 | PBR | +11.50% |
| 2 | SPCX | +7.63% |
| 3 | WDC | +6.34% |
| 4 | BABA | +4.68% |
| 5 | BIDU | +3.17% |
| 6 | VALE | +2.83% |
| 7 | TSM | +2.75% |
| 8 | V | +2.51% |
| 9 | GM | +2.50% |
| 10 | JD | +2.25% |
| 11 | MA | +2.23% |
| 12 | TSLA | +2.20% |
| 13 | NVDA | +2.12% |
| 14 | AVGO | +2.08% |
| 15 | META | +1.90% |
| 16 | UNH | +1.80% |
| 17 | RDDT | +1.73% |
| 18 | RIO | +1.53% |
| 19 | MSFT | +1.48% |
| 20 | TM | +1.45% |
| 21 | DIS | +1.39% |
| 22 | NOW | +1.27% |
| 23 | WFC | +1.23% |
| 24 | HOOD | +1.22% |
| 25 | ABBV | +1.12% |
| 26 | XLE | +1.00% |
| 27 | UBS | +0.99% |
| 28 | QQQ | +0.88% |
| 29 | PANW | +0.87% |
| 30 | GOOGL | +0.86% |
| 31 | MMM | +0.80% |
| 32 | WMT | +0.78% |
| 33 | XLF | +0.73% |
| 34 | XLV | +0.72% |
| 35 | PG | +0.71% |
| 36 | SPY | +0.67% |
| 37 | ROKU | +0.67% |
| 38 | IWM | +0.66% |
| 39 | NFLX | +0.66% |
| 40 | TMUS | +0.61% |
| 41 | NVO | +0.59% |
| 42 | XLK | +0.56% |
| 43 | CSCO | +0.55% |
| 44 | MCD | +0.50% |
| 45 | BAC | +0.47% |
| 46 | ADBE | +0.46% |
| 47 | AMAT | +0.41% |
| 48 | F | +0.41% |
| 49 | AXP | +0.41% |
| 50 | TXN | +0.37% |
| 51 | PLTR | +0.34% |
| 52 | CAT | +0.32% |
| 53 | BRK.B | +0.32% |
| 54 | COST | +0.31% |
| 55 | SHEL | +0.30% |
| 56 | NKE | +0.27% |
| 57 | ORCL | +0.12% |
| 58 | SOXX | +0.10% |
| 59 | C | +0.04% |
| 60 | LLY | +0.02% |
| 61 | JPM | +0.00% |
| 62 | CMCSA | +0.00% |
| 63 | DB | +0.00% |
| 64 | XOM | -0.01% |
| 65 | AMZN | -0.05% |
| 66 | MS | -0.06% |
| 67 | CVX | -0.11% |
| 68 | VZ | -0.15% |
| 69 | AZN | -0.24% |
| 70 | AAPL | -0.24% |
| 71 | T | -0.25% |
| 72 | SBUX | -0.30% |
| 73 | AMD | -0.34% |
| 74 | BP | -0.38% |
| 75 | MRVL | -0.38% |
| 76 | SAP | -0.40% |
| 77 | ASML | -0.40% |
| 78 | BA | -0.43% |
| 79 | IBM | -0.48% |
| 80 | HD | -0.60% |
| 81 | SNOW | -0.60% |
| 82 | ERIC | -0.75% |
| 83 | GE | -0.89% |
| 84 | GS | -1.01% |
| 85 | MU | -1.02% |
| 86 | SONY | -1.18% |
| 87 | JNJ | -1.21% |
| 88 | PFE | -1.40% |
| 89 | ARM | -1.49% |
| 90 | DELL | -1.82% |
| 91 | CRM | -2.09% |
| 92 | QCOM | -2.21% |
| 93 | INFY | -2.54% |
| 94 | INTC | -2.63% |
| 95 | MRK | -3.30% |
| 96 | NOK | -3.77% |

### (b) Altri finding toccati
- [F-009] not_exposed: nessun mover d'ingresso con segnale a segno corretto sotto il gate (BABA 0,0, BIDU senza segnale).
- [F-030] supported: VALE quota_nel_gap 2,46 e vs_apertura -63,32 $; ingresso dopo il gap brasiliano.
- [F-011] supported: `decision_signal_id_coverage` regressions ["SELL"], 3/4 SELL senza signal_id.
- [F-012] supported: il pezzo sul Brasile è taggato TSLA (signal 14028) e governa la decisione su TSLA; mapping_fanout_extra 118 su 243 righe.
- [F-013] supported: SPCX BUY 15:22 → SELL 17:07 → BUY 18:37 nella stessa seduta.
- [F-036] supported: WDC ritorno_da_ingresso -19,59% (oltre -15%); nessun alert verificato oggi (mobile_events non interrogata).
- [F-075] supported: held_at_open conta NOK (notional residuo 5,75 $, ~0,3% di uno slot da 2.200 $) come mover detenuto.
- [F-059] supported: MRK EXIT_WRONG_SIGN; il segnale negativo -0,115 non produce uscita.
- [F-063] contradicted: calendario earnings OBSERVED (FMP riuscito, streak unknown 0).

### (c) Casi di successo
- INTC (S4): chiusa per sentiment_reversal, pnl_net +230,00 $; il titolo a fine seduta era -2,63% e drift_post_uscita -15,40 $ (uscita prima di un ulteriore calo).
- SPCX (S4): mover +7,63% catturato; eod_net_pnl +35,14 $ sulla prima tranche (mark fill→close), realizzato +4,53 $; seconda tranche mtm_eod +35,31 $.
- TSLA (S4): pnl_net +6,80 $ (non mover, +2,20%).
