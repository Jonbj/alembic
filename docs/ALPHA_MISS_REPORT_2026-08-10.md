# Alpha Miss Report — 2026-08-10

Ambito: **solo** i 96 simboli di `config/trading.yaml → symbols.watchlist`. Non è uno scan di mercato.
Fonte numerica: `docs/evidence/dossier/2026-08-10.json` (Alpaca SIP, `adjustment=all`, generato
2026-08-11T08:00Z). Dove il dossier ha già il numero, non l'ho ricalcolato.
Sesta seduta del periodo di osservazione (inizio 2026-08-03).

---

## 1. Executive summary

Giornata a indici fermi (SPY −0,03%, QQQ −0,30%) e dispersione 1,95%: **13 mover ≥3%**, 8 su e 5 giù.
Il tema è netto — **rotazione fuori dai semiconduttori dentro energia e pharma** — e il libro era
dalla parte giusta: **9 dei 13 mover erano già in portafoglio** (PANW, XLE, CVX, XOM, LLY sono i
cinque migliori contributori MTM del giorno, +185,85 $ su +162,72 $ totali), e i quattro mancati sono
SPCX +4,23%, BABA +3,04%, BP +3,00%, QCOM −3,39%.

Causa prevalente dei miss: **assenza o non-informatività della notizia**, in parti uguali —
2 NO_NEWS (BABA, BP: zero righe in `news_log`) e 2 THIN_NEUTRAL (SPCX, QCOM). Nessun WRONG_SIGN,
nessun FILTERED. **Novità rispetto ai cinque giorni precedenti: oggi il gate 0,30 non è il collo di
bottiglia** (F-009 non ha occorrenze) — sui mover mancati la pipeline non ha prodotto alcun segnale
direzionale, forte o debole che fosse. Il collo è a monte, nel dato.

Copertura news 43/96 simboli a zero (45%), dentro la banda 42-57% delle sedute precedenti.
S4 ha aperto 4 posizioni (SONY, NVDA, META, MSFT) e ne ha chiuse 3 entro 1h45; nessuna era un mover.
Realizzato del giorno −2,77 $, MTM +162,72 $, NAV 110.344,06 $.

---

## 2. Rendimenti completi della watchlist (96 simboli)

`**grassetto**` = |return| ≥ 3% (soglia mover del dossier). "Catturato" = posizione aperta a fine
giornata, oppure tradata nella giornata.

| simbolo | return | catturato |
|---|---:|---|
| **PANW** | +5.82% | sì |
| **XLE** | +4.66% | sì |
| **CVX** | +4.48% | sì |
| **XOM** | +4.41% | sì |
| **SPCX** | +4.23% | no |
| **LLY** | +3.90% | sì |
| **BABA** | +3.04% | no |
| **BP** | +3.00% | no |
| ADBE | +2.92% | no |
| NFLX | +2.90% | no |
| ORCL | +2.74% | no |
| CRM | +2.47% | no |
| PBR | +2.06% | sì |
| NOW | +2.05% | no |
| PLTR | +1.87% | no |
| MRK | +1.82% | sì |
| XLV | +1.67% | sì |
| SHEL | +1.64% | sì |
| SONY | +1.53% | sì (entrata oggi) |
| JD | +1.52% | no |
| BRK.B | +1.46% | no |
| HOOD | +1.32% | no |
| AMZN | +1.32% | no |
| SNOW | +1.27% | sì |
| VALE | +1.22% | sì |
| MSFT | +1.21% | sì (intraday, uscita) |
| SAP | +1.16% | no |
| T | +1.09% | no |
| BAC | +1.09% | sì |
| PFE | +1.08% | no |
| NVO | +0.99% | no |
| JNJ | +0.99% | sì |
| NKE | +0.98% | no |
| CSCO | +0.94% | sì |
| WDC | +0.93% | sì |
| GOOGL | +0.91% | sì |
| DELL | +0.91% | sì |
| RIO | +0.80% | sì |
| ABBV | +0.78% | sì |
| WMT | +0.72% | no |
| TSLA | +0.70% | no |
| JPM | +0.63% | sì |
| TMUS | +0.57% | no |
| DB | +0.55% | no |
| COST | +0.52% | no |
| META | +0.48% | sì (intraday, uscita) |
| PG | +0.45% | no |
| GM | +0.43% | sì |
| UNH | +0.41% | sì |
| UBS | +0.37% | sì |
| XLF | +0.36% | sì |
| WFC | +0.31% | no |
| IBM | +0.31% | no |
| AZN | +0.30% | no |
| INFY | +0.24% | no |
| C | +0.16% | sì |
| F | +0.14% | no |
| MA | +0.04% | no |
| SPY | −0.03% | sì |
| VZ | −0.06% | no |
| BIDU | −0.19% | no |
| MCD | −0.28% | no |
| QQQ | −0.30% | sì |
| V | −0.33% | no |
| TSM | −0.37% | sì |
| ASML | −0.43% | sì |
| MS | −0.46% | sì |
| MMM | −0.47% | sì |
| GS | −0.49% | sì |
| IWM | −0.52% | sì |
| CAT | −0.55% | sì |
| AXP | −0.60% | no |
| CMCSA | −0.63% | no |
| TM | −0.69% | no |
| BA | −0.70% | no |
| ROKU | −0.83% | sì |
| XLK | −0.88% | sì |
| SBUX | −0.88% | sì |
| GE | −0.91% | sì |
| AVGO | −1.25% | no |
| HD | −1.36% | no |
| AAPL | −1.53% | sì |
| DIS | −1.65% | no |
| ERIC | −1.67% | no |
| RDDT | −1.84% | no |
| MU | −1.89% | sì |
| TXN | −1.97% | sì |
| NOK | −2.46% | sì |
| SOXX | −2.55% | sì |
| AMD | −2.86% | sì |
| NVDA | −2.86% | sì (intraday, uscita) |
| **AMAT** | −3.16% | sì |
| **QCOM** | −3.39% | no |
| **INTC** | −4.06% | sì (uscita oggi) |
| **MRVL** | −4.65% | sì |
| **ARM** | −5.21% | sì |

Nessun simbolo senza barre disponibili (`simboli_senza_dati: []` nel dossier).

**Soglia mover.** Uso il 3% del dossier, che oggi vale ~1,5 volte la dispersione cross-sectional
della giornata (σ = 1,95%): sopra quella soglia il movimento non è rumore di sezione.

---

## 3. I quattro miss, classificati

| simbolo | return | gap / intraday | categoria | evidenza |
|---|---:|---|---|---|
| SPCX | +4.23% | +1.38% / +2.81% | **THIN_NEUTRAL** | 4 articoli in `news_log`, 4 segnali: 14:02 +0,188 e 14:45 −0,180 entrambi `single:gpt-oss:20b-cloud` (fallback, esclusi dal ranking BUY dalla regola #108), 17:01 +0,000 e 19:15 +0,041 ensemble. Il massimo ensemble del giorno è +0,041 contro un gate di 0,300. Solo 3 righe `SKIP_THRESHOLD` (17:07-17:37), tutte a 0,000. Gli articoli spiegano il punteggio: riusabilità del booster Falcon 9, un pezzo di opinione ribassista sulla valutazione, gli "earnings highlights" di ARK, e un articolo su **Rocket Lab** attribuito a SPCX in fan-out. |
| BABA | +3.04% | +0.16% / +2.88% | **NO_NEWS** | Zero righe in `news_log`, zero in `sentiment_signals`, zero in `execution_decisions`. Nessuna catena decisionale esiste. |
| BP | +3.00% | +0.74% / +2.24% | **NO_NEWS** | Come sopra: zero righe in tutte e tre le tabelle. |
| QCOM | −3.39% | +0.18% / −3.56% | **THIN_NEUTRAL** | Un solo articolo, alle 19:30: *"7 Information Technology Stocks With Whale Alerts In Today's Session"* — un listicle attribuito in fan-out anche ad AMAT. Segnale unico 19:30, score 0,000, conf 0,100. Mover al ribasso: le strategie sono long-only, quindi **non catturabile per costruzione** e senza costo. |

Conteggi: **NO_NEWS 2, THIN_NEUTRAL 2, WRONG_SIGN 0, FILTERED 0, OUT_OF_STRATEGY_SCOPE 0.**

**Il movimento di oggi era catturabile.** Come il 08-07 e a differenza del 08-04, il grosso è
intraday, non nel gap di apertura (BABA 0,16% di gap su 3,04%; BP 0,74% su 3,00%; SPCX 1,38% su
4,23%). I miss di oggi non sono alpha inaccessibile per costruzione.

**Osservazione che non entra nel conteggio ma pesa.** Il peggior mover della giornata, **ARM −5,21%,
ha anch'esso zero righe di news** — ma è in portafoglio (S1 dal 08-03) e quindi non è un "miss".
L'assenza di copertura non gli ha impedito solo l'ingresso: gli ha impedito anche di uscire. ARM è
il peggior contributore MTM del giorno, −20,74 $. Stessa storia per XOM (+4,41%, zero news), che è
in portafoglio per momentum e ha guadagnato +37,11 $ senza che la pipeline news ne sapesse nulla:
oggi i due estremi del libro sono entrambi ciechi al sentiment.

---

## 4. Titoli catturati: esito

### 4.1 I nove mover già a libro

Otto erano aperti a inizio giornata e lo sono rimasti; INTC è uscito oggi.

| simbolo | return | strategia | MTM del giorno |
|---|---:|---|---:|
| PANW | +5.82% | S1 (dal 07-13) | +48.18 |
| XLE | +4.66% | *nessuna* (legacy 07-10) | +33.16 |
| CVX | +4.48% | S1 (dal 07-15) | +35.51 |
| XOM | +4.41% | S1 (dal 07-13) | +37.11 |
| LLY | +3.90% | S1 (dal 07-15) | +31.89 |
| AMAT | −3.16% | S1 (dal 07-14) | −14.59 |
| MRVL | −4.65% | S1 (dal 07-14) | −15.76 |
| ARM | −5.21% | S1 (dal 08-03) | −20.74 |
| INTC | −4.06% | S1 → **chiuso 16:22** | realizzato **+1,89** |

INTC: uscita `sentiment_reversal` alle 16:22 su score −0,553 (soglia −0,35), dopo 598 ore di tenuta,
realizzato +1,89 $. Il segnale era corretto e materiale — quattro articoli concordi sul collocamento
azionario da 15 miliardi, ensemble non-fallback con confidenza 0,70-0,85. Il dossier misura un
`drift_post_uscita` di −0,67 $: l'uscita ha marginalmente aggiunto valore. **È il caso meglio
riuscito della giornata**, e vale la pena notare che è arrivato dalla via *inversa* rispetto al
mandato di S4 — sentiment usato per uscire, non per entrare.

Tre dei cinque mover al rialzo detenuti sono energia, e il libro è lungo il tema per costruzione S1.
Il guadagno del giorno viene da lì, non dalla pipeline news.

### 4.2 Le quattro posizioni aperte da S4 (nessuna su un mover)

| simbolo | ora | prezzo | percentile d'ingresso | uscita | esito |
|---|---|---:|---:|---|---:|
| SONY | 16:07 | 23.77 | 0.643 | **ancora aperta** | MTM +2,51 |
| NVDA | 17:22 | 218.89 | 0.288 | 19:07 `below_entry_gate` | +1,29 |
| META | 17:37 | 594.69 | 0.164 | 19:22 `below_entry_gate` | −3,57 |
| MSFT | 17:52 | 505.87 | 0.314 | 19:37 `below_entry_gate` | −2,37 |

Due letture, una buona e una cattiva.

**Buona: la qualità dell'ingresso.** Il percentile mediano d'ingresso di oggi è ~0,30 contro una
mediana mobile a 20 giorni di **0,510** — le tre entrate del pomeriggio sono avvenute nella parte
bassa del range di giornata, cioè a prezzi buoni. E nessuna entrata è caduta nella fascia oraria
delle 14:xx, che l'aggregato del dossier segnala come sistematicamente perdente (n=127,
somma −1.449,95 $, t = −4,93).

**Cattiva: il motivo delle tre uscite.** Tutte e tre sono scattate perché il punteggio è caduto a
+0,000, e tutte e tre per **lo stesso articolo**: alle 19:00 il pezzo *"S&P 500 Earnings Growth May
Be Less Impressive Than It Looks; SpaceX Short Squeeze; Inflation…"* — un morning-brief generico —
ha prodotto tre segnali distinti (`sentiment_signals` 7149 META, 7150 MSFT, 7151 NVDA) con
confidenza 0,175 / 0,050 / 0,150 e score 0,000, sovrascrivendo i tre segnali ticker-specifici che
avevano generato gli acquisti (+0,515 META, +0,470 MSFT, +0,441 NVDA, tutti ensemble non-fallback con
confidenza 0,70-0,78 su articoli materiali: Maia 300, il target BofA su Rubin, la nota Benzinga su
Meta). **Un articolo di rassegna ha chiuso tre posizioni in trenta minuti.**

Il controfattuale corto è però **favorevole**: tenendo fino alla chiusura NVDA avrebbe perso altri
8,85 $, META guadagnato 3,80 $, MSFT 2,59 $ — netto **−2,46 $**, cioè le uscite anticipate hanno
fatto risparmiare denaro. Il meccanismo è difettoso, l'esito di oggi no.

### 4.3 Sei ingressi S4 bloccati in silenzio (non contati come miss)

Sei simboli hanno prodotto oggi un segnale ensemble **sopra il gate 0,300** e sono **scomparsi da
`execution_decisions` esattamente al ciclo in cui quel segnale è diventato l'ultimo disponibile**:

| simbolo | segnale | ora | ultima riga `execution_decisions` |
|---|---:|---|---|
| TSM | +0.691 | 17:01 | 17:37 (score 0,171) |
| CAT | +0.520 | 17:30 | 17:22, poi riprende alle 19:22 con un segnale nuovo a 0,018 |
| XLE | +0.516 | 18:30 | 18:07 |
| SHEL | +0.482 | 17:46 | — |
| GE | +0.345 | 17:01 | — |
| PANW | +0.327 | 19:00 | 18:52 (score 0,000) |

Tutti e sei sono **già a libro come posizioni S1/legacy**: il guard anti-pyramiding P0-05 li elimina
dopo il gate e prima della persistenza, quindi non lasciano riga. Due di loro sono i mover #1 e #2
del giorno (PANW +5,82%, XLE +4,66%) e il primo è il punteggio più alto della giornata (TSM +0,691).
Il no-pyramiding è una regola di design, non un bug — il difetto è che **il blocco è invisibile**:
da solo DB non si distingue "bloccato di proposito" da "mai valutato". Li tengo fuori dal conteggio
dei miss (sono simboli catturati) e li registro su F-031.

---

## 5. Pattern osservato

**Rotazione dai semiconduttori verso energia e pharma, a indici fermi.**

- **Fuori:** ARM −5,21%, MRVL −4,65%, INTC −4,06%, QCOM −3,39%, AMAT −3,16%, AMD −2,86%,
  NVDA −2,86%, SOXX −2,55%, TXN −1,97%, MU −1,89%, ASML −0,43%, TSM −0,37% — il blocco è compatto e
  senza eccezioni. INTC ha una causa propria (collocamento da 15 miliardi) ma cade nella stessa
  direzione.
- **Dentro:** XLE +4,66%, CVX +4,48%, XOM +4,41%, BP +3,00%, SHEL +1,64%, PBR +2,06% — energia in
  blocco, con la spiegazione nelle stesse headline che la pipeline ha ingerito (*"Oil Jumps 3%,
  Yields Climb as Hormuz Hopes Fade"*). Pharma/healthcare seconda gamba: LLY +3,90%, MRK +1,82%,
  XLV +1,67%, PFE +1,08%, JNJ +0,99%.
- **Fermo:** software e mega-cap (ADBE +2,92%, NFLX +2,90%, ORCL +2,74%, CRM +2,47%, NOW +2,05%),
  finanziari entro ±1%. PANW +5,82% è idiosincratico (*"Why Palo Alto Networks Stock Dropped, Then
  Popped"*), non un tema cyber.

Il movimento è **quasi tutto intraday**: SPY −0,03% con dispersione 1,95% significa che la sezione si
è mossa senza che l'indice si muovesse — la giornata migliore possibile per una strategia
cross-sectional, e infatti il libro fa +162,72 $ di MTM con SPY piatto.

---

## 6. Confronto con i giorni precedenti

**L'energia ha invertito direzione per la terza seduta consecutiva:** su il 08-06, giù il 08-07
(PBR −3,02%, BP −1,42%, CVX −1,41%, XLE −1,13%), su oggi. Sesta seduta osservata, sesta rotazione
diversa. La lettura registrata il 08-05 e ripetuta il 08-07 regge: nella finestra osservata il tema
settoriale non persiste da un giorno all'altro, e un libro costruito su momentum a 3 mesi (S1) ci
guadagna o ci perde a seconda del giorno, non della qualità del segnale.

**Ricorrenza per ticker sui buchi di copertura.** BP era già NO_NEWS il 08-04 (allora −4,00%);
BABA era THIN_NEUTRAL sotto gate il 08-03 (+4,13%) e oggi è a copertura zero; QCOM è la **quarta**
volta in cinque sedute che finisce fra i mover senza copertura utile (08-04 +7,32%, 08-05 −3,16%,
08-07 +4,66%, oggi −3,39%). Non è copertura casuale: è lo stesso insieme di ticker.

**Cambio di regime rispetto al gate.** Nei quattro giorni 08-03 → 08-06 la causa dominante
documentata era F-009 — segnale del segno giusto scartato per magnitudine. Oggi, con il gate riportato
a 0,300 (deroga #191, stopgap Redis verificato: `feedback:entry_threshold:S4` = 0.3), **F-009 non ha
occorrenze**: sui quattro mover mancati il punteggio massimo prodotto dalla pipeline è +0,041. Due
sedute consecutive (08-07 e oggi) in cui il collo di bottiglia è tornato a essere il **dato**, non la
soglia. È esattamente la distinzione che la domanda di uscita 1 della carta deve poter fare, e la
discontinuità del 08-07 registrata nella carta va tenuta presente quando si sommeranno i giorni.

---

## 7. Segnalazioni

Nessuna proposta di fix: periodo di sola osservazione (`docs/evidence/OBSERVATION_CHARTER.md`).
Dove una causa sembra un difetto e non un limite noto, lo dico e mi fermo lì.

**[F-001] Copertura news bassa — 43/96 simboli a zero (45%), BABA e BP NO_NEWS puri.** Costo stimato
133,05 $ (size S4 tipica 2.200 $ sul return pieno: BABA 66,99 + BP 66,06; sulla sola porzione intraday
112,64 $). Aggravante di oggi: i due estremi MTM del libro, ARM −20,74 $ e XOM +37,11 $, hanno
entrambi copertura zero — l'assenza di notizia non impedisce solo di entrare, impedisce anche di
uscire.

**[F-031] Sei ingressi S4 sopra gate bloccati dal guard anti-pyramiding senza lasciare traccia in
`execution_decisions`** (§4.3). È il difetto più nitidamente verificato della giornata: la scomparsa
delle righe coincide al ciclo con il momento in cui il segnale sopra gate diventa l'ultimo. Costo
stimato 9,71 $ netti sul controfattuale corto (ingresso al ciclo successivo al segnale, uscita in
chiusura, size 2.200 $: TSM −15,35, CAT +3,96, XLE +4,95, SHEL −5,43, GE +1,92, PANW +19,66). Il
blocco è corretto per design; **l'invisibilità no**.

**[F-008] Un morning-brief generico ha chiuso tre posizioni S4 in trenta minuti** (§4.2). Costo
**0,0 $ verificato**, non stimato per difetto: il controfattuale è stato calcolato ed è sfavorevole
al mantenimento (−2,46 $ netti tenendo fino alla chiusura). Stesso meccanismo di F-023 (vince
l'ultimo segnale per simbolo a prescindere da confidenza e specificità), registrato qui perché
l'effetto osservato è sull'uscita.

**[F-012] Metà delle righe scorate viene da articoli fan-out multi-ticker: 101 su 196 (51,5%).**
`extraction_method` = `org_lookup` su 111/196. Casi del giorno: il listicle whale-alert che è
l'**unica** copertura di QCOM, l'articolo su Rocket Lab attribuito a SPCX, il morning-brief che ha
prodotto le tre uscite. Costo null per non doppio-contare con F-008.

**[F-020] Fan-out bancario: MS 33 righe, GS 15, DB 11 — 59 su 196 (30%) — e nessuna riguarda le tre
banche.** Verificato titolo per titolo: a GS finiscono sei versioni della stessa notizia sul
collocamento Intel, a DB il live del FTSE 100, un upgrade su Persimmon, due pezzi su SpaceX, uno su
Western Alliance. La copertura apparente della watchlist è gonfiata da queste righe. Costo null.

**[F-030] La notizia arriva quando il movimento è già avvenuto: mediana 69,9%.** Misurato sui nove
mover con copertura, al primo segnale utile della giornata era già avvenuto il 76,0% del movimento
intraday su AMAT, 81,9% su PANW, 81,5% su QCOM, 72,3% su CVX, 69,9% su LLY, 58,2% su MRVL, 47,2% su
XLE. Solo INTC (−8,5%) e SPCX (−98,6%, il prezzo si muoveva contro al momento del segnale) fanno
eccezione. Costo null: è una proprietà della fonte, non un evento.

**[F-011] Il BUY di SONY riporta un punteggio che non corrisponde a nessun segnale in tabella.**
`execution_decisions` 8544 (16:07) ha `signal_id` NULL e `signal_score` **+0,541**, mentre il segnale
SONY più vicino è `sentiment_signals` 7046 delle 16:00:45 a **+0,451** — di cui la decisione cita
*verbatim* il reasoning di glm-5.2 ("The $6.3B joint venture with TSMC…"). Le altre tre BUY del
giorno hanno `signal_id` valorizzato e il punteggio coincide al millesimo (NVDA 7098 = 0,441,
META 7109 = 0,515, MSFT 7116 = 0,470). Complessivamente 3 righe su 463 hanno la FK. **Sembra un
difetto, non un limite noto**: quando `signal_id` non viene catturato, il numero scritto nel `reason`
non è riconciliabile con alcuna riga di `sentiment_signals`. Costo null (auditabilità).

**[F-032 — NUOVO] `BRK.B` è cieco al sentiment da sempre: i provider scrivono `BRKB`, la watchlist
dice `BRK.B`, e le due forme non si sono mai incontrate.** Oggi 11 righe di `news_log` e 11 segnali
su `BRKB`, di cui tre ticker-specifici e sopra o vicino al gate (+0,480 *"Berkshire accelerates
buybacks as profit tops forecasts"*, +0,373, +0,336), e **zero** righe in `execution_decisions`.
Storicamente: 96 segnali `BRKB` dal 2026-06-16 a oggi, zero decisioni; le 4 decisioni su `BRK.B`
esistenti vengono dal path momentum S1. Costo **0,0 verificato**: il controfattuale sul segnale più
forte (ingresso al ciclo 16:22 a 532,60, chiusura 529,39) vale −13,24 $, cioè sarebbe stato in
perdita. Id nuovo giustificato: nessun finding esistente riguarda la canonicalizzazione dei ticker
fra provider e watchlist — F-020 è attribuzione *sbagliata* di articoli a ticker esistenti, questo è
un ticker *inesistente per il resto del sistema*. **Nota**: la correzione è già stata scritta e
mergiata (`canonicalizza_ticker`, #226, commit a2ad132 delle 00:06 CEST del 2026-08-11) e i container
sono ripartiti alle 22:13 UTC del 08-10 — cioè dopo la chiusura della seduta qui analizzata. Il
finding nasce quindi già chiuso e serve solo da evidenza datata.

**[F-002] Undici posizioni su 48 restano senza `stop_strategy`** (BAC, GOOGL, GS, MS, PBR, RIO, ROKU,
SPY, UBS, UNH, XLE, tutte entrate il 07-10). Portano **+60,79 $ dei +162,72 $ di MTM del giorno, il
37%**, e fra loro c'è XLE, secondo mover della giornata (+4,66%). Costo null: non è una perdita, è
P&L non attribuibile — e oggi la fetta non attribuibile è la più grande registrata finora nella
finestra.

**[F-021] Il beat comincia 37 minuti dopo l'apertura.** Primo ciclo portfolio 14:07 UTC contro
apertura 13:30 UTC (EDT), ultimo 19:52 contro chiusura 20:00. 24 cicli, cadenza regolare, nessun gap
> 16 minuti. Oggi non è una nota di colore: al primo ciclo AMAT aveva già percorso il 76% del suo
movimento e MRVL il 58%. Costo null.

**[F-027] I log dei container del 2026-08-10 non esistono più.** `docker logs alembic-worker-1`
comincia alle 22:13:38 del 08-10, dopo la chiusura: il redeploy di ieri sera ha azzerato la
retention. Conseguenza diretta su questo report: la categoria **FILTERED non è verificabile** per la
giornata di oggi se non per inferenza sul DB (§4.3), che è esattamente quello che ho dovuto fare.
Costo null.

**[F-010] 52 segnali su 196 (26,5%) sono single-model con `fallback_used=true` e restano fuori dal
ranking BUY (regola #108).** Il più alto è MRVL +0,423 delle 14:15, sopra il gate 0,300; seguono
SPCX +0,188 e AMAT +0,138. Costo **0,0 verificato**: MRVL ha chiuso −4,65% (l'esclusione ha evitato
circa −100 $ su size tipica) ed era comunque già a libro, mentre SPCX e AMAT stanno sotto il gate e
non avrebbero prodotto ordine in nessun caso.

---

## 8. Numeri del libro

| grandezza | valore |
|---|---:|
| NAV a fine giornata (snapshot 23:42) | 110.344,06 $ |
| variazione NAV | +162,43 $ |
| realizzato (4 chiusure) | −2,77 $ |
| di cui S1 | +1,89 $ |
| di cui S4 | −4,65 $ |
| MTM sul libro aperto (48 posizioni) | +162,72 $ |
| cicli portfolio | 24 (14:07 → 19:52, nessun gap > 16 min) |
| ordini effettivi | 8 (4 BUY, 4 SELL) |
| righe `execution_decisions` | 463 (454 SKIP_THRESHOLD, 4 BUY, 4 SELL, 1 SKIP_STALE) |
| righe `news_log` | 196 su 54 ticker, 131 content_hash distinti |
| segnali `sentiment_signals` | 196 (144 ensemble, 52 fallback single-model) |
