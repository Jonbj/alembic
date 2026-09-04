"""Filtro del diff e costruzione dei prompt (spec 2026-09-03 §4)."""

from src.review_locale.estrazione import costruisci_prompt, file_toccati, filtra_diff


def _hunk(percorso: str, righe: int) -> str:
    corpo = "\n".join(f"+riga di contenuto numero {i}" for i in range(righe))
    return (
        f"diff --git a/{percorso} b/{percorso}\n"
        f"index 0000000..1111111 100644\n"
        f"--- a/{percorso}\n"
        f"+++ b/{percorso}\n"
        f"@@ -0,0 +1,{righe} @@\n"
        f"{corpo}\n"
    )


ISSUE = "## What to build\n\nUn funnel a due assi.\n\n## Acceptance criteria\n\n- [ ] Deterministico."


def test_file_toccati_elenca_tutti_i_percorsi():
    diff = _hunk("src/a.py", 3) + _hunk("docs/evidence/dossier/2026-09-01.json", 5)

    assert file_toccati(diff) == ["src/a.py", "docs/evidence/dossier/2026-09-01.json"]


def test_filtra_via_i_file_di_dati():
    """La forma di PR #477: il dossier generato domina il diff."""
    diff = _hunk("scripts/misura.py", 10) + _hunk("docs/evidence/dossier/2026-09-01.json", 5000)

    filtrato = filtra_diff(diff)

    assert "scripts/misura.py" in filtrato
    assert "dossier/2026-09-01.json" not in filtrato
    assert len(filtrato) < len(diff) / 10


def test_filtra_via_i_test():
    diff = _hunk("src/a.py", 5) + _hunk("tests/test_a.py", 5)

    filtrato = filtra_diff(diff)

    assert "src/a.py" in filtrato
    assert "tests/test_a.py" not in filtrato


def test_diff_di_soli_dati_non_produce_prompt():
    diff = _hunk("docs/evidence/dossier/2026-09-01.json", 100)

    assert costruisci_prompt(diff, ISSUE) == []


def test_diff_sotto_il_tetto_resta_un_prompt_unico():
    """Sotto il tetto si conserva la visione d'insieme.

    Il rilievo migliore prodotto su PR #472 — la contraddizione fra il commento
    di funnel.py:88 e l'ordine di valutazione reale — richiedeva di vedere il
    modulo intero.
    """
    diff = _hunk("src/a.py", 20) + _hunk("src/b.py", 20)

    prompt = costruisci_prompt(diff, ISSUE)

    assert len(prompt) == 1
    assert "src/a.py" in prompt[0]
    assert "src/b.py" in prompt[0]


def test_diff_sopra_il_tetto_si_spezza_per_file():
    diff = _hunk("src/a.py", 400) + _hunk("src/b.py", 400)

    prompt = costruisci_prompt(diff, ISSUE, tetto_byte=5_000)

    assert len(prompt) == 2
    assert "src/a.py" in prompt[0] and "src/b.py" not in prompt[0]
    assert "src/b.py" in prompt[1] and "src/a.py" not in prompt[1]


def test_ogni_prompt_porta_la_issue_e_lo_schema():
    diff = _hunk("src/a.py", 400) + _hunk("src/b.py", 400)

    prompt = costruisci_prompt(diff, ISSUE, tetto_byte=5_000)

    for singolo in prompt:
        assert "Acceptance criteria" in singolo
        assert "scenario_di_fallimento" in singolo
        assert "ramo_irraggiungibile" in singolo
        assert "mascherato_da" in singolo


def test_il_prompt_chiede_di_non_approvare():
    """Il compito e' trovare difetti, non dare un verdetto."""
    prompt = costruisci_prompt(_hunk("src/a.py", 10), ISSUE)

    assert "NON e' approvare" in prompt[0]


def test_file_piccoli_si_impacchettano_in_meno_prompt_dei_file():
    """La forma di PR #477: 14 file, i sei piu' piccoli stavano insieme sotto i 15 KB.

    Cinque file da ~390 byte l'uno (_hunk con 10 righe) con tetto_byte=1_000:
    due stanno insieme (780 <= 1000), un terzo li farebbe sforare (1170 > 1000).
    Impacchettamento greedy nell'ordine del diff:
      a+b -> 780 (c li farebbe sforare) => prompt 1: [a, b]
      c+d -> 780 (e lo farebbe sforare)  => prompt 2: [c, d]
      e                                   => prompt 3: [e]
    """
    diff = (
        _hunk("src/a.py", 10)
        + _hunk("src/b.py", 10)
        + _hunk("src/c.py", 10)
        + _hunk("src/d.py", 10)
        + _hunk("src/e.py", 10)
    )

    prompt = costruisci_prompt(diff, ISSUE, tetto_byte=1_000)

    assert len(prompt) == 3
    assert len(prompt) < 5
    assert "src/a.py" in prompt[0] and "src/b.py" in prompt[0]
    assert "src/c.py" not in prompt[0] and "src/d.py" not in prompt[0] and "src/e.py" not in prompt[0]
    assert "src/c.py" in prompt[1] and "src/d.py" in prompt[1]
    assert "src/a.py" not in prompt[1] and "src/b.py" not in prompt[1] and "src/e.py" not in prompt[1]
    assert "src/e.py" in prompt[2]
    assert "src/a.py" not in prompt[2] and "src/c.py" not in prompt[2]


def test_file_enorme_isolato_non_blocca_limpacchettamento_degli_altri():
    """Un file da solo gia' sopra il tetto resta isolato, ma non spezza i piccoli.

    huge (~1562 byte) supera da solo tetto_byte=1_000; le due small (~390 byte
    l'una) stanno insieme (780 <= 1000). Ordine nel diff: huge, small1, small2.
    """
    diff = _hunk("src/huge.py", 50) + _hunk("src/small1.py", 10) + _hunk("src/small2.py", 10)

    prompt = costruisci_prompt(diff, ISSUE, tetto_byte=1_000)

    assert len(prompt) == 2
    assert "src/huge.py" in prompt[0]
    assert "src/small1.py" not in prompt[0] and "src/small2.py" not in prompt[0]
    assert "src/small1.py" in prompt[1] and "src/small2.py" in prompt[1]
    assert "src/huge.py" not in prompt[1]


def test_nessun_file_perso_o_duplicato_nellimpacchettamento():
    diff = (
        _hunk("src/a.py", 10)
        + _hunk("src/b.py", 10)
        + _hunk("src/c.py", 10)
        + _hunk("src/d.py", 10)
        + _hunk("src/e.py", 10)
    )

    prompt = costruisci_prompt(diff, ISSUE, tetto_byte=1_000)

    for marcatore in ("src/a.py", "src/b.py", "src/c.py", "src/d.py", "src/e.py"):
        occorrenze = sum(1 for singolo in prompt if marcatore in singolo)
        assert occorrenze == 1, f"{marcatore} compare {occorrenze} volte, atteso 1"
