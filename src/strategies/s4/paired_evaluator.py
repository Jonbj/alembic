"""Valutatore confirmatory appaiato del trial exit S4 (#299).

Il modulo decide `PROMOTE`, `REJECT` o `INCONCLUSIVE` sul delta appaiato netto
fra policy, e va costruito e testato **prima** di leggere gli esiti forward:
per questo e' puro, deterministico a parita' di seme, e non conosce ne' DB ne'
broker.

Le regole vengono dal contratto congelato (`config/s4_exit_trial.yaml`) e da
`docs/s4-exit-research-2026-08-14/consolidato_exit.md` §7-§8.4:

- l'unita' di cluster e' l'**event-day**: ticker-day e articoli dello stesso
  evento non sono repliche indipendenti (§8.4);
- l'intervallo e' **unilaterale al 95%** da block bootstrap con schema e
  lunghezza fissati ex ante;
- `PROMOTE` se `LCB95 > MDE`, `REJECT` se `UCB95 <= MDE`, altrimenti
  `INCONCLUSIVE` — che non e' equivalenza ne' autorizzazione;
- la molteplicita' e' un **ordine gerarchico chiuso**: P1 vs P0, e solo se
  supera il gate si testa P2 vs P1;
- `N_cluster` deriva da MDE, varianza dei delta, potenza e dipendenza. Le ~213
  sedute sono una stima per l'IC, mai una numerosita' automatica per il paired
  exit delta;
- nessun early efficacy stop: sotto `N_cluster` non esiste una decisione, e un
  safety halt e' un esito distinto e motivato.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import date
from statistics import NormalDist, fmean, pstdev
from typing import Literal, Sequence

OUTCOME_PROMOTE = "PROMOTE"
OUTCOME_REJECT = "REJECT"
OUTCOME_INCONCLUSIVE = "INCONCLUSIVE"
OUTCOME_NOT_TESTED = "NOT_TESTED"
OUTCOME_SAFETY_HALT = "SAFETY_HALT"

# Varianti che il consolidato dichiara diagnostiche: non diventano confirmatory
# per rinomina, e non diventano out-of-sample sullo stesso campione (§8.4).
_DIAGNOSTIC_ONLY = frozenset({
    "D+1",
    "D+3",
    "decomposizione intraday/overnight",
    "term structure",
    "sottoperiodi",
    "E4 aggregata",
    "posterior/VIX",
    "trailing",
    "event-type",
    "de-risking",
})


@dataclass(frozen=True)
class PairedObservation:
    """Un delta appaiato su un intento, con il cluster che lo rende dipendente.

    `event_day` e' l'unita' di ricampionamento: due intenti nati dallo stesso
    evento condividono lo shock e non valgono due osservazioni.
    """

    intent_id: str
    event_day: date
    challenger_policy_id: str
    baseline_policy_id: str
    delta_bps: float
    delta_usd: float
    initial_notional: float
    capital_days: float | None = None
    overnight_pnl_usd: float | None = None
    false_exit: bool | None = None
    recovered_within_horizon: bool | None = None
    giveback_from_mfe_bps: float | None = None


@dataclass(frozen=True)
class BootstrapScheme:
    """Schema di ricampionamento, congelato prima di guardare i risultati."""

    kind: Literal["block", "stationary"]
    block_length: int
    resamples: int
    seed: int
    alpha: float = 0.05

    def __post_init__(self) -> None:
        if self.block_length < 1:
            raise ValueError("block length must be at least one cluster")
        if self.resamples < 1:
            raise ValueError("bootstrap needs at least one resample")
        if not 0.0 < self.alpha < 0.5:
            raise ValueError("one-sided alpha must lie in (0, 0.5)")


@dataclass(frozen=True)
class Interval:
    """Due limiti **unilaterali al 95%**, non un intervallo bilaterale al 95%.

    `lcb` e' il percentile `alpha` della distribuzione bootstrap e `ucb` il
    percentile `1-alpha`: ciascuno e' il limite di un intervallo unilaterale al
    95%, che e' la forma che il contratto chiede — `LCB95` decide PROMOTE,
    `UCB95` decide REJECT. Letti come una coppia coprono il vero all'incirca il
    90% delle volte, e confonderli con un bilaterale al 95% renderebbe le
    soglie piu' permissive di quanto pre-registrato.
    """

    point: float
    lcb: float
    ucb: float
    alpha: float
    tail: str
    clusters: int
    observations: int
    scheme: BootstrapScheme


def _clusters(
    observations: Sequence[PairedObservation],
) -> list[tuple[date, list[PairedObservation]]]:
    by_day: dict[date, list[PairedObservation]] = {}
    for observation in observations:
        by_day.setdefault(observation.event_day, []).append(observation)
    return sorted(by_day.items())


def _cluster_means(
    clusters: list[tuple[date, list[PairedObservation]]]
) -> list[float]:
    """Media per cluster: l'evento pesa una volta, non una per intento."""
    return [fmean(obs.delta_bps for obs in group) for _, group in clusters]


def bootstrap_paired_delta(
    observations: Sequence[PairedObservation],
    scheme: BootstrapScheme,
) -> Interval:
    """Intervallo unilaterale 95% sul delta medio, per block bootstrap event-day.

    I blocchi sono contigui nel tempo e circolari: la lunghezza fissata ex ante
    e' cio' che conserva la dipendenza fra giorni vicini, che l'orizzonte D+2
    introduce per costruzione. Il ricampionamento avviene sui **cluster**, mai
    sui singoli intenti — altrimenti tre articoli sullo stesso evento
    diventerebbero tre osservazioni indipendenti e l'intervallo sarebbe
    falsamente stretto.
    """
    clusters = _clusters(observations)
    if not clusters:
        raise ValueError("a paired delta needs at least one event-day cluster")

    means = _cluster_means(clusters)
    n = len(means)
    rng = random.Random(scheme.seed)
    block = min(scheme.block_length, n)
    blocks_needed = -(-n // block)

    replicates: list[float] = []
    for _ in range(scheme.resamples):
        drawn: list[float] = []
        for _ in range(blocks_needed):
            start = rng.randrange(n)
            drawn.extend(means[(start + offset) % n] for offset in range(block))
        replicates.append(fmean(drawn[:n]))

    replicates.sort()
    lower_index = int(scheme.alpha * (len(replicates) - 1))
    upper_index = int((1.0 - scheme.alpha) * (len(replicates) - 1))
    return Interval(
        point=fmean(means),
        lcb=replicates[lower_index],
        ucb=replicates[upper_index],
        alpha=scheme.alpha,
        tail="one_sided",
        clusters=n,
        observations=len(observations),
        scheme=scheme,
    )


def derive_n_cluster(
    *,
    mde_bps: float,
    sigma_delta_bps: float,
    alpha: float,
    power: float,
    dependence_inflation: float,
    missingness_rate: float,
) -> int:
    """Numero di cluster richiesto, derivato — mai preso dalle ~213 sedute.

    `sigma_delta` va stimata blinded sulla sola varianza: media e ranking fra
    le policy non possono entrare qui, o la numerosita' verrebbe scelta dopo
    aver visto chi vince.
    """
    if mde_bps <= 0:
        raise ValueError("MDE must be strictly positive to size a sample")
    if sigma_delta_bps <= 0:
        raise ValueError("sigma of the paired delta must be strictly positive")
    if not 0.0 < alpha < 0.5:
        raise ValueError("one-sided alpha must lie in (0, 0.5)")
    if not 0.5 < power < 1.0:
        raise ValueError("power must lie in (0.5, 1)")
    if dependence_inflation < 1.0:
        raise ValueError("dependence inflation cannot shrink the sample")
    if not 0.0 <= missingness_rate < 1.0:
        raise ValueError("missingness rate must lie in [0, 1)")

    normal = NormalDist()
    z_alpha = normal.inv_cdf(1.0 - alpha)
    z_power = normal.inv_cdf(power)
    # Arrotondamento per eccesso a ogni passo: la numerosita' e' un requisito
    # minimo, e un cluster in piu' costa una seduta mentre uno in meno costa
    # potenza su un campione che non si puo' allungare dopo aver guardato.
    base = ((z_alpha + z_power) * sigma_delta_bps / mde_bps) ** 2
    inflated = _ceil(base) * dependence_inflation
    return _ceil(inflated / (1.0 - missingness_rate))


def _ceil(value: float) -> int:
    whole = int(value)
    return whole if whole == value else whole + 1


def classify_outcome(*, lcb: float, ucb: float, mde: float) -> str:
    """Boundary del contratto, con le disuguaglianze nel verso giusto.

    `PROMOTE` chiede `LCB > MDE` **stretto**: un limite inferiore esattamente
    sull'MDE non dimostra il beneficio minimo. `REJECT` chiede `UCB <= MDE`
    inclusivo: se anche lo scenario favorevole arriva solo all'MDE, non
    giustifica capitale. Tutto il resto e' `INCONCLUSIVE`.
    """
    if lcb > mde:
        return OUTCOME_PROMOTE
    if ucb <= mde:
        return OUTCOME_REJECT
    return OUTCOME_INCONCLUSIVE


@dataclass(frozen=True)
class EvaluationStep:
    """Un gradino della gerarchia chiusa, con il perche' del suo esito."""

    label: str
    challenger_policy_id: str
    baseline_policy_id: str
    mde_bps: float | None
    interval: Interval | None
    outcome: str
    notes: tuple[str, ...]
    equivalence_declared: bool = False
    is_safety_halt: bool = False
    reason: str | None = None


@dataclass(frozen=True)
class EvaluationResult:
    steps: tuple[EvaluationStep, ...]
    n_cluster: int
    clusters_observed: int
    decision_due: bool
    promoted_policy_id: str | None


def safety_halt(*, reason: str, documented_at: date) -> EvaluationStep:
    """Un halt di sicurezza non e' un REJECT: non dice nulla sull'ipotesi.

    Il contratto lo ammette solo per danno operativo e pretende che sia
    documentato; senza motivo scritto sarebbe indistinguibile da un
    abbandono per risultati sgraditi.
    """
    if not reason.strip():
        raise ValueError("a safety halt needs a documented reason")
    return EvaluationStep(
        label=f"safety_halt:{documented_at.isoformat()}",
        challenger_policy_id="",
        baseline_policy_id="",
        mde_bps=None,
        interval=None,
        outcome=OUTCOME_SAFETY_HALT,
        notes=("operational_harm", "documented"),
        is_safety_halt=True,
        reason=reason.strip(),
    )


def _step(
    label: str,
    observations: Sequence[PairedObservation],
    *,
    mde_bps: float | None,
    scheme: BootstrapScheme,
    challenger: str,
    baseline: str,
    blocked: str | None,
    decision_due: bool,
) -> EvaluationStep:
    notes: list[str] = ["not_equivalence"]
    if blocked is not None:
        return EvaluationStep(
            label=label,
            challenger_policy_id=challenger,
            baseline_policy_id=baseline,
            mde_bps=mde_bps,
            interval=None,
            outcome=OUTCOME_NOT_TESTED,
            notes=tuple([*notes, blocked]),
        )
    interval = bootstrap_paired_delta(observations, scheme)
    if not decision_due:
        # Nessun early efficacy stop: l'intervallo si puo' guardare, la
        # decisione no. Restituirlo senza esito e' cio' che rende la
        # promozione anticipata impossibile invece che sconsigliata.
        return EvaluationStep(
            label=label,
            challenger_policy_id=challenger,
            baseline_policy_id=baseline,
            mde_bps=mde_bps,
            interval=interval,
            outcome=OUTCOME_NOT_TESTED,
            notes=tuple([*notes, "below_n_cluster"]),
        )
    assert mde_bps is not None
    outcome = classify_outcome(lcb=interval.lcb, ucb=interval.ucb, mde=mde_bps)
    return EvaluationStep(
        label=label,
        challenger_policy_id=challenger,
        baseline_policy_id=baseline,
        mde_bps=mde_bps,
        interval=interval,
        outcome=outcome,
        notes=tuple(notes),
    )


def evaluate_hierarchy(
    time_observations: Sequence[PairedObservation],
    *,
    mde_time_bps: float,
    scheme: BootstrapScheme,
    n_cluster: int,
    counter_observations: Sequence[PairedObservation] | None = None,
    mde_counter_bps: float | None = None,
) -> EvaluationResult:
    """Ordine gerarchico chiuso: P1 vs P0, e P2 vs P1 solo se P1 passa.

    Testare P2 dopo una P1 fallita non e' solo meno potente: renderebbe
    impossibile dire quale componente funziona, che e' l'unica domanda a cui
    questa famiglia risponde.
    """
    clusters_observed = len(_clusters(time_observations))
    decision_due = clusters_observed >= n_cluster

    time_step = _step(
        "delta1_P1_vs_P0",
        time_observations,
        mde_bps=mde_time_bps,
        scheme=scheme,
        challenger="P1",
        baseline="P0",
        blocked=None,
        decision_due=decision_due,
    )

    steps = [time_step]
    promoted = "P1" if time_step.outcome == OUTCOME_PROMOTE else None

    if counter_observations is not None:
        if time_step.outcome != OUTCOME_PROMOTE:
            blocked = "P1_did_not_pass"
        elif mde_counter_bps is None:
            blocked = "MDE_counter_not_fixed"
        else:
            blocked = None
        counter_step = _step(
            "delta2_P2_vs_P1",
            counter_observations,
            mde_bps=mde_counter_bps,
            scheme=scheme,
            challenger="P2",
            baseline="P1",
            blocked=blocked,
            decision_due=decision_due,
        )
        steps.append(counter_step)
        if counter_step.outcome == OUTCOME_PROMOTE:
            promoted = "P2"

    return EvaluationResult(
        steps=tuple(steps),
        n_cluster=n_cluster,
        clusters_observed=clusters_observed,
        decision_due=decision_due,
        promoted_policy_id=promoted,
    )


# ── Trial ledger (criterio 5) ──────────────────────────────────────────────


@dataclass(frozen=True)
class LedgerEntry:
    name: str
    role: str


@dataclass
class TrialLedger:
    """Registro append-only di ogni variante vista, con il suo ruolo.

    Serve a rendere visibile la molteplicita' realmente esplorata: senza, una
    diagnostica gia' guardata puo' riapparire come confirmatory su un campione
    che non e' piu' out-of-sample.
    """

    entries: tuple[LedgerEntry, ...] = field(default_factory=tuple)

    def record(self, name: str, *, role: str) -> None:
        if role not in {"confirmatory", "diagnostic"}:
            raise ValueError("a ledger role is confirmatory or diagnostic")
        if role == "confirmatory" and name in _DIAGNOSTIC_ONLY:
            raise ValueError(
                f"{name!r} is declared diagnostic by the contract and cannot be "
                "promoted to confirmatory by renaming"
            )
        self.entries = (*self.entries, LedgerEntry(name=name, role=role))


# ── Metriche (criterio 1) ──────────────────────────────────────────────────


def economic_metrics(
    observations: Sequence[PairedObservation],
) -> dict[str, object]:
    """Economia del delta appaiato, sul denominatore congelato dal contratto."""
    if not observations:
        return {"denominator": "initial_notional", "trades": 0}
    deltas = [obs.delta_bps for obs in observations]
    usd = [obs.delta_usd for obs in observations]
    capital_days = [obs.capital_days for obs in observations if obs.capital_days]
    overnight = [
        obs.overnight_pnl_usd
        for obs in observations
        if obs.overnight_pnl_usd is not None
    ]
    gross_usd = sum(abs(value) for value in usd)
    total_capital_days = sum(capital_days) if capital_days else None
    return {
        "denominator": "initial_notional",
        "trades": len(observations),
        "mean_delta_bps": fmean(deltas),
        "median_delta_bps": sorted(deltas)[len(deltas) // 2],
        "net_delta_usd": sum(usd),
        "hit_rate": sum(1 for value in deltas if value > 0) / len(deltas),
        "capital_days": total_capital_days,
        "return_on_occupied_capital_bps": (
            None
            if not total_capital_days
            else sum(usd) / total_capital_days * 10_000.0
        ),
        "overnight_share": (
            None if not overnight or gross_usd == 0 else sum(overnight) / gross_usd
        ),
    }


def risk_metrics(
    observations: Sequence[PairedObservation], *, es_level: float = 0.05
) -> dict[str, float]:
    """Coda e drawdown del delta appaiato; un ES migliore non salva la primaria."""
    if not observations:
        return {}
    if not 0.0 < es_level <= 1.0:
        raise ValueError("expected-shortfall level must lie in (0, 1]")
    deltas = [obs.delta_bps for obs in observations]
    negatives = [value for value in deltas if value < 0]
    ordered = sorted(deltas)
    tail_size = max(1, int(len(ordered) * es_level))

    cumulative = 0.0
    peak = 0.0
    drawdown = 0.0
    for value in deltas:
        cumulative += value
        peak = max(peak, cumulative)
        drawdown = max(drawdown, peak - cumulative)

    return {
        "downside_deviation_bps": pstdev(negatives) if len(negatives) > 1 else 0.0,
        # Media della coda, non il suo minimo: l'ES e' un'attesa condizionata.
        "expected_shortfall_bps": fmean(ordered[:tail_size]),
        "max_drawdown_bps": drawdown,
        "worst_trade_bps": min(deltas),
    }


def exit_quality(observations: Sequence[PairedObservation]) -> dict[str, float]:
    """False exit, recovery e giveback: la qualita' dell'uscita, non il P&L."""
    flagged = [obs for obs in observations if obs.false_exit is not None]
    if not flagged:
        return {}
    false_exits = [obs for obs in flagged if obs.false_exit]
    recovered = [obs for obs in false_exits if obs.recovered_within_horizon]
    givebacks = [
        obs.giveback_from_mfe_bps
        for obs in observations
        if obs.giveback_from_mfe_bps is not None
    ]
    return {
        "false_exit_rate": len(false_exits) / len(flagged),
        "recovery_within_horizon_rate": (
            len(recovered) / len(false_exits) if false_exits else 0.0
        ),
        "mean_giveback_from_mfe_bps": fmean(givebacks) if givebacks else 0.0,
    }
