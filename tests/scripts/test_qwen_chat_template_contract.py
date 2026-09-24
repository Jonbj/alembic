"""Contratto fra i chiamanti del Qwen locale e il chat template del modello (#653).

Il GGUF `Qwen3.8-27B-Q8_0.gguf` porta con se' un `chat_template.jinja` che riscrive
il prompt: con thinking attivo e `reasoning_effort` xhigh (il default del template
*e* il flag `--reasoning-effort xhigh` dei service `llama-server{,-notte}`) antepone
un system prompt che nessuno di noi ha scritto; con un livello che non conosce
(`high`, `max`, ...) solleva un'eccezione e il server risponde 500.

Questi test prendono il payload **vero** di ogni chiamante, lo uniscono ai default
del server come fa llama.cpp e lo passano al template estratto dal GGUF. Se un
chiamante perde il suo `reasoning_effort` o il suo `enable_thinking: false`, il test
lo vede nel prompt renderizzato e non in una review a occhio.

Fixture: `tests/fixtures/llm/qwen3.8-27b-q8_0.chat_template.jinja`, estratto con
`gguf-py` da `tokenizer.chat_template`. Se il modello cambia, va riestratto e lo
sha256 qui sotto aggiornato: il test sullo sha lo impone.

Il renderer e' jinja2 (arriva con torch), non il motore di llama.cpp: sui casi di
questo file i due producono gli stessi byte, verificato con
`llama.cpp/build/bin/test-chat-template --no-common` il 2026-09-24.
"""

from __future__ import annotations

import hashlib
from datetime import date
from pathlib import Path

import jinja2
import pytest

import review_notturna_locale as review
import scripts.s4_cluster_literature as cluster
import scripts.triage_log_locale as triage

TEMPLATE = Path(__file__).parents[1] / "fixtures" / "llm" / "qwen3.8-27b-q8_0.chat_template.jinja"
TEMPLATE_SHA256 = "c3cf9e34abf4f9e36c2d72165aa9c132d3e2a725b6c2586aaa3a8af9d7a81041"

# `default_template_kwargs` prodotti dai flag di ~/.config/systemd/user/llama-server{,-notte}.service:
# `--reasoning-effort xhigh` e `--reasoning-preserve` (llama.cpp common/arg.cpp).
DEFAULT_SERVER = {"reasoning_effort": "xhigh", "preserve_reasoning": True}

FRASE_INIETTATA = "Reasoning effort is set to"


def _rendi(payload: dict, default_server: dict = DEFAULT_SERVER) -> str:
    """Renderizza il prompt che llama-server costruirebbe per `payload`.

    Replica l'unione di tools/server/server-common.cpp (kwargs del server, poi quelli
    della richiesta, poi il campo OAI `reasoning_effort`) e il contesto di
    common/chat.cpp::common_chat_template_direct_apply_impl (`enable_thinking` sempre
    definito, `preserve_reasoning` -> `preserve_thinking`).
    """
    kwargs = dict(default_server)
    kwargs.update(payload.get("chat_template_kwargs") or {})
    enable_thinking = kwargs.get("enable_thinking", True)
    if "reasoning_effort" in payload:
        if payload["reasoning_effort"] == "none":
            enable_thinking = False
            kwargs.pop("reasoning_effort", None)
        elif payload["reasoning_effort"]:
            kwargs["reasoning_effort"] = payload["reasoning_effort"]

    contesto = {
        "messages": payload["messages"],
        "bos_token": "",
        "eos_token": "",
        "enable_thinking": enable_thinking,
        "add_generation_prompt": True,
    }
    if isinstance(kwargs.get("preserve_reasoning"), bool):
        contesto["preserve_thinking"] = kwargs["preserve_reasoning"]
    if kwargs.get("reasoning_effort"):
        contesto["reasoning_effort"] = kwargs["reasoning_effort"]

    def raise_exception(messaggio: str):
        raise jinja2.TemplateError(messaggio)

    ambiente = jinja2.Environment(trim_blocks=True, lstrip_blocks=True)
    ambiente.globals["raise_exception"] = raise_exception
    return ambiente.from_string(TEMPLATE.read_text()).render(**contesto)


# --- cattura dei payload reali ------------------------------------------------


def _payload_review(monkeypatch) -> dict:
    catturato: dict = {}

    class _Risposta:
        def raise_for_status(self):
            return None

        def iter_lines(self):
            return iter(["data: [DONE]"])

    class _Stream:
        def __enter__(self):
            return _Risposta()

        def __exit__(self, *_exc):
            return False

    def stream(*_a, **k):
        catturato.update(k["json"])
        return _Stream()

    monkeypatch.setattr(review.httpx, "stream", stream)
    review.interroga_modello("PROMPT_REVIEW")
    return catturato


class _RispostaJson:
    ok = True
    status_code = 200
    text = ""

    def __init__(self, contenuto: str):
        self._contenuto = contenuto

    def json(self):
        return {"choices": [{"message": {"content": self._contenuto}}]}


def _payload_triage(monkeypatch, tmp_path) -> dict:
    catturato: dict = {}

    def post(*_a, **k):
        catturato.update(k["json"])
        return _RispostaJson('{"reperti": []}')

    monkeypatch.setattr(triage.requests, "post", post)
    triage.interroga("T0001 esempio", date(2026, 9, 24), tmp_path)
    return catturato


def _payload_cluster(monkeypatch) -> dict:
    catturato: dict = {}

    def post(*_a, **k):
        catturato.update(k["json"])
        return _RispostaJson("{}")

    monkeypatch.setattr(cluster.requests, "post", post)
    cluster.chat(cluster.NODE1, cluster.MODEL1, "SISTEMA", "UTENTE", max_tokens=16)
    return catturato


# --- il template e' quello che crediamo --------------------------------------


def test_la_fixture_e_il_template_del_modello_in_uso():
    assert hashlib.sha256(TEMPLATE.read_bytes()).hexdigest() == TEMPLATE_SHA256


def test_il_renderer_riproduce_l_iniezione_su_una_chiamata_nuda():
    """Controllo del controllo: senza override il template inietta davvero la frase.

    Se questo smette di essere vero, i test sui chiamanti passerebbero per il motivo
    sbagliato (renderer rotto, non chiamanti corretti).
    """
    prompt = _rendi({"messages": [{"role": "user", "content": "ciao"}]})
    assert prompt.startswith("<|im_start|>system\n" + FRASE_INIETTATA + " xhigh.")


def test_un_livello_non_supportato_fa_fallire_il_template():
    """`high` e' un livello valido per llama.cpp ma non per questo template: 500."""
    with pytest.raises(jinja2.TemplateError, match="Unexpected reasoning effort high"):
        _rendi({"messages": [{"role": "user", "content": "ciao"}], "reasoning_effort": "high"})


# --- i chiamanti ---------------------------------------------------------------


def test_review_notturna_arriva_senza_system_iniettato(monkeypatch):
    payload = _payload_review(monkeypatch)
    assert payload["reasoning_effort"] == "medium"
    prompt = _rendi(payload)
    assert FRASE_INIETTATA not in prompt
    assert prompt == (
        "<|im_start|>user\nPROMPT_REVIEW<|im_end|>\n<|im_start|>assistant\n<think>\n"
    )


def test_triage_arriva_col_solo_system_proprio_e_thinking_chiuso(monkeypatch, tmp_path):
    payload = _payload_triage(monkeypatch, tmp_path)
    assert payload["chat_template_kwargs"] == {"enable_thinking": False}
    prompt = _rendi(payload)
    assert FRASE_INIETTATA not in prompt
    assert prompt.startswith("<|im_start|>system\n" + triage.SISTEMA.strip() + "<|im_end|>\n")
    assert prompt.endswith("<|im_start|>assistant\n<think>\n\n</think>\n\n")


def test_cluster_literature_arriva_col_solo_system_proprio_e_thinking_chiuso(monkeypatch):
    payload = _payload_cluster(monkeypatch)
    assert payload["chat_template_kwargs"] == {"enable_thinking": False}
    prompt = _rendi(payload)
    assert FRASE_INIETTATA not in prompt
    assert prompt == (
        "<|im_start|>system\nSISTEMA<|im_end|>\n"
        "<|im_start|>user\nUTENTE<|im_end|>\n"
        "<|im_start|>assistant\n<think>\n\n</think>\n\n"
    )


@pytest.mark.parametrize("default_server", [{}, {"reasoning_effort": "low"}, DEFAULT_SERVER])
def test_i_chiamanti_non_dipendono_dal_default_del_server(monkeypatch, tmp_path, default_server):
    """Il prompt di ogni chiamante e' lo stesso qualunque `--reasoning-effort` abbia il service."""
    payloads = {
        "review": _payload_review(monkeypatch),
        "triage": _payload_triage(monkeypatch, tmp_path),
        "cluster": _payload_cluster(monkeypatch),
    }
    for nome, payload in payloads.items():
        assert _rendi(payload, default_server) == _rendi(payload), nome
