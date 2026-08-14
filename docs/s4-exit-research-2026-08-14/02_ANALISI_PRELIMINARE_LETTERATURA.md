# S4: ricognizione preliminare della letteratura sulle strategie di uscita

**Data:** 2026-08-14  
**Stato:** ricerca preliminare, non decisione di implementazione  
**Scopo:** chiarire quali famiglie di exit abbiano basi teoriche o empiriche utili per S4 e quali domande debbano essere affidate a una successiva ricerca multi-modello. Non propone tuning né modifica la pre-registrazione vigente.

## Sintesi

La letteratura primaria non identifica una regola d'uscita universalmente superiore. Il risultato più robusto è **condizionale al processo dei rendimenti, alla persistenza dell'alpha, ai costi e alla frequenza di osservazione**:

- gli stop-loss stretti tendono a ridurre il rendimento atteso quando i prezzi sono prossimi a un random walk o mean-reverting e, sulle azioni USA, spesso perdono contro buy-and-hold dopo i costi;
- stop più larghi, trailing e gestione dell'esposizione in funzione della volatilità possono ridurre varianza, drawdown o downside risk, ma non implicano automaticamente maggior rendimento medio;
- take-profit, stop-loss e time-stop sono **barriere congiunte**: ottimizzarne una isolatamente cambia il valore delle altre e introduce selezione ex post;
- per una strategia news-driven, l'uscita più difendibile parte dal **decadimento misurato del segnale e dalla sua invalidazione**, non dall'età editoriale dell'articolo né da una percentuale di P&L scelta genericamente;
- la letteratura sulle news mostra sia continuazione per più giorni sia reversal quando la notizia è stantia o il contenuto cattura sentiment anziché fondamentali. Quindi un time-stop a due sedute è un'ipotesi plausibile da testare, non una durata già validata dalla letteratura;
- costi, slippage condizionato, monitoraggio discreto delle barriere e ordine intrabar dei trigger possono ribaltare la graduatoria delle exit;
- il principale rischio metodologico è scegliere la migliore fra molte combinazioni di durata, stop e target. Reality Check/SPA, PBO/CSCV, pre-registrazione e un vero segmento OOS sono parte della strategia d'uscita, non controlli opzionali.

La conclusione preliminare per S4 è quindi: **conservare come baseline confirmatoria la configurazione già pre-registrata (time-stop D+2, contro-segnale, stop catastrofale), e usare le altre exit come ipotesi shadow concorrenti in una fase esplorativa separata**. La ricerca successiva dovrebbe verificare soprattutto: decay per tipo/novità della news, uscita graduale o no-trade band, trailing/volatility stop solo come controllo del downside, e coerenza reale delle protezioni broker.

## 1. Che cos'è S4 e quali exit risultano dal repository

### 1.1 Strategia

S4 è un overlay tattico long-only guidato da news e sentiment. Ordina trasversalmente i segnali, seleziona fino a cinque titoli e assegna slot uguali; lo sleeve è limitato al 10% ([config S4](../../src/strategies/s4/config.py#L9), [strategia](../../src/strategies/s4/strategy.py#L22)). L'ingresso live usa segnali freschi e un gate di score a monte; `max_signal_age_hours=4` è dichiarato nella configurazione ([config S4](../../src/strategies/s4/config.py#L38)).

### 1.2 Exit osservabile oggi nel codice/configurazione

La superficie attuale non è una singola exit, ma la composizione seguente:

| Meccanismo | Stato rilevato | Osservazione |
|---|---|---|
| **Caduta dal target/ranking** | il core chiude una posizione assente dai nuovi target ([strategy.py](../../src/strategies/s4/strategy.py#L101)) | Nel percorso portfolio può dipendere da ranking, gate, filtri o vincoli; non coincide necessariamente con decadimento economico dell'alpha. |
| **Scadenza del segnale** | FIX-D preserva un vecchio segnale positivo per una posizione aperta se non esiste un segnale fresco sul simbolo ([scheduler](../../src/workers/portfolio_scheduler.py#L714)) | Correzione concettualmente fondata: silenzio informativo non equivale a contro-segnale. Resta possibile una weight-drop per altre cause. |
| **Contro-segnale sentiment** | force-sell sotto `-0,20`, solo segnale ensemble non-fallback e vecchio al massimo 60 minuti ([config](../../src/config.py#L264), [scheduler](../../src/workers/portfolio_scheduler.py#L4166)) | La pre-registrazione shadow usa invece `≤ -0,30`: la differenza va trattata esplicitamente, non fusa nei risultati storici. |
| **Hold minimo / hysteresis** | 90 minuti e due cicli consecutivi per le SELL di rebalance; stop e reversal bypassano entrambi ([trading.yaml](../../config/trading.yaml#L151), [scheduler](../../src/workers/portfolio_scheduler.py#L1545)) | È una forma di inaction band temporale, utile contro il churn ma non calibrata sul valore economico del segnale. |
| **Stop sintetico ordinario** | stop fisso al 2% disabilitato (`stop_loss: 0.0`); shadow di stop volatility-scaled ([trading.yaml](../../config/trading.yaml#L171)) | Il replay interno citato dal repository trovava gli stop stretti peggiori del no-stop; è coerente con molta letteratura, ma non sostituisce una validazione S4-specifica pulita. |
| **Disaster stop broker** | `d_hard` volatility-based 12–20%; il codice abilita di default stop GTC sul floor di azioni intere delle posizioni frazionarie ([config](../../src/config.py#L230), [sync](../../src/workers/portfolio_scheduler.py#L639), [planner](../../src/portfolio/fractional_stop_orders.py#L69)) | Il residuo sotto un'azione non è protetto. Il commento YAML parla ancora di sola telemetria shadow: serve riconciliare configurazione dichiarata, env runtime e ordini broker effettivi. |
| **Take-profit broker** | default +6%, ma solo per BUY non-fractionable con bracket abilitato ([config](../../src/config.py#L217), [submit](../../src/workers/portfolio_scheduler.py#L3961)) | L'exit dipende quindi dalla frazionabilità del titolo, non dall'ipotesi economica S4. È una divergenza da verificare, non una strategia coerente già dimostrata. |
| **Controlli di regime/portafoglio** | VIX 40, variazione VIX 30%, drawdown 5% dichiarati ([trading.yaml](../../config/trading.yaml#L162)) | Va distinto se ciascun controllo blocca nuovi ingressi, riduce esposizione o liquida: sono politiche economicamente diverse. |

Inoltre `rebalance_frequency=DAILY` è dichiarata in S4, ma S4 è esclusa dal set di strategie il cui clock viene ripristinato fra cicli; il commento dice esplicitamente che ciò lascia attive decisioni intraday ed exit weight-drop ([scheduler](../../src/workers/portfolio_scheduler.py#L405)). Questo conferma che lo storico recente misura in parte il lifecycle del software, non una exit economica isolata.

### 1.3 Baseline già pre-registrata

La configurazione confirmatoria futura è diversa dallo storico: shadow end-to-end, uscita primaria alla chiusura di D+2, sole eccezioni per contro-segnale `≤ -0,30` e stop di rischio; la freschezza a quattro ore resta solo un filtro d'ingresso ([pre-registrazione](../evidence/PREREGISTRAZIONE_S4_ORIZZONTE_2026-08-14.md#L87)). Il protocollo congela una sola configurazione e richiede IC, economia netta e integrità operativa congiuntamente. Questa ricognizione non è una ragione per cambiarlo dopo aver visto i dati.

## 2. Evidenze per famiglia di uscita

### 2.1 Stop-loss fissi

**Evidenza teorica ed empirica.** Kaminski e Lo dimostrano che, sotto random walk, uno stop-loss riduce sempre il rendimento atteso; può aggiungere valore con sufficiente momentum/serial correlation e può ridurre la varianza passando a un asset meno rischioso. Nel loro esempio su futures 1993–2011 alcune politiche a frequenza più lunga migliorano rendimento e volatilità ([Kaminski & Lo 2014](https://doi.org/10.1016/j.finmar.2013.07.001)). Lo e Remorov incorporano autocorrelazione, regime switching e costi e, su azioni USA 1964–2014, trovano che gli stop stretti tendono a sottoperformare per eccesso di turnover; l'outperformance richiede autocorrelazione abbastanza elevata e la riduzione del downside è spesso modesta ([Lo & Remorov 2017](https://doi.org/10.1016/j.finmar.2017.02.003)).

**Limite di trasferibilità.** S4 non è buy-and-hold né time-series momentum puro; entra dopo una news e il suo alpha potrebbe essere continuativo, mean-reverting o già esaurito al fill. La letteratura non giustifica né un 2% né qualunque altra percentuale fissa senza prima stimare MFE/MAE, volatilità condizionale e autocorrelazione post-segnale.

**Ipotesi per S4, non evidenza.** Uno stop fisso stretto non dovrebbe essere la prima variante da testare. Un disaster stop largo può avere funzione di limite di perdita e continuità operativa anche se non migliora l'expected return; va giudicato su expected shortfall, gap loss e probabilità di rovina oltre che su P&L medio.

### 2.2 Trailing e volatility-scaled stops

**Evidenza teorica.** Glynn e Iglehart derivano distribuzione, media, varianza e durata di un trailing stop sotto random walk/Brownian motion a drift positivo, mostrando esplicitamente che la distanza del trailing è un parametro del processo, non una costante universale ([Glynn & Iglehart 1995](https://doi.org/10.1287/mnsc.41.6.1096)). Leung e Zhang formulano ingresso e uscita con trailing come double-stopping con maturità path-dependent; in alcuni modelli un limit/take-profit insieme al trailing è ottimale ([Leung & Zhang 2021](https://doi.org/10.1007/s00245-019-09559-0)).

**Evidenza empirica.** Su azioni USA 1926–2016, Dai et al. trovano trailing inferiori a un benchmark mean-variance per rendimento medio ma utili nel ridurre rischio totale e downside, soprattutto nei mercati in calo; gli stop stretti soffrono i costi, mentre soglie più larghe restano più robuste. Il 20% è il compromesso del loro campione, non un numero trasferibile a S4 ([Dai et al. 2021](https://doi.org/10.1111/irfi.12328)).

**Ipotesi per S4.** Un trailing/volatility stop va trattato come overlay di rischio, non come fonte presunta di alpha. La variante utile è monotona e congelata all'ingresso o ratcheted in modo esplicito; una soglia che si allarga quando la volatilità aumenta può aumentare la perdita massima proprio durante uno shock. Il confronto deve includere stop fisso largo, volatility stop, trailing volatility stop e nessuno stop ordinario, a parità di sizing ex ante.

### 2.3 Take-profit e sistemi a barriere congiunte

**Evidenza teorica.** Imkeller e Rogers studiano insieme stop fissi/mobili, barriere di perdita e profitto e costi: i livelli sono una soluzione congiunta, non knob indipendenti ([Imkeller & Rogers 2014](https://doi.org/10.1137/130911706)). In un modello OU mean-reverting con costi, Leung e Li mostrano che alzare lo stop-loss abbassa il take-profit ottimale ([Leung & Li 2015](https://doi.org/10.1142/S021902491550020X)). Questi sono risultati model-based, non prove che S4 sia mean-reverting.

**Evidenza di microstruttura.** Ordini FX reali si concentrano a numeri tondi: take-profit sui livelli e stop-loss subito oltre; il clustering è associato a reversal e accelerazioni prevedibili ([Osler 2003](https://doi.org/10.1111/1540-6261.00588)). Attorno ai cluster di stop-loss, i movimenti FX risultano più rapidi, ampi e persistenti, compatibili con cascata di liquidità, senza prova causale definitiva ([Osler 2005](https://doi.org/10.1016/j.jimonfin.2004.12.002)).

**Ipotesi per S4.** Il take-profit +6% applicato solo ai titoli non-fractionable non ha una base economica uniforme. Una ricerca seria deve confrontare simultaneamente upper/lower/time barrier e stressare slippage agli stop; un target fisso può troncare proprio le rare code positive che finanziano una strategia event-driven.

### 2.4 Time-stop e decadimento delle news

**Evidenza empirica favorevole a una tenuta multi-day.** Tetlock, Saar-Tsechansky e Macskassy trovano che le parole negative in news firm-specific predicono fondamentali e che i prezzi sottoreagiscono brevemente, in particolare nel giorno successivo; i profitti ad alta frequenza possono però sparire con costi ragionevoli ([Tetlock et al. 2008](https://doi.org/10.1111/j.1540-6261.2008.01362.x)). Usando news Dow Jones ad alta frequenza, Jiang, Li e Wang trovano continuazione nella direzione della reazione iniziale per più giorni, con strategia a una settimana ancora profittevole dopo costi nel loro campione 2000–2012 ([Jiang, Li e Wang 2021](https://doi.org/10.1016/j.jfineco.2021.04.003)). Chan documenta drift soprattutto dopo cattive news e più forte su titoli piccoli/illiquidi ([Chan 2003](https://doi.org/10.1016/S0304-405X(03)00146-6)).

**Controevidenza/eterogeneità.** Il pessimismo dei media aggregato può generare pressione seguita da reversal ([Tetlock 2007](https://doi.org/10.1111/j.1540-6261.2007.01232.x)). Le news testualmente stantie producono una reazione più piccola ma il rendimento del giorno della news predice reversal nella settimana successiva, soprattutto con trading retail elevato ([Tetlock 2011](https://doi.org/10.1093/rfs/hhq141)). Dunque novità, fonte, contenuto fondamentale, liquidità e risposta iniziale cambiano anche il segno del profilo post-evento.

**Ipotesi per S4.** D+2 è una baseline plausibile perché separa freschezza editoriale e holding period ed è nell'ordine di grandezza del drift breve, ma la letteratura non “conferma due giorni”. Prima di confrontare exit occorre stimare una term structure post-fill a 15m/1h/close/D+1/D+2/D+3/D+5, stratificata almeno per news nuova/stale, fondamentale/non fondamentale, gap/intraday e liquidità. Gli split sono diagnostici; un solo orizzonte deve restare confirmatorio.

### 2.5 Exit per invalidazione del segnale o indicator reversal

**Evidenza.** Brock, Lakonishok e LeBaron trovano valore predittivo nei segnali buy/sell di medie mobili e trading-range break sul DJIA 1897–1986 ([Brock et al. 1992](https://doi.org/10.1111/j.1540-6261.1992.tb04681.x)). Ma una rivalutazione su 1897–2011 con false-discovery control, persistenza e costi conclude che le regole migliori non sono selezionabili affidabilmente ex ante e che piccoli costi ne annullano la performance ([Bajgrowicz & Scaillet 2012](https://doi.org/10.1016/j.jfineco.2012.06.001)). In un modello a regimi, Dai, Zhang e Zhu fanno dipendere la liquidazione dalla probabilità filtrata che il bull market sia finito, tramite soglie di optimal stopping ([Dai et al. 2010](https://doi.org/10.1137/090770552)).

**Ipotesi per S4.** Il contro-segnale è concettualmente più vicino alla falsificazione dell'idea d'ingresso di un P&L stop. Tuttavia un singolo score LLM rumoroso non è una stima affidabile dello stato. Vanno testati threshold asimmetrici, persistenza per più osservazioni, quantità di nuova informazione, affidabilità ensemble e de-risking parziale. La soglia non può essere scelta sulla stessa finestra usata per valutare l'exit.

### 2.6 Regime e risk exits

**Evidenza favorevole.** Ridurre esposizione quando la volatilità è alta ha aumentato Sharpe e utility su più fattori e carry nel campione di Moreira e Muir ([Moreira & Muir 2017](https://doi.org/10.1111/jofi.12513)); il risk management elimina quasi i crash e quasi raddoppia lo Sharpe del momentum in Barroso e Santa-Clara ([2015](https://doi.org/10.1016/j.jfineco.2014.11.010)).

**Controevidenza.** Su 103 strategie, Cederburg et al. non trovano un beneficio OOS sistematico dal volatility management e documentano instabilità e performance real-time spesso peggiore ([Cederburg et al. 2020](https://doi.org/10.1016/j.jfineco.2020.04.015)). Un lavoro successivo mostra che le versioni semplici possono fallire OOS o dopo i costi e propone un modello multifattoriale condizionale più complesso ([DeMiguel et al. 2024](https://doi.org/10.1111/jofi.13395)).

**Ipotesi per S4.** Prima di introdurre una exit binaria VIX-on/VIX-off, testare il regime come moltiplicatore continuo di size o come gate di ingresso. Uscire da singole posizioni per volatilità di mercato può confondere rischio comune e invalidazione della news. Il valore va misurato incrementale rispetto ai controlli di portafoglio già esistenti.

### 2.7 Optimal stopping, incertezza dell'edge ed exit graduale

**Evidenza teorica.** Con drift ignoto, l'optimal liquidation dipende dalla credenza aggiornata sull'edge e dal regime di volatilità, non dal solo P&L realizzato ([Vaicenavicius 2020](https://doi.org/10.1007/s00245-018-9518-5)). Con rendimenti prevedibili e costi, la posizione ottimale si muove gradualmente verso un target che anticipa i futuri target attesi (“aim in front of the target”), anziché passare sempre da pieno investimento a zero ([Gârleanu & Pedersen 2013](https://doi.org/10.1111/jofi.12080)). La teoria classica con costi produce regioni di non-intervento delimitate da barriere, non rebalancing continuo ([Davis & Norman 1990](https://doi.org/10.1287/moor.15.4.676)).

**Ipotesi per S4.** Due strategie consolidate ma non ancora esplicitamente rappresentate sono:

1. **de-risking graduale**, per esempio 100% → 50% → 0 in funzione della posterior confidence o del decadimento del segnale;
2. **no-trade band state-based**, in cui un piccolo calo di rank/score non provoca exit, ma una variazione sufficientemente grande sì.

L'hysteresis a due cicli corrente è un'approssimazione temporale della seconda idea, ma non usa costi, volatilità o forza del segnale per definire la banda.

## 3. Barriere, path dependence e costi di esecuzione

### 3.1 Il percorso conta

Trailing e combinazioni stop-loss/take-profit/time-stop dipendono dal massimo raggiunto e da quale barriera viene toccata per prima. Il monitoraggio discreto non equivale a quello continuo: Broadie, Glasserman e Kou derivano una correzione di continuità proporzionale a `σ√Δt` per opzioni barriera ([1997](https://doi.org/10.1111/1467-9965.00035)). Non è una formula da applicare meccanicamente agli stop S4, ma prova che una simulazione a close o OHLC può classificare diversamente gli hit rispetto a un feed intraday.

Il “triple barrier method” combina upper, lower e vertical barrier ed è utile per label ed event-outcome coerenti. L'evidenza accademica diretta è ancora giovane: su crypto, Grądzki et al. trovano risultati migliori del next-bar labeling nel loro specifico esperimento ([2025](https://doi.org/10.1186/s40854-025-00866-w)). Non dimostra che triple barrier ottimizzi l'exit di S4; è soprattutto una buona struttura per generare outcome e confrontare politiche senza cambiare definizione a posteriori.

### 3.2 Trigger economico ed esecuzione sono problemi distinti

Una volta deciso di uscire, liquidare immediatamente o a tranche è un problema costo-rischio. Almgren e Chriss separano market impact e rischio di esecuzione in una frontiera ottimale ([2001](https://doi.org/10.21314/JOR.2001.041)). Per S4, oggi piccolo e molto liquido, l'impatto proprio può essere limitato, ma spread, gap e cascata agli stop non sono i.i.d. L'analisi deve riportare decision price, primo prezzo eseguibile, fill broker, slippage, spread e latenza separatamente.

### 3.3 No-trade region e churn

Con costi proporzionali, la teoria produce una regione in cui non conviene negoziare ([Davis & Norman 1990](https://doi.org/10.1287/moor.15.4.676)). In un modello multi-periodo con più asset, ignorare costi e agire miopicamente può generare perdite economiche rilevanti; la soluzione torna a una regione di non-intervento state-dependent ([Mei, DeMiguel & Nogales 2016](https://doi.org/10.1016/j.jbankfin.2016.04.002)). Questo sostiene la direzione dell'hysteresis corrente, ma non ne convalida i parametri 90 minuti/due cicli.

## 4. Validazione anti-overfitting

La ricerca sulle exit crea un enorme universo implicito: tipo di exit × soglia × orizzonte × frequenza × universo × cost model × regime. Scegliere il massimo Sharpe da questa griglia senza correggere il search è un falso positivo quasi per costruzione.

- White propone il Reality Check per testare se il miglior modello incontrato supera davvero il benchmark dopo data snooping ([White 2000](https://doi.org/10.1111/1468-0262.00152)).
- Sullivan, Timmermann e White lo applicano all'intero universo di regole tecniche e mostrano come l'inferenza cambi quando la regola osservata non viene trattata come se fosse stata scelta ex ante ([1999](https://doi.org/10.1111/0022-1082.00163)).
- Hansen propone lo SPA test, più potente e meno sensibile ad alternative irrilevanti ([2005](https://doi.org/10.1198/073500105000000063)).
- Bailey et al. propongono CSCV e Probability of Backtest Overfitting, osservando che il semplice holdout può essere inaffidabile nei backtest finanziari ([2017](https://doi.org/10.21314/JCF.2016.322)); il Deflated Sharpe Ratio corregge anche per numero di trial e non-normalità ([Bailey & López de Prado 2014](https://doi.org/10.3905/jpm.2014.40.5.094)).

### Protocollo minimo per la ricerca successiva

1. **Congelare la baseline confirmatoria** D+2 già registrata; non usare questa ricerca per modificarla.
2. **Separare esplorazione e conferma.** Esplorazione: poche famiglie motivate, term structure e distribuzioni. Conferma: una sola challenger o un test SPA sull'universo dichiarato.
3. **Stesso entry stream.** Replay delle medesime decisioni/fill shadow per isolare l'exit; nessuna riammissione di segnali che non erano ordinabili.
4. **Costi realistici e path intraday.** Spread/fee/slippage/gap, corporate action, barrier hit order e ordini non eseguiti.
5. **Metriche congiunte.** Excess return netto, turnover, hit rate, payoff ratio, MFE/MAE, expected shortfall, max drawdown, capitale-giorni, overlap S1 e perdita incrementale nei tail event.
6. **Dipendenze corrette.** Bootstrap/cluster per giorno o evento, HAC per forward return sovrapposti, embargo/purging quando label e training window si sovrappongono.
7. **Sensitivity surface, non miglior punto.** Una strategia credibile ha un plateau stabile; un singolo picco di soglia è evidenza di fragilità.
8. **Audit del numero di trial.** Registrare anche le varianti fallite, affinché SPA/DSR/PBO usino il vero search space.

## 5. Strategie consolidate che S4 non adotta ancora in forma esplicita

Questa è una lista di **candidate hypotheses**, non raccomandazioni di deploy:

| Candidata | Perché merita analisi | Rischio principale |
|---|---|---|
| **Time-stop su decay event-type-specific** | allinea uscita alla vita economica della news; la baseline D+2 è già registrata | multiple testing fra orizzonti e tipi di news |
| **No-trade band su score/rank/costo** | generalizza l'hysteresis e riduce churn quando la variazione non copre i costi | può trattenere un segnale davvero invalidato |
| **De-risking parziale** | è coerente con alpha persistente ma incerto e con costi | complica attribuzione e può aumentare turnover |
| **Trailing volatility stop monotono** | protegge MFE e downside senza un livello percentuale uguale per tutti | rischio di tagliare le rare code positive; lag della volatilità |
| **Regime-aware sizing prima dell'exit** | riduce rischio comune senza confonderlo con invalidazione della news | instabilità OOS del volatility timing |
| **Novelty/information-content reversal** | tratta diversamente news nuova, stale e fondamentale | qualità del classifier e leakage testuale |
| **Execution-aware exit** | separa momento economico di uscita e schedule/ordine | piccolo beneficio alla size corrente, complessità operativa |

Non risultano invece supportate come priorità: uno stop stretto universale, un take-profit fisso non condizionato, il tuning isolato di una sola barriera o la selezione della variante col miglior P&L storico.

## 6. Domande aperte per l'analisi approfondita

1. Qual è la curva di rendimento post-fill di S4, non post-pubblicazione, per tipo di news e quintile di score/confidence?
2. L'informazione incrementale del contro-segnale resta dopo aver controllato per return reversal, nuova news, fonte e fallback?
3. Quale quota delle weight-drop exit storiche deriva da vera invalidazione, rank truncation, collisione S1, filtro, clock o bug?
4. Il take-profit +6% ha mai agito su posizioni S4? Quale parte del book era non-fractionable, e l'exit broker era coerente col ledger?
5. I disaster stop 12–20% sono realmente presenti per ogni posizione proteggibile? Qual è il rischio del residuo frazionario e delle posizioni sotto un'azione?
6. Una banda su score/rank evita più costi di quanti ritorni negativi accumuli? Qual è il valore economico marginale rispetto all'hysteresis corrente?
7. Le code positive di S4 finanziano il risultato totale? In tal caso take-profit/trailing possono peggiorare il P&L pur migliorando Sharpe o drawdown.
8. Un regime filter aggiunge informazione oltre volatilità idiosincratica, score e market move già avvenuto al fill?
9. Quale uscita massimizza valore **incrementale** del portafoglio dopo overlap S1, non il P&L standalone di S4?
10. Qual è l'intero numero di varianti già osservate o discusse? Senza questo dato DSR/SPA/PBO sottocorreggono il selection bias.

## Conclusione preliminare

La letteratura rafforza tre scelte già emerse internamente: separare signal freshness e holding period, evitare stop stretti non motivati e validare l'exit insieme a costi e path. Offre inoltre tre opportunità credibili non ancora modellate pienamente: **no-trade band state-based, de-risking graduale e novelty-aware exit**.

Non giustifica però un cambio immediato alla pre-registrazione D+2. Il passo corretto è usare questa mappa per una ricerca approfondita, documentare l'intero universo di candidati, quindi portare al test confirmatorio una sola challenger contro la baseline congelata.
