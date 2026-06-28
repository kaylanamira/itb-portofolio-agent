"""
api/schemas/dashboard_akademik.py

Pydantic response models untuk seluruh endpoint dashboard akademik.
"""

from pydantic import BaseModel


# ─── Primitif ─────────────────────────────────────────────────────────────────

class FilterOption(BaseModel):
    """Satu pilihan generik: value yang dikirim ke query param + label tampilan."""
    value: str
    label: str


class ProdiOption(BaseModel):
    """
    Satu pilihan program studi.

    value = str(no_ps) karena kd_ps TIDAK unik dalam satu fakultas.
    Contoh: di STEI, kd_ps="IF" ada untuk S1 (no_ps=135) dan S2 (no_ps=136).

    kd_strata dibutuhkan frontend untuk memfilter dropdown prodi
    berdasarkan pilihan jenjang yang aktif.
    """
    value:     str   # str(no_ps) — mis. "135", unik per baris
    label:     str   # mis. "Teknik Informatika (S1)"
    kd_ps:     str   # mis. "IF" — untuk referensi
    kd_strata: str   # "S1", "S2", "S3", "PR" — nilai DB, bukan label


# ─── GET /akademik/filter-options ─────────────────────────────────────────────

class FilterOptionsLocked(BaseModel):
    """
    Dimensi filter yang terkunci oleh role user.
    None  = user bebas memilih.
    str   = nilai terkunci — frontend tampilkan sebagai label, bukan dropdown.

    locked.prodi berisi str(no_ps), konsisten dengan ProdiOption.value.
    """
    fakultas: str | None = None   # kd_fak jika locked, mis. "STEI"
    prodi:    str | None = None   # str(no_ps) jika locked, mis. "135"


class AkademikFilterOptionsResponse(BaseModel):
    """
    Response untuk GET /api/dashboard/akademik/filter-options.

    Semua filter option dikembalikan backend — tidak ada nilai hardcoded
    di frontend. Urutan field mengikuti urutan filter bar dari kiri ke kanan.

    Catatan value format:
      tahun_ajaran  → text, mis. "2024/2025"
      semester      → text: "gasal" | "genap" | "pendek"  (dikonversi dari smallint DB)
      jenjang       → kd_strata DB persis: "S1" | "S2" | "S3" | "PR"
                      Label "PR" ditampilkan sebagai "Profesi" (lihat label field)
      fakultas      → kd_fak, mis. "STEI"
      prodi         → str(no_ps), mis. "135"
    """
    locked:            FilterOptionsLocked
    tahun_ajaran:      list[FilterOption]
    semester:          list[FilterOption]
    jenjang:           list[FilterOption]
    fakultas:          list[FilterOption]
    prodi_by_fakultas: dict[str, list[ProdiOption]]