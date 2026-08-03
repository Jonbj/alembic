# Analisi comparativa Alembic ↔ FinGPT

**Data:** 2026-07-15  
**Scope:** repository ufficiale `AI4Finance-Foundation/FinGPT`, clone locale al commit
`3799a0f7a3cb4e8a65686e0f11846632eb57ddf9`, codice e roadmap correnti di Alembic.  
**Obiettivo:** identificare integrazioni, PoC e collaborazioni che possano migliorare
alpha, redditività netta, accuratezza e robustezza di Alembic.

## 1. Verdetto esecutivo

FinGPT è utile ad Alembic come **laboratorio di modelli/dataset finanziari e insieme
di pattern sperimentali**, non come trading engine da incorporare.

Le opportunità migliori sono, in ordine:

1. **RAG point-in-time su eventi primari** (earnings, guidance, 8-K, transcript),
   usando l'idea FinGPT-RAG ma dati, provenance e replay di Alembic.
2. **FinGPT-Sentiment come candidato shadow specialistico**, confrontato con i
   modelli Alembic e con FinBERT sullo stesso label set e sugli stessi forward return.
3. **Forecaster settimanale come feature shadow per PEAD/earnings**, ricostruito su
   snapshot Alembic e sottoposto a una valutazione finanziaria che FinGPT non offre.
4. **LoRA/distillation su dati proprietari Alembic**, solo dopo avere accumulato un
   dataset abbastanza grande, stabile e temporalmente corretto.
5. **NER/relation extraction come candidate generator** per resolver ed event graph,
   mai come autorità finale sul ticker.

Non c'è invece evidenza sufficiente per:

- sostituire l'ensemble o il risk engine di Alembic;
- collegare FinGPT-Forecaster agli ordini;
- attribuire ai benchmark FinGPT un incremento atteso di P&L;
- installare l'intero repository FinGPT come dipendenza core.

Il punto decisivo è questo: FinGPT dimostra soprattutto **accuratezza NLP**. Alembic
deve dimostrare **incremental information coefficient e P&L netto out-of-sample**.
Le due cose non sono equivalenti.

## 2. Metodo e snapshot verificato

Sono state usate fonti primarie: codice locale, repository ufficiale, model/dataset
card ufficiali e paper degli autori.

Snapshot locale FinGPT:

- commit: `3799a0f`, 2026-07-10;
- 689 commit, 401 file tracciati, 125 file Python;
- un solo file sotto `tests/` e nessun workflow CI tracciato;
- i 6 test dell'integrazione Adanos passano localmente (`6 passed in 0.36s`);
- codice root sotto MIT, ma i singoli modelli e dataset hanno condizioni proprie.

Il repository GitHub è attivo e popolare (circa 20,9k star e 3k fork al momento
della verifica), ma popolarità e attività non compensano la limitata copertura di
test e la natura notebook/demo di molte componenti. La pagina ufficiale descrive
FinGPT come framework a cinque layer — data source, data engineering, LLM, task e
application — e pubblica modelli/dataset su Hugging Face
([repository ufficiale](https://github.com/AI4Finance-Foundation/FinGPT)).

## 3. Che cosa offre davvero FinGPT

### 3.1 FinGPT-Sentiment e FinGPT-Benchmark

FinGPT pubblica adapter LoRA per sentiment e modelli multi-task per sentiment,
headline classification, NER e relation extraction. Il README riporta per v3.3
weighted F1 pari a 0,882 su FPB, 0,874 su FiQA-SA, 0,903 su TFNS e 0,643 su NWGI.
Sono risultati interessanti, ma datati e misurati su dataset NLP, non su rendimenti
di mercato ([README FinGPT](https://github.com/AI4Finance-Foundation/FinGPT#current-state-of-the-arts-for-financial-sentiment-analysis)).

Il paper benchmark valuta task-specific, multi-task e zero-shot instruction tuning;
non presenta un sistema di execution o una prova di redditività
([paper benchmark](https://arxiv.org/abs/2310.04793)). Il README del benchmark
ammette inoltre che la scarsa diversità dei task/dataset può produrre risposte errate
fuori distribuzione
([benchmark locale](../../FinGPT/fingpt/FinGPT_Benchmark/readme.md)).

**Valore per Alembic:** candidato di confronto e sorgente di dataset/task template.  
**Valore non dimostrato:** alpha tradabile.

### 3.2 FinGPT-RAG

FinGPT-RAG combina instruction tuning e retrieval di contesto esterno. Gli autori
riportano guadagni del 15-48% in accuracy/F1; sul Twitter Val dichiarano accuracy
0,88 e F1 0,842 con RAG contro 0,86/0,811 senza contesto
([paper](https://arxiv.org/abs/2310.04027),
[README RAG locale](../../FinGPT/fingpt/FinGPT_RAG/README.md)).

È il risultato più trasferibile ad Alembic: una news breve può essere ambigua senza
contesto issuer, storico dell'evento, fundamentals e documento primario. Tuttavia il
codice FinGPT usa scraper e retrieval pensati per il benchmark, non il modello
point-in-time e auditabile richiesto da un backtest finanziario.

**Da importare:** l'ipotesi “contesto recuperato migliora la classificazione”.  
**Da non importare:** scraper live, CSV intermedi e retrieval non congelato.

### 3.3 FinGPT-Forecaster

Il Forecaster usa news delle settimane precedenti, movimenti di prezzo e fundamentals
per generare positive developments, concerns e una previsione della settimana
successiva. L'adapter pubblico è basato su Llama-2-7B e non è servito da un inference
provider ([model card](https://huggingface.co/FinGPT/fingpt-forecaster_dow30_llama2-7b_lora)).

Il codice locale rivela quattro limiti importanti:

1. Il dataset è costruito da rendimenti settimanali discretizzati
   ([`data.py`](../../FinGPT/fingpt/FinGPT_Forecaster/data.py)).
2. La pipeline mostra a GPT-4 il label futuro per fargli produrre il rationale teacher,
   poi rimuove il label dal prompt destinato al modello
   ([`prompt.py`](../../FinGPT/fingpt/FinGPT_Forecaster/prompt.py),
   [`data.py`](../../FinGPT/fingpt/FinGPT_Forecaster/data.py)). È una forma di
   distillation supervisionata legittima, ma il rationale è condizionato dall'outcome
   e non prova capacità causale.
3. La selezione delle news è casuale; lo stesso README avverte che ciò può introdurre
   forte bias
   ([Forecaster README](../../FinGPT/fingpt/FinGPT_Forecaster/README.md)).
4. Le metriche implementate sono binary accuracy, MSE e ROUGE; non ci sono Sharpe,
   drawdown, turnover, costi o capacity
   ([`utils.py`](../../FinGPT/fingpt/FinGPT_Forecaster/utils.py)).

Il dataset pubblico ha solo 4,5 MB, dataset card incompleta e viewer non funzionante
al momento della verifica
([dataset card](https://huggingface.co/datasets/FinGPT/fingpt-forecaster-dow30-202305-202405)).

**Valore per Alembic:** ipotesi sperimentale per un feature horizon 5d/settimanale.  
**Verdetto:** non utilizzabile live senza ricostruzione e validazione completa.

### 3.4 Data pipeline, LoRA e modelli multi-task

Il paper fondativo propone un approccio data-centric, aggiornamento automatico dei
dati e adattamento leggero LoRA
([paper FinGPT](https://arxiv.org/abs/2306.06031)). Questo è coerente con il bisogno
di Alembic di adattarsi al linguaggio finanziario senza addestrare un foundation
model.

Il riuso diretto è però fragile:

- `setup.py` dichiara versione `0.0.1` e le requirements root contengono quasi solo
  NumPy, pandas e Tushare;
- le componenti pinano spesso `transformers==4.32.0` e `peft==0.5.0`, mentre Alembic
  richiede `transformers>=4.40` ([pyproject Alembic](../pyproject.toml));
- il setup guide mostra import (`fingpt.Forecaster`) che non corrispondono a un
  modulo presente nel package locale;
- molte pipeline sono notebook con dipendenze e secret/API specifici.

**Conclusione:** isolare qualunque modello FinGPT in un servizio/container opzionale;
non mescolare il suo ambiente Python con il worker core Alembic.

### 3.5 Financial Report Analysis, MultiAgentsRAG e Adanos

La sezione FinancialReportAnalysis contiene idee utili — 10-K RAG, transcript,
clustering/summarizzazione — ma è una demo notebook, con dipendenze datate e codice
non production-grade
([README locale](../../FinGPT/fingpt/FinGPT_FinancialReportAnalysis/README.md)).

MultiAgentsRAG mira a ridurre hallucination tramite dibattito e retrieval, ma non
offre una prova che il costo/varianza multi-agent migliori P&L. Per Alembic il valore
è al massimo un'ablation futura dopo avere provato un singolo RAG ben fondato.

L'integrazione Adanos del 2026 aggrega Reddit, X, news e Polymarket, ma:

- copre al massimo 90 giorni e dichiara di non essere adatta a backfill lunghi;
- media i punteggi delle fonti senza calibrazione per fonte o volume;
- duplica aree già coperte dal funnel news/quality di Alembic.

I sei test passano, ma non esiste evidenza di alpha. Non è una priorità d'integrazione
([`market_sentiment.py`](../../FinGPT/fingpt/FinGPT_Forecaster/market_sentiment.py),
[`test_forecaster_market_sentiment.py`](../../FinGPT/tests/test_forecaster_market_sentiment.py)).

## 4. Confronto con Alembic

| Area | Alembic oggi | FinGPT | Giudizio |
|---|---|---|---|
| Ingestion | fonti persistite, dedup, provenance, source funnel | numerose demo/scraper | tenere Alembic |
| Sentiment | JSON tipizzato, ensemble, confidence, fallback, raw output audit | specialisti LoRA tri-class | FinGPT solo shadow |
| Context | prompt per articolo, body tipicamente 600 char | RAG e prompt multi-settimana | opportunità alta |
| Entity resolution | resolver shadow + golden labels | NER generica person/org/location | solo candidate generator |
| Misurazione | forward return, IC/ICIR, hit rate, Brier, LOO weights, drift | F1/accuracy/ROUGE | tenere Alembic |
| Backtest | walk-forward, realistic costs, DSR/gates | non presente end-to-end | tenere Alembic |
| Risk/execution | portfolio constraints, kill-switch, broker path | robo-advisor demo | nessuna sostituzione |
| Fine-tuning | non core oggi | LoRA/dataset tooling | utile più avanti |

Alembic ha già il seam corretto. Il worker sentiment crea un prompt issuer-specific,
richiede JSON strutturato e persiste output per modello; in caso di timeout/divergenza
usa FinBERT
([`sentiment.py`](../src/workers/sentiment.py),
[`ensemble.py`](../src/llm/ensemble.py)). Il model registry consente candidati shadow
e la model comparison calcola IC, hit rate, parse failure e divergenza
([`model_registry.py`](../src/llm/model_registry.py),
[`model_comparison.py`](../src/performance/model_comparison.py)).

Quindi FinGPT non richiede un nuovo trading stack: richiede adapter sperimentali che
entrino nello stesso sistema di misurazione.

## 5. Opportunità prioritarie

Scala: **alpha** = potenziale contributo incrementale al rendimento; **accuracy** =
qualità del segnale/resolver; **effort/risk** = costo e rischio di integrazione.

| # | Opportunità | Alpha | Accuracy | Effort | Rischio | Priorità |
|---|---|---:|---:|---:|---:|---:|
| 1 | RAG point-in-time su 8-K/earnings/guidance/transcript | alto | alto | medio | medio | **P1** |
| 2 | FinGPT-Sentiment come modello shadow | medio/ignoto | medio-alto | basso-medio | medio | **P1** |
| 3 | Forecaster feature 5d per PEAD/earnings | medio/ignoto | medio | alto | alto leakage | **P2** |
| 4 | LoRA su label/outcome Alembic | alto potenziale | alto | alto | alto overfit | **P2, dopo dati** |
| 5 | NER/relation extraction per resolver/event graph | indiretto | medio | medio | medio | **P2** |
| 6 | Report analyst/dossier per UI research | indiretto | medio | medio | basso | **P3** |
| 7 | Adanos/social overlay | basso/ignoto | basso-medio | medio | alto bias | **No-go ora** |
| 8 | Full FinGPT/MultiAgent nel core | ignoto | ignoto | molto alto | molto alto | **No-go** |

### 5.1 Opportunità 1: EvidenceBundle + RAG primario

È la migliore combinazione di sinergia e plausibilità economica. Alembic dovrebbe
creare un `EvidenceBundle` immutabile per evento:

- documento primario e timestamp di disponibilità;
- issuer/ticker risolto point-in-time;
- estratti earnings/guidance/transcript con riferimenti;
- fundamentals disponibili `as_of`;
- market/regime snapshot;
- articoli correlati deduplicati;
- hash input, versioni retrieval/prompt/model.

Il retriever deve interrogare solo documenti archiviati prima di `as_of`. L'output
resta una feature shadow (`polarity`, `materiality`, `novelty`, `guidance_delta`,
`evidence_refs`), mai un ordine.

### 5.2 Opportunità 2: FinGPT specialistico nel tournament Alembic

Un adapter traduce l'output FinGPT in `ModelOutput`. La confidence non deve essere
inventata dal testo generato: va derivata da logits/probabilità e calibrata con
temperature scaling o isotonic regression su validation temporale.

Il modello non va inserito subito nel majority-of-3. Va eseguito come candidato
shadow sulla stessa news dei modelli correnti, poi valutato per:

- macro-F1/balanced accuracy sul golden set;
- calibration (Brier/ECE);
- Spearman IC e hit rate su forward return;
- residual IC rispetto al consensus corrente;
- coverage, parse-fail, latency p95, costo/GPU-hour;
- stabilità per event type, source, ticker size e regime.

Un modello NLP migliore ma con residual IC nullo non aggiunge alpha e non deve
entrare nel live ensemble.

### 5.3 Opportunità 3: Forecaster event-conditioned

Non replicare il Forecaster generale DOW30. Costruire una variante limitata a un
solo vettore causale, preferibilmente earnings/guidance o PEAD:

```text
snapshot Alembic as_of
  -> event document + surprise + guidance + market context
  -> baseline numerica
  -> LLM/LoRA assessment shadow
  -> feature 5d
  -> backtest Alembic con costi e gate
```

Il label futuro non deve mai apparire nel prompt di inferenza né in un rationale che
possa contaminare la validation. Split e tuning devono essere puramente temporali.

### 5.4 Opportunità 4: dataset proprietario e LoRA

Il vantaggio competitivo non è l'adapter pubblico del 2023, ma un futuro adapter
addestrato su:

- label issuer-specific di Alembic;
- eventi primari e tassonomia Alembic;
- outcome multi-horizon;
- hard negative (news positive per settore ma negative per issuer, ticker ambiguo,
  rumor, already-priced-in);
- esempi di astensione.

Il target non deve essere soltanto “positivo/neutro/negativo”: deve riflettere
materiality, directness, novelty e orizzonte. Il golden set da circa 400 esempi è
utile per screening/calibrazione, non sufficiente da solo per giustificare il
fine-tuning di un 7B/13B. Conviene accumulare migliaia di esempi stabili prima di
investire nel training.

### 5.5 Opportunità 5: resolver e knowledge graph

FinGPT NER/relation extraction può proporre organizzazioni e relazioni, ma il dataset
NER pubblicizzato è molto piccolo (511 train, 98 test) e la tassonomia non comprende
identità strumento point-in-time. L'output deve quindi alimentare soltanto candidate
generation; la risoluzione finale resta deterministica e auditabile in Alembic.

## 6. Architettura raccomandata

```text
                        ALEMBIC = SOURCE OF TRUTH

ingest -> dedup -> point-in-time resolver -> materiality/novelty gate
                                      |
                                      v
                            EvidenceBundle v1
                                      |
                 +--------------------+--------------------+
                 |                                         |
                 v                                         v
      current Alembic ensemble                optional FinGPT service
                                                 - sentiment adapter
                                                 - RAG adapter
                                                 - forecaster adapter
                 |                                         |
                 +--------------------+--------------------+
                                      v
                         shadow outputs in PostgreSQL
                                      |
                                      v
                    labels + forward returns + cost/latency
                                      |
                                      v
                         Alembic comparison/promotion gates
                                      |
                         no direct edge to order submission
```

Vincoli architetturali:

- processo/container separato con API JSON versionata;
- model/prompt/retriever version e input hash persistiti;
- timeout/budget/semaphore separati dal live path;
- nessun accesso rete durante replay;
- circuit breaker e nessun blocco del worker live;
- output raw conservato per audit;
- dipendenza opzionale, removibile senza migration del core.

## 7. Tre PoC decision-grade

### PoC A — FinGPT-Sentiment shadow tournament

**Domanda:** aggiunge qualità o diversità rispetto a FinBERT e ai modelli correnti?  
**Scope:** nessun ordine, stesso corpus/input hash, adapter isolato.  
**Dataset:** golden labels Alembic + forward return già persistiti.  
**Baseline:** FinBERT, ogni modello live, consensus live.  
**Gate:** delta OOS positivo su balanced accuracy e calibration; residual IC positivo
con intervallo block-bootstrap che non attraversa zero; costo/latency entro budget;
nessun degrado concentrato su eventi materiali.  
**Kill:** residual IC nullo/negativo, confidence non calibrabile o GPU economics
peggiori del beneficio.

### PoC B — RAG ablation su eventi primari

**Domanda:** il contesto recuperato migliora l'interpretazione e il forward-return IC?  
**Varianti:** `current prompt`, `current + primary context`, `current + RAG context`.  
**Dataset:** eventi earnings/8-K con snapshot congelato; stessi modelli per isolare
l'effetto del retrieval.  
**Metriche:** macro-F1 per event/materiality, evidence precision, hallucination rate,
Brier/ECE, IC 1d/5d/20d, residual IC, costi e latency.  
**Gate:** zero leakage; ogni fatto deve avere evidence ref; miglioramento OOS stabile
per più finestre/regimi; beneficio netto dopo costi.  
**Kill:** RAG migliora F1 ma non IC, oppure il guadagno deriva da documenti non
disponibili `as_of`.

### PoC C — Earnings/PEAD forecaster feature

**Domanda:** una previsione event-conditioned a 5d aggiunge alpha al vettore numerico?  
**Varianti:** price/surprise baseline, baseline + current LLM, baseline + FinGPT-style
LoRA.  
**Metriche:** directional balanced accuracy, Spearman/Pearson IC, calibration,
net Sharpe, max drawdown, turnover, hit rate, top-event concentration, DSR e
walk-forward degradation.  
**Gate:** split temporale puro, realistic costs, più regimi, nessun singolo ticker o
evento domina il risultato.  
**Kill:** incremento solo in-sample, non supera una baseline numerica semplice o
scompare dopo costi.

## 8. Impatto atteso su alpha, redditività e accuratezza

### Accuratezza

È plausibile che FinGPT-Sentiment o RAG migliorino label accuracy su testi finanziari,
specialmente su headline brevi. L'evidenza primaria FinGPT supporta questa ipotesi.
Non dimostra però generalizzazione al news mix, alla tassonomia issuer-specific e ai
modelli 2026 di Alembic.

### Alpha

L'alpha più plausibile non viene dal “sentiment migliore” in astratto, ma da:

- contesto primario che separa headline tone da impatto economico;
- materiality/novelty e guidance delta;
- diversità residuale rispetto all'ensemble corrente;
- astensione sui casi ambigui;
- specializzazione su un orizzonte/evento dichiarato.

Ogni beneficio deve essere misurato come incremental/residual IC, non come F1 isolato.

### Redditività

Non è possibile stimare responsabilmente un incremento percentuale di P&L dai dati
FinGPT disponibili. La redditività dipenderà da coverage, threshold, turnover,
slippage, capacity e correlazione con le strategie esistenti. Il solo criterio valido
è un confronto walk-forward netto dentro Alembic.

### Efficienza economica

FinGPT può ridurre costo API solo se un modello locale specialistico raggiunge qualità
comparabile con throughput accettabile. Un Llama-2 13B in 8-bit non è automaticamente
più economico: vanno inclusi GPU-hour, idle capacity, manutenzione, cold start e
latency. Un piccolo classifier moderno o un modello distillato potrebbe avere economics
migliori dell'adapter FinGPT originale.

## 9. Rischi e no-go

### Rischi tecnici e quant

- **Dataset shift:** benchmark 2023 e DOW30 non rappresentano necessariamente il mix
  Alembic 2026.
- **Leakage:** fundamentals correnti, retrieval live o rationale condizionato dal
  label possono gonfiare i risultati.
- **Confidence fittizia:** la confidence generata come testo non è probabilità
  calibrata.
- **Overfitting/multiple testing:** molte varianti FinGPT aumentano il rischio di
  selezionare rumore; usare DSR, pre-registrazione e holdout finale.
- **Latency/capacity:** 7B/13B locali possono peggiorare throughput e freshness.
- **Fragilità software:** scarsi test, notebook, dipendenze datate e setup non
  uniforme aumentano il costo operativo.
- **Source/licensing:** dataset aggregati e API richiedono verifica di licenza,
  redistribuzione e diritti d'uso.

### Licenze

Il codice repository è MIT ([LICENSE](https://github.com/AI4Finance-Foundation/FinGPT/blob/master/LICENSE)).
Gli adapter non annullano però la licenza del base model: il sentiment adapter usa
Llama-2-13B e il Forecaster Llama-2-7B. La model card Meta identifica Llama 2 con
licenza custom e condizioni di utilizzo/redistribuzione
([Meta model card](https://huggingface.co/meta-llama/Llama-2-7b-chat-hf)). Le dataset
card FinGPT sono incomplete; prima di training commerciale serve un inventario per
record/source. Questa è una nota tecnica, non consulenza legale.

### No-go espliciti

1. FinGPT-Forecaster non invia ordini né modifica target weight.
2. Multi-agent/RAG non sostituisce risk controls deterministici.
3. Nessun fetch live durante replay storico.
4. Nessun modello entra nel live ensemble perché “batte GPT-4” in un README.
5. Nessun monorepo merge o import dell'intero package FinGPT nel core Alembic.
6. Nessun fine-tuning sul golden set piccolo senza holdout temporale e governance.

## 10. Collaborazioni possibili con AI4Finance/FinGPT

La collaborazione più credibile non è “integrare FinGPT”, ma pubblicare un benchmark
che colmi il gap sentiment-to-alpha:

1. **Temporal Financial Sentiment-to-Return Benchmark:** input point-in-time,
   issuer-specific, output strutturato, forward return multi-horizon.
2. **RAG ablation con primary evidence:** stessa base LLM, con/senza contesto, metriche
   NLP e finanziarie.
3. **Model card finanziaria:** calibration, latency, GPU economics, regime/source
   breakdown e limiti, non solo F1 aggregato.
4. **Adapter Alembic-compatible upstream:** schema JSON, logits/confidence, batch
   inference e test; senza pubblicare logica proprietaria di execution.
5. **Paper/technical report congiunto:** risultati shadow anonimizzati o dataset
   pubblico separato, con IP/data sharing agreement prima dello scambio dati.

Possibile contributo upstream immediato e a basso rischio: migliorare model/dataset
card, test di packaging e un evaluator temporale riproducibile. Una collaborazione su
dati Alembic va invece approvata esplicitamente e deve escludere secret, ordini,
posizioni e logica proprietaria.

## 11. Allineamento alla roadmap Alembic

Questa analisi non modifica lo stato della roadmap. Le issue GitHub restano l'unica
source of truth.

- `#36` (ensemble a tre modelli): FinGPT è al massimo un **candidato shadow da
  confrontare**, non una sostituzione automatica del terzo modello già pianificato.
- `#51` (alpha vectors + qualità ticker/sentiment): ospita concettualmente QS-05 RAG,
  resolver/NER e nuovi vettori; richiede triage prima di creare lavoro eseguibile.
- `#37` (Vettore A earnings chain) e `#38` (S7 PEAD): sono i punti naturali per un
  futuro RAG/Forecaster event-conditioned, nel rispetto dei loro blocker e scope.
- `#30/#54` (golden labels/migration): sono prerequisiti per una valutazione seria del
  sentiment specialistico e della calibration.

Non va implementato nulla da questo documento finché l'opportunità non viene
triagiata come child pronta secondo il processo Wayfinder.

## 12. Raccomandazione finale

La sequenza con miglior rapporto informazione/costo è:

1. completare i prerequisiti di label e measurement già in roadmap;
2. eseguire **PoC A** come shadow adapter isolato;
3. se il modello aggiunge residual IC, decidere se tenerlo come specialist/fallback;
4. in parallelo progettare **PoC B** su un solo evento primario;
5. avviare **PoC C** solo dopo avere un EvidenceBundle point-in-time e abbastanza
   eventi per un walk-forward credibile;
6. considerare LoRA proprietario solo dopo la raccolta di dati sufficiente.

In sintesi: **FinGPT può migliorare Alembic soprattutto fornendo specializzazione
finanziaria e un'ipotesi RAG da testare. L'alpha non è nel repository FinGPT; nasce
solo se Alembic dimostra che quelle feature aggiungono informazione residuale e P&L
netto fuori campione.**

## Fonti primarie principali

- [FinGPT repository ufficiale](https://github.com/AI4Finance-Foundation/FinGPT)
- [FinGPT: Open-Source Financial Large Language Models](https://arxiv.org/abs/2306.06031)
- [FinGPT: Instruction Tuning Benchmark](https://arxiv.org/abs/2310.04793)
- [Enhancing Financial Sentiment Analysis via RAG](https://arxiv.org/abs/2310.04027)
- [FinGPT sentiment adapter model card](https://huggingface.co/FinGPT/fingpt-sentiment_llama2-13b_lora)
- [FinGPT Forecaster adapter model card](https://huggingface.co/FinGPT/fingpt-forecaster_dow30_llama2-7b_lora)
- [FinGPT sentiment dataset card](https://huggingface.co/datasets/FinGPT/fingpt-sentiment-train)
- [FinGPT Forecaster dataset card](https://huggingface.co/datasets/FinGPT/fingpt-forecaster-dow30-202305-202405)
- [Meta Llama-2 model card e licenza](https://huggingface.co/meta-llama/Llama-2-7b-chat-hf)

