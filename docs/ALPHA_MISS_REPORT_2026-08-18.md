# Alpha Miss Report — 2026-08-18

Fonte prezzi: Alpaca SIP, adjustment=all (dossier deterministico `docs/evidence/dossier/2026-08-18.json`, generato 2026-08-19T08:00:08Z). Soglia mover: |return| ≥ 3% (soglia pre-registrata, invariata dalle sedute precedenti). Soglia gate S4: 0,30 (nessuna deroga attiva).

## 1. Executive summary

22 mover ≥3% sulla watchlist (4 su, 18 giù), dispersione cross-sectional **2,84σ** — la più ampia osservata da inizio finestra, su un rout compatto di semiconduttori/hardware AI. **16 catturati, 6 mancati**. Dei 16 catturati, **14 sono semiconduttori/hardware già in portafoglio S1** da settimane (nessun nuovo ingresso su un mover oggi): il libro subisce il rout quasi per intero via mark-to-market su posizioni vecchie, non per decisioni prese oggi. Causa prevalente dei 6 miss: **FILTERED** (3/6) — per la prima volta nella finestra, tre segnali con segno corretto e magnitudine **sopra** il gate 0,30 (BIDU −0,454, HOOD −0,435, META −0,312) non generano comunque un ordine perché S4/S1 sono long-only per costruzione: il vincolo di direzione, non la soglia, è il collo di bottiglia. 1 NO_NEWS (RDDT), 2 THIN_NEUTRAL (AVGO sotto gate, ADBE su articolo fan-out generico). Costo congetturale dei miss: **$0,00 verificato per 5 dei 6** (mover al ribasso, libro long-only); il sesto (ADBE, unico miss al rialzo) resta **non stimabile** per il limite noto #277. Book: 24 cicli di portfolio, cadenza 15 min regolare, nessun gap; unica attività di libro sono 3 posizioni S4 non-mover (ingresso HD e uscita stessa giornata +$2,69, ingresso TSLA ancora aperto, ingresso e uscita NVDA +$3,12); NAV −$293,39 sulla giornata (110.473,80 → 110.180,41), quasi interamente MTM.

## 2. Rendimenti completi (96 simboli)

"Catturato" = simbolo con esposizione Alembic (posizione aperta o trade) in un momento qualsiasi del 2026-08-18, indipendentemente dal fatto che sia un mover.

| Simbolo | Return % | Catturato |
|---|---:|:---:|
| LLY | +3.60% | sì |
| ADBE | +3.58% | no |
| ABBV | +3.43% | sì |
| JNJ | +3.33% | sì |
| BABA | +2.76% | no |
| CRM | +2.71% | no |
| XOM | +2.54% | sì |
| NKE | +2.48% | no |
| CMCSA | +2.46% | no |
| NFLX | +2.30% | no |
| MA | +2.14% | no |
| AZN | +2.05% | no |
| NVO | +1.85% | no |
| INFY | +1.81% | no |
| XLE | +1.76% | sì |
| IBM | +1.67% | no |
| XLV | +1.60% | sì |
| GE | +1.53% | sì |
| NOW | +1.52% | no |
| V | +1.51% | no |
| CVX | +1.50% | sì |
| TMUS | +1.46% | no |
| AAPL | +1.45% | sì |
| PFE | +1.41% | no |
| BP | +1.31% | no |
| SAP | +1.27% | no |
| JD | +1.12% | no |
| VZ | +1.00% | no |
| BRK.B | +0.95% | no |
| T | +0.89% | no |
| COST | +0.82% | no |
| WMT | +0.76% | no |
| AXP | +0.69% | no |
| JPM | +0.63% | sì |
| MCD | +0.55% | no |
| BAC | +0.53% | sì |
| XLF | +0.45% | sì |
| DIS | +0.43% | no |
| SHEL | +0.43% | sì |
| MMM | +0.41% | sì |
| MSFT | +0.27% | no |
| PG | +0.23% | no |
| GOOGL | +0.06% | sì |
| DB | −0.08% | no |
| HD | −0.12% | sì (ingresso+uscita oggi) |
| WFC | −0.16% | no |
| MS | −0.30% | sì |
| ROKU | −0.33% | sì |
| PBR | −0.38% | sì |
| UNH | −0.43% | sì |
| PANW | −0.43% | sì |
| TM | −0.49% | no |
| VALE | −0.51% | sì |
| RIO | −0.53% | sì |
| PLTR | −0.59% | no |
| MRK | −0.59% | sì |
| C | −0.62% | sì |
| SPY | −0.68% | sì |
| AMZN | −0.71% | no |
| TSLA | −0.72% | sì (ingresso oggi) |
| GM | −0.78% | sì |
| ERIC | −0.79% | no |
| F | −0.85% | no |
| UBS | −0.88% | sì |
| GS | −1.03% | sì |
| SONY | −1.14% | no |
| CSCO | −1.14% | no |
| QCOM | −1.23% | no |
| IWM | −1.26% | sì |
| BA | −1.28% | no |
| SNOW | −1.45% | sì |
| QQQ | −1.69% | sì |
| SBUX | −1.77% | sì |
| SPCX | −1.98% | no |
| DELL | −2.33% | sì |
| NVDA | −2.34% | sì (ingresso+uscita oggi) |
| XLK | −2.47% | sì |
| ORCL | −2.63% | no |
| AVGO | −3.17% | no |
| NOK | −3.62% | sì |
| TXN | −3.77% | sì |
| RDDT | −3.80% | no |
| AMAT | −3.92% | sì |
| TSM | −4.07% | sì |
| ASML | −4.26% | sì |
| AMD | −4.27% | sì |
| META | −4.45% | no |
| CAT | −4.63% | sì |
| HOOD | −4.90% | no |
| SOXX | −4.96% | sì |
| INTC | −6.58% | sì |
| ARM | −6.67% | sì |
| MU | −7.02% | sì |
| WDC | −7.43% | sì |
| MRVL | −7.82% | sì |
| BIDU | −12.73% | no |

## 3. Miss classificati (≥3%, 6 titoli)

Tutti e 22 i mover ≥3% sono stati controllati: 16 sono già in portafoglio (catturati via holding, vedi §4), i 6 restanti sono i soli candidati genuini a "miss" — questo coincide esattamente con `candidati_miss` del dossier (`aggregati.cause_del_giorno.totale_candidati=6`).

| Simbolo | Return % | Categoria | Evidenza |
|---|---:|---|---|
| [F-040] BIDU | −12.73% | FILTERED | 1 articolo dedicato ("Baidu's AI Pivot Hits the Gas, but Its Advertising Cash Cow Is Losing Steam" — miss di ricavi/utili Q2, pubblicità debole). Segnale 14:15 **−0,454** (ensemble, non-fallback) — segno concorde col prezzo, **11 punti sopra** il gate 0,30. Non genera ordine: S4/S1 comprano solo su score positivo (long-only per costruzione). Costo $0,00 verificato (accessible_opportunity_usd=0 nel dossier), non per assenza di dato ma per il vincolo di direzione — gross opportunity teorica $279,97. |
| [F-040] HOOD | −4.90% | FILTERED | 1 articolo dedicato ("Why Is Robinhood Stock Falling on Tuesday?" — calo volumi crypto YoY, venti contrari di mercato). Segnale 16:15 **−0,435** (ensemble, non-fallback) — segno corretto, sopra gate. Stesso meccanismo di BIDU: long-only blocca l'ordine indipendentemente dalla qualità del segnale. Costo $0,00 verificato — gross opportunity teorica $107,89. |
| [F-040] META | −4.45% | FILTERED | 5 articoli, uno genuinamente META-specifico ("What's Going On With Meta Platforms Stock Tuesday?" — processo per sicurezza minori in California, fino a $1,4 trilioni di responsabilità potenziale), gli altri macro/AI-bubble (Bill Eigen "2008 crash alarm", Steve Eisman su spese AI +55%, bond AI $400B). Segnale più forte 15:30 **−0,312** (ensemble, non-fallback) — sopra gate. Costo $0,00 verificato — gross opportunity teorica $97,83. |
| [F-001] RDDT | −3.80% | NO_NEWS | 0 righe `news_log`, 0 segnali. Costo $0,00 verificato: mover al ribasso, libro long-only, RDDT non detenuto. |
| [F-009] AVGO | −3.17% | THIN_NEUTRAL (sotto gate) | 1 articolo, rilevante ma multi-ticker fan-out ("Nvidia, AMD, Broadcom, Meta Slide as Bond Yields Surge...", taggato anche AMD/META/NVDA). Segnale 17:30 **−0,189** (ensemble, non-fallback) — segno corretto, 11 punti **sotto** il gate 0,30 (a differenza di BIDU/HOOD/META, qui il collo di bottiglia è davvero la magnitudine, non la direzione). Costo $0,00 verificato. |
| [F-012] ADBE | +3.58% | THIN_NEUTRAL (fan-out) | 1 articolo, roundup di mercato generico taggato a 3 ticker (ADBE, HD, IWM): "Nasdaq Drops, Chip Stocks Crater As Bond Yields Bite" — non parla di ADBE, e descrive un crollo dei chip mentre ADBE ha chiuso in controtendenza (+3,58%, miglior mover del giorno). Segnale 18:15 **−0,012** (quasi zero, segno peraltro discorde dal prezzo ma irrilevante alla magnitudine). Unico miss al rialzo del giorno: costo **non stimabile**, bloccato dal limite noto #277 (nessuna barra intraday prezzata al ciclo eligible — vedi `opportunity_v2.missingness` nel dossier). |

Conteggio cause: **NO_NEWS 1 · THIN_NEUTRAL 2 · WRONG_SIGN 0 · FILTERED 3 · OUT_OF_STRATEGY_SCOPE 0.**

Nota sulla categoria FILTERED di oggi: non è un ranking/breadth/hysteresis che scarta un candidato valido tra più concorrenti — è il vincolo strutturale long-only della strategia (nessun ramo short nel codice) che rende score negativi strutturalmente non azionabili, qualunque sia la loro qualità. Lo segnaliamo come FILTERED perché è comunque "un meccanismo della strategia" che scarta un segnale sopra soglia (definizione della carta), ma la causa è di design dichiarato, non un bug di selezione — si veda §7.

## 4. Titoli catturati: esito

Nessun nuovo ingresso oggi su un mover (`ingressi` del dossier riguarda solo HD, TSLA, NVDA — nessuno dei tre è un mover ≥3%). I 16 mover ≥3% catturati sono tutti posizioni **già aperte prima del 18/08**, esposte via mark-to-market:

| Simbolo | Return % | Strategia | Apertura posizione | MTM stimato oggi (qty × Δclose) |
|---|---:|---|---|---:|
| LLY | +3.60% | S1 | 2026-07-15 | +$29.37 |
| ABBV | +3.43% | S1 | 2026-08-06 | +$24.79 |
| JNJ | +3.33% | S1 | 2026-07-15 | +$27.16 |
| NOK | −3.62% | S1 | 2026-07-14 | −$16.21 |
| TXN | −3.77% | S1 | 2026-07-24 | −$28.71 |
| AMAT | −3.92% | S1 | 2026-07-14 | −$17.98 |
| TSM | −4.07% | S1 | 2026-07-14 | −$32.12 |
| ASML | −4.26% | S1 | 2026-07-14 | −$30.26 |
| AMD | −4.27% | S1 | 2026-07-14 | −$17.58 |
| CAT | −4.63% | S1 | 2026-07-30 | −$37.39 |
| SOXX | −4.96% | S1 | 2026-07-28 | −$32.02 |
| INTC | −6.58% | S4 | 2026-08-12 | −$81.90 |
| ARM | −6.67% | S1 | 2026-08-03 | −$25.52 |
| MU | −7.02% | S1 | 2026-07-28 | −$28.25 |
| WDC | −7.43% | S4 | 2026-07-21 | −$118.81 |
| MRVL | −7.82% | S1 | 2026-07-14 | −$28.44 |

Somma dei 16 mover catturati: **−$413,87** di MTM stimato (13 semiconduttori/hardware in rosso, 3 pharma in verde), su un NAV totale che ha perso −$293,39 nella giornata — il resto del libro (33 posizioni non-mover, incluse le 11 legacy senza `stop_strategy`, §7) ha compensato parzialmente.

Attività di libro del giorno (non mover, riportata per completezza): **HD** (S4, entrata 14:22 a $339,98, uscita 16:07 a $340,88, `exit_reason=portfolio_sell`, net_pnl **+$2,69**, drift post-uscita −$12,77 — il prezzo è sceso dopo l'uscita), **NVDA** (S4, entrata 16:37 a $219,65, uscita 18:22 a $220,23, net_pnl **+$3,12**, drift post-uscita −$2,85) e **TSLA** (S4, entrata 16:37 a $337,20, ancora aperta a fine giornata). Realizzato S4 del giorno: +$5,80; S1 realizzato: $0,00 (nessuna chiusura S1 oggi).

## 5. Pattern osservato

Rotazione netta e leggibile: **rout compatto su semiconduttori/hardware AI** (MRVL −7,82%, WDC −7,43%, MU −7,02%, ARM −6,67%, INTC −6,58%, SOXX −4,96%, AMD −4,27%, ASML −4,26%, TSM −4,07%, AMAT −3,92%, TXN −3,77%, NOK −3,62%) su rialzo dei rendimenti obbligazionari — esplicito nei titoli stessi ("Nvidia, AMD, Broadcom, Meta Slide as Bond Yields Surge", "Nasdaq Drops, Chip Stocks Crater As Bond Yields Bite", "AI's Half-Trillion-Dollar Borrowing Binge Is Competing With Uncle Sam for Bond Buyers"). SPY (−0,68%) e QQQ (−1,69%) sono negativi ma molto meno della dispersione interna (2,84σ, la più ampia della finestra osservata): non è un ribasso di mercato generale, è un comparto specifico che crolla. Controtendenza isolata su pharma/healthcare (LLY +3,60%, ABBV +3,43%, JNJ +3,33%). BIDU (−12,73%, idiosincratico, miss di utili) è il mover più forte ma fuori tema.

**Il libro è quasi interamente esposto al tema che oggi va male**: 14 dei 16 mover catturati sono semiconduttori/hardware, tutti posizioni S1 aperte fra il 13/07 e il 12/08 — nessuna decisione presa oggi ha contribuito al risultato del giorno, che è quasi puro effetto di rotazione settoriale su un book strutturalmente concentrato in quel tema da settimane.

## 6. Confronto con giorni precedenti

- **Dispersione più ampia della finestra osservata (2,84σ)**, sopra il precedente massimo 2,37σ del 08-12 e ben oltre la banda 1,5-2,2σ tipica delle sedute recenti (2,12σ il 08-17, 2,18σ il 08-14, 1,54σ il 08-11).
- **Rotazione verso i semiconduttori l'11/08-12/08 e il 17/08 era stata al RIALZO** (AMAT/MRVL/WDC/MU tutti positivi, memoria in rally sulla scarsità); oggi lo stesso identico blocco di titoli (MRVL, WDC, MU, AMAT, INTC, ARM, SOXX) inverte completamente segno. È lo stesso libro S1 concentrato nello stesso tema che ha guadagnato via MTM per due sedute e oggi perde via MTM in un colpo solo — la concentrazione settoriale del book, già osservata come fonte di guadagno passivo l'11-12/08, oggi è la fonte del rosso.
- **Prima comparsa nella finestra di FILTERED come causa dominante**: nei giorni precedenti FILTERED era sempre 0 (08-17: 0, 08-14: 0, 08-12: 0, 08-11: 0, 08-10: 0). Oggi 3/6, e per un meccanismo specifico mai osservato prima con questa nettezza — segnale corretto e sopra soglia bloccato puramente dalla direzione (long-only), non da ranking/breadth. Vedi F-040, nuovo finding.
- **Copertura news 40/96 (42%) zero righe**, dentro la banda 38-57% osservata dal 07-31, nessun cambio di regime.

## 7. Segnalazioni

[F-040] **Nuovo finding.** Tre mover al ribasso (BIDU −12,73%, HOOD −4,90%, META −4,45%) hanno oggi un segnale ensemble col segno corretto e sopra il gate d'ingresso 0,30 — la pipeline ha funzionato correttamente end-to-end, copertura specifica, segno concorde, magnitudine sufficiente — eppure zero probabilità di generare un ordine, perché S4/S1 comprano solo su score positivo: nessun ramo short esiste nel codice. È diverso da F-009 (lì il segnale non supera il gate; qui lo supera abbondantemente). Non lo segnaliamo come un difetto: il long-only è una scelta di design dichiarata (CLAUDE.md), non un bug — lo registriamo come **osservazione strutturale quantificata**, perché la decisione se valga la pena costruire una via di monetizzazione del lato ribassista (short diretto, o hedge via opzioni indice come già annotato nel backlog #197/VIX-SPX) spetta all'operatore, non a questo report. Costo di oggi $0,00 verificato (il libro non può comunque monetizzare un ribasso), gross opportunity teorica aggregata $485,69.

[F-001] Copertura news bassa sulla watchlist — ricorrenza confermata: 40/96 simboli (42%) zero righe in `news_log` il 08-18. Un solo miss NO_NEWS puro oggi (RDDT −3,80%), costo $0,00 verificato (mover al ribasso, libro long-only). Nessun nuovo costo aggiunto al cumulato.

[F-009] Il gate d'ingresso S4 scarta segnali col segno corretto ma sotto soglia — ricorrenza pulita (gate di design 0,30, nessuna deroga attiva): AVGO −3,17%, segnale −0,189, segno corretto, 11 punti sotto gate. Costo $0,00 verificato. A differenza delle tre occorrenze di F-040 di oggi, qui la magnitudine è davvero il collo di bottiglia, non la direzione.

[F-012] Articoli fan-out multi-ticker generano segnali deboli su titoli che si muovono in controtendenza rispetto al tema dell'articolo — ricorrenza: l'unico articolo del giorno su ADBE è un roundup generico ("Nasdaq Drops, Chip Stocks Crater...") taggato anche a HD/IWM, non specifico ad ADBE, e descrive un crollo dei chip mentre ADBE ha chiuso +3,58% (miglior mover del giorno) in controtendenza. Segnale quasi zero (−0,012). Costo non stimabile: oltre al limite di attribuzione, bloccato anche dal limite noto #277 sul controfattuale intraday.

[F-002] non ricontrollato in dettaglio oggi oltre la verifica di persistenza: le stesse 11 posizioni legacy senza `stop_strategy` (BAC, GOOGL, GS, MS, PBR, RIO, ROKU, SPY, UBS, UNH, XLE, tutte aperte il 07-10) risultano ancora aperte, dodicesima seduta consecutiva, e contribuiscono circa **−$13,80** di MTM stimato sui −$293,39 di NAV della giornata (4,7% — quota minore rispetto ad altre sedute, nessuno dei nomi coinvolti è un mover ≥3% oggi). Nessun nuovo id: ricorrenza minore, non è il driver del giorno (che è il rout semiconduttori, tutto su posizioni correttamente attribuite a S1).

Nessun caso WRONG_SIGN oggi, nessun caso OUT_OF_STRATEGY_SCOPE (nessun ETF settoriale della watchlist è fra i 6 candidati miss).
