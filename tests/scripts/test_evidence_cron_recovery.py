"""Contratto di recupero per i cron di evidenza (#563 / F-074)."""

from __future__ import annotations

from pathlib import Path
import shlex
import subprocess


ROOT = Path(__file__).resolve().parents[2]
HELPER = ROOT / "scripts" / "_evidence_cron_recovery.sh"


def _source(command: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", "-c", f"source '{HELPER}'; {command}"],
        text=True,
        capture_output=True,
        check=False,
    )


def test_la_firma_quota_claude_reale_e_centralizzata() -> None:
    result = _source(
        "claude_rate_limited \"You've hit your weekly limit · resets 4pm (Europe/Rome)\""
    )

    assert result.returncode == 0, result.stderr


def test_la_firma_session_limit_del_2026_09_14_e_riconosciuta() -> None:
    """#563: il log del run 09-14 termina con la firma verbatim
    `You've hit your session limit · resets 12:20pm (Europe/Rome)` —
    distinta da `weekly limit` e da `5-hour limit`. Senza un caso che la
    fissi nel regex, una rifattorizzazione dell'helper puo' perdere
    silenziosamente la quota piu' frequente in produzione.
    """
    signature = (
        "INFO 2026-09-14 -> 2026-09-14.json | mover 29 (up 9, down 20) | "
        "zero-news 38 | ingressi 4 | chiusure 9\n"
        "Dossier generato: /home/.../dossier/2026-09-14.json\n"
        "ATTENZIONE: ticker senza articoli da almeno cinque sedute: "
        "BP (10 sedute) | BRK.B (7) | COST (5) | ERIC (10) | JD (10) | "
        "MMM (5) | PBR (10) | SAP (10) | SONY (10) | UBS (8) (#511 / F-001)\n"
        "You've hit your session limit · resets 12:20pm (Europe/Rome)\n"
        "FAILED: sessione Claude terminata con codice 1"
    )
    # Il quoting passa per bash -c: serve raddoppiare l'apostrofo interno
    # (la firma contiene "You've") e sfuggire il backslash del middle-dot
    # solo se la shell lo espande — qui il quoting single-e' sufficiente.
    result = _source(f"claude_rate_limited {shlex.quote(signature)}")

    assert result.returncode == 0, result.stderr


def test_il_reset_epoch_della_session_limit_del_2026_09_14_e_nel_futuro() -> None:
    """#563: il parse deve trasformare `resets 12:20pm (Europe/Rome)` in un
    epoch futuro (oggi o domani, dipende dall'orario del run) — non vuoto,
    non passato. Senza questo controllo una regex che matcha il testo ma
    non ne estrae l'orario produce un `sleep 0` e il run muore comunque.
    """
    signature = "You've hit your session limit · resets 12:20pm (Europe/Rome)"
    result = _source(f"_claude_reset_epoch {shlex.quote(signature)}")

    assert result.returncode == 0, result.stderr
    epoch = result.stdout.strip()
    assert epoch, result.stdout
    assert epoch.isdigit(), f"epoch deve essere numerico, ottenuto: {epoch!r}"
    now = int(__import__("time").time())
    # Tolleranza 24h: il test puo' girare a cavallo di mezzanotte quando il
    # reset di oggi e' gia' passato ma `date -d 12:20pm` cade sul giorno
    # dopo — il vincolo reale e' che l'epoch sia parsato.
    assert abs(int(epoch) - now) <= 24 * 3600, (
        f"epoch {epoch} fuori dalla finestra 24h da ora ({now})"
    )


def test_il_reset_orario_gia_trascorso_viene_spostato_a_domani() -> None:
    """#563: un reset espresso come solo orario vale per domani se oggi e' passato."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        mock_date = Path(tmp) / "date"
        mock_date.write_text(
            "#!/usr/bin/env bash\n"
            "if [[ \"$1\" == '-d' && \"$2\" == '12:20pm'* ]]; then echo 100; "
            "elif [[ \"$1\" == '-d' && \"$2\" == 'tomorrow 12:20pm'* ]]; then echo 86500; "
            "elif [[ \"$1\" == '+%s' ]]; then echo 200; "
            "else exit 99; fi"
        )
        mock_date.chmod(0o755)
        result = _source(
            f"PATH={shlex.quote(tmp)}:$PATH; "
            "_claude_reset_epoch \"You've hit your session limit · resets 12:20pm (Europe/Rome)\""
        )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "86500"


def test_la_data_da_recuperare_e_la_piu_vecchia_assente() -> None:
    result = _source(
        "oldest_missing_session '2026-09-09 2026-09-10 2026-09-11' '2026-09-10 2026-09-11'"
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "2026-09-09"


def test_i_tre_script_usano_la_stessa_firma_quota() -> None:
    for name in (
        "daily_alpha_miss_analysis.sh",
        "daily_analysis.sh",
        "roadmap_agent_loop.sh",
    ):
        source = (ROOT / "scripts" / name).read_text()
        assert "_evidence_cron_recovery.sh" in source


def test_i_cron_registrano_l_esito_di_telegram() -> None:
    for name in ("daily_alpha_miss_analysis.sh", "daily_analysis.sh"):
        source = (ROOT / "scripts" / name).read_text()
        assert "HTTP_STATUS" in source
        assert '"ok":true' in source


def test_i_cron_recuperano_un_report_o_ledger_mancante() -> None:
    for name in ("daily_alpha_miss_analysis.sh", "daily_analysis.sh"):
        source = (ROOT / "scripts" / name).read_text()
        assert "oldest_missing_session" in source


def test_run_claude_with_quota_retry_richiamato_due_volte_su_quota_del_2026_09_14() -> None:
    """#563: il cron deve tentare claude una seconda volta quando la prima
    termina con la firma verbatim del 09-14. Il primo tentativo scrive la
    firma quota, il secondo deve avere successo. Senza questo controllo
    l'helper potrebbe "riconoscere" la quota ma skippare il retry (es.
    sleep 0, condizione sempre falsa, return anticipato).
    """
    import tempfile
    import textwrap

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        # Mock claude: contatore file-based, prima esecuzione quota, seconda OK.
        claude_bin = tmp_path / "claude"
        claude_bin.write_text(
            "if [[ ! -f \"$TMPDIR_FLAG\" ]]; then "
            "touch \"$TMPDIR_FLAG\"; "
            "echo \"You've hit your session limit · resets 12:20pm (Europe/Rome)\"; "
            "exit 1; "
            "fi; "
            "echo OK"
        )
        claude_bin.chmod(0o755)

        # Wrapper che azzera l'attesa di _claude_reset_epoch (il vero
        # 12:20pm Europe/Rome oggi/domani e' troppo lento per un test).
        wrapper = tmp_path / "wrap.sh"
        wrapper.write_text(
            textwrap.dedent(
                f"""\
                source {shlex.quote(str(HELPER))}
                export TMPDIR_FLAG={shlex.quote(str(tmp_path / '.first_done'))}
                export PATH={shlex.quote(str(tmp_path) + ':')}:"$PATH"
                _claude_reset_epoch() {{
                    printf '%s\\n' "$(($(date +%s) + 1))"
                }}
                run_claude_with_quota_retry "dummy prompt" "Bash"
                echo "STATUS=$CLAUDE_SESSION_STATUS"
                echo "OUTPUT=$CLAUDE_SESSION_OUTPUT"
                """
            )
        )

        result = subprocess.run(
            ["bash", str(wrapper)],
            text=True,
            capture_output=True,
            check=False,
        )

        assert result.returncode == 0, result.stderr
        assert "riprovo una volta" in result.stdout, result.stdout
        # Il file flag indica che `claude` e' stato invocato almeno una volta.
        assert (tmp_path / ".first_done").exists()
        # Lo status finale deve essere 0 (seconda esecuzione OK) e l'output OK.
        assert "STATUS=0" in result.stdout, result.stdout
        assert "OUTPUT=OK" in result.stdout, result.stdout
