"""
api/schemas/dashboard_dosen.py

Pydantic response models untuk endpoint dashboard personal dosen
(api/routers/dashboard_dosen.py). Scope selalu 1 dosen dari session —
karena itu, berbeda dari dashboard_akademik.py, tidak ada field
"granularity" (fakultas/prodi) di manapun: granularity-nya selalu
"per dosen", jadi tidak perlu dinyatakan ulang di tiap response.
"""

from typing   import Literal
from pydantic import BaseModel


# ─── Phase 1: GET /dosen/stats-overview ────────────────────────────────────────

class DosenStatsOverviewResponse(BaseModel):
    jumlah_matkul:    int
    jumlah_kelas:     int
    total_sks_diajar: int
    jumlah_mahasiswa: int


# ─── Phase 2: GET /dosen/trend ─────────────────────────────────────────────────

class DosenTrendPoint(BaseModel):
    period_label:     str
    tahun_ajaran:     str
    semester:         int
    avg_ip_mahasiswa: float | None
    avg_skor_overall: float | None   # Q1-Q12
    avg_skor_q4_q7:   float | None   # Q4-Q7, performa dosen


class DosenTrendResponse(BaseModel):
    """trend diurutkan kronologis (terlama → terbaru) untuk x-axis line chart."""
    trend: list[DosenTrendPoint]


# ─── Phase 3: GET /dosen/kelas ──────────────────────────────────────────────────

class DosenKelasItem(BaseModel):
    """
    1 baris = 1 kelas yang diajar dosen pada periode terpilih.
    prev_* = nilai periode sebelumnya untuk kelas paralel yang sama
    (dibandingkan per kode_matkul + no_kelas, bukan rata-rata seluruh kelas).
    """
    kelas_id:                int
    kode_matkul:             str
    nama_matkul_id:          str
    no_kelas:                int
    jumlah_mahasiswa:        int
    avg_ip:                  float | None
    prev_avg_ip:             float | None
    avg_skor_overall:        float | None
    prev_avg_skor_overall:   float | None
    pct_kehadiran_dosen:     float | None
    pct_kehadiran_mahasiswa: float | None


class DosenKelasResponse(BaseModel):
    items: list[DosenKelasItem]


# ─── Phase 4: GET /dosen/kelulusan ─────────────────────────────────────────────

class DosenKelulusanResponse(BaseModel):
    """Grouped bar: persentase lulus (A-C) periode ini vs periode sebelumnya."""
    pct_lulus_periode_ini:  float | None
    pct_lulus_periode_lalu: float | None
    prev_period_label:      str | None


# ─── Phase 5: GET /dosen/luaran ─────────────────────────────────────────────────

class DosenLuaranItem(BaseModel):
    kelas_id:         int
    kode_matkul:      str
    nama_matkul_id:   str
    no_kelas:         int
    jumlah_mahasiswa: int
    avg_ip:           float | None
    pct_lulus_a_c:    float | None


class DosenLuaranResponse(BaseModel):
    items: list[DosenLuaranItem]


# ─── Phase 6: GET /dosen/grading-comp ──────────────────────────────────────────

class DosenGradingCompItem(BaseModel):
    """
    Komposisi bobot penilaian per kelas (bukan rata-rata lintas kelas —
    beda dari GradingCompItem di dashboard_akademik.py yang granularity-nya
    fakultas/prodi). Field bernilai None = komponen tidak dipakai kelas ini,
    bukan dipakai dengan bobot 0.
    """
    kelas_id:           int
    kode_matkul:        str
    no_kelas:           int
    bobot_uts:          float | None
    bobot_uas:          float | None
    bobot_tugas:        float | None
    bobot_kuis:         float | None
    bobot_praktikum:    float | None
    bobot_projek:       float | None
    bobot_partisipatif: float | None


class DosenGradingCompResponse(BaseModel):
    items: list[DosenGradingCompItem]


# ─── Phase 7: GET /dosen/skor-kategori ─────────────────────────────────────────

KategoriSkor = Literal[
    "capaian", "pelaksanaan", "q28", "sarana_prasarana", "perilaku_mahasiswa",
]
"""
5 kategori chart horizontal bar Tab 3:
capaian            = Q1-Q3   (luaran mata kuliah)
pelaksanaan        = Q4-Q7   (performa dosen)
q28                = Q8      (kesesuaian SKS)
sarana_prasarana   = Q9-Q10
perilaku_mahasiswa = Q11-Q12 (pengalaman mahasiswa)
Sama persis dengan kode_grup di KODE_GRUP_TO_COL (akademik_constants.py) —
sengaja reuse nilai yang sama, bukan bikin daftar kategori baru yang beda
penamaan untuk konsep yang identik.
"""


class DosenKategoriSkorItem(BaseModel):
    kode_kategori: KategoriSkor
    label:         str
    skor:          float | None


class DosenSkorKategoriResponse(BaseModel):
    items: list[DosenKategoriSkorItem]


# ─── Phase 8: GET /dosen/skor-pertanyaan ───────────────────────────────────────

class DosenSkorPertanyaanItem(BaseModel):
    """1 baris = 1 pertanyaan individual (drill-down dari 1 kategori Tab 3)."""
    kode_pertanyaan: str   # "Q4", "Q5", dst — konsisten dengan QuestionReference frontend
    pertanyaan:      str   # teks lengkap pertanyaan
    skor:            float | None


class DosenSkorPertanyaanResponse(BaseModel):
    kode_kategori: KategoriSkor
    items:         list[DosenSkorPertanyaanItem]