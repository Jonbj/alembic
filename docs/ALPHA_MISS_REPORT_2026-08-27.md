# Alpha Miss Report — 2026-08-27

Fonte numerica primaria: `docs/evidence/dossier/2026-08-27.json` (deterministico, Alpaca SIP
`adjustment=all`). Query dirette via `docker exec alembic-postgres-1 psql` per `trades`,
`sentiment_signals`, `execution_decisions`, `news_log`, `s4_intent_events`. Equity da Alpaca
Trading API (`/v2/account/portfolio/history`). Nessun ricalcolo dei numeri già presenti nel dossier.

> **Nota di provenienza — il dossier non si è generato da solo (terza volta consecutiva).**
> `uv run python scripts/alpha_miner_dossier.py 2026-08-27` è fallito con
> `ERROR: column reference "decision_at" is ambiguous` e ha stampato `dossier scritti: 0`
> con exit code 0. Causa invariata dal 08-25: `_s4_entry_intents`
> (`scripts/alpha_miner_dossier.py:835-836`) usa `decision_at` non qualificato mentre il join
> espone quella colonna sia in `s4_candidate_population` sia in `s4_intent_events`. Il dossier di
> oggi è stato prodotto da una **copia usa-e-getta in `/tmp`** con le sole due referenze
> qualificate (`intent.decision_at`) e `PROJECT_DIR` assoluto; ogni altro numero viene dallo stesso
> codice. **Il repo non è stato modificato.** Vedi §7 [F-044].

## 1. Executive summary

Giornata a dispersione eccezionale: **σ = 3,49%**, la seconda più alta delle 18 sedute osservate
(mediana della serie 2,22%), con **14 dei 96 simboli watchlist oltre ±3% — 13 al rialzo e 1 al
ribasso** su un mercato solo tiepidamente positivo (SPY +0,66%, QQQ +1,37%). Il catalizzatore è
uno solo: la trimestrale **Salesforce**, con CRM **+22,58%**, che ha trascinato tutto il complesso
enterprise-software/AI (NOW +10,04%, ADBE +5,73%, PANW +12,83%, SNOW +4,36%, SAP +4,48%) sopra la
scia della trimestrale NVIDIA della sera prima sui semi (NVDA +8,74%, AVGO +4,49%, INTC +4,36%).
**6 mover su 14 sono stati intercettati** — CRM e NVDA tradati attivamente da S4, PANW/SNOW/XLK/GE
già a libro da S1 — e **8 sono stati mancati**: 4 `NO_NEWS` (PLTR, SAP, BIDU, IBM), 3
`THIN_NEUTRAL` (ADBE, AVGO, INTC), 1 `FILTERED` (NOW). **Causa prevalente: NO_NEWS**, con
**53 simboli su 96 a zero righe in `news_log`**. Il fatto nuovo della giornata non è però un miss
ma il **meccanismo** del solo `FILTERED`: NOW ha prodotto un segnale a **+0,363, sopra il gate
0,30**, ed è stato tagliato per **`RANK_OUTSIDE_TOP_N` in 6 cicli consecutivi** perché i 5 slot
top-N erano occupati da nomi **già detenuti** — fra cui DELL e CSCO con segnali del **25 agosto**,
vecchi di due sedute — che poi si sono tutti risolti in `SKIP_PYRAMIDING`, cioè zero ordini. Va
detto subito che **oggi questo non è costato nulla**: l'intero movimento intraday di NOW
(130,48 → 138,26) era già avvenuto **prima del primo ciclo delle 14:07 UTC**, e l'opportunità
accessibile vale **+$2,71**. 24 cicli portfolio, nessun gap oltre 15 minuti. Book: NAV
**110.041,95** (**+76,90** sulla seduta), realizzato **+20,40** (tutto S4; S1 a zero), MTM del
book aperto **+56,50**.

## 2. Tabella rendimenti completa (96 simboli)

Fonte: dossier, Alpaca SIP `adjustment=all`, close vs close precedente. Nessun simbolo senza barre
(`simboli_senza_dati: []`). Soglia mover `soglia_mover = 0.03`, quella del dossier: la tengo perché
è la stessa delle 18 sedute già in serie e cambiarla renderebbe il confronto storico inutilizzabile.

| Simbolo | Return % | Catturato |
|---|---:|---|
| CRM | +22.58% | **Sì** — tradato oggi (S4 ×3 (14:22/17:07/19:37)) |
| PANW | +12.83% | **Sì** — a libro (S1) |
| NOW | +10.04% | No — **miss (FILTERED)** |
| NVDA | +8.74% | **Sì** — tradato oggi (S4 14:07→16:52) |
| ADBE | +5.73% | No — **miss (THIN_NEUTRAL)** |
| PLTR | +4.75% | No — **miss (NO_NEWS)** |
| AVGO | +4.49% | No — **miss (THIN_NEUTRAL)** |
| SAP | +4.48% | No — **miss (NO_NEWS)** |
| INTC | +4.36% | No — **miss (THIN_NEUTRAL)** |
| SNOW | +4.36% | **Sì** — a libro (S1) |
| BIDU | +3.95% | No — **miss (NO_NEWS)** |
| IBM | +3.88% | No — **miss (NO_NEWS)** |
| XLK | +3.16% | **Sì** — a libro (S1) |
| PBR | +2.76% | — a libro (S1), sotto soglia |
| TSLA | +2.60% | **Sì** — tradato oggi (S4 19:37), sotto soglia |
| TSM | +2.30% | — a libro (S1), sotto soglia |
| ORCL | +2.06% | — sotto soglia |
| SOXX | +1.95% | — a libro (S1), sotto soglia |
| TXN | +1.82% | — a libro (S1), sotto soglia |
| DELL | +1.82% | — a libro (S1), sotto soglia |
| INFY | +1.80% | — sotto soglia |
| MSFT | +1.75% | — sotto soglia |
| NOK | +1.73% | — a libro (S1), sotto soglia |
| ARM | +1.65% | — a libro (S1), sotto soglia |
| QQQ | +1.37% | — a libro (S1), sotto soglia |
| HOOD | +1.12% | — sotto soglia |
| VALE | +0.99% | — a libro (S1), sotto soglia |
| SPCX | +0.89% | — sotto soglia |
| SPY | +0.66% | — a libro (S1), sotto soglia |
| QCOM | +0.65% | — sotto soglia |
| AMAT | +0.54% | — a libro (S1), sotto soglia |
| MS | +0.36% | — a libro (S1), sotto soglia |
| AAPL | +0.36% | — a libro (S1), sotto soglia |
| F | +0.36% | — sotto soglia |
| IWM | +0.29% | — a libro (S1), sotto soglia |
| ERIC | +0.20% | — sotto soglia |
| TM | +0.08% | — sotto soglia |
| RIO | +0.08% | — a libro (S1), sotto soglia |
| GS | +0.04% | — a libro (S1), sotto soglia |
| GM | -0.17% | — a libro (S1), sotto soglia |
| CSCO | -0.19% | — a libro (S4), sotto soglia |
| SONY | -0.21% | — sotto soglia |
| CVX | -0.22% | — a libro (S1), sotto soglia |
| XLE | -0.22% | — sotto soglia |
| BRK.B | -0.24% | — sotto soglia |
| UBS | -0.29% | — a libro (S1), sotto soglia |
| WFC | -0.31% | — sotto soglia |
| MU | -0.32% | — a libro (S1), sotto soglia |
| BP | -0.38% | — sotto soglia |
| NKE | -0.39% | — sotto soglia |
| GOOGL | -0.39% | — a libro (S1), sotto soglia |
| DB | -0.40% | — sotto soglia |
| SHEL | -0.45% | — a libro (S1), sotto soglia |
| AXP | -0.59% | — sotto soglia |
| CAT | -0.60% | — a libro (S1), sotto soglia |
| ASML | -0.61% | — a libro (S1), sotto soglia |
| JPM | -0.64% | — a libro (S1), sotto soglia |
| MMM | -0.65% | — a libro (S1), sotto soglia |
| XLF | -0.65% | — a libro (S1), sotto soglia |
| C | -0.66% | — a libro (S1), sotto soglia |
| META | -0.87% | — sotto soglia |
| AMD | -0.89% | — a libro (S1), sotto soglia |
| RDDT | -0.91% | — sotto soglia |
| JD | -0.97% | — sotto soglia |
| PFE | -0.99% | — sotto soglia |
| TMUS | -1.04% | — sotto soglia |
| BA | -1.04% | — sotto soglia |
| AZN | -1.05% | — sotto soglia |
| V | -1.10% | — sotto soglia |
| XOM | -1.11% | — a libro (S1), sotto soglia |
| LLY | -1.12% | — a libro (S1), sotto soglia |
| MA | -1.13% | — sotto soglia |
| XLV | -1.13% | — a libro (S1), sotto soglia |
| SBUX | -1.13% | — a libro (S1), sotto soglia |
| PG | -1.28% | — sotto soglia |
| WDC | -1.47% | — a libro (S4), sotto soglia |
| ROKU | -1.48% | — a libro (S1), sotto soglia |
| UNH | -1.49% | — a libro (S1), sotto soglia |
| MRVL | -1.49% | — a libro (S1), sotto soglia |
| VZ | -1.51% | — sotto soglia |
| AMZN | -1.54% | — sotto soglia |
| JNJ | -1.57% | — a libro (S1), sotto soglia |
| WMT | -1.64% | — sotto soglia |
| T | -1.70% | — sotto soglia |
| BAC | -1.70% | — a libro (S1), sotto soglia |
| ABBV | -1.81% | — a libro (S1), sotto soglia |
| HD | -1.86% | — sotto soglia |
| NVO | -1.97% | — sotto soglia |
| NFLX | -1.99% | — sotto soglia |
| COST | -2.24% | — sotto soglia |
| MRK | -2.33% | — a libro (S1), sotto soglia |
| DIS | -2.56% | — sotto soglia |
| MCD | -2.57% | — sotto soglia |
| CMCSA | -2.90% | — sotto soglia |
| BABA | -2.94% | — sotto soglia |
| GE | -3.29% | **Sì** — a libro (S1) |

## 3. Miss classificati

Otto candidati, tutti al rialzo, tutti long-actionable (nessuno era a libro). `costo lordo` =
`|close-to-close| × $2.200` (slot S4 = 2% di un NAV da ~$110k); `accessibile` = opportunità dal
primo ciclo eleggibile alla chiusura, entrambi dal blocco `opportunity_v2` del dossier.

| Simbolo | Return | Categoria | Evidenza | Costo lordo | Accessibile |
|---|---:|---|---|---:|---:|
| NOW | +10,04% | **FILTERED** | Segnale 9146 alle 17:30 UTC, **+0,363 > gate 0,30**, ensemble pieno, articolo issuer-specific *«ServiceNow Stock Jumps on Enterprise AI Momentum»*. `s4_intent_events`: `RANK_OUTSIDE_TOP_N` (rank 8) alle 17:37/17:52/18:07/18:22/18:37/18:52, poi `SKIP_ENTRY_FRESHNESS` da 19:07. Nessuna riga in `execution_decisions` dopo le 16:07. | $220,87 | **+$2,71** |
| ADBE | +5,73% | **THIN_NEUTRAL** | Un solo articolo, alle 18:46 UTC: *«Why Is Adobe Stock Surging on Thursday?»* — corpo esplicitamente rialzista («trading higher Thursday following quarterly earnings results from Salesforce»). Scorato **+0,060** da `single:gpt-oss:20b-cloud`, `fallback_used=true`, conf. 0,400: cade dentro la finestra di degrado ensemble delle 18:00 UTC (6 ensemble pieni su 20). | $126,14 | −$5,16 |
| PLTR | +4,75% | **NO_NEWS** | Zero righe in `news_log`. Nessun segnale, nessun intent. | $104,48 | +$37,98 |
| AVGO | +4,49% | **THIN_NEUTRAL** | Un articolo alle 14:00 UTC, issuer-specific, ensemble pieno: *«What's Going On With Broadcom Stock Thursday?»* — «rises nearly 2% premarket following strong NVIDIA earnings». Scorato **+0,230**, segno corretto, sotto gate 0,30 → 6 `SKIP_THRESHOLD` consecutivi. | $98,68 | +$35,99 |
| SAP | +4,48% | **NO_NEWS** | Zero righe in `news_log`, benché il catalizzatore (CRM) fosse l'evento del giorno. | $98,63 | +$35,07 |
| INTC | +4,36% | **THIN_NEUTRAL** | Articolo issuer-specific alle 16:31: *«Why Is Intel Stock Surging on Thursday?»* → **+0,228**, sotto gate. Poi **3 articoli fan-out** (17:02, 18:45, 19:15) scorati **0,000** sovrascrivono il riferimento: da 17:07 in poi `execution_decisions` motiva lo skip con «score 0.000». | $95,99 | +$31,50 |
| BIDU | +3,95% | **NO_NEWS** | Zero righe in `news_log`. | $86,81 | +$8,89 |
| IBM | +3,88% | **NO_NEWS** | Zero righe in `news_log`. | $85,37 | +$22,29 |
| | | | **Totale** | **$917,00** | **+$169,27** |

Il dossier classifica NOW come `NON_CLASSIFICATO` (il suo `max_score_own` supera il gate, quindi
`BELOW_GATE` non si applica): la categoria `FILTERED` è la mia, ed è sostenuta dal `reason_code`
persistito in `s4_intent_events`, non da inferenza.

**Lettura obbligata sull'orizzonte:** il costo lordo aggregato è $917, ma l'opportunità realmente
accessibile dal primo ciclo eleggibile è **$169**, il **18%**. In una giornata in cui il
catalizzatore è arrivato a mercati chiusi, quasi tutto il movimento è nel gap e nei primi minuti.
Questo vale anche per il caso peggiore in apparenza, NOW: dei +10,04% close-to-close, il gap vale
+3,7% e i restanti +6,1% si consumano fra l'apertura (130,48) e le 14:10 UTC (138,26), quando il
primo ciclo portfolio non è ancora passato. Il costo *accessibile* del taglio da ranking è **+$2,71**.

## 4. Titoli catturati: esito

| Simbolo | Return | Come | Esito |
|---|---:|---|---|
| CRM | +22,58% | S4, **tre ingressi** 14:22 / 17:07 / 19:37 | Trade 893 −$18,02 (`portfolio_sell` 16:07, drift post-uscita **+$39,83**), trade 894 **+$12,13** (`portfolio_sell` 18:52, drift +$2,41), trade 895 aperto a 253,23 con **MTM EOD −$6,38**. Netto giornata **−$12,27** su un titolo che ha fatto **+22,6%**. Tenere il primo lotto (5,524 az. da 247,97 a 252,05) avrebbe reso **+$22,53**: **~$34,80 lasciati al churn**. Percentili d'ingresso 0,733 / 0,786 / **0,949**. |
| NVDA | +8,74% | S4, ingresso 14:07 → uscita 16:52 | Trade 892 **+$26,29**, `portfolio_sell`, 2,75 ore di tenuta, drift post-uscita **−$6,99** (uscita corretta). Unico trade pienamente riuscito. Percentile d'ingresso 0,404, il migliore dei cinque. |
| PANW | +12,83% | A libro S1 dal 13/07 | Cattura **passiva**: +$99,05 di MTM sulle 2,275 azioni. S4 aveva un segnale a **+0,638** ma il guard anti-pyramiding lo ha bloccato (nessun incremento). |
| SNOW | +4,36% | A libro S1 dal 05/08 | Cattura passiva, +$23,74 MTM. Unico segnale della giornata alle 19:48 (**+0,138**, fallback), dopo la chiusura utile. |
| XLK | +3,16% | A libro S1 dal 20/07 | Cattura passiva, +$25,85 MTM. |
| GE | −3,29% | A libro S1 dal 22/07 | **Unico mover al ribasso della watchlist ed è nostro**: −$26,88 MTM, la peggiore posizione della giornata. Nessun segnale, nessuna news. |
| TSLA | +2,60% | S4, ingresso 19:37 | Sotto soglia mover ma tradato: MTM EOD **+$2,40**, percentile d'ingresso 0,849. |

Pannello decision-quality del dossier: `entry_percentile` mediano **0,786** su 5 ingressi, **4 su 5
sopra 0,70** (mediana mobile a 20 giorni: 0,629) — si è comprato nella parte alta del range
giornaliero. `exit_effect_usd` **−$35,25**: le uscite della giornata sono costate più di quanto
abbiano protetto, ed è quasi interamente il primo lotto CRM.

## 5. Pattern osservato

**Pattern chiarissimo, e per una volta è un pattern di eventi, non di settore.** Un unico
catalizzatore — la trimestrale Salesforce, pubblicata dopo la chiusura del 26 — ha prodotto un
ventaglio di spillover su tutto l'enterprise software: CRM +22,58% (emittente), poi NOW +10,04%,
PANW +12,83%, ADBE +5,73%, SAP +4,48%, SNOW +4,36%. Sopra ci si sovrappone la scia della
trimestrale NVIDIA sui semi: NVDA +8,74%, AVGO +4,49%, INTC +4,36%. Il rovescio è una rotazione
fuori da difensivi, consumi e Cina: GE −3,29%, BABA −2,94%, CMCSA −2,90%, MCD −2,57%, DIS −2,56%,
MRK −2,33%, COST −2,24%. Il residuo vs settore del dossier lo conferma: NOW ha +6,88% di residuo
sopra XLK, cioè non è beta di settore.

Il dettaglio che conta per il sistema è **come è scritta questa notizia**. I quattro articoli
issuer-specific sui mover mancati o quasi-mancati hanno tutti la stessa forma: il titolo riguarda
il nostro ticker, ma il **soggetto della frase causale è un terzo**.

- ADBE: «Adobe stock is trading higher Thursday **following quarterly earnings results from
  Salesforce**» → +0,060
- AVGO: «Broadcom stock rises nearly 2% premarket **following strong NVIDIA earnings**» → +0,230
- INTC: «Intel stock is surging Thursday **following Nvidia's strong Q2**» → +0,228
- NOW: «Shares of ServiceNow are trading higher **following a blockbuster Q2 from Salesforce**» → +0,143

Il segno è sempre corretto e il movimento è sempre grande; la **magnitudine assegnata è sempre
piccola**. Sono notizie di **secondo ordine**: parlano del nostro emittente ma la causa è di un
altro, e il punteggio sembra riflettere il fatto che i fondamentali del soggetto non sono la
notizia. È la stessa forma di F-009 ma con una firma riconoscibile: nella giornata di massima
dispersione della finestra, la pipeline ha visto l'evento e lo ha misurato piccolo.

## 6. Confronto con i giorni precedenti

Confronto con `docs/ALPHA_MISS_REPORT_2026-08-20/21/24/25/26.md` e con le 18 righe di
`docs/evidence/market_daily.jsonl`.

- **Dispersione:** 3,49% contro una mediana di serie del 2,22% e contro 1,52% di ieri. È il
  secondo valore più alto dopo il 4,40% del 04/08. La finestra di osservazione ha quindi ora due
  giornate ad alta dispersione, che è esattamente ciò che la carta dice servire per distinguere un
  difetto ricorrente da una coincidenza.
- **Copertura news:** 53/96 a zero righe, contro 45 (08-26), 55 (08-25), 51 (08-24), 43 (08-21).
  L'interruzione del peggioramento registrata ieri **non si conferma**: si torna nella parte alta
  della banda. Effective-timely 26/96 = 27,1% (era 25,0%).
- **`NO_NEWS` come causa dominante:** ricorre per la terza seduta su quattro (08-25: 2; 08-26: 3;
  oggi: 4). È la causa più frequente della finestra: 41 occorrenze cumulate contro 43 `THIN_NEUTRAL`.
- **`FILTERED`: prima occorrenza della serie.** Le 18 righe di `market_daily.jsonl` hanno
  `FILTERED: 0` in ognuna. Oggi è 1. Non è un caso: `FILTERED` richiede che un segnale **superi**
  il gate 0,30, e finora questo quasi non accadeva — è il primo giorno in cui il collo di
  bottiglia si sposta dal gate al meccanismo a valle.
- **Percentile d'ingresso in peggioramento:** mediana 0,786 oggi contro 0,629 sulla finestra a 20
  giorni. Il terzo lotto CRM entra a **0,949**, cioè praticamente sul massimo di giornata.
- **Churn su CRM:** stessa forma già registrata su altri nomi (F-013), ma oggi è la prima volta
  che si manifesta **tre volte sullo stesso titolo nella stessa seduta**.

## 7. Segnalazioni

Nessuna proposta di taratura né di fix: la finestra di osservazione (03/08 → 28/09) è aperta e la
carta congela soglie, pesi, flag e cooldown. Dove un'evidenza sembra un difetto di correttezza
piuttosto che un limite noto lo dico esplicitamente, e la decisione se aprire una issue resta
all'operatore.

**[F-051] Sembra un difetto — il ranking S4 assegna gli slot top-N a segnali vecchi di giorni su
simboli già detenuti, e taglia il candidato fresco e tradabile.** *Nuovo.* Alle 17:37 UTC gli
otto candidati sopravvissuti al gate erano, per `rank`: AMAT (1), CRM (2), DELL (3), QQQ (4),
ARM (5), MRVL (6), CSCO (7), **NOW (8)**. Tutti e cinque i nomi in top-5 si sono risolti in
`SKIP_PYRAMIDING` — cioè **zero ordini emessi** — mentre l'unico candidato non detenuto veniva
scartato per `RANK_OUTSIDE_TOP_N`. Peggio: i segnali che occupano gli slot non sono della giornata.
`sentiment_signals.generated_at` dice DELL id 8892 → **2026-08-25 16:15 UTC**, CSCO id 8942 →
**2026-08-25 19:00 UTC**, SOXX id 8743 → **2026-08-24 14:31 UTC**. Il filtro di freschezza esiste
ed è attivo (750 `SKIP_ENTRY_FRESHNESS` in giornata, NOW stesso lo prende dalle 19:07), ma agisce
**dopo** il ranking, non prima: il ranking vede segnali di tre sedute fa. Sull'intera seduta il
quadro è sistematico — in **20 cicli su 24** almeno 4 dei 5 slot top-N sono occupati da nomi già
a libro, e in **8 cicli** un candidato sopravvissuto al gate viene tagliato mentre nessuno dei
cinque slot produce un ordine. Distinto da [F-031], che descrive il guard che blocca l'ingresso
sul simbolo detenuto: qui la vittima è un simbolo **non** detenuto, e il meccanismo è
l'occupazione dello slot a monte del guard. Costo lordo NOW $220,87; **accessibile +$2,71**,
perché il movimento era finito prima del primo ciclo — oggi il difetto non ha pagato pegno.

**[F-052] Sembra un difetto — il `rank` persistito nel ledger #294 non è una funzione del `score`
persistito nello stesso record.** *Nuovo.* `CrossSectionalRanker.rank` ordina per
`effective_strength`, che la docstring del modulo dichiara uguale a `score`
(`src/strategies/s4/ranking.py:4-8`), e assegna il rank enumerando la lista già ordinata
(`ranking.py:131-133`). I dati non lo confermano. Slot 15:52: SOXX `snapshot.score` **0,3600**
riceve rank 6, mentre CSCO **0,3199** riceve rank 5 e MRVL **0,3578** riceve rank 4 — e in quel
caso l'inversione **cambia la membership del top-5**. Slot 17:37: DELL 0,581 → rank 3, AMAT 0,521
→ rank 1; NOW 0,363 → rank 8, MRVL 0,358 → rank 6. Non azzardo quale dei due valori sia quello
giusto: constato che, così com'è, il ledger degli intent **non permette di ricostruire la
selezione** che ha prodotto, che è la sola cosa per cui è stato scritto. Sul 27/08 nessun effetto
materiale (le membership alternative danno lo stesso insieme di ordini). Costo non stimabile.

**[F-053] Sembra un difetto — l'endpoint di storico P&L etichetta ogni seduta col giorno
successivo.** *Nuovo.* Alpaca timbra le righe di `/v2/account/portfolio/history` a 00:00 UTC del
giorno **dopo** la seduta: la riga `1787875200` (2026-08-28T00:00Z) porta equity 110.041,95 e
`profit_loss` +76,90, e 110.041,95 è esattamente `account.last_equity`, cioè la chiusura del
**27**. `src/api/routes/performance.py:379-382` fa `datetime.fromtimestamp(ts).strftime("%Y-%m-%d")`
e usa quel giorno sia come `date` della riga giornaliera sia come chiave dell'aggregato mensile.
Conseguenza: il P&L di ogni seduta è attribuito al giorno di calendario successivo, e l'ultima
seduta di ogni mese finisce nel mese dopo. Verificato per tre giorni: il +76,90 del 27 è coerente
con realizzato +20,40 e MTM +58,81 ricalcolato indipendentemente sulle quantità broker; il +5,28
etichettato «2026-08-27» è la seduta del 26 (realizzato +42,95, MTM −33,51). Le righe di
`market_daily.jsonl` usano già l'allineamento corretto, quindi la serie del ledger non è
contaminata. Costo non stimabile.

**[F-001] Copertura news bassa sulla watchlist.** 53 dei 96 simboli senza una riga in `news_log`
(era 45 ieri): l'interruzione del peggioramento registrata il 26 non si conferma. 133 righe da 69
articoli unici, effective-timely 26/96 = 27,1%. Quattro dei cinque settori peggiori sono a
copertura nulla o quasi: healthcare **0/9**, financials 2/14, energy 1/6. Costo: i quattro miss
`NO_NEWS` valgono **$375,29** lordi.

**[F-009] Il gate 0,30 scarta segnali col segno corretto sui mover forti.** AVGO **+0,230** su
articolo issuer-specific ed ensemble pieno (+4,49%), INTC **+0,228** idem (+4,36%). Entrambi
sopravvivono al segno e muoiono sulla magnitudine, ed entrambi appartengono alla famiglia
«notizia di secondo ordine» descritta in §5. Costo lordo **$194,67**.

**[F-021] La finestra beat in UTC fissa perde i primi 37 minuti di seduta.**
`crontab(minute="7,22,37,52", hour="14-21")` (`src/workers/celery_app.py:210`) fa partire il primo
ciclo alle **14:07 UTC**, mentre in EDT la seduta apre alle **13:30 UTC**. Oggi quella finestra
morta contiene, per NOW, l'intero movimento intraday: apertura 130,48, prezzo al primo ciclo
utile 138,26, chiusura 138,43. Costo attribuito: $2.200 × (138,43−130,48)/130,48 = **$134,05**.
È la prima occorrenza in cui la finestra persa è documentabile tick per tick invece che per
principio.

**[F-013] Churn intraday senza banda fra gate d'ingresso e uscita.** CRM: BUY 14:22 → SELL 16:07
(−$18,02) → BUY 17:07 → SELL 18:52 (+$12,13) → BUY 19:37 (MTM −$6,38). Tre round trip sullo stesso
titolo nella stessa seduta, su un nome che ha chiuso **+22,6%**. Tenere il primo lotto valeva
+$22,53 contro i −$12,27 realizzati+MTM: costo attribuito **$34,80**, con controfattuale corto
(stesso ticker, stessa qty, nessuna riapertura).

**[F-031] Il guard anti-pyramiding blocca gli ingressi S4 sui simboli già detenuti.** 106
`SKIP_PYRAMIDING` su 9 simboli. Su sette di essi non è mai stato aperto nulla: DELL (+1,82%),
ARM (+1,65%), SOXX (+1,95%), QQQ (+1,37%), AMAT (+0,54%), CSCO (−0,19%), MRVL (−1,49%). Somma dei
rendimenti +5,65% → costo lordo **$124,30** su slot singolo. A differenza del 26/08 il caso più
vistoso non è una perdita evitata: PANW, con segnale **+0,638** e **+12,83%** di seduta, era già
a libro da S1 e il guard ha impedito l'incremento su quello che è stato il secondo miglior titolo
della giornata.

**[F-030] La notizia arriva a movimento già avvenuto.** Lato ingresso:
`entry_percentile` mediano **0,786** su 5 ingressi, 4 su 5 sopra 0,70, contro una mediana mobile a
20 giorni di 0,629; il terzo lotto CRM entra a **0,949** con
`quota_movimento_precedente_al_segnale = 1,054` (il movimento era **più che completo**) e chiude
la seduta a **−$6,38**. Lato mercato: l'aggregato §3 dice che su $917 di opportunità lorda solo
$169 (18%) era ancora sul tavolo al primo ciclo eleggibile. Costo misurato sul solo lotto
identificabile: **$6,38**.

**[F-019] La latenza di ingestione consuma la finestra di entry-freshness.** Mediane della
timeline del dossier su 133 righe: `published_to_scored` **60,4 min**, di cui
`published_to_first_seen` 12,6 min (esterno) e **`first_seen_to_ingested` 46,1 min (interno, il
76%)**. Netto miglioramento rispetto all'~1h50m storico del finding, ma il collo resta la coda
interna, non il publisher. Costo non stimabile isolatamente.

**[F-023] S4 usa solo il segnale più recente per simbolo.** Due casi netti oggi. INTC: il segnale
issuer-specific **+0,228** delle 16:31 viene sovrascritto da tre articoli fan-out scorati **0,000**
(17:02, 18:45, 19:15), e da lì `execution_decisions` motiva lo skip con «score 0.000» mentre il
titolo saliva del 4,4%. NOW: il **+0,1425** delle 14:00 è sostituito alle 15:16 dal fan-out
*«Synopsys Posts Upbeat Q3 Results, Joins Okta…»* a **+0,021**, che regge il riferimento per
cinque cicli. NVDA ha prodotto **30 segnali** in una seduta oscillando fra **−0,405** (14:15, otto
minuti dopo la BUY) e **+0,629**. Costo non stimabile.

**[F-012] Metà delle righe scorate viene da articoli fan-out multi-ticker.** 133 righe da 69
articoli unici → **64 mapping fan-out extra (48%)**. `mapping_rilevanza`: **92 UNKNOWN** contro 41
`ISSUER_SPECIFIC`, e **zero** righe classificate `SECTOR_MACRO`, `FALSE_ENTITY_MATCH` o
`IRRELEVANT_FANOUT`: il 69% delle righe resta non caratterizzato, peggio del 70%→ di ieri solo di
un punto. Fra i candidati miss la quota di righe fan-out è **0,889**. Costo non stimabile.

**[F-011] `execution_decisions.signal_id` NULL.** 513 righe in giornata, `signal_id` popolato su
**17**. Ripartizione (tot | con signal_id): `SKIP_THRESHOLD` 487|0, `SKIP_PYRAMIDING` 14|12,
`BUY` 5|5, `SKIP_FALLBACK` 4|0, `SELL` 3|0. Le tre SELL della giornata — le uscite che hanno
prodotto il realizzato — restano senza chiave verso il segnale. Costo non stimabile.

**[F-049] L'ensemble Ollama si degrada a metà sessione.** Per ora UTC, righe con ensemble pieno:
14:00 15/19, 15:00 15/22, 16:00 17/23, 17:00 23/26, **18:00 6/20**, 19:00 18/23. Nell'ora 18:00 il
70% delle righe è scorato da un modello solo o da FinBERT. In quella finestra cade **l'unico
articolo su ADBE** (18:46, `single:gpt-oss:20b-cloud`, `fallback_used=true`, conf. 0,400), scorato
**+0,060** su un testo che dice «stock is trading higher»: ADBE ha chiuso **+5,73%**. Sull'intera
giornata 39/133 righe in fallback (29,3%), contro l'81,6% dell'outage del 26. Costo attribuito al
solo caso identificabile: **$126,14**.

**[F-048] Le uscite parziali non vengono riscritte su `trades`.** Divergenze fra `trades` con
`exit_time IS NULL` e le posizioni broker: **NOK** 41,564 contro **0,564**, **WDC** 2,981 contro
**0,335**, **MRVL** 1,552 contro **0,552**. ~$1.870 di nozionale fantasma. Effetto misurabile
oggi: l'MTM del book calcolato sulle quantità DB dà **+$44,33**, quello sulle quantità broker
**+$58,81**, e solo il secondo quadra con il +76,90 dichiarato dal broker. Costo non stimabile,
ma contamina la serie `mtm` delle righe precedenti di `market_daily.jsonl`.

**[F-044] Il dossier deterministico non si genera.** Terza occorrenza consecutiva, causa e riga
invariate rispetto al 25 e al 26 (`scripts/alpha_miner_dossier.py:835-836`). Exit code 0, quindi
un cron che non guardi lo stdout non se ne accorge. Costo non stimabile.

**[F-045] Il dossier legge `is_tradable` con un confronto che non può essere vero.** Terza
occorrenza, e oggi è **falsificata direttamente**: `aggregati.guardia_contraddizione` riporta
`n_intenti 1700, n_intenti_tradabili 0`, ma la query diretta su `s4_intent_events` per lo stesso
giorno dà **1700 disposition** di cui **112 con `is_tradable = true`** (106 `SKIP_PYRAMIDING`, 5
`SUBMITTED`, 1 `SKIP_IDEMPOTENCY`). Lo zero è del parser, non dei dati. Costo non stimabile.

**[F-027] I log dei container non sopravvivono al riavvio.** `docker logs alembic-worker-1` parte
da `2026-08-27 23:14:50`: della seduta analizzata non resta una riga. Il taglio da ranking di NOW
è stato ricostruito **solo** perché il ledger #294 lo persiste in Postgres; senza
`s4_intent_events` la giornata sarebbe finita in `NON_CLASSIFICATO`. Costo non stimabile.

## 8. Igiene operativa

24 cicli portfolio, dalle 14:07:00 alle 19:52:00 UTC, **nessun gap oltre 16 minuti** (gap massimo
00:15:00). 513 righe in `execution_decisions`, 1700 candidate + 1700 disposition in
`s4_intent_events`. Mix modelli: 94 righe ensemble pieno, 36 `single:gpt-oss:20b-cloud`, 2
`single:glm-5.2:cloud`, 1 FinBERT. Estrazione: 118 `source_metadata`, 15 `org_lookup`. Segnali
sopra gate: 26 rialzisti, **5 ribassisti** (META −0,498 e −0,306, XLF −0,490, AMD −0,350, NVDA
−0,405) — nessuno dei quali può generare un ordine su un book long-only, coerentemente con
[F-040].

## 9. Book

| Voce | Valore | Fonte |
|---|---:|---|
| NAV chiusura 27/08 | **$110.041,95** | Alpaca `portfolio/history`, riga timbrata 2026-08-28T00:00Z = `account.last_equity` |
| P&L seduta | **+$76,90** | idem |
| Realizzato | **+$20,40** | `trades` con `exit_time::date = 2026-08-27`, 3 uscite |
| di cui S1 | $0,00 | nessuna uscita S1 |
| di cui S4 | +$20,40 | trade 892 +26,29, 893 −18,02, 894 +12,13 |
| MTM book aperto | **+$56,50** | P&L seduta − realizzato; verifica indipendente su quantità broker: +$58,81 |
| Posizioni aperte | 48 | Alpaca |
| Capitale impiegato | ~32% | $34.937 di market value su $110k di equity |
