"""Le milestone pre-registrate del trial exit S4 (#298).

Il contratto congelato (`config/s4_exit_trial.yaml`) fissa tre momenti in cui
qualcuno deve intervenire, e nessuno li sorvegliava:

1. `power.N_cluster.value: null` — la raccolta non ha un traguardo. Non e' un
   dettaglio rimandabile: senza `N_cluster` non esiste ne' il 50% della
   ri-stima ne' il punto dell'analisi, quindi *nessuna* delle altre due
   milestone puo' scattare.
2. `blinded_reestimation: {allowed: 1, at_fraction_of_N_cluster: 0.50}`.
3. `stopping: {decision_analysis_count: 1, decision_analysis_at: "N_cluster"}`.

Questo modulo decide soltanto *se* un momento e' arrivato. Non stima, non
promuove, non scrive nel contratto: sono atti dell'operatore, e il contratto
li tiene fuori dalla portata di un job.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum

# `blinded_reestimation.at_fraction_of_N_cluster` del contratto congelato.
FRAZIONE_RI_STIMA = 0.50


class Milestone(StrEnum):
    N_CLUSTER_PROPONIBILE = "N_CLUSTER_PROPONIBILE"
    RI_STIMA_BLINDED = "RI_STIMA_BLINDED"
    ANALISI_DECISIONALE = "ANALISI_DECISIONALE"


@dataclass(frozen=True)
class MilestoneRaggiunta:
    """Il momento arrivato, con i soli conteggi che l'interim puo' guardare."""

    nome: Milestone
    clusters_observed: int
    observations: int
    n_cluster: int | None


def milestone_raggiunta(
    *,
    n_cluster: int | None,
    clusters_observed: int,
    observations: int,
    gia_notificate: Sequence[str],
    osservazioni_minime: int,
) -> MilestoneRaggiunta | None:
    """La prima milestone raggiunta e non ancora notificata, o None."""
    viste = set(gia_notificate)

    def _raggiunta(nome: Milestone) -> MilestoneRaggiunta | None:
        if nome in viste:
            return None
        return MilestoneRaggiunta(
            nome=nome,
            clusters_observed=clusters_observed,
            observations=observations,
            n_cluster=n_cluster,
        )

    if n_cluster is None:
        if observations >= osservazioni_minime:
            return _raggiunta(Milestone.N_CLUSTER_PROPONIBILE)
        return None

    # L'analisi viene prima nell'ordine di controllo, non solo nel tempo: al
    # traguardo la finestra della ri-stima e' chiusa, e mandare l'operatore a
    # rifare una stima intermedia consumerebbe l'unica concessa dal contratto
    # per rispondere a una domanda che non si pone piu'.
    if clusters_observed >= n_cluster:
        return _raggiunta(Milestone.ANALISI_DECISIONALE)
    # Frazione dal contratto, non arrotondata per eccesso: la ri-stima e' una
    # finestra che si apre, non una scadenza da centrare.
    if clusters_observed >= n_cluster * FRAZIONE_RI_STIMA:
        return _raggiunta(Milestone.RI_STIMA_BLINDED)
    return None


# Cio' che un interim puo' pubblicare. La lista e' un'allow-list e non una
# deny-list di proposito: un campo nuovo del report a monte non deve poter
# entrare nella notifica solo perche' nessuno si e' ricordato di vietarlo.
CAMPI_BLINDED_AMMESSI = frozenset(
    {
        "milestone",
        "clusters_observed",
        "observations",
        "n_cluster",
        "n_cluster_proposto",
        "sigma_delta_bps",
        "frazione_raggiunta",
    }
)


def riepilogo_blinded(
    raggiunta: MilestoneRaggiunta,
    *,
    sigma_delta_bps: float | None = None,
    n_cluster_proposto: int | None = None,
    extra: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Il payload della notifica, con l'effetto strutturalmente fuori.

    `sigma_delta` puo' entrare — il contratto la vuole stimata blinded, sulla
    sola varianza. Media e ranking fra le policy no: al primo campo non
    ammesso questa funzione solleva invece di scartarlo, perche' uno scarto
    silenzioso lascerebbe chi chiama convinto di averlo pubblicato.
    """
    payload: dict[str, object] = {
        "milestone": str(raggiunta.nome),
        "clusters_observed": raggiunta.clusters_observed,
        "observations": raggiunta.observations,
        "n_cluster": raggiunta.n_cluster,
    }
    if sigma_delta_bps is not None:
        payload["sigma_delta_bps"] = sigma_delta_bps
    if n_cluster_proposto is not None:
        payload["n_cluster_proposto"] = n_cluster_proposto
    if raggiunta.n_cluster:
        payload["frazione_raggiunta"] = (
            raggiunta.clusters_observed / raggiunta.n_cluster
        )
    for chiave, valore in (extra or {}).items():
        if chiave not in CAMPI_BLINDED_AMMESSI:
            raise ValueError(
                f"{chiave} non e' una statistica blinded: il contratto limita "
                "gli interim a integrita', sicurezza e statistiche blinded"
            )
        payload[chiave] = valore
    return payload
