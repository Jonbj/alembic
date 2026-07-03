# Functional Review Remediation — Roadmap Operativa Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implementare lo Sprint 1 ("smetti di perdere, inizia a misurare") della review funzionale `docs/FUNCTIONAL_REVIEW_2026-07-03.md`: spegnere le fonti net-negative, filtrare per event-time, dedup cross-source, unificare i parametri di rischio, enforcement conservativo del resolver, soglie reali nei gate di backtest, e lanciare il backtest S7 (gate ALPHA-A5).

**Architecture:** Nessun nuovo sottosistema. Solo modifiche chirurgiche a componenti esistenti: beat schedule Celery, worker di ingestione/sentiment, store PG/Redis, config loader, gate di backtest. Ogni task è indipendente e committabile da solo. L'ordine dei task è per priorità ma i task 1–8 non hanno dipendenze reciproche (il 6 dipende dal 5 solo per il numero di migration).

**Tech Stack:** Python 3.11, Celery + Redis, PostgreSQL 16 (psycopg2), Pydantic v2, pytest, Alpaca SDK, Finnhub API.

**Esecutore:** una singola sessione Claude (modello Sonnet). Esegui i task in ordine numerico (1→9), uno alla volta, un commit per task come indicato negli step. Non parallelizzare, non delegare a subagent. Spunta le checkbox (`- [x]`) direttamente in questo file man mano che completi gli step.

---

## Regole di ingaggio (leggere PRIMA di iniziare)

1. **Vincolo non-negoziabile (CLAUDE.md):** nessuna chiamata LLM/API sincrona nel path di esecuzione. Nessuno di questi task tocca il hot path — se ti sembra di doverlo fare, fermati e chiedi.
2. **Non toccare:** `src/workers/portfolio_scheduler.py` oltre a quanto specificato nel Task 4; nessuna modifica a `src/strategies/`, `src/portfolio/orchestrator.py`, `src/api/`.
3. **Decisioni riservate al PO (NON deciderle tu):** universo small/mid-cap per S7; vendor dati (FMP vs multi-vendor); budget annotazione QX-01; qualunque promozione di strategia o cambio di `allocation_pct`.
4. **Test:** la suite completa (`pytest`) deve passare dopo OGNI task. Il progetto ha ~2400 test. Esegui `pytest -q` prima del primo task per registrare la baseline (numero di passed/failed): se ci sono failure pre-esistenti, annotale e non peggiorarle.
5. **Convenzione commit:** conventional commits (`fix:`, `feat:`, `ops:`, `docs:`, `test:`), un commit per task come indicato negli step.
6. **Dove girano i test:** in locale con `pytest`. I test non richiedono Docker (Redis/PG sono mockati nei test esistenti — segui i pattern in `tests/workers/` e `tests/store/`).
7. Se un anchor di riga citato nel piano non corrisponde più (il file è cambiato), cerca il simbolo per nome, non per numero di riga.

---

## Task 1: FIX-01/02 — Disattivare MarketAux e RSS dal beat schedule

Le due fonti sono empiricamente net-negative (MarketAux: 0/20 winner, −$14.11/trade; RSS: 0 news in 17 giorni). Vanno rimosse dal beat e i task env-gated, seguendo ESATTAMENTE il precedente già nel codebase per Finnhub (`src/workers/ingestion.py:394`) e SEC EDGAR (`src/workers/ingestion.py:561`).

**Files:**
- Modify: `src/workers/celery_app.py` (beat entries `run-marketaux-ingestion` ~riga 140, `run-rss-ingestion` ~riga 167)
- Modify: `src/workers/ingestion.py` (`run_marketaux_ingestion_worker` ~riga 211, `run_rss_ingestion_worker` ~riga 676)
- Test: `tests/workers/test_ingestion_source_gating.py` (nuovo)

- [x] **Step 1: Scrivere i test che falliscono**

Crea `tests/workers/test_ingestion_source_gating.py`:

```python
"""FIX-01/FIX-02 (docs/FUNCTIONAL_REVIEW_2026-07-03.md): MarketAux and RSS are
net-negative sources and must be out of the beat schedule, with their Celery
tasks env-gated like Finnhub/SEC EDGAR."""

import os
from unittest.mock import patch


def test_marketaux_not_in_beat_schedule():
    from src.workers.celery_app import app
    assert "run-marketaux-ingestion" not in app.conf.beat_schedule


def test_rss_not_in_beat_schedule():
    from src.workers.celery_app import app
    assert "run-rss-ingestion" not in app.conf.beat_schedule


def test_marketaux_task_skips_when_disabled():
    from src.workers.ingestion import run_marketaux_ingestion_worker
    with patch.dict(os.environ, {"MARKETAUX_INGESTION_ENABLED": "0"}):
        result = run_marketaux_ingestion_worker()
    assert result.get("skipped") is True


def test_rss_task_skips_when_disabled():
    from src.workers.ingestion import run_rss_ingestion_worker
    with patch.dict(os.environ, {"RSS_INGESTION_ENABLED": "0"}):
        result = run_rss_ingestion_worker()
    assert result.get("skipped") is True


def test_marketaux_task_skips_by_default():
    """Default (env var absent) must be OFF — fail-closed."""
    env = {k: v for k, v in os.environ.items() if k != "MARKETAUX_INGESTION_ENABLED"}
    with patch.dict(os.environ, env, clear=True):
        from src.workers.ingestion import run_marketaux_ingestion_worker
        result = run_marketaux_ingestion_worker()
    assert result.get("skipped") is True
```

- [x] **Step 2: Eseguire i test per verificarne il fallimento**

Run: `pytest tests/workers/test_ingestion_source_gating.py -v`
Expected: FAIL (le entry sono ancora nel beat; i task non hanno il gate).

- [x] **Step 3: Rimuovere le entry dal beat schedule**

In `src/workers/celery_app.py`, sostituisci l'intero blocco `"run-marketaux-ingestion": {...},` (dal commento `# MarketAux ingestion every 15 min...` incluso) con:

```python
    # MarketAux ingestion: DISABLED 2026-07-03 (FIX-01, FUNCTIONAL_REVIEW_2026-07-03).
    # 17-day paper evidence: 0/20 winners, -$14.11/trade, -$282 total, p50 latency 7.6d,
    # 100 req/day cap → ~4 low-quality news/day. Task kept but not scheduled, gated
    # behind MARKETAUX_INGESTION_ENABLED. Re-enable only with per-source IC > 0 evidence.
```

e l'intero blocco `"run-rss-ingestion": {...},` (dal commento `# RSS news ingestion...` incluso) con:

```python
    # RSS (Reuters/CNBC) ingestion: DISABLED 2026-07-03 (FIX-02, FUNCTIONAL_REVIEW_2026-07-03).
    # 0 news_log rows in 17 days → dead feeds or no ticker match. Task kept but not
    # scheduled, gated behind RSS_INGESTION_ENABLED. Revive only with official IR feeds.
```

- [x] **Step 4: Aggiungere il gate env ai due task**

In `src/workers/ingestion.py`, come PRIMA istruzione del body di `run_marketaux_ingestion_worker()` (dopo la docstring), aggiungi:

```python
    if os.environ.get("MARKETAUX_INGESTION_ENABLED", "0") == "0":
        return {"skipped": True, "reason": "MARKETAUX_INGESTION_ENABLED=0 (FIX-01: net-negative source)"}
```

e come prima istruzione del body di `run_rss_ingestion_worker()` (dopo la docstring):

```python
    if os.environ.get("RSS_INGESTION_ENABLED", "0") == "0":
        return {"skipped": True, "reason": "RSS_INGESTION_ENABLED=0 (FIX-02: dead feeds, 0 news in 17d)"}
```

`os` è già importato in `ingestion.py` (usato dal gate Finnhub alla riga ~394).

- [x] **Step 5: Eseguire i test per verificarne il pass**

Run: `pytest tests/workers/test_ingestion_source_gating.py -v`
Expected: 5 PASS.

- [x] **Step 6: Verificare che i test esistenti non si rompano**

Run: `pytest tests/workers/ -q`
Expected: tutti PASS. Se un test esistente asseriva la presenza delle beat entry (cerca con `grep -rn "run-marketaux-ingestion\|run-rss-ingestion" tests/`), aggiornalo per asserire l'assenza, citando FIX-01/02.

- [x] **Step 7: Commit**

```bash
git add src/workers/celery_app.py src/workers/ingestion.py tests/workers/test_ingestion_source_gating.py
git commit -m "ops(ingestion): disable MarketAux+RSS sources (FIX-01/02) — net-negative, env-gated like Finnhub"
```

---

## Task 2: B20 — `reconcile-fills-evening` punta al task sbagliato

L'entry beat `reconcile-fills-evening` (`src/workers/celery_app.py:88-91`) esegue `src.workers.performance.run_daily_report` invece della riconciliazione fill. La funzione corretta esiste già: `run_reconcile_fills_intraday` (`src/workers/performance.py:659`) — riconcilia i trade con `exit_price` NULL, ed è idempotente, quindi va bene anche come passata serale.

**Files:**
- Modify: `src/workers/celery_app.py:88-91`
- Test: `tests/workers/test_ingestion_source_gating.py` (aggiungi il test qui — è lo stesso dominio "beat schedule corretto")

- [x] **Step 1: Scrivere il test che fallisce**

Aggiungi a `tests/workers/test_ingestion_source_gating.py`:

```python
def test_reconcile_fills_evening_points_to_reconcile_task():
    """B20: the evening entry must run fill reconciliation, not the daily report."""
    from src.workers.celery_app import app
    entry = app.conf.beat_schedule["reconcile-fills-evening"]
    assert entry["task"] == "src.workers.performance.run_reconcile_fills_intraday"
```

- [x] **Step 2: Eseguire il test per verificarne il fallimento**

Run: `pytest tests/workers/test_ingestion_source_gating.py::test_reconcile_fills_evening_points_to_reconcile_task -v`
Expected: FAIL con `assert 'src.workers.performance.run_daily_report' == 'src.workers.performance.run_reconcile_fills_intraday'`.

- [x] **Step 3: Correggere l'entry beat**

In `src/workers/celery_app.py`, nell'entry `"reconcile-fills-evening"`, sostituisci:

```python
        "task": "src.workers.performance.run_daily_report",
```

con:

```python
        "task": "src.workers.performance.run_reconcile_fills_intraday",
```

- [x] **Step 4: Eseguire i test**

Run: `pytest tests/workers/test_ingestion_source_gating.py -v`
Expected: tutti PASS.

- [x] **Step 5: Commit**

```bash
git add src/workers/celery_app.py tests/workers/test_ingestion_source_gating.py
git commit -m "fix(ops): reconcile-fills-evening beat entry pointed to run_daily_report (B20)"
```

---

## Task 3: EN-03 — Dedup content-hash cross-source

`Deduplicator.is_duplicate()` (content hash) esiste ma non è mai chiamato: lo stesso articolo da 3 fonti = 3 inferenze LLM. Il dedup per contenuto puro romperebbe però il fan-out multi-ticker (stesso testo, ticker diversi → item legittimi). Soluzione: nuovo metodo keyed su **content-hash + ticker**, wired in TUTTI i punti di ingestione accanto a `is_duplicate_by_id`.

**Files:**
- Modify: `src/connectors/deduplicator.py`
- Modify: `src/workers/ingestion.py` (7 call-site di `is_duplicate_by_id`: righe ~146, ~200, ~288, ~373, ~479, ~543, ~667)
- Test: `tests/connectors/test_deduplicator_content_symbol.py` (nuovo)

- [x] **Step 1: Scrivere i test che falliscono**

Crea `tests/connectors/test_deduplicator_content_symbol.py`:

```python
"""EN-03: cross-source content dedup. Same article text for the same ticker
from two different sources must be deduplicated; same text for two different
tickers must NOT (multi-ticker fan-out is legitimate)."""

from unittest.mock import MagicMock

from src.connectors.deduplicator import Deduplicator
from src.models.news import NewsItem


def _item(item_id: str, ticker: str, source: str) -> NewsItem:
    return NewsItem(
        id=item_id,
        title="Apple beats Q3 estimates",
        body="Apple Inc reported quarterly revenue above expectations...",
        source=source,
        asset_tags=[ticker],
    )


def _redis_first_insert_then_dup():
    """SET NX returns True on first insert, None when the key already exists."""
    r = MagicMock()
    seen: set[str] = set()

    def fake_set(key, value, ex=None, nx=None):
        if key in seen:
            return None
        seen.add(key)
        return True

    r.set.side_effect = fake_set
    return r


def test_same_content_same_ticker_cross_source_is_duplicate():
    dedup = Deduplicator(_redis_first_insert_then_dup())
    a = _item("https://benzinga.com/x:AAPL", "AAPL", "alpaca")
    b = _item("https://reuters.com/y:AAPL", "AAPL", "gdelt_gkg")  # id diverso, testo identico
    assert dedup.is_duplicate_content_symbol(a) is False
    assert dedup.is_duplicate_content_symbol(b) is True


def test_same_content_different_ticker_is_not_duplicate():
    dedup = Deduplicator(_redis_first_insert_then_dup())
    a = _item("https://x.com/1:AAPL", "AAPL", "alpaca")
    b = _item("https://x.com/1:MSFT", "MSFT", "alpaca")
    assert dedup.is_duplicate_content_symbol(a) is False
    assert dedup.is_duplicate_content_symbol(b) is False


def test_item_without_asset_tags_is_never_content_duplicate():
    dedup = Deduplicator(_redis_first_insert_then_dup())
    a = NewsItem(id="u:1", title="t", body="b", asset_tags=[])
    assert dedup.is_duplicate_content_symbol(a) is False
```

- [x] **Step 2: Eseguire i test per verificarne il fallimento**

Run: `pytest tests/connectors/test_deduplicator_content_symbol.py -v`
Expected: FAIL con `AttributeError: 'Deduplicator' object has no attribute 'is_duplicate_content_symbol'`.

- [x] **Step 3: Implementare il metodo**

In `src/connectors/deduplicator.py`, aggiungi alla classe `Deduplicator` (dopo `is_duplicate_by_id`):

```python
    def is_duplicate_content_symbol(self, item: NewsItem) -> bool:
        """Cross-source dedup: content hash + primary ticker (EN-03).

        The same article fetched from two sources has different ids
        (`is_duplicate_by_id` misses it) but identical normalised text.
        Keying on content hash ALONE would break multi-ticker fan-out
        (same text, different ticker → legitimate distinct items), so the
        key includes the item's primary ticker.

        Items without asset_tags are never treated as content duplicates
        (nothing downstream to save; discarding here would hide data).
        """
        if not item.asset_tags:
            return False
        key = f"dedup:content:{compute_dedup_hash(item)}:{item.asset_tags[0]}"
        result = self._r.set(key, 1, ex=_DEDUP_TTL_SECONDS, nx=True)
        return result is None
```

- [x] **Step 4: Eseguire i test per verificarne il pass**

Run: `pytest tests/connectors/test_deduplicator_content_symbol.py -v`
Expected: 3 PASS.

- [x] **Step 5: Wire nel worker di ingestione**

In `src/workers/ingestion.py`, per OGNUNO dei 7 call-site di `is_duplicate_by_id` (righe ~146, ~200, ~288, ~373, ~479, ~543, ~667), il pattern attuale è:

```python
            if deduplicator.is_duplicate_by_id(per_ticker):
                ...contatore duplicati...
                continue
```

Modificalo in (mantieni il nome di variabile locale reale di ciascun sito — `per_ticker` o `item`):

```python
            if deduplicator.is_duplicate_by_id(per_ticker) or deduplicator.is_duplicate_content_symbol(per_ticker):
                ...contatore duplicati...
                continue
```

NON riordinare i due check: `is_duplicate_by_id` deve restare primo (short-circuit: il check by-id è quello storicamente testato). Nota: entrambi i metodi hanno side-effect SET NX — va bene, l'item che passa registra entrambe le chiavi.

- [x] **Step 6: Eseguire tutti i test di ingestione e connettori**

Run: `pytest tests/workers/ tests/connectors/ -q`
Expected: tutti PASS. Se un test di ingestione esistente mocka `Deduplicator` con `spec=` e fallisce sull'attributo nuovo, aggiungi `is_duplicate_content_symbol` al mock con `return_value=False`.

- [x] **Step 7: Commit**

```bash
git add src/connectors/deduplicator.py src/workers/ingestion.py tests/connectors/test_deduplicator_content_symbol.py
git commit -m "feat(ingestion): cross-source content-hash dedup keyed on content+ticker (EN-03)"
```

---

## Task 4: B13 — Drawdown cap: eliminare l'hardcode 10% nel portfolio scheduler

`config/trading.yaml` dice `risk.portfolio_drawdown: 0.05`, ma il path attivo (`src/workers/portfolio_scheduler.py:26`) hardcoda `_MAX_DRAWDOWN_PCT = 0.10`. Il valore di produzione scelto è **quello di config (5%)**. Il loader `_load_risk_config()` (riga ~513) già legge `trading.yaml` con default fail-safe: va esteso con la chiave mancante.

**Files:**
- Modify: `src/workers/portfolio_scheduler.py` (righe ~26, ~513-533, ~1048-1056)
- Test: `tests/workers/test_risk_config_unification.py` (nuovo)
- Docs: `docs/strategies.md`, `docs/operations.md`, `README.md` (allineamento valori)

- [x] **Step 1: Scrivere i test che falliscono**

Crea `tests/workers/test_risk_config_unification.py`:

```python
"""B13 (FUNCTIONAL_REVIEW_2026-07-03 §6.1): the drawdown cap must come from
config/trading.yaml (risk.portfolio_drawdown), not from a hardcoded constant."""

from unittest.mock import mock_open, patch


def test_load_risk_config_includes_portfolio_drawdown_from_yaml():
    from src.workers import portfolio_scheduler as ps
    yaml_text = (
        "risk:\n"
        "  portfolio_drawdown: 0.05\n"
        "  max_portfolio_exposure: 0.50\n"
        "  max_position_pct: 0.10\n"
        "  stop_loss: 0.02\n"
    )
    with patch("builtins.open", mock_open(read_data=yaml_text)):
        cfg = ps._load_risk_config()
    assert cfg["portfolio_drawdown"] == 0.05


def test_load_risk_config_portfolio_drawdown_failsafe_default():
    """On unreadable yaml the default must be the CONFIG value (0.05), not 0.10."""
    from src.workers import portfolio_scheduler as ps
    with patch("builtins.open", side_effect=OSError("boom")):
        cfg = ps._load_risk_config()
    assert cfg["portfolio_drawdown"] == 0.05


def test_no_hardcoded_drawdown_constant():
    """The 0.10 module-level constant must be gone."""
    from src.workers import portfolio_scheduler as ps
    assert not hasattr(ps, "_MAX_DRAWDOWN_PCT")
```

- [x] **Step 2: Eseguire i test per verificarne il fallimento**

Run: `pytest tests/workers/test_risk_config_unification.py -v`
Expected: FAIL (chiave assente, costante presente).

- [x] **Step 3: Estendere `_load_risk_config` e rimuovere la costante**

In `src/workers/portfolio_scheduler.py`:

(a) Elimina la riga ~26:

```python
_MAX_DRAWDOWN_PCT = 0.10  # portfolio-level circuit breaker; mirrors execution.py constant
```

(b) In `_load_risk_config()` estendi `defaults` e il dict di ritorno:

```python
    defaults: dict[str, float] = {
        "max_portfolio_exposure": 0.50,
        "max_single_asset_pct": 0.10,
        "stop_loss": 0.02,
        "portfolio_drawdown": 0.05,  # B13: single source of truth = trading.yaml
    }
```

e nel `return` del ramo try aggiungi:

```python
            "portfolio_drawdown": float(risk.get("portfolio_drawdown", defaults["portfolio_drawdown"])),
```

(c) Al sito d'uso (righe ~1048-1056), sostituisci ogni occorrenza di `_MAX_DRAWDOWN_PCT` con una variabile locale caricata dal config. Il blocco attuale:

```python
            if drawdown >= _MAX_DRAWDOWN_PCT:
                _dd_reason = f"portfolio drawdown {drawdown:.1%} >= {_MAX_DRAWDOWN_PCT:.0%} cap"
```

diventa:

```python
            _dd_cap = _load_risk_config()["portfolio_drawdown"]
            if drawdown >= _dd_cap:
                _dd_reason = f"portfolio drawdown {drawdown:.1%} >= {_dd_cap:.0%} cap"
```

Aggiorna allo stesso modo la riga ~1056 (messaggio Telegram) usando `_dd_cap`. Verifica con `grep -n "_MAX_DRAWDOWN_PCT" src/` che non restino occorrenze.

- [x] **Step 4: Eseguire i test**

Run: `pytest tests/workers/test_risk_config_unification.py tests/workers/ -q`
Expected: tutti PASS. Se test esistenti referenziano `_MAX_DRAWDOWN_PCT`, aggiornali a usare `_load_risk_config()["portfolio_drawdown"]`.

- [x] **Step 5: Allineare la documentazione ai valori di config**

Tre correzioni testuali (usa grep per trovare le occorrenze esatte):

1. `docs/strategies.md`, tabella "Constraint Enforcement": riga `| Max portfolio exposure | 95% NAV |` → `| Max portfolio exposure | 50% NAV |`.
2. `docs/strategies.md`, tabella "Key Parameters (S4Config)": riga `stop_loss_pct | 0.05` → `stop_loss_pct | 0.02 (da config/trading.yaml risk.stop_loss)`.
3. `README.md` e `docs/operations.md`: ogni occorrenza di "daily loss cap 10%" / "drawdown cap 10%" → "5% (`risk.portfolio_drawdown` in `config/trading.yaml`)". Trova con: `grep -rn "10%" README.md docs/operations.md | grep -i "drawdown\|loss cap"`.

- [x] **Step 6: Commit**

```bash
git add src/workers/portfolio_scheduler.py tests/workers/test_risk_config_unification.py docs/strategies.md docs/operations.md README.md
git commit -m "fix(risk): drawdown cap from trading.yaml, remove 10% hardcode; align docs to config values (B13/B14/B18)"
```

---

## Task 5: FIX-03 (parte 1) — Propagare `published_at` nel segnale

Oggi la freshness decisionale usa `generated_at` (quando l'LLM ha processato), non quando la notizia è uscita. Prima parte: portare `item.timestamp` (pubblicazione, già presente su `NewsItem`) dentro `sentiment_signals` e nel modello `SentimentResult`.

**Files:**
- Create: `migrations/032_sentiment_signals_published_at.sql`
- Modify: `src/models/signals.py` (classe `SentimentResult`)
- Modify: `src/store/pg_store.py` (`_INSERT_SIGNAL` + `write_signal`, righe ~146-170)
- Modify: `src/workers/sentiment.py` (`run_inference` / costruzione `SentimentResult`)
- Test: `tests/models/test_sentiment_result_published_at.py` (nuovo)

- [x] **Step 1: Creare la migration**

Crea `migrations/032_sentiment_signals_published_at.sql`:

```sql
-- FIX-03 (FUNCTIONAL_REVIEW_2026-07-03): event-time freshness.
-- published_at = when the news was published (NewsItem.timestamp), as opposed to
-- generated_at = when the LLM processed it. NULL for legacy rows and non-news signals.
ALTER TABLE sentiment_signals
    ADD COLUMN IF NOT EXISTS published_at TIMESTAMPTZ;

COMMENT ON COLUMN sentiment_signals.published_at IS
    'News publication time (event-time). NULL = unknown/legacy. Used by fetch_signals_for_cycle freshness gate (FIX-03).';
```

Guarda `migrations/031_news_resolved_entities.sql` per la convenzione locale (header, IF NOT EXISTS) e adeguati se differisce.

- [x] **Step 2: Scrivere i test che falliscono**

Crea `tests/models/test_sentiment_result_published_at.py`:

```python
"""FIX-03 part 1: SentimentResult carries the news publication time."""

import json
from datetime import datetime, timezone

from src.models.signals import SentimentResult


def _result(**kw) -> SentimentResult:
    base = dict(
        symbol="AAPL", score=0.5, confidence=0.8, reasoning="r",
        model_id="kimi-k2.6:cloud",
    )
    base.update(kw)
    return SentimentResult(**base)


def test_published_at_defaults_to_none():
    assert _result().published_at is None


def test_published_at_roundtrips_in_json():
    ts = datetime(2026, 7, 3, 14, 30, tzinfo=timezone.utc)
    payload = json.loads(_result(published_at=ts).model_dump_json())
    assert payload["published_at"] == ts.isoformat()


def test_published_at_none_serialises_as_null():
    payload = json.loads(_result().model_dump_json())
    assert payload["published_at"] is None
```

- [x] **Step 3: Eseguire i test per verificarne il fallimento**

Run: `pytest tests/models/test_sentiment_result_published_at.py -v`
Expected: FAIL (`published_at` non esiste sul modello).

- [x] **Step 4: Estendere `SentimentResult`**

In `src/models/signals.py`, dentro `SentimentResult`, dopo `generated_at`:

```python
    # FIX-03: news publication time (event-time). None = unknown (legacy/non-news).
    published_at: datetime | None = None
```

e nel metodo `model_dump_json()` aggiungi al dict serializzato:

```python
                "published_at": self.published_at.isoformat() if self.published_at else None,
```

- [x] **Step 5: Eseguire i test per verificarne il pass**

Run: `pytest tests/models/test_sentiment_result_published_at.py -v`
Expected: 3 PASS.

- [x] **Step 6: Persistere la colonna in `write_signal`**

In `src/store/pg_store.py`: individua la costante `_INSERT_SIGNAL` (la query INSERT usata da `write_signal`, riga ~146). Aggiungi `published_at` alla lista colonne e un `%s` alla lista VALUES, mantenendo INVARIATO tutto il resto (incluso qualunque `ON CONFLICT ... RETURNING id`). Poi in `write_signal` aggiungi il parametro nella tupla, dopo `result.generated_at`:

```python
                        result.generated_at,
                        result.published_at,
```

- [x] **Step 7: Propagare dal worker**

In `src/workers/sentiment.py`, i `SentimentResult` sono costruiti dentro `run_inference` (sia il ramo ensemble sia i rami FinBERT fallback — cerca `SentimentResult(` nel file, sono ~3 occorrenze). A ogni costruzione aggiungi:

```python
            published_at=item.timestamp,
```

(`item` è il `NewsItem` in scope in tutte le occorrenze; se in un ramo non lo è, passa il timestamp come argomento della funzione helper seguendo la firma esistente).

- [x] **Step 8: Eseguire i test di store e worker**

Run: `pytest tests/store/ tests/workers/ tests/models/ -q`
Expected: tutti PASS. I test esistenti su `write_signal` mockano il cursor: se asseriscono il numero esatto di parametri della tupla, aggiornali (+1 parametro).

- [x] **Step 9: Applicare la migration all'ambiente locale/dev (se il DB è raggiungibile)**

Run: `docker compose exec -T postgres psql -U alembic -d alembic -f /dev/stdin < migrations/032_sentiment_signals_published_at.sql`
Expected: `ALTER TABLE`. Se il container non è attivo, salta lo step e segnala nel commit message che la migration va applicata al deploy (convenzione del progetto: le migration si applicano manualmente, verifica in `docs/operations.md`).

- [x] **Step 10: Commit**

```bash
git add migrations/032_sentiment_signals_published_at.sql src/models/signals.py src/store/pg_store.py src/workers/sentiment.py tests/models/test_sentiment_result_published_at.py
git commit -m "feat(sentiment): propagate news published_at into SentimentResult and sentiment_signals (FIX-03 part 1)"
```

---

## Task 6: FIX-03 (parte 2) — Gate di freshness event-time nel ciclo live

Seconda parte: (a) stringere lo skip pre-inferenza da 12h a un valore config-driven (default 2h), (b) filtrare per `published_at` in `fetch_signals_for_cycle` così il portfolio cycle non compra su notizie vecchie.

**Files:**
- Modify: `src/config.py` (nuovo campo config)
- Modify: `src/workers/sentiment.py:53` (`_SENTIMENT_MAX_NEWS_AGE_HOURS`)
- Modify: `src/store/pg_store.py` (`_FETCH_SIGNALS_FOR_CYCLE` riga ~1650 e `fetch_signals_for_cycle` riga ~1661)
- Modify: `src/workers/portfolio_scheduler.py` (call-site di `fetch_signals_for_cycle`)
- Test: `tests/store/test_fetch_signals_event_freshness.py` (nuovo)

- [x] **Step 1: Config-drive dello skip pre-inferenza**

In `src/config.py`, aggiungi accanto agli altri campi worker (segui il pattern dei campi esistenti tipo `SENTIMENT_REVERSAL_EXIT_THRESHOLD`):

```python
    # FIX-03: max age of a news item (from published time) before it is skipped
    # without inference, and before its signal is excluded from the live cycle.
    # Editorial news older than this is priced in; tactical horizon is intraday.
    MAX_NEWS_AGE_HOURS: float = float(os.environ.get("MAX_NEWS_AGE_HOURS", "2"))
```

In `src/workers/sentiment.py` sostituisci la riga 53:

```python
_SENTIMENT_MAX_NEWS_AGE_HOURS = 12
```

con:

```python
from src.config import config as _app_config  # se non già importato con altro nome nel file

_SENTIMENT_MAX_NEWS_AGE_HOURS = _app_config.MAX_NEWS_AGE_HOURS
```

ATTENZIONE: `sentiment.py` importa già `config` (verifica con `grep -n "from src.config" src/workers/sentiment.py`) — riusa l'import esistente, non duplicarlo.

- [x] **Step 2: Scrivere il test SQL-behaviour che fallisce**

Crea `tests/store/test_fetch_signals_event_freshness.py`. Segui il pattern dei test esistenti in `tests/store/` (mock del connection/cursor). Il test verifica che la query rifiuti righe con `published_at` più vecchio della soglia e accetti righe con `published_at` NULL (legacy):

```python
"""FIX-03 part 2: fetch_signals_for_cycle filters on event-time (published_at)."""

from unittest.mock import MagicMock, patch

from src.store.pg_store import PostgreSQLStore


def test_fetch_signals_sql_contains_published_at_gate():
    assert "published_at" in PostgreSQLStore._FETCH_SIGNALS_FOR_CYCLE
    # NULL-safe: legacy rows without published_at must not be dropped.
    assert "published_at IS NULL" in PostgreSQLStore._FETCH_SIGNALS_FOR_CYCLE


def test_fetch_signals_passes_news_age_parameter():
    store = PostgreSQLStore.__new__(PostgreSQLStore)  # skip real __init__/pool
    cursor = MagicMock()
    cursor.fetchall.return_value = []
    conn = MagicMock()
    conn.cursor.return_value.__enter__ = MagicMock(return_value=cursor)
    conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    with patch.object(PostgreSQLStore, "_get_connection", return_value=conn):
        store.fetch_signals_for_cycle(hours=4, symbols=["AAPL"], news_age_hours=2.0)
    params = cursor.execute.call_args[0][1]
    assert "2.0" in [str(p) for p in params]
```

Se in `tests/store/` esiste una fixture standard per lo store mockato, usala al posto del setup manuale sopra.

- [x] **Step 3: Eseguire il test per verificarne il fallimento**

Run: `pytest tests/store/test_fetch_signals_event_freshness.py -v`
Expected: FAIL (SQL senza `published_at`; parametro inesistente).

- [x] **Step 4: Estendere query e firma**

In `src/store/pg_store.py`, sostituisci `_FETCH_SIGNALS_FOR_CYCLE` con:

```python
    _FETCH_SIGNALS_FOR_CYCLE = """
        SELECT DISTINCT ON (symbol)
            symbol, score, confidence,
            COALESCE(reasoning, '') AS reasoning,
            model_id, ensemble_std, fallback_used, generated_at
        FROM sentiment_signals
        WHERE generated_at >= NOW() - (%s || ' hours')::interval
          AND (published_at IS NULL
               OR published_at >= NOW() - (%s || ' hours')::interval)
          AND symbol = ANY(%s)
        ORDER BY symbol, fallback_used ASC, generated_at DESC
    """
```

e aggiorna la firma e l'execute di `fetch_signals_for_cycle`:

```python
    def fetch_signals_for_cycle(
        self, hours: int = 4, symbols: list[str] | None = None,
        news_age_hours: float = 2.0,
    ) -> list[SentimentResult]:
```

```python
                cur.execute(
                    self._FETCH_SIGNALS_FOR_CYCLE,
                    (str(hours), str(news_age_hours), watchlist),
                )
```

Aggiorna la docstring: "published_at gate (FIX-03): signals whose news is older than `news_age_hours` are excluded; NULL published_at (legacy rows) passes — the generated_at window still bounds those."

- [x] **Step 5: Aggiornare il call-site nel portfolio scheduler**

In `src/workers/portfolio_scheduler.py`, trova il call-site (`grep -n "fetch_signals_for_cycle" src/workers/portfolio_scheduler.py`) e passa il parametro dal config:

```python
        signals = pg.fetch_signals_for_cycle(
            hours=..., symbols=...,                     # invariati
            news_age_hours=config.MAX_NEWS_AGE_HOURS,   # FIX-03
        )
```

(`config` è già importato nel modulo; verifica il nome effettivo dell'import.)

- [x] **Step 6: Eseguire i test**

Run: `pytest tests/store/ tests/workers/ -q`
Expected: tutti PASS. Test esistenti su `fetch_signals_for_cycle` che asseriscono i parametri della query vanno aggiornati (+1 parametro).

- [x] **Step 7: Commit**

```bash
git add src/config.py src/workers/sentiment.py src/store/pg_store.py src/workers/portfolio_scheduler.py tests/store/test_fetch_signals_event_freshness.py
git commit -m "feat(freshness): event-time gate — skip news >2h pre-inference and filter published_at in live cycle (FIX-03)"
```

---

## Task 7: Enforcement conservativo del resolver (solo NOT_TRADABLE / verdetti hard)

Il resolver gira già in shadow su ogni news (`resolve_and_log_shadow`, chiamato in `src/workers/sentiment.py:610-613` DOPO il processing). Con extraction precision misurata a 0.24, i verdetti a massima precisione (`NO_TRADE_NOT_TRADABLE`: il simbolo non è tradabile sul broker) devono bloccare l'inferenza. La calibrazione fine resta gated su QX-01 — qui si enforce SOLO il verdetto hard, fail-open su qualunque errore.

**Files:**
- Modify: `src/connectors/resolver_shadow.py` (`resolve_and_log_shadow` deve restituire i verdetti)
- Modify: `src/workers/sentiment.py` (spostare la chiamata shadow PRIMA del loop di processing e filtrare)
- Test: `tests/workers/test_resolver_conservative_enforcement.py` (nuovo)

- [x] **Step 1: Leggere i file prima di toccarli**

Leggi per intero `src/connectors/resolver_shadow.py` e le righe 500-640 di `src/workers/sentiment.py` (funzione task `run_sentiment_worker` e costruzione di `items_to_process`). Leggi i test esistenti: `grep -rln "resolve_and_log_shadow" tests/`. Questo task modifica un'interfaccia: devi conoscere tutti i call-site (produzione + test) prima di cambiarla.

- [x] **Step 2: Scrivere i test che falliscono**

Crea `tests/workers/test_resolver_conservative_enforcement.py`:

```python
"""Conservative resolver enforcement (FUNCTIONAL_REVIEW_2026-07-03 §3.2):
items whose resolver verdict is NO_TRADE_NOT_TRADABLE are dropped BEFORE
LLM inference. Everything else passes. Any resolver error → fail-open."""

import os
from unittest.mock import MagicMock, patch

from src.models.news import NewsItem


def _item(ticker: str) -> NewsItem:
    return NewsItem(id=f"u:{ticker}", title="t", body="b", asset_tags=[ticker])


def test_not_tradable_items_are_filtered():
    from src.workers.sentiment import _filter_enforced_items
    items = [_item("AAPL"), _item("XLF")]
    verdicts = {"u:AAPL": "RESOLVED", "u:XLF": "NO_TRADE_NOT_TRADABLE"}
    kept, dropped = _filter_enforced_items(items, verdicts)
    assert [i.id for i in kept] == ["u:AAPL"]
    assert dropped == 1


def test_unknown_verdict_passes():
    """Only the hard NOT_TRADABLE verdict blocks; low-conf/ambiguous verdicts
    stay observational until QX-01 calibration."""
    from src.workers.sentiment import _filter_enforced_items
    items = [_item("AAPL")]
    verdicts = {"u:AAPL": "NO_TRADE_LOW_CONF"}
    kept, dropped = _filter_enforced_items(items, verdicts)
    assert len(kept) == 1 and dropped == 0


def test_missing_verdict_passes():
    from src.workers.sentiment import _filter_enforced_items
    items = [_item("AAPL")]
    kept, dropped = _filter_enforced_items(items, {})
    assert len(kept) == 1 and dropped == 0


def test_enforcement_disabled_by_env():
    from src.workers.sentiment import _filter_enforced_items
    items = [_item("XLF")]
    verdicts = {"u:XLF": "NO_TRADE_NOT_TRADABLE"}
    with patch.dict(os.environ, {"RESOLVER_ENFORCE_NOT_TRADABLE": "0"}):
        kept, dropped = _filter_enforced_items(items, verdicts)
    assert len(kept) == 1 and dropped == 0
```

- [x] **Step 3: Eseguire i test per verificarne il fallimento**

Run: `pytest tests/workers/test_resolver_conservative_enforcement.py -v`
Expected: FAIL (`_filter_enforced_items` non esiste).

- [x] **Step 4: Far restituire i verdetti a `resolve_and_log_shadow`**

In `src/connectors/resolver_shadow.py`, cambia il tipo di ritorno di `resolve_and_log_shadow` da `int` a `dict[str, str]` (mappa `item.id → decision`, es. `"RESOLVED"`, `"NO_TRADE_NOT_TRADABLE"`, `"NO_TRADE_LOW_CONF"`). Il valore veniva usato solo per logging: aggiorna il chiamante per loggare `len(verdicts)`. Mantieni intatta la semantica fail-safe esistente (su errore la funzione non deve sollevare: ritorna `{}`). Aggiorna i test esistenti individuati allo Step 1 al nuovo tipo di ritorno.

- [x] **Step 5: Implementare il filtro e spostare la chiamata shadow prima del processing**

In `src/workers/sentiment.py`:

(a) Aggiungi la funzione modulo-level (vicino a `_is_stale_news`):

```python
# Conservative resolver enforcement: only the hard, maximum-precision verdict blocks
# inference. Finer gates (LOW_CONF/AMBIGUOUS thresholds) stay observational until the
# QX-01 golden label set calibrates them. Fail-open by design: no verdict → pass.
_RESOLVER_ENFORCE_NOT_TRADABLE_VERDICT = "NO_TRADE_NOT_TRADABLE"


def _filter_enforced_items(items: list, verdicts: dict[str, str]) -> tuple[list, int]:
    """Drop items whose resolver verdict is NO_TRADE_NOT_TRADABLE. Returns (kept, n_dropped)."""
    if os.environ.get("RESOLVER_ENFORCE_NOT_TRADABLE", "1") == "0":
        return items, 0
    kept = [i for i in items if verdicts.get(i.id) != _RESOLVER_ENFORCE_NOT_TRADABLE_VERDICT]
    return kept, len(items) - len(kept)
```

(b) Nel task `run_sentiment_worker`, sposta il blocco shadow (attualmente righe ~610-613, DOPO il processing) a PRIMA del loop di inferenza, subito dopo che `items_to_process` è costruito, e applica il filtro:

```python
        resolver_verdicts: dict[str, str] = {}
        if _RESOLVER_SHADOW_ENABLED and items_to_process:
            try:
                from src.connectors.resolver_shadow import resolve_and_log_shadow
                resolver_verdicts = resolve_and_log_shadow(items_to_process, pg_store)
            except Exception as _shadow_exc:
                log.warning("Resolver shadow failed (fail-open): %s", _shadow_exc)

        items_to_process, skipped_not_tradable = _filter_enforced_items(
            items_to_process, resolver_verdicts
        )
        if skipped_not_tradable:
            log.info(
                "Resolver enforcement: dropped %d NOT_TRADABLE item(s) pre-inference",
                skipped_not_tradable,
            )
```

(c) Aggiungi `"skipped_not_tradable": skipped_not_tradable` al dict di ritorno del task (accanto a `"skipped_stale"`).

(d) Rimuovi il vecchio blocco shadow post-processing (righe ~610-613) — la chiamata ora avviene una sola volta, prima.

- [x] **Step 6: Eseguire i test**

Run: `pytest tests/workers/test_resolver_conservative_enforcement.py tests/workers/ tests/connectors/ -q`
Expected: tutti PASS.

- [x] **Step 7: Commit**

```bash
git add src/connectors/resolver_shadow.py src/workers/sentiment.py tests/workers/test_resolver_conservative_enforcement.py
git commit -m "feat(resolver): conservative enforcement — drop NO_TRADE_NOT_TRADABLE items pre-inference, fail-open (review §3.2)"
```

---

## Task 8: Soglie reali nei gate di backtest

I gate hanno default tautologici (`min_sharpe=0.0`, `min_oos_sharpe=0.0` in `src/backtest/gates/runner.py:21-25` e `gate_1_significance.py:39`, `gate_2_walkforward.py:18`). Le soglie promesse dal master roadmap vanno nel codice: `min_sharpe=0.5`, `min_oos_sharpe=0.3`.

**Files:**
- Modify: `src/backtest/gates/runner.py:21-25`
- Modify: `src/backtest/gates/gate_1_significance.py:39`
- Modify: `src/backtest/gates/gate_2_walkforward.py:18`
- Test: `tests/backtest/test_gate_thresholds.py` (nuovo)

- [x] **Step 1: Scrivere i test che falliscono**

Crea `tests/backtest/test_gate_thresholds.py`:

```python
"""B12 (review §8.1): gate defaults must be real thresholds, not 0.0 —
a gate that cannot fail is not a gate. Values from the master roadmap:
Sharpe > 0.5 in-sample, OOS Sharpe > 0.3 (conservative starting point)."""

import inspect


def test_runner_default_min_sharpe_is_meaningful():
    from src.backtest.gates.runner import GateConfig
    cfg = GateConfig()
    assert cfg.min_sharpe >= 0.5
    assert cfg.min_oos_sharpe >= 0.3


def test_gate1_default_min_sharpe_is_meaningful():
    from src.backtest.gates.gate_1_significance import run_gate_1
    sig = inspect.signature(run_gate_1)
    assert sig.parameters["min_sharpe"].default >= 0.5


def test_gate2_default_min_oos_sharpe_is_meaningful():
    from src.backtest.gates.gate_2_walkforward import run_gate_2
    sig = inspect.signature(run_gate_2)
    assert sig.parameters["min_oos_sharpe"].default >= 0.3
```

NOTA: verifica i nomi reali delle funzioni con `grep -n "^def " src/backtest/gates/gate_1_significance.py src/backtest/gates/gate_2_walkforward.py` e correggi gli import del test di conseguenza PRIMA di eseguirlo.

- [x] **Step 2: Eseguire i test per verificarne il fallimento**

Run: `pytest tests/backtest/test_gate_thresholds.py -v`
Expected: FAIL (default a 0.0).

- [x] **Step 3: Alzare i default**

- `src/backtest/gates/runner.py`: `min_sharpe: float = 0.0` → `min_sharpe: float = 0.5`; `min_oos_sharpe: float = 0.0` → `min_oos_sharpe: float = 0.3`.
- `src/backtest/gates/gate_1_significance.py:39`: `min_sharpe: float = 0.0` → `min_sharpe: float = 0.5`.
- `src/backtest/gates/gate_2_walkforward.py:18`: `min_oos_sharpe: float = 0.0` → `min_oos_sharpe: float = 0.3`.

Aggiungi accanto a ogni valore il commento: `# B12: real threshold (master roadmap); 0.0 was tautological`.

- [x] **Step 4: Eseguire la suite backtest e sistemare i test che passavano tautologicamente**

Run: `pytest tests/backtest/ -q`
Expected: alcuni test esistenti possono fallire perché costruivano PnL con Sharpe basso e asserivano `passed=True`. Per ciascuno: se il test verifica la MECCANICA del gate (non la soglia), passa esplicitamente `min_sharpe=0.0` nel test con il commento `# threshold irrelevant here: testing gate mechanics`; se il test verifica il giudizio del gate, aggiorna il dato o l'assert. NON abbassare i nuovi default per far passare i test.

- [x] **Step 5: Commit**

```bash
git add src/backtest/gates/ tests/backtest/test_gate_thresholds.py tests/backtest/
git commit -m "fix(backtest): real gate thresholds (Sharpe>=0.5 IS, >=0.3 OOS) — 0.0 defaults were tautological (B12)"
```

---

## Task 9: Eseguire il backtest S7 — gate ALPHA-A5 (task operativo, non di sviluppo)

L'harness esiste già (`scripts/backtest_s7_pead.py`, commit `694df3b`). Questo task lo ESEGUE e produce il report del gate. Nessuna modifica al codice salvo fix di crash minori che emergessero al run.

**Files:**
- Create: `reports/s7_backtest/ALPHA_A5_gate_report_2026-07-XX.md` (output)

- [x] **Step 1: Verificare i prerequisiti**

Run: `docker compose ps` — i container `worker`, `postgres`, `redis` devono essere UP.
Run: `docker compose exec -T worker python -c "import os; print(bool(os.environ.get('FINNHUB_API_KEY')), bool(os.environ.get('ALPACA_API_KEY')))"`
Expected: `True True`. Se `False`, fermati e chiedi all'operatore le credenziali — NON proseguire con chiavi inventate.

- [x] **Step 2: Lanciare il backtest**

Run: `docker compose exec -T worker python scripts/backtest_s7_pead.py 2>&1 | tee reports/s7_backtest/ALPHA_A5_raw_output.txt`
Expected: run di parecchi minuti (rate-limit Finnhub 60/min, ~600 eventi max). Output finale con drift medio a 20 giorni e hit-rate per bucket BEAT/MISS × large/small-mid cap. Se lo script crasha, applica il fix minimo necessario (es. simbolo senza barre → skip), committalo separatamente (`fix(s7): ...`) e rilancia.

- [x] **Step 3: Compilare il report del gate**

Crea `reports/s7_backtest/ALPHA_A5_gate_report_<data-run>.md` con questa struttura, popolata dai numeri reali dell'output:

```markdown
# S7 PEAD — ALPHA-A5 Gate Report

**Run date:** <data>
**Window:** <BT_START>–<BT_END>  ·  **Events:** <n BEAT> / <n MISS>
**Harness:** scripts/backtest_s7_pead.py @ <git rev-parse --short HEAD>

## Gate (ROADMAP_DATA_ALPHA_2026-07-02, ALPHA-A5)
| Criterio | Soglia | Large-cap | Small/mid-cap | Esito |
|---|---|---|---|---|
| BEAT drift 20d | ≥ +1.5% | <x%> | <y%> | PASS/FAIL |
| Hit-rate | > 55% | <x%> | <y%> | PASS/FAIL |

## Verdetto
- PASS large ∧ small → proporre S7 paper (richiede PO sign-off — NON procedere da soli)
- FAIL large, PASS small/mid → decisione PO: espandere universo small/mid (stop point §9.1 roadmap)
- FAIL entrambi → S7 shelved; documentare qui il perché

## Note metodologiche
- Entry: giorno di trading successivo all'annuncio (no look-ahead)
- Prezzi: Alpaca daily bars (IEX feed)
- Limiti: <es. eventi con eps_estimate mancante scartati: n>
```

- [x] **Step 4: Commit del report e aggiornamento roadmap**

In `docs/ROADMAP_DATA_ALPHA_2026-07-02.md`, riga ALPHA-A5, aggiungi in coda alla cella gate: `→ ESEGUITO <data>, vedi reports/s7_backtest/ALPHA_A5_gate_report_<data>.md`.

```bash
git add reports/s7_backtest/ docs/ROADMAP_DATA_ALPHA_2026-07-02.md
git commit -m "docs(s7): ALPHA-A5 gate report — PEAD backtest results (large vs small/mid cap)"
```

**STOP POINT:** l'esito di questo task determina lo Sprint 2 (vedi sotto). Qualunque sia il risultato, riportalo al PO. Non promuovere S7, non cambiare `config/strategies.yaml`.

---

## Verifica finale Sprint 1

- [x] **Step 1: Suite completa**

Run: `pytest -q`
Expected: stesso numero di pass della baseline registrata all'inizio + i nuovi test; 0 nuove failure.

- [x] **Step 2: Lint**

Run: `ruff check src/ tests/`
Expected: 0 errori nei file toccati.

- [x] **Step 3: Riepilogo per il PO**

Scrivi in chat (non in un file) il riepilogo: task completati, esito gate ALPHA-A5, eventuali deviazioni dal piano, failure pre-esistenti trovate.

---

# Sprint 2 e 3 — Task card (richiedono un piano dedicato ciascuna)

I task seguenti NON vanno eseguiti in questa sessione. Sono scoped qui perché il PO possa prioritizzarli; ognuno richiede il proprio implementation plan (stessa procedura di questo documento) quando il suo criterio di ingresso è soddisfatto. Un agente che esegue lo Sprint 1 deve fermarsi qui.

## Sprint 2 — "pivot event-driven e attribution" (1-2 mesi)

| ID | Task | Criterio di ingresso | Scope sintetico | File principali attesi |
|---|---|---|---|---|
| S2-1 | **FIX-04/05 — Source P&L funnel** | Sprint 1 completo | Nuova tabella `ingestion_stats_daily` + colonne `news_log.raw_ingested_at`, `discarded_reason`, `content_hash` (EN-05); join trace news→signal→decision→trade; endpoint `/api/quality/sources`; vista frontend | `migrations/033+`, `src/workers/ingestion.py`, `src/store/pg_store.py`, `src/api/routes/` |
| S2-2 | **FIX-06 — discarded_reason logging** | S2-1 (colonna creata) | Ogni scarto in ingestione/sentiment persiste un motivo enum (`no_ticker`, `stale`, `duplicate_id`, `duplicate_content`, `not_tradable`, `parse_fail`) | `src/workers/ingestion.py`, `src/workers/sentiment.py` |
| S2-3 | **ALPHA-A1 — Earnings blackout per S1/S4** | nessuno (calendar connector esiste: `src/connectors/earnings_calendar.py`) | Worker giornaliero scrive `earnings:blackout` (set di simboli con earnings entro 2 giorni) in Redis; il portfolio scheduler esclude quei simboli dai BUY (nuova decision `SKIP_EARNINGS`) | `src/workers/`, `src/workers/portfolio_scheduler.py` |
| S2-4 | **B44 — Stop-loss broker-side sempre** | decisione PO su rinuncia al frazionamento S4 | Ordini S4 BUY arrotondati a share intere + `StopLossRequest` bracket; rimozione dipendenza dallo stop sintetico per le nuove posizioni | `src/workers/portfolio_scheduler.py` (`_submit_portfolio_orders`) |
| S2-5 | **Rigenerazione backtest S1 PIT** | Task 8 completo (soglie reali) | Rerun S1 con l'engine `src/backtest/` (fill t+1, costi realistici, universo PIT); gate report; NESSUNA modifica di allocazione senza PO | `scripts/`, `reports/s1_backtest/` |
| S2-6 | **ALPHA-A2/A3 — Consensus + transcript** | esito ALPHA-A5 positivo + decisione PO sul vendor (FMP vs multi-vendor: stop point §9.2 roadmap) | Connector consensus/transcript; tone analysis LLM sul transcript (offline, queue inference) | `src/connectors/`, `src/workers/pead_worker.py` |
| S2-7 | **B48 — NAV reale nel risk monitor** | nessuno | `_fetch_strategy_data` usa equity Alpaca invece della P&L cumulativa | `src/workers/risk_monitor_task.py:83-85` |
| S2-8 | **Enforcement resolver completo** | QX-01 annotazione completa + calibrazione | Soglie confidence/ambiguity misurate; gate `risk_flags`; weighting materiality×directness | `src/workers/sentiment.py`, `src/connectors/ticker_resolver.py` |

## Sprint 3 — "loop di discovery e diversificazione" (3-6 mesi)

| ID | Task | Criterio di ingresso | Scope sintetico |
|---|---|---|---|
| S3-1 | **Alpha attribution nightly** (`alpha_attribution`: IC/P&L per fonte × event_type × score-bucket × cap-bucket × latenza) | S2-1 | Fondazione del discovery loop (review §5.2 step 1) |
| S3-2 | **Alpha hypotheses weekly** (worker LLM offline propone ipotesi strutturate; il PO promuove; backtest auto-generato) | S3-1 | Review §5.2 step 2-3. L'LLM propone, MAI decide |
| S3-3 | **S8 Insider Form 4** | ALPHA-B0 (fix EDGAR CIK→ticker) | POC: open-market purchases, cluster ≥2 insider, hold 60d, sleeve ≤5% |
| S3-4 | **S9 Guidance/8-K multi-evento** | S2-6 | LLM classifica direzione guidance; concordanza ≥80% con surprise |
| S3-5 | **S11 Revisions momentum** | S2-6 (stesso vendor) | BUY su revisione EPS up, hold 20d, hit-rate >55% netto |
| S3-6 | **Universo small/mid + filtri liquidità** | esito ALPHA-A5 + decisione PO (stop point §9.1) | ADV/spread/market-cap filter PRIMA dell'espansione |
| S3-7 | **Short/hedge overlay** | S3-1 (evidenza IC sul segno negativo) | Riduzione beta su media segnali negativi; NO shorting singolo nome al primo giro |
| S3-8 | **Shadow-vs-backtest come gate formale** | S2-5 | 30g di segnali loggati senza ordini; confronto IC shadow vs backtest come condizione di promozione |
| S3-9 | **S5 Crypto / S6 Sector rotation** | master roadmap B-02/B-03 | Come da `docs/superpowers/plans/2026-06-16-master-roadmap.md` |

---

## Riferimenti

- Review sorgente: `docs/FUNCTIONAL_REVIEW_2026-07-03.md`
- Roadmap dati/alpha: `docs/ROADMAP_DATA_ALPHA_2026-07-02.md` (FIX-*, EN-*, ALPHA-*)
- Technical review (B-numbers): `docs/TECHNICAL_REVIEW_2026-07-02.md`
- Master roadmap strategie: `docs/superpowers/plans/2026-06-16-master-roadmap.md`
