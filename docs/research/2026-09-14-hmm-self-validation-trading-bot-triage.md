# Triage: HMM “self-validating” trading bot in MQL5

**Data:** 2026-09-14  
**Articolo:** Javier Santiago Gastón de Iriarte Cabrera, [“I Built a Trading Bot That Refuses to Trade Until It Can Prove It Has an Edge”](https://medium.com/@jsgastoniriartecabrera/i-built-a-trading-bot-that-refuses-to-trade-until-it-can-prove-it-has-an-edge-5c0519308a98), 2026-09-07.  
**Perimetro:** triage, non replica del codice. Fonti probatorie: paper originali e documentazione MetaQuotes.

## Verdetto

**Idea interessante come challenger sperimentale di #580; nessuna prova di edge e nessuna ragione per integrarla ora.** HMM gaussiano, probabilità di stato filtrate e circuit breaker sono componenti plausibili. Il titolo “refuses to trade until it can prove” è però troppo forte: un controllo di edge interno, eseguito dopo ogni retrain su dati già usati o sovrapposti, non è validazione out-of-sample.

I risultati dichiarati — 11.803 barre H4, 103 trade, profit factor 1,89, drawdown 2,12%, Sharpe 3,43 — sono descrittivi di un singolo backtest. Mancano split temporale, trial ledger, incertezza, costi e data-quality sufficienti per un claim confermativo. Inoltre la sezione risultati dice EURUSD H4, mentre la chiusura dice XAUUSD H4: il run non è identificato in modo riproducibile.

## Claim decisivi

### 1. HMM ed EM: formalmente plausibili, ma non auto-identificanti

Baum-Welch è un caso di expectation-maximization: aumenta la likelihood fino a un punto critico, ma la superficie ha molti massimi locali. Rabiner lo dichiara esplicitamente; convergenza dei log non significa modello economicamente corretto ([Rabiner, 1989](https://www.cs.cornell.edu/courses/cs481/2004fa/rabiner.pdf)). Servono più inizializzazioni, likelihood OOS e diagnostiche di stabilità.

I label di stato sono arbitrari: permutare insieme stati, transizioni ed emissioni lascia invariata la likelihood. Dopo ogni retrain “state 0/1/2” può quindi cambiare significato. Occorre un mapping deterministico basato su statistiche delle emissioni, più un gate che rifiuti stati non separabili. Questo requisito è già scritto in #580.

Una Gaussian HMM con covarianza diagonale assume inoltre indipendenza condizionale fra le feature nello stato. Return cumulativo, range e volume possono essere correlati; “diagonal” è una semplificazione da confrontare, non una proprietà dimostrata del mercato.

### 2. Expected duration: formula vera, uso come orizzonte troppo forte

Per un HMM time-homogeneous la permanenza nello stato `i` è geometrica e la durata attesa è:

`E[D_i] = 1 / (1 - A_ii)`.

Rabiner deriva questa relazione. È una **media condizionale del modello**, non il numero di barre che lo stato durerà davvero, né una confidence. Diventa estremamente sensibile a piccoli errori di `A_ii` quando `A_ii` è vicino a 1; con retrain su sole 250 barre e stati poco visitati può essere instabile. Va riportata con occupancy, intervallo/bootstrapping e cap preregistrato, non usata da sola per stop/holding.

### 3. K=5 rolling returns: migliore del single-bar target, ma crea dipendenza meccanica

Due ritorni cumulativi rolling adiacenti a cinque barre condividono quattro barre. Le 250 osservazioni non sono 250 evidenze indipendenti; il loro effective sample size è inferiore. Questo viola l'indipendenza condizionale delle emissioni gaussiane standard e rende un train/validation split confinante contaminato.

La letteratura econometrica originale sugli overlapping returns richiede esplicitamente correzioni per la correlazione seriale indotta ([Hansen e Hodrick, 1980](https://doi.org/10.1086/260910)). Nel test Alembic servono blocchi non sovrapposti oppure purge/embargo di almeno `K-1` barre, aumentato fino all'orizzonte economico dell'etichetta/trade.

### 4. Parkinson: `0.6006 × range` è solo una scorciatoia sotto ipotesi forti

La costante `0.6006 ≈ sqrt(1/(4 ln 2))` appartiene allo stimatore:

`sigma = sqrt(mean(log(H/L)^2) / (4 ln 2))`.

Parkinson assume un processo continuo di diffusione e usa il log high-low range; il paper originale parte da un continuous random walk ([Parkinson, 1980](https://www.cmegroup.com/trading/fx/files/michael_parkinson.pdf)). Moltiplicare il singolo `(H-L)/price` per 0,6006 è soltanto un'approssimazione small-range, molto rumorosa; non gestisce drift, gap o jump e non è automaticamente una previsione della prossima barra. Va confrontato con close-to-close/EWMA e con stimatori gap/drift-robust, usando una finestra causale.

### 5. Tick volume FX/CFD non è volume scambiato

La struttura ufficiale `MqlRates` distingue `tick_volume` (numero di tick nella barra) da `real_volume` (trade/exchange volume) ([MetaQuotes, testing reference](https://www.mql5.com/en/docs/runtime/testing)). Nel Forex spot/CFD il tick count dipende dal feed del broker/liquidity provider e non rappresenta un mercato centralizzato. Può essere un proxy di attività **da validare sul singolo feed**, non una conferma universale della pressione compratori/venditori. Va congelato broker/server e usata solo la barra chiusa.

## Il validation gate non “prova” l'edge

Un gate `positive edge + minimum signals` è utile come fail-closed operativo, ma è confermativo solo se:

1. il modello è fit esclusivamente sul train;
2. edge e numero segnali sono calcolati su un blocco successivo, mai usato per fit/soglie;
3. train e validation sono purged per K-bar feature e holding horizon;
4. il blocco non viene poi assorbito e riusato ripetutamente per scegliere modifiche;
5. formula, soglie, costi e numero totale di varianti sono preregistrati;
6. esiste un ultimo holdout sigillato o una replica forward untouched.

Se il controllo post-retrain usa le stesse 250 barre, o un tratto overlapping, misura in-sample fitness. Se blocca/abilita il bot ripetutamente sullo stesso storico diventa anche parte della strategia da validare, non un validatore indipendente. La sola media positiva non incorpora errore standard, autocorrelazione, costi, tail risk o multiple testing.

## MT5 e il campione di 103 trade

MetaQuotes documenta che il tester può usare real ticks, tick generati da M1, `1 minute OHLC` o open-only; perfino in real-tick mode sostituisce con tick generati i minuti mancanti/incoerenti. Il report deve quindi conservare modalità, percentuale di history/real-tick quality, broker/server e simbolo ([MetaQuotes Strategy Tester](https://www.mql5.com/en/docs/runtime/testing); [Testing Report](https://www.metatrader5.com/en/terminal/help/algotrading/testing_report)).

Mancano nell'articolo: spread variabile, commissioni, swap, slippage, contract specification, timezone/DST, fill policy, deposito/leverage e lista dei parametri provati. Il profit factor e il drawdown non compensano questi vuoti.

103 trade sono troppo pochi per leggere `Sharpe=3.43` come prova senza sapere se MT5 lo calcola su ritorni di equity, periodicità e autocorrelazione. Lo mostra anche la teoria originale: la distribuzione campionaria dello Sharpe cambia fra rendimenti IID e serialmente correlati ([Lo, 2002](https://alo.mit.edu/publications/page/18/)). Come ordine di grandezza, perfino una win rate su 103 trade indipendenti avrebbe errore standard vicino a 5 punti percentuali attorno al 50%; trade clustered/regime-dependent riducono ancora l'informazione effettiva.

## Mapping Alembic

- **#580 è il contenitore corretto.** Include già HMM come estensione, probabilità filtrate, mapping deterministico dei label, walk-forward PIT, purge/embargo, baseline semplici e doppio gate statistico/economico. L'articolo non richiede una nuova issue.
- **#31 è separata.** Riguarda lo stop `vol_scaled`; la calibrazione è già indicata come thin. La durata HMM/Parkinson non deve sostituirla senza confronto preregistrato.
- **#84 trasferisce il metodo**, non il mercato: preregistrazione, holdout 2023-2025 sigillato, trial registry e costi. Il requisito PIT universe azionario non è direttamente risolto da un EA Forex.
- **#171 vieta tarature operative fino al 2026-09-28.** L'articolo può alimentare solo ricerca offline/shadow e non giustifica cambi al money path.

## Da approfondire, solo dentro #580

1. Replica causale con seed multipli, state mapping e confronto HMM vs persistence/EWMA/GARCH.
2. Ablation: single-bar vs K=5, overlapping vs purged, range Parkinson vs alternative robuste, tick volume on/off.
3. Validation gate come oggetto della prova: blocco realmente successivo, holdout untouched, trial count e costi.
4. Artifact MT5 completo: `.set`, versione EA, hash dati, broker/server, symbol, real-tick quality e report XML/HTML.
5. Chiarire e replicare separatamente EURUSD e XAUUSD; la contraddizione attuale è un FAIL di provenance.

**Decisione:** non aprire issue, non accodare una campagna autonoma e non implementare. Conservare l'articolo come candidato/ablation note di #580.
