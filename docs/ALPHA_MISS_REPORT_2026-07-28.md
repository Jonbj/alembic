# Alpha Miss Report — 2026-07-28

Scope: solo i 96 simboli in `config/trading.yaml` → `symbols.watchlist`. Rendimenti Alpaca daily bars (close 2026-07-28 vs close 2026-07-27). Dati Alembic da `alembic-postgres-1` (trades, execution_decisions, sentiment_signals, news_log, portfolio_cycles). Nessuna modifica al codice o al sistema — solo lettura.

## 1. Executive Summary

- Soglia mover: **|return| ≥ 3%** (26/96 simboli, ~27% della watchlist — giornata ad alta dispersione, non rumore normale).
- Giornata dominata da una **rotazione settoriale netta: semiconduttori in vendita pesante (11 dei 15 mover negativi appartengono al bucket `semis` del sector map), enterprise software/IT-services e alcuni industrial/media in acquisto** (6 dei 11 mover positivi sono `tech`/SaaS).
- **5/26 mover catturati** (BA, CRM, SOXX, ARM, MU — questi ultimi tre con esito negativo/misto, non guadagno).
- **21/26 mover mancati**: causa prevalente **NO_NEWS** (9 simboli — copertura news zero) e **THIN_NEUTRAL** (8 simboli — segnale presente ma troppo debole/divergente per superare la soglia 0.30). 4 simboli **FILTERED** by design (esclusione fallback #108 o long-only ranker).
- Nessun caso **WRONG_SIGN** puro (score forte e di segno opposto al prezzo) tra i mover del giorno.
- 24 cicli di portfolio, cadenza 15 min regolare tutto il giorno, nessun gap.
- Anomalia degna di nota (non diagnosticata a fondo, solo segnalata): **ADBE** ha avuto un segnale ensemble reale (non-fallback, score 0.038) sotto soglia ma **zero righe in `execution_decisions`** per l'intera giornata, mentre segnali di magnitudine comparabile (AMAT, CAT, NOK) sono stati regolarmente loggati come `SKIP_THRESHOLD`. Non è spiegato né dall'esclusione fallback (#108) né dal filtro long-only del ranker — potrebbe essere un gap di logging, non solo di segnale. Decisione se aprire issue lasciata all'operatore.

## 2. Tabella completa rendimenti (96 simboli)

| Simbolo | Return % | Catturato |
|---|---:|:---:|
| CMCSA | +6.10% | no |
| INFY | +5.56% | no |
| IBM | +5.21% | no |
| ADBE | +4.81% | no |
| NOW | +4.79% | no |
| SAP | +4.77% | no |
| BA | +4.76% | **sì** |
| CRM | +4.55% | **sì** |
| GM | +3.75% | no |
| ERIC | +3.10% | no |
| BRK.B | +3.06% | no |
| TMUS | +2.92% | no |
| NFLX | +2.83% | no |
| JD | +2.71% | no |
| UNH | +2.67% | no |
| NVO | +2.60% | no |
| SPCX | +2.56% | no |
| HD | +2.49% | no |
| ABBV | +2.45% | no |
| MMM | +2.38% | no |
| XLV | +2.36% | no |
| PFE | +2.35% | no |
| DIS | +2.32% | no |
| TM | +2.28% | no |
| GOOGL | +2.19% | no |
| NKE | +2.16% | no |
| MA | +2.00% | no |
| LLY | +1.93% | no |
| F | +1.91% | no |
| SONY | +1.88% | no |
| VZ | +1.84% | no |
| AZN | +1.67% | no |
| COST | +1.58% | no |
| XLF | +1.27% | no |
| WMT | +1.22% | no |
| V | +1.12% | no |
| MSFT | +1.09% | no |
| T | +0.98% | no |
| AAPL | +0.94% | no |
| CSCO | +0.88% | no |
| MCD | +0.87% | no |
| MRK | +0.81% | no |
| BAC | +0.79% | no |
| ROKU | +0.69% | no |
| GE | +0.55% | no |
| PANW | +0.53% | no |
| PBR | +0.39% | no |
| AXP | +0.37% | no |
| JPM | +0.31% | no |
| JNJ | +0.29% | no |
| NVDA | +0.25% | **sì** (SELL, non-mover) |
| SPY | +0.24% | no |
| PG | +0.17% | no |
| BABA | +0.17% | no |
| IWM | +0.16% | no |
| ORCL | +0.05% | no |
| META | -0.08% | no |
| SHEL | -0.20% | no |
| AMZN | -0.23% | no |
| RIO | -0.34% | no |
| BIDU | -0.35% | no |
| DB | -0.39% | no |
| RDDT | -0.44% | no |
| WFC | -0.46% | no |
| C | -0.47% | no |
| SBUX | -0.53% | no |
| VALE | -0.54% | no |
| TSLA | -0.58% | no |
| AVGO | -0.60% | no |
| TXN | -0.84% | no |
| SNOW | -0.94% | no |
| UBS | -0.97% | no |
| QQQ | -0.97% | **sì** (SELL+re-BUY, non-mover) |
| XOM | -1.12% | no |
| CVX | -1.27% | no |
| XLE | -1.35% | no |
| MS | -1.39% | no |
| GS | -1.42% | no |
| BP | -1.51% | no |
| TSM | -1.70% | no |
| XLK | -1.84% | no |
| HOOD | -3.02% | no |
| CAT | -3.71% | no |
| NOK | -3.77% | no |
| QCOM | -4.21% | no |
| ASML | -4.37% | no |
| SOXX | -4.80% | **sì** |
| INTC | -5.86% | no |
| PLTR | -6.08% | no |
| WDC | -6.91% | no |
| MRVL | -7.77% | no |
| AMAT | -7.82% | no |
| ARM | -8.11% | **sì** |
| AMD | -8.15% | no |
| DELL | -8.15% | no |
| MU | -8.85% | **sì** |

(Tutti i 96 simboli hanno barre disponibili per entrambe le date; nessun dato mancante.)

## 3. Tabella dei miss classificati (21 mover non catturati, |ret|≥3%)

| Simbolo | Return % | Categoria | Evidenza |
|---|---:|---|---|
| CMCSA | +6.10% | NO_NEWS | 0 righe `news_log` il 07-28 |
| IBM | +5.21% | NO_NEWS | 0 righe `news_log` |
| SAP | +4.77% | NO_NEWS | 0 righe `news_log` |
| GM | +3.75% | NO_NEWS | 0 righe `news_log` |
| ERIC | +3.10% | NO_NEWS | 0 righe `news_log` |
| BRK.B | +3.06% | NO_NEWS | 0 righe `news_log` |
| QCOM | -4.21% | NO_NEWS | 0 righe `news_log` |
| ASML | -4.37% | NO_NEWS | 0 righe `news_log` |
| DELL | -8.15% | NO_NEWS | 0 righe `news_log` |
| INFY | +5.56% | THIN_NEUTRAL | 3 articoli; ensemble score 0.044→0.0 (conf 0.2-0.325), sotto soglia 0.30; unico segnale forte (0.18) era fallback, escluso da #108 |
| ADBE | +4.81% | THIN_NEUTRAL | 1 articolo; ensemble score +0.038 (conf 0.3), correttamente sotto soglia. **Anomalia**: 0 righe `execution_decisions` per l'intera giornata nonostante segnale non-fallback — a differenza di AMAT/CAT/NOK con score comparabile, regolarmente loggati SKIP_THRESHOLD. Non spiegato da #108 (non fallback) né dal filtro long-only (score positivo). Possibile gap di logging, non approfondito oltre — segnalo, non diagnostico. |
| CAT | -3.71% | THIN_NEUTRAL | 1 articolo; ensemble score +0.015 (conf 0.2, molto bassa) — segno debolmente sbagliato ma magnitudine trascurabile; loggato SKIP_THRESHOLD |
| NOK | -3.77% | THIN_NEUTRAL (segno misto) | ensemble +0.096 alle 16:30 (segno sbagliato, debole); poi single fallback -0.36 alle 19:01 (segno corretto ma tardivo, escluso da #108) |
| INTC | -5.86% | THIN_NEUTRAL | ensemble oscilla -0.11→+0.02 (conf 0.3), 1 SKIP_STALE su segnale vecchio 91h; nessun segnale ensemble supera 0.30 |
| WDC | -6.91% | THIN_NEUTRAL | ensemble -0.24 (conf 0.5), segno corretto, il più vicino alla soglia (0.30) tra tutti i miss — loggato SKIP_THRESHOLD "0.240 < 0.300" |
| AMAT | -7.82% | THIN_NEUTRAL | ensemble -0.038 (conf 0.275), molto diluito; unico segnale forte (-0.18) era single-model fallback, escluso da #108 |
| AMD | -8.15% | THIN_NEUTRAL (ensemble divergence) | 18 segnali nel giorno: ensemble oscilla -0.15↔+0.08 (sempre <0.30 in valore assoluto), single fallback oscilla -0.20↔**+0.64** — forte disaccordo tra modelli, coerente con il collo di bottiglia già noto ("Ensemble Divergence Order Drought" in memoria) |
| NOW | +4.79% | FILTERED (by design, #108) | unico segnale il 07-28: single-model fallback, score +0.24 — escluso dal ranking BUY dalla regola #108 (esclusione segnali fallback) prima ancora del gate di soglia |
| HOOD | -3.02% | FILTERED (by design, #108) + thin | unico segnale: single fallback, score -0.08 (debole comunque) |
| PLTR | -6.08% | FILTERED (by design, #108) + thin | unico segnale: single fallback, score 0.0 (neutro comunque) |
| MRVL | -7.77% | FILTERED (by design, long-only ranker) | ensemble reale (non-fallback) score -0.32 (conf 0.65) alle 17:03 — magnitudine e segno corretti, ma S4 è long-only: `ranking.py` scarta ogni `effective_strength <= 0` prima del ranking. Nessuna posizione aperta → nessun SELL possibile. Nota: questo è un limite architetturale esplicito (S4 non shorta), non un bug — ma comporta che una perdita del -7.8% con segnale coerente e ben sopra soglia non produce nessuna riga in `execution_decisions` (silenzioso by design). |

## 4. Titoli catturati: esito

| Simbolo | Strategia | Entry → Exit | Net P&L | Exit reason | Nota |
|---|---|---|---:|---|---|
| BA | S4 | BUY 14:07 @ 220.35 (posizione aperta a fine giornata) | n/d (open) | — | Entry avvenuta ~37 min dopo l'apertura, quando il prezzo (220.35) era già quasi al livello di chiusura giornaliera (221.56) — la maggior parte del movimento era già avvenuta prima dell'ingresso. Segnale ensemble forte (0.52, conf 0.775) alle 14:01 ha guidato l'entry. |
| CRM | S4 | BUY 07-27 19:07 @ 176.09 → SELL 07-28 14:22 @ 181.51 | **+$37.57** | portfolio_sell | Posizione aperta il giorno prima e chiusa alla chiusura del 07-28 (181.51 ≈ close 181.50) — ha catturato quasi l'intero +4.55% del giorno. Miglior esito tra i catturati. |
| ARM | S1 | BUY 07-14 @ 282.48 → SELL 07-28 14:22 @ 243.08 | **-$8.29** | portfolio_sell | Posizione momentum tenuta 14 giorni, lato sbagliato del rout semis; uscita a metà giornata (perdita contenuta rispetto al -8.11% di giornata, ma comunque una posizione long su un titolo in caduta). |
| SOXX | S1 | BUY 07-16 @ 526.63 → SELL 07-28 14:37 @ 485.48 (sentiment_reversal) → **re-BUY** 07-28 17:22 @ 494.14 | **-$47.72** (sulla gamba chiusa) | sentiment_reversal | Uscita per reversal a metà mattina, poi ri-acquisto lo stesso giorno a prezzo più basso — pattern di churn coerente con quanto già documentato (loop S1↔S4). |
| MU | S1 | BUY 07-21 @ 975.96 → SELL 07-28 17:07 @ 822.37 (sentiment_reversal) → **re-BUY** 07-28 19:07 @ 827.12 | **-$57.34** (sulla gamba chiusa) | sentiment_reversal | Stesso pattern di SOXX: posizione momentum liquidata durante il crollo, poi rientro lo stesso pomeriggio a prezzo leggermente più basso. |

Nota di contesto (non mover, sotto soglia 3%): **QQQ** (-0.97%) e **NVDA** (+0.25%) sono stati anch'essi scambiati lo stesso giorno (QQQ con lo stesso pattern sell-reversal + re-buy di SOXX/MU; NVDA venduta in perdita -$18.56) — riportati solo per completezza del quadro di trading, non sono mover e non entrano nella classificazione dei miss.

## 5. Pattern osservato

**Rotazione settoriale netta, non rumore diffuso**: 11 dei 15 mover negativi (QCOM, ASML, SOXX, INTC, WDC, MRVL, AMAT, ARM, AMD, DELL, MU) appartengono al bucket `semis` del sector map in `config/trading.yaml` — un sell-off quasi puro del comparto semiconduttori/AI-hardware. Sul lato opposto, 6 degli 11 mover positivi (INFY, IBM, ADBE, NOW, SAP, CRM) appartengono al bucket `tech` (enterprise software / IT services), con BA (industrials) e CMCSA (media) a completare il quadro. La lettura più naturale è una rotazione dai titoli semis verso software enterprise/IT services e alcuni industrial/media — compatibile con una giornata di post-market/pre-market di risultati trimestrali di Q2 nel comparto semis (in linea con fine luglio come finestra tipica di earnings season), ma questo report non ha verificato calendari di earnings specifici — resta un'inferenza dal solo pattern dei prezzi e dal sector map, non un fatto confermato.

## 6. Confronto con report precedenti

Coerenza con pattern già noti in report precedenti (`docs/ALPHA_MISS_REPORT_2026-07-24.md`, `2026-07-27.md`):
- **THIN_NEUTRAL da divergenza ensemble su semis/AI-hardware** ricorre (AMD in particolare, con lo stesso pattern "ensemble quasi piatto, single-model fallback che oscilla violentemente") — coerente con il problema strutturale già tracciato in memoria come "Ensemble Divergence Order Drought" (fallback 70-86% del tempo dal GLM-5.2 swap del 29/06).
- **Il pattern di churn S1 (sell via sentiment_reversal + re-buy stesso giorno a prezzo più basso)** osservato su SOXX, MU e QQQ oggi è lo stesso meccanismo già documentato nella memoria di sessione ("loop reversal S1↔S4", issue storiche #67/#68) — non è nuovo, ma si ripresenta puntualmente nei giorni di forte movimento direzionale.
- Non ho letto in dettaglio il contenuto completo degli altri report `ALPHA_MISS_REPORT_*` precedenti in questa sessione (fuori scope del compito assegnato) — questo confronto si basa sulla memoria di sessione accumulata, non su una rilettura sistematica; se serve un confronto puntuale riga-per-riga andrebbe fatto come task separato.

## 7. Nota su FILTERED vs bug

- **NOW, HOOD, PLTR**: l'esclusione è chiaramente **by design** — regola #108 (`_filter_fallback_signals`, commentata con riferimento esplicito all'incidente SPCX del 2026-07-01), documentata e intenzionale. Non richiede azione.
- **MRVL**: l'esclusione è chiaramente **by design** — il ranker S4 è long-only (`ranking.py`, `_filter_and_deduplicate`, `if strength <= 0: continue`), documentato come scelta architetturale, non un bug.
- **ADBE**: qui la causa **non è chiaramente spiegata** dalle regole note (non fallback, score positivo, non dovrebbe essere escluso da nessuno dei due meccanismi sopra) eppure non produce nessuna riga in `execution_decisions` per l'intera giornata, a differenza di segnali di magnitudine comparabile che invece vengono regolarmente loggati come `SKIP_THRESHOLD`. Non ho approfondito oltre (fuori scope di questo report puntuale) — segnalo che **potrebbe essere un gap di logging/pipeline**, non un limite noto. La decisione se aprire una issue è dell'operatore.
