# Fase 1 — Istruzioni di Avvio per la Sessione Implementante

> **Per la sessione implementante:** Queste istruzioni sono state scritte dalla sessione di review e sono completamente auto-contenute. Leggi tutto prima di iniziare qualsiasi lavoro.

---

## 1. Contesto del Progetto

Sistema Python di trading algoritmico che usa LLM come motore **offline** di generazione segnali (paradigma "Alpha Miner"). I modelli LLM **non sono mai nel loop critico di esecuzione** — generano segnali pre-calcolati che QuantConnect Lean legge da Redis/PostgreSQL.

```
[News/GDELT] → [Celery SentimentWorker] → [Redis TTL 4h + PostgreSQL]
                                                      ↓
                        [QuantConnect Lean] legge segnale a ogni tick
```

**Stack:** Python 3.11+, FastAPI, Celery, Redis, PostgreSQL, Pydantic v2, FinBERT, pytest

**Fase 1 = observational only**: Performance Worker calcola IC e manda report Telegram. **Nessun auto-update dei pesi** (quello è Fase 2).

---

## 2. Dove Trovare Spec e Piani

| Documento | Percorso | Scopo |
|-----------|----------|-------|
| Spec design completa | `docs/superpowers/specs/2026-05-03-trading-system-design.md` | Requisiti, formule, soglie |
| Piano Tasks 1–14 | `docs/superpowers/plans/2026-05-03-fase1-foundation.md` | TDD step-by-step |
| Piano Tasks 15–22 | `docs/superpowers/plans/2026-05-03-fase1-part2.md` | TDD step-by-step |
| Config workers | `config/workers.yaml` | Soglie numeriche operative |
| Migration SQL | `migrations/001_initial.sql` | Schema DB (già pronto) |

---

## 3. Stato Attuale del Repository

### 3a. File GIÀ IMPLEMENTATI — NON RICREARE

I file seguenti esistono e sono stati rivisti e corretti in sessioni precedenti. **Non sovrascrivere, non reimplementare, non modificare a meno che un test fallisca e devi correggere un bug specifico.**

```
src/config.py                    ← Config Pydantic con tutti i field_validator
src/models/signals.py            ← SentimentResult, modello dati segnale
src/models/news.py               ← NewsItem, LLMSentimentOutput
src/text/sanitizer.py            ← sanitize_text(), sanitize_ticker() + BiDi + emoji
src/llm/client.py                ← LLMClient ABC + OpusClient + Qwen35Client + DeepseekClient
src/llm/ensemble.py              ← EnsembleAggregator + run_ensemble_query (fixed)
src/llm/budget.py                ← LLMBudgetTracker (NON era nel piano originale)
src/store/redis_store.py         ← RedisStore con OOM handling e fallback callback
src/store/pg_store.py            ← PostgreSQLStore con ThreadedConnectionPool
src/notifications/telegram.py   ← TelegramNotifier completo + format_performance_report
migrations/001_initial.sql       ← Schema SQL corretto (no duplicate column)
config/workers.yaml              ← Soglie operative (ic_window, psi, weight_alpha, ecc.)
pytest.ini                       ← asyncio_mode = auto
requirements.txt                 ← Dipendenze base
tests/test_llm_client.py
tests/test_pg_store.py
tests/test_redis_store.py
tests/test_budget_tracker.py
tests/test_security_fixes.py     ← 49 test passati (verificare prima di iniziare)
```

### 3b. File DA IMPLEMENTARE

Questi file esistono come `__init__.py` vuoti o non esistono:

```
src/connectors/base.py           ← NewsConnector ABC (Task 4)
src/connectors/deduplicator.py   ← Redis dedup hash-based (Task 4)
src/connectors/rss.py            ← RSSConnector (Task 5)
src/connectors/gdelt.py          ← GDELTConnector (Task 6)
src/models/performance.py        ← PerformanceReport, PostMortem models (Task 2 esteso)
src/llm/finbert.py               ← FinBERT fallback + entropic mapping (Task 11)
src/api/main.py                  ← FastAPI app (Task 14)
src/api/auth.py                  ← X-API-Key dependency (Task 14)
src/api/routes/signals.py        ← GET /api/signals/{symbol} (Task 14)
src/api/routes/admin.py          ← POST /api/admin/killswitch (Task 14)
src/api/routes/performance.py    ← GET /api/performance (Task 14)
src/workers/celery_app.py        ← Celery app + beat schedule (Task 13)
src/workers/sentiment.py         ← SentimentWorker Celery task (Task 13)
src/workers/performance.py       ← PerformanceWorker Celery task (Task 21)
src/performance/ic.py            ← Composite IC B4 + Newey-West (Task 16)
src/performance/weights.py       ← LOO ICIR + smoothing (Task 17)
src/performance/drift.py         ← PSI + CUSUM + circuit breakers (Task 18)
src/performance/postmortem.py    ← trigger logic + diagnosi (Task 19)
src/performance/threshold.py     ← bucket IC + suggester (Task 20)
quantconnect/signal_data.py      ← LLMSignalData PythonData feed (Task 15)
quantconnect/intraday_strategy.py← Intraday 1h strategy (Task 15)
pyproject.toml                   ← Project metadata (Task 1)
docker-compose.yml               ← Redis + Postgres per dev (Task 1)
.env.example                     ← Template variabili ambiente (Task 1)
tests/conftest.py                ← Fixtures Redis/Postgres mock (Task 1)
```

---

## 4. Ordine di Esecuzione

Esegui i task nell'ordine esatto. Ogni task è auto-contenuto nel piano.

### Prima verificazione (eseguire ora, prima di qualsiasi codice)

```bash
cd /home/stefano/Documents/Projects/trading
python -m pytest tests/ -v
```

**Atteso:** 49 passed. Se fallisce qualcosa, fermati e segnala alla sessione di review.

---

### Gruppo A — Scaffold e Connettori (Tasks 1, 4, 5, 6)

**Task 1** (`docs/superpowers/plans/2026-05-03-fase1-foundation.md` → Task 1)
- Crea `pyproject.toml`, `docker-compose.yml`, `.env.example`, `tests/conftest.py`
- Il piano mostra i contenuti esatti di ogni file

**Task 2** (modelli già esistono — da estendere)
- `src/models/performance.py` non esiste ancora
- Aggiungi `PerformanceReport` e `PostMortem` Pydantic model in quel file
- Segui il piano per i campi

**Task 4** (`docs/superpowers/plans/2026-05-03-fase1-foundation.md` → Task 4)
- Crea `src/connectors/base.py` (NewsConnector ABC)
- Crea `src/connectors/deduplicator.py` (Redis hash dedup)

**Task 5** → `src/connectors/rss.py`

**Task 6** → `src/connectors/gdelt.py` + opzionale `sec_edgar.py`

---

### Gruppo B — FinBERT e SentimentWorker (Tasks 11, 13)

**Task 11** (`docs/superpowers/plans/2026-05-03-fase1-foundation.md` → Task 11)
- Crea `src/llm/finbert.py`
- Implementa la **mappatura entropica** della confidence (formula nel piano e nella spec)
- FinBERT non viene chiamata dall'ensemble — viene chiamata dal SentimentWorker come fallback separato

**Task 13** (`docs/superpowers/plans/2026-05-03-fase1-foundation.md` → Task 13)
- Crea `src/workers/celery_app.py` e `src/workers/sentiment.py`
- **ATTENZIONE:** Il piano originale non integra `LLMBudgetTracker`. **Devi integrarlo.**
- Il SentimentWorker deve chiamare `await budget.check_budget()` PRIMA di chiamare il LLM ensemble
- Se `LLMBudgetExhaustedError` viene sollevata, chiama direttamente FinBERT

```python
# Pattern corretto per il SentimentWorker
from src.llm.budget import LLMBudgetTracker, LLMBudgetExhaustedError
from src.llm.finbert import FinBERTClient

async def process_news_item(item: NewsItem, clients, budget_tracker, redis_store):
    try:
        await budget_tracker.check_budget()
        outputs = await run_ensemble_query(prompt, clients, LLMSentimentOutput, item.symbol)
        result = aggregator.aggregate(outputs)
        if result is None:
            # Divergence → FinBERT fallback
            result = await finbert.analyze(item.body, item.symbol)
        else:
            await budget_tracker.record_spending(model_id, input_tok, output_tok)
    except LLMBudgetExhaustedError:
        result = await finbert.analyze(item.body, item.symbol)
    redis_store.write_sentiment(result)
```

---

### Gruppo C — FastAPI (Task 14)

**Task 14** (`docs/superpowers/plans/2026-05-03-fase1-foundation.md` → Task 14)
- Crea `src/api/main.py`, `src/api/auth.py`, `src/api/routes/`
- Auth usa `X-API-Key` header che viene confrontato con `config.ADMIN_API_KEY`
- Implementa le route: `GET /api/signals/{symbol}`, `GET /api/signals/history`, `POST /api/admin/killswitch`, `POST /api/admin/mode`, `GET /api/performance`, `GET /api/weights`

---

### Gruppo D — QuantConnect (Task 15)

**Task 15** (`docs/superpowers/plans/2026-05-03-fase1-part2.md` → Task 15)
- Crea `quantconnect/signal_data.py` e `quantconnect/intraday_strategy.py`
- **NON chiamare mai API LLM dentro `OnData()`** — leggi solo da Redis

---

### Gruppo E — Performance Worker (Tasks 16–22)

**Task 16** → `src/performance/ic.py` — Composite IC B4 + Newey-West HAC
**Task 17** → `src/performance/weights.py` — LOO ICIR (observational, Fase 1 non aggiorna pesi)
**Task 18** → `src/performance/drift.py` — PSI + CUSUM + circuit breakers
**Task 19** → `src/performance/postmortem.py` — trigger + diagnosi
**Task 20** → `src/performance/threshold.py` — bucket IC suggester
**Task 21** → `src/workers/performance.py` — Celery task + Telegram report
**Task 22** → test di integrazione

---

## 5. Pattern Critici da Seguire (Override del Piano)

Il piano originale contiene pattern vecchi che sono stati corretti nelle sessioni di review. **Usa SEMPRE i pattern qui sotto, non quelli nel piano.**

### 5a. LLM Clients — TUTTI in `src/llm/client.py`

Il piano originale prevede `opus.py`, `qwen35.py`, `deepseek.py` come file separati. **Non è più così.** Tutti e tre i client sono già in `src/llm/client.py`. Se devi aggiungere un nuovo client, aggiungilo in quel file.

```python
# CORRETTO — tutti i client in client.py
from src.llm.client import OpusClient, Qwen35Client, DeepseekClient
```

### 5b. asyncio.get_running_loop()

```python
# SBAGLIATO (deprecato Python 3.10+)
loop = asyncio.get_event_loop()

# CORRETTO
loop = asyncio.get_running_loop()
```

### 5c. SQL INTERVAL — parametrizzato

```python
# SBAGLIATO — SQL injection
cur.execute("SELECT ... WHERE generated_at >= now() - INTERVAL '%s days'" % days)

# CORRETTO — già in pg_store.py
cur.execute("SELECT ... WHERE generated_at >= now() - (%s || ' days')::interval", (str(days),))
```

### 5d. Connection pooling — usare `_get_pool()` da `pg_store`

```python
# CORRETTO — budget.py già fa così, imitalo
from src.store.pg_store import _get_pool
conn = _get_pool().getconn()
# ... usa conn ...
_get_pool().putconn(conn)
```

### 5e. Model ID validation — ALLOWED_MODEL_IDS

Qualunque codice che passa un `model_id` a subprocess o a CLI **deve** usare la frozenset già in `src/llm/client.py`:

```python
from src.llm.client import ALLOWED_MODEL_IDS
# oppure usa self._validate_model_id(model_id) — già nel metodo base
```

### 5f. asyncio.as_completed — usa dizionario, non indice

```python
# SBAGLIATO (bug: ordine completion ≠ ordine submission)
for i, coro in enumerate(asyncio.as_completed(tasks)):
    model_id = clients[i].model_id  # SBAGLIATO

# CORRETTO (già in ensemble.py — imitalo)
task_to_model_id = {task: client.model_id for task, client in zip(tasks, clients)}
for task in asyncio.as_completed(tasks):
    model_id = task_to_model_id[task]
```

### 5g. Redis OOM — try/except in tutte le write

```python
# CORRETTO — pattern già in redis_store.py
try:
    self._r.setex(key, ttl, data)
except Exception as e:
    if "OOM" in str(e) or "out of memory" in str(e).lower():
        print(f"Redis OOM - dropping write for {key}")
    else:
        raise
```

---

## 6. Formule e Soglie Operative (dal piano/spec)

Queste formule devono essere implementate **esattamente così** — sono la fonte di verità.

### Signal Intensity
```
signal_intensity = 0.60 * confidence + 0.40 * sentiment_polarity
```

### Composite IC (B4)
```
IC_composite = 0.5 × Spearman(score, forward_return)
             + 0.3 × weighted_hit_rate
             + 0.2 × (1 − Brier_score)
```

### Entropic Confidence Mapping (FinBERT)
```python
def map_finbert_confidence(softmax_probs: list[float]) -> float:
    """Convert FinBERT softmax to confidence using normalized entropy."""
    import numpy as np
    probs = np.array(softmax_probs)
    entropy = -np.sum(probs * np.log(probs + 1e-9))
    max_entropy = np.log(len(probs))  # uniform distribution entropy
    confidence = 1.0 - (entropy / max_entropy)
    return float(np.clip(confidence, 0.0, 1.0))
```

### PSI (Population Stability Index)
```python
def compute_psi(baseline: np.ndarray, current: np.ndarray, bins: int = 10) -> float:
    lo = min(baseline.min(), current.min())
    hi = max(baseline.max(), current.max())
    if lo == hi:
        return 0.0
    edges = np.linspace(lo, hi, bins + 1)
    exp = np.histogram(baseline, edges)[0] / len(baseline) + 1e-9
    act = np.histogram(current,  edges)[0] / len(current)  + 1e-9
    return float(np.sum((exp - act) * np.log(exp / act)))

# Soglie:
# YELLOW = PSI_90gg > 0.10
# RED    = PSI_90gg > 0.25 AND PSI_12m > 0.10
```

### LOO ICIR (Leave-One-Out, Fase 1 = solo calcolo, non aggiorna pesi)
```
Per ogni modello m:
    IC_LOO(m) = IC calcolato usando l'ensemble che esclude m
    ICIR_LOO(m) = mean(IC_LOO(m)) / std(IC_LOO(m)) [Newey-West HAC]

Weight smoothing (Fase 2):
    new_weight(m) = 0.75 * old_weight(m) + 0.25 * softmax(ICIR_LOO)
    Bounds: floor 10%, cap 70%, max delta 10% per update
```

### Post-Mortem Trigger
```python
def should_trigger_postmortem(loss_pct: float, score: float, ensemble_std: float) -> bool:
    return loss_pct >= 0.03 or (loss_pct >= 0.02 and (abs(score) >= 0.5 or ensemble_std >= 0.3))
```

### Circuit Breakers (hard — da verificare in PerformanceWorker)
```python
HARD_BREAKERS = {
    "vix_spike":       lambda ctx: ctx.vix > 40 or ctx.vix_1d_change > 0.30,
    "system_drawdown": lambda ctx: ctx.portfolio_drawdown > 0.05,
    "ic_negative_run": lambda ctx: ctx.consecutive_negative_ic_days >= 5,
}
SOFT_WARNINGS = {
    "earnings_concentration": lambda ctx: ctx.portfolio_earnings_pct > 0.50,
    "cross_asset_corr":       lambda ctx: ctx.cross_asset_correlation > 0.90,
}
```

---

## 7. Disciplina TDD (Non Opzionale)

Per ogni file da implementare:

1. **Scrivi il test che fallisce** — `pytest tests/path/test_xxx.py::test_name -v` → deve mostrare FAIL
2. **Esegui per verificare che fallisca** — se passa subito, il test non sta testando nulla
3. **Implementa il codice minimo** per far passare il test
4. **Esegui tutti i test esistenti** — `python -m pytest tests/ -v` — nessuna regressione
5. **Commit** — un commit per task

```bash
# Dopo ogni task:
python -m pytest tests/ -v
# Atteso: tutti passano (numero crescente)
```

---

## 8. Convenzioni di Commit

```bash
git add <file_specifici>  # MAI git add -A
git commit -m "feat: <descrizione breve>

Co-Authored-By: Claude <noreply@anthropic.com>"
```

Esempi:
- `feat: add NewsConnector ABC and Redis deduplicator`
- `feat: implement FinBERT entropic confidence mapping`
- `feat: add SentimentWorker with budget integration`
- `feat: implement composite IC B4 with Newey-West`
- `fix: parameterize SQL INTERVAL to prevent injection`

---

## 9. Problemi Aperti (Non Bloccanti per Fase 1)

Sono stati identificati nelle sessioni di review. **Non bloccare l'implementazione per questi** — completali se hai tempo, altrimenti segnalali a fine Fase 1.

| # | Problema | File | Priorità |
|---|----------|------|----------|
| 1 | `print()` invece di `logging` module | Tutti i file | P2 |
| 2 | Integration test con Redis/Postgres reali | `tests/integration/` | P1 |
| 3 | Type hints completi per tutti i metodi `__exit__` | vari | P2 |
| 4 | `DeepseekClient` manca di test dedicati | `tests/test_llm_client.py` | P1 |

---

## 10. Protocollo di Handoff per Review

Dopo ogni **Gruppo** completato (A, B, C, D, E), la sessione implementante deve:

1. Eseguire `python -m pytest tests/ -v` e includere l'output nella comunicazione di handoff
2. Specificare esattamente quali file sono stati creati/modificati
3. Segnalare eventuali deviazioni dal piano con la motivazione

La sessione di review esaminerà:
- Correttezza dei test (se testano davvero il comportamento, non l'implementazione)
- Presenza dei pattern critici di sicurezza (ALLOWED_MODEL_IDS, OOM handling, parameterized SQL)
- Rispetto delle formule operative (IC, PSI, entropic mapping)
- Assenza di regressioni nei 49 test esistenti

---

## 11. Variabili d'Ambiente Richieste

Il sistema richiede queste variabili per funzionare (config.py le valida allo startup):

```bash
# Obbligatorie
ADMIN_API_KEY=<32+ caratteri, per FastAPI auth>
DATABASE_URL=postgresql://user:pass@localhost:5432/llm_trading
REDIS_URL=redis://localhost:6379/0

# Opzionali
CLAUDE_CLI_PATH=claude          # default: 'claude' in PATH
LLM_DAILY_BUDGET_USD=50.0
TELEGRAM_BOT_TOKEN=<da BotFather>
TELEGRAM_CHAT_ID=<id canale>
```

Per i test, usa `.env.test` o mock le dipendenze esterne.

**Attenzione:** `config.py` **lancia eccezione allo startup** se `ADMIN_API_KEY` è vuoto o < 32 caratteri e se `DATABASE_URL` non inizia con `postgresql://`. Nei test che non usano il DB, usa:

```python
import os
os.environ["ADMIN_API_KEY"] = "a" * 32
os.environ["DATABASE_URL"] = "postgresql://localhost:5432/test"
```

oppure mokerai `src.config.config` direttamente.

---

*Documento generato dalla sessione di review il 2026-05-03. Aggiorna questo file se lo stato del repository cambia significativamente durante l'implementazione.*
