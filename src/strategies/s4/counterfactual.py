"""Replacement e opportunity cost del trial exit S4 (#298).

Il modulo produce due viste riconciliate sopra gli esiti per-policy prodotti a
monte (#295 lifecycle, #296 baseline P0):

1. un **confronto paired** con ingressi congelati, dove il cash liberato non
   crea nuovi trade;
2. un **controfattuale portfolio-level** che misura replacement, slot-day e
   capitale-giorni, riportato separatamente dal test trade-level.

Le regole implementate non sono scelte qui: vengono dalla sezione
`counterfactuals` del contratto congelato (`config/s4_exit_trial.yaml`,
firmato il 2026-08-22) e da `docs/s4-exit-research-2026-08-14/consolidato_exit.md`
§5 e §7.2. Il modulo e' puro: non conosce broker, DB, ne' universo live, e non
tocca alcuna taratura.

Invariante di misura: il confronto paired **verifica** che ingressi, fill e
notional siano condivisi, invece di assumerlo. Una policy che li cambia viene
esclusa con un reason code, non misurata male.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Protocol

import yaml

from src.strategies.s4.p0_baseline import P0ReplayEvent

_NOTIONAL_TOLERANCE = 1e-6
_USD_TOLERANCE = 1e-6

# ── Famiglie di uscita (criterio 2) ─────────────────────────────────────────
# `replacement` e' una decisione di capacita', non una falsificazione della
# tesi: il consolidato §26 avverte che E0 le aggrega e che una SELL cosi'
# prodotta non prova il decadimento dell'alpha. Le quattro famiglie restano
# quindi disgiunte.
EXIT_FAMILY_TIME_STOP = "time_stop"
EXIT_FAMILY_COUNTER_QUALIFIED = "counter_qualified"
EXIT_FAMILY_RISK_CATASTROPHE = "risk_catastrophe"
EXIT_FAMILY_REPLACEMENT = "replacement"
EXIT_FAMILY_COUNTER_UNQUALIFIED = "counter_unqualified"
EXIT_FAMILY_FRESHNESS = "freshness_or_silence"
EXIT_FAMILY_UNCLASSIFIED = "unclassified"

# Reason code emesso da questo modulo quando il controfattuale attribuisce
# l'uscita alla riallocazione di uno slot. Non riusa nessun codice P0/P1/P2:
# l'attribuzione replacement e' portfolio-level, non trade-level.
REASON_REPLACEMENT = "REPLACEMENT_SLOT_REALLOCATED"

_EXIT_FAMILIES: dict[str, str] = {
    "P1_TIME_DUE": EXIT_FAMILY_TIME_STOP,
    "P2_COUNTER_QUALIFIED": EXIT_FAMILY_COUNTER_QUALIFIED,
    "P0_D_HARD": EXIT_FAMILY_RISK_CATASTROPHE,
    "P1_D_HARD": EXIT_FAMILY_RISK_CATASTROPHE,
    "P2_D_HARD": EXIT_FAMILY_RISK_CATASTROPHE,
    REASON_REPLACEMENT: EXIT_FAMILY_REPLACEMENT,
    # Il reversal ordinario di E0 non e' il counter qualificato di P2: quello
    # richiede due signal_id distinti, non-fallback e score <= -0.30.
    "P0_SENTIMENT_REVERSAL": EXIT_FAMILY_COUNTER_UNQUALIFIED,
    # Silenzio fonte, scadenza e filtri: ne' thesis exit ne' replacement.
    "P0_TARGET_ZERO_NO_SIGNAL": EXIT_FAMILY_FRESHNESS,
    "P0_TARGET_ZERO_EXPIRED": EXIT_FAMILY_FRESHNESS,
    "P0_TARGET_ZERO_WHIPSAW": EXIT_FAMILY_FRESHNESS,
    "P0_TARGET_ZERO_UNKNOWN": EXIT_FAMILY_FRESHNESS,
    "P0_TARGET_ZERO_BELOW_ENTRY_GATE": EXIT_FAMILY_FRESHNESS,
    "P0_TARGET_ZERO_FALLBACK_FILTERED": EXIT_FAMILY_FRESHNESS,
    "P0_TARGET_ZERO_ENTRY_FRESHNESS_FILTERED": EXIT_FAMILY_FRESHNESS,
}


def classify_exit_reason(reason_code: str) -> str:
    """Famiglia economica di un reason code; sconosciuto resta non classificato."""
    return _EXIT_FAMILIES.get(reason_code, EXIT_FAMILY_UNCLASSIFIED)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


# ── Esito per-policy: la forma che P0 in main soddisfa gia' ─────────────────


@dataclass(frozen=True)
class PolicyOutcome:
    """Esito di un intento sotto una policy, condiviso da P0 e challenger."""

    intent_id: str
    policy_id: str
    symbol: str
    d0: date | None
    entry_fill_id: str | None
    initial_notional: float
    status: str
    exit_reason_code: str
    exit_at: datetime | None
    virtual_exit_quantity: float
    net_pnl: float | None
    comparable: bool


def outcome_from_p0_event(event: P0ReplayEvent) -> PolicyOutcome:
    """Adatta un `P0ReplayEvent` senza reinterpretarne stato o reason code."""
    return PolicyOutcome(
        intent_id=event.intent_id,
        policy_id=event.policy_id,
        symbol=event.symbol,
        d0=event.d0,
        entry_fill_id=(
            str(event.details.get("entry_fill_id"))
            if event.details.get("entry_fill_id") is not None
            else None
        ),
        initial_notional=float(event.initial_notional),
        status=event.status,
        exit_reason_code=event.reason_code,
        exit_at=event.filled_at or event.trigger_at,
        virtual_exit_quantity=float(event.virtual_exit_quantity),
        net_pnl=None if event.net_pnl is None else float(event.net_pnl),
        comparable=bool(event.comparable),
    )


def active_policy_hierarchy(path: Path | None = None) -> tuple[str, ...]:
    """Gerarchia delle policy attive letta dal contratto, `omitted` esclusa.

    P2 e' dichiarata nella famiglia ma `omitted` a n=0: la sua attivazione
    richiede una pre-registrazione propria con MDE_counter fissato prima di
    guardare dati P2. Escluderla qui evita che entri nel trial per rinomina.
    """
    if path is None:
        path = Path(__file__).resolve().parents[3] / "config" / "s4_exit_trial.yaml"
    payload = yaml.safe_load(path.read_bytes()) or {}
    policies = payload.get("policies") or {}
    hierarchy = tuple(
        name
        for name in ("P0", "P1", "P2")
        if (policies.get(name) or {}).get("status") == "active"
    )
    if "P0" not in hierarchy:
        raise ValueError("the frozen contract must keep P0 active as benchmark")
    return hierarchy


# ── Vista 1: confronto paired con ingressi congelati (criterio 1) ───────────


@dataclass(frozen=True)
class PairedDelta:
    intent_id: str
    symbol: str
    d0: date | None
    policy_id: str
    baseline_policy_id: str
    initial_notional: float | None
    baseline_net_pnl: float | None
    challenger_net_pnl: float | None
    delta_usd: float | None
    delta_bps: float | None
    baseline_exit_family: str | None
    challenger_exit_family: str | None
    comparable: bool
    exclusion_reasons: tuple[str, ...]


@dataclass(frozen=True)
class PairedComparison:
    baseline_policy_id: str
    pairs: tuple[PairedDelta, ...]
    entries_frozen: bool
    new_trades_created: int
    excluded_by_reason: dict[str, int]

    @property
    def comparable_pairs(self) -> tuple[PairedDelta, ...]:
        return tuple(pair for pair in self.pairs if pair.comparable)

    def net_delta_usd(self, policy_id: str) -> float:
        """Somma dei delta appaiati netti, ingressi congelati e zero reinvestimenti."""
        return sum(
            pair.delta_usd or 0.0
            for pair in self.comparable_pairs
            if pair.policy_id == policy_id
        )

    def mean_delta_bps(self, policy_id: str) -> float | None:
        """Metrica primaria del contratto: media dei delta appaiati netti in bps."""
        values = [
            pair.delta_bps
            for pair in self.comparable_pairs
            if pair.policy_id == policy_id and pair.delta_bps is not None
        ]
        return sum(values) / len(values) if values else None


def build_paired_comparison(
    baseline: list[PolicyOutcome],
    challengers: list[PolicyOutcome],
    *,
    baseline_policy_id: str = "P0",
    active_policies: tuple[str, ...] | None = None,
) -> PairedComparison:
    """Appaia baseline e challenger sullo stesso intento e verifica gli invarianti.

    Il contratto impone che intenti, fill, notional e costi d'ingresso siano
    condivisi fra le policy e che il capitale liberato non venga reinvestito
    (`freed_capital_reinvested: false`). Qui l'invariante e' *controllato*: una
    coppia che lo viola viene esclusa con reason code, non mediata comunque.
    """
    by_intent = {
        outcome.intent_id: outcome
        for outcome in baseline
        if outcome.policy_id == baseline_policy_id
    }
    pairs: list[PairedDelta] = []
    new_trades = 0

    for challenger in challengers:
        reasons: list[str] = []
        if active_policies is not None and challenger.policy_id not in active_policies:
            reasons.append("POLICY_OMITTED_BY_CONTRACT")

        base = by_intent.get(challenger.intent_id)
        if base is None:
            # Un intento che esiste solo per la challenger significa che il cash
            # liberato ha creato un trade: e' la violazione che il test primario
            # deve rendere visibile, non un dato da scartare in silenzio.
            new_trades += 1
            reasons.append("PAIRED_UNSHARED_INTENT")
            pairs.append(
                PairedDelta(
                    intent_id=challenger.intent_id,
                    symbol=challenger.symbol,
                    d0=challenger.d0,
                    policy_id=challenger.policy_id,
                    baseline_policy_id=baseline_policy_id,
                    initial_notional=None,
                    baseline_net_pnl=None,
                    challenger_net_pnl=challenger.net_pnl,
                    delta_usd=None,
                    delta_bps=None,
                    baseline_exit_family=None,
                    challenger_exit_family=classify_exit_reason(
                        challenger.exit_reason_code
                    ),
                    comparable=False,
                    exclusion_reasons=tuple(reasons),
                )
            )
            continue

        if base.symbol != challenger.symbol:
            reasons.append("PAIRED_SYMBOL_MISMATCH")
        if base.d0 != challenger.d0:
            reasons.append("PAIRED_D0_MISMATCH")
        if base.entry_fill_id != challenger.entry_fill_id:
            reasons.append("PAIRED_ENTRY_FILL_MISMATCH")
        if (
            abs(base.initial_notional - challenger.initial_notional)
            > _NOTIONAL_TOLERANCE
        ):
            reasons.append("PAIRED_NOTIONAL_MISMATCH")
        if base.initial_notional <= 0:
            reasons.append("PAIRED_NOTIONAL_NOT_POSITIVE")
        if not base.comparable:
            reasons.append("PAIRED_BASELINE_NOT_COMPARABLE")
        if not challenger.comparable:
            reasons.append("PAIRED_CHALLENGER_NOT_COMPARABLE")
        if base.net_pnl is None or challenger.net_pnl is None:
            reasons.append("PAIRED_NET_PNL_MISSING")

        comparable = not reasons
        delta_usd = delta_bps = None
        if comparable:
            assert base.net_pnl is not None and challenger.net_pnl is not None
            delta_usd = challenger.net_pnl - base.net_pnl
            # Denominatore del contratto: notional iniziale dell'intento,
            # identico fra le policy per costruzione appena verificata.
            delta_bps = delta_usd / base.initial_notional * 10_000.0

        pairs.append(
            PairedDelta(
                intent_id=challenger.intent_id,
                symbol=challenger.symbol,
                d0=challenger.d0,
                policy_id=challenger.policy_id,
                baseline_policy_id=baseline_policy_id,
                initial_notional=base.initial_notional,
                baseline_net_pnl=base.net_pnl,
                challenger_net_pnl=challenger.net_pnl,
                delta_usd=delta_usd,
                delta_bps=delta_bps,
                baseline_exit_family=classify_exit_reason(base.exit_reason_code),
                challenger_exit_family=classify_exit_reason(
                    challenger.exit_reason_code
                ),
                comparable=comparable,
                exclusion_reasons=tuple(reasons),
            )
        )

    covered = {
        pair.intent_id for pair in pairs if "PAIRED_UNSHARED_INTENT" not in
        pair.exclusion_reasons
    }
    for intent_id, base in by_intent.items():
        if intent_id in covered:
            continue
        pairs.append(
            PairedDelta(
                intent_id=intent_id,
                symbol=base.symbol,
                d0=base.d0,
                policy_id="",
                baseline_policy_id=baseline_policy_id,
                initial_notional=base.initial_notional,
                baseline_net_pnl=base.net_pnl,
                challenger_net_pnl=None,
                delta_usd=None,
                delta_bps=None,
                baseline_exit_family=classify_exit_reason(base.exit_reason_code),
                challenger_exit_family=None,
                comparable=False,
                exclusion_reasons=("PAIRED_CHALLENGER_MISSING",),
            )
        )

    excluded = Counter(
        reason for pair in pairs for reason in pair.exclusion_reasons
    )
    return PairedComparison(
        baseline_policy_id=baseline_policy_id,
        pairs=tuple(pairs),
        entries_frozen=new_trades == 0,
        new_trades_created=new_trades,
        excluded_by_reason=dict(sorted(excluded.items())),
    )


# ── Vista 2: controfattuale portfolio-level (criteri 3 e 4) ─────────────────


class CostModel(Protocol):
    version: str

    def compute(
        self,
        *,
        symbol: str,
        notional: float,
        qty: float,
        fill_price: float,
        side: str,
    ): ...


@dataclass(frozen=True)
class SubstituteCandidate:
    """Candidato sostitutivo, con la provenienza point-in-time che lo qualifica."""

    symbol: str
    signal_id: int | None
    rank: int | None
    observed_at: datetime
    universe_as_of: datetime
    entry_price: float
    exit_price: float | None
    investable: bool
    collides_with_s1: bool
    investable_reason: str | None = None


@dataclass(frozen=True)
class FreedSlot:
    """Uno slot liberato da un'uscita, con la finestra in cui resta disponibile."""

    intent_id: str
    symbol: str
    policy_id: str
    freed_at: datetime
    freed_notional: float
    slot_closes_at: datetime
