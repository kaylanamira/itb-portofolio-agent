"""
api/models/akademik.py

Fungsi query untuk dashboard akademik.
Tidak ada HTTP / FastAPI di sini — murni data access layer.

Konvensi:
  - Query ke analitik.v_* (RLS via SECURITY DEFINER)
    → gunakan PsycopgExecutor (otomatis set session variable sebelum query).
  - Query ke utama.* (master data, tanpa RLS)
    → gunakan get_db_connection() dengan WHERE eksplisit per scope.
"""

import logging
from core.database     import get_db_connection
from core.scope        import UserScope, UserRole
from core.sql_executor import PsycopgExecutor
from api.schemas.dashboard_akademik import AkademikQueryFilters


logger    = logging.getLogger(__name__)
_executor = PsycopgExecutor()   # stateless, aman dipakai ulang lintas request

# Semester di DB: smallint (1=Ganjil, 2=Genap, 3=Pendek/SP)
# value = text yang dikirim sebagai query param ke chart endpoints
_SEMESTER_MAP: dict[int, tuple[str, str]] = {
    1: ("ganjil",  "Ganjil"),
    2: ("genap",  "Genap"),
    3: ("pendek", "Pendek"),
}

_SEMESTER_VALUE_TO_DB: dict[str, int] = {
    value: db_int for db_int, (value, _label) in _SEMESTER_MAP.items()
}

# Jenjang (kd_strata) — value mengikuti nilai DB persis, label untuk tampilan
# Tidak perlu query DB terpisah — diturunkan dari prodi_rows yang sudah di-fetch
_STRATA_LABEL: dict[str, str] = {
    "S1": "S1",
    "S2": "S2",
    "S3": "S3",
    "PR": "Profesi",   # "PR" di DB, ditampilkan sebagai "Profesi"
}

# Urutan tampil di filter bar (S1 paling umum, Profesi paling jarang)
_STRATA_ORDER: dict[str, int] = {
    "S1": 0,
    "S2": 1,
    "S3": 2,
    "PR": 3,
}


# ─── Phase 0.5: Filter options ────────────────────────────────────────────────

async def get_tahun_ajaran_tersedia(scope: UserScope) -> list[str]:
    """
    Daftar tahun ajaran yang punya data untuk scope ini, urutan terbaru dulu.
    Menggunakan v_akademik_statistik_prodi (SECURITY DEFINER — RLS aktif).
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


async def get_semester_tersedia(scope: UserScope) -> list[dict]:
    """
    Daftar semester yang punya data untuk scope ini, urutan kalender.
    Semester DB (smallint) dikonversi ke text untuk konsistensi query param.
    """
    sql = """
        SELECT DISTINCT semester
        FROM   analitik.v_akademik_statistik_prodi
        ORDER  BY semester
    """
    result = await _executor.execute(sql, scope)

    if result.error:
        logger.error(
            "get_semester_tersedia error (user_id=%s role=%s): %s",
            scope.user_id, scope.role, result.error,
        )
        return []

    options = []
    for row in result.rows:
        sem_int = row["semester"]
        if sem_int in _SEMESTER_MAP:
            value, label = _SEMESTER_MAP[sem_int]
            options.append({"value": value, "label": label})
        else:
            logger.warning(
                "get_semester_tersedia: semester=%s tidak dikenal", sem_int,
            )
            options.append({"value": str(sem_int), "label": f"Semester {sem_int}"})

    return options


async def get_fakultas_options(scope: UserScope) -> list[dict]:
    """
    Daftar fakultas yang visible untuk scope ini.
    utama.fakultas tidak punya RLS → filter eksplisit.
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
    Daftar prodi yang visible untuk scope ini.
    utama.program_studi tidak punya RLS → filter eksplisit.

    PENTING: kd_ps tidak unik dalam satu fakultas (contoh: "IF" bisa S1 & S2).
    Gunakan no_ps sebagai identifier, bukan kd_ps.
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
    Label prodi untuk dropdown: "Teknik Informatika (S1)", "Sains Manajemen (S2)"
    Membedakan prodi dengan nama dasar sama tapi jenjang berbeda.
    """
    strata = _STRATA_LABEL.get(kd_strata, kd_strata)
    return f"{nama_id} ({strata})"


def derive_jenjang_options(prodi_rows: list[dict]) -> list[dict]:
    """
    Turunkan opsi jenjang dari prodi_rows yang sudah di-fetch.
    Tidak perlu query database tambahan.

    Mengapa dari prodi_rows, bukan query terpisah?
      - Data kd_strata sudah ada di setiap baris prodi
      - Hasilnya scope-aware secara otomatis: kaprodi S1 hanya punya
        prodi S1 di prodi_rows, maka jenjang yang muncul hanya "S1"
      - Nol additional round-trip ke database

    Value menggunakan kd_strata DB persis ("S1"/"S2"/"S3"/"PR") supaya
    chart endpoints tidak perlu konversi saat menerima query param.
    Label "PR" ditampilkan sebagai "Profesi" untuk kejelasan.
    """
    seen: set[str] = set()
    strata_found: list[str] = []

    for row in prodi_rows:
        ks = row["kd_strata"]
        if ks not in seen and ks in _STRATA_LABEL:
            seen.add(ks)
            strata_found.append(ks)

    # Sort berdasarkan urutan tampil yang sudah didefinisikan
    strata_found.sort(key=lambda x: _STRATA_ORDER.get(x, 99))

    return [
        {"value": ks, "label": _STRATA_LABEL[ks]}
        for ks in strata_found
    ]

# ─── Shared: filter clause builder ─────────────────────────────────────────────

def build_filter_clause(
    tahun_ajaran: str | None,
    semester:     str | None,
    jenjang:      list[str] | None,
    fakultas:     str | None,
    no_ps:        str | None,
) -> tuple[str, list]:
    """
    Bangun klausa WHERE dinamis + parameter list dari filter query param.
    Param spasial (fakultas, no_ps) di sini HANYA dipakai untuk role yang
    boleh memilih bebas — enforcement scope-locking tetap di scope.active_role
    + RLS session variable, bukan di sini. Fungsi ini murni menerjemahkan
    filter dimensi yang sudah lolos validasi/locking di layer atasnya.
    """
    clauses: list[str] = []
    params:  list = []

    if tahun_ajaran:
        clauses.append("tahun_ajaran = %s")
        params.append(tahun_ajaran)

    if semester:
        clauses.append("semester = %s")
        params.append(_SEMESTER_VALUE_TO_DB[semester])  # "ganjil" → 1, dst

    if jenjang:
        clauses.append("jenjang = ANY(%s)")
        params.append(jenjang)

    if fakultas:
        clauses.append("kode_fakultas = %s")
        params.append(fakultas)

    if no_ps:
        clauses.append("no_prodi = %s")
        params.append(int(no_ps))

    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    return where_sql, params


# ─── Phase 1: Stats overview ───────────────────────────────────────────────────

async def get_stats_overview(scope: UserScope, filters: "AkademikQueryFilters") -> dict | None:
    """
    Agregat lintas prodi/semester yang lolos filter — satu baris hasil.
    RLS aktif via PsycopgExecutor; filter spasial dari client hanya relevan
    untuk role yang tidak locked (lihat resolve_spatial_filter di router).
    """
    where_sql, params = build_filter_clause(
        filters.tahun_ajaran, filters.semester, filters.jenjang,
        filters.fakultas, filters.no_ps,
    )

    sql = f"""
        SELECT
            COALESCE(SUM(jumlah_kelas), 0)               AS jumlah_kelas,
            COALESCE(SUM(jumlah_matkul_aktif), 0)         AS jumlah_matkul_aktif,
            COALESCE(SUM(jumlah_dosen_aktif), 0)          AS jumlah_dosen_aktif,
            COALESCE(SUM(jumlah_mahasiswa_aktif), 0)      AS jumlah_mahasiswa_aktif,
            ROUND(AVG(avg_pct_kehadiran_dosen)::numeric, 2)     AS avg_pct_kehadiran_dosen,
            ROUND(AVG(avg_pct_kehadiran_mahasiswa)::numeric, 2) AS avg_pct_kehadiran_mahasiswa,
            ROUND(AVG(avg_ip_akhir_mahasiswa)::numeric, 2)      AS avg_ip_akhir_mahasiswa
        FROM analitik.v_akademik_statistik_prodi
        {where_sql}
    """
    result = await _executor.execute(sql, scope, params)

    if result.error:
        logger.error(
            "get_stats_overview error (user_id=%s role=%s): %s",
            scope.user_id, scope.role, result.error,
        )
        return None

    return result.rows[0] if result.rows else None
