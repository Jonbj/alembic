# Alpha Miss Report — 2026-08-12

Fonte numerica: `docs/evidence/dossier/2026-08-12.json` (Alpaca SIP, `adjustment=all`), letto e non ricalcolato.
Perimetro: i 96 simboli di `config/trading.yaml → symbols.watchlist`. Nessun simbolo senza barre.
Periodo di sola osservazione (`docs/evidence/OBSERVATION_CHARTER.md`): nessuna proposta di taratura.

---

## 1. Executive summary

Giornata di dispersione normale (σ 2,37%) su indici in leggero rialzo (SPY +0,25%, QQQ +0,73%): 11 mover
oltre |3%|, 9 al rialzo e 2 al ribasso, tema unico e leggibile — memoria/storage e semiconduttori dopo un
CPI benigno e gli utili AI (CoreWeave, Nebius, Super Micro, Lumentum). Alembic ne ha in mano 8 su 11.
I 3 mancati sono ORCL +5,36%, META −3,38% e HD −3,12%, tutti e tre **THIN_NEUTRAL**: nessun miss per
assenza di copertura. **È la prima seduta della finestra con zero miss NO_NEWS**, pur restando 51 simboli
su 96 senza una riga di news.

Il tratto dominante non è però il conteggio dei miss: **su 7 dei 9 mover al rialzo il movimento è tutto
nel gap di apertura e l'intraday è piatto o negativo** (NOK gap +10,12% / intraday −0,72%; MU +5,11% /
−0,18%; ORCL +5,04% / +0,31%; WDC, AMAT, INTC dello stesso tenore). Quota mediana del movimento nel gap
per i mover al rialzo: 99%. Su una giornata così l'alpha non era accessibile a un motore che opera solo
in RTH, e il miss di ORCL vale $6,82 catturabili contro $117,95 di return pieno.

Conseguenza sul libro: i +271,26 $ di MTM vengono quasi tutti dalle posizioni **tenute passivamente**
(S1 +228,53 $), mentre le **tre decisioni attive** della giornata — gli ingressi S4 su NVDA, INTC, SPCX,
entrati rispettivamente al 77°, 71° e 92° percentile del range del giorno contro una mediana mobile a
20 giorni di 0,535 — valgono **−35,42 $** fra MTM e realizzato. Realizzato del giorno −27,40 $, tutto S4.

## 2. Rendimenti completi della watchlist (2026-08-12)

`SI (in book)` = posizione aperta a fine giornata (aperta oggi o ereditata); `SI (tradato+chiuso)` =
comprato e rivenduto in giornata. In grassetto i mover |return| ≥ 3%.

| simbolo | return | catturato |
|---|---:|---|
| **DELL** | +9.87% | SI (in book) |
| **SPCX** | +9.65% | SI (in book) |
| **NOK** | +9.32% | SI (in book) |
| **ORCL** | +5.36% | no |
| **MU** | +4.92% | SI (in book) |
| **AMAT** | +4.29% | SI (in book) |
| **WDC** | +3.69% | SI (in book) |
| **INTC** | +3.32% | SI (in book) |
| **NVDA** | +3.03% | SI (tradato+chiuso) |
| CSCO | +2.86% | SI (in book) |
| WMT | +2.43% | no |
| SOXX | +2.32% | SI (in book) |
| MRVL | +2.25% | SI (in book) |
| MRK | +1.92% | SI (in book) |
| AMD | +1.82% | SI (in book) |
| SBUX | +1.72% | SI (in book) |
| WFC | +1.69% | no |
| TSM | +1.68% | SI (in book) |
| XLK | +1.49% | SI (in book) |
| CAT | +1.45% | SI (in book) |
| C | +1.33% | SI (in book) |
| BAC | +1.27% | SI (in book) |
| MS | +1.19% | SI (in book) |
| ARM | +1.09% | SI (in book) |
| ERIC | +1.09% | no |
| AXP | +0.96% | no |
| JPM | +0.87% | SI (in book) |
| UNH | +0.85% | SI (in book) |
| PANW | +0.84% | SI (in book) |
| DB | +0.73% | no |
| QQQ | +0.73% | SI (in book) |
| VALE | +0.64% | SI (in book) |
| ASML | +0.59% | SI (in book) |
| ROKU | +0.58% | SI (in book) |
| IWM | +0.57% | SI (in book) |
| MCD | +0.57% | no |
| HOOD | +0.56% | no |
| COST | +0.56% | no |
| UBS | +0.45% | SI (in book) |
| LLY | +0.43% | SI (in book) |
| JNJ | +0.41% | SI (in book) |
| MMM | +0.35% | SI (in book) |
| GS | +0.27% | SI (in book) |
| XLV | +0.26% | SI (in book) |
| SPY | +0.25% | SI (in book) |
| QCOM | +0.24% | no |
| RIO | +0.23% | SI (in book) |
| XLF | +0.21% | SI (in book) |
| XLE | +0.16% | SI (in book) |
| AVGO | −0.01% | no |
| CVX | −0.03% | SI (in book) |
| XOM | −0.03% | SI (in book) |
| GOOGL | −0.08% | SI (in book) |
| AZN | −0.16% | no |
| SONY | −0.30% | no |
| DIS | −0.30% | no |
| MA | −0.30% | no |
| SHEL | −0.48% | SI (in book) |
| ABBV | −0.53% | SI (in book) |
| BP | −0.53% | no |
| SNOW | −0.56% | SI (in book) |
| VZ | −0.61% | no |
| CMCSA | −0.70% | no |
| GE | −0.74% | SI (in book) |
| NFLX | −0.78% | no |
| PG | −0.78% | no |
| TMUS | −0.81% | no |
| TM | −0.84% | no |
| AAPL | −0.87% | SI (in book) |
| BA | −0.87% | no |
| V | −0.94% | no |
| PBR | −0.95% | SI (in book) |
| JD | −0.97% | no |
| T | −1.02% | no |
| IBM | −1.02% | no (venduto oggi) |
| BIDU | −1.04% | no |
| F | −1.07% | no |
| PFE | −1.16% | no |
| BRK.B | −1.24% | no |
| TSLA | −1.59% | no |
| TXN | −1.65% | SI (in book) |
| NVO | −1.65% | no |
| RDDT | −1.75% | no |
| AMZN | −1.83% | no |
| ADBE | −1.88% | no |
| NKE | −1.96% | no |
| NOW | −2.04% | no |
| BABA | −2.06% | no |
| CRM | −2.10% | no |
| PLTR | −2.23% | no |
| MSFT | −2.26% | no |
| INFY | −2.54% | no |
| SAP | −2.64% | no |
| GM | −2.90% | SI (in book) |
| **HD** | −3.12% | no |
| **META** | −3.38% | no |

Soglia mover: |return| ≥ 3%, la stessa del dossier (`soglia_mover: 0.03`). Su una dispersione
cross-sectional di 2,37% corrisponde a ~1,27σ: seleziona la coda, non il rumore, e produce 11 nomi su 96
(11%), una numerosità confrontabile con le sedute precedenti della finestra.

## 3. Miss classificati

| simbolo | return | categoria | evidenza |
|---|---:|---|---|
| ORCL | +5,36% | THIN_NEUTRAL | 3 righe in `news_log`, di cui **una sola su Oracle**: «What's Going On With Oracle Stock on Monday?» (Benzinga, 15:54, `source_metadata`) → segnale 17:00 **+0,186** conf 0,600, ensemble non-fallback. Le altre due sono fan-out su società terze: «Nebius Jumps 20%…» (→ +0,041) e «Quantinuum Is a "Core Quantum Name to Own"» (→ +0,040 fallback). Gate attivo 0,300: 6 righe `SKIP_THRESHOLD` fra le 16:37 e le 17:52, punteggio massimo del giorno il 62% della soglia. Segno corretto, magnitudo insufficiente — il collo di bottiglia è il dato, non la soglia. |
| META | −3,38% | THIN_NEUTRAL | **1 sola riga** in `news_log`: «Super Micro, Lumentum, CoreWeave Earnings Highlight AI Infrastructure Demand; CPI Data Shows Stagflation Risks Remain» — rassegna macro multi-ticker in cui Meta è un tag di fan-out, non il soggetto. Segnale unico 18:30 **+0,080** conf 0,400, single-model fallback. Nessuna riga in `execution_decisions`. Mover al **ribasso** e libro long-only: non tradabile nella direzione del movimento. |
| HD | −3,12% | THIN_NEUTRAL | 3 righe, **due specifiche su Home Depot** («How To Earn $500 A Month From Home Depot Stock…» → −0,118; «Home Depot Stock Slips as Leadership Shift Lands Ahead of Earnings», 17:41 → **−0,204** conf 0,500) più la solita rassegna macro (+0,020 fallback). **Il segno è corretto** su un titolo che chiude −3,12%. Il gate S4 è in valore assoluto (`portfolio_scheduler.py:3719-3720`), quindi −0,204 è scartato per magnitudo: 6 righe `SKIP_THRESHOLD`. Anche fosse passato, il libro è long-only e HD non era in portafoglio: nulla da vendere. |

Conteggi del giorno: **NO_NEWS 0 · THIN_NEUTRAL 3 · WRONG_SIGN 0 · FILTERED 0 · OUT_OF_STRATEGY_SCOPE 0**.

Nota metodologica sui costi: dei tre miss solo ORCL ha un costo positivo. META e HD sono mover al ribasso
su un libro long-only e senza posizione da chiudere, quindi il controfattuale è **verificato nullo**, non
«non stimato». Per ORCL: con la size S4 tipica ($2.200) il return pieno vale $117,95, ma il gap di
apertura è il 94% del movimento e la parte realmente catturabile intraday (+0,31% dall'apertura alla
chiusura) vale **$6,82**.

## 4. Titoli catturati — esito

### 4.1 Ingressi della giornata (3, tutti S4)

| simbolo | ora UTC | prezzo | qty | percentile d'ingresso | esito a fine giornata |
|---|---|---:|---:|---:|---:|
| NVDA | 17:22 | 223,97 | 5,500 | 0,768 | **chiuso** alle 19:07, `portfolio_sell`, realizzato **−0,93 $** |
| INTC | 17:52 | 102,29 | 12,035 | 0,714 | aperto, MTM **−16,16 $** |
| SPCX | 18:52 | 148,36 | 8,295 | 0,920 | aperto, MTM **−18,33 $** |

Mediana mobile a 20 giorni del percentile d'ingresso: **0,535**. Tutti e tre gli ingressi sono sopra, e
SPCX al 92° percentile del range della giornata. I tre nomi hanno tutti chiuso in verde (+3,03%, +3,32%,
+9,65%) e le tre posizioni sono tutte in perdita: il titolo è stato scelto bene, il momento no.

Catena decisionale, per completezza:
- **NVDA** — 11 righe di news, **una sola su Nvidia** («What's Going On With Nvidia Stock on Wednesday?», 15:44 → segnale 17:15 **+0,343** conf 0,650, ensemble) che genera il BUY. Le altre 10 sono CoreWeave (5), IREN, Lumentum, Shkreli, Musk/SpaceX, rassegna CPI.
- **INTC** — BUY su segnale 17:45 **+0,419** conf 0,675 da «Intel's $20 Billion Capital Raise Is a Bullish Tell for Its Foundry Business, Analyst Says» (16:40), articolo genuinamente specifico. Prima di quello: 4 segnali fra −0,120 e +0,042, di cui due da pezzi su Nvidia e AMD.
- **SPCX** — BUY su segnale 18:45 **+0,628** conf 0,825 da «SpaceX Stock Surges Past $135 IPO Price: What's Going On?» (17:22). Il titolo dell'articolo dichiara che il movimento è già avvenuto; l'ingresso arriva 1h30 dopo la pubblicazione, a +92,11 $ di distanza dal prezzo di apertura, e chiude sotto.

### 4.2 Uscite (2)

| simbolo | ora | prezzo | realizzato | motivo | drift dopo l'uscita |
|---|---|---:|---:|---|---:|
| IBM | 14:22 | 233,27 | **−26,47 $** | `portfolio_sell` — reason `[unknown] S4 signal was stale but FIX-D re-admitted it this cycle … and the weight is 0 anyway` | **+13,71 $** |
| NVDA | 19:07 | 223,84 | **−0,93 $** | `portfolio_sell` — reason `[below_entry_gate] … score=+0,023` | **+1,38 $** |

Entrambe le uscite sono seguite da un recupero. IBM è la ricorrenza esatta del meccanismo isolato ieri
(F-035). NVDA è venduto su un punteggio **+0,023** generato alle 18:30 da «Lumentum Posts Solid Q4» — un
articolo su Lumentum — che ha sovrascritto il +0,343 su cui la posizione era nata 1h45 prima.

### 4.3 Mover tenuti passivamente (5)

DELL (+40,46 $ di MTM, S1 dal 13/07), WDC (+48,20 $, S4 dal 21/07), NOK (+36,58 $, S1 dal 14/07),
AMAT (+19,32 $, S1 dal 14/07), MU (+17,02 $, S1 dal 28/07). Sono i cinque migliori contributori MTM della
giornata e **nessuno di loro è frutto di una decisione presa oggi**: sono posizioni vecchie di 2-4
settimane. Il libro ha fatto +271,26 $ di MTM (S1 +228,53, legacy senza strategia +29,02, S4 +13,72)
con realizzato −27,40 $, tutto S4.

### 4.4 Ingressi bloccati sui mover già a libro

8 simboli hanno prodotto oggi un segnale S4 sopra il gate e sono stati bloccati da `SKIP_PYRAMIDING`
(P0-05), fra cui due mover: **NOK** (+0,672, peso non allocato 2,0%) e **MU** (+0,396, 2,3%). Il
controfattuale è **negativo in entrambi i casi**: i segnali arrivano alle 16:37, cioè dopo il gap, e la
gamba intraday di NOK è −0,72% e quella di MU −0,18%. Il guard ha risparmiato denaro oggi.

## 5. Pattern osservato

**Tema chiaro: memoria/storage e semiconduttori AI-adiacenti, su CPI benigno e utili AI.** La coda
superiore è compatta e monotematica — DELL +9,87% e WDC +3,69% (carenza di memoria, SanDisk e SK Hynix
+8%), MU +4,92% («Micron Reclaims $1 Trillion Valuation»), AMAT +4,29%, INTC +3,32% (aumento di capitale
da $20 mld letto come bullish per il foundry), NVDA +3,03%, con SOXX +2,32% e XLK +1,49% a contorno.
Fuori tema ma nella stessa coda: NOK +9,32% (idiosincratico, «Why Is Nokia Stock Surging Wednesday?»),
SPCX +9,65% (Starlink), ORCL +5,36%. La coda inferiore non è un settore: META −3,38% e HD −3,12%
(cambio ai vertici prima degli utili) sono due storie separate, e i finanziari, l'energia e il pharma
stanno tutti entro ±2%. Non c'è rotazione: c'è un blocco che sale e un mercato fermo.

**Il tratto che conta è però l'orario, non il settore.** Quota del movimento totale contenuta nel gap di
apertura, per i 9 mover al rialzo:

| | NOK | WDC | INTC | MU | AMAT | ORCL | DELL | NVDA | SPCX |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| gap | +10,12% | +4,37% | +3,70% | +5,11% | +4,26% | +5,04% | +4,15% | +1,63% | +1,32% |
| intraday | −0,72% | −0,65% | −0,38% | −0,18% | +0,03% | +0,31% | +5,49% | +1,38% | +8,22% |
| quota nel gap | 109% | 118% | 111% | 104% | 99% | 94% | 42% | 54% | 14% |

Mediana 99%. Su sette nomi su nove il movimento era **integralmente fuori dalla sessione**: la news
arriva a mercato aperto quando il prezzo l'ha già scontata durante la notte, e la gamba intraday è
mediamente negativa. La metrica solita di F-030 («quota del movimento intraday già avvenuta al primo
segnale») oggi è degenere e non la riporto: con denominatori dell'ordine di 0,03%-0,31% produce valori
fra −498% e +113% che non significano nulla. La forma corretta della stessa osservazione, oggi, è la
quota nel gap.

Le due sole eccezioni — SPCX (86% del movimento intraday) e DELL (58%) — sono l'unico alpha realmente
disponibile della giornata. DELL era già a libro da S1 dal 13/07. SPCX è stato comprato, alle 18:52, al
92° percentile del range: catturato il nome, perso il movimento.

## 6. Confronto con le sedute precedenti

- **Prima seduta della finestra con zero miss NO_NEWS.** La serie delle cause dominanti era NO_NEWS in
  quasi tutte le sedute (3 il 08-03, 5 il 08-04, 2 il 08-05, 1 il 08-06, 3 il 08-07, 2 il 08-10, 4 il
  08-11); oggi 0. Non perché la copertura sia migliorata — 51/96 simboli restano a zero righe, dentro la
  banda 40-55 di tutta la finestra — ma perché il tema del giorno (memoria/AI) è esattamente quello su
  cui Benzinga e GDELT scrivono di più. La copertura è **correlata al tema**, non uniforme: quando la
  coda cade su nomi di cui si parla, NO_NEWS sparisce; quando cade su BP, QCOM, SAP, JD, riappare.
- **Il percentile d'ingresso alto è ricorrente, non un caso di oggi.** Già annotato il 08-06 (MSFT 0,753,
  SPCX 0,748 contro mediana 0,526); oggi 0,768 / 0,714 / 0,920 contro 0,535. Quattro ingressi su quattro
  sopra la mediana mobile in due sedute distinte, entrambe con esito negativo sulle posizioni aperte.
- **Il pattern «venduto e poi è risalito» è alla seconda seduta consecutiva.** Ieri SONY e HOOD, oggi IBM,
  tutti con la stessa reason FIX-D/`_signals_as_of` (F-035), più NVDA su un articolo di terzi (F-008,
  sesta giornata del pattern).
- **La rotazione settoriale che ha caratterizzato le prime sette sedute oggi non c'è.** Le sedute 08-03 →
  08-11 avevano ciascuna una direzione di rotazione diversa; oggi è un rally monotematico con il resto
  del mercato fermo. Non ne traggo altro: è un solo giorno.

## 7. Segnalazioni

Nessuna proposta di correzione: siamo dentro la finestra di sola osservazione. Dove una causa sembra un
difetto di correttezza e non un limite noto, lo dico e mi fermo.

**[F-030] Il movimento avviene prima che il motore possa vederlo, e quando può vederlo entra sul massimo.**
Due facce della stessa cosa, oggi entrambe misurabili. (a) Sui 9 mover al rialzo la quota mediana del
movimento contenuta nel gap di apertura è **99%**; su 7 nomi su 9 la gamba intraday è piatta o negativa.
Il miss di ORCL vale $117,95 sul return pieno ma **$6,82** sulla porzione catturabile. (b) I tre ingressi
S4 della giornata sono al 77°, 71° e 92° percentile del range, contro una mediana mobile a 20 giorni di
0,535, e valgono −34,49 $ di MTM (SPCX −18,33, INTC −16,16) su tre titoli che hanno tutti chiuso in verde.
Costo registrato: **41,31 $** (34,49 misurati sugli ingressi + 6,82 congetturali su ORCL).

**[F-008] L'uscita da NVDA è decisa da un articolo su Lumentum.** BUY alle 17:22 su +0,343 conf 0,650
dall'unico pezzo su Nvidia della giornata; alle 18:30 arrivano due punteggi da articoli su società terze
(«Lumentum Posts Solid Q4…» +0,023 conf 0,275 e la rassegna CPI +0,080 fallback), vince l'ultimo, e alle
19:07 la SELL cita `score=+0,023`. NVDA chiude +3,03%. Costo attribuito **1,38 $** (drift dopo l'uscita).
Sesta giornata del pattern.

**[F-035] IBM venduta col meccanismo isolato ieri, e risale.** `execution_decisions` delle 14:22, reason
identica parola per parola a quella di SONY e HOOD del 08-11: `S4 signal was stale but FIX-D re-admitted
it this cycle — open position, no counter-signal — and the weight is 0 anyway`. Realizzato −26,47 $ su una
posizione tenuta 19,25h; dopo l'uscita IBM sale di **13,71 $** sulla stessa quantità. Costo attribuito
**13,71 $** (controfattuale corto: stessa giornata, stessa size). Seconda giornata consecutiva.

**[F-012] Metà delle righe scorate nasce ancora da articoli su società terze.** 27 articoli su 111 (24%)
sono taggati a 2+ ticker e generano **73 delle 157 righe scorate (46,5%)**, in linea con la serie
51%-66%-53%-55%-51,5%-48,8% delle sedute precedenti. Casi del giorno: NVDA ha 11 righe di cui **10 su
CoreWeave, IREN, Lumentum, Shkreli e Musk**; MU ne ha 10 di cui 9 via `org_lookup`, comprese due rassegne
Baystreet sui futures e un modulo 13F («G&S Capital LLC Sells 4,094 Shares of Micron»). Costo **0,00
verificato, non stimato per difetto**: l'unico ordine nato oggi da un pezzo su società terza è l'uscita
NVDA, il cui costo è già registrato su F-008 — contarlo qui sarebbe doppio conteggio.

**[F-020] Nuovo falso positivo del resolver, fuori dal cluster bancario: NOK ← «Nokian Renkaat Oyj».**
`news_log` del 08-12, `extraction_method='org_lookup'`: «Head to Head Survey: Iochpe-Maxion (OTCMKTS:IOCJY)
vs. Nokian Renkaat Oyj (OTCMKTS:NKRKF)» è attribuito a **NOK**. Nokian Renkaat è un produttore finlandese
di pneumatici, non ha alcun rapporto con Nokia, e ha un proprio ticker OTC citato nel titolo stesso. È il
primo caso registrato del difetto su un ticker non bancario, e mostra che la causa è la somiglianza del
nome societario, non una peculiarità di MS/GS/DB. Quel cluster resta comunque il più grosso: MS 18 righe,
GS 12, DB 5 = **35 delle 87 righe `org_lookup` del giorno (40%)**, su articoli riguardanti easyJet, il
Sensex, un 13F su Micron, ERock e Brookfield — nessuno sulle tre banche. Costo **0,00 verificato**: la
riga NOK/Nokian ha prodotto un punteggio 0,000 e nessun ordine.

**[F-031] Il guard anti-pyramiding blocca 8 ingressi S4 sopra gate, oggi a ragione.** Fra i simboli
bloccati due mover: NOK (+0,672, il punteggio più alto della giornata, peso non allocato 2,0%) e MU
(+0,396, 2,3%), entrambi già a libro da S1 da luglio. Costo **0,00 verificato**: entrambi i segnali
arrivano alle 16:37, dopo il gap, e le rispettive gambe intraday sono −0,72% e −0,18% — gli ingressi
bloccati avrebbero perso denaro. Registro la ricorrenza strutturale, non un costo.

**[F-001] Copertura news: 51/96 simboli a zero righe, ma per la prima volta nessun mover nel buco.**
53% della watchlist senza una riga in `news_log`, dentro la banda 40-55 di tutta la finestra. Costo
**0,00 verificato, non stimato per difetto**: tutti e 11 i mover del giorno hanno copertura, quindi la
lacuna strutturale oggi non è costata nulla. Il dato interessante è la spiegazione: la coda del giorno
cade sui semiconduttori e sulla memoria, cioè il tema più coperto dalle fonti — la copertura è correlata
al tema, e le sedute in cui NO_NEWS domina sono quelle in cui la coda cade altrove. Il finding resta
aperto per ricorrenza strutturale.

**[F-002] 11 posizioni su 49 restano senza `stop_strategy`.** Stesso insieme delle sette sedute precedenti
(BAC, GOOGL, GS, MS, PBR, RIO, ROKU, SPY, UBS, UNH, XLE, tutte entrate il 10/07). Portano **+29,02 $ dei
+271,26 $ di MTM del giorno**, cioè l'11%. Costo null: non è una perdita, è P&L non attribuibile, e
confligge con la domanda di uscita n.2 della carta.

**[F-006] Il Decision Log registra un segnale ribassista come se fosse rialzista.** Sembra un difetto,
non un limite noto. HD produce alle 18:15 e alle 19:15 due segnali **negativi** (−0,118 e −0,204) e le
righe `execution_decisions` corrispondenti riportano `score 0.118 < feedback threshold 0.300` e
`score 0.204 < feedback threshold 0.300`: il segno è perso. La causa è
`portfolio_scheduler.py:3186`, che compone la reason con `abs(sig_score)` — coerente col gate, che è
anch'esso in valore assoluto (righe 3719-3720), ma il risultato è che **a valle non si distingue una
chiamata ribassista corretta da una chiamata rialzista debole**. Oggi la differenza è sostanziale: HD ha
chiuso −3,12% e il modello aveva ragione, ma dal DB la giornata di HD è indistinguibile da quella di
un titolo scartato per tiepidezza. Il gate stesso non è in discussione (è congelato e comunque
documentato); il problema è che la metrica su cui verrà falsificata la domanda di uscita n.1 —
la distribuzione delle cause di miss — legge questo campo. Costo non stimabile: nessun ordine ne dipende.

---

### Nota di conformità alla carta di osservazione

Nessun parametro toccato, nessun fix proposto, nessun ordine inviato. I 24 cicli portfolio della giornata
(14:07 → 19:52 UTC) sono regolari, nessun gap oltre i 16 minuti.
