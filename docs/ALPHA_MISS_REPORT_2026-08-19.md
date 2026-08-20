# Alpha Miss Report — 2026-08-19

Fonte numeri: `docs/evidence/dossier/2026-08-19.json` (schema 2.0, Alpaca SIP adjustment=all, generato 2026-08-20T08:00 UTC). Query dirette a `alembic-postgres-1` solo per Fase 2 (trades, portfolio_cycles, sentiment_signals, news_log) e per determinare quali simboli erano già in portafoglio. Nessun numero è stato ricalcolato in autonomia oltre a somme, `equity` EOD e `mtm` derivati da `portfolio_monitor_snapshots` (non presenti nel dossier).

## 1. Executive summary

24 dei 96 simboli in watchlist si sono mossi ≥3% (soglia motivata: è la soglia già usata dal dossier stesso, `soglia_mover=0.03`, e allinea questo report a tutta la serie precedente). Di questi, **16 erano già "catturati"** (13 posizioni S1/legacy detenute da settimane più 3 movimenti del giorno: 2 ingressi S4 — HOOD, NFLX — e 1 chiusura S4 in utile — TSLA). **8 sono miss**: 6 per assenza totale di news (NO_NEWS: NOW, CRM, F, ADBE, AZN, RDDT) e 2 per segnale presente ma sotto il gate 0,30 di design (PFE, AVGO). Causa dominante: **NO_NEWS**. Copertura news sulla watchlist: 40/96 simboli (42%) a zero articoli, dentro la banda 38–57% osservata da fine luglio. Di questi 8, solo 5 avevano un controfattuale long-accessibile positivo (RDDT e AVGO sono mover al ribasso su un libro long-only, quindi il costo congetturale è verificato $0, non stimato $0 per assenza di lavoro). Nessun bug nuovo isolato oggi: le tre segnalazioni sono ricorrenze di pattern già a ledger (F-001, F-009, F-030). Giornata negativa per il book: NAV −79,85 $ (110.179,29 → 110.099,44), realizzato +38,35 $ (S4), quindi MTM sul book aperto ≈ −118,20 $, spiegato quasi per intero dalla continuazione del rout semiconduttori/hardware iniziato il 08-18 su posizioni S1/S4 vecchie di settimane.

## 2. Rendimenti completi (96 simboli)

| Simbolo | Return % | Catturato |
|---|---|---|
| MRK | +12.60% | SI |
| MRVL | +9.85% | SI |
| NOW | +6.45% | NO |
| CRM | +5.07% | NO |
| HOOD | +4.63% | SI |
| LLY | +4.46% | SI |
| TSLA | +4.23% | SI |
| F | +4.09% | NO |
| RIO | +3.88% | SI |
| PFE | +3.63% | NO |
| ADBE | +3.55% | NO |
| XLV | +3.51% | SI |
| NFLX | +3.15% | SI |
| AZN | +3.03% | NO |
| DIS | +2.87% | NO |
| ABBV | +2.72% | SI |
| NKE | +2.47% | NO |
| AMZN | +2.46% | NO |
| SAP | +2.44% | NO |
| BIDU | +2.20% | NO |
| AAPL | +2.19% | SI |
| PLTR | +2.13% | NO |
| HD | +2.02% | SI |
| PBR | +1.98% | SI |
| IBM | +1.93% | NO |
| JD | +1.84% | NO |
| INFY | +1.69% | NO |
| VZ | +1.69% | NO |
| NVO | +1.68% | NO |
| VALE | +1.61% | SI |
| GM | +1.49% | SI |
| CMCSA | +1.49% | NO |
| QCOM | +1.07% | NO |
| T | +0.88% | NO |
| CVX | +0.88% | SI |
| JNJ | +0.85% | SI |
| SHEL | +0.83% | SI |
| BP | +0.74% | NO |
| ORCL | +0.71% | NO |
| PG | +0.65% | NO |
| ERIC | +0.59% | NO |
| BABA | +0.59% | NO |
| MSFT | +0.56% | NO |
| IWM | +0.50% | SI |
| META | +0.43% | NO |
| AXP | +0.41% | NO |
| V | +0.35% | NO |
| UBS | +0.30% | SI |
| TM | +0.28% | NO |
| SONY | +0.26% | NO |
| SPY | +0.21% | SI |
| MCD | +0.17% | NO |
| GOOGL | +0.15% | SI |
| SNOW | −0.10% | SI |
| MA | −0.10% | NO |
| MMM | −0.15% | SI |
| XLE | −0.16% | SI |
| DB | −0.16% | NO |
| QQQ | −0.20% | SI |
| TMUS | −0.21% | NO |
| TSM | −0.32% | SI |
| BA | −0.39% | NO |
| MU | −0.39% | SI |
| COST | −0.45% | NO |
| XOM | −0.48% | SI |
| ROKU | −0.62% | SI |
| XLF | −0.62% | SI |
| BRK.B | −0.66% | NO |
| WMT | −0.78% | NO |
| CSCO | −0.95% | NO |
| SBUX | −0.97% | SI |
| NVDA | −0.99% | NO |
| XLK | −1.07% | SI |
| UNH | −1.35% | SI |
| MS | −1.53% | SI |
| ARM | −1.57% | SI |
| JPM | −1.65% | SI |
| BAC | −1.65% | SI |
| WFC | −1.67% | NO |
| TXN | −1.76% | SI |
| GS | −1.81% | SI |
| SOXX | −2.21% | SI |
| NOK | −2.50% | SI |
| SPCX | −2.57% | NO |
| ASML | −2.84% | SI |
| CAT | −2.94% | SI |
| C | −3.46% | SI |
| AMAT | −3.53% | SI |
| AMD | −3.71% | SI |
| PANW | −3.84% | SI |
| INTC | −4.02% | SI |
| RDDT | −4.13% | NO |
| AVGO | −4.61% | NO |
| GE | −5.03% | SI |
| DELL | −6.64% | SI |
| WDC | −6.87% | SI |

"Catturato" = simbolo con posizione aperta a inizio o fine giornata, o con entry/exit registrato in `trades` il 2026-08-19 (include HD, entrata e uscita nella stessa sessione). SPY e QQQ sono presenti come simboli di watchlist (usati anche come posizioni S1/benchmark), non solo come indici esterni.

## 3. Miss classificati

| Simbolo | Return % | Categoria | Evidenza |
|---|---|---|---|
| NOW | +6.45% | NO_NEWS | 0 righe `news_log`, 0 `sentiment_signals` il 08-19 |
| CRM | +5.07% | NO_NEWS | 0 righe `news_log`, 0 `sentiment_signals` |
| F | +4.09% | NO_NEWS | 0 righe `news_log`, 0 `sentiment_signals` |
| ADBE | +3.55% | NO_NEWS | 0 righe `news_log`, 0 `sentiment_signals` |
| AZN | +3.03% | NO_NEWS | 0 righe `news_log`, 0 `sentiment_signals` |
| RDDT | −4.13% | NO_NEWS | 0 righe `news_log`; mover al ribasso, libro long-only, non detenuto → costo accessibile verificato $0 |
| PFE | +3.63% | THIN_NEUTRAL | 1 articolo, 1 segnale (19:45, score 0.12, fallback), sotto il gate d'ingresso S4 di 0,30 — segno corretto, magnitudine insufficiente |
| AVGO | −4.61% | THIN_NEUTRAL | 3 segnali (14:00 +0.089 non-fallback, 15:30 −0.135 fallback, 16:00 −0.158 non-fallback), nessuno sopra 0,30 in valore assoluto; mover al ribasso, libro long-only, non detenuto → costo accessibile verificato $0 |

Costo congetturale (size S4 tipica $2200, dal dossier `opportunity_v2.gross_opportunity_usd`): NOW $141.95, CRM $111.60, F $90.02, ADBE $78.00, AZN $66.65, PFE $79.93 — totale **$568.15** sui 6 nomi con direzione accessibile a un motore long-only. RDDT e AVGO: $0 verificato (non stimato), perché il movimento è al ribasso su un libro che non tiene posizioni corte.

Nessuna delle due categorie osservate oggi (NO_NEWS, THIN_NEUTRAL) è nuova: sono ricorrenze di [F-001] e [F-009] già a ledger.

## 4. Titoli catturati: esito

- **HOOD** (+4.63%, mover di giornata): ingresso S4 alle 16:07 UTC a $98,46, percentile d'ingresso nel range di giornata **0,866** (contro mediana mobile 20gg 0,538 — ingresso tardivo/alto nel range). MTM a fine giornata **−$50,16** nonostante il titolo chiuda in positivo: rispetto all'apertura la posizione vale +$53,52, cioè il grosso del movimento (il gap) è stato preso a monte dell'ingresso e da lì in poi il prezzo è arretrato.
- **NFLX** (+3.15%): ingresso S4 alle 17:07 UTC a $80,31, percentile d'ingresso 0,722 (sopra mediana). MTM a fine giornata −$2,06 (quasi flat), +$45,30 rispetto all'apertura — stesso pattern di HOOD ma più contenuto.
- **HD** (+2.02%, non mover ≥3%): round-trip S4 nella stessa sessione, entrata 16:37 a $343,48 e uscita 18:22 a $344,40, **+$3,91 netti** in 1h45. Percentile d'ingresso 0,229 (sotto mediana) — l'unico dei tre ingressi S4 del giorno con esito positivo e chiuso in giornata.
- **TSLA** (+4.23%): posizione S4 apertà il giorno prima (07-18 16:37 a $337,20), chiusa oggi alle 15:52 a $346,37, **+$34,44 netti** (`exit_reason=portfolio_sell`, tenuta 23h15m). Drift post-uscita +$17,97: il prezzo ha continuato a salire dopo l'uscita, quindi l'uscita — una vendita di ribilanciamento del portafoglio, non uno stop — ha lasciato guadagno sul tavolo, ma è un singolo trade e non lo classifico come pattern.
- **13 posizioni legacy/S1 già detenute** fra i mover ≥3% (MRK, MRVL, LLY, RIO, XLV in positivo; GE, DELL, WDC, INTC, PANW, AMD, AMAT, C in negativo): nessuna azione nuova oggi, esposizione pre-esistente. Il lato negativo pesa più del lato positivo in termini di numero di posizioni (8 contro 5) ed è la determinante principale del MTM giornaliero negativo del book (§5).

## 5. Pattern osservato

Continuazione, non evento isolato: la rotazione settoriale già in `ALPHA_MISS_REPORT_2026-08-18.md` (rout semiconduttori/hardware su rendimenti obbligazionari in salita) **prosegue il secondo giorno consecutivo** su un sottoinsieme degli stessi nomi — WDC (−7.43% → −6.87%), INTC (−6.58% → −4.02%), AMD (−4.27% → −3.71%), AMAT (−3.92% → −3.53%) tutti in calo per il secondo giorno — mentre il lato farmaceutico prosegue nella direzione opposta (LLY +3.60% → +4.46%, ABBV +3.43% → +2.72%). Si aggiunge oggi un fronte software/SaaS in salita (NOW, CRM, ADBE, HOOD, NFLX) che l'08-18 non era presente. Tutte le 8 posizioni semiconduttori/hardware in calo oggi erano già detenute (S1 o S4) da settimane: il book subisce il rout quasi per intero via MTM su posizioni vecchie, non per nuovi ingressi — stessa dinamica descritta il giorno precedente.

## 6. Confronto con giorni precedenti

- **08-18 → 08-19**: stesso tema (semiconduttori/hardware giù, pharma su) con intensità in attenuazione sui nomi comuni (WDC, INTC, AMD, AMAT tutti con calo minore rispetto a ieri) — coerente con una fase avanzata di rotazione piuttosto che un nuovo shock.
- **08-17 → 08-18**: il tema si era invece invertito nella direzione opposta (memoria/hardware in salita il 17, in forte calo il 18) — la serie di 3 giorni (17→18→19) mostra quindi un'inversione secca seguita da una continuazione, non un trend lineare.
- Copertura news 40/96 zero (42%) è dentro la banda stabile 38–57% osservata dal 07-31: nessuna deviazione da segnalare oltre le occorrenze già registrate su [F-001].

## 7. Segnalazioni

[F-001] Copertura news bassa sulla watchlist — ricorrenza confermata: 40/96 simboli (42%) a zero articoli il 08-19, dentro la banda 38–57% osservata dal 07-31. 5 dei 6 miss NO_NEWS avevano direzione accessibile a un libro long-only (NOW, CRM, F, ADBE, AZN): costo congetturale $488,23 con size S4 tipica $2200. RDDT è NO_NEWS ma mover al ribasso non detenuto: costo $0 verificato. Aggravante odierna, stesso schema già visto l'08-10 su ARM/XOM: fra le 8 posizioni semi/hardware già detenute che oggi perdono terreno, **GE (−5,03%), DELL (−6,64%) e WDC (−6,87%)** — due dei tre peggiori mover della giornata — hanno zero righe in `news_log` e zero `sentiment_signals`: l'assenza di notizia non impedisce solo l'ingresso, impedisce anche qualunque segnale di uscita/riduzione su posizioni già in perdita marcata. Nessun costo aggiuntivo stimato su questo punto (non è un nuovo ingresso mancato, è un'osservazione sul lato uscita — già la natura dell'aggravante registrata in precedenza).

[F-009] Il gate d'ingresso S4 (0,30) scarta segnali col segno corretto su mover forti — due casi oggi, entrambi generati al gate di design 0,30 (nessuna deroga attiva): PFE (+3,63%, segnale 19:45 score 0,12, fallback, segno corretto, ben sotto soglia) e AVGO (−4,61%, tre segnali fra 14:00 e 16:00, ultimo −0,158, segno corretto, sotto soglia). Costo: PFE $79,93 congetturale (size S4 $2200 su return pieno); AVGO $0 verificato (mover al ribasso, libro long-only, non detenuto — il gate è comunque irrilevante in questo caso perché il vincolo binding sarebbe stato long-only anche a segnale sopra soglia).

[F-030] La notizia arriva quando il movimento è già avvenuto (lato ingresso) — dei tre ingressi S4 di oggi, i due con percentile d'ingresso sopra la mediana mobile 20gg (0,538) sono entrambi in perdita o piatti a fine giornata: HOOD (percentile 0,866, MTM −$50,16) e NFLX (percentile 0,722, MTM −$2,06). L'unico ingresso sotto mediana, HD (percentile 0,229), è l'unico chiuso in utile (+$3,91) nella stessa sessione. Costo misurato sul MTM aperto dei due ingressi tardivi: $52,22 (50,16+2,06). Non è un evento nuovo: stesso schema del "lato ingresso" già registrato l'08-12 (tre ingressi sopra mediana, tutti in perdita nonostante titoli in verde).

Nessuna delle tre segnalazioni sopra sembra un bug di correttezza non ancora noto — sono tutte ricorrenze quantificate di pattern già in ledger. Non propongo alcuna modifica di soglia, gate o logica di ranking: la carta di osservazione resta in vigore fino al 2026-09-28 o al controllo di metà periodo del 2026-08-28.
