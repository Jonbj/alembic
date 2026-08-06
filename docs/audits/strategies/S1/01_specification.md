# S1 — 01 Specificazione funzionale e matematica

**Strategia:** S1 `TimeSeriesMomentum` — "Multi-Lookback Relative Momentum"
**Sorgente:** `src/strategies/s1/strategy.py`, `src/strategies/s1/signal.py`, `src/strategies/s1/sizing.py`
**Config:** `config/s1_strategy.yaml`, `config/strategies.yaml` (allocation 0.50)
**Data:** 2026-08-04 (spec ricostruita direttamente dal sorgente)

> **Nome fuorviante.** La classe si chiama `TimeSeriesMomentum` ma non è il TSMOM canonico di Moskowitz–Ooi–Pedersen (2012), che usa un singolo segnale 12-1 e sizing su vol-target con segno long/short. S1 è un **momentum multi-orizzonte, vol-normalizzato, z-score cross-sectionale, long-only** — un ibrido TS/CS. La documentazione di progetto (`docs/strategies.md`) lo riconosce esplicitamente.

## 1. Universo e configurazione

| Parametro (`S1Config`) | Default | Sorgente |
|---|---|---|
| `lookbacks` | (21, 63, 126, 252) | `strategy.py:30`, `s1_strategy.yaml` |
| `vol_window_signal` | 63 | `strategy.py:31` |
| `vol_window_sizing` | 60 | `strategy.py:32` |
| `target_vol` | 0.10 | `strategy.py:33` |
| `max_weight` | 0.20 | `strategy.py:34` |
| `signal_threshold` | 0.0 | `strategy.py:35` |
| `rebalance_frequency` | MONTHLY | `strategy.py:36` |

Universo: la watchlist di `config/trading.yaml` (~72 simboli + ADR), filtrato per liquida; filtro di copertura applicato dentro `compute_signal` (vedi §4).

## 2. Segnale — matematica esatta

Sia $P_{t}^{(i)}$ il prezzo di chiusura del titolo $i$ al giorno $t$. Siano i lookback $L=\{21,63,126,252\}$.

**Rendimento lordo a orizzonte $l$:**
$$ r^{(i)}_{t,l} = \frac{P^{(i)}_{t}}{P^{(i)}_{t-l}} - 1 $$

**Volatilità realizzata annualizzata (finestra mobile `vol_window_signal=63`):**
$$ \sigma^{(i)}_{t} = \sqrt{252}\cdot \mathrm{std}_{\mathrm{roll}}\!\left(\Delta P/P,\; 63\right)_{t} $$

**Rendimento vol-normalizzato:**
$$ z^{(i)}_{t,l} = \frac{r^{(i)}_{t,l}}{\sigma^{(i)}_{t}} $$

**Pesi esponenziali per lookback** (`_exponential_lb_weights`, `signal.py:18-26`): ordinati per lookback crescente, pesi $\propto e^{k}$ con $k=0,1,2,3$ per il lookback più corto→più lungo, normalizzati a somma 1:
$$ w_l = \frac{e^{\mathrm{rank}(l)}}{\sum_{l'} e^{\mathrm{rank}(l')}} \quad (\text{rank}: 21\to0,\;63\to1,\;126\to2,\;252\to3) $$
⇒ i lookback più lunghi pesano molto di più (peso relativo $e^3:e^0 \approx 20:1$ tra 252d e 21d).

**Segnale grezzo aggregato** (`signal.py:77-84`):
$$ S^{(i)}_{t,\text{raw}} = \sum_{l\in L} w_l \cdot z^{(i)}_{t,l} $$
con propagazione NaN: se un qualsiasi componente $z^{(i)}_{t,l}$ è NaN (es. lookback non ancora disponibile), l'intero $S^{(i)}_{t,\text{raw}}$ diventa NaN (`signal.py:80-84`).

**Z-score cross-sectionale** (`signal.py:122-132`), calcolato **per ogni data $t$** sull'insieme dei titoli inclusi:
$$ \bar S_{t} = \frac{1}{N_t}\sum_i S^{(i)}_{t,\text{raw}}, \qquad
   s_t = \mathrm{std}_t(S_{\cdot,\text{raw}},\;ddof=1) $$
$$ \boxed{\;S^{(i)}_t = \frac{S^{(i)}_{t,\text{raw}} - \bar S_t}{s_t}\;} $$

Date degeneri ($s_t \le 10^{-12}$ o NaN) sono droppate (`signal.py:127-130`).

## 3. Selezione (entry) e sizing

In `compute_target_weights` (`strategy.py:135-153`), per la data di lookup $t^*$ (la data di segnale precomputato $\le$ `as_of`):

- **Eligibilità segnale:** il titolo $i$ entra nel target sse $S^{(i)}_{t^*} > \text{threshold}$ con `threshold = 0.0`.
  - Essendo $S$ uno z-score, `>0` significa "momentum sopra la media cross-sectionale". **Long-only**: nessun short.
  - **La magnitudo del segnale NON scala la posizione** — il segnale è solo un gate binario (sopra/sotto 0). Il sizing è indipendente (vedi sotto).

- **Sizing inverso-vol** (`sizing.py:8-40`):
  $$ w^{(i)}_{\text{raw}} = \min\!\left(\frac{\text{target\_vol}}{\sigma^{(i)}_{t,\text{sizing}}},\; \text{max\_weight}\right), \quad \sigma^{(i)}_{t,\text{sizing}}=\sqrt{252}\,\mathrm{std}_{\mathrm{roll}}(\Delta P/P,\,60)_t $$
  con `target_vol=0.10`, `max_weight=0.20`, `vol_window_sizing=60`.

- **Normalizzazione sleeve** (`strategy.py:150-152`): se $\sum_i w^{(i)}_{\text{raw}} > 1.0$, si riscala proporzionalmente a 1.0:
  $$ w^{(i)} = \frac{w^{(i)}_{\text{raw}}}{\sum_j w^{(j)}_{\text{raw}}} \quad (\text{se somma}>1) $$

- **Contratto sleeve:** i pesi sono sleeve-local; l'orchestratore li scala per `allocation_pct=0.50` → contributo di portafoglio.

## 4. Filtro di inclusione ticker (universo dinamico) — **punto critico**

`compute_signal` (`signal.py:92-116`) droppa i ticker prima dello z-score usando statistiche su **tutta la finestra**:

- `coverage_ok`: `prices.notna().sum(axis=0) >= 0.75 × len(prices)` — copertura ≥75% sull'**intera** finestra passata+presente del pannello passato a `compute_signal`.
- `recent_ok`: almeno un prezzo non-NaN negli ultimi 5 rows.
- `keep_rows` = tutte le date in cui **tutti** i ticker inclusi hanno segnale non-NaN (`signal.py:118-120`, pannello bilanciato).

> **⚠️ Look-ahead ammesso dal sorgente stesso.** Docstring `signal.py:54-57`:
> *"Ticker inclusion uses full-window statistics (coverage ratio plus a recent-price check). This is a known, accepted look-ahead in backtests; live usage feeds the strategy pre-computed bars up to the current date."*
>
> La copertura 75% è calcolata sull'intero `prices` passato (che nel backtest include tutto lo storico futuro). Un ticker che oggi non ha 75% di copertura ma la raggiungerà in futuro è incluso/escluso usando informazione futura. **Questo è look-ahead bias nella selezione dell'universo.** Registrato come fatto di spec; sarà confermato/quantificato in `06_implementation_audit` e `07_bugs`.

## 5. Rebalance ed esecuzione

- **Frequenza:** `MONTHLY` (`_should_rebalance`, `strategy.py:177-194`): ribilancia il primo tick di un mese diverso dall'ultimo rebalance.
- **Exit:** chiude le posizioni assenti dal nuovo target (`strategy.py:220-232`) con SELL.
- **Entry/adjust:** per ogni ticker nel target, target_qty = (NAV × w) / prezzo; delta vs posizione corrente → BUY/SELL (`strategy.py:234-266`). Soglia di micro-movimento `1e-4`.
- **Lookup signal** = data precomputata più recente ≤ `as_of`; warning se >5 giorni di mercato stale (`strategy.py:110-124`).
- **NAV:** cash + Σ(posizione × prezzo corrente) (`strategy.py:196-202`).

## 6. Precomputazione

Il costruttore precomputa segnali e pesi su **tutta** la storia passata e fa pivot wide (`strategy.py:64-84`); `__call__` fa solo lookup. ⇒ nel backtest, la matrice dei segnali è costruita una volta sull'intero storico (rafforza l'esposizione al look-ahead del §4).

## 7. Divergenze spec↔docs già notate (per fasi successive)

| Punto | `docs/strategies.md` | Sorgente | Divergenza |
|---|---|---|---|
| `target_vol` | "0.15" nella tabella param | `0.10` (`strategy.py:33`, `s1_strategy.yaml`) | doc dice 0.15, codice 0.10 |
| Pesi lookback | "1×, e×, e²×, e³×" | confermato (`signal.py:18-26`) | OK |
| Sizing | "raw_weight ∝ signal × (target_vol/realised_vol)" | peso NON moltiplicato per signal (signal è solo gate) | **doc implica scaling per signal, codice no** — divergenza materiale |

Queste divergenze sono findings per `05_code_mapping`/`06_implementation_audit`; riportate qui per traccia.

---
**Stato fase:** 01_specification = **done**. Prossimo cursore: `S1:02_hypothesis`.