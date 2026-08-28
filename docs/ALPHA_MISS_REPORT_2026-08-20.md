# Alpha Miss Report — 2026-08-20

Fonte numeri: `docs/evidence/dossier/2026-08-20.json` (schema 2.0, Alpaca SIP adjustment=all, generato 2026-08-21T08:00 UTC). Query dirette a `alembic-postgres-1` per Fase 2 (trades, portfolio_cycles, sentiment_signals, news_log, testo articoli) e per determinare quali simboli erano già in portafoglio. Nessun numero di rendimento è stato ricalcolato in autonomia; `equity` EOD, `mtm` e le stime di contributo NAV dei singoli simboli sono derivati da `portfolio_monitor_snapshots` più barre giornaliere Alpaca (non presenti nel dossier).

## 1. Executive summary

9 dei 96 simboli in watchlist si sono mossi ≥3% (soglia motivata: è `soglia_mover=0.03` già usata dal dossier, coerente con tutta la serie precedente). Di questi, **5 erano "catturati"**: WMT tradato oggi da S4 (entrata e uscita nella stessa sessione), MRVL/MU/MS/GE già in portafoglio da settimane (S1/legacy) senza nuovo ordine. **4 sono miss**: BP (NO_NEWS, unico con controfattuale reale, costo stimato $70,94), BA (NO_NEWS, ma mover al ribasso su libro long-only → costo $0 verificato), F (unico segnale generato da un articolo generico multi-ticker, segno opposto al movimento → WRONG_SIGN, costo $0 perché ribasso+long-only), SPCX (news pertinenti ma segnale sotto il gate 0,30 → THIN_NEUTRAL, costo $0 perché ribasso+long-only). Causa dominante nominale: NO_NEWS (2/4), ma **3 dei 4 miss sono al ribasso e quindi non tradabili per costruzione (long-only)**: il costo congetturale reale della giornata è quasi interamente $70,94 su BP. Copertura news: 41/96 simboli (43%) a zero articoli, dentro la banda 38-57% osservata da fine luglio. Nessun difetto nuovo isolato oggi: le tre segnalazioni sono ricorrenze di pattern già a ledger (F-001, F-002, F-020). Giornata negativa per il book: NAV 110.099,44 → 109.853,92 ($−245,52), realizzato $−78,57 (4 round-trip S4 nella stessa seduta), MTM sul book aperto stimato $−166,95.

## 2. Rendimenti completi (96 simboli)

| Simbolo | Return % | Catturato |
|---|---|---|
| MRVL | +5.79% | SI |
| MU | +3.97% | SI |
| BP | +3.22% | NO |
| PBR | +2.54% | SI |
| VALE | +2.37% | SI |
| NOW | +2.00% | SI |
| TM | +1.83% | NO |
| RIO | +1.72% | SI |
| WDC | +1.51% | SI |
| GM | +1.40% | SI |
| BABA | +1.26% | NO |
| TSM | +0.95% | SI |
| SHEL | +0.95% | SI |
| XOM | +0.84% | SI |
| SAP | +0.69% | NO |
| AMD | +0.65% | SI |
| MCD | +0.63% | NO |
| ARM | +0.55% | SI |
| SOXX | +0.52% | SI |
| AVGO | +0.43% | SI |
| SONY | +0.38% | NO |
| DIS | +0.36% | NO |
| XLE | +0.27% | SI |
| JD | +0.24% | NO |
| ROKU | +0.20% | SI |
| NOK | +0.20% | SI |
| UBS | +0.13% | SI |
| T | +0.12% | NO |
| AMAT | +0.12% | SI |
| V | +0.05% | NO |
| MA | +0.02% | NO |
| CVX | +0.00% | SI |
| META | −0.04% | NO |
| ASML | −0.08% | SI |
| ADBE | −0.09% | NO |
| CAT | −0.09% | SI |
| NFLX | −0.10% | SI |
| AZN | −0.28% | NO |
| XLK | −0.29% | SI |
| CRM | −0.32% | NO |
| NVDA | −0.33% | SI |
| VZ | −0.34% | NO |
| ERIC | −0.39% | NO |
| MSFT | −0.47% | NO |
| BRK.B | −0.55% | NO |
| TMUS | −0.62% | NO |
| DELL | −0.63% | SI |
| CMCSA | −0.64% | NO |
| TXN | −0.69% | SI |
| HOOD | −0.70% | NO |
| PLTR | −0.70% | NO |
| QQQ | −0.72% | SI |
| INTC | −0.72% | SI |
| QCOM | −0.72% | NO |
| NVO | −0.73% | NO |
| SPY | −0.84% | SI |
| CSCO | −0.87% | NO |
| XLF | −0.92% | SI |
| RDDT | −0.92% | NO |
| SBUX | −0.94% | SI |
| UNH | −0.97% | SI |
| BIDU | −0.97% | NO |
| PG | −0.98% | NO |
| SNOW | −1.14% | SI |
| GOOGL | −1.17% | SI |
| ORCL | −1.21% | NO |
| DB | −1.24% | NO |
| IWM | −1.34% | SI |
| MMM | −1.42% | SI |
| IBM | −1.46% | NO |
| ABBV | −1.56% | SI |
| PFE | −1.59% | NO |
| JPM | −1.60% | SI |
| INFY | −1.66% | NO |
| TSLA | −1.71% | NO |
| AAPL | −1.75% | SI |
| XLV | −1.87% | SI |
| GS | −1.93% | SI |
| NKE | −2.05% | NO |
| BAC | −2.07% | SI |
| MRK | −2.11% | SI |
| AMZN | −2.16% | NO |
| JNJ | −2.21% | SI |
| C | −2.42% | SI |
| COST | −2.48% | NO |
| AXP | −2.57% | NO |
| WFC | −2.61% | NO |
| LLY | −2.81% | SI |
| HD | −2.85% | NO |
| PANW | −2.87% | SI |
| MS | −3.16% | SI |
| BA | −3.20% | NO |
| GE | −3.25% | SI |
| F | −3.52% | NO |
| SPCX | −4.05% | NO |
| WMT | −9.16% | SI |

"Catturato" = simbolo detenuto in posizione aperta a fine giornata **o** tradato (entrata/uscita) nella sessione — non solo i mover ≥3%.

## 3. Miss classificati

| Simbolo | Return % | Categoria | Evidenza |
|---|---|---|---|
| BP | +3.22% | **NO_NEWS** | 0 righe in `news_log`, 0 in `sentiment_signals` il 2026-08-20. Catena decisionale inesistente. Controfattuale reale (mover al rialzo): `opportunity_v2.gross_opportunity_usd` = $70,94 (size S4 tipica $2.200 su un rialzo del 3,22%). `accessible_opportunity_usd` non calcolabile — bloccato da #277 (nessuna barra intraday al ciclo eleggibile). |
| BA | −3.20% | **NO_NEWS** | 0 righe in `news_log`, 0 in `sentiment_signals`. Mover al ribasso su libro **long-only, non detenuto**: nessuna size avrebbe potuto catturarlo. Costo $0 verificato, non stimato per assenza di lavoro. |
| F | −3.52% | **WRONG_SIGN** | Un solo articolo del giorno, generico multi-ticker: *"Trump Could Reportedly Cut Canadian Auto Tariffs to 15%, Aluminum and Steel to 25%: NUE, STLD, CENX in Focus"* (13:08 UTC) — F citato solo incidentalmente, non è il soggetto del pezzo. Score risultante alle 14:30: **+0,1479** (rialzista), ma il titolo ha chiuso **−3,52%**: segno opposto al movimento reale. Anche sotto il gate 0,30 di design. Mover al ribasso su libro long-only, non detenuto → costo $0. |
| SPCX | −4.05% | **THIN_NEUTRAL** | 4 articoli SPCX-specifici e pertinenti (share unlock da 319M azioni, scadenza lockup, Starship reuse) — copertura reale, non un buco. Segnali per lo più correttamente orientati al ribasso (−0,140 alle 14:00 fallback, +0,076 alle 15:45, **−0,226** alle 16:45 ensemble reale, −0,0825 alle 19:45 fallback) ma **mai sopra il gate 0,30**. Mover al ribasso su libro long-only, non detenuto → costo $0. |

Conteggi del giorno: NO_NEWS=2, THIN_NEUTRAL=1, WRONG_SIGN=1, FILTERED=0, OUT_OF_STRATEGY_SCOPE=0. Nessun candidato ha superato il gate con segno corretto e size adeguata: **il gate/BELOW_GATE non è mai la causa isolata** oggi — su 3 dei 4 miss la causa che pesa davvero è il vincolo long-only su un mover ribassista, coerente con [F-040].

## 4. Titoli catturati: esito

<!-- alpha-miss-book:start -->
<!-- alpha-miss-book-manifest: {"schema":1,"ingressi":["NVDA","WMT","NOW","AVGO"],"chiusure":["HOOD","NVDA","WMT","NOW"]} -->

Dati deterministici dal dossier; la prosa seguente li annota e non li sostituisce.

| Tipo | Simbolo | Strategia | Ora UTC | Prezzo | Quantità | P&L netto | Motivo / qualità |
|---|---|---|---|---:|---:|---:|---|
| IN | NVDA | S4 | 15:22 | $217.2388 | 8.5960 | — | percentile 37.59%; denominatore intraday valido |
| IN | WMT | S4 | 16:37 | $103.7900 | 17.9510 | — | percentile 28.74%; denominatore intraday valido |
| IN | NOW | S4 | 16:52 | $130.8000 | 14.2791 | — | percentile 91.36%; denominatore intraday valido |
| IN | AVGO | S4 | 17:07 | $363.1300 | 5.1360 | — | percentile 18.07%; denominatore intraday degenere: quota non interpretabile |
| OUT | HOOD | S4 | — | $95.2800 | 18.6485 | −$60.32 | portfolio_sell |
| OUT | NVDA | S4 | — | $217.1630 | 8.5960 | −$1.03 | portfolio_sell |
| OUT | WMT | S4 | — | $103.9800 | 17.9510 | +$2.38 | sentiment_reversal |
| OUT | NOW | S4 | — | $129.5000 | 14.2791 | −$19.60 | portfolio_sell |
<!-- alpha-miss-book:end -->

**Annotazione narrativa — WMT:**
- **WMT** (S4) — entrata 16:37 UTC @ $103,79 (score +0,318, sopra gate, subito dopo una serie di notizie negative sugli utili Q2: *"Walmart's US Sales Growth Hits Weakest Pace Since 2020"*, *"Crude Oil Gains 3%; Walmart Shares Drop After Q2 Results"*, *"Walmart Craters 9%"* — tutte pubblicate prima delle 17:03). Segnale ribaltato a **−0,704** alle 17:30 → uscita `sentiment_reversal` alle 17:37 @ $103,98, `net_pnl` **+$2,38**, tenuta ~1h. `drift_post_uscita` = **−7,00%**: il titolo ha continuato a scendere dopo l'uscita, quindi la strategia ha evitato la parte più ampia del tracollo pur essendo entrata in una giornata fortemente negativa — esito piccolo ma non peggiorativo, nonostante l'ingresso sia arrivato su un rimbalzo temporaneo dentro un crollo del −9,16% guidato da utili.

**Già in portafoglio (nessun nuovo ordine oggi):**
- **MRVL** (+5,79%, miglior mover del giorno) — posizione S1 aperta il 2026-07-14. Segnale del pomeriggio **+0,585** alle 17:45 (ensemble reale, ampiamente sopra gate) non ha prodotto alcun rabbocco: la posizione è già detenuta, e l'ingresso incrementale è bloccato dal guard anti-pyramiding [F-031].
- **MU** (+3,97%) — posizione S1 dal 2026-07-28. Segnali deboli/misti nella giornata (max +0,164 alle 15:15), nessuna azione.
- **MS** (−3,16%) — posizione legacy senza `stop_strategy` dal 2026-07-10 (set noto, vedi [F-002]). 19 righe in `news_log`, ma **tutte e 19** con `extraction_method='org_lookup'` e nessuna riguarda davvero Morgan Stanley (titoli campione: *Honeywell Aerospace*, *Aegon*, *Cencora*, *RTX Corporation*, *Birkenstock*) — recidiva esatta del pattern [F-020]. Sentiment quasi tutto a zero, un solo segnale debole +0,143 alle 17:30. Contributo stimato al MTM del giorno: **−$20,70** (qty 3,053 × Δclose −$6,78).
- **GE** (−3,25%) — posizione S1 dal 2026-07-22. **Zero righe in `news_log`, zero `sentiment_signals`** il 2026-08-20: copertura nulla anche sul lato uscita, stesso simbolo già segnalato come aggravante in [F-001] il 2026-08-19 (allora insieme a DELL e WDC).

## 5. Pattern osservato

Rotazione settoriale riconoscibile: **semiconduttori in controtendenza positiva** (MRVL +5,79%, MU +3,97%, e nel resto della classifica TSM +0,95%, AVGO +0,43%, AMD +0,65%, SOXX +0,52% tutti positivi) mentre l'**indice ampio è debole** (SPY −0,84%, QQQ −0,72%) e il **comparto bancario cede in blocco** (MS −3,16% dentro un gruppo con JPM −1,60%, BAC −2,07%, GS −1,93%, WFC −2,61%, C −2,42%, AXP −2,57% tutti negativi). **WMT −9,16% è un evento idiosincratico isolato** guidato da utili Q2 deboli, non un movimento di settore: nessun altro nome retail è vicino a quel livello (COST −2,48%, HD −2,85%). BA (−3,20%) e F (−3,52%) non formano un pattern di settore riconoscibile oltre alla debolezza generale della giornata (GM, nello stesso comparto auto di F, è anzi +1,40%).

## 6. Confronto con giorni precedenti

Tre ricorrenze, nessun pattern nuovo:
- **[F-002]** — 14a sessione consecutiva con lo stesso insieme di 11 posizioni legacy senza `stop_strategy` (BAC, GOOGL, GS, MS, PBR, RIO, ROKU, SPY, UBS, UNH, XLE, tutte entrate il 2026-07-10). Oggi MS, uno di questi 11, è un mover (−3,16%) e la sua perdita non è attribuibile a nessuna sleeve.
- **[F-020]** — MS con 19/19 righe di news via `org_lookup`, tutte su società terze. Stesso meccanismo già visto su MS/GS/DB il 08-05, 08-06, 08-07 e 08-19.
- **[F-001]** (variante) — GE ricompare con copertura zero mentre è un mover al ribasso detenuto, stesso profilo di DELL/WDC il 08-19: l'assenza di notizia impedisce anche il segnale d'uscita, non solo l'ingresso.

## 7. Note sulle cause

Nessuna delle quattro cause di miss di oggi sembra un difetto non ancora noto: BP/BA sono buchi di copertura ordinari (F-001), F è un caso di fan-out da articolo generico multi-ticker (meccanismo imparentato a [F-008] ma con effetto opposto — blocca un ingresso invece di forzare un'uscita, quindi non aggiunto come occorrenza a F-008), SPCX è un sotto-gate ordinario con segnale per il resto corretto. Nessuna proposta di fix: la decisione se aprire un'issue resta all'operatore.

---

*Segnalazioni agganciate al ledger: [F-001] (occorrenza 2026-08-20, costo $70,94), [F-002] (occorrenza 2026-08-20, costo null), [F-020] (occorrenza 2026-08-20, costo null).*
