# GDELT A/B Test — Design Spec

**Data:** 2026-05-04
**Status:** Approvato — pronto per implementazione

---

## Contesto e Obiettivo

Fase 2 richiede un gate empirico prima di attivare GDELT come fonte dati in produzione: la pipeline GDELT→FinBERT deve dimostrare un incremento di Sharpe ratio ≥ 0.10 rispetto alla baseline senza segnali LLM.

Questo script è uno script di analisi offline, non parte della pipeline di produzione. Legge dati storici da GDELT, calcola segnali FinBERT, recupera prezzi storici da yfinance e confronta le performance delle due strategie.

**Gate di promozione:** `delta_Sharpe = Sharpe_GDELT − Sharpe_baseline ≥ 0.10` → PASS  
Se FAIL, GDELT non viene integrato nella pipeline di produzione.

---

## Sezione 1 — Architettura

### File coinvolti

| File | Ruolo |
|------|-------|
| `scripts/gdelt_ab_test.py` | Entry point CLI — orchestra fetch, scoring, backtest, report |
| `src/analysis/backtest.py` | Funzioni pure: `compute_sharpe()`, `compute_signal_returns()`, `run_ab_comparison()` |
| `tests/analysis/test_backtest.py` | Unit test delle funzioni pure |
| `src/connectors/gdelt.py` | Esteso con `fetch_historical()` per query date-range |

### Dipendenze esterne

- `yfinance` — prezzi OHLCV storici (già in uso nel progetto o da aggiungere a `requirements.txt`)
- `transformers` + `torch` — FinBERT per inferenza offline
- Librerie già presenti: `numpy`, `scipy`, `pandas`

### Non dipende da

- Redis / PostgreSQL / Celery (nessuna infrastruttura richiesta per eseguire lo script)
- LLM ensemble dell'ensemble di produzione (usa solo FinBERT come modello di scoring)

---

## Sezione 2 — Data Flow

```
[GDELT API] ──► fetch_historical(symbol, start, end)
                     │ chunked by month (≤12 req/symbol)
                     ▼
              [list[NewsItem]]
                     │
                     ▼
              [FinBERT offline]
              score = polarity × confidence
                     │
                     ▼
              [Daily aggregation]
              score_day = mean(signal_scores for day)
                     │
                     ▼
              [yfinance] ──► prices OHLCV (adj close)
                     │
                     ▼
              [Forward returns]
              fwd_ret[t] = (close[t+horizon] − close[t]) / close[t]
                     │
                     ├──► [GDELT strategy]
                     │    returns[t] = fwd_ret[t] × sign(score_day[t])
                     │    (long if score>0, short if score<0, neutral if score_day=0.0)
                     │
                     └──► [Baseline strategy]
                          returns[t] = fwd_ret[t]  (buy & hold, fully invested)
                                │
                                ▼
                         [compute_sharpe()]
                         Sharpe = mean(returns) / std(returns) × √252
                                │
                                ▼
                         [Gate decision]
                         delta_Sharpe ≥ threshold → PASS / FAIL
```

### Aggregazione giornaliera dei segnali

Più articoli GDELT per simbolo per giornata → un singolo score giornaliero:

```python
score_day = np.mean([s for s in daily_scores])  # media semplice
```

Se nessun articolo per un dato giorno: `score_day = 0.0` (neutro — no trade).

### Calcolo forward return

- Orizzonte configurabile via `--horizon` (default: `1` giorno di trading)
- Formula: `fwd_ret[t] = (adj_close[t + horizon] − adj_close[t]) / adj_close[t]`
- Gli ultimi `horizon` giorni vengono scartati (nessun forward return calcolabile)

---

## Sezione 3 — Gate Logic e Metriche

### Gate primario

```python
delta_Sharpe = sharpe_gdelt - sharpe_baseline
passed = delta_Sharpe >= threshold  # default: 0.10
```

### Metriche riportate

Per ciascun simbolo e per l'aggregato sull'universo:

| Metrica | Descrizione |
|---------|-------------|
| `sharpe_baseline` | Sharpe della strategia buy&hold |
| `sharpe_gdelt` | Sharpe della strategia GDELT-driven |
| `delta_sharpe` | Differenza (gate primario) |
| `composite_ic` | IC B4 dei segnali FinBERT (riusa `compute_composite_ic`) |
| `coverage_pct` | % di giorni trading con almeno un articolo GDELT |
| `n_signals` | Numero totale di segnali (articoli) processati |
| `n_trading_days` | Giorni di trading nel periodo |
| `gate_passed` | `true` / `false` per ogni simbolo |
| `gate_passed_overall` | `true` se la media pesata delta_Sharpe supera la soglia |

### Aggregazione multi-simbolo

Il gate finale sull'universo usa la media semplice del delta_Sharpe:

```python
overall_delta_sharpe = np.mean([r.delta_sharpe for r in symbol_results])
gate_passed_overall = overall_delta_sharpe >= threshold
```

---

## Sezione 4 — Interfaccia CLI e Output

### Comando

```bash
python scripts/gdelt_ab_test.py \
  --symbols AAPL MSFT GOOGL NVDA SPY QQQ \
  --start 2024-01-01 --end 2024-12-31 \
  --horizon 1 \
  --threshold 0.1 \
  --output reports/gdelt_ab_2024.json
```

### Parametri CLI

| Parametro | Default | Descrizione |
|-----------|---------|-------------|
| `--symbols` | (required) | Lista di ticker da analizzare |
| `--start` | (required) | Data inizio `YYYY-MM-DD` |
| `--end` | (required) | Data fine `YYYY-MM-DD` |
| `--horizon` | `1` | Forward return horizon in giorni di trading |
| `--threshold` | `0.1` | Delta Sharpe minimo per gate PASS |
| `--min-confidence` | `0.3` | Confidence minima FinBERT: articoli con `confidence < min_confidence` sono esclusi dall'aggregazione giornaliera |
| `--output` | `stdout` | Path file JSON output (opzionale) |

### Formato output JSON

```json
{
  "run_date": "2026-05-04",
  "period": {"start": "2024-01-01", "end": "2024-12-31"},
  "config": {"horizon": 1, "threshold": 0.1, "min_confidence": 0.3},
  "gate_passed_overall": true,
  "overall_delta_sharpe": 0.23,
  "symbols": {
    "AAPL": {
      "sharpe_baseline": 0.82,
      "sharpe_gdelt": 1.14,
      "delta_sharpe": 0.32,
      "composite_ic": 0.043,
      "coverage_pct": 87.3,
      "n_signals": 1240,
      "n_trading_days": 252,
      "gate_passed": true
    }
  }
}
```

---

## Sezione 5 — Estensione `GDELTConnector`

Il connettore attuale supporta solo `timespan` relativo (es. `"15min"`). Serve un metodo per query storiche su date assolute.

### Nuovo metodo `fetch_historical`

```python
async def fetch_historical(
    self,
    start_date: datetime,
    end_date: datetime,
    max_records_per_chunk: int = 250,
) -> AsyncIterator[NewsItem]:
    """Fetch articles in [start_date, end_date] by chunking into monthly windows."""
```

GDELT non espone un endpoint di range date nativo — si simula iterando mese per mese con il parametro `STARTDATETIME`/`ENDDATETIME` dell'API Doc2.0:

```
?query=AAPL&mode=artlist&STARTDATETIME=20240101000000&ENDDATETIME=20240131235959&maxrecords=250
```

### Chunking

- Chunk size: 1 mese (≤ 12 chiamate per simbolo per anno)
- Rate limiting: `asyncio.sleep(1.0)` tra chunk per rispettare i limiti GDELT

---

## Sezione 6 — Testing

### Funzioni pure (unit test, nessuna rete)

`tests/analysis/test_backtest.py` copre:

- `compute_sharpe(returns)`: caso base, returns tutti zero, singolo elemento
- `compute_signal_returns(scores, fwd_returns, min_confidence)`: segnali positivi/negativi/neutri, coverage pct
- `run_ab_comparison(signal_returns, baseline_returns)`: delta_Sharpe, gate pass/fail

### Mocking delle fonti esterne

I test di integrazione in `scripts/` usano fixture che restituiscono dati pre-calcolati:
- GDELT: lista statica di `NewsItem`
- yfinance: `pd.DataFrame` con prezzi sintetici
- FinBERT: patch del tokenizer/model per ritornare logits deterministici

### Test di regressione

Un test verifica che `compute_composite_ic()` (riusato dal modulo `src/performance/ic.py`) non sia stato modificato in modo incompatibile con i segnali FinBERT.

---

## Note Implementative

1. **FinBERT device**: usa `torch.device("cuda" if torch.cuda.is_available() else "cpu")` — lo script funziona sia su GPU che CPU.
2. **Memoria**: con universo di 6 simboli e 1 anno di dati, il carico in RAM è trascurabile (< 50 MB).
3. **Progressbar**: usa `tqdm` per feedback durante il fetch GDELT (può richiedere 1-2 min per simbolo).
4. **Errori GDELT**: se un chunk ritorna errore HTTP, logga il warning e continua — non interrompere l'intera run.
5. **yfinance cache**: i prezzi vengono scaricati una sola volta e salvati in un DataFrame in memoria per la durata dello script.
6. **Stale spec check**: questo script è standalone; non interagisce con Redis, PostgreSQL o Celery. Se l'infrastruttura di produzione cambia, questo script non è impattato.
