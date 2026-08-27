"""Test di accettazione #330 — sincronizzare col remoto prima di committare il ledger.

Due report giornalieri (18 e 19 agosto) sono rimasti commit locali: il push e' stato
rifiutato come non-fast-forward perche' il remoto era avanzato mentre il job lavorava.
Il job non si sincronizza prima di committare, e per protocollo non forza il push.

Il fix va nel blocco "C)" del prompt in scripts/daily_alpha_miss_analysis.sh, e ha un
vincolo di sicurezza non negoziabile: la sincronizzazione deve stare **dentro** il ramo
che ha gia' verificato di essere su main. La issue #336 documenta che 2 dei 5 run della
stessa settimana girarono su un branch di feature altrui: un `pull --rebase` eseguito
la' rebaserebbe e spingerebbe il branch sbagliato.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "daily_alpha_miss_analysis.sh"


def _blocco_c() -> str:
    testo = SCRIPT.read_text(encoding="utf-8")
    inizio = testo.index("C) Committa i ledger")
    fine = testo.index("D) Nella sezione", inizio)
    return testo[inizio:fine]


def _indice(blocco: str, *alternative: str) -> int:
    for ancora in alternative:
        pos = blocco.find(ancora)
        if pos != -1:
            return pos
    pytest.fail(f"nessuna delle ancore {alternative!r} e' presente nel blocco C")


def test_il_blocco_c_prescrive_una_sincronizzazione_col_remoto():
    assert re.search(r"git pull\s+--rebase", _blocco_c()), (
        "il blocco C non prescrive `git pull --rebase` prima del commit"
    )


def test_la_sincronizzazione_nomina_esplicitamente_origin_main():
    assert re.search(r"git pull\s+--rebase\s+origin\s+main", _blocco_c()), (
        "la sincronizzazione deve nominare `origin main`, non un remoto implicito"
    )


def test_la_sincronizzazione_sta_dentro_il_ramo_main():
    """Vincolo di sicurezza: mai sincronizzare prima di aver verificato il branch."""
    blocco = _blocco_c()
    pos_guardia = _indice(blocco, 'Se stampa "main"')
    pos_pull = blocco.index("git pull")
    pos_altro_ramo = _indice(blocco, "QUALSIASI ALTRA COSA")
    assert pos_guardia < pos_pull < pos_altro_ramo, (
        "`git pull --rebase` deve stare dentro il ramo 'branch == main', "
        "fra la guardia e il ramo che gestisce gli altri branch"
    )


def test_la_sincronizzazione_precede_il_commit():
    blocco = _blocco_c()
    assert blocco.index("git pull") < blocco.index("git commit"), (
        "sincronizzare dopo il commit non evita il rifiuto: il pull va prima"
    )


def test_e_previsto_un_solo_nuovo_tentativo_di_push():
    blocco = _blocco_c().lower()
    assert "riprova" in blocco or "ritenta" in blocco or "nuovo tentativo" in blocco, (
        "il blocco C non prescrive di riprovare il push una volta dopo la sincronizzazione"
    )


def test_il_divieto_di_forzare_il_push_resta():
    blocco = _blocco_c()
    assert "NON forzarlo" in blocco
    assert "--force" not in blocco, "nessuna forma di push forzato e' ammessa"


def test_la_guardia_sul_branch_resta_intatta():
    blocco = _blocco_c()
    assert "git rev-parse --abbrev-ref HEAD" in blocco
    assert "ATTENZIONE: ledger scritto ma NON committato" in blocco
    assert "git push origin main" in blocco
