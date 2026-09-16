# Alpha Miss Report — 2026-09-15

Contratto: `alpha_miss_prompt_v2`, dossier `schema_version` 3.1. Fonte numerica unica: `docs/evidence/dossier/2026-09-15.json` (generato 2026-09-16T08:00:34Z, `fonte_prezzi`: Alpaca SIP adjustment=all).

## 1. Decision card

1. **7 mover ≥3%** sul book (soglia pre-registrata `soglia_mover`=0.03): 1 su (QCOM +4,25%), 6 giù (WDC −3,51%, HOOD −3,39%, GE −3,31%, SPCX −3,15%, ORCL −3,07%, NFLX −3,01%). Nessuno catturato oggi (`catturati`=0).
2. **Copertura news migliore dell'intera finestra osservata**: `watchlist_zero_news`=31/96 (32,3%), sotto il minimo precedente di 37 (09-08).
3. **3 posizioni detenute cieche lato uscita** (`copertura_uscita.aggregato.n_cieche_lato_uscita`=3): PFE, SBUX, UNH — nozionale cieco 2.033,70 $.

## 2. Stato carta

Da `docs/evidence/economic_pnl.json`, **as_of 2026-09-11** (i cumulati arrivano al giorno osservato precedente al 09-15; nessuna seduta 09-12/09-14 nel ledger — weekend + gap).

- Giorno **27/40** della finestra di osservazione (inizio 2026-08-03, scadenza attesa 2026-09-28).
- Quota NO_NEWS dominante: **13/27 = 48,1%**, sotto la soglia carta 0,60 (`superata_soglia`=false).
- S4 economico cumulato: **−707,41 $** vs banda ±200 $ (`within`=false — fuori banda, peggio della soglia).
- Book cumulato: +206,47 $. S1 cumulato: +948,72 $ (delta vs benchmark SPY: +105,60 $).

## 3. Miss del giorno

5 candidati nel dossier (`candidati_miss`), tutti mover non detenuti dal book. Nessun `causa` ha raggiunto lo stadio pipeline oltre il gate — **nessun FILTERED possibile oggi** (`funnel_v2.conteggi_pipeline`={"NO_RELEVANT_NEWS":1}, nessuna riga `risk_block`/`order`/`fill`).

| Simbolo | Return% | Categoria | Campo del dossier che decide |
|---|---:|---|---|
| QCOM | +4,25% | **NO_NEWS** | `funnel_v2.righe[QCOM].pipeline`="NO_RELEVANT_NEWS": l'unica riga in `news_log` (news_count=1) è TAG_UNCONFIRMED, attribuita per fanout da un pezzo macro ("10-Year Yield Tops 5%, Oil Storms Past $105: Stock Market Today"), non confermata rilevante per QCOM — non un buco letterale a zero righe, ma zero copertura confermata. Il campo grezzo `candidati_miss[QCOM].causa`="BELOW_GATE" (score fanout −0,222, sotto `soglia_gate_usata`=0,30) resta la vista legacy pre-#509, che non applica il filtro di rilevanza. |
| ORCL | −3,07% | **OUT_OF_STRATEGY_SCOPE** | `funnel_v2.righe[ORCL].actionability`="NON_ACTIONABLE" (`pipeline_escluso_motivo`="non_actionable_long_only"): ribasso, non detenuto, book long-only — nessuna azione possibile per costruzione, indipendentemente dal segnale (own score +0,183 alle 17:04, ISSUER_SPECIFIC, comunque di segno opposto al prezzo). Il campo grezzo `causa`="BELOW_GATE"/`legacy_causa`="BELOW_GATE" è il verdetto #208 pre-#509 (score-vs-gate puro, non verificava l'attuabilità). |
| GE | −3,31% | **OUT_OF_STRATEGY_SCOPE** | `funnel_v2.righe[GE].actionability`="NON_ACTIONABLE" (ribasso, non detenuto). Anche a zero righe `news_log` (news_count=0) — il campo grezzo `causa`="NO_NEWS" precede l'assenza di attuabilità nella vista legacy, ma la vista v2 la rende comunque non azionabile a prescindere dalla notizia. |
| HOOD | −3,39% | **OUT_OF_STRATEGY_SCOPE** | `funnel_v2.righe[HOOD].actionability`="NON_ACTIONABLE"; `legacy_causa`="NON_CLASSIFICATO" promossa (news_count=3, un articolo ISSUER_SPECIFIC score −0,12, segno corretto ma sotto gate — comunque non azionabile per direzione). |
| SPCX | −3,15% | **OUT_OF_STRATEGY_SCOPE** | `funnel_v2.righe[SPCX].actionability`="NON_ACTIONABLE"; `legacy_causa`="NON_CLASSIFICATO" promossa (news_count=11, 3 ISSUER_SPECIFIC, score proprio massimo −0,364 — segno corretto ma comunque non azionabile per direzione). |

**Nota di metodo**: 4 dei 5 candidati sono ribassisti non detenuti — su un libro long-only questo esclude qualunque cattura per costruzione, non per qualità del segnale (`funnel_v2.conteggi_actionability`={"ENTRY_OPPORTUNITY":1,"EXIT_RISK":2,"NON_ACTIONABLE":4}). Ho preferito l'asse `actionability` (più granulare, introdotto da #509) al campo grezzo `causa` quando i due divergono, perché il campo grezzo non verifica l'attuabilità — la nota per riga riporta comunque il valore legacy per continuità con `aggregati.cause_del_giorno` (che, per vincolo #288 Opzione 1, resta invariato: {"NO_NEWS":1,"BELOW_GATE":2,"NON_CLASSIFICATO":2}, dominante "BELOW_GATE").

**Titoli catturati oggi**: nessuno fra i 7 mover.

## 4. Attività del book

<!-- alpha-miss-book:start -->
<!-- alpha-miss-book-manifest: {"schema":1,"ingressi":["BA","PLTR"],"chiusure":["NFLX","PLTR"]} -->

Dati deterministici dal dossier; la prosa seguente li annota e non li sostituisce.

| Tipo | Simbolo | Strategia | Ora UTC | Prezzo | Quantità | P&L netto | Motivo / qualità |
|---|---|---|---|---:|---:|---:|---|
| IN | BA | S4 | 16:07 | $210.3000 | 6.9038 | — | percentile 44.06%; denominatore intraday valido |
| IN | PLTR | S4 | 16:07 | $172.8700 | 8.3986 | — | percentile 47.90%; denominatore intraday valido |
| OUT | NFLX | S4 | — | $77.8800 | 17.9503 | −$48.72 | portfolio_sell |
| OUT | PLTR | S4 | — | $174.8000 | 8.3986 | +$15.41 | hold_minimum_expiry |
<!-- alpha-miss-book:end -->

2 ingressi S4 (BA a 210,30 $ e PLTR a 172,87 $, entrambi 16:07 UTC — nessuno dei due è un mover). 2 chiusure S4: NFLX (mover −3,01% oggi, uscita 77,88 $, P&L netto −48,72 $, `portfolio_sell`, tenuta ~21h) e PLTR (stessa posizione aperta e chiusa in giornata, uscita 174,80 $, P&L netto +15,41 $, `hold_minimum_expiry`, tenuta 1,75h). Realizzato del giorno: S4 −33,31 $, S1 0,00 $.

## 5. Cecità lato uscita

Da `copertura_uscita` (40 posizioni, `n_indeterminati`=0 — nessuna riga `cieco_lato_uscita: null`, nessun dato mancante da dichiarare).

| Ticker | Strategia | `ritorno_da_ingresso` | `sedute_consecutive_senza_righe` | `fonti_osservate_finestra` | Nozionale |
|---|---|---:|---:|---|---:|
| PFE | S1 | **−3,97%** | 3 | `alpaca_benzinga` | 799,31 $ |
| SBUX | S1 | **−8,36%** | 4 | `alpaca_benzinga` | 635,66 $ |
| UNH | S1 | **−12,09%** | 2 | `alpaca_benzinga` | 598,72 $ |

`fonti_osservate_finestra` non è vuota in nessuno dei tre casi: i provider erano vivi e interrogati sull'intera watchlist, semplicemente non hanno reso nulla su questi tre ticker nella finestra. `ritorno_da_ingresso` è la perdita accumulata dall'ingresso al close di oggi (nessuna delle tre è uscita oggi, `uscita_nella_seduta`=false per tutte) — non confondere con `ritorno_seduta` (PFE −0,61%, SBUX −2,51%, UNH −1,99% solo oggi): il movimento della giornata non è il problema, l'assenza prolungata di righe lo è.

Aggregato: 40 posizioni, 11 a copertura grezza nulla, 23 a copertura effective-timely nulla, 11 in perdita marcata, **3 cieche**, nozionale cieco **2.033,70 $**.

## 6. Backstop NO_NEWS

Popolazione: 31 simboli a zero righe `news_log`. Fra i 7 mover, solo GE e WDC sono a zero righe (gli altri 5 hanno almeno una riga, anche se spesso non confermata rilevante o non azionabile).

### 6a. Marker calendario

| Simbolo | Return% | `observed_catalysts` |
|---|---:|---|
| GE | −3,31% | `[]` — calendario `NOT_OBSERVED` |
| WDC | −3,51% | `[]` — calendario `NOT_OBSERVED` |

Nessun marker `CALENDAR` su nessuno dei due mover a zero notizie (`calendario_earnings.status`="OBSERVED" oggi, entrambe le fonti FMP/Alpaca hanno risposto: lo 0/2 è un'osservazione, non un fallimento di fetch).

### 6b. Volume — `POST_HOC_EOD`, non point-in-time

- GE: volume 7.278.422, ADV20 3.803.412, sorpresa **+91,4%**.
- WDC: volume 7.873.054, ADV20 5.963.793, sorpresa **+32,0%**.

Entrambi i mover a zero notizie hanno volume ben sopra l'ADV — descrizione, non un segnale disponibile prima del movimento; nessuna soglia scelta, nessun false-positive rate stimato (valutazione ex-ante separata in #451).

### 6c. Copertura raw di `news_log` per settore (tutti i settori, inclusi gli zero su N)

| Settore | ticker_with_news / ticker_universe | `raw_news_coverage_rate` | mover a zero news |
|---|---:|---:|---:|
| energy | 6/6 | 100,0% | 0 |
| etf_broad | 4/4 | 100,0% | 0 |
| semis | 12/15 | 80,0% | 1 (WDC) |
| financials | 10/14 | 71,4% | 0 |
| industrials | 3/4 | 75,0% | 1 (GE) |
| healthcare | 6/9 | 66,7% | 0 |
| tech | 14/21 | 66,7% | 0 |
| media | 3/5 | 60,0% | 0 |
| consumer | 6/11 | 54,5% | 0 |
| materials | 0/2 | **0,0%** | 0 |
| telecom | 1/5 | 20,0% | 0 |

`materials` a 0/2 in copertura raw (nessun mover oggi in quel settore). Distinta dalla copertura effective-timely (`copertura_articoli.per_settore`, quota complessiva 42/96=43,75%): non mescolare le due quote.

## 7. Pattern osservato

**Pattern non chiaro sui mover.** I 6 ribassisti coprono 5 settori diversi (media/NFLX, tech/ORCL, industrials/GE, financials/HOOD, semis/WDC) più SPCX (mappato su `etf_broad`, ticker privato senza vero benchmark settoriale) — nessuna rotazione settoriale leggibile. L'unico rialzista, QCOM, sale su un articolo macro non specifico (fanout), non su una notizia propria.

Segnale di sfondo non catturato dalla soglia mover: **rally energy diffuso ma sotto soglia** — PBR +2,93%, CVX +2,64%, SHEL +2,59%, XOM +2,57%, BP +2,24%, XLE +2,17% sono i primi 6 posti della classifica dopo QCOM, tutti energy, nessuno sopra il 3%. Non lo registro come mover/pattern del giorno perché nessuno supera `soglia_mover`, ma è la struttura più coerente della sessione.

## 8. Segnalazioni

**[F-001]** Copertura news bassa sulla watchlist — nuova occorrenza 2026-09-15, aggravata sul lato uscita.

- **Esposizione**: 31 ticker della watchlist erano a zero notizie oggi; fra i 7 mover, 2 (GE, WDC) erano a zero righe pure, e uno di questi (QCOM, tramite l'unica riga non confermata) ha prodotto l'unico miss NO_NEWS azionabile. Sul lato uscita, 40 posizioni aperte erano esposte al controllo cecità (soglia −3% da ingresso, 2 sedute minime senza righe).
- **Evidenza contraria**: se il fenomeno fosse assente, i mover a zero/non-confermata notizia sarebbero rari (vicino a 0/7) e le 11 posizioni in perdita marcata avrebbero quasi tutte almeno una riga `news_log` nella finestra a 10 sedute.
- **Non-occorrenza**: 5 dei 7 mover avevano almeno una riga di news (anche se spesso TAG_UNCONFIRMED/fanout o non azionabile per direzione); 37 delle 40 posizioni aperte NON risultano cieche lato uscita nonostante 11 in perdita marcata — la cecità non è generalizzata a tutto il libro in rosso, resta concentrata su 3 nomi.
- **Next evidence**: se nella prossima seduta `watchlist_zero_news` resta ≤31 E il numero di posizioni cieche lato uscita cala in parallelo, la lettura "la copertura grezza migliora ma non protegge le posizioni già aperte" è falsificata; se invece la cecità lato uscita continua a salire nonostante la copertura grezza migliore, il pattern di oggi è confermato.
- **Meccanismo e fonte**: §3 (QCOM, `funnel_v2.righe[QCOM].pipeline`="NO_RELEVANT_NEWS"), §5 (`copertura_uscita.aggregato`, 3 posizioni `cieco_lato_uscita`=true), §6c (`no_news_backstop.per_sector`, copertura raw per settore).
- **Costo**: 93,42 $ lordo (formula: 2.200 $ × 0,042465 — size S4 tipica ~2% NAV su QCOM +4,25%, unico NO_NEWS puro azionabile). Sull'orizzonte realmente accessibile (`opportunity_v2.net_opportunity_usd` = entrata al primo ciclo eleggibile → close, meno costi roundtrip) il numero è **negativo, −12,88 $**: l'ingresso simulato avrebbe perso denaro, gran parte del movimento era già nel gap d'apertura prima del primo ciclo eleggibile (17:37 UTC). Registro il lordo per continuità con la serie F-001, il numero onesto di oggi è che il miss NO_NEWS non sarebbe stato profittevole comunque.
- **Alternativa scartata**: il miglioramento di `watchlist_zero_news` (31, minimo della finestra) potrebbe suggerire che F-001 si sta risolvendo strutturalmente. Scartata: la cecità lato uscita (3 posizioni, nozionale 2.033,70 $) è peggiore del 09-11 (2 posizioni, ASML+SBUX, nozionale 1.291,08 $) — copertura raw sulla watchlist e copertura utile sulle posizioni già aperte si muovono in direzioni opposte oggi, quindi non è la stessa metrica che migliora.

## 9. Appendice

### 9a. Rendimenti completi della watchlist (`mercato.rendimenti`, ordinati dal più alto al più basso)

| Ticker | Return% |
|---|---:|
| QCOM | +4.25% |
| PBR | +2.93% |
| CVX | +2.64% |
| SHEL | +2.59% |
| XOM | +2.57% |
| BP | +2.24% |
| AMD | +2.19% |
| XLE | +2.17% |
| NOK | +1.97% |
| DELL | +1.73% |
| MMM | +1.64% |
| MRVL | +1.32% |
| ARM | +1.18% |
| WFC | +1.14% |
| ASML | +1.04% |
| T | +0.79% |
| META | +0.70% |
| JPM | +0.67% |
| NVDA | +0.57% |
| ABBV | +0.49% |
| MU | +0.39% |
| PG | +0.37% |
| SOXX | +0.36% |
| BRK.B | +0.35% |
| JNJ | +0.33% |
| VZ | +0.31% |
| PANW | +0.31% |
| BABA | +0.10% |
| V | +0.09% |
| BAC | +0.08% |
| CSCO | +0.01% |
| TXN | +0.00% |
| C | -0.01% |
| INTC | -0.05% |
| XLV | -0.05% |
| CAT | -0.06% |
| ERIC | -0.10% |
| MS | -0.15% |
| MRK | -0.15% |
| LLY | -0.19% |
| MA | -0.20% |
| BA | -0.28% |
| IBM | -0.29% |
| XLK | -0.29% |
| XLF | -0.32% |
| NOW | -0.32% |
| RIO | -0.39% |
| PLTR | -0.43% |
| SPY | -0.46% |
| AAPL | -0.52% |
| ROKU | -0.53% |
| PFE | -0.61% |
| JD | -0.62% |
| QQQ | -0.65% |
| TSLA | -0.67% |
| IWM | -0.70% |
| AMAT | -0.72% |
| WMT | -0.91% |
| VALE | -0.96% |
| TSM | -1.02% |
| AXP | -1.02% |
| TM | -1.06% |
| AZN | -1.18% |
| GS | -1.19% |
| SAP | -1.20% |
| GOOGL | -1.26% |
| TMUS | -1.33% |
| CRM | -1.46% |
| AVGO | -1.58% |
| MSFT | -1.64% |
| BIDU | -1.64% |
| RDDT | -1.69% |
| DB | -1.73% |
| HD | -1.73% |
| MCD | -1.83% |
| CMCSA | -1.85% |
| COST | -1.91% |
| UNH | -1.99% |
| DIS | -2.00% |
| AMZN | -2.02% |
| GM | -2.05% |
| NVO | -2.12% |
| NKE | -2.24% |
| SONY | -2.25% |
| INFY | -2.41% |
| SBUX | -2.51% |
| F | -2.60% |
| SNOW | -2.82% |
| UBS | -2.83% |
| ADBE | -2.95% |
| NFLX | -3.01% |
| ORCL | -3.07% |
| SPCX | -3.15% |
| GE | -3.31% |
| HOOD | -3.39% |
| WDC | -3.51% |

### 9b. Checklist finding aperti toccati dalla giornata

| Finding | Esito | Dato decisivo |
|---|---|---|
| F-001 | **supported** | vedi §8 — nuova occorrenza registrata |
| F-009 (gate scarta segnali col segno corretto sotto soglia) | not_exposed | nessun candidato oggi ha segno corretto E sotto gate: QCOM (fanout, segno opposto), ORCL/HOOD/SPCX (own score, tutti segno opposto al prezzo) |
| F-012 (metà righe scorate da fan-out) | supported (parziale) | `copertura_articoli.totali.mapping_fanout_extra`=73 su 211 righe `news_log` = 34,6% — sostanziale ma sotto metà oggi |
| F-040 (vincolo long-only blocca segnali ribassisti corretti sopra gate) | not_exposed | nessun candidato ribassista oggi ha superato il gate (`funnel_v2.conteggi_pipeline` non ha righe oltre NO_RELEVANT_NEWS) |
| F-063 (calendario earnings indisponibile) | contradicted (oggi) | `calendario_earnings.status`="OBSERVED", `streak_sedute_consecutive_unknown`=0 — entrambe le fonti hanno risposto |
| F-067 (headline ticker-specifiche mai promosse a ISSUER_SPECIFIC) | contradicted (oggi) | HOOD, SPCX e ORCL hanno tutti almeno un articolo promosso correttamente a `relevance`="ISSUER_SPECIFIC"/`subject_ticker` confermato; solo l'articolo macro di QCOM (genuinamente non ticker-specifico) resta TAG_UNCONFIRMED |

### 9c. Casi di successo

Nessuno fra i mover ≥3% (0 catturati oggi). Fuori dai mover, PLTR è stata aperta e chiusa nella stessa seduta con P&L netto positivo (+15,41 $, `hold_minimum_expiry`) — non è un mover (return −0,43%) e non qualifica come "mover catturato", citato solo per completezza sull'attività del book.

---

*Report generato in sessione autonoma di Quant Research Analyst. Nessuna modifica a codice, nessun ordine, nessun commit. Periodo di sola osservazione (`docs/evidence/OBSERVATION_CHARTER.md`) — nessuna taratura proposta.*
