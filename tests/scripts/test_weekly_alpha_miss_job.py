"""Contratto CLI del job weekly alpha-miss (#514)."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "weekly_alpha_miss_job.py"


def _write_session(project: Path, session: str, *, git_status: str = "pushed") -> None:
    (project / "docs" / "evidence" / "dossier").mkdir(parents=True, exist_ok=True)
    (project / "logs").mkdir(parents=True, exist_ok=True)
    (project / "docs" / f"ALPHA_MISS_REPORT_{session}.md").write_text(
        f"# Alpha miss {session}\n\n[F-001] evidenza\n"
    )
    (project / "docs" / "evidence" / "dossier" / f"{session}.json").write_text(
        '{"schema_version": "test"}\n'
    )
    (project / "logs" / f"alpha_miss_analysis_run-{session}.log").write_text(
        f"=== Alembic Alpha-Miss Analysis run (target: {session}) ===\n"
        f"GIT_STATUS={git_status}\n"
    )


def _run_preflight(
    project: Path,
    calendar: list[str],
    *,
    as_of: str = "2026-09-07",
) -> subprocess.CompletedProcess[str]:
    calendar_file = project / "calendar.json"
    calendar_file.write_text(json.dumps(calendar))
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "preflight",
            "--project-root",
            str(project),
            "--logs-dir",
            str(project / "logs"),
            "--calendar-file",
            str(calendar_file),
            "--as-of",
            as_of,
            "--output",
            str(project / "manifest.json"),
        ],
        text=True,
        capture_output=True,
        check=False,
    )


def _run_validate(
    project: Path,
    *,
    manifest: dict[str, object],
    plan: dict[str, object],
    report: str,
) -> subprocess.CompletedProcess[str]:
    manifest_file = project / "manifest.json"
    plan_file = project / "publication-plan.json"
    report_file = project / "weekly.md"
    token_file = project / "publication.token"
    manifest_file.write_text(json.dumps(manifest))
    plan_file.write_text(json.dumps(plan))
    report_file.write_text(report)
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "validate",
            "--project-root",
            str(project),
            "--manifest",
            str(manifest_file),
            "--plan",
            str(plan_file),
            "--report",
            str(report_file),
            "--token",
            str(token_file),
        ],
        text=True,
        capture_output=True,
        check=False,
    )


def _valid_plan() -> dict[str, object]:
    return {
        "schema_version": 1,
        "week": "2026-W36",
        "dispositions": [
            {
                "finding_id": "F-001",
                "decision": "create_issue",
                "reason": "Pattern nuovo e materiale.",
                "publication_id": "W-001",
            }
        ],
        "publications": [
            {
                "publication_id": "W-001",
                "action": "create_issue",
                "source_findings": ["F-001"],
                "title": "Nuova opportunità",
                "body": "## Evidence\n\nEvidenza e prossimo test.",
                "labels": [
                    "alpha-miss",
                    "weekly-findings",
                    "wayfinder:task",
                    "needs-triage",
                ],
            }
        ],
    }


def test_preflight_materializza_tutte_le_sessioni_della_settimana(tmp_path: Path):
    project = tmp_path / "project"
    sessions = [
        "2026-08-31",
        "2026-09-01",
        "2026-09-02",
        "2026-09-03",
        "2026-09-04",
    ]
    for session in sessions:
        _write_session(project, session)

    result = _run_preflight(project, sessions)

    assert result.returncode == 0, result.stderr
    manifest = json.loads((project / "manifest.json").read_text())
    assert manifest["schema_version"] == 1
    assert manifest["week"] == "2026-W36"
    assert [row["session"] for row in manifest["sessions"]] == sessions
    assert all(row["report_sha256"] for row in manifest["sessions"])
    assert all(row["dossier_sha256"] for row in manifest["sessions"])
    assert all(row["log_status"] == "pushed" for row in manifest["sessions"])


def test_preflight_accetta_una_settimana_abbreviata_dal_calendario(tmp_path: Path):
    project = tmp_path / "project"
    sessions = ["2026-06-29", "2026-06-30", "2026-07-01", "2026-07-02"]
    for session in sessions:
        _write_session(project, session, git_status="nothing_to_commit")

    result = _run_preflight(project, sessions, as_of="2026-07-06")

    assert result.returncode == 0, result.stderr
    manifest = json.loads((project / "manifest.json").read_text())
    assert manifest["week"] == "2026-W27"
    assert [row["session"] for row in manifest["sessions"]] == sessions


def test_preflight_mancante_fallisce_e_non_lascia_un_manifest_stale(tmp_path: Path):
    project = tmp_path / "project"
    sessions = ["2026-08-31", "2026-09-01", "2026-09-02", "2026-09-03", "2026-09-04"]
    for session in sessions:
        _write_session(project, session)
    (project / "docs" / "ALPHA_MISS_REPORT_2026-09-04.md").unlink()
    (project / "manifest.json").write_text('{"week": "STALE"}\n')

    result = _run_preflight(project, sessions)

    assert result.returncode == 3
    assert "2026-09-04: report" in result.stderr
    assert not (project / "manifest.json").exists()


def test_validate_rifiuta_un_finding_sorgente_senza_disposizione(tmp_path: Path):
    project = tmp_path / "project"
    (project / "docs").mkdir(parents=True)
    source = project / "docs" / "ALPHA_MISS_REPORT_2026-09-01.md"
    source.write_text("[F-001] coperto\n[F-008] dimenticato\n")
    manifest = {
        "schema_version": 1,
        "week": "2026-W36",
        "sessions": [{"session": "2026-09-01", "report": str(source.relative_to(project))}],
    }
    plan = {
        "schema_version": 1,
        "week": "2026-W36",
        "dispositions": [
            {
                "finding_id": "F-001",
                "decision": "no_action",
                "reason": "Già coperto.",
            }
        ],
        "publications": [],
    }

    result = _run_validate(project, manifest=manifest, plan=plan, report="# Weekly\n[F-001]\n")

    assert result.returncode == 4
    assert "F-008" in result.stderr
    assert not (project / "publication.token").exists()


def test_validate_vieta_al_job_di_auto_autorizzare_il_loop(tmp_path: Path):
    project = tmp_path / "project"
    (project / "docs").mkdir(parents=True)
    source = project / "docs" / "ALPHA_MISS_REPORT_2026-09-01.md"
    source.write_text("[F-001] nuovo pattern\n")
    manifest = {
        "schema_version": 1,
        "week": "2026-W36",
        "sessions": [{"session": "2026-09-01", "report": str(source.relative_to(project))}],
    }
    plan = {
        "schema_version": 1,
        "week": "2026-W36",
        "dispositions": [
            {
                "finding_id": "F-001",
                "decision": "create_issue",
                "reason": "Pattern nuovo e materiale.",
                "publication_id": "W-001",
            }
        ],
        "publications": [
            {
                "publication_id": "W-001",
                "action": "create_issue",
                "source_findings": ["F-001"],
                "title": "Nuova opportunità",
                "body": "Evidenza e prossimo test.",
                "labels": ["alpha-miss", "weekly-findings", "wayfinder:task", "freeze-ok"],
            }
        ],
    }

    result = _run_validate(project, manifest=manifest, plan=plan, report="# Weekly\n[F-001]\n")

    assert result.returncode == 4
    assert "freeze-ok" in result.stderr
    assert not (project / "publication.token").exists()


def test_publish_rifiuta_un_piano_modificato_dopo_la_validazione(tmp_path: Path):
    project = tmp_path / "project"
    (project / "docs").mkdir(parents=True)
    source = project / "docs" / "ALPHA_MISS_REPORT_2026-09-01.md"
    source.write_text("[F-001] nuovo pattern\n")
    manifest = {
        "schema_version": 1,
        "week": "2026-W36",
        "sessions": [{"session": "2026-09-01", "report": str(source.relative_to(project))}],
    }
    plan = _valid_plan()
    validation = _run_validate(
        project,
        manifest=manifest,
        plan=plan,
        report="# Weekly\n[F-001]\n",
    )
    assert validation.returncode == 0, validation.stderr
    plan["publications"][0]["title"] = "Titolo cambiato dopo il PASS"  # type: ignore[index]
    (project / "publication-plan.json").write_text(json.dumps(plan))

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    capture = tmp_path / "gh-called"
    fake_gh = bin_dir / "gh"
    fake_gh.write_text(f"#!/usr/bin/env bash\ntouch {capture}\nexit 0\n")
    fake_gh.chmod(0o755)
    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "publish",
            "--manifest",
            str(project / "manifest.json"),
            "--plan",
            str(project / "publication-plan.json"),
            "--report",
            str(project / "weekly.md"),
            "--token",
            str(project / "publication.token"),
            "--repo",
            "Jonbj/alembic",
        ],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 5
    assert "cambiato dopo la validazione" in result.stderr
    assert not capture.exists()


def test_publish_crea_issue_idempotente_e_la_collega_come_child(tmp_path: Path):
    project = tmp_path / "project"
    (project / "docs").mkdir(parents=True)
    source = project / "docs" / "ALPHA_MISS_REPORT_2026-09-01.md"
    source.write_text("[F-001] nuovo pattern\n")
    manifest = {
        "schema_version": 1,
        "week": "2026-W36",
        "sessions": [{"session": "2026-09-01", "report": str(source.relative_to(project))}],
    }
    validation = _run_validate(
        project,
        manifest=manifest,
        plan=_valid_plan(),
        report="# Weekly\n[F-001]\n",
    )
    assert validation.returncode == 0, validation.stderr

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    capture = tmp_path / "gh.log"
    fake_gh = bin_dir / "gh"
    fake_gh.write_text(
        "#!/usr/bin/env bash\n"
        "printf '%s\\n' \"$*\" >> \"$GH_CAPTURE\"\n"
        "if [[ \"$1 $2\" == 'issue list' ]]; then printf '[]\\n'; exit 0; fi\n"
        "if [[ \"$1 $2\" == 'issue create' ]]; then "
        "printf 'https://github.com/Jonbj/alembic/issues/900\\n'; exit 0; fi\n"
        "if [[ \"$1\" == 'api' && \"$2\" == 'repos/Jonbj/alembic/issues/900' ]]; then "
        "printf '{\"id\":1900}\\n'; exit 0; fi\n"
        "if [[ \"$1 $2\" == 'api --method' ]]; then printf '{}\\n'; exit 0; fi\n"
        "exit 9\n"
    )
    fake_gh.chmod(0o755)
    env = os.environ.copy()
    env.update({"PATH": f"{bin_dir}:{env['PATH']}", "GH_CAPTURE": str(capture)})
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "publish",
            "--manifest",
            str(project / "manifest.json"),
            "--plan",
            str(project / "publication-plan.json"),
            "--report",
            str(project / "weekly.md"),
            "--token",
            str(project / "publication.token"),
            "--repo",
            "Jonbj/alembic",
        ],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    calls = capture.read_text()
    assert "issue list" in calls
    assert "issue create" in calls
    assert "weekly-alpha-miss:2026-W36:W-001" in calls
    assert "needs-triage" in calls
    assert "freeze-ok" not in calls
    assert "issues/21/sub_issues" in calls
