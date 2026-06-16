# Alembic Master Roadmap

**Data creazione:** 2026-06-16  
**Contesto:** Piano unico di riferimento che aggrega (a) i fix pendenti dalla code review del 2026-06-15 e (b) le nuove strategie emerse dal brainstorming del 2026-06-16. Usare questo file come source-of-truth: spuntare ogni voce quando completata, NON riscrivere il file a ogni sessione.

**Stato economico del sistema (da ricordare):**
- Capitale: < $10.000, tutto paper trading al momento
- Costi operativi: ~€0 (macchina locale + LLM condiviso con altri usi)
- Hurdle rate reale: quasi zero → ogni ritorno è profitto netto
- S1 (50% alloc, OOS Sharpe ~0.51): unico sleeve validato in live
- S4 (10% alloc, paper): news-driven LLM, capped in attesa di gate report
- 40% capitale non allocato: priorità massima per le nuove strategie

---

## PARTE A — Fix da Code Review (CODE_REVIEW_FULL_2026-06-15.md)

### P0 — Critici (sicurezza / correttezza finanziaria)

- [ ] **A-01 — Rotazione segreti + purge git history**
  - **Problema:** `.env` con segreti reali è tracked in git: `ADMIN_API_KEY`, `OLLAMA_API_KEY`, `NEWSAPI_KEY`, `MARKETAUX_API_KEY`, `FRED_API_KEY`, `DEEPL_API_KEY`, `TELEGRAM_BOT_TOKEN`, `ALPACA_API_KEY`, `ALPACA_SECRET_KEY`.
  - **Fix:**
    1. Aggiungere `.env` a `.gitignore` (già presente ma il file è già stato commitato)
    2. Rimuovere `.env` dalla storia git: `git filter-repo --invert-paths --path .env`
    3. Ruotare TUTTI i segreti elencati sopra dai rispettivi provider
    4. Creare `.env.example` con placeholder (es. `ALPACA_API_KEY=your_key_here`)
    5. Force-push su origin dopo purge (richede conferma esplicita utente)
  - **File:** `.env`, `.gitignore`, creare `.env.example`

- [ ] **A-02 — Fix connection lifecycle (resource leak)**
  - **Problema:** `RedisStore`, `PostgreSQLStore`, `TradingClient` (Alpaca), `TelegramNotifier` vengono istanziati ma mai chiusi in blocco `finally`. In `portfolio_scheduler.py` vengono creati più client per ciclo e tutti leakano su eccezione.
  - **Pattern corretto da applicare ovunque:**
    ```python
    redis_store = RedisStore()
    try:
        # uso
    finally:
        redis_store.close()
    ```
  - **File e righe specifiche:**
    - `src/workers/performance.py` righe 682, 764, 952, 1155 (RedisStore); righe 1290-1360 (TelegramNotifier)
    - `src/workers/execution.py` righe 836-873 (TradingClient + StockHistoricalDataClient in finally mancante)
    - `src/workers/portfolio_scheduler.py` righe 187, 226 (TradingClient, StockHistoricalDataClient); riga 467 (PostgreSQLStore chiuso in try invece di finally); righe 151-172, 302-328, 445-452 (connessioni Redis ephemere per ciclo)
    - `src/workers/regime.py` righe 148, 149 (RedisStore + TelegramNotifier); righe 204-205 (LLM clients)

- [ ] **A-03 — Replace asyncio.run() con pattern Celery async**
  - **Problema:** `asyncio.run()` chiamato più volte per task in Celery prefork worker. Ogni Telegram alert crea e distrugge un event loop → stato inquinato, inefficiente.
  - **Occorrenze:**
    - `performance.py`: righe 726, 904, 1332, 1357, 1675, 1715
    - `execution.py`: righe 278, 397, 534, 568, 607, 736, 807
    - `regime.py`: righe 162, 174, 185, 194, 212, 226, 239, 252, 273, 284, 330
  - **Soluzione raccomandata:** creare un event loop persistente per thread con pattern:
    ```python
    import asyncio, threading
    _loop = None
    _lock = threading.Lock()

    def _get_loop() -> asyncio.AbstractEventLoop:
        global _loop
        with _lock:
            if _loop is None or _loop.is_closed():
                _loop = asyncio.new_event_loop()
        return _loop

    def run_async(coro):
        return _get_loop().run_until_complete(coro)
    ```
    Poi sostituire `asyncio.run(coro)` con `run_async(coro)` in tutti i worker.
  - **File:** `src/workers/performance.py`, `src/workers/execution.py`, `src/workers/regime.py` (creare helper in `src/workers/_async_utils.py`)

- [ ] **A-04 — CI/CD pipeline GitHub Actions**
  - **Problema:** Zero automazione. Nessun `.github/workflows/`. Ogni push può introdurre regressioni senza detection.
  - **Pipeline da creare:** `.github/workflows/ci.yml`
    ```yaml
    on: [push, pull_request]
    jobs:
      test:
        runs-on: ubuntu-latest
        steps:
          - uses: actions/checkout@v4
          - uses: astral-sh/setup-uv@v3
          - run: uv sync --dev
          - run: uv run ruff check src/ tests/
          - run: uv run mypy src/ --ignore-missing-imports
          - run: uv run pytest tests/ -q --tb=short --cov=src --cov-report=term-missing
          - run: uv run pip-audit
    ```
  - **File da creare:** `.github/workflows/ci.yml`
  - **Prerequisito:** Fix A-10 (ruff + mypy config in pyproject.toml)

---

### P1 — Alta priorità (correttezza dati / sicurezza finanziaria)

- [ ] **A-05 — pg_store.py: race condition in close_trade**
  - **Problema:** `SELECT ... FOR UPDATE SKIP LOCKED` eseguito dentro cursor che si chiude immediatamente, rilasciando il row lock PRIMA dell'UPDATE successivo. Possibile doppio close su trade.
  - **Righe:** `src/store/pg_store.py` righe 507-556
  - **Fix:** Wrappare SELECT e UPDATE nella stessa transazione con lo stesso cursore aperto:
    ```python
    with conn:
        with conn.cursor() as cur:
            cur.execute("SELECT ... FOR UPDATE SKIP LOCKED WHERE id = %s", (trade_id,))
            row = cur.fetchone()
            if row is None:
                return  # già chiuso o locked da altro worker
            cur.execute("UPDATE trades SET exit_time=... WHERE id = %s", (trade_id,))
    ```

- [ ] **A-06 — pg_store.py: reconcile_trade_fills doppio commit**
  - **Problema:** `reconcile_trade_fills` fa commit due volte; se il secondo blocco fallisce il DB è parzialmente riconciliato.
  - **Righe:** `src/store/pg_store.py` righe 710-802
  - **Fix:** Unificare i due blocchi in un'unica transazione con un unico commit finale:
    ```python
    with conn:  # single transaction
        with conn.cursor() as cur:
            # blocco 1
            # blocco 2
        # commit implicito all'uscita del with
    ```

- [ ] **A-07 — Unificare dependency management**
  - **Problema:** `requirements.txt` non è allineato con `pyproject.toml`. Il Dockerfile installa da `requirements.txt` stale; `sqlalchemy`, `pydantic-settings`, `feedparser`, `bleach`, `python-telegram-bot`, `pyarrow`, `empyrical`, `pdfplumber` mancanti.
  - **Fix:**
    1. Eliminare `requirements.txt`
    2. Aggiornare `Dockerfile`: sostituire `pip install -r requirements.txt` con `pip install uv && uv sync --no-dev`
    3. Aggiornare `.dockerignore` se necessario
  - **File:** `requirements.txt` (delete), `Dockerfile`

- [ ] **A-08 — Fix N+1 queries**
  - **performance.py** (righe 89-91, 108-110, 955-958): loop per-symbol su `WATCHLIST_SYMBOLS` con query PG separate.
    - Fix: una query con `WHERE symbol = ANY(%s)` passando la lista intera
  - **pg_store.py** (righe 1531-1561, 804-826): INSERT row-by-row.
    - Fix: usare `executemany` o `COPY FROM` per batch insert

---

### P2 — Media priorità (qualità / tooling)

- [ ] **A-09 — docker-compose.yml hardening**
  - Aggiungere `USER` non-root in `Dockerfile` (es. `RUN useradd -m alembic && USER alembic`)
  - Cambiare password deboli: `POSTGRES_PASSWORD: trading` → variabile env da `.env`
  - Aggiungere resource limits a ogni servizio:
    ```yaml
    deploy:
      resources:
        limits:
          memory: 512M
          cpus: "0.5"
    ```
  - Fix healthcheck API: aggiungere timeout `urllib.request.urlopen(url, timeout=5)`
  - File: `docker-compose.yml`, `Dockerfile`

- [ ] **A-10 — pyproject.toml: config mypy + ruff + coverage**
  - Aggiungere:
    ```toml
    [tool.ruff]
    line-length = 100
    select = ["E", "F", "W", "I", "N"]
    ignore = ["E501"]

    [tool.mypy]
    python_version = "3.11"
    ignore_missing_imports = true
    warn_return_any = true
    warn_unused_configs = true

    [tool.coverage.run]
    source = ["src"]
    omit = ["*/tests/*", "*/migrations/*"]

    [tool.coverage.report]
    fail_under = 70
    ```
  - File: `pyproject.toml`

- [ ] **A-11 — Espandere tests/test_llm_client.py**
  - Aggiungere test per: subprocess execution, retry logic (max 3 tentativi), `_sanitize_error_output`, semaphore exhaustion (>1 richiesta concorrente), path injection in prompt
  - File: `tests/llm/test_llm_client.py`

- [ ] **A-12 — Pagination safety limits in connectors**
  - `src/connectors/marketaux.py` righe 100-134: aggiungere `max_pages: int = 10` nel loop di paginazione
  - `src/connectors/alpaca_news.py` righe 98-121: stesso pattern
  - Fix: `if page_count >= max_pages: break`

- [ ] **A-13 — Token-aware truncation in finbert.py**
  - **Problema:** riga 112 usa `clean_text[:self._MAX_TOKENS]` che taglia code points Unicode, non token. Un token BPE può essere 1-4 caratteri.
  - **Fix:**
    ```python
    tokens = self._pipe.tokenizer.encode(clean_text, truncation=True, max_length=self._MAX_TOKENS)
    truncated = self._pipe.tokenizer.decode(tokens, skip_special_tokens=True)
    ```
  - File: `src/llm/finbert.py` riga 112

---

## PARTE B — Nuove Strategie

### B-01 — S7: PEAD Earnings Event Strategy [Priorità 1]

**Rationale:** Post-Earnings Announcement Drift è uno degli effetti più documentati in letteratura (Jegadeesh & Titman, Bernard & Thomas 1989). Su positive surprise: drift medio +3-5% nei 20 giorni successivi all'annuncio. Con 115 simboli in watchlist = ~50-60 eventi/trimestre. Il SEC EDGAR connector è già live. L'LLM (già pagato) classifica il surprise dal testo 8-K.

**Architettura:**

```
SEC EDGAR 8-K (ogni 30 min in orario mercato)
    ↓
EarningsSurpriseClassifier (LLM: estrae EPS actual vs expected + sentiment)
    ↓
SurpriseSignal: {symbol, direction: "beat"|"miss"|"inline", magnitude: float, confidence: float}
    ↓
Redis: signal:SYMBOL:pead_event (TTL 30 giorni)
    ↓
PEADStrategy.compute_target_weights() → compra se beat, vendi se miss (se in posizione)
    ↓
PortfolioScheduler → ordini Alpaca
```

**Logica del segnale:**
- Parse 8-K con LLM: estrarre EPS actual, EPS consensus, guidance revised up/down
- Surprise score = (actual - consensus) / abs(consensus), dove consensus da Yahoo Finance free API o Alpaca earnings endpoint
- Soglia ingresso: `surprise_score > +0.05` (>5% beat) → BUY
- Soglia uscita: `surprise_score < -0.05` (>5% miss) → skip/SELL se già in posizione
- Hold period: fisso 20 giorni di calendario (non trading days) → exit automatico
- Position sizing: equal weight, max 5% per posizione, max 25% totale sleeve

**Configurazione:**
```python
# src/config.py (nuovi campi)
PEAD_SURPRISE_THRESHOLD: float = 0.05      # soglia ingresso
PEAD_HOLD_DAYS: int = 20                   # giorni di hold
PEAD_MAX_POSITION_PCT: float = 0.05        # max per posizione
PEAD_MAX_SLEEVE_PCT: float = 0.25          # max totale sleeve
PEAD_MIN_CONFIDENCE: float = 0.70          # min confidenza LLM
PEAD_ALLOCATION_PCT: float = 0.15          # % portafoglio (allocazione nel registry S7)
```

**Prompt LLM per classificazione surprise (DK-CoT per CLAUDE.md):**
```
Ruolo: analista buy-side equity specializzato in earnings analysis.

Testo 8-K: {testo}

Analisi step-by-step:
1. Identifica il ticker e il tipo di filing (earnings, guidance, altro)
2. Estrai: EPS reported, EPS consensus (se presente), revenue reported, revenue consensus
3. Calcola la direzione: beat / miss / inline / no-EPS
4. Valuta guidance: revised-up / revised-down / maintained / no-guidance
5. Fornisci un confidence score [0,1]

Output JSON:
{
  "ticker": "AAPL",
  "filing_type": "earnings_8k",
  "eps_actual": 1.52,
  "eps_consensus": 1.45,
  "surprise_pct": 0.048,
  "direction": "beat",
  "guidance": "revised-up",
  "confidence": 0.85,
  "reasoning": "..."
}
```

**File da creare/modificare:**
- `src/strategies/s7/__init__.py` (nuovo)
- `src/strategies/s7/signal.py` — `EarningsSurpriseClassifier`: LLM + parsing 8-K → `SurpriseSignal`
- `src/strategies/s7/strategy.py` — `PEADStrategy`: legge segnali da Redis, calcola target weights con hold-period tracking
- `src/strategies/s7/backtest.py` — backtest su dati EDGAR storici
- `src/workers/pead_worker.py` — Celery task che chiama `run_pead_ingestion_worker()` (integra con EDGAR connector esistente)
- `src/workers/celery_app.py` — aggiungere beat per pead_worker ogni 30 min in orario mercato
- `src/config.py` — aggiungere campi PEAD_*
- `config/strategies.yaml` — aggiungere S7, allocation_pct 0.15
- `tests/strategies/test_s7_pead.py`
- `tests/workers/test_pead_worker.py`

**Dipendenze dati:**
- Earnings consensus: Alpaca ha endpoint `/v1beta1/corporate_actions/announcements?ca_types=Earnings` (free per account live)
- Alternativa gratuita: Yahoo Finance `yf.Ticker(sym).earnings_dates` 
- SEC EDGAR 8-K: già disponibile via connector esistente

**Gate per promozione a live:**
- Backtest OOS (2023-2025): Sharpe > 0.5, hit rate > 55%, max drawdown < 15%
- Paper trading 30 giorni: almeno 10 eventi, win rate > 55%

---

### B-02 — S5: Crypto Momentum Strategy [Priorità 2 — build ora, attiva quando trend si gira]

**Rationale:** Stesso algoritmo di S1 (time-series momentum multi-lookback) applicato a BTC/ETH/SOL. Storicamente Sharpe 1.0-1.5 in trend bull. Alpaca supporta crypto, zero commissioni. Correlazione bassa con equity S1 → diversificazione vera. OGGI: tutti i lookback negativi su BTC ($90k→$63k) → strategia sarebbe flat, zero rischio.

**Contesto mercato (giugno 2026):**
- BTC ~$63k (da $90k di picco inizio anno, -30%)
- Fear & Greed Index: 18 (Extreme Fear)
- Solo 37% bullish positioning
- Scenario consenso: consolidamento $60k-$75k, potenziale ripresa 2H 2026
- **Implicazione:** S5 parte flat oggi, si attiverà automaticamente quando il trend si girerà

**Architettura:**
```
Alpaca Crypto OHLCV (WebSocket + REST)
    ↓
CryptoMomentumSignal (stesso di S1 ma lookbacks più corti: 14, 30, 60, 90 gg)
    ↓
CryptoStrategy.compute_target_weights() → vol-scaled weights
    ↓
PortfolioScheduler → ordini Alpaca Crypto
```

**Differenze rispetto a S1:**
- Simboli: BTC/USD, ETH/USD, SOL/USD (estendibile a AVAX, LINK se volume sufficiente)
- Lookbacks: [14, 30, 60, 90] giorni (vs [21, 63, 126, 252] di S1) — crypto ha cicli più corti
- Rebalancing: settimanale (vs mensile S1) — più reattivo
- Vol targeting: target_vol = 0.20 (vs 0.10 di S1) — crypto è 2-3x più volatile
- Max weight: 0.50 per simbolo (solo 3 simboli, diversificazione limitata)
- Mercato 24/7: usare UTC midnight come timestamp di rebalancing

**Configurazione:**
```python
# src/config.py (nuovi campi)
CRYPTO_LOOKBACKS: list[int] = [14, 30, 60, 90]
CRYPTO_VOL_WINDOW: int = 30
CRYPTO_TARGET_VOL: float = 0.20
CRYPTO_MAX_WEIGHT: float = 0.50
CRYPTO_SYMBOLS: list[str] = ["BTC/USD", "ETH/USD", "SOL/USD"]
CRYPTO_ALLOCATION_PCT: float = 0.15
```

**File da creare/modificare:**
- `src/strategies/s5/__init__.py` (nuovo)
- `src/strategies/s5/signal.py` — `CryptoMomentumSignal`: riusa logica di `s1/signal.py` con lookbacks crypto
- `src/strategies/s5/strategy.py` — `CryptoMomentum`: riusa struttura `s1/strategy.py`
- `src/strategies/s5/backtest.py` — backtest su dati Alpaca crypto storici
- `src/connectors/alpaca_crypto.py` — connector per dati OHLCV crypto Alpaca (WebSocket + REST)
- `src/config.py` — aggiungere campi CRYPTO_*
- `config/strategies.yaml` — aggiungere S5, allocation_pct 0.15, mode: paper (fino a OOS positivo)
- `tests/strategies/test_s5_crypto.py`

**Dati storici per backtest:**
- Alpaca fornisce dati crypto storici gratuiti fino a 5 anni
- Endpoint: `GET /v1beta3/crypto/us/bars?symbols=BTC/USD&timeframe=1Day&start=2020-01-01`

**Gate per attivazione:**
- BTC chiude sopra media mobile 50 giorni per 5 giorni consecutivi (momentum si gira)
- Backtest OOS (2021-2024 includendo bear 2022): Sharpe > 0.4, max drawdown < 35%
- Alert Telegram quando condizione di attivazione si verifica

---

### B-03 — S6: Macro Sector Rotation [Priorità 3]

**Rationale:** Usa il regime detector già implementato (`src/workers/regime.py`) + FRED data già integrata. Ruota tra ETF settoriali basandosi sul regime macro. Basso turnover (mensile), costo quasi zero, aggiunge layer difensivo che riduce il drawdown complessivo del portafoglio nei bear market.

**Universe ETF:**
| Regime | Allocazione |
|--------|-------------|
| `risk_on` | XLK 40%, QQQ 30%, IWM 30% |
| `risk_off` | XLV 40%, TLT 35%, GLD 25% |
| `high_vol` | TLT 50%, GLD 30%, SHY 20% |
| `neutral` | SPY 50%, XLV 25%, TLT 25% |

**Segnale regime (input):**
- Già calcolato da `regime.py` e scritto in Redis: `key: regime:current`
- Input aggiuntivi per affinare: VIX (FRED VIXCLS), Yield Curve 10Y-2Y (FRED T10Y2Y), ISM Manufacturing PMI
- LLM overlay: ogni lunedì mattina il LLM legge top-5 macro news della settimana e aggiunge un "macro sentiment score" [-1, +1] che può aggiustare marginalmente le allocation

**Configurazione:**
```python
# src/config.py
MACRO_ROTATION_ALLOCATION_PCT: float = 0.10
MACRO_ROTATION_REBALANCE_DAY: str = "MON"  # giorno della settimana
```

**File da creare/modificare:**
- `src/strategies/s6/__init__.py` (nuovo)
- `src/strategies/s6/regime_mapping.py` — mapping `regime → ETF weights`
- `src/strategies/s6/strategy.py` — `MacroSectorRotation`: legge Redis regime, calcola target weights
- `src/strategies/s6/backtest.py`
- `src/config.py` — aggiungere campi MACRO_*
- `config/strategies.yaml` — aggiungere S6, allocation_pct 0.10
- `tests/strategies/test_s6_macro.py`

---

### B-04 — S1 Improvements [Priorità 4]

**B-04a — Adaptive rebalancing (VIX-based)**
- **Attuale:** rebalancing mensile fisso
- **Miglioramento:** frequenza adattiva basata su VIX
  - VIX < 20 → mensile (attuale)
  - VIX 20–30 → bisettimanale
  - VIX > 30 → settimanale (cattura momentum breve in alta volatilità)
- **Implementazione:** `S1Config.rebalance_frequency` diventa `RebalanceFrequency.ADAPTIVE`; aggiungere metodo `_adaptive_rebalance_due(ts, vix)` nella strategy
- **File:** `src/strategies/s1/strategy.py`, `src/strategies/s1/config.py`
- **Nota:** VIX già disponibile via FRED, già usato nel regime detector

**B-04b — Earnings blackout per S1**
- **Problema:** S1 tiene posizioni durante gli earnings → rischio drawdown da surprise negativa non compensato
- **Logica:**
  - 3 giorni prima earnings di un titolo S1 in portafoglio → riduci posizione del 50%
  - 2 giorni dopo earnings → ripristina posizione se momentum ancora positivo
- **Dati:** Alpaca `GET /v1beta1/corporate_actions/announcements?ca_types=Earnings` (free)
- **File:** `src/strategies/s1/strategy.py`, nuovo `src/strategies/s1/earnings_calendar.py`

---

### B-05 — S4 Gate Report Completion [Priorità 5]

**Stato attuale:** S4 capped al 10% allocation senza gate report completo. Il gate report sblocca l'aumento a 20-25%.

**Gate da superare (formato identico a S1):**
| Gate | Metrica | Soglia |
|------|---------|--------|
| G1 | OOS Sharpe ratio | > 0.30 |
| G2 | Calmar ratio | > 0.50 |
| G3 | Hit rate | > 52% |
| G4 | Max drawdown | < 20% |
| G5 | IC medio (30gg rolling) | > 0.03 |

**Azioni:**
1. Eseguire backtest S4 OOS su periodo 2023-01 → 2025-12 con dati sentiment storici reali (non simulati)
2. Generare report `docs/s4_gate_report_2026.md` nel formato gate standard del progetto
3. Se tutti e 5 i gate passano: aggiornare `config/strategies.yaml` S4 `allocation_pct: 0.20`, `mode: live`
4. **File:** `src/strategies/s4/backtest.py` (già esiste, necessita fix del bug `pd.concat` che droppa i timestamp — vedi code review riga 70-71), `docs/s4_gate_report_2026.md`

**Bug da fixare prima del gate report (dalla code review):**
- `src/strategies/s4/backtest.py` righe 70-71: `pd.concat(wf_window_returns, ignore_index=True)` droppa i timestamp → Sharpe sbagliato. Fix: `pd.concat(wf_window_returns).sort_index()`
- `src/strategies/s4/backtest.py` righe 249-267: N+1 query per ticker → sostituire con batch fetch

---

## PARTE C — Sequenza di Esecuzione Raccomandata

```
SPRINT 1 (priorità sicurezza + qualità):
  → A-01 (segreti)
  → A-07 (requirements.txt)
  → A-10 (pyproject.toml config)
  → A-04 (CI/CD pipeline)

SPRINT 2 (correttezza finanziaria):
  → A-05 (close_trade race condition)
  → A-06 (reconcile_trade_fills)
  → A-02 (connection lifecycle — i file più urgenti: portfolio_scheduler, execution)
  → A-08 (N+1 queries)

SPRINT 3 (prima strategia nuova — alpha immediato):
  → B-01 (S7 PEAD) — include: signal classifier, strategy, worker, tests, config

SPRINT 4 (infrastruttura crypto — pronta per quando trend si gira):
  → B-02 (S5 Crypto Momentum) — include: connector, strategy, backtest

SPRINT 5 (completamento strategie + unlock S4):
  → B-05 (S4 gate report + fix bug backtest)
  → B-03 (S6 Macro Rotation)
  → B-04 (S1 improvements)

SPRINT 6 (hardening qualità):
  → A-03 (asyncio.run replacement)
  → A-09 (docker-compose hardening)
  → A-11, A-12, A-13 (test expansion, pagination, finbert)
```

---

## Legenda stato

- `[ ]` — da fare
- `[x]` — completato
- `[~]` — in corso
- `[!]` — bloccato (specificare motivo inline)

---

*Ultimo aggiornamento: 2026-06-16*
