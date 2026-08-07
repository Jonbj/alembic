# S1 — 05 Mappatura spec → codice sorgente

**Strategia:** S1 Multi-Lookback Relative Momentum
**Data:** 2026-08-04
**Scope:** ogni componente della specifica (fase 01) → `file:line` nel codice reale, con divergenze esplicite.

## 5.1 Segnale momentum (`src/strategies/s1/signal.py`)

| Componente spec | Codice |
|---|---|
| Rendimento lordo a orizzonte $l$: $r=P_t/P_{t-l}-1$ | `signal.py:78` `lb_ret = prices / prices.shift(lb) - 1` |
| Vol realizzata annualizzata (finestra 63): $\sigma=\sqrt{252}\,\mathrm{std}_{\mathrm{roll}}(63)$ | `signal.py:69-71` `ann_factor=np.sqrt(252); rolling_vol=daily_rets.rolling(vol_window).std()*ann_factor` |
| Vol-normalizzazione: $z_{t,l}=r_{t,l}/\sigma_t$ | `signal.py:79` `vol_norm = lb_ret / rolling_vol` |
| Pesi esponenziali per lookback ($e^{\mathrm{rank}}$, normalizzati) | `signal.py:18-26` `_exponential_lb_weights` |
| Aggregazione pesata + propagazione NaN | `signal.py:74-84` (`signal_raw += w*vol_norm.fillna(0)`; `nan_mask`; `signal_raw[nan_mask]=np.nan`) |
| **Filtro inclusione ticker (look-ahead full-window)** | `signal.py:92-116` (`coverage_ok` con `prices.notna().sum(axis=0)` su **tutta** la finestra; `recent_ok` ultimi 5 rows) |
| Pannello bilanciato (date con tutti i ticker validi) | `signal.py:118-120` `valid_rows = signal_raw.notna().all(axis=1)` |
| Z-score cross-sectionale ($S=(S-\bar S)/s$, ddof=1) | `signal.py:122-132` (`cross_mean`, `cross_std(ddof=1)`, drop degenerate `valid_std`, `signal_zscored`) |
| Output long-format | `signal.py:134-139` |
| Merge segnale + pesi | `signal.py:142-173` `generate_signals` |

## 5.2 Sizing inverso-vol (`src/strategies/s1/sizing.py`)

| Componente spec | Codice |
|---|---|
| Vol sizing (finestra 60): $\sigma_{\text{sizing}}=\sqrt{252}\,\mathrm{std}_{\mathrm{roll}}(60)$ | `sizing.py:27-29` |
| Peso raw $w=\min(\text{target\_vol}/\sigma,\text{max\_weight})$ | `sizing.py:31` `raw_weights=(target_vol/ann_vol).clip(upper=max_weight)` |
| Drop warm-up + long-format | `sizing.py:33-40` |

## 5.3 Selezione / entry / normalizzazione sleeve (`src/strategies/s1/strategy.py`)

| Componente spec | Codice |
|---|---|
| Precomputazione segnali+pesi, pivot wide | `strategy.py:64-84` (`__init__`) |
| Lookup data segnale ≤ as_of | `strategy.py:96-105` |
| Warning stale (>5 giorni trading) | `strategy.py:110-124` |
| Eligibilità: `signal > threshold` (threshold=0.0), long-only | `strategy.py:135-144` |
| **Sizing NON scala con la strength del segnale** (gate binario) | `strategy.py:135-144` (il peso letto è `weights_row[ticker]`, indipendente da `signals_row[ticker]` oltre il gate) |
| Normalizzazione sleeve (se somma>1 → /somma) | `strategy.py:150-152` |
| Rebalance gate MONTHLY | `strategy.py:177-194` `_should_rebalance` |
| Exit posizioni assenti dal target | `strategy.py:220-232` (`__call__`) |
| Entry/adjust verso target_qty | `strategy.py:234-266` |
| NAV = cash + Σ(qty×prezzo) | `strategy.py:196-202` |

## 5.4 Integrazione live / orchestratore (`src/workers/portfolio_scheduler.py`)

| Componente | Codice |
|---|---|
| Build istanza S1 nel path live | `portfolio_scheduler.py:3056-3068` `_build_strategy_instance` → `TimeSeriesMomentum(prices=bars_df, config=S1Config())` |
| Guarda minimo 21 bar | `portfolio_scheduler.py:3065-3067` |
| Attribuzione stop_strategy (S1 vs S4) | `portfolio_scheduler.py:1017-1029` |
| stop_strategy_params S1 {k:3.5, floor:0.06, cap:0.12} | `portfolio_scheduler.py:1065` |
| Regime scale (F8) applicata al sizing | `portfolio_scheduler.py:407-427` |
| Cross-strategy reversal cooldown (S1↔S4) | `portfolio_scheduler.py:2431-2451` |

## 5.5 Stop / risk path (`src/workers/execution.py`, `portfolio_scheduler.py`)

| Componente | Codice |
|---|---|
| Lettura `risk.stop_loss` da trading.yaml | `execution.py:73-82` |
| Stop-loss per-symbol (tier via `_cost_calc.stop_loss_pct`) | `execution.py:557`, `722-730` |
| Stop-loss cooldown Redis (stop_loss_today:{symbol}) | `portfolio_scheduler.py:798-825` |
| **Stato live:** `risk.stop_loss=0.0` → protective stop **disabilitato** (paper); stop_shadow attivo | `config/trading.yaml:182-194` |

## 5.6 Divergenze spec↔codice↔docs

| # | Punto | Spec (01) / Docs | Codice | Tipo |
|---|---|---|---|---|
| D1 | `target_vol` | `docs/strategies.md` tabella param dice **0.15** | `strategy.py:33` = **0.10**; `s1_strategy.yaml` = 0.10 | docs↔code drift |
| D2 | Sizing "∝ signal" | `docs/strategies.md`: "raw_weight ∝ signal × (target_vol/realised_vol)" | `sizing.py:31`: peso = target_vol/ann_vol, **nessun fattore signal**; `strategy.py:135-144`: signal è solo gate | **docs implica scaling per signal, codice no** — divergenza materiale |
| D3 | Look-ahead filtro universo | (non in spec esplicita) | `signal.py:92-116` usa statistiche full-window; **ammesso nel docstring** `signal.py:54-57` | look-ahead bias (per 06/07) |
| D4 | **`config/s1_strategy.yaml` non wired** | `docs/strategies.md` + commenti yaml lo presentano come config di S1 | `portfolio_scheduler.py:3068` usa `S1Config()` **defaults**; `from_yaml` (`strategy.py:38-53`) **mai chiamato** nel path runtime (grep: solo def + doc-reference in `api/routes/strategies.py:53`) | **dead config** — editare il yaml non ha effetto sul live |
| D5 | Backtest condivide i defaults | (n/a) | `backtest.py:39` `s1_config = s1_config or S1Config()` — anche il backtest usa defaults, non yaml | consistente live↔backtest, ma entrambi ignorano yaml |
| D6 | Pannello bilanciato → possibile survivorship-like | (non in spec) | `signal.py:118-120` droppa date dove un ticker incluso manca → bias di pannello | per 06 |

## 5.7 Lettura della divergenza D4 (la più importante)

`config/s1_strategy.yaml` è **documentato** come config di S1 (intestazione `strategy_id: "S1"`, referenziato in `docs/strategies.md` e `src/api/routes/strategies.py:53`), ma **non è caricato** dal path di esecuzione live. `_build_strategy_instance` istanzia `S1Config()` (dataclass defaults, `strategy.py:28-36`). Attualmente i valori yaml == defaults, quindi **nessuna divergenza comportamentale oggi**, ma:

- il file è **dead config**: un operatore che modifica `s1_strategy.yaml` (es. `target_vol`, `lookbacks`) credendo di tarare S1 **non ha alcun effetto**;
- la fonte di verità effettiva è il dataclass `S1Config`, non il yaml — contraddice la governance "config-driven" dichiarata in `CLAUDE.md` e `docs/strategies.md`;
- durante il **freeze 03/08→28/09** questo è particolarmente insidioso: un cambio "nel config" potrebbe essere scambiato per intervento autorizzato quando in realtà è inerte (o, viceversa, qualcuno potrebbe credere di aver cambiato S1 via codice quando il yaml suggerisce altro).

Conferma formale del bug (D4) in `07_bugs.md` con riproduzione deterministica (grep che mostra `from_yaml` mai invocato + trace del path live).

---
**Stato fase:** 05_code_mapping = **done**. Prossimo cursore: `S1:06_implementation_audit`.