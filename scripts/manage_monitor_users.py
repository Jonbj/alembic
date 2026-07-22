#!/usr/bin/env python3
"""Operator CLI for managing mobile monitor users, devices, and sessions.

Commands:
    create          Create a monitor user and a default device.
    disable         Disable a monitor user (blocks login + refresh).
    enable          Re-enable a monitor user.
    revoke-session  Revoke a single session by id.
    revoke-all      Revoke all active sessions for a user.
    revoke-device   Revoke a device and all its sessions.

Output is intentionally redacted: no refresh tokens, hashes, or passwords are
printed.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import uuid
from uuid import UUID

import asyncpg
import bcrypt

from src.config import config
from src.mobile_monitoring.store import MonitorStore


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Manage mobile monitor users, devices, and sessions"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    create = sub.add_parser("create", help="Create a monitor user and device")
    create.add_argument("--username", required=True)
    create.add_argument("--password", required=True)
    create.add_argument("--device-name", default="managed-device")
    create.add_argument("--app-version", default="1.0.0")

    disable = sub.add_parser("disable", help="Disable a monitor user")
    disable.add_argument("--username", required=True)

    enable = sub.add_parser("enable", help="Enable a monitor user")
    enable.add_argument("--username", required=True)

    revoke_session = sub.add_parser("revoke-session", help="Revoke a session by id")
    revoke_session.add_argument("--session-id", required=True, type=UUID)

    revoke_all = sub.add_parser("revoke-all", help="Revoke all sessions for a user")
    revoke_all.add_argument("--username", required=True)

    revoke_device = sub.add_parser("revoke-device", help="Revoke a device by id")
    revoke_device.add_argument("--device-id", required=True, type=UUID)

    return parser


async def _store() -> tuple[asyncpg.Pool, MonitorStore]:
    dsn = str(config.DATABASE_URL)
    pool = await asyncpg.create_pool(dsn=dsn, min_size=1, max_size=2)
    return pool, MonitorStore(pool)


async def _create(args: argparse.Namespace) -> int:
    pool, store = await _store()
    try:
        existing = await store.get_user_by_username(args.username)
        if existing is not None:
            print(f"user already exists: id={existing.id}")
            return 1

        password_hash = bcrypt.hashpw(args.password.encode(), bcrypt.gensalt()).decode()
        user = await store.create_user(
            username=args.username,
            password_hash=password_hash,
        )
        device = await store.create_device(
            user_id=user.id,
            installation_id=f"managed-{uuid.uuid4()}",
            name=args.device_name,
            app_version=args.app_version,
        )
        print(f"created user={user.id} device={device.id}")
        return 0
    finally:
        await pool.close()


async def _disable(args: argparse.Namespace) -> int:
    pool, store = await _store()
    try:
        user = await store.get_user_by_username(args.username)
        if user is None:
            print(f"user not found: {args.username}")
            return 1
        await store.disable_user(user.id)
        print(f"disabled user={user.id}")
        return 0
    finally:
        await pool.close()


async def _enable(args: argparse.Namespace) -> int:
    pool, store = await _store()
    try:
        user = await store.get_user_by_username(args.username)
        if user is None:
            print(f"user not found: {args.username}")
            return 1
        await store.enable_user(user.id)
        print(f"enabled user={user.id}")
        return 0
    finally:
        await pool.close()


async def _revoke_session(args: argparse.Namespace) -> int:
    pool, store = await _store()
    try:
        session = await store.get_session_by_id(args.session_id)
        if session is None:
            print(f"session not found: {args.session_id}")
            return 1
        await store.revoke_session(session.id)
        print(f"revoked session={session.id}")
        return 0
    finally:
        await pool.close()


async def _revoke_all(args: argparse.Namespace) -> int:
    pool, store = await _store()
    try:
        user = await store.get_user_by_username(args.username)
        if user is None:
            print(f"user not found: {args.username}")
            return 1
        await store.revoke_all_sessions_for_user(user.id)
        print(f"revoked all sessions for user={user.id}")
        return 0
    finally:
        await pool.close()


async def _revoke_device(args: argparse.Namespace) -> int:
    pool, store = await _store()
    try:
        device = await store.get_device(args.device_id)
        if device is None:
            print(f"device not found: {args.device_id}")
            return 1
        await store.revoke_device(device.id)
        print(f"revoked device={device.id}")
        return 0
    finally:
        await pool.close()


async def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)

    handlers = {
        "create": _create,
        "disable": _disable,
        "enable": _enable,
        "revoke-session": _revoke_session,
        "revoke-all": _revoke_all,
        "revoke-device": _revoke_device,
    }
    return await handlers[args.command](args)


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
