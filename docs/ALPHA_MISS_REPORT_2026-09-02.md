# Alpha Miss Report — 2026-09-02

**Universo:** 96 simboli di `config/trading.yaml → symbols.watchlist`.
**Fonte prezzi:** dossier deterministico `docs/evidence/dossier/2026-09-02.json` (schema 2.6, Alpaca SIP, `adjustment=all`), generato il 2026-09-03T08:00:21Z. Ogni numero di mercato, copertura, ingresso, uscita, guardia e controfattuale citato qui viene dal dossier; la lettura del testo degli articoli e la classificazione delle cause sono mie.
**Soglia mover:** `|return| ≥ 3%` (`soglia_mover` del dossier). Con σ cross-sectional a **2,60%** oggi, 3% è ≈1,15σ: soglia più permissiva del solito in termini di sigma, ma tenuta ferma per confrontabilità con la serie. Il campione che ne esce è 11 nomi, in linea con la mediana della finestra.
**Regime di scoring:** seconda seduta con la Variante A del prompt sentiment (#399/#408, deployata `bf5bef2e` il 2026-09-01T10:33Z). Gli score di oggi sono confrontabili con quelli di ieri, non con quelli di agosto.
**Cicli portfolio:** 24 cicli da 14:07 a 19:52 UTC, **zero gap oltre 16 minuti**. La cadenza non è un fattore in nessuna delle catture o dei miss di oggi.

---

## 1. Executive summary

Rotazione violenta **fuori dal software enterprise**, unico settore negativo della giornata (−1,19% medio, e i cinque peggiori titoli dell'universo sono tutti suoi), **dentro semis, finanziari, media e materials** — su indici quasi fermi (SPY +0,44%, QQQ +0,23%, XLK −0,02%). 11 mover ≥3%: **7 al rialzo, 4 al ribasso**.

Alembic ne ha **6 in mano** (DELL, VALE, HOOD, NVDA, SNOW, PANW) e **5 mancati** (RDDT, NVO, ORCL, NOW, PLTR). Sul lato accessibile — libro long-only — 3 dei 5 miss sono ribassisti e hanno `accessible_opportunity = 0` per costruzione; i miss realmente costosi sono due: **RDDT +9,31%** e **NVO +3,66%**, entrambi `NO_NEWS` puri, zero righe in `news_log`. Causa prevalente: **NO_NEWS (2 su 5)**.

Il fatto della giornata non è nella tabella dei miss. Il miglior mover dell'universo, **DELL +15,81%**, era a libro — con **429 $ di nozionale**: la posizione S1 ha reso 28,02 $ mentre lo stesso movimento su uno slot S4 da 2.200 $ valeva ~230 $. Il segnale c'era e passava largamente il gate (+0,636 alle 16:15), ed è stato bloccato tre volte dall'anti-pyramiding con «peso non allocato 2,4%». **Le due liquidazioni di posizioni vincenti** sono state entrambe innescate da articoli che non parlano del titolo: HOOD (+3,36%) da un pezzo che nomina Alumis, Sirius XM e OGE Energy e **non nomina Robinhood**; NVDA da un pezzo il cui corpo dichiara letteralmente «*This article is about the big picture, not an individual stock*».

Book: equity di chiusura **109.856,09 $** (+154,71 $ sulla seduta), realizzato **−9,60 $** (S1 −29,38 $, S4 +19,78 $), MTM del libro aperto **+164,31 $**. 45/96 simboli a zero copertura news.

---

## 2. Rendimenti — tabella completa (96 simboli)

`**M**` = mover ≥3%. "Articoli" = articoli unici in `news_log` quel giorno (dossier `copertura_articoli.per_ticker`). "Stato" è la posizione nel book all'open RTH.

| Simbolo | Return | Stato nel book | Articoli | ≥3% |
|---|---:|---|---:|:--:|
| DELL | +15.81% | detenuto | 8 | **M** |
| RDDT | +9.31% | — | 0 | **M** |
| VALE | +4.03% | detenuto | 0 | **M** |
| NVO | +3.66% | — | 0 | **M** |
| HOOD | +3.36% | uscita oggi | 2 | **M** |
| NVDA | +3.21% | ingresso+uscita oggi | 9 | **M** |
| ORCL | +3.13% | — | 1 | **M** |
| TMUS | +2.82% | — | 0 |  |
| PBR | +2.61% | detenuto | 0 |  |
| WFC | +2.56% | — | 0 |  |
| META | +2.47% | — | 2 |  |
| MU | +2.43% | detenuto | 5 |  |
| NFLX | +2.38% | — | 0 |  |
| DB | +2.32% | — | 3 |  |
| F | +2.17% | — | 0 |  |
| QCOM | +2.01% | — | 0 |  |
| CMCSA | +1.94% | — | 0 |  |
| AXP | +1.79% | — | 0 |  |
| CAT | +1.68% | detenuto | 2 |  |
| DIS | +1.66% | — | 3 |  |
| PFE | +1.65% | detenuto | 0 |  |
| BA | +1.56% | — | 0 |  |
| V | +1.54% | — | 0 |  |
| JNJ | +1.48% | detenuto | 1 |  |
| UBS | +1.40% | detenuto | 0 |  |
| ROKU | +1.40% | detenuto | 0 |  |
| C | +1.36% | detenuto | 1 |  |
| INTC | +1.21% | detenuto | 1 |  |
| MA | +1.21% | — | 0 |  |
| MRK | +1.19% | detenuto | 0 |  |
| IWM | +1.18% | detenuto | 1 |  |
| ASML | +1.03% | detenuto | 0 |  |
| BAC | +0.98% | detenuto | 1 |  |
| PG | +0.98% | — | 0 |  |
| RIO | +0.87% | detenuto | 0 |  |
| UNH | +0.85% | detenuto | 2 |  |
| XLF | +0.80% | detenuto | 2 |  |
| XLV | +0.75% | detenuto | 2 |  |
| ABBV | +0.67% | detenuto | 0 |  |
| GOOGL | +0.63% | detenuto | 8 |  |
| BRK.B | +0.58% | — | 1 |  |
| TXN | +0.58% | — | 1 |  |
| SBUX | +0.54% | detenuto | 0 |  |
| XLE | +0.51% | detenuto | 3 |  |
| SPY | +0.44% | detenuto | 4 |  |
| MS | +0.37% | detenuto | 2 |  |
| TSM | +0.36% | detenuto | 2 |  |
| JPM | +0.36% | detenuto | 1 |  |
| CVX | +0.35% | detenuto | 2 |  |
| NKE | +0.31% | — | 0 |  |
| TSLA | +0.26% | — | 4 |  |
| QQQ | +0.23% | — | 3 |  |
| SOXX | +0.23% | detenuto | 1 |  |
| GS | +0.19% | uscita oggi | 3 |  |
| WMT | +0.16% | — | 0 |  |
| IBM | +0.13% | — | 0 |  |
| TM | +0.13% | — | 1 |  |
| AMZN | +0.02% | — | 3 |  |
| ARM | +0.02% | — | 0 |  |
| LLY | +0.01% | detenuto | 0 |  |
| XLK | -0.02% | detenuto | 2 |  |
| AAPL | -0.05% | detenuto | 3 |  |
| MCD | -0.06% | — | 0 |  |
| VZ | -0.16% | — | 1 |  |
| T | -0.19% | — | 0 |  |
| ERIC | -0.20% | — | 0 |  |
| XOM | -0.24% | detenuto | 1 |  |
| INFY | -0.25% | — | 0 |  |
| JD | -0.25% | — | 0 |  |
| CSCO | -0.26% | detenuto | 0 |  |
| WDC | -0.34% | detenuto | 0 |  |
| HD | -0.39% | — | 1 |  |
| CRM | -0.46% | detenuto | 1 |  |
| GE | -0.48% | — | 0 |  |
| AZN | -0.52% | — | 0 |  |
| BIDU | -0.55% | — | 0 |  |
| AMD | -0.55% | detenuto | 1 |  |
| SONY | -0.64% | — | 0 |  |
| AVGO | -0.66% | — | 4 |  |
| SHEL | -0.76% | detenuto | 1 |  |
| AMAT | -0.77% | detenuto | 0 |  |
| MSFT | -0.84% | uscita oggi | 4 |  |
| MMM | -0.88% | — | 0 |  |
| GM | -0.89% | detenuto | 1 |  |
| NOK | -0.91% | detenuto | 1 |  |
| BABA | -0.92% | — | 0 |  |
| SPCX | -1.07% | — | 4 |  |
| SAP | -1.11% | — | 0 |  |
| BP | -1.21% | detenuto | 0 |  |
| COST | -1.22% | — | 0 |  |
| MRVL | -1.86% | detenuto | 2 |  |
| ADBE | -2.20% | — | 1 |  |
| NOW | -4.32% | — | 1 | **M** |
| SNOW | -4.37% | detenuto | 3 | **M** |
| PLTR | -5.81% | — | 3 | **M** |
| PANW | -9.28% | uscita oggi | 8 | **M** |
Nessun simbolo senza barre disponibili (`simboli_senza_dati: []`).

---

## 3. Miss classificati (mover ≥3% non detenuti e non tradati)

I 5 candidati sono esattamente quelli di `candidati_miss` del dossier. Le categorie sono mie, dopo aver letto il testo degli articoli; dove differiscono dal `causa` del dossier lo dichiaro.

| Simbolo | Return | Categoria | Dossier | Evidenza |
|---|---:|---|---|---|
| RDDT | +9,31% | **NO_NEWS** | NO_NEWS | Zero righe `news_log`, zero segnali. **Zero righe anche sull'intera finestra a 10 sedute** (nessuna riga dal 2026-08-20). Lordo 204,73 $, accessibile **60,19 $** (unico miss con opportunità realmente accessibile). |
| NVO | +3,66% | **NO_NEWS** | NO_NEWS | Zero righe, zero segnali. Ultima copertura il 2026-08-27 (3 righe in 14 giorni). Lordo 80,45 $, accessibile 8,50 $. |
| ORCL | +3,13% | **WRONG_SIGN** | BELOW_GATE | Un solo articolo, alle **19:15** — 45 minuti dal close: «OpenAI's $300B Deal Could Make Oracle the Weak Link in the AI Boom», punteggio **−0,282** su un titolo che chiude **+3,13%**. Segno opposto al movimento. Il dossier lo classifica BELOW_GATE (correttamente: −0,282 non supera 0,300) ma la nota rilevante è il segno. `accessible_opportunity` **−4,82 $**: negativo, cioè al primo ciclo eleggibile il movimento era già finito. |
| NOW | −4,32% | **THIN_NEUTRAL** | BELOW_GATE | Un solo articolo, l'unica riga è **fan-out** (`quota_righe_fanout = 1,0`): il wrap macro «Nvidia Jumps On AI Bid, Software Stocks Dip», punteggio −0,131 con segno **corretto** ma magnitudine meno di metà del gate. Ribassista e non detenuto → `accessible = 0`. |
| PLTR | −5,81% | **FILTERED** | NON_CLASSIFICATO | Segnale col **segno corretto e sopra la magnitudine del gate**: −0,420 alle 17:00 su «Why Is Palantir Stock Falling on Wednesday?» (ISSUER_SPECIFIC, n_ticker=1). Scartato non dal gate ma da `SKIP_FALLBACK` — **tutti e tre** i punteggi PLTR di oggi sono `single:gpt-oss:20b-cloud`, esclusi dal ranking per design (#108); 15 righe `SKIP_FALLBACK` sul solo PLTR. Ribassista e non detenuto → `accessible = 0`. |

**Conteggi:** NO_NEWS 2, THIN_NEUTRAL 1, WRONG_SIGN 1, FILTERED 1, OUT_OF_STRATEGY_SCOPE 0.

Da leggere insieme: 3 dei 5 miss (NOW, PLTR, e in pratica anche ORCL, la cui opportunità accessibile è negativa) **non erano tradabili** con questa costruzione, indipendentemente da qualunque soglia. L'unico miss con denaro sul tavolo è RDDT, e la sua causa è l'assenza di dati.

---

## 4. Titoli catturati: esito

<!-- alpha-miss-book:start -->
<!-- alpha-miss-book-manifest: {"schema":1,"ingressi":["NVDA"],"chiusure":["HOOD","MSFT","PANW","GS","NVDA"]} -->

Dati deterministici dal dossier; la prosa seguente li annota e non li sostituisce.

| Tipo | Simbolo | Strategia | Ora UTC | Prezzo | Quantità | P&L netto | Motivo / qualità |
|---|---|---|---|---:|---:|---:|---|
| IN | NVDA | S4 | 18:07 | $224.7900 | 6.3086 | — | percentile 66.63%; denominatore intraday valido |
| OUT | HOOD | S4 | — | $106.5652 | 13.5265 | +$41.77 | portfolio_sell |
| OUT | MSFT | S4 | — | $494.2500 | 2.8280 | −$19.12 | portfolio_sell |
| OUT | PANW | S1 | — | $323.9500 | 2.2748 | +$5.54 | sentiment_reversal |
| OUT | GS | S1 | — | $1002.1500 | 0.6452 | −$34.92 | sentiment_reversal |
| OUT | NVDA | S4 | — | $224.3800 | 6.3086 | −$2.87 | portfolio_sell |
<!-- alpha-miss-book:end -->

Sei mover su undici erano nel libro o vi sono entrati. Cinque su sei con una qualificazione.

| Simbolo | Return | Esito | Numeri |
|---|---:|---|---|
| **DELL** | +15,81% | detenuto, **sottodimensionato** | S1, trade 293, a libro dal 2026-07-13. Nozionale all'open **429,50 $** (0,93 azioni), MTM passivo **+28,02 $**. Nessuna uscita, nessuna aggiunta. |
| **VALE** | +4,03% | detenuto, cattura passiva | S1, trade 319, nozionale 817,80 $, MTM passivo **+15,90 $**. **Zero righe `news_log`** oggi e su tutta la finestra a 10 sedute: la cattura è momentum S1, la pipeline sentiment non ha contribuito. |
| **HOOD** | +3,36% | **liquidato in giornata su un articolo che non lo nomina** | S4, trade 962 (ingresso 09-01 19:37 @ 103,42). SELL 15:07 @ 106,565, **realizzato +41,77 $**, `portfolio_sell` / `below_entry_gate`. `drift_post_uscita` **+5,75 $** lasciati sul tavolo (close 106,99). Vedi §8.1. |
| **NVDA** | +3,21% | **round-trip intraday in perdita** | S4, trade 966. BUY 18:07 @ 224,79 (`entry_percentile` 0,666; `quota_movimento_precedente_al_segnale` **1,0676**, cioè il movimento era già più che completo), SELL 19:52 @ 224,38, `ore_tenuta` 1,75, **realizzato −2,87 $**. `drift_post_uscita` +0,19 $. `vs_apertura` +35,49 $: comprato a giornata già fatta. |
| **SNOW** | −4,37% | detenuto, attraversato passivamente | S1, trade 660, nozionale 536,60 $, MTM passivo **−8,12 $**. Tre articoli ISSUER_SPECIFIC (copertura effective-timely **100%**, il massimo dell'universo) su un giorno di earnings, e il punteggio massimo è **+0,167** — segno opposto al −4,37%. 24 cicli di `SKIP_THRESHOLD`, nessuna riduzione. |
| **PANW** | −9,28% | detenuto, **uscita corretta su segnale corretto** | S1, trade 294, a libro dal 2026-07-13. SELL 18:07 su `sentiment_reversal` (−0,495 < −0,35), **realizzato +5,54 $** (la posizione era in utile dall'ingresso di luglio). MTM passivo della giornata −39,85 $, `exit_active_effect` −10,30 $ (il titolo rimbalza dopo l'uscita: exit 323,95 → close 328,48). L'unico caso della giornata in cui la pipeline ha fatto esattamente il suo lavoro. |

Le altre due chiusure del giorno, non-mover: **MSFT** (S4, −19,12 $, `portfolio_sell`, drift +7,27 $) e **GS** (S1, −34,92 $, `sentiment_reversal`, drift +1,46 $ — vedi §8.2).

**Tutte e cinque le uscite della seduta hanno `drift_post_uscita` positivo**, per un totale di **25,0 $** di movimento lasciato sul tavolo (5,75 + 7,27 + 10,30 + 1,46 + 0,19). Mediana mobile a 20 giorni del `drift_post_uscita`: 0,265 $. Oggi è quasi due ordini di grandezza sopra.

---

## 5. Cecità lato uscita (posizioni detenute)

Dal campo `copertura_uscita` del dossier, non ricalcolato. Definizione: posizione viva all'open RTH, in perdita ≥3% dall'ingresso al termine della detenzione nella seduta, **zero** righe `news_log` e zero `sentiment_signals` nella seduta, e zero righe per ≥2 sedute consecutive. Finestra 10 sedute (2026-08-20 → 2026-09-02).

**48 posizioni valutate, 2 cieche lato uscita, 0 con `cieco_lato_uscita: null`** — nessun dato mancante oggi, il campo è deciso su tutte e 48.

| Ticker | Strategia | `ritorno_da_ingresso` | Sedute consecutive senza righe | `fonti_osservate_finestra` | Nozionale |
|---|---|---:|---:|---|---:|
| **WDC** | S4 | **−18,27%** | 3 | `alpaca_benzinga` | 150,25 $ |
| **ASML** | S1 | **−4,89%** | **9** | `alpaca_benzinga` | 635,15 $ |

Nozionale cieco totale **785,40 $** — esposizione a rischio, non un costo: nessun controfattuale dice che un'uscita sarebbe stata migliore. Attenzione a non confondere le misure: ASML oggi è **salita** (+1,03% di `ritorno_seduta`) pur essendo a −4,89% dall'ingresso, e WDC ha chiuso a −0,34% di seduta pur essendo a −18,27% dall'ingresso.

**ASML è a 9 sedute consecutive senza una riga** (era 8 ieri): una sola riga in tutta la finestra, il 2026-08-20. Su quella posizione nessun meccanismo di uscita basato su notizia può accendersi — per assenza di input, non per scelta. Il quadro complessivo della copertura sul libro è più severo del conteggio dei ciechi: **15 posizioni su 48 a copertura nulla** e **36 su 48 a copertura *effettiva* nulla** (zero articoli ISSUER_SPECIFIC pubblicati entro il close), cioè tre quarti del libro sono stati attraversati senza un input ticker-specifico tempestivo.

---

## 6. Pattern osservato

**Rotazione fuori dal software enterprise dentro tutto il resto, a indice fermo.** Il pattern è scritto nel titolo dell'articolo più diffuso della giornata — «**Nvidia Jumps On AI Bid, Software Stocks Dip: Stock Market Today**» — e la lettura per settore lo conferma senza ambiguità:

- **`tech` è il solo settore negativo dell'universo** (−1,19% medio su 21 nomi) e contiene i **cinque peggiori titoli in assoluto**: PANW −9,28%, PLTR −5,81%, SNOW −4,37%, NOW −4,32%, ADBE −2,20%. Con loro SAP −1,11%, MSFT −0,84%, CRM −0,46%. L'unica eccezione al rialzo è ORCL +3,13%, e su una notizia sua (OpenAI).
- **Tutti gli altri settori positivi:** media +3,33% (RDDT +9,31%, NFLX +2,38%, CMCSA +1,94%), materials +2,45%, semis +1,51% (DELL +15,81%, NVDA +3,21%, MU +2,43%), **financials +1,34% con 14 nomi su 14 positivi** (HOOD +3,36%, WFC +2,56%, DB +2,32%, AXP +1,79%, V +1,54%), healthcare +1,08%.
- **Gli ETF non lo vedono:** SPY +0,44%, QQQ +0,23%, XLK −0,02%, SOXX +0,23%. IWM +1,18% è il solo segnale d'indice della rotazione (small cap sopra il Nasdaq). Il movimento è **intra-settoriale e idiosincratico**, non beta: σ cross-sectional 2,60% contro un indice a +0,44%. Il dossier lo conferma dal lato dell'attribuzione: sul libro il `market_beta_1` spiega 131,68 $ dei 131,71 $ di P&L passivo, e tutto il resto è residuo per titolo.
- **Le tre punte del rialzo sono tre reazioni a earnings:** DELL (trimestre riportato il 01/09 a mercati chiusi — «Blowout Quarter», «AI Revenue More Than Doubles», ed era **−6,80% il giorno prima**), PANW e SNOW dal lato opposto. Il tema della giornata è earnings, non macro.

---

## 7. Confronto con i giorni precedenti

- **Copertura news.** 45/96 a zero righe (46,9%). Serie: 41 (08-13), 43 (08-21), 45 (08-26), 48 (09-01), 51 (08-24), 53 (08-27), 54 (08-28), 55 (08-25), 60 (08-31). È il valore migliore della finestra a pari merito con l'08-26, ma **la banda 40-60 non si è mai spezzata in nessuna delle 9 sedute misurate**: oscillazione, non tendenza.
- **Dispersione massima della finestra.** σ 2,60% contro 1,85% ieri, 1,52% l'08-31, 2,17% l'08-28, 2,21% l'08-13, 3,49% l'08-27. È la seconda giornata più dispersa della serie, e la prima in cui la dispersione **non** è accompagnata da un movimento d'indice (SPY +0,44%).
- **Rotazione software: terza faccia in tre sedute, sempre lo stesso lato debole.** L'08-31 e il 09-01 il software era già il lato debole (PANW −5,24%, ORCL −5,23%, SAP −4,01%, SNOW −3,51%, PLTR −3,47%, NOW −3,44% ieri). Oggi gli **stessi cinque nomi** perdono di nuovo, con magnitudine maggiore su PANW (−9,28% contro −5,24%) e PLTR (−5,81% contro −3,47%). Ciò che è cambiato è il lato forte: ieri energia, oggi semis+financials. Il libro attraversa entrambe le facce in modo prevalentemente passivo.
- **DELL: inversione completa in una seduta.** −6,80% ieri, +15,81% oggi. Ieri il report registrava DELL fra i nomi trascinati giù dalla rotazione; oggi è il primo mover dell'universo per earnings. Il segnale è arrivato ed era forte (+0,636); il vincolo binding è stato l'anti-pyramiding su una posizione S1 da 429 $, non la pipeline.
- **HOOD: seconda liquidazione consecutiva su articolo irrilevante.** Ieri (09-01) un pezzo su un meme coin sostituiva un upgrade Morgan Stanley e chiudeva la posizione a −23,06 $ (F-023). Oggi, sullo stesso titolo, un articolo che **non nomina Robinhood** la chiude di nuovo. Due sedute consecutive, stesso ticker, stesso meccanismo a valle: il segnale corrente diventa lo stato del sistema senza filtro di rilevanza.
- **Il gate continua a mancare per pochi centesimi.** HOOD +3,36% con punteggio massimo **0,260** contro gate 0,300 (scarto **0,040**), per cinque cicli consecutivi dopo la liquidazione. Terza seduta consecutiva in cui il segnale più informativo della giornata cade entro 0,04 dalla soglia (0,019 TSLA l'08-31, 0,029 NOW il 09-01, 0,040 HOOD oggi).
- **Firma «fan-out come unica fonte»: quarta occorrenza in sei sedute.** NOW oggi ha `quota_righe_fanout = 1,0`, come QCOM l'08-31, AMZN l'08-28, NOW il 09-01.
- **`NON_CLASSIFICATO` è tornato.** Ieri il report notava che la categoria era sparita dal classificatore causale e che il difetto F-060 sembrava risolto. Oggi ricompare su PLTR, che è un caso `SKIP_FALLBACK` perfettamente noto al ledger degli intent (15 righe). Il difetto non era risolto: era senza casi.
- **Tasso di fallback in calo.** 38/128 righe (29,7%) contro le bande 70-86% di luglio. Composizione del giorno: 90 righe ensemble `glm-5.2+gpt-oss`, 30 `single:gpt-oss`, 7 `single:glm-5.2`, **1 FinBERT**. Nessun segno di outage dell'ensemble (F-049) oggi.

---

## 8. Cosa sembra un difetto e non un limite noto

Non propongo tarature né fix: siamo dentro il periodo di sola osservazione (`docs/evidence/OBSERVATION_CHARTER.md`, scadenza attesa 2026-09-28, taratura congelata). Segnalo solo dove l'evidenza di oggi indica un difetto invece di un limite di design. La decisione se aprire issue è dell'operatore.

**8.1 — L'articolo che ha liquidato HOOD non nomina Robinhood. Questo è un difetto, non un limite.** `news_log` 9508, fetch 14:45, pubblicato 14:07, `extraction_method = source_metadata`, mappato su **un solo ticker: HOOD**. Titolo: «This OGE Energy Analyst Turns Bullish; Here Are Top 4 Upgrades For Wednesday». Corpo integrale, 91 caratteri: «*Analysts upgraded Alumis, Sirius XM, OGE Energy, revising their price targets and outlooks.*» Nessuna occorrenza di Robinhood o HOOD, né nel titolo né nel corpo. Punteggio: **0,000 con confidenza 0,15**, ensemble non-fallback. Alle 15:07 quel punteggio è lo stato del sistema e il gate d'uscita lo legge: SELL @ 106,565 con motivo `below_entry_gate`, su un titolo che chiude **+3,36%**. Alle 16:45 arriva l'articolo vero («Robinhood Stock Edges Higher Wednesday», Scotiabank inizia la copertura a $136), punteggio **+0,260**, e per cinque cicli consecutivi resta sotto il gate 0,300: nessun rientro. Tre cose separate qui sono verificabili e nessuna è una scelta di design plausibile: (a) il tag del provider assegna un articolo a un ticker che l'articolo non menziona; (b) il rilevatore `FALSE_ENTITY_MATCH` del dossier **non lo intercetta** — oggi segnala 2 righe, entrambe `gdelt_gkg` (CVX, MSFT), **zero** su `alpaca_benzinga`, dove i tag arrivano dai metadati del provider e non vengono validati; (c) un punteggio a confidenza 0,15 può liquidare una posizione mentre per aprirla ne servirebbe 0,30.

**8.2 — Il sistema legge le previsioni di mercato di Goldman come notizie sul titolo Goldman.** GS venduta alle 19:07 per `sentiment_reversal` su punteggio **−0,497 (confidenza 0,73, ensemble non-fallback)** generato da «Goldman Sachs warns investors to expect lower returns over the next year» (`org_lookup`, gdelt). È un'affermazione di Goldman **sul mercato**, non una notizia su Goldman: il titolo GS ha chiuso +0,19%. Realizzato −34,92 $ (la posizione era già a −5,1% dall'ingresso del 10/07: la perdita è preesistente, non causata dall'uscita; il costo attribuibile alla decisione è il drift, +1,46 $). Non è un caso isolato: **tutti e quattro** i segnali su ticker bancari oggi nascono da articoli su terzi in cui la banca è la casa d'analisi o l'organizzatore — DB su «Sirius XM Rises 6% on Deutsche Bank Upgrade» e «SiriusXM is being 'overlooked'... Deutsche Bank says»; MS su «Meta settlement... Morgan Stanley says» (+0,358, sopra la magnitudine del gate) e «Lear to Participate in Morgan Stanley 14th Annual Laguna Conference».

**8.3 — Il calendario earnings è indisponibile da tre sedute, e lo è nel giorno in cui il tema della giornata sono gli earnings.** Il campo `giorno_di_earnings` degli intent S4 vale `None` su **1438 intent su 1438**. `None` significa calendario non disponibile (UNKNOWN, non `False`), come dichiara la provenienza del dossier. La serie: `False` su tutti i 1494 intent dell'08-25, `False` su 1494 e **`True` su 24** l'08-26 (giorno di earnings NVDA — quindi il campo funzionava e discriminava), `False` su tutti i 1700 dell'08-27, poi **`None` su tutto** l'08-31, il 09-01 e il 09-02. Conseguenza: il qualificatore earnings-day della guardia ombra di contraddizione (#335) è cieco su ogni intento proprio nella seduta in cui **i tre mover più grandi dell'universo — DELL +15,81%, PANW −9,28%, SNOW −4,37% — sono tutti reazioni a trimestrali**. Nessun finding esistente copre l'indisponibilità del calendario: registrato come nuovo.

**8.4 — Nota su cosa *non* è un difetto, oggi.** La guardia ombra di contraddizione (#335, read-only) ha fatto firing correttamente: 25 intenti soppressi in ombra, 4 dei quali tradabili, **tutti PANW** con «score=+0.2926 positivo, ritorno_sessione=−0.07824 ≤ −0.04». Nessuno dei 4 è stato eseguito, quindi nessun costo. Il punteggio PANW positivo alle 15:00 (**+0,670** su «Palo Alto Networks earnings beat as CEO cites $1 trillion AI security gap») è la lettura corretta del *testo* su un titolo che stava crollando del 7%: è esattamente il caso per cui la guardia esiste, e la guardia l'ha visto. Anche l'invariante rank/ranking score del ledger S4 (#401) è pulita: 71 righe esaminate, **0 violazioni**.

---

## Segnalazioni

[F-001] **45/96 simboli watchlist (46,9%) a zero righe `news_log`, e il buco cade sul secondo mover dell'universo.** RDDT +9,31% e NVO +3,66% sono i due soli miss con denaro potenzialmente sul tavolo, e sono entrambi `NO_NEWS` puri: zero righe, zero segnali. **RDDT non ha una singola riga in tutta la finestra a 10 sedute** (nessuna dal 2026-08-20); NVO ne ha 3 in 14 giorni, l'ultima il 2026-08-27. Stessa cecità su VALE +4,03%, catturata ma solo perché detenuta da S1 momentum, che le notizie non le legge: zero righe oggi e zero su tutta la finestra. Faccia lato uscita: **ASML a 9 sedute consecutive** senza una riga mentre è a −4,89% dall'ingresso (§5), e **36 posizioni su 48 a copertura *effettiva* nulla** — tre quarti del libro attraversato senza un input ticker-specifico tempestivo. Costo registrato = lordo close-to-close × 2.200 $ dei due miss NO_NEWS, 204,73 + 80,45 = **285,18 $**, per confrontabilità con la serie; l'accessibile misurato dal dossier è 60,19 + 8,50 = 68,69 $.

[F-020] **Due posizioni liquidate su articoli che non riguardano il titolo.** (a) **HOOD**: `news_log` 9508, `source_metadata`, n_ticker=**1**, mappato solo su HOOD, e il testo integrale (titolo + 91 caratteri di corpo) nomina Alumis, Sirius XM e OGE Energy e **non nomina Robinhood** — punteggio 0,000/conf 0,15 → SELL 15:07 `below_entry_gate` su un titolo che chiude +3,36%; costo = `drift_post_uscita` **5,75 $**. Percorso identico all'occorrenza dell'08-26 (Boston Scientific mappato su NVO e solo NVO via `source_metadata`), non `org_lookup`. (b) **GS**: SELL 19:07 `sentiment_reversal` su −0,497/conf 0,73 da «Goldman Sachs warns investors to expect lower returns over the next year» — Goldman come *autore* di una previsione di mercato, non oggetto di notizia; GS ha chiuso +0,19%; costo attribuibile alla decisione = drift **1,46 $** (i −34,92 $ realizzati sono una perdita preesistente dall'ingresso del 10/07 e **non** vanno attribuiti a questo difetto). Faccia aggregata: **4 su 4** dei segnali su ticker bancari oggi nascono da articoli su terzi (SiriusXM ×2, Meta, Lear). Totale **7,21 $**, confidenza attribuita. Dettaglio in §8.1 e §8.2.

[F-008] **Un pezzo macro che dichiara di non parlare di singoli titoli chiude la posizione NVDA.** Segnale 19:45, +0,028/conf 0,20, da «Next Phase Of AI–Elon Musk's 1 Billion Robots», il cui corpo contiene letteralmente «*This article is about the big picture, not an individual stock*». Alle 19:52 SELL `below_entry_gate`. Costo **0,19 $** (`drift_post_uscita`, dossier). La liquidazione HOOD della stessa giornata appartiene allo stesso pattern ma il suo costo è addebitato a **F-020**, che ne descrive il meccanismo a monte (tag su ticker non menzionato): non contarlo due volte.

[F-031] **L'anti-pyramiding blocca peso sul mover numero uno dell'universo, tre volte, con capitale disponibile.** DELL +15,81%: `SKIP_PYRAMIDING` alle 15:22, 15:52 e 16:22 con reason «già a libro dal 2026-07-13, sentiment +0,364 / +0,303 / +0,764, **peso non allocato 2,4%**». Il dossier misura il costo su orizzonte controfattuale 1h per i tre eventi causali (signal 9527, 9528, 9543): 46,98 + 30,21 + 22,15 $. I tre eventi **non sono indipendenti** (un solo slot incrementale), quindi registro il maggiore, **46,98 $**, più HOOD `SKIP_PYRAMIDING` 14:07 (**7,54 $**, nozionale inteso 720,82 $) = **54,52 $**. È un limite inferiore stretto: tenendo lo slot da 2.200 $ dal ciclo delle 15:22 (barra 15:20, open 445,70) al close 492,20 il controfattuale a fine giornata vale **229,53 $**. Il conto economico della giornata: la posizione DELL effettiva, 429,50 $ di nozionale, ha reso 28,02 $ su un movimento del 15,81%. 68 righe `SKIP_PYRAMIDING` in totale oggi.

[F-009] **Il gate 0,30 impedisce il rientro su HOOD dopo la liquidazione, per 0,040.** L'articolo ticker-specifico arriva alle 16:45 («Robinhood Stock Edges Higher Wednesday», Scotiabank inizia a $136), punteggio **+0,260** — segno corretto su un titolo che chiude +3,36% — e resta sotto il gate per cinque cicli consecutivi (16:52, 17:07, 17:22, 17:37). Terza seduta consecutiva in cui il segnale più informativo cade entro 0,04 dalla soglia (0,019 TSLA 08-31, 0,029 NOW 09-01, 0,040 HOOD oggi). Costo **24,11 $**, congetturale: slot S4 da 2.200 $ dalla barra 16:50 (open 105,83) al close 106,99, +1,10%. **Overlap dichiarato con F-020**: le due voci sono rami alternativi dello stesso percorso di prezzo (mancata uscita *oppure* rientro), non addebiti additivi — l'unione è limitata dal maggiore dei due, 24,11 $, non dalla somma. Nota su DELL: i suoi 14 cicli `SKIP_THRESHOLD` (score 0,222-0,278) col segno corretto **non** sono addebitati qui, perché nei cicli in cui il punteggio passava il vincolo binding era l'anti-pyramiding: il costo è su F-031.

[F-030] **NVDA comprata a movimento più che completo.** BUY 18:07 con `entry_percentile` 0,666 e `quota_movimento_precedente_al_segnale` **1,0676** (`denominatore_degenere: false`), `vs_apertura` +35,49 $: al momento del segnale il titolo aveva già fatto più del suo movimento di giornata. Chiusa 1,75 ore dopo a **−2,87 $** realizzati (trade 966, `net_pnl` a DB) — è il costo registrato. Seconda faccia sullo stesso asse: ORCL ha il suo unico articolo alle **19:15**, e il dossier misura `accessible_opportunity` **−4,82 $**, negativa, cioè al primo ciclo eleggibile comprare avrebbe perso: su ORCL il ritardo non è un costo d'opportunità, è l'annullamento dell'opportunità. Mediana mobile a 20 giorni dell'`entry_percentile`: 0,562.

[F-012] **Due terzi delle mappature restano non confermate, e i due titoli tradati oggi non hanno una sola riga ISSUER_SPECIFIC.** Totali del giorno: 128 righe `news_log` per 71 articoli unici, **82 mappature `TAG_UNCONFIRMED` contro 44 `ISSUER_SPECIFIC`** (64,1% non confermate), 57 mappature fan-out extra, copertura effective-timely **22/96 = 22,9%**. Il dettaglio che conta: **HOOD 2 articoli su 2 `TAG_UNCONFIRMED`** e **NVDA 9 su 9 `TAG_UNCONFIRMED`** (effective-timely 0,0 per entrambi) — cioè entrambe le posizioni movimentate oggi sono state aperte e chiuse **senza una singola riga a rilevanza confermata**. NOW ha `quota_righe_fanout = 1,0`, quarta occorrenza della firma «fan-out come unica fonte» in sei sedute (QCOM 08-31, AMZN 08-28, NOW 09-01). Concentrazione: 2 fonti sole (`alpaca_benzinga` 49 articoli, `gdelt_gkg` 22), HHI fonte 0,504. Costo `null`: non separabile dagli altri finding sugli stessi titoli.

[F-013] **Round-trip intraday su NVDA nella stessa seduta: BUY 18:07 → SELL 19:52, `ore_tenuta` 1,75.** Manifestazione dell'assenza di banda fra gate d'ingresso (0,30) e soglia d'uscita (0): a punteggio 0,028 il sistema non è "neutrale", è "fuori". Seconda faccia: HOOD liquidata a 15:07 e poi tenuta fuori a 0,260 per cinque cicli. Costo `null` per non duplicare: i −2,87 $ sono già attribuiti a F-030 (ingresso a movimento completo) e i 24,11 $ a F-009.

[F-040] **I due segnali ribassisti che superano il gate col segno corretto non producono nulla sul lato ingresso — e funzionano su quello d'uscita.** 8 righe `RANK_LONG_ONLY` oggi: PANW 5 e GS 3. Con la stessa qualificazione registrata il 09-01 su QQQ: entrambi i simboli erano **detenuti** ed entrambi sono stati chiusi per `sentiment_reversal` nella stessa seduta (PANW 18:07 +5,54 $, GS 19:07). Il vincolo long-only costa la gamba corta, non l'informazione. Costo `null`.

[F-057] **Il rilevatore di falsa entità non tocca il percorso da cui arrivano i due terzi delle righe.** Oggi `FALSE_ENTITY_MATCH` segnala **2 righe, entrambe `gdelt_gkg`/`org_lookup`** (CVX, MSFT) e **zero** su `alpaca_benzinga`/`source_metadata`, che è la fonte del 69% degli articoli unici (49 su 71). Nello stesso giorno una riga `source_metadata` con n_ticker=1 su un articolo che non menziona il ticker (§8.1) passa come `TAG_UNCONFIRMED` e viene scorata e agita. Il tag del provider non è validato da nulla: `TAG_UNCONFIRMED` 82 su 128 righe (64,1%), `ISSUER_SPECIFIC` 44, `SECTOR_MACRO` 0, `IRRELEVANT_FANOUT` 0. Costo `null`.

[F-059] **Entrambe le liquidazioni di oggi sono state decise da segnali che non basterebbero ad aprire una posizione.** HOOD chiusa su confidenza **0,15**, NVDA su confidenza **0,20**, contro `min_confidence = 0,30` richiesta per comprare. Terza occorrenza, prima con due casi nella stessa seduta e prima in cui entrambe le posizioni chiuse erano su titoli che hanno chiuso **in rialzo** (+3,36% e +3,21%). Costo `null`: addebitato a F-020 (HOOD) e F-008 (NVDA).

[F-060] **`NON_CLASSIFICATO` ricompare una seduta dopo essere stato dichiarato apparentemente risolto.** PLTR −5,81% esce dal classificatore causale come `NON_CLASSIFICATO` benché il caso sia perfettamente noto al ledger degli intent: **15 righe `SKIP_FALLBACK` sul solo PLTR** (85 in totale nella giornata), tutti e tre i suoi punteggi generati da `single:gpt-oss:20b-cloud`. Il report del 09-01 annotava che la categoria era sparita e che il difetto sembrava risolto: non era risolto, era senza casi. Costo `null`.

[F-063] **Il calendario earnings è indisponibile da tre sedute, e la seduta cieca è quella in cui i tre mover più grandi sono tutti reazioni a trimestrali.** `giorno_di_earnings` vale `None` su **1438 intent S4 su 1438**, dove `None` significa calendario non disponibile (UNKNOWN, non `False`). La serie dei dossier disponibili mostra un campo che prima funzionava e discriminava: `False` su 1494/1494 l'08-25, `False` su 1494 e **`True` su 24** l'08-26 (earnings NVDA), `False` su 1700/1700 l'08-27, poi `None` su tutto l'08-31, il 09-01 e il 09-02. Effetto: il qualificatore earnings-day della guardia ombra di contraddizione (#335) è cieco su ogni intento nella seduta in cui DELL +15,81%, PANW −9,28% e SNOW −4,37% sono tutte reazioni a earnings. Costo `null`: è perdita di capacità osservativa, non di denaro diretto; il costo è la ricorrenza. **Nuovo id giustificato**: nessuno dei 62 finding esistenti riguarda la disponibilità del calendario corporate — F-047 è la lettura *timezone* del calendario RTH Alpaca (percorso e difetto diversi), F-021 sono le finestre beat in UTC fissa, F-036 è il trigger di revisione documentato in `trading.yaml`.

---

*Report generato in sessione autonoma di analisi giornaliera. Nessuna modifica a codice, nessun ordine, nessun worker avviato, nessun commit. Gli unici file scritti sono questo report, `docs/evidence/market_daily.jsonl` e `docs/evidence/findings.json`.*
