# Alpha Miss Report — 2026-08-26

Fonte numerica primaria: `docs/evidence/dossier/2026-08-26.json` (deterministico, Alpaca SIP
`adjustment=all`). Query dirette via `docker exec alembic-postgres-1 psql` per `trades`,
`sentiment_signals`, `execution_decisions`, `news_log`, `s4_candidate_population`. Equity e
posizioni da Alpaca Trading API. Nessun ricalcolo dei numeri già presenti nel dossier.

> **Nota di provenienza — il dossier non si è generato da solo, per la seconda seduta consecutiva.**
> `uv run python scripts/alpha_miner_dossier.py 2026-08-26` è fallito con
> `ERROR: column reference "decision_at" is ambiguous` → `dossier scritti: 0`, esattamente come il
> 2026-08-25. Causa invariata in `_s4_entry_intents` (`scripts/alpha_miner_dossier.py:835-836`):
> `WHERE`/`ORDER BY` usano `decision_at` non qualificato mentre il join espone quella colonna sia in
> `s4_candidate_population` sia in `s4_intent_events` (entrambe verificate in `information_schema`).
> Il difetto è stato introdotto da `d5dacc3` (PR #354, 2026-08-25 13:12) — `git log -S "LEFT JOIN
> s4_intent_events disposition"` restituisce quel solo commit. Come il 08-25, il dossier di oggi è
> stato prodotto da una **copia usa-e-getta** con le sole due referenze qualificate
> (`intent.decision_at`), poi rimossa; **il repo non è stato modificato** (`git status scripts/`
> pulito sul file). Vedi §7 [F-044].

## 1. Executive summary

8 dei 96 simboli watchlist si sono mossi ≥3% (`soglia_mover=0.03`), **3 al rialzo contro 5 al
ribasso**, dispersione σ=1.52% — la più bassa della serie recente — su indici fermi (SPY +0.02%,
QQQ +0.09%), regime BULL, VIX 15.45. **3 mover su 8 erano già a libro**: WDC +4.02% (S4, dal 07-21),
ARM +3.93% (S1, dal 08-03) e LLY −3.59% (S1, dal 07-15). **5 miss, tutti sul lato ribassista tranne
uno**: DB +3.05% (NO_NEWS — zero articoli, 24 intent S4 su un segnale del 08-25 già scaduto),
RDDT −4.36% ed ERIC −3.08% (NO_NEWS puri), HOOD −3.17% (THIN_NEUTRAL — 2 articoli, nessuno
issuer-specific, score max +0.12) e NVO −3.02% (OUT_OF_STRATEGY_SCOPE — segnale −0.5533 sopra gate e
col segno giusto, ma book long-only). **Causa prevalente: NO_NEWS (3/5)**, con 45/96 simboli a zero
righe in `news_log` ed effective-timely coverage 24/96 = 25.0%. L'unico miss azionabile (DB, rialzo,
non detenuto) aveva **opportunità accessibile negativa (−$7.90)**: l'intero +3.05% era gap notturno,
DB ha aperto a 40.53 e chiuso a 40.23. Il fatto migliore della giornata sono le **due uscite S4**:
NVDA e META vendute alle 10:22 e 11:07 ET hanno evitato −$9.21 e −$39.65 di drift successivo,
**+$48.87 di effetto attivo** contro un book passivo da +$6.85. 24 cicli portfolio, cadenza 15 min
esatta, nessun gap. Il reperto strutturale del giorno non è un miss: **su MRVL, NOK e WDC la tabella
`trades` porta quantità che al broker non esistono più** — $55.17 di MTM fantasma, il 91% del
movimento di book calcolato (§7 [F-048]).


## 2. Tabella rendimenti completa (96 simboli)

Fonte: dossier, Alpaca SIP `adjustment=all`, close vs close precedente. Nessun simbolo senza barre
(`simboli_senza_dati: []`). In grassetto i mover ≥3%. "Articoli" = righe `news_log` del 2026-08-26.

| # | Simbolo | Settore | Ret % | A libro | Sleeve | Articoli |
|---|---------|---------|------:|:-------:|:------:|---------:|
| 1 | **WDC** | semis | +4.02 | sì | S4 | 1 |
| 2 | **ARM** | semis | +3.93 | sì | S1 | 0 |
| 3 | **DB** | financials | +3.05 | no | — | 0 |
| 4 | ORCL | tech | +2.84 | no | — | 2 |
| 5 | PLTR | tech | +2.76 | no | — | 0 |
| 6 | DELL | semis | +2.73 | sì | S1 | 1 |
| 7 | SBUX | consumer | +2.58 | sì | S1 | 0 |
| 8 | QCOM | semis | +1.97 | no | — | 0 |
| 9 | MRVL | semis | +1.97 | sì | S1 | 0 |
| 10 | GE | industrials | +1.39 | sì | S1 | 0 |
| 11 | CAT | industrials | +1.31 | sì | S1 | 0 |
| 12 | SPCX | etf_broad | +1.22 | no | — | 3 |
| 13 | AAPL | tech | +1.15 | sì | S1 | 2 |
| 14 | CSCO | tech | +1.13 | sì | S4 | 0 |
| 15 | UNH | healthcare | +1.11 | sì | n/d | 1 |
| 16 | META | tech | +1.07 | no | — | 6 |
| 17 | MSFT | tech | +0.95 | no | — | 4 |
| 18 | INTC | semis | +0.87 | no | — | 3 |
| 19 | TXN | semis | +0.66 | sì | S1 | 0 |
| 20 | GM | consumer | +0.61 | sì | S1 | 1 |
| 21 | XLK | tech | +0.61 | sì | S1 | 2 |
| 22 | XLE | energy | +0.60 | no | — | 2 |
| 23 | MU | semis | +0.58 | sì | S1 | 3 |
| 24 | NOK | telecom | +0.58 | sì | S1 | 1 |
| 25 | UBS | financials | +0.53 | sì | n/d | 0 |
| 26 | WFC | financials | +0.52 | no | — | 1 |
| 27 | BA | industrials | +0.48 | no | — | 0 |
| 28 | T | telecom | +0.39 | no | — | 0 |
| 29 | CMCSA | media | +0.37 | no | — | 0 |
| 30 | AMD | semis | +0.37 | sì | S1 | 2 |
| 31 | MMM | industrials | +0.35 | sì | S1 | 0 |
| 32 | BABA | tech | +0.33 | no | — | 1 |
| 33 | SONY | tech | +0.29 | no | — | 0 |
| 34 | SOXX | semis | +0.26 | sì | S1 | 2 |
| 35 | C | financials | +0.23 | sì | S1 | 0 |
| 36 | CVX | energy | +0.16 | sì | S1 | 0 |
| 37 | BRK.B | financials | +0.12 | no | — | 0 |
| 38 | QQQ | etf_broad | +0.09 | sì | S1 | 2 |
| 39 | ASML | semis | +0.08 | sì | S1 | 0 |
| 40 | TSM | semis | +0.07 | sì | S1 | 1 |
| 41 | AXP | financials | +0.06 | no | — | 1 |
| 42 | SPY | etf_broad | +0.02 | sì | n/d | 1 |
| 43 | CRM | tech | -0.03 | no | — | 2 |
| 44 | JPM | financials | -0.05 | sì | S1 | 1 |
| 45 | AMAT | semis | -0.06 | sì | S1 | 1 |
| 46 | V | financials | -0.06 | no | — | 1 |
| 47 | XLF | financials | -0.09 | sì | S1 | 1 |
| 48 | IWM | etf_broad | -0.10 | sì | S1 | 1 |
| 49 | VZ | telecom | -0.12 | no | — | 1 |
| 50 | MA | financials | -0.15 | no | — | 0 |
| 51 | ADBE | tech | -0.16 | no | — | 0 |
| 52 | PANW | tech | -0.17 | sì | S1 | 2 |
| 53 | BIDU | tech | -0.18 | no | — | 1 |
| 54 | PG | consumer | -0.28 | no | — | 1 |
| 55 | AMZN | tech | -0.30 | no | — | 3 |
| 56 | BAC | financials | -0.32 | sì | n/d | 1 |
| 57 | AVGO | semis | -0.32 | no | — | 2 |
| 58 | F | consumer | -0.36 | no | — | 0 |
| 59 | COST | consumer | -0.41 | no | — | 1 |
| 60 | MCD | consumer | -0.44 | no | — | 0 |
| 61 | PBR | energy | -0.50 | sì | n/d | 0 |
| 62 | SNOW | tech | -0.52 | sì | S1 | 0 |
| 63 | TM | consumer | -0.58 | no | — | 2 |
| 64 | ROKU | media | -0.73 | sì | n/d | 0 |
| 65 | BP | energy | -0.84 | no | — | 0 |
| 66 | HD | consumer | -0.90 | no | — | 0 |
| 67 | NFLX | media | -0.94 | no | — | 0 |
| 68 | NOW | tech | -0.94 | no | — | 2 |
| 69 | PFE | healthcare | -0.95 | no | — | 0 |
| 70 | WMT | consumer | -0.99 | no | — | 2 |
| 71 | XLV | healthcare | -1.00 | sì | S1 | 4 |
| 72 | ABBV | healthcare | -1.09 | sì | S1 | 0 |
| 73 | TMUS | telecom | -1.10 | no | — | 0 |
| 74 | VALE | materials | -1.11 | sì | S1 | 0 |
| 75 | JNJ | healthcare | -1.15 | sì | S1 | 0 |
| 76 | SHEL | energy | -1.20 | sì | S1 | 0 |
| 77 | MS | financials | -1.24 | sì | n/d | 2 |
| 78 | TSLA | consumer | -1.26 | no | — | 2 |
| 79 | GOOGL | tech | -1.43 | sì | n/d | 8 |
| 80 | DIS | media | -1.46 | no | — | 2 |
| 81 | XOM | energy | -1.53 | sì | S1 | 0 |
| 82 | NVDA | semis | -1.59 | no | — | 15 |
| 83 | GS | financials | -1.74 | sì | n/d | 3 |
| 84 | IBM | tech | -1.84 | no | — | 0 |
| 85 | RIO | materials | -1.98 | sì | n/d | 0 |
| 86 | AZN | healthcare | -2.00 | no | — | 0 |
| 87 | JD | tech | -2.01 | no | — | 0 |
| 88 | MRK | healthcare | -2.14 | sì | S1 | 1 |
| 89 | NKE | consumer | -2.25 | no | — | 2 |
| 90 | SAP | tech | -2.42 | no | — | 0 |
| 91 | INFY | tech | -2.83 | no | — | 0 |
| 92 | **NVO** | healthcare | -3.02 | no | — | 1 |
| 93 | **ERIC** | telecom | -3.08 | no | — | 0 |
| 94 | **HOOD** | financials | -3.17 | no | — | 2 |
| 95 | **LLY** | healthcare | -3.59 | sì | S1 | 4 |
| 96 | **RDDT** | media | -4.36 | no | — | 0 |

Riferimenti: SPY +0.02%, QQQ +0.09%, IWM −0.10%.

## 3. Tabella dei miss classificati

Soglia mover: **|return| ≥ 3%**, la soglia del dossier (`soglia_mover=0.03`), non ridefinita qui.
Motivazione: con σ cross-sectional a 1.52% un movimento del 3% è ≈2σ, cioè fuori dal rumore di
giornata, e la soglia resta confrontabile con tutti i report precedenti della serie. I "miss" sono i
5 mover non a libro; WDC, ARM e LLY erano detenuti e stanno in §4.

| Simbolo | Ret % | Categoria | Evidenza |
|---------|------:|-----------|----------|
| DB | +3.05 | **NO_NEWS** | Zero righe `news_log` il 08-26. 24 intent S4 nella giornata, tutti `SKIP_ENTRY_FRESHNESS`, costruiti su un segnale del **08-25 11:30** (`sentiment_signals` 8876, score **+0.0863**, `gdelt_gkg`/`org_lookup`, «TerraPay Teams Up With Deutsche Bank…»). Attribuzione corretta ma testo scorato = solo il titolo (`body_snippet` identico a `title`, 84 caratteri). Anche fresco il segnale sarebbe morto sul gate: +0.0863 contro 0.30. |
| RDDT | −4.36 | **NO_NEWS** | Zero righe `news_log`, zero segnali, zero intent S4. `catalyst=UNKNOWN`, `corporate_calendar=NOT_OBSERVED` con entrambe le fonti interrogate con successo (FMP earnings-calendar, Alpaca Corporate Actions). Residuo vs XLC −3.86%: idiosincratico e invisibile alla pipeline. Volume **sotto** la media (`volume_surprise` −0.60), quindi nemmeno la microstruttura lo avrebbe segnalato. |
| ERIC | −3.08 | **NO_NEWS** | Zero righe `news_log`, zero segnali, zero intent. `volume_surprise` +1.25 (unico mover con volume anomalo al rialzo), residuo vs XLC −2.58%. Telecom: settore con copertura news nulla oggi. |
| HOOD | −3.17 | **THIN_NEUTRAL** | 2 articoli, **nessuno issuer-specific**: «SHIB Joins XRP, Bitcoin on Japan's First New Crypto Exchange in 4 Years» (score +0.12, `relevance=UNKNOWN`) e «4 Financials Stocks With Whale Alerts In Today's Session» (score +0.0057, `attribution=FANOUT`, condiviso con GS). `max_score_own = null` — nessun punteggio nasce da un pezzo di cui HOOD sia il soggetto. Il dossier classifica `BELOW_GATE`; è thin, non un problema di soglia. Segno anche sbagliato (+0.12 su −3.17%), ma su magnitudine irrilevante. I 24 intent S4 portano invece lo score **−0.0098** del 08-25, cioè l'articolo di [F-046]. |
| NVO | −3.02 | **OUT_OF_STRATEGY_SCOPE** | Un solo articolo: «Boston Scientific Reports Global Disruption After Cybersecurity Incident» — **non parla di Novo Nordisk**, `n_ticker=1`, quindi non è fan-out ma attribuzione singola errata via `source_metadata`. Il segnale è **−0.5533** (fallback FinBERT), sopra gate e con il segno che si è poi rivelato giusto, ma per l'articolo sbagliato. 2 intent S4, entrambi `SKIP_FALLBACK`. Book long-only e titolo non detenuto → nessun ordine possibile: [F-040]. |

Conteggio: **NO_NEWS 3, THIN_NEUTRAL 1, WRONG_SIGN 0, FILTERED 0, OUT_OF_STRATEGY_SCOPE 1.**

Nessun miss classificato FILTERED. Vale la pena dirlo perché il volume di scarti è enorme e
potrebbe trarre in inganno: 1.518 intent S4 generati nella giornata, **zero tradabili**, ripartiti in
`SKIP_ENTRY_FRESHNESS` 695 (35 simboli), `SKIP_ENTRY_GATE` 312 (23), `SKIP_STALE` 280 (16),
`SKIP_FALLBACK` 122 (14), `SKIP_PYRAMIDING` 108 (6), `RANK_OUTSIDE_TOP_N` 1. Nessuno di questi
scarti riguarda però un mover non detenuto con segnale valido sopra soglia, che è la definizione di
FILTERED.

## 4. Titoli catturati: esito

| Simbolo | Ret % | Sleeve | Aperto dal | Esito 08-26 |
|---------|------:|:------:|-----------|-------------|
| WDC | +4.02 | S4 (trade 373) | 2026-07-21 | `passive_pnl` dossier **+$25.37** su nozionale $600 — **ma vedi §7 [F-048]: al broker la posizione è 0.335 azioni, non 2.981**. Il guadagno reale è ≈**$6.36**. In più 20 `SKIP_ENTRY_GATE` su un segnale fresco delle 11:00 ET (+0.0578) e 4 `SKIP_STALE` su uno del 08-24 (−0.0304): S4 non avrebbe potuto rinforzare comunque. |
| ARM | +3.93 | S1 (trade 641) | 2026-08-03 | **+$15.17** su nozionale $339. **Zero articoli, zero segnali, zero intent**: catturato interamente dal momentum di S1, non dalla pipeline news. È l'unico mover rialzista pienamente incassato. |
| LLY | −3.59 | S1 (trade 337) | 2026-07-15 | **−$30.76** su nozionale $851 — la peggiore posizione della giornata. 24 intent S4 su un segnale **del 08-24 13:00** (+0.3220, sopra gate) bloccati 17× `SKIP_PYRAMIDING` e 7× `SKIP_ENTRY_GATE`: il guard anti-pyramiding [F-031] ha **impedito di raddoppiare su un titolo in caduta**, risparmiando ≈$79 a size S4 standard. |

**Uscite della giornata (entrambe S4, entrambe corrette):**

| Trade | Simbolo | Uscita ET | Prezzo | Net P&L | Motivo | Drift post-uscita |
|-------|---------|-----------|-------:|--------:|--------|------------------:|
| 829 | NVDA | 10:22 | 210.69 | **−$18.73** | `portfolio_sell` | **−$9.21** (close 209.66) |
| 831 | META | 11:07 | 588.01 | **+$61.68** | `portfolio_sell` | **−$39.65** (close 576.14) |

Realizzato di giornata **+$42.95**, tutto S4, S1 a zero. L'effetto attivo delle due uscite vale
**+$48.87** contro un book passivo da **+$6.85**: senza di esse la seduta sarebbe stata negativa.
Su META in particolare l'uscita cade a 11:07 con il titolo a 588.01 dopo un'apertura a 590.31 e
prima di una chiusura a 576.14 — è la vendita migliore delle ultime sedute, e non per fortuna del
gate: entrambe le uscite nascono dallo stesso `portfolio_sell` a peso azzerato.

## 5. Pattern osservato

**Rotazione netta fuori dal farmaceutico/difensivo, dentro semiconduttori e hardware — con un fronte
GLP-1 particolarmente pulito.**

Medie di settore sulla watchlist (n = simboli):

| Settore | n | Media | Mediana |
|---------|--:|------:|--------:|
| semis | 15 | **+1.04%** | +0.58% |
| industrials | 4 | +0.88% | +0.89% |
| etf_broad | 4 | +0.31% | +0.06% |
| tech | 21 | −0.08% | −0.16% |
| financials | 14 | −0.16% | −0.06% |
| consumer | 11 | −0.39% | −0.44% |
| energy | 6 | −0.55% | −0.67% |
| telecom | 5 | −0.67% | −0.12% |
| media | 5 | −1.42% | −0.94% |
| healthcare | 9 | **−1.53%** | −1.15% |
| materials | 2 | −1.54% | −1.54% |

Lato forte compatto su storage/hardware: WDC +4.02%, ARM +3.93%, DELL +2.73%, QCOM +1.97%,
MRVL +1.97%, con SOXX +0.26% e XLK +0.61%. Lato debole quasi monotematico sul farmaceutico: 7 dei 9
healthcare in rosso — LLY −3.59%, NVO −3.02%, MRK −2.14%, AZN −2.00%, JNJ −1.15%, XLV −1.00%,
PFE −0.95% — e **LLY e NVO, la coppia GLP-1, si muovono insieme a −3.6/−3.0%**, il che rende il
movimento tematico e non idiosincratico su nessuno dei due.

Il catalizzatore macro è leggibile negli articoli scorati: «Nasdaq 100 Falls as Hot PCE Inflation
Stirs Rate-Hike Bets» e «Hotter PCE Inflation: 5 Defensive ETFs Investors Can Turn to as Rate-Cut
Hopes Fade». Un PCE più caldo del previsto penalizza i difensivi a duration lunga (pharma, staples,
utilities) e lascia correre l'AI-hardware, che oggi ha un catalizzatore proprio (gli utili Nvidia
attesi in serata, 9 articoli su quel tema). Coerente con SPY praticamente fermo: è rotazione a somma
quasi zero, non direzione di mercato — ed è esattamente ciò che la dispersione più bassa della serie
(σ 1.52%) descrive.

Fuori dal pattern: **RDDT −4.36%**, il mover più violento, non appartiene a nessuno dei due blocchi
(media, residuo vs XLC −3.86%, volume sotto media). Non ho evidenza per attribuirgli un tema:
catalizzatore non identificato. **DB +3.05%** è l'unico financial positivo di rilievo in un settore
piatto (XLF −0.09%), residuo +3.13%: anch'esso idiosincratico, e coerente col fatto che tutto il
movimento sia gap notturno.

## 6. Confronto con i giorni precedenti

Ho riletto i report 08-21, 08-24 e 08-25.

**(a) La terza inversione consecutiva sullo stesso gruppo di titoli, ora la quarta.** Il 08-24 i semi
crollavano (MU −5.83%, WDC −5.24%) e i difensivi salivano (UNH +2.22%, WMT +2.69%); il 08-25 si
invertiva (AMD +4.91%, WDC +3.53%, DELL +4.23%, pharma su con MRK +3.84% e NVO +3.71%); oggi i semi
tengono la direzione del 08-25 ma **il pharma si inverte violentemente** — MRK da +3.84% a −2.14%,
NVO da +3.71% a −3.02%, LLY in rosso di 3.6 punti. Il report 08-25 aveva già annotato «terza
inversione in quattro sedute». È un'osservazione sul mercato, non sul sistema, ma ha una conseguenza
diretta sulla misura: **le sleeve momentum stanno operando su un regime che inverte ogni 24-48 ore**,
e ogni statistica di performance a orizzonte giornaliero costruita su queste sedute va letta sapendolo.

**(b) La copertura news migliora per la prima volta dopo cinque sedute di peggioramento monotono.**
Simboli a zero righe: 40 (08-19) → 41 → 43 → 51 → 55 (08-25) → **45 oggi**. L'effective-timely
coverage risale da 17.7% a **25.0%** (24/96 ticker). Non chiamo una tendenza su un punto: il 08-25
era un massimo della serie e questo può essere semplice ritorno alla media. Va però registrato che il
peggioramento monotono si è interrotto.

**(c) HOOD è nel report per la terza seduta consecutiva, ogni volta per una ragione diversa.** Il
08-25 era il mover #1 (+8.17%) mancato perché l'unico articolo issuer-specific veniva scorato
−0.0098 (titolo mai passato al modello, [F-046]); oggi è mover al ribasso (−3.17%) e i suoi 24 intent
S4 portano **ancora quello stesso score −0.0098**, ereditato dal 08-25 e mai sostituito da un
articolo issuer-specific. Due sedute di seguito, cioè, la lettura del sistema su HOOD è governata da
un singolo campo `body_snippet` sbagliato. Non è un nuovo difetto: è la **persistenza** di [F-046]
oltre la giornata in cui è stato osservato, ed è la ragione per cui lo registro di nuovo.

**(d) Il guard anti-pyramiding smette di proteggere il book.** 08-24: cinque segnali sopra gate
bloccati, i cinque titoli chiudono in media −3.1% → risparmio ≈$340. 08-25: due segnali bloccati,
costo zero. Oggi: sei simboli bloccati, cinque dei quali chiudono in verde, e il netto diventa un
**costo di $47.91**. Due sedute su tre il difetto [F-031] aveva fatto risparmiare denaro; alla terza
inverte. Con n=3 e segni discordi non c'è nulla da concludere se non che il costo di questo difetto
è **il rendimento condizionale dei titoli già detenuti**, cioè una variabile che cambia segno con il
regime — e il regime, per il punto (a), inverte ogni 24-48 ore. Questo suggerisce che il difetto vada
misurato su un orizzonte lungo, non giornata per giornata.

## 7. Segnalazioni

Nessun fix proposto: siamo dentro il periodo di sola osservazione (`OBSERVATION_CHARTER.md`, minimo
40 sedute dal 2026-08-03). Dove una causa mi sembra un difetto e non un limite noto lo dico e mi
fermo lì; la decisione se aprire una issue è dell'operatore.

**[F-048] Sembra un difetto, ed è il reperto più importante della giornata — su tre simboli la
tabella `trades` porta quantità che al broker non esistono più, e ogni misura di book a valle è
sbagliata di conseguenza.** Confronto diretto fra `GET /v2/positions` e le righe `trades` con
`exit_time IS NULL`: stesso numero di posizioni (46 e 46), stesse chiavi, ma tre quantità divergono —
**MRVL 0.552 al broker contro 1.552 a DB**, **NOK 0.564 contro 41.564**, **WDC 0.335 contro 2.981**.
Non è un arrotondamento: su NOK il DB dichiara 74 volte la posizione reale. La storia ordini Alpaca
ricostruisce il caso WDC per intero — BUY 2.981065 il 07-21 (trade 373), poi SELL 1.580640 (07-21),
SELL 0.065727 (07-22) e **SELL 1 di tipo STOP** (07-27): totale uscito 2.646368, residuo 0.334697,
esattamente la posizione attuale. Su MRVL lo stesso schema con una `STOP SELL 1` del 07-20. Le
uscite parziali, **inclusi i fill degli stop protettivi, non sono mai state riscritte su `trades`**:
la riga resta aperta alla quantità d'ingresso originale. Le due `STOP SELL 1` sono la firma di
[F-022] (gli stop coprono solo la parte intera della posizione), ma [F-022] descrive la *copertura*
dello stop, non la mancata scrittura a valle del fill — sono due difetti in sequenza, e questo è il
secondo. Impatto misurato oggi: il contributo close-to-close delle tre quantità inesistenti vale
**−$55.17**, contro un MTM del book aperto di +$21.66 calcolato sulle quantità DB. Il MTM vero è
quindi **−$33.51**, e la riconciliazione torna al centesimo: −33.51 (book aperto) + 38.87 (NVDA e META
da close precedente a prezzo d'uscita) = **+5.36** contro **+5.28** di variazione equity Alpaca
(Δ $0.08). Con le quantità DB il conto sarebbe stato +$60.53, cioè **oltre dieci volte** il movimento
reale. Conseguenza concreta sul report di oggi: WDC risulta il mover #1 «catturato» con +$25.37 di
`passive_pnl` nel `snapshot_apertura` del dossier, mentre la posizione reale ne ha guadagnati ≈$6.36
— **$19 su $25 sono fantasma**. La stessa distorsione contamina la serie `market_daily.jsonl` per
ogni giorno in cui MRVL, NOK o WDC erano a libro, cioè da fine luglio in avanti.
*ID NUOVO GIUSTIFICATO, e la giustificazione è che nessun finding esistente parla di quantità.
[F-022] riguarda il dimensionamento dello stop, non la scrittura del fill. [F-042] è un ordine BUY al
broker **senza** riga `trades` — qui la riga c'è e ha il numero sbagliato, difetto opposto.
[F-039] sono righe inserite e cancellate pre-market. [F-002] è l'attribuzione di sleeve mancante,
non la quantità. Se la ricorrenza mostrerà che [F-022] e questo sono lo stesso guasto visto da due
lati, si fondono in sintesi.*
*Costo: **null**. Nessun dollaro è stato perso o guadagnato dalla mismisura in sé — il conto è quello
che è. Il danno è che $55.17 su $60.53 di movimento di book (il 91%) erano fantasma oggi, quindi ogni
`mtm` della serie e ogni attribuzione per sleeve costruita su `trades` è sbagliata di una quantità
che nessuno stava misurando.*

**[F-044] Sembra un difetto, seconda occorrenza consecutiva — il dossier deterministico continua a
non generarsi e il guasto è ora databile a un commit preciso.** Riproduzione identica al 08-25:
`uv run python scripts/alpha_miner_dossier.py 2026-08-26` → `INFO 2026-08-26 saltato: Query fallita:
ERROR: column reference "decision_at" is ambiguous` seguito da `INFO dossier scritti: 0`, **exit code
0**. Elemento nuovo rispetto a ieri: `git log -S "LEFT JOIN s4_intent_events disposition" --
scripts/alpha_miner_dossier.py` restituisce **un solo commit, `d5dacc3` (PR #354, 2026-08-25
13:12:27)**, che ha introdotto il join con `s4_intent_events` senza qualificare le due referenze a
`decision_at` già presenti. Verificato in `information_schema` che entrambe le tabelle espongono la
colonna: è un errore di parsing, deterministico, indipendente dai dati. Il dossier 2026-08-25
presente nel repo ha mtime successivo al commit ma **non** è stato prodotto da questo codice — porta
la chiave `intenti_ingresso_s4` nello schema vecchio e la sessione del 08-25 dichiara di averlo
generato da una copia in `/tmp`; l'mtime viene da `backfill_provenienza_dossier.py`, che riscrive i
file senza rigenerarli. Quindi **il blocco intent non è mai stato prodotto in produzione da quando è
stato innestato**, ora per due sedute. Il degrado silenzioso resta la parte peggiore: il cron può
scrivere `dossier scritti: 0` due giorni di fila senza che nulla suoni.
*Costo: null — è strumentazione, non P&L. Il danno si conta per ricorrenza: due giornate di
osservazione che senza intervento manuale sarebbero andate perse.*

**[F-045] Ricorrenza confermata sui dati di oggi — la guardia di contraddizione è cieca al 100%.**
`aggregati.guardia_contraddizione` del dossier 2026-08-26: `n_intenti` **1.518**,
`n_intenti_tradabili` **0**, `n_intenti_non_tradabili` **1.518**, `n_valutabili` **0**,
`n_soppressi` 0. Sulla finestra di osservazione cumulata (2 giorni, schema 2.5) il quadro è identico:
3.012 intent, zero tradabili. Un partizionamento che assegna il 100% delle righe a un lato solo, per
due giorni su due, non descrive i dati: è il confronto `is_tradable::text` che non può mai essere
vero. La conseguenza è che la guardia introdotta per misurare le soppressioni **non ha mai valutato
nulla** da quando esiste, e i suoi zeri sono indistinguibili da «nessuna soppressione».
*Costo: null — strumentazione.*

**[F-001] La copertura news interrompe cinque sedute di peggioramento monotono, ma resta il vincolo
dominante: 45 dei 96 simboli senza una sola riga in `news_log`.** Serie: 40 (08-19) → 41 → 43 → 51 →
55 (08-25) → **45**. Effective-timely coverage **24/96 = 25.0%** (34 articoli issuer-specific
tempestivi su 63 articoli unici, 114 righe). **Tre dei cinque miss di oggi sono NO_NEWS puri** — DB,
RDDT, ERIC — e su tutti e tre non esiste nemmeno un segnale da scartare. Copertura di settore a zero
su **energy (0/6)**, **industrials (0/4)**, **materials (0/2)** e **telecom** — ed è proprio da
telecom che arriva ERIC −3.08%, terzo mover della giornata, con `volume_surprise` +1.25, cioè l'unico
mover con un'anomalia di volume che una fonte diversa dalle news avrebbe potuto vedere. Concentrazione
invariata: top-5 ticker al 32.4% delle righe, top-5 settori all'85.3%.
*Costo: **$67.06 lordo**, e solo su DB — è l'unico dei tre NO_NEWS al rialzo e quindi l'unico
azionabile con un book long-only (RDDT ed ERIC sono ribassi su titoli non detenuti: opportunità
accessibile 0.0 per costruzione, come calcola l'estimator v2). Sull'orizzonte realmente accessibile
il costo è **negativo, −$7.90**: DB ha aperto a 40.53 sopra la chiusura di 40.23, l'intero movimento
era gap notturno e qualunque ingresso intraday avrebbe perso denaro. Registro il lordo $67.06
nell'occorrenza per confrontabilità con la serie, ma il numero onesto oggi è che la copertura news
mancante **non è costata nulla**.*

**[F-046] Ricorrenza per persistenza, non per ripetizione — lo score sbagliato del 08-25 su HOOD è
ancora quello che il sistema usa il 08-26.** Il 08-25 l'articolo `news_log` 8902, titolo «Why Is
Robinhood Stock Surging on Tuesday?» e corpo «Robinhood Markets Inc. (NASDAQ: HOOD) stock traded
lower **Thursday** after a White House crypto summit» — giorno diverso, direzione opposta — aveva
prodotto score **−0.0098** sul mover #1 della seduta. Oggi tutti i **24 intent S4 su HOOD** portano
`snapshot->>'score' = -0.0098`, cioè **quello stesso segnale**, perché nella giornata non è arrivato
nessun articolo issuer-specific a sostituirlo (i due di oggi sono un pezzo su SHIB in Giappone e un
listicle «whale alerts», `max_score_own = null`). Il difetto quindi non dura una giornata: entra
nello stato e ci resta finché non arriva un pezzo migliore. Meccanismo invariato e già documentato:
`src/workers/sentiment.py` costruisce il prompt con il solo `text=clean_body`, il titolo non compare
mai. Nota collaterale sulla stessa classe: su DB il `body_snippet` di `gdelt_gkg` **è** il titolo (84
caratteri, identici) — lì il modello riceve il titolo e nient'altro, quindi lo stesso pipeline dà al
modello o solo il corpo o solo il titolo a seconda della fonte, mai entrambi.
*Costo: **$0.00, e zero misurato non zero mancante**. HOOD oggi ha chiuso a −3.17% e il book è
long-only: uno score corretto e positivo avrebbe potuto solo far comprare un titolo in caduta. Il
difetto oggi ha protetto il book, esattamente come [F-031]. Il costo vero di F-046 resta i $30.85
registrati sull'occorrenza 08-25.*

**[F-040] Il segnale più forte della giornata è ribassista, ha il segno giusto, ed è strutturalmente
inutilizzabile.** NVO score **−0.5533**, ampiamente sopra il gate 0.30 in modulo, generato alle 15:30
ET; NVO ha chiuso a **−3.02%**. Nessun ordine possibile: book long-only, titolo non detenuto, i 2
intent S4 si fermano su `SKIP_FALLBACK`. È la seconda occorrenza del finding. Aggravante specifica di
oggi, che vale la pena separare dal merito: **il segnale ha il segno giusto per l'articolo
sbagliato** — l'unico pezzo attribuito a NVO è «Boston Scientific Reports Global Disruption After
Cybersecurity Incident», che non nomina Novo Nordisk. Il segno corretto è una coincidenza, non una
lettura.
*Costo: **$0.00 misurato**, non non-stimato. `opportunity_v2` calcola `accessible_opportunity_usd =
0.0` con `missing_reason: long_only_no_short_downside_not_held`: il vincolo è di mandato, non un
difetto, e il lordo teorico $66.46 non è raggiungibile da nessuna configurazione attuale del book.*

**[F-020] Attribuzione ticker errata su un percorso nuovo — `source_metadata` con `n_ticker=1`,
non `org_lookup`.** L'articolo «Boston Scientific Reports Global Disruption After Cybersecurity
Incident» è mappato su **NVO e solo NVO** (`n_ticker=1`, quindi non è fan-out) tramite
`extraction_method='source_metadata'`, cioè i metadati del provider Benzinga, non il lookup delle
organizzazioni. È lo stesso *esito* di F-020 — un articolo su una società estranea che forma il
punteggio di un ticker — per un *meccanismo* diverso. Secondo caso pulito nella stessa giornata:
«Ohio Rep. Michael Rulli Sold Up to $100K Worth of **Alphabet** Stock» mappato su GOOGL **e LLY**;
LLY chiude −3.59% e 2 dei suoi 4 articoli non parlano di Eli Lilly (l'altro è il pezzo macro sul PCE,
fan-out a 7 ticker). Registro qui e non su un id nuovo per non spezzare l'evidenza: **se la
ricorrenza mostra che il percorso `source_metadata` ha un tasso di errore proprio, va scorporato**,
perché il rimedio sarebbe diverso (validare i tag del provider contro il soggetto del testo, non
correggere il lookup).
*Costo: null. Nessun ordine è nato oggi da un'attribuzione errata: gli intent NVO si fermano su
`SKIP_FALLBACK` e quelli LLY su `SKIP_PYRAMIDING`.*

**[F-012] Il fan-out resta la maggioranza delle righe scorate: 51 mapping extra su 114 righe da 63
articoli unici (44.7%).** `mapping_rilevanza`: **80 UNKNOWN contro 34 ISSUER_SPECIFIC**, zero
classificate `SECTOR_MACRO`, `FALSE_ENTITY_MATCH` o `IRRELEVANT_FANOUT` — la classificazione manda
in `UNKNOWN` tutto ciò che non riconosce, quindi il 70% delle righe non è caratterizzato. Casi
leggibili oggi: «The Fed Faces A Dangerous Choice For Investors; Nvidia Earnings Ahead» su **9**
ticker, «Nasdaq 100 Falls as Hot PCE Inflation Stirs Rate-Hike Bets» su **7** (IWM, LLY, NVDA, QQQ,
XLE, XLK, XLV), «10 Information Technology Stocks With Whale Alerts» su **6**. Su HOOD la quota
fan-out è **0.5** con `max_score_own = null`: metà dei suoi punteggi nasce da pezzi condivisi e
nessuno da un pezzo di cui sia il soggetto.
*Costo: null. Nessun ordine è stato aperto oggi, quindi nessun dollaro è attribuibile al fan-out.*

**[F-031] Il guard anti-pyramiding costa denaro per la prima volta in tre sedute — la serie
protettiva si interrompe.** 108 `SKIP_PYRAMIDING` su 6 simboli. Il caso più vistoso è **LLY**:
segnale **+0.3220** (generato il 08-24 alle 13:00, quindi già vecchio di due sedute), sopra gate,
bloccato **17 volte** perché il titolo è già detenuto da S1 — e LLY ha chiuso a **−3.59%**, la
peggiore posizione della giornata, quindi lì il blocco ha protetto. Ma gli altri cinque bloccati
sono tutti positivi: CSCO +1.13%, DELL +2.73%, MU +0.58%, SOXX +0.26%, META +1.07%, e la somma
ribalta il segno. Il difetto resta quello noto: nessuna traccia in `execution_decisions`, gli scarti
sono ricostruibili solo da `s4_intent_events`.
*Costo: **$47.91**, e per la prima volta è un costo e non un risparmio. A size S4 standard ($2.200) e
su base close-to-close i sei ingressi bloccati avrebbero prodotto CSCO +$24.75, DELL +$60.03,
MU +$12.80, SOXX +$5.73, META +$23.50 contro LLY **−$78.91**, netto **+$47.91**. Avvertenza sul
numero: è un lordo close-to-close, non l'orizzonte accessibile — l'ingresso reale sarebbe avvenuto
intraday e su DELL, che apre a 449.58 sotto la chiusura precedente di 451.50, il lordo sovrastima.
Lo registro comunque perché le due occorrenze precedenti (08-24 e 08-25) usano la stessa base e
vanno confrontabili: 08-24 −$340 (risparmio), 08-25 $0, oggi **+$47.91 (costo)**.*

**[F-002] Dieci posizioni su 48 nello `snapshot_apertura` restano senza attribuzione di sleeve.**
`strategia = "CONTAMINAZIONE"` su 10 righe, contro 34 S1 e 4 S4. Sono i trade legacy antecedenti alla
patch `stop_strategy` e non è un dato nuovo, ma va contato oggi perché **il 21% del book resta fuori
da qualunque attribuzione per strategia**, e ogni confronto S1-vs-S4 costruito su questa serie eredita
quel buco. Su `trades` la colonna `strategy` non esiste affatto: l'attribuzione passa dal campo
`stop_strategy`, che è un effetto collaterale del sistema di stop, non un'anagrafica.
*Costo: null — strumentazione.*

## 8. Nota metodologica

Tre numeri di questo report sono stati corretti rispetto a quello che le fonti dicono a prima vista,
e li dichiaro perché la serie storica ne è affetta:

1. **Equity di chiusura.** `GET /v2/account/portfolio/history` con `timeframe=1D` marca ogni riga a
   **00:00 UTC del giorno successivo** alla seduta (verificato: esiste una riga «2026-08-22», che è
   un sabato, ed è la chiusura di venerdì 08-21). L'equity della seduta 2026-08-26 è quindi la riga
   etichettata **2026-08-27: $109.965,05, P/L +$5,28**. La riga etichettata «2026-08-26» ($109.959,77,
   +$98,39) è la chiusura del **08-25** — ed è infatti il valore che il report e la riga
   `market_daily.jsonl` del 08-25 riportano correttamente.
2. **MTM del book aperto.** Riportato a **−$33,51**, cioè sulle quantità reali del broker, non le
   $+21,66 che si ottengono dalle quantità `trades`. La differenza è interamente [F-048]. Le righe
   `market_daily.jsonl` precedenti usano la base `trades` e sono quindi sovrastimate su ogni giorno
   in cui MRVL, NOK o WDC erano a libro; non le ho toccate — il ledger è solo-append.
3. **Dispersione.** σ = 1,5219% dal dossier (`adjustment=all`). Il mio calcolo indipendente su barre
   `adjustment=raw` dava 1,5139%: vince il dossier, come da protocollo.
