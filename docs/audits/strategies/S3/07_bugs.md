# S3 — 07 Bug

**Strategia:** S3 `CrossSectionalMomentum` (Residual Momentum)
**Data:** 2026-08-04
**Metodo:** ogni bug è confermato da repro eseguito (`repro_<n>.py`), traccia
statica deterministica, o controesempio matematico/letteratura. Nessun bug
asserito senza conferma.

## Riepilogo bug confermati

| ID | Severità | Luogo | Conferma |
|---|---|---|---|
| BUG-A | CRITICAL | `signal.py:136` (pannello bilanciato) | repro_1 ESEGUITO |
| BUG-B | MED | `strategy.py:36-53` (dead config) | repro_2 ESEGUITO |
| BUG-C | HIGH | `backtest.py:200,209-210` (survivorship) | repro_2 traccia statica |
| BUG-D | MED (latente) | `backtest.py:97` (gate banale) | repro_3 ESEGUITO |
| DV-1 | DESIGN | `signal.py:60` (12-0 vs 12-1) | letteratura (Jegadeesh 1990, Wiest 2022) |

---

## BUG-A — Pannello bilanciato = look-ahead nella selezione delle date (CRITICAL)

**Luogo:** `src/strategies/s3/signal.py:136`
```python
valid_rows = residual.notna().all(axis=1)   # generate_s3_signals
residual_clean = residual[valid_rows]
```

**Descrizione:** una data `t` è ammessa nel backtest iff TUTTI i ticker nel
pannello hanno residual non-NaN a `t`. Il pannello include ticker future-listed
(selezionati come sopravvissuti OGGI, vedi BUG-C). Per `t` precedente al listing
del future-listed, quel ticker ha close=NaN → residual=NaN → la data `t` è
**droppata**. Le date ammissibili sono quindi determinate dai future-listed →
look-ahead nella selezione delle date (identico a S1 BUG-2).

**Controesempio (repro_1):** pannello con SPY + OLD (listato 2010, storia piena) +
FUTURE (IPO 2012-01-02, NaN prima). `generate_s3_signals` ammette la prima data
al **2012-12-19** (≈ FUTURE listing + 252 trading days), non al 2010-12 (dove
OLD era già pienamente osservabile PIT). Il future-listed (non osservabile PIT
prima del 2012) controlla quali date il backtest può usare.

**Output repro_1:**
```
first admitted backtest date: 2012-12-19
expected if no look-ahead (OLD-only observable): ~2010-01-01 + 252td
CONFIRMED: ... leaks future listing info into date selection -> look-ahead.
```

**Impatto:** le finestre WF early sono droppate o skifate; il backtest misura un
pannello che non era osservabile PIT. Invalida il backtest.

## BUG-B — Dead config: `S3Config.from_yaml` mai chiamato, nessun yaml (MED)

**Luogo:** `src/strategies/s3/strategy.py:36-53` (definizione), `backtest.py:37`
+ `backtest.py:146` (uso bare `S3Config()`).

**Descrizione:** `S3Config.from_yaml` è definito ma ha **0 call site** in `src/`;
nessun `config/s3*.yaml` esiste (`ls config/`). Il backtest usa `S3Config()` bare
(2 call sites), quindi la configurazione è hard-coded ai default della dataclass.
Pattern identico a S1 BUG-1 / S2 BUG-D.

**Conferma (repro_2, AST walk):**
```
S3Config.from_yaml defined in strategy.py: True
S3Config.from_yaml call sites in src/: 0
S3Config(...) bare constructor calls in src/: 2
config/s3*.yaml files: []
BUG-B CONFIRMED: True
```

**Impatto:** i parametri (lookback, max_weight, short_decile) non sono
configurabili runtime; qualunque "tuning" richiede edit del codice. Coerente con
`mode=research` ma impedisce A/B testing della variante originale raccomandato
dalla review (2026-07-20) senza riscrivere il default.

## BUG-C — Survivorship universe: `active_at(end)[:50]` con `end=today` (HIGH)

**Luogo:** `src/strategies/s3/backtest.py:200,209-210`
```python
end = date.today()                       # :200
...
active = s3_universe.active_at(end)       # :209
tickers = list(active[:50])               # :210
```

**Descrizione:** il filtro di liquidità PIT (`active_at`, `universe.py:38-83`) è
corretto in sé, ma è applicato **una sola volta alla data finale** (`end=today`),
non a ogni data di rebalance. I 50 sopravvissuti liquidi OGGI sono riusati come
universo su 2000-today. I delisted/dimessi sono assenti → survivorship bias +
look-ahead nella selezione universo.

**Conferma (repro_2 traccia statica):**
```
backtest.py:200:     end = date.today()
backtest.py:209:     active = s3_universe.active_at(end)
backtest.py:210:     tickers = list(active[:50])  # cap at 50 for tractable backtest
```
Il design (#55) richiedeva un universo large/mid US liquido **PIT**; il
market-cap filter è configurato ma non implementato (review §2.2).

**Impatto:** backtest long-biased (i sopravvissuti hanno rendimenti
sistematicamente superiori). Che il 0.148 sia ~0 anche con tailwind di
survivorship è indicatore negativo per la variante di codice.

## BUG-D — Gate `milestone_c_pass` con soglia banale `[0.0, 1.0]` (MED, latente)

**Luogo:** `src/strategies/s3/backtest.py:97`
```python
milestone_c_pass = (0.0 <= oos_sharpe <= 1.0) and gate_report.overall_passed
```

**Descrizione:** il commento a `backtest.py:96` documenta "OOS Sharpe in expected
range [0.4, 0.6]", ma il codice accetta qualunque Sharpe in `[0.0, 1.0]`. Un
Sharpe di **0.0** (zero alpha, strategia che non fa nulla) è accettato dalla
prima congiunzione. Il gate è non-informativo: non può respingere una no-op.

**Conferma (repro_3):**
```
oos_sharpe=+0.000  overall_passed=True  -> milestone_c=True   (zero alpha)
oos_sharpe=+0.148  overall_passed=True  -> milestone_c=True   (actual S3)
oos_sharpe=-0.500  overall_passed=True  -> milestone_c=False  (negative)
CONFIRMED: oos_sharpe=0.0 ... yields milestone_c=True.
```
Lo stesso pattern banale `min_sharpe=0.0` appare nei sub-gate 1/2 (fase 01 §8),
che PASS nonostante Sharpe ~0.

**Impatto (latente):** nel `summary.json` attuale `overall_passed=False` (gate
3/5 FAIL) quindi `milestone_c_pass=False` indipendentemente. MA se gate 3/5
mai passassero, una strategia zero-alpha verrebbe promossa. Il gate non
protegge; la decisione si appoggia interamente sui gate 3/5.

## DV-1 — Segnale 12-0 contaminato dalla short-term reversal (DESIGN, non bug di codice)

**Luogo:** `src/strategies/s3/signal.py:60` `momentum = prices/prices.shift(lookback)-1`
con `lookback=252`.

**Descrizione:** il codice implementa fedelmente 12-0 (momentum 12 mesi **incluso**
il mese corrente). Non è un bug di codice (il codice fa quello che i parametri
dicono), ma è una **scelta di parametro non canonica** che contamina il segnale.

**Conferma (letteratura, fase 03):** Jegadeesh 1990 e la review di Wiest 2022
documentano che il rendimento dell'ultimo mese è dominato dalla **short-term
reversal**, non dal momentum. La convenzione 12-1 (skip ultimo mese, JT 1993,
Carhart 1997, Asness 2013) è standard proprio per isolare il momentum dalla
reversal. Il design originale (#55) usava 12-1 (`log(P[t-21]/P[t-252])`); il
codice usa 12-0. Il segnale S3 contiene quindi la componente reversal a 1m che
il design escludeva — un controesempio matematico: sia `r_12m = r_[t-252,t-21]`
(momentum puro) + `r_[t-21,t]` (reversal). 12-0 = `r_12m + r_last_month`; 12-1 =
`r_12m`. `r_last_month` ha segno **opposto** al momentum (Jegadeesh 1990), quindi
12-0 < 12-1 in valore atteso per i nomi momentum → diluisce/inverte il segnale.

**Impatto:** il segnale S3 è economicamente diverso dal residual momentum
canonico; l'OOS Sharpe 0.148 misura la variante contaminata, non il fenomeno.

---

## Bug non confermati / non ricercati

- **Race conditions**: S3 è offline-only (backtest single-threaded); N/A.
- **Accounting divergences**: NAV MTM corretto nel backtest (`strategy.py:169-175`);
  nessun path live → nessuna divergenza accounting runtime.
- **Float/Decimal**: pesi float, nessuna money-path Decimal in S3.
- **Weekend/off-by-one**: `_should_rebalance` mensile su change-of-month
  (`strategy.py:163-167`); nessun loop calendar-day. Non ricercato in profondità
  (offline).
- **Stale-evidence**: non applicabile (backtest precompute su full causale).

## Sintesi

L'implementazione S3 ha **2 bug di backtest critici/high** (BUG-A look-ahead
pannello bilanciato, BUG-C survivorship), **1 dead config cross-strategy**
(BUG-B), **1 gate banale latente** (BUG-D), e **1 divergenza di design**
documentata dalla letteratura (DV-1, 12-0 vs 12-1). Tutti confermati. A runtime è
morto (fase 06 asse 12: zero trades, zero lifecycle). Il backtest 0.148 è
invalidato da BUG-A + BUG-C e misura la variante contaminata di DV-1.

---
**Stato fase:** 07_bugs = **done**. Prossimo cursore: `S3:08_report`.