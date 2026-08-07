# S2, S3 e S7: validita economica, universalita e gate di investimento

**Data:** 2026-07-15

**Scope:** letteratura primaria e verifica statica delle definizioni implementate in Alembic.

**Nota:** questo documento e una research note, non un tracker di stato. Lo stato della
roadmap resta nelle issue GitHub collegate alla map issue `#21`.

**Supersessione parziale:** la revisione clean-room e la teoria normativa di S2 sono ora
in [`docs/strategies/s2-vrp-theory.md`](strategies/s2-vrp-theory.md). Le sezioni S2 di
questa nota restano un antecedente comparativo e non sono la fonte teorica ufficiale.

## Executive verdict

Nessuna delle tre strategie e "universalmente valida" nel senso di produrre alpha
positivo in ogni mercato, regime e implementazione. Le tre famiglie hanno pero un peso
empirico molto diverso e, soprattutto, il nome della strategia non basta: l'implementazione
deve riprodurre l'esposizione economica studiata.

| Strategia | Fenomeno in letteratura | Implementazione Alembic attuale | Investimento raccomandato |
|---|---|---|---|
| **S3 cross-sectional momentum** | **Forte e ampio** per momentum; la correzione beta di Alembic e una variante proprietaria plausibile, non uno standard universale | **Disallineata dalla specifica originale Alembic** e misurata da un gate report ormai non valido | **Si, P1**, prima come ripristino fedele della specifica e nuovo POC offline |
| **S2 volatility risk premium** | **Reale**, ma e soprattutto premio per assicurazione/tail risk, non alpha gratuito | **Non implementata ne validata**: il backtest negozia SPY, non opzioni | **Solo condizionale, P3**; non investire nel codice attuale |
| **S7 PEAD** | **Storicamente robusto**, ma dipende da attenzione, liquidita, costi e misura della surprise | Codice coerente solo come prototipo semplice; i test Alembic sul segnale raw hanno gia dato **FAIL** | **No** al PEAD raw standalone; **si limitato** all'infrastruttura earnings/tone riusabile |

La priorita razionale e quindi:

1. riallineare S3 alla sua specifica originale 12-1, beta-adjusted e long-only, quindi
   confrontarla con benchmark e varianti residuali;
2. mantenere l'earnings evidence plane di S7, senza promuovere la strategia raw;
3. affrontare S2 solo se Alembic decide strategicamente di diventare option-aware.

## 1. Che cosa sono davvero in Alembic

### 1.1 S2: cash-secured SPY put / VRP

Il disegno dichiara vendita mensile di put SPY con:

- delta target `-0.20` (tolleranza `0.05`);
- 30-45 DTE;
- collateral massimo 20% del NAV;
- filtro `implied_vol - realized_vol >= 0`;
- profit take al 50% del premio, stop a 2x premio o calo SPY del 5%;
- size ridotto in regime sideways/bear e nessuna nuova posizione in high volatility;
- filtro approssimato FOMC/NFP.

Fonti locali: [`src/strategies/s2/config.py`](../src/strategies/s2/config.py),
[`signal.py`](../src/strategies/s2/signal.py), [`exit.py`](../src/strategies/s2/exit.py).

Ma il contratto economico del backtest e diverso: `VRPStrategy` invia ordini **BUY/SELL
SPY** e il portafoglio contabilizza il P&L azionario. Il premio della put viene calcolato
internamente, ma non entra nel NAV. Se manca persino un contratto selezionabile, il codice
crea comunque una put sintetica e compra SPY. La documentazione nel modulo lo dichiara
esplicitamente ([`strategy.py`, righe 16-22 e 274-344](../src/strategies/s2/strategy.py)).

Le catene sono generate da Black-Scholes con IV ATM fissa 18%, skew deterministico,
volume/OI sintetici e tasso fisso 5% ([`ingestion.py`, righe 27-47 e
166-220](../src/data/options/ingestion.py)). Questo puo testare la meccanica software, non
l'esistenza del VRP: la differenza tra volatilita implicita e realizzata e imposta dal
generatore invece di essere osservata dal mercato.

**Conclusione semantica:** oggi S2 e un prototipo di selezione opzioni collegato a un
backtest long-SPY. I suoi report non sono evidenza favorevole o contraria alla vendita di
put; misurano un'altra esposizione.

Anche il possibile percorso operativo non e solo "non ancora attivato": il scheduler
ricostruisce una nuova `VRPStrategy` a ogni ciclo, mentre `_open_position` e
`_last_rebalance` vivono soltanto in memoria nell'istanza. Lo stato della put viene quindi
perso fra cicli ([`portfolio_scheduler.py`, righe 1250-1258 e 2394-2412](../src/workers/portfolio_scheduler.py),
[`strategy.py`, righe 81-94](../src/strategies/s2/strategy.py)). Inoltre la strategia
dimensiona gia l'ordine SPY come `NAV * max_collateral_pct * regime_scale`; l'orchestrator
converte quell'ordine in peso e lo moltiplicherebbe ancora per `allocation_pct`. Con una
ipotetica allocation S2 del 20%, il 20% interno diventerebbe un contributo di circa 4% al
portafoglio, non 20% ([`orchestrator.py`, righe 155-164 e 327-340](../src/portfolio/orchestrator.py)).
Non esiste infine un path di invio, accounting o riconciliazione di un contratto option:
anche abilitando forzatamente S2 si continuerebbe a negoziare SPY.

### 1.2 S3: cross-sectional momentum beta-adjusted

La specifica Alembic originale non mirava a replicare il residual momentum Fama-French di
Blitz, Huij e Martens. Definiva una variante proprietaria e piu semplice del momentum
cross-sectional di Jegadeesh-Titman:

```text
log(P[t-21] / P[t-252]) - rolling_beta_252(stock, SPY) * SPY_momentum_12_1
```

Il disegno prevedeva ranking cross-sectional, acquisto del decile migliore, esclusione del
peggiore senza short, inverse-volatility sizing a 60 giorni, normalizzazione dei pesi e
cap del 10%. Fonte storica:
[`01_strategy_design.md`, sezione S3](../archive/2026-06-p0-p2-controlled-paper-history/01_initial_specs/01_strategy_design.md).

Il codice corrente implementa invece `P[t] / P[t-252] - 1`, quindi include proprio il mese
che la specifica voleva escludere; compra il decile 10 **e vende** il decile 1; riusa la
finestra beta di 252 giorni per la volatilita; applica un cap del 20%; non normalizza i pesi
dei long. Fonti: [`signal.py`](../src/strategies/s3/signal.py) e
[`strategy.py`](../src/strategies/s3/strategy.py). Il fix del 19 giugno 2026 ha eliminato
il look-ahead dello scalar volatility sizing, ma non ha corretto questi scostamenti di
definizione.

La precedente versione di questa review giudicava S3 rispetto al residual momentum
canonico di Blitz, Huij e Martens. Era un benchmark utile, ma il criterio di correttezza
sbagliato per Alembic. Quel paper resta una **variante comparativa** interessante, non la
specifica che il codice avrebbe dovuto implementare. La sua costruzione:

- stima residui mensili contro i tre fattori Fama-French (market, SMB, HML);
- usa regressioni rolling a 36 mesi;
- forma il segnale sui residui 12-1, escludendo l'ultimo mese;
- standardizza il residual return per la sua volatilita nello stesso periodo;
- costruisce un portafoglio top-minus-bottom decile zero-investment con portafogli
  sovrapposti.

La costruzione e descritta direttamente dagli autori nel
[paper pubblicato](https://doi.org/10.1016/j.jempfin.2011.01.003) e nel
[manoscritto completo, pp. 11-13](https://pure.eur.nl/ws/files/46882404/ResidualMomentum-2011.pdf).

### 1.3 S7: PEAD long-only su earnings beat

S7 riceve actual EPS e consensus EPS strutturati, calcola una surprise percentuale, crea un
segnale sopra `|5%|`, e assegna 5% per titolo ai soli beat fino a un sleeve del 25%, per un
hold dichiarato di 20 giorni. Il worker attuale usa Finnhub, confidence fissa `0.95` e solo
la watchlist: [`earnings_pead_worker.py`](../src/workers/earnings_pead_worker.py).

La strategia e volutamente semplice e long-only: non usa il valore continuo della
surprise, non usa guidance/tone, non costruisce un ranking e dipende dall'ordine della lista
quando piu di cinque nomi sono eleggibili
([`strategy.py`, righe 49-69](../src/strategies/s7/strategy.py)).

Inoltre, `hold_until = detected_at + 20 giorni` usa giorni di calendario, non 20 sedute;
`detected_at` e la data evento alle 00:00 UTC, senza distinguere before-open e after-close
([`signal.py`](../src/strategies/s7/signal.py),
[`pead.py`](../src/models/pead.py)). Queste differenze sono materiali per un event study.

## 2. S2: quanto e universale il volatility risk premium?

### 2.1 Cosa sostiene davvero l'evidenza

Il fatto di base e solido: le opzioni incorporano una remunerazione per rischio di
volatilita e di coda. Coval e Shumway trovano rendimenti delle put inferiori al risk-free e
perdite elevate negli straddle zero-beta; Carr e Wu documentano variance risk premia su
cinque indici e 35 titoli; Bekaert, Engstrom ed Ermolov trovano un equity VRP positivo ma
solo moderatamente persistente e collegato alla coda sinistra della crescita dei consumi.

Fonti primarie:

- Coval e Shumway, [Expected Option Returns](https://doi.org/10.1111/0022-1082.00352),
  *Journal of Finance* (2001).
- Carr e Wu, [Variance Risk Premiums](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1359527),
  *Review of Financial Studies* (2009).
- Bekaert, Engstrom ed Ermolov,
  [The Variance Risk Premium in Equilibrium Models](https://www.nber.org/papers/w27108),
  NBER (2020), poi *Review of Finance* (2023).

Questa evidenza supporta **l'esistenza di un premio**, non l'idea che una short put abbia
alpha indipendente dal rischio. Una short put combina esposizione azionaria positiva,
short volatility, short skew e short jump/tail risk. Il premio e economicamente simile al
ricavo di un assicuratore: frequenti piccoli guadagni contro perdite rare e concentrate.

Broadie, Chernov e Johannes mostrano inoltre che gli elevati rendimenti medi delle OTM put
writing strategies hanno enorme sampling uncertainty; rispetto a modelli con stochastic
volatility e jump risk non sono necessariamente anomali. Santa-Clara e Saretto mostrano che
bid-ask, margin e margin call riducono sensibilmente i rendimenti realizzabili.

- Broadie, Chernov e Johannes,
  [Understanding Index Option Returns](https://doi.org/10.1093/rfs/hhp032),
  *Review of Financial Studies* (2009).
- Santa-Clara e Saretto,
  [Option Strategies: Good Deals and Margin Calls](https://doi.org/10.1016/j.finmar.2009.01.002),
  *Journal of Financial Markets* (2009).

### 2.2 Universalita, regime e decay

**Verdetto:** VRP e piu universale di una singola anomalia azionaria, ma la strategia short
put non e universalmente profittevole.

- **Regime:** il premio cresce quando la domanda di protezione e il rischio di coda sono
  elevati; e proprio allora che le perdite potenziali e la necessita di capitale aumentano.
  Bloccare sempre l'entrata in high-vol riduce la coda, ma puo anche eliminare la parte piu
  remunerativa del premio. Va testato, non assunto.
- **Universo:** l'evidenza piu forte riguarda opzioni liquide su indici. Trasferirla a
  opzioni single-name aggiunge earnings jumps, borrow, dividend ed enorme dispersione di
  liquidita.
- **Costi/capacita:** spread, execution at bid, margin, assignment e capital opportunity
  cost sono parte della strategia, non dettagli post-hoc.
- **Crowding:** il premio non deve necessariamente scomparire, perche puo essere compenso
  per rischio non desiderato; puo pero comprimersi e cambiare forma con domanda/offerta e
  diffusione dei systematic put-writing products.
- **Tail estimation:** una storia senza 1987, 2008, febbraio 2018 e marzo 2020 non stima
  credibilmente la distribuzione. La metrica primaria non puo essere solo Sharpe.

La metodologia ufficiale del
[Cboe S&P 500 PutWrite Index](https://cdn.cboe.com/api/global/us_indices/governance/Cboe_SP_500_PutWrite_Indices_Methodology.pdf)
e un benchmark utile per definire roll, collateral e settlement; non e prova indipendente
di alpha.

### 2.3 Gate minimi per investire in S2

Prima di spendere sul segnale servono, in ordine:

1. **Backtester option-aware:** quote storiche PIT bid/ask, IV surface osservata, contract
   identifiers, multiplier, corporate actions, dividend, rate curve, American exercise per
   SPY, assignment, expiry e margin giornaliero.
2. **P&L autentico:** premio incassato, mark-to-market della stessa option, fill conservativi
   (almeno sell bid / buy ask), commissioni e collateral return. Nessun proxy SPY.
3. **Benchmark decomposition:** confronto con Cboe PUT/PUTY, SPY beta-matched e una
   strategia delta-hedged. Riportare beta, vega, skew/jump exposure e convexity.
4. **Tail gates:** expected shortfall, worst-month, max loss per contract, margin peak,
   recovery time, scenario 1987-like e block bootstrap; Sharpe e max drawdown ordinari non
   bastano.
5. **Ablation:** raw put write vs VRP threshold vs regime overlay vs event filter. Un
   overlay resta solo se migliora OOS il tail-adjusted utility dopo costi.
6. **Operational gate:** chain freshness, NBBO age, contract availability, early exercise,
   broker reconciliation e kill switch dedicato.

### 2.4 Decisione S2

Non investire incrementalmente nel backtest attuale: migliorare soglie o regime su un P&L
SPY non avvicina alla validazione del VRP. S2 ha senso solo come programma derivati
separato, con costo dati e broker esplicitamente autorizzati. Fino ad allora: `disabled` e
nessuna interpretazione economica dei report esistenti (OOS Sharpe circa `-0.55`, tutti i
gate economici falliti in [`reports/s2_backtest_v2`](../reports/s2_backtest_v2/summary.json)).

## 3. S3: quanto e universale il cross-sectional momentum?

### 3.1 Evidenza di base

Tra le tre famiglie, momentum ha la piu ampia replicazione. Jegadeesh e Titman documentano
che comprare winner e vendere loser produce rendimenti positivi su holding period 3-12
mesi. Asness, Moskowitz e Pedersen trovano premi value e momentum coerenti in otto mercati
e asset class, con una struttura fattoriale globale comune.

- Jegadeesh e Titman,
  [Returns to Buying Winners and Selling Losers](https://doi.org/10.1111/j.1540-6261.1993.tb04702.x),
  *Journal of Finance* (1993).
- Asness, Moskowitz e Pedersen,
  [Value and Momentum Everywhere](https://doi.org/10.1111/jofi.12021),
  *Journal of Finance* (2013).

Il residual momentum e una variante piu specifica. Blitz, Huij e Martens trovano Sharpe
circa doppio rispetto al total-return momentum, grazie a minori esposizioni dinamiche a
market, size e value, su CRSP 1930-2009. Il risultato giustifica includerlo come comparator
nel POC, ma non implica che la variante beta-adjusted di Alembic sia "implementata male"
solo perche non replica quel paper: e una diversa ipotesi che deve essere nominata e
validata per cio che e.

### 3.2 Limiti: crash, costi e crowding

Momentum non e stabile per regime. Daniel e Moskowitz mostrano crash persistenti in panic
states, tipicamente quando il mercato rimbalza dopo un forte ribasso e i loser recuperano.
Barroso e Santa-Clara mostrano che il volatility scaling riduce fortemente skew, kurtosis e
drawdown, ma non elimina la necessita di una validazione real-time/OOS.

- Daniel e Moskowitz, [Momentum Crashes](https://doi.org/10.1016/j.jfineco.2015.12.002),
  *Journal of Financial Economics* (2016).
- Barroso e Santa-Clara,
  [Momentum Has Its Moments](https://doi.org/10.1016/j.jfineco.2014.11.010),
  *Journal of Financial Economics* (2015).

I costi dipendono criticamente dall'universo e dal weighting. Lesmond, Schill e Zhou
mostrano che i titoli che producono i maggiori paper profits sono spesso quelli piu costosi
da negoziare. Korajczyk e Sadka trovano invece strategie ancora investibili dopo costi,
soprattutto con liquidity/value weighting, ma con capacita finita. Le due fonti non si
contraddicono: dimostrano che **la costruzione del portafoglio decide se il fenomeno
accademico diventa strategia**.

- Lesmond, Schill e Zhou,
  [The Illusory Nature of Momentum Profits](https://doi.org/10.1016/S0304-405X(03)00206-X),
  *Journal of Financial Economics* (2004).
- Korajczyk e Sadka,
  [Are Momentum Profits Robust to Trading Costs?](https://doi.org/10.1111/j.1540-6261.2004.00656.x),
  *Journal of Finance* (2004).

La pubblicazione tende inoltre a comprimere le anomalie: McLean e Pontiff stimano, su 97
predictor, ritorni medi 26% inferiori OOS e 58% inferiori post-pubblicazione.
[Fonte primaria](https://doi.org/10.1111/jofi.12365), *Journal of Finance* (2016).

### 3.3 Problemi materiali nell'implementazione Alembic

1. **Segnale diverso dalla specifica Alembic.** Manca il 12-1 skip e viene usato un
   rendimento semplice fino a `t`, invece di `log(P[t-21]/P[t-252])`. Il problema
   principale e l'inclusione del mese recente, esposto a short-term reversal; semplice vs
   log sarebbe in gran parte monotono nel ranking, ma altera anche la sottrazione beta.
2. **Universo con look-ahead/survivorship.** Il full runner calcola `active_at(end)` alla
   data finale, prende i primi 50 titoli e usa quelli su tutta la storia
   ([`backtest.py`, righe 199-214](../src/strategies/s3/backtest.py)). Il filtro
   `S3Universe.active_at()` e PIT preso singolarmente, ma non viene rieseguito a ogni
   rebalance dal backtest. Questo invalida l'interpretazione OOS.
3. **Selection arbitraria.** `active[:50]` dipende dall'ordine del config, non da una
   classifica PIT per market cap o liquidita. Il source corrente contiene 57 strumenti,
   non i 72 dichiarati nel design, e include ETF come SPY, QQQ, IWM e sector ETF insieme
   alle azioni. Inoltre `min_market_cap_usd` e presente in `config/universe.yaml`, ma
   `LiquidityFilter` non lo legge ne lo applica. Con 50 nomi, ogni decile contiene circa
   cinque titoli: scarsa breadth e alta idiosincraticita.
4. **Portfolio construction divergente.** La specifica e long-only, usa volatilita a 60
   giorni, cap 10% e pesi normalizzati. Il codice apre anche lo short loser, usa 252 giorni,
   cap 20% e non normalizza l'inverse-vol sizing. Il P&L misurato non appartiene quindi al
   portafoglio originariamente approvato.
5. **Short non autorizzato ne modellato.** Il costo e la disponibilita del loser leg non
   sono modellati. Locate, borrow fee, recall, margin e gross leverage mancano, rendendo
   questa deviazione sia economica sia operativa.
6. **Corporate actions/delisting.** Per una strategia cross-sectional storica servono
   total-return prices, delisting returns e membership PIT; una matrice di survivor correnti
   non e sufficiente.
7. **Gate report obsoleto e non riproducibile come evidenza corrente.** Il run del 30
   maggio precede il fix PIT del sizing del 19 giugno. Inoltre usava Gate 1 e Gate 2 con
   soglie Sharpe `0.0`, poi alzate rispettivamente a `0.5` e `0.3`; l'OOS Sharpe `0.148`
   non passerebbe oggi. Il vecchio Gate 4 richiedeva due soli regimi, contro tre oggi. Il
   vecchio Gate 5 selezionava ex post il peggior drawdown +/-15 giorni; non era un test su
   crisi storiche predefinite. Il suo FAIL dipendeva dal cumulative return `-10.07%`, appena
   oltre la soglia `-10%`, non da una violazione del limite drawdown `-30%`. Infine DSR
   `1.0` era calcolato con `n_trials=1`. I file sotto `reports/` sono gitignored: mancano
   artifact versionato, commit e manifest dati sufficienti a trattare quel risultato come
   ultimo gate valido. Il runner corrente continua peraltro a produrre solo `high_vol` e
   `low_vol`, mentre Gate 4 richiede almeno tre regimi: oggi fallirebbe strutturalmente.
8. **Nessun percorso operativo.** Il registry costruisce soltanto S1, S2 e S4. Anche se
   S3 venisse aggiunta alla configurazione, `_extract_target_weights()` riconosce soltanto
   S1 e S4 tra le strategie con `compute_target_weights()` e per ogni altro ID restituisce
   `{}` ([`registry.py`, righe 158-181](../src/strategies/registry.py),
   [`orchestrator.py`, righe 294-325](../src/portfolio/orchestrator.py)). S3 non e quindi
   "pronta ma spenta": manca il contratto di integrazione.
9. **Motore short incompleto.** Il portafoglio virtuale permette quantita negative, ma non
   applica locate, borrow fee, recall, margin o vincoli di gross leverage. Il risultato
   long-short non rappresenta una strategia eseguibile sul loser leg.
10. **Walk-forward con stato condiviso.** `WalkForwardRunner` riusa la stessa istanza
    mutabile della strategia in tutte le finestre. `_last_rebalance` puo quindi contaminare
    l'inizio della finestra successiva. Segnali e volatilita rolling sono ora causali, ma
    l'isolamento OOS richiede una strategy factory o un reset esplicito per finestra
    ([`runner.py`](../src/backtest/walkforward/runner.py)).
11. **Validita cross-sectional troppo restrittiva.** La generazione scarta una data se
    anche un solo titolo ha un residuo `NaN`. Un IPO recente o una lacuna di dati puo
    ritardare l'intero campione invece di ridurre localmente l'universo eleggibile.

Quindi il vecchio risultato non e propriamente "3 gate su 5 passati": e un run esplorativo
storico, ottenuto con codice, soglie e stress methodology poi cambiati. Non confuta la tesi
S3 e non giustifica paper trading. Rilanciarlo senza prima riallineare la definizione
produrrebbe un numero fresco sulla strategia sbagliata.

### 3.4 Riallineamento, comparatori e gate raccomandati per S3

Costruire tre varianti pre-registrate, senza tuning iterativo sul test finale:

- **A, primaria:** specifica Alembic originale: 12-1 log momentum beta-adjusted, top decile
  long-only, loser esclusi, vol 60 giorni, cap 10%, pesi normalizzati;
- **B, ablation:** total momentum 12-1 long-only con la stessa identica costruzione di
  universo e portafoglio, per misurare il valore incrementale della correzione beta;
- **C, research comparator:** residual momentum FF3 canonico, inizialmente long-only per
  comparabilita; l'eventuale long-short e un esperimento separato con costi borrow.

Gate obbligatori:

1. universo US common stocks PIT, con membership, delisting e corporate actions;
2. almeno 200-500 nomi liquidi per rebalance, non 50 survivor finali;
3. gross exposure stabile; beta, sector exposure e cash drag riportati per il long-only;
4. spread, market impact e turnover reali; borrow solo per una successiva variante short;
5. walk-forward per decade/regime, con 2000-02, 2008-09, 2020 e 2022 presenti;
6. OOS net Sharpe hurdle > `0.30`, confidence interval block-bootstrap e Deflated Sharpe;
7. max drawdown e expected shortfall migliori di A oppure valore di diversificazione
   dimostrato nel portafoglio Alembic;
8. robustness pre-registrata su lookback e skip; per C anche 24/36/60 mesi di factor
   estimation, senza usare le perturbazioni per scegliere ex post il vincitore;
9. confronto incrementale con S1: correlation, marginal risk contribution e portfolio
   Sharpe, non solo standalone Sharpe;
10. shadow di almeno 3-6 mesi prima del paper; la variante A non dipende dal borrow.

### 3.5 Decisione S3

**E la migliore candidata allo sviluppo**, ma la prima mossa non e un rebuild FF3 ne un
semplice rerun. E un intervento circoscritto per rendere eseguibile la specifica Alembic
originaria, correggere il backtest PIT e isolare le finestre walk-forward. Subito dopo va
eseguito un POC A/B: la correzione beta resta solo se aggiunge valore al momentum 12-1
semplice. FF3 e una terza variante di ricerca, non un prerequisito. Broker wiring solo dopo
gate correnti e artifact riproducibile.

## 4. S7: quanto e universale il PEAD?

### 4.1 Evidenza di base

Ball e Brown documentano per primi che l'informazione contabile si riflette nei prezzi con
ritardo. La letteratura successiva mostra drift dopo surprise positive/negative, ma i canali
sono condizionali: underreaction, attenzione limitata, liquidita e rischio di arbitraggio.

- Ball e Brown,
  [An Empirical Evaluation of Accounting Income Numbers](https://doi.org/10.2307/2490232),
  *Journal of Accounting Research* (1968).
- Bernard e Thomas,
  [Post-Earnings-Announcement Drift: Delayed Price Response or Risk Premium?](https://doi.org/10.2307/2491062),
  *Journal of Accounting Research* (1989).
- DellaVigna e Pollet,
  [Investor Inattention and Friday Earnings Announcements](https://www.nber.org/papers/w11683),
  NBER (2005), poi *Journal of Finance* (2009).
- Hirshleifer, Lim e Teoh,
  [Driven to Distraction](https://doi.org/10.1111/j.1540-6261.2009.01501.x),
  *Journal of Finance* (2009).

Queste fonti suggeriscono un edge piu forte quando l'informazione e difficile da processare
o l'attenzione e scarsa. Non suggeriscono un semplice "EPS beat > 5% = buy" universale.

### 4.2 Costi e universo

Chordia, Goyal, Sadka, Sadka e Shivakumar trovano PEAD concentrato nei titoli molto
illiquidi: il long-short produce solo 0.04% mensile value-weighted nei titoli piu liquidi e
2.43% nei piu illiquidi, ma costi e market impact assorbono il 70-100% dei paper profits.

[Liquidity and the Post-Earnings-Announcement Drift](https://doi.org/10.2469/faj.v65.n4.3),
*Financial Analysts Journal* (2009).

Sadka trova inoltre che momentum e PEAD caricano su variazioni sistematiche inattese della
liquidita, quindi una parte dei rendimenti puo essere compensazione per liquidity risk,
non mispricing gratuito.

[Momentum and Post-Earnings-Announcement Drift Anomalies: The Role of Liquidity Risk](https://doi.org/10.1016/j.jfineco.2005.04.005),
*Journal of Financial Economics* (2006).

**Verdetto di universalita:** il PEAD e replicato storicamente, ma la sua versione
investibile e fortemente dipendente da misura della surprise, size, liquidita, attention
load, periodo e costi. L'edge teoricamente maggiore e spesso nel segmento meno negoziabile.

### 4.3 Cosa dicono gia i dati Alembic

Alembic dispone di evidenza locale negativa, piu rilevante di una citazione generale:

- **Large cap raw EPS surprise:** 76 beat; raw drift +1.96%, ma excess SPY +0.05%, mediana
  -1.07%, tutto sostenuto da cinque outlier. Nessuna dose-response. Gate FAIL
  ([`ALPHA_A5_gate_report_2026-07-03_fmp.md`](../reports/s7_backtest/ALPHA_A5_gate_report_2026-07-03_fmp.md)).
- **Small/mid full universe:** 125 beat liquidi; excess IWM netto medio **-3.47%**, hit 36%.
  Gate pre-registrato conclusivamente FAIL
  ([`POC1_smallmid_report_2026-07-04_full_universe.md`](../reports/s7_poc/POC1_smallmid_report_2026-07-04_full_universe.md)).
- **Transcript tone:** su 48 eventi, IC Spearman `+0.170` e spread terzili `+5.41%`, ma
  split-half `-0.353 / +0.559`; dentro i soli beat IC `+0.039`. Il gate ALPHA-A3 e FAIL per
  instabilita temporale (`scripts/analyze_s7_tone.py` sul CSV corrente).

Questi campioni non dimostrano che PEAD sia morto universalmente. Dimostrano pero che **le
varianti concretamente disponibili ad Alembic non meritano capitale**.

### 4.4 Problemi implementativi S7 da non confondere con il FAIL empirico

1. surprise `%` instabile quando consensus EPS e vicino a zero; manca una misura
   standardized unexpected earnings o analyst forecast error normalizzata;
2. niente timestamp preciso dell'annuncio: rischio di entry prima della disclosure per
   eventi after-close;
3. 20 giorni di calendario nel modello contro 20 sedute nei report;
4. equal weight e first-five invece di ranking continuo surprise/tone/attention;
5. confidence `0.95` costante per ogni evento strutturato, quindi non informativa;
6. guidance e tone esistono nel modello/POC ma non entrano nel target weight;
7. nessuna neutralizzazione sector/beta/size nel modulo;
8. worker limitato alla watchlist corrente, non un universe PIT utile per validazione.
9. il vecchio `pead_worker` presenta all'LLM un "SEC 8-K filing text", ma il connector
   popola `body` soltanto con `period_of_report` ed `entity_name`, non con il documento
   depositato. Quel path non puo estrarre EPS e consensus come promette. Il piu recente
   `earnings_pead_worker` corregge il numero usando actual/estimate strutturati Finnhub,
   ma non aggiunge guidance o testo qualitativo ([`sec_edgar.py`, righe 64-101](../src/connectors/sec_edgar.py),
   [`pead_worker.py`, righe 30-67](../src/workers/pead_worker.py),
   [`earnings_pead_worker.py`, righe 31-52](../src/workers/earnings_pead_worker.py));
10. S7 non e registrata, non viene costruita dal scheduler e non e gestita
    dall'orchestrator. Lo stato Redis e una singola chiave per simbolo, senza storico
    persistente del segnale. Non esiste quindi ancora un audit trail o un percorso paper;
11. i pesi `max_position_pct=0.05` e `max_sleeve_pct=0.25` sono emessi come se fossero
    assoluti, mentre il contratto dell'orchestrator richiede pesi sleeve-local e li scala
    per `allocation_pct`. Prima del wiring va risolta questa semantica per evitare una
    seconda scalatura e un deployment molto diverso da quello dichiarato.

Correggere questi punti e necessario per qualunque nuovo test, ma non e una ragione per
ignorare i FAIL gia osservati. Prima serve una nuova ipotesi pre-registrata, non una
"riparazione" post-hoc del raw PEAD.

### 4.5 Decisione S7

Non finanziare S7 come strategia autonoma `beat -> long 20d`. Mantenere invece i componenti
riusabili:

- calendar e consensus earnings PIT;
- event-time preciso BMO/AMC;
- transcript/guidance evidence bundle;
- benchmark e outcome multi-horizon;
- classificazione qualitative tone come feature shadow di S4 o di un futuro event sleeve.

Una riapertura richiede un'ipotesi diversa e falsificabile, per esempio "tone/guidance
incrementale **condizionato** a surprise, attention load e liquidity", con almeno 300-500
eventi, split temporali multipli, residual IC rispetto ai feature numerici e costi. Il
segnale non deve ricevere peso finche non supera il gate in piu periodi.

## 5. Allocazione consigliata dello sviluppo

### 5.1 S3: investimento con highest expected information value

**Go per un POC offline**, non per paper. E una strategia nota, diversificante rispetto al
news sentiment e potenzialmente complementare a S1. Il POC deve prima rispondere a due
domande:

1. la specifica originale beta-adjusted batte, OOS e net-of-cost, il total momentum 12-1
   costruito nello stesso modo?
2. aggiunge valore al portafoglio dopo aver controllato l'overlap con S1 e dopo aver
   eliminato survivorship e state leakage?

Stop o semplificazione automatica se la correzione beta non batte il total momentum e un
benchmark factor dopo costi. Solo dopo ha senso spendere sulla variante FF3.

### 5.2 S7: investimento nell'infrastruttura, non nella strategia

**No-go sul raw PEAD.** Il valore residuo sta nell'evidence plane event-driven che puo
alimentare S4, ricerca TradingAgents e nuovi segnali. Questo evita sunk-cost escalation e
preserva i componenti con utilita trasversale.

### 5.3 S2: decisione architetturale prima della strategia

**No-go ora**, salvo decisione esplicita di supportare derivati. Una implementazione seria
richiede dati storici di chain, broker/margin, accounting e risk engine dedicati. Il costo e
molto superiore a S3 e non puo essere giustificato dai report attuali. Se l'obiettivo e
studiare economicamente l'esposizione prima del build, usare un benchmark Cboe replicabile
e una serie index-level, senza chiamarlo backtest S2.

## 6. Ordine operativo raccomandato

1. **S3 design-alignment spec:** congelare la variante originale e i comparator, dataset
   PIT, portfolio constraints, provenance artifact e gate correnti pre-registrati.
2. **S3 tracer POC:** correggere prima 12-1, long-only, vol window, cap/normalizzazione,
   universo e isolamento walk-forward; poi A/B offline e solo in seguito C.
3. **Earnings evidence hardening:** event timestamps e consensus versioning, come
   infrastruttura condivisa; nessuna promozione S7.
4. **S7 archival decision:** tenere il codice come research component o rimuovere il sleeve
   in base alla roadmap, senza altri test raw-surprise.
5. **S2 architecture decision:** solo dopo una stima di costo per option data, IBKR paper,
   margin/risk e backtester. Senza budget, resta disabled.

La review decisionale e ora tracciata dalla child issue `#55`, `Part of #21`, etichettata
`wayfinder:decision` e `ready-for-human`. Non e stata assegnata, perche richiede una scelta
PO prima di aprire lavori implementativi. La frontier letta il 2026-07-15 mostrava inoltre
`#38 S7: revival resume (PEAD)` come `ready-for-agent`, tier 2 e assegnata: alla luce dei
risultati disponibili, quel lavoro non dovrebbe diventare un altro tuning del raw PEAD, ma
chiudersi o essere riformulato come archival/evidence-infrastructure. La issue `#53`
raccoglie il backlog S2/S3 e resta `needs-triage`.

## 7. Verifica software eseguita

Sono stati eseguiti i test mirati di strategie, worker e containment:

```text
263 passed, 3 warnings in 13.17s
```

I warning provengono da `tests/workers/test_pead_worker.py`: coroutine mockate
`_fetch_8k_items` e `_classify_filing` risultano non awaited in alcuni test. Non hanno
causato failure, ma indicano che il test harness asincrono del worker S7 non e pulito.

Il pass dei test prova che le funzioni fanno quanto codificato e che il containment evita
capitale accidentale. Non prova equivalenza economica con VRP/residual momentum/PEAD, non
elimina survivorship bias e non rende disponibili i percorsi paper mancanti.

## 8. Risposta sintetica alla domanda

- **Sono universalmente valide?** No. Momentum e il piu generalizzabile; VRP e un premio
  di rischio persistente ma tail-dependent; PEAD e condizionale e spesso assorbito dai
  costi dove e piu forte.
- **Vale la pena svilupparle?** S3 si, prima con riallineamento e POC comparativo; S7 solo
  come infrastruttura/event-tone; S2 solo dopo una decisione strategica sui derivati.
- **Sono implementate correttamente?** S2 no come esposizione economica; S3 no rispetto
  alla propria specifica originale e al PIT universe; S7 e un prototipo coerente ma troppo
  semplice e con timing/holding/ranking incompleti. Nessuna e pronta per paper.

La decisione piu importante e non confondere una classe di anomaly ben documentata con
una implementazione automaticamente valida. In Alembic, oggi, **S3 ha il miglior prior
accademico ma deve prima tornare coerente con il proprio design; S7 ha gia prodotto il
verdetto empirico piu informativo; S2 non e ancora stata realmente testata**.
