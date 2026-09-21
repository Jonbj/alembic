"""Contratto di recupero per i cron di evidenza (#563 / F-074)."""

from __future__ import annotations

from pathlib import Path
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
