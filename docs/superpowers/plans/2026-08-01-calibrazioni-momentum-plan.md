# Calibrazioni C1-C3 — modulo puro di momentum Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Il motore di calcolo delle calibrazioni C1-C3: segnale di momentum, formazione del portafoglio long-only, rendimenti di periodo e statistiche riassuntive.

**Architecture:** Un modulo **puro**, senza I/O. Riceve serie di prezzi già caricate e restituisce numeri. L'orchestratore che scarica da Alpaca e scrive i risultati lo scrive il revisore.

**Tech Stack:** Python 3, pytest (`uv run pytest`), solo libreria standard (`statistics`, `math`). Nessuna dipendenza nuova.

**Spec:** `docs/superpowers/specs/2026-08-01-calibrazioni-backtest-design.md`

**Pre-registrazione che vincola i risultati:** `docs/evidence/PREREGISTRAZIONE_BACKTEST_S1.md`

---

## Struttura dei file

| file | responsabilità |
|---|---|
| `src/analysis/calibration/__init__.py` | pacchetto |
| `src/analysis/calibration/momentum.py` | le quattro funzioni pure |
| `tests/analysis/test_calibration_momentum.py` | test con fixture in memoria |

**Regola di isolamento:** l'esecutore crea e modifica **solo** questi tre file. Non tocca
`src/backtest/`, `src/workers/`, `src/strategies/`, `src/store/`, `config/`, `docs/evidence/`,
`scripts/`.

**Una scelta di progetto da capire prima di scrivere.** Le funzioni ragionano su **posizioni in una
lista ordinata di giorni di borsa**, non su date di calendario. «Lookback di 252 giorni» in
letteratura significa 252 *giorni di borsa*, e sottrarre 252 giorni di calendario darebbe un
risultato diverso e sbagliato. Per questo `momentum_scores` riceve la lista ordinata delle date e un
indice, invece di una data.

---

## Task 1: Struttura del pacchetto

**Files:**
- Create: `src/analysis/calibration/__init__.py`

- [ ] **Step 1: Creare il pacchetto**

⚠️ Usa `>>` o crea il file solo se assente. `src/analysis/` **esiste già** e contiene altro: non
toccare `src/analysis/__init__.py`.

```bash
cd /home/stefano/Documents/Projects/Alembic
mkdir -p src/analysis/calibration
printf '"""Calibrazioni del programma di backtest: moduli puri, nessun I/O."""\n' > src/analysis/calibration/__init__.py
```

- [ ] **Step 2: Verificare di non aver toccato il pacchetto padre**

```bash
git status --short src/analysis/
```

Atteso: compare **solo** `src/analysis/calibration/`. Se compare `src/analysis/__init__.py` come
modificato, ripristinalo con `git checkout src/analysis/__init__.py`.

- [ ] **Step 3: Commit**

```bash
git add src/analysis/calibration/__init__.py
git commit -m "chore(calibration): struttura del pacchetto"
```

---

## Task 2: Segnale di momentum (TDD)

**Files:**
- Create: `src/analysis/calibration/momentum.py`
- Test: `tests/analysis/test_calibration_momentum.py`

- [ ] **Step 1: Scrivere i test che falliscono**

Contenuto integrale di `tests/analysis/test_calibration_momentum.py`:

```python
"""Motore di calibrazione: segnale, selezione, rendimenti, statistiche."""
import pytest

from src.analysis.calibration.momentum import momentum_scores


def test_momentum_e_il_rendimento_fra_due_posizioni():
    """12-2: dal giorno idx-skip-lookback al giorno idx-skip."""
    closes = {"AAA": {i: 100.0 for i in range(300)}}
    closes["AAA"][10] = 100.0   # inizio finestra: 273 - 21 - 242 = 10
    closes["AAA"][252] = 150.0  # fine finestra: 273 - 21 = 252
    out = momentum_scores(closes, idx=273, lookback=242, skip=21)
    assert out["AAA"] == pytest.approx(0.50)


def test_skip_esclude_il_periodo_recente():
    """Il movimento DOPO idx-skip non deve entrare nel punteggio."""
    closes = {"AAA": {i: 100.0 for i in range(300)}}
    closes["AAA"][10] = 100.0
    closes["AAA"][252] = 150.0
    closes["AAA"][273] = 10.0   # crollo recente: dentro lo skip, va ignorato
    out = momentum_scores(closes, idx=273, lookback=242, skip=21)
    assert out["AAA"] == pytest.approx(0.50)


def test_simbolo_con_storia_insufficiente_e_escluso():
    """Niente punteggio inventato per chi non ha abbastanza storia."""
    closes = {
        "AAA": {i: 100.0 for i in range(300)},
        "BBB": {i: 100.0 for i in range(260, 300)},  # troppo corto
    }
    out = momentum_scores(closes, idx=273, lookback=242, skip=21)
    assert "AAA" in out
    assert "BBB" not in out


def test_prezzo_iniziale_nullo_o_assente_esclude_il_simbolo():
    closes = {
        "AAA": {i: 100.0 for i in range(300)},
        "BBB": {i: 100.0 for i in range(300)},
        "CCC": {i: 100.0 for i in range(300)},
    }
    closes["BBB"][10] = 0.0     # divisione per zero
    del closes["CCC"][252]      # buco nella serie
    out = momentum_scores(closes, idx=273, lookback=242, skip=21)
    assert set(out) == {"AAA"}


def test_indice_troppo_piccolo_da_dizionario_vuoto():
    """Se la finestra andrebbe prima dell'inizio della serie, nessun punteggio."""
    closes = {"AAA": {i: 100.0 for i in range(300)}}
    assert momentum_scores(closes, idx=100, lookback=242, skip=21) == {}
```

- [ ] **Step 2: Eseguire e vedere il fallimento giusto**

```bash
cd /home/stefano/Documents/Projects/Alembic
uv run pytest tests/analysis/test_calibration_momentum.py -v
```

Atteso: `ModuleNotFoundError: No module named 'src.analysis.calibration.momentum'`.

- [ ] **Step 3: Implementare**

Contenuto integrale di `src/analysis/calibration/momentum.py`:

```python
"""Motore di calibrazione del momentum. Modulo puro: nessun I/O.

Le funzioni ragionano su POSIZIONI in una lista ordinata di giorni di borsa, non
su date di calendario: "lookback 252" in letteratura significa 252 giorni di
BORSA, e sottrarre giorni di calendario darebbe un risultato diverso e sbagliato.
"""
from __future__ import annotations

import math
import statistics


def momentum_scores(
    closes: dict[str, dict[int, float]],
    idx: int,
    lookback: int,
    skip: int,
) -> dict[str, float]:
    """Rendimento di formazione fra due posizioni della serie.

    Convenzione 12-2: lookback=242, skip=21 (circa 12 mesi saltando l'ultimo).

    Args:
        closes: {simbolo: {posizione: prezzo di chiusura}}.
        idx: posizione della data di valutazione.
        lookback: ampiezza della finestra di formazione, in giorni di borsa.
        skip: giorni di borsa recenti da escludere.

    Returns:
        {simbolo: rendimento di formazione}. Un simbolo senza entrambi gli
        estremi, o con prezzo iniziale nullo, viene ESCLUSO — mai stimato.
    """
    fine = idx - skip
    inizio = fine - lookback
    if inizio < 0:
        return {}

    out: dict[str, float] = {}
    for sym, serie in closes.items():
        p0 = serie.get(inizio)
        p1 = serie.get(fine)
        if p0 is None or p1 is None or p0 == 0:
            continue
        out[sym] = p1 / p0 - 1.0
    return out
```

- [ ] **Step 4: Verde**

```bash
uv run pytest tests/analysis/test_calibration_momentum.py -v
```

Atteso: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add src/analysis/calibration/momentum.py tests/analysis/test_calibration_momentum.py
git commit -m "feat(calibration): segnale di momentum su posizioni di borsa

Ragiona su posizioni in una lista di giorni di borsa, non su date di calendario:
'lookback 252' in letteratura significa 252 giorni di borsa. Un simbolo senza
entrambi gli estremi della finestra viene escluso, mai stimato."
```

---

## Task 3: Selezione del paniere long-only (TDD)

**Files:**
- Modify: `src/analysis/calibration/momentum.py`
- Modify: `tests/analysis/test_calibration_momentum.py`

- [ ] **Step 1: Test in coda al file**

```python
from src.analysis.calibration.momentum import select_top


def test_seleziona_i_migliori_n():
    scores = {"AAA": 0.5, "BBB": 0.1, "CCC": 0.9, "DDD": -0.2}
    assert select_top(scores, n_top=2) == ("CCC", "AAA")


def test_pareggio_risolto_alfabeticamente_per_determinismo():
    """Due punteggi identici devono dare sempre lo stesso paniere."""
    scores = {"BBB": 0.5, "AAA": 0.5, "CCC": 0.1}
    assert select_top(scores, n_top=2) == ("AAA", "BBB")


def test_n_top_maggiore_del_disponibile_restituisce_tutto():
    scores = {"AAA": 0.5, "BBB": 0.1}
    assert select_top(scores, n_top=10) == ("AAA", "BBB")


def test_punteggi_vuoti_danno_tupla_vuota():
    assert select_top({}, n_top=5) == ()


def test_include_anche_punteggi_negativi_se_sono_i_migliori():
    """Long-only NON significa filtro sul segno: il paniere e' relativo.
    Il filtro assoluto e' un'ipotesi separata, non un default."""
    scores = {"AAA": -0.1, "BBB": -0.5, "CCC": -0.9}
    assert select_top(scores, n_top=2) == ("AAA", "BBB")
```

- [ ] **Step 2: Fallimento atteso** (`ImportError: cannot import name 'select_top'`)

- [ ] **Step 3: Implementare (in coda a `momentum.py`)**

```python
def select_top(scores: dict[str, float], n_top: int) -> tuple[str, ...]:
    """I migliori n per punteggio, con pareggio risolto alfabeticamente.

    Il tie-break alfabetico non e' estetica: senza, l'ordine dipende
    dall'iterazione del dizionario e due esecuzioni sugli stessi dati possono
    dare panieri diversi. Una calibrazione deve essere riproducibile.

    Nota: NON filtra i punteggi negativi. Long-only significa che non shortiamo
    i perdenti, non che escludiamo i vincitori relativi in un mercato in calo.
    Il filtro di momentum assoluto e' un'ipotesi a se' (dual momentum), non un
    default silenzioso.
    """
    ordinati = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
    return tuple(sym for sym, _ in ordinati[:n_top])
```

- [ ] **Step 4: Verde** (10 passed) — **Step 5: Commit**

```bash
git add src/analysis/calibration/momentum.py tests/analysis/test_calibration_momentum.py
git commit -m "feat(calibration): selezione del paniere con tie-break deterministico

Il pareggio si risolve alfabeticamente: senza, l'ordine dipende dall'iterazione
del dizionario e due esecuzioni sugli stessi dati darebbero panieri diversi.
Non filtra i punteggi negativi: quello e' dual momentum, un'ipotesi separata."
```

---

## Task 4: Rendimento equipesato di periodo (TDD)

**Files:**
- Modify: `src/analysis/calibration/momentum.py`
- Modify: `tests/analysis/test_calibration_momentum.py`

- [ ] **Step 1: Test in coda al file**

```python
from src.analysis.calibration.momentum import equal_weighted_return


def test_rendimento_equipesato():
    closes = {
        "AAA": {0: 100.0, 21: 110.0},   # +10%
        "BBB": {0: 100.0, 21: 90.0},    # -10%
    }
    assert equal_weighted_return(("AAA", "BBB"), closes, 0, 21) == pytest.approx(0.0)


def test_media_dei_rendimenti_non_rendimento_della_media():
    """Equipesato = media aritmetica dei rendimenti dei componenti."""
    closes = {"AAA": {0: 10.0, 21: 20.0}, "BBB": {0: 1000.0, 21: 1100.0}}
    # +100% e +10% -> 55%, NON un rendimento pesato per prezzo
    assert equal_weighted_return(("AAA", "BBB"), closes, 0, 21) == pytest.approx(0.55)


def test_simbolo_senza_prezzi_nel_periodo_e_saltato_non_azzerato():
    """Chi non ha dati esce dal calcolo; NON contribuisce con uno zero."""
    closes = {"AAA": {0: 100.0, 21: 110.0}, "BBB": {0: 100.0}}
    assert equal_weighted_return(("AAA", "BBB"), closes, 0, 21) == pytest.approx(0.10)


def test_nessun_simbolo_valido_da_none():
    closes = {"AAA": {0: 100.0}}
    assert equal_weighted_return(("AAA",), closes, 0, 21) is None


def test_paniere_vuoto_da_none():
    assert equal_weighted_return((), {}, 0, 21) is None
```

- [ ] **Step 2: Fallimento atteso** — **Step 3: Implementare (in coda)**

```python
def equal_weighted_return(
    symbols: tuple[str, ...],
    closes: dict[str, dict[int, float]],
    start: int,
    end: int,
) -> float | None:
    """Media aritmetica dei rendimenti dei componenti fra due posizioni.

    Equipesato significa media dei RENDIMENTI, non rendimento di un indice
    pesato per prezzo: due titoli a 10$ e 1000$ contribuiscono uguale.

    Un simbolo senza entrambi i prezzi viene SALTATO, non contato come zero:
    contarlo come zero significherebbe affermare che non si e' mosso, che e'
    un'affermazione falsa. Restituisce None se nessun simbolo e' valutabile.
    """
    rendimenti: list[float] = []
    for sym in symbols:
        serie = closes.get(sym, {})
        p0 = serie.get(start)
        p1 = serie.get(end)
        if p0 is None or p1 is None or p0 == 0:
            continue
        rendimenti.append(p1 / p0 - 1.0)
    if not rendimenti:
        return None
    return sum(rendimenti) / len(rendimenti)
```

- [ ] **Step 4: Verde** (15 passed) — **Step 5: Commit**

```bash
git add src/analysis/calibration/momentum.py tests/analysis/test_calibration_momentum.py
git commit -m "feat(calibration): rendimento equipesato di periodo

Media dei rendimenti, non rendimento di un indice pesato per prezzo. Un simbolo
senza prezzi viene saltato, non contato come zero: contarlo come zero
affermerebbe che non si e' mosso."
```

---

## Task 5: Statistiche riassuntive (TDD)

È la funzione che produce il numero che la pre-registrazione userà per decidere. Il suo docstring
contiene l'avvertenza sull'interpretazione: copialo alla lettera.

**Files:**
- Modify: `src/analysis/calibration/momentum.py`
- Modify: `tests/analysis/test_calibration_momentum.py`

- [ ] **Step 1: Test in coda al file**

```python
from src.analysis.calibration.momentum import summarize_excess


def test_media_deviazione_e_t():
    out = summarize_excess([0.01, 0.02, 0.03, 0.02])
    assert out["n"] == 4
    assert out["media"] == pytest.approx(0.02)
    assert out["dev_std"] == pytest.approx(0.0081649658, abs=1e-9)
    assert out["t_stat"] == pytest.approx(4.898979, abs=1e-5)


def test_intervallo_di_confidenza_al_95_percento():
    out = summarize_excess([0.01, 0.02, 0.03, 0.02])
    se = 0.0081649658 / 2.0
    assert out["ci_low"] == pytest.approx(0.02 - 1.96 * se, abs=1e-9)
    assert out["ci_high"] == pytest.approx(0.02 + 1.96 * se, abs=1e-9)


def test_sotto_i_due_campioni_niente_statistiche_inventate():
    out = summarize_excess([0.01])
    assert out["n"] == 1
    assert out["media"] == pytest.approx(0.01)
    assert out["dev_std"] is None
    assert out["t_stat"] is None
    assert out["ci_low"] is None and out["ci_high"] is None


def test_serie_vuota():
    out = summarize_excess([])
    assert out["n"] == 0
    assert out["media"] is None
    assert out["t_stat"] is None


def test_dev_std_nulla_da_t_none_non_infinito():
    """Valori identici: la dev.std e' zero e il t non e' definito."""
    out = summarize_excess([0.02, 0.02, 0.02])
    assert out["dev_std"] == pytest.approx(0.0)
    assert out["t_stat"] is None


def test_soglia_di_azionabilita_a_tre():
    """La pre-registrazione impone |t| >= 3.0: il campo lo rende esplicito."""
    assert summarize_excess([0.01, 0.02, 0.03, 0.02])["supera_soglia_3"] is True
    assert summarize_excess([0.01, -0.02, 0.03, -0.02])["supera_soglia_3"] is False
```

- [ ] **Step 2: Fallimento atteso** — **Step 3: Implementare (in coda)**

```python
def summarize_excess(excess: list[float]) -> dict:
    """Statistiche riassuntive di una serie di extra-rendimenti periodali.

    ATTENZIONE ALL'INTERPRETAZIONE. La pre-registrazione
    (docs/evidence/PREREGISTRAZIONE_BACKTEST_S1.md) impone |t| >= 3.0 perche'
    con le decine di anomalie testate in letteratura la soglia convenzionale di
    1.96 produce in maggioranza falsi positivi (Harvey-Liu-Zhu 2016).

    E impone anche questo: se il t non raggiunge 3.0, l'esito da registrare e'
    "NON DIMOSTRATA su questo campione", non "falsa". Con l'effetto atteso
    (~0.3%/mese) servono oltre 100 mesi per raggiungere t=3 anche se l'effetto
    fosse reale e stabile: l'assenza di significativita' qui e' attesa per
    costruzione, non e' una scoperta.

    L'intervallo di confidenza usa l'approssimazione normale (1.96), valida per
    n >= ~30. Sotto quella soglia va letto come indicativo.
    """
    n = len(excess)
    if n == 0:
        return {"n": 0, "media": None, "dev_std": None, "t_stat": None,
                "ci_low": None, "ci_high": None, "supera_soglia_3": False}

    media = sum(excess) / n
    if n < 2:
        return {"n": n, "media": media, "dev_std": None, "t_stat": None,
                "ci_low": None, "ci_high": None, "supera_soglia_3": False}

    dev = statistics.stdev(excess)
    if dev == 0:
        return {"n": n, "media": media, "dev_std": dev, "t_stat": None,
                "ci_low": None, "ci_high": None, "supera_soglia_3": False}

    se = dev / math.sqrt(n)
    t = media / se
    return {
        "n": n,
        "media": media,
        "dev_std": dev,
        "t_stat": t,
        "ci_low": media - 1.96 * se,
        "ci_high": media + 1.96 * se,
        "supera_soglia_3": abs(t) >= 3.0,
    }
```

- [ ] **Step 4: Verde** (21 passed) — **Step 5: Commit**

```bash
git add src/analysis/calibration/momentum.py tests/analysis/test_calibration_momentum.py
git commit -m "feat(calibration): statistiche riassuntive con soglia a 3.0

La soglia |t|>=3.0 viene da Harvey-Liu-Zhu: con le decine di anomalie testate in
letteratura, 1.96 produce in maggioranza falsi positivi. Il docstring registra
anche che un t sotto soglia significa 'non dimostrata', non 'falsa': con
l'effetto atteso servono 100+ mesi per t=3, quindi l'assenza di significativita'
e' attesa per costruzione."
```

---

## Verifica finale

- [ ] `uv run pytest tests/analysis/test_calibration_momentum.py -v` → **21 passed**
- [ ] Suite completa senza nuove failure rispetto alla baseline catturata all'inizio:

```bash
uv run pytest -q 2>&1 | tail -3
```

Baseline osservata in un worktree fresco al 2026-08-01: `1 failed, 3289 passed, 14 skipped`. Il
fallimento è il caso noto **#152** (`test_get_s1_backtest_returns_equity_curve` dipende da `reports/`,
che è gitignored). Alla fine deve essere identica, più i 21 test nuovi.

- [ ] `git status --short src/analysis/` mostra solo `calibration/`
- [ ] `git push origin <branch>` e fermarsi. Niente PR, niente merge.

## Cosa resta al revisore

`src/backtest/data/alpaca_loader.py` (download con cache parquet, accanto al loader yfinance esistente
che **non va toccato**: lo usano cinque backtest di strategia), `scripts/run_calibration.py`
(orchestratore), e l'esecuzione vera delle tre calibrazioni con il relativo report.
