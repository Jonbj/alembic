# Alpha-Miss Report — 2026-07-31

Analisi limitata ai 96 simboli di `config/trading.yaml -> symbols.watchlist`. Domanda: quali titoli
del nostro universo sono saliti/scesi di più il 2026-07-31, quali Alembic ha intercettato, quali no e
perché. Periodo di sola osservazione (`docs/evidence/OBSERVATION_CHARTER.md`): nessuna proposta di
taratura o fix, solo evidenza.

## 1. Executive summary

- 11 mover con |return| ≥ 3% su 96 simboli (dispersione cross-sectional σ = 3.36%, molto sopra SPY
  +0.72% / QQQ +0.65%): giornata di forte dispersione, guidata da earnings big-tech (AMZN, AAPL,
  GOOGL, META, MSFT, BABA, BIDU tutti pubblicano/commentano risultati Q3 lo stesso giorno).
- 6 up (AMZN +15.3%, GOOGL +6.7%, BABA +5.1%, BIDU +3.4%, META +3.3%, MSFT +3.0%), 5 down (SPCX −3.4%,
  MU −5.9%, AAPL −7.4%, NVO −8.8%, RDDT −21.0%).
- **5/11 catturati** (AMZN, GOOGL, MSFT, MU, AAPL — 3 come posizioni già aperte prima del giorno, 2
  come nuovi ingressi S4 intraday), **6/11 mancati**.
- Causa prevalente dei miss: **FILTERED e THIN_NEUTRAL a pari merito (2 ciascuna)**, NO_NEWS 2/6.
  Nessun caso WRONG_SIGN, nessun caso OUT_OF_STRATEGY_SCOPE puro.
- Pattern: earnings-day dispersion **dentro lo stesso settore tech**, non rotazione tra settori — AAPL
  è l'anomalia (unico big-tech in calo, delusione utili) nello stesso paniere che ha premiato
  AMZN/GOOGL/META/MSFT/BABA/BIDU.
- Due segnalazioni strutturali agganciate al ledger: [F-001] copertura news watchlist, [F-002]
  attribuzione strategia NULL su trade pre-patch.

## 2. Rendimenti completi (96 simboli, close vs close precedente)

| Simbolo | Return% | Catturato |
|---|---:|:---:|
| AMZN | +15.32 | Sì |
| GOOGL | +6.73 | Sì |
| BABA | +5.10 | No |
| BIDU | +3.38 | No |
| META | +3.28 | No |
| MSFT | +3.02 | Sì |
| CVX | +2.35 | No |
| MRVL | +2.32 | No |
| BP | +2.26 | No |
| WDC | +2.21 | No |
| JD | +2.17 | No |
| SONY | +2.15 | No |
| CSCO | +2.14 | No |
| PANW | +1.89 | No |
| CRM | +1.83 | No |
| ORCL | +1.81 | Sì (posizione S4 pre-esistente, chiusa/riaperta nel giorno) |
| SHEL | +1.62 | No |
| VZ | +1.52 | No |
| SAP | +1.51 | No |
| PBR | +1.46 | No |
| GE | +1.42 | No |
| CMCSA | +1.23 | No |
| WFC | +1.19 | No |
| AMAT | +1.18 | No |
| NOW | +1.05 | No |
| ADBE | +1.01 | No |
| XLE | +1.00 | No |
| IBM | +0.86 | No |
| MCD | +0.82 | No |
| TSLA | +0.76 | No |
| SPY | +0.72 | benchmark |
| CAT | +0.70 | No |
| INFY | +0.67 | Sì (posizione S4 pre-esistente, chiusa nel giorno) |
| PLTR | +0.65 | No |
| QQQ | +0.65 | benchmark / Sì (posizione S1) |
| NOK | +0.55 | No |
| GM | +0.52 | No |
| VALE | +0.47 | No |
| ERIC | +0.41 | No |
| PFE | +0.40 | No |
| AVGO | +0.37 | No |
| PG | +0.37 | No |
| BRK.B | +0.36 | No |
| BAC | +0.36 | No |
| MRK | +0.32 | No |
| JPM | +0.27 | No |
| TSM | +0.23 | No |
| JNJ | +0.21 | No |
| T | +0.17 | No |
| MS | +0.17 | No |
| DELL | +0.14 | No |
| MMM | +0.12 | No |
| C | +0.10 | No |
| WMT | +0.09 | No |
| SOXX | +0.07 | No |
| DIS | +0.03 | No |
| V | −0.04 | No |
| HOOD | −0.05 | Sì (posizione S4 pre-esistente, chiusa nel giorno) |
| ROKU | −0.06 | No |
| XLF | −0.11 | No |
| XLK | −0.22 | No |
| COST | −0.24 | No |
| RIO | −0.34 | No |
| TMUS | −0.36 | No |
| AXP | −0.38 | No |
| HD | −0.42 | No |
| IWM | −0.48 | No |
| LLY | −0.53 | No |
| SBUX | −0.57 | Sì (posizione S1, gestita nel giorno) |
| XLV | −0.59 | No |
| GS | −0.63 | No |
| MA | −0.74 | Sì (nuovo ingresso S4 fine giornata) |
| ARM | −0.77 | Sì (posizione S4 pre-esistente, chiusa nel giorno) |
| DB | −0.89 | No |
| XOM | −0.97 | No |
| AZN | −0.99 | No |
| INTC | −1.02 | No |
| TXN | −1.08 | No |
| F | −1.21 | No |
| UBS | −1.22 | No |
| TM | −1.28 | No |
| ASML | −1.36 | No |
| NKE | −1.37 | No |
| SNOW | −1.62 | No |
| UNH | −1.68 | No |
| AMD | −1.90 | No |
| NFLX | −2.00 | No |
| BA | −2.15 | No |
| ABBV | −2.51 | Sì (posizione, chiusa nel giorno) |
| QCOM | −2.63 | No |
| SPCX | −3.41 | No |
| MU | −5.90 | Sì (posizione S1 pre-esistente) |
| AAPL | −7.35 | Sì (posizione S1 pre-esistente) |
| NVO | −8.78 | No |
| RDDT | −20.99 | No |

Nota: la colonna "Catturato" per i simboli sotto la soglia ±3% indica trade/posizioni effettivamente
presenti in `trades` quel giorno, riportati per completezza operativa — la classificazione formale dei
miss (sezione 3) è limitata ai soli 11 mover ≥3%.

Soglia ±3% scelta perché è circa una deviazione standard della dispersione cross-sectional del giorno
(σ = 3.36%) — sopra quella soglia un movimento è "il giorno" del titolo, non rumore.

## 3. Tabella dei miss classificati (11 mover ≥3%)

| Simbolo | Return% | Categoria | Evidenza |
|---|---:|---|---|
| BIDU | +3.38 | NO_NEWS | Zero righe in `news_log` e zero righe in `sentiment_signals` per BIDU il 2026-07-31. |
| RDDT | −20.99 | NO_NEWS | Zero righe in `news_log` e zero righe in `sentiment_signals` per RDDT il 2026-07-31, nonostante sia il mover più estremo della giornata. |
| BABA | +5.10 | FILTERED | Unico segnale del giorno (18:01 UTC, score +0.30, confidence 0.55) è `fallback_used=true` (single-model, `single:glm-5.2:cloud`). Il guardrail #108 (`_filter_fallback_signals`, `src/workers/portfolio_scheduler.py:759`) esclude i segnali fallback dal path BUY/ranking prima ancora della soglia — zero righe in `execution_decisions` per BABA quel giorno, coerente con l'esclusione a monte. Guard esistente e intenzionale (precedente SPCX −20.23 del 2026-07-01), non un bug. |
| SPCX | −3.41 | FILTERED | Entrambi i segnali del giorno (16:15 score −0.16, 16:30 score 0.0) sono `fallback_used=true` (single:gpt-oss). Stesso guardrail #108 — zero righe in `execution_decisions`. |
| META | +3.28 | THIN_NEUTRAL | 4 articoli in news_log, ma segnale ensemble oscillante intorno allo zero tutto il giorno (−0.01, −0.04, +0.04, 0.0) — mai sopra la soglia feedback attiva (0.30-0.35), coerente con 5 righe `SKIP_THRESHOLD` in `execution_decisions`. |
| NVO | −8.78 | THIN_NEUTRAL | 3 segnali ensemble non-fallback, coerentemente negativi (−0.168, −0.220, −0.395) ma sempre sotto soglia (0.168<0.35, 0.220<0.35) — 4 righe `SKIP_THRESHOLD`. Segno corretto (ribassista), ma magnitudine insufficiente per un ingresso; essendo strategia long-only e senza posizione NVO pre-esistente, un segnale negativo comunque non genera un ordine. |

## 4. Titoli catturati: esito

- **AMZN +15.32%** — S4, ingresso 14:22 UTC @267.25 (già dopo il gap overnight: prev close 235.50 →
  apertura ~267, +13.5% del movimento è gap, non catturabile intraday), uscita 18:37 UTC @270.71,
  **net_pnl +$15.53** (`portfolio_sell`). Riaperto 19:37 UTC @271.85 (posizione ancora aperta a fine
  giornata). Cattura corretta del +1.6% intraday residuo dopo il gap; il grosso del movimento (gap
  overnight su earnings AWS) era strutturalmente non intercettabile da una strategia intraday priva
  di posizione pre-esistente.
- **GOOGL +6.73%** — nessun nuovo trade; posizione aperta dal 2026-07-10 (`stop_strategy` NULL, vedi
  [F-002]) ha beneficiato del rally, **MTM giornaliero stimato +$43.19** ((356.13−333.66)×1.922
  azioni). Il segnale S4 del giorno era comunque debole (THIN_NEUTRAL, max score 0.17) e non avrebbe
  generato un nuovo ingresso.
- **MSFT +3.02%** — S4, ingresso tardivo 19:22 UTC @463.39 (segnale score +0.5425 generato 19:15),
  vicinissimo alla chiusura (464.72). Timing subottimale: cattura solo l'ultimo $1.33 su $13.62 di
  movimento giornaliero (~10%). Posizione ancora aperta a fine giornata, nessun P&L realizzato.
- **MU −5.90%** — nessun nuovo trade; posizione S1 aperta dal 2026-07-28 @827.12, **MTM giornaliero
  stimato −$20.55**. Nessuno stop scattato: il protective stop è disabilitato da config
  (`stop_loss: 0.0`, decisione operativa 2026-07-15 già nota, non una scoperta di oggi).
- **AAPL −7.35%** — nessun nuovo trade; posizione S1 aperta dal 2026-07-14 @315.25, **MTM giornaliero
  stimato −$60.27**. Stesso motivo: protective stop disabilitato da config. News del giorno spiega il
  movimento (delusione utili Q3, "100-Year Flood" nei costi memoria — vedi sezione 5).

Altri trade chiusi/aperti il 2026-07-31 sotto soglia ±3% (per completezza contabile, non nella
classificazione miss): ORCL (due trade, net_pnl −$5.67 e +$2.16), HOOD (net_pnl −$43.97), INFY
(net_pnl −$12.68), ARM (net_pnl +$45.28), SBUX (due trade, net_pnl −$8.28 e −$4.11), QQQ (net_pnl
+$1.22), ABBV (net_pnl +$16.90, attribuzione strategia NULL — vedi [F-002]), MA (nuovo ingresso S4
fine giornata, ancora aperto).

**Realizzato giornata (tutti i trade chiusi il 07-31, non solo i mover):** totale **+$6.37**; S4
+$0.64; S1 −$11.17; ABBV (+$16.90) non attribuibile con certezza a una strategia ([F-002]).

## 5. Pattern osservato

**Earnings-day dispersion dentro il settore tech, non rotazione tra settori.** Tutti e 6 gli up-mover
(AMZN, GOOGL, BABA, BIDU, META, MSFT) appartengono al gruppo "tech" della sector map di
`trading.yaml`. I titoli scesi sono eterogenei per settore (SPCX etf_broad, MU semis, AAPL tech, NVO
healthcare, RDDT media) — **tranne AAPL, che è nello stesso paniere tech dei vincitori ma va in
direzione opposta**. Gli headline del giorno confermano la lettura earnings: "Amazon Jumps 15%, Apple
Wipes Out $475 Billion" (17:42 UTC), "Amazon Helps, Apple Disappoints" (18:12 UTC), "Apple Blames
100-Year Flood in Memory Prices" (13:38 UTC), "Amazon Says AWS Could Become A $1 Trillion Business"
(14:25 UTC). Non è una rotazione settoriale — è dispersione idiosincratica da earnings dentro lo
stesso settore, con AAPL come outlier negativo isolato nello stesso paniere premiato per gli altri
nomi. MU, NVO, RDDT, SPCX non condividono un tema comune riconoscibile con i big-tech: per questi
"pattern non chiaro" oltre all'osservazione settoriale sopra.

## 6. Confronto con giorni precedenti

Nessun `docs/ALPHA_MISS_REPORT_*.md` precedente trovato nella directory `docs/` — questo è il primo
report di questa serie. Nessun confronto storico possibile; non si specula oltre la singola giornata.

## 7. Segnalazioni per il ledger

[F-001] Probabile limite strutturale, non un difetto — copertura news watchlist bassa: **55 simboli su
96 (57%)** hanno zero righe in `news_log` il 2026-07-31. Tra gli 11 mover ≥3% del giorno, questo ha
causato direttamente il miss di BIDU (+3.38%) e RDDT (−20.99%, il movimento più estremo della
giornata). Coerente con l'esempio in `OBSERVATION_CHARTER.md` ("39 simboli su 96..."); qui la
proporzione è più alta. Nessuna proposta di fix — solo evidenza per la domanda di uscita 1 della carta
("esiste alpha nella news editoriale su questa watchlist?").

[F-002] Possibile difetto di correttezza contabile (non di trading) — attribuzione strategia mancante
su trade legacy: le posizioni GOOGL (aperta 2026-07-10, tuttora aperta) e ABBV (aperta 2026-07-10,
chiusa il 2026-07-31 con net_pnl +$16.90) hanno `trades.stop_strategy` NULL, presumibilmente perché
antecedenti alla patch che valorizza questo campo (i trade da 07-14 in poi osservati oggi — MU, AAPL —
lo hanno correttamente popolato con "S1"). Effetto concreto oggi: il realizzato per strategia
(S1 −$11.17, S4 +$0.64) non include i +$16.90 di ABBV, e se GOOGL (posizione tuttora aperta, oggi
+$43.19 di MTM) chiude durante il periodo di osservazione, il suo P&L sarà anch'esso non attribuibile
a S1 o S4 — un problema diretto per la domanda di uscita 2 della carta ("S1 ha un edge..."), che
richiede lo split per strategia. Segnalato per visibilità, nessun fix proposto (fuori scope di questa
sessione read-only).

## Nota metodologica

- `AAPL`/`GOOGL` inferiti come probabile S1 legacy sulla base dell'assenza di `signal_id` (S4 lega
  sempre un `sentiment_signals.id`) e di uno `score` di ingresso (0.0138) coerente con un peso
  momentum, non un punteggio di sentiment — inferenza, non certezza, vedi [F-002].
- `book.mtm` in `market_daily.jsonl` è una stima: P&L giornaliero totale da Alpaca (`profit_loss`
  della portfolio history, +$262.25) meno il realizzato da trade chiusi (+$6.37) = **+$255.88**,
  riferito all'intero book (non solo ai simboli mover).
