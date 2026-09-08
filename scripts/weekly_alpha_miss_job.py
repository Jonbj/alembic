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
DISPOSITION_DECISIONS = {"create_issue", "comment_issue", "covered", "no_action", "defer"}
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
AUTOMATED_ISSUE_LABELS = {"alpha-miss", "weekly-findings", "wayfinder:task", "needs-triage"}


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
        GetCalendarRequest(start=as_of - timedelta(days=21), end=as_of - timedelta(days=1))
    )
    return sorted(row.date for row in rows)


def _latest_complete_week(calendar: Sequence[date], as_of: date) -> list[date]:
    completed = [session for session in calendar if session < as_of]
    if not completed:
        raise PreflightError("il calendario non contiene sessioni concluse")
    latest = completed[-1]
    iso_year, iso_week, _ = latest.isocalendar()
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
    manifest = build_preflight_manifest(project_root, args.logs_dir, calendar, args.as_of)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"PREFLIGHT_OK week={manifest['week']} sessions={len(manifest['sessions'])}")
    return 0


def _load_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValidationError(f"{path} deve contenere un oggetto JSON")
    return payload


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

    source_findings: set[str] = set()
    for row in manifest.get("sessions", []):
        if not isinstance(row, dict) or not isinstance(row.get("report"), str):
            raise ValidationError("sessione del manifest priva di report")
        source_path = (project_root / row["report"]).resolve()
        if not source_path.is_relative_to(project_root):
            raise ValidationError(f"report fuori dal progetto: {source_path}")
        source_findings.update(FINDING_RE.findall(source_path.read_text(encoding="utf-8")))

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
        if not isinstance(publication_id, str) or not re.fullmatch(r"W-\d{3}", publication_id):
            raise ValidationError("publication_id non valido")
        if publication_id in publications_by_id:
            raise ValidationError(f"publication_id duplicato: {publication_id}")
        if action not in PUBLICATION_ACTIONS:
            raise ValidationError(f"action non valida per {publication_id}: {action}")
        if not isinstance(source_ids, list) or not source_ids:
            raise ValidationError(f"source_findings mancante per {publication_id}")
        if not all(isinstance(value, str) and value in source_findings for value in source_ids):
            raise ValidationError(f"source_findings non valido per {publication_id}")
        if not isinstance(publication.get("body"), str) or not publication["body"].strip():
            raise ValidationError(f"body mancante per {publication_id}")
        if action == "create_issue":
            labels = publication.get("labels")
            if not isinstance(publication.get("title"), str) or not publication["title"].strip():
                raise ValidationError(f"title mancante per {publication_id}")
            if not isinstance(labels, list) or not all(isinstance(label, str) for label in labels):
                raise ValidationError(f"labels non valide per {publication_id}")
            forbidden = set(labels) & AUTOMATION_FORBIDDEN_LABELS
            if forbidden:
                raise ValidationError(
                    f"label riservate all'operatore per {publication_id}: "
                    + ", ".join(sorted(forbidden))
                )
            missing_labels = AUTOMATED_ISSUE_LABELS - set(labels)
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
            if not isinstance(publication_id, str) or publication_id not in publications_by_id:
                raise ValidationError(f"publication_id mancante o ignoto per {finding_id}")
            publication = publications_by_id[publication_id]
            if publication["action"] != decision or finding_id not in publication["source_findings"]:
                raise ValidationError(f"publication incoerente per {finding_id}")
        elif publication_id is not None:
            raise ValidationError(f"publication_id inatteso per {finding_id}")

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
                print(f"PUBLICATION_SKIPPED {publication_id} issue={exact[0]['number']}")
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
                raise PublicationError(f"output inatteso da gh issue create: {issue_url}") from exc
            issue_data = json.loads(_gh("api", f"repos/{args.repo}/issues/{issue_number}"))
            _gh(
                "api",
                "--method",
                "POST",
                f"repos/{args.repo}/issues/{args.map_issue}/sub_issues",
                "-F",
                f"sub_issue_id={issue_data['id']}",
            )
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
        detail = result.stderr.strip() or result.stdout.strip() or f"exit {result.returncode}"
        raise PublicationError(f"gh {' '.join(arguments[:2])}: {detail}")
    return result.stdout


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    preflight = subparsers.add_parser("preflight")
    preflight.add_argument("--project-root", type=Path, required=True)
    preflight.add_argument("--logs-dir", type=Path, required=True)
    preflight.add_argument("--calendar-file", type=Path)
    preflight.add_argument("--as-of", type=date.fromisoformat, default=date.today())
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
