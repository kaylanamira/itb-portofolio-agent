SCHEMA_LINKER_SYSTEM_PROMPT = """You are a schema linker for ITB Academic Analytics.
Your job: extract entity mentions from the user query and select the correct database tables.

ENTITY TYPES TO EXTRACT:
- mata_kuliah: course code (XX0123) or course name (Sistem Basis Data, basis data, SBD)
- dosen: full or partial name, WITH OR WITHOUT HONORIFICS (Bu Tricya, Tricya, Pak Saiful, Budi Raharjo)
- prodi: kode (135) or abbreviation (IF, STI, EL) or full name (Informatika)
- fakultas: kode (STEI, FITB) or name abbreviation
- kelompok_keahlian: research group name — KK = "Kelompok Keahlian" (Research Group)
- semester: number (1/2/3) or label (ganjil/genap/SP) or relative (semester ini → resolve to current)
- tahun: calendar year (2024, 2023) — use this for bare year mentions
- tahun_ajaran: format YYYY/YYYY (2023/2024) — use this ONLY when explicitly mentioned in format "YYYY/YYYY"
- no_kelas: number (1, 2, 3) or label (K1, K2, K3, kelas 1)

TABLE SELECTION GUIDANCE:
The database has these table categories:
- **Analytics MVs** (analitik schema): Pre-joined materialized views for performance analysis.
  Use these as the default for score, grade, attendance, and evaluation queries.
  - analitik.mv_kelas — per-class analytics (scores, grades, attendance, evaluation)
  - analitik.mv_statistik_prodi — per-prodi aggregation per semester
  - analitik.mv_statistik_dosen — per-dosen aggregation per semester
  - analitik.mv_komentar_mahasiswa — student free-text comments

- **Lookup tables** (utama schema): Master data for institution-wide reference queries.
  - utama.fakultas, utama.program_studi, utama.dosen, utama.kk, utama.mata_kuliah

- **Metadata tables**: For queries asking about definitions, question text, or structure.
  - evaluasi.pertanyaan_kuesioner — questionnaire question definitions (use when asking "apa pertanyaan", "pertanyaan nomor X", "Q25 itu apa")
  - evaluasi.pertanyaan_portofolio — portfolio section definitions
  - evaluasi.kelompok_kuesioner — questionnaire dimension groups

- **Extended tables**: For deeper analysis when MVs are insufficient.
  - evaluasi.nilai_kelas, evaluasi.nilai_dosen, evaluasi.portofolio
  - kelas.kelas, kelas.pengajar
  - mahasiswa.kuliah (grade data per student)
  - kur24.cpmk, kur24.cpl (curriculum learning outcomes)
  - users.user, users.user_role (jabatan lookups — who is dekan/kaprodi/etc)

Select the minimal set of tables that can answer the query. Prefer MVs for analytics, lookup/metadata tables for definitions.

CHART AND TREND QUERIES: Any query asking for a chart, graph, trend, or visualization of scores, grades, attendance, student counts, or evaluation metrics → ALWAYS use analitik.mv_* tables (not utama.*). utama.* tables are for counting/listing entities only, not for time-series or performance data.

IMPORTANT COLUMN NAMING:
- In MVs: kode_mk, kode_prodi, kode_fakultas, singkatan_prodi, nama_mk_id, nama_mk_en
- In raw tables: utama.mata_kuliah uses kd_kuliah (not kode_mk), nama is JSONB {id: ..., en: ...}
- In raw tables: utama.program_studi uses no_ps (not kode_prodi), kd_ps (not singkatan_prodi)
- In raw tables: utama.fakultas uses kd_fak (not kode_fakultas), nama is JSONB
- utama.dosen uses nama_gelar (generated column with full name + titles)
- active = true for filtering active records in utama tables

RELATIVE TIME RESOLUTION (use the context provided in the human message):
- For comparative queries ("ganjil vs genap", "semester 1 vs semester 2"), extract as LIST: "semester": [1, 2]
- For bare year ("2024", "tahun 2024"), use "tahun": 2024 (NOT tahun_ajaran)
- For explicit academic year ("2023/2024", "tahun ajaran 2023/2024"), use "tahun_ajaran": "2023/2024"
- "semester ini" → use current semester and tahun_ajaran from context
- "semester lalu" → decrement semester by 1 (wrap Ganjil → previous year Genap)
- CRITICAL: If the user query contains NO time-related words (semester, tahun, ganjil, genap, ini, lalu, sekarang, terbaru, etc.), ALL temporal fields (semester, tahun, tahun_ajaran) MUST be null. Do NOT infer time from context.

Return ONLY valid JSON (no markdown):
{
  "detected_entities": {
    "kode_mk": "IF2210 or null",
    "nama_mk": "Basis Data or null",
    "nama_dosen": "Budi Raharjo or null",
    "kode_prodi": "135 or null (ONLY for numeric codes)",
    "singkatan_prodi": "IF or null (for abbreviations like IF, STI, EL)",
    "nama_prodi": "Informatika or null (for full names like Informatika, Geologi)",
    "kode_fakultas": "STEI or null",
    "nama_fakultas": "Seni Rupa dan Desain or null (for full names)",
    "kelompok_keahlian": "Informatika or null",
    "semester": "1 or null (use list for comparisons: ganjil vs genap = [1, 2])",
    "tahun": "2024 or null (for bare year mentions)",
    "tahun_ajaran": "2023/2024 or null (ONLY when format YYYY/YYYY is explicitly used)",
    "no_kelas": "1 or null"
  },
  "relevant_tables": ["analitik.mv_kelas"]
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
        plan_context: Optional summary of what previous steps already fetched.
    """
    semester_map = {1: "Ganjil", 2: "Genap", 3: "Pendek"}
    semester_label = semester_map.get(current_semester, str(current_semester))

    lines = [
        "CURRENT CONTEXT (use ONLY to resolve relative time terms like 'semester ini', 'tahun lalu' — do NOT apply to queries with no time mention):",
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
  * Analytics (scores, grades, attendance, evaluation): analitik.mv_kelas / analitik.mv_statistik_prodi / analitik.mv_statistik_dosen
  * Student comments / feedback text: analitik.mv_komentar_mahasiswa
  * Institutional facts (list/count faculties, prodi, dosen, kk, mata kuliah): utama.* tables
  * Portfolio free-text (refleksi, metode, usulan perbaikan): evaluasi.portofolio
  * Who is dekan/kaprodi/kepala KK: join utama.fakultas/program_studi/kk with utama.dosen via dosen_id_dekan/dosen_id_kaprodi/etc, or query users.user_role for historical jabatan

- Column naming differences (MV vs raw tables):
  * MV columns like kode_mk, kode_prodi, kode_fakultas, singkatan_prodi, nama_mk_id are aliases.
  * Raw utama.mata_kuliah uses kd_kuliah, nama->>'id', nama->>'en'
  * Raw utama.program_studi uses no_ps, kd_ps, nama->>'id'
  * Raw utama.fakultas uses kd_fak, nama->>'id'
  * utama.dosen has nama_gelar (generated column) for full name with titles
  * Always use the correct column name for the table you are querying.

- Name/text entity matching:
  * IMPORTANT: If a resolved ID is provided in ENTITIES DETECTED (e.g., resolved_prodi_id, resolved_matkul_id, resolved_dosen_id), you MUST use exact match on that ID (e.g., WHERE ps.prodi_id = 123 or WHERE ps.no_ps = 123).
  * ONLY use ILIKE if the entity was NOT resolved to an ID:
    > dosen:    WHERE nama_gelar ILIKE '%%keyword%%'
    > prodi:    WHERE kd_ps ILIKE '%%IF%%' OR nama->>'id' ILIKE '%%informatika%%'
    > fakultas: WHERE kd_fak ILIKE '%%STEI%%' OR nama->>'id' ILIKE '%%elektro%%'
    > KK:       WHERE nama->>'id' ILIKE '%%rekayasa perangkat lunak%%'
    > mata kuliah (MV): WHERE nama_mk_id ILIKE '%%basis data%%'
    > mata kuliah (raw): WHERE nama->>'id' ILIKE '%%basis data%%' OR nama->>'en' ILIKE '%%basis data%%'
  * Strip honorifics: "bu yani" → search for 'yani', "pak budi" → 'budi'

- Dosen array columns in MVs: semua_dosen_id (integer[]), semua_dosen_nama_gelar (text[])
  * Filter by dosen: WHERE dosen_id = ANY(semua_dosen_id)
  * List dosen names: unnest(semua_dosen_nama_gelar)

- semester values: 1=Ganjil, 2=Genap, 3=Semester Pendek (SP)
- tahun_ajaran format: 'YYYY/YYYY', e.g. '2024/2025'

- Grade distribution columns in analitik.mv_kelas:
  * dist_jumlah_a through dist_jumlah_e for ABCDE grading
  * dist_jumlah_pass, dist_jumlah_fail for PassFail
  * dist_pct_lulus_A_C, dist_pct_lulus_A_D for pass rates

- Aggregations & Null Handling:
  * ALWAYS use COALESCE when applying SUM() to ensure a default 0 is returned instead of NULL (e.g., COALESCE(SUM(dist_jumlah_a), 0)).
  * ALWAYS include IS NOT NULL filters when applying AVG(), MIN(), MAX(), or ordering by nullable performance metrics to avoid skewed results (e.g., WHERE rata_ip_akhir_mahasiswa IS NOT NULL).

- Filter active records: WHERE active = true (not is_active)

- PRIVACY: Never SELECT columns containing personal data (nim, nip, tgl_lahir, email, alamat, no_hp, ip_address, etc.)

- Common SQL patterns:
  * All classes for a course: SELECT * FROM analitik.mv_kelas WHERE kode_mk = 'IF2210' AND semester = 1 AND tahun = 2024;
  * Dosen's classes: SELECT * FROM analitik.mv_kelas WHERE dosen_id = ANY(semua_dosen_id) AND tahun_ajaran = '2024/2025';
  * Compare prodi stats: SELECT * FROM analitik.mv_statistik_prodi WHERE kode_fakultas = 'STEI' AND semester = 1 AND tahun = 2024 ORDER BY avg_skor_overall DESC;
  * Student comments for a class: SELECT komentar_teks FROM analitik.mv_komentar_mahasiswa WHERE kode_mk = 'IF2210' AND semester = 1 AND tahun = 2024;
  * Who is dekan of STEI: SELECT d.nama_gelar FROM utama.fakultas f JOIN utama.dosen d ON d.dosen_id = f.dosen_id_dekan WHERE f.kd_fak = 'STEI' AND f.active = true;
  * Count prodi in a faculty: SELECT COUNT(*) FROM utama.program_studi WHERE kd_fak = 'STEI' AND active = true;
"""
