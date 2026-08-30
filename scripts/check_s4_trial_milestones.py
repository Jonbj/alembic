#!/usr/bin/env python3
"""Rileva le milestone pre-registrate del trial exit S4 (#298).

Legge il report riconciliato di #298, ne tiene SOLO le statistiche blinded e
dice se una delle tre milestone del contratto e' arrivata. Non decide, non
promuove, non scrive nel contratto congelato.

Uso:
    scripts/check_s4_trial_milestones.py --start 2026-08-25 --end 2026-08-29 \
        [--gia-notificate RI_STIMA_BLINDED,...]

Stampa un JSON su stdout. Exit 0 se nessuna milestone e' scattata, 10 se una
e' scattata, 11 se il report a monte non riconcilia (cosi' il chiamante non
deve interpretare il testo).
"""

from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.report_s4_replacement import (
    EXIT_NO_COMPARABLE_PAIRS,
    EXIT_NOT_RECONCILED,
    EXIT_RECONCILED,
)
from src.strategies.s4.evaluator_bridge import load_evaluation_settings
from src.strategies.s4.paired_evaluator import derive_n_cluster
from src.strategies.s4.trial_milestones import (
    Milestone,
    milestone_raggiunta,
    riepilogo_blinded,
)

USCITA_MILESTONE = 10
USCITA_NON_RICONCILIATO = 11

# I tre esiti in cui il report ha misurato la finestra e stampato il payload.
# Solo `EXIT_RECONCILED` e' un successo, ma nessuno dei tre e' un guasto: una
# finestra senza coppie misurabili e' lo stato normale della raccolta, ed e'
# proprio quello che le milestone devono poter sorvegliare.
_CODICI_CON_REPORT = frozenset(
    {EXIT_RECONCILED, EXIT_NOT_RECONCILED, EXIT_NO_COMPARABLE_PAIRS}
)


def _report(start: str, end: str) -> tuple[dict, int]:
    """Il report di #298, eseguito cosi' com'e' per non duplicarne le query.

    Restituisce anche il codice d'uscita: e' il codice, non il payload, a dire
    se la finestra e' riconciliata, e chi chiama deve deciderne di conseguenza.
    """
    radice = Path(__file__).resolve().parents[1]
    completato = subprocess.run(
        [
            sys.executable,
            str(radice / "scripts" / "report_s4_replacement.py"),
            "--start",
            start,
            "--end",
            end,
        ],
        capture_output=True,
        text=True,
        cwd=radice,
    )
    try:
        report = json.loads(completato.stdout)
    except json.JSONDecodeError:
        report = None
    if report is None or completato.returncode not in _CODICI_CON_REPORT:
        # Senza questo, un fallimento del report arriva al log come un
        # CalledProcessError che nomina il comando e nasconde la causa —
        # tipicamente una credenziale assente, che si riconosce in una riga.
        coda = (completato.stderr or completato.stdout or "").strip().splitlines()
        raise SystemExit(
            "il report di #298 e' fallito con codice "
            f"{completato.returncode}:\n" + "\n".join(coda[-5:])
        )
    return report, completato.returncode


def _sigma_delta_bps(report: dict) -> float | None:
    """Deviazione standard dei delta appaiati: varianza, mai media.

    Il contratto vuole `sigma_delta` stimata blinded (`uses: [varianza]`,
    `must_not_use: [media, ranking fra le policy]`). La media entra nel calcolo
    della varianza per definizione, ma non esce di qui: nessun chiamante la
    riceve, e `riepilogo_blinded` rifiuterebbe di pubblicarla.
    """
    deltas = [
        float(record["delta_bps"])
        for record in report.get("paired_records") or []
        if record.get("comparable") and record.get("delta_bps") is not None
    ]
    if len(deltas) < 2:
        return None
    return statistics.stdev(deltas)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument(
        "--gia-notificate",
        default="",
        help="milestone gia' annunciate, separate da virgola",
    )
    parser.add_argument(
        "--osservazioni-minime",
        type=int,
        default=20,
        help=(
            "soglia di sollecito per proporre N_cluster. NON e' un criterio "
            "del contratto, che non ne fissa uno: e' il punto sotto il quale "
            "una sigma non vale la pena di essere guardata."
        ),
    )
    # Il contratto dichiara `inflation_for: [dipendenza, missingness]` senza
    # fissarne i valori. Restano parametri espliciti: la proposta e' da
    # rivedere, non un numero da copiare senza guardarlo.
    parser.add_argument("--dependence-inflation", type=float, default=1.0)
    parser.add_argument("--missingness-rate", type=float, default=0.0)
    args = parser.parse_args()

    settings = load_evaluation_settings()
    report, codice = _report(args.start, args.end)
    evaluation = report.get("evaluation") or {}
    conteggi = {
        "clusters_observed": int(evaluation.get("clusters_observed") or 0),
        "observations": int(evaluation.get("observations") or 0),
        "n_cluster": settings.n_cluster,
    }

    if codice == EXIT_NOT_RECONCILED:
        # Le due viste si contraddicono: la sigma di questa finestra non e'
        # quella che il contratto vuole stimare, e derivarne `N_cluster`
        # fisserebbe il traguardo del trial su una misura che il report stesso
        # dichiara rotta — consumando l'unica ri-stima blinded concessa. Va
        # detto per quello che e', non fatto passare per un guasto del monitor.
        print(
            json.dumps(
                {
                    "milestone": None,
                    "blocco": "REPORT_NON_RICONCILIATO",
                    "blocking_reasons": list(
                        (report.get("reconciliation") or {}).get(
                            "blocking_reasons"
                        )
                        or []
                    ),
                    **conteggi,
                },
                indent=2,
            )
        )
        return USCITA_NON_RICONCILIATO

    raggiunta = milestone_raggiunta(
        n_cluster=conteggi["n_cluster"],
        clusters_observed=conteggi["clusters_observed"],
        observations=conteggi["observations"],
        gia_notificate=[
            voce.strip() for voce in args.gia_notificate.split(",") if voce.strip()
        ],
        osservazioni_minime=args.osservazioni_minime,
    )

    if raggiunta is None:
        print(json.dumps({"milestone": None, **conteggi}, indent=2))
        return 0

    sigma = _sigma_delta_bps(report)
    proposto = None
    if raggiunta.nome is Milestone.N_CLUSTER_PROPONIBILE and sigma:
        proposto = derive_n_cluster(
            mde_bps=settings.mde_time_bps,
            sigma_delta_bps=sigma,
            alpha=settings.alpha,
            power=settings.power,
            dependence_inflation=args.dependence_inflation,
            missingness_rate=args.missingness_rate,
        )

    print(
        json.dumps(
            riepilogo_blinded(
                raggiunta, sigma_delta_bps=sigma, n_cluster_proposto=proposto
            ),
            indent=2,
        )
    )
    return USCITA_MILESTONE


if __name__ == "__main__":
    raise SystemExit(main())
