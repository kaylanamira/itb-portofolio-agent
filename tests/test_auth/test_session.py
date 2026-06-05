"""
tests/test_auth/test_session.py

Test untuk auth/session.py — memverifikasi bahwa session CRUD di Redis bekerja benar.

Cara run:
    uv run python tests/test_auth/test_session.py

Requirement: Docker Redis harus jalan (docker compose up -d redis).

Tidak butuh pytest-asyncio. Semua test dijalankan via asyncio.run() di __main__.
"""

import asyncio
import sys
import os

# Pastikan root project ada di path agar import core.* dan auth.* bisa berjalan
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from core.redis_client import init_redis, close_redis
from core.scope import ScopeEntry, UserRole, UserScope
from auth.session import (
    create_session,
    delete_session,
    get_session,
    pop_oauth_flow,
    session_to_user_scope,
    store_oauth_flow,
)


# ─── Test Fixtures ────────────────────────────────────────────────────────────

def _make_admin_scope() -> UserScope:
    """Buat UserScope dummy untuk testing — meniru admin-analitik."""
    entry = ScopeEntry(
        user_role_id=163,
        role=UserRole.ADMIN,
        is_prime=True,
    )
    return UserScope(
        user_id=210015,  # user_id Andhita (dari DB)
        active_role=entry,
        available_roles=[entry],
    )


def _make_dosen_scope() -> UserScope:
    """Buat UserScope dummy untuk testing — meniru dosen biasa."""
    entry = ScopeEntry(
        user_role_id=999,
        role=UserRole.DOSEN,
        dosen_id=937,
        kd_fak="STEI",
        no_ps=135,
        kk_id=12,
        is_prime=True,
    )
    return UserScope(
        user_id=33917,
        active_role=entry,
        available_roles=[entry],
    )


# ─── Test Functions ───────────────────────────────────────────────────────────

async def test_create_and_get_session():
    """create_session harus menghasilkan session_id yang bisa di-get kembali."""
    scope = _make_admin_scope()
    session_id = await create_session(scope, nama="Andhita")

    assert session_id, "session_id tidak boleh kosong"
    assert len(session_id) > 20, "session_id terlalu pendek — entropy kurang"

    data = await get_session(session_id)
    assert data is not None, "Session tidak ditemukan di Redis setelah dibuat"
    assert data["user_id"] == 210015
    assert data["nama"] == "Andhita"
    assert data["active_role"]["role"] == UserRole.ADMIN.value

    # Cleanup
    await delete_session(session_id)
    print("  ✓ create_session + get_session")


async def test_delete_session():
    """delete_session harus membuat session tidak bisa di-get lagi."""
    scope = _make_admin_scope()
    session_id = await create_session(scope, nama="Test Delete")

    await delete_session(session_id)

    data = await get_session(session_id)
    assert data is None, "Session masih ada setelah dihapus — delete gagal"
    print("  ✓ delete_session")


async def test_get_nonexistent_session():
    """get_session dengan ID yang tidak ada harus kembalikan None."""
    data = await get_session("session_yang_tidak_pernah_ada_xyz123")
    assert data is None, "Seharusnya None untuk session yang tidak ada"
    print("  ✓ get_session (nonexistent) → None")


async def test_session_to_user_scope_roundtrip():
    """Data yang masuk ke Redis harus bisa dideserialisasi kembali persis sama."""
    original_scope = _make_dosen_scope()
    session_id = await create_session(original_scope, nama="Parama Dosen")

    data = await get_session(session_id)
    restored_scope = session_to_user_scope(data)

    assert restored_scope.user_id == original_scope.user_id
    assert restored_scope.role == original_scope.role
    assert restored_scope.active_role.dosen_id == original_scope.active_role.dosen_id
    assert restored_scope.active_role.kd_fak == original_scope.active_role.kd_fak
    assert restored_scope.active_role.no_ps == original_scope.active_role.no_ps
    assert restored_scope.active_role.kk_id == original_scope.active_role.kk_id
    assert restored_scope.active_role.is_prime == original_scope.active_role.is_prime

    # Cleanup
    await delete_session(session_id)
    print("  ✓ session_to_user_scope round-trip (semua field cocok)")


async def test_store_and_pop_oauth_flow():
    """store + pop harus berhasil, dan pop kedua harus None (one-time use)."""
    fake_flow = {
        "state": "test_state_abc123xyz",
        "auth_uri": "https://login.microsoftonline.com/...",
        "code_verifier": "test_verifier",
        "nonce": "test_nonce",
    }

    await store_oauth_flow(fake_flow)

    # Pop pertama → dapat data
    result = await pop_oauth_flow("test_state_abc123xyz")
    assert result is not None, "Flow tidak ditemukan setelah disimpan"
    assert result["state"] == "test_state_abc123xyz"
    assert result["nonce"] == "test_nonce"

    # Pop kedua → harus None (sudah dihapus)
    result2 = await pop_oauth_flow("test_state_abc123xyz")
    assert result2 is None, "Flow masih ada setelah di-pop — one-time use gagal"

    print("  ✓ store_oauth_flow + pop_oauth_flow (one-time use benar)")


async def test_store_flow_without_state_raises():
    """store_oauth_flow tanpa 'state' harus raise ValueError."""
    try:
        await store_oauth_flow({"auth_uri": "https://..."})  # tidak ada 'state'
        assert False, "Seharusnya raise ValueError"
    except ValueError:
        pass
    print("  ✓ store_oauth_flow tanpa state → ValueError")


# ─── Runner ───────────────────────────────────────────────────────────────────

async def run_all():
    print("\n=== Test auth/session.py ===")
    print("Menghubungkan ke Redis...")

    await init_redis()

    tests = [
        test_create_and_get_session,
        test_delete_session,
        test_get_nonexistent_session,
        test_session_to_user_scope_roundtrip,
        test_store_and_pop_oauth_flow,
        test_store_flow_without_state_raises,
    ]

    passed = 0
    failed = 0
    for test_fn in tests:
        try:
            await test_fn()
            passed += 1
        except AssertionError as e:
            print(f"  ✗ {test_fn.__name__}: GAGAL — {e}")
            failed += 1
        except Exception as e:
            print(f"  ✗ {test_fn.__name__}: ERROR — {type(e).__name__}: {e}")
            failed += 1

    await close_redis()

    print(f"\nHasil: {passed} lulus, {failed} gagal")
    if failed > 0:
        sys.exit(1)
    print("Semua test session lulus ✓\n")


if __name__ == "__main__":
    asyncio.run(run_all())