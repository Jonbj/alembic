# Alpha-miss report — 2026-09-11

Fonte dei numeri: `docs/evidence/dossier/2026-09-11.json` (schema 3.1, generato 2026-09-14T08:00:32Z,
prezzi Alpaca SIP adjustment=all). Nessun numero di questo report è ricalcolato: dove il dossier
contiene il dato, vince il dossier. L'interpretazione delle cause, la lettura del testo degli
articoli e le segnalazioni sono mie.

Periodo di sola osservazione (`docs/evidence/OBSERVATION_CHARTER.md`, freeze taratura fino al
2026-09-28): nessuna proposta di taratura o di fix.

---

## 1. Executive summary

Giornata larga e rialzista sulla watchlist: SPY +0,85%, QQQ +0,87%, dispersione cross-sectional
1,80%, **7 mover a |return| ≥ 3%, tutti al rialzo, zero al ribasso**. Dei 7, **4 erano già a libro
all'apertura** (DELL, NOK, CSCO, MRVL — held_at_open_rate 4/7 = 57,1%) e **3 erano opportunità
d'ingresso mancate** (ARM +4,17%, IBM +3,96%, TXN +3,82%). La causa prevalente dei miss è
**NO_NEWS** (2 su 3: IBM e TXN a zero righe `news_log`); il terzo, ARM, ha una sola riga, un
fan-out a 8 ticker su un pezzo di whale-activity, scorato 0,000 → THIN_NEUTRAL.
I 6 ingressi della giornata (NOW, ADBE, PLTR, SPCX, ORCL, TSLA) non toccano nessun mover;
`profitable_capture_rate` = 0/3. Realizzato del giorno +11,84 $ su 3 chiusure, tutte S4.
Il fatto strutturale della seduta non è il miss ma il **sottodimensionamento del catturato**:
DELL (+11,98%, quasi tre volte il secondo mover della seduta) era detenuto per 481,50 $ di nozionale PIT all’open
contro uno slot S4 normale da ~2.200 $, e il rabbocco è stato bloccato da P0-05 alle 17:22.
NOK e MRVL sono contati "catturati" con 6,30 $ e 130,20 $ di nozionale residuo.
Tre cicli portfolio su 24 (16:22/16:37/16:52) sono abortiti fail-closed per outage dell'endpoint
`/v2/clock` di Alpaca, e il task Celery risulta comunque `succeeded`.

---

## 2. Rendimenti completi della watchlist (96 simboli, 0 senza barre)

Soglia mover: **|return| ≥ 3%** (soglia del dossier, `soglia_mover` = 0.03). È la soglia della serie
storica di questo report: la conservo per non introdurre una discontinuità nella serie osservata.

| # | Simbolo | Return % | Catturato |
|---|---------|---------:|-----------|
| 1 | DELL | +11,98 | sì (detenuto, sub-slot) |
| 2 | NOK | +4,80 | sì (detenuto, 6,30 $) |
| 3 | CSCO | +4,37 | sì (detenuto) |
| 4 | ARM | +4,17 | **no** |
| 5 | MRVL | +4,03 | sì (detenuto, 130,20 $) |
| 6 | IBM | +3,96 | **no** |
| 7 | TXN | +3,82 | **no** |
| 8 | ERIC | +3,00 | no (sotto soglia: 0,029970) |
| 9 | TM | +2,97 | no |
| 10 | TMUS | +2,92 | no |
| 11 | QCOM | +2,88 | no |
| 12 | BA | +2,76 | no |
| 13 | INTC | +2,61 | no |
| 14 | AMD | +2,49 | sì (detenuto) |
| 15 | SPCX | +2,04 | sì (ingresso 15:37) |
| 16 | T | +2,00 | no |
| 17 | CRM | +1,94 | no |
| 18 | AMZN | +1,94 | no |
| 19 | SOXX | +1,86 | sì (detenuto) |
| 20 | NFLX | +1,83 | no |
| 21 | GOOGL | +1,77 | sì (detenuto) |
| 22 | AAPL | +1,75 | sì (detenuto) |
| 23 | CAT | +1,69 | sì (detenuto) |
| 24 | SONY | +1,62 | no |
| 25 | PG | +1,61 | no |
| 26 | RDDT | +1,56 | sì (uscita 14:52) |
| 27 | INFY | +1,47 | no |
| 28 | ADBE | +1,37 | sì (ingresso 14:22 / uscita 16:07) |
| 29 | WMT | +1,34 | no |
| 30 | XLK | +1,32 | sì (detenuto) |
| 31 | MMM | +1,30 | no |
| 32 | VZ | +1,28 | no |
| 33 | AXP | +1,24 | no |
| 34 | TSM | +1,22 | sì (detenuto) |
| 35 | UBS | +1,06 | sì (detenuto) |
| 36 | NOW | +1,04 | sì (ingresso 14:07) |
| 37 | HD | +1,00 | no |
| 38 | WFC | +0,94 | no |
| 39 | GS | +0,92 | no |
| 40 | BIDU | +0,89 | no |
| 41 | V | +0,88 | no |
| 42 | QQQ | +0,87 | no |
| 43 | SPY | +0,85 | sì (detenuto) |
| 44 | SHEL | +0,84 | sì (detenuto) |
| 45 | ABBV | +0,83 | sì (detenuto) |
| 46 | PLTR | +0,83 | sì (ingresso 15:37 / uscita 18:22) |
| 47 | MS | +0,81 | sì (detenuto) |
| 48 | JPM | +0,76 | sì (detenuto) |
| 49 | DIS | +0,69 | no |
| 50 | BABA | +0,68 | no |
| 51 | MA | +0,68 | no |
| 52 | XLF | +0,67 | sì (detenuto) |
| 53 | BRK.B | +0,66 | no |
| 54 | F | +0,65 | no |
| 55 | MSFT | +0,65 | no |
| 56 | ASML | +0,64 | sì (detenuto) |
| 57 | CVX | +0,61 | sì (detenuto) |
| 58 | RIO | +0,57 | sì (detenuto) |
| 59 | META | +0,57 | no |
| 60 | AMAT | +0,55 | sì (detenuto) |
| 61 | ROKU | +0,53 | sì (detenuto) |
| 62 | TSLA | +0,52 | sì (ingresso 19:07) |
| 63 | NKE | +0,49 | no |
| 64 | XOM | +0,46 | sì (detenuto) |
| 65 | IWM | +0,41 | no |
| 66 | AZN | +0,33 | no |
| 67 | XLE | +0,32 | sì (detenuto) |
| 68 | DB | +0,32 | no |
| 69 | AVGO | +0,32 | no |
| 70 | COST | +0,26 | no |
| 71 | PFE | +0,25 | sì (detenuto) |
| 72 | C | +0,23 | sì (detenuto) |
| 73 | BAC | +0,21 | sì (detenuto) |
| 74 | SAP | +0,20 | no |
| 75 | JD | +0,15 | no |
| 76 | CMCSA | +0,12 | no |
| 77 | BP | +0,04 | sì (detenuto) |
| 78 | NVDA | −0,03 | no |
| 79 | GE | −0,15 | no |
| 80 | XLV | −0,18 | sì (detenuto) |
| 81 | MCD | −0,21 | no |
| 82 | MU | −0,22 | sì (detenuto) |
| 83 | SNOW | −0,22 | sì (detenuto) |
| 84 | JNJ | −0,29 | sì (detenuto) |
| 85 | VALE | −0,33 | sì (detenuto) |
| 86 | SBUX | −0,48 | sì (detenuto) |
| 87 | MRK | −0,54 | sì (detenuto) |
| 88 | GM | −0,58 | sì (detenuto) |
| 89 | LLY | −0,65 | sì (detenuto) |
| 90 | HOOD | −0,67 | no |
| 91 | PBR | −0,84 | sì (detenuto) |
| 92 | ORCL | −1,74 | sì (ingresso 18:07) |
| 93 | NVO | −2,14 | no |
| 94 | PANW | −2,32 | no |
| 95 | UNH | −2,37 | sì (detenuto) |
| 96 | WDC | −2,98 | sì (detenuto) |

"Catturato = sì (detenuto)" significa posizione viva nello snapshot PIT all'open RTH, non una
decisione presa nella seduta.

---

## 3. Miss classificati

Solo i 3 mover non detenuti sono candidati miss per costruzione (`funnel_v2`: `esclusi_pipeline`
= 4 `held`). Tutti e tre classificati dal funnel v2 come `NO_RELEVANT_NEWS`.

| Simbolo | Return % | Categoria | Evidenza |
|---------|---------:|-----------|----------|
| IBM | +3,96 | **NO_NEWS** | 0 righe `news_log`, 0 articoli, 0 segnali. Calendario societario `NOT_OBSERVED` (FMP + Alpaca Corporate Actions entrambe interrogate con successo). Residuo vs SPY +3,11%, vs XLK +2,64% → movimento idiosincratico senza alcuna copertura. Opportunità netta v2 accessibile **+14,26 $** (entry 241,59 alla prima barra eleggibile 14:10, exit close 243,29; lordo 87,15 $). |
| TXN | +3,82 | **NO_NEWS** | 0 righe `news_log`. Calendario `NOT_OBSERVED`. **5 sedute consecutive a zero articoli** nel blind-set (finestra 08-28→09-11): non è un buco di un giorno, è un ticker spento. Opportunità netta v2 **+14,19 $** (entry 266,83 alle 14:10, exit 268,70; lordo 83,98 $). |
| ARM | +4,17 | **THIN_NEUTRAL** | 1 sola riga, tutta fan-out (`quota_righe_fanout` = 1,0): `news_log` 10624, "10 Information Technology Stocks Whale Activity In Today's Session", 8 ticker, `relevance=TAG_UNCONFIRMED`, `extraction_method=source_metadata`, pubblicata 17:35 e ingerita 17:52. Segnale 10624 score **0,000** (confidence 0,200). Legacy: `OFF_TOPIC_NON_DECIDIBILE`. Opportunità netta v2 **−11,97 $**: al primo ciclo eleggibile (18:07, prezzo 266,09) il movimento era già finito e il close è 264,79 — catturarlo avrebbe perso denaro. |

Conteggi per il ledger: **NO_NEWS 2 · THIN_NEUTRAL 1 · WRONG_SIGN 0 · FILTERED 0 ·
OUT_OF_STRATEGY_SCOPE 0**. `avoidable_miss_count` del dossier = 2.

Nessun mover è stato scartato da ranking/breadth/hysteresis: i due `SKIP_PYRAMIDING` su mover
(DELL, MRVL) riguardano simboli **già detenuti**, quindi non sono miss d'ingresso e non entrano
in questa tabella. Sono trattati al §9.

---

## 4. Titoli catturati — esito

<!-- alpha-miss-book:start -->
<!-- alpha-miss-book-manifest: {"schema":1,"ingressi":["NOW","ADBE","PLTR","SPCX","ORCL","TSLA"],"chiusure":["RDDT","ADBE","PLTR"]} -->

Dati deterministici dal dossier; la prosa seguente li annota e non li sostituisce.

| Tipo | Simbolo | Strategia | Ora UTC | Prezzo | Quantità | P&L netto | Motivo / qualità |
|---|---|---|---|---:|---:|---:|---|
| IN | NOW | S4 | 14:07 | $133.7600 | 10.7571 | — | percentile 83.00%; denominatore intraday valido |
| IN | ADBE | S4 | 14:22 | $246.1413 | 5.8454 | — | percentile 33.58%; denominatore intraday valido |
| IN | PLTR | S4 | 15:37 | $166.8600 | 8.6279 | — | percentile 45.48%; denominatore intraday valido |
| IN | SPCX | S4 | 15:37 | $148.0338 | 9.7251 | — | percentile 35.65%; denominatore intraday valido |
| IN | ORCL | S4 | 18:07 | $152.4871 | 9.3725 | — | percentile 16.38%; denominatore intraday valido |
| IN | TSLA | S4 | 19:07 | $364.7400 | 3.9400 | — | percentile 44.48%; denominatore intraday degenere: quota non interpretabile |
| OUT | RDDT | S4 | — | $155.2000 | 9.2778 | −$5.88 | portfolio_sell |
| OUT | ADBE | S4 | — | $249.0600 | 5.8454 | +$16.27 | hold_minimum_expiry |
| OUT | PLTR | S4 | — | $167.1200 | 8.6279 | +$1.45 | portfolio_sell |
<!-- alpha-miss-book:end -->

### 4a. Mover detenuti all'apertura (esposizione passiva, nessuna decisione della seduta)

| Simbolo | Return % | Strategia | Nozionale all'open | P&L passivo | Nota |
|---------|---------:|-----------|-------------------:|------------:|------|
| DELL | +11,98 | S1 | 481,50 $ (0,9295 az.) | **+45,75 $** | Slot S4 pieno = ~2.200 $: il libro era esposto al 22% di uno slot sul mover più forte della seduta. Rabbocco bloccato da P0-05 alle 17:22 (vedi §9). |
| CSCO | +4,37 | S4 | 1.865,90 $ (17,136 az.) | **+55,52 $** | Unico mover detenuto con nozionale pieno. Copertura news del giorno: 1 articolo, `TAG_UNCONFIRMED`, fan-out da un pezzo NVIDIA, score 0,0465. Cattura per inerzia, non per segnale. |
| MRVL | +4,03 | S1 | 0,00 $ PIT / 130,20 $ a DB (0,5515 az.) | 0,00 $ | `SKIP_PYRAMIDING` alle 15:22. Divergenza fra `qty_open` PIT (0) e `qty` a DB (0,5515) — vedi §9. |
| NOK | +4,80 | S1 | 0,00 $ PIT / 6,30 $ a DB (0,5640 az.) | 0,00 $ | Segnale 10517 delle 14:03, score **+0,2013**, segno corretto, sotto il gate 0,30. |

### 4b. Ingressi della seduta (6, tutti S4, nessuno su un mover)

| Simbolo | Ora UTC | Entry | Percentile d'ingresso | MTM EOD | vs apertura | Quota movimento già avvenuta |
|---------|---------|------:|----------------------:|--------:|------------:|-----------------------------:|
| NOW | 14:07 | 133,76 | 0,830 | −13,23 $ | +21,84 $ | 1,606 |
| ADBE | 14:22 | 246,14 | 0,336 | +35,59 $ | +58,80 $ | 0,395 |
| PLTR | 15:37 | 166,86 | 0,455 | +3,19 $ | −7,51 $ | 1,425 |
| SPCX | 15:37 | 148,03 | 0,356 | +30,89 $ | +11,72 $ | −1,636 |
| ORCL | 18:07 | 152,49 | 0,164 | −20,69 $ | −132,62 $ | 0,844 |
| TSLA | 19:07 | 364,74 | 0,445 | +2,76 $ | +4,89 $ | 0,436 (denominatore degenere) |

Mediana `quota_movimento_precedente_al_segnale` = **0,640**: su 3 ingressi su 6 il movimento era
già interamente consumato (≥ 1,0).

### 4c. Chiusure (3, tutte S4)

| Simbolo | Exit | P&L netto | Motivo | Ore di tenuta | Drift post-uscita |
|---------|-----:|----------:|--------|--------------:|------------------:|
| RDDT | 155,20 | **−5,88 $** | `portfolio_sell` | 20,75 | +23,84 $ |
| ADBE | 249,06 | **+16,27 $** | `hold_minimum_expiry` | 1,75 | +18,53 $ |
| PLTR | 167,12 | **+1,45 $** | `portfolio_sell` | 2,75 | +0,95 $ |

Realizzato del giorno **+11,84 $** (S4 +11,84 $, S1 0,00 $). Tutte e tre le uscite lasciano drift
positivo sul tavolo (somma +43,32 $), coerente con `decision_quality.exit_effect_usd` = −43,32 $.

---

## 5. Cecità lato uscita (posizioni detenute)

Da `copertura_uscita` (42 posizioni, `n_indeterminati` = 0: **nessuna riga con
`cieco_lato_uscita: null`**, quindi nessun dato mancante da dichiarare).

| Ticker | Strategia | `ritorno_da_ingresso` | `sedute_consecutive_senza_righe` | `fonti_osservate_finestra` | Nozionale |
|--------|-----------|----------------------:|---------------------------------:|----------------------------|----------:|
| ASML | S1 | **−3,98%** | 4 | `alpaca_benzinga` | 641,19 $ |
| SBUX | S1 | **−6,31%** | 2 | `alpaca_benzinga` | 649,88 $ |

Entrambe **ancora aperte** a fine seduta (`uscita_nella_seduta` = false), quindi il ritorno citato
è la perdita accumulata dall'ingresso al close, non un realizzato. Nella seduta ASML ha fatto
+0,64% e SBUX −0,48% (`ritorno_seduta`): il movimento del giorno non è il problema, l'assenza
prolungata di qualunque riga su cui costruire un segnale di uscita lo è.
`fonti_osservate_finestra` non è vuota in nessuno dei due casi: i provider erano vivi e
interrogati, semplicemente non hanno reso nulla su questi ticker.

Aggregato: 13/42 posizioni a copertura grezza nulla, **22/42 a copertura effective-timely nulla**,
10/42 in perdita marcata, 2 cieche, nozionale cieco 1.291,08 $.

Nel blind-set a 10 sedute, ASML e SBUX hanno **9 sedute consecutive a zero articoli
effective-timely** — sono fra i 15 ticker in quella condizione.

---

## 6. Backstop NO_NEWS

Popolazione: **39 simboli a zero righe `news_log`** (2 mover, 37 non-mover, 0 con return mancante).

### 6a. Marker calendario

| Simbolo | Return % | `observed_catalysts` |
|---------|---------:|----------------------|
| IBM | +3,96 | `[]` — calendario `NOT_OBSERVED` |
| TXN | +3,82 | `[]` — calendario `NOT_OBSERVED` |

`mover_observed` 0/2 (rate 0,0); `non_mover_observed` 1/37 (rate 2,70%) — l'unico marker
`CALENDAR` della giornata è su **MMM** (+1,30%, non-mover). Il marker significa solo che il
calendario societario aveva un evento osservato: **non** che esista un segnale sentiment o un
ordine. Le due sorgenti (FMP earnings-calendar e Alpaca Corporate Actions API) hanno risposto
entrambe, quindi lo 0/2 sui mover è un'osservazione, non un fallimento di fetch.

### 6b. Volume — `POST_HOC_EOD`, non point-in-time

`temporal_validity` = `POST_HOC_EOD`, `valid_for_signal_evaluation` = **false**. Volume di seduta e
etichetta mover sono noti solo al close: quanto segue descrive l'intera seduta e **non** dice che
il valore fosse disponibile prima del movimento. Nessuna soglia scelta, nessun false-positive rate
stimato — la valutazione ex-ante pre-registrata è separata (#451).

- IBM: volume 4.924.146, ADV20 4.838.747, sorpresa **+1,76%**.
- TXN: volume 5.257.913, ADV20 5.432.264, sorpresa **−3,21%**.
- Mediana sorpresa mover **−0,72%** contro non-mover **−21,81%**.

I due mover hanno volume in linea con il proprio ADV mentre la massa dei non-mover a zero news è
~22% sotto: la separazione mediana esiste, ma con 2 osservazioni sul lato mover non è nulla su
cui basare un giudizio.

### 6c. Copertura **raw** di `news_log` per settore (tutti i settori, inclusi gli zero su N)

Distinta dalla copertura effective-timely del §6d: non mescolare le due quote.

| Settore | ticker_with_news / ticker_universe | `raw_news_coverage_rate` | mover a zero news |
|---------|-----------------------------------:|-------------------------:|------------------:|
| etf_broad | 4/4 | 100,0% | 0 |
| semis | 12/15 | 80,0% | 1 (TXN) |
| healthcare | 6/9 | 66,7% | 0 |
| tech | 13/21 | 61,9% | 1 (IBM) |
| financials | 8/14 | 57,1% | 0 |
| consumer | 6/11 | 54,5% | 0 |
| materials | 1/2 | 50,0% | 0 |
| media | 2/5 | 40,0% | 0 |
| telecom | 2/5 | 40,0% | 0 |
| energy | 2/6 | 33,3% | 0 |
| industrials | 1/4 | 25,0% | 0 |

Nessun settore a 0 su N in copertura **raw** oggi.

### 6d. Confronto con la copertura effective-timely (`copertura_articoli.per_settore`)

Quota complessiva effective-timely: **38/96 ticker (39,6%)**, contro 57/96 in copertura raw.
Qui sì che compaiono gli zero su N:

| Settore | ticker coperti / universo | quota |
|---------|--------------------------:|------:|
| etf_broad | 3/4 | 75,0% |
| materials | 1/2 | 50,0% |
| tech | 10/21 | 47,6% |
| semis | 7/15 | 46,7% |
| healthcare | 4/9 | 44,4% |
| financials | 6/14 | 42,9% |
| media | 2/5 | 40,0% |
| telecom | 2/5 | 40,0% |
| industrials | 1/4 | 25,0% |
| consumer | 2/11 | 18,2% |
| **energy** | **0/6** | **0,0%** |

---

## 7. Pattern osservato

**Rally largo su hardware/infrastruttura legacy, non una rotazione.** Zero mover negativi su 96
simboli, SPY +0,85% e QQQ +0,87%: nessun gruppo ha finanziato il movimento, quindi non c'è un lato
corto della rotazione da leggere. Il tema è coerente e riconoscibile senza forzature: i 7 mover
sono **DELL, NOK, CSCO, ARM, MRVL, IBM, TXN**, cioè server/networking/telecom-equipment e
semiconduttori non-AI-puri; appena sotto soglia proseguono ERIC +3,00%, TMUS +2,92%, QCOM +2,88%,
INTC +2,61%. Sul lato opposto della classifica NVDA è **−0,03%** e AVGO +0,32%: i leader AI del
2026 sono fermi mentre l'hardware di seconda fila corre. La coda negativa (WDC −2,98%, UNH −2,37%,
PANW −2,32%, NVO −2,14%, ORCL −1,74%) non compone un settore: sono nomi idiosincratici.

DELL a +11,98% è un'eccezione di scala rispetto al resto del gruppo (secondo mover a +4,80%) e
guida il tema, ma la notizia che il sistema ha ricevuto su DELL alle 16:53 era un riepilogo di
mercato che **riportava il movimento già avvenuto** (§9).

Regime rilevato: `SIDEWAYS`, `regime_mult` 0,70, VIX 17,84 (osservato sul 2026-09-10, FRED:VIXCLS).

---

## 8. Confronto con i giorni precedenti

Serie disponibile in `docs/evidence/market_daily.jsonl` (ultima riga 2026-09-08; 09-09 e 09-10
non hanno una riga, quindi il confronto salta due sedute).

1. **Zero mover negativi è raro ma non nuovo.** Unico precedente identico nella finestra:
   2026-09-03 ("rally largo e non rotazionale, zero mover negativi, SPY +1,05%"). In entrambi i
   casi il numero di catturati resta basso (4 oggi, 4 il 09-03) nonostante il mercato vada in una
   sola direzione: il sistema non converte il beta largo in ingressi.
2. **`watchlist_zero_news` = 39 è il secondo valore migliore della finestra**, dietro 37 del
   2026-09-08 e davanti a 45-60 delle sedute precedenti. La copertura grezza migliora; la
   copertura effective-timely resta a 39,6%, cioè sotto il 47,9% del 09-08. Il miglioramento del
   conteggio grezzo non si traduce in copertura utilizzabile.
3. **Il tema hardware/semis ricorre in 8 delle ultime 15 sedute** (08-12, 08-17, 08-18, 08-19,
   08-20, 08-28, 09-04, 09-08 e oggi), con segno alterno. Non è un pattern nuovo della giornata;
   è la struttura dominante della watchlist in questo periodo.
4. **MRVL compare come mover per la quinta volta nella finestra** (08-17, 08-18, 08-20, 08-28 e
   oggi) e in nessuna di queste è mai stato oggetto di una decisione d'ingresso: è detenuto con
   nozionale residuo e bloccato da P0-05.
5. **DELL è la seconda occorrenza di `SKIP_PYRAMIDING` su DELL nella serie** (la precedente è del
   2026-09-03, sentiment +0,478, controfattuale +12,89 $). Stesso simbolo, stesso guard, stesso
   esito: il libro resta a una frazione di slot su un nome che si muove.

Oltre questi, non speculo.

---

## 9. Segnalazioni

Nessuna proposta di taratura o di fix: solo evidenza. Dove una causa sembra un difetto piuttosto
che un limite noto, lo dico e mi fermo lì.

**[F-001] Copertura news bassa sulla watchlist.** 39/96 simboli (40,6%) a zero righe `news_log`;
copertura effective-timely 38/96 (39,6%); energy a **0/6** effective-timely; due sole fonti
(`alpaca_benzinga` 93 articoli, `gdelt_gkg` 8) con HHI di fonte 0,818. Concentrazione per ticker:
ADBE 14 + ORCL 13 = 27 dei 101 articoli unici, top-5 share 47,3%. Entrambi i miss NO_NEWS della
giornata (IBM, TXN) ricadono qui, e **TXN è al quinto giorno consecutivo a zero articoli**.
Costo congetturale 171,13 $ (IBM 87,15 + TXN 83,98, stimatore legacy del dossier su slot 2.200 $).

**[F-031] Il guard anti-pyramiding P0-05 blocca il rabbocco su due mover detenuti a nozionale
sub-slot.** DELL: `SKIP_PYRAMIDING` alle 17:22:03, nozionale inteso 2.195,68 $, mentre il libro
teneva 481,50 $ (0,9295 azioni, 22% di uno slot) sul mover a +11,98% della giornata. MRVL:
`SKIP_PYRAMIDING` alle 15:22:04, nozionale inteso 2.193,80 $, libro a 130,20 $ a DB e 0 PIT.
Costo attribuito 41,47 $ su controfattuale corto (DELL: 558,43 → 567,29 = +1,587% × 2.195,68 =
+34,85 $; MRVL: 235,39 → 236,10 = +0,302% × 2.193,80 = +6,62 $). **Nota di aggiornamento al
finding**: il titolo dice "non lascia alcuna traccia in `execution_decisions`" — oggi le 7 righe
`SKIP_PYRAMIDING` della giornata (CVX, MRVL, AMAT, AMD, DELL, ORCL, BAC) **sono** persistite con
`intended_notional_usd` valorizzato. La tracciabilità è stata risolta; il comportamento del guard
no.

**[F-030] La notizia arriva quando il movimento è già avvenuto.** Caso limite della serie: l'unico
segnale DELL sopra il gate (id 10596, score **+0,390**, ensemble non-fallback, generato 17:15) nasce
da `news_log` 10596, pubblicata 16:53 e intitolata *"S&P 500 Snaps 4-Day Decline as Oil Cools,
**Dell Jumps 11%**: Stock Market..."*. La notizia **è** il movimento: il titolo riporta il ritorno
già realizzato. Stesso schema su MRVL (segnale 10647, +0,3159, 19:02, da *"Marvell Stock Is Up 180%
This Year"*) e su NOK (segnale 10517, +0,2013, 14:03, da *"What's Going On With Nokia Stock
Friday?"*). Sui 6 ingressi della seduta la mediana di `quota_movimento_precedente_al_segnale` è
0,640 con 3 su 6 ≥ 1,0. Costo non stimato: il costo del ritardo su DELL/MRVL è già attribuito a
F-031 e attribuirlo due volte gonfierebbe la serie.

**[F-012] L'unica copertura del solo miss non-NO_NEWS è un fan-out multi-ticker.** ARM: 1 riga su
1, `quota_righe_fanout` = 1,0, articolo "10 Information Technology Stocks Whale Activity In Today's
Session" a 8 ticker, `relevance=TAG_UNCONFIRMED`, score 0,000. Sul totale della giornata:
`mapping_fanout_extra` 73 su 174 righe (42,0%) e `TAG_UNCONFIRMED` 98 su 174 (56,3%) — più della
metà delle righe scorate non ha una rilevanza confermata sull'emittente. Costo 0,00 $: lo
stimatore v2 dà opportunità netta accessibile **negativa** (−11,97 $) perché al primo ciclo
eleggibile (18:07) il movimento era finito. È un caso raro in cui il miss è quantificabile e non
costa nulla.

**[F-009] Il gate d'ingresso 0,30 scarta un segnale col segno corretto su un mover.** NOK, segnale
10517 delle 14:03, score +0,2013, segno corretto su un +4,80%. `SKIP_ENTRY_GATE` è il secondo
motivo di scarto della giornata (576 su 1.733 intenti, 33,2%). Costo non stimato **di proposito**:
NOK era già detenuto, quindi anche superando il gate l'ordine sarebbe finito in P0-05 come DELL e
MRVL. Il gate non è il vincolo che lega oggi; attribuirgli un costo sarebbe doppio conteggio con
F-031.

**[F-019] La latenza di ingestione consuma la finestra di entry-freshness.** `SKIP_ENTRY_FRESHNESS`
è il **primo** motivo di scarto della giornata: 711 su 1.733 intenti (41,0%), davanti a
`SKIP_ENTRY_GATE` (576), `SKIP_FALLBACK` (191) e `SKIP_STALE` (145). Su 1.733 intenti, 6
`SUBMITTED` (0,35%). Esempi di latenza pubblicazione→ingestione sulla giornata: DELL 16:53→17:15
(22 min), ARM 17:35→17:52 (17 min), NOK 13:24→14:03 (39 min), TMUS 11:46→13:32 (106 min). Costo non
stimato.

**[F-018] Il bot token Telegram compare in chiaro nei log.** 8 righe INFO di httpx nel log
persistente `logs/containers/worker-2026-09-11.log` con l'URL completo
`https://api.telegram.org/bot8611445937:AAH3...` — fra queste, l'alert dell'abort per
`clock_unavailable` delle 16:22. Il log è persistente e committabile. Costo non stimabile.

**[F-048] Divergenza fra quantità a DB e quantità PIT al broker su due posizioni.** MRVL e NOK
compaiono in `copertura_uscita` con `qty` 0,5515 e 0,5640 (nozionale 130,20 $ e 6,30 $) ma in
`snapshot_apertura` con `qty_open` = 0,0 e `opening_notional_usd` = 0,0. Le due misure hanno
definizioni diverse (DB vs PIT broker), ma la divergenza è esattamente la forma del finding. Il
log delle 16:07 conferma la popolazione: `#161: 10/45 held positions are unprotectable (qty < 1):
['AMAT','AMD','ASML','CAT','DELL','LLY','MRVL','NOK','SPY','WDC']`. Costo non stimato.

**[F-074] (nuovo) Un outage dell'endpoint `/v2/clock` di Alpaca cancella 3 cicli portfolio su 24 e
il task Celery risulta comunque `succeeded`.** `portfolio_cycles` ha 21 righe per la seduta contro
24 slot schedulati; il beat ha inviato tutti e 24 i task. I tre mancanti sono 16:22:00, 16:37:00 e
16:52:00: nel log del worker ciascuno chiude con
`Could not fetch market clock: {"message":"Internal Server Error"} — aborting cycle (fail-closed)`
e con `run_portfolio_cycle[...] succeeded in 3.6s: {'error': 'clock_unavailable'}`. L'outage
lato Alpaca copre 16:16:03→17:03:03 (99 righe "market clock" nel log fra worker e task mobile).
**45 minuti consecutivi di sessione senza alcuna decisione di portafoglio.** Il comportamento
fail-closed è corretto e un alert Telegram è partito; il difetto è che lo stato finale del task
è `succeeded`, quindi qualunque monitor che guardi l'esito Celery vede 24/24 verdi. Apro un id
nuovo e non aggancio a F-017 (regime detection) né a F-065 (ciclo sentiment che non parte e non
lascia traccia): il sottosistema è diverso, la causa è una dipendenza esterna al broker, e qui una
traccia e un alert **esistono** — è solo il codice d'uscita del task a mentire. Se a fine periodo
si decidesse che i tre sono la stessa affermazione ("un fallimento che azzera una funzione critica
è registrato come `succeeded`"), si fondono. Costo non stimato: nessun ordine risultava pendente
nella finestra e il ciclo delle 17:07 ha ripreso regolarmente.

**[F-075] (nuovo) `held_at_open_rate` conta come catturati mover detenuti con nozionale residuo
sotto il 6% di uno slot.** Il funnel classifica 4 dei 7 mover come `PASSIVE_EXPOSURE` (quindi non
miss, `held_at_open_rate` 4/7 = 57,1%) indipendentemente da quanto libro ci fosse sopra. Nei fatti:
CSCO 1.865,90 $ (85% di uno slot da 2.200 $), DELL 481,50 $ (22%), MRVL 130,20 $ a DB e 0 PIT
(5,9%), NOK 6,30 $ a DB e 0 PIT (0,3%). Il P&L passivo lo conferma: CSCO +55,52 $, DELL +45,75 $,
MRVL e NOK **0,00 $**. Su un +4,80% e un +4,03% il libro ha guadagnato zero, e la metrica di
copertura li conta come catturati. Non aggancio a F-014 (telemetria di `portfolio_cycles`) né a
F-022 (stop protettivi sulla parte intera): l'affermazione riguarda la **metrica di miss** che
questo ledger pubblica ogni giorno, e ne cambia la lettura retroattiva — `catturati` non è
un conteggio di esposizione utile finché non è pesato per nozionale. È un'osservazione
strutturale, non un difetto di codice. Costo non stimabile per giornata.

### Dove sospetto un difetto e mi fermo

- **F-074** ha la forma del difetto, non del limite noto: `succeeded` su un ciclo abortito è una
  bugia dell'istrumentazione, non una scelta di rischio. La decisione se aprire un'issue è
  dell'operatore.
- **F-031** continua a essere, a mio avviso, un limite di progetto applicato a una popolazione per
  cui non è stato pensato (posizioni residue frazionarie ereditate da S1) più che un bug. Non
  propongo nulla.
- Tutto il resto della lista è ricorrenza di evidenza già registrata.

---

## Appendice — provenienza e cavea

- **Cicli portfolio**: 21 righe, un solo gap > 16 min (16:07 → 17:07, 60 min). I 6 cicli
  20:07–21:22 chiudono in ~0,45 s: fuori RTH, no-op atteso.
- **Primo ciclo alle 14:07 UTC** contro apertura RTH alle 13:30 UTC: 37 minuti di sessione senza
  ciclo, coerente con F-021 (finestre beat in ora UTC fissa, DST ignorato). Non lo registro come
  occorrenza separata perché non ha prodotto alcun effetto misurabile oggi — i tre mover mancati
  non avevano segnale in quella finestra.
- **Equity di fine giornata**: 109.480,15 $ dalla riga etichettata `2026-09-11` di
  `/v2/account/portfolio/history` (timeframe 1D, timestamp a 00:00Z). L'etichettatura di quelle
  righe è ambigua ed è oggetto di F-053 (storico P&L spostato di un giorno di calendario); il
  valore è riportato così com'è, senza correzione.
- **MTM del libro aperto**: +4,53 $, da `decision_quality.summary.actual_intraday_pnl_usd` (coorte
  dello snapshot d'apertura, 42 posizioni, 32.265,44 $ di nozionale). Non è la variazione di equity
  del conto.
- **Invariante rank/ranking_score** (#401): 110 righe esaminate, **0 violazioni**.
- **`decision_signal_id_coverage`**: 614/620 righe con `signal_id` (99,03%); 2 regressioni
  segnalate dal dossier.
- **`guardia_contraddizione`**: 0 intenti soppressi oggi, 4 nella finestra di 12 sedute, tutti non
  eseguiti e senza P&L.
- **Calendario earnings**: `OBSERVED`, 0 simboli flaggati, 0 missingness, streak di sedute
  `UNKNOWN` = 0. Nessun mover della giornata aveva earnings.
