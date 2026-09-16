"""Il motore glm53 passa da z.ai, non piu' da Ollama Cloud.

Lo script viene eseguito davvero: `claude`, `ollama` e `codex` sono finti e stanno
in un PATH davanti a quello vero. Un finto che manca non e' neutro — `ollama` vive
in /usr/local/bin e il test finirebbe per fare una chiamata cloud vera.

Le prove usano `--prova <motore>` e `--motori`, che esercitano gli stessi
`motore_installato` / `esegui_agente` del giro vero senza toccare gh o git.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "roadmap_agent_loop.sh"

CHIAVE = "zai-chiave-di-prova-123456"

# Il finto registra l'ambiente che ha ricevuto: e' l'unico modo di verificare che
# le variabili arrivino al comando giusto e non oltre.
MOTORE_FINTO = """
{
  printf '=== %s ===\\n' "$(basename "$0")"
  printf 'ARGS: %s\\n' "$*"
  printf 'ANTHROPIC_BASE_URL=%s\\n' "${ANTHROPIC_BASE_URL:-<assente>}"
  printf 'ANTHROPIC_AUTH_TOKEN=%s\\n' "${ANTHROPIC_AUTH_TOKEN:-<assente>}"
  printf 'ANTHROPIC_DEFAULT_HAIKU_MODEL=%s\\n' "${ANTHROPIC_DEFAULT_HAIKU_MODEL:-<assente>}"
  printf 'API_TIMEOUT_MS=%s\\n' "${API_TIMEOUT_MS:-<assente>}"
} >> "$ENV_CAPTURE"
printf 'PRONTO\\n'
"""


def _eseguibile(path: Path, body: str) -> None:
    path.write_text("#!/usr/bin/env bash\n" + body)
    path.chmod(0o755)


def _ambiente(tmp_path: Path, *, con_chiave: bool = True) -> dict[str, str]:
    bin_dir = tmp_path / ".local" / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    for nome in ("claude", "ollama", "codex"):
        _eseguibile(bin_dir / nome, MOTORE_FINTO)
    _eseguibile(bin_dir / "curl", 'printf "%s\\n" "$*" >> "$TG_CAPTURE"\n')

    if con_chiave:
        chiavi = tmp_path / ".config" / "alembic"
        chiavi.mkdir(parents=True, exist_ok=True)
        (chiavi / "zai.env").write_text(f"ZAI_API_KEY={CHIAVE}\n")

    log_dir = tmp_path / "logs"
    log_dir.mkdir(exist_ok=True)
    queue = tmp_path / "queue.txt"
    queue.write_text("10 prima\n")

    env = os.environ.copy()
    # Una chiave vera nell'ambiente della suite non deve poter entrare nel test.
    env.pop("ZAI_API_KEY", None)
    env.update(
        {
            "HOME": str(tmp_path),
            "PATH": f"{bin_dir}:{env['PATH']}",
            "ROADMAP_QUEUE_FILE": str(queue),
            "ROADMAP_LOG_DIR": str(log_dir),
            "TELEGRAM_BOT_TOKEN": "finto",
            "TELEGRAM_CHAT_ID": "finta",
            "TG_CAPTURE": str(tmp_path / "telegram.txt"),
            "ENV_CAPTURE": str(tmp_path / "env.txt"),
        }
    )
    return env


def _giro(env: dict[str, str], *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(ROOT),
        timeout=120,
        check=False,
    )


def _catturato(env: dict[str, str]) -> str:
    percorso = Path(env["ENV_CAPTURE"])
    return percorso.read_text() if percorso.exists() else ""


def test_glm53_chiama_claude_puntato_su_zai(tmp_path: Path) -> None:
    env = _ambiente(tmp_path)
    esito = _giro(env, "--prova", "glm53")
    catturato = _catturato(env)

    assert "=== claude ===" in catturato, esito.stdout
    assert "ANTHROPIC_BASE_URL=https://api.z.ai/api/anthropic" in catturato
    assert f"ANTHROPIC_AUTH_TOKEN={CHIAVE}" in catturato
    assert "--model glm-5.3" in catturato
    assert "--effort high" in catturato
    assert ">>> glm53 risponde: OK." in esito.stdout


def test_le_chiamate_di_servizio_vanno_sul_modello_economico(tmp_path: Path) -> None:
    # Titolo della sessione e compattazione se le fa Claude Code da solo, e con
    # ANTHROPIC_BASE_URL impostato finiscono su z.ai come tutto il resto. Senza
    # questa mappatura girano sul modello grosso: verificato dal vivo il
    # 2026-09-15, generate_session_title usava glm-5.3. Sul piano Lite e' spreco,
    # e non lo si vede da nessuna parte se non guardando la quota consumarsi.
    env = _ambiente(tmp_path)
    _giro(env, "--prova", "glm53")
    catturato = _catturato(env)
    assert "ANTHROPIC_DEFAULT_HAIKU_MODEL=glm-5.3-flash" in catturato
    # Il lavoro vero resta sul modello grosso: la mappatura economica non deve
    # traboccare su --model, altrimenti le issue le lavorerebbe Flash.
    assert "--model glm-5.3 " in catturato or catturato.count("--model glm-5.3\n")


def test_la_singola_richiesta_ha_un_timeout_largo(tmp_path: Path) -> None:
    # API_TIMEOUT_MS vale per una richiesta, non per la sessione: il limite sul
    # giro resta TIMEOUT_SESSIONE. Serve perche' con un effort alto il modello
    # puo' ragionare a lungo prima di rispondere, e un timeout scattato qui nel
    # log somiglia a un modello che si ferma da solo.
    env = _ambiente(tmp_path)
    _giro(env, "--prova", "glm53")
    catturato = _catturato(env)
    assert "API_TIMEOUT_MS=<assente>" not in catturato
    valore = int(
        [r for r in catturato.splitlines() if r.startswith("API_TIMEOUT_MS=")][0].split("=")[1]
    )
    assert valore >= 10 * 60 * 1000


def test_glm53_non_passa_piu_da_ollama(tmp_path: Path) -> None:
    # Il difetto che questo test esclude: lasciare `ollama launch` al suo posto e
    # credere di aver cambiato trasporto perche' le variabili sono state aggiunte.
    env = _ambiente(tmp_path)
    _giro(env, "--prova", "glm53")
    assert "=== ollama ===" not in _catturato(env)


def test_minimax_resta_su_ollama(tmp_path: Path) -> None:
    env = _ambiente(tmp_path)
    _giro(env, "--prova", "minimax")
    catturato = _catturato(env)
    assert "=== ollama ===" in catturato
    assert "ANTHROPIC_BASE_URL=<assente>" in catturato


def test_codex_non_vede_le_variabili_di_zai(tmp_path: Path) -> None:
    # Le variabili valgono solo per il comando che le usa. Se finissero
    # nell'ambiente globale dirotterebbero ogni altro `claude` della macchina,
    # comprese le sessioni interattive dell'operatore, senza dire niente.
    env = _ambiente(tmp_path)
    _giro(env, "--prova", "codex")
    catturato = _catturato(env)
    assert "=== codex ===" in catturato
    assert "ANTHROPIC_BASE_URL=<assente>" in catturato
    assert "ANTHROPIC_AUTH_TOKEN=<assente>" in catturato
    assert "ANTHROPIC_DEFAULT_HAIKU_MODEL=<assente>" in catturato


def test_senza_chiave_glm53_esce_dalla_rotazione(tmp_path: Path) -> None:
    # Fail-closed: senza chiave il motore non gira e non ripiega su Ollama. Un
    # ripiego silenzioso rimetterebbe il loop sulla quota del trading, che e'
    # esattamente cio' da cui lo stiamo togliendo.
    env = _ambiente(tmp_path, con_chiave=False)
    esito = _giro(env, "--motori")
    riga = [r for r in esito.stdout.splitlines() if r.startswith("glm53")]
    assert riga and "non-installato" in riga[0], esito.stdout

    prova = _giro(env, "--prova", "glm53")
    assert "non installato" in prova.stdout
    assert "=== claude ===" not in _catturato(env)


def test_la_chiave_non_finisce_nei_log(tmp_path: Path) -> None:
    env = _ambiente(tmp_path)
    esito = _giro(env, "--prova", "glm53")
    assert CHIAVE not in esito.stdout
    assert CHIAVE not in esito.stderr
    for percorso in Path(env["ROADMAP_LOG_DIR"]).rglob("*"):
        if percorso.is_file():
            assert CHIAVE not in percorso.read_text(errors="replace"), percorso
