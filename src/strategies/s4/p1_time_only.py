"""Challenger P1 del trial exit S4: D+2 time-only, in shadow (#297).

P1 non riproduce E0 come fa la baseline P0: e' un **controfattuale**. Sugli
stessi ingressi — stesso intento, stesso fill, stesso notional, stessi costi
d'ingresso — mantiene la posizione fino alla close di D0+2 sedute anche quando
il runtime l'ha gia' venduta, e ignora per costruzione ogni motivo di uscita
che non sia la scadenza o l'overlay di rischio comune.

Le regole vengono dal contratto congelato (`config/s4_exit_trial.yaml`, firmato
il 2026-08-22), non sono scelte qui:

- `policies.P1.spec` — nessuna uscita per silenzio fonte, max_signal_age,
  assenza dal top-5, rank drop, expired, unknown, crossing sotto l'entry gate o
  target-weight zero; nessun counter ordinario;
- `horizon.exit_price_rule` — ordine di chiusura solo se realmente presentabile
  entro il cutoff, altrimenti primo prezzo eseguibile successivo, **mai il
  closing print teorico**;
- `horizon.gap_beyond_stop` — fill al primo prezzo eseguibile, non al trigger;
- `risk_overlay.d_hard` — identico fra le policy e non attribuito alla policy
  alpha.

Il modulo e' puro: non conosce broker, DB ne' client di mercato. Riceve una
finestra di prezzi eseguibili gia' raccolta e restituisce un evento nella stessa
forma di P0, cosi' che le viste appaiate di #298 lo consumino senza adattatori.
Non esiste alcun campo che possa chiedere un'azione al broker.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid5

import yaml

from src.strategies.s4.lifecycle import S4LifecycleEvent
from src.strategies.s4.p0_baseline import CostModel, P0ReplayEvent

_P1_NAMESPACE = UUID("2f2f6d21-7a1c-5f60-9a2e-4b0f1f9c8d31")

REASON_HOLDING = "P1_HOLDING"
REASON_TIME_DUE = "P1_TIME_DUE"
REASON_D_HARD = "P1_D_HARD"
REASON_ENTRY_NOT_RECONSTRUCTIBLE = "P1_ENTRY_NOT_RECONSTRUCTIBLE"
REASON_DUE_SESSION_UNKNOWN = "P1_DUE_SESSION_UNKNOWN"
REASON_EXIT_PRICE_MISSING = "P1_EXIT_PRICE_MISSING"

_EXIT_RULE_AT_CUTOFF = "last_executable_before_cutoff"
_EXIT_RULE_AFTER_CUTOFF = "first_executable_after_cutoff"


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


@dataclass(frozen=True)
class P1PolicySnapshot:
    """La parte di contratto che P1 sa valutare, letta e mai ricodificata."""

    version: str
    scope: str
    promotable: bool
    d_hard_enabled: bool
    d_hard_attributed_to_alpha: bool
    max_signal_age_drives_exit: bool
    exit_rule: str
    source_hash: str


@dataclass(frozen=True)
class ExecutableQuote:
    """Un prezzo realmente presentabile, con il minimo della sua barra.

    `price` e' il prezzo a cui un ordine sarebbe stato eseguito; `low` serve
    solo a sapere se lo stop di rischio e' stato bucato dentro la barra. Sono
    distinti perche' il contratto vieta di riempire al trigger: il minimo dice
    *se*, il prezzo dice *a quanto*.
    """

    at: datetime
    price: float
    low: float


@dataclass(frozen=True)
class P1MarketWindow:
    """Prezzi eseguibili fra l'ingresso e la scadenza, piu' i confini di seduta.

    `complete=False` dichiara che la finestra non copre ancora tutta la vita
    dell'intento: e' il caso normale prima della scadenza, e non e' un errore.
    """

    quotes: tuple[ExecutableQuote, ...]
    session_close_at: datetime | None
    cutoff_at: datetime | None
    complete: bool


def load_p1_policy_snapshot(path: Path | None = None) -> P1PolicySnapshot:
    """Carica P1 dal contratto e rifiuta ogni deriva che la renderebbe altro.

    I controlli non sono difensivi per abitudine: ognuno corrisponde a una
    riga del contratto che, se cambiasse, farebbe misurare a P1 una politica
    diversa da quella pre-registrata. `max_signal_age_drives_exit` in
    particolare e' il confine fra "time-only" e "time piu' silenzio fonte".
    """
    if path is None:
        path = Path(__file__).resolve().parents[3] / "config" / "s4_exit_trial.yaml"
    raw = path.read_bytes()
    payload = yaml.safe_load(raw) or {}
    contract = payload.get("contract") or {}
    p1 = (payload.get("policies") or {}).get("P1") or {}
    horizon = payload.get("horizon") or {}
    overlay = payload.get("risk_overlay") or {}
    d_hard = overlay.get("d_hard") or {}

    if contract.get("scope") != "shadow_only" or contract.get("live_behaviour_changed"):
        raise ValueError("P1 contract must remain shadow-only")
    if p1.get("status") != "active" or p1.get("role") != "treatment":
        raise ValueError("P1 must be the active treatment")
    if p1.get("promotable") is not True:
        raise ValueError("P1 must stay promotable")
    if horizon.get("max_signal_age_drives_exit") is not False:
        raise ValueError(
            "P1 is time-only: max_signal_age cannot drive an exit"
        )
    if not d_hard.get("enabled"):
        raise ValueError("P1 requires the common d_hard overlay")
    if d_hard.get("identical_across_policies") is not True:
        raise ValueError("P1 d_hard must remain identical across policies")
    if d_hard.get("attributed_to_alpha_policy") is not False:
        raise ValueError("P1 d_hard cannot be attributed to the alpha policy")
    if any(
        bool((overlay.get(name) or {}).get("enabled"))
        for name in ("take_profit", "trailing", "scale_out", "tight_synthetic_stop")
    ):
        raise ValueError("P1 contract forbids TP, trailing, scale-out and tight stop")

    return P1PolicySnapshot(
        version=f"s4-exit-trial:{payload.get('version', 'unknown')}",
        scope=contract["scope"],
        promotable=True,
        d_hard_enabled=True,
        d_hard_attributed_to_alpha=False,
        max_signal_age_drives_exit=False,
        exit_rule=str(horizon.get("exit", "")),
        source_hash=hashlib.sha256(raw).hexdigest()[:16],
    )


def _d_hard_trigger(entry_price: float, distance: float | None) -> float | None:
    """Prezzo di trigger dello stop comune; senza distanza non esiste.

    Restituire `0.0` quando la distanza manca creerebbe uno stop che nessun
    prezzo puo' bucare — una policy silenziosamente diversa. Meglio dichiarare
    che non e' valutabile.
    """
    if distance is None or entry_price <= 0:
        return None
    return entry_price * (1.0 - float(distance))


def _first_breach(
    quotes: tuple[ExecutableQuote, ...], trigger: float | None
) -> ExecutableQuote | None:
    if trigger is None:
        return None
    for quote in quotes:
        if quote.low <= trigger:
            return quote
    return None


def _time_exit(
    quotes: tuple[ExecutableQuote, ...], cutoff_at: datetime | None
) -> tuple[ExecutableQuote | None, str]:
    """Uscita a scadenza secondo `exit_price_rule`, mai al closing print.

    Se un ordine sarebbe stato presentabile entro il cutoff, vale l'ultimo
    prezzo davvero scambiato prima di quel confine. Altrimenti vale il primo
    eseguibile successivo — non la close teorica di quella seduta, che nessuno
    avrebbe potuto ottenere.
    """
    if not quotes:
        return None, _EXIT_RULE_AT_CUTOFF
    if cutoff_at is None:
        return quotes[-1], _EXIT_RULE_AT_CUTOFF
    limite = _utc(cutoff_at)
    entro = [quote for quote in quotes if _utc(quote.at) <= limite]
    if entro:
        return entro[-1], _EXIT_RULE_AT_CUTOFF
    return quotes[0], _EXIT_RULE_AFTER_CUTOFF


def decide_p1(
    lifecycle: S4LifecycleEvent,
    window: P1MarketWindow,
    snapshot: P1PolicySnapshot,
    cost_model: CostModel,
    *,
    d_hard_distance: float | None,
    observed_at: datetime,
) -> P0ReplayEvent:
    """Decide P1 su un intento, senza inviare ordini ne' toccare target live.

    L'ordine dei rami e' la policy: prima le censure — un ingresso che non
    sappiamo ricostruire non e' un intento su cui misurare una exit — poi
    l'overlay di rischio comune, che precede la scadenza perche' e' l'unica
    uscita anticipata ammessa, e infine il time-stop. Ogni altro motivo per cui
    il runtime avrebbe venduto non compare qui: e' esattamente cio' che P1
    sostiene di non fare.

    `observed_at` non entra nell'identita' dell'evento: un secondo giro sullo
    stesso stato non deve produrre un secondo close.
    """
    quotes = tuple(sorted(window.quotes, key=lambda quote: _utc(quote.at)))
    entry_price = float(lifecycle.fill_price or 0.0)
    quantity = float(lifecycle.s4_virtual_quantity)
    initial_notional = quantity * entry_price
    trigger_price = _d_hard_trigger(entry_price, d_hard_distance)

    divergences: list[str] = []
    status = "OPEN"
    reason_code = REASON_HOLDING
    exit_quote: ExecutableQuote | None = None
    exit_rule: str | None = None

    if not lifecycle.reconstructible:
        status, reason_code = "CENSORED", REASON_ENTRY_NOT_RECONSTRUCTIBLE
        divergences.append("ENTRY_NOT_RECONSTRUCTIBLE")
    elif lifecycle.due_session is None:
        # Senza una seduta di scadenza deterministica non esiste il time-stop
        # che P1 sostiene di applicare: censurare e' l'unica lettura onesta.
        status, reason_code = "CENSORED", REASON_DUE_SESSION_UNKNOWN
        divergences.append("DUE_SESSION_UNKNOWN")
    elif lifecycle.policy_version != snapshot.version:
        status, reason_code = "CENSORED", "P1_POLICY_VERSION_MISMATCH"
        divergences.append("POLICY_VERSION_MISMATCH")
    else:
        if snapshot.d_hard_enabled and trigger_price is None:
            # Lo stop comune fa parte della policy: non poterlo valutare non
            # rende la misura sbagliata, la rende non confrontabile con P0.
            divergences.append("D_HARD_NOT_EVALUABLE")
        breach = _first_breach(quotes, trigger_price)
        if breach is not None:
            status, reason_code = "RISK_EXITED", REASON_D_HARD
            exit_quote, exit_rule = breach, "first_executable_after_trigger"
        elif window.complete:
            status, reason_code = "CLOSED", REASON_TIME_DUE
            exit_quote, exit_rule = _time_exit(quotes, window.cutoff_at)
            if exit_quote is None:
                # Criterio 4: un data failure non falsifica la tesi aperta. Il
                # time-stop resta osservabile, il P&L no.
                status, reason_code = "TRIGGERED", REASON_EXIT_PRICE_MISSING
                divergences.append("EXIT_PRICE_MISSING")

    virtual_quantity = 0.0 if exit_quote is None else quantity
    gross_pnl = entry_cost = exit_cost = net_pnl = None
    if exit_quote is not None and quantity > 0 and entry_price > 0:
        entry = cost_model.compute(
            symbol=lifecycle.symbol,
            notional=initial_notional,
            qty=quantity,
            fill_price=entry_price,
            side="BUY",
        )
        exit_breakdown = cost_model.compute(
            symbol=lifecycle.symbol,
            notional=quantity * exit_quote.price,
            qty=quantity,
            fill_price=exit_quote.price,
            side="SELL",
        )
        gross_pnl = (exit_quote.price - entry_price) * quantity
        entry_cost = float(entry.total_cost_usd)
        exit_cost = float(exit_breakdown.total_cost_usd)
        net_pnl = gross_pnl - entry_cost - exit_cost

    fingerprint = "|".join((
        lifecycle.intent_id,
        snapshot.version,
        snapshot.source_hash,
        "P1",
        reason_code,
        # Vedi #374: senza l'identita' dell'osservazione a monte, una
        # correzione del lifecycle produrrebbe lo stesso event_id e la
        # scrittura append-only la scarterebbe.
        lifecycle.event_id,
        # Il trigger di rischio e' un parametro della policy, non un dettaglio
        # del report: due decisioni con stop diversi sono decisioni diverse
        # anche quando oggi coincidono nel `reason_code`. Ometterlo faceva
        # scartare la correzione dalla scrittura append-only, come in #374.
        "no-d-hard" if trigger_price is None else f"{trigger_price:.12g}",
        "no-exit" if exit_quote is None else _utc(exit_quote.at).isoformat(),
        "no-exit" if exit_quote is None else f"{exit_quote.price:.12g}",
    ))
    return P0ReplayEvent(
        event_id=str(uuid5(_P1_NAMESPACE, fingerprint)),
        intent_id=lifecycle.intent_id,
        policy_id="P1",
        policy_version=snapshot.version,
        event_type="P1_TIME_ONLY_DECISION",
        observed_at=_utc(observed_at),
        d0=lifecycle.d0,
        symbol=lifecycle.symbol,
        status=status,
        reason_code=reason_code,
        trigger_at=(
            _utc(lifecycle.filled_at or lifecycle.observed_at)
            if exit_quote is None
            else _utc(exit_quote.at)
        ),
        virtual_exit_quantity=virtual_quantity,
        # P1 non ha una controparte runtime: il suo close esiste solo qui.
        runtime_quantity=0.0,
        first_executable_at=None if exit_quote is None else _utc(exit_quote.at),
        first_executable_price=None if exit_quote is None else exit_quote.price,
        first_executable_price_source=(
            "not_applicable:p1_holding"
            if exit_quote is None
            else "alpaca_bars.minute.executable"
        ),
        filled_at=None if exit_quote is None else _utc(exit_quote.at),
        fill_price=None if exit_quote is None else exit_quote.price,
        initial_notional=initial_notional,
        gross_pnl=gross_pnl,
        entry_cost_usd=entry_cost,
        exit_cost_usd=exit_cost,
        net_pnl=net_pnl,
        cost_model_version=cost_model.version,
        runtime_decision_id=None,
        runtime_order_id=None,
        shadow_order_id=None,
        comparable=not divergences,
        divergence_reasons=tuple(divergences),
        details={
            "entry_fill_id": lifecycle.fill_id,
            "entry_lifecycle_event_id": lifecycle.event_id,
            "entry_policy_version": lifecycle.policy_version,
            "due_session": (
                None if lifecycle.due_session is None else lifecycle.due_session.isoformat()
            ),
            "d_hard_distance": d_hard_distance,
            "d_hard_trigger_price": trigger_price,
            "attributed_to_alpha_policy": snapshot.d_hard_attributed_to_alpha,
            "exit_price_rule": exit_rule,
            "window_complete": window.complete,
            "quotes_considered": len(quotes),
            "snapshot_hash": snapshot.source_hash,
        },
    )
