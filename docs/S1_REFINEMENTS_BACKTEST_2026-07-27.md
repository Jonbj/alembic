# S1 momentum refinements — backtest comparativo (evidenza per il flip #27)

**Data:** 2026-07-27 · **Issue:** #33 (verify/implement + comparison) → decisione #27 (PO-6 flip)
**Branch/codice:** `s1-refinements-2026-07-12` (flag-gated, default OFF) · **Script:** `scripts/compare_s1_variants.py`

## TL;DR — raccomandazione: **NON flippare (tieni i flag OFF)**

Su questo panel nessuna variante batte la baseline in modo **materiale o decision-grade**. Due refinements (`skip-month`, `cap-after-normalization`) fanno **peggio**; `absolute-filter` è l'unica marginalmente positiva (+0.052 Sharpe) ma dentro il rumore per un backtest senza costi e su un campione rialzista. `absolute-filter` resta l'**unico candidato** a un eval serio (il suo beneficio vero è la protezione downside, non catturata dall'OOS Sharpe qui).

## Metodo

- **Panel:** 96 simboli (watchlist), **2020-07-27 → 2026-07-27** (1507 barre daily, IEX, adjustment ALL).
- **Walk-forward:** in-sample 504d / out-of-sample 126d.
- **5 varianti** (tutte partono da `S1Config`, i refinements sono flag-gated default OFF):
  - `baseline` — comportamento attuale in produzione.
  - `skip21` — lookback skip-month (`skip_days=21`, lookbacks 63/126/252): salta l'ultimo mese per evitare short-term reversal (12-1 classico).
  - `absfilter` — dual/absolute momentum (`absolute_filter=True`): tiene solo nomi con momentum assoluto positivo.
  - `skip21+abs` — combinazione.
  - `skip21+abs+capafter` — + `cap_after_normalization` (applica il cap di concentrazione DOPO la normalizzazione dei pesi).

### ⚠️ Limiti (P0-01, dichiarati nello script) — evidenza SOLO RELATIVA

- **Costi non modellati** (no commissioni/slippage).
- **Same-bar fills.**
- **Filtro sparse-ticker con look-ahead** (usa statistiche full-window per selezionare i ticker).
- **Universo survivorship-lite**, campione **bull-heavy** (2020-2026 prevalentemente rialzista).

→ Trattare come confronto **relativo tra varianti**, mai come validazione assoluta.

## Risultati

| variante | OOS Sharpe | Δ vs baseline | milestone B |
|---|---|---|---|
| **baseline** | 1.554 | — | ❌ |
| skip21 | 1.529 | **−0.025** | ❌ |
| **absfilter** | **1.606** | **+0.052** | ❌ |
| skip21+abs | 1.560 | +0.006 | ❌ |
| skip21+abs+capafter | 1.521 | **−0.033** | ❌ |

## Lettura

1. **Nessuna variante supera milestone B** (nemmeno la baseline) → nessuna è validazione assoluta su questo panel.
2. **Spread ~0.085 Sharpe** su 5 varianti → **entro il rumore** dati i limiti (no costi, look-ahead nella selezione, campione rialzista).
3. **`skip-month` e `cap-after-normalization` peggiorano** (−0.025, −0.033) → escludibili con confidenza.
4. **`absolute-filter` è l'unica positiva** (+0.052) e la direzione è coerente con la teoria (il dual-momentum protegge nei regimi negativi). Ma su un panel rialzista il suo beneficio — riduzione del drawdown nei bear — **non emerge nell'OOS Sharpe**, quindi +0.05 **non è decision-grade da solo**.

## Prossimi passi

- **Decisione #27 su evidenza corrente: no-flip.** Tieni `skip_days=0`, `absolute_filter=False`, `cap_after_normalization=False` (default attuali).
- **Se si vuole perseguire `absolute-filter`:** serve un eval dedicato prima di qualsiasi flip — costi modellati + decomposizione return/drawdown + campione pesato sui regimi bear (2022) — per misurare la protezione downside, che è il suo vero razionale.

## Riproduzione

```
# dal worktree s1-refinements-2026-07-12, con le chiavi Alpaca in env:
set -a; . /path/to/.env; set +a
./.venv/bin/python scripts/compare_s1_variants.py
# report → reports/s1_variants/comparison_<date>.md
```
