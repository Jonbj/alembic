# Fase 2 — Dossier deterministico e report simmetrico Implementation Plan

> **For agentic workers:** execute this plan task-by-task with the repository's implementation workflow. The numbered steps describe procedure only; live progress is tracked by the linked GitHub issue, never by editing this document.

**Goal:** Precalcolare in modo deterministico i numeri del report alpha-miner, e aggiungere le due dimensioni che oggi mancano — falsi positivi e qualità di cattura.

**Architecture:** Due moduli puri con responsabilità separate (`market.py` guarda il mercato, `book.py` guarda il nostro book), più un orchestratore sottile che li unisce e scrive il dossier JSON. I moduli non fanno I/O: ricevono dati già caricati e restituiscono dizionari, così sono testabili senza DB né rete. L'orchestratore è l'unico punto che tocca Postgres e Alpaca.

**Tech Stack:** Python 3, pytest (`uv run pytest`), pandas, alpaca-py, psycopg. Nessuna dipendenza nuova.

**Spec:** `docs/superpowers/specs/2026-08-01-report-alpha-miner-simmetrico-design.md`

**Contesto:** l'osservazione è già partita (2026-08-03) con lo strumento vecchio. Questa fase si innesta a lavoro finito. Non c'è la fretta della fase 1: **meglio tardi che sbagliato**.

---

## Struttura dei file

**Esecuzione sequenziale, un solo agente.** I due moduli non sono davvero indipendenti (il secondo dipende dal primo per la struttura del pacchetto) e questa fase non ha scadenza: l'osservazione è già partita con lo strumento vecchio. Il parallelismo avrebbe fatto risparmiare poco in cambio di contesa git e merge. Le task vanno eseguite nell'ordine A1 → A2 → A3 → B1 → B2 → B3.

| file | responsabilità |
|---|---|
| `src/analysis/dossier/market.py` | rendimenti, dispersione, mover, copertura news, candidati miss |
| `tests/analysis/test_dossier_market.py` | test del modulo mercato |
| `src/analysis/dossier/book.py` | metriche di ingresso e uscita, aggregazioni |
| `tests/analysis/test_dossier_book.py` | test del modulo book |
| `scripts/alpha_miner_dossier.py` | orchestratore: I/O, unione, scrittura JSON — **lo scrive il revisore** |
| `scripts/daily_alpha_miss_analysis.sh` | prompt che consuma il dossier — **lo scrive il revisore** |

**Regola di isolamento:** l'agente modifica solo i quattro file di modulo/test elencati sopra e gli `__init__.py` strettamente necessari per il sottopacchetto. Non tocca l'orchestratore, lo script cron, né alcunché sotto `src/workers/`, `src/strategies/`, `src/store/`, `config/`.

**Perché i moduli non fanno I/O:** ricevendo dati già caricati sono testabili con fixture in memoria, senza DB né chiamate di rete. È ciò che rende questo lavoro delegabile e verificabile.

---

## Task A1: Struttura del pacchetto

**Files:**
- Preserve and extend: `src/analysis/__init__.py`
- Create: `src/analysis/dossier/__init__.py`
- Preserve: `tests/analysis/__init__.py`

**Step 1: Preparare il sottopacchetto senza sovrascrivere i package esistenti**

```bash
cd /home/stefano/Documents/Projects/Alembic/.worktrees/fase2-dossier
mkdir -p src/analysis/dossier tests/analysis
printf '"""Moduli puri di calcolo del dossier. Nessun I/O: ricevono dati, restituiscono dict."""\n' > src/analysis/dossier/__init__.py
test -f src/analysis/__init__.py
test -f tests/analysis/__init__.py
```

Estendere il docstring esistente di `src/analysis/__init__.py` con il riferimento al sottopacchetto
`dossier`; non sostituire la descrizione preesistente delle analisi post-trade.

**Step 2: Commit**

```bash
git add src/analysis tests/analysis
git commit -m "chore(dossier): struttura del pacchetto di analisi"
```

---

## Task A2: Metriche di mercato (TDD)

**Files:**
- Create: `src/analysis/dossier/market.py`
- Test: `tests/analysis/test_dossier_market.py`

**Step 1: Scrivere i test che falliscono**

Contenuto integrale di `tests/analysis/test_dossier_market.py`:

```python
"""Metriche di mercato del dossier: rendimenti, dispersione, mover, copertura news."""
import pytest

from src.analysis.dossier.market import compute_market


def test_rendimenti_dispersione_e_mover():
    """Return = close/close_prec - 1; sigma = dev.std cross-sectional; mover = |ret| >= soglia."""
    closes = {
        "AAA": (100.0, 110.0),   # +10%  -> mover up
        "BBB": (100.0, 95.0),    # -5%   -> mover down
        "CCC": (100.0, 101.0),   # +1%   -> non mover
    }
    out = compute_market(closes=closes, news_counts={}, soglia_mover=0.03)

    assert out["rendimenti"]["AAA"] == pytest.approx(0.10)
    assert out["rendimenti"]["BBB"] == pytest.approx(-0.05)
    assert out["mover_3pct"] == 2
    assert out["up"] == 1
    assert out["down"] == 1
    # dev.std campionaria di [0.10, -0.05, 0.01]
    assert out["dispersione_sigma"] == pytest.approx(0.0754983, abs=1e-6)


def test_copertura_news_conta_i_simboli_a_zero():
    """watchlist_zero_news = quanti simboli non compaiono affatto o hanno conteggio 0."""
    closes = {"AAA": (100.0, 101.0), "BBB": (100.0, 101.0), "CCC": (100.0, 101.0)}
    out = compute_market(closes=closes, news_counts={"AAA": 3, "BBB": 0}, soglia_mover=0.03)
    # BBB ha 0 esplicito, CCC e' assente dal dizionario: entrambi contano
    assert out["watchlist_zero_news"] == 2


def test_simbolo_senza_barra_precedente_e_escluso_non_inventato():
    """Un simbolo senza entrambe le barre non produce un rendimento finto."""
    closes = {"AAA": (100.0, 110.0), "BBB": (None, 95.0)}
    out = compute_market(closes=closes, news_counts={}, soglia_mover=0.03)
    assert "BBB" not in out["rendimenti"]
    assert out["simboli_senza_dati"] == ["BBB"]
    assert out["mover_3pct"] == 1


def test_dispersione_none_con_meno_di_due_simboli():
    """La dev.std non e' definita su un solo campione: None, non zero."""
    out = compute_market(closes={"AAA": (100.0, 110.0)}, news_counts={}, soglia_mover=0.03)
    assert out["dispersione_sigma"] is None


def test_soglia_e_inclusiva():
    """Esattamente sulla soglia conta come mover."""
    out = compute_market(closes={"AAA": (100.0, 103.0)}, news_counts={}, soglia_mover=0.03)
    assert out["mover_3pct"] == 1
```

**Step 2: Eseguire e vedere il fallimento giusto**

```bash
cd /home/stefano/Documents/Projects/Alembic/.worktrees/fase2-dossier
uv run pytest tests/analysis/test_dossier_market.py -v
```

Atteso: `ModuleNotFoundError: No module named 'src.analysis.dossier.market'`. Se fallisce per altro, fermati.

**Step 3: Implementare**

Contenuto integrale di `src/analysis/dossier/market.py`:

```python
"""Metriche di mercato del dossier.

Modulo puro: riceve prezzi e conteggi gia' caricati, non tocca rete ne' DB.
"""
from __future__ import annotations

import statistics
from typing import TypedDict


class MarketMetrics(TypedDict):
    """Metriche deterministiche della watchlist per una giornata."""

    rendimenti: dict[str, float]
    dispersione_sigma: float | None
    mover_3pct: int
    up: int
    down: int
    watchlist_zero_news: int
    simboli_senza_dati: list[str]


def compute_market(
    closes: dict[str, tuple[float | None, float | None]],
    news_counts: dict[str, int],
    soglia_mover: float,
) -> MarketMetrics:
    """Calcola le metriche di mercato della giornata.

    Args:
        closes: {simbolo: (close_precedente, close_del_giorno)}. Un None su uno dei
            due valori significa dato mancante: il simbolo viene escluso dai
            rendimenti e riportato in "simboli_senza_dati". Non si inventa un valore.
        news_counts: {simbolo: numero di articoli quel giorno}. Un simbolo assente
            conta come zero.
        soglia_mover: soglia inclusiva su |rendimento| per contare come mover.

    Returns:
        dict con rendimenti, dispersione_sigma, mover_3pct, up, down,
        watchlist_zero_news, simboli_senza_dati.
    """
    rendimenti: dict[str, float] = {}
    senza_dati: list[str] = []

    for sym, (prec, oggi) in closes.items():
        if prec is None or oggi is None or prec == 0:
            senza_dati.append(sym)
            continue
        rendimenti[sym] = oggi / prec - 1.0

    valori = list(rendimenti.values())
    up = sum(1 for r in valori if r >= soglia_mover)
    down = sum(1 for r in valori if r <= -soglia_mover)

    # stdev campionaria: non definita sotto i due campioni -> None, non 0.0
    dispersione = statistics.stdev(valori) if len(valori) >= 2 else None

    zero_news = sum(1 for sym in closes if news_counts.get(sym, 0) == 0)

    return {
        "rendimenti": rendimenti,
        "dispersione_sigma": dispersione,
        "mover_3pct": up + down,
        "up": up,
        "down": down,
        "watchlist_zero_news": zero_news,
        "simboli_senza_dati": sorted(senza_dati),
    }
```

**Step 4: Eseguire e vedere il verde**

```bash
uv run pytest tests/analysis/test_dossier_market.py -v
```

Atteso: 5 passed.

**Step 5: Commit**

```bash
git add src/analysis/dossier/market.py tests/analysis/test_dossier_market.py
git commit -m "feat(dossier): metriche di mercato deterministiche

Rendimenti, dispersione cross-sectional, conteggio mover e copertura news.
Un simbolo senza barra non produce un rendimento finto: finisce in
simboli_senza_dati. La dispersione sotto i due campioni e' None, non zero."
```

---

## Task A3: Candidati miss (TDD)

Lo script raccoglie l'**evidenza**; la classificazione (NO_NEWS / THIN_NEUTRAL / …) resta alla sessione, che legge il testo degli articoli. Il modulo non classifica.

**Files:**
- Modify: `src/analysis/dossier/market.py` (aggiunge una funzione)
- Modify: `tests/analysis/test_dossier_market.py` (aggiunge test)

**Step 1: Estendere l'import in testa al file e aggiungere i test**

```python
from src.analysis.dossier.market import compute_market, compute_miss_candidates


def test_candidati_miss_solo_mover_non_in_portafoglio():
    rendimenti = {"AAA": 0.10, "BBB": -0.05, "CCC": 0.01}
    out = compute_miss_candidates(
        rendimenti=rendimenti, news_counts={"AAA": 2}, segnali={}, in_portafoglio={"BBB"},
        soglia_mover=0.03,
    )
    simboli = [candidate["symbol"] for candidate in out]
    assert simboli == ["AAA"]          # BBB e' in portafoglio, CCC non e' mover
    assert out[0]["news_count"] == 2
    assert out[0]["in_portafoglio"] is False


def test_candidati_miss_ordinati_per_rendimento_assoluto_decrescente():
    rendimenti = {"AAA": 0.04, "BBB": -0.12, "CCC": 0.08}
    out = compute_miss_candidates(
        rendimenti=rendimenti, news_counts={}, segnali={}, in_portafoglio=set(),
        soglia_mover=0.03,
    )
    assert [candidate["symbol"] for candidate in out] == ["BBB", "CCC", "AAA"]


def test_candidati_miss_riportano_i_segnali_con_fallback():
    segnali = {"AAA": [{"ora": "16:10", "score": 0.15, "fallback": True}]}
    out = compute_miss_candidates(
        rendimenti={"AAA": 0.10}, news_counts={"AAA": 1}, segnali=segnali,
        in_portafoglio=set(), soglia_mover=0.03,
    )
    assert out[0]["segnali"] == [{"ora": "16:10", "score": 0.15, "fallback": True}]


def test_candidati_miss_senza_segnali_lista_vuota_non_none():
    out = compute_miss_candidates(
        rendimenti={"AAA": 0.10}, news_counts={}, segnali={}, in_portafoglio=set(),
        soglia_mover=0.03,
    )
    assert out[0]["segnali"] == []
```

**Step 2: Eseguire e vedere il fallimento**

```bash
uv run pytest tests/analysis/test_dossier_market.py -v
```

Atteso: `ImportError: cannot import name 'compute_miss_candidates'`.

**Step 3: Aggiungere i contratti tipizzati prima delle funzioni e implementare**

```python
class SignalEvidence(TypedDict):
    """Segnale disponibile per spiegare un candidato miss."""

    ora: str
    score: float
    fallback: bool


MissCandidate = TypedDict(
    "MissCandidate",
    {
        "symbol": str,
        "return": float,
        "news_count": int,
        "segnali": list[SignalEvidence],
        "in_portafoglio": bool,
    },
)
MissCandidate.__doc__ = "Evidenza grezza su un mover non presente nel portafoglio."


def compute_miss_candidates(
    rendimenti: dict[str, float],
    news_counts: dict[str, int],
    segnali: dict[str, list[SignalEvidence]],
    in_portafoglio: set[str],
    soglia_mover: float,
) -> list[MissCandidate]:
    """Raccoglie l'evidenza sui mover NON in portafoglio.

    Non classifica: la categoria del miss (NO_NEWS, THIN_NEUTRAL, ...) richiede di
    leggere il testo degli articoli ed e' compito della sessione, non di questo modulo.

    Ordinati per |rendimento| decrescente: i candidati piu' costosi per primi.
    """
    candidates: list[MissCandidate] = [
        {
            "symbol": sym,
            "return": ret,
            "news_count": news_counts.get(sym, 0),
            "segnali": segnali.get(sym, []),
            "in_portafoglio": False,
        }
        for sym, ret in rendimenti.items()
        if abs(ret) >= soglia_mover and sym not in in_portafoglio
    ]
    return sorted(
        candidates,
        key=lambda candidate: abs(candidate["return"]),
        reverse=True,
    )
```

**Step 4: Verde**

```bash
uv run pytest tests/analysis/test_dossier_market.py -v
```

Atteso: 9 passed.

**Step 5: Commit**

```bash
git add src/analysis/dossier/market.py tests/analysis/test_dossier_market.py
git commit -m "feat(dossier): raccolta evidenza sui candidati miss

Raccoglie rendimento, copertura news e segnali per i mover non in portafoglio.
NON classifica la causa: distinguere NO_NEWS da THIN_NEUTRAL richiede di leggere
l'articolo, ed e' giudizio che resta alla sessione."
```

---

## Task B1: Metriche di ingresso (TDD)

**Files:**
- Create: `src/analysis/dossier/book.py`
- Test: `tests/analysis/test_dossier_book.py`

**Step 1: Scrivere i test che falliscono**

Contenuto integrale di `tests/analysis/test_dossier_book.py`:

```python
"""Metriche del book: ingressi, chiusure, aggregazioni."""
import pytest

from src.analysis.dossier.book import compute_entries


def _bar(
    open_: float = 100.0,
    high: float = 110.0,
    low: float = 90.0,
    close: float = 105.0,
) -> dict[str, float]:
    return {"open": open_, "high": high, "low": low, "close": close}


def test_entry_percentile_misura_dove_si_e_comprato_nel_range():
    """0 = comprato sul minimo del giorno, 1 = sul massimo."""
    trades = [{"symbol": "AAA", "strategia": "S1", "ora_utc": "14:07",
               "entry_price": 90.0, "qty": 10.0}]
    out = compute_entries(trades, {"AAA": _bar()})
    assert out[0]["entry_percentile"] == pytest.approx(0.0)

    trades[0]["entry_price"] = 110.0
    assert compute_entries(trades, {"AAA": _bar()})[0]["entry_percentile"] == pytest.approx(1.0)

    trades[0]["entry_price"] = 100.0
    assert compute_entries(trades, {"AAA": _bar()})[0]["entry_percentile"] == pytest.approx(0.5)


def test_caso_reale_f_inseguimento_del_massimo():
    """S1 compro' F a 16.02 il 2026-07-29, range 15.16-16.29, chiusura 15.28."""
    trades = [{"symbol": "F", "strategia": "S1", "ora_utc": "14:07",
               "entry_price": 16.02, "qty": 100.0}]
    bars = {"F": {"open": 15.55, "high": 16.29, "low": 15.16, "close": 15.28}}
    out = compute_entries(trades, bars)
    assert out[0]["entry_percentile"] == pytest.approx(0.7611, abs=1e-4)
    assert out[0]["mtm_eod"] == pytest.approx(-74.0)


def test_mtm_eod_e_vs_apertura():
    trades = [{"symbol": "AAA", "strategia": "S4", "ora_utc": "15:22",
               "entry_price": 102.0, "qty": 5.0}]
    out = compute_entries(trades, {"AAA": _bar()})
    assert out[0]["mtm_eod"] == pytest.approx(15.0)      # (105 - 102) * 5
    assert out[0]["vs_apertura"] == pytest.approx(25.0)  # (105 - 100) * 5


def test_range_degenere_da_percentile_none_non_divisione_per_zero():
    trades = [{"symbol": "AAA", "strategia": "S1", "ora_utc": "14:07",
               "entry_price": 100.0, "qty": 1.0}]
    bars = {"AAA": {"open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0}}
    assert compute_entries(trades, bars)[0]["entry_percentile"] is None


def test_simbolo_senza_barra_e_saltato_non_inventato():
    trades = [{"symbol": "ZZZ", "strategia": "S1", "ora_utc": "14:07",
               "entry_price": 10.0, "qty": 1.0}]
    out = compute_entries(trades, {})
    assert out[0]["entry_percentile"] is None
    assert out[0]["mtm_eod"] is None
```

**Step 2: Fallimento atteso**

```bash
uv run pytest tests/analysis/test_dossier_book.py -v
```

Atteso: `ModuleNotFoundError: No module named 'src.analysis.dossier.book'`.

**Step 3: Implementare**

Contenuto integrale di `src/analysis/dossier/book.py`:

```python
"""Metriche del nostro book per il dossier.

Modulo puro: riceve trade e barre gia' caricati, non tocca rete ne' DB.
"""
from __future__ import annotations

import statistics
from typing import TypedDict


class EntryTrade(TypedDict):
    """Campi di un ingresso necessari alle metriche del dossier."""

    symbol: str
    strategia: str
    ora_utc: str
    entry_price: float
    qty: float


class DailyBar(TypedDict):
    """Barra giornaliera OHLC usata per misurare un ingresso."""

    open: float
    high: float
    low: float
    close: float


class EntryMetrics(EntryTrade):
    """Ingresso arricchito con metriche provvisorie di fine giornata."""

    entry_percentile: float | None
    mtm_eod: float | None
    vs_apertura: float | None


def compute_entries(
    trades: list[EntryTrade], bars: dict[str, DailyBar]
) -> list[EntryMetrics]:
    """Metriche degli ingressi del giorno, con esito PROVVISORIO di fine giornata.

    Attenzione a come si legge: su un book dove la posizione media dura 14 giorni,
    il mark-to-market di fine giornata NON e' un giudizio sulla decisione. Serve a
    rendere visibile un pattern aggregato, non a condannare il singolo trade.

    entry_percentile e' la misura dell'inseguimento: 0 = comprato sul minimo del
    giorno, 1 = sul massimo. None se il range e' degenere o la barra manca.
    """
    result: list[EntryMetrics] = []
    for trade in trades:
        bar = bars.get(trade["symbol"])
        row: EntryMetrics = {
            "symbol": trade["symbol"],
            "strategia": trade["strategia"],
            "ora_utc": trade["ora_utc"],
            "entry_price": trade["entry_price"],
            "qty": trade["qty"],
            "entry_percentile": None,
            "mtm_eod": None,
            "vs_apertura": None,
        }
        if bar is not None:
            rng = bar["high"] - bar["low"]
            if rng > 0:
                row["entry_percentile"] = (trade["entry_price"] - bar["low"]) / rng
            row["mtm_eod"] = (bar["close"] - trade["entry_price"]) * trade["qty"]
            row["vs_apertura"] = (bar["close"] - bar["open"]) * trade["qty"]
        result.append(row)
    return result
```

**Step 4: Verde**

```bash
uv run pytest tests/analysis/test_dossier_book.py -v
```

Atteso: 5 passed.

**Step 5: Commit**

```bash
git add src/analysis/dossier/book.py tests/analysis/test_dossier_book.py
git commit -m "feat(dossier): metriche di ingresso con entry_percentile

entry_percentile misura dove cade il prezzo d'ingresso nel range della giornata:
e' la misura diretta dell'inseguimento. Range degenere o barra mancante danno
None, mai un numero inventato."
```

---

## Task B2: Metriche di chiusura (TDD)

**Files:**
- Modify: `src/analysis/dossier/book.py`
- Modify: `tests/analysis/test_dossier_book.py`

**Step 1: Estendere l'import in testa al file e aggiungere i test**

```python
from src.analysis.dossier.book import compute_entries, compute_exits


def test_drift_post_uscita_positivo_significa_soldi_lasciati_sul_tavolo():
    trades = [{"symbol": "AAA", "strategia": "S4", "exit_price": 100.0, "qty": 10.0,
               "pnl_net": 50.0, "exit_reason": "portfolio_sell", "ore_tenuta": 3.5}]
    out = compute_exits(trades, {"AAA": 103.0})
    assert out[0]["drift_post_uscita"] == pytest.approx(30.0)


def test_drift_negativo_significa_perdita_evitata():
    trades = [{"symbol": "AAA", "strategia": "S4", "exit_price": 100.0, "qty": 10.0,
               "pnl_net": 50.0, "exit_reason": "stop_loss", "ore_tenuta": 3.5}]
    out = compute_exits(trades, {"AAA": 97.0})
    assert out[0]["drift_post_uscita"] == pytest.approx(-30.0)


def test_caso_reale_msft_uscita_sopra_la_chiusura():
    """MSFT 2026-07-30: uscita a 455.56, chiusura 451.55, 2.82 azioni."""
    trades = [{"symbol": "MSFT", "strategia": "S4", "exit_price": 455.56, "qty": 2.82,
               "pnl_net": 13.03, "exit_reason": "portfolio_sell", "ore_tenuta": 2.75}]
    out = compute_exits(trades, {"MSFT": 451.55})
    assert out[0]["drift_post_uscita"] == pytest.approx(-11.31, abs=0.01)


def test_senza_prezzo_di_chiusura_drift_none():
    trades = [{"symbol": "ZZZ", "strategia": "S1", "exit_price": 10.0, "qty": 1.0,
               "pnl_net": 1.0, "exit_reason": "portfolio_sell", "ore_tenuta": 1.0}]
    assert compute_exits(trades, {})[0]["drift_post_uscita"] is None
```

**Step 2: Fallimento atteso** (`ImportError: cannot import name 'compute_exits'`)

```bash
uv run pytest tests/analysis/test_dossier_book.py -v
```

**Step 3: Aggiungere i contratti tipizzati prima delle funzioni e implementare**

```python
class ExitTrade(TypedDict):
    """Campi di una chiusura necessari alle metriche del dossier."""

    symbol: str
    strategia: str
    exit_price: float
    qty: float
    pnl_net: float
    exit_reason: str
    ore_tenuta: float


class ExitMetrics(ExitTrade):
    """Chiusura arricchita con il drift successivo all'uscita."""

    drift_post_uscita: float | None


def compute_exits(
    trades: list[ExitTrade], closes: dict[str, float]
) -> list[ExitMetrics]:
    """Metriche delle posizioni chiuse: qui il verdetto e' legittimo, l'esito e' completo.

    drift_post_uscita positivo = soldi lasciati sul tavolo (il titolo e' salito dopo
    che siamo usciti); negativo = perdita evitata. Se la mediana mobile e' stabilmente
    positiva, usciamo troppo presto — ed e' misurabile, a differenza di un miss.
    """
    result: list[ExitMetrics] = []
    for trade in trades:
        close = closes.get(trade["symbol"])
        result.append({
            "symbol": trade["symbol"],
            "strategia": trade["strategia"],
            "exit_price": trade["exit_price"],
            "qty": trade["qty"],
            "pnl_net": trade["pnl_net"],
            "exit_reason": trade["exit_reason"],
            "ore_tenuta": trade["ore_tenuta"],
            "drift_post_uscita": (
                None
                if close is None
                else (close - trade["exit_price"]) * trade["qty"]
            ),
        })
    return result
```

**Step 4: Verde** (9 passed) — **Step 5: Commit**

```bash
git add src/analysis/dossier/book.py tests/analysis/test_dossier_book.py
git commit -m "feat(dossier): metriche di chiusura con drift post-uscita

drift_post_uscita sistematizza un'osservazione che i report facevano a occhio.
Positivo = soldi lasciati sul tavolo, negativo = perdita evitata."
```

---

## Task B3: Aggregazione per ora d'ingresso (TDD)

È l'aggregazione da cui è emerso il finding più forte della settimana: il 90% della perdita realizzata di S4 e il 76% di quella di S1 stanno nell'ora 14:00 UTC. Diventa una riga fissa invece di una scoperta fortuita.

**Files:**
- Modify: `src/analysis/dossier/book.py`
- Modify: `tests/analysis/test_dossier_book.py`

**Step 1: Estendere l'import in testa al file e aggiungere i test**

```python
from src.analysis.dossier.book import (
    aggregate_by_entry_hour,
    compute_entries,
    compute_exits,
)


def test_aggregazione_per_ora_conta_e_somma():
    chiusi = [
        {"ora_ingresso": 14, "pnl_net": -10.0},
        {"ora_ingresso": 14, "pnl_net": -20.0},
        {"ora_ingresso": 14, "pnl_net": 6.0},
        {"ora_ingresso": 19, "pnl_net": 5.0},
    ]
    out = {r["ora"]: r for r in aggregate_by_entry_hour(chiusi)}
    assert out[14]["n"] == 3
    assert out[14]["win"] == 1
    assert out[14]["somma_pnl"] == pytest.approx(-24.0)
    assert out[14]["media"] == pytest.approx(-8.0)


def test_t_stat_none_sotto_i_due_campioni():
    """Con un solo trade la dev.std non esiste: t_stat None, non zero."""
    out = aggregate_by_entry_hour([{"ora_ingresso": 14, "pnl_net": -10.0}])
    assert out[0]["t_stat"] is None
    assert out[0]["dev_std"] is None


def test_t_stat_none_se_dev_std_nulla():
    """Tutti i valori identici: la dev.std e' zero, il t non e' definito."""
    chiusi = [{"ora_ingresso": 14, "pnl_net": -5.0} for _ in range(3)]
    assert aggregate_by_entry_hour(chiusi)[0]["t_stat"] is None


def test_ordinamento_per_ora_crescente():
    chiusi = [{"ora_ingresso": 19, "pnl_net": 1.0}, {"ora_ingresso": 14, "pnl_net": 1.0}]
    assert [r["ora"] for r in aggregate_by_entry_hour(chiusi)] == [14, 19]
```

**Step 2: Fallimento atteso** — **Step 3: aggiungere i contratti tipizzati e implementare**

```python
class ClosedTradeForHour(TypedDict):
    """Campi minimi per aggregare il P&L per ora di ingresso."""

    ora_ingresso: int
    pnl_net: float


class EntryHourAggregate(TypedDict):
    """Statistiche descrittive dei trade entrati nella stessa ora UTC."""

    ora: int
    n: int
    win: int
    somma_pnl: float
    media: float
    dev_std: float | None
    t_stat: float | None


def aggregate_by_entry_hour(
    chiusi: list[ClosedTradeForHour],
) -> list[EntryHourAggregate]:
    """Raggruppa i trade chiusi per ora UTC di ingresso.

    ATTENZIONE ALLA LETTURA: e' un'analisi post-hoc su molti bucket orari. Un t_stat
    marginale qui NON e' una scoperta: con ~8 bucket, una correzione per confronti
    multipli lo annulla. Il campo esiste per ordinare le ipotesi, non per dichiararle
    vere. Chi consuma questo dato deve riportare anche la numerosita'.
    """
    per_ora: dict[int, list[float]] = {}
    for trade in chiusi:
        per_ora.setdefault(trade["ora_ingresso"], []).append(trade["pnl_net"])

    result: list[EntryHourAggregate] = []
    for ora in sorted(per_ora):
        pnl_values = per_ora[ora]
        sample_size = len(pnl_values)
        mean = sum(pnl_values) / sample_size
        std_dev = statistics.stdev(pnl_values) if sample_size >= 2 else None
        t_stat = (mean / (std_dev / (sample_size**0.5))) if std_dev else None
        result.append({
            "ora": ora,
            "n": sample_size,
            "win": sum(1 for pnl in pnl_values if pnl > 0),
            "somma_pnl": sum(pnl_values),
            "media": mean,
            "dev_std": std_dev,
            "t_stat": t_stat,
        })
    return result
```

**Step 4: Verde** (13 passed) — **Step 5: Commit**

```bash
git add src/analysis/dossier/book.py tests/analysis/test_dossier_book.py
git commit -m "feat(dossier): aggregazione per ora d'ingresso

Rende fissa l'aggregazione da cui e' emerso il finding piu' forte della
settimana. Il docstring impone la cautela statistica: e' post-hoc su molti
bucket, il t_stat ordina le ipotesi e non le dichiara vere."
```

---

## Verifica finale

- Il proprio modulo passa: `uv run pytest tests/analysis/ -v` (22 test dossier).
- La suite completa non peggiora rispetto alla baseline catturata prima di iniziare:

```bash
uv run pytest -q 2>&1 | tail -3
```

Baseline osservata nel worktree al 2026-08-01: `1 failed, 3267 passed, 14 skipped`; il fallimento è il caso noto #152. Un fallimento in più va indagato, non ignorato.

- `git push origin evidence/fase2-dossier` e fermarsi. Niente merge.

## Cosa resta al revisore

L'orchestratore `scripts/alpha_miner_dossier.py` (I/O verso Postgres e Alpaca, unione dei due moduli, scrittura del JSON), la revisione del prompt cron perché consumi il dossier, il ricalcolo retroattivo delle righe di `market_daily.jsonl` dal 2026-08-03, e l'annotazione della deroga nella carta con il commit reale.
