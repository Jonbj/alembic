# Alembic vs TradingAgents

**Analisi comparativa funzionale, logica e strategica**

**Data:** 2026-07-15

**Alembic:** `main` @ `13fd4ef78746eefc112830cbfa4f6d6f07d2511a`

**TradingAgents:** `v0.3.1` @ `01477f9afb7a47b849ed4c9259d3a9a4738d9fda`

**Metodo:** lettura del codice e della documentazione locale, verifica della release upstream e analisi del paper primario. Il branch Alembic e' avanzato da `23aa387` a `13fd4ef` durante l'analisi; il delta, limitato a roadmap/documentazione, e' stato verificato. Nessuna inferenza LLM live o backtest e' stato eseguito per questa review.

## 1. Verdetto esecutivo

Alembic e TradingAgents operano nello stesso dominio, ma non sono concorrenti diretti.

- **TradingAgents e' un research decision framework per singolo strumento.** Prende ticker e data, raccoglie evidenze eterogenee, orchestra analisti e dibattiti LLM e restituisce un dossier con rating finale.
- **Alembic e' un trading operating system.** Produce segnali asincroni, combina strategie a livello di portafoglio, applica controlli deterministici, invia ordini paper, misura risultati e governa la promozione delle strategie.
- **L'alpha piu' interessante di TradingAgents e' cognitivo, non ancora finanziario dimostrato:** specializzazione dei ruoli, contraddittorio bull/bear, sintesi strutturata, memoria narrativa degli esiti e ampia superficie di modelli/vendor.
- **L'alpha piu' forte di Alembic e' operativo e scientifico:** separazione LLM/esecuzione, event-time, audit trail, IC/ICIR, confronto shadow, realistic costs, walk-forward, risk constraints e lifecycle fail-closed in gran parte del sistema.
- **La combinazione ad alto valore e' asimmetrica:** TradingAgents come modulo asincrono di `research enrichment` e `second opinion`, alimentato da snapshot point-in-time prodotti da Alembic; Alembic resta proprietario di segnale, sizing, rischio, backtest, promozione ed esecuzione.

**Raccomandazione:** non importare il grafo TradingAgents nel percorso ordini e non tradurre direttamente `Buy/Overweight/Hold/Underweight/Sell` in ordini. Costruire un POC shadow-only su eventi primari e materialmente rilevanti, con ablation test che misuri il contributo incrementale del dibattito rispetto a una singola sintesi LLM.

## 2. Cosa significa "alpha" in questa analisi

Uso quattro categorie separate, per evitare di chiamare alpha qualunque feature interessante:

| Categoria | Definizione | Stato relativo |
|---|---|---|
| **Alpha informativo** | Accesso tempestivo a dati non pienamente prezzati | Debole in entrambi sull'editorial news; potenziale Alembic su documenti primari |
| **Alpha interpretativo** | Migliore estrazione di conseguenze economiche dalle stesse evidenze | TradingAgents offre pattern promettenti; non isolati sperimentalmente |
| **Alpha di portafoglio** | Migliore conversione dei segnali in rischio e capitale | Vantaggio netto Alembic |
| **Alpha operativo** | Meno errori, leakage, costi, duplicazioni e downtime | Vantaggio netto Alembic |

Il punto chiave e' che il dibattito multi-agent puo' aumentare la qualita' di una tesi senza aumentare il rendimento. Deve quindi essere trattato come **ipotesi misurabile**, non come meccanismo di alpha gia' acquisito.

## 3. Confronto in una pagina

| Dimensione | Alembic | TradingAgents v0.3.1 | Vantaggio |
|---|---|---|---|
| Unita' di decisione | Portafoglio multi-strategy | Singolo ticker/data | Dipende dal caso; Alembic per trading |
| Modalita' | Pipeline schedulata, paper operations | Analisi on-demand CLI/package | Alembic per operativita'; TA per ricerca |
| Ruolo LLM | Estrazione di signal features e regime, fuori hot path | Analisi, dibattito e decisione finale | TA per ricchezza cognitiva; Alembic per safety |
| Evidenze | News, prezzi, macro, earnings/filing, opzioni in R&D | Technical, fundamentals, news, social, macro, Polymarket | TA piu' ampio per dossier; Alembic piu' tracciato |
| Output | Score continuo, confidence, metadata, target weights, ordini | Report narrativi e rating a 5 livelli | Alembic per calcolo; TA per leggibilita' |
| Portafoglio reale | NAV, posizioni, sleeve, delta orders | Nessuno stato di posizioni/cassa nel grafo | Alembic |
| Risk management | Caps numerici, vol targeting, kill-switch, drawdown, stop policy | Tre agenti di opinione sul rischio | Alembic, nettamente |
| Esecuzione | Alpaca paper, log decisioni/trade; IBKR adapter parziale | Nessun broker/order adapter nel flusso corrente | Alembic |
| Backtest | Point-in-time replay, t+1, costs, walk-forward, 5 gate | Nessun runner riproducibile nel package corrente | Alembic |
| Feedback | IC/ICIR, LOO weights, drift, loss feedback, counterfactual | Return a 5 giorni + riflessione LLM nel log | Alembic quantitativo; TA narrativo |
| Reproducibilita' | Redis/PG audit, config, molte invarianti; doc drift residuo | Checkpoint SQLite, report tree; output e fonti live non deterministici | Alembic |
| LLM portability | Registry ristretto a client Ollama predisposti | Ampio provider factory e capability registry | TradingAgents |
| UX | FastAPI + dashboard React operativa | CLI Rich interattiva + report Markdown | Complementari |
| Community | Progetto essenzialmente single-maintainer | Community molto ampia e attiva | TradingAgents |

Fonti Alembic: [`docs/ARCHITECTURE.md`](ARCHITECTURE.md), [`docs/strategies.md`](strategies.md), [`src/portfolio/orchestrator.py`](../src/portfolio/orchestrator.py), [`src/api/main.py`](../src/api/main.py). Fonti TradingAgents: [`README v0.3.1`](https://github.com/TauricResearch/TradingAgents/tree/v0.3.1), [`graph/setup.py`](https://github.com/TauricResearch/TradingAgents/blob/v0.3.1/tradingagents/graph/setup.py), [`graph/trading_graph.py`](https://github.com/TauricResearch/TradingAgents/blob/v0.3.1/tradingagents/graph/trading_graph.py).

## 4. Logica end-to-end

### 4.1 Alembic

```text
fonti -> ingest/dedup/resolve -> LLM ensemble -> signal point-in-time
                                                |
strategie quantitative + signal S4 -> target weights per sleeve
                                                |
merge pesato -> vol overlay -> constraints -> post-filtri -> broker paper
                                                |
trade/audit -> forward returns -> IC/drift/counterfactual -> governance
```

La decisione viene progressivamente compressa in contratti numerici. Gli LLM non producono ordini: il sentiment worker restituisce `score = polarity * confidence`; le strategie producono pesi locali alla sleeve; l'orchestrator somma `weight * allocation_pct`, genera un solo set di delta order e applica i vincoli dopo il vol targeting. L'ordine e' intenzionale per lasciare ai risk caps l'ultima parola ([`sentiment.py:169-287`](../src/workers/sentiment.py), [`orchestrator.py:118-290`](../src/portfolio/orchestrator.py), [`constraints.py:41-125`](../src/portfolio/constraints.py)).

La pipeline attiva e' `execution.engine: portfolio`; S1 ha il 50% di sleeve in `supervised_paper`, S4 il 10% in `paper`, mentre S2, S3 e S7 sono ricerca/disabled. Il capitale residuo resta cash. La configurazione dichiara esplicitamente che live trading e promozioni non sono autorizzati ([`config/strategies.yaml:13-58`](../config/strategies.yaml), [`docs/strategies.md:5-29`](strategies.md)).

### 4.2 TradingAgents

```text
market analyst -> sentiment analyst -> news analyst -> fundamentals analyst
       | report         | report          | report          | report
       +----------------+------------------+-----------------+
                                |
                    bull <-> bear debate
                                |
                       research manager
                                |
                             trader
                                |
          aggressive -> conservative -> neutral risk debate
                                |
                       portfolio manager
                                |
             dossier Markdown + rating a 5 livelli
```

Il grafo LangGraph e' esplicito e comprensibile: gli analisti eseguono in sequenza, ciascuno con i propri tool; seguono dibattito bull/bear, giudizio del Research Manager, proposta del Trader, dibattito tra tre posture di rischio e decisione del Portfolio Manager ([`setup.py:61-154`](https://github.com/TauricResearch/TradingAgents/blob/v0.3.1/tradingagents/graph/setup.py)). Il changelog conferma che l'esecuzione parallela degli analisti e' solo pianificata ([release v0.3.0](https://github.com/TauricResearch/TradingAgents/releases/tag/v0.3.0)).

Research Manager, Trader, Portfolio Manager e Sentiment Analyst usano output Pydantic strutturati quando il provider lo consente. Il risultato viene poi renderizzato in Markdown per compatibilita' con CLI, memory log e report ([`schemas.py`](https://github.com/TauricResearch/TradingAgents/blob/v0.3.1/tradingagents/agents/schemas.py), [`signal_processing.py`](https://github.com/TauricResearch/TradingAgents/blob/v0.3.1/tradingagents/graph/signal_processing.py)).

### 4.3 La differenza decisiva

Il `Portfolio Manager` di TradingAgents non gestisce un portafoglio nel senso operativo. Lo stato del grafo contiene ticker, data, report, dibattiti e memoria, ma non NAV, cassa, posizioni, ordini pendenti, esposizioni, correlazioni o limiti ([`agent_states.py`](https://github.com/TauricResearch/TradingAgents/blob/v0.3.1/tradingagents/agents/utils/agent_states.py)). Il sizing del Trader e' una stringa opzionale come `"5% of portfolio"`, non un vincolo eseguibile ([`schemas.py:120-180`](https://github.com/TauricResearch/TradingAgents/blob/v0.3.1/tradingagents/agents/schemas.py)).

Di conseguenza:

- in TradingAgents, "risk management" significa **contro-argomentazione qualitativa**;
- in Alembic, "risk management" significa **trasformazione deterministica o blocco dell'ordine**;
- i due livelli possono convivere, ma il primo non deve sostituire il secondo.

## 5. Gli alpha reali di TradingAgents

### 5.1 Decomposizione cognitiva e contraddittorio

Il pattern piu' interessante e' la separazione tra raccolta delle evidenze, tesi bull/bear, decisione tattica e critica del rischio. Rispetto all'ensemble Alembic, in cui piu' modelli risolvono essenzialmente lo stesso task e il reasoning finale e' preso dal modello con confidence piu' alta, TradingAgents introduce **eterogeneita' di obiettivo**, non solo di modello ([`ensemble.py:271-312`](../src/llm/ensemble.py), [`bull_researcher.py`](https://github.com/TauricResearch/TradingAgents/blob/v0.3.1/tradingagents/agents/researchers/bull_researcher.py), [`bear_researcher.py`](https://github.com/TauricResearch/TradingAgents/blob/v0.3.1/tradingagents/agents/researchers/bear_researcher.py)).

Valore potenziale per Alembic:

- rendere esplicite le assunzioni causali di un evento;
- produrre invalidation conditions e downside case;
- distinguere impatto sull'issuer da effetto settoriale/macro;
- ridurre decisioni guidate da un singolo framing editoriale;
- creare un dossier leggibile per review umana e labeling.

Limite: non esiste nel paper un'ablation che isoli il valore di bull/bear debate o risk debate rispetto a una singola sintesi. Il beneficio resta un'ipotesi.

### 5.2 Evidence plane piu' largo

TradingAgents combina technicals, fondamentali, bilancio/cash flow, news societarie, macro FRED, prediction markets Polymarket, StockTwits e Reddit. Il market analyst dispone inoltre di uno snapshot deterministico che deve prevalere su valori in conflitto ([`market_analyst.py`](https://github.com/TauricResearch/TradingAgents/blob/v0.3.1/tradingagents/agents/analysts/market_analyst.py), [`news_analyst.py`](https://github.com/TauricResearch/TradingAgents/blob/v0.3.1/tradingagents/agents/analysts/news_analyst.py), [`market_data_validator.py`](https://github.com/TauricResearch/TradingAgents/blob/v0.3.1/tradingagents/dataflows/market_data_validator.py)).

Per Alembic l'opportunita' non e' aggiungere altre editorial news. E' usare questa decomposizione su **eventi primari semi-strutturati** gia' indicati dalla roadmap Alembic: earnings, guidance, 8-K, transcript, revisioni di consensus e disclosure. La roadmap interna mostra che la monocultura editorial-news e' stata empiricamente negativa e propone esattamente questo pivot ([`ROADMAP_DATA_ALPHA_2026-07-02.md:10-35`](ROADMAP_DATA_ALPHA_2026-07-02.md)).

### 5.3 Grafo esplicito, output tipizzati e checkpoint

`TradingAgentsGraph.propagate(ticker, date)` e' un'interfaccia piccola dietro cui vivono tool calls, state transitions, report e recovery. Checkpoint SQLite e firma della forma del grafo consentono il resume senza ricominciare una pipeline LLM costosa ([`trading_graph.py:348-402`](https://github.com/TauricResearch/TradingAgents/blob/v0.3.1/tradingagents/graph/trading_graph.py), [release v0.3.1](https://github.com/TauricResearch/TradingAgents/releases/tag/v0.3.1)).

Questo pattern e' adatto a un nuovo modulo Alembic di ricerca, ma non giustifica una riscrittura dei worker Celery o del portfolio scheduler. Il seam corretto e' un singolo `ResearchAssessmentProvider`, con LangGraph come adapter possibile dietro l'interfaccia.

Va pero' separata la qualita' del contratto programmatico da quella del percorso CLI corrente: la CLI non chiama `propagate()`, ma costruisce lo stato e invoca direttamente `graph.stream()`. Di conseguenza salta parte del lifecycle descritto sopra; il dettaglio e' discusso nella sezione 6.4.

### 5.4 Memoria outcome-grounded

TradingAgents salva ogni decisione, calcola al run successivo il rendimento a cinque giorni e l'alpha rispetto a un benchmark regionale, genera una riflessione breve e la reinietta nel Portfolio Manager ([`trading_graph.py:251-334`](https://github.com/TauricResearch/TradingAgents/blob/v0.3.1/tradingagents/graph/trading_graph.py), [`memory.py:28-95`](https://github.com/TauricResearch/TradingAgents/blob/v0.3.1/tradingagents/agents/utils/memory.py), [`reflection.py`](https://github.com/TauricResearch/TradingAgents/blob/v0.3.1/tradingagents/graph/reflection.py)).

L'idea e' utile, ma l'implementazione non va copiata tale e quale:

- usa un orizzonte fisso di 5 giorni, non l'orizzonte dichiarato nella tesi;
- registra il raw return del titolo, non un return firmato per `Buy/Sell/Underweight`;
- non include costi, fill, sizing o P&L effettivo;
- le lezioni cross-ticker sono testo libero e possono generalizzare causalita' spurie.

Alembic dispone gia' dei dati migliori per implementare la stessa idea correttamente: trade reali, decision reason, counterfactual, forward returns multi-horizon, cost breakdown e postmortem. Lo spunto trasferibile e' la **memoria narrativa**, mentre la verita' dell'outcome deve restare nei dati Alembic.

### 5.5 Portabilita' modelli e vendor

TradingAgents ha un factory multi-provider, un catalogo centrale e una tabella dichiarativa delle capability per gestire `tool_choice`, JSON mode, reasoning roundtrip e altri quirks dei modelli. Il data layer permette catene vendor esplicite senza fallback silenzioso ([`llm_clients/factory.py`](https://github.com/TauricResearch/TradingAgents/blob/v0.3.1/tradingagents/llm_clients/factory.py), [`llm_clients/capabilities.py`](https://github.com/TauricResearch/TradingAgents/blob/v0.3.1/tradingagents/llm_clients/capabilities.py), [`dataflows/interface.py`](https://github.com/TauricResearch/TradingAgents/blob/v0.3.1/tradingagents/dataflows/interface.py)).

Alembic ha registry e shadow comparison efficaci, ma la costruzione dei client e' ancora legata a classi Ollama specifiche ([`model_registry.py:14-190`](../src/llm/model_registry.py)). Il pattern capability-driven di TradingAgents e' un miglioramento architetturale concreto, soprattutto se l'ensemble a tre modelli o provider alternativi verra' riaperto.

## 6. Cosa non importare

### 6.1 Rating LLM come segnale eseguibile

Il rating finale non ha una confidence numerica calibrata, una definizione univoca dell'orizzonte o una mappatura point-in-time a target weight. Usarlo direttamente introdurrebbe un secondo motore decisionale non calibrato accanto alle strategie Alembic.

**Regola:** il dossier puo' creare feature o veto shadow; non puo' creare ordini.

### 6.2 Risk agents come risk controls

I tre risk debater hanno prompt diversi ma nessun accesso ai vincoli reali del conto. Possono produrre `risk_flags`, scenari e invalidation conditions. Non possono sostituire max exposure, sector cap, correlation cap, drawdown, kill-switch, vol targeting o broker checks.

### 6.3 Fetch live durante replay storico

Nel Sentiment Analyst, `trade_date` delimita Yahoo News, ma StockTwits e Reddit vengono prelevati live senza uno snapshot storico associato ([`sentiment_analyst.py:60-80`](https://github.com/TauricResearch/TradingAgents/blob/v0.3.1/tradingagents/agents/analysts/sentiment_analyst.py), [`stocktwits.py`](https://github.com/TauricResearch/TradingAgents/blob/v0.3.1/tradingagents/dataflows/stocktwits.py), [`reddit.py`](https://github.com/TauricResearch/TradingAgents/blob/v0.3.1/tradingagents/dataflows/reddit.py)). Anche Polymarket e' esplicitamente live e filtra i mercati usando l'ora corrente, non `trade_date` ([`polymarket.py:68-100`](https://github.com/TauricResearch/TradingAgents/blob/v0.3.1/tradingagents/dataflows/polymarket.py)).

Il problema riguarda anche una parte dei fondamentali: `get_fundamentals()` dichiara che `curr_date` non viene usata e restituisce lo snapshot corrente di `yfinance.Ticker.info`, inclusi market cap, forward PE/EPS e medie mobili ([`y_finance.py:274-333`](https://github.com/TauricResearch/TradingAgents/blob/v0.3.1/tradingagents/dataflows/y_finance.py)). Le financial statements hanno filtri temporali distinti, ma questo overview non e' point-in-time. Lo stesso README avverte che una data storica fissa i prezzi mentre fonti live possono cambiare ([README, Reproducibility](https://github.com/TauricResearch/TradingAgents/tree/v0.3.1#reproducibility)).

**Conseguenza:** per qualunque backtest Alembic il grafo deve ricevere un evidence bundle immutabile dal database, e i tool di rete di TradingAgents devono essere disabilitati.

### 6.4 La CLI bypassa memoria e checkpoint del contratto programmatico

Il comando `analyze` espone opzioni di checkpoint, ma `run_analysis()` documenta nel codice che costruisce lo stato direttamente invece di passare da `propagate()` e poi chiama `graph.graph.stream()` ([`cli/main.py:1100-1119`](https://github.com/TauricResearch/TradingAgents/blob/v0.3.1/cli/main.py)). Quel percorso non esegue:

- risoluzione delle entry pending e generazione delle reflection;
- injection di `past_context` nello stato iniziale;
- ricompilazione con `SqliteSaver`, firma del grafo e `thread_id`;
- `_log_state()`, `memory_log.store_decision()` e clear del checkpoint a successo.

Queste operazioni esistono nel percorso `propagate()` ([`trading_graph.py:362-482`](https://github.com/TauricResearch/TradingAgents/blob/v0.3.1/tradingagents/graph/trading_graph.py)), ma la principale UX interattiva non le attraversa. E' una discrepanza funzionale concreta, non solo debito di documentazione: checkpoint e memoria outcome-grounded non vanno considerati affidabili end-to-end finche' i due entry point non condividono lo stesso lifecycle.

### 6.5 Full graph su ogni news item

Il paper dichiara 11 LLM call e oltre 20 tool call per previsione. Applicare il grafo a ogni articolo Alembic aumenterebbe costo, latenza e varianza senza garanzia di copertura. Va attivato solo dopo dedup, resolver, freshness, materiality e novelty gate.

### 6.6 Markdown memory come source of truth

Il log atomico Markdown e' adeguato a un tool locale single-user, non a worker concorrenti e audit finanziario. Alembic deve persistere input hash, output strutturati, prompt/model version, costi, timestamps e outcome in PostgreSQL; il Markdown e' solo una view.

### 6.7 Framework completo come dipendenza core

TradingAgents porta LangChain/LangGraph e numerosi SDK LLM. Inserirlo nel processo Alembic principale aumenterebbe superficie di dipendenze e blast radius. E' preferibile un processo separato o un optional extra, con contratto JSON versionato.

## 7. Quanto e' credibile l'alpha finanziario dichiarato

Il paper TradingAgents riporta risultati molto forti: nel test principale AAPL, GOOGL e AMZN mostrano cumulative return tra 23,21% e 26,62%, Sharpe tra 5,60 e 8,21 e maximum drawdown tra 0,91% e 2,11% ([paper, tabella 1](https://arxiv.org/pdf/2412.20138), pp. 9-11).

Questi numeri non sono sufficienti per una decisione di integrazione trading:

1. Il periodo e' solo **1 gennaio - 29 marzo 2024**.
2. La tabella principale contiene **tre titoli**, tutti large-cap growth/tech correlati.
3. Gli autori stessi segnalano che Sharpe sopra 5 e' eccezionale e attribuiscono il risultato a pochi pullback nel periodo.
4. Il paper dichiara **11 chiamate LLM e oltre 20 tool call per previsione** e limita il backtest a tre mesi per costo.
5. Non e' presentata un'ablation del contributo marginale dei dibattiti.
6. Nella descrizione dell'esperimento non emerge un modello esplicito di spread, impact, commissioni e slippage comparabile a quello Alembic.
7. Il codice `v0.3.1` si e' evoluto materialmente rispetto al framework del paper; le release recenti hanno corretto leakage/look-ahead e grounding, quindi i risultati pubblicati non validano automaticamente il codice corrente ([release v0.3.1](https://github.com/TauricResearch/TradingAgents/releases/tag/v0.3.1)).
8. Il package corrente restituisce report e rating da `propagate()`; non contiene un portfolio backtest runner o broker path equivalente a quello descritto nella figura del paper. `backtrader` e `redis` sono dichiarati tra le dipendenze, ma non sono referenziati dall'application code del clone analizzato.

**Giudizio:** evidenza interessante che giustifica un POC, ma bassa affidabilita' come prova di market alpha. Il valore oggi dimostrato dal progetto e' soprattutto come research scaffold, non come strategia replicabile.

## 8. Gli alpha di Alembic e i gap che TradingAgents puo' colmare

### 8.1 Alpha gia' presenti in Alembic

- **Separazione ricerca/esecuzione:** nessuna chiamata LLM nel percorso ordini.
- **Point-in-time e provenance:** `published_at`, dedup, resolver, raw ingestion time, source funnel, forward returns e audit PG.
- **Signal science:** score continuo, IC composito, ICIR Newey-West, LOO model weights, shadow model comparison e drift.
- **Portfolio semantics:** sleeve-local weights, single merge, delta order, cash residuale, vol overlay e deterministic constraints.
- **Execution safety:** paper default, kill-switch, idempotenza S4, pyramiding guard, hold minimum, exit hysteresis e logging di decisioni/trade.
- **Validation:** replay anti-look-ahead, t+1 fill, realistic costs, walk-forward, robustness/regime/stress gates e lifecycle di promozione.

Fonti: [`docs/CONTEXT_MAP_2026-07-10.md:81-176`](CONTEXT_MAP_2026-07-10.md), [`src/backtest/engine/data_replay.py`](../src/backtest/engine/data_replay.py), [`src/backtest/costs/realistic.py`](../src/backtest/costs/realistic.py), [`src/strategies/promotion.py`](../src/strategies/promotion.py).

### 8.2 Gap reali di Alembic

- **Interpretazione ancora stretta:** il prompt S4 lavora su circa 600 caratteri e produce feature per singolo articolo; non integra sistematicamente fondamentali, technicals, macro e controtesi.
- **Editorial-news monoculture:** la review interna ha misurato performance negativa e latenza elevata; il pivot su eventi primari non e' ancora completato.
- **Reasoning impoverito nell'aggregation:** il consensus conserva il reasoning del modello con confidence maggiore, non una sintesi delle evidenze in conflitto.
- **Provider abstraction meno profonda:** registry utile, ma client construction hardcoded e capability non dichiarative.
- **Research UX:** la dashboard e' forte sul controllo operativo, meno sul dossier causale per evento con bull case, bear case, catalyst e invalidation.
- **Debito operativo residuo:** labeling QX-01 incompleto, doc/code drift, lifecycle fail-open su row assente, alcuni constraint pass non pienamente wired e hardening pre-live ancora aperto ([`OPEN_WORK_AUDIT_2026-07-15.md`](OPEN_WORK_AUDIT_2026-07-15.md), [`CONTEXT_MAP_2026-07-10.md:178-206`](CONTEXT_MAP_2026-07-10.md)).

TradingAgents puo' colmare i primi quattro gap. Non risolve gli ultimi e non aumenta da solo la qualita' dei dati sottostanti.

## 9. Architettura di integrazione proposta

```text
                        ALEMBIC, SOURCE OF TRUTH

ingest -> dedup -> resolver -> event/materiality gate -> EvidenceBundle v1
                                                        |
                                                        v
                                  +----------------------------------------+
                                  | ResearchAssessmentProvider             |
                                  | adapter: TradingAgentsResearchGraph    |
                                  | - no network tools in replay           |
                                  | - selected analyst roles               |
                                  | - bull/bear debate optional            |
                                  | - typed output                         |
                                  +----------------------------------------+
                                                        |
                                                        v
                                             ResearchAssessment v1
                                                        |
                         +------------------------------+------------------+
                         |                                                 |
                         v                                                 v
              PostgreSQL + dossier UI                           shadow feature join
                                                                    |
                                                                    v
                                                         Alembic backtest/gates
                                                                    |
                                                          no direct execution edge
```

### 9.1 Interfaccia esterna minima

```python
class ResearchAssessmentProvider(Protocol):
    def assess(self, request: ResearchRequest) -> ResearchAssessment: ...
```

`ResearchRequest` dovrebbe contenere:

| Campo | Motivazione |
|---|---|
| `assessment_id`, `signal_id`, `event_id` | Tracciabilita' end-to-end |
| `symbol`, `as_of`, `horizons` | Identita' e point-in-time |
| `instrument_identity` | Evita ticker/company hallucination |
| `event_document`, `source`, `published_at` | Evidenza primaria |
| `market_snapshot` | Prezzi/volumi/indicatori congelati |
| `fundamental_snapshot` | Dati disponibili alla data |
| `macro_snapshot` | Regime e dati macro osservabili |
| `existing_signal` | Baseline Alembic da non nascondere |
| `input_hash`, `schema_version` | Reproducibilita' |

`ResearchAssessment` dovrebbe contenere soltanto campi di ricerca:

| Campo | Tipo |
|---|---|
| `thesis`, `bull_case`, `bear_case` | testo strutturato |
| `catalysts`, `invalidation_conditions`, `risk_flags` | liste tipizzate |
| `impact_direction`, `materiality`, `novelty`, `confidence` | feature numeriche |
| `evidence_refs` | riferimenti a fatti dell'input |
| `disagreements` | conflitti non risolti |
| `model_ids`, `prompt_versions`, `tool_trace` | provenance |
| `latency_ms`, `input_tokens`, `output_tokens`, `cost_usd` | economics |
| `status`, `error_code` | degradazione controllata |

Non dovrebbe contenere `order_qty`, `target_weight` o `submit_order`.

### 9.2 Grafo minimo per il POC

Non partire dal grafo completo. Usare tre varianti:

| Variante | Nodi | Scopo |
|---|---|---|
| **A. Baseline** | Alembic S4/S7 corrente | Controllo |
| **B. Synthesis-only** | event/fundamental analyst -> research manager | Misura valore del contesto largo |
| **C. Debate** | event/fundamental analyst -> bull -> bear -> research manager | Misura valore marginale del contraddittorio |
| **D. Full qualitative risk** | C + tre risk debater | Solo se C passa; misura se il costo extra aggiunge valore |

Se B batte A ma C non batte B, il valore viene dall'evidence bundle e non dal multi-agent debate. In quel caso il dibattito va eliminato.

## 10. Piano sperimentale e gate

### Fase 0: contratto e dataset congelato

1. Selezionare un solo vettore: earnings/guidance/8-K o transcript tone. Evitare editorial news generica.
2. Costruire `EvidenceBundle v1` da dati gia' persistiti e disponibili `as_of`.
3. Pre-registrare orizzonti, universe, metriche e soglie prima di leggere gli outcome.
4. Correggere il labeling QX-01 o creare un set specifico evento/issuer con almeno alcune centinaia di esempi utili.

### Fase 1: shadow generation

1. Eseguire A/B/C sullo stesso identico input hash.
2. Salvare ogni output e fallimento, inclusi costo e latenza.
3. Nessuna modifica a score, threshold, sizing o ordini.
4. Versionare prompt, graph shape, modello e provider.

### Fase 2: evaluation

Metriche minime:

| Area | Metriche |
|---|---|
| Signal quality | Spearman IC e Pearson IC a 1h/1d/5d/20d |
| Direction | hit rate, balanced accuracy, coverage |
| Calibration | Brier score, reliability curve per confidence bucket |
| Incremental value | residual IC dopo score Alembic, regime, beta e size controls |
| Portfolio | net Sharpe, max drawdown, turnover, capacity, realistic costs |
| Robustness | walk-forward, block bootstrap, regime split, source split |
| Concentration | quota P&L top 5 eventi/ticker |
| Economics | costo per assessment, costo per decisione utile, timeout rate |

Gate consigliati:

- nessun leakage o fetch live nel replay;
- delta IC OOS positivo con lower bound del block-bootstrap sopra zero;
- miglioramento netto dopo costi rispetto alla baseline, non solo raw return;
- beneficio stabile in piu' finestre/regimi e non spiegato da pochi outlier;
- C deve superare B abbastanza da giustificare costo e latenza del dibattito;
- D deve superare C, altrimenti i tre risk agents vengono esclusi;
- nessuna attivazione paper prima del passaggio nei gate Alembic esistenti.

### Fase 3: feature, non strategia autonoma

Solo dopo i gate, l'assessment puo' diventare:

- feature di ranking per un event-driven sleeve;
- veto su eventi con bear case forte e evidence-grounded;
- confidence haircut;
- priorita' per review umana;
- input a un dossier nella dashboard.

Il percorso `research -> paper -> supervised_paper -> live` resta quello di Alembic.

## 11. Opportunita' di collaborazione con Tauric Research

### 11.1 Joint benchmark: valore piu' alto per entrambe le parti

Proporre un benchmark riproducibile in cui:

- Alembic fornisce evidence snapshot point-in-time, outcome multi-horizon, realistic cost model e portfolio gates;
- TradingAgents fornisce role graph, provider portability e varianti di dibattito;
- il test pubblica ablation `single synthesis vs bull/bear vs full risk debate`;
- ogni run e' identificato da input hash, model/prompt version e graph signature.

Questo colma il principale gap scientifico del paper TradingAgents e il principale gap cognitivo di Alembic.

### 11.2 Contributi upstream circoscritti

| Contributo | Beneficio TradingAgents | Beneficio Alembic |
|---|---|---|
| `FrozenEvidenceProvider` / replay adapter | Backtest senza fonti live | Integrazione pulita senza fork |
| Outcome memory action-adjusted e horizon-aware | Lezioni corrette per Sell/Hold e orizzonte | Riutilizzo del pattern reflection |
| Structured evaluation event schema | Benchmark e cost accounting | Import diretto in PG |
| Analyst parallelism con state isolation | Minore latenza | POC piu' economico |
| Portfolio-context interface separata dall'execution | Ruolo PM semanticamente corretto | Possibile second opinion senza ordini |

Prima di un PR ampio conviene aprire una design issue con un contratto piccolo e testabile. La community upstream e' attiva: la release `v0.3.1` incorpora contributi su look-ahead, routing, checkpoint e crypto da numerosi autori ([release v0.3.1](https://github.com/TauricResearch/TradingAgents/releases/tag/v0.3.1)).

### 11.3 Reference integration separata

Costruire un piccolo adapter open source `alembic-tradingagents-research` che:

1. legge un `EvidenceBundle` JSON;
2. esegue un sotto-grafo TradingAgents pinning `v0.3.1` o successiva;
3. emette `ResearchAssessment` JSON;
4. non conosce Redis, PostgreSQL, Alpaca o ordini;
5. include test fixture completamente offline.

Questo e' piu' collaborativo e manutenibile di un fork interno.

### 11.4 Riutilizzo mirato di connector/pattern

- **Polymarket:** interessante come probabilita' evento/macro, non come alpha primario. Va mappato a eventi con timestamp e mercato specifico.
- **Provider capability registry:** pattern direttamente trasferibile al model registry Alembic.
- **Verified market snapshot:** utile come contratto comune per tutti gli agenti.
- **Report tree:** utile come export del dossier, mentre PostgreSQL resta source of truth.

## 12. Vincoli legali e di progetto

TradingAgents `v0.3.1` e' Apache-2.0. Alembic si dichiara MIT nel README, ma nel clone analizzato **manca il file `LICENSE` a cui il README rimanda** ([`README.md:746-748`](../README.md)). Prima di distribuire codice derivato o proporre un'integrazione pubblica occorre:

1. aggiungere la licenza effettiva di Alembic;
2. decidere se dipendere dal package, mantenere un adapter separato o copiare file;
3. se si copia/modifica codice Apache, preservare copyright/attribution, includere la licenza Apache e marcare i file modificati;
4. verificare eventuali `NOTICE` e le licenze delle dipendenze/dati.

La strada piu' semplice e' una dipendenza/adattatore separabile, non il code copy.

## 13. Roadmap raccomandata

| Priorita' | Azione | Orizzonte | Decisione prodotta |
|---|---|---|---|
| **P0** | Chiudere QX-01, fissare LICENSE, scegliere un solo event vector | 1-2 settimane | Dataset e contratto validi |
| **P1** | Implementare `EvidenceBundle` + `ResearchAssessment` e adapter offline | 2 settimane | POC riproducibile |
| **P1** | Eseguire A/B/C shadow con modelli gia' disponibili | 2-4 settimane | Valore marginale del debate |
| **P2** | Portfolio replay con realistic costs e walk-forward | 2 settimane | Go/no-go quantitativo |
| **P2** | Aprire design issue upstream con frozen evidence + evaluation schema | In parallelo | Collaborazione concreta |
| **P3** | Integrare solo feature che passano i gate | Dopo evidenza | Paper sleeve controllata |

### Decisione immediata consigliata

Avviare un POC su **earnings/guidance o transcript tone**, non sulla news generica. Implementare soltanto variante B e C. Non includere inizialmente i tre risk debater: il loro contributo e' piu' costoso e meno distinto dai controlli deterministici gia' presenti in Alembic.

## 14. Conclusione

TradingAgents non offre ad Alembic un motore di trading migliore. Offre un modo piu' ricco di **organizzare il ragionamento** e di presentare una tesi. Alembic non offre a TradingAgents un grafo di agenti migliore. Offre l'infrastruttura necessaria per stabilire se quel ragionamento produce davvero alpha, al netto di leakage, costi, rischio e selezione del campione.

La collaborazione piu' interessante e' quindi un sistema a due livelli:

1. **TradingAgents produce una tesi strutturata e falsificabile su evidenze congelate.**
2. **Alembic decide quantitativamente se quella tesi merita capitale.**

Questa separazione mantiene il valore di entrambi i progetti e rende verificabile il presunto alpha multi-agent.

## 15. Fonti primarie

### TradingAgents

- [Repository e README `v0.3.1`](https://github.com/TauricResearch/TradingAgents/tree/v0.3.1)
- [Release `v0.3.1`, 5 luglio 2026](https://github.com/TauricResearch/TradingAgents/releases/tag/v0.3.1)
- [Changelog `v0.3.1`](https://github.com/TauricResearch/TradingAgents/blob/v0.3.1/CHANGELOG.md)
- [Paper: TradingAgents: Multi-Agents LLM Financial Trading Framework, arXiv:2412.20138v7](https://arxiv.org/pdf/2412.20138)
- Clone locale analizzato: `/home/stefano/Documents/Projects/TradingAgents`, commit `01477f9afb7a47b849ed4c9259d3a9a4738d9fda`

### Alembic

- [`README.md`](../README.md)
- [`docs/ARCHITECTURE.md`](ARCHITECTURE.md)
- [`docs/strategies.md`](strategies.md)
- [`docs/ROADMAP_DATA_ALPHA_2026-07-02.md`](ROADMAP_DATA_ALPHA_2026-07-02.md)
- [`docs/CONTEXT_MAP_2026-07-10.md`](CONTEXT_MAP_2026-07-10.md)
- [`docs/OPEN_WORK_AUDIT_2026-07-15.md`](OPEN_WORK_AUDIT_2026-07-15.md)
- [`src/workers/sentiment.py`](../src/workers/sentiment.py)
- [`src/portfolio/orchestrator.py`](../src/portfolio/orchestrator.py)
- [`src/portfolio/constraints.py`](../src/portfolio/constraints.py)
- [`src/strategies/promotion.py`](../src/strategies/promotion.py)
- [`src/backtest/`](../src/backtest)
