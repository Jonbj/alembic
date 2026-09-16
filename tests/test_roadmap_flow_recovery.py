"""Recupero delle review ferme, tie-breaker sulle respinte e digest degli esiti.

Il loop viene eseguito davvero: `gh`, `git` e i motori sono finti e stanno in un
PATH davanti a quello vero, ma il codice sotto test e' lo script, non una sua
riscrittura. E' l'unico modo di verificare che le funzioni nuove siano chiamate
dai punti giusti — in --dry-run non lo sono per costruzione, e non devono esserlo.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "roadmap_agent_loop.sh"

PR_FERMA = 900
BRANCH_FERMO = "agent/issue-10"


def _eseguibile(path: Path, body: str) -> None:
    path.write_text("#!/usr/bin/env bash\n" + body)
    path.chmod(0o755)


GH_FINTO = """
_json() { printf '%s\\n' "$1"; }

if [[ "$1 $2" == "pr list" ]]; then
    if [[ "$*" == *"closingIssuesReferences"* ]]; then
        _json "$PR_LIST_CHIUSURE"
    elif [[ "$*" == *"--limit 200"* ]]; then
        _json "$PR_LIST_APERTE_JSON"
    elif [[ "$*" == *"--head"* ]]; then
        # `--head agent/issue-N --json number`: il numero della PR di quella issue.
        [[ "$*" == *"$BRANCH_FERMO"* ]] && printf '%s\\n' "$PR_FERMA"
    else
        printf '%s\\n' "$PR_APERTE_BRANCH"
    fi
    exit 0
fi

if [[ "$1 $2" == "pr view" ]]; then
    if [[ "$*" == *".comments[-1].body"* ]]; then
        printf '%s\\n' "$ULTIMO_COMMENTO"
    elif [[ "$*" == *".comments[].body"* ]]; then
        printf '%s\\n' "$TUTTI_I_COMMENTI"
    elif [[ "$*" == *"--json headRefName"* ]]; then
        printf '%s\\n' "$BRANCH_FERMO"
    elif [[ "$*" == *"--json title"* ]]; then
        printf 'Titolo della PR %s\\n' "$3"
    elif [[ "$*" == *"--json url"* ]]; then
        printf 'https://example.invalid/pr/%s\\n' "$3"
    elif [[ "$*" == *"--json state"* ]]; then
        printf 'OPEN\\n'
    fi
    exit 0
fi

if [[ "$1 $2" == "pr comment" ]]; then
    printf '%s\\n' "$*" >> "$COMMENTI_PUBBLICATI"
    exit 0
fi
if [[ "$1 $2" == "pr merge" ]]; then
    printf 'merge %s\\n' "$3" >> "$MERGE_TENTATI"
    exit 0
fi

if [[ "$1 $2" == "run list" ]]; then
    if [[ "$*" == *"--branch main"* ]]; then
        printf '111\\n'
    elif [[ "${CI_CONCLUSA:-1}" == "1" ]]; then
        printf '777\\n'
    fi
    exit 0
fi
if [[ "$1 $2" == "run view" ]]; then
    [[ "$3" == "777" ]] && printf '%s\\n' "${FALLITI_PR:-}"
    exit 0
fi

if [[ "$1 $2" == "issue view" ]]; then
    if [[ "$*" == *"--json state,labels"* ]]; then
        printf 'OPEN freeze-ok\\n'
    elif [[ "$*" == *"--json title"* ]]; then
        printf 'Issue %s\\n' "$3"
    elif [[ "$*" == *"--json body,labels"* ]]; then
        printf 'metadati-stabili\\n'
    elif [[ "$*" == *"--json updatedAt"* ]]; then
        printf '2099-01-01T00:00:00Z\\n'
    elif [[ "$*" == *"--json comments"* ]]; then
        printf '2000-01-01T00:00:00Z\\n'
    fi
    exit 0
fi
if [[ "$1" == "api" ]]; then
    printf '[]\\n'
    exit 0
fi
exit 1
"""

GIT_FINTO = """
if [[ "$1 $2" == "worktree add" ]]; then
    for a in "$@"; do
        case "$a" in /*) mkdir -p "$a"; break ;; esac
    done
elif [[ "$1 $2" == "worktree remove" ]]; then
    for a in "$@"; do
        case "$a" in /*) rm -rf "$a"; break ;; esac
    done
elif [[ "$1" == "rev-parse" ]]; then
    printf 'deadbeef\\n'
fi
exit 0
"""

MOTORE_FINTO = """
printf '%s\\n' "$*" >> "$PROMPT_CAPTURE"
printf 'Ho letto il diff.\\n'
printf 'VERDETTO: %s\\n' "${VERDETTO_FINTO:-RESPINGI}"
"""


def _ambiente(tmp_path: Path, **extra: str) -> dict[str, str]:
    # Lo script antepone `$HOME/.local/bin:/usr/local/bin` al PATH che riceve (il
    # cron parte con un PATH minimo). I finti devono stare li' dentro, altrimenti
    # `ollama`, che vive in /usr/local/bin, sarebbe quello VERO: il test farebbe
    # una chiamata cloud e misurerebbe il modello invece dello script.
    bin_dir = tmp_path / ".local" / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    _eseguibile(bin_dir / "gh", GH_FINTO)
    _eseguibile(bin_dir / "git", GIT_FINTO)
    _eseguibile(bin_dir / "codex", MOTORE_FINTO)
    _eseguibile(bin_dir / "ollama", MOTORE_FINTO)
    # glm53 non passa piu' da `ollama`: dal 2026-09-15 chiama `claude` puntato su
    # z.ai, e senza chiave sarebbe fuori rotazione. Senza questi due la suite
    # girerebbe su due motori invece di tre, e i test sul terzo motore
    # (tie-breaker, recensore diverso dall'implementatore) passerebbero per il
    # motivo sbagliato.
    _eseguibile(bin_dir / "claude", MOTORE_FINTO)
    chiavi = tmp_path / ".config" / "alembic"
    chiavi.mkdir(parents=True, exist_ok=True)
    (chiavi / "zai.env").write_text("ZAI_API_KEY=chiave-finta\n")
    _eseguibile(bin_dir / "curl", 'printf "%s\\n" "$*" >> "$TG_CAPTURE"\n')

    log_dir = tmp_path / "logs"
    log_dir.mkdir(exist_ok=True)
    queue = tmp_path / "queue.txt"
    if not queue.exists():
        queue.write_text("10 prima\n")

    env = os.environ.copy()
    env.update(
        {
            "HOME": str(tmp_path),
            "PATH": f"{bin_dir}:{env['PATH']}",
            "ROADMAP_QUEUE_FILE": str(queue),
            "ROADMAP_LOG_DIR": str(log_dir),
            "TELEGRAM_BOT_TOKEN": "finto",
            "TELEGRAM_CHAT_ID": "finta",
            "TG_CAPTURE": str(tmp_path / "telegram.txt"),
            "PROMPT_CAPTURE": str(tmp_path / "prompt.txt"),
            "COMMENTI_PUBBLICATI": str(tmp_path / "commenti.txt"),
            "MERGE_TENTATI": str(tmp_path / "merge.txt"),
            "BRANCH_FERMO": BRANCH_FERMO,
            "PR_FERMA": str(PR_FERMA),
            "PR_APERTE_BRANCH": "",
            "PR_LIST_APERTE_JSON": "[]",
            "PR_LIST_CHIUSURE": "[]",
            "ULTIMO_COMMENTO": "",
            "TUTTI_I_COMMENTI": "",
        }
    )
    env.update(extra)
    return env


def _pr_aperta_json(*, draft: bool = False, review_decision: str | None = None) -> str:
    return json.dumps(
        [
            {
                "number": PR_FERMA,
                "headRefName": BRANCH_FERMO,
                "headRefOid": "deadbeef",
                "title": "Lavoro sulla issue 10",
                "url": "https://example.invalid/pr/900",
                "isDraft": draft,
                "reviewDecision": review_decision,
            }
        ]
    )


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


def _eventi(env: dict[str, str]) -> list[dict]:
    percorso = Path(env["ROADMAP_LOG_DIR"]) / "roadmap_results.jsonl"
    if not percorso.exists():
        return []
    return [json.loads(r) for r in percorso.read_text().splitlines() if r.strip()]


# --- miglioria 1: recupero delle review ferme -----------------------------------


def test_la_pr_senza_verdetto_viene_ripresa_e_il_giro_si_ferma_li(tmp_path: Path) -> None:
    """La PR ferma da review mai eseguita torna davanti ai cancelli, e il giro
    non lavora anche la issue: una review costa quanto un lavoro."""
    env = _ambiente(
        tmp_path,
        PR_LIST_APERTE_JSON=_pr_aperta_json(),
        PR_APERTE_BRANCH=BRANCH_FERMO,
    )
    (tmp_path / "queue.txt").write_text("10 ferma\n11 lavorabile\n")

    esito = _giro(env)

    assert esito.returncode == 0, esito.stdout + esito.stderr
    assert f"Recupero review: PR #{PR_FERMA}" in esito.stdout
    assert "Giro concluso (recupero di una review ferma)" in esito.stdout

    eventi = _eventi(env)
    review = [e for e in eventi if e["action"] == "review"]
    assert len(review) == 1
    assert review[0]["recovery"] == 1
    assert review[0]["pr"] == PR_FERMA
    assert review[0]["issue"] == 10
    # Il recupero non e' un giro di lavoro: nessun tentativo addebitato a nessuno.
    assert [e for e in eventi if e["action"] == "work"] == []
    assert not (Path(env["ROADMAP_LOG_DIR"]) / "roadmap_agent_state.tsv").read_text().strip()

    prompt = (tmp_path / "prompt.txt").read_text()
    assert "Rivedi la pull request" in prompt
    assert "Lavora la issue" not in prompt


def test_il_recensore_del_recupero_non_e_l_implementatore(tmp_path: Path) -> None:
    """Il cancello 2 vale anche nel recupero: chi ha scritto la PR non la rivede."""
    env = _ambiente(
        tmp_path,
        PR_LIST_APERTE_JSON=_pr_aperta_json(),
        PR_APERTE_BRANCH=BRANCH_FERMO,
    )
    log_dir = Path(env["ROADMAP_LOG_DIR"])
    # Come fa --rivedi: l'implementatore si ricava dal log del giro che apri' la PR.
    (log_dir / "roadmap_agent_2026-09-13.log").write_text(
        f"2026-09-13T07:00:00Z #10 — PR aperta da glm53: https://example.invalid/pr/{PR_FERMA}\n"
    )

    esito = _giro(env)

    assert "implementata da glm53" in esito.stdout
    review = [e for e in _eventi(env) if e["action"] == "review"][0]
    assert review["impl"] == "glm53"
    assert review["engine"] != "glm53"


def test_ci_non_conclusa_lascia_la_pr_ferma_in_silenzio(tmp_path: Path) -> None:
    """Una CI ancora in corso non e' una PR ferma: nessun evento, nessun Telegram,
    una riga di log sola, e il giro va a lavorare la issue."""
    env = _ambiente(
        tmp_path,
        PR_LIST_APERTE_JSON=_pr_aperta_json(),
        CI_CONCLUSA="0",
    )
    (tmp_path / "queue.txt").write_text("11 lavorabile\n")

    esito = _giro(env)

    righe_recupero = [r for r in esito.stdout.splitlines() if "Recupero review" in r]
    assert len(righe_recupero) == 1
    assert "1 con CI ancora in corso" in righe_recupero[0]
    assert [e for e in _eventi(env) if e["action"] == "review"] == []
    assert "Rivedi la pull request" not in (tmp_path / "prompt.txt").read_text()
    assert "Issue selezionata: #11" in esito.stdout


def test_senza_un_secondo_motore_il_recupero_non_spende_il_giro(tmp_path: Path) -> None:
    """Il cancello 2 vale anche qui. I run a motore forzato (cron 9/14/19/23) sono
    proprio quelli che lasciano le PR senza verdetto: se il recupero ci ricadesse
    sopra brucerebbe ogni giro per riscrivere lo stesso NON_ESEGUITA."""
    env = _ambiente(
        tmp_path,
        ROADMAP_FORCE_ENGINE="codex",
        PR_LIST_APERTE_JSON=_pr_aperta_json(),
    )
    log_dir = Path(env["ROADMAP_LOG_DIR"])
    (log_dir / "roadmap_agent_2026-09-14.log").write_text(
        f"2026-09-14T12:08:28Z #10 — PR aperta da codex: https://example.invalid/pr/{PR_FERMA}\n"
    )
    (tmp_path / "queue.txt").write_text("11 lavorabile\n")

    esito = _giro(env)

    assert "senza un recensore diverso dall'implementatore" in esito.stdout
    assert [e for e in _eventi(env) if e["action"] == "review"] == []
    assert "Issue selezionata: #11" in esito.stdout


def test_la_pr_gia_giudicata_non_viene_ripresa(tmp_path: Path) -> None:
    """Il verdetto si legge dall'intestazione scritta dal loop, non dall'eco del
    prompt che la trascrizione pubblicata contiene sempre."""
    env = _ambiente(
        tmp_path,
        PR_LIST_APERTE_JSON=_pr_aperta_json(),
        TUTTI_I_COMMENTI=(
            "## Review automatica — codex\n\n"
            "Verdetto letto: **RESPINGI**\n\n---\n\n"
            "Chiudi la risposta con UNA SOLA di queste due righe:\n"
            "VERDETTO: APPROVA\nVERDETTO: RESPINGI\n"
        ),
    )
    (tmp_path / "queue.txt").write_text("11 lavorabile\n")

    esito = _giro(env)

    assert "Recupero review" not in esito.stdout
    assert [e for e in _eventi(env) if e["action"] == "review"] == []
    assert "Issue selezionata: #11" in esito.stdout


def test_il_dry_run_non_recupera_nulla(tmp_path: Path) -> None:
    env = _ambiente(
        tmp_path,
        PR_LIST_APERTE_JSON=_pr_aperta_json(),
    )
    (tmp_path / "queue.txt").write_text("11 lavorabile\n")

    esito = _giro(env, "--dry-run")

    assert "Recupero review" not in esito.stdout
    assert "Issue selezionata: #11" in esito.stdout
    assert _eventi(env) == []


# --- miglioria 2: tie-breaker ----------------------------------------------------


def _stato_due_respinte(
    tmp_path: Path, env: dict[str, str], *, tiebreaker_fatti: tuple[str, ...] = ()
) -> None:
    log_dir = Path(env["ROADMAP_LOG_DIR"])
    (log_dir / "roadmap_agent_respinte.tsv").write_text("10\t2\n")
    eventi = [
        {"ts": "2026-09-10T07:00:00Z", "action": "review", "result": "not_merged",
         "engine": "glm53", "impl": "codex", "issue": 10, "pr": PR_FERMA,
         "verdetto": "RESPINGI", "respinte": 1},
        {"ts": "2026-09-11T07:00:00Z", "action": "review", "result": "not_merged",
         "engine": "glm53", "impl": "codex", "issue": 10, "pr": PR_FERMA,
         "verdetto": "RESPINGI", "respinte": 2},
    ]
    for n, verdetto in enumerate(tiebreaker_fatti):
        eventi.append(
            {"ts": f"2026-09-1{2 + n}T07:00:00Z", "action": "review", "result": "not_merged",
             "engine": "minimax", "impl": "codex", "issue": 10, "pr": PR_FERMA,
             "verdetto": verdetto, "respinte": 2, "tiebreaker": 1}
        )
    (log_dir / "roadmap_results.jsonl").write_text(
        "".join(json.dumps(e) + "\n" for e in eventi)
    )


def test_alla_seconda_respinta_giudica_un_terzo_motore(tmp_path: Path) -> None:
    """Il tie-breaker va a chi non ha ne' scritto ne' gia' respinto, e la sua
    respinta non diventa una terza respinta."""
    env = _ambiente(
        tmp_path,
        PR_APERTE_BRANCH=BRANCH_FERMO,
        PR_LIST_CHIUSURE=json.dumps(
            [{"number": PR_FERMA, "headRefName": BRANCH_FERMO, "closingIssuesReferences": [{"number": 10}]}]
        ),
        ULTIMO_COMMENTO="Verdetto letto: **RESPINGI**\nVERDETTO: RESPINGI",
        # La PR e' gia' giudicata: il recupero non la tocca, il tie-breaker si'.
        TUTTI_I_COMMENTI="Verdetto letto: **RESPINGI**",
        PR_LIST_APERTE_JSON=_pr_aperta_json(),
    )
    _stato_due_respinte(tmp_path, env)
    (tmp_path / "queue.txt").write_text("10 respinta due volte\n")

    esito = _giro(env)

    assert "esce dalla rotazione: serve l'operatore" in esito.stdout
    assert "Tie-breaker: issue #10, PR #900 affidata a minimax" in esito.stdout
    assert "Giro concluso (tie-breaker su #10)" in esito.stdout

    tb = [e for e in _eventi(env) if e.get("tiebreaker") == 1]
    assert len(tb) == 1
    assert tb[0]["engine"] == "minimax"
    assert tb[0]["action"] == "review"
    # Il conteggio delle respinte non si muove: il tie-breaker e' il terzo
    # giudizio sulla seconda respinta, non una respinta in piu'.
    assert tb[0]["respinte"] == 2
    assert (Path(env["ROADMAP_LOG_DIR"]) / "roadmap_agent_respinte.tsv").read_text() == "10\t2\n"
    assert "minimax-m3:cloud" in (tmp_path / "prompt.txt").read_text()


def test_il_tiebreaker_approva_e_i_cancelli_restano_quelli(tmp_path: Path) -> None:
    """APPROVA non basta: con una regressione in piu' rispetto a main la PR resta
    aperta, esattamente come in un giro normale."""
    env = _ambiente(
        tmp_path,
        PR_APERTE_BRANCH=BRANCH_FERMO,
        PR_LIST_CHIUSURE=json.dumps(
            [{"number": PR_FERMA, "headRefName": BRANCH_FERMO, "closingIssuesReferences": [{"number": 10}]}]
        ),
        ULTIMO_COMMENTO="Verdetto letto: **RESPINGI**\nVERDETTO: RESPINGI",
        TUTTI_I_COMMENTI="Verdetto letto: **RESPINGI**",
        PR_LIST_APERTE_JSON=_pr_aperta_json(),
        VERDETTO_FINTO="APPROVA",
        FALLITI_PR="FAILED tests/test_qualcosa.py::test_uno",
    )
    _stato_due_respinte(tmp_path, env)
    (tmp_path / "queue.txt").write_text("10 respinta due volte\n")

    esito = _giro(env)

    tb = [e for e in _eventi(env) if e.get("tiebreaker") == 1][0]
    assert tb["verdetto"] == "APPROVA"
    assert tb["regressions"] == 1
    assert tb["result"] == "not_merged"
    assert not (tmp_path / "merge.txt").exists()
    assert "NON mergiata" in esito.stdout


def test_il_tiebreaker_si_concede_una_volta_sola(tmp_path: Path) -> None:
    env = _ambiente(
        tmp_path,
        PR_APERTE_BRANCH=BRANCH_FERMO,
        ULTIMO_COMMENTO="VERDETTO: RESPINGI",
        TUTTI_I_COMMENTI="Verdetto letto: **RESPINGI**",
        PR_LIST_APERTE_JSON=_pr_aperta_json(),
    )
    _stato_due_respinte(tmp_path, env, tiebreaker_fatti=("RESPINGI",))
    (tmp_path / "queue.txt").write_text("10 respinta due volte\n")

    esito = _giro(env)

    assert "tie-breaker gia' speso: resta all'operatore" in esito.stdout
    assert len([e for e in _eventi(env) if e.get("tiebreaker") == 1]) == 1


def test_un_tiebreaker_non_eseguito_si_riprova(tmp_path: Path) -> None:
    """Un tie-breaker morto a meta' non ha giudicato niente: bruciarci sopra
    l'unica occasione della issue sarebbe come non averla mai concessa."""
    env = _ambiente(
        tmp_path,
        PR_APERTE_BRANCH=BRANCH_FERMO,
        PR_LIST_CHIUSURE=json.dumps(
            [{"number": PR_FERMA, "headRefName": BRANCH_FERMO, "closingIssuesReferences": [{"number": 10}]}]
        ),
        ULTIMO_COMMENTO="Verdetto letto: **RESPINGI**\nVERDETTO: RESPINGI",
        TUTTI_I_COMMENTI="Verdetto letto: **RESPINGI**",
        PR_LIST_APERTE_JSON=_pr_aperta_json(),
    )
    _stato_due_respinte(tmp_path, env, tiebreaker_fatti=("NON_ESEGUITA",))
    (tmp_path / "queue.txt").write_text("10 respinta due volte\n")

    esito = _giro(env)

    assert "Tie-breaker: issue #10" in esito.stdout
    assert len([e for e in _eventi(env) if e.get("tiebreaker") == 1]) == 2


def test_due_tiebreaker_a_vuoto_bastano(tmp_path: Path) -> None:
    """...ma non all'infinito: una issue fuori rotazione non deve mangiarsi un
    giro dopo l'altro perche' il recensore muore sempre."""
    env = _ambiente(
        tmp_path,
        PR_APERTE_BRANCH=BRANCH_FERMO,
        ULTIMO_COMMENTO="VERDETTO: RESPINGI",
        TUTTI_I_COMMENTI="Verdetto letto: **RESPINGI**",
        PR_LIST_APERTE_JSON=_pr_aperta_json(),
    )
    _stato_due_respinte(tmp_path, env, tiebreaker_fatti=("NON_ESEGUITA", "NON_ESEGUITA"))
    (tmp_path / "queue.txt").write_text("10 respinta due volte\n")

    esito = _giro(env)

    assert "tie-breaker gia' speso: resta all'operatore" in esito.stdout
    assert len([e for e in _eventi(env) if e.get("tiebreaker") == 1]) == 2


def test_senza_un_terzo_motore_niente_tiebreaker(tmp_path: Path) -> None:
    """Con un solo motore in rotazione il tie-breaker non ha a chi andare: la
    issue resta all'operatore, come oggi."""
    env = _ambiente(
        tmp_path,
        ROADMAP_FORCE_ENGINE="codex",
        PR_APERTE_BRANCH=BRANCH_FERMO,
        ULTIMO_COMMENTO="VERDETTO: RESPINGI",
        TUTTI_I_COMMENTI="Verdetto letto: **RESPINGI**",
        PR_LIST_APERTE_JSON=_pr_aperta_json(),
    )
    _stato_due_respinte(tmp_path, env)
    (tmp_path / "queue.txt").write_text("10 respinta due volte\n")

    esito = _giro(env)

    assert "nessun terzo motore diverso da implementatore e recensori" in esito.stdout
    assert [e for e in _eventi(env) if e.get("tiebreaker") == 1] == []


# --- miglioria 3: digest ---------------------------------------------------------


def test_il_digest_riassume_gli_esiti_e_ne_lascia_un_record(tmp_path: Path) -> None:
    env = _ambiente(tmp_path)
    log_dir = Path(env["ROADMAP_LOG_DIR"])
    eventi = [
        {"ts": "2026-09-13T07:00:00Z", "action": "work", "result": "pr_opened",
         "engine": "codex", "issue": 10, "pr": 900, "duration_s": 600},
        {"ts": "2026-09-13T07:30:00Z", "action": "review", "result": "not_merged",
         "engine": "glm53", "impl": "codex", "issue": 10, "pr": 900,
         "verdetto": "NON_ESEGUITA", "respinte": 0},
        {"ts": "2026-09-13T12:00:00Z", "action": "work", "result": "pr_opened",
         "engine": "glm53", "issue": 11, "pr": 901, "duration_s": 1200},
        {"ts": "2026-09-13T12:40:00Z", "action": "review", "result": "merged",
         "engine": "codex", "impl": "glm53", "issue": 11, "pr": 901,
         "verdetto": "APPROVA", "recovery": 1},
        {"ts": "2026-09-13T17:00:00Z", "action": "work", "result": "noop",
         "engine": "minimax", "issue": 12, "duration_s": 120},
        {"ts": "2026-09-13T21:00:00Z", "action": "review", "result": "not_merged",
         "engine": "minimax", "impl": "codex", "issue": 13, "pr": 902,
         "verdetto": "RESPINGI", "respinte": 2, "tiebreaker": 1},
        {"ts": "2020-01-01T00:00:00Z", "action": "work", "result": "failed",
         "engine": "codex", "issue": 99, "duration_s": 9999},
    ]
    (log_dir / "roadmap_results.jsonl").write_text(
        "".join(json.dumps(e) + "\n" for e in eventi)
    )

    esito = _giro(env, "--digest", "30")

    assert esito.returncode == 0, esito.stdout + esito.stderr
    testo = esito.stdout
    assert "- PR aperte: 2" in testo
    assert "PR aperte 2 → mergiate 1 = 50%" in testo
    assert "tentate: 3 → APPROVA 1 · RESPINGI 1 · NON_ESEGUITA 1" in testo
    assert "di cui recuperi: 1 · tie-breaker: 1" in testo
    assert "- #13 — 1 respinte" in testo
    assert "- PR #900 (issue #10) — 1 review non eseguite" in testo
    assert "- pr_opened: 15m (n=2)" in testo
    # Fuori finestra: il giro del 2020 non entra in nessun conteggio.
    assert "failed" not in testo.split("## Durata")[0]

    record = list(log_dir.glob("roadmap_digest_*.md"))
    assert len(record) == 1
    assert record[0].read_text() == testo.split("\n\n(record scritto")[0] + "\n"
    assert "digest" in (tmp_path / "telegram.txt").read_text()


def test_il_digest_non_richiede_il_lock_del_giro(tmp_path: Path) -> None:
    """Un giro dura fino a 90 minuti: un riassunto che si rifiuta di uscire per
    quel motivo non lo guarderebbe nessuno."""
    env = _ambiente(tmp_path)
    log_dir = Path(env["ROADMAP_LOG_DIR"])
    (log_dir / "roadmap_results.jsonl").write_text(
        json.dumps({"ts": "2026-09-13T07:00:00Z", "action": "work",
                    "result": "pr_opened", "engine": "codex", "issue": 10,
                    "pr": 900, "duration_s": 60}) + "\n"
    )
    lock = log_dir / ".roadmap_agent.lock"
    lock.touch()

    # Il lock del giro tenuto da qualcun altro, come durante un giro vero.
    occupato = subprocess.Popen(["flock", str(lock), "-c", "sleep 20"])
    try:
        esito = _giro(env, "--digest", "30")
    finally:
        occupato.terminate()
        occupato.wait(timeout=10)

    assert esito.returncode == 0, esito.stdout + esito.stderr
    assert "Digest roadmap" in esito.stdout
    assert "Un altro giro e' gia' in corso" not in esito.stdout
