#!/usr/bin/env python3
"""Provision a mobile monitor user and device.

Usage:
    python scripts/provision_mobile_monitor.py \
        --username alice \
        --password ChangeMeNow! \
        [--device-name pixel9] \
        [--app-version 1.0.0]

Prints the created user_id and device_id. The password is hashed with bcrypt.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import uuid

import asyncpg
import bcrypt

from src.config import config
from src.mobile_monitoring.store import MonitorStore


async def main() -> int:
    parser = argparse.ArgumentParser(description="Provision a mobile monitor user")
    parser.add_argument("--username", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--device-name", default="android-device")
    parser.add_argument("--app-version", default="1.0.0")
    parser.add_argument("--platform", default="android")
    args = parser.parse_args()

    dsn = config.DATABASE_URL
    pool = await asyncpg.create_pool(dsn=dsn, min_size=1, max_size=2)
    store = MonitorStore(pool)

    existing = await store.get_user_by_username(args.username)
    if existing is not None:
        print(f"User {args.username} already exists (id={existing.id})")
        await pool.close()
        return 1

    password_hash = bcrypt.hashpw(args.password.encode(), bcrypt.gensalt()).decode()
    user = await store.create_user(
        username=args.username,
        password_hash=password_hash,
    )
    device = await store.create_device(
        user_id=user.id,
        installation_id=str(uuid.uuid4()),
        name=args.device_name,
        app_version=args.app_version,
    )
    print(f"user_id={user.id}")
    print(f"device_id={device.id}")
    await pool.close()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
