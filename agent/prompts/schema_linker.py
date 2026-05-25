SCHEMA_LINKER_SYSTEM_PROMPT = """You are a schema linker for ITB Academic Analytics.
Your job: extract entity mentions from the user query and select the correct database tables.

ENTITY TYPES TO EXTRACT:
- mata_kuliah: course code (IF3140) or name (Sistem Basis Data, basis data, SBD)
- dosen: full or partial name (Bu Tricya, Tricya, Pak Saiful, Budi Raharjo)
- prodi: kode (135) or abbreviation (IF, STI, EL) or full name (Informatika)
- fakultas: kode (STEI, FITB) or name abbreviation
- kelompok_keahlian: research group name attached to a fakultas — KK = "Kelompok Keahlian" (Research Group), NOT "Kurikulum Kompetensi"
- semester: number (1/2/3) or label (ganjil/genap/SP) or relative (semester ini → resolve to current)
- tahun_ajaran: format YYYY/YYYY or relative (tahun ini → resolve to current)
- no_kelas: number (1, 2, 3) or label (K1, K2, K3, kelas 1)

AVAILABLE TABLES — select from these exact names only:
- utama.fakultas      → global list of all faculties, no scope restriction
- utama.program_studi → global list of all prodi, no scope restriction
- utama.dosen         → global list of all lecturers, no scope restriction
- utama.kk            → research groups per faculty (used to join dosen → fakultas)
- utama.mata_kuliah   → course catalog (use for bilingual name lookup)
- mv_kelas            → per-class analytics (scores, grades, attendance) — DEFAULT
- mv_statistik_prodi  → per-prodi aggregation per semester
- mv_statistik_dosen  → per-dosen aggregation per semester
- teks_portofolio     → free-text sections (refleksi, metode, usulan perbaikan)
- komentar_mahasiswa  → student free-text comments

TABLE SELECTION RULES:
1. "berapa banyak fakultas/prodi/dosen/kk di ITB?" → lookup tables (utama.fakultas / utama.program_studi / utama.dosen / utama.kk)
2. "siapa saja dosen di STEI/IF/prodi X?" → [utama.dosen, utama.kk, utama.fakultas] or [utama.dosen, utama.program_studi]
3. Any question from a dosen about general prodi/fakultas info (NOT their own kelas) → lookup tables
4. Individual class scores, grades, attendance, evaluasi kuesioner → [mv_kelas]
5. Prodi-level performance, cross-prodi comparison → [mv_statistik_prodi]
6. Dosen performance over time, dosen comparison → [mv_statistik_dosen]
7. Student comments, keluhan, feedback text → [komentar_mahasiswa]
8. Refleksi dosen, metode perkuliahan, usulan perbaikan → [teks_portofolio]
9. Queries needing both score and text → [mv_kelas, komentar_mahasiswa] or [mv_kelas, teks_portofolio]
10. Dosen per KK per fakultas (e.g. "komposisi dosen STEI per KK") → [utama.dosen, utama.kk, utama.fakultas]
11. Dosen per prodi (e.g. "siapa dosen di prodi IF?") → [utama.dosen, utama.kk, utama.program_studi] or [utama.dosen, utama.program_studi]

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
    "kode_prodi": "135 or null (ONLY for PDDikti numeric codes)",
    "singkatan_prodi": "IF or null (for abbreviations like IF, STI, EL)",
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
    plan_context: str | None = None,
) -> str:
    """Build the human message with runtime context for the schema linker.

    Args:
        query: The current plan step task or effective query.
        current_semester: Resolved current semester number (1/2/3).
        current_tahun_ajaran: Resolved current tahun ajaran string.
        user_role: User's role string for scope context.
        plan_context: Optional summary of what previous steps already fetched,
                      to avoid redundant table selection.
    """
    semester_map = {1: "Ganjil", 2: "Genap", 3: "Pendek"}
    semester_label = semester_map.get(current_semester, str(current_semester))

    lines = [
        "CURRENT CONTEXT:",
        f"  Semester: {current_semester} ({semester_label})",
        f"  Tahun Ajaran: {current_tahun_ajaran}",
        f"  User Role: {user_role}",
    ]

    if plan_context:
        lines.append("")
        lines.append("PLAN CONTEXT (what previous steps already retrieved):")
        lines.append(f"  {plan_context}")

    lines.append("")
    lines.append(f"USER QUERY: {query}")

    return "\n".join(lines)


PORTFOLIO_SQL_DOMAIN_RULES = """
- Table routing:
  * Portfolio analytics (scores, grades, attendance): mv_kelas / mv_statistik_prodi / mv_statistik_dosen
  * Institutional facts (list/count faculties, prodi, dosen, kk, mata kuliah): lookup tables
    (utama.fakultas, utama.program_studi, utama.dosen, utama.kk, utama.mata_kuliah)

- Name/text entity matching — ALWAYS use ILIKE, never exact =:
  * dosen:    WHERE nama ILIKE '%%yani%%'
  * prodi:    WHERE singkatan_prodi ILIKE '%%IF%%' OR nama_prodi ILIKE '%%informatika%%'
  * fakultas: WHERE kd_fak ILIKE '%%STEI%%' OR nama->>'id' ILIKE '%%elektro%%'
  * kelompok keahlian: WHERE nama->>'id' ILIKE '%%rekayasa perangkat lunak%%'
    KK = "Kelompok Keahlian" (Research Group), NOT "Kurikulum Kompetensi"
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
  * If singkatan_prodi is set (no UUID) → filter with ILIKE:
    WHERE {SCOPE_FILTER} AND singkatan_prodi ILIKE '%%IF%%'
  * If a resolved_* UUID is NOT set but entity_candidates[field] is populated:
    the match was ambiguous. Use the top candidate's display name with ILIKE:
    WHERE {SCOPE_FILTER} AND nama_dosen ILIKE '%%<top candidate nama_dosen>%%'
  * ALWAYS use the exact string provided in ENTITIES for your ILIKE match (e.g. from entity_candidates or the field itself). Do NOT use the spelling from the user's raw query.
  * NEVER fabricate or guess UUIDs. Only use UUIDs that appear literally in ENTITIES.

- For person detail queries ("siapa itu X", "info lengkap"): JOIN kelompok_keahlian and
  fakultas to return d.nama_dosen, kk.nama_kk, f.nama_fakultas.

- Common SQL Patterns:
  * Institutional fact queries (use lookup tables, scope filter = TRUE):
    SELECT COUNT(*) AS total_fakultas FROM utama.fakultas WHERE active = TRUE AND {SCOPE_FILTER};
  * Dosen in a specific faculty (can use kd_fak directly):
    SELECT d.nama FROM utama.dosen d WHERE d.kd_fak = 'STEI' AND d.active = TRUE AND {SCOPE_FILTER};
  * Compare total dosen between faculties:
    SELECT d.kd_fak, COUNT(d.dosen_id) AS total_dosen FROM utama.dosen d WHERE d.kd_fak IN ('FTTM', 'STEI') AND d.active = TRUE AND {SCOPE_FILTER} GROUP BY d.kd_fak;
  * All classes for a specific matkul in a semester:
    SELECT * FROM mv_kelas WHERE kode_mk = 'IF2210' AND semester = 1 AND tahun_ajaran = '2024/2025' AND {SCOPE_FILTER} ORDER BY no_kelas;
  * Dosen's own classes:
    SELECT kode_mk, no_kelas, rata_rata_nilai, skor_avg_overall FROM mv_kelas WHERE '<dosen_uuid>'::uuid = ANY(semua_dosen_id) AND tahun_ajaran = '2024/2025' AND {SCOPE_FILTER} ORDER BY kode_mk, no_kelas;
  * Compare prodi statistics:
    SELECT singkatan_prodi, avg_nilai, avg_skor_overall, avg_kehadiran_dosen FROM mv_statistik_prodi WHERE fakultas_id = 'xxx'::uuid AND semester = 1 AND tahun_ajaran = '2024/2025' AND {SCOPE_FILTER} ORDER BY avg_skor_overall DESC;
  * Grade distribution for a class:
    SELECT kode_mk, no_kelas, dist_jumlah_A, dist_jumlah_AB, dist_jumlah_B, dist_jumlah_BC, dist_jumlah_C, dist_jumlah_D, dist_jumlah_E, dist_pct_lulus FROM mv_kelas WHERE kode_mk = 'IF2210' AND {SCOPE_FILTER};
  * Dosen performance trend:
    SELECT semester, tahun_ajaran, avg_skor_overall, avg_nilai FROM mv_statistik_dosen WHERE dosen_id = 'xxx'::uuid AND {SCOPE_FILTER} ORDER BY tahun_ajaran, semester;
"""
