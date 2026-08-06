# Alpha-Miss Report — 2026-08-03 (lunedì)

Analisi limitata ai 96 simboli di `config/trading.yaml → symbols.watchlist`. Domanda: quali titoli
del nostro universo sono saliti/scesi di più il 2026-08-03, quali Alembic ha intercettato, quali no
e perché.

**Fonte prezzi:** Alpaca `StockBarsRequest`, TimeFrame.Day, close 2026-08-03 vs close 2026-07-31
(venerdì precedente; il weekend 08-01/08-02 non ha barre). **Tutti i 96 simboli hanno barre per
entrambe le date — nessun gap dati sui prezzi.**
**Fonte sistema:** `alembic-postgres-1` (`trades`, `execution_decisions`, `sentiment_signals`,
`news_log`, `portfolio_cycles`) + Alpaca `TradingClient` per equity e posizioni.
**Modalità:** read-only. Nessuna modifica a codice, configurazione o stato del sistema.

**Primo giorno del periodo di sola osservazione** (`docs/evidence/OBSERVATION_CHARTER.md`, inizio
2026-08-03). Nessuna proposta di taratura o fix in questo documento: solo evidenza.

---

## 1. Executive summary

- Soglia mover: **|return| ≥ 3%**, coerente con tutti i report 07-24 → 07-31. Dispersione
  cross-sectional σ = **2.64%**, quindi 3% ≈ 1.13σ — il punto in cui il movimento esce dalla banda
  di rumore giornaliera della watchlist.
- **19 mover su 96: 16 al rialzo, 3 al ribasso.** Giornata risk-on stretta: SPY +1.42%, QQQ +1.76%,
  ma il grosso della performance concentrata su software/hyperscaler e nomi retail ad alto beta.
- **10/19 catturati** (ORCL, META, MSFT, AMZN tradati nel giorno; DELL, GOOGL, PANW, MRVL, VALE, WDC
  già in portafoglio), **9/19 mancati**.
- Causa prevalente dei miss: **THIN_NEUTRAL 4/9** (RDDT, SNOW, BABA, TSLA — news presente, segno
  giusto, magnitudine sotto il gate 0.30), seguita da **NO_NEWS 3/9** (BA, HOOD, SAP),
  **WRONG_SIGN 1** (SPCX), **OUT_OF_STRATEGY_SCOPE 1** (AZN, unico down mover non in book: le
  strategie sono long-only). **Nessun FILTERED** (nessun segnale ≥ 0.30 scartato da ranking/breadth).
- Il caso più caro non è un miss ma una **cattura degradata**: ORCL (+9.22%, il #2 del giorno)
  comprato alle 15:37 e rivenduto alle 17:22 per **+$23.61 su $43.15 disponibili** tenendo fino
  alla chiusura. L'uscita è innescata dal capovolgimento del segnale ensemble **+0.515 → −0.343 in
  30 minuti**, prodotto da un articolo macro generico multi-ticker (§4, §7).
- **41/96 simboli (43%) senza alcuna riga in `news_log`** nella giornata.
- Realizzato del giorno **+$142.75** (tutto S4, S1 zero exit). Equity di chiusura **$109.704,03**
  (+$201,71 sul 07-31). 24 cicli portfolio, cadenza 15 min regolare 14:07→19:52 UTC, nessun gap.
- Tre segnalazioni agganciate al ledger: **[F-001]** copertura news, **[F-002]** attribuzione
  strategia NULL, **[F-008]** e **[F-009]** nuove (§7).

---

## 2. Tabella completa rendimenti (96/96 simboli)

"Catturato" = Alembic aveva esposizione al titolo durante il 2026-08-03. **sì** = ordine eseguito
quel giorno; *held* = posizione già aperta prima del 08-03, nessuna azione nel giorno; no = nessuna
esposizione.

| Simbolo | Return % | Close 07-31 | Close 08-03 | Catturato |
|---|---:|---:|---:|---|
| RDDT | +9.98% | 140.67 | 154.71 | no |
| ORCL | +9.22% | 129.87 | 141.85 | **sì** — S4 BUY+SELL |
| BA | +8.03% | 216.14 | 233.49 | no |
| META | +6.02% | 556.71 | 590.24 | **sì** — S4 BUY |
| DELL | +5.83% | 405.37 | 429.02 | sì (*held*) |
| SPCX | +5.68% | 108.37 | 114.53 | no |
| MSFT | +4.93% | 464.72 | 487.65 | **sì** — S4 SELL+BUY+SELL |
| GOOGL | +4.88% | 356.13 | 373.51 | sì (*held*) |
| SNOW | +4.86% | 293.28 | 307.53 | no |
| PANW | +4.61% | 331.83 | 347.13 | sì (*held*) |
| AMZN | +4.58% | 271.58 | 284.02 | **sì** — S4 SELL+BUY+SELL |
| HOOD | +4.37% | 86.56 | 90.34 | no |
| BABA | +4.13% | 122.25 | 127.30 | no |
| TSLA | +3.49% | 311.21 | 322.08 | no |
| MRVL | +3.31% | 187.56 | 193.78 | sì (*held*) |
| SAP | +3.28% | 183.62 | 189.65 | no |
| NVDA | +2.93% | 200.75 | 206.64 | **sì** — S4 BUY+SELL |
| ERIC | +2.75% | 9.81 | 10.08 | no |
| QCOM | +2.68% | 147.61 | 151.57 | no |
| NOW | +2.66% | 111.23 | 114.19 | no |
| TMUS | +2.54% | 172.71 | 177.09 | no |
| AXP | +2.52% | 336.25 | 344.72 | no |
| CMCSA | +2.50% | 23.96 | 24.56 | no |
| GE | +2.46% | 360.07 | 368.93 | sì (*held*) |
| HD | +2.43% | 331.96 | 340.02 | no |
| NOK | +2.41% | 9.14 | 9.36 | sì (*held*) |
| NFLX | +2.26% | 71.71 | 73.33 | no |
| NKE | +2.23% | 41.71 | 42.64 | no |
| PLTR | +2.10% | 123.06 | 125.65 | no |
| AMAT | +2.08% | 507.67 | 518.21 | sì (*held*) |
| DIS | +2.03% | 96.19 | 98.14 | no |
| CAT | +1.87% | 814.81 | 830.03 | sì (*held*) |
| INFY | +1.83% | 12.03 | 12.25 | no |
| AMD | +1.78% | 476.15 | 484.64 | sì (*held*) |
| QQQ | +1.76% | 687.99 | 700.07 | sì (*held*) |
| BIDU | +1.76% | 111.11 | 113.06 | no |
| IWM | +1.72% | 291.20 | 296.22 | sì (*held*) |
| WFC | +1.67% | 86.45 | 87.89 | no |
| XLK | +1.53% | 175.35 | 178.04 | sì (*held*) |
| T | +1.46% | 23.25 | 23.59 | no |
| SPY | +1.42% | 747.03 | 757.67 | sì (*held*) |
| DB | +1.28% | 36.70 | 37.17 | no |
| IBM | +1.19% | 223.65 | 226.31 | no |
| VZ | +1.17% | 46.81 | 47.36 | no |
| CRM | +1.05% | 184.02 | 185.95 | no |
| INTC | +0.89% | 90.20 | 91.00 | sì (*held*) |
| BAC | +0.86% | 61.95 | 62.48 | sì (*held*) |
| GS | +0.85% | 1018.38 | 1027.06 | sì (*held*) |
| C | +0.85% | 132.45 | 133.57 | sì (*held*) |
| ASML | +0.83% | 1629.00 | 1642.52 | sì (*held*) |
| MU | +0.79% | 823.03 | 829.50 | sì (*held*) |
| XLF | +0.77% | 56.94 | 57.38 | sì (*held*) |
| AVGO | +0.76% | 389.28 | 392.23 | no |
| ROKU | +0.57% | 145.01 | 145.84 | sì (*held*) |
| SOXX | +0.55% | 504.89 | 507.68 | sì (*held*) |
| MMM | +0.54% | 176.28 | 177.23 | sì (*held*) |
| TSM | +0.46% | 404.25 | 406.11 | sì (*held*) |
| MS | +0.38% | 210.42 | 211.23 | sì (*held*) |
| ADBE | +0.37% | 250.41 | 251.34 | no |
| PG | +0.33% | 144.49 | 144.97 | no |
| BRK.B | +0.31% | 511.54 | 513.14 | no |
| JPM | +0.24% | 351.79 | 352.64 | sì (*held*) |
| UNH | +0.23% | 414.40 | 415.36 | sì (*held*) |
| COST | +0.23% | 951.89 | 954.08 | no |
| PFE | +0.08% | 25.01 | 25.03 | no |
| JD | +0.03% | 33.01 | 33.02 | no |
| NVO | +0.02% | 47.08 | 47.09 | no |
| UBS | +0.02% | 52.74 | 52.75 | sì (*held*) |
| CSCO | -0.11% | 115.99 | 115.86 | sì (*held*) |
| V | -0.13% | 366.13 | 365.67 | no |
| XLV | -0.19% | 162.55 | 162.24 | sì (*held*) |
| XOM | -0.24% | 155.44 | 155.06 | sì (*held*) |
| ARM | -0.26% | 239.69 | 239.06 | **sì** — S1 BUY |
| MA | -0.37% | 573.10 | 570.97 | **sì** — S4 SELL |
| WMT | -0.44% | 111.20 | 110.71 | no |
| JNJ | -0.76% | 256.35 | 254.41 | sì (*held*) |
| SHEL | -0.98% | 91.98 | 91.08 | sì (*held*) |
| RIO | -0.98% | 96.85 | 95.90 | sì (*held*) |
| XLE | -1.28% | 59.55 | 58.79 | sì (*held*) |
| GM | -1.33% | 88.86 | 87.68 | sì (*held*) |
| TM | -1.49% | 188.99 | 186.17 | no |
| F | -1.70% | 14.68 | 14.43 | no |
| PBR | -1.75% | 19.40 | 19.06 | sì (*held*) |
| AAPL | -1.78% | 308.91 | 303.42 | sì (*held*) |
| SBUX | -1.79% | 105.25 | 103.37 | sì (*held*) |
| CVX | -1.85% | 196.83 | 193.18 | sì (*held*) |
| MRK | -1.87% | 130.20 | 127.77 | sì (*held*) |
| MCD | -2.00% | 270.64 | 265.23 | no |
| BP | -2.12% | 45.22 | 44.26 | sì (*held*) |
| ABBV | -2.33% | 250.94 | 245.10 | sì (*held*) |
| LLY | -2.39% | 1148.84 | 1121.36 | sì (*held*) |
| TXN | -2.43% | 275.74 | 269.04 | sì (*held*) |
| SONY | -2.71% | 23.26 | 22.63 | no |
| VALE | -3.19% | 15.06 | 14.58 | sì (*held*) |
| WDC | -3.23% | 544.84 | 527.22 | sì (*held*) |
| AZN | -6.88% | 169.64 | 157.97 | no |

---

## 3. Miss classificati (9 mover senza esposizione)

Il gate d'ingresso S4 attivo tutta la giornata era **0.300** (`feedback threshold 0.300`, costante
in tutte le 494 righe `SKIP_THRESHOLD` del giorno).

| Simbolo | Return% | Categoria | Evidenza |
|---|---:|---|---|
| BA | +8.03% | **NO_NEWS** | Zero righe in `news_log` per BA il 08-03. Zero righe in `sentiment_signals`. Zero righe in `execution_decisions`. Nessuna catena decisionale esiste. |
| SPCX | +5.68% | **WRONG_SIGN** | 6 articoli (tutti `alpaca_benzinga`), 6 segnali generati, **media score −0.040** su un giorno a +5.68%. Sequenza: −0.1009 (14:15), +0.12 (14:45, fallback single glm), −0.12 (16:01, fallback single gptoss), +0.11 (16:17, fallback single glm), 0.000 (16:46), **−0.2502 (19:45)** — il segnale finisce la giornata al valore negativo più estremo. 3 dei 6 segnali sono `fallback_used=t` a modello singolo, con segni opposti a 15 minuti di distanza. Titoli disponibili espliciti sull'evento ("SpaceX Q2 Earnings Preview", "SpaceX Dodges 456 Million-Share Supply Shock Ahead Of First-Ever Earnings"). |
| HOOD | +4.37% | **NO_NEWS** | Zero righe in `news_log`, `sentiment_signals`, `execution_decisions`. |
| RDDT | +9.98% | **THIN_NEUTRAL** | 1 articolo alle 14:44, titolo esplicitamente direzionale: *"Reddit Stock Gains Monday: What's Driving the Post-Earnings Rebound?"*. Segnale ensemble non-fallback **+0.1693** (conf 0.500, std 0.141) alle 15:45 — segno **giusto**, magnitudine 56% del gate. `SKIP_THRESHOLD` ripetuto (id 5819, 5845, 5872, 5899). Il mover più forte del giorno perso con la catena dati completa e corretta nel segno. |
| SNOW | +4.86% | **THIN_NEUTRAL** | 1 articolo alle 15:36: *"Snowflake Stock Surges: What's Driving the Rebound?"*. Segnale +0.1956 (conf 0.550) alle 16:30, `SKIP_THRESHOLD` a 0.156 (id 5901, 5927, 5956, 5986). Segno giusto, sotto gate. |
| BABA | +4.13% | **THIN_NEUTRAL** | 2 articoli `gdelt_gkg` (`extraction_method=org_lookup`), il secondo alle 16:15 esplicito: *"Alibaba shares climb 4% after launch of most powerful Qwen model yet"*. Primo segnale **0.000 / conf 0.100** alle 17:00; secondo **+0.2300** alle 17:30 — sotto gate (id 6002, 6028, 6052). Da notare il ritardo: la notizia è pubblicata alle 16:15, il primo segnale utile arriva 1h15 dopo. |
| SAP | +3.28% | **NO_NEWS** | Zero righe in `news_log`, `sentiment_signals`, `execution_decisions`. |
| TSLA | +3.49% | **THIN_NEUTRAL** | 1 solo articolo, e nemmeno su TSLA: *"SpaceX Could Burn Through Billions More as Elon Musk Ramps Up AI Spending With Tesla"* — TSLA è un ticker secondario in un pezzo su SpaceX. Segnale −0.0125 con **conf 0.250** alle 14:16, invariato tutto il giorno (`SKIP_THRESHOLD` id 5696, 5713, 5731, 5753, 5777). Caso di THIN corretto: la confidence bassa riflette fedelmente la qualità della fonte. |
| AZN | −6.88% | **OUT_OF_STRATEGY_SCOPE** | Unico down mover senza esposizione. S1 e S4 sono long-only: un ribasso su un titolo non in book non è tradabile per costruzione. L'unico articolo (16:45, *"Yen Intervention And Falling Oil Help Stocks…"*) è un roundup macro senza contenuto su AZN, e produce coerentemente **0.000 / conf 0.175** alle 18:45. |

**Conteggi:** NO_NEWS 3 · THIN_NEUTRAL 4 · WRONG_SIGN 1 · FILTERED 0 · OUT_OF_STRATEGY_SCOPE 1.

Nessun caso FILTERED: nessun segnale ≥ 0.30 su un mover è stato scartato da ranking, breadth
(`min_stocks`), hysteresis o dalla regola anti-fallback #108. Il gate non ha mai dovuto scegliere —
i segnali non ci sono arrivati.

---

## 4. Titoli catturati: esito

### 4.1 Tradati il 2026-08-03 (7 exit, 4 entry; realizzato totale **+$142,75**, tutto S4)

| id | Simbolo | Strat | Entry | Exit | Prezzi | qty | net P&L | exit_reason |
|---|---|---|---|---|---|---:|---:|---|
| 594 | MA | S4 | 07-31 17:22 | 08-03 14:22 | 574.14 → 575.68 | 2.146 | **+$2,63** | portfolio_sell |
| 597 | MSFT | S4 | 07-31 19:22 | 08-03 14:22 | 463.39 → 486.67 | 2.657 | **+$61,60** | portfolio_sell |
| 598 | AMZN | S4 | 07-31 19:37 | 08-03 14:22 | 271.85 → 283.35 | 4.531 | **+$51,86** | portfolio_sell |
| 640 | ORCL | S4 | 08-03 15:37 | 08-03 17:22 | 137.09 → 139.77 | 9.065 | **+$23,61** | portfolio_sell |
| 643 | NVDA | S4 | 08-03 16:52 | 08-03 19:07 | 207.13 → 208.55 | 5.998 | **+$8,29** | portfolio_sell |
| 644 | MSFT | S4 | 08-03 16:52 | 08-03 18:37 | 488.50 → 490.05 | 2.543 | **+$3,70** | portfolio_sell |
| 642 | AMZN | S4 | 08-03 16:37 | 08-03 18:22 | 284.59 → 282.60 | 4.362 | **−$8,93** | portfolio_sell |
| 641 | ARM | S1 | 08-03 16:07 | *aperta* | 237.124 → 239.06 | 1.409 | *+$2,73 MTM* | — |
| 645 | META | S4 | 08-03 19:22 | *aperta* | 593.40 → 590.24 | 2.066 | *−$6,53 MTM* | — |

Osservazioni sulla qualità della cattura:

- **I due contributi grossi (MSFT +$61,60, AMZN +$51,86) sono ereditati**, non decisi il 08-03:
  posizioni aperte il 07-31 sera che hanno incassato il gap di apertura del lunedì e sono state
  chiuse alle 14:22 dal rebalance. La quota attribuibile alla sola giornata 08-03 (dal close 07-31
  al prezzo di uscita) è +$58,31 e +$53,32.
- **ORCL è il caso costoso**: +9,22% sulla giornata, catturato per 1h45 su ~6h30 di sessione.
  Mantenendo fino alla chiusura: 9,065 × (141,85 − 137,09) = **$43,15** contro i $23,61 realizzati
  → **$19,54 lasciati sul tavolo**. Causa dell'uscita nel §7 [F-008].
- **Churn intraday su MSFT e AMZN**: entrambe vendute alle 14:22 (`[whipsaw] … S4 signal present but
  not driving a position`, score +0.000 e −0.150) e **ricomprate più care nello stesso giorno**
  (MSFT venduta 486,67 → ricomprata 488,50; AMZN venduta 283,35 → ricomprata 284,59), poi rivendute
  entro 1h45. In aggregato però l'uscita anticipata **non** è costata: sommando i 4 trade intraday,
  tenere fino alla chiusura avrebbe reso solo **+$8,89** in più (ORCL +$19,54 e AMZN +$6,44 a favore
  del hold; MSFT −$5,86 e NVDA −$11,23 a favore dell'uscita). L'effetto è concentrato su ORCL, non
  sistematico oggi.
- **META comprata alle 19:22 UTC**, 38 minuti prima della chiusura, a 593,40 su un close di 590,24
  — ingresso *sopra* il close, dopo che il +6,02% era già avvenuto. Stesso pattern segnalato il
  07-30 (ARM/INFY/HOOD comprati alle 19:52).

### 4.2 Mover già in portafoglio, nessuna azione il 08-03

| Simbolo | Return% | Strat | Aperta il | MTM giornata |
|---|---:|---|---|---:|
| DELL | +5.83% | S1 | 07-13 | **+$21,98** |
| GOOGL | +4.88% | *NULL* | 07-10 | **+$33,41** |
| PANW | +4.61% | S1 | 07-13 | **+$34,80** |
| MRVL | +3.31% | S1 | 07-14 | **+$9,65** |
| VALE | −3.19% | S1 | 07-14 | **−$25,44** |
| WDC | −3.23% | S4 | 07-21 | **−$52,53** |

WDC è il peggiore contributo del book (−$52,53) e aveva un segnale a **+0.146** tutta la giornata
(`SKIP_THRESHOLD` ripetuto): il segnale era positivo mentre il titolo perdeva il 3,23%, ma essendo
sotto gate non ha prodotto né aggiunta né uscita — nessuna decisione errata, solo assenza di
decisione.

### 4.3 Book e cicli

| Voce | Valore |
|---|---|
| Equity chiusura 08-03 (Alpaca) | **$109.704,03** |
| Equity chiusura 07-31 | $109.502,32 |
| Delta equity | **+$201,71** |
| Realizzato del giorno | **+$142,75** (S1 **$0,00**, S4 **+$142,75**) |
| MTM book aperto a fine giornata | **−$6,89** |
| Posizioni aperte a fine giornata | 49 (DB e Alpaca coincidono esattamente) |
| Cicli portfolio | 24, cadenza 15 min esatta 14:07 → 19:52 UTC, nessun gap > 16 min |
| Ordini per ciclo | 47–51, `constraints_fired` vuoto su tutti i cicli |
| `execution_decisions` | 494 SKIP_THRESHOLD, 7 SELL, 6 BUY, 1 SKIP_STALE |
| `sentiment_signals` | 202 righe su 56 simboli, **73 (36%) `fallback_used=t`** |

**Nota di riconciliazione (non un'accusa di difetto):** il MTM del book aperto è calcolato marcando
ogni posizione dal close 07-31 (o dal prezzo di ingresso, se aperta il 08-03) al close 08-03, e vale
−$6,89. Sommato alla quota di giornata dei trade chiusi (+$145,26 lordi) dà ≈ +$138, contro i
+$201,71 di delta equity Alpaca. Il residuo (~$64) non è stato riconciliato: può derivare dai mark
ufficiali Alpaca alle 16:00 ET, diversi dal close delle barre daily usate qui. **Non lo dichiaro un
difetto** — è un limite del metodo di calcolo di questo report, segnalato per trasparenza.

Il MTM del book aperto è **negativo in una giornata SPY +1,42%** perché il book è largamente
esposto a value/energy/healthcare (LLY −$18,96, TXN −$18,03, ABBV −$16,82, WDC −$52,53, VALE
−$25,44) mentre il rialzo del giorno è concentrato in software/hyperscaler, dove il book è presente
solo su PANW, DELL, GOOGL e QQQ/XLK.

---

## 5. Pattern osservato

**Rotazione settoriale netta e leggibile: dentro software/hyperscaler + retail ad alto beta, fuori
da difensivi, energia e materie prime.**

| Blocco | Nomi | Lettura |
|---|---|---|
| **Software / hyperscaler** (su) | ORCL +9,22%, META +6,02%, MSFT +4,93%, GOOGL +4,88%, SNOW +4,86%, PANW +4,61%, AMZN +4,58%, SAP +3,28%, NOW +2,66% | Il tema dominante. Coerente con la scia degli earnings big-tech del 07-31. |
| **Retail / high-beta** (su) | RDDT +9,98%, HOOD +4,37%, SPCX +5,68%, TSLA +3,49% | Rimbalzo post-earnings (RDDT) e pre-earnings (SPCX). Blocco a beta alto, tipicamente il primo a muoversi in un risk-on. |
| **Semiconduttori** (fermi) | NVDA +2,93%, AMD +1,78%, AVGO +0,76%, TSM +0,46%, SOXX +0,55%, MU +0,79%, ASML +0,83% | **Notevole**: i semis non partecipano. È l'inverso esatto del 07-30 (melt-up semis) e del 07-28/07-29 (sell-off semis). |
| **Hardware** (spaccato) | DELL +5,83% vs WDC −3,23% | Non un blocco coerente. |
| **Difensivi / energia / materie prime** (giù) | AZN −6,88%, VALE −3,19%, SONY −2,71%, TXN −2,43%, LLY −2,39%, ABBV −2,33%, BP −2,12%, MCD −2,00%, MRK −1,87%, CVX −1,85%, XLE −1,28% | La gamba corta della rotazione, coerente e diffusa. |

Il pattern **è chiaro**: la dispersione non è idiosincratica, è una rotazione. Il book Alembic sta
prevalentemente dalla parte sbagliata di questa rotazione (S1 detiene 12 nomi energy/healthcare/
materials contro 4 software), il che spiega perché il MTM del book aperto sia negativo in una
giornata di mercato positiva.

---

## 6. Confronto con i giorni precedenti

Confronto con `docs/ALPHA_MISS_REPORT_2026-07-{24,27,28,29,30,31}.md`.

1. **NO_NEWS non è più la causa dominante, ma non è migliorata.** Serie della causa prevalente:
   07-27 NO_NEWS 7/14 (50%) → 07-28 NO_NEWS 9/26 → 07-29 NO_NEWS 12/25 (48%) → 07-31 FILTERED e
   THIN_NEUTRAL a pari merito → **08-03 THIN_NEUTRAL 4/9**. La copertura news assoluta resta
   invariata: 41/96 zero-news oggi contro 55/96 il 07-31. Oggi NO_NEWS pesa meno solo perché i
   mover erano concentrati su nomi coperti.
2. **Gli stessi ticker ricadono in NO_NEWS.** **BA** è NO_NEWS il 07-29, il 07-30 e di nuovo oggi
   (08-03, +8,03%). **SAP** è mancato per assenza o genericità di news il 07-24 (+9,30%), il 07-27
   (+6,83%), il 07-28 (+4,77%) e oggi (+3,28%). Non è casualità di copertura: sono buchi
   sistematici dello stesso set di ticker.
3. **La cattura degradata è il pattern più persistente.** 07-30: MSFT +15,51% catturato per
   +$1,04 di MTM (aperto 14:37, chiuso 17:22). 08-03: ORCL +9,22% catturato per $23,61 su $43,15,
   aperto 15:37, chiuso 17:22. Stessa forma, stessa durata (~2h45 e ~1h45), stesso esito: si
   partecipa a una frazione del movimento del giorno.
4. **Gli ingressi di fine sessione ricorrono.** 07-30: ARM/INFY/HOOD comprati alle 19:52 UTC.
   08-03: META comprata alle 19:22 a un prezzo superiore al close.
5. **Il tasso di fallback resta alto.** 36% dei segnali oggi (73/202), coerente con il collo di
   bottiglia già noto della divergenza d'ensemble.

Non estendo l'inferenza oltre questi cinque punti: sono 6 giorni di borsa osservati, sotto la
finestra di 40 giorni della carta.

---

## 7. Segnalazioni (agganciate al ledger `docs/evidence/findings.json`)

Nessuna proposta di taratura o di fix — periodo di sola osservazione.

**[F-001] Copertura news bassa sulla watchlist.** 41/96 simboli (43%) senza alcuna riga in
`news_log` il 08-03. Tre dei nove miss del giorno sono NO_NEWS puri: **BA +8,03%**, **HOOD +4,37%**,
**SAP +3,28%** — zero righe in `news_log`, zero in `sentiment_signals`, zero in
`execution_decisions`. Per questi tre nomi non esiste alcuna catena decisionale da valutare: il
sistema non ha saputo che il titolo esistesse. Costo stimato dell'occorrenza: **$345** (size S4
tipica $2.200 × 15,68% di movimento aggregato non catturato). BA e SAP sono recidivi (§6.2).

**[F-002] Attribuzione strategia NULL su trade legacy.** 12 delle 49 posizioni aperte a fine
giornata hanno `trades.stop_strategy` NULL (BAC, BP, GOOGL, GS, MS, PBR, RIO, ROKU, SPY, UBS, UNH,
XLE, tutte aperte il 07-10). Contribuiscono **+$16,69** di MTM oggi, di cui **+$33,41 da GOOGL** —
che è un mover del giorno (+4,88%) contato come "catturato" in §2 ma **non attribuibile ad alcuna
strategia**. Confligge direttamente con la domanda di uscita 2 della carta (split del P&L economico
S1 vs SPY): finché queste 12 posizioni restano aperte, una fetta del book resta fuori da qualsiasi
attribuzione. Costo non stimabile: è un difetto di misura, non di P&L.

**[F-008] *(nuovo)* Un articolo macro generico multi-ticker inverte un segnale ticker-specifico e
forza l'uscita.** Catena completa su ORCL, il #2 mover del giorno:
- 14:37 — `news_log`: *"What Is Going on With Oracle Stock on Monday?"* (`alpaca_benzinga`,
  ticker-specifico).
- 15:31 — `sentiment_signals`: **+0.5151** (conf 0.775, ensemble non-fallback, std 0.071).
- 15:37 — `execution_decisions` id 5810: **BUY**, *"S4 news-driven: sentiment +0.515 … portfolio
  weight 2.0%"*. Trade 640, 9,065 azioni a 137,09.
- 15:05 — `news_log`, secondo articolo su ORCL: *"Amazon, Alphabet Lead 'AI Debt Tsunami' Now Blamed
  for 20-Year-High Rates"* — **pezzo macro sul costo del debito AI, taggato contemporaneamente a
  ORCL e SPCX**, senza contenuto specifico su Oracle.
- 16:01 — `sentiment_signals`: **−0.3428** (conf 0.650, std 0.141). Il segnale si è capovolto di
  0,858 punti in 30 minuti.
- 17:22 — `execution_decisions` id 5997: **SELL**, *"[whipsaw] Portfolio rebalance: weight 0.0% —
  S4 signal present but not driving a position (score=−0.343…)"*. Uscita a 139,77.

ORCL chiude a 141,85. Realizzato **+$23,61** contro **$43,15** tenendo fino alla chiusura →
**$19,54** di costo attribuito, con controfattuale corto (stesso giorno, stessa size, stesso
strumento). Lo stesso articolo "AI Debt Tsunami" è taggato anche su SPCX, che quel giorno finisce in
WRONG_SIGN (§3). **Questo mi sembra un difetto, non un limite noto**: la pipeline tratta un roundup
macro multi-ticker con lo stesso peso di un pezzo ticker-specifico, e il secondo segnale sovrascrive
il primo invece di aggiungersi. La decisione se aprire un'issue è dell'operatore — non la apro io.
*Nota:* in aggregato sui 4 trade intraday del giorno l'uscita anticipata è costata solo $8,89 (§4.1),
quindi il costo è concentrato su questo singolo caso, non diffuso.

**[F-009] *(nuovo)* Il gate d'ingresso S4 a 0.30 scarta segnali col segno corretto su mover forti;
il collo di bottiglia è la magnitudine, non il segno.** Non è un riconteggio della categoria
THIN_NEUTRAL (già in `market_daily.jsonl`): l'affermazione strutturale è che su questi nomi la
pipeline **ha prodotto la risposta direzionale giusta** e l'ha scartata per calibrazione della
magnitudine.
- **RDDT +9,98%** (il mover più forte del giorno): 1 articolo con titolo esplicitamente direzionale
  (*"Reddit Stock Gains Monday: What's Driving the Post-Earnings Rebound?"*), segnale ensemble
  non-fallback **+0.1693** — segno giusto, 56% del gate. `SKIP_THRESHOLD` id 5819/5845/5872/5899.
- **SNOW +4,86%**: *"Snowflake Stock Surges: What's Driving the Rebound?"*, segnale **+0.1956**,
  `SKIP_THRESHOLD` id 5901/5927/5956/5986.
- **BABA +4,13%**: *"Alibaba shares climb 4% after launch of most powerful Qwen model yet"*,
  segnale **+0.2300**, `SKIP_THRESHOLD` id 6002/6028/6052.

In tutti e tre i casi il titolo dell'articolo afferma il movimento in modo non ambiguo e l'ensemble
restituisce un punteggio del segno corretto ma di magnitudine insufficiente. Costo stimato
dell'occorrenza: **$417** ($2.200 × (9,98% + 4,86% + 4,13%)). **Il gate è taratura, quindi congelato
dalla carta**: registro l'evidenza, non propongo di muoverlo. Rilevante direttamente per la domanda
di uscita 1 (esiste alpha nella news editoriale?): la risposta di oggi è che il segnale c'è ed è del
segno giusto — è la scala a non passare.

---

*Report generato in modalità read-only da sessione autonoma Quant Research, 2026-08-04. Nessuna
modifica a codice, configurazione, ordini o stato del sistema.*
