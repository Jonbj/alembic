# Alpha Miss Report — 2026-08-21

Fonte numerica primaria: `docs/evidence/dossier/2026-08-21.json` (deterministico). Query dirette
via `docker exec alembic-postgres-1 psql` per trades, portfolio_cycles, sentiment_signals,
execution_decisions, news_log. Nessun ricalcolo dei numeri già presenti nel dossier.

## 1. Executive summary

11 dei 96 simboli watchlist si sono mossi ≥3% (soglia `soglia_mover=0.03` del dossier, coerente
con la serie storica): 9 al rialzo, 2 al ribasso. Di questi, **6 erano già "catturati"**: HOOD
(unico nuovo ingresso S4 della giornata, ore 17:07) e cinque posizioni legacy/S1 già in
portafoglio da settimane (GS, SNOW, MS, RIO, MRVL) senza nuovo ordine. **5 sono miss**: PLTR e F
(NO_NEWS, zero righe in news_log), BABA (segno corretto ma sceso sotto il gate 0.30 per decay fra
generazione e valutazione, comunque long-only irrilevante — THIN_NEUTRAL), ORCL (unico articolo
utile un fanout a 5 ticker che non cita il titolo — THIN_NEUTRAL/OFF_TOPIC), TSLA (unico segnale
rilevante -0.36 su recall auto, di segno opposto al +5.14% di chiusura — WRONG_SIGN). Causa
dominante nominale: NO_NEWS (2/5), ma il costo congetturale reale è quasi interamente sui due
NO_NEWS puri ($141.68); gli altri tre hanno costo $0.00 verificato (BABA/ricadeva comunque nel
vincolo long-only; TSLA e ORCL sotto soglia). Portfolio_cycles regolare, 24 cicli, nessun gap
oltre i 15 minuti attesi. Nessun difetto nuovo isolato oggi: le cinque segnalazioni sono ricorrenze
di pattern già a ledger (F-001, F-002, F-009, F-012, F-023). Giornata positiva per il book: NAV
109.843,78 → 110.131,84 ($+288,06), realizzato $−1,07 (chiusura INTC), MTM stimato sul book aperto
$+274,55.

## 2. Tabella rendimenti completa (96 simboli)

Fonte: Alpaca SIP, adjustment=all, close vs close precedente (dal dossier).

| Simbolo | Return % | Catturato |
|---|---:|---|
| HOOD | +13.70% | **Sì** — nuovo ingresso S4 |
| TSLA | +5.14% | No — miss (WRONG_SIGN) |
| GS | +3.73% | Sì — legacy in portafoglio |
| SNOW | +3.58% | Sì — S1 in portafoglio |
| PLTR | +3.44% | No — miss (NO_NEWS) |
| MS | +3.25% | Sì — legacy in portafoglio |
| ORCL | +3.10% | No — miss (THIN_NEUTRAL/OFF_TOPIC) |
| RIO | +3.06% | Sì — legacy in portafoglio |
| F | +3.00% | No — miss (NO_NEWS) |
| SBUX | +2.97% | — sotto soglia 3% |
| TM | +2.66% | — sotto soglia |
| VALE | +2.53% | — sotto soglia |
| PANW | +2.41% | — sotto soglia |
| MRK | +2.39% | — sotto soglia |
| SPCX | +2.22% | — sotto soglia |
| GM | +2.07% | — sotto soglia |
| RDDT | +1.98% | — sotto soglia |
| CRM | +1.82% | — sotto soglia |
| DELL | +1.68% | — sotto soglia |
| CMCSA | +1.63% | — sotto soglia |
| COST | +1.55% | — sotto soglia |
| CAT | +1.53% | — sotto soglia |
| C | +1.53% | — sotto soglia |
| AXP | +1.46% | — sotto soglia |
| V | +1.45% | — sotto soglia |
| SONY | +1.44% | — sotto soglia |
| NKE | +1.37% | — sotto soglia |
| UNH | +1.37% | — sotto soglia |
| BIDU | +1.35% | — sotto soglia |
| CSCO | +1.32% | — sotto soglia |
| NVO | +1.30% | — sotto soglia |
| XLV | +1.29% | — sotto soglia (ETF benchmark) |
| GOOGL | +1.22% | — sotto soglia |
| AVGO | +1.21% | — sotto soglia |
| PG | +1.20% | — sotto soglia |
| ABBV | +1.20% | — sotto soglia |
| MA | +1.18% | — sotto soglia |
| ADBE | +1.13% | — sotto soglia |
| ERIC | +1.09% | — sotto soglia |
| GE | +1.08% | — sotto soglia |
| JNJ | +1.07% | — sotto soglia |
| PFE | +1.01% | — sotto soglia |
| TMUS | +1.00% | — sotto soglia |
| XLF | +0.93% | — sotto soglia (ETF benchmark) |
| INFY | +0.93% | — sotto soglia |
| AZN | +0.91% | — sotto soglia |
| LLY | +0.88% | — sotto soglia |
| IBM | +0.85% | — sotto soglia |
| AMD | +0.81% | — sotto soglia |
| IWM | +0.77% | — sotto soglia (ETF benchmark) |
| ASML | +0.77% | — sotto soglia |
| META | +0.75% | — sotto soglia |
| PBR | +0.74% | — sotto soglia |
| SAP | +0.73% | — sotto soglia |
| TSM | +0.71% | — sotto soglia |
| DB | +0.69% | — sotto soglia |
| MCD | +0.68% | — sotto soglia |
| NOK | +0.59% | — sotto soglia |
| T | +0.56% | — sotto soglia |
| VZ | +0.53% | — sotto soglia |
| MMM | +0.49% | — sotto soglia |
| MSFT | +0.43% | — sotto soglia |
| DIS | +0.43% | — sotto soglia |
| SPY | +0.41% | — sotto soglia (benchmark) |
| QQQ | +0.35% | — sotto soglia (benchmark) |
| HD | +0.33% | — sotto soglia |
| ROKU | +0.24% | — sotto soglia |
| UBS | +0.17% | — sotto soglia |
| WFC | +0.17% | — sotto soglia |
| XLK | +0.11% | — sotto soglia (ETF benchmark) |
| WMT | +0.11% | — sotto soglia |
| JPM | +0.01% | — sotto soglia |
| QCOM | +0.01% | — sotto soglia |
| JD | −0.17% | — sotto soglia |
| XLE | −0.17% | — sotto soglia (ETF benchmark) |
| BRK.B | −0.21% | — sotto soglia |
| CVX | −0.24% | — sotto soglia |
| BAC | −0.27% | — sotto soglia |
| SHEL | −0.34% | — sotto soglia |
| BA | −0.42% | — sotto soglia |
| SOXX | −0.44% | — sotto soglia (ETF benchmark) |
| TXN | −0.47% | — sotto soglia |
| AMZN | −0.57% | — sotto soglia |
| XOM | −0.63% | — sotto soglia |
| AAPL | −0.63% | — sotto soglia |
| NFLX | −0.69% | — sotto soglia |
| MU | −0.77% | — sotto soglia |
| AMAT | −0.78% | — sotto soglia |
| BP | −0.84% | — sotto soglia |
| NOW | −0.98% | — sotto soglia |
| NVDA | −0.98% | — sotto soglia |
| WDC | −2.05% | — sotto soglia |
| INTC | −2.24% | — sotto soglia (chiusa oggi, vedi §4) |
| ARM | −2.95% | — sotto soglia |
| MRVL | −5.57% | Sì — S1 in portafoglio |
| BABA | −8.57% | No — miss (THIN_NEUTRAL, correttamente bloccato dal gate/long-only) |

Nessun simbolo senza dati (`simboli_senza_dati: []` nel dossier).

## 3. Miss classificati

Soglia mover: ≥3% in valore assoluto (`soglia_mover=0.03`, stessa usata dal dossier e dalla serie
storica dei report precedenti — coerenza cross-day più importante di una soglia diversa).

| Simbolo | Return % | Categoria | Evidenza |
|---|---:|---|---|
| PLTR | +3.44% | **NO_NEWS** | Zero righe in `news_log`, zero in `sentiment_signals` il 2026-08-21. |
| F | +3.00% | **NO_NEWS** | Zero righe in `news_log`, zero in `sentiment_signals` il 2026-08-21. |
| BABA | −8.57% | **THIN_NEUTRAL** (below-gate) | Articolo dedicato 17:15 ISSUER_SPECIFIC "Alibaba Stock Falls 7% on Profit Miss..." → segnale −0.315 (segno corretto). Per decay/velocity fra generazione e ciclo successivo, `execution_decisions.signal_score` letto dal gate alle 17:22/17:37/17:52 è −0.252 (\|0.252\|<0.30) → `SKIP_THRESHOLD` tre volte. Comunque irrilevante: mover al ribasso, libro long-only, BABA non detenuto → costo $0 verificato indipendentemente dal gate. Un secondo articolo (14:15, fanout, +0.09, "China's AI Agents...") è di segno opposto ma irrilevante (relevance UNKNOWN, subject_ticker null) e non ha mai raggiunto il gate. |
| ORCL | +3.10% | **THIN_NEUTRAL** (OFF_TOPIC) | Due articoli: 14:30 fanout a 5 ticker sui bond yield (non cita ORCL) → −0.028; 16:30 org_lookup, testo "Oracle Shares Rise as Dip Buyers Return..." ma `relevance=FALSE_ENTITY_MATCH` → +0.015. Entrambi ben sotto il gate 0.30. Nota: il secondo caso è curioso — il titolo cita esplicitamente "Oracle Shares Rise" eppure il resolver lo marca FALSE_ENTITY_MATCH; non abbastanza materiale per una nuova segnalazione (serve il body completo, non disponibile con `source_metadata`/troncato), segnalato qui come osservazione grezza. |
| TSLA | +5.14% | **WRONG_SIGN** | Il segnale più forte e più rilevante del giorno (14:16:24, −0.360, articolo dedicato "Tesla Recalls Nearly 3 Million EVs in China...") è di segno opposto al +5.14% di chiusura. Sovrascritto 2 secondi dopo (14:16:26) da +0.0126 su un articolo fanout non-TSLA (confronto SpaceX/Nvidia). L'ultimo segnale valutato dal gate nella giornata è 0.000 (18:15, fanout su debito USA). Nessuno dei segnali disponibili avrebbe comunque superato il gate 0.30 col segno giusto: il mercato ha ignorato il recall (probabilmente già prezzato/non materiale) mentre nessuna fonte scorata ha colto il vero traino del rialzo. |

Conteggi del giorno: NO_NEWS=2, THIN_NEUTRAL=2, WRONG_SIGN=1, FILTERED=0,
OUT_OF_STRATEGY_SCOPE=0. Causa dominante nominale: NO_NEWS (pareggio numerico con
THIN_NEUTRAL=2, ma NO_NEWS vince per convenzione nell'ordine canonico `CAUSE_ORDER` del
classificatore). Costo congetturale
concentrato sui due NO_NEWS (PLTR $75,63 + F $66,05 = $141,68, da
`opportunity_v2.gross_opportunity_usd`, size S4 tipica $2.200); gli altri tre miss hanno costo
$0,00 verificato (BABA/ribasso+long-only; ORCL e TSLA sotto soglia — nessun controfattuale
accessibile calcolato per questi ultimi due nel dossier).

## 4. Titoli catturati: esito

- **HOOD (+13.70%, nuovo ingresso S4, 17:07 UTC)**: entry price $107,82, qty 17,34. Segnale
  scatenante +0,372 (17:00:25) su articolo dedicato "Why Is Robinhood Stock Surging Friday?" —
  non fanout (content_hash esclusivo HOOD). **Timing subottimale**: `entry_percentile=0,827`
  (comprato all'82,7° percentile del range del giorno, cioè vicino al massimo), MTM a fine
  giornata solo $5,45 contro $121,89 che la stessa size avrebbe catturato entrando all'apertura
  (`vs_apertura`) — un'ulteriore istanza del pattern "ingresso rincorso" già documentato (es. MSFT
  07-30, $13,03 realizzati su un +15,5%).
- **GS (+3,73%), MS (+3,25%), RIO (+3,06%)**: posizioni legacy dal 2026-07-10, nessun nuovo
  ordine oggi. Nessuna riga porta `stop_strategy` (F-002): l'attribuzione a S1/S4 non è
  ricostruibile dal DB.
- **SNOW (+3,58%)**: posizione S1 aperta dal 2026-08-05, nessun nuovo ordine oggi.
- **MRVL (−5,57%)**: posizione S1 aperta dal 2026-07-14, nessun nuovo ordine oggi — il calo
  odierno è quasi uno specchio del +5,79% dell'08-20 sullo stesso titolo (vedi §5).
- **Chiusura del giorno, non legata ai mover ≥3%**: INTC (−2,24% sul giorno, sotto soglia),
  posizione S4 aperta il 2026-08-12, chiusa il 2026-08-21 16:37 per `sentiment_reversal`.
  qty residua 0,0349 (posizione sub-1-azione), net_pnl −$1,07, tenuta 214,75 ore (~9 giorni),
  drift post-uscita +0,13% (trascurabile).

## 5. Pattern osservato

Rotazione settoriale riconoscibile e in buona parte **speculare rispetto all'08-20**: oggi
**banche** (GS +3,73%, MS +3,25%, C +1,53%, AXP +1,46%, V +1,45% tutti positivi), **materiali**
(RIO +3,06%, VALE +2,53%) e **auto** (F +3,00%, TM +2,66%, GM +2,07%, e TSLA +5,14% nonostante un
recall negativo) sono il gruppo forte, mentre i **semiconduttori** sono il gruppo debole (MRVL
−5,57%, ARM −2,95%, INTC −2,24%, WDC −2,05%, AMAT/MU/NVDA tutti negativi). Il giorno precedente
(08-20) era l'esatto contrario: semiconduttori forti (MRVL +5,79%, MU +3,97%) e banche deboli (MS
−3,16% dentro un gruppo bancario tutto negativo). MRVL in particolare passa da +5,79% (08-20) a
−5,57% (08-21), quasi un mirror flip sullo stesso nome in due sedute consecutive. BABA −8,57% è
uno shock idiosincratico isolato (miss di utili Q2), non parte del pattern settoriale — nessun
altro nome e-commerce/cloud cinese è vicino a quel livello.

## 6. Confronto con giorni precedenti

A differenza delle continuazioni multi-day osservate 08-18→08-19 (stesso rout
semiconduttori/hardware per due sedute consecutive) o della rotazione a due gruppi stabile
dell'08-20, oggi il pattern è un **whipsaw a un giorno**: il gruppo vincente e quello perdente
dell'08-20 si scambiano di posto quasi simbolo per simbolo (banche e semiconduttori). Le cinque
posizioni legacy (GS, MS, RIO fra i mover di oggi) restano il canale principale con cui il book
assorbe questi swing settoriali senza nuovi ordini — stesso meccanismo già documentato su
GE/DELL/WDC (08-19) e GE (08-20), qui per la prima volta osservato sul lato guadagno anziché
perdita: contributo stimato +$92,49 delle 11 posizioni legacy su un NAV change di +$288,06 (32%,
F-002).

## 7. Segnalazioni

Nessun difetto nuovo isolato oggi. Le cinque occorrenze sotto sono ricorrenze di pattern già a
ledger, con dettaglio specifico della giornata.

[F-001] Copertura news bassa — 43/96 simboli (45%) zero righe in `news_log`, dentro la banda
storica 38-57%. Due dei cinque miss del giorno sono NO_NEWS puri (PLTR, F), costo congetturale
$141,68.

[F-002] Attribuzione strategia mancante su trade legacy — le 11 posizioni pre-patch
(BAC/GOOGL/GS/MS/PBR/RIO/ROKU/SPY/UBS/UNH/XLE) includono oggi tre mover del giorno (GS, MS, RIO):
nessuna riga porta `stop_strategy`, quindi non è ricostruibile quale sleeve li possieda.
Contributo stimato +$92,49 al NAV change del giorno, non attribuibile per costruzione (costo
null, non è una perdita).

[F-009] Il gate d'ingresso S4 scarta segnali col segno corretto sotto soglia — BABA, segnale
dedicato −0,315 corretto nel segno ma decaduto a −0,252 (sotto il gate 0,30) al primo ciclo di
valutazione. Costo $0,00 verificato (mover al ribasso, long-only, non detenuto — il gate è
comunque irrilevante qui).

[F-012] Metà delle righe scorate da fan-out multi-ticker — quota del giorno 55,6%. L'unico nuovo
ordine (HOOD) nasce però da un articolo dedicato, non da fan-out: costo $0,00 verificato sul
money path. Il caso ORCL illustra il lato costo del fenomeno (miss THIN_NEUTRAL causato da un
articolo fanout a 5 ticker che non cita il titolo).

[F-023] S4 usa solo il segnale più recente per simbolo — TSLA, overwrite nel più breve intervallo
finora osservato (2 secondi): un segnale dedicato −0,360 (recall) sovrascritto da un fanout
+0,0126 (SpaceX/Nvidia) non su TSLA. Costo $0,00 verificato: nessuno dei due segnali avrebbe
comunque superato il gate col segno giusto, quindi l'overwrite non ha cambiato l'esito — ma è
l'istanza più veloce del pattern osservata finora.

Nessuna delle cinque appare come un difetto nuovo di correttezza rispetto a quanto già registrato:
sono tutte ricorrenze. Il caso ORCL/FALSE_ENTITY_MATCH (§3) resta un'osservazione grezza, non
abbastanza materiale per una segnalazione — la decisione se approfondirlo resta all'operatore.
