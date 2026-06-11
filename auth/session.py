"""
auth/session.py

CRUD operasi untuk session dan OAuth flow di Redis.

Tanggung jawab file ini HANYA:
    - Simpan / baca / hapus session user (setelah login berhasil)
    - Simpan / ambil / hapus MSAL auth flow dict (saat proses OAuth berlangsung)

File ini TIDAK tahu tentang:
    - MSAL atau Microsoft (itu urusan auth/microsoft.py)
    - Database PostgreSQL (itu urusan auth/role_mapper.py)
    - HTTP request/response (itu urusan api/routers/auth.py)

Skema key Redis:
    session:<session_id>  → data user yang sedang login (TTL: SESSION_TTL_SECONDS)
    oauth_flow:<state>    → MSAL flow dict saat proses login (TTL: OAUTH_FLOW_TTL_SECONDS)
"""

import json
import secrets
import logging
from typing import Any

from core.config import settings
from core.redis_client import get_redis
from core.scope import ScopeEntry, UserScope

logger = logging.getLogger(__name__)

# Prefix key di Redis agar tidak tabrakan dengan key lain (caching, dll)
_SESSION_PREFIX = "session:"
_OAUTH_FLOW_PREFIX = "oauth_flow:"


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _session_key(session_id: str) -> str:
    return f"{_SESSION_PREFIX}{session_id}"


def _flow_key(state: str) -> str:
    return f"{_OAUTH_FLOW_PREFIX}{state}"


# ─── Session CRUD ─────────────────────────────────────────────────────────────

async def create_session(user_scope: UserScope, nama: str) -> str:
    """
    Buat session baru di Redis untuk user yang baru login.

    Args:
        user_scope: UserScope hasil mapping dari DB.
        nama: Nama lengkap user (dari users.user.nama), untuk ditampilkan di frontend.

    Returns:
        session_id (str): ID unik session. Ini yang disimpan di cookie browser.
    """
    session_id = secrets.token_urlsafe(32)  # 32 bytes = 256-bit entropy, aman

    session_data = {
        "user_id": user_scope.user_id,
        "nama": nama,
        "active_role": user_scope.active_role.model_dump(),
        "available_roles": [r.model_dump() for r in user_scope.available_roles],
    }

    redis = get_redis()
    await redis.setex(
        name=_session_key(session_id),
        time=settings.SESSION_TTL_SECONDS,
        value=json.dumps(session_data),
    )

    logger.info(
        "Session created for user_id=%s (TTL=%ds)",
        user_scope.user_id,
        settings.SESSION_TTL_SECONDS,
    )
    return session_id


async def get_session(session_id: str) -> dict[str, Any] | None:
    """
    Ambil data session dari Redis.

    Returns:
        dict berisi user_id, nama, active_role, available_roles.
        None jika session tidak ditemukan atau sudah expired.
    """
    redis = get_redis()
    raw = await redis.get(_session_key(session_id))
    if raw is None:
        return None
    return json.loads(raw)


async def delete_session(session_id: str) -> None:
    """
    Hapus session dari Redis. Dipanggil saat user logout.
    Silent jika session tidak ditemukan (sudah expired sebelumnya).
    """
    redis = get_redis()
    await redis.delete(_session_key(session_id))
    logger.info("Session deleted: %s...", session_id[:8])


def session_to_user_scope(session_data: dict[str, Any]) -> UserScope:
    """
    Konversi raw dict dari Redis kembali ke objek UserScope.

    Ini kebalikan dari proses serialisasi di create_session().
    Dipanggil di scope_middleware setiap request masuk.
    """
    active_role = ScopeEntry(**session_data["active_role"])
    available_roles = [ScopeEntry(**r) for r in session_data["available_roles"]]
    return UserScope(
        user_id=session_data["user_id"],
        active_role=active_role,
        available_roles=available_roles,
    )


# ─── OAuth Flow Storage ───────────────────────────────────────────────────────
# MSAL's initiate_auth_code_flow() mengembalikan dict yang berisi state, nonce,
# code_verifier (PKCE), dll. Dict ini harus disimpan sementara dan diambil kembali
# saat callback tiba. Redis adalah tempat yang tepat karena:
#   1. Flow ini hanya valid 5 menit
#   2. Bisa di-expire otomatis
#   3. Aman dari race condition jika ada banyak user login bersamaan

async def store_oauth_flow(flow: dict[str, Any]) -> None:
    """
    Simpan MSAL auth code flow dict di Redis.

    MSAL menyertakan 'state' di dalam flow dict — kita pakai itu sebagai key.
    TTL pendek (OAUTH_FLOW_TTL_SECONDS = 5 menit) karena flow ini hanya
    valid selama user mengisi form login Microsoft.

    Args:
        flow: Dict dari msal.initiate_auth_code_flow() — jangan dimodifikasi.

    Raises:
        ValueError: Jika flow tidak mengandung key 'state'.
    """
    state = flow.get("state")
    if not state:
        raise ValueError("MSAL flow dict harus mengandung key 'state'.")

    redis = get_redis()
    await redis.setex(
        name=_flow_key(state),
        time=settings.OAUTH_FLOW_TTL_SECONDS,
        value=json.dumps(flow),
    )
    logger.debug("OAuth flow stored for state=%s...", state[:8])


async def pop_oauth_flow(state: str) -> dict[str, Any] | None:
    """
    Ambil dan HAPUS MSAL flow dict dari Redis (one-time use).

    'Pop' (bukan 'get') karena flow dict tidak boleh dipakai dua kali —
    ini mencegah replay attack.

    Args:
        state: Nilai 'state' dari query parameter callback Microsoft.

    Returns:
        Flow dict jika ditemukan, None jika tidak ada / sudah expired.
    """
    redis = get_redis()
    key = _flow_key(state)
    raw = await redis.get(key)
    if raw is None:
        logger.warning("OAuth flow not found for state=%s... (expired atau invalid)", state[:8])
        return None
    await redis.delete(key)  # hapus setelah dibaca — one-time use
    return json.loads(raw)