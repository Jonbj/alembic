"""Test del confine impuro del triage: la risposta grezza non si perde mai."""

import json
from datetime import date

import pytest

import scripts.triage_log_locale as triage


class _Risposta:
    """Risposta HTTP minima del server llama.cpp."""

    ok = True
    status_code = 200

    def __init__(self, contenuto):
        self._contenuto = contenuto

    def json(self):
        return {"choices": [{"message": {"content": self._contenuto}}]}


def _stub(monkeypatch, contenuto):
    monkeypatch.setattr(triage.requests, "post", lambda *a, **k: _Risposta(contenuto))


def test_la_risposta_grezza_viene_scritta_prima_del_parsing(monkeypatch, tmp_path):
    _stub(monkeypatch, '{"reperti": []}')
    triage.interroga("T0001 esempio", date(2026, 9, 14), tmp_path)
    assert (tmp_path / "risposta_grezza_2026-09-14.json").read_text() == '{"reperti": []}'


def test_la_grezza_resta_su_disco_anche_quando_il_parsing_fallisce(monkeypatch, tmp_path):
    _stub(monkeypatch, '{"reperti": [{"anomalia": "trava')
    with pytest.raises(json.JSONDecodeError):
        triage.interroga("T0001 esempio", date(2026, 9, 14), tmp_path)
    salvata = (tmp_path / "risposta_grezza_2026-09-14.json").read_text()
    assert salvata.startswith('{"reperti"')


def test_un_json_troncato_dopo_un_reperto_completo_viene_recuperato(monkeypatch, tmp_path):
    troncato = (
        '{"reperti": [{"template_id": "T0001", "gravita": "ALTA", "anomalia": "a", '
        '"citazione": "c", "perche_anomalo": "p", "cosa_controllare": "q"}, '
        '{"template_id": "T0002", "gravita": "MEDIA", "anomalia": "b'
    )
    _stub(monkeypatch, troncato)
    referto = triage.interroga("T0001 esempio", date(2026, 9, 14), tmp_path)
    assert len(referto["reperti"]) == 1
    assert referto["reperti"][0]["template_id"] == "T0001"
