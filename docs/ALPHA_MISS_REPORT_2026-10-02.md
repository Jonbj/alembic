# Alpha-miss report 2026-10-02

(prompt alpha_miss_prompt_v2, dossier schema 3.1 generato il 2026-10-09T08:00:31.470713+00:00; prezzi Alpaca SIP, adjustment=all)

## 1. Decision card
1. 12 mover |ret|>=3% su 96 simboli (10 su, 2 giù, soglia 3%); 7 già a libro all'open (held_at_open_rate 7/12), 0 ingressi e 0 chiusure nella seduta.
2. Miss d'ingresso: SPCX +7,35% e TSLA +4,65% senza alcuna riga news_log (NO_NEWS); AVGO +3,35% con score +0,2136 (segno giusto) sotto il gate 0,30; active_signal_recall 0/2.
3. watchlist_zero_news 68/96; WDC (S4) -10,22% in seduta, -24,39% dall'ingresso, con segnale EXIT_WRONG_SIGN (score_firmato +0,0184).

## 2. Stato carta
as_of economic_pnl.json: **2026-09-17** (generato 2026-09-18; l'ultima osservazione precedente a questa seduta, non aggiornata a 10-02).
- Giorno 30/40 (al 09-17).
- Quota NO_NEWS dominante: 13/30 giorni, soglia carta 0,6, superata: no.
- S4 economico cumulato -696,33 $ vs ±200 $: fuori banda (within=false). S1 +664,95 $ (delta vs SPY -279,03 $); BOOK -66,22 $.
- Il file non copre le sedute dal 09-18 al 10-02: i numeri sono quelli dichiarati, non stimati.

## 3. Miss del giorno

| Simbolo | Return | Categoria | Campo del dossier che decide |
|---|---|---|---|
| SPCX | +7,35% | (a) NO_NEWS | candidati_miss.news_count=0; funnel_v2 pipeline=NO_RELEVANT_NEWS |
| TSLA | +4,65% | (a) NO_NEWS | candidati_miss.news_count=0; funnel_v2 pipeline=NO_RELEVANT_NEWS |
| AVGO | +3,35% | (b) THIN_NEUTRAL | funnel_v2 pipeline=BELOW_GATE, score_firmato +0,2136 < 0,30 (segno corretto); quota_righe_fanout 1,0 |
| ORCL | +3,07% | (b) THIN_NEUTRAL | funnel_v2 pipeline=BELOW_GATE, score_firmato +0,0356 < 0,30 |
| NKE | -3,64% | non conteggiato (NON_ACTIONABLE) | funnel_v2 pipeline_escluso_motivo=non_actionable_long_only; max_score_own -0,6026 sopra gate, ribassista, long-only |

Conteggi: NO_NEWS 2, THIN_NEUTRAL 2, WRONG_SIGN 0, FILTERED 0, OUT_OF_STRATEGY_SCOPE 0. Nessun FILTERED: nessuno stadio oltre il gate né guardia bloccante nei candidati (le guard_decisions su AVGO/ORCL/NKE sono tutte SKIP_THRESHOLD).

Testo articoli (evidenza qualitativa, dati non fidati): AVGO ha tre righe benzinga pre-open, fra cui "Broadcom Chases NVIDIA With $60 Billion Financing Plan for AI Customers" (12:44 UTC), articolo che figura anche su ORCL (fan-out); ORCL ha un reiterato "Market Outperform" Citizens, un comunicato su costi energetici in Wisconsin, un pezzo ribassista su Eisman e uno sul bond a 20 anni (8,1%): mix eterogeneo, coerente con score vicini a zero. SPCX e TSLA: zero righe.

Titoli catturati (7, tutti già a libro all'apertura, nessun ingresso nuovo, `ingressi`=[]; `chiusure`=[]): ARM +5,18%, TXN +4,44%, DELL +3,84%, CSCO +3,56%, ASML +3,25%, PBR +3,19% (passive_pnl +33,06 $, S1), WDC -10,22% (S4). Esito P&L per posizione: DATA_INCOMPLETE per i blocchi `ingressi`/`chiusure` (vuoti); l'unico P&L passivo dichiarato è nello snapshot di apertura (PBR sopra). Nota: per WDC lo snapshot di apertura riporta qty_open 0,0 mentre copertura_uscita riporta qty 0,3347 (discrepanza interna al dossier, non risolta qui).

## 4. Attività del book

<!-- alpha-miss-book:start -->
<!-- alpha-miss-book-manifest: {"schema":1,"ingressi":[],"chiusure":[]} -->

Dati deterministici dal dossier; la prosa seguente li annota e non li sostituisce.

| Tipo | Simbolo | Strategia | Ora UTC | Prezzo | Quantità | P&L netto | Motivo / qualità |
|---|---|---|---|---:|---:|---:|---|
<!-- alpha-miss-book:end -->
Seduta senza ingressi né chiusure nel dossier (`ingressi`=[], `chiusure`=[]); l'attività si riduce a decisioni SKIP (81 SKIP_THRESHOLD, 2 SKIP_PYRAMIDING nelle guard_decisions). Il book è rimasto passivo: 7 mover su 12 già detenuti.

## 5. Cecità lato uscita
Nessuna: n_cieche_lato_uscita=0, n_indeterminati=0 su 40 posizioni (26 con copertura nulla, 31 con copertura effettiva nulla, 5 con perdita marcata). Perdite marcate non cieche: AMAT (S1) -9,05% da ingresso, NOK (S1) -9,56%, C (S1) -3,40%, PFE (S1) -3,10%, WDC (S4) -24,39% (3 righe news quel giorno, quindi non cieca). AMAT/NOK mostrano `fonti_osservate_finestra` alpaca_benzinga+gdelt_gkg; sedute consecutive senza righe: 1 su tutte (sotto il minimo 2). `ritorno_da_ingresso` è la perdita mentre detenute; `ritorno_seduta` il movimento del titolo (es. AMAT +2,03% in seduta).

## 6. Backstop NO_NEWS
Mover NO_NEWS: SPCX, TSLA. `observed_catalysts` vuoto per entrambi; calendario societario NOT_OBSERVED (calendar mover_observed 0/7, non-mover 0/61; fonti FMP earnings-calendar e Alpaca Corporate Actions complete). Nessun marker CALENDAR.
Volume EOD (POST_HOC_EOD, non point-in-time, valid_for_signal_evaluation=false): surprise mediana mover -0.015 su 7 vs non-mover -0.100 su 61. È descrizione di una seduta intera: non era disponibile prima del movimento e non si ricava soglia né false-positive rate (valutazione ex-ante in #451).
Popolazione zero_news 68 (7 mover, 61 non-mover).

Copertura raw `news_log` per settore (distinta da effective-timely):

| Settore | ticker_with_news/universe | raw_news_coverage_rate | mover zero-news | calendario osservato zero-news |
|---|---|---|---|---|
| consumer | 1/11 | 9.1% | 1 | 0 |
| energy | 1/6 | 16.7% | 1 | 0 |
| etf_broad | 2/4 | 50.0% | 1 | 0 |
| financials | 4/14 | 28.6% | 0 | 0 |
| healthcare | 2/9 | 22.2% | 0 | 0 |
| industrials | 1/4 | 25.0% | 0 | 0 |
| materials | 0/2 | 0.0% | 0 | 0 |
| media | 1/5 | 20.0% | 0 | 0 |
| semis | 7/15 | 46.7% | 3 | 0 |
| tech | 8/21 | 38.1% | 1 | 0 |
| telecom | 1/5 | 20.0% | 0 | 0 |

## 7. Pattern osservato
Rotazione verso hardware AI/semis e tech infrastrutturale (ARM +5,18%, TXN +4,44%, DELL +3,84%, CSCO +3,56%, AVGO +3,35%, ASML +3,25%) contro storage in calo (WDC -10,22% su notizia Toshiba: raddoppio dell'offerta HDD; la riga benzinga su Seagate -13% è nei dati di WDC). Il lato debole è isolato (2 ribassi); SPCX e TSLA sono estranei al tema. Pattern ricorrente rispetto ai giorni precedenti: non verificato oltre il singolo giorno.

## 8. Segnalazioni
Denominatori: longitudinal_panels.json assente; conteggi dalle occorrenze di findings.json (occorrenze registrate, non giorni distinti verificati).

* **[F-009]** Il gate 0,30 scarta un segno corretto su un mover: AVGO +3,35% con score +0,2136.
  - esposizione: 4 candidati ENTRY_OPPORTUNITY oggi, 2 con notizia (AVGO, ORCL) = base di active_signal_recall 0/2; occorrenze registrate in F-009: 26.
  - evidenza contraria: se falso, AVGO avrebbe avuto score firmato >=0,30 o segno opposto; non è così (+0,2136 vs 0,30). ORCL (+0,0356) è un contro-esempio: sotto gate per magnitudo vera, non per gate troppo alto.
  - non-occorrenza: TSLA e SPCX non hanno segnale (non attribuibili al gate); ORCL ha segni misti (max_score_own -0,1889).
  - next evidence: ricalcolo read-only sulle sedute già archiviate del rapporto score_firmato/gate sui mover con segno corretto (nessuna taratura, charter in vigore).
  - meccanismo e fonte: §3 e `funnel_v2.righe[AVGO].evidence.score_firmato`/`soglia_gate`; quota_righe_fanout=1,0 (articolo su terzi).
  - costo: 2200 × 0,03346525 = 73,62 $ (congetturale, size S4 ~2% NAV; accessibile dal dossier 4,87 $ netto 3,65 $: l'ingresso all'open 14:07 UTC avrebbe già perso gran parte del movimento).
* **[F-001]** Copertura news: 68/96 simboli a zero righe (era 28/96 il 10-01) e due dei tre mover non detenuti (SPCX, TSLA) senza alcuna riga.
  - esposizione: 96 simboli, 68 a zero news; copertura raw per settore da 0% (materials) a 46,7% (semis).
  - evidenza contraria: se falso, SPCX/TSLA avrebbero righe con rilevanza ISSUER_SPECIFIC; `rilevanza` è 0 su tutte le classi.
  - non-occorrenza: semis 7/15 con news (raw); AVGO e ORCL hanno righe; ASML, PBR e altri mover detenuti risultano a zero righe (non miss d'ingresso).
  - next evidence: confronto read-only delle fonti per ticker (blocco `copertura_articoli.per_ticker.fonti_osservate`) sulle ultime sedute per distinguere assenza di fonte e assenza di notizia.
  - meccanismo e fonte: §6 e `no_news_backstop.per_sector`; `copertura_articoli.effective_timely_coverage` 16/96 (16,7%).
  - costo: 2200 × (0,0735463 + 0,0465392) = 264,19 $ (congetturale; dossier gross SPCX 161,80 + TSLA 102,39; accessibile netto SPCX +24,29, TSLA -9,70).
  - alternative scartate: assenza di notizie reali (non verificabile: fonti_osservate vuote).
* **[F-036]** WDC (S4) è -24,39% dall'ingresso, sub-share (qty 0,3347) e non protetta, e il trigger -15/20% non produce alert.
  - esposizione: 40 posizioni, 9 non proteggibili (qty<1: AMAT, AMD, ASML, CAT, DELL, LLY, NOK, SPY, WDC); WDC unprotected a -24,3%/-24,9%/-25,2%/-26,9% nei cicli 14:07/14:22/14:37/14:52 (worker-2026-10-02.log).
  - evidenza contraria: se falso, un alert/mobile_event sarebbe presente; nel log compare solo WARNING #161. Non verificato in DB oggi (mobile_events non interrogata in questa sessione).
  - non-occorrenza: WDC non cieca lato uscita (3 righe, 3 segnali).
  - next evidence: SELECT COUNT(*) su mobile_events per il 2026-10-02 e riga risk_reports.alerts.
  - meccanismo e fonte: §5, `copertura_uscita.posizioni[WDC]`; funnel_v2 EXIT_WRONG_SIGN con score_firmato +0,0184, mentre la timeline riporta altri due segnali WDC (-0,2334, -0,3045): ordine temporale non verificato qui.
  - costo: non stimabile dal dossier (qty_open 0,0 nello snapshot contro 0,3347 in copertura_uscita): null.

## 9. Appendice
### (a) Rendimenti watchlist (mercato.rendimenti)

| # | Simbolo | Return |
|---|---|---|
| 1 | SPCX | +7.35% |
| 2 | ARM | +5.18% |
| 3 | TSLA | +4.65% |
| 4 | TXN | +4.44% |
| 5 | DELL | +3.84% |
| 6 | CSCO | +3.56% |
| 7 | AVGO | +3.35% |
| 8 | ASML | +3.25% |
| 9 | PBR | +3.19% |
| 10 | ORCL | +3.07% |
| 11 | TSM | +2.96% |
| 12 | AMD | +2.95% |
| 13 | CAT | +2.31% |
| 14 | VALE | +2.30% |
| 15 | NOK | +2.22% |
| 16 | SOXX | +2.18% |
| 17 | AMAT | +2.03% |
| 18 | UNH | +1.83% |
| 19 | PANW | +1.76% |
| 20 | MRVL | +1.57% |
| 21 | GOOGL | +1.56% |
| 22 | QCOM | +1.53% |
| 23 | RIO | +1.44% |
| 24 | HOOD | +1.43% |
| 25 | SONY | +1.40% |
| 26 | NVDA | +1.34% |
| 27 | AMZN | +1.33% |
| 28 | MS | +1.22% |
| 29 | C | +1.18% |
| 30 | TMUS | +1.18% |
| 31 | ABBV | +1.11% |
| 32 | AAPL | +1.02% |
| 33 | QQQ | +1.02% |
| 34 | XLK | +1.01% |
| 35 | MSFT | +0.92% |
| 36 | IWM | +0.90% |
| 37 | DIS | +0.85% |
| 38 | ERIC | +0.81% |
| 39 | ROKU | +0.75% |
| 40 | SPY | +0.74% |
| 41 | PG | +0.67% |
| 42 | BA | +0.67% |
| 43 | GS | +0.66% |
| 44 | BP | +0.65% |
| 45 | SHEL | +0.65% |
| 46 | COST | +0.62% |
| 47 | BRK.B | +0.43% |
| 48 | MA | +0.41% |
| 49 | MRK | +0.34% |
| 50 | META | +0.30% |
| 51 | UBS | +0.29% |
| 52 | WFC | +0.25% |
| 53 | AXP | +0.23% |
| 54 | V | +0.23% |
| 55 | XLE | +0.19% |
| 56 | HD | +0.14% |
| 57 | XOM | +0.12% |
| 58 | XLF | +0.06% |
| 59 | BAC | +0.04% |
| 60 | MCD | +0.03% |
| 61 | WMT | +0.00% |
| 62 | T | +0.00% |
| 63 | XLV | -0.01% |
| 64 | VZ | -0.13% |
| 65 | SBUX | -0.18% |
| 66 | CVX | -0.20% |
| 67 | NVO | -0.21% |
| 68 | JPM | -0.24% |
| 69 | SNOW | -0.28% |
| 70 | DB | -0.46% |
| 71 | AZN | -0.51% |
| 72 | INTC | -0.56% |
| 73 | CMCSA | -0.61% |
| 74 | LLY | -0.61% |
| 75 | PLTR | -0.68% |
| 76 | MMM | -0.69% |
| 77 | CRM | -0.84% |
| 78 | GE | -0.91% |
| 79 | TM | -1.01% |
| 80 | JNJ | -1.02% |
| 81 | SAP | -1.05% |
| 82 | RDDT | -1.12% |
| 83 | PFE | -1.14% |
| 84 | NFLX | -1.16% |
| 85 | GM | -1.31% |
| 86 | IBM | -1.32% |
| 87 | F | -1.39% |
| 88 | BIDU | -1.48% |
| 89 | ADBE | -1.49% |
| 90 | BABA | -1.49% |
| 91 | MU | -2.05% |
| 92 | JD | -2.24% |
| 93 | NOW | -2.45% |
| 94 | INFY | -2.73% |
| 95 | NKE | -3.64% |
| 96 | WDC | -10.22% |

### (b) Altri finding toccati
* [F-040]: supported, NKE -3,64% con max_score_own -0,6026 sopra gate, ribassista, escluso long-only.
* [F-023] / [F-056]: not_exposed, nessun dato del dossier che li decida per una seduta senza ordini.
* [F-075]: supported, held_at_open_rate 7/12 conta come catturati mover con esposizione residua (WDC 139 $ di nozionale).
* [F-053]: supported, equity di 10-02 letta come riga con timestamp 10-03 (110.199,99 $).
* [F-093]: not_exposed, equity al 10-02 non verificata sul cash.

### (c) Casi di successo
PBR (S1) +3,19%, passive_pnl +33,06 $ (detenuto all'open, nessun ingresso del giorno). Nessun ingresso del giorno con P&L positivo (`ingressi`=[]).

### FASE 5: attribuzione fonti per ticker
Ticker con articoli_unici=0 o fonti_osservate vuote (da `copertura_articoli.per_ticker`, forma `{fonte:{articoli_unici, articoli_effective_timely}}`): AAPL, ABBV, ADBE, AMAT, ASML, AXP, BABA, BAC, BIDU, BP, BRK.B, C, CAT, CMCSA, COST, CRM, CSCO, CVX, DB, DELL, ERIC, F, GE, GM, GS, HD, IBM, INFY, INTC, IWM, JD, JNJ, MA, MCD, MMM, MRK, MRVL, NFLX, NOK, NOW, NVO, PBR, PFE, PG, QCOM, RDDT, RIO, ROKU, SAP, SBUX, SHEL, SONY, SOXX, SPCX, T, TM, TMUS, TSLA, TXN, UNH, V, VALE, WFC, WMT, XLE, XLF, XLK, XLV. Per tutti: articoli_unici_giorno 0, effective_timely_articles_giorno 0, fonti_osservate `{}` (blind_set.per_ticker non presente nel dossier: i conteggi vengono da copertura_articoli). Nessuna fonte con righe ma effective-timely zero tra questi. Nessuna raccomandazione operativa.
