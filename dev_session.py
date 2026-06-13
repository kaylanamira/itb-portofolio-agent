"""Dev helper: buat session login di Redis tanpa lewat Microsoft SSO.

Dipakai untuk testing /chat dan /chat/stream via curl (lihat query.sh),
saat MS365_CLIENT_ID/SECRET belum dikonfigurasi di mesin lokal.

Usage:
    uv run python dev_session.py --role direktorat
    uv run python dev_session.py --role kaprodi --no-ps 135 --user-id 33917
    uv run python dev_session.py --role dosen --dosen-id 42 --kd-fak STEI

Output: session_id yang dipakai sebagai cookie session (SESSION_COOKIE_NAME
di .env, default "sid") saat memanggil /chat atau /chat/stream.

PERINGATAN: hanya untuk dev/local. Skrip ini menulis langsung ke Redis,
bypass Microsoft SSO sepenuhnya — jangan dijalankan terhadap Redis yang
dipakai bersama/production.
"""

import argparse
import asyncio
import sys

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from auth.session import create_session
from core.config import settings
from core.redis_client import close_redis, init_redis
from core.scope import ScopeEntry, UserRole, UserScope


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Buat dev session di Redis untuk testing /chat via curl")
    p.add_argument("--role", default="direktorat")
    p.add_argument("--user-id", type=int, default=100, dest="user_id")
    p.add_argument("--nama", default="Dev Tester")
    p.add_argument("--dosen-id", type=int, default=None, dest="dosen_id")
    p.add_argument("--no-ps", type=int, default=None, dest="no_ps")
    p.add_argument("--kd-fak", type=str, default=None, dest="kd_fak")
    return p.parse_args()


def _build_scope(args: argparse.Namespace) -> UserScope:
    try:
        role = UserRole(args.role.lower())
    except ValueError:
        print(f"Role '{args.role}' tidak valid. Pilihan: {[r.value for r in UserRole]}", file=sys.stderr)
        sys.exit(1)

    active_role = ScopeEntry(
        user_role_id=1,
        role=role,
        dosen_id=args.dosen_id,
        no_ps=args.no_ps,
        kd_fak=args.kd_fak,
        is_prime=True,
    )
    return UserScope(user_id=args.user_id, active_role=active_role, available_roles=[active_role])


async def main() -> None:
    args = _parse_args()
    user_scope = _build_scope(args)

    await init_redis()
    try:
        session_id = await create_session(user_scope, nama=args.nama)
    finally:
        await close_redis()

    print(f"Role    : {user_scope.role.value} (user_id={user_scope.user_id})")
    print(f"Session : {session_id}")
    print()
    print("Jalankan ini di terminal sebelum query.sh:")
    print(f"  export DEV_SESSION_ID={session_id}")


if __name__ == "__main__":
    asyncio.run(main())