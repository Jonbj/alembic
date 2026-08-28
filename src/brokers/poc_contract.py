"""Contratto PoC del secondo broker e suo valutatore (#363).

Il modulo decide `PASS`, `CONDITIONAL_PASS` o `FAIL` per un candidato (Saxo,
IBKR) e, fra due candidati, produce la raccomandazione che il gate #360 legge.
Va costruito e testato **prima** di qualunque accesso ai provider: per questo è
puro, deterministico, e non conosce né rete né credenziali.

Le regole vengono dal contratto congelato (`config/broker_poc_contract.yaml`) e
dalla spec `docs/superpowers/specs/2026-08-28-second-broker-poc-contract-design.md`:

- lo **stesso** contratto si applica a entrambi i candidati; solo i kill criteria
  sono per costruzione anche broker-specifici;
- una dimensione `blocking` fallita o **non testata** è un `FAIL`: «non l'abbiamo
  provato» non è un successo parziale;
- una dimensione `graded` non superata è un rischio residuo che il gate deve
  accettare esplicitamente, mai un pass silenzioso;
- un fatto dichiarato provato in un ambiente che il contratto non ammette per
  quella dimensione (il costo contrattuale italiano «misurato in SIM») viene
  declassato a `NOT_TESTED`;
- un kill criterion scattato annulla ogni altra evidenza;
- il confronto fra due `CONDITIONAL_PASS` è **lessicografico** su tie-breaker
  congelati, non un punteggio scalare: un numero unico permetterebbe di scegliere
  i pesi dopo aver visto i risultati. Un pareggio pieno è `NO_DECISION`.

Il valutatore rifiuta un report prodotto contro una versione o un hash di
contratto diversi: è il meccanismo che impedisce di modificare il contratto dopo
aver visto i risultati e ri-valutare come se nulla fosse.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping, Sequence

import yaml

ENV_SIM = "SIM"
ENV_LIVE_READONLY = "LIVE_READONLY"
ENV_OPERATOR = "OPERATOR"
ENV_DOC = "DOC"
# Presente solo per essere vietato: il perimetro delle issue #361/#364 esclude
# qualunque ordine live, e il contratto non può reintrodurlo di straforo.
ENV_LIVE_ORDER = "LIVE_ORDER"

_ADMITTED_ENVIRONMENTS = frozenset({ENV_SIM, ENV_LIVE_READONLY, ENV_OPERATOR, ENV_DOC})

KIND_BLOCKING = "blocking"
KIND_GRADED = "graded"

STATUS_PASS = "PASS"
STATUS_FAIL = "FAIL"
STATUS_NOT_TESTED = "NOT_TESTED"
_ADMITTED_STATUSES = frozenset({STATUS_PASS, STATUS_FAIL, STATUS_NOT_TESTED})

VERDICT_PASS = "PASS"
VERDICT_CONDITIONAL_PASS = "CONDITIONAL_PASS"
VERDICT_FAIL = "FAIL"

# Ordine dei verdetti nel confronto: un CONDITIONAL non batte un PASS, e un FAIL
# non si confronta con nulla.
_VERDICT_RANK = {VERDICT_PASS: 2, VERDICT_CONDITIONAL_PASS: 1, VERDICT_FAIL: 0}

RECOMMEND_SAXO = "SAXO"
RECOMMEND_IBKR = "IBKR"
RECOMMEND_ALPACA_ONLY = "ALPACA_ONLY"
RECOMMEND_NO_DECISION = "NO_DECISION"

# I mercati che la issue #363 richiede nel paniere minimo. Sono qui e non solo
# nella prosa perché togliere uno slot dopo la firma deve rompere il caricamento,
# non passare inosservato.
_REQUIRED_MICS: tuple[frozenset[str], ...] = (
    frozenset({"XMIL"}),           # Italia
    frozenset({"XETR"}),           # Xetra
    frozenset({"XPAR", "XAMS"}),   # Euronext
    frozenset({"XLON"}),           # LSE
    frozenset({"XNAS", "XNYS"}),   # USA
    frozenset({"XJPX", "XHKG"}),   # almeno un mercato APAC
)

# Metriche che il valutatore ricava dagli esiti: un report non può dichiararle,
# altrimenti basterebbe scriverne una migliore.
_DERIVED_METRICS = frozenset({
    "graded_failed_count",
    "graded_not_tested_count",
    "mandatory_slots_resolved_count",
})


@dataclass(frozen=True)
class BasketSlot:
    """Uno slot del paniere minimo, identico per entrambi i candidati."""

    id: str
    market: str
    mic: str
    asset_class: str
    currency: str
    mandatory: bool
    reference_name: str | None = None
    isin: str | None = None
    round_lot: int | None = None
    quoted_minor_unit: str | None = None
    expected_outcome: str | None = None


@dataclass(frozen=True)
class Dimension:
    """Una riga della matrice comune."""

    id: str
    title: str
    kind: str
    verifiable_in: tuple[str, ...]
    feeds_final_gate: bool
    kill_criteria: tuple[str, ...]


@dataclass(frozen=True)
class KillCriterion:
    id: str
    title: str
    applies_to: tuple[str, ...]


@dataclass(frozen=True)
class TieBreaker:
    metric: str
    direction: str
    best_possible: float
    worst_possible: float


@dataclass(frozen=True)
class Contingency:
    name: str
    scope: str
    trigger: str
    poc_authorized: bool


@dataclass(frozen=True)
class PocContract:
    """La parte del contratto che un valutatore sa decidere."""

    version: str
    signed_at: str
    source_hash: str
    brokers: tuple[str, ...]
    ambiguous_timeout_dimension: str
    basket_gate_dimension: str
    basket: tuple[BasketSlot, ...]
    dimensions: Mapping[str, Dimension]
    kill_criteria: Mapping[str, KillCriterion]
    tie_breakers: tuple[TieBreaker, ...]
    contingencies: Mapping[str, Contingency]

    def blocking_ids(self) -> tuple[str, ...]:
        return tuple(d.id for d in self.dimensions.values() if d.kind == KIND_BLOCKING)

    def graded_ids(self) -> tuple[str, ...]:
        return tuple(d.id for d in self.dimensions.values() if d.kind == KIND_GRADED)

    def gate_evidence_ids(self) -> tuple[str, ...]:
        return tuple(d.id for d in self.dimensions.values() if d.feeds_final_gate)

    def mandatory_slot_ids(self) -> tuple[str, ...]:
        return tuple(s.id for s in self.basket if s.mandatory)


@dataclass(frozen=True)
class DimensionOutcome:
    """L'esito di una dimensione così come il report del PoC la dichiara."""

    dimension_id: str
    status: str
    environment: str
    evidence_ref: str | None = None
    note: str | None = None


@dataclass(frozen=True)
class PocResult:
    """Il report di un PoC, nella forma che il valutatore accetta."""

    broker: str
    contract_version: str
    contract_source_hash: str
    outcomes: tuple[DimensionOutcome, ...]
    kill_criteria_tripped: tuple[str, ...] = ()
    resolved_slot_ids: tuple[str, ...] = ()
    metrics: Mapping[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class BrokerVerdict:
    broker: str
    verdict: str
    blocking_failed: tuple[str, ...]
    graded_failed: tuple[str, ...]
    not_tested: tuple[str, ...]
    kills_tripped: tuple[str, ...]
    residual_risks: tuple[str, ...]
    notes: tuple[str, ...]
    metrics: Mapping[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class GateComparison:
    recommendation: str
    winner: str | None
    tie_breaker_used: str | None
    rationale: tuple[str, ...]


def load_poc_contract(path: Path | None = None) -> PocContract:
    """Carica il contratto congelato e rifiuta le derive strutturali."""
    if path is None:
        path = Path(__file__).resolve().parents[2] / "config" / "broker_poc_contract.yaml"
    raw = path.read_bytes()
    payload = yaml.safe_load(raw) or {}

    brokers = tuple(payload.get("brokers") or ())
    if len(brokers) < 2 or len(set(brokers)) != len(brokers):
        raise ValueError("il contratto richiede almeno due candidati distinti")

    dimensions: dict[str, Dimension] = {}
    for dim_id, spec in (payload.get("dimensions") or {}).items():
        kind = spec.get("kind")
        if kind not in (KIND_BLOCKING, KIND_GRADED):
            raise ValueError(f"{dim_id}: kind non ammesso: {kind!r}")
        environments = tuple(spec.get("verifiable_in") or ())
        if not environments:
            raise ValueError(f"{dim_id}: verifiable_in non può essere vuoto")
        unknown = set(environments) - _ADMITTED_ENVIRONMENTS
        if unknown:
            # `LIVE_ORDER` finisce qui: il contratto non può richiedere un ordine
            # live, perché i PoC #361/#364 non lo autorizzano.
            raise ValueError(f"{dim_id}: ambienti non ammessi: {sorted(unknown)}")
        dimensions[dim_id] = Dimension(
            id=dim_id,
            title=spec.get("title", dim_id),
            kind=kind,
            verifiable_in=environments,
            feeds_final_gate=bool(spec.get("feeds_final_gate")),
            kill_criteria=tuple(spec.get("kill_criteria") or ()),
        )
    if not dimensions:
        raise ValueError("il contratto non dichiara nessuna dimensione")

    kill_criteria: dict[str, KillCriterion] = {}
    for kill_id, spec in (payload.get("kill_criteria") or {}).items():
        applies_to = tuple(spec.get("applies_to") or ())
        if not applies_to or not set(applies_to) <= set(brokers):
            raise ValueError(f"{kill_id}: applies_to fuori dai candidati: {applies_to}")
        kill_criteria[kill_id] = KillCriterion(
            id=kill_id, title=spec.get("title", kill_id), applies_to=applies_to
        )
    dangling = {
        ref
        for dim in dimensions.values()
        for ref in dim.kill_criteria
        if ref not in kill_criteria
    }
    if dangling:
        raise ValueError(f"kill criteria citati e non definiti: {sorted(dangling)}")

    basket = tuple(
        BasketSlot(
            id=slot["id"],
            market=slot["market"],
            mic=slot["mic"],
            asset_class=slot["asset_class"],
            currency=slot["currency"],
            mandatory=bool(slot.get("mandatory")),
            reference_name=slot.get("reference_name"),
            isin=slot.get("isin"),
            round_lot=slot.get("round_lot"),
            quoted_minor_unit=slot.get("quoted_minor_unit"),
            expected_outcome=slot.get("expected_outcome"),
        )
        for slot in (payload.get("basket") or ())
    )
    slot_ids = [s.id for s in basket]
    if len(set(slot_ids)) != len(slot_ids):
        raise ValueError("id di slot duplicati nel paniere")
    mandatory_mics = {s.mic for s in basket if s.mandatory}
    for required in _REQUIRED_MICS:
        if not required & mandatory_mics:
            raise ValueError(
                f"il paniere obbligatorio non copre nessuno di {sorted(required)}"
            )

    tie_breakers: list[TieBreaker] = []
    for spec in payload.get("tie_breakers") or ():
        if spec.get("direction") not in ("min", "max"):
            raise ValueError(f"{spec.get('metric')}: direction non ammessa")
        tie_breakers.append(
            TieBreaker(
                metric=spec["metric"],
                direction=spec["direction"],
                best_possible=float(spec["best_possible"]),
                worst_possible=float(spec["worst_possible"]),
            )
        )
    if not tie_breakers:
        raise ValueError("senza tie-breaker un pareggio si risolverebbe a mano")
    metrics = [tb.metric for tb in tie_breakers]
    if len(set(metrics)) != len(metrics):
        raise ValueError("metriche di tie-break duplicate")

    contingencies: dict[str, Contingency] = {}
    for name, spec in (payload.get("contingencies") or {}).items():
        if spec.get("poc_authorized") is not False:
            raise ValueError(f"{name}: questo contratto non può autorizzare un PoC")
        contingencies[name] = Contingency(
            name=name,
            scope=spec.get("scope", ""),
            trigger=spec.get("trigger", ""),
            poc_authorized=False,
        )

    contract = PocContract(
        version=str(payload.get("version", "unknown")),
        signed_at=str(payload.get("signed_at", "")),
        source_hash=hashlib.sha256(raw).hexdigest()[:16],
        brokers=brokers,
        ambiguous_timeout_dimension=payload["ambiguous_timeout_dimension"],
        basket_gate_dimension=payload["basket_gate_dimension"],
        basket=basket,
        dimensions=dimensions,
        kill_criteria=kill_criteria,
        tie_breakers=tuple(tie_breakers),
        contingencies=contingencies,
    )
    for named in (contract.ambiguous_timeout_dimension, contract.basket_gate_dimension):
        dim = contract.dimensions.get(named)
        if dim is None:
            raise ValueError(f"dimensione nominata e non definita: {named}")
        if dim.kind != KIND_BLOCKING:
            raise ValueError(f"{named} deve essere bloccante, non pesata")
    return contract


def evaluate_broker(contract: PocContract, result: PocResult) -> BrokerVerdict:
    """Applica il contratto a un report di PoC e restituisce il verdetto."""
    if result.broker not in contract.brokers:
        raise ValueError(f"broker fuori contratto: {result.broker}")
    if result.contract_version != contract.version:
        raise ValueError(
            f"contract_version del report {result.contract_version!r} "
            f"≠ {contract.version!r}: report non confrontabile"
        )
    if result.contract_source_hash != contract.source_hash:
        raise ValueError(
            "contract_source_hash del report non corrisponde al contratto firmato: "
            "il contratto è cambiato dopo la raccolta"
        )

    seen: dict[str, DimensionOutcome] = {}
    for outcome in result.outcomes:
        if outcome.dimension_id not in contract.dimensions:
            raise ValueError(f"dimensione sconosciuta nel report: {outcome.dimension_id}")
        if outcome.dimension_id in seen:
            raise ValueError(f"dimensione duplicata nel report: {outcome.dimension_id}")
        if outcome.status not in _ADMITTED_STATUSES:
            raise ValueError(f"{outcome.dimension_id}: status non ammesso: {outcome.status!r}")
        seen[outcome.dimension_id] = outcome

    unknown_kills = set(result.kill_criteria_tripped) - set(contract.kill_criteria)
    if unknown_kills:
        raise ValueError(f"kill criteria sconosciuti: {sorted(unknown_kills)}")
    for kill_id in result.kill_criteria_tripped:
        if result.broker not in contract.kill_criteria[kill_id].applies_to:
            raise ValueError(
                f"{kill_id} non si applica a {result.broker}: "
                "un kill di un altro candidato non è un dato"
            )

    unknown_slots = set(result.resolved_slot_ids) - {s.id for s in contract.basket}
    if unknown_slots:
        raise ValueError(f"slot sconosciuti fra i risolti: {sorted(unknown_slots)}")

    notes: list[str] = []
    statuses: dict[str, str] = {}
    for dim_id, dim in contract.dimensions.items():
        outcome = seen.get(dim_id)
        if outcome is None:
            statuses[dim_id] = STATUS_NOT_TESTED
            notes.append(f"{dim_id}: absent_from_report")
            continue
        if outcome.environment not in dim.verifiable_in:
            # Il fatto può essere vero, ma non è dimostrato dove il contratto
            # dice che si dimostra: vale come non testato.
            statuses[dim_id] = STATUS_NOT_TESTED
            notes.append(
                f"{dim_id}: environment_not_admitted:{outcome.environment} "
                f"(ammessi {', '.join(dim.verifiable_in)})"
            )
            continue
        statuses[dim_id] = outcome.status

    # Il paniere è un gate, non una dichiarazione: uno slot obbligatorio non
    # risolto fa fallire il mapping qualunque cosa dica il report.
    unresolved = [
        slot_id
        for slot_id in contract.mandatory_slot_ids()
        if slot_id not in result.resolved_slot_ids
    ]
    if unresolved:
        gate = contract.basket_gate_dimension
        statuses[gate] = STATUS_FAIL
        for slot_id in unresolved:
            notes.append(f"{gate}: mandatory_slot_unresolved:{slot_id}")

    blocking_failed = tuple(
        d for d in contract.blocking_ids() if statuses[d] == STATUS_FAIL
    )
    graded_failed = tuple(d for d in contract.graded_ids() if statuses[d] == STATUS_FAIL)
    not_tested = tuple(
        d for d in contract.dimensions if statuses[d] == STATUS_NOT_TESTED
    )
    blocking_not_tested = tuple(d for d in not_tested if d in set(contract.blocking_ids()))
    graded_not_tested = tuple(d for d in not_tested if d in set(contract.graded_ids()))

    kills = tuple(result.kill_criteria_tripped)
    if kills or blocking_failed or blocking_not_tested:
        verdict = VERDICT_FAIL
    elif graded_failed or graded_not_tested:
        verdict = VERDICT_CONDITIONAL_PASS
    else:
        verdict = VERDICT_PASS

    residual_risks = tuple(
        f"{dim_id}:{statuses[dim_id]}"
        for dim_id in contract.graded_ids()
        if statuses[dim_id] != STATUS_PASS
    )

    metrics: dict[str, float] = {
        k: float(v) for k, v in result.metrics.items() if k not in _DERIVED_METRICS
    }
    metrics["graded_failed_count"] = float(len(graded_failed))
    metrics["graded_not_tested_count"] = float(len(graded_not_tested))
    metrics["mandatory_slots_resolved_count"] = float(
        len(set(result.resolved_slot_ids) & set(contract.mandatory_slot_ids()))
    )

    return BrokerVerdict(
        broker=result.broker,
        verdict=verdict,
        blocking_failed=blocking_failed,
        graded_failed=graded_failed,
        not_tested=not_tested,
        kills_tripped=kills,
        residual_risks=residual_risks,
        notes=tuple(notes),
        metrics=metrics,
    )


def compare_candidates(
    contract: PocContract, verdicts: Sequence[BrokerVerdict]
) -> GateComparison:
    """Confronta i candidati con l'ordine lessicografico congelato nel contratto."""
    by_broker: dict[str, BrokerVerdict] = {}
    for verdict in verdicts:
        if verdict.broker in by_broker:
            raise ValueError(f"due verdetti per lo stesso broker: {verdict.broker}")
        if verdict.broker not in contract.brokers:
            raise ValueError(f"broker fuori contratto: {verdict.broker}")
        by_broker[verdict.broker] = verdict
    missing = [b for b in contract.brokers if b not in by_broker]
    if missing:
        raise ValueError(f"candidati senza verdetto: {', '.join(missing)}")

    rationale: list[str] = []
    admissible = [v for v in by_broker.values() if v.verdict != VERDICT_FAIL]
    if not admissible:
        rationale.append(
            "nessun candidato supera il contratto: la raccomandazione è restare "
            "su Alpaca come unico broker"
        )
        rationale.append(
            "una contingenza (Tradier, tastytrade, TradeStation Europe, Directa) "
            "non è promossa da qui: il trigger è dichiarato nel contratto e la "
            "scelta è dell'operatore al gate #360"
        )
        return GateComparison(RECOMMEND_ALPACA_ONLY, None, None, tuple(rationale))

    best_rank = max(_VERDICT_RANK[v.verdict] for v in admissible)
    finalists = [v for v in admissible if _VERDICT_RANK[v.verdict] == best_rank]
    if len(finalists) == 1:
        winner = finalists[0]
        rationale.append(
            f"{winner.broker}: verdetto {winner.verdict}, unico al suo livello"
        )
        if winner.residual_risks:
            rationale.append(
                "rischi residui da accettare esplicitamente al gate: "
                + ", ".join(winner.residual_risks)
            )
        return GateComparison(
            _recommendation(winner.broker), winner.broker, None, tuple(rationale)
        )

    for tie_breaker in contract.tie_breakers:
        values = {v.broker: _metric_value(v, tie_breaker) for v in finalists}
        target = (
            min(values.values()) if tie_breaker.direction == "min" else max(values.values())
        )
        leaders = [b for b, value in values.items() if value == target]
        rationale.append(
            f"{tie_breaker.metric} ({tie_breaker.direction}): "
            + ", ".join(f"{b}={values[b]:g}" for b in sorted(values))
        )
        if len(leaders) == 1:
            winner = by_broker[leaders[0]]
            if winner.residual_risks:
                rationale.append(
                    "rischi residui da accettare esplicitamente al gate: "
                    + ", ".join(winner.residual_risks)
                )
            return GateComparison(
                _recommendation(winner.broker),
                winner.broker,
                tie_breaker.metric,
                tuple(rationale),
            )
        finalists = [v for v in finalists if v.broker in leaders]

    rationale.append(
        "pareggio su tutti i tie-breaker congelati: il valutatore non inventa un "
        "preferito, la scelta torna all'operatore"
    )
    return GateComparison(RECOMMEND_NO_DECISION, None, None, tuple(rationale))


def _metric_value(verdict: BrokerVerdict, tie_breaker: TieBreaker) -> float:
    """Una metrica non misurata vale il peggio possibile, mai un vantaggio."""
    value = verdict.metrics.get(tie_breaker.metric)
    return tie_breaker.worst_possible if value is None else float(value)


def _recommendation(broker: str) -> str:
    return {"saxo": RECOMMEND_SAXO, "ibkr": RECOMMEND_IBKR}[broker]
