#!/usr/bin/env python3
"""Fonde due snapshot append-only di ``findings.json`` senza perdere evidenza."""

from __future__ import annotations

import argparse
import copy
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any


class MergeError(ValueError):
    """Il ledger non rispetta il contratto append-only e richiede un operatore."""


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise MergeError(f"{path}: JSON non leggibile: {exc}") from exc
    if not isinstance(value, dict) or not isinstance(value.get("findings"), list):
        raise MergeError(f"{path}: attesi un oggetto con una lista findings")
    return value


def _index_findings(ledger: dict[str, Any], path: Path) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for finding in ledger["findings"]:
        if not isinstance(finding, dict) or not isinstance(finding.get("id"), str):
            raise MergeError(f"{path}: finding senza id stringa")
        finding_id = finding["id"]
        if finding_id in indexed:
            raise MergeError(f"{path}: finding duplicato {finding_id}")
        if not isinstance(finding.get("occorrenze"), list):
            raise MergeError(f"{path}: {finding_id} senza lista occorrenze")
        occurrence_keys: set[tuple[str, str]] = set()
        for occurrence in finding["occorrenze"]:
            key = _occurrence_key(occurrence, path, finding_id)
            if key in occurrence_keys:
                raise MergeError(f"{path}: occorrenza duplicata in {finding_id}: {key}")
            occurrence_keys.add(key)
        indexed[finding_id] = finding
    return indexed


def _occurrence_key(occurrence: Any, path: Path, finding_id: str) -> tuple[str, str]:
    if not isinstance(occurrence, dict):
        raise MergeError(f"{path}: occorrenza non-oggetto in {finding_id}")
    data = occurrence.get("data")
    fonte = occurrence.get("fonte")
    if not isinstance(data, str) or not isinstance(fonte, str):
        raise MergeError(f"{path}: occorrenza di {finding_id} senza data/fonte stringa")
    return data, fonte


def _refresh_derived_fields(finding: dict[str, Any]) -> None:
    costs = [
        occurrence.get("costo_usd")
        for occurrence in finding["occorrenze"]
        if occurrence.get("costo_usd") is not None
    ]
    if any(isinstance(cost, bool) or not isinstance(cost, (int, float)) for cost in costs):
        raise MergeError(f"costo_usd non numerico in {finding['id']}")
    finding["costo_cumulato_usd"] = round(sum(costs), 2)
    finding["occorrenze_non_stimate"] = sum(
        occurrence.get("costo_usd") is None for occurrence in finding["occorrenze"]
    )


def merge_findings(remote: dict[str, Any], source: dict[str, Any]) -> dict[str, Any]:
    """Unisce le sole aggiunte di ``source`` sopra la versione canonica ``remote``."""
    remote_version = remote.get("schema_version")
    source_version = source.get("schema_version")
    if remote_version != source_version:
        raise MergeError(
            f"schema_version incompatibile: main={remote_version!r}, sorgente={source_version!r}"
        )

    merged = copy.deepcopy(remote)
    remote_by_id = _index_findings(merged, Path("main/findings.json"))
    source_by_id = _index_findings(source, Path("source/findings.json"))

    for finding_id, source_finding in source_by_id.items():
        remote_finding = remote_by_id.get(finding_id)
        if remote_finding is None:
            new_finding = copy.deepcopy(source_finding)
            _refresh_derived_fields(new_finding)
            merged["findings"].append(new_finding)
            remote_by_id[finding_id] = new_finding
            continue

        if remote_finding.get("titolo") != source_finding.get("titolo"):
            raise MergeError(
                f"collisione su {finding_id}: il titolo differisce fra main e sorgente"
            )

        occurrences_by_key: dict[tuple[str, str], dict[str, Any]] = {}
        for occurrence in remote_finding["occorrenze"]:
            key = _occurrence_key(occurrence, Path("main/findings.json"), finding_id)
            occurrences_by_key[key] = occurrence

        for occurrence in source_finding["occorrenze"]:
            key = _occurrence_key(occurrence, Path("source/findings.json"), finding_id)
            existing = occurrences_by_key.get(key)
            if existing is not None:
                if existing != occurrence:
                    raise MergeError(
                        f"{finding_id}: l'occorrenza {key} modifica dati gia' presenti su main"
                    )
                continue
            copied = copy.deepcopy(occurrence)
            remote_finding["occorrenze"].append(copied)
            occurrences_by_key[key] = copied

        _refresh_derived_fields(remote_finding)

    next_ids = [remote.get("prossimo_id"), source.get("prossimo_id")]
    if any(isinstance(value, bool) or not isinstance(value, int) for value in next_ids):
        raise MergeError("prossimo_id deve essere intero in entrambi i ledger")
    numeric_ids = []
    for finding_id in remote_by_id:
        match = re.fullmatch(r"F-(\d+)", finding_id)
        if match is None:
            raise MergeError(f"id finding non canonico: {finding_id}")
        numeric_ids.append(int(match.group(1)))
    merged["prossimo_id"] = max(*next_ids, max(numeric_ids, default=0) + 1)
    return merged


def _write_atomic(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent, text=True)
    try:
        with os.fdopen(handle, "w") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("remote", type=Path, help="findings.json corrente da origin/main")
    parser.add_argument("source", type=Path, help="snapshot scritto dal cron")
    parser.add_argument("output", type=Path, help="destinazione del ledger fuso")
    args = parser.parse_args()

    try:
        merged = merge_findings(_load(args.remote), _load(args.source))
        _write_atomic(args.output, merged)
    except MergeError as exc:
        print(f"RIFIUTO: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
