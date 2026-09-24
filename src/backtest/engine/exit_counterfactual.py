"""Rami controfattuali del replay uscite (#614).

Pre-registrazione di misura:
docs/evidence/PREREGISTRAZIONE_MISURA_CONTROFATTUALE_USCITE_2026-09-24.md §3.
Pre-registrazione di disegno (che questa ereda e non emenda):
docs/evidence/PREREGISTRAZIONE_DISEGNO_CONTROFATTUALE_USCITE_2026-09-16.md.

Il ramo H_N sopprime ogni vendita ``portfolio_sell`` e la sposta alla campana
della seduta D+N; i fill reali restanti sono riapplicati sotto vincolo di budget,
che è dove il displacement dell'acquisto sostitutivo entra per costruzione
(artefatto 2 della pre-registrazione di disegno: il confronto onesto è «tenuto X»
contro «comprato Y col ricavato», e qui Y non viene comprato se il cash non c'è).

Il ramo di controllo è ``orizzonte=0``: nessuna soppressione, e con nessun fill
saltato la serie coincide con il replay del cancello
(``src/backtest/engine/exit_replay.py``) — l'invariante è inchiodata dai test.

Le vendite ipotetiche sono prezzate da ``prezza_vendita``, iniettata dal runner:
il motore resta puro (niente rete, DB o config). La regola non legge il futuro:
decide solo su etichetta del motivo d'uscita e calendario; i prezzi entrano
nella valutazione (mark, vendita a D+N), mai nella decisione (§3/§5).

Convenzioni di mark ereditate dal cancello: carry-forward del close per i
simboli senza barra, avg_cost come ultima spiaggia, fill post-campana alla
seduta utile successiva.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime

from src.backtest.engine.exit_replay import (
    BrokerFill,
    GiornoReplay,
    VirtualPortfolio,
    _fill_day,
)
from src.backtest.engine.types import MarketSnapshot, OrderSide

# L'unico motivo d'uscita che il controfattuale ritarda (§3). Un SELL senza
# etichetta non è un portfolio_sell: resta reale (fail-closed sull'etichetta).
MOTIVO_RITARDATO = "portfolio_sell"

# §3: un buy che sfora il cash di meno di così passa (arrotondamenti del paper);
# oltre, è displacement, non rumore.
TOLLERANZA_BUDGET = 1.0

# Le quantità dei fill broker differiscono dal detenuto per ~1e-15 (float):
# quella non è una troncatura, è polvere. Sotto questa soglia la vendita è
# piena e non produce eventi di displacement (sui dati reali: 6 falsi eventi
# su 130 vendite, tutti dell'ordine di 1e-15 azioni).
EPS_QTY = 1e-6


@dataclass(frozen=True)
class FillConMotivo(BrokerFill):
    """Un fill reale con il motivo d'uscita dal DB diagnostico (``trades``).

    ``exit_reason`` è ``None`` per i buy e per i sell senza trade associato.
    """

    exit_reason: str | None = None


@dataclass(frozen=True)
class VenditaRitardata:
    """Programma di una soppressione: cosa, quanto, quando esce."""

    simbolo: str
    quantita_soppressa: float
    seduta_originale: date
    seduta_uscita: date | None  # None: estensione censurata dalla fine finestra


@dataclass(frozen=True)
class EventoDisplacement:
    """Un fill reale che il vincolo di budget ha reso impossibile nel ramo."""

    giorno: date
    simbolo: str
    tipo: str  # "buy_saltato" | "sell_troncata"
    quantita: float
    dettaglio: str


@dataclass(frozen=True)
class EsitoRamo:
    orizzonte: int
    serie: tuple[GiornoReplay, ...]
    vendite_ritardate: tuple[VenditaRitardata, ...]  # programma, pre-esecuzione
    fill_ipotetici: tuple[BrokerFill, ...]  # vendite realmente eseguite a D+N
    estensioni_censurate: int
    buy_saltati: tuple[EventoDisplacement, ...]
    sell_troncate: tuple[EventoDisplacement, ...]
    equity_finale: float
    capitale_medio_impiegato: float  # Q2-rec-4: media di valore posizioni / equity
    cash_drag_medio: float  # Q2-rec-4: media di cash / equity


# (simbolo, quantità, close di seduta, campana) -> fill ipotetico col suo costo.
PrezzoVendita = Callable[[str, float, float, datetime], BrokerFill]


def orizzonte_in_sedute(
    sedute: Sequence[date], da_seduta: date, n: int
) -> date | None:
    """La seduta D+n in indice di seduta, o None se cade oltre la finestra."""
    indice = sedute.index(da_seduta)
    se_index = indice + n
    if se_index >= len(sedute):
        return None
    return sedute[se_index]


def replay_ramo(
    start_qty: Mapping[str, float],
    start_cash: float,
    start_closes: Mapping[str, float],
    fills: Sequence[FillConMotivo],
    closes_by_day: Mapping[date, Mapping[str, float]],
    session_closes: Mapping[date, datetime],
    orizzonte: int,
    prezza_vendita: PrezzoVendita,
    tolleranza_budget: float = TOLLERANZA_BUDGET,
) -> tuple[EsitoRamo, VirtualPortfolio]:
    """Rigioca la finestra con le uscite ``portfolio_sell`` ritardate di N sedute."""
    sedute = sorted(session_closes)
    portafoglio = VirtualPortfolio(initial_cash=start_cash)
    for symbol, qty in start_qty.items():
        portafoglio.load_position(symbol, qty, avg_cost=start_closes[symbol])

    per_giorno: dict[date, list[FillConMotivo]] = {}
    for f in sorted(fills, key=lambda f: f.timestamp):
        per_giorno.setdefault(_fill_day(f, session_closes), []).append(f)

    # programma delle soppressioni (orizzonte 0 = ramo di controllo, nulla soppresso)
    programma: list[VenditaRitardata] = []
    soppressi: set[int] = set()
    if orizzonte >= 1:
        for giorno in sedute:
            for f in per_giorno.get(giorno, []):
                if f.side == OrderSide.SELL and f.exit_reason == MOTIVO_RITARDATO:
                    soppressi.add(id(f))
                    programma.append(
                        VenditaRitardata(
                            simbolo=f.symbol,
                            quantita_soppressa=f.quantity,
                            seduta_originale=giorno,
                            seduta_uscita=orizzonte_in_sedute(sedute, giorno, orizzonte),
                        )
                    )
    per_seduta_uscita: dict[date, list[VenditaRitardata]] = {}
    censurate = 0
    for v in programma:
        if v.seduta_uscita is None:
            censurate += 1
        else:
            per_seduta_uscita.setdefault(v.seduta_uscita, []).append(v)

    buy_saltati: list[EventoDisplacement] = []
    sell_troncate: list[EventoDisplacement] = []
    fill_ipotetici: list[BrokerFill] = []

    ultimo_close: dict[str, float] = dict(start_closes)
    serie: list[GiornoReplay] = []

    def _close_del_giorno(simbolo: str, giorno: date) -> float:
        p = closes_by_day.get(giorno, {}).get(simbolo)
        if p is None:
            pos = portafoglio.position_of(simbolo)
            p = ultimo_close.get(simbolo, pos.avg_cost if pos is not None else 0.0)
        return p

    for giorno in sedute:
        for f in per_giorno.get(giorno, []):
            if id(f) in soppressi:
                continue
            engine_fill = f.to_engine_fill()
            if f.side == OrderSide.BUY:
                costo = -engine_fill.net_value
                if portafoglio.cash >= costo - tolleranza_budget:
                    portafoglio.apply_fill(engine_fill)
                else:
                    buy_saltati.append(
                        EventoDisplacement(
                            giorno=giorno,
                            simbolo=f.symbol,
                            tipo="buy_saltato",
                            quantita=f.quantity,
                            dettaglio=f"costo {costo:.2f} contro cash {portafoglio.cash:.2f}",
                        )
                    )
            else:  # SELL reale di altro motivo (o senza etichetta)
                pos = portafoglio.position_of(f.symbol)
                detenuta = pos.quantity if pos is not None else 0.0
                if detenuta <= EPS_QTY:
                    sell_troncate.append(
                        EventoDisplacement(
                            giorno=giorno,
                            simbolo=f.symbol,
                            tipo="sell_troncata",
                            quantita=f.quantity,
                            dettaglio="posizione assente nel ramo",
                        )
                    )
                elif f.quantity <= detenuta + EPS_QTY:
                    # polvere di virgola mobile a parte, vende tutto il detenuto
                    if f.quantity <= detenuta:
                        portafoglio.apply_fill(engine_fill)
                    else:
                        portafoglio.apply_fill(
                            BrokerFill(
                                timestamp=f.timestamp,
                                symbol=f.symbol,
                                side=f.side,
                                quantity=detenuta,
                                fill_price=f.fill_price,
                                commission=f.commission,
                            ).to_engine_fill()
                        )
                else:
                    ridotto = BrokerFill(
                        timestamp=f.timestamp,
                        symbol=f.symbol,
                        side=f.side,
                        quantity=detenuta,
                        fill_price=f.fill_price,
                        commission=f.commission,
                    )
                    portafoglio.apply_fill(ridotto.to_engine_fill())
                    sell_troncate.append(
                        EventoDisplacement(
                            giorno=giorno,
                            simbolo=f.symbol,
                            tipo="sell_troncata",
                            quantita=f.quantity - detenuta,
                            dettaglio=f"troncata a {detenuta:.6f} su {f.quantity:.6f}",
                        )
                    )

        # vendite ipotetiche: alla campana, dopo i fill reali della seduta
        for v in per_seduta_uscita.get(giorno, []):
            pos = portafoglio.position_of(v.simbolo)
            detenuta = pos.quantity if pos is not None else 0.0
            qty = min(v.quantita_soppressa, detenuta)
            if qty <= 1e-9:
                continue
            close = _close_del_giorno(v.simbolo, giorno)
            ipotetico = prezza_vendita(v.simbolo, qty, close, session_closes[giorno])
            fill_ipotetici.append(ipotetico)
            portafoglio.apply_fill(ipotetico.to_engine_fill())

        # mark: stessa convenzione del cancello
        prezzo: dict[str, float] = {}
        for pos in portafoglio.all_positions():
            p = _close_del_giorno(pos.symbol, giorno)
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

    capitale = [
        r.valore_posizioni / r.equity for r in serie if r.equity > 0
    ]
    drag = [r.cash / r.equity for r in serie if r.equity > 0]
    esito = EsitoRamo(
        orizzonte=orizzonte,
        serie=tuple(serie),
        vendite_ritardate=tuple(programma),
        fill_ipotetici=tuple(fill_ipotetici),
        estensioni_censurate=censurate,
        buy_saltati=tuple(buy_saltati),
        sell_troncate=tuple(sell_troncate),
        equity_finale=serie[-1].equity,
        capitale_medio_impiegato=sum(capitale) / len(capitale) if capitale else 0.0,
        cash_drag_medio=sum(drag) / len(drag) if drag else 0.0,
    )
    return esito, portafoglio
