"""
api/schemas/dashboard_akademik.py

Pydantic response models untuk seluruh endpoint dashboard akademik.
"""

from typing    import Annotated, Literal
from fastapi   import Query
from pydantic  import BaseModel


# ─── Primitif ─────────────────────────────────────────────────────────────────

class FilterOption(BaseModel):
    value: str
    label: str


class ProdiOption(BaseModel):
    """
    value = str(no_ps) — kd_ps TIDAK unik dalam satu fakultas.
    kd_strata dibutuhkan frontend untuk filter dropdown prodi by jenjang.
    """
    value:     str
    label:     str
    kd_ps:     str
    kd_strata: str


# ─── Phase 0.5: GET /akademik/filter-options ──────────────────────────────────

class FilterOptionsLocked(BaseModel):
    fakultas: str | None = None   # kd_fak jika locked
    prodi:    str | None = None   # str(no_ps) jika locked


class AkademikFilterOptionsResponse(BaseModel):
    locked:            FilterOptionsLocked
    tahun_ajaran:      list[FilterOption]
    semester:          list[FilterOption]
    jenjang:           list[FilterOption]
    fakultas:          list[FilterOption]
    prodi_by_fakultas: dict[str, list[ProdiOption]]


# ─── Shared query filter ──────────────────────────────────────────────────────

class AkademikQueryFilters(BaseModel):
    """
    Query param filter untuk semua endpoint chart dashboard akademik.

    jenjang WAJIB memakai Annotated[..., Query()] agar FastAPI menerima
    multi-value: ?jenjang=S1&jenjang=S2 → ["S1", "S2"].
    Tanpa Query(), FastAPI tidak menangani list dari repeated params.
    """
    tahun_ajaran: str | None                                  = None
    semester:     Literal["ganjil", "genap", "pendek"] | None = None
    jenjang:      Annotated[list[str] | None, Query()]        = None
    fakultas:     str | None                                  = None
    no_ps:        str | None                                  = None   # str(no_prodi)


# ─── Phase 1: GET /akademik/stats-overview ────────────────────────────────────

class StatsOverviewResponse(BaseModel):
    """
    4 stat card baris atas dashboard.
    avg_kelas_per_matkul = SUM(kelas)/SUM(matkul), None jika tidak ada data.
    Kolom attendance ada di endpoint /attendance terpisah.
    """
    jumlah_kelas:          int
    jumlah_matkul_aktif:   int
    jumlah_dosen_aktif:    int
    jumlah_mahasiswa_aktif: int
    avg_kelas_per_matkul:  float | None


# ─── Phase 2: GET /akademik/attendance ────────────────────────────────────────

class AttendanceItem(BaseModel):
    label:                    str
    kode:                     str
    kehadiran_dosen:          float | None
    kehadiran_mahasiswa:      float | None
    prev_kehadiran_dosen:     float | None
    prev_kehadiran_mahasiswa: float | None
    prev_period_label:        str | None   # mis. "2023/2024 Ganjil"


class AttendanceResponse(BaseModel):
    granularity: Literal["fakultas", "prodi"]
    items:       list[AttendanceItem]


# ─── Phase 3: GET /akademik/skor-pertanyaan ───────────────────────────────────

class SkorItem(BaseModel):
    label:             str
    kode:              str
    skor:              float | None
    prev_skor:         float | None
    prev_period_label: str | None


class SkorPertanyaanResponse(BaseModel):
    granularity: Literal["fakultas", "prodi"]
    kode_grup:   str
    items:       list[SkorItem]


# ─── Phase 4a: GET /akademik/grade-distribution ───────────────────────────────

class GradeDistItem(BaseModel):
    label:              str
    kode:               str
    # Grade ABCDE + T (tidak hadir) + PassFail
    dist_pct_a:         float | None
    dist_pct_ab:        float | None
    dist_pct_b:         float | None
    dist_pct_bc:        float | None
    dist_pct_c:         float | None
    dist_pct_d:         float | None
    dist_pct_e:         float | None
    dist_pct_t:         float | None
    dist_pct_pass:      float | None
    dist_pct_fail:      float | None
    dist_pct_lulus_a_c: float | None   # % lulus (>=C atau Pass)
    dist_pct_lulus_a_d: float | None   # % lulus (>=D atau Pass)
    total_mahasiswa:    int


class GradeDistResponse(BaseModel):
    granularity: Literal["fakultas", "prodi"]
    items:       list[GradeDistItem]


# ─── Phase 4b: GET /akademik/grade-trend ─────────────────────────────────────

class GradeTrendPoint(BaseModel):
    period_label:       str      # mis. "2024/2025 Ganjil"
    tahun_ajaran:       str
    semester:           int
    avg_skor_overall:   float | None
    dist_pct_a:         float | None
    dist_pct_lulus_a_c: float | None
    total_mahasiswa:    int


class GradeTrendResponse(BaseModel):
    """
    trend diurutkan dari semester tertua ke terbaru (untuk x-axis line chart).
    n_semester = jumlah titik data yang dikembalikan.
    """
    granularity: Literal["fakultas", "prodi"]
    n_semester:  int
    trend:       list[GradeTrendPoint]


# ─── Phase 4c: GET /akademik/course-ranking ───────────────────────────────────

class CourseRankingItem(BaseModel):
    kode_matkul:       str
    nama_matkul_id:    str
    sks:               int
    kode_prodi:        str
    nama_prodi_id:     str
    kode_fakultas:     str
    jumlah_kelas:      int
    avg_skor:          float | None
    prev_skor:         float | None
    prev_period_label: str | None


class CourseRankingResponse(BaseModel):
    limit:  int
    top:    list[CourseRankingItem]
    bottom: list[CourseRankingItem]


# ─── Phase 5: GET /akademik/skor-heatmap ─────────────────────────────────────

class HeatmapRow(BaseModel):
    label:        str
    kode:         str
    # 12 Q scores yang ada di v_akademik_statistik_prodi
    avg_skor_q21: float | None
    avg_skor_q22: float | None
    avg_skor_q23: float | None
    avg_skor_q24: float | None
    avg_skor_q25: float | None
    avg_skor_q26: float | None
    avg_skor_q27: float | None
    avg_skor_q28: float | None
    avg_skor_q29: float | None
    avg_skor_q30: float | None
    avg_skor_q35: float | None
    avg_skor_q37: float | None


class SkorHeatmapResponse(BaseModel):
    granularity: Literal["fakultas", "prodi"]
    items:       list[HeatmapRow]