# Alpha Miss Report — 2026-08-06

Perimetro: i 96 simboli di `config/trading.yaml → symbols.watchlist`. Non è uno scan di mercato.
Numeri deterministici da `docs/evidence/dossier/2026-08-06.json` (Alpaca SIP, `adjustment=all`);
l'interpretazione, la lettura dei testi degli articoli e la classificazione delle cause sono di
questa sessione. Periodo di sola osservazione (`docs/evidence/OBSERVATION_CHARTER.md`): nessun fix
e nessuna taratura proposta.

## 1. Executive summary

Giornata a indici fermi (SPY −0.16%, QQQ −0.37%) con dispersione 2.24% e **8 mover ≥3%**, 4 su e 4 giù.
Alembic ne ha in libro o ha tradato **4** (SPCX, ARM, DELL, WDC) e ne ha **mancati 4** (TMUS, NVO, BA, CRM).
Causa prevalente dei miss: **THIN_NEUTRAL (2)**, entrambi su articoli-lista generici multi-ticker;
poi NO_NEWS (1, TMUS) e FILTERED (1, NVO, scartato dal gate feedback a 0.350 con score +0.266 del segno giusto).
Il fatto dominante del giorno non è però un miss: è **come sono stati gestiti i titoli catturati**.
SPCX (+6.14%) è stato comprato e rivenduto in perdita (−$34.98) per scadenza del segnale, lasciando
+$51.77 di drift sul tavolo; MSFT (+2.54%) chiuso dopo 1h45 a −$7.79 lasciando +$11.14; WDC, tenuta
da S4 dal 21/07, ha gappato **−17.39%** in apertura e vale da sola **−$201.67** di MTM, cioè il 100%
dell'MTM S4 del giorno. Realizzato del giorno −$46.26 (S1 −$3.49, S4 −$42.77), MTM del libro aperto
−$292.31, NAV di chiusura $110.051,33 (−$187,77 sul giorno).
La copertura news resta il vincolo di fondo: **40/96 simboli senza una riga** in `news_log`.

## 2. Rendimenti completi della watchlist (96 simboli, close vs close precedente)

`P` = posizione aperta a fine giornata · `T` = tradato il 2026-08-06 · `—` = fuori dal libro.
In grassetto gli 8 mover con |return| ≥ 3%. Nessun simbolo privo di barre.

| # | Sym | Return | Libro |
|--:|---|--:|:-:|
| 1 | **SPCX** | **+6.14%** | T |
| 2 | **ARM** | **+4.41%** | P |
| 3 | **TMUS** | **+3.75%** | — |
| 4 | **NVO** | **+3.23%** | — |
| 5 | SONY | +2.94% | — |
| 6 | DIS | +2.87% | — |
| 7 | T | +2.82% | — |
| 8 | MSFT | +2.54% | T |
| 9 | BP | +2.48% | — |
| 10 | XOM | +2.12% | P |
| 11 | ROKU | +2.12% | P |
| 12 | SHEL | +2.10% | P |
| 13 | LLY | +1.89% | P |
| 14 | QCOM | +1.82% | — |
| 15 | CMCSA | +1.70% | — |
| 16 | ASML | +1.56% | P |
| 17 | CVX | +1.51% | P |
| 18 | PFE | +1.51% | — |
| 19 | AMD | +1.50% | P |
| 20 | XLE | +1.48% | P |
| 21 | VZ | +1.12% | — |
| 22 | BRK.B | +1.11% | P/T |
| 23 | SAP | +1.08% | — |
| 24 | TSM | +1.01% | P |
| 25 | ERIC | +0.99% | — |
| 26 | MA | +0.96% | — |
| 27 | PBR | +0.87% | P |
| 28 | TM | +0.86% | — |
| 29 | JD | +0.83% | — |
| 30 | MCD | +0.82% | — |
| 31 | COST | +0.76% | — |
| 32 | AVGO | +0.55% | — |
| 33 | V | +0.52% | — |
| 34 | AAPL | +0.45% | P |
| 35 | SNOW | +0.37% | P |
| 36 | ADBE | +0.35% | — |
| 37 | SOXX | +0.34% | P |
| 38 | TXN | +0.24% | P |
| 39 | META | +0.19% | — |
| 40 | XLV | +0.18% | P |
| 41 | PG | +0.12% | — |
| 42 | NOW | +0.11% | — |
| 43 | MRK | +0.03% | P |
| 44 | NVDA | -0.10% | — |
| 45 | AMZN | -0.14% | — |
| 46 | SPY | -0.16% | P |
| 47 | MRVL | -0.23% | P |
| 48 | JNJ | -0.24% | P |
| 49 | WMT | -0.24% | — |
| 50 | AZN | -0.27% | — |
| 51 | XLK | -0.31% | P |
| 52 | XLF | -0.33% | P |
| 53 | QQQ | -0.37% | P |
| 54 | BAC | -0.40% | P |
| 55 | IWM | -0.51% | P |
| 56 | CSCO | -0.51% | P |
| 57 | TSLA | -0.63% | — |
| 58 | ORCL | -0.64% | — |
| 59 | NFLX | -0.69% | — |
| 60 | MMM | -0.75% | P/T |
| 61 | SBUX | -0.79% | T |
| 62 | JPM | -0.82% | P |
| 63 | PANW | -0.87% | P |
| 64 | ABBV | -0.95% | P/T |
| 65 | INFY | -0.96% | — |
| 66 | HD | -1.03% | — |
| 67 | IBM | -1.06% | — |
| 68 | NKE | -1.06% | — |
| 69 | DB | -1.08% | — |
| 70 | INTC | -1.24% | P |
| 71 | AMAT | -1.27% | P |
| 72 | GOOGL | -1.29% | P |
| 73 | MU | -1.31% | P |
| 74 | BABA | -1.34% | — |
| 75 | UBS | -1.36% | P |
| 76 | VALE | -1.47% | P |
| 77 | NOK | -1.57% | P |
| 78 | PLTR | -1.58% | — |
| 79 | BIDU | -1.60% | — |
| 80 | CAT | -1.62% | P |
| 81 | GE | -1.75% | P |
| 82 | WFC | -1.77% | — |
| 83 | AXP | -1.83% | — |
| 84 | RIO | -1.83% | P |
| 85 | MS | -2.07% | P |
| 86 | UNH | -2.13% | P |
| 87 | HOOD | -2.25% | — |
| 88 | F | -2.41% | — |
| 89 | GM | -2.49% | P |
| 90 | GS | -2.62% | P |
| 91 | C | -2.78% | P |
| 92 | RDDT | -2.83% | — |
| 93 | **CRM** | **-3.22%** | — |
| 94 | **BA** | **-3.33%** | — |
| 95 | **DELL** | **-5.41%** | P |
| 96 | **WDC** | **-13.03%** | P |

Soglia mover: **|return| ≥ 3%**, la stessa del dossier e delle giornate precedenti. Con dispersione
cross-sectional 2.24%, 3% è ~1.34σ: seleziona il movimento idiosincratico e scarta il beta di
giornata. Ne risultano 8 nomi (8.3% della watchlist), un campione leggibile uno per uno.

## 3. Miss classificati

| Sym | Ret | gap / intraday | Categoria | Evidenza |
|---|--:|---|---|---|
| TMUS | +3.75% | +2.27% / +1.45% | **NO_NEWS** | Zero righe in `news_log`, zero in `sentiment_signals`, zero in `execution_decisions`. Nessuna catena decisionale esiste. TMUS è uno dei 40/96 simboli senza copertura. |
| NVO | +3.23% | +2.43% / +0.79% | **FILTERED** | Due segnali col **segno corretto**: 14:16 score +0.208 (conf 0.58) e 14:46 +0.221 (conf 0.65, sull'articolo NVO-specifico *"Novo Nordisk Scores Major Court Win, Dutch Judge Halts Compounded Semaglutide Nasal Spray"*). `execution_decisions` registra `SKIP_THRESHOLD score 0.266 < feedback threshold 0.350` a ogni ciclo dalle 14:22 alle 16:22, poi la soglia sale a 0.400. Il gate di design S4 è 0.30: la soglia che ha scartato NVO è quella **alzata dal loss-feedback**, non quella di configurazione. |
| BA | −3.33% | −0.08% / −3.25% | **THIN_NEUTRAL** | Unico articolo del giorno: *"10 Industrials Stocks With Whale Alerts In Today's Session"* — lista generica multi-ticker. Ensemble non-fallback → score **0.000**, confidence 0.20. |
| CRM | −3.22% | −4.94% / +1.82% | **THIN_NEUTRAL** | Unico articolo: *"10 Information Technology Stocks Whale Activity In Today's Session"* — stessa forma. Ensemble non-fallback → score **0.000**, confidence 0.15. |

Conteggi: NO_NEWS 1 · THIN_NEUTRAL 2 · WRONG_SIGN 0 · FILTERED 1 · OUT_OF_STRATEGY_SCOPE 0.

Nota sui costi: BA e CRM sono mover **al ribasso** e il libro è long-only, quindi il controfattuale
vale **zero dollari** (non "non stimato"): non c'era alpha catturabile. Il costo dei due miss veri è
TMUS $82,50 e NVO $71,06 a size S4 tipica ($2.200), sul rendimento pieno; sulla sola porzione
intraday realmente catturabile varrebbero $31,90 e $17,38.

## 4. Titoli catturati: esito

**SPCX +6.14% — catturato e perso.** BUY 14:37 a $113,07 (2,0% del NAV, score ensemble +0.402),
SELL 18:52 a $109,93, **net −$34,98**, `exit_reason=portfolio_sell`. Motivo reale dal decision log:
`[expired] S4 signal expired (age=4.4h > max_age=4h, generated 14:30, score=+0.402): no counter-signal
found, position closed`. Il titolo ha chiuso a $114,92: **drift post-uscita +$51,77**, e l'MTM a fine
giornata sarebbe stato **+$19,20**. `entry_percentile` 0.748 — ingresso nel quartile alto del range
del giorno. Due dettagli che aggravano la lettura:
- fra le 14:30 e le 18:52 SPCX ha prodotto tre segnali (15:45 −0.120, 16:45 **+0.560**, 17:00 −0.360),
  tutti `fallback_used=true` single-model. La query che compone il testo della decisione filtra
  `fallback_used = FALSE` (`src/store/pg_store.py:67-71`): il log dice quindi "scaduto il segnale
  delle 14:30" mentre nella finestra esistevano segnali più recenti, uno dei quali **sopra la soglia
  d'ingresso del giorno**.
- alle 15:07, 30 minuti dopo l'acquisto, un SELL su SPCX era già stato richiesto e bloccato dal
  guard hold-minimum (`Hold minimum (90 min): skipped 1 SELL order(s) for recently-bought`).

**MSFT +2.54% — catturato e perso.** BUY 14:22 a $498,34 su score ensemble **+0.508**
(articolo *"AI Hyperscaler Spending Is Entering Uncharted Territory"*, `entry_percentile` 0.753),
SELL 16:07 a $495,13, **net −$7,79**, durata 1h45. Motivo: `[whipsaw] weight 0.0% — S4 signal present
but not driving a position (score=+0.012, age=0.8h)`. Lo score che ha azzerato il peso viene da un
**articolo diverso** (*"Steve Eisman Pushes Back on Michael Burry's Market Top Call"*, 15:00 e 15:16,
score −0.018 e +0.012) che ha semplicemente sostituito il segnale forte delle 14:15. MSFT ha chiuso a
$499,86: **drift post-uscita +$11,14**.

**ARM +4.41% — in libro (S1, dal 03/08).** Non è merito di S4: l'unico articolo ARM del giorno
(*"SoftBank Shrugs Off AI Bubble Fears"*) ha prodotto score 0.000 / conf 0.20 e ha generato 24 righe
`SKIP_THRESHOLD score 0.007` consecutive. Il titolo ha gappato −2.75% e recuperato +7.36% intraday.

**DELL −5.41% — in libro (S1, dal 13/07).** Perdita subita, nessuna decisione del giorno.

**WDC −13.03% — in libro (S4, dal 21/07), è il fatto della giornata.** Ingresso $549,24, chiusura
$451,52: **−17.8% dall'ingresso**. Oggi da sola vale **−$201,67** di MTM, cioè l'intero MTM S4 del
giorno (−$201,67 su −$201,67). Tre osservazioni con evidenza:
1. Il movimento è **tutto nel gap**: apertura a $428,89 (−17.39% sul close precedente), poi +5.28%
   intraday. Nessun meccanismo intraday — stop compreso — poteva evitarlo. Lo stop registrato sul
   trade è `stop_mode=fixed`, `stop_floor=0.03`: irrilevante contro un gap di 17 punti.
2. Il segnale S4 su WDC è rimasto **positivo per tutto il giorno del crollo** (15:15 −0.313 ensemble,
   poi 18:00 +0.100 e 19:15 +0.120 fallback; il gate lo legge come +0.250 e poi +0.313), su articoli
   che *raccontano il crollo*: *"Western Digital Stock's Worst Drop Since March 2020: History Offers a
   Bullish Signal"*. Segno sbagliato rispetto al prezzo, ma sotto soglia, quindi senza effetto: non ha
   comprato di più e non ha venduto.
3. **L'asimmetria**: la stessa strategia, lo stesso giorno, ha chiuso SPCX dopo 4h15 perché il segnale
   era scaduto, e ha tenuto WDC per 16 giorni perché il segnale resta debolmente positivo. La regola
   `_preserve_stale_signals_for_open_positions` (`src/workers/portfolio_scheduler.py:555-577`)
   ri-ammette i segnali stantii con score > 0 quando esiste una posizione aperta e nessun
   contro-segnale: di fatto S4 non ha un orizzonte di uscita per le posizioni che restano tiepidamente
   positive, mentre ne ha uno di 4 ore per quelle che smettono di essere aggiornate.

Chiusure S1 del giorno (nessuna riguarda un mover): SBUX −$13,87, BRK.B +$0,77, ABBV −$6,89,
MMM +$18,16 e −$1,66. Realizzato totale −$46,26.

## 5. Pattern osservato

**Stress su storage/hardware da un lato, rotazione difensiva dall'altro, e un forte rientro intraday
dei gap.** Gli indici sono fermi (SPY −0.16%, QQQ −0.37%) ma la coda inferiore è monotematica:
WDC −13.03% (gap −17.39% sui conti SanDisk), DELL −5.41%, con MU −1.31%, AMAT −1.27% e INTC −1.24%
a fare da contorno. Il titolo di uno degli articoli del giorno lo riassume: *"SanDisk, WDC Disappoint;
SK Hynix's Flash Crash"*. Sul lato opposto salgono i difensivi da cash flow — telecom (TMUS +3.75%,
T +2.82%, VZ +1.12%, CMCSA +1.70%) ed energia (BP +2.48%, XOM +2.12%, SHEL +2.10%, CVX +1.51%,
XLE +1.48%) — mentre i finanziari scendono in blocco (C −2.78%, GS −2.62%, MS −2.07%, GM −2.49%,
F −2.41%, AXP −1.83%, WFC −1.77%).

Il secondo tratto, più rilevante per l'esecuzione che per il tema: **i mover di oggi hanno gappato in
una direzione e sono andati nell'altra**. WDC gap −17.39% → intraday +5.28%; ARM gap −2.75% →
intraday +7.36%; SPCX gap −1.09% → intraday +7.32%; CRM gap −4.94% → intraday +1.82%. È l'inverso
esatto del 04/08, quando il 55% del movimento dei mover era nel gap e l'intraday lo restituiva.
Su una giornata così, entrare nel quartile alto del range (MSFT 0.753, SPCX 0.748, contro una mediana
mobile a 20 giorni di 0.526) e uscire per scadenza del segnale è la combinazione peggiore: il segnale
arriva a mossa avviata e la posizione viene chiusa prima che il recupero si completi.

## 6. Ricorrenze rispetto ai giorni precedenti

- **Copertura news**: 40/96 simboli scoperti oggi, contro 41 (03/08), 42 (04/08), 51 (05/08), 55 (31/07).
  Banda stabile 42-57%, quattro giorni consecutivi dentro la finestra di osservazione.
- **Fan-out sui ticker bancari** (F-020): MS 30 righe + GS 10 = **40 delle 162 righe del giorno (24.7%)**,
  nessuna delle quali riguarda Morgan Stanley o Goldman Sachs (*"Zacks Research Upgrades AMC Networks"*,
  *"Archer Daniels Midland Issues FY 2026 Earnings Guidance"*, …). Terzo giorno consecutivo.
- **Gate S4 che scarta segnali col segno giusto** (F-009): quarto giorno consecutivo, oggi su NVO.
  Novità: la soglia effettiva non è 0.30 ma 0.350 → 0.400, alzata dal loss-feedback dopo le perdite.
  Log: `S4 feedback gate: dropped 33/35 signals below threshold 0.350`.
- **Uscite premature su mover** (F-013 / F-024): terzo giorno consecutivo. Oggi due casi nello stesso
  giorno (MSFT 1h45, SPCX 4h15) su titoli che hanno chiuso rispettivamente +2.54% e +6.14%.
- **Miglioramento, non ricorrenza**: la latenza di ingestione news oggi ha mediana **40,4 minuti**
  (p90 105 min) contro la mediana ~1h50m che aveva motivato F-019. Non registro un'occorrenza di
  F-019 per oggi.
- **`execution_decisions.signal_id` NULL** (F-011): 703 righe su 705 oggi, invariato.

## 7. Segnalazioni

Nessun fix proposto: periodo di sola osservazione. Dove sotto si legge «sembra un difetto», è una
constatazione, e la decisione se aprire una issue è dell'operatore.

- **[F-025] Sembra un difetto — S4 non ha un orizzonte di uscita per le posizioni tiepidamente
  positive, mentre ne ha uno di 4 ore per le altre.** WDC è aperta dal 21/07 (16 giorni) a −17.8%
  dall'ingresso perché `_preserve_stale_signals_for_open_positions` ri-ammette il segnale stantio
  finché lo score è > 0; SPCX è stata chiusa lo stesso giorno dopo 4h15 perché il suo segnale è
  scaduto. Oggi WDC vale −$201,67 di MTM, il 100% dell'MTM S4 del giorno.
- **[F-024] Sembra un difetto — la scadenza del segnale chiude una posizione senza contro-segnale, e
  oggi lo fa dentro la stessa sessione.** SPCX chiusa alle 18:52 a −$34,98 su un titolo che ha chiuso
  +6.14%; drift post-uscita **+$51,77**. Variante intraday dello stesso meccanismo registrato il 04/08
  in forma overnight.
- **[F-013] Sembra un difetto — SELL con score positivo, nessuna banda fra gate d'ingresso e uscita.**
  MSFT venduta a 1h45 dall'acquisto con `score=+0.012` presente e fresco (tag `[whipsaw]`), su un
  titolo che chiude +2.54%: **+$11,14** lasciati sul tavolo.
- **[F-023] Osservazione — il segnale forte è stato sostituito da uno debole su un articolo diverso.**
  MSFT: +0.508 alle 14:15 (capex hyperscaler) → −0.018 alle 15:00 e +0.012 alle 15:16 (commento di
  Steve Eisman su Michael Burry). È il secondo score, non il primo, a decidere l'uscita. Dollari
  contabilizzati su F-013 per non contarli due volte.
- **[F-009] Alpha mancato — il gate d'ingresso scarta un segnale col segno corretto.** NVO +3.23%:
  score +0.266 contro soglia 0.350, su un articolo NVO-specifico e materiale (vittoria in tribunale
  sul semaglutide compoundato). Costo congetturale **$71,06**.
- **[F-001] Osservazione — copertura news assente su 40/96 simboli.** TMUS +3.75% è il miss puro del
  giorno: zero news, zero segnali, zero decisioni. Costo congetturale **$82,50**.
- **[F-012] Sembra un difetto — articoli-lista generici multi-ticker producono score identicamente
  nulli.** BA e CRM hanno come unica copertura del giorno *"10 Industrials Stocks With Whale Alerts"*
  e *"10 Information Technology Stocks Whale Activity"*: entrambi score 0.000, confidence 0.15-0.20.
  Costo zero verificato (mover al ribasso, libro long-only), ma la forma è quella che consuma la
  copertura apparente.
- **[F-020] Sembra un difetto — `org_lookup` attribuisce a MS e GS articoli su società terze.**
  40/162 righe del giorno (24.7%) su due ticker bancari, nessuna delle quali parla delle due banche.
- **[F-006] Sembra un difetto — il testo della decisione nomina un segnale diverso da quello che ha
  deciso.** Il SELL su SPCX riporta `[expired] ... generated 14:30, score=+0.402` mentre nella finestra
  esistevano tre segnali più recenti (15:45, 16:45, 17:00): la query che compone il testo filtra
  `fallback_used = FALSE` (`src/store/pg_store.py:67-71`), quindi i segnali single-model sono invisibili
  al log della decisione. Un'analisi solo-DB ricostruisce la causa sbagliata.
- **[F-014] Sembra un difetto — telemetria del ciclo portfolio fuorviante.** `Hold minimum (90 min):
  skipped 1 SELL order(s) for recently-bought: ['ABBV', 'MSFT', 'SPCX']`: il conteggio dice 1, la lista
  ne elenca 3, e sono i candidati, non gli scartati.
- **[F-011] Sembra un difetto — la catena segnale→decisione→trade non è ricostruibile per chiave.**
  703 righe su 705 di `execution_decisions` con `signal_id` NULL.
