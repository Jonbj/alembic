# Alpha Miss Report — 2026-08-24

Fonte numerica primaria: `docs/evidence/dossier/2026-08-24.json` (deterministico, Alpaca SIP
`adjustment=all`). Query dirette via `docker exec alembic-postgres-1 psql` per `trades`,
`portfolio_cycles`, `sentiment_signals`, `execution_decisions`, `news_log`. Equity e MTM del book
da Alpaca Trading API. Nessun ricalcolo dei numeri già presenti nel dossier.

## 1. Executive summary

12 dei 96 simboli watchlist si sono mossi ≥3% (soglia `soglia_mover=0.03` del dossier, coerente con
la serie), ma solo **3 al rialzo** (MA +3.31%, VALE +3.08%, V +3.06%) contro **9 al ribasso**, con
dispersione σ=1.83% su un mercato piatto-debole (SPY −0.29%, QQQ −1.00%). **7 mover erano a libro**
(MU, WDC, AMD, MRVL, SNOW, VALE via S1/legacy; HOOD via S4, uscito alle 17:22): per sei di essi
"catturato" significa che il book ha incassato il ribasso, non che l'alpha sia stato colto. **5 sono
miss**, tutti fra i non detenuti: MA e V (THIN_NEUTRAL — segnale del segno giusto ma a +0.054 e
+0.025 contro un gate 0.30), TSLA (THIN_NEUTRAL — l'unico segnale issuer-specific vale +0.008),
F e INTC (OUT_OF_STRATEGY_SCOPE — segnale ribassista corretto, rispettivamente −0.310 e −0.318, ma
book long-only e titoli non detenuti: nulla su cui agire). **Zero NO_NEWS fra i miss**, per la prima
volta nella serie recente. Costo congetturale dei due miss azionabili (MA, V): $140.28 lordi, $29.97
sull'orizzonte realmente accessibile. Il fatto più netto della giornata non è un miss ma un fatto di
segno: **tutti e 9 i segnali generati sopra il gate 0.30 sono rialzisti, e i loro titoli chiudono in
media −2.0%** (MU +0.539 → −5.83%, MRVL +0.368 → −3.27%, SOXX +0.360 → −2.67%). 24 cicli portfolio,
nessun gap oltre i 16 minuti, primo ciclo alle 14:07 UTC (37 minuti dopo l'apertura). Book: NAV
109.861,38 (−269,00 sulla giornata), realizzato −53,91 (tutto S4), MTM del book aperto −282,77.

## 2. Tabella rendimenti completa (96 simboli)

Fonte: dossier, Alpaca SIP `adjustment=all`, close vs close precedente. Nessun simbolo senza barre
(`simboli_senza_dati: []`).

| Simbolo | Return % | Catturato |
|---|---:|---|
| MA | +3.31% | No — miss (THIN_NEUTRAL) |
| VALE | +3.08% | **Sì** — a libro (S1/legacy) |
| V | +3.06% | No — miss (THIN_NEUTRAL) |
| WMT | +2.69% | — sotto soglia |
| DIS | +2.63% | — sotto soglia |
| COST | +2.50% | — sotto soglia |
| UNH | +2.22% | — a libro, sotto soglia |
| BRK.B | +1.71% | — sotto soglia |
| META | +1.66% | — sotto soglia |
| DB | +1.59% | — sotto soglia |
| T | +1.58% | — sotto soglia |
| SONY | +1.42% | — sotto soglia |
| VZ | +1.42% | — sotto soglia |
| JPM | +1.37% | — a libro, sotto soglia |
| AMZN | +1.33% | — sotto soglia |
| PG | +1.33% | — sotto soglia |
| XLF | +1.29% | — a libro, sotto soglia |
| WFC | +1.05% | — sotto soglia |
| JNJ | +1.04% | — a libro, sotto soglia |
| BAC | +1.04% | — a libro, sotto soglia |
| GOOGL | +0.94% | — a libro, sotto soglia |
| MSFT | +0.84% | — sotto soglia |
| UBS | +0.79% | — a libro, sotto soglia |
| CMCSA | +0.63% | — sotto soglia |
| MCD | +0.59% | — sotto soglia |
| HD | +0.54% | — sotto soglia |
| NFLX | +0.53% | — tradato oggi, sotto soglia |
| MMM | +0.47% | — a libro, sotto soglia |
| AZN | +0.44% | — sotto soglia |
| ROKU | +0.44% | — a libro, sotto soglia |
| AXP | +0.40% | — sotto soglia |
| NVO | +0.39% | — sotto soglia |
| SBUX | +0.38% | — a libro, sotto soglia |
| ADBE | +0.35% | — sotto soglia |
| AAPL | +0.32% | — a libro, sotto soglia |
| C | +0.05% | — a libro, sotto soglia |
| XLV | +0.05% | — a libro, sotto soglia |
| SAP | -0.01% | — sotto soglia |
| NKE | -0.02% | — sotto soglia |
| CRM | -0.05% | — sotto soglia |
| MS | -0.06% | — a libro, sotto soglia |
| ABBV | -0.17% | — a libro, sotto soglia |
| TMUS | -0.23% | — sotto soglia |
| GS | -0.29% | — a libro, sotto soglia |
| SPY | -0.29% | — a libro, sotto soglia |
| NOW | -0.33% | — sotto soglia |
| SHEL | -0.35% | — a libro, sotto soglia |
| PFE | -0.36% | — sotto soglia |
| RDDT | -0.38% | — sotto soglia |
| RIO | -0.47% | — a libro, sotto soglia |
| JD | -0.58% | — sotto soglia |
| ERIC | -0.59% | — sotto soglia |
| XOM | -0.64% | — a libro, sotto soglia |
| IWM | -0.66% | — a libro, sotto soglia |
| LLY | -0.67% | — a libro, sotto soglia |
| BABA | -0.73% | — sotto soglia |
| CSCO | -0.73% | — sotto soglia |
| XLE | -0.83% | — a libro, sotto soglia |
| QQQ | -1.00% | — a libro, sotto soglia |
| INFY | -1.01% | — sotto soglia |
| CVX | -1.06% | — a libro, sotto soglia |
| GM | -1.08% | — a libro, sotto soglia |
| BIDU | -1.11% | — sotto soglia |
| MRK | -1.24% | — a libro, sotto soglia |
| ASML | -1.34% | — a libro, sotto soglia |
| QCOM | -1.38% | — sotto soglia |
| SPCX | -1.44% | — tradato oggi, sotto soglia |
| AMAT | -1.65% | — a libro, sotto soglia |
| BA | -1.75% | — sotto soglia |
| XLK | -1.78% | — a libro, sotto soglia |
| TM | -1.79% | — sotto soglia |
| ARM | -1.87% | — a libro, sotto soglia |
| GE | -1.87% | — a libro, sotto soglia |
| PANW | -1.95% | — a libro, sotto soglia |
| IBM | -1.97% | — sotto soglia |
| DELL | -2.01% | — a libro, sotto soglia |
| CAT | -2.04% | — a libro, sotto soglia |
| TXN | -2.05% | — a libro, sotto soglia |
| TSM | -2.11% | — a libro, sotto soglia |
| PLTR | -2.25% | — sotto soglia |
| BP | -2.28% | — sotto soglia |
| NOK | -2.45% | — a libro, sotto soglia |
| AVGO | -2.63% | — tradato oggi, sotto soglia |
| SOXX | -2.67% | — a libro, sotto soglia |
| ORCL | -2.74% | — sotto soglia |
| PBR | -2.89% | — a libro, sotto soglia |
| NVDA | -2.91% | — tradato oggi, sotto soglia |
| SNOW | -3.00% | **Sì** — a libro (S1/legacy) |
| INTC | -3.12% | No — miss (OUT_OF_STRATEGY_SCOPE) |
| MRVL | -3.27% | **Sì** — a libro (S1/legacy) |
| F | -3.33% | No — miss (OUT_OF_STRATEGY_SCOPE) |
| AMD | -3.49% | **Sì** — a libro (S1/legacy) |
| TSLA | -3.83% | No — miss (THIN_NEUTRAL) |
| HOOD | -4.17% | **Sì** — a libro, uscita il 24/08 |
| WDC | -5.24% | **Sì** — a libro (S1/legacy) |
| MU | -5.83% | **Sì** — a libro (S1/legacy) |

## 3. Miss classificati

Soglia: |return| ≥ 3%, la stessa `soglia_mover` del dossier e della serie storica — su una
dispersione cross-sectional di 1.83% corrisponde a ~1.6σ, cioè al di là della fluttuazione ordinaria
della watchlist. Sono classificati solo i mover **non detenuti**: i 7 già a libro sono in §4.

| Simbolo | Return % | Categoria | Evidenza |
|---|---:|---|---|
| MA | +3.31% | THIN_NEUTRAL | 2 articoli. Il primo (17:15, "CRCL Could Hit $140…", fanout a 2 ticker) esce a score 0.000 e viene comunque scartato come `SKIP_FALLBACK` (single `gpt-oss:20b-cloud`). Il secondo è issuer-specific e del segno giusto — "Why Is Mastercard Stock Surging on Monday?" — ma vale **+0.054**, contro un gate 0.30, ed è scorato alle **19:15**, 45 minuti prima della chiusura. `SKIP_THRESHOLD` ai cicli 19:22/19:37/19:52. |
| VALE | +3.08% | *(non un miss)* | Zero articoli in `news_log`, zero segnali: sarebbe NO_NEWS puro, ma il titolo è a libro da S1 dal 2026-07-14 e il rialzo è stato incassato. Conta in §5 e in F-001, non fra i miss. |
| V | +3.06% | THIN_NEUTRAL | 3 articoli, **nessuno** issuer-specific secondo il dossier (`effective_timely_articles: 0`, `quota_effective_timely: 0.0`). Score massimo +0.025 ("Visa Stock Climbs After Trump Buys Millions in Stock", 19:15, fallback single-model); gli altri due sono fanout sul pezzo Mastercard/Circle. Il dossier classifica la causa `OFF_TOPIC_NON_DECIDIBILE`. Tutti i segnali arrivano alle 17:15–19:15, a movimento in gran parte compiuto. |
| INTC | −3.12% | OUT_OF_STRATEGY_SCOPE | 5 articoli. Il segnale issuer-specific delle 19:00 — "Why Is Intel Stock Falling on Monday?" — vale **−0.318**, cioè del segno corretto e sopra il gate in modulo. Non è un errore del modello: è il vincolo di libro. Il dossier lo certifica: `missing_reason: long_only_no_short_downside_not_held`, `accessible_opportunity_usd: 0.0`. Nessuna azione era possibile. |
| F | −3.33% | OUT_OF_STRATEGY_SCOPE | 3 articoli, **3 su 3 fanout** (`quota_righe_fanout: 1.0`, `max_score_own: null`): l'intero segnale del titolo nasce dai pezzi sul dazio Canada 50% ("Trump Threatens 50% Canada Auto Tariff: Steelmakers Rally While Detroit Stocks Fall", −0.310). Segno corretto, ma stesso vincolo di INTC: long-only, non detenuto, `accessible_opportunity_usd: 0.0`. |
| TSLA | −3.83% | THIN_NEUTRAL | 4 articoli, 3 su 4 fanout. L'unico issuer-specific è "If You Invested $1000 In Tesla Stock 10 Years Ago…" (16:15), che vale **+0.008** — cioè il pezzo che parla davvero di Tesla è un filler retrospettivo senza contenuto direzionale. Il segnale più informativo (−0.110, evento Cybercab) è un fanout a 2 ticker. `SKIP_THRESHOLD` su tutti i cicli. Anche qui il vincolo long-only rende il costo accessibile nullo. |

Conteggio per la serie: **NO_NEWS 0, THIN_NEUTRAL 3, WRONG_SIGN 0, FILTERED 0,
OUT_OF_STRATEGY_SCOPE 2**.

Costo congetturale, size S4 standard (2% NAV ≈ $2.200):

| Simbolo | Lordo (close-to-close × size) | Accessibile (entrata al primo ciclo eleggibile → close) |
|---|---:|---:|
| MA | $72.86 | $15.75 (ingresso 595.595 alle 17:22, uscita 599.86) |
| V | $67.42 | $14.21 (ingresso 379.955 alle 17:22, uscita 382.41) |
| TSLA / F / INTC | — | $0.00 (long-only, non detenuti, ribasso) |
| **Totale** | **$140.28** | **$29.97** |

Lo scarto fra le due colonne è la misura del problema: anche se il gate avesse lasciato passare
MA e V, il segnale arriva così tardi che resta il 20-21% del movimento.

## 4. Mover già a libro: esito

Nessuno dei 7 è stato "catturato" nel senso di un ingresso tempestivo sulla notizia. Sei erano
posizioni vecchie che hanno semplicemente subito il ribasso.

| Simbolo | Return % | Sleeve | Da | Esito 2026-08-24 |
|---|---:|---|---|---|
| VALE | +3.08% | S1 | 2026-07-14 | Unico rialzo utile incassato, e senza alcuna copertura news (0 articoli). |
| SNOW | −3.00% | S1 | 2026-08-05 | MTM negativo. `SKIP_PYRAMIDING` alle 14:07 e 14:22 (sentiment **+0.327**, sopra gate, segno sbagliato). |
| MRVL | −3.27% | S1 | 2026-07-14 | MTM negativo. `SKIP_PYRAMIDING` alle 16:52 (sentiment **+0.442**) e 18:07. Il guard ha impedito di raddoppiare su un segnale rialzista errato. |
| AMD | −3.49% | S1 | 2026-07-14 | MTM negativo. Unico articolo del giorno un fanout a 13 ticker sul dazio Canada, score −0.033: `SKIP_THRESHOLD` su 10 cicli. |
| HOOD | −4.17% | S4 | 2026-08-21 | **Chiuso** alle 17:22, `portfolio_sell`, net **−16,56** (costo $1,04, 5,31 bps), 72,2 ore di tenuta. `drift_post_uscita` −57,22: uscire ha evitato altre perdite. |
| WDC | −5.24% | S4 | 2026-07-21 | MTM negativo. Unico articolo un fanout a 13 ticker (score −0.030). Posizione aperta da oltre un mese. |
| MU | −5.83% | S1 | 2026-07-28 | Peggiore della watchlist. `SKIP_PYRAMIDING` alle 14:07 e 14:37, quest'ultimo su un sentiment **+0.539** (il più alto della giornata) generato da un pezzo issuer-specific — "Micron CEO Sounds Alarm on AI Memory Crunch" — mentre il titolo perdeva il 5,8%. |

Trade chiusi il 2026-08-24 (tutti S4, tutti `portfolio_sell`):

| id | Simbolo | Entrata | Uscita | Net P&L | Costo | Drift post-uscita |
|---|---|---|---|---:|---:|---:|
| 751 | NFLX | 19/08 17:07 @ 80,31 | 24/08 14:22 @ 80,22 | −3,09 | $1,02 | −4,82 |
| 782 | NVDA | 24/08 14:37 @ 210,24 | 24/08 16:22 @ 210,99 | +6,31 | $0,38 | −22,42 |
| 755 | AVGO | 20/08 17:07 @ 363,13 | 24/08 17:22 @ 360,59 | −14,07 | $1,03 | −9,41 |
| 756 | HOOD | 21/08 17:07 @ 107,82 | 24/08 17:22 @ 106,92 | −16,56 | $1,04 | −57,22 |
| 784 | NVDA | 24/08 17:07 @ 209,99 | 24/08 18:52 @ 209,51 | −4,69 | $0,39 | −9,24 |
| 783 | SPCX | 24/08 17:07 @ 136,32 | 24/08 19:37 @ 134,88 | −21,82 | $1,99 | +1,60 |

Realizzato del giorno: **−53,91**, interamente S4 (S1 zero uscite). Ingressi: 3 (NVDA ×2, SPCX),
tutti S4, tutti rientrati e riusciti in giornata. NVDA è stata comprata, venduta, ricomprata e
rivenduta nello stesso giorno: entrambe le uscite con causale `below_entry_gate`.

## 5. Pattern osservato

**Rotazione netta fuori da semiconduttori/memoria e auto, dentro pagamenti e difensivi.**

Il lato debole è quasi interamente un solo gruppo: MU −5.83%, WDC −5.24%, AMD −3.49%, MRVL −3.27%,
INTC −3.12%, NVDA −2.91%, AVGO −2.63%, SOXX −2.67%, TSM −2.11%, ARM −1.87%, AMAT −1.65%. Il
catalizzatore è leggibile nei titoli scorati: "Samsung Crash Brings Semi Selling" (17:30) e "Memory
Stocks Slide as Trump Threatens 50% Tariffs on Canadian Autos, Steel in 2027" (17:45), quest'ultimo
un pezzo a 13 ticker che ricorre su AMD, INTC, MU, WDC e F.

Il secondo fronte è l'auto, sullo stesso dazio: F −3.33%, TSLA −3.83%, GM −1.08%, TM −1.79%.

Il lato forte è compatto e difensivo: pagamenti (MA +3.31%, V +3.06%), retail/staples (WMT +2.69%,
COST +2.50%, PG +1.33%), sanità (UNH +2.22%), banche (XLF +1.29%, JPM +1.37%, BAC +1.04%),
telecom (T +1.58%, VZ +1.42%). VALE +3.08% e i materiali sono l'unica presenza ciclica al rialzo,
coerente con la lettura "gli acciaieri salgono, Detroit scende" dell'articolo sui dazi.

Il pattern è chiaro e non serve inventarlo: rotazione da ciclici tech/auto verso difensivi e
pagamenti, con SPY quasi fermo (−0.29%) e QQQ (−1.00%) che assorbe tutto il rosso semi.

## 6. Confronto con i giorni precedenti

Rispetto alle righe già in `market_daily.jsonl`:

- **Semiconduttori, quarta seduta in alternanza.** 08-19 rout semi, 08-20 rimbalzo semi con banche
  deboli, 08-21 semi deboli e banche/materiali/auto forti, 08-24 semi di nuovo il gruppo peggiore —
  ma con l'auto che questa volta *segue* i semi invece di opporvisi (F era +3.00% il 08-21, oggi
  −3.33%). Il fattore comune del 24/08 è l'annuncio sui dazi, che colpisce entrambi i gruppi.
- **Copertura news in peggioramento monotòno.** `watchlist_zero_news`: 40 (08-19) → 41 (08-20) →
  43 (08-21) → **51** (08-24). Oggi 51 dei 96 simboli non hanno una sola riga in `news_log`, e la
  copertura "effective timely" è 21/96 = 21.9%. È il valore peggiore della serie recente.
- **Il mix delle cause di miss si è spostato.** NO_NEWS domina i cumulati (36) e i giorni precedenti
  (2, 2, 6), ma oggi è **zero**: tutti e 5 i miss avevano notizie. Il collo di bottiglia si è
  spostato dalla copertura al segnale (3 THIN_NEUTRAL) e al vincolo di libro (2
  OUT_OF_STRATEGY_SCOPE). Un giorno solo non fa tendenza, ma vale registrarlo.
- **Uscite verso il basso, un pattern che si ripete.** La mediana mobile a 20 giorni del
  `drift_post_uscita` è +0.08 (praticamente neutra), mentre oggi 5 chiusure su 6 hanno drift
  negativo (fino a −57,22 su HOOD). Coerente con una giornata di ribasso generale, non con un
  edge di timing sulle uscite.

## 7. Segnalazioni

Nessuna proposta di taratura né di fix: siamo dentro il periodo di sola osservazione
(`docs/evidence/OBSERVATION_CHARTER.md`, 2026-08-03 → ~2026-09-28). Ogni voce è agganciata al ledger.

**[F-043] *(nuovo)* Tutti i segnali che superano il gate 0.30 in giornata sono rialzisti, e i loro
titoli scendono.** Sono 9 i segnali generati il 2026-08-24 con score ≥ 0.30, su 7 ticker distinti:
MU +0.539 e +0.430, MRVL +0.368, SOXX +0.360, NVDA +0.378 e +0.316, DIS +0.413, LLY +0.322,
SPCX +0.320. **Nessuno è ribassista.** Alla chiusura: MU −5.83%, MRVL −3.27%, SOXX −2.67%,
NVDA −2.91%, SPCX −1.44%, LLY −0.67%, DIS +2.63% — media −2.02%, 6 su 7 negativi. Cinque di questi
sono stati fermati dal guard anti-pyramiding e due sono diventati ordini (NVDA, SPCX). Non è un
problema di fanout: MU +0.539 viene da "Micron CEO Sounds Alarm on AI Memory Crunch" e MRVL +0.368
da "Analyst Calls Marvell A Top Chip Pick", entrambi issuer-specific e correttamente attribuiti — il
modello ha letto bene l'articolo e l'articolo non prediceva il prezzo. È l'osservazione speculare a
[F-009]: quella dice che il gate scarta segnali del segno giusto, questa dice che quelli che passa
non hanno segno affidabile. Vanno tenute distinte finché la ricorrenza non dice altrimenti, ma sono
candidate alla fusione in sintesi. Non è un difetto di codice: è un'assenza di potere predittivo.

**[F-009] Il gate d'ingresso 0.30 scarta segnali del segno corretto sui due soli mover azionabili
della giornata.** MA sale +3.31% con un segnale issuer-specific corretto a **+0.054**; V sale +3.06%
con un massimo a **+0.025**. Entrambi finiscono in `SKIP_THRESHOLD` con la causale esplicita
`score 0.054 < feedback threshold 0.300`. Il problema non è il segno ma la magnitudine: il modulo
del punteggio è un ordine di grandezza sotto il gate anche quando la direzione è giusta.
Costo congetturale lordo $140.28 (MA $72.86 + V $67.42); sull'orizzonte accessibile $29.97.

**[F-001] Copertura news al minimo della serie: 51 simboli su 96 senza una sola riga in
`news_log`.** La copertura "effective timely" è 21/96 = 21.9%; 124 righe scorate da 57 articoli
unici, 28 dei quali effective-timely. Per settore la copertura è nulla su energy (0/6), industrials
(0/4) e materials (0/2) — e proprio da materials arriva VALE +3.08%, il secondo rialzo della
giornata, colto solo perché già a libro da S1 dal 14/07, non perché il sistema l'abbia visto.
La serie peggiora in modo monotòno: 40 → 41 → 43 → 51.

**[F-012] Tre quarti delle righe scorate nascono da articoli fan-out multi-ticker.**
`quota_righe_fanout` di giornata **0.7647**; 67 mapping fan-out extra su 124 righe totali. Casi
concreti: il segnale di F è fanout al 100% (`max_score_own: null`, `quota_righe_fanout: 1.0`) e
nasce interamente dai pezzi sul dazio Canada; TSLA è fanout su 3 righe su 4, e il suo unico
articolo issuer-specific è un filler retrospettivo da +0.008. Un singolo pezzo a 13 ticker
("Memory Stocks Slide as Trump Threatens 50% Tariffs…") produce da solo righe su AMD, INTC, MU, WDC
e F. Oggi nessun ordine è nato da un fanout improprio — i due articoli che hanno generato ordini
(NVDA, SPCX) hanno entrambi due soggetti legittimi — quindi l'occorrenza è strutturale e senza
costo attribuibile.

**[F-013] Churn intraday su NVDA: comprata, venduta, ricomprata e rivenduta nella stessa seduta.**
BUY 14:37 (score +0.380) → SELL 16:22 `below_entry_gate` → BUY 17:07 (score +0.378) → SELL 18:52
`below_entry_gate`. Due round-trip completi sullo stesso simbolo in quattro ore, più SPCX
comprata 17:07 e venduta 19:37 con la stessa causale dopo 2,5 ore. Costi espliciti dei tre
round-trip: $0,38 + $0,38 + $1,99 = **$2,75**. Il meccanismo è quello già a ledger: nessuna banda
fra il gate d'ingresso (0.30) e la condizione d'uscita, quindi il decadimento naturale del punteggio
basta a chiudere e il segnale successivo a riaprire. **Oggi il churn ha guadagnato, non perso**: i
`drift_post_uscita` delle tre uscite sono −22,42, −9,24 e +1,60, cioè uscire ha evitato in netto
circa $30 di ribasso. L'occorrenza va registrata comunque — il meccanismo è indipendente dal segno
del giorno — ma con costo zero, ed è un dato che va contro il finding, non a favore.

**[F-031] Il guard anti-pyramiding blocca 10 ingressi S4 su simboli già detenuti da S1/legacy.**
Cinque dei blocchi sono su segnali sopra gate: MU +0.539, MRVL +0.442, SOXX +0.360, SNOW +0.327,
LLY +0.322. Il messaggio resta quello noto (`P0-05 anti-pyramiding: gia' a libro dal …, peso non
allocato 2.0-2.5%`): il peso resta non allocato e nessun altro candidato lo raccoglie. **Anche qui
il segno del giorno è favorevole al difetto**: i cinque titoli bloccati hanno chiuso a −5.83%,
−3.27%, −2.67%, −3.00% e −0.67%, quindi a size S4 standard i cinque ingressi mancati avrebbero perso
circa **$340**. Costo dell'occorrenza: zero, non "non stimato".

**[F-030] La notizia arriva a movimento già compiuto.** Sui due ingressi NVDA il dossier misura
`quota_movimento_precedente_al_segnale` = **0.750** (14:37) e **0.786** (17:07): tre quarti del
movimento erano già avvenuti quando il segnale è diventato azionabile. Stesso quadro sui miss: il
segnale issuer-specific di MA è delle 19:15 e quello di V delle 19:15, con il primo ciclo eleggibile
alle 17:22 — da lì alla chiusura resta il 21.6% (MA) e il 21.1% (V) del movimento di giornata.
L'ingresso SPCX ha `denominatore_degenere: true` e va scartato dalla statistica.

**[F-021] La giornata operativa parte 30-37 minuti dopo l'apertura.** 24 cicli portfolio il
2026-08-24, primo alle **14:07 UTC** (10:07 ET) contro un'apertura alle 13:30 UTC (09:30 ET), ultimo
alle 19:52 UTC, nessun gap oltre i 16 minuti nella cadenza. Anche lo scoring parte tardi: il primo
dei 124 segnali della giornata è delle **14:00:37 UTC** (10:00 ET), e solo 5 segnali cadono nella
finestra 13:30-14:07. È l'ampiezza già descritta a ledger (finestre beat in ora UTC fissa, DST
ignorato). Costo non stimabile: la finestra persa oggi non conteneva segnali sopra gate — i più
forti (MU +0.430/+0.539, SOXX +0.360) arrivano alle 14:30-14:31, cioè dopo il primo ciclo.

**[F-002] L'MTM del book non è scomponibile per sleeve.** Delle 46 posizioni aperte a fine giornata,
**11 sono legacy senza `stop_strategy`** (BAC, GOOGL, GS, MS, PBR, RIO, ROKU, SPY, UBS, UNH, XLE),
tutte entrate il 2026-07-10. Il realizzato del giorno è attribuibile (−53,91, tutto S4), ma l'MTM
del book aperto — **−282,77**, cioè cinque volte il realizzato — non lo è: quattro di quelle
posizioni legacy (RIO, PBR, UBS, XLE) sono nel gruppo energia/materiali e nessuna sleeve se ne
assume il risultato.

### Sospetto difetto vs limite noto

Nessuna delle voci di oggi ha il profilo del bug nuovo. [F-009], [F-030] e [F-043] sono limiti di
capacità informativa della pipeline, non errori di codice. [F-013], [F-021] e [F-031] sono difetti
già a ledger che oggi si sono manifestati **a favore** del P&L, e questo va detto esattamente così:
tre occorrenze con costo zero non sono tre assoluzioni, ma nemmeno tre capi d'accusa. La decisione
se aprire una issue resta all'operatore.

## 8. Note metodologiche

- I numeri di mercato, copertura, ingressi, chiusure e opportunità vengono dal dossier
  deterministico. Le uniche grandezze calcolate in sessione sono l'equity Alpaca (109.861,38, riga
  di portfolio history datata 2026-08-25T00:00Z = 20:00 ET del 24/08) e l'MTM del book aperto
  (−282,77 = Σ qty × (close 24/08 − close precedente) sulle 46 posizioni aperte a fine giornata).
- `realizzato` (−53,91) e `mtm` (−282,77) non sommano alla variazione di equity (−269,00) per
  costruzione: il `net_pnl` dei trade è misurato contro il prezzo d'ingresso, che per quattro delle
  sei chiusure è di giorni precedenti.
- La classificazione delle cause di miss è interpretativa (lettura del testo degli articoli); i
  conteggi e i costi sono del dossier.
