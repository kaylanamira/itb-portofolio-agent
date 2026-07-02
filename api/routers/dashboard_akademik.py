"""
api/routers/dashboard_akademik.py

Router untuk endpoint dashboard portofolio & kuesioner akademik.
"""

import asyncio
import logging
from dataclasses import dataclass

from fastapi import APIRouter, Depends, HTTPException, Query, status

from api.dependencies import get_user_scope
from api.schemas.dashboard_akademik import (
    AkademikFilterOptionsResponse,
    AkademikQueryFilters,
    AttendanceResponse,    AttendanceItem,
    CourseRankingResponse, CourseRankingItem,
    FilterOption, FilterOptionsLocked, ProdiOption,
    GradeDistResponse,   GradeDistItem,
    GradeTrendResponse,  GradeTrendPoint,
    HeatmapRow,
    SkorHeatmapResponse,
    SkorItem, SkorPertanyaanResponse,
    StatsOverviewResponse,
)
from api.models.akademik import (
    VALID_KODE_GRUP,
    build_prodi_label,
    derive_jenjang_options,
    get_attendance,
    get_course_ranking_bottom,
    get_course_ranking_top,
    get_grade_distribution,
    get_grade_trend,
    get_prodi_options,
    get_fakultas_options,
    get_semester_tersedia,
    get_skor_heatmap,
    get_skor_pertanyaan,
    get_stats_overview,
    get_tahun_ajaran_tersedia,
    _period_label,
    _is_faculty_level,
)
from core.scope import UserRole, UserScope

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/dashboard", tags=["dashboard-akademik"])


# ─── Internal helpers ─────────────────────────────────────────────────────────

@dataclass
class _ResolvedSpatial:
    """Nilai spasial setelah scope-locking. Beda dari FilterOptionsLocked."""
    fakultas: str | None
    no_ps:    str | None


def _resolve_locked(scope: UserScope) -> FilterOptionsLocked:
    role = scope.role
    if role in (UserRole.ADMIN, UserRole.DIREKTORAT):
        return FilterOptionsLocked(fakultas=None, prodi=None)
    if role in (UserRole.DEKAN, UserRole.JAJARAN_DEKANAT):
        return FilterOptionsLocked(fakultas=scope.active_role.kd_fak, prodi=None)
    locked_prodi = (
        str(scope.active_role.no_ps)
        if scope.active_role.no_ps is not None else None
    )
    if locked_prodi is None:
        logger.warning("_resolve_locked: no_ps None role=%s user=%s",
                       scope.role, scope.user_id)
    return FilterOptionsLocked(fakultas=scope.active_role.kd_fak, prodi=locked_prodi)


def _resolve_spatial(
    scope: UserScope, fakultas: str | None, no_ps: str | None,
) -> _ResolvedSpatial:
    """
    Scope-locking: dimensi yang terkunci diabaikan dari client, diganti scope.
    RLS PostgreSQL adalah jaring pengaman terakhir.
    """
    locked = _resolve_locked(scope)
    return _ResolvedSpatial(
        fakultas = locked.fakultas or fakultas,
        no_ps    = locked.prodi    or no_ps,
    )


# ─── Phase 0.5 ────────────────────────────────────────────────────────────────

@router.get(
    "/akademik/filter-options",
    response_model=AkademikFilterOptionsResponse,
    summary="Opsi dropdown filter dashboard akademik",
)
async def get_akademik_filter_options(
    scope: UserScope = Depends(get_user_scope),
) -> AkademikFilterOptionsResponse:
    tahun_list, semester_rows, fak_rows, prodi_rows = await asyncio.gather(
        get_tahun_ajaran_tersedia(scope),
        get_semester_tersedia(scope),
        get_fakultas_options(scope),
        get_prodi_options(scope),
    )
    locked = _resolve_locked(scope)

    prodi_by_fak: dict[str, list[ProdiOption]] = {}
    for r in prodi_rows:
        prodi_by_fak.setdefault(r["kd_fak"], []).append(
            ProdiOption(
                value=str(r["no_ps"]), label=build_prodi_label(r["nama_id"], r["kd_strata"]),
                kd_ps=r["kd_ps"], kd_strata=r["kd_strata"],
            )
        )

    return AkademikFilterOptionsResponse(
        locked            = locked,
        tahun_ajaran      = [FilterOption(value=t, label=t) for t in tahun_list],
        semester          = [FilterOption(value=r["value"], label=r["label"]) for r in semester_rows],
        jenjang           = [FilterOption(value=r["value"], label=r["label"])
                             for r in derive_jenjang_options(prodi_rows)],
        fakultas          = [FilterOption(value=r["kd_fak"], label=r["nama_id"]) for r in fak_rows],
        prodi_by_fakultas = prodi_by_fak,
    )


# ─── Phase 1 ──────────────────────────────────────────────────────────────────

@router.get(
    "/akademik/stats-overview",
    response_model=StatsOverviewResponse,
    summary="4 stat card baris atas dashboard akademik",
)
async def get_akademik_stats_overview(
    filters: AkademikQueryFilters = Depends(),
    scope:   UserScope            = Depends(get_user_scope),
) -> StatsOverviewResponse:
    resolved = _resolve_spatial(scope, filters.fakultas, filters.no_ps)
    row = await get_stats_overview(
        scope,
        filters.model_copy(update={"fakultas": resolved.fakultas, "no_ps": resolved.no_ps}),
    )
    if row is None:
        return StatsOverviewResponse(
            jumlah_kelas=0, jumlah_matkul_aktif=0,
            jumlah_dosen_aktif=0, jumlah_mahasiswa_aktif=0,
            avg_kelas_per_matkul=None,
        )
    return StatsOverviewResponse(**row)


# ─── Phase 2 ──────────────────────────────────────────────────────────────────

@router.get(
    "/akademik/attendance",
    response_model=AttendanceResponse,
    summary="Kehadiran dosen & mahasiswa per entitas + trend prev periode",
)
async def get_akademik_attendance(
    filters: AkademikQueryFilters = Depends(),
    scope:   UserScope            = Depends(get_user_scope),
) -> AttendanceResponse:
    resolved = _resolve_spatial(scope, filters.fakultas, filters.no_ps)
    rows = await get_attendance(scope, filters, resolved.fakultas, resolved.no_ps)
    granularity = "fakultas" if _is_faculty_level(scope) else "prodi"

    items = [
        AttendanceItem(
            label                    = r["label"],
            kode                     = r["kode"],
            kehadiran_dosen          = r["kehadiran_dosen"],
            kehadiran_mahasiswa      = r["kehadiran_mahasiswa"],
            prev_kehadiran_dosen     = r["prev_kehadiran_dosen"],
            prev_kehadiran_mahasiswa = r["prev_kehadiran_mahasiswa"],
            prev_period_label        = _period_label(r["prev_tahun_ajaran"], r["prev_semester"]),
        )
        for r in rows
    ]
    return AttendanceResponse(granularity=granularity, items=items)


# ─── Phase 3 ──────────────────────────────────────────────────────────────────

@router.get(
    "/akademik/skor-pertanyaan",
    response_model=SkorPertanyaanResponse,
    summary="Skor rata-rata satu kelompok pertanyaan per entitas + trend",
    description=(
        "kode_grup yang valid: capaian | pelaksanaan | sarana_prasarana | "
        "perilaku_mahasiswa | overall | q21 | q22 | q23 | q24 | q25 | q26 | "
        "q27 | q28 | q29 | q30 | q35 | q37"
    ),
)
async def get_akademik_skor_pertanyaan(
    kode_grup: str,
    filters:   AkademikQueryFilters = Depends(),
    scope:     UserScope            = Depends(get_user_scope),
) -> SkorPertanyaanResponse:
    if kode_grup not in VALID_KODE_GRUP:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"kode_grup '{kode_grup}' tidak valid. "
                   f"Nilai yang diterima: {sorted(VALID_KODE_GRUP)}",
        )

    resolved = _resolve_spatial(scope, filters.fakultas, filters.no_ps)
    rows = await get_skor_pertanyaan(
        scope, filters, resolved.fakultas, resolved.no_ps, kode_grup,
    )
    granularity = "fakultas" if _is_faculty_level(scope) else "prodi"

    items = [
        SkorItem(
            label             = r["label"],
            kode              = r["kode"],
            skor              = r["skor"],
            prev_skor         = r["prev_skor"],
            prev_period_label = _period_label(r["prev_tahun_ajaran"], r["prev_semester"]),
        )
        for r in rows
    ]
    return SkorPertanyaanResponse(granularity=granularity, kode_grup=kode_grup, items=items)


# ─── Phase 4a ─────────────────────────────────────────────────────────────────

@router.get(
    "/akademik/grade-distribution",
    response_model=GradeDistResponse,
    summary="Distribusi nilai (A/AB/B/.../Fail) per entitas untuk periode terpilih",
)
async def get_akademik_grade_distribution(
    filters: AkademikQueryFilters = Depends(),
    scope:   UserScope            = Depends(get_user_scope),
) -> GradeDistResponse:
    resolved = _resolve_spatial(scope, filters.fakultas, filters.no_ps)
    rows = await get_grade_distribution(scope, filters, resolved.fakultas, resolved.no_ps)
    granularity = "fakultas" if _is_faculty_level(scope) else "prodi"

    items = [GradeDistItem(**r) for r in rows]
    return GradeDistResponse(granularity=granularity, items=items)


# ─── Phase 4b ─────────────────────────────────────────────────────────────────

@router.get(
    "/akademik/grade-trend",
    response_model=GradeTrendResponse,
    summary="Tren nilai N semester terakhir untuk scope aktif (line chart)",
    description=(
        "n_semester mengontrol jumlah titik data di line chart (default 6). "
        "Filter tahun_ajaran digunakan sebagai ceiling (titik akhir tren), "
        "bukan filter tunggal. Filter semester diabaikan di endpoint ini."
    ),
)
async def get_akademik_grade_trend(
    n_semester: int                   = Query(default=6, ge=2, le=20),
    filters:    AkademikQueryFilters  = Depends(),
    scope:      UserScope             = Depends(get_user_scope),
) -> GradeTrendResponse:
    resolved = _resolve_spatial(scope, filters.fakultas, filters.no_ps)
    rows = await get_grade_trend(
        scope, filters, resolved.fakultas, resolved.no_ps, n_semester,
    )
    granularity = "fakultas" if _is_faculty_level(scope) else "prodi"

    trend = [
        GradeTrendPoint(
            period_label       = _period_label(r["tahun_ajaran"], r["semester"]) or "",
            tahun_ajaran       = r["tahun_ajaran"],
            semester           = r["semester"],
            avg_skor_overall   = r["avg_skor_overall"],
            dist_pct_a         = r["dist_pct_a"],
            dist_pct_lulus_a_c = r["dist_pct_lulus_a_c"],
            total_mahasiswa    = r["total_mahasiswa"],
        )
        for r in rows
    ]
    return GradeTrendResponse(
        granularity=granularity, n_semester=len(trend), trend=trend,
    )


# ─── Phase 4c ─────────────────────────────────────────────────────────────────

@router.get(
    "/akademik/course-ranking",
    response_model=CourseRankingResponse,
    summary="Top-N dan bottom-N mata kuliah berdasarkan skor kuesioner",
)
async def get_akademik_course_ranking(
    limit:   int                   = Query(default=5, ge=1, le=20),
    filters: AkademikQueryFilters  = Depends(),
    scope:   UserScope             = Depends(get_user_scope),
) -> CourseRankingResponse:
    resolved = _resolve_spatial(scope, filters.fakultas, filters.no_ps)

    # Top dan bottom dijalankan paralel — dua query terpisah, satu koneksi masing-masing
    top_rows, bottom_rows = await asyncio.gather(
        get_course_ranking_top(scope, filters, resolved.fakultas, resolved.no_ps, limit),
        get_course_ranking_bottom(scope, filters, resolved.fakultas, resolved.no_ps, limit),
    )

    def _to_item(r: dict) -> CourseRankingItem:
        return CourseRankingItem(
            kode_matkul       = r["kode_matkul"],
            nama_matkul_id    = r["nama_matkul_id"],
            sks               = r["sks"],
            kode_prodi        = r["kode_prodi"],
            nama_prodi_id     = r["nama_prodi_id"],
            kode_fakultas     = r["kode_fakultas"],
            jumlah_kelas      = r["jumlah_kelas"],
            avg_skor          = r["avg_skor"],
            prev_skor         = r["prev_skor"],
            prev_period_label = _period_label(r["prev_tahun_ajaran"], r["prev_semester"]),
        )

    return CourseRankingResponse(
        limit  = limit,
        top    = [_to_item(r) for r in top_rows],
        bottom = [_to_item(r) for r in bottom_rows],
    )


# ─── Phase 5 ──────────────────────────────────────────────────────────────────

@router.get(
    "/akademik/skor-heatmap",
    response_model=SkorHeatmapResponse,
    summary="12 skor pertanyaan per entitas (snapshot satu periode, untuk heatmap)",
)
async def get_akademik_skor_heatmap(
    filters: AkademikQueryFilters = Depends(),
    scope:   UserScope            = Depends(get_user_scope),
) -> SkorHeatmapResponse:
    resolved = _resolve_spatial(scope, filters.fakultas, filters.no_ps)
    rows = await get_skor_heatmap(scope, filters, resolved.fakultas, resolved.no_ps)
    granularity = "fakultas" if _is_faculty_level(scope) else "prodi"

    items = [HeatmapRow(**r) for r in rows]
    return SkorHeatmapResponse(granularity=granularity, items=items)