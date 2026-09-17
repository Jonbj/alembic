# Verifica critica: ML, volatilità, regimi e stop dinamici

**Data:** 2026-09-14  
**Articolo esaminato:** “Why Quants Don’t Use ML to Predict Price (And What They Predict Instead)”, Elara Venn, 2026-09-03  
**Metodo:** confronto claim-per-claim con lavori accademici primari e documentazione ufficiale. L'articolo è stato fornito integralmente dall'utente; non è trattato come fonte probatoria.

## Verdetto

L'articolo contiene una buona intuizione divulgativa — la volatilità ha persistenza e in genere un rapporto segnale/rumore maggiore del rendimento direzionale — ma la trasforma in una falsa dicotomia. La ricerca primaria mostra sia applicazioni ML alla previsione della volatilità sia applicazioni ML alla previsione dei rendimenti. Non esiste evidenza pubblica sufficiente per la generalizzazione professionale “i quant raramente prevedono la direzione”.

Per Alembic la parte utile non è un nuovo modello da copiare, ma una conferma del problema già affrontato dal redesign degli stop: una soglia fissa può essere sub-σ e produrre stop su rumore. La soluzione interna è però più prudente dell'articolo: distanza calibrata sulla volatilità, congelata all'ingresso, mai allargata durante la posizione, con sizing sul rischio monetario e buffer per i gap. La formula proposta dall'articolo con una “liquidation cascade probability” non ha supporto identificabile e non dovrebbe entrare nel sistema.

**Valutazione:** interessante come spunto divulgativo, non idoneo come fonte scientifica o specifica di implementazione. Non va messo nel corpus di ricerca dei nodi. Gli eventuali esperimenti devono partire dalle fonti primarie e dall'attuale shadow mode di Alembic.

## Audit dei claim

| Claim dell'articolo | Valutazione | Evidenza primaria |
|---|---|---|
| I modelli ML direzionali “quasi universalmente falliscono” live | **Eccessivo e non dimostrato** | La previsione del rendimento è a basso SNR, ma Gu, Kelly e Xiu trovano guadagni out-of-sample ed economici da alberi e reti neurali nella previsione cross-sectional dei premi al rischio. Il risultato non equivale a prevedere correttamente il segno di un singolo titolo domani, ma smentisce la tesi assoluta che ML non venga utilmente applicato ai rendimenti ([NBER WP 25398](https://www.nber.org/papers/w25398), versione pubblicata DOI [10.1093/rfs/hhaa009](https://doi.org/10.1093/rfs/hhaa009)). Nel 2026 un lavoro RFS costruisce esplicitamente rendimenti attesi stock-level con ML e mostra che costi di trading e implementabilità sono il vero collo di bottiglia, non l'assenza totale di segnale ([DOI 10.1093/rfs/hhag022](https://doi.org/10.1093/rfs/hhag022)). |
| La volatilità è più prevedibile della direzione grazie al clustering | **Sostanzialmente corretto** | ARCH/GARCH formalizzano varianza condizionale persistente ([Engle 1982, DOI 10.2307/1912773](https://doi.org/10.2307/1912773); [Bollerslev 1986, DOI 10.1016/0304-4076(86)90063-1](https://doi.org/10.1016/0304-4076(86)90063-1)). Realized volatility e HAR-RV sfruttano dati intraday e persistenza a più orizzonti ([Andersen et al. 2003, DOI 10.1111/1468-0262.00418](https://doi.org/10.1111/1468-0262.00418); [Corsi 2009, DOI 10.1093/jjfinec/nbp001](https://doi.org/10.1093/jjfinec/nbp001)). È però impreciso dire che i *returns* siano continuamente non stazionari: sono prezzi, rendimenti e distribuzioni condizionali a richiedere ipotesi e test distinti. |
| Passare da direzione a magnitudine produce automaticamente “genuine predictive validity” | **Direzione giusta, garanzia falsa** | La persistenza rende la volatilità un target più favorevole, ma la validità dipende da asset, orizzonte, proxy e loss. Hansen e Lunde confrontano 330 specifiche: GARCH(1,1) non viene battuto sui cambi, mentre su IBM è superato da modelli con leverage effect ([DOI 10.1002/jae.800](https://doi.org/10.1002/jae.800)). Quindi non esiste un vincitore universale. |
| XGBoost/LightGBM sono il modo professionale per prevedere la varianza | **Plausibile, non stabilito** | Christensen, Siggaard e Veliyev trovano che più famiglie ML siano competitive e battano vari HAR sulla realized variance dei componenti Dow Jones, soprattutto a orizzonti lunghi ([arXiv:2601.13014](https://arxiv.org/abs/2601.13014)). Un confronto 2026 fra foundation models e benchmark econometrici trova invece vantaggi piccoli, concentrati in pochi asset e in parte dovuti alla calibrazione; Log-HAR resta competitivo ([arXiv:2607.05291](https://arxiv.org/abs/2607.05291)). La conclusione corretta è “ML va confrontato con EWMA/GARCH/HAR/Realized-GARCH”, non “ML sostituisce GARCH”. |
| Garman–Klass è “far superior” alla deviazione standard | **Vero solo sotto ipotesi specifiche** | L'estimatore OHLC originale ha efficienza teorica molto superiore agli stimatori close-to-close nel modello mantenuto dagli autori ([Garman e Klass 1980, DOI 10.1086/296072](https://doi.org/10.1086/296072)). Non segue che sia sempre superiore con drift, salti, overnight gap, trading discontinuo o microstructure noise. Va trattato come uno dei proxy, non come ground truth. |
| Order-book imbalance è una feature non lineare di volatilità | **Uso confuso** | L'evidenza primaria mostra soprattutto potere sul *segno del prossimo movimento* del mid-price e relazione fra order-flow imbalance e variazione di prezzo ([Cont, Kukanov e Stoikov, arXiv:1011.6402](https://arxiv.org/abs/1011.6402); [Gould e Bonart, arXiv:1512.03492](https://arxiv.org/abs/1512.03492)). Può informare liquidità/slippage o rischio di breve, ma non è automaticamente un predittore di varianza. Inoltre reintroduce proprio una componente direzionale che l'articolo dichiara inutile. |
| HMM/GMM identificano in tempo reale compression, expansion e cascade | **Metodo plausibile; tassonomia e uso operativo non dimostrati** | Hamilton introduce regimi latenti Markoviani e inferenza probabilistica su cambi discreti ([Econometrica 1989, DOI 10.2307/1912559](https://doi.org/10.2307/1912559)). HMM sono stati applicati a regimi bull/bear/alta volatilità con esempi out-of-sample ([Werge 2022, DOI 10.1016/j.eswa.2021.115576](https://doi.org/10.1016/j.eswa.2021.115576)). Ma un GMM statico non modella la persistenza temporale; un HMM sì. Né il nome economico dei cluster né “alta volatilità ⇒ trend ottimale” discendono dall'algoritmo. Le probabilità real-time devono essere **filtrate**, non smoothed/Viterbi su tutto il campione. |
| Alta volatilità richiede stop più larghi e size più piccola | **Identità di risk budgeting ragionevole, non legge empirica universale** | Ridurre l'esposizione quando la volatilità cresce ha supporto in Moreira e Muir ([DOI 10.1111/jofi.12513](https://doi.org/10.1111/jofi.12513)), ma una verifica più ampia su 103 strategie non trova un miglioramento out-of-sample sistematico e segnala instabilità strutturale ([Cederburg et al. 2020, DOI 10.1016/j.jfineco.2020.04.015](https://doi.org/10.1016/j.jfineco.2020.04.015)). Questi lavori riguardano esposizione/portfolio scaling, non dimostrano una specifica regola di stop. |
| Gli stop fissi sono una ragione primaria delle liquidazioni retail | **Non supportato e terminologicamente improprio** | Uno stop è un ordine di uscita; una liquidazione è una chiusura forzata per insufficienza di margine. Kaminski e Lo mostrano che, con random walk, lo stop riduce il rendimento atteso; può aiutare in processi con momentum. Lo e Remorov mostrano che stop stretti possono perdere per costi e che il risultato dipende dall'autocorrelazione ([DOI 10.1016/j.finmar.2013.07.001](https://doi.org/10.1016/j.finmar.2013.07.001); [DOI 10.1016/j.finmar.2017.02.003](https://doi.org/10.1016/j.finmar.2017.02.003)). Non emerge una condanna generale dello stop fisso né il nesso causale con la liquidazione. |
| `stop = k × predicted_vol × (1 + cascade_probability)`, con `k=2–3` | **Formula ad hoc, nessuna fonte identificata** | Esistono evidenze che leverage e liquidazioni amplifichino stress nei mercati crypto ([BIS, *Crypto carry*](https://www.bis.org/publ/work1087.pdf); [BIS, *DeFi leverage*](https://www.bis.org/publ/work1171.pdf)), ma non supportano questa formula, il range 2–3 o una probabilità comparabile tra asset. La formula mescola una deviazione standard con un classificatore di evento estremo senza calibrazione, loss function o derivazione economica. Non è trasferibile alle azioni Alembic. |
| Allargare lo stop e ridurre la size mantiene il rischio in dollari costante | **Solo in un modello senza gap/slippage** | Se il budget è `R` e la distanza frazionaria è `d`, `notional <= R/d` è aritmeticamente coerente. Ma un ordine stop diventa market e il prezzo di esecuzione non è garantito, soprattutto in mercati veloci o dopo un gap ([FINRA Regulatory Notice 16-19](https://www.finra.org/rules-guidance/notices/16-19); [documentazione ordini Alpaca](https://docs.alpaca.markets/us/docs/orders-at-alpaca)). Proprio durante una cascade l'ipotesi di perdita limitata a `d` è più fragile. Servono gap buffer, slippage stress e limiti aggregati. |

## Il punto più pericoloso: “dynamic widening”

Aggiornare la volatilità durante una posizione e spostare più lontano lo stop può aumentare il rischio *dopo* l'ingresso e trasformare una regola protettiva in una regola path-dependent. L'articolo non specifica:

- se lo stop possa solo stringersi o anche allargarsi;
- quando venga ricalcolato e con quale latenza;
- come cambi la size di una posizione già aperta;
- cosa accada con gap, halt, partial fill, spread e costi;
- come vengano gestite correlazioni e rischio aggregato della sleeve.

La specifica Alembic evita esplicitamente questo difetto: calcola `σ_eff`, `k`, floor, cap e `d_init` all'ingresso e li congela; lo stop protettivo non si allarga. La size è limitata da:

```text
notional <= NAV × budget_per_position / (d_init + gap_buffer)
```

Questo approccio è già descritto in [Stop-Loss Redesign](../superpowers/plans/2026-07-11-stop-loss-redesign.md) e implementato in [`src/portfolio/stop_policy.py`](../../src/portfolio/stop_policy.py). Il default corrente resta `stop_loss_mode: fixed`; la modalità `vol_scaled` è quindi una candidata da valutare in shadow/replay, non una modifica live giustificata dall'articolo.

## HMM e GMM: controlli indispensabili

Per un esperimento serio sui regimi:

1. **Separare identificazione e previsione.** Un cluster che descrive bene il passato non predice necessariamente lo stato successivo o il P&L di una policy.
2. **Usare solo probabilità filtrate:** `P(S_t | F_t)`. Le probabilità smoothed `P(S_t | F_T)` usano dati futuri e producono look-ahead.
3. **Fit nel solo training window.** Standardizzazione, PCA, GMM/HMM, numero di stati e mapping dei label vanno rifatti nel walk-forward senza vedere il test.
4. **Gestire label switching.** “Regime 0” non mantiene automaticamente lo stesso significato tra refit; serve un mapping deterministico basato su statistiche del training.
5. **Confrontare con baseline semplici.** Soglie su EWMA/realized vol/VIX e un Markov-switching econometrico devono essere inclusi; HMM/GMM hanno valore solo se migliorano calibrazione o utilità netta.
6. **Penalizzare turnover e ritardo.** Uno stato inferito con ritardo o molto instabile può peggiorare costi ed esecuzione anche con buona classificazione retrospettiva.

## Leakage, nonstationarity e point-in-time

L'articolo omette i rischi principali di un progetto Alembic:

- **Overlap del target:** una label di volatilità sui prossimi `N` intervalli si sovrappone tra esempi vicini; train/validation richiedono purge/embargo almeno pari all'orizzonte.
- **Feature leakage:** scaler, imputazione, winsorization, PCA e selezione feature devono essere fittati soltanto sul passato.
- **Revisioni e disponibilità:** corporate actions, composizione dell'universo e variabili fondamentali/macro devono essere ricostruite secondo ciò che era disponibile al decision timestamp, non nella versione revisionata oggi.
- **Clock di mercato:** order book, trade, news e barra devono avere event time e arrival time; una feature pubblicata dopo la decisione non è point-in-time anche se condivide la stessa barra.
- **Survivorship bias:** includere delisting e universo storico reale.
- **Nonstationarity:** usare walk-forward/expanding windows, monitorare drift e calibrazione per periodo; non scegliere la finestra ex post.
- **Ricerca ripetuta:** registrare tutte le varianti provate. La selezione fra molti modelli e iperparametri gonfia la performance apparente; il problema è documentato da test di data-snooping e backtest overfitting ([Hansen e Lunde 2005](https://doi.org/10.1002/jae.800); [Bailey e López de Prado 2021](https://doi.org/10.1111/1740-9713.01588)).
- **Contaminazione dei modelli preaddestrati:** un modello addestrato sull'intera storia può conoscere il test. Un benchmark 2026 per agenti AI in asset pricing identifica esplicitamente il look-ahead da pretraining e propone una valutazione realmente real-time ([Koijen e Levy, NBER WP 35431](https://www.nber.org/papers/w35431)).

## Esperimento raccomandato per Alembic

Non implementare la pipeline dell'articolo. Se si vuole approfondire, l'esperimento minimo difendibile è:

1. **Target:** realized variance a 1 giorno e all'orizzonte reale delle strategie; definizione e calendario congelati prima del test.
2. **Baseline:** naive persistence, EWMA/STD già usato da Alembic, GARCH con leverage effect e HAR-RV quando sono disponibili dati intraday.
3. **Challenger ML:** prima gradient boosting, poi eventualmente una rete; stessi input e stesso walk-forward dei benchmark.
4. **Metriche:** QLIKE e MSE/RMSE, calibrazione, tail loss, turnover e utilità/P&L netto; test Diebold–Mariano/Model Confidence Set senza scegliere una metrica ex post.
5. **Uso del forecast:** inizialmente solo sizing delle nuove posizioni e shadow stop. Non allargare lo stop di una posizione aperta.
6. **Regimi:** aggiungerli solo se forniscono valore incrementale oltre la previsione continua di volatilità. Nessuna etichetta “cascade” senza dati specifici di leverage, open interest, liquidazioni, spread e profondità.
7. **Gate:** promozione solo dopo replay PIT, periodo shadow bloccato in anticipo e confronto netto dei costi con la policy corrente.

## Conclusione operativa

- **Non accodare l'articolo** come fonte di ricerca.
- **Non aprire una nuova linea HMM/GMM** sulla sola base dell'articolo.
- **Conservare la tesi testabile:** volatility-scaled sizing/stop può ridurre i false stop rispetto al 2% fisso.
- **Rigettare la ricetta:** stop dinamicamente allargato e fattore `1 + cascade_probability` non sono supportati.
- **Approfondimento utile:** confronto point-in-time tra la policy Alembic esistente e baseline EWMA/GARCH/HAR più un challenger gradient boosting, in shadow/replay.

## Fonti primarie essenziali

1. Engle, R. F. (1982), “Autoregressive Conditional Heteroscedasticity…”, *Econometrica*. [DOI](https://doi.org/10.2307/1912773)
2. Bollerslev, T. (1986), “Generalized Autoregressive Conditional Heteroskedasticity”, *Journal of Econometrics*. [DOI](https://doi.org/10.1016/0304-4076(86)90063-1)
3. Andersen, Bollerslev, Diebold e Labys (2003), “Modeling and Forecasting Realized Volatility”, *Econometrica*. [DOI](https://doi.org/10.1111/1468-0262.00418)
4. Corsi, F. (2009), “A Simple Approximate Long-Memory Model of Realized Volatility”, *Journal of Financial Econometrics*. [DOI](https://doi.org/10.1093/jjfinec/nbp001)
5. Gu, Kelly e Xiu (2020), “Empirical Asset Pricing via Machine Learning”, *Review of Financial Studies*. [NBER](https://www.nber.org/papers/w25398)
6. Christensen, Siggaard e Veliyev (2026), “A Machine Learning Approach to Volatility Forecasting”. [arXiv](https://arxiv.org/abs/2601.13014)
7. Hamilton, J. D. (1989), “A New Approach to the Economic Analysis of Nonstationary Time Series and the Business Cycle”, *Econometrica*. [DOI](https://doi.org/10.2307/1912559)
8. Kaminski e Lo (2014), “When Do Stop-Loss Rules Stop Losses?”, *Journal of Financial Markets*. [DOI](https://doi.org/10.1016/j.finmar.2013.07.001)
9. Lo e Remorov (2017), “Stop-Loss Strategies with Serial Correlation, Regime Switching, and Transaction Costs”, *Journal of Financial Markets*. [DOI](https://doi.org/10.1016/j.finmar.2017.02.003)
10. Moreira e Muir (2017), “Volatility-Managed Portfolios”, *Journal of Finance*. [DOI](https://doi.org/10.1111/jofi.12513)
11. Cederburg et al. (2020), “On the Performance of Volatility-Managed Portfolios”, *Journal of Financial Economics*. [DOI](https://doi.org/10.1016/j.jfineco.2020.04.015)
12. FINRA (2016), “Regulatory Notice 16-19: Risks of Stop Orders”. [Documento ufficiale](https://www.finra.org/rules-guidance/notices/16-19)
