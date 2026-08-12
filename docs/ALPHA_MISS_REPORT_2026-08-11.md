# Alpha Miss Report — 2026-08-11

Ambito: **solo** i 96 simboli di `config/trading.yaml → symbols.watchlist`. Non è uno scan di mercato.
Fonte numerica: `docs/evidence/dossier/2026-08-11.json` (Alpaca SIP, `adjustment=all`, generato
2026-08-12T08:00Z). Dove il dossier ha già il numero, non l'ho ricalcolato.
Settima seduta del periodo di osservazione (inizio 2026-08-03).

---

## 1. Executive summary

Giornata a indici in leggero calo (SPY −0,32%, QQQ −0,34%) e dispersione 1,54%, la più bassa della
finestra: **11 mover ≥3%, ma 9 su 11 al ribasso**. Il libro è long-only, quindi la lettura si
capovolge rispetto ai giorni precedenti — i miss di oggi non sono alpha perso, sono perdite evitate.

**5 mover su 11 erano in portafoglio** (ASML +3,80% e NOK +3,40% dal lato giusto; GOOGL −3,84%,
VALE −3,83%, DELL −3,69% dal lato sbagliato) e **6 sono stati mancati**: JD −4,63%, SPCX −3,93%,
ORCL −3,69%, ADBE −3,39%, BABA −3,38%, BIDU −3,25%. Tutti e sei scendono: **il costo dei miss di
oggi è zero, verificato, non stimato**.

Causa prevalente: **NO_NEWS, 4 su 6** (JD, ADBE, BABA, BIDU: zero righe in `news_log`), più 2
THIN_NEUTRAL (SPCX, ORCL). Nessun WRONG_SIGN, nessun FILTERED, come il 08-10: **secondo giorno
consecutivo in cui il gate 0,30 non è il collo di bottiglia** (F-009 senza occorrenze).

Copertura news 50/96 simboli a zero (52%), dentro la banda 40-55 delle sei sedute precedenti.
S4 ha aperto IBM alle 19:07 e ha chiuso SONY e HOOD; realizzato del giorno **−14,29 $** (tutto S4),
MTM del libro aperto **−19,46 $**, equity di chiusura **110.298,73 $**.
Il rosso di giornata non viene dai miss ma dalle posizioni tenute: VALE −30,21 $, GOOGL −26,37 $,
DELL −15,72 $ di MTM.

---

## 2. Rendimenti completi della watchlist (96 simboli)

`**grassetto**` = |return| ≥ 3% (soglia mover del dossier). "Catturato" = posizione aperta durante la
giornata, oppure tradata nella giornata; fra parentesi la sleeve detentrice.

| simbolo | return | catturato |
|---|---:|---|
| **ASML** | **+3.80%** | sì (S1) |
| **NOK** | **+3.40%** | sì (S1) |
| SBUX | +1.92% | sì (S1) |
| T | +1.87% | no |
| MRVL | +1.80% | sì (S1) |
| CMCSA | +1.79% | no |
| GM | +1.58% | sì (S1) |
| XLE | +1.25% | sì (legacy) |
| HD | +1.05% | no |
| AMD | +1.01% | sì (S1) |
| F | +0.94% | no |
| SOXX | +0.91% | sì (S1) |
| ERIC | +0.90% | no |
| CVX | +0.90% | sì (S1) |
| IBM | +0.89% | sì (S4, entrata oggi) |
| MU | +0.87% | sì (S1) |
| TSM | +0.86% | sì (S1) |
| ABBV | +0.85% | sì (S1) |
| META | +0.71% | no |
| CAT | +0.69% | sì (S1) |
| AMAT | +0.67% | sì (S1) |
| BP | +0.65% | no |
| JPM | +0.63% | sì (S1) |
| SHEL | +0.61% | sì (S1) |
| V | +0.60% | no |
| MMM | +0.60% | sì (S1) |
| TSLA | +0.58% | no |
| AXP | +0.58% | no |
| TM | +0.55% | no |
| SAP | +0.54% | no |
| WMT | +0.53% | no |
| VZ | +0.51% | no |
| C | +0.41% | sì (S1) |
| ARM | +0.40% | sì (S1) |
| GE | +0.37% | sì (S1) |
| DIS | +0.34% | no |
| IWM | +0.34% | sì (S1) |
| INFY | +0.32% | no |
| QCOM | +0.31% | no |
| TXN | +0.29% | sì (S1) |
| BAC | +0.22% | sì (legacy) |
| TMUS | +0.21% | no |
| INTC | +0.19% | no |
| BA | +0.19% | no |
| MCD | +0.16% | no |
| NOW | +0.08% | no |
| XOM | +0.01% | sì (S1) |
| GS | -0.01% | sì (legacy) |
| XLF | -0.02% | sì (S1) |
| CRM | -0.02% | no |
| NVDA | -0.02% | no |
| WFC | -0.08% | no |
| WDC | -0.09% | sì (S4) |
| DB | -0.10% | no |
| MS | -0.12% | sì (legacy) |
| XLK | -0.12% | sì (S1) |
| HOOD | -0.15% | sì (S4, aperta e chiusa oggi) |
| PLTR | -0.17% | no |
| SNOW | -0.17% | sì (S1) |
| XLV | -0.26% | sì (S1) |
| MA | -0.31% | no |
| SPY | -0.32% | sì (legacy) |
| PANW | -0.32% | sì (S1) |
| QQQ | -0.34% | sì (S1) |
| MRK | -0.38% | sì (S1) |
| MSFT | -0.44% | no |
| UBS | -0.50% | sì (legacy) |
| ROKU | -0.61% | sì (legacy) |
| JNJ | -0.77% | sì (S1) |
| PG | -0.84% | no |
| SONY | -0.88% | sì (S4, chiusa oggi) |
| COST | -0.88% | no |
| RIO | -0.90% | sì (legacy) |
| AAPL | -1.09% | sì (S1) |
| NVO | -1.17% | no |
| LLY | -1.37% | sì (S1) |
| AVGO | -1.50% | no |
| PFE | -1.59% | no |
| RDDT | -1.59% | no |
| UNH | -1.60% | sì (legacy) |
| CSCO | -1.75% | sì (S1) |
| NKE | -1.88% | no |
| AZN | -1.95% | no |
| NFLX | -1.97% | no |
| AMZN | -2.09% | no |
| PBR | -2.18% | sì (legacy) |
| BRK.B | -2.46% | no |
| **BIDU** | **-3.25%** | no |
| **BABA** | **-3.38%** | no |
| **ADBE** | **-3.39%** | no |
| **ORCL** | **-3.69%** | no |
| **DELL** | **-3.69%** | sì (S1) |
| **VALE** | **-3.83%** | sì (S1) |
| **GOOGL** | **-3.84%** | sì (legacy) |
| **SPCX** | **-3.93%** | no |
| **JD** | **-4.63%** | no |

Nessun simbolo della watchlist è rimasto senza barre (`simboli_senza_dati: []` nel dossier).

---

## 3. Miss classificati

Soglia mover: |return| ≥ 3%, la stessa del dossier. La motivo così: con dispersione cross-sectional
1,54% il 3% è circa 2σ, cioè il movimento che non si spiega col rumore di giornata e che una
strategia news-driven dovrebbe avere qualche speranza di vedere.

| simbolo | return | categoria | evidenza |
|---|---:|---|---|
| JD | −4.63% | NO_NEWS | zero righe in `news_log` il 08-11, zero segnali. Mover più forte della giornata. |
| SPCX | −3.93% | THIN_NEUTRAL | 6 articoli, 6 segnali, **nessuno su SPCX**: Rocket Lab (id 7184, 7197, 7239), Tesla (7195), lista generica "10 Communication Services Stocks With Whale Alerts" (7335), SpaceX/AST SpaceMobile (7343). Punteggi +0,165 (fallback single-model), +0,016, +0,012, −0,120 (fallback), 0,000, 0,000 → `SKIP_THRESHOLD`. |
| ORCL | −3.69% | THIN_NEUTRAL | 1 articolo ticker-specifico, "What's Going On With Oracle Stock Tuesday?" (id 7254, pubblicato 15:31). Segnale unico alle 16:00: **−0,0516**, segno corretto ma magnitudine 1/7 del gate. Sei `SKIP_THRESHOLD` fra 16:07 e 17:22. Long-only: un segnale negativo non può comunque produrre un ordine. |
| ADBE | −3.39% | NO_NEWS | zero righe in `news_log`, zero segnali. |
| BABA | −3.38% | NO_NEWS | zero righe in `news_log`, zero segnali. |
| BIDU | −3.25% | NO_NEWS | zero righe in `news_log`, zero segnali. |

Conteggio: **NO_NEWS 4, THIN_NEUTRAL 2, WRONG_SIGN 0, FILTERED 0, OUT_OF_STRATEGY_SCOPE 0**.

**Il costo di questi sei miss è 0,00 $, verificato e non stimato**: tutti e sei sono mover al
ribasso e il libro è long-only, quindi nessuna delle sei "occasioni" era tradabile nella direzione
del movimento. Su una giornata così la copertura news mancante non ci è costata nulla — ci ha
risparmiato sei ingressi sbagliati. Va detto per simmetria: è la stessa lacuna che il 08-03 e il
08-04 costava rispettivamente 344,92 $ e 452,54 $ di alpha stimato, quando i mover salivano.

---

## 4. Mover catturati: esito

| simbolo | return | sleeve | esito |
|---|---:|---|---|
| ASML | +3.80% | S1 (dal 07-14) | **+24,88 $ MTM**, il miglior contributore della giornata. |
| NOK | +3.40% | S1 (dal 07-14) | **+12,88 $ MTM**. Vedi §7: S4 aveva un segnale +0,725 sopra il gate e non ha potuto aggiungere. |
| GOOGL | −3.84% | legacy (dal 07-10, `stop_strategy` NULL) | **−26,37 $ MTM**. |
| VALE | −3.83% | S1 (dal 07-14) | **−30,21 $ MTM**, la peggiore posizione del giorno. |
| DELL | −3.69% | S1 (dal 07-13) | **−15,72 $ MTM**. |

Trade del giorno (nessuno su un mover):

| simbolo | sleeve | evento | esito |
|---|---|---|---|
| SONY | S4 | chiusa 14:22 dopo 22h15 (ingresso 08-10 16:07) | net **−5,47 $**, `portfolio_sell`. Uscita a segnale scaduto in tempo di parete, senza contro-segnale (score ancora +0,431). Il prezzo è poi **sceso** ancora: `drift_post_uscita` −5,03 $, quindi stavolta il difetto ha giovato. |
| HOOD | S4 | aperta 14:07 a 94,18 su score +0,360, chiusa 18:22 a 93,69 | net **−8,82 $**, `portfolio_sell` allo scadere delle 4h. Il prezzo è poi **risalito**: `drift_post_uscita` +8,91 $. `entry_percentile` 0,601 — comprata nel terzo alto del range di giornata. |
| IBM | S4 | aperta 19:07 a 238,01 su score +0,388 ("IBM Lands $240 Million AI Deal with Together AI") | +2,08 $ MTM a fine giornata; `entry_percentile` 0,404. Ingresso a 53 minuti dalla chiusura: è il profilo esatto che F-024 chiude al primo ciclo del giorno dopo. |

24 cicli portfolio, dalle 14:07 alle 19:52, cadenza 15 minuti **senza alcun gap**.

---

## 5. Pattern osservato

**Rotazione fuori dal software/AI americano e dagli ADR cinesi, dentro l'hardware europeo.**
Il raggruppamento è netto, non forzato:

- **ADR cinesi: 3 su 3 in fondo alla classifica.** JD −4,63%, BABA −3,38%, BIDU −3,25%. Nessuno dei
  tre ha una riga di news in tutta la giornata.
- **Software/cloud americano a larga capitalizzazione:** ORCL −3,69%, ADBE −3,39%, GOOGL −3,84%,
  più DELL −3,69% sul lato hardware-server. Con CRM −0,02% e MSFT −0,44% fermi, la gamba è
  selettiva, non un selloff di settore.
- **I due unici mover positivi sono europei e di hardware:** ASML +3,80%, NOK +3,40%.
- **Non è un selloff di semiconduttori:** NVDA −0,02%, AMD +1,01%, SOXX +0,91%, MU +0,87%,
  TSM +0,86%, AMAT +0,67%. La gamba negativa colpisce chi *compra* AI, non chi la *vende*.

Coerente con questa lettura, gli unici titoli con più copertura editoriale della giornata parlano
di NVIDIA e del suo impegno da 500 miliardi ("Neocloud Stocks Rally on Tuesday After NVIDIA's $500
Billion Pledge", "Nvidia's Masterstroke To Turn Itself Into An Asset Class") — cioè del lato che
sale, non di quello che scende.

---

## 6. Confronto con i giorni precedenti della finestra

| data | SPY | σ cross | mover | up/down | zero-news | catturati | causa dominante |
|---|---:|---:|---:|---:|---:|---:|---|
| 07-31 | +0,72% | 3,36% | 11 | 6/5 | 55 | 5 | NO_NEWS + THIN + FILTERED (pari) |
| 08-03 | +1,42% | 2,64% | 19 | 16/3 | 41 | 10 | THIN_NEUTRAL |
| 08-04 | +1,77% | 4,40% | 29 | 27/2 | 42 | 20 | NO_NEWS |
| 08-05 | −0,20% | 2,28% | 11 | 4/7 | 51 | 7 | NO_NEWS |
| 08-06 | −0,16% | 2,24% | 8 | 4/4 | 40 | 4 | THIN_NEUTRAL |
| 08-07 | +0,61% | 2,52% | 12 | 10/2 | 52 | 5 | THIN_NEUTRAL |
| 08-10 | −0,03% | 1,95% | 13 | 8/5 | 43 | 9 | NO_NEWS + THIN (pari) |
| **08-11** | **−0,32%** | **1,54%** | **11** | **2/9** | **50** | **5** | **NO_NEWS (4/6)** |

Ricorrenze che il giorno conferma:

1. **La copertura news a zero resta stabile fra il 42% e il 57% della watchlist** (oggi 52%), per la
   settima seduta consecutiva. È l'osservazione più regolare della finestra, e cumulativamente
   NO_NEWS è la causa di miss più frequente (18 casi su 43 classificati).
2. **Secondo giorno consecutivo senza FILTERED e senza WRONG_SIGN.** Dopo quattro giorni consecutivi
   (08-03 → 08-06) in cui il gate 0,30 scartava segnali col segno corretto su mover forti, dal 08-07
   in poi il collo di bottiglia è tornato a monte, nel dato. Da tenere presente che il gate è stato
   riportato a 0,30 il 08-07 (deroga #191): il confronto pre/post non è omogeneo.
3. **La dispersione cross-sectional si sta comprimendo** — 4,40% il 08-04, poi 2,52 / 1,95 / 1,54.
   Meno mover forti significa meno occasioni sia di alpha sia di errore: sconta l'informatività di
   ogni singola giornata verso la scadenza del 28/09.

Discontinuità rispetto a tutti i giorni precedenti: **è la prima seduta della finestra in cui i
mover sono per l'82% al ribasso**. La conclusione sui miss va quindi letta al contrario del solito e
non va mediata coi giorni precedenti senza dirlo.

---

## 7. Segnalazioni

Nessuna proposta di taratura né di fix: periodo di sola osservazione (`OBSERVATION_CHARTER.md`).
Dove qualcosa somiglia a un difetto e non a un limite noto, lo dico e mi fermo lì.

**[F-032] Sembra un difetto, ed è una correzione deployata che non funziona.** La
canonicalizzazione `BRKB → BRK.B` (#226, commit `a2ad132`) è **presente e funzionante**
nell'immagine in esecuzione — verificato chiamandola dentro `alembic-worker-1`:
`canonicalizza_ticker('BRKB') → 'BRK.B'`. Ciononostante il 08-11 `news_log` contiene ancora **6
righe con ticker `BRKB`**, tutte accodate *dopo* il redeploy (`raw_ingested_at` 14:15, 15:15, 17:15
dell'08-11; container creati alle 12:20 UTC), e altrettanti `sentiment_signals` su `BRKB`. In tutta
la storia del DB le righe con ticker `BRK.B` sono **zero**. La causa è a valle
dell'ingestione: `src/workers/sentiment.py:274` fa `clean_symbol = sanitize_ticker(raw_symbol)`, e
`src/text/sanitizer.py:86` chiude con `re.sub(r"[^A-Z0-9]", "", ascii_only)` — il punto viene tolto,
`result.symbol` torna `BRKB`, e sotto quel nome vengono scritti sia il segnale sia la riga di
`news_log`. La canonicalizzazione a monte c'è, la sanitizzazione a valle la annulla.
Il finding era stato registrato ieri con `stato: chiuso` proprio perché la correzione risultava
deployata: l'ho riportato ad `aperto` nel ledger, con la verifica sopra come motivazione.

**[F-031] Il guard anti-pyramiding ha bloccato l'unico segnale forte della giornata su un mover.**
NOK, +3,40%, articolo ticker-specifico "Why Is Nokia Stock Surging on Tuesday?" (id 7253): segnale
**+0,725 alle 16:07** e **+0,605 alle 18:07**, entrambi ampiamente sopra il gate 0,30, entrambi
`SKIP_PYRAMIDING` — "gia' a libro dal 2026-07-14, peso non allocato 2,0%". Rispetto alle due
occorrenze precedenti cambia una cosa: **la traccia in `execution_decisions` adesso c'è**, quindi la
seconda metà del titolo del finding ("non lascia alcuna traccia") non descrive più il presente.
Costo reale ~2,20 $: alle 16:07 NOK quotava 9,465 contro un close di 9,450 — **l'intero +3,4% era il
gap di apertura**, e l'articolo è uscito alle 15:44, a movimento concluso.

**[F-030] La notizia continua ad arrivare a movimento avvenuto.** Misura sui quattro mover con
copertura, come frazione del movimento apertura→chiusura già realizzata al prezzo del momento del
primo segnale: GOOGL 34,4%, SPCX 57,1%, ORCL **110,8%**, NOK **121,1%**. Mediana 84%, in linea con
l'82% del 08-07 e con la seconda occorrenza del 08-10. Su ORCL e NOK la frazione supera il 100%
perché al primo segnale il prezzo aveva già oltrepassato il livello di chiusura: la notizia arriva
non solo in ritardo, ma dopo l'estremo.

**[F-024] Due uscite per scadenza del segnale in tempo di parete, con esiti opposti.** SONY: chiusa
alle 14:22, 22h15 di tenuta, motivazione registrata "S4 signal was stale but FIX-D re-admitted it
this cycle — open position, no counter-signal ... age=19.6h vs max_age=4h, score=+0.431"; il prezzo
è poi sceso, quindi l'uscita ha **risparmiato** 5,03 $. HOOD: aperta 14:07 e chiusa 18:22 alla
scadenza delle 4h con la stessa identica motivazione, e il prezzo è poi **risalito**, quindi
l'uscita è costata 8,91 $. Netto della giornata +3,88 $ di costo. Il punto non è il segno: è che in
entrambi i casi la posizione è stata chiusa **senza alcun contro-segnale**, per il solo trascorrere
del tempo di parete, e la telemetria stessa registra che "the mechanism that zeroed it is not
recorded". IBM, aperta alle 19:07, è il prossimo candidato allo stesso trattamento domani mattina.

**[F-012] Metà delle righe scorate viene ancora da articoli fan-out.** 26 articoli su 109 (24%)
sono taggati a 2+ ticker e generano **79 delle 162 righe** della giornata (48,8%), in linea con la
serie 51 / 66 / 53 / 55 / 51,5%. Caso della giornata: SPCX, mover a −3,93%, ha **sei** righe di
copertura e **nessuna** parla di SPCX — tre di Rocket Lab, una di Tesla, una di SpaceX/AST
SpaceMobile e una lista generica ("10 Communication Services Stocks With Whale Alerts") che è stata
scorata sia su SPCX sia su GOOGL. Costo 0,00 verificato: nessuno di quei punteggi ha superato il
gate, quindi nessun ordine è nato da un pezzo su società terze.

**[F-020] Un terzo della giornata editoriale è attribuito a tre banche che non c'entrano.** GS 25
righe, MS 23, DB 7 — **55 su 162, il 34%**, in peggioramento sul 30,1% del 08-10 — tutte via
`org_lookup`, e **nessuna riguarda le tre banche**: fra i titoli attribuiti a GS ci sono
"Hamilton Lane Q1 2027 Earnings Call Transcript", "DuPont Q2 2026 Earnings Call Transcript",
"NRG Energy Q2 2026 Earnings Call Transcript"; a DB finiscono "SpaceX analyst plots path to bold
$100 billion claim", "Kimco Q2 2026 Earnings Call Transcript", "US-Iran impasse sends oil up".
GS e MS restano i due ticker più coperti dell'intera watchlist mentre i mover della giornata hanno
zero righe.

**[F-001] Copertura news a zero su 50 dei 96 simboli (52%).** Dentro la banda 40-55 delle sei sedute
precedenti. Quattro dei sei miss del giorno sono NO_NEWS puri (JD −4,63%, ADBE −3,39%, BABA −3,38%,
BIDU −3,25%). **Costo 0,00 verificato, non stimato**: tutti e quattro sono mover al ribasso su un
libro long-only.

**[F-010] Quattro segnali esclusi dal ranking perché single-model.** 44 dei 162 segnali della
giornata (27%) hanno `fallback_used=true`. Alle 14:07 quattro `SKIP_FALLBACK`: MRVL (score
**+0,423**, conf 0,65), IWM (−0,150), WDC (−0,055), RIO (0,000). Solo MRVL era sopra il gate ed è
finito +1,80% sulla giornata; controfattuale corto misurato: entrata al prezzo delle 14:07
(211,195) e chiusura a 211,838 su size S4 tipica → **6,70 $** di alpha mancato.

**[F-002] Attribuzione di strategia mancante su 11 delle 47 posizioni aperte.** BAC, GOOGL, GS, MS,
PBR, RIO, ROKU, SPY, UBS, UNH, XLE — lo stesso insieme del 08-07 e del 08-10, tutte entrate il
07-10, tutte con `trades.stop_strategy` NULL. Rilevante oggi perché la peggiore posizione per
MTM della giornata dopo VALE è GOOGL (−26,37 $), che è dentro questo insieme: la sua perdita non è
attribuibile a nessuna sleeve.

---

## 8. Nota di metodo

I numeri di mercato, gli ingressi, le chiusure e gli aggregati vengono dal dossier deterministico e
non sono stati ricalcolati. Sono miei, e derivati da query dirette al DB e da Alpaca: la
classificazione delle cause dei miss (che richiede di leggere i titoli degli articoli), i
controfattuali in dollari, il MTM per posizione, le frazioni di movimento già avvenuto di §7, e la
verifica della catena di canonicalizzazione del ticker.
