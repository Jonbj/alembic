# 06 — Decision Rules

Regole esplicite per gestire ambiguità senza chiedere all'utente. L'agente applica queste rules **prima** di considerare un HUMAN_GATE.

---

## DR-01 — Naming e structure

### Naming files
- `snake_case.py` per moduli Python
- `PascalCase` per classi
- `snake_case` per funzioni e variabili
- `UPPER_CASE` per costanti
- Test file: `test_<module>.py`

### Project structure
```
alembic/
├── alembic/                    # package principale (esistente, riusare)
│   ├── ingestion/              # esistente
│   ├── signals/                # esistente
│   ├── strategies/             # NUOVO per v2
│   │   ├── base.py             # BaseStrategy interface
│   │   ├── s1_ts_momentum/
│   │   │   ├── __init__.py
│   │   │   ├── strategy.py
│   │   │   ├── signal.py
│   │   │   ├── sizing.py
│   │   │   └── config.yaml
│   │   ├── s2_vrp/
│   │   ├── s3_xs_momentum/
│   │   └── s4_news_tactical/
│   ├── backtest/               # NUOVO per v2
│   │   ├── engine/
│   │   ├── costs/
│   │   ├── walkforward/
│   │   ├── metrics/
│   │   └── gates/
│   ├── portfolio/              # NUOVO per v2
│   │   ├── combiner.py
│   │   └── constraints.py
│   ├── brokers/                # esistente, estendere
│   │   ├── alpaca_adapter.py   # esistente
│   │   └── ibkr_adapter.py     # NUOVO per S2
│   ├── regime/                 # esistente
│   ├── risk/                   # esistente, estendere
│   └── common/                 # esistente
├── config/
│   ├── alembic_v2.yaml
│   ├── strategies/
│   │   ├── s1.yaml
│   │   ├── s2.yaml
│   │   ├── s3.yaml
│   │   └── s4.yaml
│   └── universe.yaml
├── tests/
├── scripts/                    # one-off scripts (backfill, migrations)
└── docs/
```

### Quando la struttura esiste già diversa
Se il repo esistente ha una struttura diversa: **NON refactor**. Adatta i nuovi moduli alla struttura esistente. Cambio di struttura = task separato esplicito + HG.

---

## DR-02 — Dipendenze Python

### Quale tool usare per cosa

| Tool | Quando usarlo | Quando non usarlo |
|---|---|---|
| `vectorbt` (community) o `vectorbt-pro` | Backtest signal-based veloce (S1, S3, S4) | Per S2 options |
| `NautilusTrader` | Validation finale, S2 options | Per exploration veloce |
| `PyPortfolioOpt` | Optimization, mean-variance, Black-Litterman | Per HRP (usa `riskfolio-lib`) |
| `riskfolio-lib` | HRP, risk parity | Per cose basic (overkill) |
| `arch` | Modelli vol GARCH, EWMA | Solo se serve davvero (overkill spesso) |
| `empyrical` | Performance metrics validation | Per metriche custom |
| `quantstats` | Reporting interattivo | Per metriche pure (usa empyrical) |
| `pandas` | Time-series manipulation | Per >1M rows (use polars) |
| `polars` | Big data (>1M rows) | Quando pandas basta |
| `numpy` | Numerical | Per high-level (usa pandas) |
| `scipy` | Stats, optimization | Per ML (usa scikit-learn) |
| `yfinance` | Free historical data | Per data quality serio (use Polygon paid) |
| `ib_insync` | IBKR API | Per Alpaca (usa alpaca-py) |
| `alpaca-py` | Alpaca | Per IBKR |

### Quale broker per quale strategia

| Strategia | Broker primario | Razionale |
|---|---|---|
| S1 (trend ETF) | Alpaca | Già integrato, supporta ETF |
| S2 (options) | IBKR | Alpaca non offre opzioni |
| S3 (equity) | Alpaca | Equity US-listed |
| S4 (news) | Alpaca | Equity US-listed |

Se in futuro serve un broker unificato per IT compliance, è una decisione strategica → HG.

### Pin delle versioni
File `pyproject.toml` con versioni pin:
```toml
[tool.poetry.dependencies]
python = "^3.11"
vectorbt = "^0.27.0"
ib-insync = "^0.9.86"
# ... ecc
```
**Mai** dependencies senza version pin in produzione.

---

## DR-03 — Data sources

### Priorità per ogni tipo di dato

**Daily equity prices (universe US)**:
1. Yahoo Finance via `yfinance` (FREE, ok per backtest)
2. Alpaca historical (free per account holders)
3. Polygon (paid, alta qualità) — solo se serve davvero

**Macro data**:
1. FRED API (FREE, ufficiale)
2. Yahoo per VIX, term structure

**Option chains (per S2)**:
1. IBKR historical (richiede account)
2. Tradier (paid, ~30$/mo)
3. CBOE direct (limitato, scraping)
4. Polygon options (paid, ~80$/mo)

**News (esistente)**:
- Mantenere stack GDELT + MarketAux + Benzinga

### Quando un dato sorgente fallisce
1. Retry con exponential backoff (3 tentativi)
2. Switch a fallback (es. Yahoo → Alpaca)
3. Log warning + emit metric
4. Se tutti i sorgenti falliscono: **NON inferire dati, NON inventare**. Skip il timestep con flag DATA_UNAVAILABLE.

### Survivorship bias
**Mai** usare universe "as of today" per backtest passati. Per ogni periodo:
- Universe S&P 500: lookup constituents storici (Wikipedia ha snapshot, oppure usa `pandas_datareader`)
- Universe custom: snapshot per quarterly e usa il più recente disponibile a `as_of`

---

## DR-04 — Parameter selection

### Default sempre da letteratura

Quando un parametro è ambiguo:
1. Cerca nei paper canonici citati in `01_strategy_design.md` di `/alembic_v2/`
2. Usa il valore "median" da review letterature (es. lookback 252 giorni = standard)
3. Documenta in `DECISIONS.md` con paper reference

### Parameter tuning: regole rigide

- **In Fase A-D**: parametri fissati da letteratura, MAI cambiati per "fittare meglio"
- **In Fase E (S4)**: ammesso tuning ma documentato come hyperparameter trial
- **In gate 3 (robustness)**: testa varianti per validare, NON per ottimizzare

Se il backtest sotto-performa con parametri da letteratura: **non re-tunare**. Il problema è altrove (data, slippage, look-ahead). Investigare.

### Quando un parametro è inevitabilmente arbitrario
Esempio: "stop loss = 2× ATR" oppure "2.5× ATR"? Letteratura non specifica univocamente.
**Decisione**: scegli il valore middle (2.25), documenta scelta, testa robustness con ±20%.

---

## DR-05 — Testing strategy

### Coverage target per modulo

| Module type | Coverage min | Test priority |
|---|---|---|
| Business logic (signal, sizing, combiner) | 90% | High — property-based |
| Strategy module | 85% | High — golden test data |
| Backtest engine | 90% | Critical — anti-look-ahead |
| Cost model | 85% | High — validation vs literature |
| Glue code (DB, broker adapter) | 60% | Medium — integration |
| Reporting | 50% | Low — visual review |

### Tipi di test

**Unit test** (per funzione/classe):
```python
def test_compute_momentum_signal():
    # Arrange
    prices = create_synthetic_prices(...)
    # Act
    signal = compute_momentum(prices, lookback=252, skip=21)
    # Assert
    assert signal.shape == expected_shape
    assert np.allclose(signal['SPY'].iloc[-1], expected_value, rtol=1e-4)
```

**Property-based test** (con `hypothesis`):
```python
@given(
    weights=st.lists(st.floats(min_value=-1, max_value=1), min_size=2, max_size=20),
    target_vol=st.floats(min_value=0.05, max_value=0.30),
)
def test_vol_targeting_property(weights, target_vol):
    scaled = vol_target(weights, target_vol)
    portfolio_vol = compute_vol(scaled)
    assert portfolio_vol <= target_vol * 1.05  # tolerance
```

**Integration test** (end-to-end di una pipeline):
```python
def test_strategy_full_pipeline_e2e():
    config = load_test_config()
    data = load_test_data()
    result = run_backtest(config, data)
    assert result.total_return is not None
    assert -0.5 < result.sharpe < 5.0  # sanity range
```

**Regression test** (per bug specifici):
```python
def test_regression_issue_42():
    """Bug: signal era look-ahead per ticker delisted mid-period.
    Vedi commit abc123."""
    # ... test che il bug non ricorra
```

### Test data fixtures

Mantenere in `tests/fixtures/`:
- `synthetic_prices.csv`: data sintetica deterministica
- `golden_signals.json`: input → output coppie validate
- `mock_news.jsonl`: news con sentiment annotato manualmente
- `regime_history.csv`: regime per ogni data per testing

Mai test che dipendono da rete live (per riproducibilità).

---

## DR-06 — Git workflow

### Branches
```
main                           ← protected, no direct push
├── phase-A-foundation
├── phase-B-s1-momentum
├── phase-C-s3-momentum
├── phase-D-s2-vrp
├── phase-E-s4-refactor
├── phase-F-combiner
└── phase-G-deployment
```

Ogni phase branch ha sub-feature branches per task:
```
phase-A-foundation
├── feature/T-001-data-loading
├── feature/T-002-backtest-engine
└── ...
```

### Commit policy
- Squash PR (un task = un commit in main dopo merge)
- Commit body include: cosa, perché, test fatti, dipendenze toccate
- Sempre signed-off-by con autore

### PR template
```markdown
## Task: [T-NNN] <title>

### What changed
- File 1: description
- File 2: description

### How to test
```bash
pytest tests/path/
python scripts/validate.py
```

### Acceptance criteria check
- [ ] Criterion 1
- [ ] Criterion 2

### Dependencies / linked tasks
- Depends on: T-NNN
- Unblocks: T-NNN+1

### Notes
- Decisioni documentate in DECISIONS.md
- Known limitations: ...
```

---

## DR-07 — Configuration management

### Hierarchy delle config

```
1. Default values in Python (constanti dei moduli)
2. config/alembic_v2.yaml (globale)
3. config/strategies/<id>.yaml (per strategia)
4. ENV variables (per secrets, no parametri)
5. CLI flags (per scripts one-off)
```

Priorità: dal basso al alto. ENV override config files.

### Secrets

**MAI** in repo:
- API keys (Alpaca, IBKR, MarketAux, FRED, etc.)
- DB passwords
- Tokens (Telegram, etc.)

**Storage corretto**:
- Local dev: file `.env` (gitignored)
- Production: env variables o secrets manager (AWS Secrets, Vault)
- Test: mock o env variables

### Versioning della config

Ogni file YAML ha header obbligatorio:
```yaml
version: "0.1.0"
last_modified: "2026-05-28"
changelog:
  - "0.1.0: initial version"
```

Cambiare un parametro = bump version + entry in changelog.

---

## DR-08 — Database migrations

### Tool: alembic-migrations (sì, omonimo, ironico)

Non confondere con `Alembic the product` (questo progetto).

```bash
# Crea migration
alembic revision -m "add strategy_outputs table"

# Apply
alembic upgrade head

# Rollback
alembic downgrade -1
```

### Naming
`YYYYMMDD_HHMM_<descrizione_breve>.py`

Esempio: `20260528_1430_add_strategy_outputs_table.py`

### Test migrations
Ogni migration ha:
- `upgrade()` testato (creazione)
- `downgrade()` testato (rollback)
- Test di idempotenza (upgrade due volte = nessun errore)

---

## DR-09 — Error handling

### Pattern standard per task background

```python
try:
    result = expensive_operation()
except ExpectedError as e:
    log.warning("Expected error in <context>", exc_info=e)
    return fallback_value
except Exception as e:
    log.error("Unexpected error in <context>", exc_info=e)
    metric_counter("errors_unexpected", tags={"module": "X"}).inc()
    raise  # never silently swallow
```

### Mai usare `except: pass` nudo
Sempre catturare classi specifiche. Se proprio serve catch-all, almeno log + metric.

### Retry logic
Usare `tenacity` library:
```python
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(min=1, max=60),
    retry=retry_if_exception_type(NetworkError),
)
def fetch_from_api(): ...
```

Mai retry su errori non-transient (validation, auth).

### Critical errors → alert immediato
```python
if data_corruption_detected():
    alert_telegram(level=CRITICAL, message=...)
    circuit_breaker.trip()
    raise CriticalSystemError(...)
```

---

## DR-10 — Logging

### Format strutturato

JSON logs ovunque:
```python
log.info(
    "Strategy signal computed",
    extra={
        "strategy_id": "s1_ts_momentum",
        "as_of": "2026-05-28T00:00:00Z",
        "n_active_signals": 12,
        "compute_duration_ms": 250,
    }
)
```

### Livelli

- DEBUG: dettagli interni, solo dev
- INFO: eventi business normali (signal computed, order submitted, ...)
- WARNING: cose anomale ma gestite (retry, fallback, slow query)
- ERROR: errori non gestiti, recuperati
- CRITICAL: errori che richiedono intervento immediato

### Cosa NON loggare
- Secrets (anche se "solo per debug")
- Dati personali / cliente
- Dati di mercato in bulk (overhead)

---

## DR-11 — Performance considerations

### When to optimize
**Mai prematuramente**. Optimize quando:
1. Profile mostra bottleneck specifico
2. Funzionalità è completa e testata
3. Tempo di esecuzione > threshold business (es. backtest > 30 min)

### Standard performance targets

| Operation | Target | Critical if |
|---|---|---|
| Backtest 10 years × 4 strategies | < 30 min | > 2h |
| Walk-forward 10 years | < 2h | > 8h |
| Daily strategy signal computation | < 5 min | > 30 min |
| Risk metrics snapshot | < 30s | > 5 min |
| DB query "decisions last 30d" | < 1s | > 10s |

### Profiling tools
- `cProfile` + `snakeviz` per Python
- `py-spy` per running processes
- `EXPLAIN ANALYZE` per Postgres queries

---

## DR-12 — Quando NON essere "smart"

L'agente è incentivato a essere intelligente. Ma in alcuni casi, smart = bug. Casi specifici:

### Non ottimizzare il codice "perché è elegante"
Esempio: scrivere list comprehension annidate al posto di for loop chiari. Il prossimo sviluppatore (umano o LLM) deve poter leggere.

### Non aggiungere "feature in più" non chiesta
Se il task chiede "implementa S1 signal", non aggiungere "anche S1 con beta-adjustment perché magari serve". Quello è un task separato.

### Non refactor "while you're there"
Se sei in un file per fixare X e vedi Y che potrebbe essere migliorato: **NO**. Open issue per Y, fix solo X.

### Non commentare il codice "per chiarezza"
Codice che ha bisogno di commenti spesso ha bisogno di refactor. Commenti solo per:
- Spiegare "perché" (mai "cosa")
- Link a paper / issue / external doc
- Warning specifici ("non rimuovere questa linea perché ...")

### Non scrivere abstractions premature
3 use case in produzione = abstraction. 1 use case + 2 ipotetici futuri = no abstraction.

---

## DR-13 — Quando un test fallisce

Procedura rigida:

1. **Read the error message** completamente, non solo la prima riga
2. **Identify what's tested**: business logic? glue code? integration?
3. **Is the test correct?**
   - Se test assume comportamento sbagliato → discussion needed → HG-5
   - Se test è ok → bug in codice
4. **Reproduce** isolatamente (1 test, no fixture complesse)
5. **Bisect** se serve
6. **Fix the code, not the test** (salvo errori del test palesi)
7. **Add regression test** se il bug era subtle

**Mai**:
- `@pytest.skip` un test per "andare avanti"
- `assert True` per "passare"
- Modificare expected value senza capire perché era sbagliato

---

## DR-14 — Quando il backtest dà numeri sospetti

Sanity check pre-flight ogni backtest:

```python
SANITY_CHECKS = {
    "SPY_buy_and_hold_2010_2020": {"sharpe_min": 0.5, "sharpe_max": 1.0},
    "60_40_buy_and_hold_2010_2020": {"sharpe_min": 0.6, "sharpe_max": 1.1},
    "TLT_buy_and_hold_2010_2020": {"sharpe_min": 0.3, "sharpe_max": 0.8},
    "random_strategy_2010_2020": {"sharpe_min": -0.3, "sharpe_max": 0.3},
}

def run_sanity_check():
    for name, expected in SANITY_CHECKS.items():
        result = run_simple_backtest(name)
        if not (expected["sharpe_min"] <= result.sharpe <= expected["sharpe_max"]):
            raise SanityCheckFailed(name, result.sharpe, expected)
```

Se sanity fail → STOP, debug engine. Non procedere con strategy testing.

---

## DR-15 — Quando un componente "esiste già diverso da quanto specificato"

Esempio: il doc `02_architecture.md` definisce `BaseStrategy` interface con metodo `compute_target_weights()`. Ma il repo esistente ha già una classe `Strategy` con metodo `generate_signals()`.

**Decision tree**:
1. **Il componente esistente è in produzione?** 
   - Sì → wrappa, non rimpiazza. Crea `BaseStrategy` come adapter che chiama `Strategy.generate_signals()`.
   - No → rinomina/refactor per allinearti al doc nuovo.
2. **Refactor breaking changes?**
   - Sì → HG-11 (decisione strategica)
   - No → procedi, documenta in DECISIONS.md.

---

## DR-16 — Quando una libreria non funziona come sperato

Procedura:
1. Verifica versione installata (`pip show <lib>`)
2. Verifica documentazione **per quella versione esatta** (non latest)
3. Cerca github issues della libreria
4. Se bug confermato → workaround documentato + issue aperta upstream
5. Se è un misunderstanding tuo → fix l'uso, documenta lesson

**Mai**:
- Fork la libreria nel monorepo (overhead enorme)
- Re-implementare la libreria from scratch (overkill)
- Switch a libreria diversa senza valutare costo

---

## DR-17 — Communication con l'utente

Quando l'agente comunica all'utente (output finale, HG, status update):

### Format compatto e azionabile

❌ Cattivo:
> "Ho lavorato sul task T-001 e ho fatto molte cose. Ho installato vectorbt, configurato il data loader, scritto test, eseguito il primo backtest di prova. Tutto sembra funzionare ma ho una piccola domanda..."

✅ Buono:
> **T-001 status: 90% complete**
>
> Done:
> - vectorbt installed (v0.27.0)
> - Data loader implemented at `alembic/backtest/data/loader.py`
> - 5 test passing (`pytest tests/backtest/test_loader.py`)
>
> Blocked on:
> - Yahoo Finance returning empty data for ticker XYZ delisted 2019. Need decision: skip XYZ or fail backtest? → HG-12

### Lingua
- Se utente scrive in italiano → rispondi in italiano
- Codice e docs sempre in inglese
- Variabili e nomi sempre in inglese

### Lunghezza
- Status update: max 5 righe
- HG request: max 15 righe (vedi format in 00)
- Spiegazione tecnica richiesta: dettagliato ma strutturato

---

## DR-18 — Anti-pattern da non commettere mai

Lista nera, da rileggere prima di ogni task.

### Mai

1. **Mai modificare un test per farlo passare senza capire perché falliva**
2. **Mai commentare codice "in case I need it later"** (git mantiene la storia)
3. **Mai disabilitare un check di sicurezza "temporaneamente"**
4. **Mai aggiungere parametro hardcoded "perché ora serve"**
5. **Mai catch + pass su exception**
6. **Mai eseguire ordini live in un test**
7. **Mai usare data sample > training period in OOS validation**
8. **Mai assume che un file esista senza check**
9. **Mai assume internet disponibile in unit test**
10. **Mai loggare secrets, anche temporaneamente**
11. **Mai delete file/table senza backup**
12. **Mai re-run backtest "per vedere se va meglio" senza cambiare nulla**
13. **Mai ottimizzare parametri su data che entrerà in OOS test**
14. **Mai forzare push (`-f`) su main o phase branches**
15. **Mai merge PR senza CI green**
