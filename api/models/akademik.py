"""
api/models/akademik.py

Fungsi query untuk dashboard akademik. Tidak ada HTTP / FastAPI di sini.

Konvensi:
  - Query ke analitik.v_* (RLS via SECURITY DEFINER)
    → gunakan PsycopgExecutor (otomatis set session variable sebelum query).
  - Query ke utama.* (master data, tanpa RLS)
    → gunakan get_db_connection() dengan WHERE eksplisit per scope.
"""

import asyncio
import logging
from core.database     import get_db_connection
from core.scope        import UserScope, UserRole
from core.sql_executor import PsycopgExecutor
from api.schemas.dashboard_akademik import AkademikQueryFilters

logger    = logging.getLogger(__name__)
_executor = PsycopgExecutor()

# Semester DB → (value_text, label)
_SEMESTER_MAP: dict[int, tuple[str, str]] = {
    1: ("ganjil", "Ganjil"),
    2: ("genap",  "Genap"),
    3: ("pendek", "Pendek"),
}
_SEMESTER_TO_DB: dict[str, int] = {v: k for k, (v, _) in _SEMESTER_MAP.items()}

_STRATA_LABEL: dict[str, str] = {
    "S1": "S1", "S2": "S2", "S3": "S3", "PR": "Profesi",
}
_STRATA_ORDER: dict[str, int] = {"S1": 0, "S2": 1, "S3": 2, "PR": 3}

# Phase 3: mapping kode_grup → kolom di v_akademik_statistik_prodi
_KODE_GRUP_TO_COL: dict[str, str] = {
    "capaian":            "avg_skor_capaian",
    "pelaksanaan":        "avg_skor_pelaksanaan",
    "sarana_prasarana":   "avg_skor_sarana_prasarana",
    "perilaku_mahasiswa": "avg_skor_perilaku_mahasiswa",
    "overall":            "avg_skor_overall",
    "q21": "avg_skor_q21", "q22": "avg_skor_q22", "q23": "avg_skor_q23",
    "q24": "avg_skor_q24", "q25": "avg_skor_q25", "q26": "avg_skor_q26",
    "q27": "avg_skor_q27", "q28": "avg_skor_q28", "q29": "avg_skor_q29",
    "q30": "avg_skor_q30", "q35": "avg_skor_q35", "q37": "avg_skor_q37",
}

VALID_KODE_GRUP: frozenset[str] = frozenset(_KODE_GRUP_TO_COL)


# ─── Shared helpers ───────────────────────────────────────────────────────────

def _is_faculty_level(scope: UserScope) -> bool:
    """Admin/direktorat → chart per-fakultas. Role lain → per-prodi."""
    return scope.role in (UserRole.ADMIN, UserRole.DIREKTORAT)


def _period_label(tahun_ajaran: str | None, semester: int | None) -> str | None:
    """Konversi (tahun_ajaran, semester_int) → "2023/2024 Ganjil"."""
    if tahun_ajaran is None or semester is None:
        return None
    _, label = _SEMESTER_MAP.get(int(semester), ("?", str(semester)))
    return f"{tahun_ajaran} {label}"


def _build_where(clauses: list[str]) -> str:
    return f"WHERE {' AND '.join(clauses)}" if clauses else ""


def _base_cte_clauses(
    jenjang:  list[str] | None,
    fakultas: str | None,
    no_ps:    str | None,
) -> tuple[list[str], list]:
    """
    Klausa untuk base CTE (sebelum LAG).
    Hanya jenjang + spasial — TANPA filter temporal (tahun/semester).
    Ini krusial: LAG harus dihitung atas seluruh riwayat entitas,
    baru temporal di-filter di outer WHERE.
    """
    clauses, params = [], []
    if jenjang:
        clauses.append("jenjang = ANY(%s)")
        params.append(jenjang)
    if fakultas:
        clauses.append("kode_fakultas = %s")
        params.append(fakultas)
    if no_ps:
        clauses.append("no_prodi = %s")
        params.append(int(no_ps))
    return clauses, params


def _temporal_clauses(filters: AkademikQueryFilters) -> tuple[list[str], list]:
    """Klausa temporal (tahun_ajaran, semester) untuk outer WHERE setelah LAG."""
    clauses, params = [], []
    if filters.tahun_ajaran:
        clauses.append("tahun_ajaran = %s")
        params.append(filters.tahun_ajaran)
    if filters.semester:
        db_val = _SEMESTER_TO_DB.get(filters.semester)
        if db_val:
            clauses.append("semester = %s")
            params.append(db_val)
    return clauses, params


# ─── Phase 0.5: Filter options ────────────────────────────────────────────────

async def get_tahun_ajaran_tersedia(scope: UserScope) -> list[str]:
    sql = """
        SELECT   tahun_ajaran, MAX(tahun) AS tahun_max
        FROM     analitik.v_akademik_statistik_prodi
        GROUP BY tahun_ajaran
        ORDER BY tahun_max DESC
    """
    result = await _executor.execute(sql, scope)
    if result.error:
        logger.error("get_tahun_ajaran_tersedia (user=%s role=%s): %s",
                     scope.user_id, scope.role, result.error)
        return []
    return [row["tahun_ajaran"] for row in result.rows]


async def get_semester_tersedia(scope: UserScope) -> list[dict]:
    sql = """
        SELECT DISTINCT semester
        FROM   analitik.v_akademik_statistik_prodi
        ORDER  BY semester
    """
    result = await _executor.execute(sql, scope)
    if result.error:
        logger.error("get_semester_tersedia (user=%s role=%s): %s",
                     scope.user_id, scope.role, result.error)
        return []
    options = []
    for row in result.rows:
        sem = row["semester"]
        if sem in _SEMESTER_MAP:
            value, label = _SEMESTER_MAP[sem]
            options.append({"value": value, "label": label})
        else:
            logger.warning("get_semester_tersedia: semester=%s tidak dikenal", sem)
            options.append({"value": str(sem), "label": f"Semester {sem}"})
    return options


async def get_fakultas_options(scope: UserScope) -> list[dict]:
    role, kd_fak = scope.role, scope.active_role.kd_fak or ""
    async with get_db_connection() as conn:
        if role in (UserRole.ADMIN, UserRole.DIREKTORAT):
            cur = await conn.execute(
                "SELECT kd_fak, nama->>'id' AS nama_id "
                "FROM utama.fakultas WHERE active = true ORDER BY weight"
            )
        else:
            cur = await conn.execute(
                "SELECT kd_fak, nama->>'id' AS nama_id "
                "FROM utama.fakultas WHERE active = true AND kd_fak = %s ORDER BY weight",
                [kd_fak],
            )
        rows = await cur.fetchall()
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in rows]


async def get_prodi_options(scope: UserScope) -> list[dict]:
    role, kd_fak, no_ps = scope.role, scope.active_role.kd_fak or "", scope.active_role.no_ps
    async with get_db_connection() as conn:
        if role in (UserRole.ADMIN, UserRole.DIREKTORAT):
            cur = await conn.execute(
                "SELECT no_ps, kd_ps, kd_fak, kd_strata, nama->>'id' AS nama_id "
                "FROM utama.program_studi WHERE active = true "
                "ORDER BY kd_fak, kd_strata, kd_ps"
            )
        elif role in (UserRole.DEKAN, UserRole.JAJARAN_DEKANAT):
            cur = await conn.execute(
                "SELECT no_ps, kd_ps, kd_fak, kd_strata, nama->>'id' AS nama_id "
                "FROM utama.program_studi WHERE active = true AND kd_fak = %s "
                "ORDER BY kd_strata, kd_ps",
                [kd_fak],
            )
        else:
            if no_ps is None:
                logger.warning("get_prodi_options: no_ps is None role=%s user=%s",
                               role, scope.user_id)
                return []
            cur = await conn.execute(
                "SELECT no_ps, kd_ps, kd_fak, kd_strata, nama->>'id' AS nama_id "
                "FROM utama.program_studi WHERE active = true AND no_ps = %s",
                [no_ps],
            )
        rows = await cur.fetchall()
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in rows]


def build_prodi_label(nama_id: str, kd_strata: str) -> str:
    return f"{nama_id} ({_STRATA_LABEL.get(kd_strata, kd_strata)})"


def derive_jenjang_options(prodi_rows: list[dict]) -> list[dict]:
    seen: set[str] = set()
    found: list[str] = []
    for row in prodi_rows:
        ks = row["kd_strata"]
        if ks not in seen and ks in _STRATA_LABEL:
            seen.add(ks)
            found.append(ks)
    found.sort(key=lambda x: _STRATA_ORDER.get(x, 99))
    return [{"value": ks, "label": _STRATA_LABEL[ks]} for ks in found]


# ─── Phase 1: Stats overview ──────────────────────────────────────────────────

def build_filter_clause(
    tahun_ajaran: str | None,
    semester:     str | None,
    jenjang:      list[str] | None,
    fakultas:     str | None,
    no_ps:        str | None,
) -> tuple[str, list]:
    clauses, params = [], []
    if tahun_ajaran:
        clauses.append("tahun_ajaran = %s"); params.append(tahun_ajaran)
    if semester:
        db_val = _SEMESTER_TO_DB.get(semester)
        if db_val is not None:
            clauses.append("semester = %s"); params.append(db_val)
        else:
            logger.warning("build_filter_clause: semester tidak dikenal: %s", semester)
    if jenjang:
        clauses.append("jenjang = ANY(%s)"); params.append(jenjang)
    if fakultas:
        clauses.append("kode_fakultas = %s"); params.append(fakultas)
    if no_ps:
        clauses.append("no_prodi = %s"); params.append(int(no_ps))
    return _build_where(clauses), params


async def get_stats_overview(
    scope: UserScope, filters: AkademikQueryFilters,
) -> dict | None:
    where_sql, params = build_filter_clause(
        filters.tahun_ajaran, filters.semester, filters.jenjang,
        filters.fakultas, filters.no_ps,
    )
    sql = f"""
        SELECT
            COALESCE(SUM(jumlah_kelas),           0) AS jumlah_kelas,
            COALESCE(SUM(jumlah_matkul_aktif),    0) AS jumlah_matkul_aktif,
            COALESCE(SUM(jumlah_dosen_aktif),     0) AS jumlah_dosen_aktif,
            COALESCE(SUM(jumlah_mahasiswa_aktif), 0) AS jumlah_mahasiswa_aktif,
            ROUND(
                SUM(jumlah_kelas)::numeric
                / NULLIF(SUM(jumlah_matkul_aktif), 0),
            2) AS avg_kelas_per_matkul
        FROM analitik.v_akademik_statistik_prodi
        {where_sql}
    """
    result = await _executor.execute(sql, scope, params)
    if result.error:
        logger.error("get_stats_overview (user=%s role=%s): %s",
                     scope.user_id, scope.role, result.error)
        return None
    return result.rows[0] if result.rows else None


# ─── Phase 2: Attendance ──────────────────────────────────────────────────────

async def get_attendance(
    scope:    UserScope,
    filters:  AkademikQueryFilters,
    fakultas: str | None,
    no_ps:    str | None,
) -> list[dict]:
    """
    Kehadiran dosen & mahasiswa per entitas + nilai prev periode sebelumnya.

    Pola CTE dua lapis:
      base      → filter spasial + jenjang (TANPA temporal) supaya LAG bisa
                  melihat seluruh riwayat entitas, bukan hanya periode terpilih.
      with_prev → tambah LAG per entitas secara kronologis.
      Final     → filter temporal di outer WHERE.
    """
    is_fak = _is_faculty_level(scope)

    # Klausa base CTE: jenjang + spasial
    b_cls, b_prm = _base_cte_clauses(
        filters.jenjang,
        fakultas if is_fak else fakultas,   # per-fak: kode_fakultas filter jika admin pilih 1 fak
        None if is_fak else no_ps,           # per-prodi: no_prodi jika kaprodi/filter prodi
    )
    base_where = _build_where(b_cls)

    # Klausa outer WHERE: temporal
    t_cls, t_prm = _temporal_clauses(filters)
    outer_where = _build_where(t_cls)

    all_params = b_prm + t_prm

    if is_fak:
        sql = f"""
            WITH base AS (
                SELECT kode_fakultas, nama_fakultas_id,
                       semester, tahun, tahun_ajaran,
                       AVG(avg_pct_kehadiran_dosen)     AS kehadiran_dosen,
                       AVG(avg_pct_kehadiran_mahasiswa)  AS kehadiran_mahasiswa
                FROM   analitik.v_akademik_statistik_prodi
                {base_where}
                GROUP BY kode_fakultas, nama_fakultas_id, semester, tahun, tahun_ajaran
            ),
            with_prev AS (
                SELECT kode_fakultas        AS kode,
                       nama_fakultas_id     AS label,
                       kehadiran_dosen, kehadiran_mahasiswa,
                       semester, tahun, tahun_ajaran,
                       LAG(kehadiran_dosen)     OVER w AS prev_kehadiran_dosen,
                       LAG(kehadiran_mahasiswa) OVER w AS prev_kehadiran_mahasiswa,
                       LAG(tahun_ajaran)        OVER w AS prev_tahun_ajaran,
                       LAG(semester)            OVER w AS prev_semester
                FROM base
                WINDOW w AS (PARTITION BY kode_fakultas ORDER BY tahun, semester)
            )
            SELECT * FROM with_prev {outer_where}
            ORDER BY kehadiran_dosen DESC NULLS LAST
        """
    else:
        sql = f"""
            WITH base AS (
                SELECT no_prodi, nama_prodi_id,
                       semester, tahun, tahun_ajaran,
                       avg_pct_kehadiran_dosen     AS kehadiran_dosen,
                       avg_pct_kehadiran_mahasiswa  AS kehadiran_mahasiswa
                FROM   analitik.v_akademik_statistik_prodi
                {base_where}
            ),
            with_prev AS (
                SELECT no_prodi::text   AS kode,
                       nama_prodi_id    AS label,
                       kehadiran_dosen, kehadiran_mahasiswa,
                       semester, tahun, tahun_ajaran,
                       LAG(kehadiran_dosen)     OVER w AS prev_kehadiran_dosen,
                       LAG(kehadiran_mahasiswa) OVER w AS prev_kehadiran_mahasiswa,
                       LAG(tahun_ajaran)        OVER w AS prev_tahun_ajaran,
                       LAG(semester)            OVER w AS prev_semester
                FROM base
                WINDOW w AS (PARTITION BY no_prodi ORDER BY tahun, semester)
            )
            SELECT * FROM with_prev {outer_where}
            ORDER BY kehadiran_dosen DESC NULLS LAST
        """

    result = await _executor.execute(sql, scope, all_params)
    if result.error:
        logger.error("get_attendance (user=%s role=%s): %s",
                     scope.user_id, scope.role, result.error)
        return []
    return result.rows


# ─── Phase 3: Skor Pertanyaan ─────────────────────────────────────────────────

async def get_skor_pertanyaan(
    scope:     UserScope,
    filters:   AkademikQueryFilters,
    fakultas:  str | None,
    no_ps:     str | None,
    kode_grup: str,
) -> list[dict]:
    """
    Skor rata-rata satu kelompok pertanyaan per entitas + LAG prev.
    Struktur CTE identik dengan get_attendance — hanya kolom skor yang berbeda.
    kode_grup sudah divalidasi di router sebelum masuk sini.
    """
    col = _KODE_GRUP_TO_COL[kode_grup]   # aman: sudah divalidasi router
    is_fak = _is_faculty_level(scope)

    b_cls, b_prm = _base_cte_clauses(
        filters.jenjang,
        fakultas if is_fak else fakultas,
        None if is_fak else no_ps,
    )
    base_where = _build_where(b_cls)

    t_cls, t_prm = _temporal_clauses(filters)
    outer_where = _build_where(t_cls)

    all_params = b_prm + t_prm

    if is_fak:
        # Nama kolom dari dict internal — aman untuk f-string
        sql = f"""
            WITH base AS (
                SELECT kode_fakultas, nama_fakultas_id,
                       semester, tahun, tahun_ajaran,
                       AVG({col}) AS skor
                FROM   analitik.v_akademik_statistik_prodi
                {base_where}
                GROUP BY kode_fakultas, nama_fakultas_id, semester, tahun, tahun_ajaran
            ),
            with_prev AS (
                SELECT kode_fakultas    AS kode,
                       nama_fakultas_id AS label,
                       skor, semester, tahun, tahun_ajaran,
                       LAG(skor)        OVER w AS prev_skor,
                       LAG(tahun_ajaran) OVER w AS prev_tahun_ajaran,
                       LAG(semester)    OVER w AS prev_semester
                FROM base
                WINDOW w AS (PARTITION BY kode_fakultas ORDER BY tahun, semester)
            )
            SELECT * FROM with_prev {outer_where}
            ORDER BY skor DESC NULLS LAST
        """
    else:
        sql = f"""
            WITH base AS (
                SELECT no_prodi, nama_prodi_id,
                       semester, tahun, tahun_ajaran,
                       {col} AS skor
                FROM   analitik.v_akademik_statistik_prodi
                {base_where}
            ),
            with_prev AS (
                SELECT no_prodi::text AS kode,
                       nama_prodi_id  AS label,
                       skor, semester, tahun, tahun_ajaran,
                       LAG(skor)        OVER w AS prev_skor,
                       LAG(tahun_ajaran) OVER w AS prev_tahun_ajaran,
                       LAG(semester)    OVER w AS prev_semester
                FROM base
                WINDOW w AS (PARTITION BY no_prodi ORDER BY tahun, semester)
            )
            SELECT * FROM with_prev {outer_where}
            ORDER BY skor DESC NULLS LAST
        """

    result = await _executor.execute(sql, scope, all_params)
    if result.error:
        logger.error("get_skor_pertanyaan kode_grup=%s (user=%s): %s",
                     kode_grup, scope.user_id, result.error)
        return []
    return result.rows


# ─── Phase 4a: Grade Distribution ────────────────────────────────────────────

async def get_grade_distribution(
    scope:    UserScope,
    filters:  AkademikQueryFilters,
    fakultas: str | None,
    no_ps:    str | None,
) -> list[dict]:
    """
    Distribusi nilai (A/AB/B/BC/C/D/E/T/Pass/Fail) per entitas.
    Tidak ada LAG — ini snapshot satu periode.

    Per-fakultas: hitung dari total_jumlah_* / total_mahasiswa_dinilai
                  (bukan AVG dist_pct_* — itu akan salah secara matematis).
    Per-prodi:    gunakan dist_pct_* yang sudah dihitung view.
    """
    is_fak = _is_faculty_level(scope)

    # Semua filter: spasial + jenjang + temporal sekaligus (tidak perlu LAG)
    where_sql, params = build_filter_clause(
        filters.tahun_ajaran, filters.semester, filters.jenjang,
        fakultas, no_ps,
    )

    if is_fak:
        # Denominatornya adalah total_mahasiswa_dinilai (sudah dikumpulkan per prodi valid)
        # SUM(total_jumlah_*) di level fakultas memberikan agregat yang matematis benar
        denom = "NULLIF(SUM(total_mahasiswa_dinilai), 0)"
        pct = lambda col: f"ROUND(SUM({col})::numeric * 100 / {denom}, 2)"
        lulus_ac_num = ("SUM(total_jumlah_a + total_jumlah_ab + total_jumlah_b "
                        "+ total_jumlah_bc + total_jumlah_c + total_jumlah_pass)")
        lulus_ad_num = ("SUM(total_jumlah_a + total_jumlah_ab + total_jumlah_b "
                        "+ total_jumlah_bc + total_jumlah_c + total_jumlah_d + total_jumlah_pass)")

        sql = f"""
            SELECT
                kode_fakultas    AS kode,
                nama_fakultas_id AS label,
                {pct('total_jumlah_a')}    AS dist_pct_a,
                {pct('total_jumlah_ab')}   AS dist_pct_ab,
                {pct('total_jumlah_b')}    AS dist_pct_b,
                {pct('total_jumlah_bc')}   AS dist_pct_bc,
                {pct('total_jumlah_c')}    AS dist_pct_c,
                {pct('total_jumlah_d')}    AS dist_pct_d,
                {pct('total_jumlah_e')}    AS dist_pct_e,
                {pct('total_jumlah_t')}    AS dist_pct_t,
                {pct('total_jumlah_pass')} AS dist_pct_pass,
                {pct('total_jumlah_fail')} AS dist_pct_fail,
                ROUND({lulus_ac_num}::numeric * 100 / {denom}, 2) AS dist_pct_lulus_a_c,
                ROUND({lulus_ad_num}::numeric * 100 / {denom}, 2) AS dist_pct_lulus_a_d,
                COALESCE(SUM(total_mahasiswa_dinilai), 0)::integer AS total_mahasiswa
            FROM analitik.v_akademik_statistik_prodi
            {where_sql}
            GROUP BY kode_fakultas, nama_fakultas_id
            ORDER BY dist_pct_a DESC NULLS LAST
        """
    else:
        sql = f"""
            SELECT
                no_prodi::text  AS kode,
                nama_prodi_id   AS label,
                dist_pct_a, dist_pct_ab, dist_pct_b, dist_pct_bc, dist_pct_c,
                dist_pct_d, dist_pct_e, dist_pct_t, dist_pct_pass, dist_pct_fail,
                dist_pct_lulus_a_c, dist_pct_lulus_a_d,
                COALESCE(total_mahasiswa_dinilai, 0)::integer AS total_mahasiswa
            FROM analitik.v_akademik_statistik_prodi
            {where_sql}
            ORDER BY dist_pct_a DESC NULLS LAST
        """

    result = await _executor.execute(sql, scope, params)
    if result.error:
        logger.error("get_grade_distribution (user=%s role=%s): %s",
                     scope.user_id, scope.role, result.error)
        return []
    return result.rows


# ─── Phase 4b: Grade Trend ────────────────────────────────────────────────────

async def get_grade_trend(
    scope:      UserScope,
    filters:    AkademikQueryFilters,
    fakultas:   str | None,
    no_ps:      str | None,
    n_semester: int,
) -> list[dict]:
    """
    Tren nilai N semester terakhir dari periode yang dipilih (scope-level aggregate).

    Tidak per-entity — ini satu deret waktu untuk seluruh scope (ITB, atau fakultas
    untuk dekan, atau prodi untuk kaprodi). Untuk line chart.

    Jika filters.tahun_ajaran diisi, hanya tampilkan semester ≤ tahun tsb.
    Jika tidak diisi, ambil N semester terbaru.
    """
    # Spatial + jenjang filter (tanpa temporal) untuk base data
    b_cls, b_prm = _base_cte_clauses(filters.jenjang, fakultas, no_ps)
    base_where = _build_where(b_cls)

    # Ceiling: hanya ambil periode s.d. tahun_ajaran yang dipilih
    ceiling_cls, ceiling_prm = [], []
    if filters.tahun_ajaran:
        ceiling_cls.append("tahun_ajaran <= %s")
        ceiling_prm.append(filters.tahun_ajaran)

    all_clauses = b_cls + ceiling_cls
    all_params  = b_prm + ceiling_prm + [n_semester]
    final_where = _build_where(all_clauses)

    lulus_ac_num = ("SUM(total_jumlah_a + total_jumlah_ab + total_jumlah_b "
                    "+ total_jumlah_bc + total_jumlah_c + total_jumlah_pass)")
    denom = "NULLIF(SUM(total_mahasiswa_dinilai), 0)"

    sql = f"""
        SELECT
            tahun_ajaran, semester, tahun,
            ROUND(AVG(avg_skor_overall)::numeric, 2) AS avg_skor_overall,
            ROUND(SUM(total_jumlah_a)::numeric * 100 / {denom}, 2) AS dist_pct_a,
            ROUND({lulus_ac_num}::numeric * 100 / {denom}, 2)      AS dist_pct_lulus_a_c,
            COALESCE(SUM(total_mahasiswa_dinilai), 0)::integer      AS total_mahasiswa
        FROM analitik.v_akademik_statistik_prodi
        {final_where}
        GROUP BY tahun_ajaran, semester, tahun
        ORDER BY tahun DESC, semester DESC
        LIMIT %s
    """

    result = await _executor.execute(sql, scope, all_params)
    if result.error:
        logger.error("get_grade_trend (user=%s role=%s): %s",
                     scope.user_id, scope.role, result.error)
        return []

    # Balik urutan: query ambil terbaru dulu (untuk LIMIT benar),
    # response ke frontend dalam urutan kronologis (terlama → terbaru)
    return list(reversed(result.rows))


# ─── Phase 4c: Course Ranking ─────────────────────────────────────────────────

async def get_course_ranking_top(
    scope:    UserScope,
    filters:  AkademikQueryFilters,
    fakultas: str | None,
    no_ps:    str | None,
    limit:    int,
) -> list[dict]:
    return await _course_ranking_query(scope, filters, fakultas, no_ps, limit, desc=True)


async def get_course_ranking_bottom(
    scope:    UserScope,
    filters:  AkademikQueryFilters,
    fakultas: str | None,
    no_ps:    str | None,
    limit:    int,
) -> list[dict]:
    return await _course_ranking_query(scope, filters, fakultas, no_ps, limit, desc=False)


async def _course_ranking_query(
    scope:    UserScope,
    filters:  AkademikQueryFilters,
    fakultas: str | None,
    no_ps:    str | None,
    limit:    int,
    desc:     bool,
) -> list[dict]:
    """
    Ranking mata kuliah berdasarkan avg_skor_overall untuk periode terpilih.

    Sumber: v_akademik_kelas (granularity per kelas, bukan per prodi).
    LAG per kode_matkul — 'prev' = periode sebelumnya MK itu diajarkan.

    Dua query terpisah (top & bottom) dijalankan paralel oleh pemanggil.
    """
    # Base CTE: semua periode (untuk LAG), filter spasial + jenjang
    b_cls, b_prm = [], []
    if filters.jenjang:
        b_cls.append("jenjang = ANY(%s)"); b_prm.append(filters.jenjang)
    if fakultas:
        b_cls.append("kode_fakultas = %s"); b_prm.append(fakultas)
    if no_ps:
        b_cls.append("no_prodi = %s"); b_prm.append(int(no_ps))

    base_where = _build_where(["avg_skor_overall IS NOT NULL"] + b_cls)

    # Outer: filter temporal
    t_cls, t_prm = _temporal_clauses(filters)
    outer_where = _build_where(t_cls)

    order = "DESC" if desc else "ASC"
    all_params = b_prm + t_prm + [limit]

    sql = f"""
        WITH all_periods AS (
            SELECT
                kode_matkul, nama_matkul_id,
                MAX(sks)         AS sks,
                kode_prodi, nama_prodi_id, kode_fakultas,
                tahun_ajaran, tahun, semester,
                COUNT(*)                                  AS jumlah_kelas,
                ROUND(AVG(avg_skor_overall)::numeric, 2)  AS avg_skor
            FROM analitik.v_akademik_kelas
            {base_where}
            GROUP BY kode_matkul, nama_matkul_id, kode_prodi, nama_prodi_id,
                     kode_fakultas, tahun_ajaran, tahun, semester
        ),
        with_lag AS (
            SELECT *,
                LAG(avg_skor)     OVER w AS prev_skor,
                LAG(tahun_ajaran) OVER w AS prev_tahun_ajaran,
                LAG(semester)     OVER w AS prev_semester
            FROM all_periods
            WINDOW w AS (PARTITION BY kode_matkul ORDER BY tahun, semester)
        )
        SELECT * FROM with_lag
        {outer_where}
        ORDER BY avg_skor {order} NULLS LAST
        LIMIT %s
    """

    result = await _executor.execute(sql, scope, all_params)
    if result.error:
        logger.error("_course_ranking_query desc=%s (user=%s): %s",
                     desc, scope.user_id, result.error)
        return []
    return result.rows


# ─── Phase 5: Skor Heatmap ───────────────────────────────────────────────────

async def get_skor_heatmap(
    scope:    UserScope,
    filters:  AkademikQueryFilters,
    fakultas: str | None,
    no_ps:    str | None,
) -> list[dict]:
    """
    12 skor pertanyaan per entitas untuk satu periode (snapshot, tanpa LAG).
    Per-fakultas: AVG setiap q-column across prodi dalam fakultas itu.
    Per-prodi: ambil langsung dari view.
    """
    is_fak = _is_faculty_level(scope)
    where_sql, params = build_filter_clause(
        filters.tahun_ajaran, filters.semester, filters.jenjang,
        fakultas, no_ps,
    )

    Q_COLS = ["q21","q22","q23","q24","q25","q26","q27","q28","q29","q30","q35","q37"]

    if is_fak:
        q_select = ",\n               ".join(
            f"ROUND(AVG(avg_skor_{q})::numeric, 2) AS avg_skor_{q}" for q in Q_COLS
        )
        sql = f"""
            SELECT kode_fakultas    AS kode,
                   nama_fakultas_id AS label,
                   {q_select}
            FROM analitik.v_akademik_statistik_prodi
            {where_sql}
            GROUP BY kode_fakultas, nama_fakultas_id
            ORDER BY kode_fakultas
        """
    else:
        q_select = ", ".join(f"avg_skor_{q}" for q in Q_COLS)
        sql = f"""
            SELECT no_prodi::text AS kode,
                   nama_prodi_id  AS label,
                   {q_select}
            FROM analitik.v_akademik_statistik_prodi
            {where_sql}
            ORDER BY nama_prodi_id
        """

    result = await _executor.execute(sql, scope, params)
    if result.error:
        logger.error("get_skor_heatmap (user=%s role=%s): %s",
                     scope.user_id, scope.role, result.error)
        return []
    return result.rows