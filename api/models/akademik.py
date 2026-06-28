"""
api/models/akademik.py

Fungsi query untuk dashboard akademik.
Berisi SQL dan logika pengambilan data — tidak ada HTTP / FastAPI di sini.

Konvensi:
  - Query ke analitik.v_* (RLS-protected via SECURITY DEFINER)
    → gunakan PsycopgExecutor supaya session variable RLS di-set otomatis.
  - Query ke utama.* (master data, tanpa RLS)
    → gunakan get_db_connection() langsung dengan WHERE eksplisit per scope.
"""

import logging
from core.database     import get_db_connection
from core.scope        import UserScope, UserRole
from core.sql_executor import PsycopgExecutor

logger    = logging.getLogger(__name__)
_executor = PsycopgExecutor()   # stateless, aman dipakai ulang lintas request

# Mapping kd_strata DB → label yang ditampilkan di UI
_STRATA_LABEL: dict[str, str] = {
    "S1": "S1",
    "S2": "S2",
    "S3": "S3",
    "PR": "Profesi",
}


# ─── Phase 0.5: Filter options ────────────────────────────────────────────────

async def get_tahun_ajaran_tersedia(scope: UserScope) -> list[str]:
    """
    Ambil daftar tahun ajaran yang benar-benar punya data untuk scope ini.

    Menggunakan analitik.v_akademik_statistik_prodi (SECURITY DEFINER — RLS aktif),
    sehingga PsycopgExecutor sudah otomatis set session variable sebelum query.

    Satu tahun ajaran bisa span dua nilai `tahun` berbeda
    (mis. 2024/2025: tahun=2024 untuk gasal, tahun=2025 untuk genap),
    maka GROUP BY + ORDER BY MAX(tahun) DESC untuk urutan yang benar.
    """
    sql = """
        SELECT   tahun_ajaran,
                 MAX(tahun) AS tahun_max
        FROM     analitik.v_akademik_statistik_prodi
        GROUP BY tahun_ajaran
        ORDER BY tahun_max DESC
    """
    result = await _executor.execute(sql, scope)

    if result.error:
        logger.error(
            "get_tahun_ajaran_tersedia error (user_id=%s role=%s): %s",
            scope.user_id, scope.role, result.error,
        )
        return []

    return [row["tahun_ajaran"] for row in result.rows]


async def get_fakultas_options(scope: UserScope) -> list[dict]:
    """
    Ambil daftar fakultas yang visible untuk scope ini.

    utama.fakultas TIDAK punya RLS → filter eksplisit berdasarkan role:
      admin / direktorat → semua fakultas aktif
      role lain          → hanya fakultas dari scope.active_role.kd_fak
    """
    role   = scope.role
    kd_fak = scope.active_role.kd_fak or ""

    async with get_db_connection() as conn:
        if role in (UserRole.ADMIN, UserRole.DIREKTORAT):
            cur = await conn.execute(
                """
                SELECT   kd_fak,
                         nama->>'id' AS nama_id
                FROM     utama.fakultas
                WHERE    active = true
                ORDER BY weight
                """
            )
        else:
            cur = await conn.execute(
                """
                SELECT   kd_fak,
                         nama->>'id' AS nama_id
                FROM     utama.fakultas
                WHERE    active = true
                  AND    kd_fak = %s
                ORDER BY weight
                """,
                [kd_fak],
            )

        rows = await cur.fetchall()
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in rows]


async def get_prodi_options(scope: UserScope) -> list[dict]:
    """
    Ambil daftar prodi yang visible untuk scope ini.

    utama.program_studi TIDAK punya RLS → filter eksplisit:
      admin / direktorat      → semua prodi aktif
      dekan / jajaran_dekanat → prodi dalam kd_fak scope
      lainnya (kaprodi, dll.) → hanya prodi scope sendiri (filter by no_ps)

    Kolom yang dikembalikan:
      no_ps      → dipakai sebagai `value` (unik, tidak ambigu)
      kd_ps      → untuk referensi / grouping di frontend
      kd_fak     → untuk mengelompokkan ke prodi_by_fakultas
      kd_strata  → untuk filter jenjang di frontend ("S1"/"S2"/"S3"/"PR")
      nama_id    → nama prodi dalam bahasa Indonesia

    PENTING: kd_ps TIDAK unik dalam satu fakultas.
    Contoh: di STEI, kd_ps="IF" ada untuk S1 (no_ps=X) dan S2 (no_ps=Y).
    Maka nilai yang dikirim ke chart endpoint harus no_ps, bukan kd_ps.
    """
    role   = scope.role
    kd_fak = scope.active_role.kd_fak or ""
    no_ps  = scope.active_role.no_ps

    async with get_db_connection() as conn:
        if role in (UserRole.ADMIN, UserRole.DIREKTORAT):
            cur = await conn.execute(
                """
                SELECT   no_ps,
                         kd_ps,
                         kd_fak,
                         kd_strata,
                         nama->>'id' AS nama_id
                FROM     utama.program_studi
                WHERE    active = true
                ORDER BY kd_fak, kd_strata, kd_ps
                """
            )
        elif role in (UserRole.DEKAN, UserRole.JAJARAN_DEKANAT):
            cur = await conn.execute(
                """
                SELECT   no_ps,
                         kd_ps,
                         kd_fak,
                         kd_strata,
                         nama->>'id' AS nama_id
                FROM     utama.program_studi
                WHERE    active = true
                  AND    kd_fak = %s
                ORDER BY kd_strata, kd_ps
                """,
                [kd_fak],
            )
        else:
            # kaprodi, jajaran_prodi, dosen — hanya prodi sendiri
            if no_ps is None:
                logger.warning(
                    "get_prodi_options: no_ps is None untuk role=%s user_id=%s",
                    role, scope.user_id,
                )
                return []

            cur = await conn.execute(
                """
                SELECT   no_ps,
                         kd_ps,
                         kd_fak,
                         kd_strata,
                         nama->>'id' AS nama_id
                FROM     utama.program_studi
                WHERE    active = true
                  AND    no_ps = %s
                """,
                [no_ps],
            )

        rows = await cur.fetchall()
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in rows]


def build_prodi_label(nama_id: str, kd_strata: str) -> str:
    """
    Bangun label prodi yang ditampilkan di dropdown.
    Contoh: "Teknik Informatika (S1)", "Teknik Informatika (S2)"

    Ini penting supaya dua prodi dengan nama dasar yang sama tapi jenjang berbeda
    bisa dibedakan oleh user di UI.
    """
    strata = _STRATA_LABEL.get(kd_strata, kd_strata)
    return f"{nama_id} ({strata})"