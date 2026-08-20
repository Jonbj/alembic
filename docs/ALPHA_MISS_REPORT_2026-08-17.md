# Alpha Miss Report — 2026-08-17

Fonte prezzi: Alpaca SIP, adjustment=all (dossier deterministico `docs/evidence/dossier/2026-08-17.json`, generato 2026-08-18T08:00:08Z). Soglia mover: |return| ≥ 3% (soglia pre-registrata, invariata dalle sedute precedenti). Soglia gate S4: 0,30.

## 1. Executive summary

13 mover ≥3% sulla watchlist (5 su, 8 giù), dispersione cross-sectional 2,12σ. **4 catturati** (AMAT, MRVL, WDC, MU — tutte posizioni S1/S4 già aperte prima di oggi, nessun nuovo ingresso), **9 mancati**. Causa prevalente: **THIN_NEUTRAL** (5/9) — copertura tangenziale o articoli non specifici sul titolo. 2 NO_NEWS (RDDT, NOW), 2 WRONG_SIGN (INFY, MSFT — segnale fallback di segno opposto al prezzo). **Costo congetturale dei miss: $0,00 verificato per 8 dei 9** (tutti mover al ribasso, libro long-only); il nono (SPCX, unico miss al rialzo) resta **non stimabile** per il limite noto #277 (nessuna barra intraday prezzata al ciclo eligible). Zero nuovi ingressi oggi: l'unica attività di libro sono due chiusure S4 (JD −$36,80, BA −$27,93), entrambe fuori dai mover del giorno. 24 cicli di portfolio, cadenza 15 min regolare, nessun gap.

## 2. Rendimenti completi (96 simboli)

"Catturato" = simbolo con esposizione Alembic (posizione aperta o trade) in un momento qualsiasi del 2026-08-17, indipendentemente dal fatto che sia un mover.

| Simbolo | Return % | Catturato |
|---|---:|:---:|
| AMAT | +5.55% | sì |
| MRVL | +5.54% | sì |
| WDC | +5.35% | sì |
| SPCX | +4.45% | no |
| MU | +4.13% | sì |
| CAT | +2.93% | sì |
| ASML | +2.12% | sì |
| PBR | +2.07% | sì |
| RIO | +1.60% | sì |
| SOXX | +1.58% | sì |
| XOM | +1.50% | sì |
| CVX | +1.35% | sì |
| SHEL | +1.27% | sì |
| TXN | +1.19% | sì |
| GS | +1.14% | sì |
| CSCO | +1.09% | no |
| TSM | +1.08% | sì |
| XLE | +1.08% | sì |
| INTC | +0.97% | sì |
| VALE | +0.88% | sì |
| JNJ | +0.78% | sì |
| BP | +0.75% | no |
| BABA | +0.73% | no |
| HOOD | +0.72% | no |
| BIDU | +0.43% | no |
| ROKU | +0.40% | sì |
| MS | +0.39% | sì |
| SNOW | +0.36% | sì |
| ABBV | +0.35% | sì |
| PFE | +0.30% | no |
| GE | +0.29% | sì |
| AZN | +0.28% | no |
| LLY | +0.25% | sì |
| SBUX | +0.21% | sì |
| NOK | +0.19% | sì |
| XLK | +0.16% | sì |
| MRK | +0.10% | sì |
| SAP | −0.06% | no |
| NVDA | −0.07% | no |
| AAPL | −0.11% | sì |
| AVGO | −0.14% | no |
| QQQ | −0.16% | sì |
| XLV | −0.19% | sì |
| HD | −0.29% | no |
| IWM | −0.34% | sì |
| UBS | −0.35% | sì |
| SPY | −0.47% | sì |
| AMZN | −0.51% | no |
| JPM | −0.52% | sì |
| GOOGL | −0.55% | sì |
| C | −0.59% | sì |
| COST | −0.79% | no |
| WMT | −0.82% | no |
| T | −0.84% | no |
| PLTR | −0.86% | no |
| VZ | −0.87% | no |
| TSLA | −0.87% | no |
| BAC | −0.93% | sì |
| ERIC | −0.97% | no |
| PG | −0.99% | no |
| XLF | −1.00% | sì |
| TM | −1.01% | no |
| DB | −1.14% | no |
| BRK.B | −1.15% | no |
| MA | −1.23% | no |
| NVO | −1.32% | no |
| MMM | −1.34% | sì |
| TMUS | −1.36% | no |
| WFC | −1.44% | no |
| V | −1.46% | no |
| UNH | −1.52% | sì |
| AMD | −1.63% | sì |
| AXP | −1.83% | no |
| JD | −1.93% | sì (uscita oggi) |
| QCOM | −2.18% | no |
| PANW | −2.21% | sì |
| F | −2.23% | no |
| DELL | −2.24% | sì |
| CMCSA | −2.33% | no |
| IBM | −2.33% | no |
| SONY | −2.43% | no |
| BA | −2.47% | sì (uscita oggi) |
| ORCL | −2.57% | no |
| CRM | −2.67% | no |
| MCD | −2.68% | no |
| NFLX | −2.74% | no |
| GM | −2.77% | sì |
| ARM | −2.87% | sì |
| MSFT | −3.04% | no |
| DIS | −3.14% | no |
| META | −3.54% | no |
| ADBE | −3.78% | no |
| INFY | −3.89% | no |
| NKE | −4.03% | no |
| NOW | −5.08% | no |
| RDDT | −7.63% | no |

## 3. Miss classificati (≥3%, 9 titoli)

| Simbolo | Return % | Categoria | Evidenza |
|---|---:|---|---|
| [F-001] RDDT | −7.63% | NO_NEWS | 0 righe `news_log`, 0 segnali. Costo $0,00 verificato: mover al ribasso, libro long-only. |
| [F-001] NOW | −5.08% | NO_NEWS | 0 righe `news_log`, 0 segnali. Costo $0,00 verificato: mover al ribasso, libro long-only. |
| SPCX | +4.45% | THIN_NEUTRAL | 4 articoli specifici SpaceX (lancio record, "Sellers Are Waiting Above", disclosure stake, xAI/Grok — quest'ultimo poco pertinente). 4 segnali: +0.188, 0.0, +0.18 (fallback), 0.0 — tutti col segno giusto ma nessuno supera il gate 0,30. Unico miss al rialzo del giorno: costo **non stimabile**, bloccato dal limite noto #277 (nessuna barra intraday prezzata al ciclo eligible — vedi `opportunity_v2.missingness` nel dossier). |
| NKE | −4.03% | THIN_NEUTRAL | 1 solo articolo ("Why Is Nike Stock Falling on Monday?"), segnale −0.125 (unico, non-fallback) — segno giusto, ampiamente sotto soglia. Costo $0,00: mover al ribasso, long-only. |
| INFY | −3.89% | WRONG_SIGN | 5 articoli genuinamente specifici sul settore IT indiano in calo ("IT Stocks Today: Why Nifty IT Declined 1.50%; Infosys... Under Pressure", "Nifty... markets stay in the red"). Il segnale delle 16:45 (**+0.42**, fallback single-model) è scorato positivo proprio sull'articolo che descrive il ribasso del settore — segno opposto al prezzo e sopra il gate. Gli altri 4 segnali (−0.10, −0.11, −0.02, −0.165, tutti fallback) hanno segno corretto ma sotto soglia. Costo $0,00: mover al ribasso, long-only — il segno errato non ha comunque prodotto un ordine. |
| ADBE | −3.78% | THIN_NEUTRAL | 1 solo articolo, tangenziale ("SanDisk Rips 10%, Micron Rises 6% as AI Memory Frenzy Builds") — non parla di ADBE, la menzione è di contesto. Segnale 0.0. Costo $0,00: mover al ribasso, long-only. |
| META | −3.54% | THIN_NEUTRAL | 5 articoli, tutti listicle/roundup generici ("Tepper Cuts Micron Stake...", "Ackman Bets Big on Magnificent 7... Only Loves 3 of Them", "Anthropic's Revenue Jumps 14x") — nessuno è news specifica su META. Segnali deboli e misti: 0.0, +0.049, +0.04 (fb), +0.24 (fb), 0.0 — nessuno vicino al gate. Costo $0,00: mover al ribasso, long-only. |
| DIS | −3.14% | THIN_NEUTRAL | 3 articoli, nessuno sostanzialmente su Disney ("Ackman's Biggest Portfolio Overhaul... Return to Netflix", una rubrica media, un pezzo Halloween Lowe's che cita solo di striscio). Segnali 0.0, −0.06 (fb), 0.0. Costo $0,00: mover al ribasso, long-only. |
| MSFT | −3.04% | WRONG_SIGN | 6 articoli, in gran parte listicle AI-macro non specifici ("Eisman Says AI Has an Achilles' Heel", "Ackman Bets Big on Magnificent 7... Only Loves 3 of Them", "Anthropic's Revenue Jumps 14x"). Il segnale più forte della giornata (**+0.30**, 18:15, fallback, esattamente al gate) è positivo — presumibilmente dall'articolo Ackman, che descrive un endorsement — mentre il titolo ha chiuso −3,04%; i restanti 4 segnali sono deboli ma col segno corretto (−0.001, −0.0675, −0.04, −0.04 fb). Segnali contrastanti, nessuno riconducibile a un evento specifico MSFT del giorno. Costo $0,00: mover al ribasso, long-only. |

Conteggio cause: **NO_NEWS 2 · THIN_NEUTRAL 5 · WRONG_SIGN 2 · FILTERED 0 · OUT_OF_STRATEGY_SCOPE 0.**

Nessun caso FILTERED: nessun segnale sopra 0,30 col segno corretto è stato scartato da ranking/breadth/hysteresis oggi (gli unici due segnali sopra o al gate, INFY +0.42 e MSFT +0.30, hanno segno sbagliato — sono WRONG_SIGN, non FILTERED). Nessun OUT_OF_STRATEGY_SCOPE: nessuno dei mover del giorno è un ETF settoriale della watchlist.

## 4. Titoli catturati: esito

Nessun nuovo ingresso oggi (`ingressi` vuoto nel dossier). I 4 mover ≥3% catturati sono posizioni **già aperte prima del 17/08** che hanno beneficiato del rialzo via mark-to-market, non nuovi ordini:

| Simbolo | Return % | Strategia | Apertura posizione | MTM stimato oggi (qty × Δclose) |
|---|---:|---|---|---:|
| AMAT | +5.55% | S1 | 2026-07-14 | +$24.11 |
| MRVL | +5.54% | S1 | 2026-07-14 | +$19.10 |
| WDC | +5.35% | S4 | 2026-07-21 | +$81.11 |
| MU | +4.13% | S1 | 2026-07-28 | +$15.96 |

Attività di libro del giorno (non mover, riportata per completezza): **JD** (S4, entrata 08-14 a $29,02, uscita 08-17 15:52 a $28,46, `exit_reason=portfolio_sell`, net_pnl **−$36,80**, drift post-uscita +$2,49 — prezzo risalito dopo l'uscita) e **BA** (S4, entrata 08-14 a $230,98, uscita 08-17 15:52 a $227,53, net_pnl **−$27,93**, drift post-uscita −$12,34 — uscita tempestiva, il prezzo ha continuato a scendere).

## 5. Pattern osservato

Rotazione settoriale leggibile: i 5 mover al rialzo sono quasi tutti hardware/memoria semiconduttori — AMAT (equipaggiamento), MRVL, WDC, MU (memoria) — con SPCX come outlier non-semi. L'articolo ADBE del giorno lo rende esplicito: *"SanDisk Rips 10%, Micron Rises 6% as AI Memory Frenzy Builds"*. Sul lato opposto, i mover al ribasso sono in prevalenza software/mega-cap AI-adjacent (NOW, ADBE, MSFT, META) più consumer/media diversi (NKE, DIS, RDDT, INFY) — nessun tema comune stretto oltre "non è memoria/semiconduttori". La lettura più supportata dai dati è una **rotazione infra-tech verso l'hardware di memoria e lontano dal software/mega-cap AI**, non una rotazione generica di mercato (SPY −0,47%, QQQ −0,16%, entrambi piatti-negativi mentre la dispersione interna è ampia, 2,12σ).

## 6. Confronto con giorni precedenti

- **Giornata quasi interamente accessibile solo sul lato "captured-by-holding"**: per la prima volta nella finestra osservata di recente, tutti e 4 i mover catturati lo sono via posizioni preesistenti, zero nuovi ingressi S4 in giornata — coerente con l'assenza di segnali sopra gate col segno giusto (nessun FILTERED, nessun BUY nuovo).
- **WRONG_SIGN torna a comparire dopo assenza prolungata**: gli ultimi report con WRONG_SIGN erano 08-03 (SPCX) e più indietro 07-30 (AVGO), 07-27 (RDDT), 07-24 (TMUS) — sempre isolato a un singolo segnale fallback. Oggi 2 casi (INFY, MSFT) nello stesso giorno, entrambi su segnali fallback single-model che hanno "vinto" sul segno rispetto a segnali ensemble/altri fallback correttamente segnati. Pattern ricorrente non nuovo (stesso meccanismo dei giorni citati), ma la doppia occorrenza nello stesso giorno non ha precedenti nella finestra recente.
- **Copertura news 38/96 (40%) a zero**, leggermente sotto la banda 42-57% osservata dal 07-31 in poi — miglioramento marginale, non un cambio di regime.
- Come già osservato più volte (F-001), quando la coda del giorno cade prevalentemente al ribasso su un libro long-only, il costo congetturale dei miss collassa a zero: oggi 8 dei 9 miss sono a costo $0,00 verificato, l'unico potenzialmente positivo (SPCX) resta bloccato dal limite di misura #277 già tracciato.

## 7. Segnalazioni

[F-001] Copertura news bassa sulla watchlist — ricorrenza confermata: 38/96 simboli (40%) zero righe in `news_log` il 08-17, leggero miglioramento sulla banda 42-57% osservata dal 07-31. 2 dei 9 miss del giorno sono NO_NEWS puri (RDDT −7.63%, NOW −5.08%), ma **costo $0,00 verificato**: entrambi mover al ribasso su libro long-only, nessuna occasione era catturabile nella direzione del movimento. Nessun nuovo costo aggiunto al cumulato.

[F-002] Attribuzione strategia mancante su trade legacy — ricorrenza esatta: le stesse 11 posizioni (BAC, GOOGL, GS, MS, PBR, RIO, ROKU, SPY, UBS, UNH, XLE, tutte aperte il 07-10) restano con `stop_strategy` NULL, undicesima seduta consecutiva. Oggi contribuiscono **+$21,53 di MTM stimato su +$37,28 di nav_change_today (58%)** — la fetta non attribuibile è oggi la maggioranza del movimento netto del NAV, il valore più alto osservato finora nella serie di occorrenze di questo finding. Nessuno dei nomi coinvolti è un mover ≥3% oggi. Costo null: non è una perdita, è P&L non attribuibile allo split S1/S4 richiesto dalla domanda di uscita n.2 della carta.

Questa non è un'osservazione di bug nuovo: entrambe le voci sono ricorrenze quantificate di finding già aperti, non richiedono nuovi id per la regola "nel dubbio, aggancia".
