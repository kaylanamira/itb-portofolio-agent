import asyncio
import logging
from core.database     import get_db_connection
from core.scope        import UserScope, UserRole
from core.sql_executor import PsycopgExecutor
from api.schemas.dashboard_akademik import AkademikQueryFilters
from api.services.akademik_helpers import (
    SEMESTER_MAP, STRATA_LABEL, STRATA_ORDER,
    KODE_GRUP_TO_COL, VALID_KODE_GRUP,
    METRIC_TO_EXPR, VALID_RANKING_METRIC,
    KOMENTAR_SOURCE,
    is_faculty_level, period_label, build_where, extend_where,
    base_cte_clauses, temporal_clauses, build_filter_clause,
    resolve_default_period,
)

logger    = logging.getLogger(__name__)
_executor = PsycopgExecutor()


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
    options = []
    for row in result.rows:
        sem = row["semester"]
        if sem in SEMESTER_MAP:
            value, label = SEMESTER_MAP[sem]
            options.append({"value": value, "label": label})
        else:
            options.append({"value": str(sem), "label": f"Semester {sem}"})
    return options


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
    seen: set[str] = set()
    found: list[str] = []
    for row in prodi_rows:
        ks = row["kd_strata"]
        if ks not in seen and ks in STRATA_LABEL:
            seen.add(ks); found.append(ks)
    found.sort(key=lambda x: STRATA_ORDER.get(x, 99))
    return [{"value": ks, "label": STRATA_LABEL[ks]} for ks in found]


# GET /api/dashboard/akademik/stats-overview
async def get_stats_overview(scope: UserScope, filters: AkademikQueryFilters) -> dict | None:
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
            ROUND(SUM(jumlah_kelas)::numeric / NULLIF(SUM(jumlah_matkul_aktif),0), 2) AS avg_kelas_per_matkul
        FROM analitik.v_akademik_statistik_prodi {where_sql}
    """
    result = await _executor.execute(sql, scope, params)
    if result.error:
        logger.error("get_stats_overview (user=%s): %s", scope.user_id, result.error)
        return None
    return result.rows[0] if result.rows else None


# GET /api/dashboard/akademik/attendance
async def get_attendance(
    scope: UserScope, filters: AkademikQueryFilters,
    fakultas: str | None, no_ps: str | None,
) -> list[dict]:
    is_fak = is_faculty_level(scope)
    b_cls, b_prm = base_cte_clauses(filters.jenjang, fakultas if is_fak else fakultas, None if is_fak else no_ps)
    t_cls, t_prm = temporal_clauses(filters)
    base_where  = build_where(b_cls)
    outer_where = build_where(t_cls)
    all_params  = b_prm + t_prm

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
                FROM base WINDOW w AS (PARTITION BY kode_fakultas ORDER BY tahun, semester)
            )
            SELECT * FROM with_prev {outer_where}
            ORDER BY kehadiran_dosen DESC NULLS LAST
        """
    else:
        sql = f"""
            WITH base AS (
                SELECT no_prodi, kode_prodi, nama_prodi_id, semester, tahun, tahun_ajaran,
                       avg_pct_kehadiran_dosen    AS kehadiran_dosen,
                       avg_pct_kehadiran_mahasiswa AS kehadiran_mahasiswa
                FROM analitik.v_akademik_statistik_prodi {base_where}
            ),
            with_prev AS (
                SELECT kode_prodi AS kode, nama_prodi_id AS label,
                       kehadiran_dosen, kehadiran_mahasiswa, semester, tahun, tahun_ajaran,
                       LAG(kehadiran_dosen)     OVER w AS prev_kehadiran_dosen,
                       LAG(kehadiran_mahasiswa) OVER w AS prev_kehadiran_mahasiswa,
                       LAG(tahun_ajaran)        OVER w AS prev_tahun_ajaran,
                       LAG(semester)            OVER w AS prev_semester
                FROM base WINDOW w AS (PARTITION BY no_prodi ORDER BY tahun, semester)
            )
            SELECT * FROM with_prev {outer_where}
            ORDER BY kehadiran_dosen DESC NULLS LAST
        """

    result = await _executor.execute(sql, scope, all_params)
    if result.error:
        logger.error("get_attendance (user=%s): %s", scope.user_id, result.error)
        return []
    return result.rows


# GET /api/dashboard/akademik/skor-pertanyaan
async def get_skor_pertanyaan(
    scope: UserScope, filters: AkademikQueryFilters,
    fakultas: str | None, no_ps: str | None, kode_grup: str,
) -> list[dict]:
    col = KODE_GRUP_TO_COL[kode_grup]
    is_fak = is_faculty_level(scope)
    b_cls, b_prm = base_cte_clauses(filters.jenjang, fakultas if is_fak else fakultas, None if is_fak else no_ps)
    t_cls, t_prm = temporal_clauses(filters)
    base_where  = build_where(b_cls)
    outer_where = build_where(t_cls)
    all_params  = b_prm + t_prm

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
                FROM base WINDOW w AS (PARTITION BY kode_fakultas ORDER BY tahun, semester)
            )
            SELECT * FROM with_prev {outer_where} ORDER BY skor DESC NULLS LAST
        """
    else:
        sql = f"""
            WITH base AS (
                SELECT no_prodi, kode_prodi, nama_prodi_id, semester, tahun, tahun_ajaran,
                       {col} AS skor
                FROM analitik.v_akademik_statistik_prodi {base_where}
            ),
            with_prev AS (
                SELECT kode_prodi AS kode, nama_prodi_id AS label,
                       skor, semester, tahun, tahun_ajaran,
                       LAG(skor)        OVER w AS prev_skor,
                       LAG(tahun_ajaran) OVER w AS prev_tahun_ajaran,
                       LAG(semester)    OVER w AS prev_semester
                FROM base WINDOW w AS (PARTITION BY no_prodi ORDER BY tahun, semester)
            )
            SELECT * FROM with_prev {outer_where} ORDER BY skor DESC NULLS LAST
        """

    result = await _executor.execute(sql, scope, all_params)
    if result.error:
        logger.error("get_skor_pertanyaan kode_grup=%s (user=%s): %s", kode_grup, scope.user_id, result.error)
        return []
    return result.rows


# GET /api/dashboard/akademik/grade-distribution
async def get_grade_distribution(
    scope: UserScope, filters: AkademikQueryFilters,
    fakultas: str | None, no_ps: str | None,
) -> list[dict]:
    is_fak = is_faculty_level(scope)
    where_sql, params = build_filter_clause(
        filters.tahun_ajaran, filters.semester, filters.jenjang, fakultas, no_ps,
    )

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
            SELECT kode_prodi AS kode, nama_prodi_id AS label,
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
    return result.rows


# GET /api/dashboard/akademik/grade-trend
async def get_grade_trend(
    scope: UserScope, filters: AkademikQueryFilters,
    fakultas: str | None, no_ps: str | None, n_semester: int,
) -> list[dict]:
    b_cls, b_prm = base_cte_clauses(filters.jenjang, fakultas, no_ps)
    ceiling_cls, ceiling_prm = [], []
    if filters.tahun_ajaran:
        ceiling_cls.append("tahun_ajaran <= %s")
        ceiling_prm.append(filters.tahun_ajaran)

    all_clauses = b_cls + ceiling_cls
    all_params  = b_prm + ceiling_prm + [n_semester]
    final_where = build_where(all_clauses)

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
        FROM analitik.v_akademik_statistik_prodi {final_where}
        GROUP BY tahun_ajaran, semester, tahun
        ORDER BY tahun DESC, semester DESC
        LIMIT %s
    """

    result = await _executor.execute(sql, scope, all_params)
    if result.error:
        logger.error("get_grade_trend (user=%s): %s", scope.user_id, result.error)
        return []
    return list(reversed(result.rows))


# GET /api/dashboard/akademik/skor-heatmap
async def get_skor_heatmap(
    scope: UserScope, filters: AkademikQueryFilters,
    fakultas: str | None, no_ps: str | None,
) -> list[dict]:
    is_fak = is_faculty_level(scope)
    where_sql, params = build_filter_clause(
        filters.tahun_ajaran, filters.semester, filters.jenjang, fakultas, no_ps,
    )
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
            SELECT kode_prodi AS kode, nama_prodi_id AS label, {q_sel}
            FROM analitik.v_akademik_statistik_prodi {where_sql}
            ORDER BY nama_prodi_id
        """

    result = await _executor.execute(sql, scope, params)
    if result.error:
        logger.error("get_skor_heatmap (user=%s): %s", scope.user_id, result.error)
        return []
    return result.rows


# GET /api/dashboard/akademik/grading-comp
async def get_grading_comp(
    scope: UserScope, filters: AkademikQueryFilters,
    fakultas: str | None, no_ps: str | None,
) -> list[dict]:
    is_fak = is_faculty_level(scope)
    where_sql, params = build_filter_clause(
        filters.tahun_ajaran, filters.semester, filters.jenjang, fakultas, no_ps,
    )

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
            SELECT kode_prodi AS kode, MAX(nama_prodi_id) AS label,
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
    return result.rows


# GET /api/dashboard/akademik/skor-by-sks
async def get_skor_by_sks(
    scope: UserScope, filters: AkademikQueryFilters,
    fakultas: str | None, no_ps: str | None,
) -> list[dict]:
    where_sql, params = build_filter_clause(
        filters.tahun_ajaran, filters.semester, filters.jenjang, fakultas, no_ps,
    )
    where_sql, params = extend_where(where_sql, params, "avg_skor_q28 IS NOT NULL")

    sql = f"""
        SELECT
            CASE WHEN sks <= 2 THEN '1-2 SKS'
                 WHEN sks = 3  THEN '3 SKS'
                 ELSE               '4+ SKS'
            END                                       AS sks_label,
            COUNT(*)::integer                         AS jumlah_kelas,
            ROUND(AVG(avg_skor_q28)::numeric, 2)     AS avg_skor_q8
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


# GET /api/dashboard/akademik/komentar-mentah
async def get_komentar_mentah(
    scope:     UserScope,
    filters:   AkademikQueryFilters,
    sumber:    str,
    page:      int,
    page_size: int,
    fakultas:  str | None,
    no_ps:     str | None,
) -> tuple[list[dict], int]:
    src        = KOMENTAR_SOURCE[sumber]
    view       = src["view"]
    teks_col   = src["teks_col"]
    null_filt  = src["null_filter"]

    where_sql, params = build_filter_clause(
        filters.tahun_ajaran, filters.semester, filters.jenjang, fakultas, no_ps,
    )
    where_sql, params = extend_where(where_sql, params, null_filt)

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


# GET /api/dashboard/akademik/course-ranking
async def get_course_ranking_top(
    scope: UserScope, filters: AkademikQueryFilters,
    fakultas: str | None, no_ps: str | None, limit: int, metric: str = "overall",
) -> list[dict]:
    return await _course_ranking_query(scope, filters, fakultas, no_ps, limit, desc=True, metric=metric)


# GET /api/dashboard/akademik/course-ranking
async def get_course_ranking_bottom(
    scope: UserScope, filters: AkademikQueryFilters,
    fakultas: str | None, no_ps: str | None, limit: int, metric: str = "overall",
) -> list[dict]:
    return await _course_ranking_query(scope, filters, fakultas, no_ps, limit, desc=False, metric=metric)


# GET /api/dashboard/akademik/course-ranking
async def _course_ranking_query(
    scope: UserScope, filters: AkademikQueryFilters,
    fakultas: str | None, no_ps: str | None, limit: int, desc: bool,
    metric: str = "overall",
) -> list[dict]:
    if metric not in VALID_RANKING_METRIC:
        raise ValueError(f"metric tidak valid: {metric}")
    skor_expr = METRIC_TO_EXPR[metric]

    b_cls, b_prm = [], []
    if filters.jenjang: b_cls.append("jenjang = ANY(%s)"); b_prm.append(filters.jenjang)
    if fakultas:        b_cls.append("kode_fakultas = %s"); b_prm.append(fakultas)
    if no_ps:           b_cls.append("no_prodi = %s"); b_prm.append(int(no_ps))

    base_where = build_where(b_cls)
    t_cls, t_prm = temporal_clauses(filters)
    t_cls = t_cls + ["skor IS NOT NULL"]

    outer_where = build_where(t_cls)
    order = "DESC" if desc else "ASC"
    all_params = b_prm + t_prm + [limit]

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
                LAG(skor)     OVER w AS prev_skor,
                LAG(tahun_ajaran) OVER w AS prev_tahun_ajaran,
                LAG(semester)     OVER w AS prev_semester
            FROM all_periods
            WINDOW w AS (PARTITION BY kode_matkul ORDER BY tahun, semester)
        )
        SELECT * FROM with_lag {outer_where}
        ORDER BY skor {order}
        LIMIT %s
    """

    result = await _executor.execute(sql, scope, all_params)
    if result.error:
        logger.error("_course_ranking_query desc=%s (user=%s): %s", desc, scope.user_id, result.error)
        return []
    return result.rows