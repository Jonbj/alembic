# Alpha Miss Report — 2026-08-04

Analista: sessione autonoma Quant Research. Perimetro: **solo** i 96 simboli di
`config/trading.yaml → symbols.watchlist`. Periodo di sola osservazione (carta del 2026-08-01,
giorno 2 di 40): nessuna proposta di taratura, solo registrazione di evidenza.

Fonti: barre giornaliere e 15m Alpaca (feed **IEX** — il feed SIP non è nella sottoscrizione,
cfr. F-016), `alembic-postgres-1`, `docker compose logs worker`.

---

## 1. Executive summary

Giornata di rally violento su semiconduttori/AI: SPY +1.77%, QQQ +3.37%, dispersione
cross-sectional σ = 4.40% (contro 2.64% il 08-03). **29 mover ≥ 3%** su 96, 27 al rialzo e 2 al
ribasso. **20 catturati, 9 mancati.** Causa prevalente dei miss: **NO_NEWS (5 su 9)** — QCOM,
HOOD, NOW, RDDT, SAP hanno zero righe in `news_log`; 42 dei 96 simboli (44%) non hanno alcuna
copertura in giornata. Il book era strutturalmente lungo il tema giusto: le posizioni S1 aperte a
metà luglio su semis (ARM, MRVL, INTC, AMD, MU, DELL, AMAT, TXN, ASML, SOXX, XLK, PANW, CSCO, WDC)
producono +819 $ di mark-to-market, mentre il realizzato del giorno è −57,98 $ per due uscite S1
in perdita (SBUX, ABBV) e una S4 (META). Equity di chiusura 110.366,23 $ (+662 $ sul 08-03).
Osservazione che pesa più dei singoli miss: **in media il 55% del movimento dei mover è avvenuto
nel gap di apertura**, che nessuna strategia intraday può catturare (PLTR +29,17% totale = +15,30%
gap + 12,03% intraday). Difetto nuovo isolato: la **latenza di ingestione news (mediana 1h50m)
consuma il 92% della finestra di freschezza d'ingresso (2,0h)**, e 28-31 segnali per ciclo vengono
scartati da quel gate.

---

## 2. Rendimenti completi della watchlist (2026-08-04)

Barre disponibili per **tutti i 96 simboli**, nessun buco dati.
"Catturato" = simbolo in portafoglio quel giorno o tradato quel giorno.

| # | Simbolo | Prev close | Close | Return % | Catturato |
|---:|---|---:|---:|---:|:--:|
| 1 | PLTR | 125.89 | 162.61 | **+29.17** | sì (BUY 19:37) |
| 2 | ARM | 238.98 | 280.63 | **+17.43** | sì (S1) |
| 3 | MRVL | 193.74 | 218.47 | **+12.77** | sì (S1) |
| 4 | INTC | 90.99 | 100.91 | **+10.90** | sì (S1) |
| 5 | SPCX | 114.44 | 125.95 | **+10.06** | **no** |
| 6 | DELL | 429.12 | 467.13 | **+8.86** | sì (S1) |
| 7 | AMD | 484.00 | 525.52 | **+8.58** | sì (S1) |
| 8 | MU | 829.01 | 891.84 | **+7.58** | sì (S1) |
| 9 | QCOM | 151.57 | 162.67 | **+7.32** | **no** |
| 10 | SOXX | 507.84 | 542.04 | **+6.73** | sì (S1) |
| 11 | AVGO | 392.32 | 418.06 | **+6.56** | **no** |
| 12 | NOK | 9.36 | 9.93 | **+6.15** | sì (S1) |
| 13 | CAT | 831.04 | 877.09 | **+5.54** | sì (S1) |
| 14 | AMAT | 518.14 | 546.60 | **+5.49** | sì (S1) |
| 15 | PANW | 347.28 | 366.17 | **+5.44** | sì (S1) |
| 16 | TXN | 268.93 | 283.48 | **+5.41** | sì (S1) |
| 17 | CSCO | 115.87 | 121.73 | **+5.06** | sì (S1) |
| 18 | XLK | 178.09 | 186.86 | **+4.92** | sì (S1) |
| 19 | ASML | 1642.07 | 1710.74 | **+4.18** | sì (S1) |
| 20 | IBM | 226.13 | 235.09 | **+3.96** | **no** |
| 21 | WDC | 527.52 | 548.37 | **+3.95** | sì (S4) |
| 22 | HOOD | 90.36 | 93.50 | **+3.48** | **no** |
| 23 | NOW | 114.19 | 118.14 | **+3.45** | **no** |
| 24 | QQQ | 700.10 | 723.69 | **+3.37** | sì (S1) |
| 25 | RIO | 95.85 | 99.02 | **+3.31** | sì (legacy) |
| 26 | RDDT | 154.87 | 159.97 | **+3.30** | **no** |
| 27 | SAP | 189.80 | 195.54 | **+3.02** | **no** |
| 28 | SNOW | 307.54 | 316.62 | +2.95 | no |
| 29 | INFY | 12.25 | 12.60 | +2.86 | no |
| 30 | MS | 211.25 | 217.06 | +2.75 | sì (legacy) |
| 31 | ORCL | 141.84 | 145.72 | +2.74 | no |
| 32 | CRM | 185.96 | 190.98 | +2.70 | no |
| 33 | TSM | 406.12 | 417.08 | +2.70 | sì (S1) |
| 34 | GS | 1027.03 | 1053.13 | +2.54 | sì (legacy) |
| 35 | NVDA | 206.72 | 211.96 | +2.53 | no |
| 36 | ADBE | 251.38 | 257.48 | +2.42 | no |
| 37 | HD | 340.12 | 348.37 | +2.42 | no |
| 38 | C | 133.57 | 136.80 | +2.42 | sì (S1) |
| 39 | MMM | 177.24 | 181.44 | +2.37 | sì (S1) |
| 40 | GE | 369.00 | 377.15 | +2.21 | sì (S1) |
| 41 | PG | 144.97 | 148.00 | +2.09 | no |
| 42 | AAPL | 303.41 | 309.33 | +1.95 | sì (S1) |
| 43 | IWM | 296.15 | 301.71 | +1.88 | sì (S1) |
| 44 | VALE | 14.57 | 14.83 | +1.78 | sì (S1) |
| 45 | TM | 186.12 | 189.41 | +1.77 | no |
| 46 | SPY | 757.72 | 771.11 | +1.77 | sì (legacy) |
| 47 | ERIC | 10.09 | 10.26 | +1.68 | no |
| 48 | TSLA | 322.08 | 327.37 | +1.64 | no |
| 49 | CMCSA | 24.55 | 24.95 | +1.63 | no |
| 50 | BA | 233.41 | 237.12 | +1.59 | no |
| 51 | SBUX | 103.40 | 104.94 | +1.49 | sì (S1, roundtrip) |
| 52 | PFE | 25.05 | 25.40 | +1.42 | sì (S4, roundtrip) |
| 53 | JPM | 352.65 | 357.52 | +1.38 | sì (S1) |
| 54 | BABA | 127.27 | 128.99 | +1.35 | no |
| 55 | UBS | 52.76 | 53.46 | +1.33 | sì (legacy) |
| 56 | GOOGL | 373.51 | 377.68 | +1.12 | sì (legacy) |
| 57 | MSFT | 487.57 | 492.83 | +1.08 | no |
| 58 | V | 365.64 | 369.53 | +1.06 | no |
| 59 | ROKU | 145.88 | 147.35 | +1.01 | sì (legacy) |
| 60 | MCD | 265.68 | 268.34 | +1.00 | sì (BUY 18:37) |
| 61 | XLF | 57.37 | 57.86 | +0.86 | sì (S1) |
| 62 | DB | 37.17 | 37.49 | +0.86 | no |
| 63 | WMT | 110.70 | 111.54 | +0.75 | no |
| 64 | BRK.B | 513.02 | 516.88 | +0.75 | no |
| 65 | GM | 87.67 | 88.31 | +0.72 | sì (S1) |
| 66 | BAC | 62.49 | 62.91 | +0.67 | sì (legacy) |
| 67 | AXP | 344.77 | 346.71 | +0.56 | no |
| 68 | WFC | 87.89 | 88.34 | +0.52 | no |
| 69 | NFLX | 73.31 | 73.54 | +0.31 | no |
| 70 | MRK | 127.74 | 128.04 | +0.23 | sì (S1) |
| 71 | JNJ | 254.41 | 254.94 | +0.21 | sì (S1) |
| 72 | TMUS | 177.06 | 177.23 | +0.10 | no |
| 73 | MA | 571.03 | 571.20 | +0.03 | no |
| 74 | DIS | 98.15 | 98.16 | +0.01 | no |
| 75 | XLV | 162.25 | 162.08 | −0.10 | sì (S1) |
| 76 | JD | 33.02 | 32.97 | −0.17 | no |
| 77 | LLY | 1121.18 | 1117.47 | −0.33 | sì (S1) |
| 78 | META | 590.15 | 587.83 | −0.39 | sì (S4, chiusa) |
| 79 | BIDU | 113.06 | 112.61 | −0.40 | no |
| 80 | XLE | 58.78 | 58.52 | −0.44 | sì (legacy) |
| 81 | ABBV | 245.09 | 243.70 | −0.57 | sì (S1, roundtrip) |
| 82 | COST | 954.19 | 948.08 | −0.64 | no |
| 83 | XOM | 155.07 | 153.97 | −0.71 | sì (S1) |
| 84 | VZ | 47.34 | 46.87 | −0.99 | no |
| 85 | T | 23.60 | 23.36 | −1.00 | no |
| 86 | SONY | 22.63 | 22.36 | −1.19 | no |
| 87 | SHEL | 91.08 | 89.81 | −1.39 | sì (S1) |
| 88 | CVX | 193.17 | 190.42 | −1.42 | sì (S1) |
| 89 | F | 14.43 | 14.22 | −1.46 | no |
| 90 | AZN | 158.00 | 155.51 | −1.57 | no |
| 91 | UNH | 415.38 | 407.73 | −1.84 | sì (legacy) |
| 92 | PBR | 19.07 | 18.71 | −1.86 | sì (legacy) |
| 93 | AMZN | 284.12 | 277.38 | −2.37 | no |
| 94 | NKE | 42.63 | 41.51 | −2.63 | no |
| 95 | BP | 44.22 | 42.45 | **−4.00** | sì (legacy, avverso) |
| 96 | NVO | 47.09 | 44.24 | **−6.05** | sì (BUY 18:52, segno errato) |

**Soglia scelta: |return| ≥ 3%.** Motivazione: è la soglia già codificata in
`market_daily.jsonl` (`mover_3pct`) e usata nei sei report precedenti, quindi mantiene la serie
confrontabile. Va però letta sapendo che oggi è un filtro debole: con σ = 4.40% il 3% vale 0,68σ e
seleziona il 30% della watchlist, contro il 20% del 08-03. Il gruppo davvero anomalo è quello
≥ 5% (16 nomi), tutti semiconduttori o hardware AI tranne CAT e PLTR.

---

## 3. Miss classificati

| Simbolo | Return % | (di cui gap / intraday) | Categoria | Evidenza |
|---|---:|---|---|---|
| SPCX | +10.06 | +2.43 / +7.45 | **FILTERED** | 7 articoli in `news_log`, 5 segnali a ≈0.000. L'unico segnale utile, id 6476 (+0.4500, conf 0.750) alle 19:16:16, viene da un articolo pubblicato alle 17:16:39: al ciclo 19:22 ha già 2h06m ed è scartato dal gate `entry-freshness` (#150, `news_age_hours=2.0`). Log 19:22:10 e 19:37:38: "S4: dropped 30 signal(s) below entry-freshness". Sarebbe comunque caduto sul filtro #108 (`fallback_used=true`, `single:gpt-oss:20b-cloud`). In più `S1 compute_signal` scarta SPCX come sparse/stale-tailed a ogni ciclo. Ultimo segnale del giorno −0.3001 (19:45), `SKIP_THRESHOLD` id 6577. |
| QCOM | +7.32 | +3.47 / +3.73 | **NO_NEWS** | Zero righe in `news_log` il 08-04. Zero in `sentiment_signals`. Zero in `execution_decisions`. Nessuna catena decisionale esistente. |
| AVGO | +6.56 | +2.71 / +3.74 | **THIN_NEUTRAL** | 4 articoli, massimo segnale +0.2762 (conf 0.600, ensemble non-fallback, id 6379, 16:45) — segno corretto ma sotto il gate 0.300. `SKIP_THRESHOLD` id 6552 a 0.133. L'articolo è "Big Tech's $1.2 Trillion Hyperscaler AI Bet Could Ignite the Next Semiconductor ETF Rally", pezzo di settore taggato in fan-out anche ad AMAT e SOXX: non è una notizia su Broadcom. |
| IBM | +3.96 | −1.07 / +5.08 | **THIN_NEUTRAL** | Un solo articolo, "Why Is Rigetti Stock Surging on Tuesday?" (id 6478) — un pezzo su Rigetti taggato a IBM in fan-out. Segnale 0.0000, conf 0.400, `fallback_used=true`. Nessuna notizia IBM-specifica in tutta la giornata. |
| HOOD | +3.48 | +2.62 / +0.84 | **NO_NEWS** | Zero righe in `news_log`, zero segnali, zero decisioni. Già NO_NEWS anche il 08-03. |
| NOW | +3.45 | −1.63 / +5.17 | **NO_NEWS** | Zero righe in `news_log`, zero segnali, zero decisioni. Il movimento è interamente intraday: era catturabile. |
| RDDT | +3.30 | −0.42 / +3.74 | **NO_NEWS** | Zero righe in `news_log`. Già NO_NEWS il 07-31 (quando fece −20.99%) e il 08-03 non produsse ordine per magnitudine sotto gate. Terzo giorno consecutivo di miss su questo ticker. |
| SAP | +3.02 | +0.45 / +2.56 | **NO_NEWS** | Zero righe in `news_log`. Già NO_NEWS il 08-03 e mancato per assenza/genericità di news anche il 07-24, 07-27, 07-28. |
| BP | −4.00 | −2.26 / −1.78 | **WRONG_SIGN** | Segnale id 6398 alle 17:15: **+0.6458, conf 0.860**, ensemble non-fallback, da "BP's Q2 Profit Doubles Amid Middle East Conflict, but It Cuts Production, Capex Outlook". Il titolo è esplicitamente misto (utile raddoppiato *ma* taglio di produzione e capex) e il mercato ha prezzato la seconda metà: −4.00%. Nessun ordine perché BP è già in book dal 07-10 e il guard P0-05 (no pyramiding) blocca il BUY. Strategie long-only: nessuna perdita aggiuntiva oltre il MTM della posizione esistente (−29,51 $). |

**Conteggi:** NO_NEWS 5 · THIN_NEUTRAL 2 · WRONG_SIGN 1 · FILTERED 1 · OUT_OF_STRATEGY_SCOPE 0.

Nota su OUT_OF_STRATEGY_SCOPE: i tre ETF fra i mover (SOXX +6.73%, XLK +4.92%, QQQ +3.37%) sono
tutti in book come posizioni S1, quindi non sono fuori scope per costruzione — la categoria resta
a zero per questa giornata.

---

## 4. Titoli catturati: esito

### 4.1 Trade chiusi il 2026-08-04 (realizzato −57,98 $)

| id | Simbolo | Strat | Entry | Exit | qty | net P&L | exit_reason |
|---:|---|---|---|---|---:|---:|---|
| 595 | SBUX | S1 | 07-31 17:52 @ 105.827 | 08-04 14:22 @ 102.210 | 6.842 | **−25,14 $** | `portfolio_sell` (`[s1_weight_drop]`) |
| 645 | META | S4 | 08-03 19:22 @ 593.40 | 08-04 14:22 @ 582.05 | 2.066 | **−23,69 $** | `portfolio_sell` (`[expired]`, età 19,1h > 4h) |
| 646 | PFE | S4 | 08-04 14:07 @ 25.11 | 08-04 15:52 @ 25.46 | 48.266 | **+16,22 $** | `portfolio_sell` (`[whipsaw]`, score sceso a +0.018) |
| 596 | ABBV | S1 | 07-31 18:07 @ 251.31 | 08-04 17:52 @ 242.640 | 2.881 | **−25,37 $** | `portfolio_sell` (`[s1_weight_drop]`) |

Realizzato per strategia: **S1 −50,51 $**, **S4 −7,47 $**.

Due dettagli di churn, già coperti da F-013 (non ri-registrati oggi):
- **PFE** comprata alle 14:07 a 25.11, venduta alle 15:52 a 25.46 e **ricomprata alle 18:37 a
  25.44**: roundtrip completo e rientro 2 centesimi sotto il prezzo di uscita. Chiude a 25.40.
- **SBUX** e **ABBV** vendute per `s1_weight_drop` e ricomprate lo stesso giorno (14:37 e 18:52).
  Su SBUX il rientro è a 102.62 contro un'uscita a 102.21, su ABBV a 243.91 contro 242.64: in
  entrambi i casi si è ricomprato **più caro** di quanto si era venduto poche ore prima.

### 4.2 Nuovi ingressi del 2026-08-04

| Simbolo | Ora | Prezzo | Score | Close | MTM | Nota |
|---|---|---:|---:|---:|---:|---|
| PFE | 18:37 | 25.44 | +0.5144 | 25.40 | −1,80 $ | secondo ingresso della giornata |
| MCD | 18:37 | 265.33 | +0.4712 | 268.34 | +12,99 $ | earnings beat, articolo ticker-specifico |
| NVO | 18:52 | 44.00 | +0.6557 | 44.24 | +6,23 $ | **segno errato sul giorno** (vedi sotto) |
| PLTR | 19:37 | 162.90 | +0.3834 | 162.61 | −2,02 $ | **il mover #1, comprato 23 minuti prima della chiusura** |

**NVO** merita una riga a sé. Il segnale +0.6557 (conf 0.850, ensemble) nasce da un comunicato
societario reale e corretto ("Novo Nordisk raises adjusted sales and adjusted operating profit
outlook for 2026"), ma il titolo ha chiuso **−6.05%**, con −7.02% dall'apertura. L'ingresso alle
18:52 a 44.00 è avvenuto vicino ai minimi, quindi il MTM immediato è positivo (+6,23 $): il segno
del segnale è opposto al movimento del giorno, ma l'esecuzione tardiva ha di fatto neutralizzato
il danno. Registrato come esito, non come costo.

**PLTR** è il caso più istruttivo della giornata e va letto insieme al §5: il +29,17% si scompone
in **+15,30% di gap** (125.89 → 145.15 in apertura) e **+12,03% intraday** (145.15 → 162.61). Il
prezzo era già a 162.56 alle 17:00, cioè il 96% del movimento intraday era finito prima delle 17.
L'ingresso alle 19:37 a 162.90 ha catturato **zero**. Il segnale ticker-specifico su PLTR
(id 6392, +0.3528, "Palantir Is Growing Like Nvidia—Without Joining The AI Spending Race") era
disponibile già alle 17:01 ma è stato scartato dal gate di freschezza; l'ordine è poi partito
alle 19:37 su un segnale (id 6480) derivato da un articolo intitolato **"What Is Going on With
Broadcom Stock on Tuesday?"**. Anche entrando alle 17:07 il guadagno sarebbe stato di ~2,4 $:
il costo del ritardo è trascurabile perché l'alpha era già consumato.

### 4.3 Il book: dove è nato il +819 $

MTM del book aperto: **+819,35 $** (S1 +701,56 · S4 +77,55 · legacy senza attribuzione +40,24).
I primi dodici contributori sono tutti posizioni S1 aperte fra il 13 e il 31 luglio su semis e
hardware AI: WDC +62,16 · ARM +58,68 · PANW +42,96 · CAT +42,22 · CSCO +39,99 · SOXX +39,49 ·
XLK +39,29 · TXN +39,15 · INTC +38,64 · MRVL +38,38 · DELL +35,34 · AMD +33,78. I peggiori sono
le posizioni legacy su energia e difensivi: BP −29,51 · PBR −14,06 · UNH −12,18 · CVX −11,70 ·
SHEL −11,68.

Riconciliazione: realizzato −57,98 + MTM +819,35 = **+761,37 $** contro una variazione di equity
Alpaca di **+662,20 $** (109.704,03 → 110.366,23). Scarto ~99 $ (0,09% del NAV), attribuibile ai
costi di transazione dei 6 roundtrip e alla differenza fra chiusure IEX e chiusure ufficiali
consolidate. Non ho una via per azzerarlo senza il feed SIP.

### 4.4 Cadenza dei cicli

24 cicli `portfolio_cycles`, dalle 14:07:00 alle 19:52:00 UTC, passo esattamente 15 minuti,
**nessun gap > 16 minuti**. Identico ai quattro giorni di borsa precedenti (07-29, 07-30, 07-31,
08-03: 24 cicli, stessa finestra). Nessuna anomalia operativa.

---

## 5. Pattern osservato

**Pattern chiaro e monotematico: rotazione violenta dentro semiconduttori / hardware AI.**

I 16 mover ≥ 5% sono, in ordine: PLTR, ARM, MRVL, INTC, SPCX, DELL, AMD, MU, QCOM, SOXX, AVGO,
NOK, CAT, AMAT, PANW, TXN. Di questi, 11 sono semiconduttori o loro fornitori diretti, uno è
l'ETF di settore (SOXX +6.73%) e uno l'ETF tech (XLK +4.92%). Il tema è esplicito nelle headline
raccolte: "Data Center Royalty Growth Drives Post-Selloff Semiconductor Rally" (ARM),
"AI Growth Narrative Trumps Foundry Capex Concerns" (INTC), "AI Memory Demand Sparks Rebound
After Recent Selloff" (MU), "Big Tech's $1.2 Trillion Hyperscaler AI Bet" (AMAT/AVGO/SOXX),
"Caterpillar Cashes In On AI Buildout" (CAT). È il **rimbalzo speculare del selloff** citato nelle
notizie stesse, e l'esatto inverso del 08-03, quando i semi erano fermi (NVDA +2.9%, AMD +1.8%,
SOXX +0.6%) e correvano software e retail high-beta.

Dalla parte opposta non c'è un settore che scende: solo due nomi sotto −3%, entrambi
idiosincratici (BP su guidance di produzione tagliata, NVO su reazione negativa a una guidance
alzata). Non è una rotazione fuori da qualcosa, è un afflusso su un tema.

**Il fatto più rilevante della giornata non è nella tabella dei miss.** Sui 29 mover, il gap di
apertura vale in media 3,45 punti percentuali contro 2,79 di movimento intraday: **il 55% del
movimento accade a mercato chiuso**. Sui primi tre — PLTR (+15,30 gap / +12,03 intraday),
MRVL (+8,30 / +4,13), CAT (+11,65 / **−5,47**) — la quota è ancora più alta, e CAT è il caso
limite: ha guadagnato l'11,65% nel gap e ne ha restituito il 5,47% durante la seduta. Un sistema
che decide solo dentro la sessione cash, su cicli da 15 minuti, non può accedere alla metà del
movimento; e su un titolo come CAT il segnale corretto (+0.747, conf 0.900, alle 14:00:35) sarebbe
stato *dannoso* se avesse prodotto un ingresso intraday.

---

## 6. Confronto con i giorni precedenti

Esistono sei report precedenti (07-24, 07-27, 07-28, 07-29, 07-30, 07-31, 08-03). Ricorrenze che
si vedono adesso e non si vedevano su un giorno solo:

1. **Gli stessi ticker restano scoperti.** RDDT è NO_NEWS il 07-31, sotto-gate il 08-03, NO_NEWS
   oggi. SAP è mancato per assenza o genericità di news il 07-24, 07-27, 07-28, 08-03 e oggi.
   HOOD è NO_NEWS il 08-03 e oggi. Non è copertura casuale: è un insieme stabile di simboli su
   cui le due fonti non arrivano mai. La quota di watchlist scoperta oscilla in una banda stretta:
   55/96 (07-31), 41/96 (08-03), 42/96 (08-04).
2. **Il fan-out multi-ticker cresce.** Articoli con 2+ ticker: 25% delle testate e 51% delle righe
   scorate il 08-03; **34% delle testate (36/106) e 66% delle righe (134/204) oggi**, con due
   articoli taggati a 13 ticker ciascuno. Entrambi i miss THIN_NEUTRAL di oggi (AVGO, IBM) hanno
   come unica o principale fonte un articolo su una terza società, e l'unico BUY sul mover #1
   (PLTR) nasce da un pezzo su Broadcom.
3. **La sovrascrittura del segnale forte da parte di un articolo generico si ripete.** Il 08-03 su
   ORCL (uscita anticipata) e MSFT (ingresso mancato); oggi su ARM e CAT (§7).
4. **Il churn intraday continua.** 08-03: 4 BUY su 6 chiusi lo stesso giorno, con roundtrip
   completi su AMZN e MSFT. Oggi: roundtrip su PFE, SBUX e ABBV, tutti e tre con rientro a un
   prezzo peggiore dell'uscita.

---

## 7. Segnalazioni per il ledger

Registrazione di evidenza, non proposte. Il periodo di sola osservazione congela ogni taratura.

**[F-001] Copertura news bassa sulla watchlist — 42 simboli su 96 (44%) senza articoli.**
Cinque dei nove miss sono NO_NEWS puri: QCOM (+7.32%), HOOD (+3.48%), NOW (+3.45%),
RDDT (+3.30%), SAP (+3.02%) — zero righe in `news_log`, zero in `sentiment_signals`, zero in
`execution_decisions`, nessuna catena decisionale esistente. Costo stimato con la size S4 tipica
di 2.200 $ sul return pieno: 161,04 + 76,56 + 75,90 + 72,60 + 66,44 = **452,54 $**. Va letto con
un caveat che le occorrenze precedenti non avevano: su questi cinque nomi il **56% del movimento
è nel gap**, quindi la porzione realmente catturabile intraday vale 352,88 $ e non 452,54 $. Uso
il return pieno per non rompere la comparabilità della serie, e lascio qui il numero alternativo
perché l'operatore possa ri-derivarlo.

**[F-002] Attribuzione strategia mancante su trade legacy.** Dodici delle 52 posizioni aperte a
fine 08-04 (BAC, BP, GOOGL, GS, MS, PBR, RIO, ROKU, SPY, UBS, UNH, XLE, tutte aperte il 07-10)
hanno `trades.stop_strategy` NULL. Contribuiscono +40,24 $ di MTM del giorno. Fra queste c'è
**RIO (+3.31%)**, un mover contato come catturato ma non attribuibile ad alcuna strategia, e
**BP (−4.00%)**, il peggiore contributore del book (−29,51 $): entrambi i lati dell'estremo
restano fuori dallo split S1/S4 richiesto dalla domanda di uscita 2 della carta. Costo non
stimabile.

**[F-008] Un articolo generico multi-ticker sovrascrive un segnale ticker-specifico.** Due casi
oggi, entrambi sul lato ingresso.
*ARM:* alle 15:15:20 il segnale id 6328 vale **+0.6264 (conf 0.800**, ensemble non-fallback) e
nasce da "Arm Jumps More Than 11%: Data Center Royalty Growth Drives Post-Selloff Semiconductor
Rally" — headline direzionale e ticker-specifica. **Sedici secondi dopo**, alle 15:15:36, il
segnale id 6330 vale **+0.0082 (conf 0.175)** e nasce da "Caterpillar, Wayfair, Zebra
Technologies, Gartner And Other Big Stocks Moving Higher On Tuesday", una rassegna in cui ARM è
un tag di fan-out. Il ciclo legge l'ultimo segnale per simbolo: dalle 15:22 alle 19:52 seguono
**17 righe consecutive di `SKIP_THRESHOLD` a score 0.007** (id 6253…6580). ARM chiude +17.43%.
*CAT:* +0.7470 (conf 0.900) alle 14:00:35 da "Caterpillar Cashes In On AI Buildout, Raises 2026
Sales Outlook", azzerato a 0.000 alle 14:30:21; il pattern si ripete sei volte nella giornata
(0.7177→0.000, 0.7200→0.006, 0.6932→0.000, 0.6605→0.058, 0.6484→0.013).
**Costo 0,00 $ — non `null`: il controfattuale è stato calcolato ed è nullo.** Sia ARM sia CAT
erano già in book come posizioni S1, e il guard P0-05 (no pyramiding) ha bloccato esplicitamente
il BUY a ogni ciclo indipendentemente dal punteggio: log worker 14:07:09, 14:22:09, 14:37:09,
14:52:09, 15:07:08, 15:22:08, 15:37:09, 15:52:07, 16:07:11, 16:22:09, 16:37:09, 16:52:08,
17:07:12, 17:22:09 — "P0-05: skipping BUY decision for ARM — already has an open trade". Il
difetto di segnale è reale e documentato, ma quel giorno non ha impedito alcun ordine.

**[F-009] Il gate d'ingresso 0.300 scarta un segnale del segno giusto su un mover forte.**
AVGO +6.56%: segnale id 6379 alle 16:45, **+0.2762 conf 0.600**, ensemble non-fallback, segno
corretto, sotto gate; `SKIP_THRESHOLD` id 6552. Costo stimato con size S4 tipica 2.200 $ sul
return pieno: **144,32 $** (82,28 $ sulla sola porzione intraday). Nota che indebolisce
l'attribuzione a questo finding: l'articolo sorgente non è su Broadcom ma è "Big Tech's $1.2
Trillion Hyperscaler AI Bet Could Ignite the Next Semiconductor ETF Rally", taggato in fan-out
anche ad AMAT e SOXX — quindi la magnitudine bassa può essere una conseguenza corretta della
genericità della fonte, non una mis-calibrazione. Il legame è con F-012.

**[F-012] Metà e più delle righe scorate viene da articoli fan-out multi-ticker.** 36 articoli su
106 (34%) sono taggati a 2+ ticker e generano **134 delle 204 righe scorate (66%)**, contro il 51%
del 08-03. Distribuzione dei ticker per articolo: 1→70, 2→17, 3→10, 4→1, 5→2, 6→1, 7→1, 8→1,
9→1, 13→2. Tre conseguenze misurate oggi: (a) l'unico BUY sul mover #1 della giornata, **PLTR
+29.17%**, nasce dal segnale id 6480 il cui articolo è **"What Is Going on With Broadcom Stock on
Tuesday?"**, mentre il pezzo Palantir-specifico (id 6392) era stato scartato prima; (b) IBM
(+3.96%) ha come unica copertura del giorno "Why Is Rigetti Stock Surging on Tuesday?"; (c) CSCO
(+5.06%) ha come unica copertura "Why Is CrowdStrike Stock Surging on Tuesday?". Costo non
stimabile: l'affermazione non è "questi trade hanno perso" ma "il meccanismo di attribuzione
misura un'altra cosa", e questo non ha un prezzo giornaliero.

**[F-019 — nuovo] La latenza di ingestione news consuma il 92% della finestra di freschezza
d'ingresso: i segnali nascono quasi scaduti.**
Misura sul 08-04, su `news_log` con `published_at` non nullo: latenza `created_at − published_at`
**mediana 111,7 minuti** per `alpaca_benzinga` (n=126, media 102,2, min 18, max 121) e **105,6
minuti** per `gdelt_gkg` (n=78, media 97,2, min 46, max 107). Il gate `entry-freshness` (#150) usa
`MAX_NEWS_AGE_HOURS = 2.0`. Ne segue che l'articolo mediano viene scorato quando gli restano
**circa 8 minuti** di vita utile, cioè meno di un ciclo di portafoglio (cadenza 15 minuti), e
**14 articoli su 126 (11%) sono già scaduti nell'istante in cui vengono scorati**. Effetto
aggregato: ogni ciclo del 08-04 scarta **da 26 a 32 segnali** per questo solo gate (log:
"S4: dropped 30 signal(s) below entry-freshness (news_age_hours=2.0)" e varianti, 24 cicli su 24),
il che lo rende il filtro più selettivo dell'intero percorso S4 — più del gate 0.300, che ne
scarta 14-21 su 16-26.
Non è una deriva del giorno: 07-31 media 91,3 / 102,0 minuti, 08-03 media 80,4 / 74,1 minuti,
08-04 media 102,2 / 97,2. La latenza è sempre stata dello stesso ordine di grandezza del gate.
Due casi tracciati riga per riga: **PLTR** id 6392 pubblicato 15:06:13, scorato 17:01:13
(+0.3528, sopra gate), scartato al ciclo 17:07 perché a 2h01m di età — l'ordine arriverà solo
alle 19:37 su un altro articolo; **SPCX** id 6476 pubblicato 17:16:39, scorato 19:16:16
(+0.4500), già a 2h00m alla nascita.
**Costo stimato 2,37 $**, ed è l'unica istanza prezzabile della giornata: contro-fattuale corto su
PLTR, stesso notional effettivo (1.136,71 $), ingresso al ciclo 17:07 a 162.56 invece che alle
19:37 a 162.90 → 6,9927 azioni che chiudono a 162.61 danno +0,35 $ contro i −2,02 $ realmente a
mercato. È piccolo perché il 96% del movimento intraday di PLTR era già finito alle 17:00, non
perché il gate sia innocuo. Su SPCX il gate non è vincolante (il segnale sarebbe caduto comunque
su #108, `fallback_used=true`), quindi non lo prezzo.
**Id nuovo giustificato:** nessun finding esistente riguarda la latenza della pipeline di
ingestione. F-001 riguarda l'*assenza* di copertura, non il ritardo di quella che c'è; F-009 il
gate di magnitudine 0.300; F-012 l'attribuzione dei ticker. Questa è la terza causa strutturale
di scarto ed è quella che opera sul volume maggiore di segnali.
**Nota di conformità:** `MAX_NEWS_AGE_HOURS` è taratura e resta congelato dalla carta. La
segnalazione riguarda la latenza misurata, non il valore del parametro.

**Sembra un difetto e non un limite noto — [F-019].** La decisione se aprire una issue è
dell'operatore, io mi fermo alla constatazione. Il gate a 2,0 ore e una pipeline con latenza
mediana di 1,85 ore sono due parametri che non sono mai stati confrontati fra loro: qualunque
valore del gate sotto le ~2 ore rende il percorso S4 dipendente dal rumore di ingestione più che
dal contenuto delle notizie. Non è una taratura da rivedere, è un'interazione fra due componenti
che nessuno dei due conosce.

**Osservazione fuori-ledger (nessun id, non è un difetto del sistema).** Il 55% del movimento dei
mover del 08-04 è nel gap di apertura, e su alcuni nomi il segno intraday è opposto al segno del
giorno (CAT +11,65% gap / −5,47% intraday). Questo non è un difetto di Alembic: è una proprietà
della classe di eventi (earnings, guidance) che genera i mover. Va però tenuto presente nella
sintesi del giorno 40, perché condiziona la domanda di uscita 1 della carta: se l'alpha delle
notizie editoriali sta prevalentemente nel gap, un sistema che decide solo dentro la sessione non
può misurarlo, indipendentemente dalla qualità del segnale. Non la registro come finding perché
non è un'affermazione su un componente del sistema, ed è la prima volta che la misuro.

---

## 8. Nota metodologica

- Prezzi da feed **IEX**: il feed SIP non è coperto dalla sottoscrizione Alpaca (cfr. F-016). Le
  chiusure possono differire di qualche centesimo dalle chiusure consolidate; è la fonte più
  probabile dei 99 $ di scarto in §4.3.
- Il MTM del book è calcolato marcando dal close del 08-03 (o dal prezzo d'ingresso per le
  posizioni aperte il 08-04) al close del 08-04, per quantità.
- Equity di fine giornata = `last_equity` dell'account Alpaca letto il 2026-08-05.
- Nessuna modifica a codice, configurazione o stato di runtime. Nessun ordine. Sessione read-only
  a parte questo report e i due ledger.
