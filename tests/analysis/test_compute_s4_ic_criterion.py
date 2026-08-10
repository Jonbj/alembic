"""Test per la logica di esito contro la soglia del kill criterion S4 (#180).

La soglia del kill criterion e' registrata in `config/s4_kill_criterion.yaml`
dall'operatore. Lo script `scripts/compute_s4_ic.py` la legge, confronta il
campione corrente e scrive l'esito in `docs/evidence/s4_ic.json`. Quando
l'esito diventa PASS o FAIL, parte una notifica Telegram UNA VOLTA — la
seconda volta viene soppressa finche' lo stato non rientra.

Questi test coprono la logica pura, senza DB, senza docker, senza Telegram:
- lettura/assenza del file di soglia
- calcolo dell'esito in tutti e quattro gli stati (NO_CRITERION,
  INSUFFICIENT_N, PASS, FAIL)
- idempotenza della notifica (secondo trigger = niente)
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _importa(monkeypatch=None, criterion_file=None, notify_file=None):
    """Importa/ricarica il modulo e applica gli override dei path.

    monkeypatch va applicato DOPO il reload: altrimenti il reload sovrascrive
    gli attributi CRITERION_FILE/NOTIFY_FILE con i valori del sorgente.
    """
    if "compute_s4_ic" in sys.modules:
        cs = importlib.reload(sys.modules["compute_s4_ic"])
    else:
        cs = importlib.import_module("compute_s4_ic")
    if monkeypatch is not None:
        if criterion_file is not None:
            monkeypatch.setattr(cs, "CRITERION_FILE", criterion_file, raising=False)
        if notify_file is not None:
            monkeypatch.setattr(cs, "NOTIFY_FILE", notify_file, raising=False)
    return cs


# ----------------------------------------------------------------------------
# Lettura della soglia
# ----------------------------------------------------------------------------


def test_leggi_criterio_ritorna_none_se_file_assente(tmp_path, monkeypatch):
    """Se il file non esiste, l'esito sara' NO_CRITERION."""
    cs = _importa(monkeypatch, criterion_file=tmp_path / "inesistente.yaml")
    assert cs._leggi_criterio() is None


def test_leggi_criterio_ritorna_none_se_file_vuoto(tmp_path, monkeypatch):
    """File presente ma vuoto: consideralo assente, NO_CRITERION."""
    path = tmp_path / "s4_kill_criterion.yaml"
    path.write_text("")
    cs = _importa(monkeypatch, criterion_file=path)
    assert cs._leggi_criterio() is None


def test_leggi_criterio_legge_i_campi_minimi(tmp_path, monkeypatch):
    """Con un file valido, il dict contiene i campi attesi."""
    path = tmp_path / "s4_kill_criterion.yaml"
    path.write_text(
        "min_giorni: 73\n"
        "significativo_a_t: 3.0\n"
        "max_ic_rilevabile_a_t: 0.05\n"
    )
    cs = _importa(monkeypatch, criterion_file=path)
    criterio = cs._leggi_criterio()
    assert criterio == {
        "min_giorni": 73,
        "significativo_a_t": 3.0,
        "max_ic_rilevabile_a_t": 0.05,
    }


def test_leggi_criterio_segnala_file_senza_min_giorni(tmp_path, monkeypatch):
    """File presente ma senza il campo richiesto: consideralo assente."""
    path = tmp_path / "s4_kill_criterion.yaml"
    path.write_text("significativo_a_t: 3.0\n")
    cs = _importa(monkeypatch, criterion_file=path)
    assert cs._leggi_criterio() is None


# ----------------------------------------------------------------------------
# Calcolo dell'esito
# ----------------------------------------------------------------------------


@pytest.fixture
def sintesi_minima():
    """Una sintesi del blocco 1g di S4 con IC negativo e t = -2.5, n=40."""
    return {
        "tutti": {
            "1g": {
                "giorni": 40,
                "ic_medio": -0.030,
                "dev_std": 0.140,
                "t_stat": -2.5,
                "significativo_a_3": False,
                "ic_rilevabile_a_t3": 0.066,
            }
        }
    }


def test_esito_no_criterion_se_file_assente(tmp_path, monkeypatch, sintesi_minima):
    cs = _importa(monkeypatch, criterion_file=tmp_path / "inesistente.yaml")
    esito = cs._esito(sintesi_minima)
    assert esito["criterio_registrato"] is False
    assert esito["esito"] == "NO_CRITERION"
    assert esito["soglia"] is None
    assert esito["n_corrente"] == 40
    assert esito["n_richiesto"] is None


def test_esito_insufficient_n_sotto_min_giorni(tmp_path, monkeypatch, sintesi_minima):
    path = tmp_path / "s4_kill_criterion.yaml"
    path.write_text(
        "min_giorni: 73\nsignificativo_a_t: 3.0\nmax_ic_rilevabile_a_t: 0.05\n"
    )
    cs = _importa(monkeypatch, criterion_file=path)
    esito = cs._esito(sintesi_minima)
    assert esito["esito"] == "INSUFFICIENT_N"
    assert esito["soglia"] is None
    assert esito["n_corrente"] == 40
    assert esito["n_richiesto"] == 73


def test_esito_fail_quando_ic_sopra_min_giorni_e_significativo_negativo(tmp_path, monkeypatch):
    path = tmp_path / "s4_kill_criterion.yaml"
    path.write_text(
        "min_giorni: 30\nsignificativo_a_t: 3.0\nmax_ic_rilevabile_a_t: 0.05\n"
    )
    cs = _importa(monkeypatch, criterion_file=path)
    sintesi = {
        "tutti": {
            "1g": {
                "giorni": 40, "ic_medio": -0.08, "dev_std": 0.140,
                "t_stat": -4.0, "significativo_a_3": True, "ic_rilevabile_a_t3": 0.066,
            }
        }
    }
    esito = cs._esito(sintesi)
    assert esito["esito"] == "FAIL"
    assert esito["n_corrente"] == 40
    assert esito["n_richiesto"] == 30


def test_esito_pass_quando_ic_sopra_min_giorni_e_significativo_positivo(tmp_path, monkeypatch):
    path = tmp_path / "s4_kill_criterion.yaml"
    path.write_text(
        "min_giorni: 30\nsignificativo_a_t: 3.0\nmax_ic_rilevabile_a_t: 0.05\n"
    )
    cs = _importa(monkeypatch, criterion_file=path)
    sintesi = {
        "tutti": {
            "1g": {
                "giorni": 40, "ic_medio": 0.08, "dev_std": 0.140,
                "t_stat": 4.0, "significativo_a_3": True, "ic_rilevabile_a_t3": 0.066,
            }
        }
    }
    esito = cs._esito(sintesi)
    assert esito["esito"] == "PASS"


def test_esito_insufficient_n_se_significativo_ma_sotto_min_giorni(tmp_path, monkeypatch):
    """Soglia 73, n=40, IC forte: lo stato resta INSUFFICIENT_N, non PASS/FAIL."""
    path = tmp_path / "s4_kill_criterion.yaml"
    path.write_text(
        "min_giorni: 73\nsignificativo_a_t: 3.0\nmax_ic_rilevabile_a_t: 0.05\n"
    )
    cs = _importa(monkeypatch, criterion_file=path)
    sintesi = {
        "tutti": {
            "1g": {
                "giorni": 40, "ic_medio": -0.08, "dev_std": 0.140,
                "t_stat": -4.0, "significativo_a_3": True, "ic_rilevabile_a_t3": 0.066,
            }
        }
    }
    esito = cs._esito(sintesi)
    # Il criterio richiede 73 giorni, ne abbiamo 40: anche con segnale forte,
    # senza campione sufficiente la decisione e' "non decidibile" — e il freeze
    # del criterio esige questo comportamento.
    assert esito["esito"] == "INSUFFICIENT_N"
    assert esito["n_corrente"] == 40
    assert esito["n_richiesto"] == 73


def test_esito_insufficient_n_se_t_sotto_soglia_signif(tmp_path, monkeypatch):
    """n >= soglia ma |t| < soglia_signif: NON PASS per default."""
    path = tmp_path / "s4_kill_criterion.yaml"
    path.write_text(
        "min_giorni: 30\nsignificativo_a_t: 3.0\nmax_ic_rilevabile_a_t: 0.05\n"
    )
    cs = _importa(monkeypatch, criterion_file=path)
    sintesi = {
        "tutti": {
            "1g": {
                "giorni": 40, "ic_medio": 0.01, "dev_std": 0.140,
                "t_stat": 0.5, "significativo_a_3": False, "ic_rilevabile_a_t3": 0.066,
            }
        }
    }
    esito = cs._esito(sintesi)
    assert esito["esito"] == "INSUFFICIENT_N"


# ----------------------------------------------------------------------------
# Notifica one-shot: idempotenza
# ----------------------------------------------------------------------------


def _scrivi_notifica(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload))


def test_notifica_primo_trigger_ritorna_true(tmp_path, monkeypatch):
    """Se non c'e' notifica precedente, il trigger deve passare."""
    cs = _importa(monkeypatch, notify_file=tmp_path / "s4_ic_notification.json")
    monkeypatch.setattr(cs, "_tg_send", lambda text: True)
    deve = cs._gestisci_notifica({"esito": "FAIL", "n_corrente": 73, "n_richiesto": 73})
    assert deve is True


def test_notifica_secondo_trigger_stesso_esito_ritorna_false(tmp_path, monkeypatch):
    """Se l'ultima notifica aveva lo stesso esito, NON retriggerare."""
    from datetime import datetime, timezone, timedelta

    cs = _importa(monkeypatch, notify_file=tmp_path / "s4_ic_notification.json")
    monkeypatch.setattr(cs, "_tg_send", lambda text: True)
    ieri = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    _scrivi_notifica(tmp_path / "s4_ic_notification.json",
                     {"esito": "FAIL", "notificato_il": ieri})
    deve = cs._gestisci_notifica({"esito": "FAIL", "n_corrente": 73, "n_richiesto": 73})
    assert deve is False


def test_notifica_transizione_fail_a_pass_rettriggerra(tmp_path, monkeypatch):
    """Un cambio di esito (FAIL -> PASS) e' un nuovo evento, va notificato."""
    from datetime import datetime, timezone, timedelta

    cs = _importa(monkeypatch, notify_file=tmp_path / "s4_ic_notification.json")
    monkeypatch.setattr(cs, "_tg_send", lambda text: True)
    ieri = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    _scrivi_notifica(tmp_path / "s4_ic_notification.json",
                     {"esito": "FAIL", "notificato_il": ieri})
    deve = cs._gestisci_notifica({"esito": "PASS", "n_corrente": 80, "n_richiesto": 73})
    assert deve is True


def test_notifica_non_triggera_per_stati_non_decisionali(tmp_path, monkeypatch):
    """NO_CRITERION e INSUFFICIENT_N non sono notifiche: l'osservazione prosegue."""
    cs = _importa(monkeypatch, notify_file=tmp_path / "s4_ic_notification.json")
    monkeypatch.setattr(cs, "_tg_send", lambda text: True)
    for stato in ("NO_CRITERION", "INSUFFICIENT_N"):
        deve = cs._gestisci_notifica({"esito": stato, "n_corrente": 10, "n_richiesto": 73})
        assert deve is False, f"{stato} non deve mai triggerare una notifica"


def test_notifica_solo_per_fail_pass_via_telegram(tmp_path, monkeypatch):
    """Quando ritriggera, il testo del messaggio contiene i campi chiave."""
    catturato = []
    cs = _importa(monkeypatch, notify_file=tmp_path / "s4_ic_notification.json")
    # Patch DOPO l'import/refresh del modulo, altrimenti il reload ripristina
    # la funzione originale.
    monkeypatch.setattr(cs, "_tg_send", lambda t: catturato.append(t))
    cs._gestisci_notifica({
        "esito": "FAIL", "n_corrente": 73, "n_richiesto": 73,
        "ic_medio": -0.07, "t_stat": -3.4,
    })
    assert len(catturato) == 1
    msg = catturato[0]
    assert "FAIL" in msg
    assert "73" in msg  # n_corrente
