"""Test della disposizione dei reperti: senza, la precisione resta un aneddoto."""

from datetime import date

from scripts.triage_disponi import riassunto


def _reperto(giorno, identificativo):
    return {"giorno": giorno, "id": identificativo}


def test_il_riassunto_conta_i_non_disposti_separatamente():
    reperti = [_reperto("2026-09-14", "R01"), _reperto("2026-09-14", "R02")]
    disposizioni = [{"giorno": "2026-09-14", "id": "R01", "esito": "confermato"}]
    testo = riassunto(reperti, disposizioni, date(2026, 9, 1))
    assert "2 reperti, 1 disposti" in testo
    assert "non_disposto=1" in testo
    assert "precisione sui disposti: 100%" in testo


def test_zero_confermati_fa_scattare_l_avviso_della_clausola_di_uscita():
    reperti = [_reperto("2026-09-14", "R01")]
    disposizioni = [{"giorno": "2026-09-14", "id": "R01", "esito": "falso"}]
    assert "clausola di uscita" in riassunto(reperti, disposizioni, date(2026, 9, 1))


def test_i_reperti_fuori_finestra_non_entrano_nel_conto():
    reperti = [_reperto("2026-08-01", "R01"), _reperto("2026-09-14", "R02")]
    assert "1 reperti" in riassunto(reperti, [], date(2026, 9, 1))


def test_senza_disposizioni_la_precisione_non_e_un_numero_inventato():
    assert "precisione sui disposti: n/d" in riassunto([_reperto("2026-09-14", "R01")], [], date(2026, 9, 1))
