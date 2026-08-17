# S2 - Variance Risk Premium: feasibility study su strumenti, broker e dati

**Data:** 2026-08-17

**Issue:** #57

**Stato:** studio di fattibilita, non di design. Nessun acquisto, nessuna
subscription, nessun ordine e nessuna promozione a paper o live. Le informazioni
non verificabili su fonti pubbliche sono marcate come tali e non sono trattate come
condizioni soddisfatte.

**Provenienza:** questo documento non e un tracker di stato della roadmap. La
teoria approvata dal PO il 2026-07-15 vive in
`docs/strategies/s2-vrp-theory.md`; questo studio applica i suoi gate senza
modificarne soglie o parametri.

## 1. Executive verdict

**NO-GO.** Nessun candidato dimostra contemporaneamente esposizione al
seller-sign SPX variance risk premium, perdita massima contrattualmente finita,
liquidita verificata e rispetto dei limiti PO-19.

Il disqualifier determinante e il bounded loss, non la dimensione della sleeve:

- Il Cboe S&P 500 Variance Future corrente (CFE `VA`) e listato, cash-settled,
  centrally cleared e puro rispetto alla varianza realizzata. Il lato **long** ha
  perdita limitata dal floor naturale della varianza a zero, ma compra
  assicurazione ed espone al segno opposto rispetto al premio seller-sign
  approvato. Il lato **short**, necessario per raccogliere quel premio, ha perdita
  teoricamente illimitata perche il final settlement non ha un cap superiore.
- Una strip SPX short che approssima la varianza eredita la coda short delle
  opzioni. L'acquisto di ali rende finita la perdita, ma tronca proprio la coda che
  contribuisce alla replica della varianza. Senza una struttura completa, quote
  eseguibili e un worksheet per tutte le gambe non e dimostrato che purezza,
  materialita economica e limiti di capitale coesistano.
- Il portafoglio SPX delta-hedged e una approssimazione secondaria con rischio di
  salto e hedge discreto; non ripara il conflitto fra purezza e perdita finita.

Il `CONDITIONAL GO` della prima versione era quindi errato. In particolare, il
sizing non rende bounded una perdita senza cap: per ogni numero positivo di
contratti short VA il massimo contrattuale rimane infinito. La PO-19 prescrive
esplicitamente `NO-GO` quando purezza, liquidita e bounded loss non coesistono.

## 2. Domanda 1 - Cboe S&P 500 Variance Futures (candidato #1)

### 2.1 Contratto corrente e convenzione delle unita

Questo studio usa solo il prodotto rilanciato da Cboe nel 2024. La FAQ distingue
esplicitamente il contratto corrente dal precedente: il vecchio prodotto negoziava
in volatility/vega units e veniva poi ristabilito in variance units; il nuovo
contratto quota, negozia e viene compensato direttamente in variance units.
Le scale non sono intercambiabili: nella prima versione il mix ha prodotto errori
di fattore 10 nello stress e 100 nell'esempio di settlement.

Le specifiche correnti sono:

- **Ticker e venue:** `VA`, Cboe Futures Exchange (CFE).
- **Sottostante:** varianza realizzata annualizzata dello S&P 500, calcolata sui
  log-return giornalieri fra la data di listing e la scadenza, con media giornaliera
  assunta pari a zero e annualizzazione a 252 sedute.
- **Scadenze:** allineate alle opzioni SPX mensili standard AM-settled attive. Il
  final settlement usa la SOQ dello SPX il terzo venerdi del mese.
- **Contract size:** un contratto equivale a una variance unit.
- **Quotazione:** variance points con due decimali.
- **Contract multiplier:** `$1.00 per variance point`.
- **Tick minimo:** `0.50` variance points, cioe `$0.50` per contratto.
- **Settlement e clearing:** cash settlement, trading su CFE e clearing OCC.
- **Microstruttura prevista:** block trades ed ECRP ammessi; TAS e spread
  instruments nativi non ammessi; e previsto un Lead Market Maker.

Fonti primarie: Cboe FAQ e fact sheet nelle fonti [1]-[3].

### 2.2 Esempio normalizzato e payoff

Per passare dalla varianza decimale ai variance points si usa:

`variance_points = 10,000 * sigma^2`

Quindi volatilita annualizzata `20%` significa varianza decimale `0.04`, cioe
`400 variance points`, e l'equivalente monetario del settlement e
`400 * $1 = $400`. Non e `$40,000` e non e `$40`. Trattandosi di un future,
questo valore non e un premio anticipato: il guadagno o la perdita maturano tramite
variation margin.

Se un contratto viene comprato a `300` variance points e scade a `400`, il P&L
lordo del long e `(400 - 300) * $1 = +$100`; il P&L dello short e `-$100`.
Indicando con `K` il prezzo d'ingresso e con `RVp` il final settlement in variance
points:

- `PnL_long = (RVp - K) * $1`;
- `PnL_short = (K - RVp) * $1`.

Poiche `RVp >= 0`, il long aperto a un `K` positivo perde al massimo `K * $1` per
contratto. Non esiste invece un cap superiore contrattuale per `RVp`: lo short
puo perdere senza limite. Un'uscita discrezionale o uno stop-loss non trasformano
questo payoff in bounded loss e sono vietati come sostituto del cap dalla issue.

### 2.3 Liquidita

La pagina Cboe dei settlement giornalieri mostra scadenze VA attive e prezzi
pubblicati. Questo prova listing e price discovery, non prova profondita o
eseguibilita. La FAQ conferma LMM, block trades ed ECRP, ma non fornisce una serie
di ADV, open interest e bid/ask sufficiente al gate richiesto.

Per dichiarare la liquidita verificata servirebbero almeno ADV e open interest per
scadenza, bid/ask con size e frequenza di quote two-sided, inclusi giorni di stress.
Queste misure non sono state raccolte e il documento non inferisce illiquidita o
liquidita dalla sola presenza di settlement prices.

### 2.4 Accesso IBKR, margin e costi

Le pagine pubbliche IBKR confermano accesso generale a futures e marginazione
risk-based, con requisiti che possono cambiare e condizioni dipendenti da
residenza, account ed exchange. Non e stata trovata una pagina primaria IBKR che
identifichi specificamente il nuovo `VA`, il suo contract identifier, le
permission per clientela italiana, il market-data package e i margin correnti.

Di conseguenza l'accesso IBKR a `VA` e **non verificato**, non `SI`. Vanno richiesti
per iscritto a IBKR:

1. contract identifier e scadenze effettivamente negoziabili;
2. eligibility del tipo di conto e della residenza italiana;
3. initial, maintenance e stressed margin per long e short;
4. market-data subscription, commissioni ed exchange/clearing fees.

La FAQ Cboe descrive solo i minimi al lancio e avverte che OCC e broker possono
modificarli o aumentarli. Non supporta la cifra `$2,500` usata nella prima versione;
quella cifra e rimossa dal worksheet.

## 3. Domanda 2 - SPX option-strip replication (candidato #2)

### 3.1 Strumento e replica 30 giorni

Le opzioni SPX sono cash-settled, European-style e hanno multiplier `$100`.
Le serie standard sono AM-settled; SPXW include scadenze PM-settled. La metodologia
Cboe VIX costruisce una misura a 30 giorni da opzioni SPX/SPXW su due scadenze che
racchiudono l'orizzonte, usando put e call OTM su piu strike e interpolazione di
maturity. E una base primaria per definire campi e pesi della strip, non una prova
che la strip possa essere eseguita ai midpoint o con perdita finita.

La replica investibile richiede:

- quote bid/ask e size sincronizzate su tutte le gambe;
- forward, tasso, settlement convention e pesi per strike;
- gestione di strike discreti, zero-bid exclusion e truncation;
- costi di esecuzione multi-leg, funding e roll;
- delta hedge e relativa frequenza;
- ali acquistate per imporre una perdita massima contrattuale.

Una strip short non protetta contiene short call e short put. Le ali protettive
convertono le gambe in spread e rendono finita la perdita, ma oltre gli strike
protettivi il payoff non segue piu la varianza. Spostare le ali piu lontano migliora
l'approssimazione e contemporaneamente aumenta il massimo loss. Senza quote reali
non esiste un punto dimostrato che rispetti sia `max loss <= 2% NAV` sia
`stressed margin <= 50% sleeve capital` restando economicamente materiale.

### 3.2 Accesso broker

Il commento dell'operatore del 2026-07-23 richiedeva di verificare il nuovo supporto
Alpaca. Al 2026-08-17:

- la documentazione pubblica Alpaca sulle opzioni descrive equity/ETF options;
- la pagina prodotto dichiara index options `coming soon`;
- un dipendente Alpaca ha confermato sul forum ufficiale che SPX, SPXW, XSP, DJX,
  VIX e VIXW sono disponibili in paper per retail, mentre il live retail non ha una
  data pubblica.

Quindi Alpaca retail non costituisce accesso live verificato. Anche permission,
market data e limitazioni IBKR per il conto italiano Alembic richiedono conferma
specifica. In ogni caso il broker non risolve il disqualifier economico del payoff.

### 3.3 Esito candidato #2

Il candidato e tecnicamente costruibile come portafoglio listed/cleared e puo essere
reso defined-loss con ali. Non supera pero il gate di questa feasibility: non e
stato costruito un payoff che dimostri simultaneamente fedelta alla varianza 30d,
max loss al 2% NAV, stressed margin al 50% della sleeve ed esecuzione su quote
reali. Definirlo `GO` sulla base di un generico credit spread sostituirebbe il
payoff approvato con una strategia diversa.

## 4. Domanda 3 - rischi residui

| Rischio | VA short | Strip SPX short con ali |
|---|---|---|
| Basis | Contratto nativo sulla RV dalla data di listing, non una serie constant-30d | Discretizzazione, interpolazione e truncation |
| Jump/tail | Entra direttamente nella RV; perdita short senza cap | Le ali limitano la perdita ma troncano la replica |
| Settlement | SOQ SPX e calendario AM mensile | Mix AM/PM se si combinano SPX e SPXW |
| Roll | Le scadenze VA non formano da sole un'esposizione costante a 30 giorni | Richiede roll fra due maturita e ribilanciamento dei pesi |
| Convexity | Lineare in variance points, non in volatilita | Gamma, vega e skew dipendono da strike e hedge |
| Liquidita | ADV, OI e bid/ask non verificati | SPX aggregato liquido, ma serve prova sulle ali e sulle size della strip |
| Hedge | Nessun delta hedge per il future puro | Delta hedge discreto, con gap e costi residui |
| Margin | Corrente IBKR non verificato; non e un cap al loss | Dipende dall'intero portafoglio e dalle ali |
| Counterparty | Clearing OCC, rischio trasferito alla CCP | Clearing OCC, rischio trasferito alla CCP |

Il candidato #3, portafoglio SPX delta-hedged senza una replica esplicita, aggiunge
errore di hedge, gamma e jump. Rimane un'approssimazione secondaria e non soddisfa
il gate di purezza come via alternativa.

## 5. Domanda 4 - vendor matrix SPX PIT 1996-oggi

Il requisito storico puo essere coperto solo da una sorgente che conservi la catena
SPX point-in-time con bid/ask. Le cifre non pubblicate non sono stimate.

| Vendor/prodotto | Copertura pubblicamente documentata | Campi utili pubblicati | Copre 1996-oggi? | Prezzo/licenza |
|---|---|---|---|---|
| OptionMetrics IvyDB US | Gennaio 1996-oggi, EOD, equity e index options | closing bid/ask, volume, OI, underlying, tassi, permanent ID, IV/Greeks | **Si**, da validare su SPX e date campione | Quote e licenza da richiedere |
| Cboe DataShop MDR Quotes and Trades | `^SPX` da gennaio 1990; storia varia per simbolo | timestamp, expiry, put/call, strike, bid/ask, size, trade e underlying | **Si**, con verifica dei cambi timezone/schema | Prezzo calcolato dal portale; licenza da verificare |
| Cboe Option EOD Summary | Gennaio 2012-oggi | due snapshot NBBO, size, OHLC, volume, VWAP, OI | **No** da solo | Acquisto DataShop; indici/licenze separati |
| ORATS Near-EOD/API | 2007-oggi | quote, greeks e surface EOD/near-EOD | **No** da solo | Pricing pubblico/quote; licenza da verificare |

Massive/Polygon, Bloomberg, Refinitiv e LiveVol non sono promossi a candidati
completi senza una fonte primaria pubblica che dimostri contemporaneamente
copertura SPX dal 1996, quote eseguibili, identificatori e licenza compatibile. La
prima versione riportava costi di settore non riconducibili a quote: sono rimossi.

### 5.1 Quote/data contract

Ogni osservazione usata per la validazione deve portare:

- `option_root`, `expiry_date`, `strike`, `put_call_flag`, `contract_id`;
- `quote_timestamp`, `quote_timezone`, sessione ed exchange/NBBO source;
- `bid`, `ask`, `bid_size`, `ask_size`, `midpoint`, `stale_quote_flag`;
- `underlying_spx_level`, forward, `risk_free_rate_input`, dividend input;
- `settlement_type`, `tradable_indicator` e motivo di esclusione;
- `vendor_name`, versione schema, `license_boundary`, `retrieval_date`.

Prima di un eventuale nuovo studio, una prova vendor dovrebbe controllare almeno
2008-10-15, 2018-02-05, 2020-03-16 e 2022-09-13, piu un mese completo, verificando
catena integra, timestamp, bid/ask non stale e assenza di look-ahead. Questa
feasibility non autorizza ne l'acquisto ne la prova.

## 6. Domanda 5 - bounded loss e stressed margin

### 6.1 Vincoli approvati

- perdita massima contrattuale `<= 2%` del NAV Alembic;
- stressed margin `<= 50%` del capitale della sleeve;
- uno stop-loss o l'intenzione di chiudere prima della scadenza non valgono come
  bounded loss.

### 6.2 Worksheet VA

| Voce | Long VA | Short VA (segno seller-VRP) |
|---|---:|---:|
| P&L a scadenza | `(RVp - K) * $1 * N` | `(K - RVp) * $1 * N` |
| `RVp` minimo | `0` | `0` |
| `RVp` massimo contrattuale | nessuno | nessuno |
| Max loss per `K > 0` | `K * $1 * N` | **illimitata** |
| Rispetta il cap 2% tramite sizing? | verificabile dato NAV e `K` | **no, per ogni `N > 0`** |

Esempi di unita, un contratto:

- da varianza decimale `0.04` a `0.09`: da `400` a `900` variance points;
  P&L long `+$500`, short `-$500`;
- da volatilita `20%` a `25%`: da `400` a `625` variance points;
  P&L long `+$225`, short `-$225`.

Il secondo esempio e uno shock di **5 volatility points**, non di `0.05` variance
decimale. La prima versione li aveva equiparati e aveva applicato un multiplier
obsoleto da `$1,000`, sovrastimando di 10 volte lo stress `0.04 -> 0.09`. Lo stesso
mix di unita sovrastimava di 100 volte l'esempio di settlement a varianza `0.04`.

Il margin corrente IBKR non e pubblicamente verificato per questo contratto, quindi
il rapporto di stressed margin non viene inventato. Anche se risultasse sotto il
50% in uno scenario scelto, non imporrebbe un cap al payoff short e non sanerebbe
il primo vincolo.

### 6.3 Worksheet strip SPX

Per una singola credit spread, il max loss e
`(ampiezza strike * $100) - credito netto`, ma una replica e un portafoglio di molte
gambe e maturita: il max loss va calcolato sul payoff aggregato, includendo overlap,
ali, costi e hedge. Senza strikes, quantita e premi eseguibili non esiste un numero
difendibile per max loss o stressed margin.

La conclusione non e che servano `$50,000`: quella soglia derivava dai calcoli
sbagliati. La conclusione e che VA short fallisce il bounded loss per costruzione e
che la strip bounded non ha ancora dimostrato di conservare il target entro i due
capitali approvati.

## 7. Domanda 6 - accesso e vincoli operativi

| Elemento | VA | SPX/SPXW/XSP |
|---|---|---|
| Venue | CFE | Cboe Options |
| Permission | Futures; conferma IBKR specifica mancante | Options; livello e residenza da confermare |
| Market data | CFE feed/package da confermare | OPRA/Cboe package da confermare |
| Symbol | `VA` su CFE; contract ID broker da confermare | `SPX`, `SPXW`, `XSP` |
| Ordini necessari | almeno limit; block/ECRP lato venue | multi-leg limit/RFQ da verificare sul conto |
| Margin | risk-based e variabile; cifra specifica non verificata | dipende da struttura, account e portfolio margin |
| Alpaca retail live | futures non supportati nel perimetro corrente | index options non verificate live al 2026-08-17 |

L'assenza di una conferma specifica IBKR impedisce di dichiarare broker access
verificato per VA. Una conferma futura non cambierebbe il NO-GO sul payoff short.

## 8. Domanda 7 - verdict formale

| Condizione hard | VA short | Strip SPX bounded | Esito |
|---|---|---|---|
| Listed/cleared | Si | Si | non bloccante |
| Esposizione seller-sign alla varianza | Si | Parziale, dipende dalla truncation | non sufficiente |
| Perdita massima contrattuale finita | **No** | Si solo con ali | bloccante |
| Max loss `<= 2% NAV` | **No per ogni size positiva** | non dimostrato senza struttura/quote | bloccante |
| Stressed margin `<= 50% sleeve` | non verificato | non dimostrato | bloccante |
| Liquidita eseguibile | non verificata | non verificata sull'intera strip | bloccante |
| Broker access verificato | non verificato specificamente | Alpaca retail live no; IBKR da confermare | bloccante operativo |

**Verdetto: NO-GO.** Il candidato piu puro, VA short, viola direttamente il
bounded-loss gate. Il candidato che puo essere bounded, la strip con ali, non ha
dimostrato di mantenere il target e i cap di capitale su quote eseguibili. In base
alla decisione PO gia approvata non e consentito sostituirli con short put, VIX
products, long SPY o un'altra proxy.

Questo NO-GO chiude la domanda di fattibilita corrente. Non significa che nessuna
struttura bounded potra mai essere studiata; significa che servirebbe una nuova
tesi esplicita, con payoff troncato approvato e un nuovo gate, invece di chiamarla
equivalente alla strategia qui autorizzata.

## 9. Fonti primarie e limiti

1. **Cboe S&P 500 Variance Futures FAQ.**
   `https://cdn.cboe.com/resources/participant_resources/Cboe_Variance_Futures_FAQ.pdf`
   - differenza fra vecchio e nuovo contratto, variance units, multiplier, tick,
     settlement, LMM, block/ECRP, margin al lancio.
2. **Cboe VA fact sheet e contract specifications.**
   `https://cdn.cboe.com/resources/participant_resources/SP-500_Variance_Futures_Fact_Sheet.pdf`
   e `https://cdn.cboe.com/resources/participant_resources/SP_500_Variance_Futures.pdf`
   - formula, annualizzazione, SOQ, scadenza e specifiche correnti.
3. **Cboe VA product page.**
   `https://www.cboe.com/tradable-products/sp-500/variance-futures/`
   - listing CFE, clearing OCC e risorse del prodotto.
4. **Cboe daily futures settlement prices.**
   `https://www.cboe.com/markets/us/futures/market-statistics/settlement/futures/daily/`
   - contratti VA attivi e settlement; non e prova di liquidita.
5. **Cboe SPX specifications.**
   `https://www.cboe.com/tradable-products/sp-500/spx-options/spx-specifications`
   - multiplier, orari e settlement SPX/SPXW.
6. **Cboe Volatility Index Methodology.**
   `https://cdn.cboe.com/api/global/us_indices/governance/VIX_Methodology.pdf`
   - maturita 30 giorni, selezione SPX/SPXW, strike e market data.
7. **IBKR Futures & FOPs Margin Requirements.**
   `https://www.interactivebrokers.com/en/trading/margin-futures-fops.php`
   - regole generali risk-based; non verifica VA specificamente.
8. **Alpaca options docs e product page.**
   `https://docs.alpaca.markets/docs/options-trading` e
   `https://alpaca.markets/options`
   - perimetro pubblico equity/ETF e index options `coming soon`.
9. **Alpaca Community Forum, risposta staff.**
   `https://forum.alpaca.markets/t/when-will-you-support-index-options/16411`
   - paper retail e stato live retail; e una risposta operativa ufficiale, non una
     contract specification.
10. **OptionMetrics IvyDB US.** `https://optionmetrics.com/united-states/`
    - copertura da gennaio 1996 e campi EOD.
11. **Cboe DataShop MDR Quotes and Trades.**
    `https://datashop.cboe.com/mdr-quotes-trades-data`
    - copertura SPX dal 1990, schema quote/trade e timezone.
12. **Cboe Option EOD Summary.** `https://datashop.cboe.com/option-eod-summary`
    - copertura dal 2012 e campi NBBO.
13. **ORATS Near-EOD/API.** `https://orats.com/near-eod-data`
    - copertura dal 2007.

Le fonti pubbliche non bastano per dichiarare permission IBKR, margin broker,
commissioni, profondita VA o costo/licenza vendor. Il documento conserva questi
punti come non verificati invece di completarli con stime secondarie.

## 10. Conferme esterne che sarebbero necessarie per una nuova tesi

Il NO-GO corrente non richiede acquisti. Solo se il PO autorizza una nuova tesi su
un payoff bounded e troncato avrebbero senso:

1. conferma scritta IBKR su VA e SPX/SPXW/XSP per il conto italiano;
2. export Cboe/IBKR di ADV, OI, bid/ask e size VA;
3. quote OptionMetrics e Cboe DataShop con campioni prima dell'acquisto;
4. specifica completa della strip bounded, con strikes, pesi, ali e hedge;
5. worksheet su quote eseguibili per max loss e stressed margin.

Finche il PO non apre quel nuovo perimetro, non va acquistato nulla e non va aperto
un conto in funzione di S2.

## 11. Decisione PO richiesta

La decisione conseguente a questo studio e una sola:

- **accettare il NO-GO e fermare il design S2 corrente**; oppure
- aprire una nuova issue/tesi che autorizzi esplicitamente un payoff troncato e ne
  definisca il massimo scostamento ammissibile dalla varianza pura.

Broker, sleeve e vendor non sono decisioni da prendere dentro #57: con il gate
contrattuale fallito sarebbero spesa e operativita premature.

## 12. Cosa non e stato fatto

- Nessun acquisto dati, subscription o richiesta commerciale.
- Nessuna apertura conto o modifica di permission.
- Nessun test paper/live e nessun ordine, neppure simulato.
- Nessun backtest interno usato come evidenza.
- Nessuna modifica a soglie, pesi, flag, cooldown o parametri di strategia durante
  il freeze #171.
- Nessuna sostituzione con proxy economicamente diverse.

## 13. Relazione con la roadmap

Il deliverable richiesto da #57 e completo con un esito ammesso dai criteri di
accettazione: quando una hard condition fallisce, `NO-GO` e il risultato, non una
richiesta implicita di allargare il perimetro. Eventuale ricerca su una strip
troncata appartiene a una nuova decisione PO e non resta come sotto-task nascosta
di questa issue.

## 14. Sintesi in pochi minuti

Il contratto VA corrente e molto piu piccolo di quanto riportava la prima versione:
quota direttamente in variance points, con multiplier `$1` e tick `$0.50`. A 20%
di volatilita, `0.04` di varianza decimale equivale a `400` variance points e
`$400` per contratto.

Questa correzione non salva il candidato. Il long VA ha perdita finita ma compra
varianza; lo short VA cattura il seller-sign VRP ma ha perdita senza cap. Il sizing
riduce lo stress scelto, non rende finito il massimo contrattuale. Una strip SPX
con ali puo limitare il loss, ma modifica le code del payoff e non e stata
dimostrata entro i cap PO-19 su quote eseguibili.

Il verdetto corretto e quindi **NO-GO**. Non sono richiesti acquisti o azioni
operative; un seguito richiede una nuova tesi approvata dal PO.
