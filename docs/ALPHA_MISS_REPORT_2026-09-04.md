# Alpha Miss Report — 2026-09-04

Fonte numeri: `docs/evidence/dossier/2026-09-04.json` (generato 2026-09-07T08:00:19Z, Alpaca SIP adjustment=all). Nessun numero qui è ricalcolato — dove il mio calcolo avrebbe potuto divergere ho letto il dossier. Periodo di osservazione attivo (`docs/evidence/OBSERVATION_CHARTER.md`): solo evidenza, nessuna proposta di taratura.

## 1. Executive summary

**18 mover ≥3%** su 96 simboli watchlist (11 su, 7 giù), dispersione cross-sectional σ=2,42%. **Zero ingressi** in tutta la seduta (`ingressi: []`): l'unica attività di libro sono due chiusure, PLTR (S4, portfolio_sell, −53,06 $) e IWM (S1, sentiment_reversal, +12,19 $, non-mover). **9 dei 18 mover erano già in portafoglio** (esposizione subita, nessuna decisione attiva quel giorno) e **9 sono candidati miss** (non detenuti, non tradati).

Causa dominante dei 9 miss: **NO_NEWS (6/9)** — zero righe `news_log` per NFLX, BIDU, ARM, INFY, ORCL, e un settimo caso equivalente (TSLA: 7 righe ma zero confermate sul ticker, vedi §3). **THIN_NEUTRAL (3/9)**: ADBE, MU, TMUS — segnale presente, segno corretto, magnitudine sotto il gate 0,30 (MU il più vicino, 0,258, a soli 0,042 dal gate). Zero WRONG_SIGN, zero FILTERED, zero OUT_OF_STRATEGY_SCOPE oggi. Il classificatore meccanico del dossier diverge in un punto (TSLA → `NON_CLASSIFICATO`), spiegato in §3.

Book: equity fine giornata **109.970,86 $**, variazione **−109,86 $**, realizzato **−40,87 $** (S1 +12,19 $, S4 −53,06 $), MTM implicito del libro aperto **−68,99 $**. **54/96 simboli (56,3%)** a zero righe news, secondo valore più alto della finestra osservata dal 07-31 (record 60 l'08-31).

## 2. Rendimenti — tabella completa (96 simboli)

| Simbolo | Return % | Catturato |
|---|---:|---|
| MRVL | +7.05% | sì (in portafoglio) |
| MU | +6.10% | no |
| WDC | +5.86% | sì (in portafoglio) |
| AMD | +4.69% | sì (in portafoglio) |
| INTC | +4.51% | sì (in portafoglio) |
| AMAT | +4.31% | sì (in portafoglio) |
| ASML | +4.17% | sì (in portafoglio) |
| BIDU | +4.07% | no |
| ARM | +3.92% | no |
| SOXX | +3.52% | sì (in portafoglio) |
| ORCL | +3.08% | no |
| TSM | +2.85% | sì (in portafoglio) |
| NOK | +2.66% | sì (in portafoglio) |
| JD | +1.87% | no |
| TXN | +1.82% | no |
| CAT | +1.72% | sì (in portafoglio) |
| DELL | +1.50% | sì (in portafoglio) |
| F | +1.46% | no |
| BABA | +1.28% | no |
| GE | +1.09% | no |
| META | +1.00% | no |
| HD | +0.94% | no |
| WFC | +0.87% | no |
| NVDA | +0.84% | no |
| GM | +0.83% | sì (in portafoglio) |
| BA | +0.83% | no |
| XLK | +0.70% | sì (in portafoglio) |
| SHEL | +0.67% | sì (in portafoglio) |
| CSCO | +0.54% | sì (in portafoglio) |
| BP | +0.53% | sì (in portafoglio) |
| RIO | +0.42% | sì (in portafoglio) |
| PANW | +0.40% | no |
| IWM | +0.28% | sì (in portafoglio) |
| MS | +0.26% | sì (in portafoglio) |
| AVGO | +0.21% | no |
| QQQ | +0.18% | sì (in portafoglio) |
| MMM | +0.15% | no |
| QCOM | +0.10% | no |
| IBM | +0.08% | no |
| GS | +0.07% | no |
| BAC | -0.06% | sì (in portafoglio) |
| AMZN | -0.15% | no |
| VALE | -0.26% | sì (in portafoglio) |
| ERIC | -0.30% | no |
| C | -0.30% | sì (in portafoglio) |
| PG | -0.33% | no |
| SPY | -0.39% | sì (in portafoglio) |
| BRK.B | -0.41% | no |
| UBS | -0.54% | sì (in portafoglio) |
| DB | -0.55% | no |
| CMCSA | -0.60% | no |
| XLF | -0.79% | sì (in portafoglio) |
| XLE | -0.87% | sì (in portafoglio) |
| LLY | -0.88% | sì (in portafoglio) |
| SAP | -0.88% | no |
| VZ | -0.89% | no |
| JPM | -0.94% | sì (in portafoglio) |
| UNH | -0.95% | sì (in portafoglio) |
| NKE | -0.95% | no |
| V | -0.97% | no |
| RDDT | -0.98% | no |
| XLV | -1.04% | sì (in portafoglio) |
| COST | -1.04% | no |
| AXP | -1.11% | no |
| MA | -1.11% | no |
| GOOGL | -1.11% | sì (in portafoglio) |
| JNJ | -1.15% | sì (in portafoglio) |
| WMT | -1.18% | no |
| SPCX | -1.20% | no |
| PFE | -1.25% | sì (in portafoglio) |
| AZN | -1.26% | no |
| SBUX | -1.28% | sì (in portafoglio) |
| CVX | -1.29% | sì (in portafoglio) |
| MRK | -1.32% | sì (in portafoglio) |
| TM | -1.38% | no |
| ABBV | -1.44% | sì (in portafoglio) |
| MCD | -1.52% | no |
| SONY | -1.60% | no |
| XOM | -1.69% | sì (in portafoglio) |
| ROKU | -1.72% | sì (in portafoglio) |
| DIS | -1.73% | no |
| PBR | -1.90% | sì (in portafoglio) |
| NVO | -1.92% | no |
| T | -1.95% | no |
| CRM | -1.97% | sì (in portafoglio) |
| MSFT | -2.04% | no |
| HOOD | -2.09% | no |
| AAPL | -2.51% | sì (in portafoglio) |
| NOW | -2.97% | no |
| INFY | -3.23% | no |
| TMUS | -3.46% | no |
| PLTR | -4.49% | sì (in portafoglio) |
| NFLX | -5.35% | no |
| SNOW | -5.41% | sì (in portafoglio) |
| TSLA | -5.92% | no |
| ADBE | -6.73% | no |

Nessun simbolo senza barra (`simboli_senza_dati: []`). "Catturato" = posizione già a libro all'apertura RTH (`snapshot_apertura`, 45 posizioni) o tradata in giornata; non implica una decisione attiva sul movimento specifico.

## 3. Miss classificati (9 candidati, mover ≥3% non detenuti e non tradati)

Soglia mover: |return| ≥ 3% (`soglia_mover` del dossier, coerente con la serie osservata). Il dossier applica un classificatore meccanico (`causa`) che confronta `max |score|` con il gate 0,30 senza guardare segno né tipo di attribuzione; la mia classificazione a sei categorie usa lo stesso segnale ma legge anche segno e provenienza (own vs fan-out), come nei report precedenti.

| Simbolo | Return | Categoria | Causa dossier | Evidenza |
|---|---:|---|---|---|
| MU | +6.10% | THIN_NEUTRAL | BELOW_GATE | 3 articoli. Segnale **own/ISSUER_SPECIFIC** alle 15:30, score **+0,258** (segno corretto), **0,042 sotto il gate 0,30** — il candidato più vicino alla soglia della giornata. Un secondo articolo fan-out (18:45, fallback) porta score −0,24 ma non tocca il canale own. `net_opportunity` simulata +36,46 $. |
| BIDU | +4.07% | NO_NEWS | NO_NEWS | Zero righe `news_log`, zero `sentiment_signals`. `net_opportunity` simulata +37,07 $ (accessibile +39,40 $): il singolo candidato con più denaro a tavola oggi, e zero dati per vederlo. |
| ARM | +3.92% | NO_NEWS | NO_NEWS | Zero righe, zero segnali. `net_opportunity` simulata **negativa** (−17,77 $): anche in assenza del gap dati, il timing d'ingresso simulato al primo ciclo eleggibile avrebbe perso. |
| ORCL | +3.08% | NO_NEWS | NO_NEWS | Zero righe, zero segnali. `net_opportunity` simulata +14,12 $. |
| TMUS | -3.46% | THIN_NEUTRAL | BELOW_GATE | 1 solo articolo, fan-out/TAG_UNCONFIRMED, score −0,21 (segno corretto), sotto gate. Nessun pezzo issuer-specific. |
| INFY | -3.23% | NO_NEWS | NO_NEWS | Zero righe, zero segnali. |
| NFLX | -5.35% | NO_NEWS | NO_NEWS | Zero righe, zero segnali. |
| TSLA | -5.92% | NO_NEWS *(equivalente)* | NON_CLASSIFICATO | **7 articoli**, il volume più alto della giornata fra i miss, ma **zero** con `relevance=ISSUER_SPECIFIC` o `subject_ticker=TSLA`: tutti e 7 marcati `TAG_UNCONFIRMED`/fan-out, incluse headline inequivocabilmente su Tesla ("Tesla's Cybercab 'Storm' Was More of a 'Drizzle'", "Musk Says Autonomy Is Flight's Next Step", "Tesla Stock Down 29% from All-Time Highs... Sell the News" score −0,44). `max_score_fanout` −0,299 (segno corretto) ma mai promosso a canale own. Effetto pratico identico a NO_NEWS: nessun segnale "proprio" è mai stato generabile, nonostante 7 righe in tabella. Il classificatore meccanico del dossier non ha una casella per questo caso e lo marca `NON_CLASSIFICATO` — non è un difetto del dossier (misura correttamente `causa=None → NON_CLASSIFICATO`), è un gap nella tassonomia legacy. Segnalato in §9/[F-067]. |
| ADBE | -6.73% | THIN_NEUTRAL | BELOW_GATE | 1 solo articolo, fan-out/TAG_UNCONFIRMED ("SanDisk Jumps 10%, Lululemon Crashes 17%: Stock Market Today", 12 ticker), score −0,156 (segno corretto), sotto gate. Zero canale own nonostante il -6,73% sia il movimento più ampio della giornata — nessun pezzo issuer-specific è mai apparso. |

**Conteggi: NO_NEWS 6 · THIN_NEUTRAL 3 · WRONG_SIGN 0 · FILTERED 0 · OUT_OF_STRATEGY_SCOPE 0.**

Nota sull'accessibilità: per i 5 miss ribassisti non detenuti (TMUS, INFY, NFLX, TSLA, ADBE) `opportunity_v2.accessible_opportunity_usd = 0` per costruzione (`missing_reason: long_only_no_share_downside_not_held`) — una strategia long-only non può monetizzare un ribasso su un titolo che non detiene, indipendentemente da quanto il segnale fosse buono. Questo non li retrocede a OUT_OF_STRATEGY_SCOPE (categoria riservata a simboli esclusi per costruzione, es. ETF benchmark): sono comunque miss di segnale/copertura genuini nel senso della domanda 1 della carta, coerente con come i report dell'01-09 hanno trattato casi identici (ORCL, SAP, NOW).

## 4. Titoli catturati: esito

<!-- alpha-miss-book:start -->
<!-- alpha-miss-book-manifest: {"schema":1,"ingressi":[],"chiusure":["PLTR","IWM"]} -->

Dati deterministici dal dossier; la prosa seguente li annota e non li sostituisce.

| Tipo | Simbolo | Strategia | Ora UTC | Prezzo | Quantità | P&L netto | Motivo / qualità |
|---|---|---|---|---:|---:|---:|---|
| OUT | PLTR | S4 | — | $176.1700 | 7.5684 | −$53.06 | portfolio_sell |
| OUT | IWM | S1 | — | $295.6600 | 2.6299 | +$12.19 | sentiment_reversal |
<!-- alpha-miss-book:end -->

**Nessun ingresso oggi** (0 righe in `ingressi`), quindi nessuna nuova cattura da segnale sentiment. L'unica azione sul libro riguardante un mover:

- **PLTR (−4,49%, S4)**: posizione aperta il 09-03, uscita alle 14:22 UTC via `portfolio_sell` a 176,17 $ (entrata 183,08 $), **net P&L −53,06 $**. `drift_post_uscita` **−13,93 $**: il prezzo ha continuato a scendere dopo l'uscita, quindi il timing dell'uscita ha evitato una perdita maggiore, non la ha causata.

Le altre 8 posizioni mover-e-detenute (MRVL +7,05%, WDC +5,86%, AMD +4,69%, INTC +4,51%, AMAT +4,31%, ASML +4,17%, SOXX +3,52%, SNOW −5,41%) sono esposizione passiva subita, nessuna decisione attiva registrata quel giorno. Copertura news su queste: WDC (2 articoli, segnali −0,15/+0,28), SNOW (2 articoli, segnali +0,18/+0,35), INTC/AMAT/ASML (1 articolo ciascuno, segnali deboli, uno con fallback) — **MRVL, AMD e SOXX a zero righe `news_log`** nonostante MRVL sia il mover più forte della giornata: la pipeline non aveva nulla da dire nemmeno sul titolo con l'esposizione più favorevole già in portafoglio.

## 5. Cecità lato uscita (posizioni detenute)

Dal campo `copertura_uscita` del dossier, non ricalcolato. Definizione: posizione viva all'open RTH, perdita ≥3% da `ritorno_da_ingresso`, zero righe `news_log` e zero `sentiment_signals` nella seduta, streak ≥2 sedute consecutive senza righe, finestra 10 sedute.

**45 posizioni valutate, 1 cieca lato uscita, 0 con `cieco_lato_uscita: null`** — nessun dato mancante oggi, il campo è deciso su tutte e 45.

| Ticker | Strategia | `ritorno_da_ingresso` | Sedute consecutive senza righe | `fonti_osservate_finestra` | Nozionale |
|---|---|---:|---:|---|---:|
| **UNH** | S1 | **−7,13%** | 2 | `alpaca_benzinga` | 632,50 $ |

Attenzione a non confondere le misure: UNH oggi ha `ritorno_seduta` −0,95% (movimento di giornata modesto), ma `ritorno_da_ingresso` −7,13% — è la perdita accumulata da quando la posizione è stata aperta, non il movimento di oggi. Nozionale cieco 632,50 $ è esposizione a rischio, non un costo: nessun controfattuale dice che un'uscita sarebbe stata migliore.

## 6. Backstop NO_NEWS

**Marker calendario**: nessuno degli 8 mover a zero news (AMD, ARM, BIDU, INFY, MRVL, NFLX, ORCL, SOXX) ha un evento `CALENDAR` osservato — tutti `calendar.status: UNKNOWN`, `observed_catalysts: []`. Nessuna evidenza di un evento societario noto dietro questi movimenti.

**Volume POST_HOC_EOD** (non un segnale point-in-time, solo descrittivo dell'intera seduta): mediana `adv_ratio - 1` dei mover a zero news = **+15,68%** sopra media mobile 20 giorni, contro **−21,65%** dei non-mover a zero news. Descrittivo, non una soglia proposta: il dato è noto solo a fine seduta insieme al ritorno stesso.

**Copertura raw per settore** (`ticker_with_news / ticker_universe`, righe `news_log` grezze, distinta dalla copertura effective-timely):

| Settore | Con news | Universo | Copertura raw | Mover a zero news |
|---|---:|---:|---:|---:|
| etf_broad | 4 | 4 | 100,0% | 0 |
| semis | 9 | 15 | 60,0% | 4 |
| tech | 11 | 21 | 52,4% | 3 |
| industrials | 2 | 4 | 50,0% | 0 |
| consumer | 5 | 11 | 45,5% | 0 |
| telecom | 2 | 5 | 40,0% | 0 |
| energy | 2 | 6 | 33,3% | 0 |
| financials | 4 | 14 | 28,6% | 0 |
| healthcare | 2 | 9 | 22,2% | 0 |
| media | 1 | 5 | 20,0% | 1 |
| materials | 0 | 2 | 0,0% | 0 |

Semis e tech concentrano sia il volume di mover sia la maggior parte dei mover a zero news (4 e 3 su 8 totali) — coerente con §7: il settore più in movimento oggi è anche quello dove la copertura raw, pur relativamente alta (60%/52%), lascia scoperti proprio i nomi che si muovono di più.

## 7. Pattern osservato

**Rotazione semis/hardware (su) contro software/growth ad alto multiplo (giù), su indici quasi piatti.** SPY −0,39%, QQQ +0,18%: nessuna direzione di mercato forte, la dispersione è idiosincratica/settoriale.

- **Lato forte — semiconduttori e hardware, 9 su 9 dei nomi semis/hardware nella lista mover positivi:** MRVL +7,05%, MU +6,10%, WDC +5,86%, AMD +4,69%, INTC +4,51%, AMAT +4,31%, ASML +4,17%, ARM +3,92%, SOXX +3,52%, con BIDU/TSM/ORCL al seguito nel tech più ampio.
- **Lato debole — software/growth e consumer discretionary ad alta duration:** ADBE −6,73%, TSLA −5,92%, SNOW −5,41%, NFLX −5,35%, PLTR −4,49%, TMUS −3,46%, INFY −3,23%, NOW −2,97%.
- **Indizio di catalizzatore macro-tassi**: l'unico articolo scorato su MU alle 15:30 ("Micron, SanDisk Jump 4% Even as Hot Jobs Report Briefly Flips Fed Hike Odds Above 50%") cita esplicitamente un dato sull'occupazione che sposta le probabilità implicite di rialzo dei tassi. Un jobs report "caldo" è coerente con la rotazione osservata (hardware/value su, growth a lunga duration giù) ma **nessun secondo articolo indipendente conferma il nesso causale sugli altri nomi**: resta un indizio, non un pattern confermato sul lato notizie — la pipeline non ha prodotto una copertura esplicita del tema macro sui mover deboli (a differenza del 09-01 e 09-03, dove un singolo articolo macro appariva come fan-out su gran parte del gruppo).
- ADBE è isolato all'interno del pattern software: il calo (−6,73%, il più ampio della giornata) non condivide settore con nessun altro mover debole tranne in senso lato (tech/software), e la pipeline non ha una sola riga issuer-specific a spiegarlo — coerente con un evento idiosincratico (es. post-earnings) non captato.

## 8. Confronto con i giorni precedenti

- **watchlist_zero_news 54/96 (56,3%)**: secondo valore più alto della finestra osservata dal 07-31 (record 60 l'08-31), sopra il 50 del 09-03 e il 45 del 09-02. La banda 40-60 osservata da inizio agosto non si è ancora spezzata in nessuna seduta.
- **Zero ingressi in giornata** è raro nella serie recente (09-01/09-02/09-03 avevano tutti almeno un ingresso): non necessariamente un'anomalia da sola — coerente con un giorno senza segnale sopra gate su nessun simbolo non detenuto — ma segnalato per continuità con l'osservazione.
- **Il pattern TSLA di oggi è diverso da quello del 09-03.** Il 09-03 TSLA aveva un segnale **sopra gate** (0,468, fallback) generato alle 19:45 che non riceveva alcuna decisione al ciclo successivo — un vero e proprio buco nella pipeline decisionale (F-056/F-060). Oggi TSLA ha 7 articoli ma **zero** mai promossi a `ISSUER_SPECIFIC`/`subject_ticker` confermato, quindi non arriva mai a generare un segnale "proprio" sopra o sotto gate: è un gap diverso, a monte, nella classificazione di rilevanza (vedi [F-067] in §9). I due giorni non vanno sommati come lo stesso fenomeno.
- **MU a 0,042 dal gate** si aggiunge alla serie di near-miss già in F-009 (RDDT 08-03, ORCL/NOW 09-01, altri) — il gate continua a scartare segnali col segno corretto per un margine stretto su mover forti.

## 9. Segnalazioni

[F-001] Copertura news bassa sulla watchlist, 54/96 simboli (56,3%) a zero righe `news_log` il 09-04 — secondo valore più alto della finestra osservata. I 6 miss NO_NEWS (inclusa l'equivalenza TSLA, vedi [F-067]) sommano un lordo close-to-close × 2.200 $ di **562,24 $** (TSLA 130,26 + NFLX 117,62 + BIDU 89,54 + ARM 86,15 + INFY 70,97 + ORCL 67,70), per confrontabilità con la serie; l'accessibile misurato dal dossier sui soli rialzisti non detenuti è +37,07 $ (BIDU), −17,77 $ (ARM), +14,12 $ (ORCL). Faccia lato uscita (§5): UNH cieca da 2 sedute consecutive, −7,13% dall'ingresso, nozionale 632,50 $ a rischio.

[F-009] Il gate d'ingresso S4 (0,30) scarta segnali col segno corretto su mover forti: oggi 3 nuovi casi, ADBE (fan-out −0,156), MU (own +0,258, **0,042 dal gate**, il margine più stretto della serie insieme a TSLA 08-31/NOW 09-01), TMUS (fan-out −0,21). Lordo close-to-close × 2.200 $ = 358,35 $ (ADBE 148,13 + MU 134,16 + TMUS 76,06), per confrontabilità con la serie.

[F-067] **Nuovo.** Headline inequivocabilmente ticker-specifiche non vengono mai promosse a `relevance=ISSUER_SPECIFIC`/`subject_ticker` confermato: TSLA il 09-04 riceve 7 articoli (il volume più alto fra i miss della giornata), incluse headline come "Tesla's Cybercab 'Storm'...", "Musk Says Autonomy Is Flight's Next Step...", "Tesla Stock Down 29% from All-Time Highs...Sell the News" — tutti e 7 marcati `TAG_UNCONFIRMED`/fan-out, `subject_ticker: null`. Effetto: nessun segnale "proprio" generabile nonostante il volume di copertura, e il classificatore causale legacy del dossier non ha una casella per il caso (`NON_CLASSIFICATO`, coerente con il gap già noto in F-060 ma di natura diversa — qui il segnale non arriva mai a monte, non è il ranking a scartarlo dopo). Nuovo id giustificato: non è un riconteggio di F-020 (org_lookup attribuisce a un ticker sbagliato — qui il ticker è quello giusto e resta comunque non confermato) né di F-057 (resolver shadow `news_resolved_entities`, pipeline diversa e non gating). Confidenza congetturale (nessun trade avvenuto). Costo `null`: il dollaro equivalente (130,26 $) è già contato nella somma di [F-001] per non duplicare; qui l'affermazione è strutturale (la tassonomia/pipeline di rilevanza, non il dato mancante).

Nessun candidato di oggi ricade nella categoria FILTERED (ranking/breadth/hysteresis su segnale sopra soglia) — non verificato nel dettaglio nei log persistenti del worker perché il dossier stesso non ne classifica nessuno oggi. Nessuna proposta di fix in questo report: la decisione se aprire un'issue su [F-067] è dell'operatore.
