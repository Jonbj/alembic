# S3 strategy review: decision brief per il POC di design alignment

**Data:** 2026-07-20  
**Scope:** sola analisi documentale, statica e di letteratura; nessun nuovo backtest,
codice strategico, acquisto dati, modifica a issue o promozione operativa.  
**Domanda:** autorizzare o respingere un POC offline che misuri la S3 originariamente
approvata contro un benchmark momentum comparabile.  
**Stato della fonte di verita:** la roadmap resta la issue GitHub
[#21](https://github.com/Jonbj/alembic/issues/21); questa nota non e un tracker.

## Verdetto esecutivo

**Raccomandazione (inferenza): autorizzare un POC offline, circoscritto e
pre-registrato; non autorizzare paper trading, broker wiring o allocazione.**

La ragione non e che S3 sia gia validata. E l'opposto: esiste un prior accademico forte
per il momentum cross-sectional, ma oggi Alembic non possiede una misura decisionale
della propria variante. Il codice corrente non riproduce il design originale e il report
del 1 giugno misura una strategia diversa con dati, soglie e metodologia poi cambiati.
Un POC A/B correttamente costruito ha quindi valore informativo; un semplice rerun del
codice corrente no.

La decisione da prendere e limitata:

- **GO** significa finanziare una specifica e un backtest offline riproducibile della
  variante originale contro un benchmark, con stop condition dichiarate prima dei
  risultati;
- **NO-GO** significa archiviare S3 senza reinterpretare il vecchio Sharpe `0.148` come
  confutazione della variante originale;
- nessuno dei due esiti autorizza capitale o paper trading.

## 1. Domanda decisionale ancora irrisolta

La issue [#55](https://github.com/Jonbj/alembic/issues/55), aperta, non assegnata e
`ready-for-human` alla data di questa ricerca, chiede al PO di autorizzare o respingere un
"design-alignment POC" S3. Definisce come variante primaria il 12-1 beta-adjusted
long-only originale, come ablation il total momentum 12-1 e come eventuale comparator
successivo il residual momentum FF3. Il commento del PO nella stessa issue ha risolto
soltanto il ramo S2 e, al momento del commento, dichiarava S3 e S7 ancora aperte. La
roadmap #21 registra decisioni S7 successive; in pratica, il ramo di #55 che questa nota
trova ancora senza decisione e S3.

La roadmap [#21](https://github.com/Jonbj/alembic/issues/21), letta il 2026-07-20, non
contiene ancora una decisione S3 nella sezione `Decisions-so-far`. La issue
[#53](https://github.com/Jonbj/alembic/issues/53) e invece un contenitore Tier 5
`needs-triage` per il backlog Sprint 2/3: non sostituisce la decisione PO di #55 e non e
un'autorizzazione a implementare.

**Conclusione fattuale:** l'ultimo lavoro di analisi ha ristretto correttamente la scelta,
ma non l'ha chiusa. La prossima mossa non e selezionare una task `ready-for-agent`; e una
decisione umana sul budget informativo del POC.

## 2. Inventario degli artefatti S3

### 2.1 Decisioni, specifiche e documenti

| Artefatto | Che cosa stabilisce | Uso corretto oggi |
|---|---|---|
| [Issue #55](https://github.com/Jonbj/alembic/issues/55) | Domanda PO corrente e acceptance criteria | Fonte della decisione ancora aperta |
| [Issue #21](https://github.com/Jonbj/alembic/issues/21) | Stato roadmap e decisioni consolidate | Unica fonte di verita sullo stato |
| [`01_strategy_design.md`](../archive/2026-06-p0-p2-controlled-paper-history/01_initial_specs/01_strategy_design.md) | Design S3 originale e successiva demotion storica | Fonte normativa della variante A da misurare, non stato corrente |
| [`RESEARCH_S2_S3_S7_PRIMARY_LITERATURE_2026-07-15.md`](RESEARCH_S2_S3_S7_PRIMARY_LITERATURE_2026-07-15.md) | Review comparativa e gap analysis precedente | Antecedente analitico; questa nota isola la decisione S3 |
| [`strategies.md`](strategies.md), [`ARCHITECTURE.md`](ARCHITECTURE.md), [`user_guide.md`](user_guide.md) | Descrizione prodotto e stato `research`/0% | Contesto operativo, non evidenza di performance |
| [`RESIDUAL_RISK_REGISTER.md`](RESIDUAL_RISK_REGISTER.md) | S3 non deve essere promossa senza review dedicata | Guardrail di governance ancora coerente |
| [`investment-strategy-analysis-2026-06-06.md`](archive/2026-05-reviews/investment-strategy-analysis-2026-06-06.md) | Review storica basata anche sul report di maggio | Evidenza storica, superata dove codice e gate sono cambiati |

Le design spec e le review storiche non tracciano avanzamento. In particolare, la frase
"gate 3 e 5 falliti" descrive un artifact esplorativo del 2026-06-01, non un risultato
valido sui gate e sul codice correnti.

### 2.2 Codice, dati, test e report

| Superficie | Stato osservato nel repository |
|---|---|
| [`signal.py`](../src/strategies/s3/signal.py) | Beta rolling contro SPY, total return `t-252`→`t`, sottrazione del market momentum e ranking in decili |
| [`strategy.py`](../src/strategies/s3/strategy.py) | Long decile 10, short decile 1 di default; inverse-vol sulla finestra `beta_window=252`; cap 20%; pesi non normalizzati |
| [`universe.py`](../src/strategies/s3/universe.py) | Filtro PIT se interrogato a una data, ma solo per prezzo, storia e ADV; il market-cap filter configurato non e implementato |
| [`backtest.py`](../src/strategies/s3/backtest.py) | Seleziona una sola volta i primi 50 nomi attivi alla data finale e li riusa indietro; produce walk-forward e gate report |
| [`walkforward/runner.py`](../src/backtest/walkforward/runner.py) | Riusa la stessa istanza mutabile della strategia tra finestre |
| [`registry.py`](../src/strategies/registry.py) | Registra S1, S2 e S4, non S3 |
| [`orchestrator.py`](../src/portfolio/orchestrator.py) | Il path `compute_target_weights()` gestisce esplicitamente S1 e S4; per un altro ID restituisce pesi vuoti |
| [`config/strategies.yaml`](../config/strategies.yaml) | S3 disabilitata, allocation 0%, mode `research` |
| [`config/universe.yaml`](../config/universe.yaml), [`sp500_tickers.csv`](../data/sp500_tickers.csv) | Source statico di 57 righe dati; include una lista corrente, non membership storica PIT |
| [`tests/strategies/`](../tests/strategies/), [`test_p1_s3_sizing_pit.py`](../tests/test_p1_s3_sizing_pit.py), [`test_p2_validation_truth.py`](../tests/test_p2_validation_truth.py) | Buona copertura del comportamento codificato, incluso il fix PIT del sizing; non provano validita economica o assenza di survivorship |
| [`reports/s3_backtest/`](../reports/s3_backtest/) | `summary.json` e `gate_report.json`, modificati il 2026-06-01 e ignorati da Git; nessun manifest dati/versione sufficiente a riprodurre il run |

**Evidenza:** S3 e correttamente contenuta a 0% e fuori dal registry operativo. Non e una
strategia pronta da accendere: oltre ai problemi empirici, manca il contratto di
integrazione. Questo e desiderabile finche #55 non viene risolta.

## 3. Design originale, codice corrente e report storico

### 3.1 Differenze materiali

| Dimensione | Variante A richiesta da #55 / design originale | Codice corrente | Impatto probatorio |
|---|---|---|---|
| Return di formazione | `log(P[t-21]/P[t-252])`, cioe 12-1 | `P[t]/P[t-252]-1` | Include il mese che il design esclude |
| Correzione mercato | Beta 252d × momentum SPY 12-1 | Beta 252d × momentum SPY fino a `t` | Testa una diversa ipotesi beta-adjusted |
| Leg | Top decile long; bottom escluso | Top long e bottom short per default | Cambia payoff, costi, margine e crash exposure |
| Sizing | Inverse-vol 60d, normalizzato | Inverse-vol 252d, non normalizzato | Cambia concentrazione, cash e gross exposure |
| Cap | 10% dentro il bucket S3 | 20% | Raddoppia la concentrazione ammessa |
| Universo | US large/mid liquide secondo regole | Primi 50 survivor liquidi alla data finale | Introduce selection e survivorship bias |
| Operativita | Nessuna prima dei gate | Nessun path registry/orchestrator | Coerente con lo stato research |

Queste differenze sono leggibili direttamente nella
[specifica originale](../archive/2026-06-p0-p2-controlled-paper-history/01_initial_specs/01_strategy_design.md),
in [`signal.py`](../src/strategies/s3/signal.py),
[`strategy.py`](../src/strategies/s3/strategy.py) e
[`backtest.py`](../src/strategies/s3/backtest.py). Non sono dettagli di tuning: definiscono
un portafoglio economicamente diverso.

### 3.2 Perche il vecchio `0.148` non decide #55

Il report storico dichiara OOS Sharpe `0.1483`, gate 3 robustness FAIL e gate 5 stress
FAIL. Ma:

1. i file sono datati 2026-06-01, mentre il sizing PIT e stato corretto il 19 giugno
   (`e15d5e7`) e la metodologia stress il 20 giugno (`d6d7f44`);
2. il report applicava `min_sharpe=0.0` al Gate 1 e `min_oos_sharpe=0.0` al Gate 2;
   il runner corrente usa rispettivamente `0.5` e `0.3`, introdotti il 3 luglio
   (`05cb65a`), come mostra [`GateConfig`](../src/backtest/gates/runner.py);
3. il report usa due regimi e uno stress ex-post chiamato `worst_drawdown`; il codice
   corrente richiede almeno tre regimi e usa stress storici estratti esplicitamente;
4. `n_trials=1` rende il DSR del report incapace di riflettere le varianti e le
   perturbazioni effettivamente esplorate;
5. il run misura la variante corrente long-short, non la variante A di #55;
6. report gitignored, assenza di manifest del dataset e universo scelto alla data finale
   impediscono una riproduzione auditabile.

**Inferenza:** con le soglie attuali quello stesso numero non supererebbe almeno Gate 1 e
Gate 2, ma neppure questa riclassificazione sarebbe un test valido della variante A. Il
report puo motivare cautela; non puo essere usato ne come GO ne come NO-GO sul POC.

## 4. Che cosa sostiene davvero la letteratura primaria

### 4.1 Evidenza trasferibile

Jegadeesh e Titman documentano rendimenti positivi di strategie che comprano winner e
vendono loser con formation/holding period di 3-12 mesi. E evidenza primaria per il
fenomeno cross-sectional, non per i parametri proprietari di Alembic
([paper originale](https://doi.org/10.1111/j.1540-6261.1993.tb04702.x)).

La Data Library di Kenneth French costruisce il fattore momentum con rendimenti pregressi
2-12 e come differenza high-minus-low su sei portafogli size × prior-return. Include NYSE,
AMEX e NASDAQ e richiede storia del rendimento coerente alla data di formazione
([metodologia first-party](https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/Data_Library/det_mom_factor_daily.html)).
Questa fonte conferma due elementi trasferibili: esclusione del mese recente e ranking su
un cross-section ampio. Non conferma la correzione a un solo beta ne il solo leg long.

Blitz, Huij e Martens trovano che ordinare sui residui riduce le esposizioni variabili ai
fattori Fama-French e migliora i risk-adjusted profits rispetto al total momentum. La loro
costruzione usa pero residui da un modello FF3 e un portafoglio long-short; non e la
sottrazione `stock momentum - beta × SPY momentum` di Alembic
([versione pubblicata degli autori](https://pure.eur.nl/files/46882404/ResidualMomentum-2011.pdf)).

**Inferenza:** la letteratura rende ragionevole misurare S3, ma non permette di saltare
l'ablation A/B. Il beneficio incrementale della correzione beta proprietaria e proprio
la quantita ignota che il POC deve identificare.

### 4.2 Rischi che il POC deve conservare, non ottimizzare via

Daniel e Moskowitz mostrano che le strategie momentum possono subire perdite rare e
persistenti, soprattutto dopo ribassi di mercato, con volatilita elevata e rimbalzi
contemporanei ([paper NBER degli autori](https://www.nber.org/papers/w20439)). Il loser
leg e centrale in quella dinamica: togliere lo short modifica il rischio, ma non autorizza
a presumere che lo elimini.

I costi non sono un'aggiunta cosmetica. Korajczyk e Sadka stimano capacita finita e
risultati molto dipendenti da liquidity/value weighting; le loro strategie con maggiore
break-even size sono quelle liquidity-weighted o ibride
([paper originale](https://doi.org/10.1111/j.1540-6261.2004.00656.x)). Questo rende
obbligatorio mantenere uguali universo, weighting e cost model nel confronto A/B.

Un dataset che conserva solo titoli correnti non registra la perdita terminale di chi e
uscito dal campione. La documentazione CRSP definisce esplicitamente il delisting return
come il rendimento fra l'ultimo prezzo negoziato e il valore successivo al delisting, fino
a `-1` quando il titolo e dichiarato senza valore
([guida first-party CRSP](https://www.crsp.org/crsp_pdf/crsp-us-stock-indexes-databases-data-descriptions-guide-crspaccess/)).
Questa e evidenza che il dataset decisionale deve rappresentare corporate actions e
delisting; non implica che Alembic debba necessariamente acquistare CRSP.

Infine, il Deflated Sharpe Ratio corregge selection bias, multiple testing e ritorni non
normali. Inserire `n_trials=1` dopo avere osservato piu varianti non realizza tale scopo
([Bailey e Lopez de Prado, paper originale](https://papers.ssrn.com/sol3/Delivery.cfm/SSRN_ID2460551_code87814.pdf?abstractid=2460551)).

## 5. Gap probatori da chiudere

| Domanda decisionale | Evidenza disponibile | Evidenza mancante | Stop condition proposta (inferenza) |
|---|---|---|---|
| Il momentum 12-1 funziona nel dominio Alembic? | Prior accademico robusto, ma report interno invalido | OOS netto su universo PIT coerente | Stop se il benchmark B non supera i gate pre-registrati |
| La correzione beta aggiunge valore? | Solo plausibilita economica; comparator FF3 non equivalente | Delta A−B su return, tail risk, turnover e diversificazione | Semplificare a B se A non migliora materialmente il profilo netto OOS |
| Il long-only conserva un payoff utile? | Letteratura prevalente high-minus-low | Beta, sector exposure, cash drag e drawdown del solo long | Stop se il risultato e spiegato da beta/sector tilt senza valore incrementale |
| Il risultato sopravvive ai bias dati? | Universe loader PIT isolato, ma full runner usa survivor finali | Membership/eligibility a ogni rebalance, corporate actions, delisting | Nessuna decisione con lista corrente riusata indietro |
| Il risultato sopravvive ai costi? | Nessun artifact costed riproducibile | Spread, fee e impact coerenti con liquidita/turnover | Stop se l'hurdle esiste solo gross-of-cost |
| E complementare a S1? | Motivazione narrativa, nessuna misura valida | Correlazione OOS, marginal risk contribution, portfolio delta | Stop se non migliora il portafoglio rispetto a S1+cash |
| E robusto senza data snooping? | Tre perturbazioni storiche; DSR con `n_trials=1` | Registro completo dei trial e final holdout intatto | Stop se l'esito dipende dalla scelta ex-post della variante |
| Il run e auditabile? | JSON locali gitignored | Manifest dati, commit, config, checksum, cost model e split | Nessun gate decisionale senza artifact versionato |

## 6. POC minimo che renderebbe decidibile S3

Questa sezione e una **proposta inferenziale**, non un risultato empirico e non autorizza
l'implementazione prima della decisione PO.

### 6.1 Congelare prima di eseguire

1. **Variante A primaria:** momentum 12-1 in log return, correzione beta SPY coerente
   sullo stesso 12-1, top decile long-only, vol 60d, pesi normalizzati, cap 10%.
2. **Variante B ablation:** stessa pipeline, ma total momentum 12-1 senza correzione beta.
3. **Nessuna C nello stesso ciclo decisionale:** il residual FF3 puo essere un POC
   successivo; aggiungerlo ora aumenta i trial e confonde la domanda A−B.
4. Regola di universo US common-stock large/mid e liquidita definita ex ante, valutata a
   ogni rebalance. Nessuna selezione dei survivor alla data finale e nessun `active[:50]`.
5. Split temporali, holdout finale, cost model, gate, numero di trial e stop condition
   fissati in un manifest prima di osservare i risultati finali.

### 6.2 Evidenza da produrre

- risultati gross e net per A e B con gli stessi dati e gli stessi vincoli;
- coverage per data, turnover, concentrazione, gross/net exposure, beta e sector exposure;
- walk-forward con istanza strategia isolata per finestra;
- periodi di crash/rimbalzo momentum visibili separatamente, non scelti ex post;
- block-bootstrap confidence interval e DSR con il numero reale di trial;
- confronto incrementale con S1+cash: correlazione OOS, marginal risk contribution,
  drawdown ed effetto sul portfolio Sharpe;
- artifact versionato con commit, config, provenance/checksum dati, intervalli temporali e
  cost model.

### 6.3 Regola di uscita

Il POC e riuscito anche se produce un NO-GO, purche chiuda l'incertezza. Una regola
decisionale coerente e:

- **archiviare S3** se B non supera i gate netti pre-registrati;
- **archiviare la correzione beta e semplificare** se B e valida ma A non aggiunge valore
  OOS netto o diversificazione;
- **aprire una nuova child issue di #21** solo se A supera i gate e aggiunge valore a
  S1+cash; quella child coprirebbe hardening e solo successivamente shadow, non una
  promozione automatica;
- trattare un esito ambiguo come NO-GO temporaneo, non come invito a tuning sul holdout.

## 7. Limiti della presente ricerca

- Non e stato eseguito un nuovo backtest; nessun claim di performance corrente e quindi
  possibile.
- Non e stata verificata la disponibilita commerciale o il prezzo di dataset PIT: la nota
  identifica il requisito probatorio, non sceglie un vendor.
- La letteratura primaria valida famiglie di momentum, non la variante beta-adjusted
  long-only di Alembic. Il trasferimento a S3 resta un'inferenza da testare.
- La verifica del repository e statica al 2026-07-20; processi paralleli possono cambiare
  il working tree, mentre lo stato roadmap deve sempre essere riletto su GitHub.
- I test esistenti dimostrano conformita al comportamento codificato, non assenza di
  survivorship, validita economica o eseguibilita del loser leg.

## 8. Decisione richiesta al PO

**Scelta raccomandata:** approvare il solo POC A/B descritto sopra, con budget e tempo
limitati, e registrare su #55 che:

1. l'oggetto primario e la variante A originale, non il codice corrente;
2. B e il benchmark obbligatorio e C e rinviata;
3. il vecchio report S3 e storico/non decisionale;
4. il POC non abilita paper trading;
5. ogni lavoro successivo richiede una child separata di #21 e un nuovo gate umano.

Questa scelta e giustificata dal valore dell'informazione, non da una promessa di alpha:
il fenomeno momentum merita un test fedele; Alembic non possiede ancora quel test.
