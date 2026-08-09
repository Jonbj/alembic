"""Regression tests per #211 — lettura del verdetto di review nel loop roadmap.

Il cancello 2 dell'auto-merge legge il verdetto dall'output del recensore. Quell'output
non e' un giudizio: e' la trascrizione completa della sessione (prompt riecheggiato,
comandi eseguiti, diff, sorgenti). Cercarci dentro una sottostringa produce due difetti,
entrambi riprodotti qui con materiale preso dalle review reali del 2026-08-08.
"""

from __future__ import annotations

import os
from pathlib import Path
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "roadmap_agent_loop.sh"

# La coda del prompt, riecheggiata da codex nel proprio output PRIMA di giudicare.
# Contiene entrambe le righe canoniche: e' la sorgente del falso APPROVA.
ECO_DEL_PROMPT = """\
Sii concreto: cita file e riga. Se non trovi problemi dillo in una riga, senza inventarne per
sembrare accurato.

Chiudi la risposta con UNA SOLA di queste due righe, esattamente come scritta, in ultima posizione:
VERDETTO: APPROVA
VERDETTO: RESPINGI
codex
Leggo prima le convenzioni, il metodo roadmap e il charter.
"""


def _verdetto(testo: str) -> str:
    """Esegue il parser del verdetto sullo stdin dato e ne restituisce l'esito."""
    env = os.environ.copy()
    env["HOME"] = env.get("HOME", "/tmp")
    res = subprocess.run(
        ["bash", str(SCRIPT), "--verdetto"],
        input=testo,
        capture_output=True,
        text=True,
        env=env,
        cwd=str(ROOT),
        timeout=60,
    )
    assert res.returncode == 0, f"parser uscito con {res.returncode}: {res.stderr}"
    return res.stdout.strip()


class TestVerdettoLettoDallaCoda:
    """Difetto 1: il verdetto veniva letto dall'eco del prompt invece che dal giudizio."""

    def test_respingi_non_diventa_approva_per_eco_del_prompt(self) -> None:
        """Il caso di PR #209: giudizio RESPINGI, ma l'eco del prompt viene prima.

        Con `grep -q "^VERDETTO: APPROVA$"` su tutto l'output il match cadeva sulla
        riga 52 (eco), non sul giudizio finale: APPROVA, e quindi merge + deploy di
        una PR che il recensore aveva respinto.
        """
        out = ECO_DEL_PROMPT + "\nLa PR non soddisfa il criterio 1.\n\nVERDETTO: RESPINGI\n"
        assert _verdetto(out) == "RESPINGI"

    def test_approva_autentico_resta_approva(self) -> None:
        """Il fix non deve rendere impossibile approvare: il caso di PR #206."""
        out = ECO_DEL_PROMPT + "\nNessun problema rilevato nel diff.\n\nVERDETTO: APPROVA\n"
        assert _verdetto(out) == "APPROVA"

    def test_output_pulito_senza_eco_resta_corretto(self) -> None:
        """glm52 non riecheggia il prompt: l'output e' gia' un giudizio."""
        assert _verdetto("Nessun problema.\n\nVERDETTO: APPROVA\n") == "APPROVA"
        assert _verdetto("Test insufficienti.\n\nVERDETTO: RESPINGI\n") == "RESPINGI"

    def test_sessione_morta_dopo_l_eco_non_approva_mai(self) -> None:
        """Se la sessione muore subito dopo aver riecheggiato il prompt, l'unico
        materiale disponibile sono le due righe canoniche. L'esito non deve MAI
        essere APPROVA: nell'eco RESPINGI viene per ultima, quindi `tail -1` e'
        sicuro per costruzione."""
        assert _verdetto(ECO_DEL_PROMPT) != "APPROVA"


class TestRateLimitNonDedottoDallaTrascrizione:
    """Difetto 2: il rate limit veniva dedotto da cio' che il recensore aveva LETTO."""

    def test_titolo_di_issue_su_rate_limiting_non_e_un_rate_limit(self) -> None:
        """Il caso reale: `gh issue list` stampa il titolo della issue #43."""
        out = (
            "43\tOPEN\tB8: rate limiting + CORS\thigh, pre-live-blocker\t2026-08-06T11:15:01Z\n"
            "La PR non soddisfa il criterio 1.\n\nVERDETTO: RESPINGI\n"
        )
        assert _verdetto(out) == "RESPINGI"

    def test_hunk_del_diff_con_429_non_e_un_rate_limit(self) -> None:
        """`@@ -429,6 +438,20 @@` soddisfaceva il ramo `429` del regex."""
        out = "@@ -429,6 +438,20 @@\n-  vecchio\n+  nuovo\n\nVERDETTO: RESPINGI\n"
        assert _verdetto(out) == "RESPINGI"

    def test_numero_di_riga_429_non_e_un_rate_limit(self) -> None:
        """Un sorgente numerato che passa per la riga 3429."""
        out = "  3429\t# #108: exclude FinBERT-fallback signals\n\nVERDETTO: APPROVA\n"
        assert _verdetto(out) == "APPROVA"

    def test_rate_limit_vero_resta_rilevato(self) -> None:
        """Una sessione uccisa dal rate limit non produce un verdetto in coda."""
        out = "Reading input...\nError: 429 Too Many Requests\nquota exceeded\n"
        assert _verdetto(out) == "RATE_LIMIT"

    def test_sessione_senza_verdetto_e_senza_rate_limit(self) -> None:
        """Timeout o crash: nessun verdetto, nessun rate limit."""
        assert _verdetto("Sto leggendo il diff...\nsegmentation fault\n") == "NON_ESEGUITA"


class TestMergeSoloSuApprovaEsplicito:
    """Il cancello deve poter dire di si' solo su un giudizio esplicito."""

    @pytest.mark.parametrize(
        "testo",
        [
            "",
            "VERDETTO: FORSE\n",
            "verdetto: approva\n",
            "Direi VERDETTO: APPROVA ma con riserva\n",
        ],
    )
    def test_niente_di_ambiguo_produce_approva(self, testo: str) -> None:
        assert _verdetto(testo) != "APPROVA"
