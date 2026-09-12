"""Qualita' dell'uscita del trial exit S4 (#299, criterio 1: §8.3 del dossier).

Le metriche di qualita' che il consolidato chiede — false-exit rate, recovery
entro l'orizzonte, giveback da MFE — e la decomposizione intraday/overnight
della gamba challenger non esistono nei delta appaiati: nascono dal path di
prezzo fra ingresso e orizzonte. Questo modulo e' puro: riceve fill, uscite e
barre gia' osservati, e non conosce broker ne' DB, cosi' come il valutatore
viene costruito e testato **prima** di leggere gli esiti forward.

Le definizioni operative, dichiarate qui perche' il dossier nomina le metriche
ma non le formalizza:

- **componente overnight della gamba challenger**: la somma dei salti di
  prezzo sui gap fra sedute dentro (ingresso, uscita challenger], per quantita'
  virtuale. Con l'ancora sul prezzo d'ingresso la decomposizione e' completa:
  overnight + intraday = pnl lordo della gamba;
- **falsa uscita della baseline**: la baseline e' uscita prima dell'orizzonte
  e alla fine dell'orizzonte — il prezzo eseguibile dell'uscita challenger —
  starebbe meglio di come e' uscita. Tenere sarebbe stato superiore: l'uscita
  era falsa;
- **recovery entro l'orizzonte**: per le sole uscite false, il prezzo torna
  sopra l'ingresso prima della fine dell'orizzonte;
- **giveback da MFE**: quanto la challenger restituisce dal massimo favorevole
  toccato (high delle barre) fino alla sua uscita, in bps dell'ingresso.

La regola e' quella di `live_tp_check`: **ignoto non e' zero**. Barre o fill
mancanti lasciano la metrica `None`, fuori dalle medie: un buco contato come un
favore abbasserebbe proprio il false-exit rate, cioe' il numero che il
contratto vuole sorvegliato.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Sequence

# Le barre sono al minuto: un buco piu' lungo di cosi' non e' un silenzio di
# mercato dentro una seduta, e' la chiusura che separa due sedute (o un guasto
# del feed — che resta comunque un gap, mai un movimento intraday).
SESSION_GAP = timedelta(minutes=30)


@dataclass(frozen=True)
class PairedExitPath:
    """Un intento visto dalle due policy, con i prezzi gia' osservati.

    `entry_*` e' il fill dell'ingresso condiviso; le uscite sono i fill delle
    due policy (baseline = P0, challenger = P1). L'orizzonte del trial e'
    l'uscita della challenger: e' li' che il tempo D+2 finisce.
    """

    intent_id: str
    entry_at: datetime | None
    entry_price: float | None
    quantity: float
    baseline_exit_at: datetime | None
    baseline_exit_price: float | None
    challenger_exit_at: datetime | None
    challenger_exit_price: float | None


@dataclass(frozen=True)
class PairedExitQuality:
    """Gli input di `exit_quality` del valutatore per un intento."""

    overnight_pnl_usd: float | None
    false_exit: bool | None
    recovered_within_horizon: bool | None
    giveback_from_mfe_bps: float | None


def exit_quality_from_path(
    path: PairedExitPath,
    bars: Sequence[tuple[datetime, float, float]],
) -> PairedExitQuality:
    """Deriva le metriche di qualita' di un intento dal suo path di prezzo.

    `bars` sono triple ``(timestamp, high, close)`` ordinate nel tempo, gia'
    filtrate dal chiamante sul simbolo: qui dentro si entra solo con la
    finestra che conta, e ogni metrica si ritaglia la sua.
    """
    return PairedExitQuality(
        overnight_pnl_usd=_overnight_component(path, bars),
        false_exit=_false_exit(path),
        recovered_within_horizon=_recovered_within_horizon(path, bars),
        giveback_from_mfe_bps=_giveback_from_mfe(path, bars),
    )


def _overnight_component(
    path: PairedExitPath,
    bars: Sequence[tuple[datetime, float, float]],
) -> float | None:
    if path.entry_at is None or path.entry_price is None:
        return None
    if path.challenger_exit_at is None or not path.quantity:
        return None
    # Ancora sul fill: anche il primo salto — se e' un gap — e' overnight
    punti: list[tuple[datetime, float]] = [
        (path.entry_at, path.entry_price)
    ]
    punti.extend(
        (timestamp, close)
        for timestamp, _high, close in bars
        if path.entry_at < timestamp <= path.challenger_exit_at
    )
    if len(punti) < 2:
        return None
    overnight = 0.0
    for (prima_at, prima), (dopo_at, dopo) in zip(punti, punti[1:]):
        if dopo_at - prima_at > SESSION_GAP:
            overnight += (dopo - prima) * path.quantity
    return overnight


def _false_exit(path: PairedExitPath) -> bool | None:
    if (
        path.baseline_exit_at is None
        or path.baseline_exit_price is None
        or path.challenger_exit_at is None
        or path.challenger_exit_price is None
    ):
        return None
    if path.baseline_exit_at >= path.challenger_exit_at:
        # La baseline e' rimasta fino all'orizzonte: non c'e' uscita da
        # giudicare prematura.
        return False
    return path.challenger_exit_price > path.baseline_exit_price


def _recovered_within_horizon(
    path: PairedExitPath,
    bars: Sequence[tuple[datetime, float, float]],
) -> bool | None:
    if _false_exit(path) is not True:
        # La recovery ha senso solo per un'uscita falsa: altrove la domanda
        # non si pone e il campo resta non applicabile.
        return None
    assert path.baseline_exit_at is not None
    assert path.challenger_exit_at is not None
    if path.entry_price is None:
        # L'ingresso e' il livello da recuperare: senza fill non esiste
        # neanche la domanda.
        return None
    chiusure = [
        close
        for timestamp, _high, close in bars
        if path.baseline_exit_at < timestamp <= path.challenger_exit_at
    ]
    if not chiusure:
        # Non sappiamo dove sia andato il prezzo dopo l'uscita: e' un ignoto,
        # non una mancata recovery.
        return None
    return max(chiusure) >= path.entry_price


def _giveback_from_mfe(
    path: PairedExitPath,
    bars: Sequence[tuple[datetime, float, float]],
) -> float | None:
    if (
        path.entry_at is None
        or path.entry_price is None
        or not path.entry_price
        or path.challenger_exit_at is None
        or path.challenger_exit_price is None
    ):
        return None
    massimi = [
        high
        for timestamp, high, _close in bars
        if path.entry_at < timestamp <= path.challenger_exit_at
    ]
    if not massimi:
        return None
    return (max(massimi) - path.challenger_exit_price) / path.entry_price * 10_000.0