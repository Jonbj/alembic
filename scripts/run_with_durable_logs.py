#!/usr/bin/env python3
"""Esegue un servizio duplicandone l'output su log giornalieri persistenti."""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import BinaryIO

DEFAULT_LOG_DIR = Path("/var/log/alembic")
DEFAULT_RETENTION_DAYS = 60
# Tetto per servizio e per giorno: un loop di errori (DNS giu' il 2026-10-02 e
# il 2026-10-12/13, ~3M traceback/giorno da worker-news-stream) ha riempito il
# disco. Oltre il tetto il file riceve una riga di avviso e poi nient'altro fino
# al giorno dopo; stdout (driver json-file, gia' limitato) continua a ricevere.
DEFAULT_MAX_BYTES_PER_DAY = 1024 * 1024 * 1024


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--service", required=True)
    parser.add_argument("--log-dir", type=Path, default=DEFAULT_LOG_DIR)
    parser.add_argument(
        "--retention-days", type=int, default=DEFAULT_RETENTION_DAYS
    )
    parser.add_argument(
        "--max-bytes-per-day", type=int, default=DEFAULT_MAX_BYTES_PER_DAY
    )
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    if args.command[:1] == ["--"]:
        args.command = args.command[1:]
    if not args.command:
        parser.error("manca il comando da eseguire dopo --")
    if args.retention_days < 1:
        parser.error("--retention-days deve essere positivo")
    if args.max_bytes_per_day < 1:
        parser.error("--max-bytes-per-day deve essere positivo")
    if not args.service.replace("-", "").replace("_", "").isalnum():
        parser.error("--service contiene caratteri non validi")
    return args


def _remove_expired_logs(
    log_dir: Path, service: str, retention_days: int, today: date
) -> None:
    cutoff = today - timedelta(days=retention_days)
    prefix = f"{service}-"
    for path in log_dir.glob(f"{service}-*.log"):
        try:
            log_date = date.fromisoformat(path.name[len(prefix) : -len(".log")])
        except ValueError:
            continue
        if log_date < cutoff:
            path.unlink()


def _open_daily_log(log_dir: Path, service: str, day: date) -> BinaryIO:
    return (log_dir / f"{service}-{day.isoformat()}.log").open(
        "ab", buffering=0
    )


class _CappedDailyLog:
    """File giornaliero che smette di crescere oltre `max_bytes`."""

    def __init__(self, log_dir: Path, service: str, day: date, max_bytes: int):
        self._file = _open_daily_log(log_dir, service, day)
        # dopo un riavvio nello stesso giorno il tetto conta anche quanto gia' scritto
        self._written = self._file.tell()
        self._max_bytes = max_bytes
        self._truncated = self._written >= max_bytes

    def write(self, chunk: bytes) -> None:
        if self._truncated:
            return
        room = self._max_bytes - self._written
        if len(chunk) <= room:
            self._file.write(chunk)
            self._written += len(chunk)
            return
        self._file.write(chunk[:room])
        self._file.write(
            f"\n[run_with_durable_logs] tetto di {self._max_bytes} byte/giorno "
            "raggiunto: output successivo di oggi solo su stdout (docker logs)\n"
            .encode()
        )
        self._truncated = True

    def close(self) -> None:
        self._file.close()


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    args.log_dir.mkdir(parents=True, exist_ok=True)

    today = datetime.now(UTC).date()
    _remove_expired_logs(args.log_dir, args.service, args.retention_days, today)
    durable_log = _CappedDailyLog(
        args.log_dir, args.service, today, args.max_bytes_per_day
    )

    child = subprocess.Popen(
        args.command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )

    def forward_signal(signum: int, _frame: object) -> None:
        try:
            os.killpg(child.pid, signum)
        except ProcessLookupError:
            pass

    signal.signal(signal.SIGTERM, forward_signal)
    signal.signal(signal.SIGINT, forward_signal)

    assert child.stdout is not None
    try:
        while chunk := os.read(child.stdout.fileno(), 65536):
            current_day = datetime.now(UTC).date()
            if current_day != today:
                durable_log.close()
                today = current_day
                _remove_expired_logs(
                    args.log_dir, args.service, args.retention_days, today
                )
                durable_log = _CappedDailyLog(
        args.log_dir, args.service, today, args.max_bytes_per_day
    )
            durable_log.write(chunk)
            sys.stdout.buffer.write(chunk)
            sys.stdout.buffer.flush()
    finally:
        durable_log.close()

    returncode = child.wait()
    return returncode if returncode >= 0 else 128 - returncode


if __name__ == "__main__":
    raise SystemExit(main())
