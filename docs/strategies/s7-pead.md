# S7 — PEAD (Post-Earnings Announcement Drift)

> ⚠️ **SHELVED 2026-07-03 — gate ALPHA-A5 FAIL conclusivo.** Su 96 eventi reali (FMP,
> Gen–Mag 2026) il drift raw +1.96% è interamente beta SPY (excess +0.05%, mediana
> −1.07%) più 5 outlier; nessuna dose-response per magnitudine della surprise; universo
> small/mid non testato (0 eventi). Report:
> `reports/s7_backtest/ALPHA_A5_gate_report_2026-07-03_fmp.md` · audit in
> `strategy_lifecycle_audit`. Riapertura solo via decisione PO (universo small/mid o POC
> transcript-tone ALPHA-A3). Il resto di questo documento descrive l'implementazione,
> che resta in repo come mattone di S9/vettore B.
>
> **Aggiornamento 2026-07-04 (corretto in serata):** POC revival IN CORSO. POC-1
> (small/mid PEAD): primo run INCONCLUSIVE_DATA (n=15 < 30, campione 600 simboli
> alfabetici) — in ri-esecuzione su universo completo. POC-2 (transcript tone):
> in corso via Alpha Vantage `EARNINGS_CALL_TRANSCRIPT` free tier (i transcript FMP
> richiedono Ultimate, non acquistato; il primo run seguiva la versione pre-correzione
> del piano). Piano: `docs/superpowers/plans/2026-07-04-s7-revival-resume.md`.
> Esito e decisione PO entro 2026-08-01.


## Razionale

Il PEAD è una delle anomalie di mercato più robuste documentate in letteratura finanziaria (Ball & Brown 1968, Foster et al. 1984). Dopo una sorpresa positiva negli earnings, il prezzo non incorpora immediatamente tutta l'informazione: c'è un drift positivo misurabile nei 60 giorni successivi. S7 cattura questo effetto usando LLM per classificare gli 8-K filing SEC.

## Pipeline

```
SEC EDGAR API (ogni 30 min) → run_sec_edgar_ingestion_worker
       ↓
run_pead_ingestion_worker (+5 min offset) → Ollama LLM classification
       ↓
pead_signals table (PostgreSQL)
       ↓
Portfolio Orchestrator → weight target S7
```

## Parametri

| Parametro | Valore | Note |
|-----------|--------|------|
| Allocazione target | 15% | del portfolio totale |
| Score minimo | 0.3 | soglia per generare segnale |
| Freshness massima | 4 ore | filing più vecchi ignorati |
| Schedule | ogni 30 min | 14:05, 14:35, ... 21:05 UTC |
| Queue | inference | single-process Ollama |
| Modello LLM | Ollama (locale) | classificazione 8-K text |

## Classificazione 8-K

Il worker estrae il testo del filing, lo passa all'LLM con prompt DK-CoT, ottiene:
- `direction`: positive / negative / neutral
- `confidence`: 0.0–1.0
- `category`: earnings_beat / earnings_miss / guidance_up / guidance_down / other

`score = direction_sign × confidence`

## Integrazione con Portfolio Orchestrator

S7 espone `compute_target_weights(pead_signals) → dict[str, float]`. Il segnale viene aggregato con S1 e S4 dal `PortfolioOrchestrator`:

```python
# Allocazioni attive (da config/strategies.yaml):
#   S1: allocation_pct=0.50
#   S4: allocation_pct=0.10
#   S7: allocation_pct=0.15
```

## Stato

- **Introdotto**: 2026-06-07
- **Stato**: `research` / R&D/contained — NON nel PortfolioOrchestrator (P0-13, commit `6d86d3f`). Nonostante `allocation_pct=0.15` nel YAML di configurazione, S7 non è wired nell'orchestratore. Promozione bloccata fino al completamento dei gate di validazione sotto.
- **Beat task**: `pead-ingestion` in `src/workers/celery_app.py`
- **Worker**: `src/workers/pead_worker.py`
- **Routes**: `src/api/routes/pead_routes.py`
- **Migration**: `migrations/021_*` e `migrations/022_*`

## Gate di validazione (da completare)

| Gate | Soglia | Stato |
|------|--------|-------|
| IS IC > 0 | IC > 0 su in-sample | Da misurare |
| OOS IC > 0 | IC > 0 su out-of-sample | Da misurare |
| Sharpe OOS > 0.3 | — | Da misurare |

S7 è in paper trading fino al completamento del gate report in `reports/s7_backtest/`.
