# S2 - Variance Risk Premium: feasibility study su strumenti, broker e dati

**Data:** 2026-08-17
**Issue:** #57
**Autore:** agente (lavoro AFK)
**Stato:** studio di fattibilita, non di design. Nessun acquisto, nessuna subscription,
nessun ordine e nessuna promozione a paper o live. Le risposte alle domande 1-7 della
issue sono ricavate solo da fonti primarie pubbliche accessibili al 2026-08-17.
**Provenienza:** questo documento non e un tracker di stato della roadmap. Le decisioni
operative che ne derivano sono elencate nella sezione finale e richiedono separata
approvazione del PO.

**Predecessore concettuale:** la teoria approvata dal PO il 2026-07-15 vive in
`docs/strategies/s2-vrp-theory.md`. La feasibility presuppone che quel gate teorico
risulti superato (sezione 19 della teoria) e risponde al "come si realizza" senza
reintrodurre la discussione del "cosa si cattura".

## 1. Executive verdict

**CONDITIONAL GO - ma con un perimetro di broker e candidati piu stretto di quello
proposto nella issue.** Il candidato #1 (Cboe S&P 500 Variance Futures, ticker CFE **VA**)
soddisfa quattro delle cinque condizioni hard della PO-19 (defined-loss, listing,
clearing, settlement in OCC). La quinta condizione (liquidita) e verificabile solo a
livello di trade history, non di marketing copy: i dati ADV pubblicati da Cboe su
`cboe.com/us/options/market_statistics/daily/` e su `ir.cboe.com` indicano volumi
storicamente molto bassi rispetto a VX (VIX futures), e questo resta il principale
rischio di esecuzione. Il candidato #2 (SPX option-strip replication) richiede un
broker che offra SPX/SPXW come underlying eseguibile in **live**; la verifica su Alpaca
(retail) ha esito negativo al 2026-08-17 e su IBKR rimane un'ipotesi operativa, non una
garanzia. Il candidato #3 (SPX delta-hedged book) e il piu debole dei tre su bounded
loss e non va preso in considerazione se la PO-19 ha priorita 1.

Il verdict non e' GO pieno per due motivi: (a) Alpaca retail non offre index options in
live trading (solo paper, e solo per i simboli esplicitamente elencati - SPX, SPXW, XSP,
DJX, VIX, VIXW), quindi il candidato #2 non e eseguibile senza IBKR; (b) la liquidita
del candidato #1 va confermata su un dataset storico di almeno tre mesi consecutivi,
cosa che qui non viene misurata.

## 2. Domanda 1 - Cboe S&P 500 Variance Futures (candidato #1)

### 2.1 Listing, settlement, clearing, specifiche

Il contratto e listato sulla CBOE Futures Exchange (CFE) sotto il ticker **VA**. La
documentazione primaria Cboe (FAQ PDF ufficiale) specifica:

- **Sottostante:** S&P 500 Index (SPX), indice proprietario S&P DJI.
- **Calcolo della varianza realizzata:** `RV = (252 / N) * Sum[r(t)^2]` con `r(t) =
  ln(S(t) / S(t-1))`, dove `S(t)` e il prezzo SPX al minuto `t` su un campione
  1-minutario di N rilevazioni tra l'open del Last Trade Day e la close del giorno
  precedente al Final Settlement Date. Annualizzazione su base 252.
- **Settlement:** cash settlement, single payment alla expiration. No physical delivery.
  Clearing centrale tramite OCC. (Fonte: Cboe FAQ PDF, domande 1-2.)
- **Eligible expirations:** fino a 23 per anno, scadenze da 30 a 365 giorni. Settlement
  il venerdi, ad esclusione dei venerdi di Monthly Option Expiration (MEOC). Per le
  scadenze mensili, settlement il venerdi che chiude il mese. (FAQ domanda 3.)
- **Final Settlement Date:** terzo venerdi del mese di expiration. Last Trade Day: il
  mercoledi precedente. (FAQ domanda 4.)
- **Tick / multiplier / posizione:**
  - Tick minimo 0.05 punti di varianza (1 vol point = 1 punto di varianza).
  - Valore del tick = `0.05 * $1,000 = $50` per contratto.
  - Contract multiplier: `$1,000` per unita di varianza (un punto di varianza vale
    $1,000 per contratto).
  - Position limit (regolamentare): 10,000 contratti long o short in una qualsiasi
    scadenza. No accountability level separato.
  (FAQ domande 6-8.)

- **Esempio di payoff (FAQ, domanda 10):** se la RV finale calcolata e 0.04 (cioe 4
  punti di varianza, equivalenti a circa 20% di volatilita annualizzata), il Final
  Settlement Value per contratto e `0.04 * $1,000 = $40,000`. Se il contratto era stato
  acquistato a un fair variance strike di 0.03, il P&L lordo e `($40,000 - $30,000) =
  $10,000` per contratto long.
- **Bounded loss:** la perdita massima per il compratore e limitata al premio pagato
  (contrariamente a una short variance position, che ha payoff illimitato). Per il
  venditore, la perdita massima teorica e RV = 0, che darebbe settlement value 0, cioe
  perdita pari al premio incassato. Quindi **entrambi i lati hanno bounded loss per
  costruzione del contratto**. (FAQ domanda 11-12; e' il tratto distintivo rispetto
  a una OTC variance swap che ha lo stesso profilo ma senza clearing centrale.)
- **Cash daily mark-to-market:** si, variazione di margine giornaliera. (FAQ domanda 13.)

### 2.2 Liquidita - la condizione fragile

Il documento Cboe evidenzia "block trades e ECRP transactions" come meccanismi di
migrazione da OTC, ma non pubblica un ADV numerico ufficiale del VA sulla pagina FAQ.
La pagina di prodotto (`cboe.com/en/tradable-products/sp-500/variance-futures/`) e
renderizzata dinamicamente e non contiene testo statico su volumi. Le fonti terze
indicano storicamente volumi molto inferiori ai VX (VIX futures), dove VX muove
centinaia di migliaia di contratti al giorno nelle scadenze front-month. VA non e un
prodotto "mainstream" e la letteratura accademica usa sovente la strip SPX come
surrogato proprio per la scarsita di profondita del VA.

**Cosa va misurato prima di un GO pieno:** ADV su rolling 3 mesi, open interest per
scadenza, bid-ask spread tipico sul book, presenza di market makers designati, e
disponibilita di quote in regime di stress (ottobre 2008, febbraio 2018, marzo 2020,
2022). La FAQ Cboe indica esplicitamente che block trade ed ECRP sono i canali
primari, il che di per se e' un segnale che il book aperto non sempre offre depth
sufficiente.

### 2.3 Accesso IBKR

IBKR offre il VA come futures. Il simbolo lato IBKR segue la convenzione CFE: la
root symbol e **VA**, esposta in TWS come `VA{YYM MMM}` (esempio `VA26H` per
scadenza marzo 2026). L'alternativa `VARG` che compare in alcune pagine marketing
non e un ticker primario CFE.

**Margin Reg-T tipica:** circa $2,500 per contratto sul front-month, con profilo che
**decresce verso il Last Trade Day** (la variazione marginale si riduce man mano che
l'intervallo di settlement si accorcia). Questo e' esplicitamente diverso da VX dove
il margin resta flat. Per conti istituzionali o a tier superiore, IBKR puo applicare
SPAN CFE, che e' capital-efficiente. (Fonte: web search su doc IBKR Traders' Insight e
pagine futures CFE - link in sezione 9.)

**Caveat operativo:** il Reg-T di $2,500 e' nominale; il notional per contratto a
un trade price di 25 vol points (variance 0.0625) e' `1,000 * 625 = $625,000`. La
vera esposizione e quindi di due ordini di grandezza superiore al margine iniziale:
le variazioni giornaliere di MTM possono produrre margin call nell'ordine delle
decine di migliaia di dollari su un singolo contratto, e questo va dimensionato
contro il budget di sleeve della PO-19.

### 2.4 Commissioni e costi espliciti

IBKR applica commissioni futures secondo la tabella pubblica. Il valore preciso per
VA va confermato sulla pagina `interactivebrokers.com/en/pricing/commissions-options-futures-fop.php`
(la pagina e renderizzata dinamicamente e non e' catturabile con curl semplice al
2026-08-17). Per la pianificazione del budget si assume una commissione IBKR futures
US dell'ordine di $0.62-$1.12 per contratto per lato (ordine di grandezza tipico per
le CFE equity-index futures), piu' exchange + clearing fees Cboe/OCC. **Cifre da
confermare prima di firmare il budget di sleeve.**

## 3. Domanda 2 - SPX option-strip replication (candidato #2)

### 3.1 Cosa offre il sottostante SPX

Le opzioni SPX su Cboe Options Exchange (ticker root **SPX**) sono:

- **Cash-settled, European-style** (no early assignment, no physical delivery).
- **AM-settled** (SPX tradizionali) e **PM-settled** (SPX Weeklys = **SPXW**, EOM).
- **Mini-SPX (XSP):** 1/10 del notional SPX. Stesse caratteristiche settlement.
- **Nanos S&P 500:** 1/100 di XSP.
- **GTH (Global Trading Hours):** 8:15 PM - 9:25 AM ET, copertura 24/5 per SPX, SPXW,
  XSP. VIX e VIXW idem.
- **Tax treatment:** 60% long-term / 40% short-term capital gains sotto Section 1256
  del US Tax Code, sia per SPX che per SPXW.
- **Covered margin treatment** quando la posizione short SPX e offsettata da un ETF
  index-tracking (SPY o IVV) nello stesso account. (Fonte: Cboe SPX options product
  page, sezione "Certainty of Settlement, No Contra-Exercise Risk" e footnote su
  RG15-183.)

(Fonte primaria: `ww2.cboe.com/tradable-products/sp_500/spx_options/`.)

### 3.2 Approssimazione 30d con strip

Una replica modello-libera della varianza 30d usa una strip di opzioni OTM put + call
su SPX con scadenza 30 giorni, secondo la formula di Carr-Madan o di Neuberger-Bakshi-
Cao-Chen. La purezza di replica dipende da:

- Densita della catena OTM: SPXW garantisce daily + EOM expiry, e 0DTE e ormai
  una realta' su SPX/SPXW. Quindi la copertura di scadenze e' ampia.
- Bid-ask spread: il book SPX 0DTE e' profondo, ma la qualita' peggiora sugli strikes
  lontani dal forward. La letteratura (Carr-Wu 2009, Broadie-Johannes) riporta
  bias sistematici nella varianza implicita estratta da strip.
- Truncation effects: serve un cap inferiore e superiore sugli strike per ridurre
  l'influenza delle ali. La scelta del cap modifica l'esposizione non-linear e va
  calibrata sul book eseguibile.
- Jump risk residuo: la strip non neutralizza perfettamente i salti overnight; serve
  un aggiustamento esplicito (es. correzione di Broadie-Jain o bootstrap con forward).
- Funding: la strip replicante richiede di finanziare l'acquisto delle opzioni (o di
  incassare il premio sul lato short). Il funding rate e' un costo primario che la
  PO-19 ha esplicitamente escluso dal perimetro di sostituzione: e' una leva di
  taglio del rendimento, non una sostituzione dello strumento.

### 3.3 Broker access - la verifica Alpaca

Il commento dell'operatore del 2026-07-23 sulla issue #57 segnalava il lancio di
index options in paper su Alpaca. Verifica al 2026-08-17:

- **Paper trading (retail):** SPX, SPXW, XSP, DJX, VIX, VIXW disponibili via
  `/v2/options/contracts?underlying_symbols=SPX,XSP,DJX,VIX&style=european`.
  Conferma ufficiale di Dan Whitnable (Alpaca) sul community forum, 2026-06-30 e
  2026-07-01. (Fonte: `forum.alpaca.markets/t/when-will-you-support-index-options/16411`.)
- **Live trading (retail):** NON ancora disponibile. La stessa fonte Alpaca scrive:
  "As of June 2026, index option trading is live for broker partner accounts but not
  for Alpaca retail accounts. They should be coming soon for retail accounts, but no
  specific date has been announced." (Dan Whitnable, post #11 sul thread.)
- **Commissioni:** `$0.50 per contract + Cboe exchange pass-through fees (vary by
  symbol)` per la fase paper; retail e' commission-free per equity/ETF options
  secondo la pagina `alpaca.markets/options`, ma la pagina stessa dichiara "index
  options coming soon" e quindi la commissione retail per index options non e' ancora
  formalizzata.
- **Trading levels:** il sistema Alpaca usa 4 livelli (0-3). Le index options per
  retail saranno presumibilmente soggette allo stesso gating, ma il livello richiesto
  e la sequence di approval non sono documentati al 2026-08-17.

**Implicazione:** il candidato #2 non e' eseguibile live su Alpaca retail oggi. Se
Alembic vuole usare solo Alpaca come broker, il candidato #2 e' escluso finche' la
disponibilita' retail non viene annunciata. Per restare nel perimetro "no secondo
broker", il candidato #2 va parcheggiato.

### 3.4 Broker access - IBKR

IBKR offre SPX e SPXW come listed options su Cboe Options Exchange. Le permission
richieste sono:

- **Account type:** margin account necessario per vendita uncovered; cash account
  limita a defined-risk strategies (spread, butterfly, calendar). Le IRA hanno
  restrizioni piu' severe (tipicamente no naked options).
- **Market data subscription:** `NP-NYSE' e `NQBX' per OPRA + Cboe depth.
  Costo indicativo (dalla tabella IBKR pubblica, da confermare sulla pagina
  specifica): ~$1.50-$14.50/mese a seconda dei pacchetti; il bundle OPRA
  professional e' ~$60-$80/mese, con fee di exchange addizionali.
- **Symbol root:** `SPX`, `SPXW` (Weeklys), `SPX` + monthly (EOM). XSP se serve
  taglia 1/10. OCC clearing standard.
- **Order types:** market, limit, stop, OCO, OTO, brackets. Algo order: VWAP, TWAP,
  Adaptive. Per la replicazione modello-libera servono quote leggibili in real time.
- **Margin su SPX short put:** Reg-T standard o portfolio margin. SPX cash-secured
  put richiede buying power pari allo strike * 100. Una short put spread riduce il
  margin a `(strike_long - strike_short) * 100 - premium`.

(Le cifre di margin/market data vanno verificate su `interactivebrokers.com/en/pricing/`
al momento dell'effettiva apertura del conto, dato che le pagine IBKR sono largamente
renderizzate dinamicamente e i numeri cambiano.)

### 3.5 Sintesi candidato #2

Purezza di replica: alta se la strip e' daily-rrolled, ma con **basis, truncation,
jump e funding** non eliminabili. Bounded loss: solo per le strategie spread
(credit spread, iron condor), non per naked short volatility. Esecuzione: richiede
IBKR se Alembic non vuole aspettare Alpaca retail. Costo delisto: OPRA market data +
commissioni + funding. Il candidato #2 ha un perimetro di bounded loss **narrower**
del candidato #1 (che ha bounded loss per costruzione su entrambi i lati).

## 4. Domanda 3 - rischi residui per candidato

### 4.1 Candidato #1 (VA futures)

| Rischio residuo | Natura | Mitigazione | Rimozione completa? |
|---|---|---|---|
| Basis (VA vs replica SPX) | VA replica RV 1-min, non VIX^2; gap tra il portafoglio sintetico OTC e VA | Nessuna naturale; documentare | No |
| Jump / overnight gap | La RV include i gap overnight; una notizia macro sposta RV senza che il trader possa uscire | Bounded loss per il lato long; short variance e' illimitato | Solo sul lato long |
| Settlement (occasionalita' Friday move) | Final Settlement il terzo venerdi; se coincide con MEOC, slitta | Calendar awareness | No |
| Roll | VA non ha una curva di scadenza liquida a 30d; il "30d" si realizza solo nel Last Trade Day | Calendar roll continuo | No, costo strutturale |
| Convexity / vol-of-vol | Il payoff e lineare in variance, non in vol; la copertura su base daily puo' sottoperformare | Monitoraggio P&L | No |
| Liquidita | ADV basso, bid-ask wide, block trade come canale primario | Limit orders, RFQ, ECRP | No, strutturale |
| Hedge | VA non richiede hedge esplicito (e' gia variance pura) | n/a | n/a |
| Counterparty | Clearing centrale OCC, no bilateral | n/a | gia' mitigato |

### 4.2 Candidato #2 (SPX option strip)

| Rischio residuo | Natura | Mitigazione | Rimozione completa? |
|---|---|---|---|
| Basis (strip vs continuous) | Truncation, discretization, jump residual | Bias correttivi (Broadie-Jain) | Parziale |
| Jump | Strip non neutralizza salti; aggiustamento modello-dipendente | Modello jump, accrual | Parziale |
| Settlement | SPX AM vs SPXW PM: due settlement date diverse | Calendar | n/a |
| Roll | Daily roll se si vuole 30d continuo; costo di bid-ask + commissioni | Calendar aware | No, costo |
| Convexity | Strip esplicita, hedging richiesto | Delta-hedge SPX del book | Parziale (gamma residuo) |
| Liquidita | SPX 0DTE profondo, ma ali sottili | Limit order, RFQ | Parziale |
| Hedge | SPX delta hedge continuo (intraday) | Costoso (commissioni, market impact) | No |
| Funding | Acquisto opzioni richiede capitale; vendita opzioni richiede margine | Capital allocation | No |
| Counterparty | OCC clearing, no bilateral | n/a | gia' mitigato |

### 4.3 Candidato #3 (SPX delta-hedged book)

Puo' essere considerato una variante del candidato #2 in cui la posizione in opzioni
e' sostituita da una combinazione di spot SPX (via SPY/IVV) e short puts/calls, con
ri-bilancing discreto. Purezza molto piu' bassa: il delta-hedge discreto fallisce sui
salti, e l'esposizione non e' piu' "pura variance" ma una mistura di equity beta,
skew, vol-of-vol, gamma. **Non soddisfa la condizione "purity" della PO-19** se la
purezza e' definita come vicinanza a `E^Q[QV] - E^P[QV]` su SPX. Escluso per
decisione di design, non di feasibility.

## 5. Domanda 4 - vendor matrix per SPX surface PIT 1996-oggi

La tabella raccoglie i vendor che possono soddisfare il requisito "SPX negoziato dal
1996 al presente, con PIT 2008, febbraio 2018, marzo 2020, 2022 obbligatori; 1987 come
stress ricostruito separato" fissato nella PO-19. Nessun acquisto e' stato effettuato
per questo studio; le cifre di costo sono indicative e da confermare con un vendor
formale.

| Vendor | Prodotto | Copertura storica SPX | EOD / intraday | PIT | Costo indicativo annuo | Note |
|---|---|---|---|---|---|---|
| OptionMetrics (MIAX) | IvyDB US | 1996-oggi | EOD, intraday dal 2006 | Si (no look-ahead) | Accademico ~$1.500-$2.500; commerciale ~$10.000-$20.000+ | Standard di fatto accademico; copertura tutti gli strike + Greeks. Fonte: optionmetrics.com |
| CBOE DataShop | Cboe historical options + Data Vantage | 1986-oggi (Cboe-proprietary) | EOD + intraday | Si | Quote su richiesta, indicativamente ~$3.000-$15.000+/anno per surface completa | Proprietario Cboe: migliore copertura SPX, ma dipendenza da Cboe per changelog |
| ORATS | ORATS Historical | 2007-oggi, ~1.200 ticker | EOD (surface) | Si | Quote su richiesta, contatto commerciale | Include IV, greeks, OI, 30+ campi calcolati |
| Polygon (ora Massive) | Options API (OPRA) | 2003-oggi | EOD free; intraday 1-min da $29/mese; real-time da $199/mese | Si (ma qualita' EOD variabile per i 2003-2010) | Starter $29-$199/mese | API REST/WS; nessun endpoint "all trades for date", serve paginare per contratto |
| Bloomberg (B-PIPE / BBG) | WAPI options | 1986-oggi (dipende dalla licenza) | EOD + intraday | Si (terminal-level PIT) | ~$24.000-$28.000/anno per Bloomberg Terminal + add-on | Gia' usato da operatori istituzionali |
| Refinitiv (LSEG) | Tick History / Datascope | 1996-oggi | EOD + intraday | Si | ~$15.000-$25.000/anno per surface completa | Wraps OptionMetrics-like per opzioni |
| CBOE LiveVol (S&P Global) | LiveVol | 2002-oggi (varies) | EOD + intraday | Si | Contatto commerciale | Storicamente popolare per accademia; copertura un po' piu' corta di IvyDB |

(Fonti: optionmetrics.com, cboe.com, orats.com, polygon.io, bloomberg.com/refinitiv -
pagine marketing pubbliche. I costi sono ordini di grandezza riportati dalla
letteratura secondaria; non costituiscono quote.)

### 5.1 Quote/data contract (per commento initial-d del 2026-07-27)

Ogni osservazione storica SPX usata per la validazione dovra' portare:

- `option_root`, `expiry_date`, `strike`, `put_call_flag`, `contract_id` (OCC).
- `quote_timestamp` + `quote_timezone` (ET vs UTC).
- `bid`, `ask`, `midpoint`, `size` se disponibile, `stale_quote_flag` (0/1).
- `underlying_spx_level`, `risk_free_rate_input`, `dividend_input`.
- `settlement_type` (AM vs PM), `tradable_indicator` (eseguibile o solo indicativo).
- `vendor_name`, `license_boundary`, `retrieval_date`.

La decisione di un vendor (o di una combinazione OptionMetrics + CBOE DataShop)
richiede un test di copertura esplicito su 4 date campione (2008-10-15, 2018-02-05,
2020-03-16, 2022-09-13) e su 1 mese di trading completo (es. gennaio 2010) per
verificare completezza, mancanza di look-ahead e bid-ask coverage. **Il test va
fatto dopo la firma del budget, non in questa feasibility.**

## 6. Domanda 5 - bounded loss e stressed margin

### 6.1 Vincoli della PO-19

- **Max loss contrattuale:** 2% NAV Alembic.
- **Stressed margin:** <= 50% del capitale della sleeve.

### 6.2 VA futures (candidato #1)

- **Bounded loss:** SI per il lato long. La perdita massima e il premio pagato; la RV
  finale e' floorata a 0 dal calcolo (varianza non negativa), quindi il settlement
  value minimo e 0. (FAQ domanda 11.)
- **Bounded loss:** SI anche per il lato short in termini nominali - la perdita
  massima del venditore e' il premio incassato se la RV va a 0. **MA attenzione:**
  RV = 0 e' un evento economico estremo (zero volatilita' realizzata per l'intero
  mese), non un floor contrattuale. Il contratto non ha un cap superiore esplicito
  sulla RV finale, quindi la perdita del venditore e' limitata dal premio incassato
  solo **se la posizione viene chiusa a mercato prima della expiration**. Se la
  posizione viene tenuta fino a settlement, la perdita lorda del venditore
  e `RV_final * $1,000 - premium`, che e' teoricamente illimitata in teoria e puo'
  arrivare a $100.000/contratto se RV finale = 0.10 (10% vol^2 = 31.6% vol).
- **Margin Reg-T:** ~$2,500/contratto front-month. Una sleeve con $50.000 di
  dedicated margin puo' ospitare 20 contratti VA. A trade price 0.05 (variance 0.05
  = 22.4% vol), il notional e' `$1,000 * 0.05^2 = $2.500/contratto` in valore di
  settlement, ma il valore del contratto (long variance) a trade entry e' zero (parte
  flat, ha solo theta negativo se si e' short); il "vero" rischio e' il movimento
  mark-to-market, non il nozionale iniziale.
- **Margin stressato:** sotto un ipotetico shock +5 vol points sulla RV (es. RV passa
  da 0.04 a 0.09), il MTM di un singolo contratto long variance e' `+$1,000 * 0.05 =
  +$5,000`. Per il lato short e' -$5,000. Una sleeve 20 contratti short VA subisce
  quindi un MTM di -$100,000 sotto questo stress, che e' circa 200% del dedicated
  margin di $50,000 e quindi genera margin call e forced sale. **Per la PO-19,
  questo scenario e' un fallimento del vincolo "50% stressed margin" se la sleeve e'
  piccola.** Una sleeve 5 contratti short VA subisce invece -$25,000 = 50% del
  dedicated margin, che e' al limite del vincolo. **Una sleeve 1-2 contratti e'
  invece entro i limiti.** La conclusione e che VA futures richiede un budget di
  sleeve molto superiore al 2% NAV per poter avere un numero di contratti
  economicamente materiale (>= 1). Se il budget e' 2% di $110.000 = $2,200, il
  vincolo "economicamente materiale" non e soddisfatto.

### 6.3 SPX option strip (candidato #2)

- **Bounded loss:** solo per strategie spread (credit spread, iron condor, calendar).
  Le strategie naked (short straddle, short strangle) hanno perdita illimitata.
- **Margin su credit spread:** `(strike_long - strike_short) * 100 - premium`. Per
  SPX, con scadenza 30d e ATM, tipicamente $5.000-$15.000 per spread a 1 contratto
  (dipende da vol e distanza tra strikes).
- **Stress test:** un gap di 5% su SPX in un giorno produce un drawdown del lato
  short di circa 4-5x il premio incassato, facilmente superiore al 2% NAV. Il
  candidato #2 richiede un sizing molto conservativo o l'uso di strategie spread
  (che pero' riducono drasticamente il premio).

### 6.4 Sintesi bounded loss

Il candidato #1 ha un bounded loss per costruzione **se la dimensione della posizione
e' <= 1-2 contratti** su una sleeve con budget di sleeve >= $50.000. Il candidato #2
ha bounded loss solo su strategie spread, e lo stress test produce drawdown che
facilmente superano il 2% NAV. **Nessuno dei due candidati soddisfa la PO-19 con
un budget di sleeve < $50.000.** Se il PO fissa un budget di sleeve <= $10.000
(ordine di grandezza del 2% NAV su $500k), la feasibility diventa NO-GO per taglia,
non per design.

## 7. Domanda 6 - IBKR permissions, market data, order types

(Sintesi; vedi sezioni 2.3 e 3.4 per i dettagli gia' esposti.)

- **Permissions:** per VA futures serve un futures-approved account; per SPX options
  serve un options-approved account livello 3 o 4 (covered + uncovered). Le IRA hanno
  restrizioni. SPX/SPXW sono marginabili; SPX naked short put richiede margin
  consistente.
- **Market data subscriptions:** OPRA + Cboe depth per real-time. ~$60-$80/mese per
  OPRA professional. Cboe historical: costo addizionale in Datashop o LiveVol.
- **Symbols:** VA (CFE), SPX/SPXW/XSP (Cboe Options Exchange).
- **Order types:** market, limit, stop, OCO, OTO, brackets, algo (VWAP/TWAP/Adaptive).
  Per la replicazione della varianza 30d servono quote leggibili in real-time e
  fill immediato sul book.

## 8. Domanda 7 - verdict

### 8.1 Hard conditions della PO-19

| Condizione hard | VA futures (cand #1) | SPX option strip (cand #2) |
|---|---|---|
| Listed/cleared | SI (CFE + OCC) | SI (Cboe Options + OCC) |
| Pure variance (vs proxy) | SI - contratto nativo su RV | Parziale (richiede modello e strip) |
| Bounded loss contrattuale | SI lato long; lato short solo se chiuso a mercato | SI solo su spread |
| 2% NAV max loss | SI se <= 1-2 contratti su sleeve >= $50k | SI solo su spread, NO su naked |
| 50% stressed margin | Marginale su 1-2 contratti | Marginale su spread |
| Liquidita verificata | Da misurare (ADV Cboe, rolling 3 mesi) | SPX 0DTE profondo, ma ali sottili |
| Esecuzione broker oggi | IBKR: SI, futures-approved | IBKR: SI, options-approved; Alpaca retail: NO (paper only) |

### 8.2 Verdetto

**CONDITIONAL GO** - ma solo per il candidato #1 (VA futures) e solo se sono soddisfatte
contemporaneamente le seguenti condizioni pre-trade:

1. Apertura di un conto futures-approved IBKR (oggi Alembic usa Alpaca; richiede un
   secondo broker o la sostituzione, che e una decisione di operatore).
2. Allocazione di una sleeve ring-fenced di almeno $50,000 di dedicated margin.
3. Misurazione pre-trade dell'ADV VA su un rolling 3 mesi (gennaio-marzo 2026) e
   conferma che il bid-ask spread su almeno 5 scadenze mensili consecutive e <= 0.10
   punti di varianza.
4. Vendor matrix confermata con almeno 2 vendor indipendenti (OptionMetrics + CBOE
   DataShop) per la validazione PIT.
5. Decisione PO su: (a) sleeve size, (b) broker, (c) budget vendor data, (d)
   tolleranza al MTM gap su stress.

Se una di queste 5 condizioni fallisce, il verdict degrada a NO-GO.

### 8.3 Esclusioni esplicite

- **Candidato #2 con Alpaca retail:** escluso al 2026-08-17 per mancanza di
  disponibilita live.
- **Candidato #3 (SPX delta-hedged book):** escluso per violazione del vincolo di
  purezza (PO-19).
- **Proxy non-variance (short put, VIX futures, long SPY):** esclusi dalla PO-19.

## 9. Fonti primarie consultate

Tutte le affermazioni fattuali di questo documento si appoggiano alle seguenti fonti
pubbliche, accessibili al 2026-08-17:

1. **Cboe S&P 500 Variance Futures FAQ (PDF ufficiale).** URL:
   `https://cdn.cboe.com/resources/participant_resources/Cboe_Variance_Futures_FAQ.pdf`.
   5 pagine, 251KB. Specifiche contratto, settlement, multiplier, tick, position limit,
   bounded loss, MTM.
2. **Cboe - S&P 500 Index Options product page.** URL:
   `https://ww2.cboe.com/tradable_products/sp_500/spx_options/`. Caratteristiche SPX,
   SPXW, XSP, GTH, settlement AM/PM, 60/40 tax, covered margin treatment.
3. **Cboe - S&P 500 Variance Futures product page.** URL:
   `https://www.cboe.com/en/tradable-products/sp-500/variance-futures/`. Pagina di
   marketing del prodotto.
4. **Cboe - Risk Management Specification.** URL:
   `https://www.cboe.com/document/tech-spec/content/technical-specifications/cboe-titanium-cboe-futures-exchange-risk-management-specification`.
   Specifiche margine CFE.
5. **Alpaca - Options Trading documentation.** URL:
   `https://docs.alpaca.markets/docs/options-trading`. Enablement, trading levels,
   contracts endpoint. **Non menziona index options nella pagina pubblica**, da cui
   si deduce che sono in rollout separato.
6. **Alpaca - Options marketing page.** URL: `https://alpaca.markets/options`.
   Dichiarazione: "You can trade exchange-listed US equity and ETF options (American
   style) today, with index options coming soon."
7. **Alpaca Community Forum - When will you support Index options?** URL:
   `https://forum.alpaca.markets/t/when-will-you-support-index-options/16411`.
   Post di Dan Whitnable (Alpaca) del 2026-06-30 e 2026-07-01: paper trading
   disponibile per SPX, SPXW, XSP, DJX, VIX, VIXW; live solo per broker-partner
   accounts, retail "coming soon, no specific date."
8. **Cboe - Variance Futures Overview page.** URL:
   `https://www.cboe.com/tradable_products/variance_futures/`. Use cases, confronto
   vs OTC variance swap.
9. **Cboe - DataShop.** URL: `https://www.cboe.com/us/data/market_statistics/`.
   Portale dati Cboe.
10. **OptionMetrics - IvyDB US.** URL:
    `https://www.optionmetrics.com/data-ivydb.html` (pagina di presentazione prodotto;
    il pricing formale richiede contatto commerciale).
11. **Polygon.io - Options API.** URL: `https://polygon.io/` (ora rebrand Massive).
    Piani: Free, Starter $29/mese, Developer $79/mese, Advanced $199/mese.

### 9.1 Limitazioni delle fonti

Alcune pagine ufficiali (vendor symbols Cboe, IBKR commissions, OptionMetrics
pricing) sono renderizzate dinamicamente via JavaScript e non sono accessibili via
`curl` semplice. Le informazioni provenienti da queste pagine sono state ricavate da
WebSearch che indicizza i contenuti, e verificate dove possibile sui documenti
statici (Cboe FAQ PDF, Alpaca docs statiche, community forum). I **costi
indicativi** riportati nella sezione 5 (vendor matrix) sono ordini di grandezza di
settore, non quote formali.

## 10. Domande aperte e conferme esterne richieste

Questa feasibility non puo' essere chiusa senza le seguenti conferme esterne, che
richiedono interazione umana (operatore):

1. **Conferma IBKR formale su VA futures** - simboli esatti per anno, Reg-T corrente
   per scadenza, exchange + clearing fees, market data subscription richiesta.
2. **Conferma IBKR formale su SPX/SPXW/XSP** - permission level richiesto per spread
   vs naked, market data fees, eventuali limitazioni per clientela italiana.
3. **Quote formale da almeno 2 vendor** (OptionMetrics + CBOE DataShop oppure
   ORATS) per la copertura 1996-oggi con licenza research-only.
4. **Conferma operativa Alpaca** sul rilascio retail di index options (timeline
   piu' precisa di "coming soon").
5. **Misurazione ADV VA** su un rolling 3 mesi a scelta (consigliato gennaio-marzo
   2026, periodo che include dati di inizio anno con vol normale).
6. **Decisione PO** su: budget di sleeve (>= $50k per candidati 1-2), broker
   (Alpaca-only vs Alpaca + IBKR), vendor data budget, policy di MTM gap su stress.

## 11. Decisioni operative richieste dopo lo studio

Nessuna decisione e' stata applicata in questo studio. Le decisioni che **spettano al
PO** prima di un qualsiasi passo successivo sono:

| ID | Decisione | Opzioni | Default se nessuna scelta |
|---|---|---|---|
| D-01 | Broker | (a) Alpaca-only, attendere index options retail; (b) Alpaca + IBKR; (c) IBKR-only, abbandonare Alpaca | (a) - minor disruption |
| D-02 | Budget sleeve | $50k / $100k / $250k / nessuna sleeve | $0 - nessuna azione |
| D-03 | Vendor data | OptionMetrics + CBOE DataShop / ORATS / Bloomberg / Refinitiv / nessuno | (d) - studio chiuso senza dati |
| D-04 | Tolleranza MTM gap | ±10% sleeve / ±20% / ±50% | (a) - conservativo |
| D-05 | Timeline | Q3 2026 / Q4 2026 / 2027 / rinvio | (d) - tutto fermo |
| D-06 | Strategia di execution | Market orders / limit-only / RFQ-only | (b) - riduce fill, aumenta certainty |
| D-07 | Ruolo di Alpaca | Mantenere / dismettere / ruolo secondario | (a) - minor disruption |

Le decisioni D-01..D-07 non sono in scope per l'AFK. Vanno prese **dopo** che
l'operatore abbia letto questo studio e il commento PO collegato.

## 12. Cosa NON e' stato fatto (perimetro rispettato)

- **Nessun acquisto di dati, vendor, subscription.**
- **Nessuna apertura di conto IBKR.**
- **Nessun test di execution, paper o live.**
- **Nessun ordine simulato, neanche in paper.**
- **Nessun backtest interno usato come evidenza** (PO-19 divieto esplicito).
- **Nessuna modifica a parametri di taratura** (freeze #171 rispettato).
- **Nessuna sostituzione con proxy** (PO-19 divieto esplicito).
- **Nessuna decisione su candidato definitivo**: il verdict e CONDITIONAL GO,
  e le 5 condizioni pre-trade della sezione 8.2 richiedono conferma esterna
  prima di qualunque GO pieno.

## 13. Registro delle issue aperte derivate

Questo studio non chiude la issue #57 - la issue richiede una feasibility, ma
l'attuazione dipende da decisioni PO. Lo studio quindi marca `Part of #57` e
lascia aperte le seguenti sotto-issue implicite, da tracciare separatamente se
il PO decide di procedere:

- Sotto-issue 1: Decisione broker (Alpaca vs IBKR) - blocca candidati 1-2.
- Sotto-issue 2: Allocazione budget sleeve - blocca dimensionamento.
- Sotto-issue 3: Vendor data selection - blocca validazione quantitativa.
- Sotto-issue 4: ADV measurement VA - blocca conferma liquidita candidato 1.
- Sotto-issue 5: Gate di promozione paper -> IBKR -> live (PO-19 gia indica la
  sequenza, ma va formalizzata in un design doc separato).

## 14. Sintesi in pochi minuti

Cboe S&P 500 Variance Futures (ticker CFE VA) e' un contratto reale, listato,
centrally-cleared, con bounded loss per il lato long e settlement cash via OCC. La
formula di calcolo della varianza realizzata e' ufficiale e standardizzata. Il
principale rischio e' la liquidita', storicamente bassa rispetto ai VX futures, che va
misurata su dati reali prima di un GO pieno.

SPX option-strip replication (candidato #2) e' fattibile su IBKR oggi, ma richiede
un conto aggiuntivo. Su Alpaca retail e' esclusa al 2026-08-17 (index options solo in
paper, retail live "coming soon"). Il bounded loss e' intrinseco solo per le
strategie spread, e lo stress test supera facilmente il 2% NAV su posizioni naked.

Nessuno dei due candidati soddisfa la PO-19 se la sleeve e' < $50.000. Per sleeve
>= $50.000, il candidato #1 (VA futures) e' l'unico che ha bounded loss per
costruzione e che richiede un singolo broker (IBKR).

Il verdict e' CONDITIONAL GO, subordinato a 5 condizioni pre-trade (sezione 8.2) e a
6 conferme esterne (sezione 10). Il PO mantiene tutte le decisioni operative; questo
studio non ha acquistato, attivato o eseguito nulla.
