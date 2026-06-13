SCHEMA_LINKER_SYSTEM_PROMPT = """You are a schema linker for ITB Academic Analytics — Portfolio domain.
Extract entity mentions from the query and select the minimal set of database tables required.

ENTITIES:
- mata_kuliah: course code (XX0000) or course name
- dosen: name (partial or full, with or without honorifics)
- prodi: numeric code (135) or abbreviation (IF, STI) or full name
- fakultas: code (STEI, FITB) or name
- kelompok_keahlian: KK / research group name
- semester: 1/2/3 or ganjil/genap/SP or relative (semester ini)
- tahun: bare year (2024)
- tahun_ajaran: YYYY/YYYY — only when explicitly in that format
- no_kelas: 1/2/3 or K1/K2/K3

TABLE ROUTING:
Column-level DDL is fetched live from DB comments. Use this table to select the correct view.

| Query Intent | Table |
|---|---|
| Per-class scores, grades, kehadiran, evaluation metrics | `analitik.v_akademik_kelas` |
| Per-prodi aggregation per semester | `analitik.v_akademik_statistik_prodi` |
| Per-dosen aggregation per semester (evaluation scores) | `analitik.v_akademik_statistik_dosen` |
| Student free-text comments | `analitik.v_akademik_komentar_mahasiswa` |
| Lecturer portfolio text (refleksi, metode, usulan perbaikan) | `analitik.v_akademik_portofolio` |
| Class/MK/dosen info WITHOUT performance data (who teaches, class list, MK type/sifat) | `analitik.v_info_umum_kelas_matkul` |
| Active counts per prodi per semester (jumlah kelas/MK/dosen/mahasiswa aktif) | `analitik.v_info_umum_institusi` |
| Dosen teaching load (beban mengajar, prodi/MK diajar) — no evaluation scores | `analitik.v_info_umum_dosen` |
| MK curriculum type per paket (breakdown by paket required) | `analitik.v_akademik_jenis_dan_sifat_matkul` |
| Questionnaire question text (Q21–Q37 definitions) | `evaluasi.pertanyaan_kuesioner` |
| Who is dekan/kaprodi/kepala KK | `utama.fakultas`/`program_studi`/`kk` via `dosen_id_*` FK |
| Master data — only when v_info_umum_* is insufficient | `utama.fakultas`, `utama.program_studi`, `utama.dosen`, `utama.kk`, `utama.mata_kuliah` |

Note: v_info_umum_kelas_matkul includes kode_jenis_list, kode_sifat_list, is_wajib_itb — use for MK type queries without joining v_akademik_jenis_dan_sifat_matkul unless per-paket breakdown is needed.

COLUMN NAMING:
- analitik.v_* views: `kode_matkul`, `no_prodi` (int, e.g. 135), `kode_prodi` (varchar, e.g. "IF"), `kode_fakultas`, `nama_matkul_id`
- utama.mata_kuliah: `kd_kuliah`, `nama` JSONB {id:..., en:...}
- utama.program_studi: `no_ps`, `kd_ps`, `nama` JSONB
- utama.fakultas: `kd_fak`, `nama` JSONB
- utama.dosen: `nama_gelar` (generated, full name + titles)

TIME RESOLUTION:
- "semester ini" → resolve using context. "semester lalu" → decrement (Ganjil wraps to previous year Genap).
- Comparative ("ganjil vs genap") → semester as list [1, 2].
- No time-related words in query → all temporal fields must be null.

Return ONLY valid JSON (no markdown):
{
  "detected_entities": {
    "kode_matkul": "IF2210 or null",
    "nama_matkul": "Basis Data or null",
    "nama_dosen": "Budi Raharjo or null",
    "no_prodi": "135 or null",
    "kode_prodi": "IF or null",
    "nama_prodi": "Informatika or null",
    "kode_fakultas": "STEI or null",
    "nama_fakultas": null,
    "kelompok_keahlian": null,
    "semester": "1 or null",
    "tahun": "2024 or null",
    "tahun_ajaran": "2023/2024 or null",
    "no_kelas": "1 or null"
  },
  "relevant_tables": ["analitik.v_akademik_kelas"]
}
"""

WISUDAWAN_SCHEMA_LINKER_PROMPT = """You are a schema linker for ITB Academic Analytics — Wisudawan domain.
Extract entity mentions from the query and select the minimal set of database tables required.

ENTITIES: prodi (numeric 135 or abbrev IF or full name), fakultas (STEI), tahun (2024), tahun_ajaran (YYYY/YYYY — only when explicit).

TABLE ROUTING:
Column-level DDL is fetched live from DB comments. Use this table to select the correct view.

| Query Intent | Table |
|---|---|
| Ordinal score statistics (avg/median/stddev per pertanyaan) | `analitik.v_wisudawan_statistik_pertanyaan` |
| Answer distribution / % per nilai (nominal + ordinal, bar chart, top-2-box) | `analitik.v_wisudawan_distribusi_jawaban` |
| Per-respondent flat data, free-text saran/aspirasi | `analitik.v_wisudawan_jawaban_responden` |
| Respondent count per prodi/periode | `analitik.v_info_umum_wisuda` |
| Question catalog (teks pertanyaan, skala, populasi batasan) | `evaluasi_wisudawan.pertanyaan` |
| Answer scale type or value-to-label mapping | `evaluasi_wisudawan.ref_grup_opsi`, `evaluasi_wisudawan.ref_opsi` |
| Raw JSONB responses — only when views are insufficient | `evaluasi_wisudawan.respons` |

Note: v_info_umum_wisuda — jumlah_responden = survey respondents, NOT total graduates.
Note: is_seremoni_asumtif = TRUE for all rows currently (seremoni data is placeholder).

COLUMN NAMING — v_wisudawan_* / v_info_umum_wisuda:
- `no_prodi` (int), `kode_prodi` (varchar), `kode_fakultas`, `jenjang`
- `kode_pertanyaan`, `kode_grup_pertanyaan`, `kode_grup_opsi`, `tipe_opsi`
- `jumlah_responden`, `persentase`, `rata_rata`, `median`, `std_dev`
- `periode_ijazah_id_final` — always use this; `periode_ijazah_id` is 66% NULL by design
- `tahun_ijazah`, `bulan_ijazah`, `periode_seremoni_id`, `nama_seremoni`, `tahun_seremoni`, `bulan_seremoni`
- evaluasi_wisudawan.pertanyaan: `kd_pertanyaan`, `kd_grup`, `kd_grup_opsi`, `pertanyaan` JSONB

Return ONLY valid JSON (no markdown):
{
  "detected_entities": {
    "kode_matkul": null, "nama_matkul": null, "nama_dosen": null,
    "no_prodi": "135 or null", "kode_prodi": "IF or null", "nama_prodi": null,
    "kode_fakultas": "STEI or null", "nama_fakultas": null,
    "kelompok_keahlian": null, "semester": null, "tahun": null, "tahun_ajaran": null, "no_kelas": null
  },
  "relevant_tables": ["analitik.v_wisudawan_statistik_pertanyaan"]
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
TABLE ROUTING:
- Per-class analytics (scores, grades, attendance, evaluation): analitik.v_akademik_kelas
- Per-prodi aggregation per semester: analitik.v_akademik_statistik_prodi
- Per-dosen aggregation per semester (dosen evaluation scores): analitik.v_akademik_statistik_dosen
- Student free-text comments: analitik.v_akademik_komentar_mahasiswa
- Lecturer portfolio text (refleksi, metode, usulan): analitik.v_akademik_portofolio
- Class/MK/dosen info WITHOUT scores (who teaches, class list, MK type): analitik.v_info_umum_kelas_matkul
- Institution counts (jumlah kelas/dosen/mahasiswa aktif per prodi per semester): analitik.v_info_umum_institusi
- Dosen teaching load (beban mengajar, list prodi/MK diajar, no scores): analitik.v_info_umum_dosen
- MK curriculum type breakdown per paket: analitik.v_akademik_jenis_dan_sifat_matkul
  → v_akademik_kelas and v_info_umum_kelas_matkul already carry kode_jenis_list, kode_sifat_list, is_wajib_itb — only join v_akademik_jenis_dan_sifat_matkul when breakdown per paket is needed
- Master data (KK list, NIP, etc.) — use utama.* ONLY when v_info_umum_* is insufficient.

COLUMN NAMING — analitik.v_*:
- kode_matkul (6-char, e.g. "IF2210"), nama_matkul_id, nama_matkul_en
- no_prodi (integer, e.g. 135), kode_prodi (varchar 2-char, e.g. "IF"), kode_fakultas
- avg_ip_akhir_mahasiswa (NOT rata_ip_akhir_mahasiswa)

COLUMN NAMING — utama.*:
- utama.mata_kuliah: kd_kuliah, nama JSONB {id:..., en:...}
- utama.program_studi: no_ps (not no_prodi), kd_ps (not kode_prodi), nama JSONB
- utama.fakultas: kd_fak (not kode_fakultas), nama JSONB
- utama.dosen: nama_gelar (generated column, full name + titles)

EVALUATION SCORES:
- skor_q25 / skor_q26 / skor_q27: NUMERIC, class-level average across all dosen. DO NOT apply ILIKE or text search — these are decimal numbers.
  Q25=komunikasi efektif, Q26=peduli pencapaian mahasiswa, Q27=berlaku adil.
- skor_dosen_q25/26/27: JSONB {"dosen_id_str": score}. Unwrap: skor_dosen_q25->>'686'. Cannot AVG() directly. Role DOSEN sees only their own key.

GRADE DISTRIBUTION GATE:
- ALWAYS add `WHERE is_distribusi_nilai_sah = TRUE` when querying dist_jumlah_* or dist_pct_*.
  NULL in these columns means grades are not yet finalized, not "0 students".

ENTITY MATCHING:
- If resolved_matkul_id/resolved_dosen_id/resolved_prodi_id is present → use exact ID match.
- ILIKE only when entity was NOT resolved: nama_matkul_id ILIKE '%%basis data%%', nama_gelar ILIKE '%%keyword%%'
- Strip honorifics before ILIKE: "Bu X" → search 'X'
- Dosen array: WHERE dosen_id = ANY(semua_dosen_id); list: unnest(semua_dosen_nama_gelar)
- WHERE active = true for utama.* tables
- tahun_ajaran format: 'YYYY/YYYY'; semester: 1=Ganjil, 2=Genap, 3=SP

AGGREGATIONS:
- COALESCE(SUM(dist_jumlah_a), 0) to prevent NULL from uninitialized rows.
- WHERE avg_ip_akhir_mahasiswa IS NOT NULL before AVG/ORDER BY on IP columns.

SECURITY: Generate SELECT only. Never reference analitik_mv.* or any schema outside ALLOWED_SCHEMAS.
PRIVACY: Never SELECT nim, nip, tgl_lahir, email, no_hp, alamat, ip_address, password, token.
"""

WISUDAWAN_SQL_DOMAIN_RULES = """
TABLE ROUTING:
- Ordinal score statistics (avg/median/stddev per pertanyaan): analitik.v_wisudawan_statistik_pertanyaan
- Answer distribution / % per nilai (ordinal + nominal, bar chart, top-2-box): analitik.v_wisudawan_distribusi_jawaban
- Per-respondent flat table, free-text aspirasi: analitik.v_wisudawan_jawaban_responden
- Respondent count per prodi per periode: analitik.v_info_umum_wisuda (jumlah_responden = survey respondents, NOT total graduates)
- Question catalog (teks pertanyaan, skala, populasi): evaluasi_wisudawan.pertanyaan (kd_pertanyaan, kd_grup, kd_grup_opsi)
- Raw JSONB responses — only when views are insufficient: evaluasi_wisudawan.respons

COLUMN NAMING — v_wisudawan_* views:
- no_prodi (integer), kode_prodi (varchar), kode_fakultas, jenjang
- kode_pertanyaan, kode_grup_pertanyaan, kode_grup_opsi, tipe_opsi
- jumlah_responden, persentase, rata_rata, median, std_dev
- periode_ijazah_id_final ← ALWAYS use this (periode_ijazah_id is 66% NULL by design)
- tahun_ijazah, bulan_ijazah, periode_seremoni_id, nama_seremoni, tahun_seremoni, bulan_seremoni
- is_seremoni_asumtif: currently TRUE for all rows (seremoni data is placeholder); note this to the user when querying seremoni-specific data

kode_grup_pertanyaan values — use EXACT, NEVER ILIKE on kode_pertanyaan:
  U03=fasilitas ITB | U01=pendidikan/prodi/dosen | U02=rekomendasi prodi (NOMINAL)
  U04=softskill | U05=karakter | U06=masalah studi | U07=dukungan
  S1=rencana lanjut S1 | M=rencana lanjut S2 | D01=MKU S3
  FSRD01–FSRD05=FSRD specific | SBM01=SBM specific

ORDINAL vs NOMINAL:
- NEVER AVG/STDDEV on tipe_opsi='N'. Nominal questions: U02, S101, S102, S103, M01, M02, M03.
- For nominal: use v_wisudawan_distribusi_jawaban (jumlah_responden, persentase) only.
- FREKUENSI scale (U06): nilai >= 2 = "pernah mengalami". High score = more problems (negative).
- HARAPAN and HARAPAN_FSRD: both 1–5 but nilai-4 has different label — never aggregate across both.

v_wisudawan_jawaban_responden: values already decoded to label text; no JOIN to ref_opsi needed for display.
Free-text: g10q22, g01q23–g01q29 (Section E), g11q30, g01q31–g01q35 (Section F).
Section-specific (NULL for other strata/fakultas): S1→s101–s104_sq*; S2→m01–m03; S3→d01_sq*; FSRD→fsrd01–fsrd05; SBM→sbm01.
"""
