# ALPHA MISS REPORT — 2026-09-29

Contratto alpha_miss_prompt_v2 / dossier schema 3.1 (verificato). Dossier generato il 2026-10-06T08:00Z, prezzi Alpaca SIP adjustment=all.

## 1. Decision card
1. 6 mover ≥3% (soglia_mover 0,03), tutti al rialzo (up 6 / down 0), dispersione σ 1,42%; SPY −0,18%, QQQ +0,19%.
2. Dei 6 mover: 1 catturato (META +3,24%, eod_net_pnl +35,62 $), 3 già detenuti (AMAT, MRVL, ASML: PASSIVE_EXPOSURE), 2 miss BELOW_GATE (ORCL +3,91% score +0,131; ARM +3,65% score +0,045; gate 0,30).
3. Book del giorno: 3 chiusure S4, net_pnl realizzato +6,42 $ (META +25,23, NVDA −3,90 e −14,91); 26 simboli a zero news.

## 2. Stato carta
- as_of economic_pnl.json: **2026-09-17** (generato 2026-09-18; non include 09-29). Giorno 30/40 a quella data; il giorno 09-29 non è conteggiato nel file, e la scadenza attesa della carta (2026-09-28) è già passata: stato aggiornato = DATA_INCOMPLETE.
- Quota NO_NEWS dominante: 13/30 giorni = 0,43 vs soglia carta 0,60 (non superata) — as_of 09-17.
- S4 economico cumulato −696,33 $ vs ±200 $: fuori banda (within=false). S1 +664,95 $ (delta vs SPY −279,03 $); book −66,22 $ — as_of 09-17.

## 3. Miss del giorno
| Simbolo | Return | Categoria | Campo del dossier che decide |
|---|---|---|---|
| ORCL | +3,91% | (b) THIN_NEUTRAL (v2: BELOW_GATE) | `funnel_v2.righe[ORCL].pipeline=BELOW_GATE`, `evidence.score_firmato=+0,131 < soglia_gate 0,30`; legacy `causa=BELOW_GATE`, `in_portafoglio=false` |
| ARM | +3,65% | (b) THIN_NEUTRAL (v2: BELOW_GATE) | `funnel_v2.righe[ARM].pipeline=BELOW_GATE`, `score_firmato=+0,045 < gate` (anche < thin 0,05); legacy `causa=OFF_TOPIC_NON_DECIDIBILE` |

Non-miss (held, PASSIVE_EXPOSURE, `pipeline_escluso_motivo=held_rising`): AMAT +5,19%, MRVL +4,51%, ASML +3,56%.

Catturati:
| Simbolo | Return | Esito (dossier `ingressi`/`chiusure`) |
|---|---|---|
| META | +3,24% | S4 ingresso 15:22 @720,99, entry_percentile 0,23, mtm_eod +35,91, vs_apertura +27,82; uscita portfolio_sell @733,64 pnl_net +25,23 dopo 4,25h, drift_post_uscita +10,39. Ingresso presto nel movimento (percentile basso), uscita anticipata rispetto al close 738,79. |

Testo articoli (qualitativo, news_log):
- ORCL: 8 righe. La sola ISSUER_SPECIFIC significativa è Benzinga 12:19 "What's Going On With Oracle Stock Tuesday?" (OpenAI annulla GPT-6.1 Astra, titolo volatile) scorata −0,24 fallback; GDELT 16:45 "ORCL stock jumps..." +0,024; NetApp/Oracle storage 17:33 +0,131. Le altre 5 righe sono fan-out (Anthropic/SpaceX, macro 30Y yield, riunione Trump-leader AI x3) con score ±0,02–0,08.
- ARM: 1 riga, Benzinga 16:12 "What Is Going on With Arm Holdings Stock" (+~6% in giornata, forza semis/mega-cap), +0,045, pubblicata a movimento già in corso. Il controfattuale accessibile (ingresso 16:22 @297,31 → close 293,67) è −28,16 $ netti.

## 4. Attività del book

<!-- alpha-miss-book:start -->
<!-- alpha-miss-book-manifest: {"schema":1,"ingressi":["META","SPCX","NVDA"],"chiusure":["NVDA","NVDA","META"]} -->

Dati deterministici dal dossier; la prosa seguente li annota e non li sostituisce.

| Tipo | Simbolo | Strategia | Ora UTC | Prezzo | Quantità | P&L netto | Motivo / qualità |
|---|---|---|---|---:|---:|---:|---|
| IN | META | S4 | 15:22 | $720.9900 | 2.0172 | — | percentile 23.23%; denominatore intraday valido |
| IN | SPCX | S4 | 15:37 | $149.1749 | 9.7544 | — | percentile 80.72%; denominatore intraday valido |
| IN | NVDA | S4 | 15:52 | $230.5816 | 6.3063 | — | percentile 61.37%; denominatore intraday valido |
| OUT | NVDA | S4 | — | $229.6169 | 6.3995 | −$3.90 | portfolio_sell |
| OUT | NVDA | S4 | — | $228.2637 | 6.3063 | −$14.91 | portfolio_sell |
| OUT | META | S4 | — | $733.6400 | 2.0172 | +$25.23 | portfolio_sell |
<!-- alpha-miss-book:end -->
Tre ingressi S4 (META 15:22, SPCX 15:37, NVDA 15:52) e tre chiusure S4 (NVDA ×2, META), tutte `portfolio_sell`. Il realizzato +6,42 $ è la somma +25,23 (META) −3,90 −14,91 (NVDA); NVDA ha perso su entrambe le tranche (1 detenuta 20h, 1 detenuta 2h) con drift post-uscita negativo (−15,40, −6,64): le uscite hanno evitato ulteriore perdita. SPCX resta aperta (mtm_eod +0,64).

## 5. Cecità lato uscita
Nessuna: `aggregati.copertura_uscita.n_cieche_lato_uscita=0` su 44 posizioni (n_indeterminati=0, nessun `cieco_lato_uscita` null). Nota: 8 con copertura nulla e 16 con copertura effettiva nulla, ma nessuna con perdita ≥3% dall'ingresso con le condizioni della definizione.

## 6. Backstop NO_NEWS
- Mover NO_NEWS: 0 (`population.movers=0`); marker CALENDAR: nessuno (`calendar_observation.mover_observed=0/0`, `non_mover_observed=0/26`; `calendario_earnings.simboli_flaggati=[]`, status OBSERVED).
- Volume EOD (POST_HOC_EOD, non point-in-time, non valutabile come segnale): mediana non-mover (surprise) −0,162 su 26 osservazioni; mediana mover null (0 osservazioni). Nessuna soglia né false-positive rate.
- Copertura raw `news_log` per settore (distinta dalla effective-timely di `copertura_articoli.per_settore`):

| Settore | ticker_with_news/ticker_universe | raw_news_coverage_rate | zero_news_movers |
|---|---|---|---|
| consumer | 6/11 | 0.545 | 0 |
| energy | 4/6 | 0.667 | 0 |
| etf_broad | 4/4 | 1.000 | 0 |
| financials | 10/14 | 0.714 | 0 |
| healthcare | 9/9 | 1.000 | 0 |
| industrials | 2/4 | 0.500 | 0 |
| materials | 1/2 | 0.500 | 0 |
| media | 4/5 | 0.800 | 0 |
| semis | 11/15 | 0.733 | 0 |
| tech | 15/21 | 0.714 | 0 |
| telecom | 4/5 | 0.800 | 0 |

## 7. Pattern osservato
Rimbalzo AI-hardware/semis (AMAT, MRVL, ASML, ARM) più ORCL e META, sui mover ≥3%; SOXX +1,19%, XLK −0,02%, QQQ +0,19%. Gli stessi nomi (ARM, ORCL, META, MRVL) erano fra i perdenti del 09-28 (vedi candidates/2026-09-28.json, risk-off AI/semis): lettura da rendimenti e titoli, causa non verificata. Nessun mover al ribasso.

## 8. Segnalazioni

[F-009] Il gate 0,30 scarta segnali col segno corretto su mover rialzisti (ORCL +0,131, ARM +0,045).
- esposizione: 3 mover ENTRY_OPPORTUNITY non detenuti con notizia tempestiva (`funnel_v2.conteggi_actionability`); 2 sotto gate, 1 sopra e catturato (META). `active_signal_recall` 1/3.
- evidenza contraria: ARM entrando al primo ciclo eleggibile (16:25) avrebbe perso −28,16 $ netti (`opportunity_v2.net_opportunity_usd`): il gate lì non è costato niente, perché la notizia è arrivata a movimento esaurito (compatibile con F-030).
- non-occorrenza: META ha passato il gate e chiuso +25,23 $; AMAT/MRVL/ASML detenuti, non esposti.
- next evidence: sulla finestra, per mover ENTRY_OPPORTUNITY con score firmato corretto sotto gate, somma di `net_opportunity_usd` accessibile (non lordo) vs mover sopra gate, con N e t.
- meccanismo e fonte: gate d'ingresso S4 su magnitudine; `funnel_v2.righe[].pipeline=BELOW_GATE`, `evidence.score_firmato`; §3.
- costo: net_opportunity ORCL 53,09 + ARM (−28,16) = 24,93 $ (formula opportunity_v2: (close − open al primo ciclo eleggibile) × shares − costi; size 2.200 $). Alternativa scartata: costo lordo 86,11 + 80,29 = 166,40 $ — non accessibile, ARM era già esaurito.

[F-012] Metà delle righe scorate sono fan-out multi-ticker: ORCL ha 5 righe su 8 fan-out.
- esposizione: 9 righe scorate sui 2 candidati, 5 fan-out (`cause_del_giorno.quota_righe_fanout=0,556`; ORCL `quota_righe_fanout=0,625`); su tutto il giorno TAG_UNCONFIRMED 153/258 righe news_log (`copertura_articoli.totali.mapping_rilevanza`).
- evidenza contraria: se falso, la quota fan-out sarebbe ben sotto 0,5; ARM (0,0) è l'unico caso a quota nulla.
- non-occorrenza: ARM (1 riga, ISSUER_SPECIFIC); 105 righe ISSUER_SPECIFIC su 258.
- next evidence: join read-only fra ordini S4 del giorno e `attribution` del segnale sorgente (FANOUT vs ISSUER_SPECIFIC) per le 3 entrate (META, SPCX, NVDA) — non verificato oggi.
- meccanismo e fonte: righe da articoli macro/multi-ticker (riunione AI Trump/Johnson su 8–11 ticker) attribuite a ORCL; `candidati_miss[ORCL].segnali[].attribution`, `n_ticker_articolo`.
- costo: non stimabile (nessun ordine nato da una riga fan-out verificata oggi) → null.

[F-076] sanitize_text non decodifica le entità HTML: `&#39;` ancora nel testo scorato.
- esposizione: 8 righe scorate di ORCL + 1 di ARM; entità in 2 di 9 `testo_scorato` ("What&#39;s Going On With Oracle Stock Tuesday?", "&#39;Anthropic Discloses…&#39;"); `&#xAE;` anche nel body NetApp (news_log).
- evidenza contraria: se risolto, nessun `testo_scorato` conterrebbe `&#`.
- non-occorrenza: 7 di 9 righe scorate senza entità (ARM, GDELT, macro).
- next evidence: rapporto righe con `&#`/`&amp;` fra righe scorate sull'intera seduta, prima e dopo il deploy del fix (F-076 già nel registro esenti-freeze come difetto di correttezza).
- meccanismo e fonte: `sanitize_text` senza `html.unescape`; `candidati_miss[].segnali[].testo_scorato`.
- costo: non stimabile (nessun effetto sul segno dimostrabile oggi) → null.

## 9. Appendice
### (a) Rendimenti watchlist (`mercato.rendimenti`, 96 simboli, nessun simbolo senza dati)

| # | Simbolo | Rendimento |
|---|---|---|
| 1 | AMAT | +5.19% |
| 2 | MRVL | +4.51% |
| 3 | ORCL | +3.91% |
| 4 | ARM | +3.65% |
| 5 | ASML | +3.56% |
| 6 | META | +3.24% |
| 7 | SPCX | +2.59% |
| 8 | NOK | +2.37% |
| 9 | BA | +1.78% |
| 10 | RDDT | +1.59% |
| 11 | AVGO | +1.58% |
| 12 | NFLX | +1.55% |
| 13 | TXN | +1.21% |
| 14 | SOXX | +1.19% |
| 15 | INFY | +1.14% |
| 16 | MU | +1.05% |
| 17 | ADBE | +0.94% |
| 18 | TSM | +0.90% |
| 19 | CAT | +0.82% |
| 20 | SAP | +0.74% |
| 21 | SNOW | +0.67% |
| 22 | MRK | +0.40% |
| 23 | UBS | +0.33% |
| 24 | AMZN | +0.21% |
| 25 | QQQ | +0.19% |
| 26 | CSCO | +0.19% |
| 27 | COST | +0.18% |
| 28 | SONY | +0.17% |
| 29 | SBUX | +0.17% |
| 30 | MCD | +0.16% |
| 31 | DB | +0.08% |
| 32 | WDC | +0.06% |
| 33 | PFE | +0.00% |
| 34 | PBR | +0.00% |
| 35 | GS | -0.00% |
| 36 | LLY | -0.01% |
| 37 | XLK | -0.02% |
| 38 | AMD | -0.05% |
| 39 | MSFT | -0.05% |
| 40 | INTC | -0.09% |
| 41 | GE | -0.11% |
| 42 | BRK.B | -0.15% |
| 43 | DIS | -0.17% |
| 44 | SPY | -0.18% |
| 45 | HOOD | -0.21% |
| 46 | GM | -0.21% |
| 47 | RIO | -0.26% |
| 48 | PLTR | -0.27% |
| 49 | BIDU | -0.30% |
| 50 | AXP | -0.30% |
| 51 | IBM | -0.31% |
| 52 | XLV | -0.31% |
| 53 | XLF | -0.33% |
| 54 | ROKU | -0.35% |
| 55 | IWM | -0.36% |
| 56 | C | -0.39% |
| 57 | WFC | -0.41% |
| 58 | MS | -0.45% |
| 59 | PG | -0.48% |
| 60 | JPM | -0.48% |
| 61 | V | -0.51% |
| 62 | GOOGL | -0.53% |
| 63 | MMM | -0.58% |
| 64 | HD | -0.64% |
| 65 | F | -0.65% |
| 66 | DELL | -0.71% |
| 67 | XOM | -0.72% |
| 68 | NVDA | -0.72% |
| 69 | UNH | -0.76% |
| 70 | MA | -0.82% |
| 71 | TM | -0.84% |
| 72 | CRM | -0.86% |
| 73 | CMCSA | -0.87% |
| 74 | XLE | -0.90% |
| 75 | BAC | -0.92% |
| 76 | BABA | -0.94% |
| 77 | PANW | -0.94% |
| 78 | CVX | -0.96% |
| 79 | NVO | -1.03% |
| 80 | ERIC | -1.06% |
| 81 | ABBV | -1.12% |
| 82 | NOW | -1.15% |
| 83 | JD | -1.16% |
| 84 | AZN | -1.17% |
| 85 | TSLA | -1.29% |
| 86 | SHEL | -1.38% |
| 87 | VZ | -1.50% |
| 88 | NKE | -1.51% |
| 89 | JNJ | -1.61% |
| 90 | T | -1.69% |
| 91 | WMT | -1.78% |
| 92 | QCOM | -1.80% |
| 93 | BP | -2.05% |
| 94 | TMUS | -2.08% |
| 95 | VALE | -2.13% |
| 96 | AAPL | -2.66% |

### (b) Altri finding toccati
- [F-001] contradicted: 26 simboli a zero news su 96 (minoranza) nella seduta.
- [F-030] supported: SPCX entry 15:37 `quota_nel_gap` 0,32, `quota_movimento_precedente_al_segnale` 0,97, entry_percentile 0,81; META non esposto (percentile 0,23).
- [F-043] not_exposed: nessun segnale sopra gate su mover al ribasso (up 6 / down 0).
- [F-089] not_exposed: nessun mover S4 con segnale fresco sotto gate che non sia uscito (dato dossier insufficiente per verificare il combiner).
- [F-075] supported: held_at_open_rate 3/6 conta AMAT/MRVL/ASML come catturati senza ponderare l'esposizione (nozionale per posizione non riportato nel dossier del giorno: DATA_INCOMPLETE sul peso).

### (c) Successo
- META: S4 +25,23 $ realizzato, mtm_eod +35,91 $ (ingresso percentile 0,23).

### Attribuzione fonti per ticker (FASE 5)
26 ticker a zero articoli, `fonti_osservate` vuoto = zero resa dei provider (non fonte non configurata); nessun caso "fonte presente ma non effective-timely". Nessuna raccomandazione.

| Ticker | settore | articoli_unici_giorno | effective_timely_giorno | fonti_osservate |
|---|---|---|---|---|
| ADBE | tech | 0 | 0 | {} |
| BIDU | tech | 0 | 0 | {} |
| BRK.B | financials | 0 | 0 | {} |
| COST | consumer | 0 | 0 | {} |
| CRM | tech | 0 | 0 | {} |
| ERIC | telecom | 0 | 0 | {} |
| F | consumer | 0 | 0 | {} |
| GE | industrials | 0 | 0 | {} |
| GM | consumer | 0 | 0 | {} |
| HD | consumer | 0 | 0 | {} |
| IBM | tech | 0 | 0 | {} |
| INTC | semis | 0 | 0 | {} |
| JD | tech | 0 | 0 | {} |
| MA | financials | 0 | 0 | {} |
| MMM | industrials | 0 | 0 | {} |
| PBR | energy | 0 | 0 | {} |
| PG | consumer | 0 | 0 | {} |
| QCOM | semis | 0 | 0 | {} |
| RIO | materials | 0 | 0 | {} |
| ROKU | media | 0 | 0 | {} |
| SHEL | energy | 0 | 0 | {} |
| SONY | tech | 0 | 0 | {} |
| SOXX | semis | 0 | 0 | {} |
| TXN | semis | 0 | 0 | {} |
| UBS | financials | 0 | 0 | {} |
| V | financials | 0 | 0 | {} |
