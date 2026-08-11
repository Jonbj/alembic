"""Test del wrapper `scripts/daily_s4_ic.sh` aggiunto per #180.

Il vincolo strutturale e' doppio:
- come gli altri script di cron, deve redirigere TUTTO lo stdout/stderr sul
  file di log PRIMA di qualunque operazione significativa, perche' il
  crontab di sistema non fornisce un suo redirect;
- NON deve toccare il cron del report alpha-miss (#171, #174 congelano
  quel cron fino alla verifica del primo commit automatico del ledger).
"""

from __future__ import annotations

from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
S4_IC_SCRIPT = ROOT / "scripts" / "daily_s4_ic.sh"
ALPHA_MISS_SCRIPT = ROOT / "scripts" / "daily_alpha_miss_analysis.sh"


def test_esiste_e_rendere_eseguibile():
    """Lo script deve esistere come file eseguibile."""
    assert S4_IC_SCRIPT.exists()
    # Il bit di esecuzione deve essere settato per essere invocato dal cron.
    mode = S4_IC_SCRIPT.stat().st_mode
    assert mode & 0o111, f"{S4_IC_SCRIPT} non e' eseguibile"


def test_redirect_persistente_prima_del_run():
    """`exec >>"$LOG_FILE"` deve apparire prima dell'invocazione di compute_s4_ic.py.

    Pattern identico agli altri cron (#74): la creazione della directory di log
    puo' precedere il redirect perche' non produce output (mkdir e' silenzioso
    se la directory esiste gia'), ma il comando operativo che puo' fallire —
    l'invocazione di compute_s4_ic.py — deve gia' redirigere tutto.
    """
    source = S4_IC_SCRIPT.read_text()
    pos_redirect = source.index('exec >>"$LOG_FILE" 2>&1')
    # Cerca l'invocazione effettiva (uv run), non i riferimenti nei commenti.
    pos_run = source.index('uv run python "$PROJECT_DIR/scripts/compute_s4_ic.py"')
    assert pos_redirect < pos_run, (
        "Il redirect persistente deve precedere il run di compute_s4_ic.py, "
        "altrimenti un fallimento resterebbe invisibile."
    )


def test_chiama_compute_s4_ic_senza_toccare_alpha_miss():
    """Il wrapper chiama compute_s4_ic.py e NON modifica daily_alpha_miss_analysis.sh."""
    wrapper = S4_IC_SCRIPT.read_text()
    assert "compute_s4_ic.py" in wrapper
    # Il cron alpha-miss non deve cambiare: lo snapshot della sua source resta
    # quello del branch base (lo script non viene toccato).
    assert ALPHA_MISS_SCRIPT.exists()
    # Niente riferimenti al nuovo script dentro alpha-miss: significa che non
    # lo stiamo agganciando DENTRO quel cron, ma accanto.
    alpha_source = ALPHA_MISS_SCRIPT.read_text()
    assert "compute_s4_ic" not in alpha_source
    assert "daily_s4_ic.sh" not in alpha_source


def test_log_file_path_dentro_Project():
    """Il log deve finire in logs/ del progetto, non altrove."""
    source = S4_IC_SCRIPT.read_text()
    assert 'LOG_DIR="$PROJECT_DIR/logs"' in source
    assert 's4_ic_${DATE}.log' in source


def test_notification_state_e_in_gitignore():
    """Lo stato della notifica e' runtime, non un artefatto decisionale."""
    gitignore = (ROOT / ".gitignore").read_text()
    assert "s4_ic_notification.json" in gitignore, (
        "Il file di stato della notifica one-shot NON va versionato: e' "
        "informazione runtime di quando l'ultimo PASS/FAIL e' stato annunciato, "
        "l'artefatto decisionale e' docs/evidence/s4_ic.json."
    )


# ---------------------------------------------------------------------------
# Ambiente del cron (rilievo bloccante della review su PR #224).
# Il cron parte con PATH minimo e senza le variabili del .env: senza correzione
# il wrapper muore su `uv: command not found`, oppure gira e salta la notifica
# Telegram in silenzio. E' gia' successo al loop roadmap (bb74fa4).
# ---------------------------------------------------------------------------

def test_il_wrapper_mette_local_bin_nel_path():
    """Sotto cron `uv` sta in ~/.local/bin, che non e' nel PATH minimale."""
    testo = (ROOT / "scripts" / "daily_s4_ic.sh").read_text()
    assert 'export PATH="$HOME/.local/bin' in testo, (
        "senza questo il cron non trova `uv` e il giro muore prima di cominciare"
    )


def test_il_wrapper_carica_le_credenziali_telegram():
    """Senza le due chiavi la notifica del kill criterion viene saltata in silenzio."""
    testo = (ROOT / "scripts" / "daily_s4_ic.sh").read_text()
    assert "TELEGRAM_(BOT_TOKEN|CHAT_ID)" in testo, (
        "l'annuncio richiesto da #180 resterebbe meta' fatto"
    )
    assert ".env" in testo
