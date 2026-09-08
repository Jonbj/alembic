#!/usr/bin/env python3
"""Deterministic gates for the weekly alpha-miss analysis job."""

from __future__ import annotations

import argparse
from datetime import date, timedelta
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Sequence


SUCCESSFUL_GIT_STATUSES = {"pushed", "nothing_to_commit"}
TARGET_RE = re.compile(r"\(target: (\d{4}-\d{2}-\d{2})\)")
GIT_STATUS_RE = re.compile(r"^GIT_STATUS=(\S+)\s*$", re.MULTILINE)
FINDING_RE = re.compile(r"\[(F-\d{3})\]")
PROVENANCE_RE = re.compile(
    r"<!--\s*weekly-alpha-miss-provenance:\s*(\{.*?\})\s*-->",
    re.DOTALL,
)
DISPOSITION_DECISIONS = {
    "create_issue",
    "comment_issue",
    "covered",
    "no_action",
    "defer",
}
PUBLICATION_ACTIONS = {"create_issue", "comment_issue"}
AUTOMATION_FORBIDDEN_LABELS = {
    "freeze-ok",
    "ready-for-agent",
    "ready-for-human",
    "waiting",
    "tier0",
    "tier1",
    "tier2",
    "tier3",
    "tier4",
    "tier5",
}
AUTOMATED_ISSUE_LABELS = {
    "alpha-miss",
    "weekly-findings",
    "wayfinder:task",
    "needs-triage",
}


class PreflightError(RuntimeError):
    """The weekly input set is incomplete or cannot be trusted."""


class ValidationError(RuntimeError):
    """The model draft is incomplete or violates the publication contract."""


class PublicationError(RuntimeError):
    """Publication cannot safely proceed."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _calendar_from_file(path: Path) -> list[date]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    values = [row if isinstance(row, str) else row["date"] for row in payload]
    return sorted(date.fromisoformat(value) for value in values)


def _calendar_from_alpaca(as_of: date) -> list[date]:
    from alpaca.trading.client import TradingClient
    from alpaca.trading.requests import GetCalendarRequest

    client = TradingClient(
        os.environ["ALPACA_API_KEY"],
        os.environ["ALPACA_SECRET_KEY"],
        paper=True,
    )
    rows = client.get_calendar(
        GetCalendarRequest(
            start=as_of - timedelta(days=21), end=as_of - timedelta(days=1)
        )
    )
    return sorted(row.date for row in rows)


def _latest_complete_week(calendar: Sequence[date], as_of: date) -> list[date]:
    completed = [session for session in calendar if session < as_of]
    if not completed:
        raise PreflightError("il calendario non contiene sessioni concluse")
    latest = completed[-1]
    iso_year, iso_week, _ = latest.isocalendar()
    if as_of.isocalendar()[:2] == (iso_year, iso_week):
        raise PreflightError(
            "settimana target non ancora conclusa; attendere la settimana ISO successiva"
        )
    sessions = [
        session
        for session in completed
        if session.isocalendar()[:2] == (iso_year, iso_week)
    ]
    if not sessions:
        raise PreflightError("nessuna sessione nella settimana target")
    return sessions


def _successful_log(logs_dir: Path, session: str) -> tuple[Path, str] | None:
    for path in sorted(logs_dir.glob("alpha_miss_analysis_*.log"), reverse=True):
        text = path.read_text(encoding="utf-8", errors="replace")
        target = TARGET_RE.search(text)
        statuses = GIT_STATUS_RE.findall(text)
        if target and target.group(1) == session and statuses:
            status = statuses[-1]
            if status in SUCCESSFUL_GIT_STATUSES:
                return path, status
    return None


def build_preflight_manifest(
    project_root: Path,
    logs_dir: Path,
    calendar: Sequence[date],
    as_of: date,
) -> dict[str, object]:
    sessions = _latest_complete_week(calendar, as_of)
    iso_year, iso_week, _ = sessions[-1].isocalendar()
    rows: list[dict[str, object]] = []
    missing: list[str] = []

    for session_date in sessions:
        session = session_date.isoformat()
        report = project_root / "docs" / f"ALPHA_MISS_REPORT_{session}.md"
        dossier = project_root / "docs" / "evidence" / "dossier" / f"{session}.json"
        log = _successful_log(logs_dir, session)
        if not report.is_file():
            missing.append(f"{session}: report {report}")
        if not dossier.is_file():
            missing.append(f"{session}: dossier {dossier}")
        if log is None:
            missing.append(f"{session}: log alpha-miss riuscito")
        if not report.is_file() or not dossier.is_file() or log is None:
            continue
        log_path, log_status = log
        rows.append(
            {
                "session": session,
                "report": str(report.relative_to(project_root)),
                "report_sha256": _sha256(report),
                "dossier": str(dossier.relative_to(project_root)),
                "dossier_sha256": _sha256(dossier),
                "log": str(log_path.resolve()),
                "log_sha256": _sha256(log_path),
                "log_status": log_status,
            }
        )

    if missing:
        raise PreflightError("input settimanali incompleti:\n- " + "\n- ".join(missing))

    return {
        "schema_version": 1,
        "week": f"{iso_year}-W{iso_week:02d}",
        "as_of": as_of.isoformat(),
        "sessions": rows,
    }


def _preflight(args: argparse.Namespace) -> int:
    # Un manifest appartiene a un singolo tentativo. Se questo giro fallisce,
    # il chiamante non deve poter consumare per errore l'ultimo PASS rimasto.
    args.output.unlink(missing_ok=True)
    project_root = args.project_root.resolve()
    calendar = (
        _calendar_from_file(args.calendar_file)
        if args.calendar_file
        else _calendar_from_alpaca(args.as_of)
    )
    manifest = build_preflight_manifest(
        project_root, args.logs_dir, calendar, args.as_of
    )
    # Snapshot e prompt sono input dell'analisi tanto quanto report e dossier:
    # congelarli qui permette di attribuire ogni conclusione alla versione letta.
    json.loads(args.issues_snapshot.read_text(encoding="utf-8"))
    manifest.update(
        {
            "job_version": 1,
            "git_commit": args.git_commit,
            "model": args.model,
            "prompt": str(args.prompt.resolve()),
            "prompt_sha256": _sha256(args.prompt),
            "issues_snapshot": str(args.issues_snapshot.resolve()),
            "issues_snapshot_sha256": _sha256(args.issues_snapshot),
        }
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"PREFLIGHT_OK week={manifest['week']} sessions={len(manifest['sessions'])}")
    return 0


def _week(args: argparse.Namespace) -> int:
    calendar = (
        _calendar_from_file(args.calendar_file)
        if args.calendar_file
        else _calendar_from_alpaca(args.as_of)
    )
    sessions = _latest_complete_week(calendar, args.as_of)
    iso_year, iso_week, _ = sessions[-1].isocalendar()
    print(f"{iso_year}-W{iso_week:02d}")
    return 0


def _load_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValidationError(f"{path} deve contenere un oggetto JSON")
    return payload


def _validate_report_provenance(manifest: dict[str, object], report_text: str) -> None:
    """Verify the machine-readable provenance copied from a production manifest."""
    if manifest.get("job_version") is None:
        # Compatibility for reports generated before the versioned weekly job.
        return
    match = PROVENANCE_RE.search(report_text)
    if not match:
        raise ValidationError("blocco di provenienza mancante nel report")
    try:
        provenance = json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        raise ValidationError("blocco di provenienza JSON non valido") from exc
    if not isinstance(provenance, dict):
        raise ValidationError("blocco di provenienza non strutturato")

    sessions = manifest.get("sessions")
    if not isinstance(sessions, list) or not all(
        isinstance(row, dict) for row in sessions
    ):
        raise ValidationError("sessioni non valide nel manifest")
    expected = {
        "job_version": manifest.get("job_version"),
        "week": manifest.get("week"),
        "git_commit": manifest.get("git_commit"),
        "model": manifest.get("model"),
        "prompt_sha256": manifest.get("prompt_sha256"),
        "sessions": [row.get("session") for row in sessions],
    }
    mismatches = [
        key for key, value in expected.items() if provenance.get(key) != value
    ]
    if mismatches:
        raise ValidationError(
            "provenienza del report non coincide col manifest: "
            + ", ".join(sorted(mismatches))
        )


def _manifest_path(
    project_root: Path,
    raw_path: object,
    *,
    field: str,
    allow_external: bool = False,
) -> Path:
    if not isinstance(raw_path, str):
        raise ValidationError(f"{field} mancante nel manifest")
    path = Path(raw_path)
    resolved = path.resolve() if path.is_absolute() else (project_root / path).resolve()
    if not allow_external and not resolved.is_relative_to(project_root):
        raise ValidationError(f"{field} fuori dal progetto: {resolved}")
    return resolved


def _validate_manifest_inputs(project_root: Path, manifest: dict[str, object]) -> None:
    """Re-hash every frozen input after the model session and before publication."""
    sessions = manifest.get("sessions")
    if not isinstance(sessions, list) or not all(
        isinstance(row, dict) for row in sessions
    ):
        raise ValidationError("sessioni non valide nel manifest")

    checks: list[tuple[str, Path, object]] = []
    for row in sessions:
        session = row.get("session", "UNKNOWN")
        for path_key, hash_key, allow_external in (
            ("report", "report_sha256", False),
            ("dossier", "dossier_sha256", False),
            ("log", "log_sha256", True),
        ):
            checks.append(
                (
                    f"{session}:{hash_key}",
                    _manifest_path(
                        project_root,
                        row.get(path_key),
                        field=f"{session}:{path_key}",
                        allow_external=allow_external,
                    ),
                    row.get(hash_key),
                )
            )
    for path_key, hash_key in (
        ("prompt", "prompt_sha256"),
        ("issues_snapshot", "issues_snapshot_sha256"),
    ):
        checks.append(
            (
                hash_key,
                _manifest_path(project_root, manifest.get(path_key), field=path_key),
                manifest.get(hash_key),
            )
        )

    mismatches: list[str] = []
    for label, path, expected in checks:
        if (
            not isinstance(expected, str)
            or not path.is_file()
            or _sha256(path) != expected
        ):
            mismatches.append(label)
    if mismatches:
        raise ValidationError(
            "input modificati o non verificabili dopo il preflight: "
            + ", ".join(sorted(mismatches))
        )


def _validate(args: argparse.Namespace) -> int:
    args.token.unlink(missing_ok=True)
    project_root = args.project_root.resolve()
    manifest = _load_json(args.manifest)
    plan = _load_json(args.plan)
    report_text = args.report.read_text(encoding="utf-8")

    if manifest.get("schema_version") != 1 or plan.get("schema_version") != 1:
        raise ValidationError("schema_version non supportata")
    if manifest.get("week") != plan.get("week"):
        raise ValidationError("week del manifest e del piano non coincidono")
    if manifest.get("job_version") is not None:
        _validate_manifest_inputs(project_root, manifest)
    _validate_report_provenance(manifest, report_text)

    source_findings: set[str] = set()
    for row in manifest.get("sessions", []):
        if not isinstance(row, dict) or not isinstance(row.get("report"), str):
            raise ValidationError("sessione del manifest priva di report")
        source_path = (project_root / row["report"]).resolve()
        if not source_path.is_relative_to(project_root):
            raise ValidationError(f"report fuori dal progetto: {source_path}")
        source_findings.update(
            FINDING_RE.findall(source_path.read_text(encoding="utf-8"))
        )

    dispositions = plan.get("dispositions")
    if not isinstance(dispositions, list):
        raise ValidationError("dispositions deve essere una lista")
    disposition_ids: list[str] = []
    dispositions_by_id: dict[str, dict[str, object]] = {}
    for row in dispositions:
        if not isinstance(row, dict):
            raise ValidationError("disposition non strutturata")
        finding_id = row.get("finding_id")
        decision = row.get("decision")
        reason = row.get("reason")
        if not isinstance(finding_id, str) or not re.fullmatch(r"F-\d{3}", finding_id):
            raise ValidationError("finding_id non valido nel piano")
        if decision not in DISPOSITION_DECISIONS:
            raise ValidationError(f"decision non valida per {finding_id}: {decision}")
        if not isinstance(reason, str) or not reason.strip():
            raise ValidationError(f"reason mancante per {finding_id}")
        disposition_ids.append(finding_id)
        dispositions_by_id[finding_id] = row

    if len(disposition_ids) != len(set(disposition_ids)):
        raise ValidationError("finding_id duplicato nelle dispositions")
    missing = source_findings - set(disposition_ids)
    extra = set(disposition_ids) - source_findings
    if missing or extra:
        details = []
        if missing:
            details.append("senza disposizione: " + ", ".join(sorted(missing)))
        if extra:
            details.append("non presenti nelle fonti: " + ", ".join(sorted(extra)))
        raise ValidationError("; ".join(details))

    report_findings = set(FINDING_RE.findall(report_text))
    missing_from_report = source_findings - report_findings
    if missing_from_report:
        raise ValidationError(
            "finding assenti dalla disposition matrix del report: "
            + ", ".join(sorted(missing_from_report))
        )

    publications = plan.get("publications")
    if not isinstance(publications, list):
        raise ValidationError("publications deve essere una lista")
    publications_by_id: dict[str, dict[str, object]] = {}
    for publication in publications:
        if not isinstance(publication, dict):
            raise ValidationError("publication non strutturata")
        publication_id = publication.get("publication_id")
        action = publication.get("action")
        source_ids = publication.get("source_findings")
        if not isinstance(publication_id, str) or not re.fullmatch(
            r"W-\d{3}", publication_id
        ):
            raise ValidationError("publication_id non valido")
        if publication_id in publications_by_id:
            raise ValidationError(f"publication_id duplicato: {publication_id}")
        if action not in PUBLICATION_ACTIONS:
            raise ValidationError(f"action non valida per {publication_id}: {action}")
        if not isinstance(source_ids, list) or not source_ids:
            raise ValidationError(f"source_findings mancante per {publication_id}")
        if not all(
            isinstance(value, str) and value in source_findings for value in source_ids
        ):
            raise ValidationError(f"source_findings non valido per {publication_id}")
        if (
            not isinstance(publication.get("body"), str)
            or not publication["body"].strip()
        ):
            raise ValidationError(f"body mancante per {publication_id}")
        if action == "create_issue":
            labels = publication.get("labels")
            if (
                not isinstance(publication.get("title"), str)
                or not publication["title"].strip()
            ):
                raise ValidationError(f"title mancante per {publication_id}")
            if not isinstance(labels, list) or not all(
                isinstance(label, str) for label in labels
            ):
                raise ValidationError(f"labels non valide per {publication_id}")
            normalized_labels = {label.casefold() for label in labels}
            forbidden = {
                label
                for label in labels
                if label.casefold() in AUTOMATION_FORBIDDEN_LABELS
                or label.casefold().startswith("tier")
            }
            if forbidden:
                raise ValidationError(
                    f"label riservate all'operatore per {publication_id}: "
                    + ", ".join(sorted(forbidden))
                )
            missing_labels = AUTOMATED_ISSUE_LABELS - normalized_labels
            if missing_labels:
                raise ValidationError(
                    f"label obbligatorie mancanti per {publication_id}: "
                    + ", ".join(sorted(missing_labels))
                )
        elif not isinstance(publication.get("issue_number"), int):
            raise ValidationError(f"issue_number mancante per {publication_id}")
        publications_by_id[publication_id] = publication

    for finding_id, disposition in dispositions_by_id.items():
        decision = disposition["decision"]
        publication_id = disposition.get("publication_id")
        if decision in PUBLICATION_ACTIONS:
            if (
                not isinstance(publication_id, str)
                or publication_id not in publications_by_id
            ):
                raise ValidationError(
                    f"publication_id mancante o ignoto per {finding_id}"
                )
            publication = publications_by_id[publication_id]
            if (
                publication["action"] != decision
                or finding_id not in publication["source_findings"]
            ):
                raise ValidationError(f"publication incoerente per {finding_id}")
        elif publication_id is not None:
            raise ValidationError(f"publication_id inatteso per {finding_id}")

    for publication_id, publication in publications_by_id.items():
        for finding_id in publication["source_findings"]:
            disposition = dispositions_by_id[finding_id]
            if (
                disposition["decision"] != publication["action"]
                or disposition.get("publication_id") != publication_id
            ):
                raise ValidationError(
                    f"pubblicazione {publication_id} non collegata alla disposizione "
                    f"di {finding_id}"
                )

    token = {
        "schema_version": 1,
        "week": manifest["week"],
        "manifest_sha256": _sha256(args.manifest),
        "plan_sha256": _sha256(args.plan),
        "report_sha256": _sha256(args.report),
    }
    args.token.parent.mkdir(parents=True, exist_ok=True)
    args.token.write_text(json.dumps(token, sort_keys=True) + "\n", encoding="utf-8")
    print(f"VALIDATION_OK week={manifest['week']} findings={len(source_findings)}")
    return 0


def _publish(args: argparse.Namespace) -> int:
    token = _load_json(args.token)
    expected = {
        "manifest_sha256": _sha256(args.manifest),
        "plan_sha256": _sha256(args.plan),
        "report_sha256": _sha256(args.report),
    }
    changed = [name for name, digest in expected.items() if token.get(name) != digest]
    if changed:
        raise PublicationError(
            "artefatto cambiato dopo la validazione: " + ", ".join(sorted(changed))
        )

    plan = _load_json(args.plan)
    publications = plan.get("publications", [])
    if args.dry_run:
        print(f"PUBLICATION_DRY_RUN repo={args.repo} items={len(publications)}")
        return 0

    created = 0
    commented = 0
    skipped = 0
    for publication in publications:
        publication_id = publication["publication_id"]
        marker = f"<!-- weekly-alpha-miss:{token['week']}:{publication_id} -->"
        if publication["action"] == "create_issue":
            existing_raw = _gh(
                "issue",
                "list",
                "--repo",
                args.repo,
                "--state",
                "all",
                "--search",
                f'"{marker}" in:body',
                "--json",
                "number,body",
                "--limit",
                "100",
            )
            existing = json.loads(existing_raw or "[]")
            exact = [row for row in existing if marker in (row.get("body") or "")]
            if exact:
                issue_number = exact[0]["number"]
                _ensure_map_child(args.repo, args.map_issue, issue_number)
                print(f"PUBLICATION_SKIPPED {publication_id} issue={issue_number}")
                skipped += 1
                continue
            body = f"Part of #{args.map_issue}.\n\n{marker}\n\n{publication['body']}"
            command = [
                "issue",
                "create",
                "--repo",
                args.repo,
                "--title",
                publication["title"],
                "--body",
                body,
            ]
            for label in publication["labels"]:
                command.extend(("--label", label))
            issue_url = _gh(*command).strip().splitlines()[-1]
            try:
                issue_number = int(issue_url.rstrip("/").rsplit("/", 1)[-1])
            except (IndexError, ValueError) as exc:
                raise PublicationError(
                    f"output inatteso da gh issue create: {issue_url}"
                ) from exc
            _ensure_map_child(args.repo, args.map_issue, issue_number)
            print(f"PUBLICATION_CREATED {publication_id} issue={issue_number}")
            created += 1
        else:
            issue_number = publication["issue_number"]
            issue_raw = _gh(
                "issue",
                "view",
                str(issue_number),
                "--repo",
                args.repo,
                "--json",
                "comments",
            )
            comments = json.loads(issue_raw).get("comments", [])
            if any(marker in (row.get("body") or "") for row in comments):
                print(f"PUBLICATION_SKIPPED {publication_id} issue={issue_number}")
                skipped += 1
                continue
            _gh(
                "issue",
                "comment",
                str(issue_number),
                "--repo",
                args.repo,
                "--body",
                f"{marker}\n\n{publication['body']}",
            )
            print(f"PUBLICATION_COMMENTED {publication_id} issue={issue_number}")
            commented += 1

    print(f"PUBLICATION_OK created={created} commented={commented} skipped={skipped}")
    return 0


def _gh(*arguments: str) -> str:
    result = subprocess.run(
        ["gh", *arguments],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        detail = (
            result.stderr.strip()
            or result.stdout.strip()
            or f"exit {result.returncode}"
        )
        raise PublicationError(f"gh {' '.join(arguments[:2])}: {detail}")
    return result.stdout


def _ensure_map_child(repo: str, map_issue: int, issue_number: int) -> None:
    """Attach a publication to the roadmap, including after a partial retry."""
    child_numbers = _gh(
        "api",
        "--paginate",
        f"repos/{repo}/issues/{map_issue}/sub_issues",
        "--jq",
        ".[].number",
    )
    if str(issue_number) in child_numbers.splitlines():
        return
    issue_data = json.loads(_gh("api", f"repos/{repo}/issues/{issue_number}"))
    _gh(
        "api",
        "--method",
        "POST",
        f"repos/{repo}/issues/{map_issue}/sub_issues",
        "-F",
        f"sub_issue_id={issue_data['id']}",
    )


def _record_pilot(args: argparse.Namespace) -> int:
    issue_raw = _gh(
        "issue",
        "view",
        str(args.issue),
        "--repo",
        args.repo,
        "--json",
        "comments",
    )
    comments = json.loads(issue_raw).get("comments", [])
    bodies = [row.get("body") or "" for row in comments]
    marker = f"<!-- weekly-alpha-miss-pilot:{args.week} -->"
    weeks = {
        match
        for body in bodies
        for match in re.findall(r"weekly-alpha-miss-pilot:(\d{4}-W\d{2})", body)
    }
    if marker not in "\n".join(bodies):
        _gh(
            "issue",
            "comment",
            str(args.issue),
            "--repo",
            args.repo,
            "--body",
            (
                f"{marker}\n\n"
                f"Campione appaiato `{args.week}` prodotto.\n\n"
                f"- PR: {args.pr_url}\n"
                f"- Baseline: `{args.baseline_path}`\n"
                f"- Value-first: `{args.challenger_path}`"
            ),
        )
        weeks.add(args.week)
    if len(weeks) >= 2:
        _gh(
            "issue",
            "edit",
            str(args.issue),
            "--repo",
            args.repo,
            "--remove-label",
            "waiting",
            "--add-label",
            "ready-for-agent",
        )
        print(f"PILOT_READY samples={len(weeks)} issue={args.issue}")
    else:
        print(f"PILOT_WAITING samples={len(weeks)} issue={args.issue}")
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    week = subparsers.add_parser("week")
    week.add_argument("--calendar-file", type=Path)
    week.add_argument("--as-of", type=date.fromisoformat, default=date.today())
    week.set_defaults(handler=_week)
    preflight = subparsers.add_parser("preflight")
    preflight.add_argument("--project-root", type=Path, required=True)
    preflight.add_argument("--logs-dir", type=Path, required=True)
    preflight.add_argument("--calendar-file", type=Path)
    preflight.add_argument("--as-of", type=date.fromisoformat, default=date.today())
    preflight.add_argument("--prompt", type=Path, required=True)
    preflight.add_argument("--issues-snapshot", type=Path, required=True)
    preflight.add_argument("--git-commit", required=True)
    preflight.add_argument("--model", required=True)
    preflight.add_argument("--output", type=Path, required=True)
    preflight.set_defaults(handler=_preflight)
    validate = subparsers.add_parser("validate")
    validate.add_argument("--project-root", type=Path, required=True)
    validate.add_argument("--manifest", type=Path, required=True)
    validate.add_argument("--plan", type=Path, required=True)
    validate.add_argument("--report", type=Path, required=True)
    validate.add_argument("--token", type=Path, required=True)
    validate.set_defaults(handler=_validate)
    publish = subparsers.add_parser("publish")
    publish.add_argument("--manifest", type=Path, required=True)
    publish.add_argument("--plan", type=Path, required=True)
    publish.add_argument("--report", type=Path, required=True)
    publish.add_argument("--token", type=Path, required=True)
    publish.add_argument("--repo", required=True)
    publish.add_argument("--map-issue", type=int, default=21)
    publish.add_argument("--dry-run", action="store_true")
    publish.set_defaults(handler=_publish)
    record_pilot = subparsers.add_parser("record-pilot")
    record_pilot.add_argument("--repo", required=True)
    record_pilot.add_argument("--issue", type=int, default=515)
    record_pilot.add_argument("--week", required=True)
    record_pilot.add_argument("--pr-url", required=True)
    record_pilot.add_argument("--baseline-path", required=True)
    record_pilot.add_argument("--challenger-path", required=True)
    record_pilot.set_defaults(handler=_record_pilot)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        return args.handler(args)
    except PublicationError as exc:
        print(f"PUBLICATION_FAILED: {exc}", file=sys.stderr)
        return 5
    except ValidationError as exc:
        print(f"VALIDATION_FAILED: {exc}", file=sys.stderr)
        return 4
    except (KeyError, OSError, ValueError, PreflightError) as exc:
        print(f"{args.command.upper()}_FAILED: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
