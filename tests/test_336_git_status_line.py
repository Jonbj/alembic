"""Test di accettazione #336 (punto 4) — esito git machine-readable nel log del cron.

Il cron alpha-miss segnala oggi il proprio esito git solo in prosa italiana
("ATTENZIONE: ledger scritto ma NON committato — branch corrente <nome>, atteso main"),
quindi la review settimanale non puo' contare i fallimenti senza interpretare testo libero.

Contratto richiesto: il blocco C del prompt deve istruire a stampare come ultima riga
una fra `GIT_STATUS=pushed`, `GIT_STATUS=committed_not_pushed`, `GIT_STATUS=not_committed`,
una per ciascuno dei tre esiti gia' descritti nel blocco. Le frasi esistenti restano.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "daily_alpha_miss_analysis.sh"

VALORI_AMMESSI = {"pushed", "committed_not_pushed", "not_committed"}
TOKEN_RE = re.compile(r"GIT_STATUS=([A-Za-z_]+)")


def _blocco_c() -> str:
    """Il blocco C del prompt (istruzioni di commit/push), fino all'inizio del blocco D."""
    testo = SCRIPT.read_text(encoding="utf-8")
    inizio = testo.index("C) Committa i ledger")
    fine = testo.index("D) Nella sezione", inizio)
    return testo[inizio:fine]


def _indice(blocco: str, *alternative: str) -> int:
    """Posizione della prima ancora trovata; fallisce il test se nessuna e' presente."""
    for ancora in alternative:
        pos = blocco.find(ancora)
        if pos != -1:
            return pos
    pytest.fail(f"nessuna delle ancore {alternative!r} e' presente nel blocco C")


def test_i_tre_valori_sono_presenti():
    trovati = set(TOKEN_RE.findall(_blocco_c()))
    assert VALORI_AMMESSI <= trovati, f"valori mancanti: {sorted(VALORI_AMMESSI - trovati)}"


def test_nessun_valore_estraneo():
    trovati = set(TOKEN_RE.findall(_blocco_c()))
    assert trovati <= VALORI_AMMESSI, f"valori non previsti: {sorted(trovati - VALORI_AMMESSI)}"


def test_ramo_push_riuscito_emette_pushed():
    blocco = _blocco_c()
    inizio = _indice(blocco, 'Se stampa "main"')
    fine = _indice(blocco, "Se il push fallisce")
    assert "GIT_STATUS=pushed" in blocco[inizio:fine], (
        "il ramo 'branch main, commit e push riusciti' non emette GIT_STATUS=pushed"
    )


def test_ramo_push_fallito_emette_committed_not_pushed():
    blocco = _blocco_c()
    inizio = _indice(blocco, "Se il push fallisce")
    fine = _indice(blocco, "QUALSIASI ALTRA COSA")
    assert "GIT_STATUS=committed_not_pushed" in blocco[inizio:fine], (
        "il ramo 'push fallito, commit locale' non emette GIT_STATUS=committed_not_pushed"
    )


def test_ramo_branch_sbagliato_emette_not_committed():
    blocco = _blocco_c()
    inizio = _indice(blocco, "QUALSIASI ALTRA COSA")
    assert "GIT_STATUS=not_committed" in blocco[inizio:], (
        "il ramo 'branch diverso da main' non emette GIT_STATUS=not_committed"
    )


def test_le_frasi_esistenti_restano():
    blocco = _blocco_c()
    assert "ATTENZIONE: ledger scritto ma NON committato" in blocco
    assert "git push origin main" in blocco
