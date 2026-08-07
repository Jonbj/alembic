# Alpha Miss Report — 2026-08-05

Analista: sessione autonoma Quant Research. Perimetro: **solo** i 96 simboli di
`config/trading.yaml → symbols.watchlist`. Periodo di sola osservazione (carta del 2026-08-01,
giorno 3 di 40): nessuna proposta di taratura, solo registrazione di evidenza.

Fonti: **dossier deterministico** `docs/evidence/dossier/2026-08-05.json` (rendimenti, dispersione,
copertura news, candidati miss, ingressi/chiusure, aggregati — Alpaca SIP `adjustment=all`),
`alembic-postgres-1`, `docker compose logs worker`, Alpaca `TradingClient` per l'equity.
Ogni rendimento citato viene dal dossier. Le decomposizioni gap/intraday e le classificazioni
delle cause sono aggiunte di questa sessione.

---

## 1. Executive summary

Giornata di **rotazione, non di direzione**: SPY −0.20%, QQQ −0.90%, dispersione cross-sectional
σ = 2.28% (contro 4.40% il 08-04). **11 mover ≥ 3%** su 96, 4 al rialzo e 7 al ribasso.
**7 catturati, 4 mancati.** Cause dei miss: NO_NEWS 2 (AZN, QCOM), THIN_NEUTRAL 1 (NVDA),
WRONG_SIGN 1 (SPCX); nessun FILTERED. **51 dei 96 simboli (53%) senza alcuna riga in `news_log`.**
Il tema è l'inverso esatto del 08-04: fuori da semiconduttori/AI-speculativo (AMD −7.04%,
WDC −5.36%, MRVL −3.46%, QCOM −3.16%, SPCX −13.61%, SOXX −2.12%), dentro pharma/healthcare
(LLY +4.86%, AZN +3.78%, XLV +1.27%). Il book, costruito long sui semi a metà luglio, è dalla
parte sbagliata: **MTM del book aperto −197,12 $** contro **+65,51 $ realizzati** (S1 +41,71,
S4 +23,80); equity di chiusura **110.239,74 $**, −126,49 $ sul 08-04. Il fatto più costoso della
giornata non è un miss ma un **catturato gestito male**: DIS, comprato alle 14:22 sull'unico
articolo ticker-specifico del giorno ("Disney Earnings Beat Views", segnale +0.5722) e venduto
alle 16:07 a −18,76 $ perché un pezzo macro generico ("Baystreet.ca — Futures Muscle Higher
Midweek", attribuito a DIS via `org_lookup`) aveva azzerato il segnale; DIS chiude +3.65% e tenere
fino alla chiusura valeva +14,70 $ — **33,46 $ di costo attribuito**. In più **4 rientri
same-day** (BP due volte, PLTR, SNOW) per 8,38 $ di penalità di churn.

---

## 2. Rendimenti completi della watchlist (2026-08-05)

Barre disponibili per **tutti i 96 simboli**, nessun buco dati (`simboli_senza_dati: []` nel
dossier). "Catturato" = simbolo in portafoglio quel giorno (posizione aperta, anche legacy) o
tradato quel giorno. In grassetto i mover ≥ 3%.

| # | Simbolo | Return % | Catturato |
|---:|---|---:|---|
| 1 | LLY | **+4.86** | sì (in book S1) |
| 2 | AZN | **+3.78** | **no** |
| 3 | DIS | **+3.65** | sì (tradato S4) |
| 4 | NVDA | **+3.43** | **no** |
| 5 | RIO | +2.52 | sì (in book S1) |
| 6 | NKE | +2.22 | **no** |
| 7 | MCD | +2.11 | sì (in book S4) |
| 8 | PFE | +1.57 | sì (in book S4) |
| 9 | DB | +1.52 | **no** |
| 10 | HD | +1.41 | **no** |
| 11 | BA | +1.28 | **no** |
| 12 | UNH | +1.28 | sì (in book S1) |
| 13 | XLV | +1.27 | sì (in book S1) |
| 14 | GE | +1.04 | sì (in book S1) |
| 15 | JNJ | +1.04 | sì (in book S1) |
| 16 | CRM | +1.04 | **no** |
| 17 | ABBV | +0.98 | sì (in book S1) |
| 18 | SBUX | +0.98 | sì (tradato S1) |
| 19 | GM | +0.96 | sì (in book S1) |
| 20 | SAP | +0.94 | **no** |
| 21 | WFC | +0.88 | **no** |
| 22 | NFLX | +0.86 | **no** |
| 23 | VALE | +0.74 | sì (in book S1) |
| 24 | ADBE | +0.71 | **no** |
| 25 | WMT | +0.71 | **no** |
| 26 | GS | +0.70 | sì (in book S1) |
| 27 | AXP | +0.66 | **no** |
| 28 | MS | +0.57 | sì (in book S1) |
| 29 | NVO | +0.56 | sì (in book S4) |
| 30 | C | +0.56 | sì (in book S1) |
| 31 | BAC | +0.56 | sì (in book S1) |
| 32 | AAPL | +0.52 | sì (in book S1) |
| 33 | JPM | +0.48 | sì (in book S1) |
| 34 | SONY | +0.40 | **no** |
| 35 | MMM | +0.35 | sì (in book S1) |
| 36 | IBM | +0.33 | **no** |
| 37 | BRK.B | +0.32 | sì (tradato S1) |
| 38 | MRK | +0.26 | sì (in book S1) |
| 39 | XLF | +0.21 | sì (in book S1) |
| 40 | UBS | +0.21 | sì (in book S1) |
| 41 | INTC | +0.20 | sì (in book S1) |
| 42 | META | +0.14 | **no** |
| 43 | MU | +0.06 | sì (in book S1) |
| 44 | AVGO | +0.03 | **no** |
| 45 | SNOW | +0.02 | sì (tradato S1) |
| 46 | MA | −0.11 | **no** |
| 47 | CSCO | −0.20 | sì (in book S1) |
| 48 | SPY | −0.20 | sì (in book S1) |
| 49 | ROKU | −0.25 | sì (in book S1) |
| 50 | V | −0.28 | **no** |
| 51 | BABA | −0.36 | **no** |
| 52 | XLK | −0.53 | sì (in book S1) |
| 53 | COST | −0.62 | **no** |
| 54 | CAT | −0.62 | sì (in book S1) |
| 55 | IWM | −0.64 | sì (in book S1) |
| 56 | CMCSA | −0.72 | **no** |
| 57 | HOOD | −0.76 | **no** |
| 58 | TSM | −0.76 | sì (in book S1) |
| 59 | F | −0.77 | **no** |
| 60 | NOW | −0.78 | **no** |
| 61 | PG | −0.82 | **no** |
| 62 | VZ | −0.87 | **no** |
| 63 | QQQ | −0.90 | sì (in book S1) |
| 64 | ORCL | −0.93 | **no** |
| 65 | INFY | −0.95 | **no** |
| 66 | DELL | −0.98 | sì (in book S1) |
| 67 | PANW | −1.00 | sì (in book S1) |
| 68 | MSFT | −1.09 | **no** |
| 69 | JD | −1.30 | **no** |
| 70 | BIDU | −1.31 | **no** |
| 71 | T | −1.37 | **no** |
| 72 | XOM | −1.51 | sì (in book S1) |
| 73 | AMZN | −1.72 | **no** |
| 74 | TM | −1.73 | **no** |
| 75 | TSLA | −1.77 | **no** |
| 76 | PBR | −1.92 | sì (in book S1) |
| 77 | ASML | −1.97 | sì (in book S1) |
| 78 | ERIC | −2.04 | **no** |
| 79 | XLE | −2.07 | sì (in book S1) |
| 80 | TXN | −2.08 | sì (in book S1) |
| 81 | CVX | −2.10 | sì (in book S1) |
| 82 | TMUS | −2.12 | **no** |
| 83 | SOXX | −2.12 | sì (in book S1) |
| 84 | ARM | −2.13 | sì (in book S1) |
| 85 | AMAT | −2.26 | sì (in book S1) |
| 86 | SHEL | −2.32 | sì (in book S1) |
| 87 | PLTR | −2.60 | sì (tradato S4) |
| 88 | BP | −2.90 | sì (tradato S1) |
| 89 | RDDT | −2.94 | **no** |
| 90 | QCOM | **−3.16** | **no** |
| 91 | NOK | **−3.43** | sì (in book S1) |
| 92 | MRVL | **−3.46** | sì (in book S1) |
| 93 | GOOGL | **−4.03** | sì (in book S1) |
| 94 | WDC | **−5.36** | sì (in book S4) |
| 95 | AMD | **−7.04** | sì (in book S1) |
| 96 | SPCX | **−13.61** | **no** |

**Soglia mover.** Confermo la soglia |return| ≥ 3% del dossier (`soglia_mover: 0.03`), invariata
dai report precedenti. Con σ = 2.28% corrisponde a ~1.3 deviazioni standard cross-sectional: è
selettiva quanto basta (11 nomi su 96) e mantiene la serie comparabile con le giornate precedenti.

---

## 3. Miss classificati

Quattro mover su undici non erano in portafoglio: sono i `candidati_miss` del dossier.

| Simbolo | Return % | (gap / intraday) | Categoria | Evidenza |
|---|---:|---|---|---|
| SPCX | −13.61 | −10.34 / −3.65 | **WRONG_SIGN** | 4 articoli in `news_log`. Il primo segnale del giorno, id 6496 alle 14:30, è **+0.1078** (conf 0.279, `finbert`, `fallback_used=true`) su "SpaceX Latest Pentagon Deal Is Bigger Than Half a Year of Rocket Revenue": segno **opposto** al −13.61% della giornata, e generato dopo che il titolo aveva già aperto a −10.34%. Il segno corretto arriva solo alle 17:30 (id 6605, −0.1706, ensemble non-fallback) su "SpaceX's Biggest Growth Story Comes with a Concentration Risk", cioè a crollo quasi consumato. Nessun ordine: 0.1078 < gate 0.300 **e** il filtro #108 scarta i segnali `fallback_used=true` dal ranking BUY. Due guard indipendenti hanno impedito un acquisto sbagliato — il miss è una non-perdita, non un'occasione persa: le strategie sono long-only e su un −13.61% non c'era alpha catturabile. |
| GOOGL* | −4.03 | +1.51 / −5.45 | *(in book, non un miss)* | Riportato qui solo perché è l'unico caso in cui una notizia ticker-specifica e direzionalmente corretta è arrivata: "Alphabet Stock Dives as Key AI Leadership Exits" (id 6648, pubblicata 16:50, ingerita 18:45), segnale −0.1250. Con 2 soli articoli sul mover #4 della giornata. |
| AZN | +3.78 | +5.25 / −1.40 | **NO_NEWS** | Zero righe in `news_log`, zero in `sentiment_signals`, zero in `execution_decisions`: nessuna catena decisionale esiste. È il secondo mover al rialzo della giornata e il secondo farmaceutico dopo LLY — su cui invece abbiamo 17 articoli. **Caveat che indebolisce il costo:** il movimento è interamente nel gap (+5.25%), e l'intraday è **negativo** (−1.40%); nessuna strategia intraday avrebbe catturato questo return, e un ingresso all'apertura avrebbe perso. |
| NVDA | +3.43 | +2.32 / +1.09 | **THIN_NEUTRAL** | 6 articoli, **nessuno ticker-specifico**: "QQQ Pulls In Nearly $5 Billion in a Day", "Michael Burry Pegs Palantir, Nvidia as 'Future Ghost Towns'", "AMD Stock Hit By Musk's Nvidia Bet", "What Is Going on with Taiwan Semiconductor Stock", "SpaceX Lockup Expiry Could Send a Gentle Jolt Through QQQ", "SpaceX Chooses Nvidia". Massimo segnale **+0.1543** (conf 0.550, ensemble non-fallback, id 6592, 17:15) — segno corretto, sotto il gate 0.300. `SKIP_THRESHOLD` id 6838 (0.154), 6905 (0.100), 6993 (0.000). Il catalizzatore vero della giornata *era* nei nostri dati ("SpaceX Chooses Nvidia", id 6660) ma è arrivato alle 19:00 e lo stesso articolo è taggato in fan-out anche a GOOGL, SPCX, DIS e LLY. |
| QCOM | −3.16 | −0.84 / −2.34 | **NO_NEWS** | Zero righe in `news_log`, zero segnali, zero decisioni. **Secondo giorno consecutivo di NO_NEWS su QCOM** (il 08-04 era +7.32%, anch'esso NO_NEWS). Strategie long-only: su un −3.16% non c'era alpha catturabile, quindi il costo è nullo per costruzione — ma il buco di copertura è lo stesso di ieri. |

**Conteggi:** NO_NEWS 2 · THIN_NEUTRAL 1 · WRONG_SIGN 1 · FILTERED 0 · OUT_OF_STRATEGY_SCOPE 0.

Nota su OUT_OF_STRATEGY_SCOPE: gli ETF in watchlist (SPY, QQQ, IWM, XLF, XLK, XLE, XLV, SOXX) sono
tutti in book come posizioni S1 e nessuno di essi è fra i mover della giornata; la categoria resta
a zero. Nota su FILTERED: nessun mover non-in-book ha prodotto un segnale sopra gate poi scartato
a valle — il gate di freschezza e il filtro fallback hanno agito, ma su segnali che erano comunque
sotto soglia.

---

## 4. Titoli catturati: esito

Sette degli undici mover erano in portafoglio. Solo uno è stato tradato quel giorno.

| Simbolo | Return % | Come | Esito |
|---|---:|---|---|
| **DIS** | +3.65 | **tradato S4** | BUY 14:22 @ 100,87 (16,516 az., dec. 6599, `sentiment +0.687`) → SELL 16:07 @ 99,79 (dec. 6747, `exit_mechanism=whipsaw`), **net −18,76 $**. `entry_percentile` 0.336 (ingresso nel terzo basso del range del giorno: buono). DIS chiude a 101,76: `mtm_eod` del dossier **+14,70 $**, `drift_post_uscita` **+32,54 $**. Uscita 1h45m dopo l'ingresso su un titolo che ha chiuso sopra il prezzo d'entrata. |
| **LLY** | +4.86 | in book S1 (dal 07-15) | Posizione 0,690 az. da 1.138,37 → MTM del giorno **+37,38 $**. **S4 non ha potuto aggiungere**: 8 segnali ensemble fra +0.45 e **+0.747** (il più forte della giornata, id 6616 alle 17:45 su "Eli Lilly's Weight-Loss Empire Keeps Expanding") e il guard P0-05 no-pyramiding ha bloccato il BUY a ogni ciclo (log worker 14:07, 14:22, 14:37, 14:52, …: "P0-05: skipping BUY decision for LLY — already has an open trade"). Il segnale corretto c'era, l'ordine no. |
| **AMD** | −7.04 | in book S1 (dal 07-14) | 0,814 az. → MTM **−29,72 $**. 11 articoli, segnali oscillanti fra −0.270 e +0.257 nella stessa giornata (11 righe in `sentiment_signals`): nessuna lettura stabile. Nessuna uscita: S1 esce per perdita di rango momentum, non su sentiment. |
| **WDC** | −5.36 | in book S4 (dal 07-21) | 2,981 az. → MTM **−87,61 $**, la singola perdita mark-to-market più grande della giornata. **Zero articoli, zero segnali**: S4 detiene la posizione senza alcuna copertura informativa corrente. |
| **GOOGL** | −4.03 | in book S1 (dal 07-10) | 1,922 az. → MTM **−29,26 $**. Unico caso con notizia ticker-specifica corretta (uscita del capo AI), segnale −0.1250 alle 18:45, sotto qualunque soglia d'uscita S4 e comunque irrilevante per S1. |
| **MRVL** | −3.46 | in book S1 (dal 07-14) | 1,552 az. → MTM **−11,75 $**. Zero articoli. |
| **NOK** | −3.43 | in book S1 (dal 07-14) | 41,564 az. → MTM **−14,13 $**. Zero articoli. |

**Book della giornata.** Chiusure: 11 trade, realizzato **+65,51 $** (S1 +41,71 su 5 uscite,
S4 +23,80 su 6). Le uscite migliori sono le posizioni tenute overnight (BP +48,19 dopo 625 ore,
NVO +37,52, MCD +36,14, SBUX +19,28); tutte e cinque le uscite in perdita sono trade
aperti e chiusi **lo stesso giorno** (DIS −18,76, PLTR −18,97 e −12,84, BP −13,50 e −5,00,
SNOW −7,26). Ingressi: 8, `entry_percentile` mediano 0.42 (mediana mobile a 20 giorni del dossier:
0.526). MTM del book aperto **−197,12 $** su 49 posizioni. Equity Alpaca a fine giornata
**110.239,74 $**, contro 110.366,23 $ del 08-04: **−126,49 $**.

**Cicli.** 24 cicli `portfolio_cycles` fra le 14:07 e le 19:52 UTC, **nessun gap > 16 minuti**:
la cadenza a 15 minuti ha retto per tutta la sessione.

---

## 5. Pattern osservato

**Rotazione settoriale netta, e l'inverso esatto del 08-04.** SPY −0.20% e QQQ −0.90% nascondono
una dispersione di 2.28%: non è stata una giornata direzionale, è stato uno spostamento di denaro
fra settori.

*Fuori* — semiconduttori e hardware AI: AMD −7.04%, WDC −5.36%, MRVL −3.46%, QCOM −3.16%,
SOXX −2.12%, AMAT −2.26%, ARM −2.13%, TXN −2.08%, ASML −1.97%, XLK −0.53%. Insieme al complesso
speculativo AI/retail: SPCX −13.61%, RDDT −2.94%, PLTR −2.60%. Il 08-04 questi stessi nomi erano
il rally (SOXX +6.73%, XLK +4.92%, PLTR +29.17%, ARM +17.43%): il movimento si è ritirato in un
giorno.

*Dentro* — pharma e healthcare: LLY +4.86%, AZN +3.78%, PFE +1.57%, UNH +1.28%, XLV +1.27%,
JNJ +1.04%, ABBV +0.98%, MRK +0.26%. Ed è a sua volta l'inverso del 08-03, quando pharma e
difensivi erano il lato in uscita della rotazione (AZN, LLY, ABBV, MRK fra i peggiori).

*Anche fuori* — energia: BP −2.90%, SHEL −2.32%, CVX −2.10%, XLE −2.07%, XOM −1.51%.

*Fermi* — finanziari, tutti in banda ±1%: JPM +0.48%, BAC +0.56%, GS +0.70%, MS +0.57%,
WFC +0.88%, C +0.56%, XLF +0.21%.

**Eccezione dentro il tema:** NVDA +3.43% è l'unico semiconduttore in positivo, e la causa è
idiosincratica e presente nei nostri dati — "SpaceX Chooses Nvidia" (id 6660). È anche uno dei
quattro miss.

**Conseguenza sul book.** Il portafoglio è strutturalmente lungo il tema in uscita: delle 49
posizioni aperte, il blocco semi/hardware costruito da S1 a metà luglio (AMD, MRVL, NOK, AMAT,
ARM, ASML, TXN, TSM, MU, INTC, DELL, SOXX, XLK, PANW, CSCO) più WDC di S4. Il risultato è un MTM
di −197,12 $ in una giornata in cui SPY ha perso solo lo 0.20%: **il book ha una esposizione
tematica concentrata che non deriva da una scelta di sentiment ma dal ranking momentum di S1
congelato a metà luglio.** Nelle ultime tre sedute questa esposizione ha prodotto +819 $ (08-04),
−7 $ (08-03) e −197 $ (08-05): la varianza è il tema, non il segnale.

---

## 6. Ricorrenze rispetto ai giorni precedenti

Confronto con `market_daily.jsonl` (07-31, 08-03, 08-04) e i report corrispondenti.

- **Copertura news stabilmente bassa e in peggioramento oggi**: 55/96 (07-31), 41/96 (08-03),
  42/96 (08-04), **51/96 (53%) oggi**. Quarta giornata su quattro sopra il 40%.
- **QCOM è NO_NEWS per il secondo giorno consecutivo** (08-04 +7.32%, 08-05 −3.16%). Su un mover
  ≥3% in entrambe le direzioni, zero righe in `news_log` in entrambe.
- **SPCX per il terzo giorno di fila non produce un ordine**, ogni volta per una causa diversa:
  WRONG_SIGN il 08-03, FILTERED il 08-04 (gate di freschezza), WRONG_SIGN oggi. È il simbolo più
  volatile della watchlist (+10.06% il 08-04, −13.61% oggi) e la pipeline non ne ha mai una lettura
  utilizzabile in tempo.
- **La latenza di ingestione non migliora**: mediana 100,2 min per `alpaca_benzinga` (n=77) e
  90,8 min per `gdelt_gkg` (n=117), contro una finestra `MAX_NEWS_AGE_HOURS` di 120 min — 83% e 76%
  già consumati alla nascita del segnale. Il log riporta "S4: dropped 30 signal(s) below
  entry-freshness" su tutti i 24 cicli. Serie: 07-31 ~91/102 min, 08-03 ~80/74, 08-04 ~102/97,
  08-05 ~100/91.
- **Il fan-out multi-ticker resta la metà dell'evidenza**: 32 articoli su 124 (26%) sono taggati a
  2+ ticker e generano 102 delle 194 righe scorate (53%), con un massimo di 13 ticker su un singolo
  articolo. Serie: 51% (08-03), 66% (08-04), 53% oggi.
- **Il pattern "articolo generico che cancella il segnale ticker-specifico" si ripete per la terza
  giornata consecutiva** (ORCL il 08-03, ARM e CAT il 08-04, DIS e LLY oggi) — ma oggi, a
  differenza del 08-04, **ha effettivamente cambiato un ordine**: la SELL di DIS.
- **Novità rispetto ai giorni precedenti**: il churn same-day passa da 2 roundtrip (08-03) e 3
  (08-04) a **4 oggi**, e per la prima volta uno stesso simbolo viene venduto e ricomprato **due
  volte nella stessa sessione** (BP: SELL 15:52 → BUY 16:07 → SELL 17:52 → BUY 18:07 → SELL 19:52).

---

## 7. Segnalazioni

Nessuna proposta di taratura né di fix: il periodo di osservazione è in corso (giorno 3 di 40).
Ogni voce è agganciata al ledger `docs/evidence/findings.json`.

**[F-008] Sembra un difetto, non un limite noto** — un articolo macro generico multi-ticker ha
invertito un segnale ticker-specifico e forzato l'uscita anticipata dall'unico mover tradato del
giorno. Catena completa: `news_log` 6491 "Dow Jumps 500 Points; Disney Earnings Beat Views"
(`source_metadata`, ticker-specifico) → `sentiment_signals` 6491 alle 14:15:09, **+0.5722**
conf 0.775, ensemble non-fallback → `execution_decisions` 6599 alle 14:22 BUY, trade 654, 16,516 az.
a 100,87. Poi tre articoli generici attribuiti a DIS via `org_lookup` — 6516 "S&P 500, Dow futures
edge higher on Mideast hopes" (+0.0125), 6538 "The S&P 500 just hit a new high. 'Big Short'
investor Michael Burry…" (−0.1200), **6543 "Baystreet.ca — Futures Muscle Higher Midweek"
(0.0000, conf 0.175)** — e alle 16:07 la decisione 6747 vende: reason `[whipsaw] … score=+0.000,
age=0.1h, generated 2026-08-05 16:00 UTC`. Nessuno dei tre parla di Disney. DIS chiude a 101,76:
**realizzato −18,76 $ contro +14,70 $ tenendo fino alla chiusura** (`mtm_eod` del dossier) =
**33,46 $ di costo attribuito**, controfattuale corto (stesso giorno, stessa size, stesso
strumento). Nota: la stessa decisione porta `anti_whipsaw_shadow: would_suppress=True, streak=1/2`
— il guard che l'avrebbe soppressa esiste ed è in shadow per design.

**[F-013] Limite noto, ma con severità nuova** — churn intraday: **4 rientri same-day**, per la
prima volta due sullo stesso simbolo. BP: SELL 15:52 @ 41,64 → BUY 16:07 @ 41,7617 → SELL 17:52
@ 41,63 → BUY 18:07 @ 41,74 → SELL 19:52 @ 41,24 (trade 285, 657, 658). PLTR: SELL 14:22 @ 160,27
→ BUY 15:37 @ 159,87 → SELL 19:52 @ 158,72 (trade 652, 656). SNOW: BUY 14:22 → SELL 16:07 @ 317,83
→ BUY 19:07 @ 319,014 (trade 653, 660). Costo con il metodo delle occorrenze precedenti (sola
penalità di rientro a prezzi di fill reali + costi di transazione del rientro): BP¹
22,994 × (41,7617−41,64) = 2,80 + 1,97 di costi; BP² 23,061 × (41,74−41,63) = 2,54 + 1,97;
PLTR 10,369 × (159,87−160,27) = **−4,15** (rientro favorevole) + 0,92; SNOW 1,728 ×
(319,014−317,83) = 2,05 + 0,28. **Totale 8,38 $.** Non include il costo d'uscita anticipata di DIS,
già contato in F-008: nessun doppio conteggio. Meccanismo invariato — S1 ricalcola il ranking
momentum ogni 15 min, S4 non ha banda fra gate d'ingresso 0.30 e uscita 0.

**[F-023] Sembra un difetto** — S4 usa il segnale più recente per simbolo, e oggi il caso è
sull'evento più informativo della giornata. LLY: `sentiment_signals` 6563 alle **16:30:46**
score **+0.618** ("Lilly Reports Strong Q2 2026 Results, Raises Full-Year Guidance") viene
sostituito da 6578 alle **16:46:27** score **+0.013** ("CVS Targets Affordable GLP-1 Access With
New Eli Lilly Deal"), e la decisione delle 16:52 (id 6794) porta `score 0.013 < feedback threshold
0.300`. Stesso schema alle 17:45: 6616 **+0.747** alle 17:45:31 seguito 11 secondi dopo da 6618
**+0.450**. In tutta la giornata LLY produce 8 segnali ≥ +0.45 e **ogni riga `execution_decisions`
del giorno porta 0.051, 0.013 o 0.000**. **COSTO 0.0 (non null): il controfattuale è stato
calcolato ed è nullo** — LLY era già in book come posizione S1 dal 07-15 e il guard P0-05 ha
bloccato esplicitamente il BUY a ogni ciclo (log worker 14:07:12, 14:22:09, 14:37:10, 14:52:07,
…). Il difetto di selezione è reale e documentato, ma oggi non ha impedito alcun ordine.

**[F-001] Osservazione strutturale, ricorrente** — 51 dei 96 simboli (53%) senza alcuna riga in
`news_log`. Due dei quattro miss del giorno sono NO_NEWS puri: AZN +3.78% e QCOM −3.16%, entrambi
con zero righe in `news_log`, `sentiment_signals` ed `execution_decisions`. **Costo stimato
prudenzialmente 0,00 $ e non 83,16 $**: con la size S4 tipica di 2.200 $, AZN varrebbe 83,16 $ sul
return pieno, ma il suo movimento è interamente nel gap (+5.25%) e l'intraday è **negativo**
(−1.40%) — un ingresso all'apertura avrebbe perso denaro; QCOM è un mover al ribasso e le strategie
sono long-only. Registro quindi la ricorrenza del buco di copertura con costo nullo verificato,
non stimato per difetto. QCOM è NO_NEWS per il secondo giorno consecutivo.

**[F-009] Osservazione, ricorrente** — il gate d'ingresso S4 (0.30) scarta un segnale del segno
corretto sul mover NVDA +3.43%: massimo +0.1543 (conf 0.550, ensemble non-fallback, id 6592),
`SKIP_THRESHOLD` id 6838/6905/6993. Costo stimato con size S4 tipica 2.200 $: **75,46 $** sul
return pieno, **23,98 $** sulla sola porzione intraday (il gap vale +2.32pp dei +3.43pp). Uso il
return pieno per comparabilità di serie, come nelle occorrenze precedenti. **Caveat che indebolisce
l'attribuzione, identico a quello di AVGO il 08-04:** nessuno dei 6 articoli su NVDA è
ticker-specifico — la magnitudine bassa può essere la conseguenza *corretta* della genericità
delle fonti e non una mis-calibrazione del gate. Il legame vero è con F-012.

**[F-012] Osservazione strutturale, ricorrente** — 32 articoli su 124 (26%) taggati a 2+ ticker
generano 102 delle 194 righe scorate (**53%**), con un massimo di 13 ticker su un singolo articolo.
Serie: 51% (08-03), 66% (08-04), 53% oggi. Oggi tocca il money path due volte: (a) la SELL di DIS
nasce da "Baystreet.ca — Futures Muscle Higher Midweek", (b) il singolo articolo "SpaceX Chooses
Nvidia; Short Squeeze Drives Market Rally" (pubblicato 17:17) genera segnali su **GOOGL, NVDA,
SPCX, DIS e LLY** — cinque ticker, un articolo, e per NVDA è l'unico pezzo che tocchi il vero
catalizzatore della giornata. Costo non stimabile.

**[F-019] Osservazione, ricorrente** — la latenza di ingestione consuma la finestra di
entry-freshness: mediana 100,2 min per `alpaca_benzinga` (n=77, max 120,1) e 90,8 min per
`gdelt_gkg` (n=117, max 106,4) contro `MAX_NEWS_AGE_HOURS`=120 min, cioè 83% e 76% consumati
all'arrivo; 1 articolo su 77 è già scaduto quando viene scorato. Gate attivo su tutti i 24 cicli
("S4: dropped 30-31 signal(s) below entry-freshness"). Sui 13 articoli LLY tracciati riga per
riga la latenza va da 76 a 107 minuti. Costo non stimabile oggi: nessun segnale sopra gate su
simbolo non-detenuto è stato scartato per sola freschezza.

**[F-020] Sembra un difetto, ricorrente e in peggioramento** — `org_lookup` continua ad attribuire
ai ticker bancari articoli su società completamente estranee, e oggi è il primo produttore di
righe della giornata. **MS ha 33 articoli**, il ticker più coperto della watchlist, e sono su
SunocoCorp, Sysco, SBA Communications, Macerich, Pinterest, AMETEK, Mettler-Toledo, Mitsubishi UBE
Cement, Shopify, Best Buy, oltre a due "ISM - MSBV - ISSUER CALL - XS2877627559" che sono avvisi
societari su un ISIN. Con GS (13) e DB (5) fanno **51 righe su 194 (26%) della copertura giornaliera
su tre ticker bancari, tutte via `org_lookup`**, che generano 51 righe in `sentiment_signals`
(range −0.180…+0.150). Costo non stimabile: nessuna di queste righe ha superato il gate oggi. Ma
gonfia la copertura news apparente — i 46 ticker con news diventano 43 se si escludono MS/GS/DB.

**[F-011] Osservazione, ricorrente, con un caso concreto nuovo** — la catena
segnale→decisione→trade resta non ricostruibile: **487 righe su 488** di `execution_decisions` del
giorno hanno `signal_id` NULL. Caso concreto: la decisione BUY 6599 su DIS porta
`signal_score = 0.6866898466006927` e reason "sentiment +0.687", ma **nessuna riga di
`sentiment_signals` per DIS quel giorno ha quel valore** — il massimo è +0.5722 (id 6491, 14:15:09),
e una query su `round(score,3)=0.687` per DIS restituisce zero righe su tutta la storia. Non posso
stabilire se sia una trasformazione applicata a valle dal ranking o un vero disallineamento score,
proprio perché `signal_id` è NULL. Costo non stimabile: è un difetto di osservabilità, e rende
non verificabile l'attribuzione di ogni ordine.

---

## Nota di conformità

Report prodotto in sola lettura. Nessuna modifica a codice, configurazione o stato di runtime;
nessun ordine; nessun worker avviato. Gate, soglie e parametri citati (0.300,
`MAX_NEWS_AGE_HOURS`=2.0, `s4_anti_whipsaw_confirm_cycles`, banda d'uscita) sono **taratura** e
restano congelati dalla carta di osservazione: quanto sopra è registrazione di evidenza, non una
proposta di modifica. Le uniche scritture di questa sessione sono questo file e le due appendici
di ledger (`market_daily.jsonl`, `findings.json`).
