# Sessione Multi-Modello — Analisi Sistema di Trading LLM

## Istruzioni per la sessione

Questo documento coordina una sessione di analisi distribuita su un sistema di trading algoritmico basato su LLM. Ci sono **6 file di analisi** indipendenti, ciascuno pensato per un dominio specifico. L'obiettivo è raccogliere risposte da più modelli, assegnando ogni file al modello più adatto per competenza, e poi sintetizzare i risultati.

---

## Contesto del progetto (da leggere per tutti i modelli)

Sistema Python di trading algoritmico multi-asset che integra LLM come motore offline di generazione segnali (paradigma "Alpha Miner"). I modelli linguistici **non sono mai nel loop critico di esecuzione** — generano segnali pre-calcolati consumati da QuantConnect Lean.

**Stack:** FastAPI + Celery + Redis + PostgreSQL + QuantConnect Lean  
**LLM:** Claude Sonnet / GPT-4o / Gemini Pro via API (provider-agnostico)  
**Fallback locale:** FinBERT (HuggingFace, CPU)  
**Pattern architetturale:** Monolite modulare → decomponibile in microservizi  
**Fase corrente:** design completato, pre-implementazione

I 6 file di analisi sono stati preparati prima dell'inizio dell'implementazione per raccogliere feedback specializzato su componenti critici del sistema. Ogni file è autonomo e contiene tutto il contesto necessario.

---

## Assegnazione dei file ai modelli

### Logica di assegnazione

Ogni file richiede competenze specifiche. Di seguito l'assegnazione consigliata in base ai punti di forza tipici dei modelli disponibili. Se un modello non è disponibile, ridistribuisci i file mantenendo la separazione dei domini.

---

### File 01 — `01-dkcot-prompt-engineering.md`
**Dominio:** Prompt engineering, NLP finanziario  
**Assegna a:** Claude (Anthropic) — forte in prompt engineering e ragionamento strutturato  
**Alternativa:** GPT-4o  
**Output atteso:** System prompt + user prompt completi, analisi critica, variante alternativa  

---

### File 02 — `02-risk-parameter-calibration.md`
**Dominio:** Quantitative risk management  
**Assegna a:** GPT-4o — forte in matematica finanziaria e letteratura quant  
**Alternativa:** Claude  
**Output atteso:** Tabella validazione parametri, lista parametri mancanti, due set YAML (conservativo/operativo)  

---

### File 03 — `03-module-structure-contracts.md`
**Dominio:** Software architecture Python, sistemi event-driven  
**Assegna a:** Claude — forte in architettura software e codice Python idiomatico  
**Alternativa:** GPT-4o  
**Output atteso:** Valutazione struttura, tabella contratti mancanti, struttura directory proposta, codice Python completo per 3 contratti  

---

### File 04 — `04-ab-test-methodology.md`
**Dominio:** Statistica finanziaria, metodologia di backtest  
**Assegna a:** GPT-4o — forte in statistica e machine learning finanziario  
**Alternativa:** Gemini  
**Output atteso:** Design A/B test completo, schema walk-forward, matrice decisionale, framework IC  

---

### File 05 — `05-finbert-mapping.md`
**Dominio:** NLP, modelli transformer, ingegneria del segnale  
**Assegna a:** Gemini — forte in NLP e modelli HuggingFace  
**Alternativa:** Claude  
**Output atteso:** Analisi 3 approcci di mapping, implementazione Python completa con test pytest, confronto alternative fallback  

---

### File 06 — `06-postgresql-schema.md`
**Dominio:** Database design, PostgreSQL, sistemi time-series  
**Assegna a:** GPT-4o — forte in SQL e ottimizzazione database  
**Alternativa:** Claude  
**Output atteso:** Schema SQL migliorato completo, strategia indici, 4 query ottimizzate, pattern operativi  

---

## Istruzioni per ogni modello che risponde

Prima di iniziare, leggi:
1. Il contesto del progetto in questo documento (sezione sopra)
2. Il file assegnato nella sua interezza

Poi rispondi secondo il formato atteso specificato in fondo al file assegnato. Non è necessario leggere gli altri 5 file — ogni file è completamente autonomo.

**Vincoli di risposta:**
- Risposte concrete e implementabili, non principi generali
- Dove richiesto codice: codice funzionante e completo, non pseudocodice
- Dove richiesto YAML o SQL: sintassi corretta e pronta all'uso
- Segnala esplicitamente se una parte del file contiene assunzioni che ritieni errate
- Se identifichi un problema critico non coperto dal file, aggiungilo in una sezione "Problemi aggiuntivi rilevati"

---

## Istruzioni per la sintesi finale

Dopo aver raccolto le risposte da tutti i modelli, esegui questa sintesi:

### 1. Conflitti da risolvere
Per ogni coppia di file dove due modelli hanno risposto allo stesso tema (es. entrambi menzionano la struttura moduli), identifica eventuali raccomandazioni contrastanti e segnalale.

### 2. Dipendenze cross-file
Alcune raccomandazioni in un file impattano altri file:
- Modifiche allo schema `SentimentResult` (file 01, 05) → impattano schema PostgreSQL (file 06)
- Nuovi parametri di rischio (file 02) → impattano la struttura del Risk Manager (file 03)
- Requisiti A/B test (file 04) → impattano la struttura delle tabelle PostgreSQL (file 06)

Identifica e risolvi queste dipendenze prima di portare le raccomandazioni all'implementazione.

### 3. Priorità di implementazione
Classifica le raccomandazioni raccolte in:
- **Bloccanti:** devono essere incorporate nella spec prima di scrivere una riga di codice
- **Importanti:** da incorporare nell'implementazione della Fase 1
- **Nice-to-have:** da valutare in Fase 2+

### 4. Domande aperte residue
Elenca eventuali questioni che i modelli hanno sollevato ma non risolto, che richiedono una decisione da parte del team prima dell'implementazione.

---

---

### File 09 — `09-implementation-plan-review.md`
**Dominio:** Software engineering, sistemi distribuiti Python, TDD, sicurezza  
**Assegna a:** deepseek-v4-pro:cloud — forte in code review e analisi tecnica sistematica  
**Alternativa:** opus o qwen3.5:cloud  
**Output atteso:** Lista bug confermati con fix, test mancanti con codice pytest, problemi architetturali con soluzioni, gap spec/piano prioritizzati, lista max 5 fix critici da applicare prima dell'implementazione

---

## Distribuzione alternativa (se hai accesso a un solo modello)

Se stai usando un solo modello per tutti i file, invia i file in questo ordine di priorità:

1. `09-implementation-plan-review.md` — **priorità massima**: va inviato subito prima di iniziare a scrivere codice
2. `03-module-structure-contracts.md` — fondamenta architetturali
3. `01-dkcot-prompt-engineering.md` — componente LLM core
4. `06-postgresql-schema.md` — schema dati
5. `02-risk-parameter-calibration.md` — parametri di rischio
6. `05-finbert-mapping.md` — fallback
7. `04-ab-test-methodology.md` — metodologia A/B test

Invia ogni file in una conversazione separata per evitare interferenze di contesto.
