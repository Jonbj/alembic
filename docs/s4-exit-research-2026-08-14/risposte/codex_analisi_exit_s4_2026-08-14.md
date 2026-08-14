# S4 — analisi indipendente delle strategie di uscita

**Data cutoff comune:** 2026-08-14  
**Perimetro Alembic:** soltanto fatti, codice e decisioni documentati entro il cutoff; nessuna modifica successiva del progetto è stata usata.  
**Metodo:** ricerca Web su fonti primarie/ufficiali, citation chaining, lettura critica degli allegati [01](../01_PROMPT_MULTI_LLM.md), [02](../02_ANALISI_PRELIMINARE_LETTERATURA.md), [03](../03_DECISIONE_PRECEDENTE_CONSOLIDATA.md) e [04](../04_PREREGISTRAZIONE_D2.md). Gli allegati 02–04 sono evidenza e contesto, non conclusioni da confermare.

Le etichette epistemiche usate sono: `EVIDENZA ESTERNA`, `EVIDENZA ALEMBIC`, `INFERENZA`, `IPOTESI`, `NON DECIDIBILE`.

## 1. Executive verdict

**Verdetto: `MODIFY`, confidenza media.**

`EVIDENZA ALEMBIC` L'uscita ordinaria corrente non è una exit strategy coerente: è soprattutto la conseguenza di target weight zero dopo ranking, gate, scadenza editoriale, collisioni o failure di pipeline. La tenuta osservata di 1h45/4h15 descrive il software più dell'alpha.

`EVIDENZA ESTERNA` La migliore prior disponibile per una pipeline editoriale lenta è un orizzonte in **sedute**, non in ore di parete. Heston–Sinha trovano prevedibilità giornaliera per 1–2 giorni, ma incorporazione più rapida delle notizie positive; Jiang–Li–Wang trovano drift per alcuni giorni dopo news firm-specific. Tetlock mostra invece reversal dopo news stantie. Poiché S4 è long-only e compra segnali positivi, D+2 è plausibile ma non forte: può essere già troppo lungo per news positive comuni e troppo corto per eventi fondamentali inattesi o ad attenzione bassa.

Raccomando un **D+2 session-clock modificato**: uscita alla close della seconda seduta successiva alla seduta d'ingresso; nessuna uscita per silenzio, rank drop o semplice caduta sotto il gate d'ingresso; sole eccezioni per (i) contro-segnale ensemble, nuovo, entity-resolved e riferito alla tesi originaria e (ii) catastrophe stop largo definito dal risk budget, non ottimizzato sul P&L. Nessun take-profit fisso.

La prova primaria deve essere il **delta paired di rendimento netto rispetto a E0 sugli stessi ingressi**, non l'IC D+2: l'IC verifica soprattutto l'ingresso. IC, integrità, tail risk, costi, capitale-giorni e valore incrementale rispetto a S1 restano gate congiunti. D+2 è promosso solo se il limite inferiore dell'intervallo di confidenza del delta netto supera un MDE economico predefinito senza peggiorare la coda oltre il risk budget; è respinto se il limite superiore non raggiunge quel MDE; altrimenti resta `INCONCLUSIVE` in shadow.

## 2. As-is audit

### 2.1 Mappa dei rami correnti al cutoff

| Ramo | Trigger e clock | Bypass/interazione | Razionalità economica | Failure mode osservabile | Falsificazione della classificazione |
|---|---|---|---|---|---|
| **Target/rank weight-drop** | Il simbolo scompare dal target ricalcolato; ciclo ogni 15 minuti, nonostante `DAILY` dichiarato | Attraversa min-hold 90 minuti, protezione del positivo fresco e isteresi di due cicli | Bassa come thesis exit; può essere sensata solo come replacement/capacity exit esplicita | Confonde nuova informazione, gate, slot top-5, collisione, dato perso e bug | Diventerebbe una exit economica solo se ogni zero-weight avesse causa point-in-time ricostruibile e confronto di expected edge netto |
| **Caduta sotto entry gate** | Ultimo score non soddisfa più la soglia di ingresso | Può essere protetta se resta un positivo fresco sopra gate; poi isteresi | Debole: un gate d'ingresso non è automaticamente una soglia di liquidazione | Soglie uguali in entrata/uscita creano churn; l'ultimo articolo può sovrascrivere la tesi | Evidenza paired che il crossing sotto gate predice rendimento futuro netto negativo, su dati forward |
| **Freshness/expired/no signal** | `max_signal_age_hours=4`, ore di parete; oppure nessun nuovo segnale | FIX-D prova a preservare un vecchio positivo, ma altre trasformazioni possono ancora azzerare il peso | Razionale come filtro d'ingresso; non come prova di invalidazione | Silenzio editoriale trattato come SELL; weekend e overnight hanno durata diversa dalle ore di mercato | Dimostrare che l'assenza di update, condizionata a copertura e source uptime, ha valore predittivo negativo incrementale |
| **FIX-D / positive-signal protection** | Vecchio positivo riammesso se manca segnale fresco | Interagisce con ranker, gate, target aggregation e reason code | Concettualmente corretta: assenza di prova non è prova contraria | Uscite `unknown` anche dopo riammissione; protezione non end-to-end | Lifecycle completi mostrano che nessun positivo preservato può finire a zero senza causa economica esplicita |
| **Hold minimo + hysteresis** | 90 minuti e due SELL consecutivi | Stop e reversal forzati bypassano entrambi; anti-whipsaw S4 aggiuntivo è disabilitato | Ragionevole come inaction band contro rumore/costi, ma non calibrata economicamente | Ritardi meccanici a 1h45; doppia isteresi se si attiva anche quella S4 | Il beneficio paired al netto costi è non positivo o i falsi hold dopo invalidazione superano il budget di rischio |
| **Counter-signal force-sell** | Segnale ensemble non-fallback fresco ≤60 min; default codice `<−0,20`, runtime documentato `−0,35`, futura ipotesi `≤−0,30` | Bypassa hold/isteresi; cooldown re-entry 2h | È il ramo più vicino a una thesis exit, ma soglia e semantica non sono validate | Divergenza config/runtime; ultimo articolo rumoroso o non pertinente; soglia non legata alla tesi iniziale | Il contro-segnale qualificato non predice delta post-exit negativo rispetto all'hold, o aumenta false exits/costi |
| **Stop sintetico ordinario** | Stop fisso 2% disabilitato; candidata vol-scaled in shadow | Bypassa i normali guard | Risk exit legittima in principio | Replay 245 trade misti: 2% e candidato vol-scaled peggiori; noise stop e costi | Nuovo campione S4-specifico, congelato e paired mostra miglioramento netto o utilità di coda senza drag eccessivo |
| **Broker catastrophe stop `d_hard`** | Fascia indicativa 12–20%; GTC per quantità intere, bracket in alcuni BUY non-fractionable | Può essere attivo quando la logica applicativa non gira | Razionale come limite operativo/tail, non come fonte di alpha | Residuo <1 azione non protetto; commento YAML/runtime/ordini non riconciliati; gap oltre il trigger | Audit broker dimostra copertura completa e coerente, oppure il tail gate mostra che la gamba non riduce la perdita rilevante |
| **Take-profit broker +6%** | Solo alcuni BUY non-fractionable in bracket | OCO con stop; assente per notional/fractional | Nessuna tesi S4 omogenea | Trattamento dipendente dalla frazionabilità; possibile troncamento della coda destra | Può restare solo se un confronto paired, includendo right-tail contribution, mostra utilità netta positiva fuori campione |
| **Drawdown/VIX/alert** | Controlli di portafoglio; alert perdita non protetta 15% non è ordine | Possono bloccare ingressi, ridurre rischio o liquidare a seconda del runtime | Risk governance di portafoglio, non thesis exit per-trade | Confusione fra alert, gate e ordine; doppio conteggio del rischio | Audit runtime separa chiaramente effetti e dimostra l'azione effettiva per ogni controllo |

`EVIDENZA ALEMBIC` Nove round trip recenti non stimano l'alpha, ma il fatto che nessuno sia uscito per contro-segnale e che sei siano caduti a scadenze meccaniche è sufficiente per rifiutare l'interpretazione dello storico come test pulito di una exit economica.

### 2.2 Risposta esplicita alla domanda 1

La policy corrente è **prevalentemente un effetto collaterale del ranker/orchestrator**. Sono razionali, come categorie, il counter-signal qualificato, il catastrophe stop, una inaction band contro churn e una replacement exit esplicita. Sono difetti di semantica o osservabilità: `expired/no_signal` come SELL, `unknown`, uso del gate d'ingresso come gate d'uscita, clock `DAILY` non applicato, dipendenza del take-profit dalla frazionabilità e divergenze fra codice/config/runtime. Questa risposta sarebbe falsificata da lifecycle point-in-time che ricostruissero ogni weight-drop come decisione economica esplicita e coerente.

## 3. Literature evidence table

La tabella distingue risultati effettivamente letti in full text da abstract/preview. “Exit” indica la regola studiata o, per i paper sulle news, l'orizzonte di outcome pertinente; non implica che il paper abbia testato S4.

| Fonte primaria | Accesso | Universo, periodo, frequenza, lato/strategia | Exit/outcome e risultato economico-rischio-costi | Replica, limite o contraddizione; trasferibilità a S4 |
|---|---|---|---|---|
| Heston & Sinha, *News versus Sentiment* ([FEDS 2016-048](https://doi.org/10.17016/FEDS.2016.048); [versione rivista](https://doi.org/10.2469/faj.v73.n3.3)) | Full text Fed | 900.754 storie Thomson Reuters, azioni USA, 2003–2010; daily e weekly; portafogli long-short per quantili | Nella specifica daily lo spread è circa 17 bp a D+1 e 4 bp a D+2, poi piatto; l'aggregazione weekly dura di più soprattutto sul negativo. Le positive sono incorporate più rapidamente; il sentiment daily è rumoroso. Inoltre i rendimenti dei dieci giorni precedenti predicono il tono: la storia può arrivare dopo l'evento. Costi e gamba long S4 non sono validati | Jiang et al. trovano drift multi-day; Tetlock 2011 trova reversal per stale news. **Trasferibilità alta** per clock/aggregazione, **media** per rendimento: S4 è long-only e usa modelli/fonti diversi |
| Jiang, Li & Wang, *Pervasive Underreaction* ([JFE](https://doi.org/10.1016/j.jfineco.2021.04.003)) | Preview esteso publisher/abstract | Dow Jones Newswire, azioni USA, 2000–2012; intervalli 15 minuti + overnight; long-short su news return, holding 1 settimana | Drift nella direzione della reazione iniziale, più forte nei primi giorni; strategia one-week resta positiva dopo effective-spread cost nel loro campione | Non isola la gamba long né sentiment LLM e identifica news tramite risposta di prezzo. **Trasferibilità media**: forte sulla plausibilità multi-day, debole sulla soglia D+2 esatta |
| Tetlock, Saar-Tsechansky & Macskassy, *More Than Words* ([DOI](https://doi.org/10.1111/j.1540-6261.2008.01362.x); [author PDF](https://www.columbia.edu/~pt2238/papers/TSM_More_Than_Words_JF_05_07.pdf)) | Full text autore | >350.000 WSJ/DJNS su imprese S&P 500, 1980–2004; daily; ritorni e fondamentali firm-level | Negative words predicono earnings e breve underreaction, soprattutto nelle storie fondamentali; i profitti high-frequency sono sensibili ai costi. Le storie multiple del ticker-giorno sono aggregate | Contrasta l'uso dell'ultimo articolo. **Trasferibilità alta** per aggregazione/contenuto fondamentale, **media** per il lato long positivo |
| Tetlock, *All the News That's Fit to Reprint* ([DOI](https://doi.org/10.1093/rfs/hhq141); [full text autore](https://business.columbia.edu/sites/default/files-efs/pubfiles/3099/Tetlock%20Fit%20to%20Reprint%2010%2010.pdf)) | Full text autore | >850.000 firm-days, 10.187 imprese USA, DJ Newswire, nov. 1996–ott. 2008; daily | Staleness = similarità con le dieci storie precedenti. Minore reazione immediata, ma il return del giorno di stale news predice reversal nella settimana seguente; più forte con retail trading alto | Limita qualsiasi time-stop universale e il “last article wins”. **Trasferibilità alta** se S4 può misurare novelty point-in-time |
| Tetlock, *Giving Content to Investor Sentiment* ([DOI](https://doi.org/10.1111/j.1540-6261.2007.01232.x)) | Full text publisher | Colonna WSJ “Abreast of the Market”, 1984–1999; daily; mercato aggregato | Pessimismo alto predice pressione ribassista seguita da reversione e volume alto; misura sentiment generico, non informazione fondamentale | Contraddice il trasferimento ingenuo da “sentiment” a drift firm-specific. **Trasferibilità bassa-media**: utile come failure mode per news editoriali/generiche |
| Chan, *Stock Price Reaction to News and No-News* ([DOI](https://doi.org/10.1016/S0304-405X(03)00146-6); [working paper](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=262452)) | Abstract publisher + working paper | Campione casuale di azioni CRSP, 1980–2000; headline e rendimenti mensili; portafogli news/no-news | Forte drift soprattutto dopo cattive news; reversal dopo grandi movimenti senza news; effetti concentrati in small/illiquid | Frequenza mensile e predominio lato negativo limitano S4. **Trasferibilità media-bassa**, ma separa price move da informazione |
| Boudoukh et al., *Information, Trading, and Volatility* ([DOI](https://doi.org/10.1093/rfs/hhy083); [author PDF](https://www.shimonkogan.com/_files/ugd/6739fc_ff6f6c2865bd4dc882ac065eab9bfe66.pdf)) | Full text autore | S&P 500, Dow Jones Newswire, circa 2000–2015; intraday vs overnight; event taxonomy | News fondamentali identificate spiegano molta più volatilità idiosincratica, soprattutto overnight (49,6% vs 12,4% intraday); eventi multipli contano | Non è uno studio di exit/direzione. **Trasferibilità alta** per event type, overnight clock e multi-news aggregation; bassa per P&L |
| Neuhierl, Scherbina & Schlusche, *Market Reaction to Corporate Press Releases* ([DOI](https://doi.org/10.1017/S002210901300046X); [author copy](https://escholarship.org/content/qt1xf8t2j6/qt1xf8t2j6.pdf)) | Full text autore | Comunicati societari USA, ampio catalogo di topic, daily/event study | Reazioni differiscono per news finanziarie, strategia, clienti/partner, prodotti, management e legale | Conferma eterogeneità per event type ma non un orizzonte ottimo S4. **Trasferibilità media-alta** per tassonomia point-in-time |
| DellaVigna & Pollet, *Investor Inattention and Friday Earnings Announcements* ([DOI](https://doi.org/10.1111/j.1540-6261.2009.01447.x)) | Abstract publisher | Earnings USA, venerdì vs altri giorni; event study e drift | Venerdì: risposta immediata 15% più bassa, risposta ritardata 70% più alta, volume 8% più basso | Specifico a earnings programmati; non autorizza split liberi. **Trasferibilità media** come prior su attenzione/scheduled events |
| Hirshleifer, Lim & Teoh, *Driven to Distraction* ([DOI](https://doi.org/10.1111/j.1540-6261.2009.01501.x)) | Abstract publisher | Earnings USA; carico di annunci same-day; event study | Più annunci concorrenti: reazione immediata più debole e drift successivo più forte | Event type specifico. **Trasferibilità media**: attenzione è uno stato plausibile, ma richiede numerosità e misura ex ante |
| Peress, *Media and the Diffusion of Information* ([DOI](https://doi.org/10.1111/jofi.12179)) | Abstract publisher | Scioperi di quotidiani in più paesi; daily; natural experiment | Nei giorni di sciopero volume −12%, dispersione/volatilità intraday −7%; i giornali propagano news precedenti e facilitano incorporazione | Dimostra che fonte derivata può accelerare diffusione senza essere informazione nuova. **Trasferibilità alta** per distinguere origine e redistribuzione |
| Kaminski & Lo, *When Do Stop-Loss Rules Stop Losses?* ([DOI](https://doi.org/10.1016/j.finmar.2013.07.001)) | Preview esteso publisher | Teoria + futures indice, gen. 1993–nov. 2011; daily/multi-frequency; buy-hold con stop/re-entry | Sotto random walk lo stop riduce expected return; può aiutare con momentum e ridurre varianza passando a asset meno rischioso; alcune regole più lente migliorano nel loro campione | Lo & Remorov aggiungono azioni e costi. **Trasferibilità media-bassa**: processo e asset diversi; alta come prova di condizionalità |
| Lo & Remorov, *Stop-loss Strategies...* ([DOI](https://doi.org/10.1016/j.finmar.2017.02.003)) | Preview esteso publisher | Grande campione azioni USA, 1964–2014; AR(1), regime switching, costi bid-ask | Stop stretti sottoperformano buy-hold dopo costi; outperformance richiede autocorrelazione sufficiente; riduzione downside spesso modesta | Coerente con replay Alembic, non prova contro catastrophe stop. **Trasferibilità media** per azioni/costi, bassa per entry news-specific |
| Dai et al., *Risk Reduction Using Trailing Stop-Loss Rules* ([DOI](https://doi.org/10.1111/irfi.12328)) | Full text publisher | Azioni USA 1926–2016; long benchmark/mean-variance; trailing | Mean return inferiore al benchmark mean-variance, ma rischio totale/downside minore, soprattutto in mercati ribassisti; stop stretti soffrono costi, larghi più robusti | Non news-driven e non dimostra maggiore P&L. **Trasferibilità media-bassa**; utile soltanto come overlay di rischio |
| Glynn & Iglehart, *Trading Securities Using Trailing Stops* ([DOI](https://doi.org/10.1287/mnsc.41.6.1096)) | Abstract + PDF publisher | Modelli random walk/Brownian con drift positivo; long; nessun dataset | Deriva distribuzione, media, varianza e durata per trailing a distanza fissa; la soglia dipende dal processo | Elegante ma senza news, salti o costi realistici. **Trasferibilità bassa**; falsifica soglie universali, non sceglie il valore |
| Leung & Zhang, *Optimal Trading with a Trailing Stop* ([DOI](https://doi.org/10.1007/s00245-019-09559-0); [SSRN full](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2895437)) | Full text working paper | Diffusione lineare, esempio exponential-OU; double stopping, long | Con trailing path-dependent deriva regioni di acquisto/liquidazione e, nel modello, uso congiunto di sell limit | L'esempio OU è mean-reverting e non news momentum. **Trasferibilità bassa**; utile solo per path dependence e non-indipendenza delle barriere |
| Imkeller & Rogers, *Trading to Stops* ([DOI](https://doi.org/10.1137/130911706)) | Abstract publisher | Modello di stopping state-based con costi; non empirico | Stop di perdita/profitto/trailing sono scelti congiuntamente rispetto a un obiettivo; riducono frequenza e rendono esplicita la riallocazione | Non identifica parametri S4. **Trasferibilità media** per non ottimizzare una barriera isolata |
| Gârleanu & Pedersen, *Dynamic Trading with Predictable Returns and Transaction Costs* ([DOI](https://doi.org/10.1111/jofi.12080)) | Full text publisher | Modello multi-asset con segnali a decay diversi; applicazione commodity futures | Politica ottima: “aim in front” e trade parziale verso il target; segnali più persistenti pesano di più; net return migliore di benchmark ingenui nell'applicazione | Asset/applicazione diversi e size S4 piccola. **Trasferibilità alta** concettualmente per E8/E9, media empiricamente |
| Mei, DeMiguel & Nogales, *Multiperiod Portfolio Optimization...* ([DOI](https://doi.org/10.1016/j.jbankfin.2016.04.002)) | Preview esteso publisher | Teoria multi-asset; applicazione a 15 futures; costi proporzionali/impact | Con costi proporzionali emerge una no-trade region; con impact si negozia al bordo; ignorare costi o agire miopicamente può essere costoso | A size S4 l'impact proprio può essere trascurabile, spread no. **Trasferibilità media** per hysteresis/replacement, non per soglie |
| Vaicenavicius, *Asset Liquidation Under Drift Uncertainty...* ([DOI](https://doi.org/10.1007/s00245-018-9518-5)) | Full text open access | Modello con drift ignoto e volatilità Markov-switching; long optimal liquidation | La frontiera di vendita dipende da posterior mean, tempo di apprendimento e regime di volatilità | Richiede un posterior ben calibrato che S4 non ha. **Trasferibilità bassa oggi**, alta come direzione per thesis-state futuro |
| Fine & Gray, *A Proportional Hazards Model for the Subdistribution of a Competing Risk* ([DOI](https://doi.org/10.1080/01621459.1999.10474144)) | Abstract publisher | Statistica generale di time-to-event; non trading | Modella cumulative incidence in presenza di eventi mutuamente esclusivi | Utile per descrivere quali exit “vincono” per prime, non per causalità o ottimalità. **Trasferibilità media diagnostica**, bassa come policy |
| Broadie, Glasserman & Kou, *A Continuity Correction for Discrete Barrier Options* ([DOI](https://doi.org/10.1111/1467-9965.00035)) | Abstract/PDF publisher | Teoria barrier option; monitoraggio discreto vs continuo | La barriera discreta non equivale a quella continua; correzione scala con volatilità e radice dell'intervallo | Non è una formula da copiare sugli stop S4. **Trasferibilità media** per provare che OHLC/close non basta a ricostruire hit intrabar |
| Moreira & Muir, *Volatility-Managed Portfolios* ([DOI](https://doi.org/10.1111/jofi.12513)) | Full text publisher | Fattori equity e carry; volatilità mensile; scaling di esposizione | Ridurre rischio quando volatilità alta aumenta Sharpe/utility nel loro campione | Cederburg et al. trovano benefici OOS non sistematici. **Trasferibilità bassa-media**: sizing di portafoglio, non per-trade thesis exit |
| Cederburg et al., *On the Performance of Volatility-Managed Portfolios* ([DOI](https://doi.org/10.1016/j.jfineco.2020.04.015)) | Preview esteso publisher | 103 strategie equity; real-time OOS | Nessuna superiorità sistematica; versioni real-time spesso hanno CER/Sharpe inferiori per instabilità strutturale | Contraddice una regola volatility-managed universale. **Trasferibilità media** come caution OOS |
| White, *A Reality Check for Data Snooping* ([DOI](https://doi.org/10.1111/1468-0262.00152)) | Abstract publisher | Metodo econometrico; specification search | Testa se il miglior modello incontrato supera un benchmark tenendo conto del riuso dei dati | Può avere bassa potenza con molte alternative irrilevanti. **Trasferibilità alta** se si confronta un catalogo di exit |
| Hansen, *A Test for Superior Predictive Ability* ([DOI](https://doi.org/10.1198/073500105000000063)) | Abstract publisher | Metodo + Monte Carlo e forecast inflazione | SPA studentizza e riduce sensibilità alle alternative scadenti rispetto al Reality Check | Non sostituisce un vero forward; richiede universo di trial completo. **Trasferibilità alta** |
| Bailey & López de Prado, *The Deflated Sharpe Ratio* ([DOI](https://doi.org/10.3905/jpm.2014.40.5.094)) | Publisher + PDF | Metodo; strategie/backtest con selezione e non-normalità | DSR corregge Sharpe per selection bias e non-normalità | Dipende dal numero effettivo di trial, oggi `NON DECIDIBILE`. **Trasferibilità alta** come secondario, non come metrica primaria |
| Bailey et al., *The Probability of Backtest Overfitting* ([DOI](https://doi.org/10.21314/JCF.2016.322)) | Abstract publisher | Metodo CSCV/PBO; backtest finanziari | Stima probabilità che il miglior IS sottoperformi OOS; semplice holdout può essere inaffidabile | Campioni molto piccoli e dipendenze rendono PBO instabile. **Trasferibilità media-alta** se abbastanza dati |
| Alpaca, *Orders at Alpaca* ([documentazione ufficiale](https://docs.alpaca.markets/us/docs/orders-at-alpaca)) | Full text ufficiale | Regole broker correnti consultate al cutoff della ricerca; non paper | Stop-market non garantisce il prezzo; stop-limit può restare non eseguito dopo gap; bracket non opera extended-hours; trailing non triggera fuori RTH; advanced order può avere entrambe le gambe fill in mercati estremi | Rende impossibile chiamare il catastrophe stop “perdita massima garantita”. **Trasferibilità alta** se il broker effettivo è Alpaca; runtime da verificare |

### 3.1 Sintesi della term structure e risposta alla domanda 2

`EVIDENZA ESTERNA` Per una pipeline lenta e derivata, la term structure più plausibile è: gran parte del repricing prima del fill o nel giorno dell'evento; residuo modesto a D+1/D+2; coda più lunga solo per news fondamentali, inattese, negative o a bassa attenzione; rischio di reversal per contenuto stale/generico. Non esiste una curva unica.

`INFERENZA` D+2 ha supporto sufficiente come **prior di confronto**, non come policy già validata. È probabilmente troppo lungo quando il segnale positivo è una riscrittura stantia, quando la risposta iniziale/gap ha già incorporato l'informazione o quando la fonte è soltanto redistributiva. Può essere troppo corto per earnings/fondamentali complessi, annunci affollati o a bassa attenzione, ma S4 long-only non può appropriarsi automaticamente dell'evidenza più persistente sulle cattive news. La falsificazione è una term structure post-fill pulita in cui il paired marginal return da D+1 a D+2 è stabilmente non positivo, oppure resta materialmente positivo oltre D+2 fino a D+3/D+5.

### 3.2 Silenzio e contro-segnale: risposte alle domande 3 e 4

**Domanda 3.** Il silenzio della fonte non deve chiudere una posizione, salvo che sia informativo sotto assunzioni documentate: copertura/source uptime nota, evento con update atteso e mancata osservazione point-in-time distinguibile da outage o assenza editoriale. Anche allora è una variabile di tesi, non una scadenza a quattro ore. Il clock deve essere di sedute/event time; weekend e notte non sono equivalenti a ore RTH. Falsificazione: su forward pulito, l'assenza condizionata di update predice rendimento successivo negativo incrementale e copre i costi di uscita.

**Domanda 4.** Un contro-segnale è giustificato perché nuova informazione contraria aggiorna la tesi; non è giustificato dal solo crossing numerico dell'ultimo articolo. La prima policy deve richiedere ensemble non-fallback, entity resolution corretta, novelty, pertinenza alla tesi e timestamp point-in-time. Lo stesso modello dell'ingresso offre coerenza ma errori correlati; un ensemble separato offre indipendenza ma apre un nuovo trial. La soglia non deve essere assunta simmetrica: selezione long-only e diversa velocità positive/negative rompono la simmetria. `−0,30` è `IPOTESI`, conservabile per disciplina ma da validare via delta hold-vs-exit. La policy è falsificata se il rendimento post-counter-signal non è peggiore dell'uscita dopo costi o se il false-counter rate supera il budget predefinito.

## 4. Strategy catalog

| ID | Policy e ruolo | Razionale / vantaggi | Failure mode | Complessità e trial cost | Condizione di falsificazione | Stato |
|---|---|---|---|---|---|---|
| **E0** | As-is: zero target → full close | Benchmark reale, include attrito software | Non è semanticamente una exit; contaminata da bug e clock | Bassa; nessun nuovo trial, ma va versionata | Non falsificabile come descrizione; è invalidata come benchmark se lifecycle non ricostruibile | **Baseline obbligatoria** |
| **E1M** | D+2 session-clock + counter-signal qualificato + catastrophe stop | Policy parsimoniosa; separa ingresso, tesi e rischio; riduce churn | D+2 errato per gamba long; contro-segnale raro/rumoroso; capitale occupato | Media; **un trial primario** | Limite superiore del CI del delta netto paired ≤ MDE, oppure tail/costi/overlap falliscono il gate | **Confirmatoria primaria** |
| **E2** | D+1 e D+3, medesime eccezioni | Mappa il gradiente attorno a D+2 | Winner selection ex post | Bassa tecnica, due trial econometrici | Non applicabile come policy: sono diagnostiche; nessuna scelta sulla finestra esplorativa | **Diagnostica** |
| **E3** | Counter-signal only con maximum hold molto ampio e dichiarato | Testa vera invalidazione della tesi | Silenzio prolungato, capacità bloccata; counter-signal non calibrato | Media; un trial, poca potenza per pochi eventi | Nessun vantaggio netto vs E1M o capitale-giorni e tail eccedono budget | **Diagnostica/respinta ora** |
| **E4** | D+2 + thesis-state aggregato nel tempo, anziché ultimo articolo | Direttamente motivata da Heston–Sinha e Tetlock et al.; riduce input churn | Definizione di evento/novelty può fare leakage; confonde nuova pipeline con exit | Alta; nuovo artefatto point-in-time e nuova famiglia di trial | Aggregazione non migliora delta netto/reason quality o vantaggio scompare forward | **Diagnostica/futura; fuori dal confronto confirmatorio** |
| **E5** | D+2 + wide volatility/catastrophe stop | Limita coda senza noise stop | Soglia adattiva può allargarsi durante shock; gap oltre stop | Media; ogni calibrazione aggiunge trial | ES/gap loss non migliora, o drag netto supera risk utility predefinita | **Parte risk-only di E1M; non alpha challenger** |
| **E6** | Trailing attivato dopo MFE predefinita | Protegge vincitori dopo guadagno | Taglia right tail; RTH-only/gap; path data | Alta; almeno due barriere congiunte | Right-tail contribution o mean P&L peggiorano oltre tolleranza senza compenso di tail | **Diagnostica futura** |
| **E7** | Exit per event type/segno/regime | Coerente con eterogeneità della letteratura | Moltiplica celle/trial; taxonomy leakage; scarsa potenza | Molto alta | Nessuna interazione pre-specificata stabile forward o celle sotto MDE power | **Respinta per il primo test** |
| **E8** | Replacement exit su expected edge netto e costo opportunità | Separa slot top-5 da falsificazione; coerente con dynamic trading | Expected edge non calibrato; può ricreare rank churn | Alta; richiede opportunity-set ledger | Nuovo candidato non supera valore residuo + costi con affidabilità forward | **Diagnostica prioritaria, non confirmatoria ora** |
| **E9** | De-risking parziale/posterior + no-trade band | Evita full-close binario; coerente con costi e incertezza | Posterior non disponibile; più turnover e gradi di libertà | Molto alta; molti stati impliciti | Non migliora utility netta/capitale rispetto a E1M o posterior non calibrato | **Ricerca futura** |
| **E10** | Take-profit fisso +6% | Semplice, già accidentalmente presente in parte del book | Trunca vincitori; dipende dalla frazionabilità; nessuna prior news-specific | Bassa tecnica, ma trial ingiustificato | Già respinta come policy universale finché non esiste evidenza right-tail paired | **Respinta** |
| **E11** | Stop fisso 2% | Semplice controllo di perdita | Noise/turnover; replay interno negativo; letteratura condizionale | Bassa, trial già consumato internamente | Nuovo forward S4-specifico dovrebbe ribaltare replay e costi | **Respinta** |

### 4.1 Risposte esplicite alle domande 5–7 e 9

**Domanda 5.** Il replay a 245 trade consente di dire che **quel** 2% fisso e **quel** candidato vol-scaled, su quel campione misto e con quei costi/path, non meritano riproposizione ingenua. Non dimostra che nessun disaster stop, trailing, soglia larga o risk overlay possa migliorare ES/utility; non identifica l'effetto S4-specifico; non rende il no-stop una legge. Falsificazione: forward S4 congelato con confronto paired e path intraday mostra beneficio netto/tail robusto per una diversa regola pre-registrata.

**Domanda 6.** Non emerge evidenza diretta sufficiente per take-profit o trailing in news-momentum long-only. Dai et al. trovano minore mean return ma minore downside per trailing in un contesto diverso; l'evidenza sul drift rende credibile il rischio di tagliare i pochi vincitori. Il take-profit fisso è respinto; il trailing post-MFE resta solo diagnostico dopo aver misurato la concentrazione della coda destra. Falsificazione: trailing congelato migliora delta netto e tail utility senza ridurre la quota di P&L dei top winners oltre la tolleranza.

**Domanda 7.** Ora è migliore una policy unica e parsimoniosa. Una policy condizionata è giustificata solo con un'interazione economica pre-specificata e potenza per **ogni** cella, non con significatività pooled. La numerosità è `NON DECIDIBILE` senza varianza dei paired deltas, frequenza degli event type e intracluster correlation; non si può riusare “213 sedute” come risposta. Per (K) celle, l'ordine di grandezza cresce almeno linearmente con (K) a effetto/varianza uguali e più che linearmente con celle rare e correzione multipla. Falsificazione: un singolo modello mostra eterogeneità stabile forward e beneficio netto maggiore del costo di complessità.

**Domanda 9.** Le strategie consolidate non adottate pienamente sono: time-stop in event/session clock; state aggregation; no-trade region; trade parziale; replacement su expected edge netto; volatility-managed sizing; optimal stopping sotto posterior; survival/competing-risk audit. Sono realmente trasferibili oggi soltanto session clock, separazione tesi/rischio/capacità, no-trade/hysteresis e confronto paired. Posterior optimal stopping, OU trailing, factor volatility scaling e execution optimization sofisticata sono matematicamente utili ma non direttamente trasferibili alla piccola sleeve news long-only.

## 5. Shortlist

Solo due policy entrano nel confronto confirmatorio; tutte le altre restano diagnostiche, future o respinte come indicato nella tabella precedente.

1. **E0 — as-is, benchmark.** Serve per quantificare il valore di rimuovere le exit spurie. Non è una candidata da promuovere. È utilizzabile solo se almeno il lifecycle minimo è ricostruibile; in caso contrario il confronto storico è `NON DECIDIBILE` e il benchmark forward deve essere simulato con la versione congelata al cutoff.
2. **E1M — D+2 session-clock modificato, primaria.** Exit alla close di D+2, senza silenzio/rank drop; counter-signal qualificato e catastrophe stop come sole eccezioni. È la singola ipotesi confirmatoria.
`INFERENZA` E2 D+1/D+3 ed E4 sono soltanto diagnostiche; E3, E6, E7–E9 sono research hypotheses future; E10/E11 sono respinte. E4 non può sostituire E1M se E1M fallisce: richiederebbe una nuova pre-registrazione e un nuovo forward. La shortlist stessa è falsificata se l'audit mostra che gli ingressi non possono essere congelati/ricostruiti: senza identico entry stream non esiste un test di exit.

## 6. Empirical protocol

### 6.1 Ledger point-in-time e query logiche

Una riga base è un **entry intent eleggibile**; articoli, segnali e fill sono tabelle figlie versionate, non colonne sovrascritte. Il ledger minimo deve contenere:

- identità: `signal_id`, `event_id`, articolo/documento, ticker risolto, versione del resolver, source primaria/derivata, event type e relazione articolo-ticker verificata;
- tempi originali e timezone: published, first-seen/ingested, model-generated, decision, intent, ack e fill; sessione RTH/extended/overnight; nessun timestamp retro-corretto senza versione;
- stato informativo: score, polarity, confidence, coppia ensemble, fallback, relevance, novelty rispetto ai documenti disponibili allora, link alla tesi/evento iniziale, tutte le news successive e non soltanto l'ultima;
- eleggibilità: universo, liquidità/spread, gate, slot, sizing, collisione S1, motivo di esclusione; bisogna conservare anche i candidati non tradati per analisi di capacità senza usarli come trade;
- esecuzione: decision price, prima quote/bar realmente disponibile dopo la decisione, fill virtuale, bid/ask/spread, partial fill, notional/qty, fee, slippage, latenza, stato e copertura degli ordini broker;
- path: barre almeno alla frequenza capace di ordinare le barriere, corporate actions/total return, halt, LULD, delisting; MAE/MFE e tempi relativi, gap overnight, volatilità/liquidità point-in-time;
- exit: per E0/E1M, primo trigger, tutti i trigger concorrenti, decision time, prezzo eseguibile, fill, reason code atomico, counterfactual censoring; post-exit drift a 1h/close/D+1/D+2/D+3/D+5; E4 può essere calcolata separatamente come sola diagnostica senza inferenza confirmatoria;
- portfolio: capitale-giorni, slot displacement, candidato rimpiazzante, overlap/collisione e marginal contribution rispetto a S1.

Qualsiasi taxonomy, novelty o ticker label ottenuta dopo l'evento può servire a un audit retrospettivo, non alla policy forward, finché non esisteva point-in-time.

### 6.2 Controfattuali, clock, prezzi e costi

- **Ingressi congelati:** identici intenti, timestamp, prezzo e size iniziale per E0/E1M. Una exit anticipata non autorizza un re-entry che l'altra policy non avrebbe potuto fare; la riallocazione si misura separatamente come E8. L'eventuale E4 diagnostica usa gli stessi ingressi ma non appartiene al confronto confirmatorio.
- **Clock:** D0 è la seduta del primo fill RTH eseguibile; per decisioni dopo la close, D0 è la seduta successiva. D+2 è la close della seconda seduta successiva a D0. Half-day e holiday calendar sono espliciti. Wall-clock age resta solo ingresso.
- **Close:** usare un prezzo d'asta realmente ottenibile se l'intento arriva entro il cutoff broker; altrimenti prima esecuzione conservativa successiva. Non attribuire automaticamente il closing print.
- **Barriere:** il primo evento osservabile vince. Se OHLC non ordina stop/counter/target, il trade è ambiguo e richiede quote/trade più fini; non scegliere il percorso favorevole. Halt/delisting/gap sono esiti economici, non missing casuali.
- **Cost model:** spread contemporaneo, fee, slippage condizionato a liquidità/ora/volatilità, impatto se materiale, auction/market order; stress predefiniti almeno baseline e conservativo. Un broker stop è simulato come market dopo trigger, non al trigger; uno stop-limit può non eseguire.
- **Corporate actions:** total-return coerente, split e dividend; gli advanced orders DNR/DNC richiedono riconciliazione specifica.

### 6.3 Metriche

**Primaria exit-specific:** media del delta paired netto per entry, 

\[
\Delta_i = r^{net}_{i,E1M} - r^{net}_{i,E0},
\]

con initial notional identico e inferenza cluster per event-day. Il MDE deve essere il minimo incremento che copre costi operativi, capitale e rischio, fissato dal PO **prima** di leggere il forward. Il delta pooled non sostituisce il portafoglio end-to-end.

**Gate economico secondario di portafoglio:** excess return netto E1M vs E0 sullo stesso stream e vs equal-weight watchlist, includendo cash degli slot vuoti e collisione S1. Non è una seconda ipotesi primaria e non può compensare il fallimento della metrica primaria.

**Gate/secondarie:** expectancy, mediana, hit rate, payoff win/loss, profit factor; turnover, spread/slippage, capitale-giorni e return on occupied capital; vol, downside deviation, drawdown/durata, skewness, empirical VaR/ES con CI; quota di P&L prodotta dai migliori 1/5/10% trade; false-stop rate (exit in perdita seguita da recupero entro thesis horizon); MFE giveback e MAE loss avoided; IC post-fill a D+1/D+2/D+3 come diagnostica dell'ingresso; counter-signal precision e delta hold-vs-exit; overlap e marginal P&L/ES rispetto a S1.

Gli split per source, novelty, event type, ora, gap, liquidità e regime sono diagnostici congelati. Nessun sottogruppo può salvare una primaria fallita.

### 6.4 Inferenza, dipendenza, competing risks e trial accounting

- Test paired sulla media e mediana dei delta; moving/block bootstrap per trading day e cluster evento/ticker-day. Più articoli sullo stesso evento non aumentano (n) indipendente.
- Serie degli IC giornalieri con HAC/Newey–West coerente con l'orizzonte; forward overlapping non è trattato come osservazione indipendente.
- Cumulative incidence/cause-specific hazard descrivono time, counter, risk, replacement e operational exits concorrenti. Fine–Gray può descrivere probabilità cumulative, ma non dimostra causalità né policy ottima.
- La primaria E1M vs E0 è l'unico confronto pre-registrato. E4 e la term structure D+1/D+3/D+5 sono descrittive/diagnostiche e non selezionano un vincitore sullo stesso campione.
- Tutti i trial storici noti — stop 2%, vol-scaled, soglie/orizzonti discussi e analisi informalmente viste — entrano nel registro. SPA/Reality Check si usano se si confronta l'intero catalogo esplorativo; DSR/PBO sono secondari e `INCONCLUSIVE` se il trial count è incompleto o (n) insufficiente.
- Una sensitivity surface serve a vedere plateau/fragilità; non trasforma nuove soglie in test. Ogni nuova soglia richiede nuovo forward.

### 6.5 Potenza e stopping

`NON DECIDIBILE` Il numero “213 sedute” della preregistrazione precedente deriva dalla varianza dell'IC e da una soglia IC, non dalla varianza del **paired exit delta**; non è una power analysis della domanda di uscita.

Prima dell'avvio si devono fissare (MDE_{net}), potenza (per esempio 80% o superiore), alpha della primaria e stima conservativa di \(\sigma_\Delta\) a livello di cluster. L'ordine di grandezza è:

\[
N_{cluster} \approx \left(\frac{(z_{1-\alpha}+z_{power})\sigma_\Delta}{MDE_{net}}\right)^2,
\]

poi inflazionato per intracluster correlation, missing non casuali e sequential monitoring. La varianza può essere stimata da segmento storico/pilot **senza usare la media per scegliere la policy**; una sola rivalutazione blinded della varianza può essere pre-specificata. Se il campione ottenibile non raggiunge (N_{cluster}), il risultato è `INCONCLUSIVE`, non negativo.

### 6.6 Separazione exit/upstream e risposta alla domanda 8

Il valore della exit si separa congelando gli ingressi e duplicando solo il lifecycle dopo il fill. In parallelo, ma fuori dalla primaria:

1. misurare la term structure da publication, first-seen, decision e fill per quantificare il movimento perso a monte;
2. mantenere coorti resolver corretto/errato e single-/multi-ticker, senza concatenarle;
3. confrontare last-article e event-aggregated **solo** come E4, con lo stesso ingresso;
4. riportare attrition e cause di esclusione, non “pulire” dopo aver visto i rendimenti;
5. usare il segmento post-fix come nuova popolazione; il pre-fix serve a failure analysis e varianza, non a conferma.

La separazione è falsificata se una candidata cambia chi o quando entra, il sizing iniziale o il price source: allora il delta non è attribuibile all'uscita.

## 7. Pre-registration draft

Questa bozza modifica la logica inferenziale della [pre-registrazione D+2 esistente](../04_PREREGISTRAZIONE_D2.md); non ne “conferma” le soglie.

### 7.1 Ipotesi primaria unica

`IPOTESI H1` A parità di entry stream, notional iniziale e prezzi eseguibili, **E1M** produce un expected net return paired maggiore di E0 di almeno (MDE_{net}), senza violare i gate di coda, costi, integrità e valore incrementale S1.

`H0`: il miglioramento è inferiore a (MDE_{net}). Il valore di (MDE_{net}) deve essere scelto ex ante dal risk/capital owner in unità di bps per trade e tradotto in dollari/NAV; non può essere ricavato dal miglior risultato storico.

### 7.2 Policy congelata

- D0 = seduta del primo fill RTH realistico; uscita time alla close di D+2.
- `max_signal_age=4h` governa solo l'ingresso.
- Nessuna exit per source silence, rank/top-5 drop, `expired`, `unknown` o semplice score sotto entry gate.
- Counter-signal exception: ensemble non-fallback, fresco, entity-resolved, materialmente nuovo e riferito alla tesi/evento iniziale. `≤−0,30` resta una soglia `IPOTESI` congelata per questo test; non è dichiarata simmetrica o ottima.
- Catastrophe stop: soglia determinata dal risk budget e congelata, wide; valutata come protezione di coda. Non è un prezzo garantito né una fonte di alpha.
- Nessun take-profit, trailing, scale-out, replacement o conditioning per evento/regime nella primaria.

### 7.3 Benchmark, metrica e inferenza

- **Benchmark primario:** E0 versionata al medesimo sample start, sullo stesso stream d'ingressi.
- **Benchmark economico secondario:** equal-weight della watchlist con cash e costi coerenti; valore incrementale portafoglio rispetto a S1.
- **Metrica primaria:** media \(\Delta_i=r^{net}_{E1M}-r^{net}_{E0}\), cluster event-day, con CI unilaterale pre-specificato.
- **Diagnostiche necessarie ma non primarie:** IC post-fill D+2, D+1/D+3, turnover, capitale-giorni, tail e lifecycle.
- **Power:** (N_{cluster}) fissato dalla varianza paired e (MDE_{net}), non dall'IC; parametri alpha/power registrati prima del sample start.

### 7.4 Gate congiunto

**PROMOTE** solo se tutte le condizioni tengono:

1. **integrità:** almeno 95% dei lifecycle ricostruibili; `unknown`/uscite semantiche spurie sotto la tolleranza pre-registrata; config dichiarata = runtime = shadow;
2. **economia primaria:** lower confidence bound del delta netto paired > (MDE_{net}), non soltanto >0;
3. **portafoglio:** excess netto E1M vs E0 e benchmark non negativo con CI coerente; capitale-giorni/opportunity cost incluso;
4. **coda:** ES, drawdown, gap loss e durata non peggiorano oltre tolleranze fissate dal risk owner prima dei risultati;
5. **costi:** segno e gate economico reggono allo scenario di slippage conservativo congelato;
6. **stabilità:** delta direzionalmente non contraddetto nei due sottoperiodi cronologici predefiniti e nei regimi ampio/ordinario; gli split non devono essere singolarmente significativi;
7. **trial correction:** nessun riuso della term structure per cambiare primaria; E4 resta soltanto diagnostica e non produce una decisione sullo stesso campione;
8. **S1:** marginal P&L/ES e capitale rispetto a S1 superano la soglia economica predefinita; un overlap arbitrario del 50% da solo non prova valore.

**REJECT/REDESIGN** a (N_{cluster}) se l'upper confidence bound del delta è ≤ (MDE_{net}), oppure se integrità/tail/costi rendono la policy non deployabile. **KEEP SHADOW / INCONCLUSIVE** se il CI contiene sia effetti economicamente utili sia inutili; non si promuove e non si cerca un nuovo orizzonte nello stesso campione.

### 7.5 Sample start, stopping rule e invalidazione

- **Sample start:** prima seduta completa successiva a un batch atomico datato che congela resolver/entity validation, fonti, ensemble, gate, universo, sizing, collisione S1, cost model, clock e shadow end-to-end. Finché la data non è registrata, (n=0).
- **Stop:** nessun early efficacy stop. Analisi decisionale soltanto a (N_{cluster}); review intermedie vedono integrità/rischio e statistiche blinded o descrittive senza cambiare policy. La fine amministrativa non è uno stopping rule statistico.
- **Riavvio obbligatorio:** qualsiasi modifica che può cambiare eleggibilità, timestamp, score, resolver, source mix, fill, exit o costi; perdita materiale di dati; divergenza shadow/runtime; reason code non ricostruibile oltre tolleranza; uso di label future nella policy.
- **Pausa senza riavvio:** outage completamente osservato che non genera ingressi e non altera i lifecycle già aperti, secondo regola registrata.

La preregistrazione è falsificata come strumento di governance se il trial ledger non include tutte le analisi viste o se (MDE_{net}), tail tolerance o cost scenario vengono fissati dopo l'accesso ai risultati.

## 8. Unknowns and data requests

| Stato | Dato richiesto, esatto | Decisione che sblocca |
|---|---|---|
| `NON DECIDIBILE` | Snapshot runtime/deploy al 2026-08-14: soglia counter-signal effettiva (`−0,20/−0,30/−0,35`), clock DAILY, anti-whipsaw, stop/TP attivi | Definire E0 storico e validare la policy congelata |
| `NON DECIDIBILE` | Export ordini broker: parent/legs, qty, fractionability, TIF, stop/limit, status/fill/cancel/reject, copertura residua per ogni posizione S4 | Stabilire se catastrophe stop e +6% abbiano agito e quale gap risk resti |
| `NON DECIDIBILE` | Event ledger con published/ingested/generated/decision/intent/fill e timezone originali | Term structure post-fill e ritardo strutturale senza leakage |
| `NON DECIDIBILE` | Storia completa di tutti gli articoli per ticker/evento, non soltanto l'ultimo; testo/hash e source lineage primaria→derivata | Novelty, repetition, E4 e attribuzione del counter-signal |
| `NON DECIDIBILE` | Gold sample etichettato point-in-time per ticker relevance, event type, novelty, source origin e thesis linkage | Gate data-quality e trasferibilità delle policy event-aware |
| `NON DECIDIBILE` | NBBO/quote o barre abbastanza fini per ordinare hit, più auction data; halt/LULD/delisting/corporate actions | Stop/trailing path, fill realistico, MAE/MFE |
| `NON DECIDIBILE` | Trade/intent eleggibili ma bloccati, collisione S1 e opportunità top-5 nel tempo | Capital opportunity cost, E8, valore marginale S1 |
| `NON DECIDIBILE` | Distribuzione paired \(\Delta\) storica/pilot per cluster, intracluster correlation, missing rate | (MDE_{net}), power e (N_{cluster}) validi |
| `NON DECIDIBILE` | Registro completo dei trial formali e informali già osservati | SPA/DSR/PBO e alpha family corretti |
| `NON DECIDIBILE` | Definizione del risk budget in dollari/NAV: tolleranza ES, drawdown, gap e capitale-giorni | Catastrophe threshold e gate tail non arbitrari |
| `NON DECIDIBILE` | Stato fonte/crawler e coverage expectation per ticker-session | Distinguere silenzio informativo da outage/non-coverage |

Altri unknown rilevanti: distribuzione della right tail S4; frequenza reale dei contro-segnali qualificati; capacità di riprodurre la close; comportamento delle fractional stop order al broker effettivo; regime/liquidità durante i pochi trade; dipendenza fra correzioni del resolver e popolazione di segnali. Nessuno può essere colmato con una soglia presa da un paper non comparabile.

## 9. Challenge to the existing D+2 decision

### 9.1 Miglior argomento a favore

`EVIDENZA ESTERNA` D+2 è nell'ordine di grandezza corretto per news daily: Heston–Sinha trovano 1–2 giorni; Jiang–Li–Wang documentano drift più forte nei primi giorni; limited attention e media diffusion rendono credibile un assorbimento non istantaneo. `EVIDENZA ALEMBIC` È inoltre una discontinuità concettuale utile: sostituisce scadenze software di 4 ore con una policy economica deterministica, riduce churn e separa freshness d'ingresso da holding period. La close offre un punto eseguibile/auditabile più credibile di una barriera intraday ricostruita male.

### 9.2 Miglior argomento contro

S4 è **long-only e seleziona notizie positive**. Proprio Heston–Sinha trovano che le positive sono incorporate rapidamente, mentre la persistenza più lunga è soprattutto negativa; Chan e Tetlock et al. sono anch'essi più forti sul lato bad-news. In più, una pipeline editoriale lenta può arrivare dopo il gap e ripubblicare informazione stantia, per cui D+2 può prolungare una posizione senza edge e aggiungere due overnight gap. Tetlock 2011 mostra reversal dopo stale news. Quindi la letteratura che rende D+2 plausibile può anche renderlo troppo lungo per la popolazione effettivamente comprata. Il dato Alembic sulla term structure pulita post-fill è ancora insufficiente.

### 9.3 Verdetto `MODIFY`

Mantengo D+2 come **una sola prior primaria**, ma modifico quattro elementi:

1. definizione non ambigua in session clock dalla seduta del fill;
2. counter-signal thesis-linked/novel/ensemble, non ultimo score qualsiasi;
3. delta netto paired vs E0 come metrica primaria della exit, IC come gate d'ingresso;
4. stopping/power basati sulla varianza del paired delta, non sul numero 213 derivato dall'IC.

### 9.4 Risposta esplicita alla domanda 10 e osservazioni falsificanti

La raccomandazione finale è E1M in shadow end-to-end, con E0 benchmark ed E4 soltanto diagnostica, senza stop stretto o take-profit. È falsificata concretamente da uno qualsiasi dei seguenti risultati a campione pre-registrato:

- upper CI del delta netto E1M−E0 ≤ (MDE_{net});
- paired marginal return D+1→D+2 non positivo e costi/capitale rendono D+1 dominante forward;
- tail risk/gap loss supera la tolleranza nonostante il catastrophe stop;
- counter-signal qualificato non migliora hold-vs-exit o produce troppi falsi stop;
- lifecycle non ricostruibile o popolazione cambia durante il test;
- valore marginale dopo S1 e capitale-giorni è non positivo;
- stale/derived news domina gli ingressi e il post-fill return mostra reversal.

L'osservazione contraria — delta netto con lower CI > (MDE_{net}), tail e costi nei limiti, stabilità forward e valore incrementale S1 — falsifica lo shadow prudenziale e giustifica un canary paper/minima size. Non dimostra che D+2 sia universalmente ottimo; dimostra che supera il benchmark dichiarato nella popolazione congelata.

## 10. Bibliography

Tutte le fonti seguenti sono primarie o documentazione ufficiale. “Full text” indica che è stata consultata una versione integrale accessibile; “abstract/preview” indica il limite di accesso.

1. Bailey, D. H., Borwein, J. M., López de Prado, M., & Zhu, Q. J. (2017). *The Probability of Backtest Overfitting*. Journal of Computational Finance, 20(4). [DOI](https://doi.org/10.21314/JCF.2016.322). **Abstract/preview publisher**.
2. Bailey, D. H., & López de Prado, M. (2014). *The Deflated Sharpe Ratio: Correcting for Selection Bias, Backtest Overfitting, and Non-Normality*. Journal of Portfolio Management, 40(5), 94–107. [DOI](https://doi.org/10.3905/jpm.2014.40.5.094); [author PDF](https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf). **Full text autore**.
3. Boudoukh, J., Feldman, R., Kogan, S., & Richardson, M. (2019). *Information, Trading, and Volatility: Evidence from Firm-Specific News*. Review of Financial Studies, 32(3), 992–1033. [DOI](https://doi.org/10.1093/rfs/hhy083); [author PDF](https://www.shimonkogan.com/_files/ugd/6739fc_ff6f6c2865bd4dc882ac065eab9bfe66.pdf). **Full text autore**.
4. Broadie, M., Glasserman, P., & Kou, S. (1997). *A Continuity Correction for Discrete Barrier Options*. Mathematical Finance, 7(4), 325–349. [DOI](https://doi.org/10.1111/1467-9965.00035). **Abstract/PDF publisher**.
5. Cederburg, S., O'Doherty, M. S., Wang, F., & Yan, X. S. (2020). *On the Performance of Volatility-Managed Portfolios*. Journal of Financial Economics, 138(1), 95–117. [DOI](https://doi.org/10.1016/j.jfineco.2020.04.015). **Preview esteso publisher**.
6. Chan, W. S. (2003). *Stock Price Reaction to News and No-News: Drift and Reversal after Headlines*. Journal of Financial Economics, 70(2), 223–260. [DOI](https://doi.org/10.1016/S0304-405X(03)00146-6); [working paper](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=262452). **Working paper/full; publisher preview**.
7. Dai, B., Marshall, B. R., Nguyen, N. H., & Visaltanachoti, N. (2021). *Risk Reduction Using Trailing Stop-Loss Rules*. International Review of Finance, 21(4), 1334–1352. [DOI](https://doi.org/10.1111/irfi.12328). **Full text publisher**.
8. DellaVigna, S., & Pollet, J. M. (2009). *Investor Inattention and Friday Earnings Announcements*. Journal of Finance, 64(2), 709–749. [DOI](https://doi.org/10.1111/j.1540-6261.2009.01447.x). **Abstract publisher**.
9. Fine, J. P., & Gray, R. J. (1999). *A Proportional Hazards Model for the Subdistribution of a Competing Risk*. Journal of the American Statistical Association, 94(446), 496–509. [DOI](https://doi.org/10.1080/01621459.1999.10474144). **Abstract publisher**.
10. Gârleanu, N., & Pedersen, L. H. (2013). *Dynamic Trading with Predictable Returns and Transaction Costs*. Journal of Finance, 68(6), 2309–2340. [DOI](https://doi.org/10.1111/jofi.12080). **Full text publisher**.
11. Glynn, P. W., & Iglehart, D. L. (1995). *Trading Securities Using Trailing Stops*. Management Science, 41(6), 1096–1106. [DOI](https://doi.org/10.1287/mnsc.41.6.1096). **Abstract/PDF publisher**.
12. Hansen, P. R. (2005). *A Test for Superior Predictive Ability*. Journal of Business & Economic Statistics, 23(4), 365–380. [DOI](https://doi.org/10.1198/073500105000000063). **Abstract publisher**.
13. Heston, S. L., & Sinha, N. R. (2016/2017). *News versus Sentiment: Predicting Stock Returns from News Stories*. FEDS 2016-048 / Financial Analysts Journal 73(3). [FEDS DOI e full text](https://doi.org/10.17016/FEDS.2016.048); [journal DOI](https://doi.org/10.2469/faj.v73.n3.3). **Full text Fed**.
14. Hirshleifer, D., Lim, S. S., & Teoh, S. H. (2009). *Driven to Distraction: Extraneous Events and Underreaction to Earnings News*. Journal of Finance, 64(5), 2289–2325. [DOI](https://doi.org/10.1111/j.1540-6261.2009.01501.x). **Abstract publisher**.
15. Imkeller, N., & Rogers, L. C. G. (2014). *Trading to Stops*. SIAM Journal on Financial Mathematics, 5(1), 753–781. [DOI](https://doi.org/10.1137/130911706). **Abstract publisher**.
16. Jiang, H., Li, S. Z., & Wang, H. (2021). *Pervasive Underreaction: Evidence from High-Frequency Data*. Journal of Financial Economics, 141(2), 573–599. [DOI](https://doi.org/10.1016/j.jfineco.2021.04.003). **Preview esteso publisher**.
17. Kaminski, K. M., & Lo, A. W. (2014). *When Do Stop-Loss Rules Stop Losses?* Journal of Financial Markets, 18, 234–254. [DOI](https://doi.org/10.1016/j.finmar.2013.07.001). **Preview esteso publisher**.
18. Leung, T., & Zhang, H. (2021). *Optimal Trading with a Trailing Stop*. Applied Mathematics & Optimization, 83, 669–698. [DOI](https://doi.org/10.1007/s00245-019-09559-0); [SSRN](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2895437). **Full text working paper**.
19. Lo, A. W., & Remorov, A. (2017). *Stop-Loss Strategies with Serial Correlation, Regime Switching, and Transaction Costs*. Journal of Financial Markets, 34, 1–15. [DOI](https://doi.org/10.1016/j.finmar.2017.02.003). **Preview esteso publisher**.
20. Mei, X., DeMiguel, V., & Nogales, F. J. (2016). *Multiperiod Portfolio Optimization with Multiple Risky Assets and General Transaction Costs*. Journal of Banking & Finance, 69, 108–120. [DOI](https://doi.org/10.1016/j.jbankfin.2016.04.002). **Preview esteso publisher**.
21. Moreira, A., & Muir, T. (2017). *Volatility-Managed Portfolios*. Journal of Finance, 72(4), 1611–1644. [DOI](https://doi.org/10.1111/jofi.12513). **Full text publisher**.
22. Neuhierl, A., Scherbina, A., & Schlusche, B. (2013). *Market Reaction to Corporate Press Releases*. Journal of Financial and Quantitative Analysis, 48(4), 1207–1240. [DOI](https://doi.org/10.1017/S002210901300046X); [author copy](https://escholarship.org/content/qt1xf8t2j6/qt1xf8t2j6.pdf). **Full text autore**.
23. Peress, J. (2014). *The Media and the Diffusion of Information in Financial Markets: Evidence from Newspaper Strikes*. Journal of Finance, 69(5), 2007–2043. [DOI](https://doi.org/10.1111/jofi.12179). **Abstract publisher**.
24. Tetlock, P. C. (2007). *Giving Content to Investor Sentiment: The Role of Media in the Stock Market*. Journal of Finance, 62(3), 1139–1168. [DOI](https://doi.org/10.1111/j.1540-6261.2007.01232.x). **Full text publisher**.
25. Tetlock, P. C. (2011). *All the News That's Fit to Reprint: Do Investors React to Stale Information?* Review of Financial Studies, 24(5), 1481–1512. [DOI](https://doi.org/10.1093/rfs/hhq141); [author full text](https://business.columbia.edu/sites/default/files-efs/pubfiles/3099/Tetlock%20Fit%20to%20Reprint%2010%2010.pdf). **Full text autore**.
26. Tetlock, P. C., Saar-Tsechansky, M., & Macskassy, S. (2008). *More Than Words: Quantifying Language to Measure Firms' Fundamentals*. Journal of Finance, 63(3), 1437–1467. [DOI](https://doi.org/10.1111/j.1540-6261.2008.01362.x); [author full text](https://www.columbia.edu/~pt2238/papers/TSM_More_Than_Words_JF_05_07.pdf). **Full text autore**.
27. Vaicenavicius, J. (2020). *Asset Liquidation Under Drift Uncertainty and Regime-Switching Volatility*. Applied Mathematics & Optimization, 81, 757–784. [DOI](https://doi.org/10.1007/s00245-018-9518-5). **Full text open access**.
28. White, H. (2000). *A Reality Check for Data Snooping*. Econometrica, 68(5), 1097–1126. [DOI](https://doi.org/10.1111/1468-0262.00152). **Abstract publisher**.
29. Alpaca Markets. *Orders at Alpaca*. [Documentazione ufficiale](https://docs.alpaca.markets/us/docs/orders-at-alpaca). **Full text ufficiale consultato il 2026-08-14; contenuto operativo temporalmente variabile, da archiviare al sample start**.
