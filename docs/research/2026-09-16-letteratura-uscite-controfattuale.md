# Letteratura sulle uscite sotto vincolo di capitale — ricerca pre-registrata

**Data:** 2026-09-16 · **Issue:** #614

Questa è una **ricerca pre-registrata**. Il perimetro, le cinque domande, la regola
anti-selezione e la barra di qualità sono fissati in
[`docs/evidence/PREREGISTRAZIONE_DISEGNO_CONTROFATTUALE_USCITE_2026-09-16.md`](../evidence/PREREGISTRAZIONE_DISEGNO_CONTROFATTUALE_USCITE_2026-09-16.md)
§5, scritto **prima** di qualunque ricerca bibliografica. La lista delle domande è chiusa:
qui non se ne aggiungono.

Il documento **non** esegue alcuna misura e **non** propone modifiche al path live. Cadenza
di ribilanciamento, stop e orizzonti sono **taratura**, e la taratura è congelata fino al
2026-09-28 (`docs/evidence/OBSERVATION_CHARTER.md` § «Cosa è congelato»: «Tutta la
**taratura**: soglie, pesi, flag, cooldown, parametri di strategia»). L'unica esenzione
prevista dal charter è il **difetto di correttezza** («Se non lo correggo, l'evidenza che
raccolgo nelle prossime settimane è sbagliata?»), e nulla di quanto segue la invoca.

## Il problema, in tre numeri

Nella finestra osservata il ribilanciatore (`portfolio_sell`) produce **63 uscite su 114** e
**−$447,81 su −$463,93** di perdita realizzata (il 97%). La detenzione mediana è **0,7
giorni**. Gli stop-loss non sono mai scattati. Il capitale è finito: tenere X significa non
comprare Y.

## Metodo e regole applicate

- **Regola anti-selezione.** Il manifest in fondo elenca **tutte** le fonti aperte, incluse
  quelle risultate inutili, irrecuperabili o contrarie all'ipotesi. Nessuna è stata rimossa
  dopo la lettura.
- **Barra di qualità.** Solo peer-reviewed, working paper di istituzioni riconoscibili
  (NBER, Federal Reserve Bank of Philadelphia, business school) o documentazione ufficiale
  (CFA Institute / GIPS). Nessun blog e nessun materiale di vendor è usato come evidenza.
- **Verifica bibliografica.** Ogni citazione è stata verificata contro l'API Crossref
  (autori, titolo, rivista, anno, volume, fascicolo, pagine). L'output grezzo della verifica
  è in [`2026-09-16-uscite-source-cache/VERIFICA-CROSSREF.txt`](2026-09-16-uscite-source-cache/VERIFICA-CROSSREF.txt).
- **Cache del testo.** Il testo grezzo di ogni fonte da cui è tratta anche una sola
  affermazione è salvato in [`2026-09-16-uscite-source-cache/`](2026-09-16-uscite-source-cache/),
  un file per `id`. Dove è stato possibile recuperare solo il record bibliografico, il file
  lo dice in testa e l'esito nel manifest è marcato di conseguenza.
- **Citazioni testuali.** Ogni affermazione attribuita a una fonte porta la citazione
  testuale esatta fra virgolette con l'`id`. Dove non è stato possibile estrarre testo,
  l'affermazione è marcata `SENZA_CITAZIONE_TESTUALE` e non viene usata come evidenza.
- **Ruolo delle domande.** Come dichiarato in pre-registrazione, **Q1–Q3 sono vincoli di
  disegno**, **Q4 e Q5 sono prior utilizzabili** (letteratura replicata e poco soggetta ad
  arbitraggio).

---

## Q1 — Benchmark corretto sotto vincolo di capitale e trattamento del displacement

### Cosa dice la letteratura

**1. Il costo dell'operazione che non avviene è un costo, e la letteratura sui costi di
transazione lo dice esplicitamente.** Wagner & Edwards (1993) elencano l'opportunity cost
come quarta e più insidiosa componente del costo di esecuzione:

> «opportunity cost-the portfolio performance forgone because a trade cannot be made. These
> costs are likely to overwhelm the simple commission charge.» — `Q1-WAGNER-EDWARDS`

> «(4) Opportunity Cost: The cost of failing to find the liquidity to complete the trade. We
> define opportunity cost as the price change on unexecuted shares from the time of
> submission to the trade desk until cancellation or until four days after the last» —
> `Q1-WAGNER-EDWARDS`

**Nota di verificabilità su queste due citazioni.** Il PDF di Wagner & Edwards ha un layer
OCR su tre colonne: `pdftotext` restituisce le righe delle tre colonne interlacciate, quindi
nessuna frase del corpo è contigua nel file di cache. Le due citazioni sopra sono **ricomposte
leggendo una sola colonna**, e la ricomposizione — con i numeri di riga sorgente — è in coda a
`Q1-WAGNER-EDWARDS.txt`, sotto l'intestazione «APPENDICE — RICOMPOSIZIONE DELLE COLONNE». La
seconda citazione risulta inoltre troncata a fine colonna nell'OCR: l'ultima parola leggibile
è «last». La terza citazione qui sotto è invece contigua nell'originale.

> «In the absence of either, timing and opportunity costs occur. Most trade cost studies
> ignore these costs.» — `Q1-WAGNER-EDWARDS`

**Attenzione al salto logico.** L'opportunity cost di Wagner & Edwards è il costo di un
ordine che *non trova liquidità*. Il nostro displacement è il costo di un acquisto che *non
trova capitale*. Sono due vincoli diversi che generano la stessa struttura contabile — una
gamba mancante del confronto — ma la letteratura che ho letto non tratta il secondo caso.
Vedi «Buchi dichiarati».

**2. Il framing «paper portfolio contro portafoglio reale» è di Perold (1988).** Questa è la
citazione canonica per l'artefatto 1 della pre-registrazione. **Non ho potuto leggerne il
testo**: l'articolo è dietro paywall su pm-research.com e Crossref non espone alcun abstract
per il DOI. `SENZA_CITAZIONE_TESTUALE`. Dettagli bibliografici verificati: Perold, A.F., «The
implementation shortfall», *The Journal of Portfolio Management* 14(3):4–9, 1988
(`Q1-PEROLD`, `VERIFICA-CROSSREF`). Il contenuto dell'articolo **non** è usato come evidenza
in questo documento.

**3. La letteratura ha una risposta diretta alla domanda «il ribilanciatore vende troppo
presto?», ed è una risposta di disegno, non di calendario.** Novy-Marx & Velikov (2016)
confrontano diverse tecniche di mitigazione del costo su un ampio insieme di anomalie:

> «introducing a buy/hold spread, which allows investors to continue to hold stocks that
> they would not actively trade into, is the single most effective simple cost mitigation
> strategy» — `Q1-NOVYMARX-VELIKOV`

La regola è una soglia asimmetrica fra comprare e tenere (regola sS, zona di inazione):

> «These strategies follow an sS rule, under which a trader will hold (maintain short
> positions on) stocks that they own (are short) provided that the sorting variable is in
> the extreme s%, but will only actively buy (short) a stock that they have no position in
> when it enters the most extreme S%.» — `Q1-NOVYMARX-VELIKOV`

E — questo è il punto che riguarda direttamente il displacement — **la ragione per cui
funziona è che il sostituto Y ha un rendimento atteso quasi identico a X**:

> «The procedure dramatically reduces turnover by holding (not selling) close substitutes to
> the stocks you would have bought, since there is not much of a difference in expected
> returns between stocks in the 75-80% range of the distribution of a given return predictor
> and those in the 80-85% range.» — `Q1-NOVYMARX-VELIKOV`

Sul turnover, il verdetto è quantitativo e ci riguarda:

> «Most of the anomalies that we consider with one-sided monthly turnover lower than 50%
> continue to generate statistically significant net spreads, at least when designed to
> mitigate transaction costs. Few of the strategies with higher turnover do.» —
> `Q1-NOVYMARX-VELIKOV`

Con detenzione mediana di 0,7 giorni il nostro turnover è di ordini di grandezza sopra la
soglia del 50% mensile citata.

**4. Sotto costi di transazione l'ottimo non è «tenere di più», è «muoversi di meno verso il
bersaglio».** Gârleanu & Pedersen (2013):

> «The optimal strategy is characterized by two principles: 1) aim in front of the target
> and 2) trade partially towards the current aim.» — `Q1-GARLEANU-PEDERSEN`

> «Due to transaction costs, it is obviously not optimal to trade all the way to the target
> all the time.» — `Q1-GARLEANU-PEDERSEN`

> «predictors with slower mean reversion (alpha decay) get more weight in the aim
> portfolio» — `Q1-GARLEANU-PEDERSEN`

L'ultima frase collega Q1 a Q5: la velocità di decadimento del segnale è un *input* della
regola di uscita ottimale, non un parametro indipendente.

**5. Il vincolo di capitale, nella letteratura, appare soprattutto come vincolo di
capacità/impatto, non come crowd-out di budget.** Korajczyk & Sadka (2004):

> «The price impact models imply that abnormal returns to portfolio strategies decline with
> portfolio size.» — `Q1-KORAJCZYK-SADKA`

È un vincolo diverso dal nostro (il nostro book è microscopico e non muove i prezzi). Lo
registro come **parzialmente pertinente**: conferma che «capitale finito» va modellato, ma
il canale è un altro.

### Raccomandazione operativa — Q1

**Sostenuto dalla letteratura:**

1. Il confronto «tenuto X contro venduto X e cash» è il paper portfolio di Perold ed è
   sbagliato per costruzione; il costo dell'operazione impedita è un costo reale
   (`Q1-WAGNER-EDWARDS`). Il replay di portafoglio a budget vincolato già fissato in
   pre-registrazione §3 è la risposta corretta: **confermare quella scelta, non rivederla**.
2. Il sostituto Y non va trattato come un'incognita da modellare: è noto, ed è ciò che il
   sistema ha effettivamente comprato quel giorno. Novy-Marx & Velikov danno anche la
   ragione teorica per cui il confronto è quasi-neutrale — i rendimenti attesi di X e Y sono
   vicini (`Q1-NOVYMARX-VELIKOV`) — il che implica che **il grosso della differenza fra i
   rami sarà costo di transazione, non alpha**. Questa è una predizione falsificabile da
   dichiarare *prima* di vedere i numeri.
3. Il turnover attuale è ben oltre la soglia sotto cui, in letteratura, un'anomalia
   sopravvive ai costi (`Q1-NOVYMARX-VELIKOV`).

**Mia inferenza, non della letteratura:**

4. L'asse del controfattuale scelto in pre-registrazione — «N sedute in più», con N in
   {1,2,5,10,21} — **non è l'asse che la letteratura indica**. La letteratura indica una
   soglia asimmetrica compra/tieni (regola sS, `Q1-NOVYMARX-VELIKOV`) o un tasso di
   avvicinamento parziale al bersaglio (`Q1-GARLEANU-PEDERSEN`). Un'estensione a calendario
   è un'approssimazione grossolana di entrambe: agisce sul tempo invece che sulla forza del
   segnale, e quindi tiene anche le posizioni che il ranker ha giustamente declassato.
5. Conseguenza operativa: la griglia a calendario **resta come pre-registrata** (cambiarla
   ora sarebbe esattamente il «scegliere la variante migliore dopo averla vista» che la
   pre-registrazione vieta), ma un **braccio sS** va aggiunto dichiarandolo esplicitamente
   come emerso dopo la ricerca — la pre-registrazione §2 lo prevede: «Se dopo la ricerca ne
   emergessero altri, si aggiungono e si annota che sono emersi dopo». In alternativa, una
   pre-registrazione separata.

---

## Q2 — Normalizzazione per capitale-tempo con durate diverse fra i rami

### Cosa dice la letteratura

**1. La costruzione canonica esiste dal 1993 ed è a coorti sovrapposte con 1/K di capitale
ciascuna.** Jegadeesh & Titman risolvono esattamente il problema «orizzonti diversi, stesso
capitale»:

> «To increase the power of our tests, the strategies we examine include portfolios with
> overlapping holding periods. Therefore, in any given month t, the strategies hold a series
> of portfolios that are selected in the current month as well as in the previous K - 1
> months, where K is the holding period.» — `Q23-JEGADEESH-TITMAN`

> «Hence, under this trading strategy we revise the weights on [1/K] of the securities in
> the entire portfolio in any given month and carry over the rest from the previous month.»
> — `Q23-JEGADEESH-TITMAN`
>
> Nel layer OCR del PDF la frazione 1/K è disarticolata: l'estrazione produce letteralmente
> «Hence, under this trading strategy we / [a capo] 1 / [a capo] revise the weights on - of
> the securities in the entire portfolio in any given month and carry over the rest from the
> previous month.», con il numeratore «1» su una riga a sé e il denominatore perduto. Il
> `[1/K]` fra parentesi quadre nella citazione è quindi una **mia ricostruzione**, non testo
> dell'originale; il resto della frase è letterale.

Il capitale impiegato è quindi **invariante rispetto a K** per costruzione: è questa la
normalizzazione capitale-tempo, e non un aggiustamento *ex post* del P&L.

**2. Il time-weighted return è progettato per neutralizzare proprio ciò che vogliamo
misurare.** Il GIPS lo dichiara apertamente:

> «The GIPS standards require a time-weighted rate of return because it removes the effects
> of external cash flows, which are generally client-driven. Therefore, a time-weighted rate
> of return best reflects the firm's ability to manage the portfolios according to a
> specified mandate, objective, or strategy» — `Q2-GIPS-CALC`

**3. E il GIPS 2020 dice in quali condizioni il money-weighted è invece la metrica
ammessa** — condizioni che il nostro conto paper soddisfa:

> «The firm must present time-weighted returns unless certain criteria are met, in which
> case the firm may present money-weighted returns. The firm may present money-weighted
> returns only if the firm has control over the external cash flows into the portfolios in
> the composite or pooled fund and the portfolios in the composite have or the pooled fund
> has at least one of the following characteristics: a. Closed-end b. Fixed life c. Fixed
> commitment d. Illiquid investments as a significant part of the investment strategy.» —
> `Q2-GIPS-2020` (requisito 1.A.35)

Il nostro book ha controllo totale sui flussi esterni (non ce ne sono) e capitale a impegno
fisso: è il caso *closed-end / fixed commitment*.

**4. Il portafoglio in calendar time è il veicolo che risolve insieme normalizzazione e
inferenza.** Fama (1998), a proposito di eventi sovrapposti:

> «In contrast, if average monthly returns are used, there has long been a full solution to
> the cross-correlation problem. […] Then average the abnormal returns for the calendar
> month across stocks to get the abnormal return for the month on the portfolio of stocks
> with an event in the last five years. Re-form the portfolio every month.» — `Q23-FAMA1998`

### Raccomandazione operativa — Q2

**Sostenuto dalla letteratura:**

1. **Il time-weighted return non va usato come metrica principale del confronto.** Il GIPS è
   esplicito sul fatto che il TWR esiste per rimuovere gli effetti della tempistica dei
   flussi di capitale (`Q2-GIPS-CALC`), che è precisamente la dimensione oggetto del
   controfattuale. La metrica ammissibile per un pool a capitale fisso con controllo pieno
   sui flussi è quella money-weighted (`Q2-GIPS-2020`, 1.A.35).
2. L'equity terminale del book replayato — già fissata dalla pre-registrazione §3 — **è** una
   misura money-weighted e non ha bisogno di correzioni di durata: il vincolo di budget
   svolge la normalizzazione per costruzione. **Confermare, non emendare.**
3. Se in aggiunta si vuole un confronto *per orizzonte*, la forma corretta è la costruzione a
   coorti sovrapposte di Jegadeesh & Titman: N coorti da 1/N del capitale ciascuna, così che
   il capitale impiegato sia identico in tutti i rami (`Q23-JEGADEESH-TITMAN`).

**Mia inferenza, non della letteratura:**

4. Con capitale fisso, un ramo «tieni di più» può semplicemente **non riuscire a schierare**
   tutto il capitale, e a quel punto l'equity terminale confronta due cose diverse. Vanno
   quindi pubblicati, per ogni ramo, anche il **capitale medio impiegato** e il **cash drag**:
   senza questi due numeri l'equity terminale è ambigua. Nessuna fonte letta prescrive questo;
   è una conseguenza diretta del vincolo di budget.
5. Il P&L per-trade non va pubblicato come titolo, in nessuna forma. È l'artefatto 3 della
   pre-registrazione e nessuna delle fonti lette lo sostiene come metrica.

---

## Q3 — Inferenza con detenzioni sovrapposte e clustering per giornata

### Cosa dice la letteratura

**1. Il clustering per giornata è il problema dominante, e la sottostima è misurata.** Fama
(1998), citando Mitchell & Stafford:

> «on average the covariances of event-firm abnormal returns account for about half the
> standard deviation of the event portfolio's abnormal return. Thus, if the covariances are
> ignored, the standard error of the abnormal portfolio return is too small by about 50%!»
> — `Q23-FAMA1998`

**2. Il rimedio di Fama è strutturale, non un aggiustamento di varianza**: aggregare in
portafoglio di calendario e fare inferenza sulla serie storica del portafoglio (citazione
completa in Q2 sopra, `Q23-FAMA1998`).

**3. Se invece si fa una regressione su osservazioni per-evento, il clustering va sulla
dimensione temporale.** Petersen (2009):

> «Since the Fama-MacBeth procedure is designed to address a time effect, the Fama-MacBeth
> standard errors are unbiased.» — `Q3-PETERSEN`

> «A time effect may be found in equity returns and earnings surprises, for example.» —
> `Q3-PETERSEN`

**4. È anche la pratica effettiva del paper più vicino al nostro caso d'uso.** Tetlock,
Saar-Tsechansky & Macskassy (2008), che regrediscono rendimenti su tono delle news
firm-specific:

> «We compute clustered standard errors (Froot (1989)) to account for the correlations
> between firms' stock returns within trading days.» — `Q5-TETLOCK-TSM2008`

**5. Gli orizzonti multipli non sono test indipendenti.** Boudoukh, Richardson & Whitelaw
(2008):

> «We show that for persistent regressors, a characteristic of most of the predictive
> variables used in the literature, the estimators are almost perfectly correlated across
> horizons under the null hypothesis of no predictability. For the persistence levels of
> dividend yields, the analytical correlation is 99% between the 1- and 2-year horizon
> estimators and 94% between the 1- and 5-year horizons.» — `Q3-BOUDOUKH-RW`

> «the persistence of Xt acts in much the same way as overlapping horizons in terms of the
> limited amount of independent information across multiple horizons.» — `Q3-BOUDOUKH-RW`

**6. Newey-West su regressione sovrapposta funziona male in campione finito.**
Britten-Jones, Neuberger & Nolte (2011):

> «Our method can easily be applied within standard software packages since conventional
> inference procedures (OLS-, White-, Newey-West-standard errors) are asymptotically valid
> when applied to the transformed regression. Through Monte Carlo analysis we show that it
> performs better in finite samples than the methods applied to the original regression that
> are in common usage.» — `Q3-BRITTENJONES`
>
> (fonte: abstract del record istituzionale Warwick WRAP; il full text non è stato
> recuperato)

**7. Newey-West è comunque la prassi dichiarata per CAR sovrapposti.** Jegadeesh & Titman,
nota 16:

> «Since overlapping returns are used to calculate the cumulative returns in event time, the
> autocorrelation-consistent Newey-West standard errors are used to compute the t-statistics
> for the cumulative returns (see Newey and West (1987)).» — `Q23-JEGADEESH-TITMAN`

**8. Sulla barra del t.** Harvey, Liu & Zhu:

> «The estimation of our model suggests that a newly discovered factor needs to clear a much
> higher hurdle, with a t-ratio greater than 3.0. Echoing a recent disturbing conclusion in
> the medical literature, we argue that most claimed research findings in financial economics
> are likely false.» — `Q3-HARVEY-LIU-ZHU`

**Fonti aperte ma non utilizzabili come evidenza testuale.** Hansen & Hodrick (1980) è
l'origine dell'HAC per previsioni k-step-ahead su dati sovrapposti, ma il PDF disponibile è
una scansione senza layer di testo e il record RePEc non espone abstract:
`SENZA_CITAZIONE_TESTUALE` (`Q3-HANSEN-HODRICK-ABS`). Stessa situazione per Newey & West
(1987) e (1994): Crossref non espone abstract e non ho recuperato i full text
(`Q3-NEWEY-WEST-1987`, `Q3-NEWEY-WEST-1994`). I riferimenti restano bibliograficamente
verificati ma il loro **contenuto non è usato come evidenza qui**.

### Raccomandazione operativa — Q3

**Sostenuto dalla letteratura:**

1. **La statistica principale deve essere la serie storica dei rendimenti giornalieri del
   book replayato, non una raccolta di rendimenti per-trade.** È la soluzione «completa» di
   Fama al problema della cross-correlazione (`Q23-FAMA1998`), e risolve simultaneamente
   sovrapposizione e clustering per giornata. Il replay di portafoglio già fissato in
   pre-registrazione §3 produce naturalmente questa serie: **usarla come oggetto
   dell'inferenza**.
2. Se si pubblica *comunque* una regressione per-evento, gli standard error vanno clusterati
   sul **giorno di calendario** (`Q3-PETERSEN`, `Q5-TETLOCK-TSM2008`), non sul ticker.
3. **I cinque orizzonti non sono cinque test.** Sono stimatori quasi perfettamente correlati
   sotto la nulla (`Q3-BOUDOUKH-RW`). Serve una correzione per molteplicità dichiarata, e la
   barra |t| ≥ 3 già in uso nel repo è quella sostenuta dalla letteratura
   (`Q3-HARVEY-LIU-ZHU`).
4. La scelta pre-registrata «Newey-West con lag pari all'orizzonte» resta valida come prassi
   (`Q23-JEGADEESH-TITMAN`), ma va accompagnata dall'avvertenza che in campione finito
   sovra-rigetta (`Q3-BRITTENJONES`): **il t pubblicato è un limite superiore alla
   significatività, non una stima neutrale**.

**Mia inferenza, non della letteratura:**

5. Con 114 uscite in finestra e detenzioni estese fino a 21 sedute, il numero di *giornate
   indipendenti* è il denominatore vero e sarà piccolo. Il criterio `INSUFFICIENT_N` del
   repo va valutato **sul conteggio dei cluster-giornata**, non sul conteggio dei trade. Se
   questo conteggio non regge, `INSUFFICIENT_N` sovrasta PASS/FAIL come da costruzione del
   `config/s4_kill_criterion.yaml` e il lavoro si ferma prima di produrre un verdetto.

---

## Q4 — Stop-loss: evidenza replicata, e quando distruggono rendimento

*(prior utilizzabile, per la clausola §5 della pre-registrazione)*

### Cosa dice la letteratura

**1. Il risultato teorico centrale è netto e ha un segno.** Kaminski & Lo (2014) definiscono
lo «stopping premium» come il contributo marginale della regola di stop al rendimento atteso:

> «If the portfolio follows a random walk (i.e., independently and identically distributed
> returns) the stopping premium is always negative.» — `Q4-KAMINSKI-LO`

> «If returns are unforecastable, stop-loss rules simply force the portfolio out of
> higher-yielding assets on occasion, thereby lowering the overall expected return without
> adding any benefits. In such cases, stop-loss rules never stop losses.» — `Q4-KAMINSKI-LO`

La condizione sotto cui invece funzionano è esplicita e verificabile:

> «if portfolio returns are characterized by “momentum” or positive serial correlation, we
> show that the stopping premium can be positive and is directly proportional to the
> magnitude of return persistence.» — `Q4-KAMINSKI-LO`

Con magnitudini empiriche su futures azionari:

> «For example in one calibration, using stop loss over monthly intervals in daily data can
> increase the return by 1.5% and decrease the volatility by 5% causing an increase in the
> Sharpe Ratio by as much as 20%.» — `Q4-KAMINSKI-LO`

**2. Sul momentum cross-sectional, uno stop semplice tronca le code.** Han, Zhou & Zhu
(working paper, **non** ho potuto verificare una pubblicazione su rivista):

> «For stocks in our winners portfolio, we automatically sell any one of them when it drops
> 10% below the beginning price of the month (which is the close price of the previous month
> used for forming the momentum portfolio).» — `Q4-HAN-ZHOU-ZHU`

> «As a result, the worst monthly return of the equal-weighted stop-loss momentum strategy
> is −11.36%, slightly below the −10% level.» — `Q4-HAN-ZHOU-ZHU`

> «For example, in those four months when the original momentum strategy has its worst
> losses, −49.79%, −39.43%, −35.24% and −34.46%, the stop-loss momentum has returns 1.69%,
> 2.64%, −6.00% and −3.57%.» — `Q4-HAN-ZHOU-ZHU`

**3. Ma la parte davvero replicata è un'altra: la protezione che funziona è il
dimensionamento condizionale, non lo stop per-posizione.** Due lavori indipendenti, su
riviste diverse, stesso verdetto.

Daniel & Moskowitz:

> «These momentum crashes are partly forecastable. They occur in "panic" states – following
> market declines and when market volatility is high – and are contemporaneous with market
> rebounds.» — `Q4-DANIEL-MOSKOWITZ`

> «An implementable dynamic momentum strategy based on forecasts of momentum's mean and
> variance approximately doubles the alpha and Sharpe Ratio of a static momentum strategy,
> and is not explained by other factors. These results are robust across multiple time
> periods, international equity markets, and other asset classes.» — `Q4-DANIEL-MOSKOWITZ`

Barroso & Santa-Clara:

> «We find that the risk of momentum is highly variable over time and predictable. Managing
> this risk virtually eliminates crashes and nearly doubles the Sharpe ratio of the momentum
> strategy. Risk-managed momentum is a much greater puzzle than the original version.» —
> `Q4-BARROSO-SC` (abstract dal record istituzionale NOVA; full text non recuperato)

**4. L'errore costoso documentato sugli investitori è tagliare i vincitori, non tenerli.**
Odean (1998):

> «For winners that are sold, the average excess return over the following year is 3.4
> percent more than it is for losers that are not sold. Investors who sell winners and hold
> losers because they expect the losers to outperform the winners in the future are, on
> average, mistaken.» — `Q4-ODEAN`

Cornice teorica in Shefrin & Statman (1985), di cui ho letto solo l'abstract:

> «we place this behavior pattern into a wider theoretical framework concerning a general
> disposition to sell winners too early and hold losers too long» — `Q4-SHEFRIN-STATMAN`
> (abstract Crossref; full text non recuperato)

### Raccomandazione operativa — Q4

**Sostenuto dalla letteratura:**

1. **Non introdurre stop-loss per-posizione come risposta a questa perdita.** Sotto assenza
   di dipendenza seriale positiva alla frequenza dello stop, il contributo atteso di uno
   stop è **negativo per teorema**, non incerto (`Q4-KAMINSKI-LO`). La condizione va
   *misurata* sulla nostra serie prima di considerare la leva, e finché non lo è, la prior è
   contraria.
2. Se si vuole protezione dalle code, la forma con **due repliche indipendenti** è il
   dimensionamento condizionale alla volatilità/regime (`Q4-DANIEL-MOSKOWITZ`,
   `Q4-BARROSO-SC`), non lo stop per-posizione. Han, Zhou & Zhu mostrano che anche lo stop
   semplice tronca le code sul momentum, ma è un singolo working paper non peer-reviewed e
   non va pesato allo stesso modo (`Q4-HAN-ZHOU-ZHU`).
3. L'osservazione «gli stop non sono mai scattati nella finestra» **non è un difetto**: alla
   luce di Kaminski & Lo è, se mai, l'esito favorevole.

**Mia inferenza, non della letteratura:**

4. **Q4 vincola una leva che non è quella che sta causando la perdita.** Il nostro ribilanciatore
   non è uno stop-loss: non vende perché il prezzo è sceso di una soglia, vende perché il
   budget serve altrove. Nessuna delle fonti lette copre quel meccanismo, e applicare a esso
   i risultati sugli stop sarebbe un trasferimento indebito. Questo va detto esplicitamente
   nel controfattuale, perché la tentazione di leggere «97% delle perdite dalle uscite» come
   «problema di stop» è forte e sbagliata.
5. Odean è un risultato su investitori retail e non descrive un ribilanciatore
   sistematico. Lo tengo come **cautela direzionale** — l'errore documentato è nella
   direzione del taglio rapido — non come evidenza sul nostro caso.

---

## Q5 — Orizzonte ottimale dei segnali news/sentiment e loro decadimento

*(prior utilizzabile, per la clausola §5 della pre-registrazione)*

### Cosa dice la letteratura

Il punto decisivo è che **«news» non è una cosa sola**: il tono aggregato di mercato, il tono
firm-specific e la sorpresa sugli utili hanno orizzonti di ordini di grandezza diversi.

**1. Sentiment aggregato di mercato: l'effetto è rumore e si annulla entro la settimana.**
Tetlock (2007), su una colonna quotidiana del Wall Street Journal:

> «I find that high media pessimism predicts downward pressure on market prices followed by
> a reversion to fundamentals» — `Q5-TETLOCK2007`

> «Consistent with the model in Campbell, Grossman, and Wang (1993), this negative influence
> is only temporary and is almost fully reversed later in the trading week. The magnitude of
> the reversal in lags 2 through 5 is 6.8 basis points» — `Q5-TETLOCK2007` (contro un impatto
> iniziale di «8.1 basis points»)

> «I conclude that the negative sentiment has a significant temporary impact on future Dow
> Jones returns that is fully reversed within a week.» — `Q5-TETLOCK2007`

**2. Tono firm-specific: contiene informazione, ma il prezzo la incorpora in 1-2 sedute.**
Tetlock, Saar-Tsechansky & Macskassy (2008):

> «the fraction of negative words in firm-specific news stories forecasts low firm earnings;
> (2) firms' stock prices briefly underreact to the information embedded in negative words»
> — `Q5-TETLOCK-TSM2008`

> «The main result in Table II is that negative words in firm-specific news stories robustly
> predict slightly lower returns on the following trading day. […] next-day abnormal returns
> (FFCAR+1,+1) are 3.20 basis points lower after each one-standard deviation increase in
> negative words.» — `Q5-TETLOCK-TSM2008`

> «the 12-day market reaction, from day -2 to day 10, to WSJ stories is virtually complete
> after the first two trading days—7.5 basis points (bps) of underreaction after day 1 and
> only 2.4 bps after day 2. By contrast, the second line in Figure 3 shows that more of the
> 12-day market reaction to DJNS stories persists beyond the first two days—16.8 bps after
> day 1 and 6.2 bps after day 2.» — `Q5-TETLOCK-TSM2008`

> «Although the total day 1 delayed reaction to DJNS news stories is 10.6 bps (see the
> difference line), this magnitude is relatively small (17.2%) as a percentage of the total
> 12-day reaction of roughly 61.6 bps.» — `Q5-TETLOCK-TSM2008`

**3. Drift post-news su orizzonti lunghi: esiste, ma su un costrutto diverso e su titoli
piccoli.** Chan (2003):

> «I find evidence of post-news drift, which supports the idea that investors underreact to
> information. This is strongest after bad news. I also find some evidence of reversal after
> extreme price movements that are unaccompanied by public news. […] They appear, however,
> to apply mainly to smaller stocks.» — `Q5-CHAN2003`

> «The difference between news and all returns is statistically significant in the first 12
> months.» — `Q5-CHAN2003`

Va notato che il portafoglio di Chan è formato su *rendimento passato mensile estremo* più
presenza di news, non sul tono di un modello di sentiment.

**4. PEAD: orizzonte di ~60 sedute, ma ampiamente attenuato nell'era recente.** Federal
Reserve Bank of Philadelphia WP 21-07:

> «When reported earnings are high relative to expectations, stock prices tend to rise for
> over 60 trading days. Conversely, when earnings are low, prices continuously fall. This
> post-earnings-announcement drift (PEAD), first documented by Ball and Brown (1968) and so
> named by Bernard and Thomas (1989), is a long-standing robust market anomaly commonly
> attributed to investor underreaction» — `Q5-PEADTXT-FRB`

> «The magnitude of PEAD.txt is considerable even in recent years when the classic PEAD is
> close to zero.» — `Q5-PEADTXT-FRB`

> «The difference is growing each quarter following the release of the earnings call text:
> 2.87% to 1.54%, 4.61% to 2.7%, 6.51% to 3.87%, and 8.01% to 4.63%.» — `Q5-PEADTXT-FRB`
> (PEAD.txt contro PEAD classico, quintili, campione 2010-2019)

Questo è il risultato più interessante per noi: **una misura di sorpresa derivata dal testo
mostra ancora un drift pluritrimestrale nel 2010-2019, mentre il PEAD classico è vicino a
zero**. Non è però la nostra misura: SUE.txt è addestrata su earnings call e rendimenti
anomali a un giorno, non è un punteggio di sentiment.

**5. L'arbitraggio delle anomalie pubblicate è misurato.** McLean & Pontiff (2016):

> «Portfolio returns are 26% lower out‐of‐sample and 58% lower post‐publication. […] We
> estimate a 32% (58%–26%) lower return from publication‐informed trading.» —
> `Q5-MCLEAN-PONTIFF` (abstract Crossref; full text non recuperato. Nel record Crossref i
> trattini sono U+2010, non ASCII: la citazione qui li riproduce tali e quali)

**Fonti aperte ma non utilizzabili come evidenza testuale.** Bernard & Thomas (1989), la
citazione canonica del PEAD, è dietro paywall e Crossref non espone abstract:
`SENZA_CITAZIONE_TESTUALE` (`Q5-BERNARD-THOMAS`). L'affermazione «il drift dura oltre 60
sedute» in questo documento poggia **solo** sul working paper della Fed di Philadelphia
(`Q5-PEADTXT-FRB`), che la attribuisce a Bernard & Thomas. Martineau (2022), «Rest in Peace
Post-Earnings Announcement Drift», *Critical Finance Review* 11(3-4):613-646, è
bibliograficamente verificato ma **non ne ho letto una riga** (`Q5-MARTINEAU`): il titolo
punta nella stessa direzione dell'attenuazione, ma senza testo non lo uso come evidenza.

### Raccomandazione operativa — Q5

**Sostenuto dalla letteratura:**

1. **Per un segnale di tono su news firm-specific — che è ciò che il sistema usa —
   l'orizzonte replicato è 1-2 sedute**, con l'85-93% della reazione completata entro il
   secondo giorno (`Q5-TETLOCK-TSM2008`). Una detenzione mediana di 0,7 giorni non è
   *prima facie* troppo corta: è **nell'intorno dell'orizzonte del segnale**.
2. **Per il sentiment aggregato l'effetto è temporaneo e si inverte entro la settimana**
   (`Q5-TETLOCK2007`). Se una parte del nostro segnale è di quella natura, tenere di più non
   è neutrale: è dannoso.
3. **Da qui una predizione pre-registrabile, da fissare PRIMA di eseguire il controfattuale:**
   i rami N=10 e N=21 non testano «il nostro alpha vive più a lungo». Testano se il
   risparmio di costo di transazione supera il decadimento del segnale, con in più
   l'esposizione al drift di mercato. Se vincono, **il guadagno va attribuito a costo o beta
   finché non è dimostrato il contrario**, e l'onere della prova sta sul ramo vincente.
4. **Non trasferire l'orizzonte PEAD al nostro segnale.** Le 60 sedute sono di una sorpresa
   sugli utili (`Q5-PEADTXT-FRB`), le 12 mensilità di Chan sono di un portafoglio formato su
   rendimento estremo su small cap (`Q5-CHAN2003`). Nessuno dei due è un punteggio di
   sentiment su news.
5. La magnitudine attesa è piccola: ~3,2 bps per deviazione standard di parole negative
   (`Q5-TETLOCK-TSM2008`). Qualunque risultato controfattuale molto più grande di questo
   ordine di grandezza è più probabilmente un artefatto di disegno che alpha.

**Mia inferenza, non della letteratura:**

6. La combinazione «orizzonte del segnale ≈ 1-2 sedute» + «detenzione mediana 0,7 giorni» +
   «97% delle perdite dal ribilanciatore» **non descrive un problema di cadenza**. Descrive
   un problema di **selezione all'ingresso o di costo**, cioè l'artefatto 6 della
   pre-registrazione («Selezione sull'uscita»): il ribilanciatore vende secondo un criterio,
   e se quel criterio ha una qualunque abilità, il controfattuale a calendario misura
   l'abilità e non la cadenza. Il controfattuale va quindi **condizionato sul motivo della
   vendita** e non solo sulla sua data.
7. Il risultato di FRB WP 21-07 (`Q5-PEADTXT-FRB`) suggerisce una direzione di ricerca
   diversa — una misura di sorpresa derivata dal testo delle earnings call, con drift
   pluritrimestrale ancora vivo — ma è **fuori dal perimetro di questa domanda** e va
   trattata come tale, non fatta entrare di soppiatto in questo controfattuale.

---

## Manifest delle fonti

Tutte le fonti aperte, nell'ordine in cui sono state consultate, incluse quelle scartate.
Esito registrato prima di passare alla successiva.

| id | fonte | tipo | domanda | esito | file_cache |
|---|---|---|---|---|---|
| `Q1-PEROLD` | Perold, «The implementation shortfall», *J. of Portfolio Management* 14(3):4-9, 1988 | peer-reviewed (rivista professionale) | Q1 | **A favore, ma inutilizzabile**: full text a paywall, Crossref senza abstract. Citato solo bibliograficamente; contenuto non usato come evidenza | `Q1-PEROLD.txt` (solo record) |
| `Q1-WAGNER-EDWARDS` | Wagner & Edwards, «Best Execution», *Financial Analysts Journal* 49(1):65-71, 1993 | peer-reviewed | Q1 | **A favore**: definisce l'opportunity cost dell'operazione non eseguita e dice che la maggior parte degli studi lo ignora. Caveat: il vincolo è liquidità, non budget | `Q1-WAGNER-EDWARDS.txt` |
| `Q1-NOVYMARX-VELIKOV` | Novy-Marx & Velikov, «A Taxonomy of Anomalies and Their Trading Costs», *RFS* 29(1):104-147, 2016 (NBER WP 20721) | peer-reviewed | Q1 | **A favore, fonte centrale**: la regola sS (buy/hold spread) è la risposta della letteratura al «vende troppo presto»; soglia del 50% di turnover mensile | `Q1-NOVYMARX-VELIKOV.txt` |
| `Q1-GARLEANU-PEDERSEN` | Gârleanu & Pedersen, «Dynamic Trading with Predictable Returns and Transaction Costs», *J. of Finance* 68(6):2309-2340, 2013 | peer-reviewed | Q1, Q5 | **A favore**: sotto costi l'ottimo è muoversi parzialmente verso l'aim; la velocità di decadimento del segnale è input della regola | `Q1-GARLEANU-PEDERSEN.txt` |
| `Q1-KORAJCZYK-SADKA` | Korajczyk & Sadka, «Are Momentum Profits Robust to Trading Costs?», *J. of Finance* 59(3):1039-1082, 2004 | peer-reviewed | Q1 | **Parzialmente pertinente**: il vincolo di capitale c'è ma è capacità/impatto, non crowd-out di budget. Non usata per conclusioni | `Q1-KORAJCZYK-SADKA.txt` |
| `Q2-GIPS-CALC` | CFA Institute, GIPS Guidance Statement on Calculation Methodology (adoz. 2010-09-28) | documentazione ufficiale | Q2 | **Contro l'uso ingenuo del TWR**: il TWR esiste per rimuovere proprio ciò che vogliamo misurare | `Q2-GIPS-CALC.txt` |
| `Q2-GIPS-2020` | CFA Institute, *2020 Global Investment Performance Standards for Firms* | documentazione ufficiale | Q2 | **A favore**: 1.A.35 ammette il money-weighted per pool closed-end / fixed commitment con controllo sui flussi — il nostro caso | `Q2-GIPS-2020.txt` |
| `Q23-JEGADEESH-TITMAN` | Jegadeesh & Titman, «Returns to Buying Winners and Selling Losers», *J. of Finance* 48(1):65-91, 1993 | peer-reviewed | Q2, Q3 | **A favore**: coorti sovrapposte da 1/K del capitale = normalizzazione capitale-tempo canonica; nota 16 = prassi Newey-West su CAR sovrapposti | `Q23-JEGADEESH-TITMAN.txt` |
| `Q23-FAMA1998` | Fama, «Market efficiency, long-term returns, and behavioral finance», *JFE* 49(3):283-306, 1998 | peer-reviewed | Q2, Q3 | **A favore, fonte centrale Q3**: cross-correlazione ignorata ⇒ standard error sottostimato del ~50%; portafoglio in calendar time come soluzione completa | `Q23-FAMA1998.txt` |
| `Q3-PETERSEN` | Petersen, «Estimating Standard Errors in Finance Panel Data Sets», *RFS* 22(1):435-480, 2009 | peer-reviewed | Q3 | **A favore**: con time effect servono SE clusterati sul tempo / Fama-MacBeth | `Q3-PETERSEN.txt` |
| `Q3-BOUDOUKH-RW` | Boudoukh, Richardson & Whitelaw, «The Myth of Long-Horizon Predictability», *RFS* 21(4):1577-1605, 2008 | peer-reviewed | Q3 | **A favore**: stimatori su orizzonti diversi quasi perfettamente correlati sotto la nulla ⇒ la griglia a 5 orizzonti non è 5 test | `Q3-BOUDOUKH-RW.txt` |
| `Q3-BRITTENJONES` | Britten-Jones, Neuberger & Nolte, «Improved Inference in Regression with Overlapping Observations», *JBFA* 38(5-6):657-683, 2011 | peer-reviewed | Q3 | **A favore, con caveat**: Newey-West sulla regressione grezza si comporta peggio in campione finito. Letto solo l'abstract (record Warwick WRAP) | `Q3-BRITTENJONES.txt` (abstract) |
| `Q3-HANSEN-HODRICK-ABS` | Hansen & Hodrick, *JPE* 88(5):829-853, 1980 | peer-reviewed | Q3 | **Non utilizzabile**: PDF disponibile è scansione senza layer di testo, RePEc senza abstract. Nessuna affermazione tratta da questa fonte | `Q3-HANSEN-HODRICK-ABS.txt` (solo record) |
| `Q3-NEWEY-WEST-1987` | Newey & West, *Econometrica* 55(3):703-708, 1987 | peer-reviewed | Q3 | **Non utilizzabile**: Crossref senza abstract, full text non recuperato. Solo riferimento bibliografico | `Q3-NEWEY-WEST-1987.txt` (solo record) |
| `Q3-NEWEY-WEST-1994` | Newey & West, «Automatic Lag Selection in Covariance Matrix Estimation», *ReStud* 61(4):631-653, 1994 | peer-reviewed | Q3 | **Non utilizzabile**: Crossref senza abstract, full text non recuperato. La selezione automatica del lag non è quindi documentata qui | `Q3-NEWEY-WEST-1994.txt` (solo record) |
| `Q3-HARVEY-LIU-ZHU` | Harvey, Liu & Zhu, «… and the Cross-Section of Expected Returns», *RFS* 29(1):5-68, 2016 (NBER WP 20592) | peer-reviewed | Q3 | **A favore**: la barra |t| ≥ 3 già in uso nel repo ha una fonte primaria | `Q3-HARVEY-LIU-ZHU.txt` |
| `Q4-KAMINSKI-LO` | Kaminski & Lo, «When do stop-loss rules stop losses?», *J. of Financial Markets* 18:234-254, 2014 | peer-reviewed | Q4 | **Fonte centrale Q4**: stopping premium negativo per teorema sotto random walk; positivo solo con persistenza seriale | `Q4-KAMINSKI-LO.txt` |
| `Q4-DANIEL-MOSKOWITZ` | Daniel & Moskowitz, «Momentum crashes», *JFE* 122(2):221-247, 2016 (NBER WP 20439) | peer-reviewed | Q4 | **A favore del dimensionamento condizionale**, non dello stop per-posizione | `Q4-DANIEL-MOSKOWITZ.txt` |
| `Q4-HAN-ZHOU-ZHU` | Han, Zhou & Zhu, «Taming Momentum Crashes: A Simple Stop-Loss Strategy», working paper (SSRN 2407199, versione CICF ott. 2014) | working paper, **non** peer-reviewed; autori a UC Denver / WashU Olin / Tsinghua | Q4 | **A favore, peso ridotto**: stop al 10% tronca le code del momentum. Non ho verificato alcuna pubblicazione su rivista | `Q4-HAN-ZHOU-ZHU.txt` |
| `Q4-BARROSO-SC` | Barroso & Santa-Clara, «Momentum has its moments», *JFE* 116(1):111-120, 2015 | peer-reviewed | Q4 | **A favore, seconda replica indipendente** del dimensionamento condizionale. Letto solo l'abstract (record NOVA) | `Q4-BARROSO-SC.txt` (abstract) |
| `Q4-ODEAN` | Odean, «Are Investors Reluctant to Realize Their Losses?», *J. of Finance* 53(5):1775-1798, 1998 | peer-reviewed | Q4 | **Cautela direzionale**: l'errore documentato è tagliare i vincitori. Popolazione retail, non un ribilanciatore sistematico | `Q4-ODEAN.txt` |
| `Q4-SHEFRIN-STATMAN` | Shefrin & Statman, «The Disposition to Sell Winners Too Early…», *J. of Finance* 40(3):777-790, 1985 | peer-reviewed | Q4 | **Contesto teorico**. Letto solo l'abstract (Crossref) | `Q4-SHEFRIN-STATMAN.txt` (abstract) |
| `Q5-TETLOCK2007` | Tetlock, «Giving Content to Investor Sentiment», *J. of Finance* 62(3):1139-1168, 2007 | peer-reviewed | Q5 | **Contro il tenere più a lungo**: l'effetto del sentiment aggregato è interamente invertito entro la settimana | `Q5-TETLOCK2007.txt` |
| `Q5-TETLOCK-TSM2008` | Tetlock, Saar-Tsechansky & Macskassy, «More Than Words», *J. of Finance* 63(3):1437-1467, 2008 | peer-reviewed | Q5, Q3 | **Fonte centrale Q5**: tono firm-specific ⇒ orizzonte 1-2 sedute, ~3,2 bps per σ. Inoltre: SE clusterati per giornata di borsa | `Q5-TETLOCK-TSM2008.txt` |
| `Q5-CHAN2003` | Chan, «Stock price reaction to news and no-news», *JFE* 70(2):223-260, 2003 | peer-reviewed | Q5 | **A favore con forte caveat**: drift post-news su 12 mesi, ma su small cap e su portafoglio formato da rendimento estremo, non da tono | `Q5-CHAN2003.txt` |
| `Q5-PEADTXT-FRB` | Meursault, Liang, Routledge & Scanlon, «PEAD.txt», FRB Philadelphia WP 21-07 (feb. 2021, rev. ago. 2022) | working paper di banca centrale | Q5 | **A favore**: 60 sedute per il PEAD classico; PEAD classico ≈ zero negli anni recenti; drift pluritrimestrale ancora vivo su sorpresa da testo | `Q5-PEADTXT-FRB.txt` |
| `Q5-BERNARD-THOMAS` | Bernard & Thomas, «Post-Earnings-Announcement Drift: Delayed Price Response or Risk Premium?», *JAR* 27:1-36, 1989 | peer-reviewed | Q5 | **Non utilizzabile**: paywall, Crossref e RePEc senza abstract. L'affermazione sulle 60 sedute poggia solo su `Q5-PEADTXT-FRB` | `Q5-BERNARD-THOMAS.txt` (solo record) |
| `Q5-MARTINEAU` | Martineau, «Rest in Peace Post-Earnings Announcement Drift», *Critical Finance Review* 11(3-4):613-646, 2022 | peer-reviewed | Q5 | **Non utilizzabile**: nowpublishers dietro challenge JS, SSRN 403; il dominio `cfr.pub` indicizzato per la versione accettata è ora un dominio riusato che serve spam. Nessuna riga letta | `Q5-MARTINEAU.txt` (solo record) |
| `Q5-MCLEAN-PONTIFF` | McLean & Pontiff, «Does Academic Research Destroy Stock Return Predictability?», *J. of Finance* 71(1):5-32, 2016 | peer-reviewed | Q5 | **A favore**: −26% out-of-sample, −58% post-pubblicazione. Letto solo l'abstract (Crossref) | `Q5-MCLEAN-PONTIFF.txt` (abstract) |
| `Q5-CHORDIA-ST` | Chordia, Subrahmanyam & Tong, «Have capital market anomalies attenuated…?», *JAE* 58(1):41-58, 2014 | peer-reviewed | Q5 | **Aperta e scartata**: Crossref non espone abstract e non ho recuperato il full text. Nessuna affermazione ne dipende | `Q5-CHORDIA-ST.txt` (solo record) |
| `VERIFICA-CROSSREF` | Crossref REST API | verifica bibliografica | tutte | **Strumento**: 24 DOI verificati (autori, titolo, rivista, anno, volume, fascicolo, pagine). Nessuna discrepanza rispetto alle citazioni usate | `VERIFICA-CROSSREF.txt` |

### Fonti aperte e scartate senza lasciare traccia nel corpo del documento

Registrate qui per completezza della regola anti-selezione; nessuna è usata come evidenza.

| fonte | tipo | esito |
|---|---|---|
| Semantic Scholar, scheda Perold (1988) | aggregatore | **Non recuperata**: risposta vuota (blocco anti-bot) |
| De Gruyter/Brill, capitolo Perold in *Streetwise* (Princeton UP, 1998) | editore | **Non recuperata**: risposta vuota |
| pm-research.com, landing page JPM 14(3)/4 | editore | **Non recuperata**: redirect su login OIDC |
| journals.uchicago.edu, DOI 10.1086/260910 | editore | **Non recuperata**: HTTP 403 |
| business.columbia.edu, PDF Hansen & Hodrick (1980) | repository | **Recuperata ma inutilizzabile**: 26 pagine scansionate senza layer di testo |
| onlinelibrary.wiley.com, abstract McLean & Pontiff | editore | **Non recuperata**: HTTP 403 (abstract poi ottenuto da Crossref) |
| papers.ssrn.com, Martineau (2022) | repository | **Non recuperata**: HTTP 403 |
| nowpublishers.com, scheda Martineau | editore | **Non recuperata**: challenge JavaScript |
| `cfr.pub`, presunta versione accettata di Martineau | — | **Scartata come non-fonte**: il dominio serve oggi pagine di spam commerciale non correlate. Il file di cache scaricato è stato cancellato |
| Semantic Scholar Graph API | API | **Non disponibile**: HTTP 429 (rate limit) |

---

## Buchi dichiarati

Cose per cui **non** ho trovato una fonte primaria, o per cui l'ho trovata ma non ho potuto
leggerla. Una lacuna dichiarata vale più di una citazione plausibile e non verificabile.

1. **Nessuna fonte primaria trovata sul displacement come lo intendiamo noi.** Non ho trovato
   alcun paper che formalizzi il controfattuale «vendo X per comprare Y sotto vincolo di
   budget stringente» e ne derivi un benchmark. Le due cose più vicine trattano vincoli
   diversi: l'opportunity cost di Wagner & Edwards è mancanza di *liquidità*
   (`Q1-WAGNER-EDWARDS`), la capacità di Korajczyk & Sadka è *impatto di prezzo*
   (`Q1-KORAJCZYK-SADKA`). Il vincolo di budget compare come vincolo del programma di
   ottimizzazione in Gârleanu & Pedersen (`Q1-GARLEANU-PEDERSEN`), non come oggetto di una
   valutazione ex post. **Il replay di portafoglio fissato in pre-registrazione resta la
   scelta giusta, ma non ha una citazione che lo prescriva: è argomentabile, non citabile.**

2. **Perold (1988) non è stato letto.** Il framing «paper portfolio contro portafoglio reale»
   che sostiene l'artefatto 1 della pre-registrazione è nella letteratura, ma in questo
   documento non ne ho la citazione testuale. `SENZA_CITAZIONE_TESTUALE`.

3. **Bernard & Thomas (1989) non è stato letto.** L'orizzonte di 60 sedute del PEAD poggia
   interamente sul working paper della Fed di Philadelphia che lo riferisce
   (`Q5-PEADTXT-FRB`). È una citazione di seconda mano, dichiarata come tale.

4. **Hansen & Hodrick (1980), Newey & West (1987) e Newey & West (1994) non sono stati
   letti.** Sono bibliograficamente verificati contro Crossref, ma nessuna affermazione
   metodologica in Q3 poggia sul loro testo. La pratica «Newey-West su CAR sovrapposti» è
   documentata qui tramite la nota 16 di Jegadeesh & Titman (`Q23-JEGADEESH-TITMAN`), non
   tramite l'originale. In particolare, **la selezione automatica del lag di Newey-West
   (1994) non è documentata in questo documento**: la scelta pre-registrata «lag = orizzonte»
   resta una convenzione dichiarata, non una prescrizione citata.

5. **Nessuna fonte primaria trovata sul termine «return on capital employed in
   backtesting».** La query non ha prodotto letteratura accademica: quello che esiste è la
   costruzione a coorti sovrapposte (`Q23-JEGADEESH-TITMAN`) e la distinzione TWR/MWR degli
   standard di performance (`Q2-GIPS-CALC`, `Q2-GIPS-2020`). Se esiste un corpus accademico
   con quel nome, non l'ho trovato.

6. **Nessuna fonte primaria letta sull'efficacia degli stop-loss in strategie guidate da
   sentiment o da news.** Tutta l'evidenza replicata di Q4 è su momentum e su asset
   allocation index-futures. Il trasferimento al nostro caso è un'assunzione, non un
   risultato.

7. **Nessuna fonte primaria trovata sul decadimento di segnali prodotti da LLM su testo
   finanziario.** La letteratura letta usa conteggi di parole (`Q5-TETLOCK2007`,
   `Q5-TETLOCK-TSM2008`) o regressione logistica regolarizzata su testo
   (`Q5-PEADTXT-FRB`). Nessuna copre un punteggio di sentiment prodotto da un ensemble di
   modelli generativi. Gli orizzonti di 1-2 sedute vanno quindi trattati come **prior su una
   classe vicina, non come misura sul nostro segnale**.

8. **Martineau (2022) e Chordia, Subrahmanyam & Tong (2014) non sono stati letti.** La tesi
   dell'attenuazione recente del PEAD poggia solo su `Q5-PEADTXT-FRB` e su
   `Q5-MCLEAN-PONTIFF` (abstract).
