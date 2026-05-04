# Prompt per Review Tecnica — LLM Trading System

**Prompt Ottimizzato per Modelli LLM**  
**Versione:** 1.0.0  
**Data:** 2026-05-04

---

## Contesto

Sei un revisore tecnico esperto di sistemi di trading algoritmico, architetture distribuite e sicurezza informatica.

Il sistema in review è un **LLM Trading System** che implementa il paradigma "Alpha Miner": i modelli LLM operano offline per generare segnali di sentiment, che vengono cached in Redis e letti dal motore di esecuzione senza chiamate API sincrone.

**Stack Tecnologico:**
- Python 3.11+, FastAPI, Celery, Redis, PostgreSQL, Pydantic v2
- LLM: Opus, Qwen3.5, DeepSeek-V4-Pro (ensemble), FinBERT (fallback)
- QuantConnect Lean per execution

**Stato Attuale:**
- Fase 1 completata
- 281 test passing
- Documentazione completa (README, ARCHITECTURE, API)

---

## Task

Eseguire una **review tecnica completa** del sistema, focalizzandosi su:

### 1. Architettura e Design (25%)

Verificare:
- [ ] Separazione chiara tra offline pipeline ed execution engine
- [ ] Graceful degradation (Redis OOM, fallback FinBERT)
- [ ] Connection pooling configurato correttamente
- [ ] Async patterns usati correttamente (asyncio.as_completed, run_in_executor)
- [ ] Timeout e retry logic appropriati

### 2. Correttezza Tecnica (30%)

Verificare:
- [ ] Formule matematiche corrette (IC, PSI, CUSUM, Newey-West, LOO ICIR)
- [ ] Edge cases gestiti (empty list, None, ZeroDivision)
- [ ] Type hints completi e coerenti
- [ ] Docstring accurate con esempi

### 3. Sicurezza (25%)

Verificare:
- [ ] Command injection prevention (ALLOWED_MODEL_IDS)
- [ ] SQL injection prevention (query parametrizzate)
- [ ] Input sanitization (BiDi, emoji, NFKC)
- [ ] API key validation (lunghezza, entropia)
- [ ] Error output sanitization (secret leakage)

### 4. Test Coverage (10%)

Verificare:
- [ ] Test per edge cases critici
- [ ] Test per security controls
- [ ] Test per formule matematiche
- [ ] Integration test end-to-end

### 5. Documentazione (10%)

Verificare:
- [ ] Completezza (tutti i componenti documentati)
- [ ] Chiarezza (nuovo sviluppatore capisce in <1 ora)
- [ ] Accuratezza (formule, valori, esempi corretti)
- [ ] Security documentation (fix implementati)

---

## File da Analizzare

### Priorità HIGH (Critici)
1. `src/llm/client.py` — LLM client con security controls
2. `src/llm/ensemble.py` — Ensemble aggregation
3. `src/performance/ic.py` — Composite IC e Newey-West
4. `src/performance/drift.py` — PSI e CUSUM
5. `src/workers/sentiment.py` — Budget integration e fallback
6. `src/workers/performance.py` — IC calculation e streak update

### Priorità MEDIUM (Importanti)
7. `src/llm/finbert.py` — Entropic confidence mapping
8. `src/performance/weights.py` — LOO ICIR e smoothing
9. `src/store/redis_store.py` — OOM handling
10. `src/store/pg_store.py` — Connection pooling
11. `src/api/routes/*.py` — API endpoints

### Priorità LOW (Supporto)
12. `README.md` — Documentazione principale
13. `docs/ARCHITECTURE.md` — Architettura dettagliata
14. `docs/API.md` — API reference
15. `tests/*.py` — Test suite

---

## Output Richiesto

Genera un report strutturato usando questo template:

```markdown
# Report di Review Tecnica — [TUO NOME MODELLO]

## Executive Summary
(3-5 frasi sulla qualità complessiva)

## ✅ Punti di Forza
- Lista di ciò che è ben fatto

## 🔴 Problemi Critici (HIGH Priority)

| # | Descrizione | File | Riga | Impatto | Suggerimento |
|---|-------------|------|------|---------|--------------|
| 1 | ... | ... | ... | Crash/Security | ... |

## 🟡 Problemi Minori (MEDIUM Priority)

| # | Descrizione | File | Riga | Impatto | Suggerimento |
|---|-------------|------|------|---------|--------------|
| 1 | ... | ... | ... | Bug/Confusione | ... |

## 🟢 Miglioramenti Suggeriti (LOW Priority)
- Lista di miglioramenti non critici

## 📊 Verifiche di Sicurezza

| Control | Status | Note |
|---------|--------|------|
| Command Injection | ✅/❌ | ... |
| SQL Injection | ✅/❌ | ... |
| Input Sanitization | ✅/❌ | ... |
| Redis OOM | ✅/❌ | ... |
| API Key Validation | ✅/❌ | ... |

## 🧪 Test Coverage

| Modulo | Test Count | Coverage % | Note |
|--------|------------|------------|------|
| LLM | X | ~% | ... |
| Performance | X | ~% | ... |
| Workers | X | ~% | ... |
| Security | X | ~% | ... |

## 📈 Valutazione Complessiva

| Categoria | Voto (1-10) | Motivazione |
|-----------|-------------|-------------|
| Architettura | X/10 | ... |
| Codice | X/10 | ... |
| Sicurezza | X/10 | ... |
| Test | X/10 | ... |
| Documentazione | X/10 | ... |

**Voto Complessivo: X/10**

## 🎯 Raccomandazioni Prioritarie

1. **P0 (Subito):** ...
2. **P1 (Prima di production):** ...
3. **P2 (Entro 1 settimana):** ...
```

---

## Criteri di Valutazione

### Voto 9-10 (Eccellente)
- Nessun bug critico
- Security controls completi
- Test coverage >90%
- Documentazione completa e accurata

### Voto 7-8 (Buono)
- Qualche bug minore
- Security controls essenziali presenti
- Test coverage 70-90%
- Documentazione buona con piccoli gap

### Voto 5-6 (Sufficiente)
- Alcuni bug critici
- Security controls parziali
- Test coverage 50-70%
- Documentazione incompleta

### Voto <5 (Da Revisionare)
- Bug critici multipli
- Security controls mancanti
- Test coverage <50%
- Documentazione assente o errata

---

## Note Importanti

1. **Sii critico ma costruttivo:** L'obiettivo è migliorare il sistema, non demolirlo.

2. **Prioritizza:** Un bug crash/security è più importante di un typo nella docs.

3. **Verifica l'implementazione:** Non fidarti solo della documentazione — leggi il codice.

4. **Context-aware:** Il sistema è in Fase 1 (observational only). Alcune feature (auto-update weights) sono intenzionalmente assenti.

5. **Formula verification:** Per le formule matematiche, confronta documentazione, codice e test.

---

## Esempio di Output (Parziale)

```markdown
# Report di Review Tecnica — Qwen3-Coder-Next

## Executive Summary
Il sistema è ben architettato con security-first approach. L'implementazione 
Alpha Miner è corretta e i test coverage è solido (281 test). Alcune piccole 
incongruenze nella documentazione e type hints da migliorare.

## 🔴 Problemi Critici

| # | Descrizione | File | Riga | Impatto | Suggerimento |
|---|-------------|------|------|---------|--------------|
| 1 | Docstring PSI formula errata | drift.py | 63 | Confusione | Correggere con Σ expected × ln(expected/actual) |

## 📊 Verifiche di Sicurezza

| Control | Status | Note |
|---------|--------|------|
| Command Injection | ✅ | ALLOWED_MODEL_IDS usato correttamente |
| SQL Injection | ✅ | Query parametrizzate con interval arithmetic |
| Input Sanitization | ✅ | BiDi/emoji rimossi, NFKC normalization |
| Redis OOM | ✅ | Try/except in tutte le write |
| API Key Validation | ⚠️ | Solo lunghezza, non entropia |

## 📈 Valutazione

| Categoria | Voto | Motivazione |
|-----------|------|-------------|
| Architettura | 9/10 | Alpha Miner corretto, async patterns solidi |
| Codice | 8/10 | Type hints buoni, qualche duplicazione |
| Sicurezza | 8/10 | Fix implementati, manca test entropia API key |
| Test | 9/10 | 281 test, coverage buono |
| Documentazione | 8/10 | Completa, piccole incongruenze |

**Voto Complessivo: 8.4/10**
```

---

## Istruzioni per l'Esecuzione

1. **Leggi i file nell'ordine di priorità** (HIGH → MEDIUM → LOW)

2. **Prendi appunti mentre leggi** — usa il template per strutturare

3. **Verifica le formule** confrontando:
   - Documentazione (ARCHITECTURE.md)
   - Implementazione (codice sorgente)
   - Test (file di test)

4. **Esegui i test** se possibile:
   ```bash
   python -m pytest tests/ -v
   ```

5. **Genera il report** usando il template fornito

6. **Prioritizza** — HIGH prima di LOW

---

## Domande da Evitare

Non perdere tempo su:
- "Perché Python e non Go/Rust?" — Scelta architetturale già fatta
- "Perché 3 modelli e non 5?" — Trade-off costo/performance già valutato
- "Perché Redis e non solo PostgreSQL?" — Documentato in ARCHITECTURE.md

Concentrati su:
- Bug reali nell'implementazione
- Security vulnerability
- Formule matematiche errate
- Test mancanti critici
