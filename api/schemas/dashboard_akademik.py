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
    """value = str(no_ps) — kd_ps TIDAK unik dalam satu fakultas."""
    value:     str
    label:     str
    kd_ps:     str
    kd_strata: str


# ─── Phase 0.5: GET /akademik/filter-options ──────────────────────────────────

class FilterOptionsLocked(BaseModel):
    fakultas: str | None = None
    prodi:    str | None = None


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
    jenjang memakai Annotated[..., Query()] untuk multi-value: ?jenjang=S1&jenjang=S2.
    """
    tahun_ajaran: str | None                                  = None
    semester:     Literal["ganjil", "genap", "pendek"] | None = None
    jenjang:      Annotated[list[str] | None, Query()]        = None
    fakultas:     str | None                                  = None
    no_ps:        str | None                                  = None


# ─── Phase 1: GET /akademik/stats-overview ────────────────────────────────────

class StatsOverviewResponse(BaseModel):
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
    prev_period_label:        str | None


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
    dist_pct_lulus_a_c: float | None
    dist_pct_lulus_a_d: float | None
    total_mahasiswa:    int
    avg_ip:             float | None   # avg_ip_akhir_mahasiswa per entitas


class GradeDistResponse(BaseModel):
    granularity: Literal["fakultas", "prodi"]
    items:       list[GradeDistItem]


# ─── Phase 4b: GET /akademik/grade-trend ─────────────────────────────────────

class GradeTrendPoint(BaseModel):
    period_label:         str
    tahun_ajaran:         str
    semester:             int
    avg_skor_overall:     float | None
    avg_skor_capaian:     float | None   # Q1-Q3, untuk garis q1q3 di line chart
    avg_skor_pelaksanaan: float | None   # Q4-Q7, untuk garis q4q7 di line chart
    avg_skor_q28: float | None  # Q8, untuk line chart tren beban kerja
    dist_pct_a:           float | None
    dist_pct_lulus_a_c:   float | None
    total_mahasiswa:      int


class GradeTrendResponse(BaseModel):
    """trend diurutkan kronologis (terlama → terbaru) untuk x-axis line chart."""
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


# ─── Phase B: GET /akademik/grading-comp ─────────────────────────────────────

class GradingCompItem(BaseModel):
    """
    Rata-rata bobot komponen penilaian per entitas.
    Nilai None = komponen tidak dipakai sama sekali (avg = 0, disaring di endpoint).
    Frontend menampilkan hanya komponen dengan nilai > 0.
    """
    label:              str
    kode:               str
    jumlah_kelas:       int
    avg_bobot_uts:          float | None
    avg_bobot_uas:          float | None
    avg_bobot_tugas:        float | None
    avg_bobot_kuis:         float | None
    avg_bobot_praktikum:    float | None
    avg_bobot_projek:       float | None
    avg_bobot_partisipatif: float | None


class GradingCompResponse(BaseModel):
    granularity: Literal["fakultas", "prodi"]
    items:       list[GradingCompItem]


# ─── Phase C: GET /akademik/skor-by-sks ──────────────────────────────────────

class SkorBySksBucket(BaseModel):
    """
    Skor Q8 (beban kerja) per kelompok SKS.
    sks_label: "1-2 SKS", "3 SKS", atau "4+ SKS".
    """
    sks_label:    str
    jumlah_kelas: int
    avg_skor_q8:  float | None


class SkorBySksResponse(BaseModel):
    """items diurutkan dari SKS terkecil ke terbesar."""
    items: list[SkorBySksBucket]


# ─── Phase D: GET /akademik/komentar-mentah ───────────────────────────────────

class KomentarItem(BaseModel):
    """
    Satu komentar teks dari kuesioner/portofolio.
    Untuk sumber=mahasiswa: bisa ada banyak item per kelas_id (satu per mahasiswa).
    Untuk sumber=dosen/itb: satu item per kelas_id (dari portofolio dosen).
    """
    kelas_id:       int
    kode_matkul:    str
    nama_matkul_id: str
    kode_prodi:     str
    nama_prodi_id:  str
    kode_fakultas:  str
    tahun_ajaran:   str
    semester:       int
    teks:           str


class KomentarPagination(BaseModel):
    page:        int
    page_size:   int
    total_items: int
    total_pages: int


class KomentarResponse(BaseModel):
    """
    sumber: mahasiswa = kuesioner mahasiswa (komentar_teks, banyak per kelas)
            dosen     = usulan perbaikan dosen (satu per kelas, dari portofolio)
            itb       = rekomendasi dosen ke ITB (satu per kelas, dari portofolio)
    isu_dominan tidak ada di endpoint ini — tunggu pipeline RAG.
    """
    sumber:     Literal["mahasiswa", "dosen", "itb"]
    pagination: KomentarPagination
    items:      list[KomentarItem]