# Alpha Miss Report — 2026-08-07

Ambito: **solo** i 96 simboli di `config/trading.yaml -> symbols.watchlist`. Non e' uno scan di
mercato: la domanda e' "abbiamo perso qualcosa che potevamo effettivamente tradare".

Fonte numerica: `docs/evidence/dossier/2026-08-07.json` (deterministico, Alpaca SIP `adjustment=all`).
Ogni cifra di mercato viene da li'. Il lavoro di questa sessione e' la classificazione delle cause
leggendo il testo degli articoli e la catena decisionale nel DB.

Periodo di **sola osservazione** (`docs/evidence/OBSERVATION_CHARTER.md`, giorno 5 di 40):
nessuna proposta di taratura, nessun fix. Solo evidenza.

---

## 1. Executive summary

Giornata di dispersione media (sigma 2,52%) con indici in rialzo moderato: **SPY +0,61%, QQQ +1,17%**.
**12 mover >= 3%** sulla watchlist, **10 in salita e 2 in discesa**.

Dei 12, **5 erano gia' in portafoglio** (SNOW, MRVL, DELL sul lato giusto; WDC e PBR sul lato
sbagliato) e **7 sono stati mancati**. Nessun mover e' stato *comprato* durante la giornata: l'unico
ingresso e' SBUX (S1, +0,40%, non un mover) e l'unica uscita e' BRK.B (S1, -2,77 $).

La causa prevalente dei miss **non e' l'assenza di notizie** (3 casi su 7) ma la **loro
irrilevanza**: 4 mover su 7 avevano copertura, e per tre di essi (SPCX +15,83%, RDDT +7,18%,
NOW +6,42%) l'unica o la quasi totalita' della copertura e' un articolo-lista generico su societa'
terze. Il modello lo dice esplicitamente nella propria motivazione — *"the article provides only a
generic statement about whale alerts without any mention of RDDT"* — e produce correttamente 0,000.
Il collo di bottiglia oggi e' **a monte del gate**, non nel gate.

Fatto nuovo e quantificato: **quando la notizia su un mover arriva a produrre un punteggio, in
mediana l'82% del movimento intraday della giornata e' gia' avvenuto** (SPCX 71%, RDDT 81%, NOW 83%,
PLTR 96%) — e questo *nonostante* la latenza di ingestione sia oggi la migliore della finestra
(mediana 39,6 min contro ~100 dei giorni precedenti). Vedi [F-030].

---

## 2. Rendimenti completi della watchlist

96 simboli, tutti con barre disponibili (`simboli_senza_dati: []`). Ordinati per rendimento.
"In book" = posizione aperta durante la seduta del 08-07.

| # | Simbolo | Return | In book | Mover >=3% |
|--:|---|--:|---|---|
| 1 | SPCX | +15.83% | no | **si** |
| 2 | PLTR | +10.32% | no | **si** |
| 3 | RDDT | +7.18% | no | **si** |
| 4 | NOW | +6.42% | no | **si** |
| 5 | QCOM | +4.66% | no | **si** |
| 6 | SNOW | +3.93% | si | **si** |
| 7 | MRVL | +3.89% | si | **si** |
| 8 | DELL | +3.68% | si | **si** |
| 9 | SAP | +3.36% | no | **si** |
| 10 | CRM | +3.20% | no | **si** |
| 11 | HOOD | +2.84% | no |  |
| 12 | TSLA | +2.83% | no |  |
| 13 | NVO | +2.81% | no |  |
| 14 | TXN | +2.76% | si |  |
| 15 | ORCL | +2.47% | no |  |
| 16 | NVDA | +2.27% | no |  |
| 17 | AMAT | +2.21% | si |  |
| 18 | ASML | +2.15% | si |  |
| 19 | PFE | +2.14% | no |  |
| 20 | ROKU | +2.03% | si |  |
| 21 | SOXX | +2.02% | si |  |
| 22 | ADBE | +1.91% | no |  |
| 23 | INTC | +1.84% | si |  |
| 24 | HD | +1.75% | no |  |
| 25 | UBS | +1.74% | si |  |
| 26 | AVGO | +1.71% | no |  |
| 27 | IBM | +1.65% | no |  |
| 28 | SONY | +1.56% | no |  |
| 29 | RIO | +1.46% | si |  |
| 30 | XLK | +1.42% | si |  |
| 31 | TM | +1.39% | no |  |
| 32 | F | +1.38% | no |  |
| 33 | INFY | +1.38% | no |  |
| 34 | BABA | +1.26% | no |  |
| 35 | PANW | +1.22% | si |  |
| 36 | MMM | +1.21% | si |  |
| 37 | MS | +1.21% | si |  |
| 38 | QQQ | +1.17% | si |  |
| 39 | DB | +1.14% | no |  |
| 40 | IWM | +1.11% | si |  |
| 41 | BA | +0.96% | no |  |
| 42 | ABBV | +0.89% | si |  |
| 43 | C | +0.88% | si |  |
| 44 | AZN | +0.88% | no |  |
| 45 | JNJ | +0.88% | si |  |
| 46 | AMZN | +0.82% | no |  |
| 47 | UNH | +0.77% | si |  |
| 48 | CMCSA | +0.75% | no |  |
| 49 | XLV | +0.75% | si |  |
| 50 | GM | +0.74% | si |  |
| 51 | GS | +0.68% | si |  |
| 52 | SPY | +0.61% | si |  |
| 53 | NFLX | +0.61% | no |  |
| 54 | JD | +0.49% | no |  |
| 55 | CSCO | +0.45% | si |  |
| 56 | TSM | +0.44% | si |  |
| 57 | SBUX | +0.40% | si |  |
| 58 | META | +0.37% | no |  |
| 59 | BIDU | +0.35% | no |  |
| 60 | JPM | +0.34% | si |  |
| 61 | T | +0.34% | no |  |
| 62 | AAPL | +0.29% | si |  |
| 63 | BAC | +0.27% | si |  |
| 64 | DIS | +0.22% | no |  |
| 65 | WFC | +0.18% | no |  |
| 66 | MRK | +0.16% | si |  |
| 67 | VZ | +0.15% | no |  |
| 68 | MSFT | +0.03% | no |  |
| 69 | VALE | -0.07% | si |  |
| 70 | ERIC | -0.10% | no |  |
| 71 | COST | -0.14% | no |  |
| 72 | WMT | -0.20% | no |  |
| 73 | XLF | -0.36% | si |  |
| 74 | MU | -0.44% | si |  |
| 75 | AXP | -0.49% | no |  |
| 76 | LLY | -0.52% | si |  |
| 77 | BRK.B | -0.54% | si |  |
| 78 | MCD | -0.64% | no |  |
| 79 | NKE | -0.71% | no |  |
| 80 | NOK | -0.74% | si |  |
| 81 | PG | -0.80% | no |  |
| 82 | GOOGL | -0.96% | si |  |
| 83 | XLE | -1.13% | si |  |
| 84 | XOM | -1.16% | si |  |
| 85 | GE | -1.19% | si |  |
| 86 | AMD | -1.21% | si |  |
| 87 | SHEL | -1.23% | si |  |
| 88 | CVX | -1.41% | si |  |
| 89 | BP | -1.42% | no |  |
| 90 | ARM | -1.43% | si |  |
| 91 | TMUS | -1.54% | no |  |
| 92 | CAT | -1.72% | si |  |
| 93 | V | -2.15% | no |  |
| 94 | MA | -2.26% | no |  |
| 95 | PBR | -3.02% | si | **si** |
| 96 | WDC | -3.81% | si | **si** |

Riferimenti: SPY +0,61%, QQQ +1,17%, dispersione cross-sectional 2,52%.

---

## 3. Miss classificati

Soglia mover: **|return| >= 3%**, la stessa del dossier (`soglia_mover: 0.03`) e la stessa usata in
tutti i report precedenti della finestra. La motivo cosi': con una dispersione giornaliera di 2,52%
un movimento sotto il 3% e' dentro una deviazione standard, cioe' non distinguibile dal rumore
cross-sectional; sopra il 3% il movimento e' idiosincratico e quindi in linea di principio
attribuibile a un evento che una pipeline news dovrebbe vedere.

Un mover conta come **miss** se non era in portafoglio e non e' stato tradato. I 2 mover al ribasso
(WDC, PBR) erano entrambi in book e sono trattati in §4: il libro e' long-only, quindi su di essi non
c'era alpha da catturare in nessun caso.

| Simbolo | Return | Categoria | Evidenza |
|---|--:|---|---|
| SPCX | +15,83% | THIN_NEUTRAL | 6 articoli, 6 segnali, massimo **+0,120** contro gate 0,300. Cinque dei sei articoli non parlano dell'evento di prezzo: due su Kevin O'Leary che medita un ingresso (`Kevin O'Leary Sat Out SpaceX's IPO`, `Kevin O'Leary Eyes SpaceX as AI Bets Soar`), uno sui chip (`Chip Stocks Find Buyers After Earnings Shock`), uno di whale-alert generico, uno su oro e argento. Il sesto (`SpaceX Stock Meltdown Takes $28 Billion Bite Out of Google's Portfolio`, 15:45) tratta SpaceX attraverso il bilancio di Alphabet. Ultimo segnale del giorno: **0,000**, da un articolo su oro e argento. |
| PLTR | +10,32% | THIN_NEUTRAL | 2 articoli. Il primo (17:15) e' un pezzo su ETF tematici AI in cui PLTR e' un tag di fan-out, score +0,013. Il secondo (18:30) e' l'unico PLTR-specifico — `QUICK SPARK: Palantir Stock Up 38% This Week in Software Snapback` — score **+0,120**, e la motivazione del modello e' corretta: *"the week-long rally reflects positive investor sentiment but shows no new company-specific driver"*. L'articolo **descrive** il rialzo, non lo anticipa: alle 18:30 il 96% del movimento intraday era gia' avvenuto. |
| RDDT | +7,18% | THIN_NEUTRAL | **1 solo articolo**: `8 Communication Services Stocks With Whale Alerts In Today's Session`, un listicle generico. Score **0,000**, motivazione del modello: *"the article provides only a generic statement about whale alerts without any mention of RDDT; thus no clear impact can be inferred"*. La copertura esiste formalmente e non contiene informazione. |
| NOW | +6,42% | THIN_NEUTRAL | **1 solo articolo**: `10 Information Technology Stocks With Whale Alerts In Today's Session`, stessa famiglia del precedente. Score **0,000**, motivazione: *"no information in the article indicates NOW is referenced or affected; the article merely reports a generic whale-alert tool"*. |
| QCOM | +4,66% | NO_NEWS | Zero righe in `news_log`, zero in `sentiment_signals`, zero in `execution_decisions`. Nessuna catena decisionale esiste. **Terza occorrenza NO_NEWS su QCOM nella finestra** (08-04 a +7,32%, 08-05 a -3,16%, oggi a +4,66%). |
| SAP | +3,36% | NO_NEWS | Zero righe in `news_log`. Ricorrenza sistematica: SAP e' mancato per assenza o genericita' di copertura il 07-24, 07-27, 07-28, 08-03, 08-04 e oggi. |
| CRM | +3,20% | NO_NEWS | Zero righe in `news_log` oggi. Il 08-06, con CRM a -3,22%, l'unica copertura era il listicle `10 Information Technology Stocks Whale Activity In Today's Session`: alterna fra assenza e copertura non informativa. |

**Conteggio:** NO_NEWS 3 · THIN_NEUTRAL 4 · WRONG_SIGN 0 · FILTERED 0 · OUT_OF_STRATEGY_SCOPE 0.

Nessun FILTERED oggi: nessun segnale della watchlist ha superato il gate ed e' stato poi scartato da
ranking o breadth. Il gate in vigore era **0,300**, cioe' il valore di design — lo stopgap Redis
registrato nella carta il 08-07 ha effetto (tutte le 584 righe `SKIP_THRESHOLD` recitano
`< feedback threshold 0.300`, contro lo 0,350-0,400 del 08-06).

Nessun WRONG_SIGN: nessun segnale della giornata ha segno opposto al movimento su un mover.

### 3.1 Quanto era realmente catturabile

Il movimento di oggi e' **quasi interamente intraday**, al contrario del 08-04 dove il 55% stava nel
gap. Questo rende i miss piu' gravi del solito: non e' alpha inaccessibile per costruzione.

| Simbolo | Gap apertura | Intraday | Totale |
|---|--:|--:|--:|
| SPCX | +0,04% | **+15,78%** | +15,83% |
| PLTR | +2,66% | +7,46% | +10,32% |
| RDDT | +1,61% | +5,48% | +7,18% |
| NOW | +3,68% | +2,64% | +6,42% |
| QCOM | +1,67% | +2,94% | +4,66% |
| SAP | +1,85% | +1,48% | +3,36% |
| CRM | +2,31% | +0,86% | +3,20% |

Ma il movimento catturabile **dal momento in cui il segnale esiste** e' molto piu' piccolo, ed e' il
numero onesto per un controfattuale:

| Simbolo | Primo segnale | Prezzo | Residuo a chiusura | Su size S4 tipica 2.200 $ |
|---|---|--:|--:|--:|
| SPCX | 14:15 | 127,92 | +4,16% | +91,58 $ |
| SPCX | 15:00 (massimo residuo) | 126,15 | +5,62% | +123,62 $ |
| PLTR | 17:15 | 171,15 | +0,29% | +6,43 $ |
| PLTR | 18:30 | 170,10 | +0,91% | +20,05 $ |
| RDDT | 18:15 | 159,97 | +0,95% | +20,83 $ |
| NOW | 18:30 | 124,34 | +0,43% | +9,50 $ |

SPCX aveva gia' fatto **+11,3% nei primi 45 minuti di seduta**, prima che il primo articolo fosse
ingerito. Nelle stime di costo del §7 uso il **return pieno** per non rompere la comparabilita' con
le occorrenze precedenti della serie, e riporto sempre accanto il residuo post-segnale.

---

## 4. Titoli intercettati: esito

Nessun mover e' stato **comprato** oggi. I 5 mover "catturati" erano gia' in portafoglio da giorni
precedenti.

| Simbolo | Return | Strategia | Ingresso | MTM del giorno |
|---|--:|---|---|--:|
| SNOW | +3,93% | S1 | 08-05 19:07 @ 319,01 | **+21,58 $** |
| MRVL | +3,89% | S1 | 07-14 14:07 @ 221,91 | **+12,69 $** |
| DELL | +3,68% | S1 | 07-13 14:07 @ 427,69 | **+14,99 $** |
| WDC | -3,81% | S4 | 07-21 16:37 @ 549,24 | **-51,33 $** |
| PBR | -3,02% | *(NULL)* | 07-10 14:07 @ 17,20 | **-22,17 $** |

I cinque mover in book fanno **-24,24 $ netti**: i tre vincenti non compensano WDC. WDC e' la
posizione di F-025 (S4 senza orizzonte di uscita per le posizioni tiepide), aperta il 21 luglio e
oggi a -20,9% dall'ingresso. PBR e' una delle 11 posizioni con `stop_strategy` NULL (F-002): uno dei
due estremi negativi del giorno resta fuori dallo split S1/S4 richiesto dalla domanda di uscita 2.

**Trade della giornata**

| Simbolo | Strategia | Evento | Prezzo | Esito |
|---|---|---|--:|---|
| SBUX | S1 | BUY 14:07 | 105,39 | aperta a fine giornata, MTM +1,25 $ |
| BRK.B | S1 | SELL 14:22, `portfolio_sell` | 520,52 | **net -2,77 $**, tenuta 21h |

Realizzato del giorno: **-2,77 $** (tutto S1; S4 zero trade). MTM del libro aperto: **+133,36 $**.
NAV di chiusura 110.179,88 $ (variazione +130,59 $ su una seduta SPY +0,61%).

Ingresso SBUX a `entry_percentile` 0,541 contro mediana mobile 20g 0,526: a meta' del range della
giornata, non nel quartile alto come il 08-06. Uscita BRK.B con `drift_post_uscita` +1,68 $, contro
mediana mobile 20g +3,19 $: uscita mediamente meno costosa del solito.

24 cicli portfolio, dalle 14:07 alle 19:52, **nessun gap superiore a 16 minuti**. La cadenza ha
funzionato: l'assenza di ordini non e' un problema di scheduling.

---

## 5. Pattern osservato

**Snapback del software e del complesso speculativo contro energia e pagamenti, su un dato
macro di attenuazione dei tassi.**

Il tema e' leggibile dalla coda alta ed e' coerente con il titolo di uno degli articoli ingeriti oggi
(`S&P 500 Hits Record As Jobs Shock Sinks Rate-Hike Bets`): un dato sull'occupazione che smonta le
aspettative di rialzo dei tassi, quindi risk-on sulla duration lunga.

- **Dentro — software/SaaS enterprise:** NOW +6,42%, SNOW +3,93%, SAP +3,36%, CRM +3,20%,
  PLTR +10,32%, ORCL +2,47%. L'articolo PLTR di oggi lo chiama per nome: *"Software Snapback"*.
- **Dentro — speculativo ad alto beta:** SPCX +15,83% (dopo -13,61% il 08-05 e un rimbalzo intraday
  il 08-06), RDDT +7,18%, HOOD +2,84%, TSLA +2,83%.
- **Semiconduttori divisi**, quindi non e' un tema: QCOM +4,66%, MRVL +3,89%, AMAT +2,21%,
  ASML +2,15%, TXN +2,76% contro AMD -1,21%, ARM -1,43%, MU -0,44%, WDC -3,81%. SOXX +2,02%.
- **Fuori — energia:** PBR -3,02%, CVX -1,41%, SHEL -1,23%, BP -1,42%, XOM -1,16%, XLE -1,13%.
- **Fuori — pagamenti:** MA -2,26%, V -2,15%, con AXP -0,49%. Il resto dei finanziari e' piatto
  (JPM +0,34%, BAC +0,27%, GS +0,68%), quindi e' un fatto di settore-pagamenti, non di banche.
- **WDC -3,81%** prosegue il crollo storage cominciato il 08-06 (-13,03%): e' l'unico filo che
  attraversa due sedute consecutive.

Il libro e', per una volta, prevalentemente dalla parte giusta (+133,36 $ di MTM), ma **non grazie
ai mover**: i cinque mover detenuti fanno -24,24 $ e il guadagno viene dal resto delle 48 posizioni.

---

## 6. Confronto coi giorni precedenti della finestra

Quinta seduta osservata (08-03, 08-04, 08-05, 08-06, 08-07). Tre pattern ricorrono.

**a) La rotazione cambia direzione ogni giorno.** 08-03 dentro software / fuori difensivi;
08-04 rally violento sui semi; 08-05 dentro pharma / fuori semi; 08-06 dentro telecom+energia /
fuori finanziari+storage; 08-07 dentro software+speculativo / fuori energia+pagamenti. Cinque
sedute, cinque direzioni diverse, con l'energia che oggi inverte esattamente il 08-06. Nessuna
delle due strategie ha un meccanismo che reagisca a una rotazione con questa frequenza: S1 e'
momentum a frequenza mensile dichiarata, S4 e' event-driven per singolo titolo.

**b) Gli stessi ticker mancano per lo stesso motivo.** QCOM e' NO_NEWS per la terza volta in
quattro sedute (08-04, 08-05, 08-07); SAP per la sesta volta dal 07-24; RDDT e NOW hanno come unica
copertura un listicle whale-alert, esattamente la forma vista il 08-06 su BA e CRM. La copertura
mancante non e' distribuita a caso: e' concentrata su un insieme stabile di ticker.

**c) La quota di copertura scoperta e' stabile in banda stretta.** 55/96 (07-31), 41/96 (08-03),
42/96 (08-04), 51/96 (08-05), 40/96 (08-06), **52/96 (08-07)**. Oscilla fra il 42% e il 57% senza
tendenza.

**Una discontinuita' rispetto ai giorni precedenti, e va detta perche' e' un miglioramento.**
La latenza di ingestione news oggi e' **mediana 39,6 minuti, p90 106,9** contro le mediane di
~100-105 minuti delle sedute 07-31 -> 08-05 (F-019). Non registro una ricorrenza di F-019 su questa
seduta: sarebbe scorretto contare come occorrenza di un difetto un giorno in cui la grandezza
misurata migliora di due volte e mezzo. Il fatto rilevante e' che **il miglioramento della latenza
non ha cambiato nulla**: l'82% del movimento era comunque gia' avvenuto quando il segnale e' nato.
Questo separa nettamente due cose finora confuse — la lentezza della nostra pipeline e il fatto che
l'articolo stesso sia scritto dopo il movimento. Vedi [F-030].

---

## 7. Segnalazioni

Nessuna proposta di correzione: periodo di sola osservazione. Dove una causa sembra un difetto
piuttosto che un limite noto lo dico e mi fermo; la decisione se aprire un'issue e' dell'operatore.

**[F-012] Ricorrenza, e per la prima volta con dollari sopra.** *Fan-out multi-ticker: gli articoli
riguardano societa' terze.* 21 articoli su 84 (25%) sono taggati a 2+ ticker e generano **76 delle
139 righe scorate (55%)**, in linea con la serie 51% / 66% / 53% / — dei giorni precedenti.
La forma che conta oggi e' quella gia' vista il 08-06 su BA e CRM, ma stavolta sui **tre mover
maggiori al rialzo**: per RDDT (+7,18%) e NOW (+6,42%) l'unica riga della giornata e' un listicle
whale-alert che non nomina il titolo, e la motivazione persistita dal modello lo dichiara
esplicitamente; per SPCX (+15,83%) cinque articoli su sei riguardano altro (O'Leary, chip, whale
alert, oro e argento) e il sesto tratta SpaceX dal punto di vista di Alphabet. Il modello risponde
correttamente 0,000 e 0,048-0,120: **il difetto non e' nello scoring, e' che l'input non e' sulla
societa'**. Costo stimato con size S4 tipica 2.200 $ sul return pieno:
348,26 + 157,96 + 141,24 = **647,46 $**. Sul solo residuo post-segnale varrebbe
123,62 + 20,83 + 9,50 = 153,95 $. Il 08-06 la stessa forma era costata 0,00 verificato perche'
colpiva due mover al ribasso su un libro long-only: oggi colpisce il lato lungo, ed e' la prima
volta che questa forma ha un prezzo.

**[F-001] Ricorrenza.** *Copertura news bassa.* **52/96 simboli (54%)** con zero righe in
`news_log` il 08-07, dentro la banda 42-57% delle cinque sedute precedenti. Tre dei sette miss sono
NO_NEWS puri: QCOM +4,66%, SAP +3,36%, CRM +3,20%, tutti e tre con zero righe in `news_log`, zero in
`sentiment_signals` e zero in `execution_decisions` — nessuna catena decisionale esiste. Costo con
size S4 tipica 2.200 $ sul return pieno: 102,52 + 73,92 + 70,40 = **246,84 $** (sulla sola porzione
intraday: 116,16 $). Aggravante gia' nota che vale anche oggi: la copertura apparente e' gonfiata dal
fan-out bancario di F-020.

**[F-030] NUOVO.** *La notizia arriva quando il movimento e' gia' avvenuto: al primo punteggio
utile e' passato in mediana l'82% del movimento intraday della giornata.* Misura sui quattro mover
con copertura: SPCX 70,9% del movimento gia' fatto al segnale delle 14:15, RDDT 81,4% (18:15),
NOW 83,2% (18:30), PLTR 95,7% (17:15). Mediana 82,3%. **Nuovo id giustificato, e la giustificazione
e' proprio la giornata di oggi:** F-019 dice che la latenza della *nostra* ingestione consuma la
finestra di freschezza, ed e' una grandezza che possiamo ridurre; oggi quella latenza e' scesa a
39,6 minuti mediani — il valore migliore della finestra, due volte e mezzo meglio dei giorni
precedenti — e **l'82% e' rimasto**. Le due grandezze si muovono in modo indipendente, quindi non
sono lo stesso fenomeno: questa riguarda l'istante in cui la fonte *scrive*, non l'istante in cui noi
*leggiamo*. Il caso piu' netto e' PLTR, dove l'unico articolo specifico si intitola
`Palantir Stock Up 38% This Week`: e' un resoconto del rialzo. Costo `null`: non e' stimabile
separatamente e i dollari della giornata sono gia' contati su F-012 e F-001, contarli qui li
conterebbe due volte. Tocca direttamente la domanda di uscita n.1 della carta — se la news
editoriale su questa watchlist e' strutturalmente ex-post, l'alpha che cerchiamo non c'e' a
prescindere dalla taratura.

**[F-024] Ricorrenza, con controfattuale esteso.** *Uscita per scadenza del segnale in tempo di
parete.* SPCX e' stata chiusa il 08-06 alle 18:52 a 109,93 (trade 667, 10,375 azioni,
`[expired] S4 signal expired (age=4.4h > max_age=4h) ... no counter-signal found`) e **il giorno dopo
e' il mover numero uno della watchlist a +15,83%**, con il movimento quasi interamente intraday.
L'occorrenza del 08-06 ha gia' contabilizzato 51,77 $ fino alla chiusura di quel giorno (114,92):
registro qui **solo l'incremento** da 114,92 a 133,11, cioe' 10,375022 x 18,19 = **188,72 $**, per
non contare due volte gli stessi dollari. **Caveat che indebolisce l'attribuzione, e va pesato:** il
controfattuale e' lungo un giorno, non intragiornaliero come richiede la carta, e S4 non avrebbe
comunque ri-comprato SPCX il 08-07 (massimo punteggio 0,120 contro gate 0,300). Il danno attribuibile
e' quindi alla regola di *uscita*, non a quella di ingresso: la posizione era gia' li' e la regola
l'ha espulsa per assenza di informazione nuova alla vigilia del movimento.

**[F-010] Ricorrenza, costo verificato nullo.** *Il ramo single-model e' escluso dal ranking.*
54 dei 139 segnali della giornata (39%) sono `single:*` con `fallback_used=true`. Verifica diretta
sulla catena: SPCX ha segnali alle 15:00 (+0,020), 15:15 (+0,040) e 15:45 (+0,120), tutti
`single:gpt-oss:20b-cloud`, e in `execution_decisions` **non esiste alcuna riga SPCX fra le 14:37 e
le 18:22** — quei tre segnali non hanno nemmeno raggiunto il gate. Stesso schema su PLTR: segnale
+0,120 alle 18:30, ultima riga di decisione alle 18:22. **COSTO 0,00 verificato, non stimato per
difetto:** tutti e quattro i punteggi sono sotto il gate 0,300, quindi anche entrando nel ranking non
avrebbero prodotto ordine. Registro la ricorrenza del meccanismo, non un danno.

**[F-020] Ricorrenza, quarto giorno consecutivo.** *org_lookup attribuisce ai ticker bancari articoli
su societa' estranee.* MS e' di nuovo il ticker piu' coperto della watchlist con **19 righe su 139**;
con GS (4) e DB (5) fanno **28 righe, il 20% della giornata**, e **nessuna riguarda le tre banche**.
Campione dei titoli attribuiti: `Appian (NASDAQ:APPN) Releases Q3 2026 Earnings Guidance`,
`Cytokinetics (NASDAQ:CYTK) Price Target Raised to $110.00`,
`Duolingo (NASDAQ:DUOL) Issues Earnings Results`,
`Halozyme Therapeutics (NASDAQ:HALO) Upgraded to "Outperform" at Leerink Partners`,
`Celanese (CE) - Analysts' Recent Ratings Changes`. La banca compare come casa di analisi nel
boilerplate. Costo `null`: nessuna di queste righe ha superato il gate, nessun ordine ne e' nato.
Effetto composto su F-001: dei 44 ticker con almeno una riga, tre assorbono il 20% della copertura
con materiale che non li riguarda, quindi la copertura reale e' peggiore di quella apparente.

**[F-011] Ricorrenza, al massimo storico.** *`execution_decisions.signal_id` NULL.* Oggi
**588 righe su 588 hanno `signal_id` NULL** — il 100%, contro 703/705 il 08-06 e 487/488 il 08-05.
Comprese l'unica BUY (SBUX) e l'unica SELL (BRK.B) della giornata. Sono entrambe S1 e quindi prive
di segnale per costruzione, il che spiega queste due righe ma non le 584 `SKIP_THRESHOLD`, ciascuna
delle quali nasce da un segnale identificabile e non lo cita. Costo `null`: e' auditabilita'. Nota
di lettura per chi rilegge questa finestra: la ricostruzione della catena in questo report e' stata
fatta a mano incrociando timestamp, simbolo e punteggio.

**[F-002] Ricorrenza.** *Attribuzione strategia mancante.* **11 delle 48 posizioni aperte** a fine
08-07 hanno `trades.stop_strategy` NULL (BAC, GOOGL, GS, MS, PBR, RIO, ROKU, SPY, UBS, UNH, XLE,
tutte aperte il 07-10) — una in meno del 08-04, per la chiusura di BP. Fra queste c'e' **PBR,
-3,02%, uno dei due mover al ribasso del giorno e -22,17 $ di MTM**. Costo `null`: non e' una
perdita, e' una perdita non attribuibile. Finche' queste posizioni restano aperte, una fetta del
libro resta fuori dallo split S1/S4 richiesto dalla domanda di uscita 2 della carta.

### Cosa NON e' una segnalazione, oggi

- **Il gate a 0,300.** Ha funzionato come da design e non ha scartato nulla che avesse il segno
  giusto e la magnitudine giusta: nessuna occorrenza di F-009 oggi. Lo stopgap Redis registrato in
  carta il 08-07 e' visibilmente in vigore su tutte e 584 le righe `SKIP_THRESHOLD`.
- **La cadenza dei cicli.** 24 cicli, nessun gap oltre 16 minuti.
- **La latenza di ingestione.** Migliorata di due volte e mezzo. Registrarla come ricorrenza di
  F-019 sarebbe falso.

### Una nota di lettura sugli aggregati del dossier, senza segnalazione

L'aggregato `per_ora_ingresso` continua ad accumulare un dato scomodo sull'ora 14 UTC, il primo
ciclo della seduta: **n=127, 33 vincenti, somma -1.449,95 $, media -11,42 $, t = -4,93**. Nessuna
altra ora ha una t oltre 0,9 in valore assoluto. L'unico ingresso di oggi (SBUX) e' alle 14:07. Non
apro un finding: il dato e' un aggregato che il dossier ricalcola ogni giorno, quindi genererebbe
una ricorrenza automatica ogni seduta senza aggiungere evidenza. Lo segnalo perche' alla sintesi del
giorno 40 va guardato, e perche' non e' coperto da nessuno dei findings esistenti.
