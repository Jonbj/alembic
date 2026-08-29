"""Ponte fra le viste appaiate (#298) e il valutatore confirmatory (#299).

E' l'unico punto in cui una vista descrittiva diventa una statistica
decisionale, quindi e' anche l'unico punto in cui un errore di selezione o di
cluster si trasforma in un intervallo falsamente stretto. Il modulo e' puro:
legge il contratto congelato e trasforma `PairedDelta` in `PairedObservation`,
senza toccare DB, broker o mercato.

Due regole reggono tutto il resto:

1. **Entra solo cio' che e' misurabile.** Una coppia esclusa non ha un delta;
   contarla come zero sarebbe inventare un'osservazione neutra che il campione
   non contiene.
2. **Il cluster e' l'event-day.** Non esiste oggi un identificativo di evento
   giornalistico nel ledger, quindi si usa `d0` — la seduta del primo fill —
   come proxy. Il limite e' dichiarato nel report, non nascosto: due eventi
   distinti nello stesso giorno finiscono in un cluster solo. L'errore va
   nella direzione sicura, perche' riduce il numero di cluster e **allarga**
   l'intervallo; il costo e' che la raccolta richiede piu' tempo, mai che una
   promozione arrivi troppo facilmente.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

import yaml

from src.strategies.s4.counterfactual import PairedDelta
from src.strategies.s4.paired_evaluator import (
    OUTCOME_NOT_TESTED,
    BootstrapScheme,
    PairedObservation,
    evaluate_hierarchy,
)

CLUSTER_UNIT = "d0_session"
CLUSTER_CAVEAT = (
    "proxy: il ledger non porta un event_id giornalistico, quindi due eventi "
    "distinti nella stessa seduta contano come un solo cluster. Riduce i "
    "cluster e allarga l'intervallo: l'errore e' conservativo."
)

_DEFAULT_SCHEME = BootstrapScheme(
    kind="block",
    # Due sedute: la lunghezza minima coerente con un orizzonte D+2, dove il
    # rendimento di un intento si sovrappone a quello del giorno successivo.
    block_length=2,
    resamples=10_000,
    seed=20260822,  # data di firma del contratto: fissato ex ante, non scelto
)


@dataclass(frozen=True)
class EvaluationSettings:
    """I parametri di inferenza, letti dal contratto e mai ricodificati."""

    mde_time_bps: float
    mde_counter_bps: float | None
    alpha: float
    power: float
    n_cluster: int | None
    scheme: BootstrapScheme


def load_evaluation_settings(path: Path | None = None) -> EvaluationSettings:
    """Carica MDE, alpha, potenza e `N_cluster` dal contratto congelato.

    I due `raise` non sono difensivi per abitudine: un contratto che ammettesse
    un early efficacy stop, o che promuovesse le ~213 sedute a `N_cluster`,
    descriverebbe un trial diverso da quello pre-registrato, e il valutatore
    non deve poterlo eseguire per distrazione.
    """
    if path is None:
        path = Path(__file__).resolve().parents[3] / "config" / "s4_exit_trial.yaml"
    payload = yaml.safe_load(path.read_bytes()) or {}
    thresholds = payload.get("thresholds") or {}
    power_cfg = payload.get("power") or {}
    stopping = payload.get("stopping") or {}

    if stopping.get("early_efficacy_stop") is not False:
        raise ValueError("the frozen contract forbids an early efficacy stop")
    if power_cfg.get("sessions_213_is_N_cluster") is not False:
        raise ValueError(
            "the 213 sessions are an IC sample-size estimate and cannot become "
            "N_cluster for the paired exit delta"
        )

    mde_time = (thresholds.get("MDE_time") or {}).get("value")
    if mde_time is None:
        raise ValueError("MDE_time must be fixed before any evaluation")
    counter = thresholds.get("MDE_counter") or {}
    n_cluster = (power_cfg.get("N_cluster") or {}).get("value")

    return EvaluationSettings(
        mde_time_bps=float(mde_time),
        mde_counter_bps=(
            None if not counter.get("fixed") else float(counter.get("value"))
        ),
        alpha=float(power_cfg.get("alpha", 0.05)),
        power=float(power_cfg.get("power", 0.90)),
        n_cluster=None if n_cluster is None else int(n_cluster),
        scheme=_DEFAULT_SCHEME,
    )


def observations_from_pairs(
    pairs: Iterable[PairedDelta], *, policy_id: str
) -> tuple[PairedObservation, ...]:
    """Seleziona le coppie misurabili della policy e le assegna a un cluster."""
    observations: list[PairedObservation] = []
    for pair in pairs:
        if pair.policy_id != policy_id or not pair.comparable:
            continue
        if pair.d0 is None or pair.delta_bps is None or pair.delta_usd is None:
            # Una coppia dichiarata comparabile ma senza delta o senza seduta
            # non e' assegnabile a un cluster: resta fuori invece di entrare
            # con un valore inventato.
            continue
        observations.append(
            PairedObservation(
                intent_id=pair.intent_id,
                event_day=pair.d0,
                challenger_policy_id=pair.policy_id,
                baseline_policy_id=pair.baseline_policy_id,
                delta_bps=pair.delta_bps,
                delta_usd=pair.delta_usd,
                initial_notional=pair.initial_notional or 0.0,
                capital_days=pair.challenger_capital_days,
            )
        )
    return tuple(observations)


def _blocked_result(
    policy_id: str, note: str, clusters: int, observations: int, n_cluster: int | None
) -> dict[str, object]:
    return {
        "cluster_unit": CLUSTER_UNIT,
        "cluster_caveat": CLUSTER_CAVEAT,
        "observations": observations,
        "clusters_observed": clusters,
        "n_cluster": n_cluster,
        "decision_due": False,
        "promoted_policy_id": None,
        "steps": [
            {
                "label": "delta1_P1_vs_P0",
                "challenger_policy_id": policy_id,
                "baseline_policy_id": "P0",
                "outcome": OUTCOME_NOT_TESTED,
                "notes": ["not_equivalence", note],
                "interval": None,
            }
        ],
    }


def run_evaluation(
    pairs: Iterable[PairedDelta],
    *,
    policy_id: str,
    mde_time_bps: float,
    scheme: BootstrapScheme,
    n_cluster: int | None,
    counter_pairs: Sequence[PairedDelta] | None = None,
    mde_counter_bps: float | None = None,
) -> dict[str, object]:
    """Esegue la gerarchia sui delta appaiati e restituisce un blocco JSON.

    Con `n_cluster` non ancora derivato la raccolta non ha un traguardo, quindi
    non esiste nemmeno una decisione da prendere: lo dice esplicitamente invece
    di scegliere un default, che sarebbe una regola di stopping inventata qui.
    """
    observations = observations_from_pairs(pairs, policy_id=policy_id)
    clusters = len({obs.event_day for obs in observations})

    if not observations:
        return _blocked_result(policy_id, "no_comparable_pairs", 0, 0, n_cluster)
    if n_cluster is None:
        return _blocked_result(
            policy_id, "N_cluster_not_derived", clusters, len(observations), None
        )

    counter_observations = (
        None
        if counter_pairs is None
        else observations_from_pairs(counter_pairs, policy_id="P2")
    )
    result = evaluate_hierarchy(
        observations,
        mde_time_bps=mde_time_bps,
        scheme=scheme,
        n_cluster=n_cluster,
        counter_observations=counter_observations,
        mde_counter_bps=mde_counter_bps,
    )

    return {
        "cluster_unit": CLUSTER_UNIT,
        "cluster_caveat": CLUSTER_CAVEAT,
        "observations": len(observations),
        "clusters_observed": result.clusters_observed,
        "n_cluster": result.n_cluster,
        "decision_due": result.decision_due,
        "promoted_policy_id": result.promoted_policy_id,
        "steps": [
            {
                "label": step.label,
                "challenger_policy_id": step.challenger_policy_id,
                "baseline_policy_id": step.baseline_policy_id,
                "mde_bps": step.mde_bps,
                "outcome": step.outcome,
                "notes": list(step.notes),
                "interval": (
                    None
                    if step.interval is None
                    else {
                        **{
                            key: value
                            for key, value in asdict(step.interval).items()
                            if key != "scheme"
                        },
                        "scheme": asdict(step.interval.scheme),
                    }
                ),
            }
            for step in result.steps
        ],
    }
