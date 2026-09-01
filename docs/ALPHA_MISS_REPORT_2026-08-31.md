# Alpha Miss Report — 2026-08-31

Fonte numeri: `docs/evidence/dossier/2026-08-31.json` (schema 2.6, generato 2026-09-01T08:00:20Z,
Alpaca SIP adjustment=all). Query dirette a `alembic-postgres-1` solo per verifica incrociata
(trades, portfolio_cycles, news_log/sentiment_signals su PBR). Nessun numero è stato ricalcolato
dove il dossier lo forniva già.

## 1. Executive summary

- 5 mover ≥3% sulla watchlist (soglia coerente con `soglia_mover=0.03` del dossier): **3 up** (TSLA
  +5,51%, PBR +4,43%, QCOM +3,83%), **2 down** (RDDT -3,39%, BABA -4,10%).
- **1 catturato** (PBR, posizione S1 già detenuta dall'apertura — nessun nuovo trade, nessun segnale
  richiesto). **4 mancati**: TSLA, QCOM, BABA, RDDT.
- Causa prevalente dei miss: **THIN_NEUTRAL/BELOW_GATE** (3 su 4 — TSLA e QCOM sotto il gate 0,30
  con segno corretto, BABA a punteggio 0,0 nonostante 2 articoli). RDDT è l'unico NO_NEWS puro.
- 60/96 simboli (62,5%) a zero righe `news_log` oggi — massimo della serie osservata finora
  (precedenti: 41, 45, 51, 53, 54, 55).
- Cadenza `portfolio_cycles`: 24 cicli regolari, nessun gap >16 min.
- Cecità lato uscita: 5 posizioni S1 (`ASML, MMM, NOK, TXN, UNH`), 2 nuove rispetto al 08-28
  (NOK, TXN); nessuna con dato insufficiente (`null`).
- Nessun candidato FILTERED, WRONG_SIGN o OUT_OF_STRATEGY_SCOPE oggi.

## 2. Rendimenti — tabella completa (96 simboli watchlist)

Catturato = tradato oggi (ingresso/uscita) o già detenuto all'apertura.

| Simbolo | Return % | Catturato |
|---|---:|---|
| TSLA | +5.51% | no |
| PBR | +4.43% | **sì** (S1, detenuto) |
| QCOM | +3.83% | no |
| PANW | +2.84% | no |
| MU | +2.77% | no |
| XOM | +2.71% | no |
| NOW | +2.27% | no |
| CVX | +2.12% | no |
| XLE | +2.04% | **sì** (S4, nuovo ingresso) |
| PFE | +1.79% | no |
| WMT | +1.73% | no |
| BP | +1.71% | no |
| SPCX | +1.55% | no |
| UBS | +1.49% | no |
| NVDA | +1.48% | no |
| ERIC | +1.41% | no |
| ARM | +1.20% | no |
| AMD | +1.10% | no |
| TM | +1.06% | no |
| SNOW | +1.05% | no |
| PG | +0.93% | no |
| TXN | +0.88% | no (detenuto, cieco lato uscita — v. §5) |
| CRM | +0.60% | no |
| SHEL | +0.59% | no |
| HOOD | +0.53% | no |
| CSCO | +0.51% | no |
| SOXX | +0.48% | no |
| XLK | +0.44% | no |
| ADBE | +0.44% | no |
| F | +0.43% | no |
| AVGO | +0.42% | **sì** (S4, ingresso+uscita intraday) |
| VALE | +0.40% | no |
| ABBV | +0.37% | no |
| INFY | +0.08% | no |
| GM | +0.06% | no |
| PLTR | +0.05% | no |
| QQQ | +0.05% | no |
| INTC | +0.04% | no |
| ASML | -0.01% | no (detenuto, cieco lato uscita — v. §5) |
| DELL | -0.05% | no |
| VZ | -0.16% | no |
| COST | -0.17% | no |
| BRK.B | -0.19% | no |
| SAP | -0.29% | no |
| SPY | -0.30% | n/a (benchmark) |
| WFC | -0.35% | no |
| CAT | -0.35% | no |
| AZN | -0.35% | no |
| XLV | -0.36% | no |
| MRK | -0.40% | no |
| JPM | -0.45% | no |
| T | -0.46% | no |
| ROKU | -0.47% | no |
| DIS | -0.51% | no |
| TMUS | -0.51% | no |
| TSM | -0.53% | no |
| MCD | -0.55% | no |
| V | -0.58% | no |
| BAC | -0.61% | no |
| NVO | -0.61% | no |
| IWM | -0.62% | no |
| XLF | -0.67% | no |
| MS | -0.68% | no |
| NOK | -0.69% | no (detenuto, cieco lato uscita — v. §5) |
| AMAT | -0.71% | no |
| HD | -0.71% | no |
| IBM | -0.73% | no |
| DB | -0.74% | no |
| RIO | -0.77% | no |
| GS | -0.78% | no |
| JNJ | -0.82% | no |
| NFLX | -0.82% | no |
| AAPL | -0.89% | no |
| UNH | -0.90% | no (detenuto, cieco lato uscita — v. §5) |
| AXP | -0.91% | no |
| C | -0.96% | no |
| BA | -0.97% | no |
| META | -0.98% | no |
| MA | -1.01% | no |
| ORCL | -1.15% | no |
| SONY | -1.17% | no |
| MSFT | -1.22% | no |
| NKE | -1.35% | no |
| MMM | -1.44% | no (detenuto, cieco lato uscita — v. §5) |
| SBUX | -1.48% | no |
| LLY | -1.52% | no |
| CMCSA | -1.63% | no |
| JD | -1.74% | no |
| BIDU | -1.89% | no |
| WDC | -1.94% | no |
| GE | -2.01% | no |
| GOOGL | -2.09% | **sì** (S1, uscita `sentiment_reversal`) |
| MRVL | -2.29% | no |
| AMZN | -2.50% | no |
| RDDT | -3.39% | no |
| BABA | -4.10% | no |

## 3. Miss classificati (mover ≥3%, non catturati)

Soglia: |return| ≥ 3%, coerente con `soglia_mover=0.03` del dossier.

| Simbolo | Return % | Categoria | Evidenza |
|---|---:|---|---|
| TSLA | +5.51% | THIN_NEUTRAL (`causa` dossier: BELOW_GATE) | 5 articoli, punteggio massimo 0,281 (gate 0,30) — un solo punto sotto soglia. L'unico segnale issuer-specific ("Tesla Stock Surges Ahead of Cybercab Event", 18:00) è anche il più alto; 4/5 righe (80%) sono fan-out su pezzi che non parlano di TSLA. Segno corretto. |
| QCOM | +3.83% | THIN_NEUTRAL (`causa` dossier: BELOW_GATE) | 1 solo articolo nella giornata, punteggio 0,18 (gate 0,30), 100% fan-out (`quota_righe_fanout`=1,0, pezzo generico "Analysts Eye Data Center Growth"), nessun articolo issuer-specific disponibile. Segno corretto. |
| BABA | -4.10% | THIN_NEUTRAL | 2 articoli, punteggio massimo 0,0. Il pezzo issuer-specific (org_lookup) è un confronto societario ("Montague International versus Alibaba Group"), scorato neutro; l'altro è fan-out (4 ticker, irrilevante a BABA). Nessun segnale generato. |
| RDDT | -3.39% | NO_NEWS | 0 righe `news_log`, 0 `sentiment_signals` nella seduta. |

Nessun caso WRONG_SIGN, FILTERED o OUT_OF_STRATEGY_SCOPE oggi: nessuno dei quattro miss ha
raggiunto il gate d'ingresso 0,30, quindi non c'è stato nulla da scartare a valle
(ranking/breadth/hysteresis) — la causa si ferma al punteggio o all'assenza di dati, non a un
meccanismo successivo.

Nota book long-only: BABA e RDDT sono discesi. Anche con un punteggio/gate favorevole, S4 non
short — `opportunity_v2` del dossier calcola `accessible_opportunity_usd=0` per entrambi
(`missing_reason: long_only_no_short_downside_not_held`). Il costo lordo close-to-close riportato
in §Segnalazioni per RDDT è quindi un tetto teorico, non un'opportunità realmente accessibile con
questa costruzione del book.

## 4. Titoli catturati: esito

<!-- alpha-miss-book:start -->
<!-- alpha-miss-book-manifest: {"schema":1,"ingressi":["AVGO","XLE"],"chiusure":["AVGO","GOOGL"]} -->

Dati deterministici dal dossier; la prosa seguente li annota e non li sostituisce.

| Tipo | Simbolo | Strategia | Ora UTC | Prezzo | Quantità | P&L netto | Motivo / qualità |
|---|---|---|---|---:|---:|---:|---|
| IN | AVGO | S4 | 17:22 | $369.5100 | 3.7960 | — | percentile 49.77%; denominatore intraday degenere: quota non interpretabile |
| IN | XLE | S4 | 19:37 | $63.8600 | 22.0056 | — | percentile 55.38%; denominatore intraday degenere: quota non interpretabile |
| OUT | AVGO | S4 | — | $369.3795 | 3.7960 | −$1.27 | portfolio_sell |
| OUT | GOOGL | S1 | — | $338.6700 | 1.9222 | −$30.21 | sentiment_reversal |
<!-- alpha-miss-book:end -->

| Simbolo | Strategia | Movimento | Evento | Esito |
|---|---|---:|---|---|
| PBR | S1 | +4.43% | Detenuto dall'apertura (nessun trade oggi) | +$6.73 passive P&L intraday (mark-to-market, posizione ancora aperta a fine giornata). Zero righe `news_log` e zero `sentiment_signals` su PBR oggi: catturato per detenzione pregressa, non per segnale. |
| AVGO | S4 | +0.42% (titolo, non mover) | Ingresso 17:22 UTC, uscita 19:07 UTC (`portfolio_sell`) | -$1.27 net, tenuta 1h45. `entry_percentile` 0,50, `mtm_eod`/`vs_apertura` +3,15%/+3,11% — timing e size ordinari, nessuna anomalia. |
| XLE | S4 | +2.04% (titolo, non mover) | Ingresso 19:37 UTC | Ancora aperta a fine giornata, nessun P&L realizzato oggi. `entry_percentile` 0,55. |
| GOOGL | S1 | -2.09% (titolo, non mover) | Uscita 19:37 UTC, `sentiment_reversal` | -$30.21 net, tenuta 1253h (posizione aperta dal 2026-07-10). `drift_post_uscita` +1,31% — il titolo ha continuato a scendere poco dopo l'uscita, coerente col segno dell'uscita. |

Nessuno dei quattro trade di oggi riguarda un mover ≥3%: sono titoli sotto soglia, riportati per
completezza del quadro esecutivo del giorno.

## 5. Cecità lato uscita (posizioni detenute)

Da `copertura_uscita` del dossier (definizione: perdita ≥3% dall'ingresso, zero righe
news/sentiment nella seduta, streak ≥2 sedute consecutive a zero righe). 47 posizioni valutate,
**nessuna con `cieco_lato_uscita: null`** (dato sempre sufficiente oggi).

**5 posizioni con `cieco_lato_uscita: true`** (tutte S1):

| Ticker | ritorno_da_ingresso | sedute_consecutive_senza_righe | fonti_osservate_finestra |
|---|---:|---:|---|
| ASML | -4.11% | 7 | alpaca_benzinga |
| MMM | -4.62% | 9 | alpaca_benzinga |
| NOK | -13.48% | 2 | alpaca_benzinga, gdelt_gkg |
| TXN | -6.99% | 2 | alpaca_benzinga, gdelt_gkg |
| UNH | -8.94% | 3 | alpaca_benzinga |

ASML, MMM e UNH erano già ciechi lato uscita nel report del 08-28 (streak allora 6/8/2 sedute,
oggi 7/9/3 — la cecità è continuativa, non risolta nel mezzo). NOK e TXN sono nuovi in questa
lista: entrambi avevano streak sotto soglia (1 seduta) il 08-28. Nessuno dei cinque è fra i mover
di oggi (tutti sotto la soglia 3% in seduta — v. §2): la cecità è pregressa e cumulata su più
sedute, non un effetto della giornata odierna. `ritorno_da_ingresso` misura la perdita mentre la
posizione è detenuta (dall'ingresso al mark di chiusura odierno, nessuna delle cinque è uscita
intraday), non il movimento della sola seduta.

## 6. Pattern osservato

Non chiaro / assente sui top mover secondo il clustering del dossier
(`event_market_context.clusters`): TSLA (consumer/XLY), QCOM (semis/SOXX), RDDT (media/XLC), BABA
(tech/XLK) risultano ciascuno un cluster indipendente di 1 simbolo — nessuna correlazione settoriale
rilevata fra loro. TSLA e QCOM hanno catalizzatori idiosincratici/analyst-driven distinti
(Cybercab event; data-center growth outlook); BABA e RDDT non condividono un tema comune
riconoscibile nei dati raccolti. PBR (energy, +4.43%) non compare nel contesto eventi del dossier
(fuori dal set dei candidati miss, essendo detenuto) ma il suo settore (energy, coerente con
XOM +2.71%/CVX +2.12%/XLE +2.04%/SHEL +0.59%/BP +1.71% tutti positivi) suggerisce una gamba
energy-positiva del giorno, distinta e non collegata al gruppo dei quattro miss.

## 7. Confronto con i giorni precedenti

- **Cecità lato uscita in crescita**: da 3 posizioni (08-28: ASML, MMM, UNH) a 5 oggi (+NOK, +TXN).
  Le tre originarie non sono mai uscite nel frattempo — streak in aumento monotono (6→7, 8→9, 2→3).
  Solo due punti dati disponibili da quando il campo esiste nel dossier (deploy 2026-08-29): non
  chiamo ancora una tendenza, ma la direzione è coerente con "nessun meccanismo la risolve da solo".
- **Copertura news watchlist**: 60/96 (62,5%) è il massimo della serie osservata (prima: 41, 45,
  51, 53, 54, 55 nei report precedenti) — un solo punto, non una tendenza dichiarabile su una serie
  così rumorosa.
- **Gate d'ingresso S4 vicino-miss**: TSLA a 0,281 contro gate 0,30 è lo scarto più piccolo
  osservato finora nella serie F-009 (differenza 0,019); i casi precedenti (AVGO 0,230, INTC 0,228,
  AMZN 0,066) avevano margini più ampi. Un solo punto, coerente con la firma già nota (magnitudine
  sotto soglia, segno corretto) — non un pattern nuovo.

## 8. Nota di metodo

Nessuna delle cause classificate in §3 sembra un difetto piuttosto che un limite noto già in
osservazione: TSLA e QCOM ripetono la firma già registrata su F-009/F-012 (gate su magnitudine,
fonte fan-out unica), RDDT ripete F-001 (copertura news strutturalmente bassa), BABA è un caso di
segnale genuinamente neutro su un articolo di confronto societario. La decisione se e quando
intervenire resta dell'operatore.

---

## Segnalazioni

[F-009] Il gate d'ingresso S4 (0,30) scarta due mover forti col segno corretto: TSLA +5,51%
(punteggio massimo 0,281 — lo scarto più piccolo osservato finora nella serie, solo 0,019 sotto
soglia — su articolo issuer-specific "Tesla Stock Surges Ahead of Cybercab Event") e QCOM +3,83%
(punteggio 0,18 su unico articolo fan-out "Qualcomm Outperforms Broader Market Slump"). Nessuno dei
due detenuto. Costo lordo close-to-close x $2.200 (da `opportunity_v2.legacy.costo_usd` del
dossier): TSLA $121,12 + QCOM $84,28.

[F-012] QCOM ripete la firma "fan-out come unica fonte disponibile": l'unico articolo del giorno
(`quota_righe_fanout`=1,0) non è issuer-specific, nessuna alternativa nella finestra osservata.
Stesso caso di AMZN il 08-28. Costo non stimabile separatamente da F-009 (stesso trade).

[F-001] 60/96 simboli watchlist (62,5%) a zero righe `news_log` oggi — massimo della serie
osservata (41 il 13/08, 45 il 26/08, 51 il 24/08, 53 il 27/08, 54 il 28/08, 55 il 25/08). Un solo
candidato miss NO_NEWS puro oggi: RDDT -3,39%, zero righe news e zero sentiment_signals. Costo
lordo close-to-close x $2.200: $74,63 — registrato per confrontabilità con la serie, ma il titolo è
sceso e il book è long-only: `opportunity_v2` calcola `accessible_opportunity_usd=0,0`
(`missing_reason: long_only_no_short_downside_not_held`), quindi il costo realmente accessibile è
$0.

---

*Report generato in sessione autonoma di analisi giornaliera. Nessuna modifica a codice, nessun
ordine, nessun commit. Read-only.*
