# Alpha Miss Report — 2026-09-01

**Universo:** 96 simboli di `config/trading.yaml → symbols.watchlist`.
**Fonte prezzi:** dossier deterministico `docs/evidence/dossier/2026-09-01.json` (Alpaca SIP, `adjustment=all`), generato il 2026-09-02T08:00:18Z. Ogni numero di mercato, copertura, ingresso, uscita e guardia citato qui viene dal dossier; la classificazione delle cause e la lettura degli articoli sono mie.
**Soglia mover:** `|return| ≥ 3%` (`soglia_mover` del dossier). Scelta non arbitraria: con σ cross-sectional a 1,85% oggi, 3% è ≈1,6σ — abbastanza da isolare un movimento idiosincratico dal rumore di giornata senza ridurre il campione a due nomi.
**Regime di scoring:** la Variante A del prompt sentiment (#399/#408) è stata deployata `bf5bef2e` il **2026-09-01T10:33Z**. Questa è la **prima seduta** con il nuovo regime: gli score di oggi non sono confrontabili con quelli di agosto senza segmentare.

---

## 1. Executive summary

Giornata di rotazione violenta fuori dal software dentro l'energia, con 11 mover ≥3% di cui **9 al ribasso**. Alembic ha catturato **entrambi** i mover rialzisti: PBR +5,06% (detenuto da luglio) e BP +3,73% (ingresso S1 alle 14:07, +11,19 $ MTM a fine giornata). Sul lato entrata è la giornata migliore possibile con questa costruzione.

I **5 miss** classificati dal dossier — ORCL −5,23%, SAP −4,01%, PLTR −3,47%, NOW −3,44%, TSLA −3,22% — sono **tutti ribassisti e tutti non detenuti**: il libro è long-only e non shorta, quindi `opportunity_v2` calcola per ognuno `accessible = 0`. La causa prevalente secondo il dossier è **BELOW_GATE (3 su 5)**, seguita da NO_NEWS (2). Riclassificati leggendo il testo degli articoli: 2 NO_NEWS, 2 THIN_NEUTRAL, 1 WRONG_SIGN.

Il fatto scomodo della giornata non è nella tabella dei miss: **i due mover rialzisti hanno entrambi zero righe `news_log`**, e sono stati presi da S1 momentum, che le notizie non le legge. La pipeline sentiment non ha contribuito a nessuna delle due catture, e ha invece prodotto il costo della giornata (whipsaw HOOD, −23,06 $ realizzati). 48/96 simboli a zero copertura.

---

## 2. Rendimenti — tabella completa (96 simboli)

`**M**` = mover ≥3%. "Articoli" = articoli unici in `news_log` quel giorno (dossier `copertura_articoli.per_ticker`).

| Simbolo | Return | Stato nel book | Articoli | ≥3% |
|---|---:|---|---:|:--:|
| PBR | +5.06% | detenuto | 0 | **M** |
| BP | +3.73% | ingresso oggi | 0 | **M** |
| AAPL | +2.61% | detenuto | 3 |  |
| CVX | +2.38% | detenuto | 1 |  |
| SHEL | +2.25% | detenuto | 2 |  |
| XOM | +2.24% | detenuto | 2 |  |
| JNJ | +2.01% | detenuto | 0 |  |
| UNH | +1.77% | detenuto | 0 |  |
| MRK | +1.42% | detenuto | 1 |  |
| ABBV | +1.39% | detenuto | 0 |  |
| XLE | +1.27% | detenuto | 2 |  |
| META | +1.08% | — | 2 |  |
| SONY | +1.02% | — | 0 |  |
| WMT | +1.00% | — | 0 |  |
| TMUS | +0.95% | — | 0 |  |
| TM | +0.77% | — | 1 |  |
| WFC | +0.75% | — | 1 |  |
| PG | +0.75% | — | 0 |  |
| C | +0.70% | detenuto | 1 |  |
| XLV | +0.66% | detenuto | 2 |  |
| VZ | +0.56% | — | 0 |  |
| T | +0.42% | — | 0 |  |
| PFE | +0.32% | ingresso oggi | 0 |  |
| LLY | +0.28% | detenuto | 0 |  |
| CRM | +0.22% | detenuto | 1 |  |
| AZN | +0.21% | — | 0 |  |
| VALE | +0.20% | detenuto | 0 |  |
| BAC | +0.08% | detenuto | 1 |  |
| WDC | -0.02% | detenuto | 0 |  |
| SBUX | -0.09% | detenuto | 0 |  |
| AVGO | -0.18% | — | 1 |  |
| MCD | -0.22% | — | 0 |  |
| NFLX | -0.30% | — | 0 |  |
| ERIC | -0.30% | — | 0 |  |
| JPM | -0.30% | detenuto | 1 |  |
| TSM | -0.32% | detenuto | 1 |  |
| BRK.B | -0.34% | — | 0 |  |
| COST | -0.42% | — | 0 |  |
| BIDU | -0.44% | — | 0 |  |
| NVO | -0.46% | — | 0 |  |
| INFY | -0.50% | — | 1 |  |
| MRVL | -0.60% | detenuto | 0 |  |
| INTC | -0.60% | ingresso oggi | 1 |  |
| RIO | -0.62% | detenuto | 0 |  |
| CSCO | -0.68% | detenuto | 0 |  |
| SPY | -0.69% | detenuto | 4 |  |
| F | -0.72% | — | 0 |  |
| GM | -0.80% | detenuto | 0 |  |
| XLF | -0.88% | detenuto | 1 |  |
| ROKU | -0.89% | detenuto | 0 |  |
| MMM | -0.93% | uscita oggi | 0 |  |
| SPCX | -1.02% | — | 3 |  |
| BA | -1.02% | — | 0 |  |
| BABA | -1.03% | — | 0 |  |
| IBM | -1.06% | — | 0 |  |
| MS | -1.07% | detenuto | 1 |  |
| IWM | -1.14% | detenuto | 1 |  |
| DB | -1.20% | — | 3 |  |
| CMCSA | -1.20% | — | 1 |  |
| JD | -1.20% | — | 0 |  |
| MSFT | -1.24% | ingresso oggi | 2 |  |
| DIS | -1.24% | — | 2 |  |
| HOOD | -1.24% | ingresso+uscita | 5 |  |
| QQQ | -1.27% | uscita oggi | 4 |  |
| GOOGL | -1.28% | ingresso oggi | 4 |  |
| NKE | -1.37% | — | 0 |  |
| GE | -1.38% | uscita oggi | 0 |  |
| MA | -1.39% | — | 0 |  |
| NVDA | -1.51% | — | 10 |  |
| XLK | -1.53% | detenuto | 2 |  |
| V | -1.77% | — | 1 |  |
| GS | -1.80% | detenuto | 3 |  |
| AXP | -1.81% | — | 1 |  |
| ASML | -1.82% | detenuto | 0 |  |
| AMZN | -1.87% | — | 5 |  |
| NOK | -2.07% | detenuto | 0 |  |
| SOXX | -2.10% | detenuto | 1 |  |
| RDDT | -2.14% | — | 0 |  |
| QCOM | -2.27% | — | 0 |  |
| ADBE | -2.29% | — | 0 |  |
| CAT | -2.30% | detenuto | 0 |  |
| AMD | -2.36% | detenuto | 2 |  |
| HD | -2.46% | — | 2 |  |
| MU | -2.64% | detenuto | 3 |  |
| UBS | -2.84% | detenuto | 1 |  |
| TXN | -2.90% | uscita oggi | 0 |  |
| ARM | -2.93% | uscita oggi | 0 |  |
| TSLA | -3.22% | — | 4 | **M** |
| NOW | -3.44% | — | 1 | **M** |
| PLTR | -3.47% | — | 0 | **M** |
| SNOW | -3.51% | detenuto | 2 | **M** |
| AMAT | -3.61% | detenuto | 1 | **M** |
| SAP | -4.01% | — | 0 | **M** |
| ORCL | -5.23% | — | 4 | **M** |
| PANW | -5.24% | detenuto | 4 | **M** |
| DELL | -6.80% | detenuto | 3 | **M** |

**Indici:** SPY −0,69%, QQQ −1,27%, IWM −1,14%. Dispersione cross-sectional σ = 1,85%.
Nessun simbolo senza barra (`simboli_senza_dati: []`).

---

## 3. Miss classificati (mover ≥3% non detenuti e non tradati)

Tutti e 5 i candidati miss del dossier. La colonna **Accessibile** riporta `opportunity_v2.accessible`: per tutti vale 0 con `missing_reason: long_only_no_short_downside_not_held`.

| Simbolo | Return | Categoria | Evidenza | Lordo ×2.200 $ | Accessibile |
|---|---:|---|---|---:|---:|
| ORCL | −5,23% | THIN_NEUTRAL | 4 articoli, punteggio massimo **−0,180** (18:15, «Oil Surges, Treasury Yields Climb a Fifth Day, Software Retreats», fan-out a 9 ticker). **Segno corretto**, magnitudine 0,12 sotto il gate 0,30. L'unico pezzo issuer-specific del giorno («$100 Invested In Oracle 20 Years Ago…») è un filler retrospettivo scorato 0,000. `max_score_own = 0,000`, `quota_righe_fanout = 0,5`. Catalizzatore IDIOSYNCRATIC, residuo vs XLK −3,70%. | 115,08 | 0 |
| SAP | −4,01% | NO_NEWS | **Zero** righe `news_log`, zero `sentiment_signals`. Catalizzatore UNKNOWN nel dossier. Residuo vs XLK −2,47%. | 88,14 | 0 |
| PLTR | −3,47% | NO_NEWS | **Zero** righe `news_log`, zero `sentiment_signals`. L'unico intent S4 del giorno è `SKIP_ENTRY_FRESHNESS` su un segnale del **2026-08-28** (score 0,000): quattro sedute senza una riga nuova. Residuo vs XLK −1,93%. | 76,25 | 0 |
| NOW | −3,44% | THIN_NEUTRAL | 1 solo articolo, lo stesso pezzo macro di ORCL, punteggio **−0,271** alle 18:00. **Segno corretto, 0,029 sotto il gate 0,30** — il secondo scarto più stretto della serie osservata (record: TSLA 0,019 l'08-31). `quota_righe_fanout = 1,0`: la sola fonte disponibile è un fan-out, nessun pezzo issuer-specific esiste. | 75,67 | 0 |
| TSLA | −3,22% | WRONG_SIGN | 4 articoli. I due **issuer-specific** sono entrambi rialzisti mentre il titolo scende: «Tesla's Cybercab Fleet Hits 45 Ahead of Austin Launch» **+0,150** (15:15) e «Tesla Touts Full Self-Driving as 4.1X Less Likely to Crash» **+0,268** (19:47, a 13 minuti dalla chiusura). L'unica lettura col segno giusto (−0,136) viene da un fan-out macro a 9 ticker. Il +0,268 ha superato lo stadio di gate ed è morto in `RANK_OUTSIDE_TOP_N`: il ranking ha evitato una perdita che il segnale avrebbe prodotto. | 70,91 | 0 |

**Conteggi:** NO_NEWS 2 · THIN_NEUTRAL 2 · WRONG_SIGN 1 · FILTERED 0 · OUT_OF_STRATEGY_SCOPE 0.

**Discrepanza dichiarata col dossier.** Il dossier classifica `NO_NEWS: 2, BELOW_GATE: 3` (dominante BELOW_GATE). Il suo classificatore è meccanico — confronta `max |score|` col gate — e non guarda il segno. Su ORCL e NOW le due letture coincidono (sotto soglia, segno corretto → THIN_NEUTRAL). Su **TSLA divergono**: è vero che è sotto soglia, ma le uniche notizie su Tesla di quel giorno erano rialziste su un titolo che perdeva il 3,22%, e questo è un errore di segno che il conteggio BELOW_GATE nasconde. Dove il dossier è deterministico vince il dossier; qui la differenza è interpretativa e la registro esplicitamente invece di appiattirla.

**Nota sulla misura del costo.** I valori "Lordo ×2.200 $" sono riportati per confrontabilità con la serie storica (convenzione dei report precedenti), **non** sono opportunità reali: per tutti e cinque il libro avrebbe dovuto shortare. Il costo realmente accessibile della tabella dei miss oggi è **0 $**.

---

## 4. Titoli catturati: esito

<!-- alpha-miss-book:start -->
<!-- alpha-miss-book-manifest: {"schema":1,"ingressi":["INTC","GOOGL","PFE","BP","HOOD","MSFT","HOOD"],"chiusure":["TXN","MMM","GE","ARM","QQQ","HOOD"]} -->

Dati deterministici dal dossier; la prosa seguente li annota e non li sostituisce.

| Tipo | Simbolo | Strategia | Ora UTC | Prezzo | Quantità | P&L netto | Motivo / qualità |
|---|---|---|---|---:|---:|---:|---|
| IN | INTC | S1 | 14:07 | $86.5900 | 5.9196 | — | percentile 23.58%; denominatore intraday valido |
| IN | GOOGL | S1 | 14:07 | $336.0700 | 2.4768 | — | percentile 72.77%; denominatore intraday degenere: quota non interpretabile |
| IN | PFE | S1 | 14:07 | $28.6900 | 29.0132 | — | percentile 36.00%; denominatore intraday valido |
| IN | BP | S1 | 14:07 | $43.8800 | 18.9697 | — | percentile 30.57%; denominatore intraday valido |
| IN | HOOD | S4 | 14:52 | $106.3998 | 13.3398 | — | percentile 87.58%; denominatore intraday valido |
| IN | MSFT | S4 | 15:37 | $500.9100 | 2.8280 | — | percentile 44.94%; denominatore intraday valido |
| IN | HOOD | S4 | 19:37 | $103.4200 | 13.5265 | — | percentile 21.51%; denominatore intraday valido |
| OUT | TXN | S1 | — | $252.4700 | 2.6908 | −$75.86 | portfolio_sell |
| OUT | MMM | S1 | — | $170.6400 | 3.7981 | −$36.53 | portfolio_sell |
| OUT | GE | S1 | — | $333.5800 | 2.3050 | −$19.14 | portfolio_sell |
| OUT | ARM | S1 | — | $231.6700 | 1.4089 | −$7.86 | portfolio_sell |
| OUT | QQQ | S1 | — | $711.0300 | 1.0790 | +$25.70 | sentiment_reversal |
| OUT | HOOD | S4 | — | $104.7300 | 13.3398 | −$23.06 | portfolio_sell |
<!-- alpha-miss-book:end -->

**Mover rialzisti — entrambi catturati (2 su 2):**

| Simbolo | Return | Come | Esito |
|---|---:|---|---|
| PBR | +5,06% | Detenuto (trade 270, S1, aperto 2026-07-10) | +18,20% dall'ingresso. Nozionale d'apertura 779,10 $. **Zero righe news_log** oggi e in tutta la finestra a 10 sedute (`fonti_osservate_finestra: []`). Alle 14:07 il ciclo ha tentato di aggiungere peso 1,2% ed è stato fermato da `SKIP_PYRAMIDING`: costo guardia 1,63 $ sull'orizzonte 1h. |
| BP | +3,73% | **Ingresso S1 14:07** @ 43,88, qty 18,97 | MTM fine giornata **+11,19 $**; contro un ingresso all'apertura avrebbe fatto +12,52 $, quindi il timing è costato 1,33 $. `entry_percentile` 0,306 (buon terzo inferiore della giornata). Motivazione a DB: «S1 momentum: time-series momentum signal, portfolio weight 1,2%». **Zero righe news_log**: la cattura non ha nulla a che vedere con la pipeline sentiment. |

**Mover ribassisti detenuti (4)** — non sono catture, sono esposizione subita: SNOW −3,51%, AMAT −3,61%, PANW −5,24%, DELL −6,80%. Su tutti e quattro S4 aveva un segnale col **segno corretto** (PANW −0,220 e −0,161, DELL −0,154) o nullo, e nessuno ha prodotto un'uscita: la soglia d'uscita non esiste (cfr. §Segnalazioni, F-059 già a ledger).

**Ingressi del giorno non-mover (5):** INTC (S1, 14:07, MTM +14,09 $, il migliore della giornata), GOOGL (S1, −2,60 $), PFE (S1, −4,06 $), MSFT (S4, 15:37, +0,31 $), HOOD (S4, due volte — vedi sotto).

**Chiusure del giorno (6), realizzato −136,76 $:**

| Simbolo | Strategia | Exit | P&L netto | Motivo | Drift post-uscita |
|---|---|---:|---:|---|---:|
| TXN | S1 | 252,47 | **−75,86** | portfolio_sell | +2,34% (uscita anticipata di un rimbalzo) |
| MMM | S1 | 170,64 | −36,53 | portfolio_sell | −1,52% (uscita corretta) |
| HOOD | S4 | 104,73 | −23,06 | portfolio_sell (`below_entry_gate`) | −16,27% |
| GE | S1 | 333,58 | −19,14 | portfolio_sell | −5,74% (uscita corretta) |
| ARM | S1 | 231,67 | −7,86 | portfolio_sell | +4,44% (uscita anticipata) |
| QQQ | S1 | 711,03 | **+25,70** | sentiment_reversal | −3,66% (uscita corretta) |

L'unica chiusura in utile è **QQQ**, ed è l'unica guidata dal sentiment: alle 16:00 QQQ ha prodotto un segnale **−0,407**, sopra il gate in magnitudine e col segno giusto, e alle 16:07 la posizione è stata chiusa a +25,70 $. Lo stesso segnale, sul lato ingresso, è morto in `RANK_LONG_ONLY`.

**Il costo della giornata: whipsaw HOOD.** Sequenza ricostruita da `sentiment_signals` + `execution_decisions`:

- **14:47** segnale 9400, **+0,4815** (ensemble, non-fallback) su «Robinhood Stock Rises as Morgan Stanley Upgrades Target to $150» → **BUY 14:52 @ 106,40**, 13,34 azioni.
- **15:01** segnale 9404, **+0,0228**, su «How Did BONER Meme Coin Create One of Robinhood's Biggest Stories?». Quattordici minuti dopo, un pezzo di colore sostituisce l'upgrade Morgan Stanley come stato del sistema.
- **15:07 → 16:22** cinque cicli consecutivi `SKIP_THRESHOLD: score 0.023 < feedback threshold 0.300`.
- **16:37 SELL @ 104,73**, motivo `[below_entry_gate] S4 signal fell below the active feedback entry threshold (age=1.6h vs max_age=4h, score=+0.023)` → **−23,06 $ realizzati** dopo 1h45m di detenzione.
- **19:34** segnale 9477, **+0,5395**, su «Morgan Stanley Upgrades HOOD, Cites Prediction Market Boom for $150 Target» — **la stessa notizia di 4h45m prima, altro titolo** → **BUY 19:37 @ 103,42**.

Il sistema ha venduto a 104,73 e ricomprato la stessa tesi a 103,42: ha pagato 23,06 $ per un giro a vuoto e ha ricomprato 2,98 $ più in basso. Il MTM del secondo ingresso a fine giornata è +1,22 $.

---

## 5. Cecità lato uscita (posizioni detenute)

Dal campo `copertura_uscita` del dossier (non ricalcolato). Definizione: posizione viva all'open RTH, in perdita ≥3% dall'ingresso al termine della detenzione, **zero** righe `news_log` e zero `sentiment_signals` nella seduta, e zero righe per ≥2 sedute consecutive. Finestra 10 sedute (2026-08-19 → 2026-09-01).

**47 posizioni valutate, 7 cieche lato uscita, 0 con `cieco_lato_uscita: null`** — nessun dato mancante oggi, il campo è deciso su tutte e 47.

| Ticker | Strategia | `ritorno_da_ingresso` | Sedute consecutive senza righe | `fonti_osservate_finestra` | Nozionale |
|---|---|---:|---:|---|---:|
| WDC | S4 | **−17,99%** | 2 | `alpaca_benzinga` | 151 $ |
| NOK | S1 | **−15,27%** | 3 | `alpaca_benzinga`, `gdelt_gkg` | 6 $ |
| TXN | S1 | −10,00% | 3 | `alpaca_benzinga`, `gdelt_gkg` | 679 $ |
| UNH | S1 | −7,33% | 4 | `alpaca_benzinga` | 631 $ |
| ASML | S1 | **−5,86%** | **8** | `alpaca_benzinga` | 629 $ |
| MMM | S1 | −5,28% | **10** (troncato dalla finestra) | **vuoto** | 648 $ |
| CAT | S1 | −4,13% | 2 | `alpaca_benzinga`, `gdelt_gkg` | 714 $ |

Da leggere con attenzione: `ritorno_da_ingresso` è la perdita subita mentre la posizione era detenuta (per TXN e MMM termina al prezzo d'uscita di oggi, non al close); `ritorno_seduta` è tutt'altro — UNH oggi è **salita** dell'1,77% pur essendo a −7,33% dall'ingresso.

Due casi sono strutturali più che congiunturali: **MMM** ha `fonti_osservate_finestra` **vuoto** e 10 sedute su 10 senza una riga, cioè **zero resa dei provider su quel ticker per l'intera finestra** — non una fonte non configurata, dato che i connettori per-ticker interrogano tutta la watchlist; ed è uscita oggi per `portfolio_sell`, mai per un segnale. **ASML** è a 8 sedute consecutive. Su queste due posizioni nessun meccanismo di uscita basato su notizia poteva accendersi, per assenza di input, non per scelta.

---

## 6. Pattern osservato

**Rotazione netta fuori dal software enterprise dentro l'energia, su indici moderatamente negativi.** Il pattern è leggibile ed è scritto per esteso nel titolo dell'articolo più diffuso della giornata: **«Oil Surges, Treasury Yields Climb a Fifth Day, Software Retreats: Stock Market Today»**.

- **Lato forte — energia, 6 su 6 positivi:** PBR +5,06%, BP +3,73%, CVX +2,38%, SHEL +2,25%, XOM +2,24%, XLE +1,27%. Secondo giorno consecutivo (l'08-31 registrava già «energy leggermente positivo su tutta la fascia»), ma oggi con magnitudine tripla. Difensivi al seguito: JNJ +2,01%, UNH +1,77%, MRK +1,42%, ABBV +1,39%, XLV +0,66%.
- **Lato debole — software/enterprise, compatto:** PANW −5,24%, ORCL −5,23%, SAP −4,01%, SNOW −3,51%, PLTR −3,47%, NOW −3,44%, ADBE −2,29%, CRM +0,22% (unica eccezione). Con loro l'hardware/AI: DELL −6,80%, AMAT −3,61%, TXN −2,90%, ARM −2,93%, MU −2,64%, SOXX −2,10%, XLK −1,53%.
- SPY −0,69% contro QQQ −1,27%: il rosso è concentrato nel Nasdaq, coerente con la rotazione, non con una direzione di mercato.

Il pattern è chiaro. **Quello che non è chiaro è perché la pipeline lo abbia visto solo da un lato.** L'articolo che descrive la rotazione (`content:26524ae4…`) è mappato su 9 ticker: DELL, IWM, NOW, ORCL, PANW, QQQ, XLE, XLK, XLV — cioè tutto il lato **software** e l'ETF settoriale, e **nessun nome petrolifero individuale**. Un pezzo il cui titolo comincia con «Oil Surges» non ha prodotto una singola riga su PBR, BP, XOM, CVX o SHEL. L'unico articolo energia-specifico del giorno («Trump Presses Refiners on Gas Prices Tuesday») copre solo CVX e XOM. I due mover migliori della giornata restano a zero righe.

---

## 7. Confronto con i giorni precedenti

- **Copertura news.** 48/96 a zero righe (50,0%). Nel contesto della serie: 41 (08-13), 43 (08-21), 45 (08-26), 51 (08-24), 53 (08-27), 54 (08-28), 55 (08-25), 60 (08-31). È il valore migliore da due settimane e un calo netto rispetto al massimo di ieri, ma resta metà universo e **la banda 40-60 non si è mai spezzata in tutta la finestra**: il miglioramento è oscillazione, non tendenza. I connettori di #454/#455/#456 non risultano ancora deployati.
- **Speculare all'08-25.** Il 25/08 il ledger registrava esattamente l'inverso: «rotazione intra-tech da software a hardware, **finanziata dall'energia**», con XOM −2,08%, BP −2,01%, XLE −1,66%, PBR −1,71%, CVX −1,58%, SHEL −0,84%, sei su sei negativi. Oggi gli stessi sei nomi sono sei su sei positivi. È la **quinta inversione dello stesso gruppo di titoli in sette sedute** (08-20, 08-24, 08-25, 08-26, 09-01). Il libro attraversa queste inversioni prevalentemente in modo passivo.
- **Ricorrenza della firma «fan-out come unica fonte».** NOW oggi ha `quota_righe_fanout = 1,0` — stesso caso di QCOM l'08-31 e AMZN l'08-28. Terza occorrenza in cinque sedute.
- **Il gate d'ingresso continua a mancare per pochi centesimi.** NOW −0,271 contro gate 0,30: scarto 0,029. Ieri TSLA a 0,281, scarto 0,019. Due sedute consecutive in cui il segnale più informativo della giornata cade entro 0,03 dalla soglia.
- **Novità che rompe la serie:** entrambi i mover rialzisti catturati (2/2). Nella finestra osservata i "catturati" oscillavano fra 1 e 7 su 5-14 mover; oggi la copertura del lato accessibile è completa. Va però letta insieme al fatto che **nessuna delle due catture viene dalla pipeline sentiment**.

---

## 8. Cosa sembra un difetto e non un limite noto

Non propongo tarature né fix: siamo dentro il periodo di sola osservazione (`docs/evidence/OBSERVATION_CHARTER.md`, scadenza attesa 2026-09-28). Segnalo solo dove l'evidenza di oggi indica un difetto invece di un limite di design.

1. **La sostituzione del segnale HOOD sembra un difetto, non un limite.** Che un segnale scada è design; che un pezzo di colore («BONER Meme Coin») **sostituisca** un upgrade Morgan Stanley 14 minuti dopo, azzerando lo stato del sistema su quel titolo, è la conseguenza di una regola — usare solo il segnale più recente per simbolo — che non pesa né la rilevanza né la magnitudine. È già a ledger come F-023. La decisione se aprirci un'issue è dell'operatore.
2. **Il fan-out asimmetrico sull'articolo di rotazione sembra un difetto di mappatura.** Un articolo intitolato «Oil Surges…» mappato su 9 ticker di cui zero petroliferi non è una scelta di design plausibile: è il tagger del provider che assegna i ticker della parte "Software Retreats" e ignora la parte "Oil Surges". Osservazione, non correzione proposta.
3. **`findings.json` era corrotto all'inizio di questa sessione** — vedi la nota di metodo qui sotto. Questo è un problema di infrastruttura dell'evidenza, non di trading, ed è il più urgente dei tre.

---

## 9. Nota di metodo — stato di `findings.json` all'apertura della sessione

`docs/evidence/findings.json` era **non parsabile**: conteneva i marcatori di conflitto di un `git stash pop` mai risolto (righe 2-17 e 723-4722, `Updated upstream` / `Stashed changes`).

- Il lato **`Updated upstream`** coincide byte per byte con `HEAD` (59 finding, `prossimo_id: 60`).
- Il lato **`Stashed changes`** è una versione più vecchia dello stesso file (39 finding, `prossimo_id: 40`) che contiene **12 occorrenze datate 2026-08-13 e attribuite a `FORENSIC_DAILY_REPORT_2026-08-13.md`, mai committate in nessun punto della storia del repo** (verificato scandendo tutti i commit che toccano il file).

Risoluzione applicata, conservativa e di solo append:
- base = lato `Updated upstream` (= `HEAD`);
- **restaurate 11 occorrenze orfane** su F-003, F-004, F-007, F-008, F-011, F-021, F-027, F-031, F-033, F-035 e F-001, dopo aver verificato che il titolo del finding coincide su entrambi i lati. L'occorrenza F-001 del 08-13 è stata restaurata con `costo_usd: null` invece dei 336,00 $ originali perché `HEAD` registra **già** un'occorrenza F-001 del 2026-08-13 da 336,01 $ (`ALPHA_MISS_REPORT_2026-08-13.md`): è lo stesso giorno visto dai due report gemelli, e sommarli raddoppierebbe il costo;
- lo spazio degli id **si era biforcato su F-039**: lo stash ha un F-039 diverso da quello di `HEAD` («il classificatore causale del dossier non distingue segnale fallback sopra soglia da causa realmente ignota»). Nessun finding esistente lo copre, quindi è stato restaurato come **F-060**, con la ri-numerazione motivata nella sua nota;
- nessuna occorrenza esistente è stata modificata o cancellata; nessun titolo e nessun id preesistente è stato toccato.

**Avvertenza all'operatore, fuori dal mio mandato.** Lo stesso `git stash pop` ha lasciato `docs/evidence/dossier/2026-08-13.json` con i marcatori di conflitto **ancora non risolti**: il file è non parsabile in questo momento. Non l'ho toccato — non è uno dei due ledger e non è mio da risolvere — ma `scripts/commit_evidence_ledger.sh` va lanciato sapendolo, perché rischia di committare un dossier corrotto. Lo stash `stash@{0}` ("WIP on main: 4eebb89") è ancora presente e intatto: la copia originale delle 12 occorrenze restaurate è recuperabile con `git show 'stash@{0}:docs/evidence/findings.json'`.

Colgo l'occasione per notare che il difetto descritto dall'orfano **sembra risolto**: il classificatore del dossier di oggi emette `BELOW_GATE` come categoria propria (3 casi su 5) e `intenti_ingresso_s4` distingue `SKIP_FALLBACK` (122 righe oggi) dagli altri codici. `NON_CLASSIFICATO` non compare più.

---

## Segnalazioni

[F-001] **48/96 simboli watchlist (50,0%) a zero righe `news_log`, e il buco cade esattamente sui due vincitori della giornata.** PBR +5,06% e BP +3,73% — il primo e il secondo mover — hanno entrambi zero articoli; PBR ne ha zero anche sull'intera finestra a 10 sedute (`fonti_osservate_finestra: []`). Entrambi sono stati comunque presi, ma **da S1 momentum, che le notizie non le legge**: se la cattura fosse dipesa da S4 sarebbero stati due miss NO_NEWS sul lato accessibile del libro. I due miss NO_NEWS effettivi sono SAP −4,01% e PLTR −3,47%, entrambi ribassisti quindi inaccessibili. Costo registrato = lordo close-to-close × 2.200 $ dei due miss NO_NEWS, 88,14 + 76,25 = **164,39 $**, per confrontabilità con la serie; il costo realmente accessibile oggi è 0 $.

[F-009] **Il gate 0,30 scarta due segnali col segno corretto su mover forti, uno per 0,029.** NOW −3,44% con punteggio massimo −0,271 (scarto dal gate 0,029, il secondo più stretto della serie dopo lo 0,019 di TSLA l'08-31) e ORCL −5,23% con −0,180. Entrambi dallo stesso articolo macro, entrambi col segno giusto. Costo lordo × 2.200 $: 75,67 + 115,08 = **190,75 $**, di cui accessibile 0 $ — il libro è long-only e nessuno dei due era detenuto, quindi anche superando il gate non sarebbe successo nulla. Registrato per la serie; il vincolo che morde davvero è F-040, non il gate.

[F-040] **Il segnale ribassista più forte della giornata supera il gate, ha il segno corretto e non produce nulla sul lato ingresso.** QQQ: −0,407 alle 16:00 e −0,303 alle 18:16, entrambi sopra 0,30 in magnitudine, contro un QQQ che chiude −1,27%; entrambi terminati in `RANK_LONG_ONLY` (8 righe oggi). Con una qualificazione che rende il finding più preciso invece che più grave: **lo stesso segnale ha funzionato sul lato uscita** — trade 593 chiuso alle 16:07 per `sentiment_reversal` a +25,70 $, l'unica chiusura in utile della giornata. Il vincolo long-only costa la gamba corta, non l'informazione. Costo lordo × 2.200 $ = **27,99 $**, accessibile 0 $.

[F-023] **Un pezzo di colore sostituisce un upgrade Morgan Stanley e chiude la posizione in perdita.** Segnale 9400 alle 14:47, +0,4815 ensemble non-fallback, su «Robinhood Stock Rises as Morgan Stanley Upgrades Target to $150» → BUY 14:52 @ 106,40. Alle 15:01 il segnale 9404 (+0,0228) su «How Did BONER Meme Coin Create One of Robinhood's Biggest Stories?» diventa lo stato del sistema; cinque cicli di `SKIP_THRESHOLD` a 0,023; alle 16:37 SELL @ 104,73 con motivo `below_entry_gate`. **Costo misurato: −23,06 $** (trade 927, `net_pnl` a DB). Alle 19:34 la **stessa notizia Morgan Stanley** ricompare con altro titolo (segnale 9477, +0,5395) e il sistema ricompra @ 103,42. Confidenza `misurata`: il P&L è una riga di `trades`, la catena segnale→decisione è ricostruibile da `execution_decisions`.

[F-013] **Round-trip intraday sullo stesso simbolo: BUY 14:52 → SELL 16:37 → BUY 19:37 su HOOD.** Manifestazione dell'assenza di banda fra gate d'ingresso (0,30) e soglia d'uscita (0): a 0,023 il sistema non è "neutrale", è "fuori". `ore_tenuta` 1,75. Costo `null` per non duplicare: i −23,06 $ sono già attribuiti a F-023, che è il meccanismo a monte.

[F-012] **L'articolo che descrive la rotazione della giornata è mappato su 9 ticker, nessuno dei quali è un petrolifero.** «Oil Surges, Treasury Yields Climb a Fifth Day, Software Retreats» → DELL, IWM, NOW, ORCL, PANW, QQQ, XLE, XLK, XLV. La metà "Software Retreats" produce segnali su 5 titoli; la metà "Oil Surges" non produce nulla su PBR, BP, XOM, CVX, SHEL. Sul totale del giorno: 106 righe `news_log` per 59 articoli unici, di cui **76 mappature `TAG_UNCONFIRMED` contro 28 `ISSUER_SPECIFIC`**, e 47 mappature fan-out extra; copertura effective-timely 21/96 = 21,9%. NOW ha `quota_righe_fanout = 1,0` — terza occorrenza in cinque sedute della firma "fan-out come unica fonte" (QCOM 08-31, AMZN 08-28). Costo `null`: non separabile dagli altri finding sugli stessi titoli.

[F-031] **La guardia anti-pyramiding blocca peso sul miglior mover della giornata.** 44 righe `SKIP_PYRAMIDING` oggi, fra cui **PBR** (+5,06%, il mover numero uno): «P0-05 anti-pyramiding: già a libro dal 2026-07-10, peso non allocato 1,2%». Sul complesso delle guardie il dossier misura, su orizzonte controfattuale 1h, **72,53 $ di costo contro 31,28 $ di perdita evitata → netto −41,25 $**. Confidenza `attribuita`: l'orizzonte 1h cattura solo +0,35% dei +5,06% di PBR, quindi 41,25 $ è un limite inferiore. Parte del titolo del finding è oggi superata: le righe hanno un `reason` esplicito e finiscono nel dossier, la traccia esiste.

[F-026] **Un giorno intero di evidenza forense perso e lo spazio degli id biforcato.** Le 12 occorrenze scritte da `FORENSIC_DAILY_REPORT_2026-08-13.md` non sono mai state committate: sono rimaste dentro `stash@{0}` e sono riemerse oggi come conflitto non risolto in `findings.json`, rendendo il file non parsabile all'apertura della sessione. Conseguenza aggiuntiva prevista dal titolo del finding: **id duplicato** — F-039 designa due finding diversi nei due rami. Ricostruzione e risoluzione conservativa in §9. Costo `null`: è perdita di evidenza, non di denaro; il costo è la ricorrenza. Meccanismo diverso da quello descritto in origine (lì il ciclo non scriveva affatto; qui scriveva in un ramo che non è mai arrivato a `main`), stessa conseguenza — agganciato qui invece di aprire un id nuovo.

[F-060] **Record restaurato, non nuova osservazione.** Il finding orfano del 2026-08-13 sul classificatore causale del dossier, recuperato dallo stash e ri-numerato perché l'id F-039 era già occupato in `main` da un finding diverso. Vedi §9. Nessuna occorrenza nuova a suo carico oggi; anzi, l'evidenza di oggi suggerisce che il difetto sia stato risolto (il dossier emette `BELOW_GATE`, `intenti_ingresso_s4` distingue `SKIP_FALLBACK`), ma non chiudo un finding di cui non sono l'autore: decisione dell'operatore.

---

*Report generato in sessione autonoma di analisi giornaliera. Nessuna modifica a codice, nessun ordine, nessun worker avviato, nessun commit. Gli unici file scritti sono questo report, `docs/evidence/market_daily.jsonl` e `docs/evidence/findings.json`.*
