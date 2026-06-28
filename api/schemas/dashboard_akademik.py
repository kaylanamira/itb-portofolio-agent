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
    Satu pilihan program studi — lebih kaya dari FilterOption biasa.

    Mengapa value = str(no_ps), bukan kd_ps?
    - no_ps adalah PK sejati di utama.program_studi (unik per baris)
    - kd_ps TIDAK unik dalam satu fakultas: mis. "IF" bisa muncul untuk
      Teknik Informatika S1 (no_ps=135) dan Teknik Informatika S2 (no_ps=136)
    - Kaprodi IF S1 dan Kaprodi IF S2 punya kd_ps sama tapi no_ps berbeda
    - Chart endpoints memfilter dengan WHERE no_ps = <angka>, bukan kd_ps

    kd_strata dibutuhkan frontend untuk:
    - Filter dropdown prodi berdasarkan pilihan jenjang aktif
    - Membedakan "Teknik Informatika (S1)" dari "Teknik Informatika (S2)"
      saat dua prodi punya nama dasar yang sama
    """
    value:     str   # str(no_ps) — mis. "135"
    label:     str   # mis. "Teknik Informatika (S1)"
    kd_ps:     str   # mis. "IF" — untuk referensi / grouping
    kd_strata: str   # "S1", "S2", "S3", atau "Profesi" (sudah di-convert dari "PR")


# ─── GET /akademik/filter-options ─────────────────────────────────────────────

class FilterOptionsLocked(BaseModel):
    """
    Dimensi filter yang terkunci oleh role user.

    None  = user bebas memilih dimensi ini.
    str   = nilai terkunci — frontend tampilkan sebagai label statis, bukan dropdown.

    Nilai locked untuk prodi adalah str(no_ps), konsisten dengan ProdiOption.value.
    """
    fakultas: str | None = None   # kd_fak jika locked, mis. "STEI"
    prodi:    str | None = None   # str(no_ps) jika locked, mis. "135"


class AkademikFilterOptionsResponse(BaseModel):
    """Response untuk GET /api/dashboard/akademik/filter-options."""
    locked:            FilterOptionsLocked
    tahun_ajaran:      list[FilterOption]
    fakultas:          list[FilterOption]
    # Key = kd_fak; Value = list prodi di fakultas itu, sudah termasuk kd_strata
    prodi_by_fakultas: dict[str, list[ProdiOption]]