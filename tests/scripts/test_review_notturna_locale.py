"""Orchestratore della review notturna: integrazione con gh e server finti."""

import json

import httpx
import pytest

import review_notturna_locale as orch


_RILIEVO = {
    "gravita": "ALTA",
    "categoria": "non_determinismo",
    "posizione": "src/x.py:10",
    "difetto": "soglia letta a run time",
    "scenario_di_fallimento": "rieseguire il giorno 08-25 riclassifica BELOW_GATE",
    "mascherato_da": None,
}


class _Finti:
    """Registra le chiamate esterne invece di eseguirle."""

    def __init__(self, risposta: str):
        self.risposta = risposta
        self.commenti: list[tuple[int, str]] = []
        self.ledger: list[dict] = []
        self.server_avviato = 0
        self.server_fermato = 0


@pytest.fixture
def finti(monkeypatch):
    f = _Finti(risposta=json.dumps({"rilievi": [_RILIEVO]}))

    monkeypatch.setattr(orch, "avvia_server", lambda: f.__setattr__("server_avviato", f.server_avviato + 1))
    monkeypatch.setattr(orch, "ferma_server", lambda: f.__setattr__("server_fermato", f.server_fermato + 1))
    monkeypatch.setattr(orch, "pr_aperte", lambda: [orch.PrCandidata(472, "bbb", "2026-09-02T08:00:00Z")])
    monkeypatch.setattr(orch, "diff_pr", lambda numero: (
        "diff --git a/src/x.py b/src/x.py\n--- a/src/x.py\n+++ b/src/x.py\n@@ -0,0 +1,1 @@\n+x = 1\n"
    ))
    monkeypatch.setattr(orch, "issue_della_pr", lambda numero: "## Acceptance criteria\n- [ ] Deterministico.")
    monkeypatch.setattr(orch, "leggi_ledger", lambda: f.ledger)
    monkeypatch.setattr(orch, "scrivi_ledger", lambda voce: f.ledger.append(voce))
    monkeypatch.setattr(orch, "pubblica_commento", lambda numero, corpo: f.commenti.append((numero, corpo)))
    monkeypatch.setattr(orch, "interroga_modello", lambda prompt: (f.risposta, "ragionamento", 1000))
    return f


def test_referto_con_rilievi_pubblica_e_registra(finti):
    codice = orch.main([])

    assert codice == 0
    assert len(finti.commenti) == 1
    numero, corpo = finti.commenti[0]
    assert numero == 472
    assert "soglia letta a run time" in corpo
    assert finti.ledger[-1]["stato"] == "ESAMINATA_CON_RILIEVI"


def test_il_commento_dichiara_l_origine(finti):
    """Chi legge deve poter pesare i rilievi sapendo da dove vengono."""
    orch.main([])

    _, corpo = finti.commenti[0]
    assert "modello locale" in corpo
    assert "non verificat" in corpo


def test_referto_senza_rilievi_non_pubblica(finti):
    finti.risposta = json.dumps({"rilievi": []})

    codice = orch.main([])

    assert codice == 0
    assert finti.commenti == []
    assert finti.ledger[-1]["stato"] == "ESAMINATA_SENZA_RILIEVI"


def test_json_invalido_non_pubblica(finti):
    finti.risposta = "{non e' JSON"

    codice = orch.main([])

    assert codice == 0
    assert finti.commenti == []
    assert finti.ledger[-1]["stato"] == "NON_ESAMINATA"


def test_le_assoluzioni_non_raggiungono_il_commento(finti):
    """Il principio della spec, verificato end-to-end."""
    finti.risposta = json.dumps({
        "rilievi": [_RILIEVO],
        "verificato_e_scartato": ["La SQL esclude correttamente SKIP_THRESHOLD"],
    })

    orch.main([])

    _, corpo = finti.commenti[0]
    assert "verificato_e_scartato" not in corpo
    assert "SKIP_THRESHOLD" not in corpo


def test_nessuna_pr_eleggibile_non_accende_il_server(finti, monkeypatch):
    monkeypatch.setattr(orch, "pr_aperte", lambda: [])

    codice = orch.main([])

    assert codice == 0
    assert finti.server_avviato == 0
    assert finti.commenti == []


def test_il_server_viene_sempre_fermato(finti):
    finti.risposta = "{non e' JSON"

    orch.main([])

    assert finti.server_avviato == 1
    assert finti.server_fermato == 1


def test_avvio_server_fallito_ferma_e_registra_e_rilancia(finti, monkeypatch):
    """Issue 3: se avvia_server() esplode, ferma_server() gira comunque e il
    ledger riceve una riga NON_ESAMINATA invece di sparire nel nulla."""

    def esplodi():
        raise RuntimeError("il server locale non ha risposto a /health entro 5 minuti")

    monkeypatch.setattr(orch, "avvia_server", esplodi)

    with pytest.raises(RuntimeError, match="non ha risposto a /health"):
        orch.main([])

    assert finti.server_fermato == 1
    assert finti.commenti == []
    assert finti.ledger[-1]["stato"] == "NON_ESAMINATA"
    assert "guasto durante avvio del server" in finti.ledger[-1]["causa"]


def test_pubblicazione_fallita_ferma_e_registra_e_rilancia(finti, monkeypatch):
    """Issue 4: se pubblica_commento() esplode, i rilievi gia' trovati non
    scompaiono senza lasciare traccia nel ledger."""

    def esplodi(numero, corpo):
        raise RuntimeError("gh pr comment: rete irraggiungibile")

    monkeypatch.setattr(orch, "pubblica_commento", esplodi)

    with pytest.raises(RuntimeError, match="rete irraggiungibile"):
        orch.main([])

    assert finti.server_avviato == 1
    assert finti.server_fermato == 1
    ultima = finti.ledger[-1]
    assert ultima["stato"] == "NON_ESAMINATA"
    assert "guasto durante pubblicazione del commento" in ultima["causa"]
    assert ultima["rilievi"] == 1


def test_interroga_modello_propaga_errore_http(monkeypatch):
    """Issue 5: un 4xx/5xx dal server non deve diventare silenziosamente
    ("", "", 0) — che a valle e' indistinguibile da un JSON rotto del modello."""

    class _RispostaFinta:
        def raise_for_status(self):
            richiesta = httpx.Request("POST", "http://127.0.0.1:8080/v1/chat/completions")
            raise httpx.HTTPStatusError(
                "500 Internal Server Error",
                request=richiesta,
                response=httpx.Response(500, request=richiesta),
            )

        def iter_lines(self):
            raise AssertionError("non si deve iterare il corpo dopo un errore HTTP")

    class _StreamFinto:
        def __enter__(self):
            return _RispostaFinta()

        def __exit__(self, *_exc):
            return False

    monkeypatch.setattr(orch.httpx, "stream", lambda *a, **k: _StreamFinto())

    with pytest.raises(httpx.HTTPStatusError):
        orch.interroga_modello("prompt qualunque")
