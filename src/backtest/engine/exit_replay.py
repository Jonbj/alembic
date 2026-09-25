"""Cancello di riproducibilità per il controfattuale sulle uscite (#614).

Pre-registrazione: docs/evidence/PREREGISTRAZIONE_DISEGNO_CONTROFATTUALE_USCITE_2026-09-16.md
§4 — con la regola invariata, il replay deve riprodurre la storia realmente accaduta
entro ±2% sull'equity terminale della finestra, e la differenza va spiegata.

Il replay è a livello di PORTAFOGLIO, non per-trade (§3 della pre-registrazione): la
contabilità è quella di ``src.backtest/engine/portfolio.py`` (regola #169/#467), riusata
e non riscritta. I fill sono quelli realmente avvenuti (broker), con le commissioni
reali: sui rami controfattuali — quando saranno pre-registrati — i fill ipotetici
passeranno da ``src/backtest/costs/``.

Modulo puro: niente rete, niente DB. Il runner è ``scripts/replay_gate_614.py``.

Convenzioni dichiarate:

* Il mark di una seduta senza barra per un simbolo è il carry-forward dell'ultimo
  close noto (la stessa convenzione di ``src/analysis/dossier/economic_pnl.py``):
  nessun prezzo viene inventato.
* Un fill dopo la campana della sua seduta appartiene alla seduta utile successiva:
  è ciò che fa il broker nel mark giornaliero.
* L'equity del cancello è quella money-weighted (cash + posizioni marcate): la metrica
  ammessa dalla letteratura per un pool a capitale fisso (Q2 del report di ricerca).
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import uuid

from src.backtest.engine.portfolio import VirtualPortfolio
from src.backtest.engine.types import Fill, MarketSnapshot, OrderSide

# Tolleranza pre-registrata §4: ±2% sull'equity terminale.
TOLLERANZA_PCT = 2.0


@dataclass(frozen=True)
class BrokerFill:
    """Un fill realmente avvenuto, come lo riporta il broker.

    ``commission`` è la commissione effettiva del conto (0 sul paper Alpaca):
    il cancello riproduce la storia, non la stima.
    """

    timestamp: datetime
    symbol: str
    side: OrderSide
    quantity: float
    fill_price: float
    commission: float = 0.0

    def to_engine_fill(self) -> Fill:
        return Fill(
            fill_id=uuid.uuid4().hex,
            order_id=uuid.uuid4().hex,
            timestamp=self.timestamp,
            symbol=self.symbol,
            side=self.side,
            quantity=self.quantity,
            fill_price=self.fill_price,
            commission=self.commission,
            slippage_bps=0.0,
            strategy_id="replay_gate_614",
        )


@dataclass(frozen=True)
class GiornoReplay:
    """Equity money-weighted del book a fine seduta."""

    giorno: date
    equity: float
    cash: float
    valore_posizioni: float


@dataclass(frozen=True)
class EsitoGate:
    replay_equity: float
    broker_equity: float
    delta: float
    delta_pct: float
    tolleranza_pct: float
    superato: bool


def reconstruct_start_quantities(
    current: Mapping[str, float],
    fills: Sequence[BrokerFill],
    after: datetime,
) -> dict[str, float]:
    """Quantità detenute a inizio finestra, per inversione dei fill successivi.

    ``after`` è la campana dell'ancoraggio (chiusura dell'ultima seduta prima
    della finestra): i fill con timestamp > after appartengono alla finestra.
    ``qty_inizio = qty_attuale - somma dei fill firmati nella finestra``.
    Vale per ogni storia (posizioni cresciute, chiuse, chiuse e riaperte):
    l'inversione è esatta per costruzione.
    """
    start = dict(current)
    for f in fills:
        if f.timestamp <= after:
            continue
        segno = 1 if f.side == OrderSide.BUY else -1
        start[f.symbol] = start.get(f.symbol, 0.0) - segno * f.quantity
    # gli zeri esatti non sono posizioni
    return {s: q for s, q in start.items() if abs(q) > 1e-9}


def initial_cash(
    equity_at_start: float,
    start_qty: Mapping[str, float],
    start_closes: Mapping[str, float],
) -> float:
    """Cash iniziale: equity del broker a inizio finestra meno le posizioni marcate.

    Rifiuta un close mancante invece di inventare un prezzo.
    """
    mancanti = [s for s in start_qty if s not in start_closes]
    if mancanti:
        raise ValueError(f"close mancante a inizio finestra per: {sorted(mancanti)}")
    return equity_at_start - sum(q * start_closes[s] for s, q in start_qty.items())


def _fill_day(
    f: BrokerFill,
    session_closes: Mapping[date, datetime],
) -> date:
    """Seduta a cui il fill appartiene: la prima la cui campana non è passata."""
    giorni = sorted(session_closes)
    for g in giorni:
        if f.timestamp <= session_closes[g]:
            return g
    raise ValueError(
        f"fill {f.symbol} {f.timestamp} fuori dai giorni di seduta (ultimo: {giorni[-1]})"
    )


def replay(
    start_qty: Mapping[str, float],
    start_cash: float,
    start_closes: Mapping[str, float],
    fills: Sequence[BrokerFill],
    closes_by_day: Mapping[date, Mapping[str, float]],
    session_closes: Mapping[date, datetime],
) -> tuple[tuple[GiornoReplay, ...], VirtualPortfolio]:
    """Rigioca i fill sulle sedute e marca l'equity a ogni campana.

    Ritorna la serie dei ``GiornoReplay`` (ordinata per seduta) e il portafoglio
    finale, per ispezione e decomposizione della differenza.
    """
    portafoglio = VirtualPortfolio(initial_cash=start_cash)
    mancanti = [s for s in start_qty if s not in start_closes]
    if mancanti:
        raise ValueError(f"close mancante a inizio finestra per: {sorted(mancanti)}")

    for symbol, qty in start_qty.items():
        portafoglio.load_position(symbol, qty, avg_cost=start_closes[symbol])

    per_giorno: dict[date, list[BrokerFill]] = {}
    for f in sorted(fills, key=lambda f: f.timestamp):
        per_giorno.setdefault(_fill_day(f, session_closes), []).append(f)

    ultimo_close: dict[str, float] = dict(start_closes)
    serie: list[GiornoReplay] = []
    for giorno in sorted(session_closes):
        for f in per_giorno.get(giorno, []):
            portafoglio.apply_fill(f.to_engine_fill())

        # closes_by_day[giorno] è il dict dei simboli con barra quel giorno; gli
        # altri fanno carry-forward dell'ultimo close noto.
        prezzo: dict[str, float] = {}
        for pos in portafoglio.all_positions():
            p = closes_by_day.get(giorno, {}).get(pos.symbol)
            if p is None:
                p = ultimo_close.get(pos.symbol, pos.avg_cost)
            prezzo[pos.symbol] = p
            ultimo_close[pos.symbol] = p

        snapshot = portafoglio.mark_to_market(
            MarketSnapshot(
                timestamp=session_closes[giorno],
                prices=prezzo,
                volumes={},
                adv_20d={},
            )
        )
        valore_pos = snapshot.total_nav - snapshot.cash
        serie.append(
            GiornoReplay(
                giorno=giorno,
                equity=snapshot.total_nav,
                cash=snapshot.cash,
                valore_posizioni=valore_pos,
            )
        )
    return tuple(serie), portafoglio


def ph_label_epoch(session_day: date) -> int:
    """Epoch dell'etichetta che Alpaca dà alla seduta nella portfolio history 1D.

    Empirico su paper-api: la seduta S compare con etichetta 00:00Z del giorno di
    calendario SUCCESSIVO (le sedute di venerdì come sabato; l'ultimo punto della
    serie vale ``last_equity``, cioè il close del giorno di borsa precedente).
    """
    label = datetime(
        session_day.year, session_day.month, session_day.day, tzinfo=timezone.utc
    ) + timedelta(days=1)
    return int(label.timestamp())


def equity_di_seduta(ph: Mapping, session_day: date) -> float:
    """Equity del broker a fine seduta, dalla portfolio history 1D."""
    ts_epoch = ph_label_epoch(session_day)
    timestamps = list(ph["timestamp"])
    if ts_epoch not in timestamps:
        raise ValueError(
            f"la portfolio history non copre la seduta {session_day} "
            f"(etichetta {ts_epoch} assente)"
        )
    return float(ph["equity"][timestamps.index(ts_epoch)])


def evaluate_gate(
    replay_equity: float,
    broker_equity: float,
    tolleranza_pct: float = TOLLERANZA_PCT,
) -> EsitoGate:
    """Verifica §4: ±tolleranza sull'equity terminale, sul denominatore del broker."""
    delta = replay_equity - broker_equity
    delta_pct = delta / broker_equity * 100.0 if broker_equity else float("inf")
    return EsitoGate(
        replay_equity=replay_equity,
        broker_equity=broker_equity,
        delta=delta,
        delta_pct=delta_pct,
        tolleranza_pct=tolleranza_pct,
        superato=abs(delta_pct) <= tolleranza_pct,
    )
