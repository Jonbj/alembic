# Istruzioni per Review Esterna — LLM Trading System

**Documento per Reviewer Esterni**  
**Versione:** 1.0.0  
**Data:** 2026-05-04  
**Stato:** Fase 1 Completata (281 test passing)

---

## Panoramica

Questo documento fornisce istruzioni per un modello LLM esterno che deve eseguire una **review tecnica completa** del nostro LLM Trading System.

Il sistema implementa il paradigma **"Alpha Miner"**: i modelli LLM operano offline per generare segnali di sentiment, che vengono cached in Redis e letti dal motore di esecuzione (QuantConnect) senza chiamate API sincrone.

---

## Prerequisiti

Prima di iniziare la review, assicurati di avere accesso a:

1. **Repository completo** con tutti i file sorgente
2. **Documentazione** in `README.md`, `docs/ARCHITECTURE.md`, `docs/API.md`
3. **Test suite** eseguibile con `python -m pytest tests/ -v`

---

## Istruzioni per la Review

### Step 1: Comprensione dell'Architettura (30 min)

Leggi nell'ordine:

1. **README.md** — Panoramica, setup, componenti principali
2. **docs/ARCHITECTURE.md** — Architettura dettagliata, formule, decisioni
3. **docs/API.md** — Endpoint API, request/response format

**Obiettivo:** Capire il flusso end-to-end:
```
News → Celery Worker → LLM Ensemble → Redis → QuantConnect OnData()
```

---

### Step 2: Review del Codice (60 min)

Analizza i file critici nell'ordine:

| File | Cosa Verificare | Priorità |
|------|-----------------|----------|
| `src/llm/client.py` | Security (ALLOWED_MODEL_IDS, CLI validation), async patterns | HIGH |
| `src/llm/ensemble.py` | Aggregazione, divergence detection, edge cases | HIGH |
| `src/llm/finbert.py` | Entropic confidence mapping | MEDIUM |
| `src/performance/ic.py` | Composite IC formula, Newey-West HAC | HIGH |
| `src/performance/drift.py` | PSI formula, CUSUM, circuit breakers | HIGH |
| `src/performance/weights.py` | LOO ICIR, smoothing, guardrails | MEDIUM |
| `src/store/redis_store.py` | OOM handling, TTL management | MEDIUM |
| `src/store/pg_store.py` | Connection pooling, rollback | MEDIUM |
| `src/workers/sentiment.py` | Budget integration, fallback logic | HIGH |
| `src/workers/performance.py` | IC calculation, streak update | HIGH |

---

### Step 3: Review della Sicurezza (30 min)

Verifica i seguenti security controls:

| Control | File | Cosa Cercare |
|---------|------|--------------|
| **Command Injection** | `src/llm/client.py` | `ALLOWED_MODEL_IDS` usato prima di subprocess |
| **SQL Injection** | `src/store/pg_store.py` | Query parametrizzate con `(%s \|\| ' days')::interval` |
| **Input Sanitization** | `src/text/sanitizer.py` | BiDi removal, emoji removal, NFKC normalization |
| **Redis OOM** | `src/store/redis_store.py` | Try/except in tutte le write operation |
| **API Key Validation** | `src/config.py`, `src/api/auth.py` | Lunghezza minima 32 char, header check |

---

### Step 4: Review dei Test (30 min)

Esegui e analizza:

```bash
# Esegui tutti i test
python -m pytest tests/ -v

# Coverage per modulo
python -m pytest tests/ --cov=src --cov-report=term-missing
```

**Cosa verificare:**
- Test per edge cases (empty list, None, ZeroDivision)
- Test per security controls (model_id injection, SQL injection)
- Test per formule matematiche (IC, PSI, CUSUM)
- Integration test per flussi end-to-end

---

### Step 5: Review della Documentazione (30 min)

Valuta la documentazione con questi criteri:

| Criterio | Domande da Porre |
|----------|------------------|
| **Completezza** | Tutti i componenti sono documentati? Ci sono esempi sufficienti? |
| **Chiarezza** | Un nuovo sviluppatore può capire il sistema in <1 ora? |
| **Accuratezza** | Le formule corrispondono all'implementazione? I valori sono corretti? |
| **Sicurezza** | I security controls sono ben documentati? Ci sono avvertimenti? |

---

## Template per il Report di Review

Usa questo template per strutturare il tuo report:

```markdown
# Report di Review — [TUO NOME MODELLO]

## Executive Summary
Breve panoramica (3-5 frasi) sulla qualità complessiva del sistema.

## ✅ Punti di Forza
Lista di ciò che è ben fatto:
- Architettura solida
- Security-first approach
- Test coverage elevato
- ...

## 🔴 Problemi Critici (HIGH Priority)

| # | Descrizione | File | Impatto | Suggerimento |
|---|-------------|------|---------|--------------|
| 1 | ... | ... | ... | ... |

## 🟡 Problemi Minori (MEDIUM Priority)

| # | Descrizione | File | Impatto | Suggerimento |
|---|-------------|------|---------|--------------|
| 1 | ... | ... | ... | ... |

## 🟢 Miglioramenti Suggeriti (LOW Priority)

Lista di miglioramenti non critici ma utili.

## 📊 Verifiche di Sicurezza

| Control | Status | Note |
|---------|--------|------|
| Command Injection Prevention | ✅/❌ | ... |
| SQL Injection Prevention | ✅/❌ | ... |
| Input Sanitization | ✅/❌ | ... |
| Redis OOM Handling | ✅/❌ | ... |
| API Key Validation | ✅/❌ | ... |

## 📈 Valutazione Complessiva

| Categoria | Voto (1-10) | Note |
|-----------|-------------|------|
| Architettura | X/10 | ... |
| Codice | X/10 | ... |
| Sicurezza | X/10 | ... |
| Test | X/10 | ... |
| Documentazione | X/10 | ... |

**Voto Complessivo: X/10**

## 🎯 Raccomandazioni Prioritarie

Lista delle 3-5 azioni più importanti da intraprendere prima del deployment in production.
```

---

## Checklist di Verifica Rapida

Usa questa checklist per una valutazione iniziale:

### Architettura
- [ ] LLM mai chiamato sincronamente nel loop di trading
- [ ] Redis caching con TTL appropriato (4h)
- [ ] PostgreSQL per audit trail
- [ ] Kill-switch implementato e testato

### Sicurezza
- [ ] `ALLOWED_MODEL_IDS` frozenset definita e usata
- [ ] CLI path validato con `shutil.which()` o existence check
- [ ] SQL query parametrizzate (no string interpolation)
- [ ] BiDi characters e emoji rimossi dall'input
- [ ] Redis OOM gestito con try/except

### Codice
- [ ] Type hints completi
- [ ] Edge cases gestiti (empty list, None, ZeroDivision)
- [ ] Docstring con esempi d'uso
- [ ] Async patterns corretti (`asyncio.as_completed` con task mapping)

### Test
- [ ] 250+ test passing
- [ ] Test per security controls
- [ ] Test per formule matematiche
- [ ] Integration test per flussi end-to-end

### Documentazione
- [ ] README con setup instructions
- [ ] ARCHITECTURE con formule e diagrammi
- [ ] API reference completa
- [ ] Security fix documentati

---

## Domande Frequenti (FAQ)

### D: Qual è la formula corretta per il PSI?
**R:** `PSI = Σ expected_i × ln(expected_i / actual_i)`

La formula **NON** include `(expected_i - actual_i)` come moltiplicatore.
Vedi `src/performance/drift.py` riga 103 per l'implementazione corretta.

### D: Come viene calcolato il Composite IC?
**R:** `IC_composite = 0.5 × Spearman + 0.3 × weighted_hit_rate + 0.2 × (1 − Brier)`

Vedi `src/performance/ic.py` riga 104 per l'implementazione.

### D: Cosa succede se Redis è down?
**R:** Le write operation falliscono gracefully (log + drop), le read operation sollevano eccezioni. L'execution engine può continuare con segnali stale.

### D: Come viene gestito il budget LLM?
**R:** `LLMBudgetTracker.check_budget()` solleva `LLMBudgetExhaustedError` se il budget è exhausted. Il SentimentWorker fallback a FinBERT (gratis).

### D: Qual è la formula per l'entropic confidence mapping di FinBERT?
**R:** `confidence = 1 - H(p) / H_max` dove `H(p) = -Σ p_i × log(p_i)`

Vedi `src/llm/finbert.py` per l'implementazione.

---

## Contatti e Supporto

Per domande o chiarimenti durante la review:

1. Consulta la documentazione in `docs/`
2. Verifica i test in `tests/` per esempi d'uso
3. Controlla il Decision Log in `ARCHITECTURE.md` sezione 8

---

## Prossimi Passi

Dopo la review:

1. **Priorità HIGH:** Correggere eventuali bug critici identificati
2. **Priorità MEDIUM:** Migliorare documentazione e test coverage
3. **Priorità LOW:** Refactor e ottimizzazioni

Il sistema è considerato **production-ready** quando:
- Tutti i bug HIGH sono corretti
- Test coverage è >90% sui moduli critici
- La documentazione è completa e accurata
