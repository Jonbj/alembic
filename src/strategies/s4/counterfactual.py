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

from bisect import bisect_left, bisect_right
from collections import Counter
from collections.abc import Sequence
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
# Un intento ancora aperto non e' un'uscita che non sappiamo leggere: e'
# un'uscita che non c'e'. Tenerli distinti evita che il conteggio per famiglia
# faccia sembrare non classificata una policy che sta semplicemente tenendo.
EXIT_FAMILY_OPEN = "not_exited"
EXIT_FAMILY_UNCLASSIFIED = "unclassified"

# Stati in cui la policy ha davvero lasciato la posizione. Fuori da questi
# `exit_at` porta l'ultimo trigger osservato — un'osservazione, non un'uscita —
# e va trattato come tale. `TRIGGERED` e `CENSORED` restano fuori: la prima non
# ha ancora un prezzo eseguibile, la seconda non e' ricostruibile.
TERMINAL_STATUSES = frozenset({"CLOSED", "RISK_EXITED"})

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
    # Stati di attesa: la policy non e' uscita, non ha deciso male.
    "P1_HOLDING": EXIT_FAMILY_OPEN,
    "P0_RUNTIME_OPEN": EXIT_FAMILY_OPEN,
}


def classify_exit_reason(reason_code: str) -> str:
    """Famiglia economica di un reason code; sconosciuto resta non classificato."""
    return _EXIT_FAMILIES.get(reason_code, EXIT_FAMILY_UNCLASSIFIED)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def normalize_sessions(sessions: Sequence[date] | None) -> tuple[date, ...] | None:
    """Calendario di sedute in ordine crescente e senza duplicati; None resta None."""
    if sessions is None:
        return None
    return tuple(sorted(set(sessions)))


def _sessions_elapsed(
    d0: date, exit_date: date, sessions: tuple[date, ...]
) -> int | None:
    """Sedute trascorse fra D0 e l'uscita, contate sul calendario dato.

    Nessuna approssimazione a giorni di calendario: un D0 di venerdi' con
    uscita al martedi' successivo vale due sedute, non quattro giorni. Se il
    calendario non copre D0, o si ferma prima dell'uscita, il conteggio non e'
    determinato e vale None: e' la stessa scelta di `lifecycle.py`, che emette
    `CALENDAR_INCOMPLETE` invece di indovinare la seduta di scadenza.
    """
    if not sessions:
        return None
    if exit_date < d0:
        return 0
    start = bisect_left(sessions, d0)
    if start >= len(sessions) or sessions[start] != d0:
        return None
    if exit_date > sessions[-1]:
        return None
    end = bisect_right(sessions, exit_date) - 1
    return max(0, end - start)


def _capital_days(
    notional: float,
    d0: date | None,
    exit_at: datetime | None,
    sessions: tuple[date, ...] | None,
) -> float | None:
    """Capitale-giorni occupati, contati in sedute come l'orizzonte del contratto.

    L'orizzonte e' definito in sedute ("close di D0+2 sedute"), quindi la
    granularita' resta quella: un'uscita intraday a D0 vale zero sedute, la
    scadenza D+2 ne vale due. Contarle richiede un calendario, che il modulo
    non puo' dedurre: senza calendario la misura non esiste e vale None, mai
    un conteggio di giorni solari travestito da sedute. Il bias sarebbe
    monodirezionale — colpisce solo i D0 che attraversano un weekend — quindi
    proprio la forma che `slot_occupancy_capital_days_delta` non distingue dal
    segnale.
    """
    if d0 is None or exit_at is None or sessions is None:
        return None
    elapsed = _sessions_elapsed(d0, _utc(exit_at).date(), sessions)
    if elapsed is None:
        return None
    return notional * elapsed


def _outcome_capital_days(
    outcome: PolicyOutcome, sessions: tuple[date, ...] | None
) -> float | None:
    """Capitale-giorni di un intento sotto una policy, solo se e' davvero uscita.

    Una policy ancora aperta non ha occupato zero sedute: non lo sappiamo
    ancora. Il ledger le assegna comunque un `exit_at` — l'ultimo trigger
    osservato — e prenderlo per un'uscita pubblicherebbe uno zero proprio sulla
    policy che sta occupando il capitale piu' a lungo, invertendo il confronto
    di occupazione del criterio 3. La stessa nozione di uscita che
    `build_freed_slots` usa per aprire uno slot vale qui per misurarlo.
    """
    if outcome.status not in TERMINAL_STATUSES:
        return None
    return _capital_days(
        outcome.initial_notional, outcome.d0, outcome.exit_at, sessions
    )


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
    baseline_capital_days: float | None
    challenger_capital_days: float | None
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


def _challenger_scope(
    challengers: list[PolicyOutcome],
    baseline_policy_id: str,
    active_policies: tuple[str, ...] | None,
    challenger_policy_ids: tuple[str, ...] | None,
) -> tuple[str, ...]:
    """Le policy challenger di cui il confronto deve rendere conto per ogni intento.

    Serve a nominare la policy di una riga `PAIRED_CHALLENGER_MISSING`: senza
    un nome quella riga non appartiene a nessun confronto e sparisce dai
    filtri per policy, facendo dichiarare copertura piena su un campione
    dimezzato. L'ordine di preferenza va dall'esplicito all'osservato.
    """
    if challenger_policy_ids is not None:
        candidates: tuple[str, ...] = tuple(challenger_policy_ids)
    elif active_policies is not None:
        candidates = tuple(active_policies)
    else:
        candidates = tuple(outcome.policy_id for outcome in challengers)
    return tuple(
        dict.fromkeys(
            name for name in candidates if name and name != baseline_policy_id
        )
    )


def build_paired_comparison(
    baseline: list[PolicyOutcome],
    challengers: list[PolicyOutcome],
    *,
    baseline_policy_id: str = "P0",
    active_policies: tuple[str, ...] | None = None,
    challenger_policy_ids: tuple[str, ...] | None = None,
    sessions: Sequence[date] | None = None,
) -> PairedComparison:
    """Appaia baseline e challenger sullo stesso intento e verifica gli invarianti.

    Il contratto impone che intenti, fill, notional e costi d'ingresso siano
    condivisi fra le policy e che il capitale liberato non venga reinvestito
    (`freed_capital_reinvested: false`). Qui l'invariante e' *controllato*: una
    coppia che lo viola viene esclusa con reason code, non mediata comunque.

    `sessions` e' il calendario di borsa su cui si contano i capitale-giorni:
    e' lo stesso input che `lifecycle.reconcile_entry` gia' riceve. Omesso, i
    capitale-giorni restano `None` e la riconciliazione lo dichiara invece di
    pubblicare uno zero.

    Un intento della baseline senza controparte challenger produce una riga
    `PAIRED_CHALLENGER_MISSING` **per ogni** policy challenger in perimetro,
    nominata: e' l'unico modo perche' la copertura resti quella vera quando la
    challenger tiene alcuni intenti piu' a lungo degli altri.
    """
    calendar = normalize_sessions(sessions)
    by_intent = {
        outcome.intent_id: outcome
        for outcome in baseline
        if outcome.policy_id == baseline_policy_id
    }
    scope = _challenger_scope(
        challengers, baseline_policy_id, active_policies, challenger_policy_ids
    )
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
                    baseline_capital_days=None,
                    challenger_capital_days=_outcome_capital_days(
                        challenger, calendar
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
                baseline_capital_days=_outcome_capital_days(base, calendar),
                challenger_capital_days=_outcome_capital_days(
                    challenger, calendar
                ),
                comparable=comparable,
                exclusion_reasons=tuple(reasons),
            )
        )

    # La copertura e' per coppia (policy, intento): un intento che la P1 ha e la
    # P2 no resta scoperto per la P2, e la sua riga deve dirlo.
    covered = {
        (pair.policy_id, pair.intent_id)
        for pair in pairs
        if "PAIRED_UNSHARED_INTENT" not in pair.exclusion_reasons
    }
    for policy in scope:
        for intent_id, base in by_intent.items():
            if (policy, intent_id) in covered:
                continue
            pairs.append(
                PairedDelta(
                    intent_id=intent_id,
                    symbol=base.symbol,
                    d0=base.d0,
                    policy_id=policy,
                    baseline_policy_id=baseline_policy_id,
                    initial_notional=base.initial_notional,
                    baseline_net_pnl=base.net_pnl,
                    challenger_net_pnl=None,
                    delta_usd=None,
                    delta_bps=None,
                    baseline_exit_family=classify_exit_reason(base.exit_reason_code),
                    challenger_exit_family=None,
                    baseline_capital_days=_outcome_capital_days(base, calendar),
                    challenger_capital_days=None,
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
    s1_state_missing: bool = False


@dataclass(frozen=True)
class FreedSlot:
    """Uno slot liberato da un'uscita, con la finestra in cui resta disponibile."""

    intent_id: str
    symbol: str
    policy_id: str
    freed_at: datetime
    freed_notional: float
    slot_closes_at: datetime


@dataclass(frozen=True)
class SlotGap:
    """Un intento della coorte che non ha prodotto uno slot, e il motivo.

    Serve alla stessa ragione di `PAIRED_CHALLENGER_MISSING` nella vista
    appaiata: senza una riga, un opportunity cost *non ancora determinato* si
    legge come un opportunity cost *nullo*. Con la P1 che tiene fino a D+2 la
    maggior parte della coorte e' in quello stato a ogni esecuzione, quindi la
    differenza non e' teorica.
    """

    intent_id: str
    symbol: str
    reason_code: str


@dataclass(frozen=True)
class ReplacementRecord:
    """Una riga per slot liberato: cosa lo avrebbe occupato, e a che prezzo."""

    intent_id: str
    freed_symbol: str
    policy_id: str
    freed_at: datetime
    freed_notional: float
    slot_available: bool
    slot_days: float
    capital_days: float
    idle_capital_days: float
    substitute_symbol: str | None
    substitute_signal_id: int | None
    point_in_time_rank: int | None
    gross_pnl: float
    incremental_pnl: float
    entry_cost_usd: float | None
    exit_cost_usd: float | None
    cost_model_version: str | None
    reason_code: str
    candidates_considered: int
    rejected_candidates: tuple[tuple[str, str], ...]


def _candidate_rejection(
    candidate: SubstituteCandidate, slot: FreedSlot
) -> str | None:
    """Motivo di esclusione di un candidato, in ordine deterministico.

    L'ordine conta solo per la leggibilita' del report: un candidato escluso
    non rientra comunque. Il guard point-in-time viene per primo perche' e'
    l'unico che invaliderebbe la misura invece di limitarla.
    """
    if _utc(candidate.observed_at) > _utc(slot.freed_at):
        return "CANDIDATE_LOOKAHEAD"
    if _utc(candidate.universe_as_of) > _utc(slot.freed_at):
        return "CANDIDATE_UNIVERSE_NOT_POINT_IN_TIME"
    if candidate.rank is None:
        return "CANDIDATE_RANK_MISSING"
    if candidate.s1_state_missing:
        return "CANDIDATE_S1_STATE_MISSING"
    if candidate.collides_with_s1:
        return "CANDIDATE_S1_COLLISION"
    if not candidate.investable:
        return "CANDIDATE_CAPITAL_NOT_INVESTABLE"
    if candidate.entry_price <= 0:
        return "CANDIDATE_ENTRY_PRICE_MISSING"
    if candidate.exit_price is None:
        return "CANDIDATE_EXIT_PRICE_MISSING"
    return None


def _slots_overlap(left: FreedSlot, right: FreedSlot) -> bool:
    """Vero se le due finestre liberate condividono anche un solo istante."""
    return _utc(left.freed_at) < _utc(right.slot_closes_at) and _utc(
        right.freed_at
    ) < _utc(left.slot_closes_at)


def _choose_substitute(
    eligible: list[SubstituteCandidate],
) -> tuple[SubstituteCandidate | None, str, list[tuple[str, str]]]:
    """Il candidato che occupa lo slot, o il motivo per cui nessuno lo occupa."""
    if not eligible:
        return None, "NO_SUBSTITUTE_AVAILABLE", []
    best_rank = min(int(c.rank or 0) for c in eligible)
    tied = [c for c in eligible if int(c.rank or 0) == best_rank]
    outranked = [
        (c.symbol, "CANDIDATE_OUTRANKED")
        for c in eligible
        if int(c.rank or 0) != best_rank
    ]
    if len(tied) > 1:
        # Pari rank point-in-time: non c'e' un sostituto determinato, e
        # sceglierne uno significherebbe scegliere un P&L.
        return (
            None,
            "AMBIGUOUS_SUBSTITUTE",
            [(c.symbol, "CANDIDATE_AMBIGUOUS_RANK") for c in tied] + outranked,
        )
    return tied[0], REASON_REPLACEMENT, outranked


def build_portfolio_counterfactual(
    slots: list[FreedSlot],
    candidates_by_intent: dict[str, list[SubstituteCandidate]],
    *,
    sessions: Sequence[date],
    cost_model: CostModel | None = None,
) -> tuple[ReplacementRecord, ...]:
    """Misura, slot per slot, cosa avrebbe reso il capitale liberato.

    Vive separata dal test trade-level per costruzione: il contratto impone
    `opportunity_cost_reported: separatamente, a livello di portafoglio`. Un
    pari-merito fra candidati non sceglie il ramo favorevole: viene marcato
    ambiguo e non accredita nulla (`ambiguous_case` del contratto).

    `sessions` e' lo stesso calendario esplicito usato dalla vista paired. Gli
    slot si misurano in sedute, non in giorni wall-clock: senza questo input un
    intervallo venerdi'→martedi' sembrerebbe occupare quattro giorni invece di
    due e gonfierebbe in modo sistematico il capitale-giorni.

    La vista e' portfolio-level, quindi gli slot non sono indipendenti: un
    sostituto ne occupa **uno solo alla volta**. Due slot che si sovrappongono
    leggono lo stesso universo point-in-time e sceglierebbero lo stesso primo
    candidato, accreditando due volte un capitale che il portafoglio non
    aveva. Gli slot si servono in ordine di liberazione — quando il primo si
    libera il secondo non esiste ancora, che e' la stessa regola point-in-time
    dei candidati — e quelli liberati nello stesso istante non hanno una
    precedenza: un simbolo conteso non va a nessuno dei due, come per il pari
    rank. L'esclusiva vale dentro una policy: P0 e P1 sono due controfattuali
    distinti, non un portafoglio solo.
    """
    calendar = normalize_sessions(sessions)
    assert calendar is not None

    # Fase 1 — geometria dello slot e ammissibilita' del singolo candidato:
    # dipendono solo dallo slot, quindi restano fuori dall'allocazione.
    geometry: list[tuple[bool, float, float]] = []
    eligible_by_slot: list[list[SubstituteCandidate]] = []
    rejected_by_slot: list[list[tuple[str, str]]] = []
    for slot in slots:
        slot_available = _utc(slot.slot_closes_at) > _utc(slot.freed_at)
        slot_days = 0.0
        if slot_available:
            elapsed = _sessions_elapsed(
                _utc(slot.freed_at).date(),
                _utc(slot.slot_closes_at).date(),
                calendar,
            )
            if elapsed is None:
                raise ValueError(
                    f"market sessions do not cover freed slot {slot.intent_id}"
                )
            slot_days = float(elapsed)
        capital_days = slot.freed_notional * slot_days if slot_available else 0.0
        geometry.append((slot_available, slot_days, capital_days))

        rejected: list[tuple[str, str]] = []
        eligible: list[SubstituteCandidate] = []
        if slot_available:
            for candidate in candidates_by_intent.get(slot.intent_id, ()):
                reason = _candidate_rejection(candidate, slot)
                if reason is None:
                    eligible.append(candidate)
                else:
                    rejected.append((candidate.symbol, reason))
        eligible_by_slot.append(eligible)
        rejected_by_slot.append(rejected)

    # Fase 2 — allocazione cronologica: gli slot liberati nello stesso istante
    # formano un gruppo, perche' fra loro nessuno viene prima.
    order = sorted(
        range(len(slots)),
        key=lambda index: (_utc(slots[index].freed_at), slots[index].intent_id),
    )
    groups: list[list[int]] = []
    for index in order:
        if groups and _utc(slots[groups[-1][0]].freed_at) == _utc(
            slots[index].freed_at
        ):
            groups[-1].append(index)
        else:
            groups.append([index])

    held: list[tuple[str, FreedSlot]] = []
    chosen_by_slot: list[SubstituteCandidate | None] = [None] * len(slots)
    reason_by_slot: list[str] = ["NO_SUBSTITUTE_AVAILABLE"] * len(slots)
    for group in groups:
        for index in group:
            taken = [
                candidate
                for candidate in eligible_by_slot[index]
                if any(
                    symbol == candidate.symbol
                    and other.policy_id == slots[index].policy_id
                    and _slots_overlap(other, slots[index])
                    for symbol, other in held
                )
            ]
            for candidate in taken:
                eligible_by_slot[index].remove(candidate)
                rejected_by_slot[index].append(
                    (candidate.symbol, "CANDIDATE_SUBSTITUTE_ALREADY_HELD")
                )
        while True:
            wants = {
                index: _choose_substitute(eligible_by_slot[index])[0]
                for index in group
            }
            contested = {
                key
                for key, count in Counter(
                    (slots[index].policy_id, candidate.symbol)
                    for index, candidate in wants.items()
                    if candidate is not None
                ).items()
                if count > 1
            }
            if not contested:
                break
            for index, candidate in wants.items():
                if candidate is None:
                    continue
                if (slots[index].policy_id, candidate.symbol) not in contested:
                    continue
                eligible_by_slot[index].remove(candidate)
                rejected_by_slot[index].append(
                    (candidate.symbol, "CANDIDATE_CONTENDED_BY_SLOT")
                )
        for index in group:
            chosen, reason, outranked = _choose_substitute(eligible_by_slot[index])
            rejected_by_slot[index].extend(outranked)
            chosen_by_slot[index] = chosen
            reason_by_slot[index] = (
                reason if geometry[index][0] else "SLOT_NOT_AVAILABLE"
            )
            if chosen is not None:
                held.append((chosen.symbol, slots[index]))

    # Fase 3 — le righe, nell'ordine in cui gli slot sono stati dati.
    records: list[ReplacementRecord] = []
    for index, slot in enumerate(slots):
        slot_available, slot_days, capital_days = geometry[index]
        chosen = chosen_by_slot[index]
        gross = 0.0
        entry_cost = exit_cost = None
        if chosen is not None:
            assert chosen.exit_price is not None
            # Il capitale liberato e' la size del sostituto: lo slot non
            # cambia dimensione, cambia solo cosa lo occupa.
            quantity = slot.freed_notional / chosen.entry_price
            gross = (chosen.exit_price - chosen.entry_price) * quantity
            if cost_model is not None:
                entry_cost = float(
                    cost_model.compute(
                        symbol=chosen.symbol,
                        notional=slot.freed_notional,
                        qty=quantity,
                        fill_price=chosen.entry_price,
                        side="BUY",
                    ).total_cost_usd
                )
                exit_cost = float(
                    cost_model.compute(
                        symbol=chosen.symbol,
                        notional=quantity * chosen.exit_price,
                        qty=quantity,
                        fill_price=chosen.exit_price,
                        side="SELL",
                    ).total_cost_usd
                )

        incremental = gross - (entry_cost or 0.0) - (exit_cost or 0.0)
        records.append(
            ReplacementRecord(
                intent_id=slot.intent_id,
                freed_symbol=slot.symbol,
                policy_id=slot.policy_id,
                freed_at=_utc(slot.freed_at),
                freed_notional=slot.freed_notional,
                slot_available=slot_available,
                slot_days=slot_days,
                capital_days=capital_days,
                idle_capital_days=capital_days if chosen is None else 0.0,
                substitute_symbol=None if chosen is None else chosen.symbol,
                substitute_signal_id=None if chosen is None else chosen.signal_id,
                point_in_time_rank=None if chosen is None else chosen.rank,
                gross_pnl=gross,
                incremental_pnl=incremental,
                entry_cost_usd=entry_cost,
                exit_cost_usd=exit_cost,
                cost_model_version=(
                    None if cost_model is None else cost_model.version
                ),
                reason_code=reason_by_slot[index],
                candidates_considered=len(
                    candidates_by_intent.get(slot.intent_id, ())
                ),
                rejected_candidates=tuple(rejected_by_slot[index]),
            )
        )

    return tuple(records)


# ── Riconciliazione delle due viste (criterio 5) ────────────────────────────


@dataclass(frozen=True)
class Reconciliation:
    """Il ponte fra vista trade-level e vista portfolio-level, senza residui.

    L'identita' in dollari e' `portfolio_delta = trade_delta +
    replacement_challenger - replacement_baseline`: il controfattuale aggiunge
    al test appaiato la differenza fra cio' che il capitale liberato avrebbe
    reso sotto le due policy. La differenza di *occupazione* non e' in dollari
    — sono capitale-giorni — e resta riportata a parte, perche' e' proprio il
    caso in cui il delta per trade migliora mentre il rendimento sul capitale
    occupato peggiora (consolidato §7 punto 7).

    I capitale-giorni sono `None` — non zero — quando il calendario di borsa
    manca o non copre l'intera coppia: in quel caso `reconciled` e' falso con
    `CAPITAL_DAYS_NOT_COMPUTABLE`, cosi' la misura del criterio 3 non viene
    pubblicata al posto di un'occupazione davvero nulla.
    """

    policy_id: str
    trade_level_net_usd: float
    reinvestment_usd: float
    portfolio_level_net_usd: float
    unattributed_usd: float
    reconciled: bool
    blocking_reasons: tuple[str, ...]
    pairs_comparable: int
    pairs_excluded: int
    excluded_by_reason: dict[str, int]
    baseline_capital_days: float | None
    challenger_capital_days: float | None
    slot_occupancy_capital_days_delta: float | None
    idle_capital_days: float
    baseline_idle_capital_days: float
    challenger_idle_capital_days: float
    slots_total: int
    substitutes_selected: int


def reconcile_views(
    comparison: PairedComparison,
    records: tuple[ReplacementRecord, ...],
    *,
    policy_id: str,
) -> Reconciliation:
    """Riconcilia trade-level e portfolio-level attribuendo ogni differenza."""
    pairs = [pair for pair in comparison.pairs if pair.policy_id == policy_id]
    comparable = [pair for pair in pairs if pair.comparable]
    trade_level = sum(pair.delta_usd or 0.0 for pair in comparable)

    # Il reinvestimento conta solo se lo slot liberato appartiene a una coppia
    # comparabile: altrimenti c'e' un P&L di replacement che nessun delta
    # appaiato spiega, ed e' quello il residuo che la riconciliazione deve
    # esporre invece di assorbire nel totale.
    paired_intents = {pair.intent_id for pair in comparable}
    policy_sign = {
        comparison.baseline_policy_id: -1.0,
        policy_id: 1.0,
    }
    # Gli slot di una policy estranea alla coppia non appartengono a questo
    # confronto: ne' il loro P&L ne' la loro occupazione. Restringere una sola
    # delle due meta' renderebbe le diagnostiche incoerenti col netto.
    pair_records = [record for record in records if record.policy_id in policy_sign]
    replacements = [
        record for record in pair_records if record.reason_code == REASON_REPLACEMENT
    ]
    reinvestment = sum(
        policy_sign[record.policy_id] * record.incremental_pnl
        for record in replacements
        if record.intent_id in paired_intents
    )
    unattributed = sum(
        policy_sign[record.policy_id] * record.incremental_pnl
        for record in replacements
        if record.intent_id not in paired_intents
    )
    portfolio_level = trade_level + reinvestment + unattributed

    blocking: list[str] = []
    if not comparison.entries_frozen:
        # Il contratto vieta il reinvestimento nel test appaiato: se e'
        # avvenuto, la vista trade-level non misura piu' la sola exit.
        blocking.append("ENTRIES_NOT_FROZEN")
    if abs(unattributed) > _USD_TOLERANCE:
        blocking.append("UNATTRIBUTED_RESIDUAL")

    excluded = Counter(
        reason
        for pair in pairs
        if not pair.comparable
        for reason in pair.exclusion_reasons
    )
    # I capitale-giorni sono la misura del criterio 3: se anche una sola coppia
    # non li ha (calendario assente o incompleto) il totale non e' zero, non
    # esiste. Sommare con `or 0.0` pubblicherebbe un'occupazione piu' bassa del
    # vero proprio sulle coppie che restano aperte piu' a lungo.
    capital_days_known = all(
        pair.baseline_capital_days is not None
        and pair.challenger_capital_days is not None
        for pair in comparable
    )
    if capital_days_known:
        baseline_days: float | None = sum(
            pair.baseline_capital_days or 0.0 for pair in comparable
        )
        challenger_days: float | None = sum(
            pair.challenger_capital_days or 0.0 for pair in comparable
        )
        occupancy_delta: float | None = (challenger_days or 0.0) - (
            baseline_days or 0.0
        )
    else:
        baseline_days = challenger_days = occupancy_delta = None
        blocking.append("CAPITAL_DAYS_NOT_COMPUTABLE")

    return Reconciliation(
        policy_id=policy_id,
        trade_level_net_usd=trade_level,
        reinvestment_usd=reinvestment,
        portfolio_level_net_usd=portfolio_level,
        unattributed_usd=unattributed,
        reconciled=not blocking,
        blocking_reasons=tuple(blocking),
        pairs_comparable=len(comparable),
        pairs_excluded=len(pairs) - len(comparable),
        excluded_by_reason=dict(sorted(excluded.items())),
        baseline_capital_days=baseline_days,
        challenger_capital_days=challenger_days,
        slot_occupancy_capital_days_delta=occupancy_delta,
        idle_capital_days=sum(record.idle_capital_days for record in pair_records),
        baseline_idle_capital_days=sum(
            record.idle_capital_days
            for record in pair_records
            if record.policy_id == comparison.baseline_policy_id
        ),
        challenger_idle_capital_days=sum(
            record.idle_capital_days
            for record in pair_records
            if record.policy_id == policy_id
        ),
        slots_total=len(pair_records),
        substitutes_selected=sum(
            1 for record in pair_records if record.substitute_symbol is not None
        ),
    )


# ── Report (criterio 6) ────────────────────────────────────────────────────


def cohort_intents_for_window(
    comparison: PairedComparison,
    *,
    policy_id: str,
    window_start: date,
    window_end: date,
) -> set[str]:
    """Gli intent_id della coorte D0 pubblicata da questa finestra.

    Una sola definizione perche' i consumatori sono due — il dettaglio degli
    slot misurati e l'elenco di quelli che mancano — e due copie basterebbero a
    far descrivere loro campioni diversi, che e' il difetto che #333 e #412
    hanno gia' corretto altrove.
    """
    return {
        pair.intent_id
        for pair in comparison.pairs
        if pair.policy_id == policy_id
        and pair.d0 is not None
        and window_start <= pair.d0 <= window_end
    }


def replacement_records_for_window(
    comparison: PairedComparison,
    records: tuple[ReplacementRecord, ...],
    *,
    policy_id: str,
    window_start: date,
    window_end: date,
) -> tuple[ReplacementRecord, ...]:
    """Restringe il dettaglio portfolio alla stessa coorte D0 del paired."""
    if window_end < window_start:
        raise ValueError("validation window ends before it starts")
    cohort_intents = cohort_intents_for_window(
        comparison,
        policy_id=policy_id,
        window_start=window_start,
        window_end=window_end,
    )
    pair_policies = {comparison.baseline_policy_id, policy_id}
    return tuple(
        record
        for record in records
        if record.intent_id in cohort_intents and record.policy_id in pair_policies
    )


def build_replacement_report(
    comparison: PairedComparison,
    records: tuple[ReplacementRecord, ...],
    *,
    policy_id: str,
    window_start: date,
    window_end: date,
    without_slot: Sequence[SlotGap] = (),
    contract_path: Path | None = None,
) -> dict[str, object]:
    """Le due viste in una riga logica per finestra, con i residui contati."""
    if window_end < window_start:
        raise ValueError("validation window ends before it starts")

    in_window = tuple(
        pair
        for pair in comparison.pairs
        if pair.d0 is not None and window_start <= pair.d0 <= window_end
    )
    # Anche gli invarianti vanno riletti sulla coorte: un intento challenger
    # senza baseline e' un trade nato dal cash liberato, ma se il suo D0 cade
    # fuori dalla finestra appartiene a un altro report, dove ha una coppia e
    # uno slot. Ereditarlo qui dichiarerebbe `ENTRIES_NOT_FROZEN` — e quindi
    # non riconciliata — una finestra in cui nessun ingresso e' stato creato,
    # cioe' esattamente il contrario di cio' che la guardia deve dire.
    new_trades = sum(
        1
        for pair in in_window
        if "PAIRED_UNSHARED_INTENT" in pair.exclusion_reasons
    )
    windowed = PairedComparison(
        baseline_policy_id=comparison.baseline_policy_id,
        pairs=in_window,
        entries_frozen=new_trades == 0,
        new_trades_created=new_trades,
        excluded_by_reason=dict(
            sorted(
                Counter(
                    reason
                    for pair in in_window
                    for reason in pair.exclusion_reasons
                ).items()
            )
        ),
    )
    # Stesso perimetro del netto riconciliato: coorte D0 *e* coppia di policy.
    # Filtrare gli slot sulla data di liberazione mescolerebbe due coorti: un
    # intento entrato a fine finestra perderebbe l'opportunity cost D+1/D+2,
    # mentre uno entrato prima potrebbe rientrare soltanto perche' esce dentro
    # la finestra. La coorte e' gia' congelata dagli intent_id della vista
    # paired, quindi anche la vista portfolio-level usa quelli.
    slots = replacement_records_for_window(
        comparison,
        records,
        policy_id=policy_id,
        window_start=window_start,
        window_end=window_end,
    )
    # Stessa coorte anche per i buchi: un intento fuori finestra non porta
    # dentro il proprio motivo, altrimenti il blocco `slots` tornerebbe a
    # descrivere un campione diverso da quello pubblicato sopra.
    cohort_intents = cohort_intents_for_window(
        comparison,
        policy_id=policy_id,
        window_start=window_start,
        window_end=window_end,
    )
    gaps = tuple(gap for gap in without_slot if gap.intent_id in cohort_intents)
    reconciliation = reconcile_views(windowed, slots, policy_id=policy_id)
    hierarchy = active_policy_hierarchy(contract_path)

    return {
        "window_start": window_start.isoformat(),
        "window_end": window_end.isoformat(),
        "policy_id": policy_id,
        "baseline_policy_id": comparison.baseline_policy_id,
        "policy_hierarchy": list(hierarchy),
        "p2_omitted_by_contract": "P2" not in hierarchy,
        "paired": {
            "total": len([p for p in in_window if p.policy_id == policy_id]),
            "comparable": reconciliation.pairs_comparable,
            "excluded": reconciliation.pairs_excluded,
            "excluded_by_reason": reconciliation.excluded_by_reason,
            "entries_frozen": windowed.entries_frozen,
            "new_trades_created": windowed.new_trades_created,
            "mean_delta_bps": windowed.mean_delta_bps(policy_id),
            "net_delta_usd": windowed.net_delta_usd(policy_id),
        },
        "slots": {
            "total": len(slots),
            # `total` da solo non distingue "nessun opportunity cost" da "non
            # ancora determinato": `total + without_slot` copre la coorte.
            "without_slot": len(gaps),
            "without_slot_by_reason": dict(
                sorted(Counter(gap.reason_code for gap in gaps).items())
            ),
            "substitutes_selected": reconciliation.substitutes_selected,
            "by_reason": dict(
                sorted(Counter(record.reason_code for record in slots).items())
            ),
            "rejected_by_reason": dict(
                sorted(
                    Counter(
                        reason
                        for record in slots
                        for _, reason in record.rejected_candidates
                    ).items()
                )
            ),
            "capital_days": sum(record.capital_days for record in slots),
            "idle_capital_days": reconciliation.idle_capital_days,
            "baseline_idle_capital_days": reconciliation.baseline_idle_capital_days,
            "challenger_idle_capital_days": (
                reconciliation.challenger_idle_capital_days
            ),
            "incremental_pnl_usd": reconciliation.reinvestment_usd,
        },
        "reconciliation": {
            "trade_level_net_usd": reconciliation.trade_level_net_usd,
            "reinvestment_usd": reconciliation.reinvestment_usd,
            "portfolio_level_net_usd": reconciliation.portfolio_level_net_usd,
            "unattributed_usd": reconciliation.unattributed_usd,
            "slot_occupancy_capital_days_delta": (
                reconciliation.slot_occupancy_capital_days_delta
            ),
            "reconciled": reconciliation.reconciled,
            "blocking_reasons": list(reconciliation.blocking_reasons),
        },
    }
