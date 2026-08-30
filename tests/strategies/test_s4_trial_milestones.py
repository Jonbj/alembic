"""Milestone pre-registrate del trial exit S4 (#298).

Il contratto congelato fissa tre momenti in cui qualcuno deve fare qualcosa:
derivare `N_cluster` quando ancora non esiste, la ri-stima blinded a meta'
strada, e l'unica analisi decisionale al traguardo. Finche' nessuno li
sorveglia, il trial puo' superarli in silenzio.
"""

import pytest

from src.strategies.s4.trial_milestones import (
    CAMPI_BLINDED_AMMESSI,
    Milestone,
    milestone_raggiunta,
    riepilogo_blinded,
)


def test_senza_n_cluster_la_milestone_e_proporne_uno():
    """`N_cluster: null` non e' "nessun traguardo": e' un traguardo non ancora derivato."""
    raggiunta = milestone_raggiunta(
        n_cluster=None,
        clusters_observed=4,
        observations=12,
        gia_notificate=(),
        osservazioni_minime=10,
    )

    assert raggiunta is not None
    assert raggiunta.nome == Milestone.N_CLUSTER_PROPONIBILE


def test_troppo_poche_osservazioni_non_bastano_a_proporre_n_cluster():
    """Una sigma stimata su tre delta non e' una numerosita': e' rumore arrotondato."""
    assert (
        milestone_raggiunta(
            n_cluster=None,
            clusters_observed=2,
            observations=3,
            gia_notificate=(),
            osservazioni_minime=10,
        )
        is None
    )


def test_una_milestone_gia_notificata_non_si_ripete():
    """Il job gira ogni poche ore: senza spegnimento la milestone diventa rumore."""
    assert (
        milestone_raggiunta(
            n_cluster=None,
            clusters_observed=4,
            observations=12,
            gia_notificate=(Milestone.N_CLUSTER_PROPONIBILE,),
            osservazioni_minime=10,
        )
        is None
    )


def test_a_meta_strada_si_apre_la_ri_stima_blinded():
    """`at_fraction_of_N_cluster: 0.50`, e il contratto ne concede una sola."""
    raggiunta = milestone_raggiunta(
        n_cluster=40,
        clusters_observed=20,
        observations=60,
        gia_notificate=(),
        osservazioni_minime=10,
    )

    assert raggiunta is not None
    assert raggiunta.nome == Milestone.RI_STIMA_BLINDED
    assert raggiunta.n_cluster == 40


def test_prima_di_meta_strada_non_si_apre_nulla():
    assert (
        milestone_raggiunta(
            n_cluster=40,
            clusters_observed=19,
            observations=57,
            gia_notificate=(),
            osservazioni_minime=10,
        )
        is None
    )


def test_al_traguardo_scatta_l_unica_analisi_decisionale():
    raggiunta = milestone_raggiunta(
        n_cluster=40,
        clusters_observed=40,
        observations=118,
        gia_notificate=(Milestone.RI_STIMA_BLINDED,),
        osservazioni_minime=10,
    )

    assert raggiunta is not None
    assert raggiunta.nome == Milestone.ANALISI_DECISIONALE


def test_al_traguardo_l_analisi_vince_sulla_ri_stima_mai_notificata():
    """Se il job e' stato fermo, non si recupera una finestra gia' chiusa.

    A `N_cluster` la ri-stima non serve piu': notificarla adesso manderebbe
    l'operatore a rifare una stima intermedia invece dell'analisi che il
    contratto gli chiede, e la ri-stima concessa e' una sola.
    """
    raggiunta = milestone_raggiunta(
        n_cluster=40,
        clusters_observed=41,
        observations=120,
        gia_notificate=(),
        osservazioni_minime=10,
    )

    assert raggiunta is not None
    assert raggiunta.nome == Milestone.ANALISI_DECISIONALE


def test_il_riepilogo_porta_solo_statistiche_blinded():
    """`interim_reviews_limited_to: [integrita', sicurezza, statistiche blinded]`.

    Il report di #298 calcola anche `mean_delta_bps` e `net_delta_usd`. Un
    monitor che li spedisse ogni quattro ore mostrerebbe l'effetto prima
    dell'analisi decisionale, che e' esattamente cio' che la pre-registrazione
    vieta.
    """
    raggiunta = milestone_raggiunta(
        n_cluster=40,
        clusters_observed=20,
        observations=60,
        gia_notificate=(),
        osservazioni_minime=10,
    )
    assert raggiunta is not None

    riepilogo = riepilogo_blinded(raggiunta, sigma_delta_bps=180.4)

    assert set(riepilogo) <= CAMPI_BLINDED_AMMESSI
    assert "mean_delta_bps" not in riepilogo
    assert "net_delta_usd" not in riepilogo
    assert riepilogo["sigma_delta_bps"] == 180.4


def test_un_campo_non_blinded_e_rifiutato_invece_che_ignorato():
    """Scartarlo in silenzio lascerebbe credere che sia stato pubblicato."""
    raggiunta = milestone_raggiunta(
        n_cluster=40,
        clusters_observed=40,
        observations=120,
        gia_notificate=(),
        osservazioni_minime=10,
    )
    assert raggiunta is not None

    with pytest.raises(ValueError, match="mean_delta_bps"):
        riepilogo_blinded(raggiunta, extra={"mean_delta_bps": 246.5})
