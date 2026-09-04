# Alpha Miss Report — 2026-09-03

**Universo:** 96 simboli di `config/trading.yaml → symbols.watchlist`.
**Fonte prezzi:** dossier deterministico `docs/evidence/dossier/2026-09-03.json` (schema 2.7, Alpaca SIP, `adjustment=all`), generato il 2026-09-04T08:00:27Z. Ogni numero di mercato, copertura, ingresso, uscita, guardia e controfattuale citato qui viene dal dossier; la lettura del testo degli articoli e la classificazione delle cause sono mie.
**Soglia mover:** `|return| ≥ 3%` (`soglia_mover` del dossier). Con σ cross-sectional al **2,92%** oggi, 3% è ≈1,03σ — coerente con la finestra. 12 nomi sopra soglia.
**Regime di scoring:** terza seduta con la Variante A del prompt sentiment (#399/#408, deployata `bf5bef2e` il 2026-09-01T10:33Z). Confrontabile con 09-01 e 09-02, non con agosto.
**Cicli portfolio:** 24 cicli da 14:07 a 19:52 UTC, **zero gap oltre 16 minuti**. La cadenza non è un fattore in nessuna delle catture o dei miss di oggi.
**Log applicativi:** `logs/containers/{worker,worker-inference,api,beat}-2026-09-03.log` **non disponibili** — la directory contiene solo i log del 2026-09-04 (rotazione senza persistenza del giorno target). Tutte le affermazioni sotto sul percorso live vengono da `execution_decisions`/`sentiment_signals`/`trades` via query diretta, non dai log.

---

## 1. Executive summary

Seduta **anomala rispetto alla serie**: **12 mover, tutti al rialzo, zero al ribasso** — non una rotazione fra vincitori e perdenti come il 09-02, ma un rally largo (SPY +1,05%, QQQ +1,19%) con dispersione idiosincratica sopra: alcuni nomi corrono molto di più dell'indice (HOOD +16,57%, SNOW +16,55%), nessuno lo tradisce in negativo.

Alembic ne ha **4 in mano o tradati** (HOOD, SNOW, PLTR, DELL) e **8 mancati** (NOW, SPCX, ORCL, TSLA, SAP, GS, ARM, META). Causa prevalente per il classificatore del dossier: **BELOW_GATE (4/8)**; nella mia classificazione a sei categorie, **THIN_NEUTRAL domina (5/8, 62,5%)** — notizia presente ma segnale troppo debole o diluito da fan-out/filler, non assenza di dati. Solo 2 miss sono NO_NEWS puri (SAP, ARM). **Il miss economicamente più rilevante è NOW** (+6,49%, `accessible_opportunity` netta **+26,39 $**, unico caso su 8 con opportunità realmente accessibile e positiva); tutti gli altri hanno opportunità netta **negativa o marginale** — cioè anche superando gate/filtro, all'orario in cui il segnale sarebbe diventato eleggibile il movimento era già scontato o in fase di reversal.

Il fatto della giornata non è nella tabella dei miss: **TSLA (+5,42%) ha un punteggio 0,468 — sopra il gate 0,30 — generato alle 19:45:44 da un modello singolo (fallback)**, e la posizione **non riceve alcuna decisione al ciclo delle 19:52**, l'unico simbolo su 31 valutati quel ciclo a restare senza riga in `execution_decisions` (ogni altro simbolo, incluso ogni altro mover, ha una riga). Coerente con F-056 (preferenza per il segnale non-fallback più vecchio) e F-060 (il classificatore causale del dossier etichetta il caso `NON_CLASSIFICATO`, mentre il `funnel_v2` più recente lo disambigua correttamente come `FALLBACK_REJECT`).

**HOOD** è stata aperta e chiusa nella stessa seduta: **+2,55 $ realizzati** contro **+18,11 $** se tenuta fino al close (drift `+14,79 $` lasciato sul tavolo) — sul mover più forte della giornata. **PLTR** è stata comprata quando il movimento intraday era già oltre il 100% completo (`quota_movimento_precedente_al_segnale = 1,05`), fill sopra il close di giornata, MTM **−4,92 $**. **SNOW** e **DELL** erano già a libro (S1): SNOW ha aperto con un gap enorme e **ha perso terreno intraday** (passivo −35,90 $ open→close, pur chiudendo +16,55% sul giorno precedente); DELL ha guadagnato +27,96 $ passivi su un nozionale di 452 $, con l'anti-pyramiding che blocca un aggiunta a punteggio 0,478 all'ultimo ciclo.

Book: equity di chiusura **110.132,01 $** (+51,29 $ sulla seduta), realizzato **+93,56 $** (S1 +50,64 $, S4 +42,93 $), MTM implicito del libro aperto **−42,27 $**. **50/96 simboli (52,1%)** a zero copertura news.

---

## 2. Rendimenti — tabella completa (96 simboli)

`**M**` = mover ≥3%. "Stato" è la posizione nel book all'open RTH più eventuali ingressi/uscite della seduta (dossier `snapshot_apertura` + `ingressi` + `chiusure`). "Articoli" = articoli unici in `news_log` quel giorno (`copertura_articoli.per_ticker`).

| Simbolo | Return | Stato nel book | Articoli | ≥3% |
|---|---:|---|---:|:--:|
| HOOD | +16.57% | ingresso oggi + uscita oggi | 8 | **M** |
| SNOW | +16.55% | detenuto | 6 | **M** |
| PLTR | +7.71% | ingresso oggi | 6 | **M** |
| NOW | +6.49% | — | 4 | **M** |
| SPCX | +6.42% | — | 1 | **M** |
| ORCL | +5.69% | — | 2 | **M** |
| TSLA | +5.42% | — | 7 | **M** |
| DELL | +4.91% | detenuto | 2 | **M** |
| SAP | +3.50% | — | 0 | **M** |
| GS | +3.34% | — | 2 | **M** |
| ARM | +3.29% | — | 0 | **M** |
| META | +3.01% | — | 5 | **M** |
| CRM | +2.92% | detenuto + ingresso oggi + uscita oggi | 3 |  |
| C | +2.83% | detenuto | 0 |  |
| GM | +2.77% | detenuto | 0 |  |
| MSFT | +2.68% | ingresso oggi + uscita oggi | 7 |  |
| DB | +2.62% | — | 1 |  |
| MS | +2.52% | detenuto | 3 |  |
| WMT | +2.20% | — | 2 |  |
| ADBE | +2.13% | — | 0 |  |
| AZN | +1.94% | — | 0 |  |
| F | +1.91% | — | 0 |  |
| NVDA | +1.80% | ingresso oggi + uscita oggi | 14 |  |
| INTC | +1.80% | detenuto | 0 |  |
| JPM | +1.64% | detenuto | 1 |  |
| GOOGL | +1.59% | detenuto | 8 |  |
| NVO | +1.58% | — | 0 |  |
| XLF | +1.56% | detenuto | 2 |  |
| AMZN | +1.54% | — | 4 |  |
| UBS | +1.42% | detenuto | 0 |  |
| NKE | +1.39% | — | 0 |  |
| BIDU | +1.31% | — | 0 |  |
| IBM | +1.30% | — | 0 |  |
| XLK | +1.29% | detenuto | 2 |  |
| SONY | +1.26% | — | 0 |  |
| GE | +1.21% | — | 0 |  |
| QQQ | +1.19% | ingresso oggi | 3 |  |
| JNJ | +1.17% | detenuto | 0 |  |
| MRVL | +1.14% | detenuto | 2 |  |
| PANW | +1.05% | — | 1 |  |
| SPY | +1.05% | detenuto | 2 |  |
| INFY | +1.00% | — | 0 |  |
| AAPL | +1.00% | detenuto | 3 |  |
| CAT | +0.99% | detenuto | 1 |  |
| T | +0.92% | — | 0 |  |
| ERIC | +0.90% | — | 0 |  |
| TM | +0.79% | — | 0 |  |
| BA | +0.79% | — | 1 |  |
| VZ | +0.74% | — | 0 |  |
| BAC | +0.71% | detenuto | 1 |  |
| HD | +0.60% | — | 1 |  |
| BRK.B | +0.57% | — | 0 |  |
| MRK | +0.46% | detenuto | 1 |  |
| IWM | +0.40% | detenuto | 1 |  |
| ROKU | +0.39% | detenuto | 0 |  |
| TMUS | +0.38% | — | 0 |  |
| TSM | +0.36% | detenuto | 3 |  |
| UNH | +0.32% | detenuto | 0 |  |
| MU | +0.22% | detenuto + uscita oggi | 2 |  |
| XLV | +0.18% | detenuto | 2 |  |
| SOXX | +0.15% | detenuto | 0 |  |
| V | +0.09% | — | 0 |  |
| RIO | +0.09% | detenuto | 0 |  |
| BABA | +0.00% | — | 1 |  |
| LLY | -0.04% | detenuto | 0 |  |
| AXP | -0.05% | — | 0 |  |
| NFLX | -0.07% | — | 0 |  |
| WFC | -0.09% | — | 0 |  |
| AMD | -0.20% | detenuto | 3 |  |
| CVX | -0.22% | detenuto | 0 |  |
| MMM | -0.26% | — | 0 |  |
| QCOM | -0.28% | — | 0 |  |
| JD | -0.32% | — | 0 |  |
| COST | -0.33% | — | 0 |  |
| TXN | -0.38% | — | 1 |  |
| MA | -0.41% | — | 1 |  |
| PG | -0.49% | — | 0 |  |
| MCD | -0.51% | — | 1 |  |
| SHEL | -0.51% | detenuto | 0 |  |
| ABBV | -0.58% | detenuto | 1 |  |
| AMAT | -0.58% | detenuto | 1 |  |
| CMCSA | -0.60% | — | 0 |  |
| NOK | -0.71% | detenuto | 1 |  |
| PFE | -0.72% | detenuto | 1 |  |
| XLE | -0.74% | detenuto | 2 |  |
| DIS | -0.76% | — | 0 |  |
| CSCO | -0.77% | detenuto | 0 |  |
| BP | -0.80% | detenuto | 0 |  |
| SBUX | -0.84% | detenuto | 0 |  |
| XOM | -1.18% | detenuto | 0 |  |
| RDDT | -1.33% | — | 0 |  |
| WDC | -1.63% | detenuto | 0 |  |
| PBR | -1.68% | detenuto | 0 |  |
| ASML | -2.15% | detenuto | 0 |  |
| VALE | -2.67% | detenuto | 0 |  |
| AVGO | -2.74% | ingresso oggi + uscita oggi | 7 |  |

Nessun simbolo senza barre disponibili (`simboli_senza_dati: []`).

---

## 3. Miss classificati (mover ≥3% non detenuti e non tradati)

Gli 8 candidati sono esattamente `candidati_miss` del dossier. Le categorie della colonna "Categoria" sono le mie (schema del prompt: NO_NEWS / THIN_NEUTRAL / WRONG_SIGN / FILTERED / OUT_OF_STRATEGY_SCOPE / CAUGHT), dopo aver letto il testo degli articoli; "Dossier" è la `causa` del suo classificatore, con vocabolario diverso (BELOW_GATE / NO_NEWS / OFF_TOPIC_NON_DECIDIBILE / NON_CLASSIFICATO) — dove differiscono lo dichiaro.

| Simbolo | Return | Categoria | Dossier | `net_opportunity_usd` | Evidenza |
|---|---:|---|---|---:|---|
| SAP | +3,50% | **NO_NEWS** | NO_NEWS | −3,25 $ | Zero righe `news_log`, zero segnali, zero rilevanza di qualunque tipo. |
| ARM | +3,29% | **NO_NEWS** | NO_NEWS | **+132,54 $** | Zero righe `news_log`, zero segnali. È il candidato con l'opportunità netta più alta di tutta la giornata, e nessun dato per intercettarla. |
| NOW | +6,49% | **THIN_NEUTRAL** | BELOW_GATE | **+26,39 $** | 4 righe, tutte `TAG_UNCONFIRMED`/fan-out (`quota_righe_fanout=1,0`), zero `ISSUER_SPECIFIC`. Punteggio massimo **0,121** (19:15, dal pezzo macro "Wall Street Rallies as Fed's Waller Hints..."), segno corretto, meno di metà gate. Unico miss dell'universo con opportunità netta positiva e accessibile. |
| SPCX | +6,42% | **THIN_NEUTRAL** | BELOW_GATE | −32,90 $ | 1 sola riga, fan-out (stesso pezzo macro Fed Waller, 19:15), punteggio 0,18. Nota: SPCX è classificato `etf_broad` in `trading.yaml` insieme a SPY/QQQ/IWM — non è un titolo Musk/SpaceX ma un ETF a paniere largo; resta comunque tradabile dal sistema (QQQ, stesso gruppo, è stato tradato oggi), quindi non è OUT_OF_STRATEGY_SCOPE. |
| ORCL | +5,69% | **THIN_NEUTRAL** | BELOW_GATE | −23,28 $ | 2 righe fan-out, punteggio massimo 0,10 (segno corretto), zero copertura issuer-specific. |
| TSLA | +5,42% | **FILTERED** | NON_CLASSIFICATO | −35,29 $ | Segnale **0,468** (19:45:44, `single:gpt-oss:20b-cloud`, `fallback_used=true`) è sopra gate 0,30 ma non produce **nessuna** riga in `execution_decisions` al ciclo delle 19:52 — unico simbolo su 31 valutati quel ciclo senza decisione. Il segnale ensemble più recente prima di quello, 0,277 (16:15, non-fallback), è **anch'esso** sotto gate per soli 0,023 punti. Il dossier classifica `NON_CLASSIFICATO`; `funnel_v2.righe` lo disambigua come `FALLBACK_REJECT` con `score_firmato=0,468`. Dettaglio in §8.1. |
| GS | +3,34% | **THIN_NEUTRAL** | OFF_TOPIC_NON_DECIDIBILE | +10,54 $ | 2 articoli, **nessuno con contenuto informativo**: "If You Invested $100 In Goldman Sachs Group Stock 15 Years Ago, You Would Have This Much Today" (`ISSUER_SPECIFIC`, punteggio 0,002) e "6 Financials Stocks Whale Activity In Today's Session" (fan-out, punteggio 0,0). Nessun articolo tocca il catalizzatore del +3,34%. Dettaglio in §8.2. |
| META | +3,01% | **THIN_NEUTRAL** | BELOW_GATE | −27,22 $ | 5 righe. L'unico articolo `ISSUER_SPECIFIC` ("Analyst Sees a Google-Like AI Moment Brewing for Meta After $18 Billion Settlement", framing rialzista) è scorato **−0,026**: segno opposto al movimento ma magnitudine trascurabile, non un caso `WRONG_SIGN` netto. Il punteggio più alto della giornata resta il fan-out Fed Waller a 0,18, sotto gate. |

**Conteggi (mia classificazione):** NO_NEWS 2, THIN_NEUTRAL 5, WRONG_SIGN 0, FILTERED 1, OUT_OF_STRATEGY_SCOPE 0. **Conteggi dossier:** BELOW_GATE 4, NO_NEWS 2, OFF_TOPIC_NON_DECIDIBILE 1, NON_CLASSIFICATO 1.

Da leggere insieme: **6 degli 8 miss hanno `net_opportunity_usd` negativa** — anche disarmando ogni gate/filtro coinvolto, all'orario in cui il segnale sarebbe diventato eleggibile la finestra di guadagno netto di costi era già chiusa o negativa. Solo **NOW (+26,39 $)** e **ARM (+132,54 $, ma NO_NEWS puro — nessun meccanismo di scoring l'avrebbe mai vista)** rappresentano denaro realmente lasciato sul tavolo dalla pipeline.

---

## 4. Titoli catturati: esito

<!-- alpha-miss-book:start -->
<!-- alpha-miss-book-manifest: {"schema":1,"ingressi":["HOOD","MSFT","NVDA","AVGO","CRM","PLTR","QQQ"],"chiusure":["CRM","MSFT","NVDA","AVGO","HOOD","MU"]} -->

Dati deterministici dal dossier; la prosa seguente li annota e non li sostituisce.

| Tipo | Simbolo | Strategia | Ora UTC | Prezzo | Quantità | P&L netto | Motivo / qualità |
|---|---|---|---|---:|---:|---:|---|
| IN | HOOD | S4 | 15:22 | $123.1400 | 11.4635 | — | percentile 85.30%; denominatore intraday valido |
| IN | MSFT | S4 | 15:52 | $513.5400 | 2.7268 | — | percentile 85.79%; denominatore intraday valido |
| IN | NVDA | S4 | 16:37 | $227.5800 | 6.1735 | — | percentile 50.09%; denominatore intraday valido |
| IN | AVGO | S4 | 16:52 | $354.8300 | 3.9355 | — | percentile 73.23%; denominatore intraday valido |
| IN | CRM | S4 | 18:37 | $267.5100 | 5.1797 | — | percentile 88.61%; denominatore intraday valido |
| IN | PLTR | S4 | 18:37 | $183.0800 | 7.5684 | — | percentile 80.24%; denominatore intraday valido |
| IN | QQQ | S4 | 19:22 | $717.8160 | 1.9444 | — | percentile 88.09%; denominatore intraday valido |
| OUT | CRM | S4 | — | $263.8700 | 7.6000 | +$30.37 | portfolio_sell |
| OUT | MSFT | S4 | — | $510.0710 | 2.7268 | −$9.74 | portfolio_sell |
| OUT | NVDA | S4 | — | $229.6168 | 6.1735 | +$12.29 | portfolio_sell |
| OUT | AVGO | S4 | — | $356.9200 | 3.9355 | +$7.46 | portfolio_sell |
| OUT | HOOD | S4 | — | $123.4300 | 11.4635 | +$2.55 | portfolio_sell |
| OUT | MU | S1 | — | $954.7840 | 0.3981 | +$50.64 | sentiment_reversal |
<!-- alpha-miss-book:end -->

Dati deterministici dal dossier (`ingressi`, `chiusure`, `snapshot_apertura`, `funnel_v2.righe`); la prosa seguente li annota e non li sostituisce.

| Simbolo | Return | Esito | Numeri |
|---|---:|---|---|
| **HOOD** | +16,57% | **round-trip in giornata, uscita anticipata** | S4, trade 975. BUY 15:22 @ 123,14 (11,4635 az.), `entry_percentile` 0,853, `quota_movimento_precedente_al_segnale` 0,855 — il segnale arriva a movimento già in gran parte fatto. SELL 19:22 @ 123,43, `portfolio_sell`, **realizzato +2,55 $** (`trades.net_pnl`). `mtm_eod` se tenuta al close **+18,11 $**: **+14,79 $ lasciati sul tavolo** (`drift_post_uscita`) sul mover più forte della giornata. |
| **SNOW** | +16,55% | detenuto, **movimento quasi tutto overnight** | S1, trade 660, a libro dal 2026-08-05. Open 377,245 → close 356,47: **passivo intraday −35,90 $**, nonostante il +16,55% di seduta (close vs close-precedente) — il rialzo è quasi interamente un gap d'apertura, poi la posizione **perde terreno** durante il giorno. Due punteggi qualificanti per pyramiding (+0,306 alle 16:37, +0,220 alle 16:52) bloccati da `SKIP_PYRAMIDING`, entrambi con controfattuale 1h **negativo** (−14,99 $ e −17,99 $): qui il blocco ha evitato una perdita, non causato un miss. Vedi §8.3. |
| **PLTR** | +7,71% | **ingresso a movimento già superato, fill sopra il close** | S4, trade non ancora chiuso al cutoff. BUY 18:37 @ 183,08, `entry_percentile` 0,802, **`quota_movimento_precedente_al_segnale` 1,055** (>1: il titolo aveva già superato il suo massimo di giornata al momento dell'ingresso, `denominatore_degenere=false`). Close 182,53: **MTM −4,92 $** (`funnel_v2`, pipeline `BAD_FILL`). |
| **DELL** | +4,91% | detenuto, cattura passiva, pyramiding bloccato | S1, trade 293, a libro dal 2026-07-13. Nozionale open **452,03 $** (0,93 az.), open 486,31 → close 516,39: **passivo +27,96 $**. `SKIP_PYRAMIDING` alle 19:52 su sentiment +0,478, peso non allocato 2,4%, controfattuale 1h **+12,89 $** (nozionale inteso 1.997,53 $). |

**Tutte e due le uscite/round-trip della seduta (HOOD) hanno `drift_post_uscita` positivo**, coerente con la mediana mobile a 20 giorni di `drift_post_uscita` (0,265 $) ma di un ordine di grandezza sopra (14,79 $ su HOOD da sola).

---

## 5. Cecità lato uscita (posizioni detenute)

Dal campo `copertura_uscita` del dossier, non ricalcolato. Definizione: posizione viva all'open RTH, perdita ≥3% da `ritorno_da_ingresso`, zero righe `news_log` e zero `sentiment_signals` nella seduta, zero righe per ≥2 sedute consecutive. Finestra 10 sedute.

**44 posizioni valutate, 2 cieche lato uscita, 0 con `cieco_lato_uscita: null`** — nessun dato mancante oggi, il campo è deciso su tutte e 44.

| Ticker | Strategia | `ritorno_da_ingresso` | Sedute consecutive senza righe | `fonti_osservate_finestra` | Nozionale |
|---|---|---:|---:|---|---:|
| **ASML** | S1 | **−6,93%** | **10** (troncato dalla finestra) | — (vuoto) | 621,52 $ |
| **WDC** | S4 | **−19,60%** | 4 | `alpaca_benzinga` | 147,79 $ |

Nozionale cieco totale **769,31 $** — esposizione a rischio, non un costo: nessun controfattuale dice che un'uscita sarebbe stata migliore. Attenzione a non confondere le misure: ASML oggi è **scesa** anche a livello di seduta (−2,15% `ritorno_seduta`, coerente col −6,93% da ingresso), mentre WDC ha chiuso quasi piatta a seduta (−1,63%) pur essendo a −19,60% dall'ingresso.

**ASML ha `fonti_osservate_finestra` vuoto su tutte e 10 le sedute** — non "fonte non configurata" (i connettori interrogano l'intera watchlist), ma zero resa dei provider su questo ticker per un'intera finestra a doppia cifra di sedute. Continuità con il 09-02 (allora 9 sedute consecutive, oggi 10, la finestra è troncata dal denominatore a 10 sedute: la vera serie di silenzio è più lunga). Su questa posizione nessun meccanismo di uscita basato su notizia può accendersi — per assenza di input, non per scelta.

---

## 6. Pattern osservato

**Rally largo e non rotazionale, con dispersione concentrata su software/AI e financials.** A differenza del 09-02 (rotazione netta out-of-software / into-semis-financials, con perdenti chiari), oggi **zero simboli scendono sopra soglia**: SPY +1,05%, QQQ +1,19% — l'indice sale, e i mover sono i nomi che salgono *molto di più* dell'indice, non un gruppo che scende mentre un altro sale.

- **Settori sopra soglia:** tech (media +2,90% su 21 nomi, include SNOW +16,55%, PLTR +7,71%, NOW +6,49%, ORCL +5,69%, SAP +3,50%, META +3,01%), financials (+2,38% su 14, include HOOD +16,57%, GS +3,34%), etf_broad (+2,26%, include SPCX +6,42% e QQQ). Nessun settore in territorio negativo sopra soglia; i più deboli sono materials (−1,29%, 2 nomi) ed energy (−0,85%).
- **Un solo articolo macro appare come fan-out su quasi tutti i miss THIN_NEUTRAL:** "Wall Street Rallies as Fed's Waller Hints at September Rate Hold: Stock Market Today", pubblicato verso le 19:15 UTC, compare come riga fan-out su NOW, SPCX, TSLA, META, PLTR, SNOW, DELL, HOOD — cioè su **8 dei 12 mover della giornata**, quasi sempre a fine seduta e quasi sempre con punteggio modesto (0,10–0,22). Non è la causa del rally (troppo tardi nella sessione, il rally era già in corso dal mattino), ma è il motivo per cui la pipeline "vede" quei ticker senza avere nulla di specifico da dire su di loro.
- **Le due punte del rialzo (HOOD, SNOW +16,5% ciascuna) non condividono un tema evidente** — HOOD guidata da coverage retail/crypto-adiacente eterogenea (prediction market, meme-coin fees, upgrade Scotiabank), SNOW da un upgrade analisti "AI product adoption". Non pattern earnings come il 09-02: nessuno dei titoli visti in §3/§4 ha news che menzioni una trimestrale.

Dichiarato esplicitamente: **non ho trovato un singolo tema settoriale o macro sufficiente a spiegare perché proprio HOOD e SNOW abbiano fatto +16,5% mentre il resto del gruppo forte si è fermato a +3-8%** — oltre "AI/software + fintech in un giorno di risk-on generale". Non forzo un pattern più specifico di questo.

---

## 7. Confronto con i giorni precedenti

- **Prima seduta della serie con zero mover negativi.** Confrontato con 09-02 (7 su 11 al rialzo, 4 al ribasso) e 09-01 (misto), oggi è **12 su 12 al rialzo**: mai osservato prima nella finestra dal 2026-08-03.
- **Copertura news.** 50/96 a zero righe (52,1%) — sopra la banda 40-60% osservata dal 07-31 ma dentro il suo limite superiore. Serie recente: 45 (09-02), 48 (09-01), 60 (08-31), 41 (08-13).
- **Il gate continua a mancare per pochi centesimi, terza volta consecutiva su TSLA/NOW/HOOD.** Oggi TSLA ensemble 0,277 contro gate 0,300 (scarto **0,023**). Serie: 0,019 TSLA 08-31, 0,029 NOW 09-01, 0,040 HOOD 09-02, **0,023 TSLA oggi** — quarta occorrenza in quattro sedute dello stesso schema "il segnale più informativo della giornata cade entro 0,04 dalla soglia".
- **Firma "fan-out come unica fonte": quinta+ occorrenza per NOW specificamente.** NOW ha `quota_righe_fanout = 1,0` oggi, come il 09-01 e il 09-02 (allora ribassista, oggi rialzista — la struttura del difetto è indipendente dal segno del movimento). SPCX, ORCL e META condividono la stessa firma oggi.
- **`NON_CLASSIFICATO` di nuovo presente, con una sfumatura nuova.** Dopo essere ricomparso su PLTR il 09-02, oggi è su TSLA — ma per la prima volta il `funnel_v2` del dossier (introdotto più di recente della serie legacy `candidati_miss.causa`) lo disambigua correttamente come `FALLBACK_REJECT`. Il classificatore legacy resta ambiguo; quello nuovo no. Vedi F-060 in Segnalazioni.
- **Anomalia nuova, non vista nei report precedenti: un simbolo scompare del tutto da un ciclo `execution_decisions`.** Nei giorni precedenti i segnali fallback rifiutati producevano comunque una riga `SKIP_THRESHOLD`/`SKIP_FALLBACK` (vedi F-056 dell'08-13 su NFLX/PLTR, dove il fenomeno era già documentato ma su un giorno più vecchio). Oggi è la prima volta nella serie recente (09-01, 09-02) che lo confermo con query diretta sullo stesso giorno del report: TSLA non ha **alcuna riga**, di alcun tipo, dopo le 19:37, mentre gli altri 30 simboli valutati al ciclo delle 19:52 ce l'hanno tutti.
- **Anti-pyramiding: prima volta nella serie con controfattuale prevalentemente negativo.** Il 09-02 i tre blocchi su DELL erano tutti positivi (46,98+30,21+22,15 $). Oggi due dei tre eventi (SNOW ×2) hanno controfattuale 1h **negativo**: il guard ha evitato una perdita, non causato un miss. Solo DELL resta positivo (+12,89 $). Vedi F-031.

---

## 8. Cosa sembra un difetto e non un limite noto

Non propongo tarature né fix: siamo dentro il periodo di sola osservazione (`docs/evidence/OBSERVATION_CHARTER.md`, scadenza attesa 2026-09-28, taratura congelata). Segnalo solo dove l'evidenza di oggi indica un difetto invece di un limite di design. La decisione se aprire issue è dell'operatore.

**8.1 — Un segnale sopra gate su TSLA non produce nessuna decisione, nemmeno di scarto.** Alle 19:45:44 UTC `sentiment_signals` riceve per TSLA un punteggio **0,468** (`single:gpt-oss:20b-cloud`, `fallback_used=true`), sopra il gate 0,30. Il ciclo portfolio delle 19:52:03/04 valuta **31 simboli** (verificato via query diretta su `execution_decisions`) e produce una riga per ciascuno — tranne TSLA, che non ne ha nessuna dopo le 19:37:04 (score 0,221, sotto gate). Non è un `SKIP_FALLBACK` esplicito (nessuna riga con quel `decision` per TSLA oggi): il simbolo è semplicemente assente dall'esito del ciclo. Coerente con la meccanica descritta da F-056 (`fetch_signals_for_cycle` preferisce il segnale non-fallback più recente indipendentemente da forza/recency del fallback), ma questa è la prima volta che verifico l'esito con **zero righe di qualunque tipo**, non solo l'assenza di una `SKIP_STALE` come nei casi 08-13. Il costo economico oggi è nullo: `net_opportunity_usd` per TSLA è **negativo** (−35,29 $), quindi anche se il segnale fosse stato valutato e avesse superato il gate, l'ingresso al primo ciclo eleggibile avrebbe perso denaro dopo i costi. Il difetto è confermato una volta di più, il suo costo di oggi no.

**8.2 — Un articolo "content-mill" genericamente intestato a GS non contiene alcuna informazione su GS.** `news_log`, `ticker=GS`, titolo "If You Invested $100 In Goldman Sachs Group Stock 15 Years Ago, You Would Have This Much Today", classificato `ISSUER_SPECIFIC` (il tag è corretto: l'articolo *è* su GS, a differenza dei casi F-020 dove il ticker è sbagliato) ma **zero contenuto legato a un catalizzatore**: è un pezzo evergreen di rendimento storico, generato indipendentemente da qualunque notizia del giorno. Punteggio **0,002**, indistinguibile da rumore. Il secondo articolo del giorno su GS ("6 Financials Stocks Whale Activity In Today's Session", fan-out, punteggio 0,0) è nella stessa categoria. **Nessuno dei due articoli tocca il vero motivo del +3,34%** (probabilmente il rialzo di settore financials, comune a JPM/MS/C/DB oggi). Il meccanismo è distinto sia da F-020 (attribuzione a ticker sbagliato) sia da F-057 (`FALSE_ENTITY_MATCH` non copre `source_metadata`): qui l'entità è corretta, il rilevamento di rilevanza (`ISSUER_SPECIFIC`) è tecnicamente corretto, e il contenuto è comunque privo di informazione. Nuovo finding, F-066.

**8.3 — Nota su cosa *non* è un difetto, oggi.** Il blocco anti-pyramiding su SNOW (due volte, 16:37 e 16:52) ha impedito un aggiunta di peso mentre il controfattuale 1h era **negativo** (−14,99 $ e −17,99 $): SNOW stava già perdendo terreno intraday dopo il gap d'apertura, e il guard ha evitato una perdita, non causato un miss. È l'inverso esatto della lettura consueta di F-031 (dove il guard blocca denaro sul tavolo): oggi, su questo ticker, ha funzionato nella direzione giusta per puro effetto del timing di mercato, non per merito del meccanismo (il guard non guarda il segno del controfattuale, lo ignora comunque). L'invariante rank/ranking score del ledger S4 (#401) resta pulita: 82 righe esaminate, **0 violazioni**.

---

## Segnalazioni

[F-001] **50/96 simboli watchlist (52,1%) a zero righe `news_log`, valore più alto della finestra osservata dal 07-31.** I due miss NO_NEWS puri sono SAP +3,50% e ARM +3,29%: zero righe, zero segnali per entrambi. Costo registrato = lordo close-to-close × 2.200 $, SAP 77,01 $ + ARM 72,41 $ = **149,42 $**, per confrontabilità con la serie; l'accessibile misurato dal dossier è **−3,25 $ (SAP)** e **+132,54 $ (ARM)** — ARM è il singolo candidato con il maggior denaro potenzialmente sul tavolo dell'intera giornata, e zero dati per vederlo. Faccia lato uscita (§5): **ASML a 10 sedute consecutive** senza una riga (`fonti_osservate_finestra` vuoto su tutta la finestra), a −6,93% dall'ingresso.

[F-012] **Fan-out come unica fonte: quarta+ occorrenza su NOW, e prima giornata con quattro simboli contemporaneamente nella stessa firma.** NOW (`quota_righe_fanout=1,0`, terza sessione consecutiva con questa firma dopo 09-01 e 09-02), SPCX, ORCL e META hanno oggi **zero** righe `ISSUER_SPECIFIC`/`SECTOR_MACRO`: l'unica origine dei loro punteggi è un pezzo macro fan-out (per 3 dei 4, lo stesso articolo, "Wall Street Rallies as Fed's Waller..."). Totale giornata: 134 righe `news_log` per 61 articoli unici, **101 mappature `TAG_UNCONFIRMED` contro 32 `ISSUER_SPECIFIC`** (75,9% non confermate), copertura effective-timely **21,9%** (21/96). Costo `null`: non separabile da F-009, che insiste sugli stessi titoli.

[F-009] **Il gate 0,30 scarta segnali col segno corretto su tre mover forti oggi; solo uno aveva denaro davvero sul tavolo.** NOW (+0,121, scarto 0,179), SPCX (+0,18, scarto 0,12), ORCL (+0,10, scarto 0,20) e TSLA (ensemble 0,277, scarto **0,023** — il più stretto della serie dopo lo 0,019 di TSLA l'08-31) sono tutti sotto gate col segno corretto. Ma solo **NOW ha `accessible_opportunity_usd` positiva (26,39 $)**: SPCX (−32,90 $), ORCL (−23,28 $) e TSLA (−35,29 $) avrebbero perso denaro anche disarmando il gate, perché il movimento era già scontato al primo ciclo eleggibile. Costo registrato **26,39 $** (NOW, unico caso con opportunità reale), congetturale. TSLA ha un secondo profilo distinto in F-056/F-060 (segnale sopra gate ma mai valutato) — non sommare i due: sono facce alternative dello stesso ticker.

[F-031] **L'anti-pyramiding blocca peso su DELL e SNOW, con segno del controfattuale opposto fra i due.** DELL: `SKIP_PYRAMIDING` alle 19:52, sentiment +0,478, controfattuale 1h **+12,89 $** (nozionale inteso 1.997,53 $) — denaro lasciato sul tavolo, coerente col pattern del 09-02. SNOW: due blocchi (16:37, 16:52) con controfattuale 1h **negativo** (−14,99 $, −17,99 $, vedi §8.3) — qui il guard ha evitato una perdita. Costo registrato **12,89 $** (solo DELL; i controfattuali negativi di SNOW non sono un costo). Prima occorrenza della serie con controfattuale a segno misto sullo stesso giorno.

[F-030] **PLTR comprata quando il movimento era già oltre il 100% completo.** BUY 18:37 @ 183,08, `quota_movimento_precedente_al_segnale` **1,055** (`denominatore_degenere=false`): il titolo aveva già superato il proprio massimo di seduta al momento dell'ingresso. Fill sopra il close (182,53): MTM a fine giornata **−4,92 $** (posizione non ancora chiusa al cutoff — costo attribuito, non realizzato). Mediana mobile a 20 giorni di `entry_percentile`: 0,629; oggi PLTR è a 0,802, sopra mediana.

[F-056] **`fetch_signals_for_cycle` lascia TSLA senza alcuna decisione al ciclo delle 19:52, non solo senza fallback valutato.** Verificato con query diretta (non dal log persistente, non disponibile per oggi — vedi nota in testa al report): il segnale fallback 0,468 (19:45:44) e il segnale ensemble precedente 0,221 (19:15:59, ancora nella finestra di 96h) coesistono, ma **nessuno dei due produce una riga in `execution_decisions`** al ciclo successivo. Ogni altro simbolo valutato quel ciclo (30/31) ha una riga. Costo `null`: `net_opportunity_usd` di TSLA è negativa (−35,29 $), quindi il difetto non ha avuto conseguenza economica oggi, a differenza dell'occorrenza dell'08-13 (56,05 $ su NFLX+PLTR).

[F-060] **`NON_CLASSIFICATO` su TSLA oggi, ma il `funnel_v2` più recente lo disambigua correttamente.** Il classificatore causale legacy del dossier (`candidati_miss.causa`) etichetta TSLA `NON_CLASSIFICATO`, lo stesso bucket ambiguo documentato su NFLX/PLTR (08-13) e PLTR (09-02). Novità di oggi: il campo `funnel_v2.righe[].pipeline` — introdotto più di recente nello schema — etichetta correttamente lo stesso caso `FALLBACK_REJECT` con `evidence.score_firmato=0,468`. Il difetto di misura persiste sul campo legacy (che alimenta `cause_del_giorno` e quindi il criterio di falsificazione della domanda 1 della carta), ma esiste già, nello stesso dossier, un campo che non ce l'ha. Costo `null`.

[F-063] **Il calendario earnings è indisponibile per la quarta seduta consecutiva.** `giorno_di_earnings` vale `None` su **1594 intent S4 su 1594** oggi (era 1438/1438 il 09-02, tutto `None` anche l'08-31 e il 09-01). La serie di quattro sedute consecutive a `None` prosegue senza segnali di ripristino. A differenza del 09-02, oggi non ho evidenza che i mover principali siano reazioni a trimestrali (§6), quindi l'impatto pratico della cecità è minore — ma la causa strutturale (calendario non disponibile) non è cambiata. Costo `null`: perdita di capacità osservativa, il costo è la ricorrenza.

[F-066] **Nuovo — un articolo "content-mill" con ticker corretto ma zero contenuto informativo passa `ISSUER_SPECIFIC` e diluisce il segnale a rumore.** GS: "If You Invested $100 In Goldman Sachs Group Stock 15 Years Ago, You Would Have This Much Today", tag `ISSUER_SPECIFIC` corretto (l'articolo è genuinamente su GS, non un'attribuzione errata), punteggio 0,002 — indistinguibile da assenza di segnale. Distinto da F-020 (ticker sbagliato) e F-057 (rilevatore falsa entità non copre `source_metadata`): qui l'entità è giusta e il rilevamento di rilevanza ha funzionato come da design, ma il contenuto stesso non porta informazione su alcun catalizzatore. **Id nuovo giustificato**: nessuno dei 65 finding esistenti copre contenuto correttamente taggato ma strutturalmente vuoto (evergreen/listicle). Costo congetturale **10,54 $** (`net_opportunity_usd` di GS, unico articolo del giorno sul ticker rilevante ai fini del punteggio).

---

*Report generato in sessione autonoma di analisi giornaliera. Nessuna modifica a codice, nessun ordine, nessun worker avviato, nessun commit. Gli unici file scritti sono questo report, `docs/evidence/market_daily.jsonl` e `docs/evidence/findings.json`.*
