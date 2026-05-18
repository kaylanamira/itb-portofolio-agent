"""
Schema linker prompt.

Extracts entity mentions from the user query and determines which DB tables
"""

SCHEMA_LINKER_SYSTEM_PROMPT = """You are a schema linker for ITB Academic Analytics.
Your job: extract entity mentions from the user query and select the correct database tables.

ENTITY TYPES TO EXTRACT:
- mata_kuliah: course code (IF3140) or name (Sistem Basis Data, basis data, SBD)
- dosen: full or partial name (Bu Tricya, Tricya, Pak Saiful, Budi Raharjo)
- prodi: kode (135) or abbreviation (IF, STI, EL) or full name (Informatika)
- fakultas: kode (STEI, FITB) or name abbreviation
- kelompok_keahlian: research group name attached to a fakultas— KK stands for "Kelompok Keahlian" (Research Group), NOT "Kurikulum Kompetensi" OR ELSE
- semester: number (1/2/3) or label (ganjil/genap/SP) or relative (semester ini → resolve to current)
- tahun_ajaran: format YYYY/YYYY or relative (tahun ini → resolve to current)
- no_kelas: number (1, 2, 3) or label (K1, K2, K3, kelas 1)

AVAILABLE TABLES — select from these exact names only:
- fakultas            → global list of all faculties, no scope restriction
- program_studi       → global list of all prodi, no scope restriction
- dosen               → global list of all lecturers, no scope restriction
- kelompok_keahlian   → research groups per faculty (used to join dosen → fakultas)
- mata_kuliah         → course catalog (use for bilingual name lookup)
- mv_kelas            → per-class analytics (scores, grades, attendance) — DEFAULT
- mv_statistik_prodi  → per-prodi aggregation per semester
- mv_statistik_dosen  → per-dosen aggregation per semester
- teks_portofolio     → free-text sections (refleksi, metode, usulan perbaikan)
- komentar_mahasiswa  → student free-text comments

TABLE SELECTION RULES:
1. "berapa banyak fakultas/prodi/dosen/kk di ITB?" → lookup tables (fakultas / program_studi / dosen / kelompok_keahlian)
2. "siapa saja dosen di STEI/IF/prodi X?" → [dosen, kelompok_keahlian, fakultas] or [dosen, program_studi]
3. Any question from a dosen about general prodi/fakultas info (NOT their own kelas) → lookup tables
4. Individual class scores, grades, attendance, evaluasi kuesioner → [mv_kelas]
5. Prodi-level performance, cross-prodi comparison → [mv_statistik_prodi]
6. Dosen performance over time, dosen comparison → [mv_statistik_dosen]
7. Student comments, keluhan, feedback text → [komentar_mahasiswa]
8. Refleksi dosen, metode perkuliahan, usulan perbaikan → [teks_portofolio]
9. Queries needing both score and text → [mv_kelas, komentar_mahasiswa] or [mv_kelas, teks_portofolio]

RELATIVE TIME RESOLUTION (use the context provided in the human message):
- ONLY populate "semester" and "tahun_ajaran" if the user explicitly mentions a time period (e.g., "semester 1", "2024/2025") or uses a relative term (e.g., "semester ini", "semester lalu", "tahun ini").
- If the user does NOT mention any time period (explicit or relative), set "semester" and "tahun_ajaran" to null.
- "semester ini" → use the current semester and tahun_ajaran from context.
- "semester lalu" → decrement semester by 1 (wrap Ganjil → previous year Genap).
- "tahun ini" / "tahun lalu" → resolve from tahun_ajaran context.

Return ONLY valid JSON (no markdown):
{
  "detected_entities": {
    "kode_mk": "IF2210 or null",
    "nama_mk": "Basis Data or null",
    "nama_dosen": "Budi Raharjo or null",
    "kode_prodi": "135 or null",
    "singkatan_prodi": "IF or null",
    "kode_fakultas": "STEI or null",
    "kelompok_keahlian": "Informatika or null",
    "semester": "number or null",
    "tahun_ajaran": "YYYY/YYYY or null",
    "no_kelas": "1 or null"
  },
  "relevant_tables": ["mv_kelas"]
}
"""


def build_schema_linker_human_message(
    query: str,
    current_semester: int,
    current_tahun_ajaran: str,
    user_role: str,
) -> str:
    """Build the human message with runtime context for the schema linker."""
    semester_map = {
      1: "Ganjil", 
      2: "Genap", 
      3: "Pendek"
    }
    semester_label = semester_map.get(current_semester, str(current_semester))
    return (
        f"CURRENT CONTEXT:\n"
        f"  Semester: {current_semester} ({semester_label})\n"
        f"  Tahun Ajaran: {current_tahun_ajaran}\n"
        f"  User Role: {user_role}\n"
        f"\n"
        f"USER QUERY: {query}"
    )


PORTFOLIO_SQL_DOMAIN_RULES = """
- Table routing:
  * Portfolio analytics (scores, grades, attendance): mv_kelas / mv_statistik_prodi / mv_statistik_dosen
  * Institutional facts (list/count faculties, prodi, dosen, kk, mata kuliah): lookup tables
    (fakultas, program_studi, dosen, kelompok_keahlian, mata_kuliah)
  * Free-text content: teks_portofolio, komentar_mahasiswa
  * dosen does NOT have fakultas_id — JOIN through kelompok_keahlian to reach fakultas

- Name/text entity matching — ALWAYS use ILIKE, never exact =:
  * dosen:    WHERE nama_dosen ILIKE '%%yani%%'
  * prodi:    WHERE kode_prodi ILIKE '%%IF%%' OR nama_prodi ILIKE '%%informatika%%'
  * fakultas: WHERE kode_fakultas ILIKE '%%STEI%%' OR nama_fakultas ILIKE '%%elektro%%'
  * kelompok keahlian: WHERE nama_kk ILIKE '%%rekayasa perangkat lunak%%' — KK stands for "Kelompok Keahlian" (Research Group), NOT "Kurikulum Kompetensi"
  * mata kuliah: WHERE nama_mk ILIKE '%%basis data%%' OR nama_mk_en ILIKE '%%basis data%%'
  * Strip honorifics mentally: "bu yani" → search for 'yani', "pak budi" → 'budi'

- Searching mata kuliah in mv_kelas: use `nama_mk ILIKE '%%keyword%%'`.
  mv_kelas does NOT have nama_mk_en.
  For bilingual search: JOIN mata_kuliah mk2 ON mk2.matkul_id = mv_kelas.matkul_id
  WHERE (mk2.nama_mk || ' ' || COALESCE(mk2.nama_mk_en, '')) ILIKE '%%keyword%%'

- semester values: 1=Ganjil, 2=Genap, 3=Semester Pendek (SP)
- tahun_ajaran format: 'YYYY/YYYY', e.g. '2024/2025'

- Grade distribution columns:
  * jenis_nilai='ABCDE': use dist_jumlah_A, dist_jumlah_AB, dist_jumlah_B, dist_jumlah_BC,
    dist_jumlah_C, dist_jumlah_D, dist_jumlah_E
  * jenis_nilai='Pass/Fail': use dist_jumlah_pass, dist_jumlah_fail
  * dist_pct_lulus works for both jenis_nilai types

- Entity resolution — how to use ENTITIES:
  * If resolved_dosen_id is set → use it directly:
    WHERE {SCOPE_FILTER} AND 'uuid'::uuid = ANY(semua_dosen_id)
  * If resolved_matkul_id is set → use it directly:
    WHERE {SCOPE_FILTER} AND matkul_id = 'uuid'::uuid
  * If resolved_prodi_id is set → use it directly:
    WHERE {SCOPE_FILTER} AND prodi_id = 'uuid'::uuid
  * If a resolved_* UUID is NOT set but entity_candidates[field] is populated:
    the match was ambiguous. Use the top candidate's display name with ILIKE:
    WHERE {SCOPE_FILTER} AND nama_dosen ILIKE '%%<top candidate nama_dosen>%%'
  * NEVER fabricate or guess UUIDs. Only use UUIDs that appear literally in ENTITIES.

- For person detail queries ("siapa itu X", "info lengkap"): JOIN kelompok_keahlian and
  fakultas to return d.nama_dosen, kk.nama_kk, f.nama_fakultas.
"""

