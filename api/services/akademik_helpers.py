import logging
from core.scope import UserScope, UserRole
from core.sql_executor import PsycopgExecutor
from api.schemas.dashboard_akademik import AkademikQueryFilters

logger    = logging.getLogger(__name__)
_executor = PsycopgExecutor()


SEMESTER_MAP: dict[int, tuple[str, str]] = {
    1: ("ganjil", "Ganjil"),
    2: ("genap",  "Genap"),
    3: ("pendek", "Pendek"),
}
SEMESTER_TO_DB: dict[str, int] = {v: k for k, (v, _) in SEMESTER_MAP.items()}

STRATA_LABEL: dict[str, str] = {
    "S1": "S1", "S2": "S2", "S3": "S3", "PR": "Profesi",
}
STRATA_ORDER: dict[str, int] = {"S1": 0, "S2": 1, "S3": 2, "PR": 3}

KODE_GRUP_TO_COL: dict[str, str] = {
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
VALID_KODE_GRUP: frozenset[str] = frozenset(KODE_GRUP_TO_COL)

# Sinkron manual dengan frontend metricToActualColumn.ts
METRIC_TO_EXPR: dict[str, str] = {
    "overall":            "AVG(avg_skor_overall)",
    "capaian":            "AVG(avg_skor_capaian)",
    "sarana_prasarana":   "AVG(avg_skor_sarana_prasarana)",
    "perilaku_mahasiswa": "AVG(avg_skor_perilaku_mahasiswa)",
    "avg_ip":             "AVG(avg_ip_akhir_mahasiswa)",
    "q4_q7": "(AVG(skor_q24) + AVG(skor_q25) + AVG(skor_q26) + AVG(skor_q27)) / 4.0",
    **{f"q{n}": f"AVG(skor_q{n})" for n in (21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 35, 37)},
}
VALID_RANKING_METRIC: frozenset[str] = frozenset(METRIC_TO_EXPR)

KOMENTAR_SOURCE: dict[str, dict] = {
    "mahasiswa": {
        "view":        "analitik.v_akademik_komentar_mahasiswa",
        "teks_col":    "komentar_teks",
        "order":       "ts_jawaban DESC",
        "null_filter": "komentar_teks IS NOT NULL AND komentar_teks != ''",
    },
    "dosen": {
        "view":        "analitik.v_akademik_portofolio",
        "teks_col":    "usulan_perbaikan_oleh_dosen_berikutnya",
        "order":       "tahun_ajaran DESC, semester DESC, kode_matkul",
        "null_filter": "usulan_perbaikan_oleh_dosen_berikutnya IS NOT NULL AND usulan_perbaikan_oleh_dosen_berikutnya != ''",
    },
    "itb": {
        "view":        "analitik.v_akademik_portofolio",
        "teks_col":    "usulan_perbaikan_oleh_itb",
        "order":       "tahun_ajaran DESC, semester DESC, kode_matkul",
        "null_filter": "usulan_perbaikan_oleh_itb IS NOT NULL AND usulan_perbaikan_oleh_itb != ''",
    },
}


def is_faculty_level(scope: UserScope) -> bool:
    return scope.role in (UserRole.ADMIN, UserRole.DIREKTORAT)


def period_label(tahun_ajaran: str | None, semester: int | None) -> str | None:
    if tahun_ajaran is None or semester is None:
        return None
    _, label = SEMESTER_MAP.get(int(semester), ("?", str(semester)))
    return f"{tahun_ajaran} {label}"


def build_where(clauses: list[str]) -> str:
    return f"WHERE {' AND '.join(clauses)}" if clauses else ""


def extend_where(where_sql: str, params: list, extra: str) -> tuple[str, list]:
    if where_sql:
        return f"{where_sql} AND {extra}", params
    return f"WHERE {extra}", params


def base_cte_clauses(
    jenjang: list[str] | None, fakultas: str | None, no_ps: str | None,
) -> tuple[list[str], list]:
    clauses, params = [], []
    if jenjang:
        clauses.append("jenjang = ANY(%s)"); params.append(jenjang)
    if fakultas:
        clauses.append("kode_fakultas = %s"); params.append(fakultas)
    if no_ps:
        clauses.append("no_prodi = %s"); params.append(int(no_ps))
    return clauses, params


def temporal_clauses(filters: AkademikQueryFilters) -> tuple[list[str], list]:
    clauses, params = [], []
    if filters.tahun_ajaran:
        clauses.append("tahun_ajaran = %s"); params.append(filters.tahun_ajaran)
    if filters.semester:
        db_val = SEMESTER_TO_DB.get(filters.semester)
        if db_val:
            clauses.append("semester = %s"); params.append(db_val)
    return clauses, params


def build_filter_clause(
    tahun_ajaran: str | None, semester: str | None, jenjang: list[str] | None,
    fakultas: str | None, no_ps: str | None,
) -> tuple[str, list]:
    clauses, params = [], []
    if tahun_ajaran:
        clauses.append("tahun_ajaran = %s"); params.append(tahun_ajaran)
    if semester:
        db_val = SEMESTER_TO_DB.get(semester)
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
    return build_where(clauses), params


async def resolve_default_period(
    scope: UserScope, fakultas: str | None, no_ps: str | None,
) -> tuple[str, int] | None:
    b_cls, b_prm = [], []
    if fakultas: b_cls.append("kode_fakultas = %s"); b_prm.append(fakultas)
    if no_ps:    b_cls.append("no_prodi = %s"); b_prm.append(int(no_ps))
    where = build_where(b_cls)

    sql = f"""
        SELECT tahun_ajaran, semester
        FROM analitik.v_akademik_statistik_prodi {where}
        ORDER BY tahun DESC, semester DESC
        LIMIT 1
    """
    result = await _executor.execute(sql, scope, b_prm)
    if result.error or not result.rows:
        if result.error:
            logger.error("resolve_default_period (user=%s): %s", scope.user_id, result.error)
        return None
    row = result.rows[0]
    return row["tahun_ajaran"], row["semester"]