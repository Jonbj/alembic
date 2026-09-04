"""Politica di selezione della PR da esaminare (spec 2026-09-03 §4)."""

from src.review_locale.selezione import PrCandidata, scegli


def _pr(numero: int, sha: str, creata_il: str) -> PrCandidata:
    return PrCandidata(numero=numero, sha=sha, creata_il=creata_il)


def _voce(numero: int, sha: str, stato: str) -> dict:
    return {"pr": numero, "sha": sha, "stato": stato}


def test_ledger_vuoto_prende_la_piu_vecchia():
    scelta = scegli(
        [
            _pr(480, "aaa", "2026-09-02T10:00:00Z"),
            _pr(472, "bbb", "2026-09-02T08:00:00Z"),
        ],
        ledger=[],
    )

    assert scelta is not None
    assert scelta.numero == 472


def test_pr_gia_esaminata_non_torna():
    scelta = scegli(
        [_pr(472, "bbb", "2026-09-02T08:00:00Z")],
        ledger=[_voce(472, "bbb", "ESAMINATA_CON_RILIEVI")],
    )

    assert scelta is None


def test_esaminata_senza_rilievi_conta_come_esaminata():
    scelta = scegli(
        [_pr(472, "bbb", "2026-09-02T08:00:00Z")],
        ledger=[_voce(472, "bbb", "ESAMINATA_SENZA_RILIEVI")],
    )

    assert scelta is None


def test_nuovo_commit_riapre_la_pr():
    """L'identita' dell'esame e' (numero, sha), non il numero."""
    scelta = scegli(
        [_pr(472, "ccc", "2026-09-02T08:00:00Z")],
        ledger=[_voce(472, "bbb", "ESAMINATA_CON_RILIEVI")],
    )

    assert scelta is not None
    assert scelta.sha == "ccc"


def test_un_tentativo_fallito_non_esaurisce_lo_sha():
    scelta = scegli(
        [_pr(472, "bbb", "2026-09-02T08:00:00Z")],
        ledger=[_voce(472, "bbb", "NON_ESAMINATA")],
    )

    assert scelta is not None


def test_due_tentativi_falliti_esauriscono_lo_sha():
    """Stop rule del NODE_CONTRACT: due tentativi per sha, poi basta."""
    scelta = scegli(
        [_pr(472, "bbb", "2026-09-02T08:00:00Z")],
        ledger=[_voce(472, "bbb", "NON_ESAMINATA"), _voce(472, "bbb", "NON_ESAMINATA")],
    )

    assert scelta is None


def test_sha_esaurito_non_blocca_un_commit_nuovo():
    scelta = scegli(
        [_pr(472, "ccc", "2026-09-02T08:00:00Z")],
        ledger=[_voce(472, "bbb", "NON_ESAMINATA"), _voce(472, "bbb", "NON_ESAMINATA")],
    )

    assert scelta is not None
    assert scelta.sha == "ccc"


def test_nessuna_pr_aperta_non_e_un_errore():
    assert scegli([], ledger=[]) is None


def test_salta_la_esaurita_e_prende_la_successiva():
    scelta = scegli(
        [
            _pr(472, "bbb", "2026-09-02T08:00:00Z"),
            _pr(480, "aaa", "2026-09-02T10:00:00Z"),
        ],
        ledger=[_voce(472, "bbb", "ESAMINATA_CON_RILIEVI")],
    )

    assert scelta is not None
    assert scelta.numero == 480
