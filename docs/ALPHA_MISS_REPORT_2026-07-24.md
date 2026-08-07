# Alpha Miss Report — 2026-07-24 (venerdì)

**Scope:** esclusivamente i 96 simboli in `config/trading.yaml → symbols.watchlist`.
**Domanda:** tra i titoli che potevamo effettivamente tradare, quali sono saliti di più il
2026-07-24, quali Alembic ha intercettato e quali no, e perché.
**Modalità:** read-only. Barre giornaliere Alpaca (`StockHistoricalDataClient`, TimeFrame.Day),
DB operativo `alembic-postgres-1`, Redis `alembic-redis-1`.
**Autore:** sessione autonoma Quant Research — generato 2026-07-25.

---

## 1. Executive summary

Giornata di **rotazione settoriale netta e violenta**: software enterprise + telecom + IT
services su, semiconduttori giù. Dispersione cross-sectional σ = 3.08% (media |ret| 2.12%),
quindi ho fissato la soglia "mover rilevante" a **|return| ≥ 3%** ≈ 1σ: 22 nomi su 96, di cui
**10 al rialzo** (unico lato tradabile — S1 e S4 sono long-only, i SELL sono solo chiusure).

Dei 10 mover al rialzo, Alembic ne ha **catturati 2** (NOW +7.44%, VZ +5.84%), ne ha **1 già in
portafoglio** (AAPL +3.53%, entrato il 07-14, nessuna azione) e ne ha **mancati 7**. La causa
prevalente dei miss è **di dati, non di logica**: 3 nomi su 7 (ADBE, T, CRM — da +4.3% a +6.1%)
hanno **zero righe in `news_log`** quel giorno, altri 3 (SAP, INFY, IBM) hanno solo articoli
generici/roundup che producono score ~0. **Nessun mover al rialzo è stato perso per filtro**: la
soglia feedback (0.35 fino alle 17:30, poi 0.30) non ha scartato alcun segnale ≥ 0.30 su un
titolo salito — lo skip più vicino è TSLA a 0.344, che è poi sceso -2.08%.

Il costo vero della giornata non è nei miss ma nel **posizionamento**: il book era lungo tutto
il complesso semis che è crollato (ARM -8.14%, INTC -7.89%, MRVL -7.21%, MU -6.99%, WDC -6.90%),
per un MTM stimato di circa **-$336 sui semis su -$280 totali di book** — cioè il resto del
portafoglio ha guadagnato mentre i semis hanno bruciato tutto e oltre.

---

## 2. Tabella completa rendimenti (96/96 simboli, nessuna barra mancante)

Legenda "Catturato": **SI** = ordine eseguito il 07-24; *held* = posizione già aperta prima del
07-24, nessuna azione quel giorno; *no* = nessuna esposizione.

| Simbolo | Return % | Intraday % (open→close) | Close 07-23 | Close 07-24 | Catturato |
|---|---:|---:|---:|---:|---|
| SAP | +9.30% | +4.07% | 146.38 | 160.00 | no |
| NOW | +7.44% | +4.07% | 91.94 | 98.78 | **SI** — S4 BUY |
| ADBE | +6.10% | +3.98% | 212.17 | 225.11 | no |
| VZ | +5.84% | +5.23% | 43.82 | 46.38 | **SI** — S4 BUY+SELL |
| TMUS | +5.67% | +4.61% | 170.42 | 180.09 | no |
| T | +5.10% | +4.91% | 22.96 | 24.13 | no |
| CRM | +4.29% | +2.05% | 156.93 | 163.66 | no |
| INFY | +4.12% | +2.11% | 10.67 | 11.11 | no |
| IBM | +3.65% | +2.35% | 206.65 | 214.19 | no |
| AAPL | +3.53% | +3.49% | 321.66 | 333.02 | held (no action) |
| HD | +2.55% | +2.43% | 324.71 | 332.98 | no |
| GM | +2.44% | +2.61% | 80.67 | 82.64 | held (no action) |
| DIS | +2.18% | +1.70% | 92.83 | 94.85 | **SI** — S4 BUY |
| MMM | +1.79% | +1.36% | 169.59 | 172.62 | no |
| MA | +1.77% | +1.54% | 530.29 | 539.66 | no |
| NFLX | +1.74% | +1.15% | 68.89 | 70.09 | no |
| NKE | +1.73% | +1.24% | 40.99 | 41.70 | no |
| CMCSA | +1.71% | +4.67% | 21.92 | 22.30 | no |
| JNJ | +1.59% | +0.75% | 259.27 | 263.40 | held (no action) |
| F | +1.55% | +1.41% | 14.15 | 14.37 | no |
| DB | +1.52% | +0.49% | 34.14 | 34.66 | no |
| SONY | +1.40% | +0.90% | 20.69 | 20.98 | no |
| GE | +1.36% | +1.00% | 349.00 | 353.73 | held (no action) |
| BAC | +1.26% | +0.85% | 61.28 | 62.05 | held (no action) |
| CSCO | +1.25% | +1.61% | 112.76 | 114.17 | held (no action) |
| NVO | +1.22% | -0.12% | 48.18 | 48.77 | no |
| V | +1.18% | +0.64% | 351.60 | 355.74 | no |
| SNOW | +1.11% | -0.31% | 265.13 | 268.06 | no |
| WMT | +0.99% | +1.25% | 108.40 | 109.47 | no |
| COST | +0.97% | +1.08% | 926.06 | 935.03 | no |
| ABBV | +0.95% | +0.32% | 256.92 | 259.36 | held (no action) |
| JPM | +0.95% | +0.73% | 349.90 | 353.21 | held (no action) |
| XLF | +0.86% | +0.86% | 55.83 | 56.31 | no |
| LLY | +0.86% | +0.14% | 1185.87 | 1196.03 | held (no action) |
| BRK.B | +0.83% | +0.71% | 490.85 | 494.93 | no |
| MCD | +0.75% | +0.37% | 262.80 | 264.76 | no |
| XLV | +0.70% | +0.06% | 161.44 | 162.57 | held (no action) |
| GOOGL | +0.65% | +0.41% | 317.69 | 319.74 | held (no action) |
| AZN | +0.59% | -0.34% | 168.27 | 169.26 | no |
| SHEL | +0.49% | -0.01% | 87.95 | 88.38 | held (no action) |
| MRK | +0.45% | -0.28% | 130.48 | 131.07 | held (no action) |
| XLE | +0.40% | +0.37% | 59.38 | 59.62 | held (no action) |
| UBS | +0.37% | +0.04% | 51.55 | 51.74 | held (no action) |
| TM | +0.35% | +0.21% | 176.80 | 177.42 | no |
| JD | +0.33% | +0.58% | 30.09 | 30.19 | no |
| ERIC | +0.32% | -0.32% | 9.31 | 9.34 | no |
| PG | +0.30% | +0.66% | 146.97 | 147.41 | no |
| C | +0.24% | -0.04% | 131.88 | 132.19 | held (no action) |
| ROKU | +0.21% | +0.12% | 141.67 | 141.97 | held (no action) |
| CVX | +0.19% | +0.17% | 194.42 | 194.79 | held (no action) |
| WFC | +0.14% | +0.42% | 86.19 | 86.31 | no |
| BA | +0.14% | -0.27% | 209.23 | 209.52 | no |
| SPY | +0.10% | +0.06% | 738.18 | 738.93 | held (no action) |
| SBUX | +0.04% | -0.62% | 103.21 | 103.25 | no |
| XOM | +0.03% | -0.03% | 156.89 | 156.94 | held (no action) |
| MSFT | +0.03% | -1.38% | 381.58 | 381.70 | no |
| RDDT | -0.03% | -0.45% | 168.78 | 168.73 | no |
| BP | -0.25% | -0.27% | 43.93 | 43.82 | held (no action) |
| VALE | -0.27% | +0.48% | 14.83 | 14.79 | held (no action) |
| IWM | -0.31% | -0.76% | 292.09 | 291.17 | **SI** — S1 BUY |
| RIO | -0.32% | -0.46% | 91.51 | 91.22 | held (no action) |
| MS | -0.33% | -0.88% | 215.18 | 214.48 | held (no action) |
| PLTR | -0.36% | -1.79% | 123.37 | 122.92 | no |
| DELL | -0.42% | -0.33% | 439.34 | 437.50 | held (no action) |
| PANW | -0.57% | -1.31% | 325.63 | 323.79 | held (no action) |
| CAT | -0.65% | -0.70% | 894.54 | 888.73 | held (no action) |
| AMZN | -0.66% | -0.97% | 233.66 | 232.11 | no |
| UNH | -0.67% | -1.06% | 423.56 | 420.74 | held (no action) |
| NVDA | -0.92% | -0.29% | 208.76 | 206.84 | no |
| QQQ | -1.12% | -0.90% | 691.96 | 684.23 | held (no action) |
| PBR | -1.21% | -0.64% | 19.00 | 18.77 | held (no action) |
| GS | -1.26% | -1.28% | 1074.72 | 1061.23 | held (no action) |
| XLK | -1.44% | -1.09% | 178.45 | 175.88 | held (no action) |
| BABA | -1.68% | -0.58% | 114.06 | 112.14 | no |
| META | -1.80% | -1.67% | 606.10 | 595.19 | no |
| PFE | -1.88% | -0.32% | 25.01 | 24.54 | no |
| TXN | -1.90% | -0.54% | 284.99 | 279.58 | **SI** — S1 BUY |
| BIDU | -1.91% | -0.88% | 107.39 | 105.34 | no |
| TSLA | -2.08% | -2.40% | 319.69 | 313.03 | no |
| QCOM | -2.42% | -1.60% | 171.11 | 166.97 | no |
| ASML | -2.55% | -1.83% | 1803.00 | 1757.09 | held (no action) |
| SPCX | -2.68% | -0.81% | 118.24 | 115.07 | no |
| AVGO | -2.69% | -1.49% | 392.47 | 381.92 | no |
| TSM | -2.93% | -1.93% | 415.58 | 403.41 | held (no action) |
| AMD | -3.29% | -4.57% | 539.69 | 521.95 | held (no action) |
| ORCL | -4.21% | -6.11% | 120.04 | 114.99 | no |
| AXP | -4.30% | +0.02% | 340.84 | 326.17 | **SI** — S4 BUY |
| SOXX | -4.40% | -3.19% | 551.24 | 527.01 | held (no action) |
| AMAT | -4.72% | -3.59% | 562.80 | 536.25 | held (no action) |
| NOK | -6.47% | -5.01% | 9.73 | 9.10 | held (no action) |
| HOOD | -6.57% | -5.16% | 101.58 | 94.91 | no |
| WDC | -6.90% | -3.47% | 558.30 | 519.80 | held (no action) |
| MU | -6.99% | -3.97% | 990.21 | 920.95 | held (no action) |
| MRVL | -7.21% | -4.28% | 209.32 | 194.23 | held (no action) |
| INTC | -7.89% | -8.01% | 100.23 | 92.32 | held (no action) |
| ARM | -8.14% | -8.05% | 283.04 | 260.01 | held (no action) |

Statistiche: mediana +0.22%, media -0.09%, σ 3.08%. 10 titoli ≥ +3%, 12 ≤ -3%.

---

## 3. Miss classificati (mover al rialzo ≥ +3% non tradati)

### Perché la soglia è ≥ +3% e solo il lato long

σ cross-sectional = 3.08%: 3% è ~1σ, taglia i 22 nomi con movimento realmente anomalo su 96.
Il lato short non è classificabile come "miss": `src/strategies/s4/strategy.py:110,144` e
`src/strategies/s1/strategy.py:228,262` emettono `OrderSide.SELL` **solo** per chiudere o
ridurre posizioni esistenti — non esiste apertura di short. Un titolo sceso -8% non era
tradabile in guadagno per costruzione.

| Simbolo | Return % | Categoria | Evidenza |
|---|---:|---|---|
| SAP | +9.30% | **THIN_NEUTRAL** | 1 solo articolo (`alpaca_benzinga`, roundup earnings di terzi: *"Booz Allen Hamilton Posts Upbeat Q1 Earnings, Joins Tenet Healthcare, SS&C Tech…"*). Segnale 15:30 UTC = **0.015**, confidence 0.20. Reasoning del modello, testuale: *"SAP is merely listed as a notable gainer with no company-specific catalyst described"*. Il catalyst reale di un +9.3% non è mai entrato nella pipeline. |
| ADBE | +6.10% | **NO_NEWS** | **0 righe in `news_log`** per ADBE il 07-24 (ultima: 1 articolo il 07-21). 0 righe in `sentiment_signals`. Nessuna riga in `execution_decisions`. Gap di copertura puro. |
| TMUS | +5.67% | **WRONG_SIGN** | 1 solo segnale, 15:00 UTC, **-0.208** (conf 0.65), da *"T-Mobile Analysts Cut Their Forecasts After Q2 Results"* (pubbl. 13:26). Reasoning: *"Bear case: Missing revenue estimates and subsequent analyst price target cuts…"*. Il titolo ha fatto +5.67% (intraday +4.61%). Segno invertito rispetto al prezzo, ed è l'unico segnale della giornata. |
| T | +5.10% | **NO_NEWS** | **0 righe in `news_log`** il 07-24 (ultime: 2 articoli il 07-22). Zero segnali, zero decisioni. |
| CRM | +4.29% | **NO_NEWS** | **0 righe in `news_log`** il 07-24 (ultime: 1 il 07-21, 2 il 07-22). Zero segnali, zero decisioni. |
| INFY | +4.12% | **THIN_NEUTRAL** (+ 1 wrong-sign) | 4 segnali: 0.000 (conf 0.10), 0.000 (conf 0.15), **-0.180**, 0.000 (conf 0.10). L'articolo sugli earnings è solo un titolo nudo — reasoning: *"provides only a headline ('Infosys Q1 Earnings Call Highlights') with no substance"*; un altro: *"INFY is not mentioned in the article"*. Copertura solo `gdelt_gkg`, nessun `alpaca_benzinga`. Skip a 0.180 vs soglia 0.300. |
| IBM | +3.65% | **THIN_NEUTRAL** | 2 segnali (`alpaca_benzinga`): -0.010 e **0.030**. Skip registrato: *"score 0.030 < feedback threshold 0.350"*. Nessun articolo con catalyst specifico. |

**AAPL (+3.53%)** è a parte: **posizione già in book** (ingresso 07-14, $775 notional), quindi
l'esposizione al movimento c'era ed è valsa ~+$27 di MTM. Il mancato *incremento* rientra in
THIN_NEUTRAL (3 segnali, max 0.048, tutti skippati sotto 0.350).

### Categorie vuote — e perché è un fatto rilevante

**(d) FILTERED — nessun caso.** Questa è l'ipotesi più naturale ("la soglia alzata dal ratchet
ci ha fatto perdere i vincitori") e i dati la smentiscono per questa giornata:

* `constraints_fired` è `[]` in **tutti** i 24 cicli — nessun cap settoriale, breadth o
  `min_stocks` ha sparato.
* Interrogando `execution_decisions` per gli skip con score ≥ 0.25, gli unici sono:
  TSLA 0.344 (×4), TM 0.300 (×2), VZ 0.280 (×2, poi ri-segnalata più alta e comprata),
  META 0.271, INTC 0.264 (×2).
* TSLA è lo skip più doloroso in apparenza (0.344 contro soglia 0.350, mancato per 0.006) ma
  **TSLA ha chiuso -2.08%**: skip corretto. Idem TM (+0.35%, irrilevante), META (-1.80%),
  INTC (-7.89%).
* Nessun titolo salito ≥ +3% ha mai prodotto uno score sopra 0.25 tranne quelli comprati.

Conclusione: il 07-24 il collo di bottiglia **non** è stato il gate di soglia. È stato l'input.

**(e) OUT_OF_STRATEGY_SCOPE — nessun caso.** Gli ETF in watchlist non sono esclusi per
costruzione: IWM è stato comprato da S1 quello stesso giorno, SOXX/QQQ/XLK/XLE/XLV/SPY sono
posizioni aperte in book. Nessun mover cade fuori scope strategico.

---

## 4. Titoli catturati: esito

Sei ordini eseguiti, tutti in 3 cicli (14:07, 17:22, 18:37). Un solo SELL.

| Simbolo | Strategia | Ora (UTC) | Entry | Close 07-24 | Da entry a close | Esito |
|---|---|---|---:|---:|---:|---|
| **NOW** | S4 (sent. **+0.810**, glm-5.2+gpt-oss) | 18:37 BUY | 98.20 | 98.78 | **+0.59%** | Aperta. Segnale ottimo, **timing tardivo**: il titolo aveva già fatto +7.44%. Catturati 0.59 punti su 7.44. |
| **VZ** | S4 (sent. +0.504) | 17:22 BUY → 19:22 SELL | 45.46 | exit 46.07 | +1.34% | **Chiusa, net +$15.89**, `exit_reason=portfolio_sell`. Unico trade chiuso della giornata, in utile. Uscita a 46.07 contro close 46.38 (~$8 lasciati sul tavolo su 27.16 azioni). |
| **AXP** | S4 (sent. **+0.638**) | 18:37 BUY | 323.05 | 326.17 | **+0.97%** | Aperta. Il titolo chiude **-4.30%** sul giorno, ma il crollo era già avvenuto in mattinata (intraday open→close +0.02%): l'ingresso è un **dip-buy dopo la discesa**, non un inseguimento. Da entry a close è in guadagno. |
| **DIS** | S4 (sent. +0.385) | 18:37 BUY | 95.19 | 94.85 | **-0.36%** | Aperta, leggermente sotto. Segnale il più debole dei quattro (conf 0.55, base: flusso di call options). |
| **TXN** | S1 momentum (peso 1.2%) | 14:07 BUY | 280.51 | 279.58 | **-0.33%** | Aperta, sotto. Nota: TXN era stato **venduto il 07-23 a -$11.75** e ricomprato il giorno dopo. |
| **IWM** | S1 momentum (peso 1.2%) | 14:07 BUY | 290.97 | 291.17 | **+0.07%** | Aperta, flat. Anche IWM era stato venduto il 07-23 (`sentiment_reversal`, -$7.05) e ricomprato il 07-24. |

Sui 4 ingressi S4, 3 su 4 sono in guadagno dall'entry al close. La qualità dei segnali S4 che
hanno superato la soglia è stata buona; il problema è **quanti pochi ne sono arrivati e quando**.

---

## 5. Pattern osservato

**Il pattern è chiarissimo e non serve forzarlo: rotazione da semiconduttori verso software
enterprise / telecom / IT services.**

* **Vincitori (top 10):** SAP, NOW, ADBE, CRM = software enterprise. VZ, TMUS, T = telecom
  (tutti e tre nei primi 6!). INFY, IBM = IT services. AAPL.
* **Perdenti (bottom 12):** ARM, INTC, MRVL, MU, WDC, AMAT, SOXX, AMD, + più su TSM, AVGO,
  ASML, QCOM. **9 dei 12 peggiori sono semis o semi-cap**, e SOXX (l'ETF del settore, -4.40%)
  conferma che è un movimento di settore e non idiosincratico. Le uniche eccezioni al tema:
  ORCL -4.21%, HOOD -6.57%, AXP -4.30%, NOK -6.47%.
* I due sottoinsiemi non si sovrappongono: **nessun** titolo software/telecom è tra i perdenti,
  **nessun** semi è tra i vincitori. Rotazione, non beta di mercato — SPY ha fatto +0.10%.

### Il book era sul lato sbagliato della rotazione

Delle 43 posizioni portate dentro il 07-24, il complesso semis/hardware (ARM, MRVL, MU, INTC,
AMAT, SOXX, AMD, TSM, ASML, WDC, XLK) pesava ~$6.9K di notional. Stima MTM sulla giornata
(return del giorno × notional di ingresso — **approssimazione**, il notional è quello di entry
e le posizioni sono driftate):

| | MTM stimato |
|---|---:|
| Complesso semis/hardware (11 posizioni) | **-$336.50** |
| Book pre-esistente totale (43 posizioni, ~$29.7K) | **-$280.04** |

Cioè: tutto il resto del portafoglio ha generato circa **+$56** e i semis hanno bruciato quel
guadagno e altri $280. Le peggiori singole: WDC -$112.89, NOK -$31.53, INTC -$29.52,
ARM -$27.75, SOXX -$26.15. Sul lato opposto, l'unica esposizione significativa al tema
vincente era AAPL (+$27.37) — e nessuna delle prime 9 posizioni in classifica dei guadagni
era software o telecom, perché il book non ne aveva.

Il danno della giornata è quindi **di posizionamento, non di segnale mancato**: anche avendo
comprato tutti e 7 i miss alle size S4 tipiche (~$1.2K l'uno), il contributo positivo sarebbe
stato dell'ordine di +$400 lordi contro -$336 di semis — cioè i miss contano, ma la
concentrazione settoriale del book conta almeno altrettanto.

---

## 6. Osservazioni operative emerse dai dati

Non sono richieste di fix. Sono fatti misurati che l'operatore può decidere se tracciare.

### 6.1 Latenza pubblicazione → ingestione: 83–119 minuti

Misurata su `news_log.published_at` vs `fetched_at` per i mover del giorno (n=24 articoli):

| Ticker | Articolo | Pubblicato | Ingerito | Lag |
|---|---|---|---|---:|
| NOW | *Why Is ServiceNow Stock Surging On Friday?* | 16:38:20 | 18:30:12 | **112 min** |
| VZ | *Crude Oil Down Over 4%; Verizon Raises Earnings Forecast* | 16:55:39 | 18:45:07 | **109 min** |
| AXP | *American Express lifts revenue growth guidance…* | 16:45:00 | 18:30:59 | **106 min** |
| INTC | *Intel Stock Slips Despite Blowout Quarter* | 16:02:44 | 18:00:07 | **117 min** |
| INTC | *Intel Just Took 14A Off Death Row* | 13:54:30 | 14:15:35 | 21 min |
| TMUS | *T-Mobile Analysts Cut Their Forecasts After Q2* | 13:26:46 | 15:00:48 | 94 min |

Mediana ~106 min. Conseguenza diretta e verificabile: l'articolo che spiegava il rally di NOW è
stato pubblicato alle 16:38, il segnale +0.810 è nato alle 18:30 e l'ordine è partito alle
18:37 — **119 minuti dopo la pubblicazione**, con il titolo già a +7.44%. Il trade ha catturato
+0.59%. È il limite strutturale che separa "segnale corretto" da "alpha catturata".

### 6.2 Rottura di provenance sul trade VZ — sembra un bug

Il trade `id=422+2` (VZ, ingresso 17:22) ha `signal_score = 0.5040` e **`signal_id = NULL`**.
Interrogando `sentiment_signals`, **non esiste alcun segnale VZ con score 0.504** — né quel
giorno né nei precedenti. I segnali VZ persistiti il 07-24 sono: 0.2800 (15:45), 0.4200 (17:16),
0.4825 (18:45), -0.1487 (19:00). Il valore usato per decidere l'ordine, 0.504, è **esattamente
1.2 × 0.4200** (il segnale delle 17:16, stesso `model_id` citato nella reason:
`ensemble:gpt-oss:20b-cloud`), ma un fattore 1.2 non compare in `src/strategies/s4/` né in
`src/workers/portfolio_scheduler.py`. Gli altri 3 trade S4 dello stesso giorno (NOW→5085,
AXP→5091, DIS→5088) hanno `signal_id` valorizzato e score che combacia al decimale.

**Questo ha l'aspetto di un bug**, ed è la stessa classe del noto disallineamento
`signal_id ↔ score`: un ordine reale eseguito su un numero che non è ricostruibile da nessuna
riga persistita. Non ho indagato oltre né aperto issue.

### 6.3 Stato feedback S1: soglia azzerata dopo 10 perdite consecutive

`feedback:state:S1` in Redis, aggiornato alle 18:30 del 07-24:

```json
{"reason": "EWMA R -0.56 <= -0.5 + 10 consecutive losses", "ewma_r": -0.5623,
 "consecutive_losses": 10, "rolling_net_pnl": -178.48,
 "threshold_before": 0.3, "threshold_after": 0.0, "scale_before": 0.2, "scale_after": 0.2}
```

La soglia d'ingresso di S1 è stata portata **da 0.30 a 0.0** dopo 10 perdite consecutive, con
`regime_scale` fermo a 0.2. `config/trading.yaml` documenta il ratchet nella direzione opposta
(`consecutive_loss_trigger: 3` → *raise* threshold, `threshold_step: 0.05`,
`threshold_max: 0.60`). **La direzione sembra invertita rispetto alla semantica documentata** —
segnalo il fatto, non propongo modifiche; è possibile che per S1 il campo "score" (che è un peso
di portafoglio, 0.0124 negli ordini reali, non un sentiment) abbia una semantica diversa che
rende la soglia non comparabile a quella di S4.

Per contesto, S4 nello stesso giorno ha fatto il percorso opposto e coerente: threshold
0.35 → 0.30 alle 17:30 per decay a 24h, scale 0.80 → 1.00.

### 6.4 Churn S1: nomi venduti il 07-23 e ricomprati il 07-24

NOW venduto il 07-23 alle 18:37 a **-$49.69**, ricomprato il 07-24 alle 18:37 (da S4, su
segnale nuovo — legittimo). TXN venduto il 07-23 a -$11.75, ricomprato il 07-24 alle 14:07.
IWM venduto il 07-23 (`sentiment_reversal`, -$7.05), ricomprato il 07-24 alle 14:07. È il
pattern di auto-churn già noto e già oggetto di mitigazioni (cooldown #71, anti-whipsaw #61);
lo riporto solo come osservazione di continuità, non come finding nuovo.

Nota su VZ: il SELL delle 19:22 riporta `[anti_whipsaw_shadow: would_suppress=True, streak=1/2]`
— in shadow mode il damping avrebbe soppresso quell'uscita. In questo caso specifico la
soppressione **non** avrebbe aiutato molto: uscita a 46.07 vs close 46.38, ~$8 di differenza.

### 6.5 Cadenza cicli: nessuna anomalia

24 cicli portfolio, dalle 14:07:00 alle 19:52:00 UTC, intervallo esatto di 15 minuti,
**zero gap > 16 minuti**. La finestra 14:07→19:52 è identica a 07-17, 07-20, 07-21 e 07-23
(24 cicli ciascuno), quindi è per design, non un troncamento. Il mercato apre alle 13:30 UTC:
i primi 37 minuti non sono coperti, e in quella finestra sono stati pubblicati gli articoli
TMUS (13:26) e AXP (13:45). Fatto, non giudizio.

Copertura news del giorno: **167 articoli su 49 ticker distinti** su 96 in watchlist — cioè
**47 simboli della watchlist non hanno avuto alcuna notizia**. Tutti i segnali del giorno sono
usciti dall'ensemble reale (`fallback_used = false` su **tutti** i segnali dei mover, modelli
`glm-5.2:cloud` + `gpt-oss:20b-cloud`): nessun fallback FinBERT su questi nomi.

---

## 7. Confronto con giorni precedenti

**Non disponibile.** Questo è il primo `docs/ALPHA_MISS_REPORT_*.md`: nessun report della stessa
famiglia esiste in `docs/`. Come richiesto, non estrapolo oltre la singola giornata. I confronti
diventeranno possibili dal secondo report in poi; le metriche che consiglio di ricalcolare
uguali per la comparabilità sono: (i) numero di mover ≥ 1σ, (ii) quota catturata, (iii) split
NO_NEWS / THIN_NEUTRAL / WRONG_SIGN / FILTERED, (iv) lag mediano published→fetched, (v) numero
di ticker della watchlist con zero news.

---

## Appendice — comandi e fonti

* Barre: Alpaca `StockHistoricalDataClient.get_stock_bars`, `TimeFrame.Day`, 2026-07-17→2026-07-25.
  96/96 simboli con barre disponibili per 07-23 e 07-24, **nessun dato mancante**.
* DB: `docker exec alembic-postgres-1 psql -U trading -d trading` — tabelle `trades`,
  `portfolio_cycles`, `execution_decisions`, `sentiment_signals`, `news_log`.
* Redis: `docker exec alembic-redis-1 redis-cli` — chiavi `feedback:*`.
* Codice consultato in sola lettura: `src/strategies/s4/strategy.py`,
  `src/strategies/s4/ranking.py`, `src/strategies/s1/strategy.py`, `config/trading.yaml`.
* Il MTM di sezione 5 è una **stima** su notional di ingresso, non una rivalutazione esatta
  delle quantità correnti.
