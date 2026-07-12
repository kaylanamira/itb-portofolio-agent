# api/services/akademik.py

import asyncio
import logging

from core.database     import get_db_connection
from core.scope        import UserScope, UserRole
from core.sql_executor import PsycopgExecutor
from api.schemas.dashboard_akademik import AkademikQueryFilters
from api.services.akademik_constants import (
    SEMESTER_MAP, STRATA_LABEL, STRATA_ORDER,
    KODE_GRUP_TO_COL, VALID_KODE_GRUP,
    METRIC_TO_EXPR, VALID_RANKING_METRIC,
    KOMENTAR_SOURCE,
)
from api.services.akademik_scope_rules import is_faculty_level, period_label

logger    = logging.getLogger(__name__)
_executor = PsycopgExecutor()


# ─── Filter options ────────────────────────────────────────────────

# GET /api/dashboard/akademik/filter-options
async def get_tahun_ajaran_tersedia(scope: UserScope) -> list[str]:
    sql = """
        SELECT tahun_ajaran, MAX(tahun) AS tahun_max
        FROM analitik.v_akademik_statistik_prodi
        GROUP BY tahun_ajaran ORDER BY tahun_max DESC
    """
    result = await _executor.execute(sql, scope)
    if result.error:
        logger.error("get_tahun_ajaran_tersedia (user=%s): %s", scope.user_id, result.error)
        return []
    return [row["tahun_ajaran"] for row in result.rows]


# GET /api/dashboard/akademik/filter-options
async def get_semester_tersedia(scope: UserScope) -> list[dict]:
    sql = "SELECT DISTINCT semester FROM analitik.v_akademik_statistik_prodi ORDER BY semester"
    result = await _executor.execute(sql, scope)
    if result.error:
        logger.error("get_semester_tersedia (user=%s): %s", scope.user_id, result.error)
        return []
    return [
        {
            "value": str(row["semester"]),
            "label": SEMESTER_MAP.get(row["semester"], f"Semester {row['semester']}"),
        }
        for row in result.rows
    ]


# GET /api/dashboard/akademik/filter-options
async def get_fakultas_options(scope: UserScope) -> list[dict]:
    role, kd_fak = scope.role, scope.active_role.kd_fak or ""
    async with get_db_connection() as conn:
        if role in (UserRole.ADMIN, UserRole.DIREKTORAT):
            cur = await conn.execute(
                "SELECT kd_fak, nama->>'id' AS nama_id FROM utama.fakultas WHERE active=true ORDER BY weight"
            )
        else:
            cur = await conn.execute(
                "SELECT kd_fak, nama->>'id' AS nama_id FROM utama.fakultas WHERE active=true AND kd_fak=%s ORDER BY weight",
                [kd_fak],
            )
        rows = await cur.fetchall()
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in rows]


# GET /api/dashboard/akademik/filter-options
async def get_prodi_options(scope: UserScope) -> list[dict]:
    role, kd_fak, no_ps = scope.role, scope.active_role.kd_fak or "", scope.active_role.no_ps
    async with get_db_connection() as conn:
        if role in (UserRole.ADMIN, UserRole.DIREKTORAT):
            cur = await conn.execute(
                "SELECT no_ps,kd_ps,kd_fak,kd_strata,nama->>'id' AS nama_id FROM utama.program_studi WHERE active=true ORDER BY kd_fak,kd_strata,kd_ps"
            )
        elif role in (UserRole.DEKAN, UserRole.JAJARAN_DEKANAT):
            cur = await conn.execute(
                "SELECT no_ps,kd_ps,kd_fak,kd_strata,nama->>'id' AS nama_id FROM utama.program_studi WHERE active=true AND kd_fak=%s ORDER BY kd_strata,kd_ps",
                [kd_fak],
            )
        else:
            if no_ps is None:
                logger.warning("get_prodi_options: no_ps None role=%s user=%s", role, scope.user_id)
                return []
            cur = await conn.execute(
                "SELECT no_ps,kd_ps,kd_fak,kd_strata,nama->>'id' AS nama_id FROM utama.program_studi WHERE active=true AND no_ps=%s",
                [no_ps],
            )
        rows = await cur.fetchall()
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in rows]


# GET /api/dashboard/akademik/filter-options
def build_prodi_label(nama_id: str, kd_strata: str) -> str:
    return f"{nama_id} ({STRATA_LABEL.get(kd_strata, kd_strata)})"


# GET /api/dashboard/akademik/filter-options
def derive_jenjang_options(prodi_rows: list[dict]) -> list[dict]:
    kode_strata_unik = set(row["kd_strata"] for row in prodi_rows)
    kode_valid = [ks for ks in kode_strata_unik if ks in STRATA_LABEL]
    kode_terurut = sorted(kode_valid, key=lambda x: STRATA_ORDER.get(x, 99))

    return [{"value": ks, "label": STRATA_LABEL[ks]} for ks in kode_terurut]

# GET /api/dashboard/akademik/filter-options
# periode akademik default : periode akademik (tahun_ajaran, semester) terbaru
# pake v_akademik_statistik_prodi karena filter butuh tahu periode mana yang paling baru untuk prodi/fakultas tertentu.
async def resolve_default_period(
    scope: UserScope, fakultas: list[str] | None, no_ps: list[str] | None,
) -> tuple[str, int] | None:
    clauses = []
    params  = []
    if fakultas:
        clauses.append("kode_fakultas = ANY(%s)")
        params.append(fakultas)
    if no_ps:
        clauses.append("no_prodi = ANY(%s)")
        params.append([int(x) for x in no_ps])
    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""

    sql = f"""
        SELECT tahun_ajaran, semester
        FROM analitik.v_akademik_statistik_prodi {where_sql}
        ORDER BY tahun_ajaran DESC, semester DESC
        LIMIT 1
    """
    result = await _executor.execute(sql, scope, params)
    if result.error or not result.rows:
        if result.error:
            logger.error("resolve_default_period (user=%s): %s", scope.user_id, result.error)
        return None
    row = result.rows[0]
    return row["tahun_ajaran"], row["semester"]


# ─── Phase 1: Stats overview ──────────────────────────────────────────────────

# GET /api/dashboard/akademik/stats-overview
async def get_stats_overview(
    scope: UserScope, filters: AkademikQueryFilters,
    fakultas: list[str] | None, no_ps: list[str] | None,
) -> dict | None:
    clauses = []
    params  = []

    if filters.jenjang:
        clauses.append("jenjang = ANY(%s)")
        params.append(filters.jenjang)
    if fakultas:
        clauses.append("kode_fakultas = ANY(%s)")
        params.append(fakultas)
    if  no_ps:
        clauses.append("no_prodi = ANY(%s)")
        params.append([int(x) for x in no_ps])
    if filters.tahun_ajaran:
        clauses.append("tahun_ajaran = %s")
        params.append(filters.tahun_ajaran)
    if filters.semester:
        clauses.append("semester = ANY(%s)")
        params.append(filters.semester)
    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""

    sql = f"""
        SELECT
            COALESCE(SUM(jumlah_kelas),           0) AS jumlah_kelas,
            COALESCE(SUM(jumlah_matkul_aktif),    0) AS jumlah_matkul_aktif,
            COALESCE(SUM(jumlah_dosen_aktif),     0) AS jumlah_dosen_aktif,
            COALESCE(SUM(jumlah_mahasiswa_aktif), 0) AS jumlah_mahasiswa_aktif,
            ROUND(SUM(jumlah_kelas)::numeric / NULLIF(SUM(jumlah_matkul_aktif),0), 2) AS avg_kelas_per_matkul
        FROM analitik.v_akademik_statistik_prodi {where_sql}
    """
    result = await _executor.execute(sql, scope, params)
    if result.error:
        logger.error("get_stats_overview (user=%s): %s", scope.user_id, result.error)
        return None
    return result.rows[0] if result.rows else None


# ─── Phase 2: Attendance ──────────────────────────────────────────────────────

# GET /api/dashboard/akademik/attendance
async def get_attendance(
    scope: UserScope, filters: AkademikQueryFilters,
    fakultas: list[str] | None, no_ps: list[str] | None,
) -> list[dict]:
    is_fak = is_faculty_level(scope)

    # Klausa untuk CTE base (filter entitas: jenjang/fakultas/no_ps)
    base_clauses = []
    base_params  = []
    if filters.jenjang:
        base_clauses.append("jenjang = ANY(%s)")
        base_params.append(filters.jenjang)
    if fakultas:
        base_clauses.append("kode_fakultas = ANY(%s)")
        base_params.append(fakultas)
    if not is_fak and no_ps:
        base_clauses.append("no_prodi = ANY(%s)")
        base_params.append([int(x) for x in no_ps])
    base_where = f"WHERE {' AND '.join(base_clauses)}" if base_clauses else ""

    # Klausa untuk outer query (filter periode: tahun_ajaran/semester)
    outer_clauses = []
    outer_params  = []
    if filters.tahun_ajaran:
        outer_clauses.append("tahun_ajaran = %s")
        outer_params.append(filters.tahun_ajaran)
    if filters.semester:
        outer_clauses.append("semester = ANY(%s)")
        outer_params.append(filters.semester)
    outer_where = f"WHERE {' AND '.join(outer_clauses)}" if outer_clauses else ""

    all_params = base_params + outer_params

    if is_fak:
        sql = f"""
            WITH base AS (
                SELECT kode_fakultas, nama_fakultas_id, semester, tahun, tahun_ajaran,
                       AVG(avg_pct_kehadiran_dosen)    AS kehadiran_dosen,
                       AVG(avg_pct_kehadiran_mahasiswa) AS kehadiran_mahasiswa
                FROM analitik.v_akademik_statistik_prodi {base_where}
                GROUP BY kode_fakultas, nama_fakultas_id, semester, tahun, tahun_ajaran
            ),
            with_prev AS (
                SELECT kode_fakultas AS kode, nama_fakultas_id AS label,
                       kehadiran_dosen, kehadiran_mahasiswa, semester, tahun, tahun_ajaran,
                       LAG(kehadiran_dosen)     OVER w AS prev_kehadiran_dosen,
                       LAG(kehadiran_mahasiswa) OVER w AS prev_kehadiran_mahasiswa,
                       LAG(tahun_ajaran)        OVER w AS prev_tahun_ajaran,
                       LAG(semester)            OVER w AS prev_semester
                FROM base WINDOW w AS (PARTITION BY kode_fakultas ORDER BY tahun_ajaran, semester)
            )
            SELECT * FROM with_prev {outer_where}
            ORDER BY kehadiran_dosen DESC NULLS LAST
        """
    else:
        sql = f"""
            WITH base AS (
                SELECT no_prodi, kode_prodi, nama_prodi_id AS label, jenjang, semester, tahun, tahun_ajaran,
                       avg_pct_kehadiran_dosen    AS kehadiran_dosen,
                       avg_pct_kehadiran_mahasiswa AS kehadiran_mahasiswa
                FROM analitik.v_akademik_statistik_prodi {base_where}
            ),
            with_prev AS (
                SELECT no_prodi, kode_prodi, label, jenjang,
                       kehadiran_dosen, kehadiran_mahasiswa, semester, tahun, tahun_ajaran,
                       LAG(kehadiran_dosen)     OVER w AS prev_kehadiran_dosen,
                       LAG(kehadiran_mahasiswa) OVER w AS prev_kehadiran_mahasiswa,
                       LAG(tahun_ajaran)        OVER w AS prev_tahun_ajaran,
                       LAG(semester)            OVER w AS prev_semester
                FROM base WINDOW w AS (PARTITION BY no_prodi ORDER BY tahun_ajaran, semester)
            )
            SELECT * FROM with_prev {outer_where}
            ORDER BY kehadiran_dosen DESC NULLS LAST
        """

    result = await _executor.execute(sql, scope, all_params)
    if result.error:
         logger.error("get_attendance (user=%s): %s", scope.user_id, result.error)
         return []
    if is_fak:
         return result.rows
    return [
        {**row, "kode": f"{row['kode_prodi']} ({row['no_prodi']})",
         "label": build_prodi_label(row["label"], row["jenjang"])}
         for row in result.rows
     ]


# ─── Phase 3: Skor Pertanyaan ─────────────────────────────────────────────────

# GET /api/dashboard/akademik/skor-pertanyaan
async def get_skor_pertanyaan(
    scope: UserScope, filters: AkademikQueryFilters,
    fakultas: list[str] | None, no_ps: list[str] | None, kode_grup: str,
) -> list[dict]:
    col    = KODE_GRUP_TO_COL[kode_grup]
    is_fak = is_faculty_level(scope)

    base_clauses = []
    base_params  = []
    if filters.jenjang:
        base_clauses.append("jenjang = ANY(%s)")
        base_params.append(filters.jenjang)
    if fakultas:
        base_clauses.append("kode_fakultas = ANY(%s)")
        base_params.append(fakultas)
    if not is_fak and no_ps:
        base_clauses.append("no_prodi = ANY(%s)")
        base_params.append([int(x) for x in no_ps])
    base_where = f"WHERE {' AND '.join(base_clauses)}" if base_clauses else ""

    outer_clauses = []
    outer_params  = []
    if filters.tahun_ajaran:
        outer_clauses.append("tahun_ajaran = %s")
        outer_params.append(filters.tahun_ajaran)
    if filters.semester:
        outer_clauses.append("semester = ANY(%s)")
        outer_params.append(filters.semester)
    outer_where = f"WHERE {' AND '.join(outer_clauses)}" if outer_clauses else ""

    all_params = base_params + outer_params

    if is_fak:
        sql = f"""
            WITH base AS (
                SELECT kode_fakultas, nama_fakultas_id, semester, tahun, tahun_ajaran,
                       AVG({col}) AS skor
                FROM analitik.v_akademik_statistik_prodi {base_where}
                GROUP BY kode_fakultas, nama_fakultas_id, semester, tahun, tahun_ajaran
            ),
            with_prev AS (
                SELECT kode_fakultas AS kode, nama_fakultas_id AS label,
                       skor, semester, tahun, tahun_ajaran,
                       LAG(skor)        OVER w AS prev_skor,
                       LAG(tahun_ajaran) OVER w AS prev_tahun_ajaran,
                       LAG(semester)    OVER w AS prev_semester
                FROM base WINDOW w AS (PARTITION BY kode_fakultas ORDER BY tahun_ajaran, semester)
            )
            SELECT * FROM with_prev {outer_where} ORDER BY skor DESC NULLS LAST
        """
    else:
        sql = f"""
            WITH base AS (
                SELECT no_prodi, kode_prodi, nama_prodi_id AS label, jenjang, semester, tahun, tahun_ajaran,
                       {col} AS skor
                FROM analitik.v_akademik_statistik_prodi {base_where}
            ),
            with_prev AS (
                SELECT no_prodi, kode_prodi, label, jenjang,
                       skor, semester, tahun, tahun_ajaran,
                       LAG(skor)        OVER w AS prev_skor,
                       LAG(tahun_ajaran) OVER w AS prev_tahun_ajaran,
                       LAG(semester)    OVER w AS prev_semester
                FROM base WINDOW w AS (PARTITION BY no_prodi ORDER BY tahun_ajaran, semester)
            )
            SELECT * FROM with_prev {outer_where} ORDER BY skor DESC NULLS LAST
        """

    result = await _executor.execute(sql, scope, all_params)
    if result.error:
         logger.error("get_skor_pertanyaan kode_grup=%s (user=%s): %s", kode_grup, scope.user_id, result.error)
         return []
    if is_fak:
         return result.rows
    return [
        {**row, "kode": f"{row['kode_prodi']} ({row['no_prodi']})",
        "label": build_prodi_label(row["label"], row["jenjang"])}
        for row in result.rows
     ]


# ─── Phase 4a: Grade Distribution ─────────────────────────────────────────────

# GET /api/dashboard/akademik/grade-distribution
async def get_grade_distribution(
    scope: UserScope, filters: AkademikQueryFilters,
    fakultas: list[str] | None, no_ps: list[str] | None,
) -> list[dict]:
    is_fak = is_faculty_level(scope)

    clauses = []
    params  = []
    if filters.jenjang:
        clauses.append("jenjang = ANY(%s)")
        params.append(filters.jenjang)
    if fakultas:
        clauses.append("kode_fakultas = ANY(%s)")
        params.append(fakultas)
    if no_ps:
        clauses.append("no_prodi = ANY(%s)")
        params.append([int(x) for x in no_ps])
    if filters.tahun_ajaran:
        clauses.append("tahun_ajaran = %s")
        params.append(filters.tahun_ajaran)
    if filters.semester:
        clauses.append("semester = ANY(%s)")
        params.append(filters.semester)
    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""

    if is_fak:
        denom = "NULLIF(SUM(total_mahasiswa_dinilai), 0)"
        pct   = lambda col: f"ROUND(SUM({col})::numeric * 100 / {denom}, 2)"
        lulus_ac = ("SUM(total_jumlah_a + total_jumlah_ab + total_jumlah_b "
                    "+ total_jumlah_bc + total_jumlah_c + total_jumlah_pass)")
        lulus_ad = ("SUM(total_jumlah_a + total_jumlah_ab + total_jumlah_b "
                    "+ total_jumlah_bc + total_jumlah_c + total_jumlah_d + total_jumlah_pass)")
        sql = f"""
            SELECT kode_fakultas AS kode, nama_fakultas_id AS label,
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
                   ROUND({lulus_ac}::numeric * 100 / {denom}, 2) AS dist_pct_lulus_a_c,
                   ROUND({lulus_ad}::numeric * 100 / {denom}, 2) AS dist_pct_lulus_a_d,
                   COALESCE(SUM(total_mahasiswa_dinilai), 0)::integer AS total_mahasiswa,
                   ROUND(AVG(avg_ip_akhir_mahasiswa)::numeric, 2)    AS avg_ip
            FROM analitik.v_akademik_statistik_prodi {where_sql}
            GROUP BY kode_fakultas, nama_fakultas_id
            ORDER BY dist_pct_a DESC NULLS LAST
        """
    else:
        sql = f"""
            SELECT no_prodi, kode_prodi, nama_prodi_id AS label, jenjang,
                   dist_pct_a, dist_pct_ab, dist_pct_b, dist_pct_bc, dist_pct_c,
                   dist_pct_d, dist_pct_e, dist_pct_t, dist_pct_pass, dist_pct_fail,
                   dist_pct_lulus_a_c, dist_pct_lulus_a_d,
                   COALESCE(total_mahasiswa_dinilai, 0)::integer AS total_mahasiswa,
                   ROUND(avg_ip_akhir_mahasiswa::numeric, 2)     AS avg_ip
            FROM analitik.v_akademik_statistik_prodi {where_sql}
            ORDER BY dist_pct_a DESC NULLS LAST
        """

    result = await _executor.execute(sql, scope, params)
    if result.error:
        logger.error("get_grade_distribution (user=%s): %s", scope.user_id, result.error)
        return []
    if is_fak:
        return result.rows
    return [
        {**row, "kode": f"{row['kode_prodi']} ({row['no_prodi']})",
        "label": build_prodi_label(row["label"], row["jenjang"])}
        for row in result.rows
    ]


# ─── Phase 4b: Grade Trend ────────────────────────────────────────────────────

# GET /api/dashboard/akademik/grade-trend
async def get_grade_trend(
    scope: UserScope, filters: AkademikQueryFilters,
    fakultas: list[str] | None, no_ps: list[str] | None, n_semester: int,
) -> list[dict]:
    clauses = []
    params  = []
    if filters.jenjang:
        clauses.append("jenjang = ANY(%s)")
        params.append(filters.jenjang)
    if fakultas:
        clauses.append("kode_fakultas = ANY(%s)")
        params.append(fakultas)
    if no_ps:
        clauses.append("no_prodi = ANY(%s)")
        params.append([int(x) for x in no_ps])
    if filters.tahun_ajaran:
        clauses.append("tahun_ajaran <= %s")   # ceiling, bukan equality
        params.append(filters.tahun_ajaran)
    if filters.semester:
        clauses.append("semester = ANY(%s)")
        params.append(filters.semester)
    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""

    lulus_ac = ("SUM(total_jumlah_a + total_jumlah_ab + total_jumlah_b "
                "+ total_jumlah_bc + total_jumlah_c + total_jumlah_pass)")
    denom    = "NULLIF(SUM(total_mahasiswa_dinilai), 0)"

    sql = f"""
        SELECT tahun_ajaran, semester, tahun,
               ROUND(AVG(avg_skor_overall)::numeric, 2)    AS avg_skor_overall,
               ROUND(AVG(avg_skor_capaian)::numeric, 2)    AS avg_skor_capaian,
               ROUND(AVG(avg_skor_pelaksanaan)::numeric, 2) AS avg_skor_pelaksanaan,
               ROUND(AVG(avg_skor_q28)::numeric, 2) AS avg_skor_q28,
               ROUND(SUM(total_jumlah_a)::numeric * 100 / {denom}, 2) AS dist_pct_a,
               ROUND({lulus_ac}::numeric * 100 / {denom}, 2)          AS dist_pct_lulus_a_c,
               COALESCE(SUM(total_mahasiswa_dinilai), 0)::integer      AS total_mahasiswa
        FROM analitik.v_akademik_statistik_prodi {where_sql}
        GROUP BY tahun_ajaran, semester, tahun
        ORDER BY tahun_ajaran DESC, semester DESC
        LIMIT %s
    """
    result = await _executor.execute(sql, scope, params + [n_semester])
    if result.error:
        logger.error("get_grade_trend (user=%s): %s", scope.user_id, result.error)
        return []
    return list(reversed(result.rows))


# ─── Phase 5: Skor Heatmap ────────────────────────────────────────────────────

# GET /api/dashboard/akademik/skor-heatmap
async def get_skor_heatmap(
    scope: UserScope, filters: AkademikQueryFilters,
    fakultas: list[str] | None, no_ps: list[str] | None,
) -> list[dict]:
    is_fak = is_faculty_level(scope)

    clauses = []
    params  = []
    if filters.jenjang:
        clauses.append("jenjang = ANY(%s)")
        params.append(filters.jenjang)
    if fakultas:
        clauses.append("kode_fakultas = ANY(%s)")
        params.append(fakultas)
    if no_ps:
        clauses.append("no_prodi = ANY(%s)")
        params.append([int(x) for x in no_ps])
    if filters.tahun_ajaran:
        clauses.append("tahun_ajaran = %s")
        params.append(filters.tahun_ajaran)
    if filters.semester:
        clauses.append("semester = ANY(%s)")
        params.append(filters.semester)
    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""

    Q = ["q21","q22","q23","q24","q25","q26","q27","q28","q29","q30","q35","q37"]

    if is_fak:
        q_sel = ",\n               ".join(
            f"ROUND(AVG(avg_skor_{q})::numeric, 2) AS avg_skor_{q}" for q in Q
        )
        sql = f"""
            SELECT kode_fakultas AS kode, nama_fakultas_id AS label, {q_sel}
            FROM analitik.v_akademik_statistik_prodi {where_sql}
            GROUP BY kode_fakultas, nama_fakultas_id ORDER BY kode_fakultas
        """
    else:
        q_sel = ", ".join(f"avg_skor_{q}" for q in Q)
        sql = f"""
            SELECT no_prodi, kode_prodi, nama_prodi_id AS label, jenjang, {q_sel}
            FROM analitik.v_akademik_statistik_prodi {where_sql}
            ORDER BY nama_prodi_id
        """

    result = await _executor.execute(sql, scope, params)
    if result.error:
         logger.error("get_skor_heatmap (user=%s): %s", scope.user_id, result.error)
         return []
    if is_fak:
         return result.rows
    return [
        {**row, "kode": f"{row['kode_prodi']} ({row['no_prodi']})",
        "label": build_prodi_label(row["label"], row["jenjang"])}
        for row in result.rows
     ]


# ─── Phase B: Grading Comp ────────────────────────────────────────────────────

# GET /api/dashboard/akademik/grading-comp
async def get_grading_comp(
    scope: UserScope, filters: AkademikQueryFilters,
    fakultas: list[str] | None, no_ps: list[str] | None,
) -> list[dict]:
    is_fak = is_faculty_level(scope)

    clauses = []
    params  = []
    if filters.jenjang:
        clauses.append("jenjang = ANY(%s)")
        params.append(filters.jenjang)
    if fakultas:
        clauses.append("kode_fakultas = ANY(%s)")
        params.append(fakultas)
    if no_ps:
        clauses.append("no_prodi = ANY(%s)")
        params.append([int(x) for x in no_ps])
    if filters.tahun_ajaran:
        clauses.append("tahun_ajaran = %s")
        params.append(filters.tahun_ajaran)
    if filters.semester:
        clauses.append("semester = ANY(%s)")
        params.append(filters.semester)
    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""

    if is_fak:
        sql = f"""
            SELECT kode_fakultas AS kode, MAX(nama_fakultas_id) AS label,
                   COUNT(*)::integer                               AS jumlah_kelas,
                   ROUND(AVG(bobot_uts)::numeric, 2)          AS avg_bobot_uts,
                   ROUND(AVG(bobot_uas)::numeric, 2)          AS avg_bobot_uas,
                   ROUND(AVG(bobot_tugas)::numeric, 2)        AS avg_bobot_tugas,
                   ROUND(AVG(bobot_kuis)::numeric, 2)         AS avg_bobot_kuis,
                   ROUND(AVG(bobot_praktikum)::numeric, 2)    AS avg_bobot_praktikum,
                   ROUND(AVG(bobot_projek)::numeric, 2)       AS avg_bobot_projek,
                   ROUND(AVG(bobot_partisipatif)::numeric, 2) AS avg_bobot_partisipatif
            FROM analitik.v_akademik_komponen_evaluasi_kelas
            {where_sql}
            GROUP BY kode_fakultas ORDER BY kode_fakultas
        """
    else:
        sql = f"""
            SELECT no_prodi, kode_prodi, MAX(nama_prodi_id) AS label, MAX(jenjang) AS jenjang,
                   COUNT(*)::integer                               AS jumlah_kelas,
                   ROUND(AVG(bobot_uts)::numeric, 2)          AS avg_bobot_uts,
                   ROUND(AVG(bobot_uas)::numeric, 2)          AS avg_bobot_uas,
                   ROUND(AVG(bobot_tugas)::numeric, 2)        AS avg_bobot_tugas,
                   ROUND(AVG(bobot_kuis)::numeric, 2)         AS avg_bobot_kuis,
                   ROUND(AVG(bobot_praktikum)::numeric, 2)    AS avg_bobot_praktikum,
                   ROUND(AVG(bobot_projek)::numeric, 2)       AS avg_bobot_projek,
                   ROUND(AVG(bobot_partisipatif)::numeric, 2) AS avg_bobot_partisipatif
            FROM analitik.v_akademik_komponen_evaluasi_kelas
            {where_sql}
            GROUP BY no_prodi, kode_prodi ORDER BY no_prodi
        """

    result = await _executor.execute(sql, scope, params)
    if result.error:
        logger.error("get_grading_comp (user=%s): %s", scope.user_id, result.error)
        return []
    if is_fak:
        return result.rows
    return [
        {**row, "kode": f"{row['kode_prodi']} ({row['no_prodi']})",
        "label": build_prodi_label(row["label"], row["jenjang"])}
        for row in result.rows
    ]


# ─── Phase C: Skor by SKS ─────────────────────────────────────────────────────

# GET /api/dashboard/akademik/skor-by-sks
async def get_skor_by_sks(
    scope: UserScope, filters: AkademikQueryFilters,
    fakultas: list[str] | None, no_ps: list[str] | None,
) -> list[dict]:
    clauses = ["skor_q28 IS NOT NULL"]
    params  = []
    if filters.jenjang:
        clauses.append("jenjang = ANY(%s)")
        params.append(filters.jenjang)
    if fakultas:
        clauses.append("kode_fakultas = ANY(%s)")
        params.append(fakultas)
    if no_ps:
        clauses.append("no_prodi = ANY(%s)")
        params.append([int(x) for x in no_ps])
    if filters.tahun_ajaran:
        clauses.append("tahun_ajaran = %s")
        params.append(filters.tahun_ajaran)
    if filters.semester:
        clauses.append("semester = ANY(%s)")
        params.append(filters.semester)
    where_sql = f"WHERE {' AND '.join(clauses)}"

    sql = f"""
        SELECT
            CASE WHEN sks <= 2 THEN '1-2 SKS'
                 WHEN sks = 3  THEN '3 SKS'
                 ELSE               '4+ SKS'
            END                                   AS sks_label,
            COUNT(*)::integer                     AS jumlah_kelas,
            ROUND(AVG(skor_q28)::numeric, 2)      AS avg_skor_q8
        FROM analitik.v_akademik_kelas
        {where_sql}
        GROUP BY sks_label
        ORDER BY MIN(sks)
    """
    result = await _executor.execute(sql, scope, params)
    if result.error:
        logger.error("get_skor_by_sks (user=%s): %s", scope.user_id, result.error)
        return []
    return result.rows


# ─── Phase D: Komentar Mentah ─────────────────────────────────────────────────

# GET /api/dashboard/akademik/komentar-mentah
async def get_komentar_mentah(
    scope:     UserScope,
    filters:   AkademikQueryFilters,
    sumber:    str,
    page:      int,
    page_size: int,
    fakultas:  list[str] | None,
    no_ps:     list[str] | None,
) -> tuple[list[dict], int]:
    src      = KOMENTAR_SOURCE[sumber]
    view     = src["view"]
    teks_col = src["teks_col"]

    clauses = [src["null_filter"]]
    params  = []
    if filters.jenjang:
        clauses.append("jenjang = ANY(%s)")
        params.append(filters.jenjang)
    if fakultas:
        clauses.append("kode_fakultas = ANY(%s)")
        params.append(fakultas)
    if no_ps:
        clauses.append("no_prodi = ANY(%s)")
        params.append([int(x) for x in no_ps])
    if filters.tahun_ajaran:
        clauses.append("tahun_ajaran = %s")
        params.append(filters.tahun_ajaran)
    if filters.semester:
        clauses.append("semester = ANY(%s)")
        params.append(filters.semester)
    where_sql = f"WHERE {' AND '.join(clauses)}"

    offset = (page - 1) * page_size

    count_sql = f"SELECT COUNT(*) AS total FROM {view} {where_sql}"
    data_sql  = f"""
        SELECT kelas_id, kode_matkul, nama_matkul_id,
               kode_prodi, nama_prodi_id, kode_fakultas,
               tahun_ajaran, semester,
               {teks_col} AS teks
        FROM   {view}
        {where_sql}
        ORDER  BY {src["order"]}
        LIMIT  %s OFFSET %s
    """

    count_result, data_result = await asyncio.gather(
        _executor.execute(count_sql, scope, params),
        _executor.execute(data_sql,  scope, params + [page_size, offset]),
    )

    if count_result.error:
        logger.error("get_komentar_mentah count sumber=%s (user=%s): %s",
                     sumber, scope.user_id, count_result.error)
        return [], 0
    if data_result.error:
        logger.error("get_komentar_mentah data sumber=%s (user=%s): %s",
                     sumber, scope.user_id, data_result.error)
        return [], 0

    total = count_result.rows[0]["total"] if count_result.rows else 0
    return data_result.rows, int(total)


# ─── Phase 4c: Course Ranking ─────────────────────────────────────────────────

# GET /api/dashboard/akademik/course-ranking
async def get_course_ranking_top(
    scope: UserScope, filters: AkademikQueryFilters,
    fakultas: list[str] | None, no_ps: list[str] | None, limit: int, metric: str = "overall",
) -> list[dict]:
    return await _course_ranking_query(scope, filters, fakultas, no_ps, limit, desc=True, metric=metric)


# GET /api/dashboard/akademik/course-ranking
async def get_course_ranking_bottom(
    scope: UserScope, filters: AkademikQueryFilters,
    fakultas: list[str] | None, no_ps: list[str] | None, limit: int, metric: str = "overall",
) -> list[dict]:
    return await _course_ranking_query(scope, filters, fakultas, no_ps, limit, desc=False, metric=metric)


# GET /api/dashboard/akademik/course-ranking
async def _course_ranking_query(
    scope: UserScope, filters: AkademikQueryFilters,
    fakultas: list[str] | None, no_ps: list[str] | None, limit: int, desc: bool,
    metric: str = "overall",
) -> list[dict]:
    if metric not in VALID_RANKING_METRIC:
        raise ValueError(f"metric tidak valid: {metric}")
    skor_expr = METRIC_TO_EXPR[metric]

    base_clauses = []
    base_params  = []
    if filters.jenjang:
        base_clauses.append("jenjang = ANY(%s)")
        base_params.append(filters.jenjang)
    if fakultas:
        base_clauses.append("kode_fakultas = ANY(%s)")
        base_params.append(fakultas)
    if no_ps:
        base_clauses.append("no_prodi = ANY(%s)")
        base_params.append([int(x) for x in no_ps])
    base_where = f"WHERE {' AND '.join(base_clauses)}" if base_clauses else ""

    outer_clauses = ["skor IS NOT NULL"]
    outer_params  = []
    if filters.tahun_ajaran:
        outer_clauses.append("tahun_ajaran = %s")
        outer_params.append(filters.tahun_ajaran)
    if filters.semester:
        outer_clauses.append("semester = ANY(%s)")
        outer_params.append(filters.semester)
    outer_where = f"WHERE {' AND '.join(outer_clauses)}"

    order      = "DESC" if desc else "ASC"
    all_params = base_params + outer_params

    sql = f"""
        WITH all_periods AS (
            SELECT kode_matkul, nama_matkul_id, MAX(sks) AS sks,
                   kode_prodi, nama_prodi_id, kode_fakultas,
                   tahun_ajaran, tahun, semester,
                   COUNT(*)::integer AS jumlah_kelas,
                   SUM(jumlah_mahasiswa)::integer AS jumlah_mahasiswa,
                   ROUND(({skor_expr})::numeric, 2) AS skor
            FROM analitik.v_akademik_kelas {base_where}
            GROUP BY kode_matkul, nama_matkul_id, kode_prodi, nama_prodi_id,
                     kode_fakultas, tahun_ajaran, tahun, semester
        ),
        with_lag AS (
            SELECT *,
                LAG(skor)         OVER w AS prev_skor,
                LAG(tahun_ajaran) OVER w AS prev_tahun_ajaran,
                LAG(semester)     OVER w AS prev_semester
            FROM all_periods
            WINDOW w AS (PARTITION BY kode_matkul ORDER BY tahun_ajaran, semester)
        )
        SELECT * FROM with_lag {outer_where}
        ORDER BY skor {order}
        LIMIT %s
    """
    result = await _executor.execute(sql, scope, all_params + [limit])
    if result.error:
        logger.error("_course_ranking_query desc=%s (user=%s): %s", desc, scope.user_id, result.error)
        return []
    return result.rows