# S4 — prompt per una ricerca approfondita sulle strategie di uscita

> Documento autosufficiente da consegnare a più LLM con accesso a Internet e, se possibile,
> insieme agli allegati elencati in fondo. Preparato il 2026-08-14 dopo una ricognizione del codice,
> dell'evidenza Alembic e di una prima selezione di letteratura primaria.
>
> Obiettivo: ottenere analisi indipendenti e verificabili, non un voto fra opzioni già formulate.
> Ogni modello deve poter contestare sia l'uscita attuale sia la decisione preliminare D+2.

---

## 0. Analisi preliminare da non trattare come conclusione

La diagnosi iniziale è che S4 non possiede ancora una vera **policy di uscita economica**. Il ramo
ordinario chiude una posizione quando essa non compare più nel target del ranker/portafoglio. Questo
confonde almeno quattro eventi diversi:

1. la tesi è stata smentita da informazione nuova;
2. il segnale si è indebolito, è scaduto o non è stato ripetuto;
3. un altro titolo ha occupato lo slot top-5;
4. il dato è stato filtrato, attribuito male o perso dalla pipeline.

Questi eventi non hanno lo stesso contenuto informativo. La prima opportunità di miglioramento non è
quindi scegliere subito fra stop-loss, take-profit e trailing stop, ma separare nel design:

- **thesis exit**: la previsione originaria non è più valida;
- **time exit**: è terminato l'orizzonte entro cui l'alpha avrebbe dovuto manifestarsi;
- **risk exit**: il rischio di coda non è più accettabile, anche se la tesi non è falsificata;
- **portfolio/capacity exit**: il capitale ha un uso alternativo migliore;
- **operational exit**: dati, broker, universo o controlli non permettono più una gestione affidabile.

La letteratura preliminare non supporta una regola universale:

- Kaminski e Lo mostrano che, sotto random walk, uno stop semplice riduce il rendimento atteso; può
  aggiungere valore in presenza di momentum. Lo e Remorov trovano inoltre che stop stretti su azioni
  USA tendono a sottoperformare dopo i costi, salvo sufficiente autocorrelazione. Questo è coerente
  con il replay interno che ha bocciato lo stop fisso al 2%, ma **non** boccia stop di catastrofe,
  trailing stop o uscite condizionate al regime.
- Heston e Sinha trovano che la news giornaliera predice in media per 1–2 giorni, con incorporazione
  più rapida delle notizie positive e reazione più lenta alle negative. Jiang, Li e Wang trovano
  drift per più giorni dopo news firm-specific. D+2 è quindi un candidato plausibile, ma il risultato
  non può essere trasferito automaticamente alla miscela di fonti, timestamp e ticker di S4.
- Tetlock e la letteratura successiva distinguono reversione del sentiment generico, sotto-reazione
  a informazione fondamentale e differenze per contenuto della notizia. Una sola scadenza per ogni
  evento può essere troppo grossolana.
- Una griglia di decine di soglie e orizzonti produrrebbe quasi certamente un vincitore spurio.
  White Reality Check, Hansen SPA, Deflated Sharpe Ratio/PBO e una vera finestra forward sono parte
  del problema di uscita, non un'appendice statistica.

L'ipotesi di lavoro più parsimoniosa è dunque un **time-stop primario dichiarato**, affiancato soltanto
da un contro-segnale affidabile e da una protezione di catastrofe. Il candidato già scelto dal PO è
D+2 in shadow end-to-end. Va però confrontato con benchmark seri e può essere respinto.

### Fonti primarie di partenza, non esaustive

- Kathryn Kaminski e Andrew W. Lo, *When Do Stop-Loss Rules Stop Losses?*:
  <https://papers.ssrn.com/sol3/papers.cfm?abstract_id=968338>
- Andrew W. Lo e Alexander Remorov, *Stop-loss Strategies with Serial Correlation, Regime Switching,
  and Transaction Costs*, DOI <https://doi.org/10.1016/j.finmar.2017.02.003>
- Steven L. Heston e Nitish R. Sinha, *News versus Sentiment: Predicting Stock Returns from News
  Stories*, Federal Reserve FEDS 2016-048: <https://doi.org/10.17016/FEDS.2016.048>
- Hao Jiang, Sophia Zhengzi Li e Hao Wang, *Pervasive Underreaction: Evidence from High-frequency
  Data*, DOI <https://doi.org/10.1016/j.jfineco.2021.04.003>
- Paul C. Tetlock, *Giving Content to Investor Sentiment*, DOI
  <https://doi.org/10.1111/j.1540-6261.2007.01232.x>
- Paul C. Tetlock, Maytal Saar-Tsechansky e Sofus Macskassy, *More Than Words*, versione autore:
  <https://www.columbia.edu/~pt2238/papers/TSM_More_Than_Words_02_07.pdf>
- Jacob Boudoukh, Ronen Feldman, Shimon Kogan e Matthew Richardson, *Information, Trading, and
  Volatility: Evidence from Firm-Specific News*, DOI <https://doi.org/10.1093/rfs/hhy083>
- Tim Leung e Hongzhong Zhang, *Optimal Trading with a Trailing Stop*:
  <https://arxiv.org/abs/1701.03960>
- Bochuan Dai et al., *Risk Reduction Using Trailing Stop-Loss Rules*, DOI
  <https://doi.org/10.1111/irfi.12328>
- Nicolae Gârleanu e Lasse Heje Pedersen, *Dynamic Trading with Predictable Returns and Transaction
  Costs*, DOI <https://doi.org/10.1111/jofi.12080>
- Mark Broadie, Paul Glasserman e Steven Kou, *A Continuity Correction for Discrete Barrier
  Options*, DOI <https://doi.org/10.1111/1467-9965.00035>
- Halbert White, *A Reality Check for Data Snooping*, DOI
  <https://doi.org/10.1111/1468-0262.00152>
- Peter R. Hansen, *A Test for Superior Predictive Ability*, DOI
  <https://doi.org/10.1198/073500105000000063>
- David H. Bailey e Marcos Lopez de Prado, *The Deflated Sharpe Ratio*:
  <https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf>
- Bailey, Borwein, Lopez de Prado e Zhu, *The Probability of Backtest Overfitting*, DOI
  <https://doi.org/10.21314/JCF.2016.322>

Questi lavori definiscono piste e cautele. Non dimostrano che una regola funzioni su S4.

---

# PROMPT DA CONSEGNARE AL MODELLO

Sei un senior quantitative researcher specializzato in event-driven equity strategies, news
analytics, market microstructure, optimal stopping e validazione statistica di trading system.

Devi svolgere una **ricerca approfondita e critica** sulle strategie di uscita applicabili a S4,
una strategia long-only basata su sentiment da news. Il fine non è massimizzare il P&L di un backtest
storico, ma individuare poche policy economicamente motivate, testabili senza leakage e capaci di
migliorare il rendimento netto con rischio controllato.

Usa tutti i canali a tua disposizione:

- conoscenza interna, soltanto per formulare piste e termini di ricerca;
- ricerca Web;
- Google Scholar, Crossref, SSRN, NBER, arXiv e siti degli autori;
- riviste accademiche e working paper originali;
- documentazione ufficiale del broker o delle API, se una proposta dipende dall'esecuzione;
- codice e documenti Alembic allegati;
- citation chaining in entrambe le direzioni: riferimenti del paper e lavori successivi che lo
  replicano, ne limitano il risultato o lo contraddicono.

Non usare blog, vendor marketing, social media o manuali divulgativi come prova. Possono servire a
trovare una fonte primaria, che dovrai poi leggere e citare. Se leggi solo abstract o snippet,
dichiaralo. Non inventare DOI, risultati, numerosità o soglie.

## 1. Domanda decisionale

Quale struttura di uscita dovrebbe essere confrontata con il comportamento corrente di S4 per
aumentare il P&L netto atteso senza introdurre un rischio di coda inaccettabile o un backtest
overfit? La decisione deve includere:

- la policy primaria;
- le eccezioni di rischio e di contro-segnale;
- la metrica di confronto;
- un protocollo di validazione;
- un criterio ex ante per promuovere, respingere o mantenere in shadow la policy.

Non assumere che D+2 sia corretto solo perché è già stato scelto come candidato. Trattalo come una
ipotesi falsificabile.

## 2. S4: fatti verificati e stato attuale

### 2.1 Strategia e ingresso

- S4 è un overlay tattico long-only da news, in paper trading e con promozione bloccata.
- Sleeve massima: 10% del NAV; top 5; slot fissi da circa 2% ciascuno. Gli slot non usati restano
  liquidi.
- Il segnale è `score = polarity × confidence`. Il ranker usa l'ultimo segnale per ticker.
- Prefiltri del ranker: `min_score=0,10`, `min_confidence=0,30`. Il vero gate d'ordine è separato,
  baseline 0,30 e può essere alzato dal feedback loop.
- I BUY da fallback FinBERT/single-model sono esclusi. La strategia è long-only: un punteggio
  negativo su un titolo non detenuto non genera uno short.
- `max_signal_age_hours=4`; la misura è su ore di parete, non ore di mercato.
- Il ciclo del portafoglio gira ogni 15 minuti. S4 dichiara rebalance DAILY, ma nel codice corrente
  è esplicitamente esclusa da `_REBALANCE_CLOCK_STRATEGIES`: l'istanza viene ricreata e il clock non
  viene ripristinato, quindi il percorso live può ricalcolare target e weight-drop intraday a ogni
  ciclo. La decisione futura D+2 richiede invece di applicare davvero DAILY. Verifica comunque il
  deploy/log: non confondere codice corrente, runtime e storia pre-fix.

### 2.2 Uscita ordinaria corrente

Il ranker non emette una decisione HOLD/SELL autonoma. Produce target weights. Il portfolio
orchestrator vende integralmente una posizione quando il simbolo scompare dal target aggregato.

I normali SELL di ribilanciamento attraversano:

1. min-hold di 90 minuti dall'ingresso;
2. protezione se esiste ancora un segnale positivo fresco sopra gate;
3. isteresi: il SELL deve persistere per 2 cicli;
4. anti-whipsaw S4 aggiuntivo disponibile ma disabilitato. Se attivato, si somma all'isteresi
   generica e non la sostituisce.

Le reason osservabili includono `below_entry_gate`, `whipsaw`, `expired`, `unknown`,
`fallback_filtered`, `entry_freshness_filtered` e `no_signal`. Alcune descrivono davvero il filtro
applicato; `unknown` dichiara esplicitamente che il meccanismo che ha azzerato il peso non è noto.

FIX-D tenta di preservare un vecchio segnale positivo per una posizione aperta quando non esiste un
segnale fresco sul ticker. Tuttavia sono state osservate uscite a peso zero anche dopo la
riammissione: il silenzio o una trasformazione di pipeline può ancora diventare economicamente un
SELL senza una smentita della tesi.

### 2.3 Uscite forzate e rischio

- Esiste un force-sell per contro-segnale sentiment fortemente negativo. Il default nel codice è
  `score < -0,20`, mentre la documentazione operativa ha indicato `-0,35` nel runtime; la freschezza
  massima è 60 minuti e i fallback non possono innescarlo. Dopo l'uscita c'è cooldown di re-entry di
  2 ore. **Verifica il valore effettivo nel deploy**: questa divergenza è un finding, non va risolta
  per supposizione.
- Lo stop protettivo sintetico è disabilitato: `risk.stop_loss=0,0`. Un replay interno su 245 trade
  ha trovato `no_protective` molto migliore dello stop fisso al 2% e del candidato vol-scaled nel
  suo OOS. Il campione è piccolo e mischia strategie, ma basta per escludere la riproposizione
  ingenua dello stesso stop al 2%.
- Il codice abilita di default un disaster stop broker `d_hard`, indicativamente 12–20%. Per
  posizioni frazionarie tenta un ordine GTC sul floor di azioni intere, lasciando non protetto il
  residuo sotto un'azione; per BUY non-fractionable può inserirlo nella bracket. Il commento YAML
  continua però a descriverlo come shadow telemetry: verifica env, ordini broker e copertura reale,
  senza assumere che commento e runtime coincidano.
- La stessa bracket sui BUY non-fractionable include di default un take-profit a +6%. Le posizioni
  fractionable/notional non ricevono quella gamba. Esiste quindi una exit dipendente dalla
  frazionabilità del titolo, non da una tesi S4 omogenea; va misurata e separata dal confronto.
- Esiste inoltre un alert su perdita non protetta del 15%; l'alert non è un ordine.
- Il drawdown cap è di portafoglio, non una policy di uscita S4 per-trade.

### 2.4 Evidenza osservata che motiva la ricerca

Nelle cinque sedute 2026-08-06–2026-08-12 S4 ha chiuso 9 round trip: 8 perdenti, netto −89,12
dollari. Nessuna delle 9 uscite è nata da un contro-segnale:

| meccanismo | n | interpretazione |
|---|---:|---|
| `below_entry_gate` | 4 | il segnale è sceso sotto la soglia di ingresso, non è diventato bearish |
| `unknown` / QS-07/FIX-D | 3 | vecchio positivo riammesso, nessun counter-signal, peso comunque zero |
| `expired` | 1 | segnale oltre 4 ore, nessun counter-signal |
| `whipsaw` | 1 | segnale fresco ma debole/non più nel target |

Tenuta mediana: 1h45. Sei uscite su nove sono avvenute esattamente dopo 1h45 o 4h15, cioè su
scadenze prodotte dal ciclo e dai filtri. L'evidenza è selezionata e insufficiente per stimare
l'alpha, ma sufficiente a mostrare che la durata osservata è in parte una proprietà del software.

Altri fatti rilevanti:

- segnali molto frequenti sullo stesso ticker possono sovrascriversi; l'ultimo articolo vince;
- articoli su società terze e difetti di entity resolution hanno generato segnali attribuiti al
  ticker sbagliato;
- molti ingressi arrivano dopo che gran parte del movimento giornaliero o del gap è già avvenuta;
- metà circa della watchlist può non avere articoli in una giornata;
- S4 condivide alcuni intenti con S1, quindi il valore incrementale e l'occupazione di capitale
  contano quanto il P&L standalone.

### 2.5 Decisione già presa, ma non ancora provata

Il 2026-08-14 il PO ha scelto come candidato uno **shadow end-to-end reversibile** con:

- time-stop primario alla chiusura di D+2;
- contro-segnale `<= -0,30` e stop di rischio come sole eccezioni;
- `max_signal_age` usato soltanto come filtro di ingresso;
- rebalance DAILY applicato;
- stessa selezione, ranking, collisione S1, fill virtuale, cost model, aging e uscita della futura
  versione eseguibile;
- configurazione di ingresso congelata durante la misura.

Questa è la baseline candidata, non un fatto scientifico. La tua analisi può raccomandare di
mantenerla, modificarla o respingerla.

## 3. Ricerca di letteratura richiesta

Costruisci una mappa della letteratura primaria almeno per queste famiglie:

1. **Decadimento dell'informazione da news**: event time, intraday vs overnight, 1–5 giorni,
   differenza positive/negative, fundamental vs generic/editorial, scheduled vs unscheduled,
   novelty/repetition e fonte primaria vs articolo derivato.
2. **Time stop / maximum holding period**: orizzonte fisso, session clock vs wall clock, chiusura
   della seduta vs N ore di mercato, uscite event-specific.
3. **Signal exit**: inversione del segnale, doppia soglia/isteresi, posterior probability della
   tesi, decadimento temporale, aggregazione di news multiple, conferma da prezzo o volume.
4. **Price/risk exit**: stop fisso, volatility-scaled, ATR, drawdown, trailing, break-even,
   catastrophe stop, gap risk e broker-side vs synthetic stop.
5. **Profit-taking**: take-profit fisso, trailing attivato dopo MFE, scale-out e loro effetto sulla
   coda destra dei rendimenti.
6. **Regime e stato**: volatilità, liquidità, spread, gap, market regime, event type, attenzione e
   crowdedness come variabili che possono modificare l'uscita.
7. **Optimal stopping e survival/hazard models**: soltanto se le assunzioni sono compatibili con
   un segnale news long-only; segnala apertamente i modelli matematicamente eleganti ma non
   trasferibili (per esempio risultati per spread OU mean-reverting).
8. **Portfolio replacement/capacity exit**: quando vendere perché un nuovo candidato ha valore
   atteso superiore, separando il rank turnover dalla falsificazione della tesi.
9. **Validazione**: path dependence, competing risks, costi, microstructure, multiple testing,
   non-stazionarietà e potenza statistica.
10. **Uscita parziale / no-trade region**: riduzione progressiva della posizione, hysteresis e
    frontiere di non-intervento come alternativa al full-close binario; chiarisci se la teoria dei
    costi di transazione è applicabile alla piccola size di S4.

Per ogni paper riporta:

- riferimento completo, DOI/URL e accesso full-text o solo abstract;
- universo, periodo, frequenza, lato long/short e tipo di strategia;
- definizione esatta dell'uscita;
- effetto economico, rischio e costi;
- replica o contraddizione successiva;
- trasferibilità a S4: alta, media, bassa, con motivazione.

Non usare risultati long-short come se valessero automaticamente per la gamba long. Non usare
risultati su mean reversion, FX, futures o market making senza esplicitare perché dovrebbero valere
per news momentum su azioni.

## 4. Candidate policy da confrontare

Non ottimizzare una griglia aperta. Parti da famiglie economicamente distinte e proponi un catalogo
ristretto. Come minimo valuta:

| ID | policy | ruolo nel confronto |
|---|---|---|
| E0 | uscita corrente a target weight zero | baseline as-is |
| E1 | D+2 time-stop + contro-segnale + catastrophe stop | candidata già scelta |
| E2 | D+1 e D+3 | diagnostica della term structure, non due nuovi vincitori da scegliere ex post |
| E3 | counter-signal only con massimo holding dichiarato | test della falsificazione della tesi |
| E4 | time-stop + uscita su segnale aggregato/decaduto, non ultimo articolo | separa exit design da input churn |
| E5 | time-stop + wide volatility/catastrophe stop | protezione di coda senza noise stop |
| E6 | trailing attivato solo dopo MFE predefinita | verifica se protegge vincitori senza troncare subito la coda destra |
| E7 | policy event-type/segno-specifica | soltanto se la letteratura e la numerosità la rendono identificabile |
| E8 | replacement exit basata su costo-opportunità | separa capacità top-5 e validità della tesi |
| E9 | de-risking parziale / posterior expected-edge exit | diagnostica se il full-close binario è dominato, senza presumere che la complessità sia implementabile |

Puoi eliminare o aggiungere policy, ma ogni aggiunta consuma un trial e alza l'onere statistico.
Spiega perché il beneficio informativo giustifica quel trial.

## 5. Disegno empirico richiesto

Progetta un confronto **a ingressi congelati**: tutte le exit candidate devono ricevere gli stessi
trade/intenti di ingresso, gli stessi timestamp, lo stesso sizing iniziale e gli stessi prezzi
eseguibili. In caso contrario non sapremo se il risultato deriva dall'uscita.

### 5.1 Dataset minimo e ricostruzione

Specifica le query/dati necessari per costruire un event ledger point-in-time con almeno:

- `signal_id`, articolo/evento, ticker risolto, source, published/ingested/generated/decision time;
- score, confidence, modello, fallback, novelty e appartenenza reale dell'articolo al ticker;
- entry intent, fill eseguibile, size, collisione S1, costi e spread;
- barre intraday e daily con corporate actions;
- MAE, MFE, tempo a MAE/MFE, gap overnight, volatilità e liquidità all'ingresso;
- ogni condizione di uscita candidata e prezzo realisticamente eseguibile;
- post-exit drift a 1h, close, D+1, D+2, D+3 e D+5;
- motivo di censura o dato mancante.

Evita look-ahead: un tipo evento, una novelty score o una validazione ticker calcolati dopo il trade
non possono entrare nella policy senza una versione point-in-time disponibile allora.

### 5.2 Metriche

Non limitarti a win rate o P&L realizzato. Includi almeno:

- P&L netto e excess return rispetto a E0 e benchmark equal-weight della watchlist;
- paired trade-level delta sugli stessi ingressi;
- turnover, costi, slippage e capitale-giorni occupato;
- expectancy, mediana, hit rate, profit factor e payoff win/loss;
- volatilità, downside deviation, VaR/ES con cautela, max drawdown e drawdown duration;
- skewness e contributo della coda destra: quanti grandi vincitori vengono troncati;
- false-stop rate: uscita in perdita seguita da recupero entro l'orizzonte della tesi;
- giveback dalla MFE e perdita evitata rispetto alla MAE;
- performance per event type, segno, ora, gap, liquidità, source e regime, ma come diagnostica
  predefinita, non come licenza per scegliere il sottogruppo migliore;
- overlap e valore incrementale rispetto a S1.

### 5.3 Inferenza e anti-overfitting

- Usa test paired e bootstrap a blocchi per giorno/event cluster; più articoli sullo stesso evento o
  ticker-giorno non sono osservazioni indipendenti.
- Gestisci forward return sovrapposti con HAC/Newey-West o bootstrap coerente con l'orizzonte.
- Conta e pubblica tutti i trial, incluse analisi precedenti già viste dal team.
- Per scegliere fra policy usa White Reality Check o Hansen SPA; affianca DSR/PBO se le assunzioni e
  il campione lo consentono. Spiega limiti e implementazione, non citare solo il nome.
- Se esplori la term structure `{1h, 4h, close, D+1, D+2, D+3, D+5}`, usa il risultato per fissare
  una singola ipotesi confirmatoria su dati forward mai letti. Il segmento esplorativo non diventa
  OOS per rinomina.
- Prevedi una power analysis basata sulla varianza dei paired deltas e un minimum detectable effect
  economicamente sensato. Se il campione non può decidere, scrivi `INCONCLUSIVE`.
- Considera competing risks: un trade che raggiunge prima counter-signal, stop o time barrier non
  può essere trattato come se le altre barriere fossero indipendenti.
- Indica come trattare delisting, halt, overnight gap, partial fill, market close, missing bar e
  corporate action.

### 5.4 Gate richiesto

Proponi un gate congiunto, non un singolo Sharpe. Deve includere almeno:

1. integrità del lifecycle e reason code;
2. miglioramento economico netto paired rispetto a E0;
3. rischio di coda non peggiore oltre una tolleranza predefinita;
4. robustezza a costi/slippage conservativi;
5. stabilità direzionale per sottoperiodo e regime;
6. correzione per le policy provate;
7. valore incrementale rispetto a S1 e uso del capitale.

Fornisci numeri soltanto se sono derivati da dati o letteratura comparabile. Altrimenti definisci il
metodo con cui stimarli prima della pre-registrazione.

## 6. Domande a cui devi rispondere esplicitamente

1. La policy corrente è una exit strategy o un effetto collaterale del ranker? Quali rami sono
   razionali e quali sono difetti di semantica o osservabilità?
2. Qual è la term structure dell'alpha da news più plausibile per una pipeline editoriale lenta?
   D+2 ha supporto sufficiente come prior? Quando sarebbe troppo corto o troppo lungo?
3. Il semplice silenzio della fonte deve mai chiudere una posizione? Se sì, sotto quali assunzioni e
   con quale clock?
4. Quale evidenza giustifica un'uscita su contro-segnale? Deve usare lo stesso modello dell'ingresso,
   un ensemble separato, una soglia simmetrica o un posterior sulla tesi originaria?
5. Il replay che boccia lo stop al 2% cosa consente davvero di concludere, e cosa no?
6. C'è evidenza per take-profit o trailing stop in una news-momentum long-only, oppure rischiano di
   troncare proprio i pochi vincitori che pagano la strategia?
7. È meglio una policy unica e parsimoniosa o una policy condizionata per segno/tipo evento/regime?
   Quanta numerosità servirebbe per la seconda?
8. Come separare il valore della exit dal problema a monte dell'ultimo articolo, del resolver ticker
   e del timing tardivo?
9. Quali strategie consolidate non stiamo adottando e quali sono realmente trasferibili a S4?
10. Qual è la tua raccomandazione finale, e quale osservazione concreta la falsificherebbe?

## 7. Formato obbligatorio della risposta

Produci le sezioni seguenti, in quest'ordine:

1. **Executive verdict** — massimo 300 parole, con policy raccomandata e grado di confidenza.
2. **As-is audit** — diagramma o tabella dei rami di uscita correnti, trigger, clock, bypass,
   interazioni e failure mode.
3. **Literature evidence table** — una riga per fonte primaria, con trasferibilità a S4.
4. **Strategy catalog** — policy, razionale, vantaggi, failure mode, complessità e trial cost.
5. **Shortlist** — massimo tre policy da portare al confronto confirmatorio; tutto il resto va
   etichettato diagnostico o respinto.
6. **Empirical protocol** — ledger, controfattuali, prezzi, costi, metriche, inferenza, potenza e
   gestione del multiple testing.
7. **Pre-registration draft** — una sola ipotesi primaria, benchmark, metrica primaria, gate,
   sample start, stopping rule e condizioni di invalidazione/riavvio del campione.
8. **Unknowns and data requests** — ciò che non è decidibile e i dati esatti che mancano.
9. **Challenge to the existing D+2 decision** — l'argomento migliore a favore e quello migliore
   contro; verdetto finale `KEEP`, `MODIFY` o `REJECT`.
10. **Bibliography** — DOI/URL diretti e indicazione full-text/abstract.

Ogni proposta deve avere una condizione di falsificazione. Distingui con etichette visibili:
`EVIDENZA ESTERNA`, `EVIDENZA ALEMBIC`, `INFERENZA`, `IPOTESI`, `NON DECIDIBILE`.

Non proporre modifiche al codice in questa fase. Non presentare come “miglioramento dei guadagni” una
riduzione della volatilità che abbassa il P&L atteso, o viceversa: mostra separatamente rendimento,
rischio e utilità economica.

## 8. Allegati da fornire al modello, in ordine di priorità

1. `docs/s4-exit-research-2026-08-14/03_DECISIONE_PRECEDENTE_CONSOLIDATA.md`
2. export completo dell'issue GitHub `#242`, inclusa la decisione del 2026-08-14
3. `src/strategies/s4/{config.py,ranking.py,strategy.py}`
4. `src/portfolio/orchestrator.py` e `src/portfolio/exit_classification.py`
5. sezioni rilevanti di `src/workers/portfolio_scheduler.py`: freshness/FIX-D, hold minimo,
   hysteresis, decision logging, stop e sentiment reversal
6. `config/trading.yaml` e `config/strategies.yaml`
7. `docs/stop_loss_calibration_handback_2026-07-15.md`
8. `docs/ALPHA_MISS_REPORT_2026-08-{06,07,10,11,12}.md`
9. `docs/evidence/s4_ic.json` e il protocollo IC/kill criterion corrente
10. `docs/s4-exit-research-2026-08-14/02_ANALISI_PRELIMINARE_LETTERATURA.md`

In caso di conflitto, distingui:

- **codice corrente**: cosa farebbe il repository oggi;
- **config/runtime effettivo**: cosa è davvero deployato;
- **evidenza storica**: cosa è successo prima o dopo specifici fix;
- **decisione futura**: cosa è stato scelto ma non ancora validato.

Non colmare una divergenza con una supposizione. Registrala come dato mancante o finding.

---

## Nota per il consolidamento multi-LLM

Inviare lo stesso prompt, gli stessi allegati e la stessa data cutoff a ogni modello. Conservare
anche risposte negative o incomplete. Nel consolidamento non contare i voti come probabilità:
confrontare invece fonti, assunzioni, policy shortlisted, criteri di falsificazione e divergenze.
Una proposta citata da più modelli ma derivata dallo stesso paper resta una sola evidenza.
