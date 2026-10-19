# Alpha-miss report 2026-10-07

(prompt alpha_miss_prompt_v2, dossier schema 3.1 generato il 2026-10-19T08:00:34Z; prezzi Alpaca SIP, adjustment=all)

## 1. Decision card
1. 6 mover |ret|>=3% su 96 simboli (1 su, 5 giù); 4 erano già a libro all'open (held_at_open_rate 4/6). I due miss, DB −4,50% e VALE −3,34%, sono NO_NEWS (0 righe in news_log) e non tradabili long-only (accessible_opportunity_usd 0).
2. Unico ingresso: HOOD (S4, 15:37, entry_percentile 0,17), chiuso dopo 2,5 h a +18,25 $ (portfolio_sell); le 3 chiusure del giorno sommano −9,29 $ (SPCX −40,59 sentiment_reversal, NOW +13,06, HOOD +18,25).
3. CAT −5,75% (mover detenuto, −5,75% di seduta) resta EXIT_BELOW_THRESHOLD (score_firmato −0,025): nessuna uscita; exit_signal_recall 1/3.

## 2. Stato carta
as_of economic_pnl.json: **2026-09-17** (generato 2026-09-18). Il file non copre le sedute dal 2026-09-18 al 2026-10-06 né quella di oggi: i numeri sono quelli dichiarati nel file, non stime.
- Giorno 30/40 (al 2026-09-17).
- Quota NO_NEWS dominante: 13/30 giorni; soglia carta 0,6; superata: no.
- S4 economico cumulato −696,33 $ contro ±200 $: fuori banda. S1 +664,95 $; BOOK −66,22 $.

## 3. Miss del giorno

| Simbolo | Return | Categoria | Campo del dossier che decide |
|---|---|---|---|
| DB | −4,50% | NO_NEWS (non tradabile long-only) | `candidati_miss[DB].causa` = NO_NEWS, `news_count` 0; `funnel_v2.righe[DB].pipeline_escluso_motivo` = non_actionable_long_only |
| VALE | −3,34% | NO_NEWS (non tradabile long-only) | `candidati_miss[VALE].causa` = NO_NEWS, `news_count` 0; `funnel_v2.righe[VALE].pipeline_escluso_motivo` = non_actionable_long_only |

Conteggi: NO_NEWS 2, THIN_NEUTRAL 0, WRONG_SIGN 0, FILTERED 0, OUT_OF_STRATEGY_SCOPE 0. Nessun articolo da leggere: news_log ha zero righe per DB e VALE (`copertura_articoli.per_ticker.articoli_unici` = 0, `fonti_osservate` vuoto). Costo legacy |ret|×2200: DB 98,95 $, VALE 73,44 $; nel modello v2 `net_opportunity_usd` = 0 per entrambi (downside, book long-only).

Mover detenuti (non sono miss, `funnel_v2.righe`): MU +4,06% PASSIVE_EXPOSURE; CAT −5,75% EXIT_BELOW_THRESHOLD (score −0,025); PANW −3,42% EXIT_WRONG_SIGN (score +0,06); NOK −3,19% STALE_EXIT_SIGNAL (segnale 14382 del 2026-10-06 19:55, score +0,148).

Catturati/tradati: HOOD S4 ingresso 15:37 @107,97, uscita @109,29, pnl_net +18,25 $ (mtm_eod +22,34 $, `quota_nel_gap` 1,43, `quota_movimento_precedente_al_segnale` −0,44; HOOD chiude −2,22%, non è un mover). `drift_post_uscita` +3,22 $: l'uscita ha lasciato sul tavolo parte del recupero.

## 4. Attività del book

<!-- alpha-miss-book:start -->
<!-- alpha-miss-book-manifest: {"schema":1,"ingressi":["HOOD"],"chiusure":["SPCX","NOW","HOOD"]} -->

Dati deterministici dal dossier; la prosa seguente li annota e non li sostituisce.

| Tipo | Simbolo | Strategia | Ora UTC | Prezzo | Quantità | P&L netto | Motivo / qualità |
|---|---|---|---|---:|---:|---:|---|
| IN | HOOD | S4 | 15:37 | $107.9700 | 14.5053 | — | percentile 17.23%; denominatore intraday valido |
| OUT | SPCX | S4 | — | $167.5500 | 9.1623 | −$40.59 | sentiment_reversal |
| OUT | NOW | S4 | — | $137.9700 | 11.5098 | +$13.06 | portfolio_sell |
| OUT | HOOD | S4 | — | $109.2879 | 14.5053 | +$18.25 | portfolio_sell |
<!-- alpha-miss-book:end -->
1 ingresso (HOOD) e 3 chiusure (SPCX, NOW, HOOD), tutte S4, somma pnl_net −9,29 $. SPCX è l'unica perdita (−40,59 $, sentiment_reversal dopo 19,5 h; log worker 14:07: score −0,390 < soglia −0,35, stop protettivo cancellato prima della vendita forzata); drift_post_uscita +0,46 $. NOW chiude +13,06 $ dopo 19,7 h con drift −1,15 $ (uscita favorevole).

## 5. Cecita' lato uscita
Nessuna: `copertura_uscita.aggregato.n_cieche_lato_uscita` = 0 su 41 posizioni, n_indeterminati 0 (nessun `cieco_lato_uscita` null). Perdite marcate (`perdita_marcata`) su 4 posizioni, nessuna cieca: AMAT (S1, −12,32% da ingresso, 0 righe oggi, 1 seduta senza righe, fonti alpaca_benzinga+gdelt_gkg), NOK (S1, −9,39%, 1 seduta senza righe, stesse fonti; nozionale 5,99 $), WDC (S4, −26,19%, 1 seduta senza righe, fonte alpaca_benzinga), C (S1, −4,28%, 2 righe oggi). `ritorno_da_ingresso` ≠ `ritorno_seduta` (es. WDC seduta −1,37%).

## 6. Backstop NO_NEWS
Marker `CALENDAR`: nessuno. DB e VALE (e NOK, mover detenuto a zero righe) hanno `observed_catalysts` vuoto, calendario NOT_OBSERVED con FMP earnings-calendar e Alpaca Corporate Actions riuscite: mover_observed 0/3, non-mover 0/29.

Volume EOD (POST_HOC_EOD, valid_for_signal_evaluation=false): surprise mediana +0,306 sui 3 mover e −0,203 sui 29 non-mover. Misura sull'intera seduta, non disponibile prima del movimento: nessuna soglia né false-positive rate (valutazione ex-ante in #451).

Popolazione zero_news: 32 (3 mover, 29 non-mover). Copertura raw di `news_log` per settore (distinta dalla effective-timely di `copertura_articoli.per_settore`):

| Settore | ticker_with_news/ticker_universe | raw_news_coverage_rate | zero_news | mover zero_news |
|---|---:|---:|---:|---:|
| consumer | 7/11 | 63,6% | 4 | 0 |
| energy | 5/6 | 83,3% | 1 | 0 |
| etf_broad | 4/4 | 100,0% | 0 | 0 |
| financials | 8/14 | 57,1% | 6 | 1 |
| healthcare | 7/9 | 77,8% | 2 | 0 |
| industrials | 3/4 | 75,0% | 1 | 0 |
| materials | 0/2 | 0,0% | 2 | 1 |
| media | 2/5 | 40,0% | 3 | 0 |
| semis | 9/15 | 60,0% | 6 | 0 |
| tech | 15/21 | 71,4% | 6 | 0 |
| telecom | 4/5 | 80,0% | 1 | 1 |

Attribuzione fonti (FASE 5): 32 ticker con `articoli_unici` 0 e `fonti_osservate` vuoto, cioè zero resa dei provider (nessuna fonte con righe non effective-timely):

| Ticker | articoli_unici_giorno | effective_timely_articles_giorno | fonti_osservate |
|---|---:|---:|---|
| AMAT | 0 | 0 | {} |
| ARM | 0 | 0 | {} |
| ASML | 0 | 0 | {} |
| AZN | 0 | 0 | {} |
| BABA | 0 | 0 | {} |
| BRK.B | 0 | 0 | {} |
| CMCSA | 0 | 0 | {} |
| CRM | 0 | 0 | {} |
| DB | 0 | 0 | {} |
| F | 0 | 0 | {} |
| GM | 0 | 0 | {} |
| GS | 0 | 0 | {} |
| INFY | 0 | 0 | {} |
| JD | 0 | 0 | {} |
| MA | 0 | 0 | {} |
| MCD | 0 | 0 | {} |
| MMM | 0 | 0 | {} |
| NOK | 0 | 0 | {} |
| PBR | 0 | 0 | {} |
| PLTR | 0 | 0 | {} |
| RDDT | 0 | 0 | {} |
| RIO | 0 | 0 | {} |
| ROKU | 0 | 0 | {} |
| SBUX | 0 | 0 | {} |
| SNOW | 0 | 0 | {} |
| SOXX | 0 | 0 | {} |
| TXN | 0 | 0 | {} |
| UBS | 0 | 0 | {} |
| UNH | 0 | 0 | {} |
| V | 0 | 0 | {} |
| VALE | 0 | 0 | {} |
| WDC | 0 | 0 | {} |

## 7. Pattern osservato
Non chiaro. I 5 mover in calo sono eterogenei (DB financials, VALE materials, CAT industrials, PANW tech, NOK telecom), SPY −0,24%, QQQ −0,25%, dispersione 1,56%; l'unico mover al rialzo è MU +4,06%. Nessun confronto ricorrente con i report precedenti: il tema AI-hardware del 10-02/10-06 non si ripete.

## 8. Segnalazioni

* [F-001] Copertura news bassa: 32/96 simboli a zero righe, DB e VALE (mover) NO_NEWS.
  * esposizione: 96 simboli, 32 a zero righe (`mercato.watchlist_zero_news`); 5 ticker oltre la soglia di allerta di 5 sedute (ASML, MMM, RIO, ROKU, TXN); materials 0/2 e media 2/5 di copertura raw. Denominatore da findings.json (longitudinal_panels.json assente): 44 occorrenze su 42 giorni distinti.
  * evidenza contraria: se falso, DB e VALE avrebbero avuto righe in news_log o `fonti_osservate` non vuoto; invece 0/0 con provider interrogati sull'intera watchlist.
  * non-occorrenza: etf_broad 4/4 e energy 5/6 coperti; i 4 mover su 6 già a libro non sono miss; i 29 non-mover a zero righe non hanno costo.
  * next evidence: ripetere il conteggio `no_news_backstop.per_sector` per materials sulle prossime sedute (due ticker, VALE e RIO) e verificare se il vuoto è del provider (fonti_osservate) o del filtro.
  * meccanismo e fonte: §3 e §6; `candidati_miss[].news_count` 0, `copertura_articoli.per_ticker[DB|VALE]`.
  * costo: legacy |ret|×size = 0,0450×2200 + 0,0334×2200 = 98,95 + 73,44 = 172,38 $ (congetturale); alternativa scartata: costo v2 reale 0 $ perché entrambi in discesa su book long-only (`accessible_opportunity_usd` 0), quindi il costo effettivo non è dimostrato.
* [F-011] signal_id NULL sulle SELL: 1/3 con signal_id (`decision_signal_id_coverage.regressions` = ["SELL"]); BUY 2/2, SKIP_THRESHOLD 706/706.
  * esposizione: 3 decisioni SELL su 763 righe totali (761 con signal_id, fill_rate 0,9974); 35 giorni distinti su 37 occorrenze in findings.json.
  * evidenza contraria: se falso, le 3 SELL (SPCX, NOW, HOOD) avrebbero tutte signal_id; invece 2 no (`without_signal_id` 2, atteso `must_be_full`).
  * non-occorrenza: BUY, SKIP_FALLBACK (42/42), SKIP_PYRAMIDING (9/9) e SKIP_REVERSAL_OWNER hanno signal_id pieno.
  * next evidence: join read-only fra le due SELL senza signal_id e `execution_decisions.reason_code` per verificare se sono le uscite portfolio_sell (NOW, HOOD) rispetto alla sentiment_reversal (SPCX).
  * meccanismo e fonte: §4; `decision_signal_id_coverage.by_reason_code.SELL`. Non verificato quale delle 3 SELL abbia l'id.
  * costo: non stimabile (nessun P&L attribuibile alla mancanza di catena); null.

## 9. Appendice

### (a) Rendimenti watchlist (`mercato.rendimenti`)

| # | Simbolo | Return |
|---:|---|---:|
| 1 | MU | +4,06% |
| 2 | LLY | +2,70% |
| 3 | RDDT | +2,52% |
| 4 | JD | +2,00% |
| 5 | NVO | +1,95% |
| 6 | PFE | +1,82% |
| 7 | ABBV | +1,75% |
| 8 | NFLX | +1,47% |
| 9 | JNJ | +1,44% |
| 10 | AMZN | +1,42% |
| 11 | PLTR | +1,07% |
| 12 | TMUS | +1,04% |
| 13 | XLV | +1,03% |
| 14 | AZN | +0,95% |
| 15 | AAPL | +0,91% |
| 16 | WMT | +0,90% |
| 17 | DELL | +0,86% |
| 18 | GOOGL | +0,81% |
| 19 | PBR | +0,80% |
| 20 | COST | +0,70% |
| 21 | DIS | +0,69% |
| 22 | MA | +0,62% |
| 23 | MRK | +0,60% |
| 24 | INTC | +0,55% |
| 25 | ROKU | +0,44% |
| 26 | V | +0,39% |
| 27 | ERIC | +0,32% |
| 28 | AVGO | +0,19% |
| 29 | T | +0,17% |
| 30 | BRK,B | +0,14% |
| 31 | MSFT | +0,09% |
| 32 | INFY | +0,00% |
| 33 | NOW | -0,07% |
| 34 | UNH | -0,09% |
| 35 | AXP | -0,10% |
| 36 | SAP | -0,16% |
| 37 | CRM | -0,19% |
| 38 | SPY | -0,24% |
| 39 | QQQ | -0,25% |
| 40 | XOM | -0,26% |
| 41 | XLK | -0,30% |
| 42 | HD | -0,32% |
| 43 | IBM | -0,35% |
| 44 | PG | -0,40% |
| 45 | VZ | -0,46% |
| 46 | CSCO | -0,47% |
| 47 | XLF | -0,48% |
| 48 | JPM | -0,51% |
| 49 | AMD | -0,55% |
| 50 | XLE | -0,61% |
| 51 | MCD | -0,68% |
| 52 | MS | -0,69% |
| 53 | NKE | -0,72% |
| 54 | NVDA | -0,74% |
| 55 | TSLA | -0,75% |
| 56 | SHEL | -0,79% |
| 57 | BA | -0,79% |
| 58 | MRVL | -0,81% |
| 59 | ORCL | -0,84% |
| 60 | SNOW | -0,92% |
| 61 | MMM | -0,93% |
| 62 | C | -0,93% |
| 63 | BAC | -1,05% |
| 64 | BP | -1,11% |
| 65 | GS | -1,11% |
| 66 | SOXX | -1,12% |
| 67 | CVX | -1,17% |
| 68 | GM | -1,24% |
| 69 | IWM | -1,29% |
| 70 | F | -1,30% |
| 71 | CMCSA | -1,37% |
| 72 | WDC | -1,37% |
| 73 | SONY | -1,38% |
| 74 | TM | -1,43% |
| 75 | WFC | -1,53% |
| 76 | ASML | -1,59% |
| 77 | AMAT | -1,81% |
| 78 | GE | -1,86% |
| 79 | BIDU | -2,01% |
| 80 | BABA | -2,07% |
| 81 | TSM | -2,09% |
| 82 | QCOM | -2,16% |
| 83 | UBS | -2,17% |
| 84 | HOOD | -2,22% |
| 85 | ADBE | -2,25% |
| 86 | META | -2,38% |
| 87 | SPCX | -2,51% |
| 88 | SBUX | -2,63% |
| 89 | ARM | -2,71% |
| 90 | TXN | -2,78% |
| 91 | RIO | -2,85% |
| 92 | NOK | -3,19% |
| 93 | VALE | -3,34% |
| 94 | PANW | -3,42% |
| 95 | DB | -4,50% |
| 96 | CAT | -5,75% |

### (b) Altri finding toccati
- [F-009] not_exposed: nessun mover rialzista a segnale sotto gate fuori dal book (l'unico, MU, è già detenuto); `active_signal_recall` 0/0.
- [F-030] not_exposed: HOOD entra con `quota_movimento_precedente_al_segnale` −0,44 (non dopo il movimento) e non è un mover.
- [F-020] not_exposed: DB ha zero righe, nessun articolo org_lookup attribuito oggi.
- [F-024] supported (debole): NOK STALE_EXIT_SIGNAL, segnale 14382 del 2026-10-06 19:55 con score +0,148; posizione S1 da 5,99 $, costo non rilevante.
- [F-059] supported (debole): CAT EXIT_BELOW_THRESHOLD a score −0,025 (nessuna uscita su −5,75%); `soglia_exit` null.

### (c) Successi
- HOOD (trade 1058): S4 +18,25 $ in 2,5 h, ingresso a entry_percentile 0,17; non è un mover (−2,22%), quindi non è una cattura di mover.
- NOW (S4, portfolio_sell): +13,06 $ dopo 19,7 h. Nessun mover catturato con P&L positivo.
