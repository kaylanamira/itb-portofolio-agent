"""
api/routers/dashboard_dosen.py

Router untuk endpoint dashboard personal dosen. Scope selalu 1 dosen dari
session (dosen_id di active_role) — tidak menerima parameter fakultas/no_ps
dari client sama sekali, beda dari dashboard_akademik.py yang scope-nya
per entitas (fakultas/prodi).
"""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status

from api.dependencies import get_user_scope
from api.schemas.dashboard_akademik import (
    AkademikQueryFilters,
    KomentarItem, KomentarPagination, KomentarResponse,
)
from api.schemas.dashboard_dosen import (
    DosenStatsOverviewResponse,
    DosenTrendPoint,        DosenTrendResponse,
    DosenKelasItem,         DosenKelasResponse,
    DosenKelulusanResponse,
    DosenLuaranItem,        DosenLuaranResponse,
    DosenGradingCompItem,   DosenGradingCompResponse,
    DosenKategoriSkorItem,  DosenSkorKategoriResponse,
    DosenSkorPertanyaanItem, DosenSkorPertanyaanResponse,
    KategoriSkor,
)
from api.services import akademik_dosen as service
from api.services.akademik import get_komentar_mentah, period_label
from core.scope import UserRole, UserScope

router = APIRouter(prefix="/api/dashboard/dosen", tags=["dashboard-dosen"])


# ─── Internal helper ───────────────────────────────────────────────────────────

def _require_dosen_id(scope: UserScope) -> int:
    """
    Semua endpoint di router ini butuh dosen_id konkret dari role aktif.
    403 (bukan 500) kalau role bukan dosen atau dosen_id kosong — supaya
    frontend bisa bedakan "salah role" (bug pemanggilan endpoint) dari
    error server yang sesungguhnya.
    """
    if scope.role != UserRole.DOSEN or scope.active_role.dosen_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Endpoint ini khusus role dosen dengan dosen_id yang valid.",
        )
    return scope.active_role.dosen_id


# ─── Phase 1: stats overview ────────────────────────────────────────────────────

@router.get("/stats-overview", response_model=DosenStatsOverviewResponse,
            summary="4 stat card baris atas dashboard dosen")
async def get_dosen_stats_overview(
    filters: Annotated[AkademikQueryFilters, Query()] = AkademikQueryFilters(),
    scope:   UserScope                                 = Depends(get_user_scope),
) -> DosenStatsOverviewResponse:
    dosen_id = _require_dosen_id(scope)
    row = await service.get_dosen_stats_overview(scope, filters, dosen_id)
    if row is None:
        return DosenStatsOverviewResponse(
            jumlah_matkul=0, jumlah_kelas=0, total_sks_diajar=0, jumlah_mahasiswa=0,
        )
    return DosenStatsOverviewResponse(**row)


# ─── Phase 2: tren temporal (Tab 1 baris 1) ────────────────────────────────────

@router.get("/trend", response_model=DosenTrendResponse,
            summary="Tren temporal IP, Q1-Q12, dan Q4-Q7 untuk 3 line chart Tab 1")
async def get_dosen_trend(
    filters:    Annotated[AkademikQueryFilters, Query()] = AkademikQueryFilters(),
    n_semester: int                                       = Query(default=8, ge=1, le=20),
    scope:      UserScope                                 = Depends(get_user_scope),
) -> DosenTrendResponse:
    dosen_id = _require_dosen_id(scope)
    rows = await service.get_dosen_trend(scope, filters, dosen_id, n_semester)
    return DosenTrendResponse(trend=[DosenTrendPoint(**r) for r in rows])


# ─── Phase 3: tabel utama kelas (Tab 1 baris 2) ────────────────────────────────

@router.get("/kelas", response_model=DosenKelasResponse,
            summary="Tabel utama seluruh kelas yang diajar dosen pada periode terpilih")
async def get_dosen_kelas(
    filters: Annotated[AkademikQueryFilters, Query()] = AkademikQueryFilters(),
    scope:   UserScope                                 = Depends(get_user_scope),
) -> DosenKelasResponse:
    dosen_id = _require_dosen_id(scope)
    rows = await service.get_dosen_kelas(scope, filters, dosen_id)
    return DosenKelasResponse(items=[DosenKelasItem(**r) for r in rows])


# ─── Phase 4: kelulusan A-C vs D-E (Tab 2 baris 1) ─────────────────────────────

@router.get("/kelulusan", response_model=DosenKelulusanResponse,
            summary="Persentase lulus (A-C) periode ini vs periode lalu, untuk grouped bar chart")
async def get_dosen_kelulusan(
    filters: Annotated[AkademikQueryFilters, Query()] = AkademikQueryFilters(),
    scope:   UserScope                                 = Depends(get_user_scope),
) -> DosenKelulusanResponse:
    dosen_id = _require_dosen_id(scope)
    data = await service.get_dosen_kelulusan(scope, filters, dosen_id)
    return DosenKelulusanResponse(**data)


# ─── Phase 5: tabel luaran (Tab 2 baris 2) ─────────────────────────────────────

@router.get("/luaran", response_model=DosenLuaranResponse,
            summary="Tabel luaran mata kuliah: IP dan persentase lulus per kelas")
async def get_dosen_luaran(
    filters: Annotated[AkademikQueryFilters, Query()] = AkademikQueryFilters(),
    scope:   UserScope                                 = Depends(get_user_scope),
) -> DosenLuaranResponse:
    dosen_id = _require_dosen_id(scope)
    rows = await service.get_dosen_luaran(scope, filters, dosen_id)
    return DosenLuaranResponse(items=[DosenLuaranItem(**r) for r in rows])


# ─── Phase 6: komposisi bobot penilaian (Tab 2 baris 3) ────────────────────────

@router.get("/grading-comp", response_model=DosenGradingCompResponse,
            summary="Komposisi bobot komponen penilaian per kelas, untuk stacked bar chart")
async def get_dosen_grading_comp(
    filters: Annotated[AkademikQueryFilters, Query()] = AkademikQueryFilters(),
    scope:   UserScope                                 = Depends(get_user_scope),
) -> DosenGradingCompResponse:
    dosen_id = _require_dosen_id(scope)
    rows = await service.get_dosen_grading_comp(scope, filters, dosen_id)
    return DosenGradingCompResponse(items=[DosenGradingCompItem(**r) for r in rows])


# ─── Phase 7: skor per kategori (Tab 3, default view) ──────────────────────────

@router.get("/skor-kategori", response_model=DosenSkorKategoriResponse,
            summary="5 kategori skor kuesioner untuk horizontal bar chart Tab 3")
async def get_dosen_skor_kategori(
    filters: Annotated[AkademikQueryFilters, Query()] = AkademikQueryFilters(),
    scope:   UserScope                                 = Depends(get_user_scope),
) -> DosenSkorKategoriResponse:
    dosen_id = _require_dosen_id(scope)
    rows = await service.get_dosen_skor_kategori(scope, filters, dosen_id)
    return DosenSkorKategoriResponse(items=[DosenKategoriSkorItem(**r) for r in rows])


# ─── Phase 8: drill-down per pertanyaan (Tab 3, saat 1 kategori diklik) ────────

@router.get("/skor-pertanyaan", response_model=DosenSkorPertanyaanResponse,
            summary="Breakdown skor per pertanyaan individual dalam 1 kategori (drill-down)")
async def get_dosen_skor_pertanyaan(
    kode_kategori: KategoriSkor,
    filters:       Annotated[AkademikQueryFilters, Query()] = AkademikQueryFilters(),
    scope:         UserScope                                 = Depends(get_user_scope),
) -> DosenSkorPertanyaanResponse:
    dosen_id = _require_dosen_id(scope)
    rows = await service.get_dosen_skor_pertanyaan(scope, filters, dosen_id, kode_kategori)
    return DosenSkorPertanyaanResponse(
        kode_kategori=kode_kategori,
        items=[DosenSkorPertanyaanItem(**r) for r in rows],
    )


# ─── Tab 4: komentar — reuse penuh endpoint akademik umum ──────────────────────
# Tidak didaftarkan ulang di sini. RLS v_akademik_komentar_mahasiswa untuk role
# dosen sudah filter ke kelas yang benar-benar diajarkan (semua_dosen_id) —
# lihat DB_REFERENCE.md. Frontend dashboard dosen memanggil endpoint yang sudah
# ada: GET /api/dashboard/akademik/komentar-mentah, tanpa perubahan apapun.