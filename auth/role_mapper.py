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
    8. Resolve nama entitas → scope_label      → nama fakultas/prodi/kk per role
    9. Tentukan active_role                    → role dengan prime=true, atau pertama
    10. Return AuthUser                        → siap untuk create_session()

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

        # Dosen info dibutuhkan untuk mengisi dosen_id, kk_id, dan kd_fak
        # (khusus scope_type == "dosen") pada ScopeEntry.
        needs_dosen_info = any(
            r["scope_type"] in ("dosen", "prodi", "tpb", "sps", "fakultas")
            for r in authorized
        )
        dosen_info = await _fetch_dosen_info(conn, ms365_id) if needs_dosen_info else None

        # FIX: _build_scope_entry sekarang async karena butuh lookup kd_fak
        # dari program_studi untuk scope_type prodi/tpb/sps (lihat fungsi itu).
        scope_entries = [
            await _build_scope_entry(conn, r, dosen_info) for r in authorized
        ]

        # Resolve nama entitas (fakultas/prodi/kk) → scope_label per entry.
        # Dilakukan sebagai batch step terpisah supaya query nama tidak
        # berulang untuk kd_fak/no_ps/kk_id yang sama di beberapa entry.
        scope_entries = await _attach_scope_labels(conn, scope_entries)

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

    Catatan: kd_fak dari sini HANYA valid dipakai untuk scope_type == "dosen"
    (fakultas "rumah" dosen itu sendiri). JANGAN dipakai sebagai kd_fak untuk
    scope_type prodi/tpb/sps — dosen bisa berbeda fakultas rumah dengan prodi
    yang dia jabat sebagai kaprodi/jajaran. Untuk itu pakai _fetch_prodi_kd_fak().
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


async def _fetch_prodi_kd_fak(conn, no_ps: int) -> str | None:
    """
    Ambil kd_fak resmi milik suatu prodi, berdasarkan no_ps.

    kd_fak di utama.program_studi adalah NOT NULL — ini SUMBER KEBENARAN
    untuk menentukan fakultas suatu prodi. JANGAN pakai dosen.kd_fak untuk
    tujuan ini, karena dosen bisa punya fakultas "rumah" berbeda dengan
    fakultas resmi prodi yang dia jabat sebagai kaprodi/jajaran prodi.
    """
    cursor = await conn.execute(
        "SELECT kd_fak FROM utama.program_studi WHERE no_ps = %s",
        (no_ps,),
    )
    row = await cursor.fetchone()
    return row[0] if row else None


async def _fetch_fakultas_names(conn, kd_fak_list: list[str]) -> dict[str, str]:
    """Batch lookup nama fakultas (id) untuk daftar kd_fak. Kembalikan {} jika kosong."""
    if not kd_fak_list:
        return {}
    cursor = await conn.execute(
        "SELECT kd_fak, nama->>'id' AS nama_id FROM utama.fakultas WHERE kd_fak = ANY(%s)",
        (kd_fak_list,),
    )
    rows = await cursor.fetchall()
    return {row[0]: row[1] for row in rows}


async def _fetch_prodi_names(conn, no_ps_list: list[int]) -> dict[int, str]:
    """
    Batch lookup nama prodi (id) + jenjang untuk daftar no_ps. Kembalikan {} jika kosong.

    Label diformat "Nama Prodi (Jenjang)", misal "Teknik Informatika (S1)",
    supaya prodi dengan nama sama di jenjang berbeda (S1/S2/S3) tetap
    terbedakan di profil header.
    """
    if not no_ps_list:
        return {}
    cursor = await conn.execute(
        "SELECT no_ps, nama->>'id' AS nama_id, kd_strata "
        "FROM utama.program_studi WHERE no_ps = ANY(%s)",
        (no_ps_list,),
    )
    rows = await cursor.fetchall()
    return {
        row[0]: f"{row[1]} ({row[2]})" if row[2] else row[1]
        for row in rows
    }


async def _fetch_kk_names(conn, kk_id_list: list[int]) -> dict[int, str]:
    """Batch lookup nama kk (id) untuk daftar kk_id. Kembalikan {} jika kosong."""
    if not kk_id_list:
        return {}
    cursor = await conn.execute(
        "SELECT kk_id, nama->>'id' AS nama_id FROM utama.kk WHERE kk_id = ANY(%s)",
        (kk_id_list,),
    )
    rows = await cursor.fetchall()
    return {row[0]: row[1] for row in rows}


_INSTITUT_LABEL = "Institut Teknologi Bandung"


def _compute_scope_label(
    entry: ScopeEntry,
    fakultas_names: dict[str, str],
    prodi_names: dict[int, str],
    kk_names: dict[int, str],
) -> str:
    """
    Tentukan scope_label yang tampil di profil header, sesuai role:
        dekan / jajaran_dekanat → nama fakultas (kd_fak)
        kaprodi / jajaran_prodi → nama prodi (no_ps)
        dosen                   → nama kk (kk_id); fallback nama fakultas
                                   rumah kalau dosen belum tergabung KK aktif
        admin / direktorat      → label institut (scope nasional, tidak terikat entitas)
    """
    if entry.role in (UserRole.DEKAN, UserRole.JAJARAN_DEKANAT):
        if entry.kd_fak and entry.kd_fak in fakultas_names:
            return fakultas_names[entry.kd_fak]
        return entry.kd_fak or _INSTITUT_LABEL

    if entry.role in (UserRole.KAPRODI, UserRole.JAJARAN_PRODI):
        if entry.no_ps is not None and entry.no_ps in prodi_names:
            return prodi_names[entry.no_ps]
        return f"Prodi {entry.no_ps}" if entry.no_ps is not None else _INSTITUT_LABEL

    if entry.role == UserRole.DOSEN:
        if entry.kk_id is not None and entry.kk_id in kk_names:
            return kk_names[entry.kk_id]
        if entry.kd_fak and entry.kd_fak in fakultas_names:
            return fakultas_names[entry.kd_fak]
        return _INSTITUT_LABEL

    # ADMIN / DIREKTORAT → scope nasional, tidak terikat entitas tunggal
    return _INSTITUT_LABEL


async def _attach_scope_labels(conn, entries: list[ScopeEntry]) -> list[ScopeEntry]:
    """
    Batch-resolve nama fakultas/prodi/kk untuk semua entries sekaligus
    (menghindari N query terpisah), lalu tempel scope_label ke tiap entry.
    """
    kd_fak_list = list({e.kd_fak for e in entries if e.kd_fak})
    no_ps_list  = list({e.no_ps for e in entries if e.no_ps is not None})
    kk_id_list  = list({e.kk_id for e in entries if e.kk_id is not None})

    fakultas_names = await _fetch_fakultas_names(conn, kd_fak_list)
    prodi_names    = await _fetch_prodi_names(conn, no_ps_list)
    kk_names       = await _fetch_kk_names(conn, kk_id_list)

    return [
        e.model_copy(update={
            "scope_label": _compute_scope_label(e, fakultas_names, prodi_names, kk_names),
        })
        for e in entries
    ]


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


async def _build_scope_entry(conn, role_row: dict, dosen_info: dict | None) -> ScopeEntry:
    """
    Bangun ScopeEntry dari satu baris role DB + info dosen (jika ada).

    Logika pengisian field scope:
        DOSEN         → semua dari dosen_info (dosen_id, kd_fak, no_ps, kk_id)
        PRODI/TPB/SPS → no_ps dari ur.scope (integer),
                        kd_fak di-LOOKUP dari program_studi berdasarkan no_ps
                        (FIX: bukan dari dosen_info — lihat _fetch_prodi_kd_fak)
        FAKULTAS      → kd_fak dari ur.scope (string), dosen_id dari dosen_info
        ADMIN/DIREK   → semua null (tidak butuh scope spesifik)
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
        no_ps = _to_int(scope_val)
        # FIX: kd_fak WAJIB dari program_studi (sumber resmi, NOT NULL),
        # bukan dari dosen_info — dosen bisa beda fakultas rumah dengan
        # prodi yang dia jabat, dan dosen_info bisa None kalau user tidak
        # terdaftar di ms365.user_dosen.
        kd_fak = await _fetch_prodi_kd_fak(conn, no_ps) if no_ps is not None else None

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