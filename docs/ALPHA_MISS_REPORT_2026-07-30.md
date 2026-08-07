# Alpha Miss Report — 2026-07-30 (giovedì)

Scope: solo i 96 simboli in `config/trading.yaml` → `symbols.watchlist`. Rendimenti da Alpaca daily
bars (`StockHistoricalDataClient`, close 2026-07-30 vs close 2026-07-29). Dati Alembic da
`alembic-postgres-1` (`trades`, `execution_decisions`, `sentiment_signals`, `news_log`,
`portfolio_cycles`), `alembic-redis-1` (stato gate feedback) e `docker logs alembic-worker-1`.
Nessuna modifica al codice o al sistema — solo lettura. Tutti i 96 simboli hanno barre disponibili
per entrambe le date: **nessun gap dati sui prezzi**.

## 1. Executive summary

- Soglia mover: **|return| ≥ 3%**, coerente con i report 07-27/28/29 — sopra la banda di rumore
  giornaliera tipica della watchlist. **40/96 mover rilevanti: 29 al rialzo, 11 al ribasso.**
- Giornata a fortissima dispersione, dominata da un **melt-up dei semiconduttori/hardware**
  (MU +18.4%, WDC +15.4%, AMAT +15.0%, AMD +13.0%, MRVL +12.2%, INTC +11.3%) innescato dagli
  earnings Microsoft/Azure del 29 sera, con **META −7.95%** sul lato opposto.
- **24/29 mover al rialzo erano in portafoglio** (esposizione presente durante la giornata),
  **5 mancati**: AVGO, DB, AMZN, TSLA, BA.
- Ma la cattura è **quasi interamente ereditata, non decisa il 30**: il delta mark-to-market delle
  posizioni aperte è **≈ +$862**, di cui **+$626 (73%) dal blocco semis entrato tra il 13 e il 28
  luglio**. Le **7 posizioni aperte il 30 hanno contribuito +$3.95 in totale**; gli 8 exit del
  giorno hanno realizzato **−$53.03**.
- Causa prevalente dei 5 miss: nessuna categoria singola domina — 1 NO_NEWS (BA), 2 THIN_NEUTRAL
  (AMZN, TSLA), 1 WRONG_SIGN (AVGO), 1 FILTERED (DB, troncato da `n_top=5`).
- Il problema del giorno **non sono i miss**, è la **cattura degradata sui nomi presi**: MSFT
  (+15.5%) comprato alle 14:37 e rivenduto alle 17:22 per **+$1.04 di MTM**; SNOW (+5.37%) venduto
  alle 14:22 per signal-expiry; ARM/INFY/HOOD comprati alle **19:52 UTC, 8 minuti prima della
  chiusura**, due dei quali su titoli in perdita sulla giornata (INFY −5.16%, HOOD −3.61%).
- 24 cicli portfolio, cadenza 15 min regolare 14:07→19:52 UTC, **nessun gap** (`constraints_fired`
  vuoto su tutti i cicli).

## 2. Tabella completa rendimenti (96/96 simboli)

"Catturato" = Alembic aveva esposizione al titolo durante il 2026-07-30 (posizione aperta prima o
durante la giornata). "(aperta 07-30)" = entry avvenuta durante la giornata stessa.

| Simbolo | Return % | Catturato |
|---|---:|:---|
| MU | +18.36% | **sì** |
| MSFT | +15.51% | **sì** (aperta 07-30) |
| WDC | +15.37% | **sì** |
| AMAT | +14.97% | **sì** |
| AMD | +13.00% | **sì** |
| MRVL | +12.18% | **sì** |
| INTC | +11.30% | **sì** |
| DELL | +9.51% | **sì** |
| SOXX | +8.50% | **sì** |
| ORCL | +8.34% | **sì** (aperta 07-30) |
| NOK | +8.09% | **sì** |
| TSM | +7.64% | **sì** |
| ARM | +7.40% | **sì** (aperta 07-30) |
| ASML | +6.50% | **sì** |
| XLK | +5.50% | **sì** |
| SNOW | +5.37% | **sì** |
| AVGO | +4.73% | no |
| GS | +4.50% | **sì** |
| DB | +4.40% | no |
| C | +4.08% | **sì** |
| AMZN | +3.90% | no |
| RIO | +3.76% | **sì** |
| PANW | +3.67% | **sì** |
| TSLA | +3.53% | no |
| MS | +3.41% | **sì** |
| CAT | +3.38% | **sì** (aperta 07-30) |
| QQQ | +3.30% | **sì** (aperta 07-30) |
| BA | +3.22% | no |
| UBS | +3.07% | **sì** |
| PBR | +2.85% | **sì** |
| TXN | +2.75% | **sì** |
| NVDA | +2.65% | no |
| MA | +2.49% | **sì** (aperta 07-30) |
| SHEL | +2.46% | **sì** |
| VALE | +2.32% | **sì** |
| BIDU | +2.10% | no |
| BP | +2.08% | **sì** |
| WFC | +1.86% | no |
| AXP | +1.82% | no |
| JPM | +1.78% | **sì** |
| SPY | +1.68% | **sì** |
| SBUX | +1.64% | **sì** (aperta 07-30) |
| IWM | +1.39% | **sì** |
| GE | +1.26% | **sì** |
| BABA | +1.12% | no |
| BAC | +1.08% | **sì** |
| CSCO | +0.96% | **sì** |
| XLF | +0.56% | **sì** (aperta 07-30) |
| XLE | +0.53% | **sì** |
| JD | +0.34% | no |
| CVX | +0.23% | **sì** |
| UNH | +0.21% | **sì** |
| XOM | +0.14% | **sì** |
| BRK.B | +0.10% | no |
| NVO | +0.06% | no |
| RDDT | +0.03% | no |
| ROKU | −0.17% | **sì** |
| ERIC | −0.20% | no |
| SPCX | −0.31% | no |
| MRK | −0.44% | **sì** |
| PLTR | −0.60% | no |
| NFLX | −0.62% | no |
| V | −0.67% | no |
| TM | −0.72% | no |
| GOOGL | −0.91% | **sì** |
| PFE | −0.95% | no |
| MMM | −1.06% | **sì** (aperta 07-30) |
| GM | −1.12% | **sì** |
| AZN | −1.13% | no |
| MCD | −1.13% | no |
| AAPL | −1.41% | **sì** |
| HD | −1.45% | no |
| PG | −1.46% | no |
| XLV | −1.64% | **sì** |
| COST | −2.04% | no |
| IBM | −2.08% | no |
| SONY | −2.15% | no |
| NKE | −2.15% | no |
| ABBV | −2.24% | **sì** |
| VZ | −2.35% | **sì** |
| DIS | −2.36% | no |
| QCOM | −2.62% | no |
| WMT | −2.73% | no |
| SAP | −2.75% | no |
| F | −2.75% | **sì** |
| T | −3.05% | no |
| HOOD | −3.61% | **sì** (aperta 07-30) |
| JNJ | −3.66% | **sì** |
| CMCSA | −3.82% | no |
| CRM | −4.07% | no |
| TMUS | −4.51% | no |
| LLY | −4.55% | **sì** |
| NOW | −4.92% | no |
| INFY | −5.16% | **sì** (aperta 07-30) |
| ADBE | −5.90% | no |
| META | −7.95% | no |

## 3. Miss classificati

Il sistema è **long-only**: gli 11 mover al ribasso non posseduti non sono "miss" (nessuno short da
perdere) e non vengono classificati qui. Restano i **5 mover al rialzo ≥ 3% senza esposizione**.

| Simbolo | Return % | Categoria | Evidenza |
|---|---:|---|---|
| AVGO | +4.73% | **WRONG_SIGN** | 2 articoli in `news_log` (alpaca_benzinga). L'unico segnale ensemble non-fallback della giornata è **−0.240** (14:01 UTC, `ensemble:glm-5.2+gpt-oss`), cioè segno opposto al movimento. Il secondo segnale (+0.150, 14:45) è `fallback_used=true` → escluso dal ranking BUY per la regola #108. Il gate registra `SKIP_THRESHOLD "score 0.240 < 0.300"` in 6 cicli consecutivi (il confronto è su valore assoluto). |
| DB | +4.40% | **FILTERED** | 8 articoli (tutti `gdelt_gkg`, `org_lookup`). Picco **score +0.330 alle 16:31 UTC — sopra il gate 0.30**, non-fallback, `published_at` 15:00 (entro `MAX_NEWS_AGE_HOURS=2`). Al ciclo 16:37 DB **non compare** fra i `SKIP_THRESHOLD` → ha superato il gate, ma il basket S4 di quel ciclo è SBUX/LLY/XLK/MSFT/MA (5 nomi, pesi 0.02): DB è **6° e troncato da `n_top=5`**. Tutti gli altri segnali DB del giorno sono 0.000 / −0.180. |
| AMZN | +3.90% | **THIN_NEUTRAL** | 4 articoli. Il solo segnale di magnitudine (+0.240, 14:01) è **fallback** → escluso da #108; i restanti sono 0.000, +0.060, 0.000. Mai vicino a 0.30. |
| TSLA | +3.53% | **THIN_NEUTRAL** | 1 solo articolo (`alpaca_benzinga`, 14:30), segnale ensemble **0.000**. Copertura news troppo sottile per generare qualsiasi convinzione. |
| BA | +3.22% | **NO_NEWS** | **Zero righe** in `news_log` per BA il 2026-07-30, zero `sentiment_signals`. Gap di copertura dati puro. |

Nessun caso **OUT_OF_STRATEGY_SCOPE**: gli ETF in watchlist (SOXX, XLK, QQQ, SPY, IWM, XLE, XLF,
XLV) sono trattati da S1 come qualunque altro simbolo — SOXX e XLK erano in posizione, QQQ e XLF
sono stati tradati il 30.

**Contesto che riduce l'esposizione al bacino dei miss** (non una causa per-simbolo, ma il filtro
più aggressivo della giornata): ad ogni ciclo il log riporta
`S4: dropped 31-35 signal(s) below entry-freshness (news_age_hours=2.0)` — cioè ~34 segnali per
ciclo scartati perché la notizia sottostante ha più di 2 ore, applicato ai soli simboli senza
posizione aperta (comportamento #150, corretto by design). Dopo il gate 0.30 restano tipicamente
**5-7 candidati su 21-26 segnali freschi**.

## 4. Titoli catturati: esito

### 4.1 Delta mark-to-market della giornata (posizioni aperte, close-to-close)

Delta MTM totale posizioni aperte **≈ +$862**. Attribuzione:

| Simbolo | MV fine 30 | Δ MTM giorno |
|---|---:|---:|
| WDC | $1,589 | **+$211.66** |
| AMAT | $430 | +$55.98 |
| MU | $348 | +$54.00 |
| TSM | $738 | +$52.40 |
| SOXX | $583 | +$45.64 |
| AMD | $395 | +$45.43 |
| XLK | $787 | +$41.03 |
| ASML | $624 | +$38.04 |
| INTC | $355 | +$36.03 |
| DELL | $376 | +$32.69 |
| MRVL | $284 | +$30.88 |
| C | $781 | +$30.64 |
| … | | |
| HOOD (nuova) | $1,200 | −$12.94 |
| JNJ | $795 | −$30.18 |
| LLY | $797 | −$37.98 |

- **Blocco `semis` (15 nomi del sector map): +$626, il 73% del guadagno di giornata.** Tutte
  posizioni aperte fra il 13 e il 28 luglio dal path S1 — nessuna decisione del 30 le riguarda.
- **Le 7 posizioni aperte il 30 e ancora aperte a fine giornata valgono +$3.95 complessivi**
  (SBUX +$0.87, XLF +$8.33, MMM +$3.00, ORCL +$1.06, ARM +$2.87, INFY +$4.07, HOOD −$12.94).
- Le dimensioni sono fortemente disallineate rispetto al risultato: **WDC $1,589 di MV** ha prodotto
  $212, mentre **MU — il miglior titolo del giorno (+18.4%) — pesava solo $348** (entry 07-28 con
  notional $329). Non è un miss di segnale: è un miss di sizing su una posizione già aperta.

### 4.2 Uscite del 2026-07-30 — realizzato **−$53.03** su 8 exit

| Simbolo | Exit | Prezzo entry → exit | Net P&L | `exit_reason` (Decision Log) |
|---|---|---|---:|---|
| SNOW | 14:22 | 284.04 → 288.17 | **+$17.83** | `[expired]` — segnale S4 scaduto (age 23.9h > max 4h, score +0.542). Chiuso su un titolo che ha finito la giornata a **+5.37%**: l'exit ha lasciato circa 3.4 punti sul tavolo. |
| F | 14:22 | 16.02 → 14.83 | **−$52.00** | `[s1_weight_drop]` — peso S1 a 0%. |
| VZ | 14:22 | 47.23 → 46.02 | **−$18.81** | `[s1_weight_drop]` |
| MMM | 14:52 | 177.74 → 174.11 | **−$15.39** | `[s1_weight_drop]` — poi **ricomprato alle 16:22** (churn intraday su un titolo a −1.06%). |
| XLF | 15:22 | 57.00 → 56.32 | **−$9.17** | `[s1_weight_drop]` — **ricomprato alle 15:37**, 15 minuti dopo. |
| QQQ | 16:07 | 681.46 → 681.29 | **−$0.32** | `[s1_weight_drop]` — comprato 14:22, venduto 16:07: round-trip di 1h45m su un giorno a +3.30%. |
| MSFT | 17:22 | 450.72 → 455.56 | **+$13.03** | `[whipsaw]` — "weight 0.0% — S4 signal present but not driving a position (score=+0.270, age=0.4h)". Il segnale MSFT era **+0.765** alle 14:30, è sceso a +0.270 alle 17:00 e il titolo è uscito dal gate 0.30 → venduto. Giornata MSFT: **+15.51%**. |
| MA | 19:37 | 570.20 → 575.90 | **+$11.81** | `[expired]` — segnale scaduto (age 4.4h > 4h) con score ancora +0.663. |

### 4.3 Entrate del 2026-07-30

- **S4** (peso 2.0% = 1/`n_top` × bucket 10%, `s4_fixed_slot_sizing_enabled=true`): MSFT 14:37
  (+0.765), MA 15:22 (+0.663), ORCL 17:37 (+0.507), poi **ARM, INFY e HOOD tutte nello stesso ciclo
  delle 19:52 UTC**, con la chiusura alle 20:00. ARM +7.40% sul giorno ma comprata a 240.97 con la
  giornata già fatta (open 258, close 241.54); INFY comprata su un −5.16%; HOOD su un −3.61%.
- **S1** (peso 1.2%): SBUX 14:07, CAT 14:07, QQQ 14:22, XLF 15:37 (ri-entrata), MMM 16:22
  (ri-entrata).

## 5. Pattern osservato

**Rotazione netta e leggibile: semiconduttori/hardware in acquisto, mega-cap software e
healthcare/telecom in vendita.**

- **Su**: 13 dei primi 15 mover appartengono ai bucket `semis` + `tech`-hardware
  (MU, WDC, AMAT, AMD, MRVL, INTC, DELL, SOXX, TSM, ARM, ASML) più MSFT/ORCL/XLK. Driver
  identificabile dal `news_log` stesso: la trimestrale Microsoft/Azure del 29 sera
  ("Azure Ignites Microsoft Stock: AI-Fueled Earnings Beat Sparks 9% Rally", 13:07 UTC) e la
  conferma di scarsità di memoria da Samsung ("Micron Shares Surge Nearly 15% as Samsung's Record
  Profits Point to a Deepening Chip Shortage Through 2028", 16:00 UTC).
- **Giù**: META −7.95% (l'altra faccia degli stessi earnings: capex AI senza monetizzazione
  immediata), poi software applicativo e IT services (ADBE −5.90%, INFY −5.16%, NOW −4.92%,
  CRM −4.07%), healthcare (LLY −4.55%, JNJ −3.66%) e telecom (TMUS −4.51%, T −3.05%).
- Nota importante: **la mossa è quasi tutta gap overnight, non intraday.** MSFT ha chiuso il 29 a
  ~390.5 e aperto a 437.9; META ha chiuso a ~585.6 e aperto a 526. Il primo ciclo portfolio della
  giornata è alle **14:07 UTC, 37 minuti dopo l'apertura** (finestra configurata, non un gap di
  schedulazione): per costruzione l'esposizione al gap può venire solo da posizioni già aperte, mai
  da una decisione del giorno. Questo spiega perché il P&L del 30 è ereditato.

## 6. Confronto con i giorni precedenti

| Data | Mover ≥3% | Catturati | Causa prevalente miss |
|---|---:|---:|---|
| 07-27 | 19 | 5 | NO_NEWS (7/14) |
| 07-28 | 26 | 5 | NO_NEWS (9/21) + THIN_NEUTRAL (8/21) |
| 07-29 | 29 | 4 | NO_NEWS (12/25) + THIN_NEUTRAL (7/25) |
| **07-30** | **40** | **24 (esposizione)** | nessuna dominante (1/1/2/1 su 5 miss) |

Pattern ricorrenti confermati:

1. **NO_NEWS resta il collo di bottiglia strutturale**, anche se oggi è mascherato dal fatto che il
   portafoglio era già lungo il tema giusto. Sui 96 simboli, **39 hanno zero articoli** il 30
   (fra cui ASML +6.50%, SNOW +5.37%, UBS +3.07%, PBR, VALE, BIDU, WFC): la copertura news è
   presente per ~59% della watchlist e nessun segnale può nascere sul resto.
2. **La regola #108 (esclusione fallback FinBERT / single-model dal ranking BUY) continua a essere
   il filtro che disattiva i segnali di magnitudine più alta** su nomi non coperti dall'ensemble —
   il 07-29 era la causa di 6/25 miss, oggi tocca AMZN (+0.240 fallback) e AVGO (+0.150 fallback).
   È il comportamento voluto, ma il costo è ricorrente e misurabile.
3. **Inversione rispetto al 07-28/29**: quei due giorni erano semis *in vendita* e il report
   segnalava semis mancati/persi. Oggi lo stesso blocco, invariato in portafoglio, è la fonte del
   73% del guadagno. Il book semis non è stato ruotato: è stato subito in entrambe le direzioni.

Osservazioni nuove, non riscontrate nei report precedenti:

4. **Churn intraday del segnale S4 su singolo ticker.** MU ha prodotto **20 segnali in 6 ore**, con
   score che oscillano fra −0.200 e +0.565; il ranker usa il segnale **più recente** per ticker, per
   cui il picco +0.565 delle 17:45 è stato sovrascritto 16 minuti dopo da un +0.037 e poi da
   +0.008/+0.005. Lo stesso su MS (31 segnali), AMD (17), MSFT (14). Il punteggio che finisce nel
   ranking dipende quindi da **quale articolo è arrivato per ultimo**, non dal peso complessivo
   della notizia sul titolo. È visibile nel Decision Log come `SKIP_THRESHOLD "score 0.005 <
   0.300"` su MU nello stesso giorno in cui MU fa +18.4%.
5. **Il gate 0.30 funziona sull'ingresso ma non c'è isteresi in uscita.** MSFT è entrato a +0.765 e
   uscito 2h45m dopo perché il segnale è sceso a +0.270 — 0.03 sotto la soglia di *ingresso*. Un
   titolo può quindi essere comprato e rivenduto lo stesso giorno per una variazione marginale del
   punteggio, mentre il prezzo si muove del 15%.

## 7. Segnalazioni all'operatore (nessun fix proposto)

Elenco di ciò che, dall'evidenza raccolta, **sembra un difetto e non un limite noto**. La decisione
se aprire issue è dell'operatore.

- **Sembra un difetto — exit su soglia d'ingresso senza banda morta.** L'uscita MSFT delle 17:22
  (`[whipsaw]`, score +0.270 vs gate 0.300) e l'uscita MA delle 19:37 (`[expired]`, score ancora
  +0.663, scaduto per età 4.4h > 4h) mostrano che una posizione S4 viene chiusa quando il punteggio
  attraversa la *stessa* soglia usata per aprirla, o quando invecchia, indipendentemente da quanto
  il segnale sia ancora forte. Su un giorno a +15.5% questo ha convertito un'esposizione corretta in
  +$13.03 realizzati. Il flag `s4_anti_whipsaw_damping_enabled` è `false` in `config/trading.yaml`
  e il log lo conferma in shadow (`anti_whipsaw_shadow: would_suppress=True, streak=1/2`) — cioè il
  meccanismo che avrebbe soppresso proprio questa SELL esiste e non è armato.
- **Sembra un difetto — "ultimo segnale vince" sul dedup del ranker.** Vedi §6.4. Con 20-31 segnali
  al giorno sullo stesso ticker e varianza da −0.20 a +0.57, il punteggio in ranking è di fatto
  campionato a caso rispetto all'informazione disponibile. Non è documentato come scelta di design
  in `docs/strategies.md`.
- **Da verificare, potenziale falso positivo del resolver.** Il segnale DB +0.330 delle 16:31 —
  quello che ha sfiorato il basket — deriva dall'articolo *"Molten Ventures Plc: Extension of Share
  Buyback Programme by GBP15 million"* (fonte `gdelt_gkg`, `extraction_method=org_lookup`), che non
  riguarda Deutsche Bank. Il risultato di prezzo sarebbe stato favorevole (+4.40%) ma per la ragione
  sbagliata. È esattamente la classe di errore che QX-01 deve misurare.
- **Limite noto, non un bug — timing degli ingressi S4.** Tre entry su sei (ARM, INFY, HOOD) sono
  finite nel ciclo delle 19:52 UTC, 8 minuti prima della chiusura, perché il ciclo di sentiment
  produce i segnali di fine giornata a 19:45-19:46. Conseguenza diretta e prevedibile della cadenza,
  non un malfunzionamento — ma vale registrarla: due delle tre sono state comprate su titoli in
  perdita di giornata.
- **Contesto operativo, non un difetto.** Alle 14:30 UTC il loss-feedback ha fatto scattare S1:
  *"EWMA R −1.60, 12 consecutive losses, rolling P&L −$258.82 — threshold 0.30→0.00, regime scale
  0.20→0.20"*. La soglia S1 è ora a **0.00** e la scala di regime al floor 0.20. F8 resta in shadow
  (`apply_regime_scale: false`): il log riporta `unscaled_weight=0.50 scaled_weight=0.10
  applied=false`, cioè il de-risk S1 sarebbe stato −80% del peso ma non è stato applicato. S4 non è
  triggerato (EWMA R +0.016, rolling P&L +$79.22, threshold 0.30, scale 1.0). Da tenere presente che
  la sequenza di perdite S1 su cui si basa quel trigger è la stessa che #134 ha mostrato essere
  double-counted.

---

*Nota di affidabilità: le posizioni e i P&L provengono dalla tabella `trades` di Postgres, che è
nota per poter divergere dal book effettivo del broker (cfr. memoria progetto sul deadband/accounting
DB). Il delta mark-to-market di §4.1 è una ricostruzione close-to-close da barre Alpaca, non un dato
di conto Alpaca.*
