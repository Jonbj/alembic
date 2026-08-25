"""Regression tests per la pubblicazione delle review verbose su GitHub.

GitHub rifiuta i commenti oltre 65536 caratteri. Le trascrizioni dei recensori che
leggono molti file (diff, sorgenti numerati, prompt riecheggiato) arrivano a 230-280 KB:
il commento non veniva pubblicato e il cancello restava senza verbale. `tronca_coda_review`
pubblica la coda — dove sta il giudizio — con la stessa nozione di coda usata da
`estrai_verdetto`, piu' un tetto in caratteri come rete finale.
"""

from __future__ import annotations

import os
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "roadmap_agent_loop.sh"

# Il limite duro di GitHub sul corpo di un commento.
LIMITE_GITHUB = 65536


def _tronca(testo: str) -> str:
    """Esegue il troncamento sullo stdin dato e ne restituisce l'output."""
    env = os.environ.copy()
    env["HOME"] = env.get("HOME", "/tmp")
    res = subprocess.run(
        ["bash", str(SCRIPT), "--tronca-coda"],
        input=testo,
        capture_output=True,
        text=True,
        env=env,
        cwd=str(ROOT),
        timeout=60,
    )
    assert res.returncode == 0, f"troncamento uscito con {res.returncode}: {res.stderr}"
    return res.stdout


class TestTestoCorto:
    """Una review breve entra tutta: non deve essere alterata."""

    def test_verdetto_resta_presente_e_in_coda(self) -> None:
        testo = (
            "Ho letto il diff di scripts/roadmap_agent_loop.sh.\n"
            "Il criterio 1 e' soddisfatto: la costante e' derivata da CODA_ESITO.\n"
            "Il criterio 2 e' soddisfatto: il tetto in caratteri resta sotto 65536.\n"
            "\n"
            "VERDETTO: APPROVA\n"
        )
        out = _tronca(testo)
        righe = [r for r in out.splitlines() if r.strip()]
        assert righe[-1] == "VERDETTO: APPROVA"
        assert "Ho letto il diff di scripts/roadmap_agent_loop.sh." in out

    def test_nessuna_riga_persa(self) -> None:
        testo = "riga 1\nriga 2\nriga 3\nVERDETTO: RESPINGI\n"
        assert _tronca(testo).splitlines() == testo.splitlines()


class TestTrascrizioneVerbosa:
    """Il caso reale: una trascrizione piu' grande di entrambi i limiti."""

    def test_output_sotto_il_limite_di_github(self) -> None:
        testo = "riga di trascrizione con un po' di contenuto\n" * 5000 + "VERDETTO: RESPINGI\n"
        assert len(testo) > LIMITE_GITHUB
        out = _tronca(testo)
        assert len(out) < LIMITE_GITHUB, f"output di {len(out)} caratteri: non pubblicabile"

    def test_verdetto_sopravvive_al_troncamento(self) -> None:
        testo = "riga di trascrizione con un po' di contenuto\n" * 5000 + "VERDETTO: RESPINGI\n"
        out = _tronca(testo)
        righe = [r for r in out.splitlines() if r.strip()]
        assert righe[-1] == "VERDETTO: RESPINGI"

    def test_riga_singola_enorme_viene_tagliata(self) -> None:
        """Poche righe non bastano a stare sotto il limite: un dump di sorgente su
        una riga sola supera 65536 caratteri da solo. E' il caso che `tail -n`
        non copre e che il tetto in caratteri esiste per chiudere."""
        testo = "x" * 300000 + "\nVERDETTO: RESPINGI\n"
        out = _tronca(testo)
        assert len(out) < LIMITE_GITHUB, f"output di {len(out)} caratteri: non pubblicabile"
        assert "VERDETTO: RESPINGI" in out
