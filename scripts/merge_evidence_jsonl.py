#!/usr/bin/env python3
"""Fonde due ledger JSONL append-only (una riga per giorno) senza perdere righe.

Gemello di ``merge_evidence_findings.py`` per ``market_daily.jsonl`` (#336): la
copia su disco della tree condivisa puo' essere piu' vecchia di main — basta un
``git checkout`` altrui — quindi copiarla sopra il remoto cancellerebbe giorni
gia' pubblicati. Le righe di ``remote`` sono canoniche e restano verbatim; di
``source`` si prendono solo le chiavi che il remoto non ha ancora.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any


class MergeError(ValueError):
    """Il ledger non rispetta il contratto append-only e richiede un operatore."""


def _load_lines(path: Path) -> list[str]:
    # Un file assente vale come vuoto: e' il caso del primo commit di un ledger.
    if not path.exists():
        return []
    try:
        text = path.read_text()
    except OSError as exc:
        raise MergeError(f"{path}: non leggibile: {exc}") from exc
    return [line for line in text.splitlines() if line.strip()]


def _key_of(line: str, key: str, path: Path) -> str:
    try:
        record = json.loads(line)
    except json.JSONDecodeError as exc:
        raise MergeError(f"{path}: riga JSON non valida: {exc}") from exc
    if not isinstance(record, dict) or key not in record:
        raise MergeError(f"{path}: riga senza campo '{key}': {line[:80]}")
    value = record[key]
    if not isinstance(value, str):
        raise MergeError(f"{path}: campo '{key}' non stringa: {value!r}")
    return value


def merge_lines(remote: list[str], source: list[str], key: str) -> list[str]:
    """Righe di ``remote`` in ordine, piu' le sole chiavi nuove di ``source``."""
    remote_path = Path("main/ledger.jsonl")
    source_path = Path("source/ledger.jsonl")
    merged: list[str] = []
    by_key: dict[str, Any] = {}
    for line in remote:
        line_key = _key_of(line, key, remote_path)
        if line_key in by_key:
            raise MergeError(f"main: chiave duplicata {line_key}")
        by_key[line_key] = json.loads(line)
        merged.append(line)

    for line in source:
        line_key = _key_of(line, key, source_path)
        record = json.loads(line)
        existing = by_key.get(line_key)
        if existing is not None:
            # Stessa chiave, contenuto diverso: non e' una riga nuova, e'
            # una riscrittura di evidenza gia' pubblicata.
            if existing != record:
                raise MergeError(
                    f"{line_key}: la riga modifica dati gia' presenti su main"
                )
            continue
        by_key[line_key] = record
        merged.append(line)
    return merged


def _write_atomic(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent, text=True)
    try:
        with os.fdopen(handle, "w") as stream:
            for line in lines:
                stream.write(line + "\n")
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("remote", type=Path, help="ledger corrente da origin/main")
    parser.add_argument("source", type=Path, help="snapshot scritto dal cron")
    parser.add_argument("output", type=Path, help="destinazione del ledger fuso")
    parser.add_argument("--key", default="data", help="campo che identifica la riga")
    args = parser.parse_args()

    try:
        merged = merge_lines(
            _load_lines(args.remote), _load_lines(args.source), args.key
        )
        _write_atomic(args.output, merged)
    except MergeError as exc:
        print(f"RIFIUTO: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
