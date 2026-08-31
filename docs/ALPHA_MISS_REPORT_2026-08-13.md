# Alpha Miss Report — 2026-08-13

Fonte numerica primaria: `docs/evidence/dossier/2026-08-13.json` (deterministico, Alpaca SIP
`adjustment=all`, schema 2.0, generato il 2026-08-22). Query dirette via `docker exec
alembic-postgres-1 psql` per `trades`, `sentiment_signals`, `execution_decisions`, `news_log`,
`portfolio_cycles`. Equity da Alpaca Trading API (`/v2/account/portfolio/history`). Nessun
ricalcolo dei numeri già presenti nel dossier.

> **Nota di provenienza — backfill.** Questo report ricostruisce la seduta del 2026-08-13, che il
> cron del 08-14 non ha mai scritto (crash a metà sessione dopo la generazione del dossier ma
> prima del report e delle righe di ledger). Il dossier `2026-08-13.json` esiste già (generato il
> 22/08 in un batch di recupero) e viene usato così com'è, schema 2.0 — **precede** il deploy
> `34940df` del 2026-08-29 che introduce `copertura_uscita`: quella chiave non esiste in questo
> dossier (vedi §5) e `s4_intent_events` è vuoto per l'intera giornata (il ledger degli intenti
> comincia a popolarsi dal 2026-08-25, migration 050/051 — vedi `OBSERVATION_CHARTER.md`).

## 1. Executive summary

Seduta a dispersione nella norma (**σ = 2,21%**, dentro la banda 1,5–2,4% osservata nei giorni
adiacenti), **14 dei 96 simboli watchlist oltre ±3% — 11 al rialzo, 3 al ribasso** — su un mercato
moderatamente positivo (SPY +0,70%, QQQ +1,16%). **5 mover su 14 catturati**: WDC (+7,31%), MU
(+4,23%) e INTC (+3,58%) a libro passivamente (rally memoria/storage, prosecuzione del tema del
08-12); SPCX (−3,33%) e CSCO (−8,40%, trimestrale propria con miss sui margini) chiusi in giornata
con perdita netta. **9 mancati**, causa dominante **NO_NEWS (4)**: ADBE, CRM, TMUS, RDDT. Il fatto
nuovo della giornata è un **meccanismo**, non un singolo miss: **NFLX e PLTR avevano entrambi un
segnale sopra gate (0,36 e 0,385) generato in giornata, ma la query che alimenta S4
(`fetch_signals_for_cycle`) non lo ha mai visto**, perché preferisce sempre l'ultimo segnale
*non-fallback* nella finestra di 96h anche quando è più vecchio e più debole del segnale
*fallback* appena arrivato — vedi §8 [F-056]. Costo verificato basso oggi (**$56,05** accessibili
su entrambi), perché gran parte del movimento era già avvenuta prima del ciclo eleggibile. 24 cicli
portfolio, cadenza 15 min, nessun gap. Libro: NAV **$110.463,81** (**+$3,77** sulla seduta, riga
Alpaca del 14/08 per l'allineamento noto in [F-053]), realizzato **−$66,17** (S1 −$18,97 su CSCO,
S4 −$47,20 su SPCX/META), MTM del book aperto **+$69,94**.

## 2. Tabella rendimenti completa (96 simboli)

Fonte: dossier, Alpaca SIP `adjustment=all`, close vs close precedente. Nessun simbolo senza barre
(`simboli_senza_dati: []`). Soglia mover `soglia_mover = 0.03` (quella del dossier).

| Simbolo | Return % | Catturato |
|---|---:|---|
| WDC | +7.31% | **Sì** — a libro (S1) |
| NFLX | +5.43% | No — **miss (FILTERED*)** |
| HOOD | +4.70% | No — **miss (THIN_NEUTRAL / OFF_TOPIC_NON_DECIDIBILE)** |
| PLTR | +4.66% | No — **miss (FILTERED*)** |
| ADBE | +4.54% | No — **miss (NO_NEWS)** |
| MU | +4.23% | **Sì** — a libro (S1) |
| CRM | +4.16% | No — **miss (NO_NEWS)** |
| TSLA | +3.80% | No — **miss (THIN_NEUTRAL / BELOW_GATE)** |
| INTC | +3.58% | **Sì** — a libro (S4) |
| TMUS | +3.53% | No — **miss (NO_NEWS)** |
| RDDT | +3.04% | No — **miss (NO_NEWS)** |
| CMCSA | +2.79% | — sotto soglia |
| META | +2.78% | — tradato oggi (S4, ingresso e chiusura stessa seduta), sotto soglia |
| VZ | +2.64% | — sotto soglia |
| SAP | +2.51% | — sotto soglia |
| ARM | +2.49% | — a libro (S1), sotto soglia |
| MRVL | +2.35% | — a libro (S1), sotto soglia |
| NOK | +2.33% | — a libro (S1), sotto soglia |
| PANW | +2.32% | — a libro (S1), sotto soglia |
| ASML | +2.09% | — a libro (S1), sotto soglia |
| DELL | +2.07% | — a libro (S1), sotto soglia |
| MRK | +1.98% | — a libro (S1), sotto soglia |
| ORCL | +1.92% | — sotto soglia |
| PFE | +1.86% | — sotto soglia |
| NOW | +1.85% | — sotto soglia |
| NKE | +1.78% | — sotto soglia |
| V | +1.68% | — sotto soglia |
| SNOW | +1.54% | — a libro (S1), sotto soglia |
| DIS | +1.53% | — sotto soglia |
| ROKU | +1.51% | — a libro (S1), sotto soglia |
| T | +1.36% | — sotto soglia |
| MA | +1.31% | — sotto soglia |
| COST | +1.29% | — sotto soglia |
| QQQ | +1.16% | — a libro (S1), sotto soglia |
| INFY | +1.06% | — sotto soglia |
| QCOM | +1.05% | — sotto soglia |
| XLK | +1.01% | — a libro (S1), sotto soglia |
| AAPL | +1.00% | — a libro (S1), sotto soglia |
| MSFT | +0.91% | — sotto soglia |
| ERIC | +0.88% | — sotto soglia |
| C | +0.84% | — a libro (S1), sotto soglia |
| ABBV | +0.83% | — a libro (S1), sotto soglia |
| GOOGL | +0.82% | — a libro (S1), sotto soglia |
| SOXX | +0.76% | — a libro (S1), sotto soglia |
| PBR | +0.73% | — a libro (S1), sotto soglia |
| SPY | +0.70% | — a libro (S1), sotto soglia |
| NVO | +0.70% | — sotto soglia |
| XLF | +0.59% | — a libro (S1), sotto soglia |
| CVX | +0.56% | — a libro (S1), sotto soglia |
| NVDA | +0.54% | — sotto soglia |
| GS | +0.52% | — a libro (S1), sotto soglia |
| IBM | +0.49% | — sotto soglia |
| JNJ | +0.47% | — a libro (S1), sotto soglia |
| F | +0.43% | — sotto soglia |
| AVGO | +0.43% | — sotto soglia |
| MS | +0.34% | — a libro (S1), sotto soglia |
| TSM | +0.31% | — a libro (S1), sotto soglia |
| SONY | +0.30% | — sotto soglia |
| IWM | +0.26% | — a libro (S1), sotto soglia |
| TM | +0.26% | — sotto soglia |
| PG | +0.12% | — sotto soglia |
| SBUX | +0.06% | — a libro (S1), sotto soglia |
| XLE | +0.05% | — a libro (S1), sotto soglia |
| AMD | +0.02% | — a libro (S1), sotto soglia |
| XLV | -0.04% | — a libro (S1), sotto soglia |
| CAT | -0.12% | — a libro (S1), sotto soglia |
| AXP | -0.12% | — sotto soglia |
| BIDU | -0.15% | — sotto soglia |
| SHEL | -0.17% | — a libro (S1), sotto soglia |
| BP | -0.21% | — sotto soglia |
| WMT | -0.25% | — sotto soglia |
| DB | -0.34% | — sotto soglia |
| UBS | -0.37% | — a libro (S1), sotto soglia |
| BA | -0.38% | — sotto soglia |
| GM | -0.43% | — a libro (S1), sotto soglia |
| HD | -0.50% | — sotto soglia |
| JPM | -0.57% | — a libro (S1), sotto soglia |
| BRK.B | -0.60% | — sotto soglia |
| MMM | -0.61% | — a libro (S1), sotto soglia |
| XOM | -0.71% | — a libro (S1), sotto soglia |
| AZN | -0.79% | — sotto soglia |
| AMZN | -0.80% | — sotto soglia |
| WFC | -0.92% | — sotto soglia |
| LLY | -0.92% | — a libro (S1), sotto soglia |
| BAC | -1.11% | — a libro (S1), sotto soglia |
| TXN | -1.14% | — a libro (S1), sotto soglia |
| MCD | -1.25% | — sotto soglia |
| GE | -1.28% | — a libro (S1), sotto soglia |
| UNH | -1.61% | — a libro (S1), sotto soglia |
| VALE | -2.06% | — a libro (S1), sotto soglia |
| BABA | -2.44% | — sotto soglia |
| AMAT | -2.48% | — a libro (S1), sotto soglia |
| RIO | -2.99% | — a libro (S1), sotto soglia |
| SPCX | -3.33% | **Sì** — tradato oggi (S4, chiuso in perdita) |
| JD | -7.31% | No — **miss (THIN_NEUTRAL / OFF_TOPIC_NON_DECIDIBILE)** |
| CSCO | -8.40% | **Sì** — tradato oggi (S1, chiuso in perdita) |

`*` = categoria FILTERED assegnata da questa analisi; il dossier classifica entrambi
`NON_CLASSIFICATO` (`max_score_own` supera il gate). Vedi §3 e §8.

## 3. Miss classificati

Nove candidati, tutti al rialzo tranne JD, tutti long-actionable (nessuno era a libro). `costo
lordo` = `|close-to-close| × $2.200` (slot S4 = 2% di un NAV da ~$110k); `accessibile` =
opportunità dal primo ciclo eleggibile alla chiusura, entrambi dal blocco `opportunity_v2` del
dossier (v2.0, congetturale).

| Simbolo | Return | Categoria | Evidenza | Costo lordo | Accessibile |
|---|---:|---|---|---:|---:|
| ADBE | +4,54% | **NO_NEWS** | Zero righe in `news_log`. Nessun segnale, nessun intent. | $99,82 | +$62,65 |
| CRM | +4,16% | **NO_NEWS** | Zero righe in `news_log`. | $91,61 | +$62,87 |
| TMUS | +3,53% | **NO_NEWS** | Zero righe in `news_log`. | $77,63 | +$40,25 |
| RDDT | +3,04% | **NO_NEWS** | Zero righe in `news_log`. | $66,95 | +$41,39 |
| JD | −7,31% | **THIN_NEUTRAL** (`OFF_TOPIC_NON_DECIDIBILE`) | 2 righe, entrambe `source_metadata` (snippet troncato, non ispezionabile): trascrizione della call sugli utili Q2 (14:01) e un pezzo whale-alert multi-ticker (19:15, 4 simboli). Score **0,000** su entrambe. Mover al ribasso, libro long-only: anche con segno corretto non avrebbe generato un ordine (coerente con [F-040]). | $160,77 | $0,00 (long-only, down, non detenuto) |
| HOOD | +4,70% | **THIN_NEUTRAL** (`OFF_TOPIC_NON_DECIDIBILE`) | 1 articolo, `source_metadata`: *«Why Is Robinhood Stock Surging on Thursday?»* (15:45), score **+0,013**. Snippet troncato, non ispezionabile per rilevanza. | $103,38 | +$42,34 |
| TSLA | +3,80% | **THIN_NEUTRAL** (`BELOW_GATE`) | 5 righe in giornata, score max **|−0,15|** (16:00, fallback, *«Gary Black Says Tesla Needs to Work on Branding»*) — sotto gate 0,30 e di segno **opposto** al movimento, ma sulla magnitudine irrilevante. Le altre 4 righe sono fan-out o score nullo. | $83,63 | +$37,31 |
| NFLX | +5,43% | **FILTERED** (dossier: `NON_CLASSIFICATO`) | Segnale id 7610, 17:00:26 UTC, **score 0,36 > gate 0,30**, `single:glm-5.2:cloud`, `fallback_used=true`, da *«Bill Ackman Bets on Netflix as the Chart Shows Early Signs of a Rebound»*. **Mai valutato**: `execution_decisions` per NFLX si ferma alle 15:07:10 (ultimo `SKIP_THRESHOLD` sul vecchio segnale ensemble id 7510, score 0,138, 14:15). Nessuna riga dopo. Causa verificata in §8 [F-056]. | $119,47 | +$19,57 |
| PLTR | +4,66% | **FILTERED** (dossier: `NON_CLASSIFICATO`) | Segnale id 7613, 17:15:14 UTC, **score 0,385 > gate 0,30**, `single:gpt-oss:20b-cloud`, `fallback_used=true`, da *«Palantir Shares Edge Higher Thursday»*. **Zero righe in `execution_decisions` per PLTR in tutta la giornata** — nessun `SKIP_THRESHOLD`, nessun `BUY`, nessuna riga. Causa verificata in §8 [F-056]. | $102,51 | +$36,48 |
| | | | **Totale** | **$905,77** | **+$300,86** |

## 4. Titoli catturati: esito

<!-- alpha-miss-book:start -->
<!-- alpha-miss-book-manifest: {"schema":1,"ingressi":["META"],"chiusure":["SPCX","CSCO","META"]} -->

Dati deterministici dal dossier; la prosa seguente li annota e non li sostituisce.

| Tipo | Simbolo | Strategia | Ora UTC | Prezzo | Quantità | P&L netto | Motivo / qualità |
|---|---|---|---|---:|---:|---:|---|
| IN | META | S4 | 16:37 | $587.0700 | 3.0442 | — | percentile 46.66%; denominatore intraday valido |
| OUT | SPCX | S4 | — | $142.1508 | 8.2946 | −$54.02 | portfolio_sell |
| OUT | CSCO | S1 | — | $112.4600 | 6.8185 | −$18.97 | sentiment_reversal |
| OUT | META | S4 | — | $589.4300 | 3.0442 | +$6.82 | portfolio_sell |
<!-- alpha-miss-book:end -->

<!-- il blocco IN/OUT deterministico viene inserito qui dallo script di riconciliazione -->

**WDC (+7,31%)** — a libro da S1 dal 21/07 (2,981 az.). Cattura passiva: articolo unico del giorno
alle 17:05, *«Chip Stocks Power S&P 500 to Record Highs, SanDisk Soars 15%»* (score +0,12, fallback,
fan-out), prosecuzione del tema memoria del 08-12 (allora +3,69%). Nessuna decisione attiva.

**MU (+4,23%)** — a libro da S1 dal 28/07 (0,398 az.). Cattura passiva, stesso tema memoria.

**INTC (+3,58%)** — a libro da S4 dal 12/08 (0,035 az., `signal_id` 7450). Cattura passiva.

**SPCX (−3,33%)** — S4, chiuso alle ~ore indicate dal blocco book: `exit_reason=portfolio_sell`,
tenuto 19,5 ore, **net_pnl −$54,02**. `drift_post_uscita −$7,14`: il prezzo ha continuato a scendere
dopo la vendita, quindi l'uscita ha evitato una perdita maggiore, non l'ha causata.

**CSCO (−8,40%)** — S1, chiuso via `sentiment_reversal` (score −0,520 < soglia −0,35 alle 17:52:13),
tenuto quasi 700 ore (posizione legacy). **net_pnl −$18,97**. Catalizzatore proprio: trimestrale
Q4 con «margin static sinks share price» (16:12, score −0,52, da *«Gold Down 2%; Cisco Shares
Tumble After Q4 Results»*), dopo una mattinata di copertura mista/positiva (0,60 e 0,21 nelle prime
ore). Segno e tempismo dell'uscita corretti: `drift_post_uscita +$6,89` (recupero parziale dopo la
vendita, ma non abbastanza da invertire il segno della perdita).

**META (+2,78%, sotto soglia)** — S4, ingresso 16:37 (percentile 0,467, sotto la mediana mobile a
20g di 0,625) e uscita 1,75 ore dopo: **net_pnl +$6,82**. Se tenuta a fine seduta, l'MTM sarebbe
stato **+$24,05** (`drift_post_uscita +$16,86`): il round-trip nella stessa seduta lascia **~$17,23
sul tavolo**, stessa forma di [F-013] — vedi §8, occorrenza registrata.

## 5. Cecità lato uscita

**Non misurabile su questo dossier.** `docs/evidence/dossier/2026-08-13.json` è schema 2.0,
generato il 2026-08-22 — **precede** il deploy `34940df` (2026-08-29) che introduce la chiave
`copertura_uscita` (schema 2.5→2.6). La chiave è assente dal documento, non popolata a `null`: per
la regola di discontinuità registrata in `OBSERVATION_CHARTER.md` («i dossier fino al
2026-08-27.json non hanno il campo … non misurato, non zero»), questo giorno **non entra** nella
serie di `copertura_uscita` e non va letto come "nessuna posizione cieca". Rigenerare il dossier
con lo script corrente esporrebbe il campo ma userebbe fonti live (prezzi/news correnti) fuori
scope per un backfill puramente storico: non fatto qui.

## 6. Pattern osservato

**Parzialmente chiaro: due pattern distinti, non uno.** Il primo è una **prosecuzione**, non un
evento nuovo — WDC (+7,31%), MU (+4,23%) e INTC (+3,58%) continuano il tema memoria/storage/
semiconduttori AI-adiacenti già dominante il 08-12 (allora DELL +9,87%, WDC +3,69%, MU +4,92%,
INTC +3,32%), qui rinforzato da un secondo giorno di SanDisk +15%. Tutti e tre erano già a libro
prima di oggi: nessuna decisione attiva li ha catturati, li ha solo tenuti.

Il secondo è **idiosincratico, senza tema comune**: CSCO −8,40% (trimestrale propria, miss sui
margini), NFLX +5,43% (una scommessa di Bill Ackman, riportata da più articoli), JD −7,31%
(trimestrale propria), PLTR +4,66% e HOOD +4,70% (articoli single-name generici, «stock surging/
edge higher», senza causa esplicita nel testo scorato), ADBE/CRM/TMUS/RDDT (zero news, nessuna
causa osservabile nei dati raccolti). SPY +0,70% e QQQ +1,16% confermano un mercato ampiamente
positivo ma senza un singolo catalizzatore macro dominante. **Non c'è un settore o un evento unico
che leghi i nove miss**: la causa dominante (NO_NEWS, 4/9) è una lacuna di copertura, non un
segnale comune mancato.

## 7. Pattern ricorrenti vs altri report

Confronto con `docs/ALPHA_MISS_REPORT_2026-08-{10,11,12,14,17}.md` e con le righe adiacenti di
`docs/evidence/market_daily.jsonl`.

- **Dispersione nella norma**: σ 2,21% è dentro la banda stretta 1,54–2,37% dei quattro giorni
  intorno (08-11: 1,54%, 08-12: 2,37%, 08-14: 2,18%, 08-17: 2,12%) — non è un giorno anomalo come
  il 08-27 (3,49%) o il 04-08 (4,40%).
- **NO_NEWS ancora causa dominante**: 4/9 oggi, coerente con la ricorrenza già documentata in
  [F-001] su quasi tutte le sedute della finestra. Copertura: 41/96 simboli a zero righe, nella
  parte bassa della banda osservata (41–55 nelle sedute vicine) — non un peggioramento.
- **Tema memoria/storage ricorrente**: seconda seduta consecutiva (dopo il 08-12) in cui lo stesso
  cluster di nomi (WDC/MU/INTC, con DELL/AMAT/SOXX come vicini) guida il rialzo — sempre catturato
  solo *passivamente* tramite posizioni già aperte, mai da una decisione S4 attiva sullo stesso
  giorno del movimento.
- **Prima occorrenza verificata del meccanismo fallback-vs-ensemble** [F-056]: NFLX e PLTR sono i
  primi casi in cui si è potuto dimostrare, con la query SQL sotto mano, che un segnale fresco
  sopra gate non è mai stato valutato perché un segnale ensemble più vecchio (fino a un giorno)
  ma più debole occupava lo slot "distinct on symbol". Il costo di oggi è basso ($56,05
  accessibili), ma il meccanismo è strutturale e non specifico del giorno: si applica ogni volta
  che un simbolo ha sia un segnale ensemble recente-ma-vecchio sia un nuovo fallback forte nella
  stessa finestra di 96 ore. Non è la stessa cosa di [F-023] (che descrive un segnale forte
  sovrascritto da uno debole generato *pochi secondi dopo*, entrambi comunque visibili in
  `execution_decisions`): qui il segnale forte **non produce mai nessuna riga**, nemmeno di skip —
  è invisibile, non solo battuto.
- **Churn intraday su META**: nona occorrenza registrata di [F-013] nella finestra, la prima su
  META. Pattern invariato: uscita entro 2 ore, segno positivo, valore lasciato sul tavolo.

## 8. Bug sospetti (nessuna proposta di fix)

**[F-056] — nuovo — Un segnale fallback sopra gate può non essere mai valutato da S4 se esiste un
segnale ensemble più vecchio (fino a 96h) nella stessa finestra, indipendentemente da quale sia più
recente o più forte.** `PostgreSQLStore.fetch_signals_for_cycle` (`src/store/pg_store.py:2763-2788`)
usa `SELECT DISTINCT ON (ss.symbol) ... ORDER BY ss.symbol, ss.fallback_used ASC, ss.generated_at
DESC`: per ogni simbolo viene scelta la riga con `fallback_used=false` più recente, **e solo se non
ne esiste nessuna** si scende ai segnali `fallback_used=true`. Verificato su due casi indipendenti
del 2026-08-13:

- **NFLX**: id 7510 (2026-08-13 14:15, score 0,138, ensemble) resta nella finestra di 96h per tutta
  la giornata e oltre. Alle 17:00:26 arriva id 7610 (score **0,36**, sopra gate, `single:glm-5.2:
  cloud`, `fallback_used=true`) — ma la query continua a restituire id 7510, perché
  `fallback_used ASC` lo mette sempre prima. `execution_decisions` per NFLX si ferma infatti alle
  15:07:10 (4 righe `SKIP_THRESHOLD` sul vecchio score 0,138) e **non produce più nulla** dopo,
  nonostante 19 cicli portfolio successivi.
- **PLTR**: id 7390 (2026-08-12 16:00, score −0,012, ensemble) resta in finestra. Alle 17:15:14 del
  13/08 arriva id 7613 (score **0,385**, sopra gate, `single:gpt-oss:20b-cloud`, `fallback_used=
  true`) — sistematicamente battuto da 7390. Il risultato pratico è peggiore che per NFLX: la riga
  "vincente" (7390, score 0,012) è sotto anche il prefiltro `min_score=0,10` di S4, quindi non
  entra nemmeno in `signals_df`, e la riga "stale" viene scartata da `_filter_stale_signals`
  (>4h) senza generare `SKIP_STALE` (soglia di materialità `|score|>=min_score` non raggiunta,
  `src/workers/portfolio_scheduler.py:3534-...`). **Risultato: zero righe in `execution_decisions`
  per PLTR in tutta la giornata del 13/08** — verificato via query diretta, unico giorno su 22 con
  dati storici in cui questo accade per PLTR. Il segnale 0,385 riappare solo il 14/08 quando un
  nuovo segnale ensemble (score 0,000) prende il posto di 7390 nello stesso meccanismo, e da lì
  in poi PLTR torna a produrre `SKIP_THRESHOLD` regolari — sul nuovo segnale, non su 7613.

Il commento sul design (`fetch_signals_for_cycle` docstring) dichiara l'intento — «la lettura
ensemble più recente è preferita a un fallback debole, così un fallback debole non sovrascrive una
lettura ensemble forte» — ma l'implementazione non confronta *forza* né *recency* fra i due rami:
preferisce sempre e comunque il ramo non-fallback, anche quando è più vecchio e più debole del
fallback. Il guard `_filter_fallback_signals` (linea 1199, pensato per impedire che un BUY riposi
su un segnale fallback, commento #108) non entra mai in gioco per questi due casi: la riga
fallback non arriva nemmeno a quello stadio, perché la query SQL l'ha già scartata a monte.
Costo verificato oggi: **$56,05** (accessibile, NFLX $19,57 + PLTR $36,48) — basso perché su
entrambi i simboli gran parte del movimento era già avvenuta prima del primo ciclo eleggibile
dopo il segnale. Il costo potenziale su un caso con più movimento residuo al momento del segnale
sarebbe interamente quello del gross (NFLX $119,47 + PLTR $102,51 = $221,99), cioè quasi 4× quello
osservato oggi. Non propongo fix: registrazione di evidenza secondo la carta di osservazione.

**[F-013] — occorrenza — Churn intraday su META (nuovo simbolo per questo finding).** Vedi §4.
BUY 16:37 → SELL ~18:22 (1,75h), net_pnl +$6,82 contro un MTM-a-EOD di +$24,05 se tenuta: **$17,23**
lasciati sul tavolo dal round-trip nella stessa seduta. Stesso meccanismo già registrato (nessuna
banda fra gate d'ingresso 0,30 e uscita 0).

**[F-001] — occorrenza — Copertura news bassa.** 41/96 simboli (43%) a zero righe in `news_log` il
13/08. Quattro dei nove miss del giorno sono NO_NEWS puri: ADBE (+4,54%), CRM (+4,16%), TMUS
(+3,53%), RDDT (+3,04%) — zero righe in `news_log`, zero in `sentiment_signals`, zero in
`execution_decisions`. Costo stimato con size S4 tipica $2.200 sul return pieno: 99,82+91,61+
77,63+66,95 = **$336,01**.

## 9. Igiene operativa / Libro

24 cicli portfolio, 14:07:00–19:52:00 UTC, cadenza esatta 15 minuti, **nessun gap**. 556 righe in
`execution_decisions` (540 `SKIP_THRESHOLD`, 8 `SKIP_PYRAMIDING`, 3 `SELL`, 3 `SKIP_FALLBACK`,
1 `BUY`, 1 `SKIP_STALE`). 193 righe in `sentiment_signals` da 193 righe `news_log`, 55/193 (28,5%)
in fallback.

| Voce | Valore | Fonte |
|---|---:|---|
| NAV chiusura 13/08 | **$110.463,81** | Alpaca `portfolio/history`, riga timbrata 2026-08-14T00:00Z (allineamento [F-053]: quella riga porta la chiusura del 13, non del 14) |
| P&L seduta | **+$3,77** | idem |
| Realizzato | **−$66,17** | `trades` con `exit_time::date = 2026-08-13`, 3 uscite (SPCX −$54,02, CSCO −$18,97, META +$6,82) |
| di cui S1 | −$18,97 | CSCO, `sentiment_reversal` |
| di cui S4 | −$47,20 | SPCX `portfolio_sell` −$54,02 + META `portfolio_sell` +$6,82 |
| MTM book aperto | **+$69,94** | P&L seduta − realizzato (non verificato indipendentemente sulle quantità broker) |
| Ingressi | 1 | META, S4, 16:37 UTC |
| Chiusure | 3 | SPCX, CSCO, META |
