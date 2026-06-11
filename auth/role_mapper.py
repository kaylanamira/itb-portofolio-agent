"""
auth/role_mapper.py

Mapping dari ms365_id (oid dari Microsoft ID token) → AuthUser.

Pipeline:
    1. Lookup users.user by ms365_id          → dapat user_id, nama, active
    2. Cek active = true                       → tolak jika tidak aktif
    3. Fetch semua role aktif dari DB          → users.user_role JOIN users.role
    4. Filter role yang diizinkan              → sesuai aturan akses aplikasi
    5. Tolak jika tidak ada role valid         → tidak punya akses
    6. Fetch dosen info (opsional)             → ms365.user_dosen JOIN utama.dosen
    7. Build ScopeEntry per role               → isi dosen_id, no_ps, kd_fak, kk_id
    8. Tentukan active_role                    → role dengan prime=true, atau pertama
    9. Return AuthUser                         → siap untuk create_session()

Tanggung jawab file ini HANYA:
    - Query PostgreSQL
    - Mapping data DB → domain objects (UserScope, ScopeEntry)

Tidak tahu tentang:
    - Redis / session  (auth/session.py)
    - MSAL / Microsoft (auth/microsoft.py)
    - HTTP             (api/routers/auth.py)
"""

import logging
from dataclasses import dataclass

from core.database import get_db_connection
from core.scope import ScopeEntry, UserRole, UserScope

logger = logging.getLogger(__name__)


# ─── Result Types ─────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class AuthUser:
    """
    Hasil sukses dari get_auth_user().
    Berisi semua yang dibutuhkan untuk membuat session.
    """
    user_id: int
    nama: str
    user_scope: UserScope


class AuthError(Exception):
    """
    Raised saat autentikasi gagal karena alasan yang bisa diprediksi.
    Bukan bug — ini kondisi bisnis normal (user tidak aktif, tidak punya akses, dll).

    Attributes:
        reason: Pesan yang aman ditampilkan ke pengguna.
        http_status: HTTP status yang sesuai untuk error ini.
    """
    def __init__(self, reason: str, *, http_status: int = 403):
        self.reason = reason
        self.http_status = http_status
        super().__init__(reason)


# ─── Role Authorization Rules ─────────────────────────────────────────────────
# Aturan ini langsung dari spesifikasi akses aplikasi.
# Ubah di sini jika ada perubahan kebijakan akses — satu tempat, efek ke seluruh app.

# scope_type yang diizinkan login
_ALLOWED_SCOPE_TYPES: frozenset[str] = frozenset({
    "prodi", "fakultas", "tpb", "sps", "dosen",
})

# role_name khusus yang diizinkan meski scope_type-nya NULL atau di luar allowed list
_DIREKTORAT_ROLE_NAMES: frozenset[str] = frozenset({
    "spm", "dirdik", "ditmawa-mhs", "dir-ektm", "ditmawa-ult",
    "ditpran", "ditsp", "ditsti sp", "ev-kur", "koord-porto", "wrm", "dektm",
})


# ─── Public API ───────────────────────────────────────────────────────────────

async def get_auth_user(ms365_id: str) -> AuthUser:
    """
    Entry point utama: dari ms365_id → AuthUser siap pakai.

    Args:
        ms365_id: Object ID (oid) dari Microsoft ID token. Format UUID.

    Returns:
        AuthUser berisi user_id, nama, dan UserScope lengkap.

    Raises:
        AuthError: Jika user tidak ditemukan, tidak aktif, atau tidak punya akses.
        Exception: Jika ada error DB yang tidak terduga.
    """
    async with get_db_connection() as conn:
        user = await _fetch_user(conn, ms365_id)

        if user is None:
            raise AuthError(
                "Akun Microsoft Anda tidak terdaftar di sistem.",
                http_status=403,
            )
        if not user["active"]:
            raise AuthError(
                "Akun Anda tidak aktif. Hubungi administrator.",
                http_status=403,
            )

        role_rows = await _fetch_user_roles(conn, user["user_id"])
        authorized = _filter_authorized(role_rows)

        if not authorized:
            raise AuthError(
                "Akun Anda tidak memiliki akses ke aplikasi ini.",
                http_status=403,
            )

        # Dosen info dibutuhkan untuk mengisi dosen_id, kd_fak, no_ps, kk_id
        # pada ScopeEntry. Hanya diquery jika ada role yang membutuhkannya.
        needs_dosen_info = any(
            r["scope_type"] in ("dosen", "prodi", "tpb", "sps", "fakultas")
            for r in authorized
        )
        dosen_info = await _fetch_dosen_info(conn, ms365_id) if needs_dosen_info else None

        scope_entries = [_build_scope_entry(r, dosen_info) for r in authorized]
        user_scope = _build_user_scope(user["user_id"], scope_entries)

        logger.info(
            "Auth OK | user_id=%s | nama=%s | roles=%s",
            user["user_id"],
            user["nama"],
            [e.role.value for e in scope_entries],
        )
        return AuthUser(
            user_id=user["user_id"],
            nama=user["nama"],
            user_scope=user_scope,
        )


# ─── Private: DB Queries ──────────────────────────────────────────────────────

async def _fetch_user(conn, ms365_id: str) -> dict | None:
    """
    Cari user berdasarkan ms365_id (UUID dari oid Microsoft token).
    Kembalikan None jika tidak ditemukan.
    """
    cursor = await conn.execute(
        """
        SELECT user_id, nama, active
        FROM users.user
        WHERE ms365_id = %s::uuid
        """,
        (ms365_id,),
    )
    row = await cursor.fetchone()
    if row is None:
        return None
    cols = [d[0] for d in cursor.description]
    return dict(zip(cols, row))


async def _fetch_user_roles(conn, user_id: int) -> list[dict]:
    """
    Ambil semua role aktif user beserta detail role-nya.

    Hanya role dengan:
        - ur.active = true
        - ts_valid mencakup waktu sekarang (atau tidak ada batas waktu)
    """
    cursor = await conn.execute(
        """
        SELECT
            ur.user_role_id,
            r.role_name,
            r.scope_type,
            ur.scope,
            ur.prime
        FROM users.user_role ur
        JOIN users.role r ON r.role_id = ur.role_id
        WHERE ur.user_id = %s
          AND ur.active = true
          AND (ur.ts_valid IS NULL OR ur.ts_valid @> now())
        ORDER BY ur.prime DESC, ur.weight DESC
        """,
        (user_id,),
    )
    rows = await cursor.fetchall()
    cols = [d[0] for d in cursor.description]
    return [dict(zip(cols, row)) for row in rows]


async def _fetch_dosen_info(conn, ms365_id: str) -> dict | None:
    """
    Ambil informasi dosen berdasarkan ms365_id.
    Kembalikan None jika user bukan dosen (misal: admin-analitik mahasiswa).

    Join ms365.user_dosen → utama.dosen untuk dapat dosen_id, kd_fak, no_ps, kk_id.
    """
    cursor = await conn.execute(
        """
        SELECT d.dosen_id, d.kd_fak, d.no_ps, d.kk_id
        FROM ms365.user_dosen ud
        JOIN utama.dosen d ON d.dosen_id = ud.dosen_id
        WHERE ud.user_id = %s::uuid
          AND d.active = true
        """,
        (ms365_id,),
    )
    row = await cursor.fetchone()
    if row is None:
        return None
    cols = [d[0] for d in cursor.description]
    return dict(zip(cols, row))


# ─── Private: Role Mapping ────────────────────────────────────────────────────

def _filter_authorized(role_rows: list[dict]) -> list[dict]:
    """
    Filter hanya role yang diizinkan masuk ke aplikasi ini.
    Role yang tidak masuk kriteria diabaikan (tidak raise error).
    """
    result = []
    for row in role_rows:
        role_name = row["role_name"]
        scope_type = row["scope_type"]
        if _resolve_user_role(role_name, scope_type) is not None:
            result.append(row)
    return result


def _resolve_user_role(role_name: str, scope_type: str | None) -> UserRole | None:
    """
    Tentukan UserRole dari (role_name, scope_type) DB.
    Kembalikan None jika role ini tidak diizinkan.

    Aturan (urutan penting: cek spesifik dulu, umum belakangan):
        1. admin-analitik → ADMIN
        2. role direktorat khusus → DIREKTORAT
        3. scope_type 'dosen' → DOSEN
        4. scope_type 'prodi' + role_name 'prodi' → KAPRODI
        5. scope_type 'prodi'/'tpb'/'sps' lainnya → JAJARAN_PRODI
        6. scope_type 'fakultas' + role_name 'fakultas' → DEKAN
        7. scope_type 'fakultas' lainnya → JAJARAN_DEKANAT
        8. Selainnya → None (tidak diizinkan)
    """
    if role_name == "admin-analitik":
        return UserRole.ADMIN
    if role_name in _DIREKTORAT_ROLE_NAMES:
        return UserRole.DIREKTORAT
    if scope_type == "dosen":
        return UserRole.DOSEN
    if scope_type == "prodi":
        return UserRole.KAPRODI if role_name == "prodi" else UserRole.JAJARAN_PRODI
    if scope_type in ("tpb", "sps"):
        return UserRole.JAJARAN_PRODI
    if scope_type == "fakultas":
        return UserRole.DEKAN if role_name == "fakultas" else UserRole.JAJARAN_DEKANAT
    return None


def _build_scope_entry(role_row: dict, dosen_info: dict | None) -> ScopeEntry:
    """
    Bangun ScopeEntry dari satu baris role DB + info dosen (jika ada).

    Logika pengisian field scope:
        DOSEN       → semua dari dosen_info (dosen_id, kd_fak, no_ps, kk_id)
        PRODI/TPB/SPS → no_ps dari ur.scope (integer), kd_fak dari dosen_info
        FAKULTAS    → kd_fak dari ur.scope (string), dosen_id dari dosen_info
        ADMIN/DIREK → semua null (tidak butuh scope spesifik)
    """
    role_name: str = role_row["role_name"]
    scope_type: str | None = role_row["scope_type"]
    scope_val: str | None = role_row["scope"]
    user_role = _resolve_user_role(role_name, scope_type)  # tidak None, sudah difilter

    dosen_id = dosen_info["dosen_id"] if dosen_info else None
    kk_id    = dosen_info["kk_id"]    if dosen_info else None
    no_ps: int | None = None
    kd_fak: str | None = None

    if scope_type == "dosen":
        no_ps  = dosen_info["no_ps"]   if dosen_info else None
        kd_fak = dosen_info["kd_fak"]  if dosen_info else None

    elif scope_type in ("prodi", "tpb", "sps"):
        # scope berisi no_ps sebagai string, misal '135'
        no_ps  = _to_int(scope_val)
        kd_fak = dosen_info["kd_fak"] if dosen_info else None

    elif scope_type == "fakultas":
        # scope berisi kd_fak sebagai string, misal 'STEI'
        kd_fak = scope_val
        # dosen_id tetap diisi jika user juga seorang dosen

    return ScopeEntry(
        user_role_id=role_row["user_role_id"],
        role=user_role,
        dosen_id=dosen_id,
        kk_id=kk_id,
        no_ps=no_ps,
        kd_fak=kd_fak,
        is_prime=bool(role_row["prime"]),
    )


def _build_user_scope(user_id: int, entries: list[ScopeEntry]) -> UserScope:
    """
    Tentukan active_role dari list ScopeEntry.
    Prioritas: prime=True → jika tidak ada, pakai entry pertama.
    """
    prime = next((e for e in entries if e.is_prime), None)
    active = prime if prime is not None else entries[0]
    return UserScope(
        user_id=user_id,
        active_role=active,
        available_roles=entries,
    )


# ─── Private: Helpers ─────────────────────────────────────────────────────────

def _to_int(value: str | None) -> int | None:
    """Parse string ke int dengan aman. None jika tidak bisa diparse."""
    if value is None:
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None