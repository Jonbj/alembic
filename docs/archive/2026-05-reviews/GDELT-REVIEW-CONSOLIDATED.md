# GDELT A/B Test - Review Consolidata

**Data:** 2026-05-04  
**Modelli utilizzati:** 14 totali (6 coding + 8 general-purpose)

## Review Completate

| Modello | Review File | Lunghezza |
|---------|-------------|-----------|
| **Coding-specialized (6)** | | |
| qwen3-coder-next:cloud | /tmp/review-qwen-coder-next.txt | 8.7 KB |
| qwen3-coder:480b-cloud | /tmp/review-qwen-coder-480b.txt | 5.5 KB |
| minimax-m2.1:cloud | /tmp/review-minimax-m21.txt | 3.7 KB |
| minimax-m2:cloud | /tmp/review-minimax-m2.txt | 4.9 KB |
| devstral-2:123b-cloud | /tmp/review-devstral-123b.txt | 569 B |
| devstral-small-2:24b-cloud | /tmp/review-devstral-small.txt | 439 B |
| **General-purpose (8)** | | |
| sonnet | /tmp/review-sonnet.txt | 22.8 KB |
| opus | /tmp/review-opus.txt | 9.9 KB |
| haiku | /tmp/review-haiku.txt | 9.3 KB |
| qwen3.5:cloud | /tmp/review-qwen35.txt | 23.2 KB |
| deepseek-v4-pro:cloud | /tmp/review-deepseek.txt | 14.3 KB |
| glm-5.1:cloud | /tmp/review-glm.txt | 0 B (vuoto) |
| kimi-k2.6:cloud | /tmp/review-kimi.txt | 13.5 KB |
| gemma4:31b-cloud | /tmp/review-gemma.txt | 2.1 KB (90 righe) |

**Totale:** 13/14 modelli hanno fornito review utili (93%)

---

## Bug Critici Identificati (Consenso >= 3 modelli)

### 1. Blocking I/O in async path [CRITICAL]
**Modelli:** Kimi, DeepSeek, Qwen3.5  
**File:** `scripts/gdelt_ab_test.py:94-98`

```python
hist = ticker.history(...)  # Blocking HTTP call in async function
```

**Fix:**
```python
loop = asyncio.get_event_loop()
hist = await loop.run_in_executor(None, lambda: ticker.history(...))
```

### 2. CPU-intensive FinBERT in async path [CRITICAL]
**Modelli:** Kimi, DeepSeek  
**File:** `scripts/gdelt_ab_test.py:84`

```python
dated_scores = score_articles(articles, min_confidence=min_confidence)  # CPU-bound
```

**Fix:**
```python
dated_scores = await loop.run_in_executor(
    None, score_articles, articles, min_confidence
)
```

### 3. NaN/Inf price data non gestito [HIGH]
**Modelli:** Kimi, Qwen3.5, Sonnet  
**File:** `scripts/gdelt_ab_test.py:113`

```python
if closes[i] == 0:  # Non cattura NaN o Inf
    continue
```

**Fix:**
```python
if not np.isfinite(closes[i]) or closes[i] == 0:
    continue
```

### 4. json.dumps con np.float64 [HIGH]
**Modelli:** Kimi, Sonnet  
**File:** `scripts/gdelt_ab_test.py:176`

```python
output_str = json.dumps(result, indent=2)  # np.float64 non serializzabile
```

**Fix:**
```python
output_str = json.dumps(result, indent=2, default=float)
```

### 5. sanitize_text non solleva ValueError [MEDIUM]
**Modelli:** Opus, Haiku, DeepSeek  
**File:** `src/connectors/gdelt.py:135-137`

```python
try:
    clean_title = sanitize_text(title)
except ValueError:  # Dead code - sanitize_text non solleva mai
    continue
```

**Fix:** Rimuovere try/except

### 6. Singleton FinBERT non thread-safe [MEDIUM]
**Modelli:** Haiku, Qwen3.5, DeepSeek  
**File:** `src/analysis/finbert.py:14-31`

```python
_pipeline = None  # Race condition se chiamato in parallelo
```

**Fix:** Aggiungere threading.Lock

### 7. Path traversal in --output [MEDIUM]
**Modelli:** Kimi, Sonnet  
**File:** `scripts/gdelt_ab_test.py:177-179`

```python
with open(args.output, "w") as f:  # Path non validato
```

**Fix:**
```python
output_path = Path(args.output).resolve()
if not str(output_path).startswith(str(Path.cwd())):
    raise ValueError("Output must be inside working directory")
```

### 8. Symbol injection in GDELT query [MEDIUM]
**Modelli:** Kimi, DeepSeek  
**File:** `scripts/gdelt_ab_test.py:77`

```python
connector = GDELTConnector(query=f'"{symbol}"', asset_tags=[symbol])
```

**Fix:** Validare simbolo con regex `^[A-Z0-9.-]+$`

---

## Fix Applicati (questa sessione)

| Fix | File | Status |
|-----|------|--------|
| Exponential backoff per rate limiting | `src/connectors/gdelt.py` | ✅ Applicato |
| Session reuse (ClientSession unico) | `src/connectors/gdelt.py` | ✅ Applicato |
| Documentazione truncation FinBERT | `src/analysis/finbert.py` | ✅ Applicato |
| Commento auto_adjust deprecato | `scripts/gdelt_ab_test.py` | ✅ Applicato |

---

## Fix da Applicare (Prioritari)

### P0 - Critical (prima di production)

1. **Blocking I/O in async path** - `scripts/gdelt_ab_test.py`
2. **CPU-bound FinBERT senza executor** - `scripts/gdelt_ab_test.py`
3. **NaN/Inf price data** - `scripts/gdelt_ab_test.py`
4. **json.dumps np.float64** - `scripts/gdelt_ab_test.py`

### P1 - High (entro 2 giorni)

5. **Rimuovere dead code ValueError** - `src/connectors/gdelt.py`
6. **Thread-safe FinBERT singleton** - `src/analysis/finbert.py`
7. **Path traversal validation** - `scripts/gdelt_ab_test.py`
8. **Symbol validation** - `scripts/gdelt_ab_test.py`

### P2 - Medium (entro 1 settimana)

9. **Test per NaN price data** - `tests/analysis/test_gdelt_ab_cli.py`
10. **Test per yfinance failure** - `tests/analysis/test_gdelt_ab_cli.py`
11. **Test per FinBERT exception** - `tests/analysis/test_gdelt_ab_cli.py`
12. **Test per timezone alignment** - `tests/analysis/test_gdelt_ab_cli.py`

---

## Gap Architetturali (non implementati in Fase 1)

| Componente | Priorità | Note |
|------------|----------|------|
| Redis/PostgreSQL store | Bloccante | Script scrive solo su JSON |
| Kill-switch check | Bloccante | Nessuna verifica prima di processare |
| 3 fallback consecutivi → alert | Bloccante | Contatore non implementato |
| GET /api/signals/history | Importante | Serve per QC backtest |
| Connection pooling PostgreSQL | Importante | Per Celery workers |
| Semantic cache Redis | Nice-to-have | Ottimizzazione |

---

## Raccomandazione Finale

**Stato attuale:** Il codice è funzionale come script batch standalone per backtest offline.

**Per production:** Applicare tutti i fix P0 e P1 prima di integrare nel pipeline Celery/FastAPI.

**Test:** 312 test passati, ma mancano test per edge case critici (NaN, exception handling, path traversal).
