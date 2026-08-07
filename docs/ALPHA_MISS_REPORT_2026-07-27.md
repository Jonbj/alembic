# Alpha Miss Report — 2026-07-27 (lunedì)

Ambito: 96 simboli di `config/trading.yaml` → `symbols.watchlist`. Rendimento = close 2026-07-27
vs close del giorno di trading precedente (venerdì 2026-07-24, il weekend 07-25/07-26 non ha barre).
Fonte prezzi: Alpaca `StockBarsRequest`, timeframe daily, feed IEX. Tutti i 96 simboli hanno barre
disponibili per entrambe le date — nessun gap di dati sui prezzi.

## 1. Executive summary

- Soglia mover: **|return| ≥ 3%** (simmetrica, long e short side). Motivazione: è il punto in cui il
  rendimento giornaliero supera chiaramente il rumore tipico intraday dei nomi in watchlist (la
  maggioranza dei simboli quel giorno sta in una banda ±2.5%); sotto soglia diventa difficile
  distinguere "mossa" da "rumore".
- **19 mover rilevanti** (12 al rialzo, 7 al ribasso).
- **5 catturati** (NOW, CRM, ORCL, MMM, NVDA), **14 mancati**.
- Causa prevalente dei miss: **NO_NEWS** (7/14, 50%) — gap puro di copertura dati, nessun articolo
  in `news_log` per quel simbolo quel giorno. Segue **THIN_NEUTRAL** (4/14: SONY, INFY, AMD, WDC —
  news presenti ma generiche/macro, non specifiche al titolo, segnale vicino a zero). **WRONG_SIGN**
  puro un caso (RDDT). **2 casi anomali** (ERIC, AMAT): un segnale è stato generato ma non ha mai
  raggiunto `execution_decisions` — pattern distinto, descritto in dettaglio in §3 e §7.
- Nessun caso di FILTERED classico (segnale sopra soglia scartato da ranking/breadth/hysteresis).
- Pattern del giorno: rotazione **software/SaaS enterprise (su) vs semiconduttori+energy (giù)** —
  vedi §5.

## 2. Tabella completa rendimenti (96/96 simboli)

| Simbolo | Return % | Catturato |
|---|---|---|
| PLTR | +6.97% | No |
| NOW | +6.84% | Sì |
| SAP | +6.83% | No |
| RDDT | +6.22% | No |
| SONY | +6.19% | No |
| CRM | +6.07% | Sì |
| INFY | +5.58% | No |
| ADBE | +5.58% | No |
| GM | +5.34% | No |
| ORCL | +4.24% | Sì |
| ERIC | +3.70% | No |
| MMM | +3.22% | Sì |
| AXP | +2.82% | Sì |
| TM | +2.59% | No |
| BABA | +2.55% | No |
| JD | +2.47% | No |
| ARM | +2.43% | No |
| DB | +2.41% | No |
| F | +2.30% | No |
| MA | +2.28% | No |
| CMCSA | +2.24% | No |
| MCD | +2.24% | No |
| GE | +2.24% | No |
| NOK | +2.21% | No |
| WMT | +2.08% | No |
| GOOGL | +2.08% | No |
| VZ | +2.01% | Sì |
| MSFT | +1.92% | No |
| V | +1.87% | No |
| DIS | +1.86% | Sì |
| NVO | +1.85% | No |
| QCOM | +1.75% | No |
| SNOW | +1.74% | No |
| COST | +1.73% | No |
| UBS | +1.55% | No |
| NKE | +1.25% | No |
| T | +1.22% | No |
| AAPL | +1.16% | No |
| XLF | +1.02% | Sì |
| WFC | +1.01% | No |
| JNJ | +0.94% | No |
| BA | +0.94% | No |
| HD | +0.91% | No |
| IBM | +0.90% | No |
| JPM | +0.86% | No |
| PG | +0.85% | No |
| RIO | +0.84% | No |
| HOOD | +0.77% | No |
| ROKU | +0.69% | No |
| C | +0.67% | No |
| IWM | +0.59% | No |
| XLV | +0.50% | No |
| AZN | +0.49% | No |
| PFE | +0.45% | No |
| BRK.B | +0.44% | No |
| NFLX | +0.43% | No |
| AVGO | +0.40% | No |
| SBUX | +0.39% | No |
| CSCO | +0.38% | No |
| BAC | +0.19% | No |
| LLY | +0.11% | No |
| MS | +0.01% | No |
| SPY | -0.01% | No |
| BIDU | -0.07% | No |
| VALE | -0.07% | No |
| TXN | -0.11% | No |
| META | -0.24% | No |
| MRK | -0.25% | No |
| AMZN | -0.29% | No |
| QQQ | -0.32% | No |
| UNH | -0.74% | No |
| INTC | -0.77% | No |
| XLK | -0.93% | No |
| ABBV | -0.93% | No |
| TSLA | -1.17% | No |
| TSM | -1.18% | No |
| GS | -1.25% | No |
| XOM | -1.29% | No |
| SPCX | -1.37% | No |
| TMUS | -1.57% | No |
| CAT | -1.79% | No |
| PANW | -2.06% | No |
| XLE | -2.07% | No |
| SOXX | -2.16% | No |
| SHEL | -2.27% | No |
| MU | -2.29% | No |
| DELL | -2.41% | No |
| CVX | -2.45% | No |
| MRVL | -2.69% | No |
| BP | -3.40% | No |
| AMAT | -3.73% | No |
| PBR | -4.05% | No |
| WDC | -4.22% | No |
| NVDA | -5.08% | Sì |
| AMD | -5.20% | No |
| ASML | -5.89% | No |

"Catturato" = Alembic ha aperto o chiuso un trade su quel simbolo il 2026-07-27 (indipendentemente
dal fatto che sia o meno un mover ≥3%). Trade attivi quel giorno anche su AXP, VZ, XLF, DIS — nessuno
di questi è un mover rilevante (tutti <3%), riportati per completezza dell'incrocio.

### Cadenza portfolio-cycle

24 cicli il 2026-07-27, dalle 14:07 alle 19:52 UTC, nessun gap interno >16 min (cadenza attesa 15
min rispettata). La finestra 13:30–14:07 UTC (i primi ~37 min di mercato) non ha cicli, ma è lo
stesso pattern esatto osservato il 07-24 (24 cicli, 14:07→19:52) — non è un'anomalia del giorno, è
la finestra operativa standard.

## 3. Tabella dei miss classificati

| Simbolo | Return % | Categoria | Evidenza |
|---|---|---|---|
| PLTR | +6.97% | NO_NEWS | 0 righe `news_log`, 0 `sentiment_signals`, 0 `execution_decisions` il 07-27. |
| SAP | +6.83% | NO_NEWS | 0 righe `news_log`, 0 `sentiment_signals`, 0 `execution_decisions` il 07-27. |
| RDDT | +6.22% | WRONG_SIGN | 1 articolo, specifico e on-topic: *"Reddit Stock Climbs Monday: What's Driving the Pre-Earnings Rally?"* (alpaca_benzinga, 16:46 UTC) — parla esplicitamente del rally in corso. Il modello lo ha comunque scorato **-0.095** (conf 0.475, ensemble glm-5.2+gpt-oss). Segno opposto al prezzo su un articolo che descrive il rally stesso; sotto soglia (0.30) comunque. |
| SONY | +6.19% | THIN_NEUTRAL | 1 articolo, generico/macro: *"Key Events This Busy Week: FOMC, PCE, GDP, War On/War Off... And Earnings Galore"* — nessun contenuto specifico su SONY. Score -0.030, confidence 0.20: segnale sostanzialmente rumore. |
| INFY | +5.58% | THIN_NEUTRAL | 7 articoli, **tutti** roundup del mercato indiano (Sensex/Nifty, flussi FII/DII) — zero contenuto specifico Infosys. Score ensemble sempre ≤0.038 (soglia 0.30), skip ripetuti "score 0.038 < feedback threshold 0.300". |
| ADBE | +5.58% | NO_NEWS | 0 righe `news_log`, 0 `sentiment_signals`, 0 `execution_decisions` il 07-27. **Stesso simbolo NO_NEWS anche nel report del 07-24** (vedi §6). |
| GM | +5.34% | NO_NEWS | 0 righe `news_log`, 0 `sentiment_signals`, 0 `execution_decisions` il 07-27. |
| ERIC | +3.70% | NO_NEWS (con segnale spurio) | Il vero catalyst del +3.70% non è mai entrato in `news_log`. L'unico articolo ingerito è un comunicato studio-legale generico: *"Bronstein, Gewirtz & Grossman, LLC Is Investigating Telefonaktiebolaget..."* (indagine class-action boilerplate, non una notizia sul business). Da questo è uscito un segnale single-model fallback (-0.08, conf 0.4) che non ha mai raggiunto `execution_decisions` — vedi nota pipeline in §7. |
| ASML | -5.89% | NO_NEWS | 0 righe `news_log`, 0 `sentiment_signals`, 0 `execution_decisions` il 07-27. |
| AMD | -5.20% | THIN_NEUTRAL | 4 articoli, tutti macro/roundup di mercato (S&P/Nasdaq futures, prezzo petrolio, un pezzo che nomina AMD solo di striscio insieme a Nvidia/SK Hynix) — nessun catalyst AMD-specifico. Ensemble converge vicino a zero (0.008–0.014) nonostante un'unica lettura single-model a 0.39 (fallback, non ensemble). Skip ripetuti sotto soglia 0.300. |
| WDC | -4.22% | THIN_NEUTRAL | 1 articolo specifico e negativo: *"EXCLUSIVE: China Is Coming For SanDisk—But Not Yet For Micron's Memory Crown"* — segno corretto (-0.045, ensemble), ma magnitudine troppo bassa (score in decisioni 0.036 < soglia 0.30). Segnale nella direzione giusta, semplicemente troppo debole. |
| PBR | -4.05% | NO_NEWS | 0 righe `news_log`, 0 `sentiment_signals`, 0 `execution_decisions` il 07-27. |
| AMAT | -3.73% | Pipeline gap (segnale generato, mai in execution_decisions) | 1 articolo specifico e a tono rialzista: *"Applied Materials Stock Keeps Winning Upgrades: Is Michael Burry Dead Wrong to Short This Semiconductor"* → segnale single-model fallback 0.36 (conf 0.6) — nessun ensemble calcolato quel giorno, e questo segnale non è mai comparso in `execution_decisions`. Nota: anche se fosse arrivato a decisione, sarebbe stato comunque disallineato rispetto al calo -3.73% (probabile trascinamento settoriale semicap: ASML -5.89%, AMD -5.20%, MRVL -2.69% tutti giù lo stesso giorno). |
| BP | -3.40% | NO_NEWS | 0 righe `news_log`, 0 `sentiment_signals`, 0 `execution_decisions` il 07-27. |

**Conteggio cause:** NO_NEWS 7, THIN_NEUTRAL 4, WRONG_SIGN 1, pipeline gap (ERIC/AMAT) 2.
Nessun caso FILTERED classico (nessun segnale sopra soglia scartato da ranking/breadth/hysteresis
osservato quel giorno).

## 4. Titoli catturati: esito

| Simbolo | Return % | Trade | Esito |
|---|---|---|---|
| NOW | +6.84% | Posizione aperta il 07-24, chiusa il 07-27 alle 14:22 UTC. Uscita = `portfolio_sell` motivata **"no S4 signal found in DB"** (rebalance forzato a peso zero, non un segnale di uscita). Prezzo entrata 98.20 (07-24) → uscita 102.88. | **Profitto +$58.07 netto.** Ma l'uscita è avvenuta 14:22 UTC (poco dopo l'apertura), mentre il close di giornata è 105.53 — Alembic ha lasciato sul tavolo la parte finale del rally (102.88→105.53, altri ~2.6 punti) perché il segnale S4 era scaduto/assente, non per una decisione attiva. |
| CRM | +6.07% | BUY alle 19:07 UTC (a ridosso della chiusura, score +0.560, "$1.6B VA contract"). Entrata 176.09. Posizione **ancora aperta** a fine giornata. | Nessun P&L realizzato. Entrata avvenuta *sopra* il close di giornata (173.55) — timing subottimale, il titolo si era già ritracciato quando Alembic è entrato tardi nella sessione. |
| ORCL | +4.24% | BUY 16:52 UTC (score +0.588, "$7B Pentagon contract"), SELL 18:37 UTC per whipsaw (score sceso a 0.049). Entrata 120.16 → uscita 119.47. | **Perdita -$7.86 netta.** Il titolo ha chiuso la giornata in rialzo (+4.24%, close 119.88) ma Alembic è stato espulso dalla posizione dal meccanismo whipsaw prima della chiusura, quindi in perdita su una giornata che a livello di prezzo era vincente. |
| MMM | +3.22% | BUY 14:07 UTC via **S1 momentum** (non sentiment), score 0.012, peso 1.2%. Entrata 177.74. Posizione ancora aperta. | Marked-to-close ~+0.25% (close 178.18). Cattura pulita via momentum, indipendente dalla pipeline news/sentiment. |
| NVDA | -5.08% | Round-trip 1: BUY 14:22 (score +0.345, "financing OpenAI... GPU demand") @200.38 → SELL 16:07 per whipsaw (score sceso a 0) @197.93. Round-trip 2: BUY 18:22 (score +0.368, "$1.5B Blackwell contract") @196.35, posizione ancora aperta a fine giornata. | **Perdita -$15.49 sul primo round-trip.** Il titolo ha chiuso la giornata a -5.08% (close 196.56) nonostante notizie aziendali specifiche genuinamente positive (due contratti distinti) — probabile trascinamento del comparto semiconduttori (ASML -5.89%, AMD -5.20%, AMAT -3.73%, MU -2.29% tutti giù lo stesso giorno). La seconda posizione (entrata 196.35) chiude la giornata sostanzialmente flat (close 196.56), non ancora un miss ma nemmeno una vittoria — esito a determinarsi nei giorni successivi. |

## 5. Pattern osservato

Rotazione chiara **enterprise software/SaaS (su) vs semiconduttori + energy (giù)**:

- **Rialzo:** 6 dei 12 mover positivi sono enterprise software/SaaS — NOW, SAP, CRM, ADBE, ORCL,
  INFY (quest'ultimo IT services, stesso bucket largo). Aggiungendo PLTR (software/data), RDDT
  (internet/tech) e SONY (elettronica), **10 dei 12 mover positivi sono tech/software** in senso
  lato. Solo GM (auto) e MMM (industriale) sono fuori da questo bucket.
- **Ribasso:** 5 dei 7 mover negativi sono semiconduttori/semicap — ASML, AMD, NVDA, WDC, AMAT.
  I restanti 2 sono energy — PBR, BP.

Lettura: non è "mercato generico su/giù", è una rotazione **dentro il tech stesso** (software su,
hardware/semis giù) più una gamba di debolezza energy. Il caso NVDA (notizie aziendali specifiche
positive ma titolo giù) è coerente con questa lettura: il trascinamento settoriale semicap ha
dominato il newsflow idiosincratico positivo.

## 6. Confronto con il report precedente (2026-07-24)

- **ADBE è NO_NEWS in entrambi i report** (07-24: +6.10% NO_NEWS; 07-27: +5.58% NO_NEWS) — gap di
  copertura ricorrente specifico su questo simbolo, non un caso isolato. Vale la pena tenerlo
  d'occhio nei prossimi report prima di trarre conclusioni più forti (n=2 al momento).
- **SAP mancato in entrambi i report**, ma con causa diversa: THIN_NEUTRAL il 07-24 (+9.30%, un
  articolo generico da roundup terzi), NO_NEWS il 07-27 (+6.83%, zero articoli). Stesso simbolo,
  due meccanismi di miss distinti — indica che il problema con SAP è la copertura news in generale
  (quando c'è, è irrilevante; quando serve, non c'è), non un singolo bug puntuale.
- **CRM** era NO_NEWS il 07-24, oggi è CAUGHT (anche se con timing tardivo) — nessuna conclusione,
  solo a titolo di continuità del simbolo tra i due report.
- Il report del 07-24 non aveva nessun caso "pipeline gap" (segnale generato ma mai arrivato a
  `execution_decisions`); questo report ne ha 2 (ERIC, AMAT). Con solo due osservazioni non è
  possibile dire se sia un pattern ricorrente o un'anomalia isolata del 07-27 — da verificare nei
  prossimi report.

Non vado oltre questi tre confronti puntuali: con solo due report disponibili non è possibile
distinguere pattern strutturali da coincidenze.

## 7. Nota tecnica — non è un fix, è un'osservazione per l'operatore

Sia ERIC che AMAT hanno prodotto un **unico segnale single-model fallback** (`fallback_used=true`,
`model_id="single:gpt-oss:20b-cloud"`) senza alcun corrispondente segnale ensemble calcolato quel
giorno, e in entrambi i casi **quel segnale non è mai comparso in `execution_decisions`** — non
nemmeno come `SKIP_THRESHOLD`. Questo è diverso da AMD (che ha sia letture fallback sia letture
ensemble, e le letture ensemble *sono* arrivate a `execution_decisions` come `SKIP_THRESHOLD`) e da
RDDT/SONY/WDC (dove l'unico segnale del giorno era già una lettura ensemble, ed è arrivato
regolarmente a decisione). Il pattern osservato: **quando il calcolo ensemble non produce affatto
un risultato quel giorno per un simbolo (fallback totale), il segnale fallback risultante non entra
nel loop decisionale S4** — a differenza di quando l'ensemble fallisce solo su *alcune* letture nella
giornata (come AMD), dove le letture ensemble successive vengono comunque valutate.

Con solo 2 osservazioni su un giorno non è possibile dire con certezza se questo sia un
comportamento *intenzionale* (i segnali fallback-puro sono scartati by design per bassa affidabilità)
o un **gap della pipeline non intenzionale**. Sembra plausibile che sia un bug — ma la decisione se
verificarlo nel codice e se aprire una issue è dell'operatore, non mia in questa sessione read-only.

Non emergono invece casi di FILTERED classico (segnale sopra soglia scartato da ranking/breadth/
hysteresis) nei dati del 07-27.
