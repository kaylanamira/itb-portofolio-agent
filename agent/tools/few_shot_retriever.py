"""
Few-shot example retriever for SQL generator.

Strategy: Hardcoded examples grouped by QueryType.
These are derived from `core/dashboard_queries.py`.
"""

from agent.state import QueryType

_EXAMPLES: dict[QueryType, list[tuple[str, str]]] = {

    QueryType.DATA_LOOKUP: [
        (
            "Berapa rata-rata nilai mahasiswa di kelas IF3140 K1 semester ini?",
            "SELECT rata_rata_nilai FROM mv_kelas WHERE {SCOPE_FILTER} AND kode_mk = 'IF3140' AND no_kelas = '1' AND semester = 1 AND tahun_ajaran = '2024/2025' LIMIT 1;",
        ),
        (
            "Siapa saja dosen yang mengajar matkul basis data semester ini?",
            "SELECT DISTINCT unnest(semua_dosen_nama) AS nama_dosen FROM mv_kelas WHERE {SCOPE_FILTER} AND nama_mk ILIKE '%basis data%' AND semester = 1 AND tahun_ajaran = '2024/2025' ORDER BY nama_dosen LIMIT 100;",
        ),
        (
            "Berapa jumlah kelas di prodi IF semester ini?",
            "SELECT COUNT(*) AS jumlah_kelas FROM mv_kelas WHERE singkatan_prodi='IF' AND semester = 1 AND tahun_ajaran = '2024/2025';",
        ),
        (
            "Ada berapa fakultas di ITB?",
            "SELECT COUNT(*) AS total_fakultas FROM fakultas WHERE {SCOPE_FILTER} AND is_active = TRUE;",
        ),
        (
            "Berapa persentase kehadiran dosen IF3140?",
            "SELECT pct_kehadiran_dosen FROM mv_kelas WHERE {SCOPE_FILTER} AND kode_mk = 'IF3140';",
        )
    ],

    QueryType.ANALYTICAL_NUMERIC: [
        (
            "Bagaimana tren nilai mahasiswa IF3140 dua tahun terakhir?",
            "SELECT tahun_ajaran, semester, AVG(rata_rata_nilai) AS avg_nilai FROM mv_kelas WHERE {SCOPE_FILTER} AND kode_mk = 'IF3140' GROUP BY tahun_ajaran, semester ORDER BY tahun_ajaran, semester LIMIT 100;",
        ),
        (
            "Bagaimana perbandingan kehadiran dosen dan mahasiswa di prodi ini semester ini?",
            "SELECT AVG(pct_kehadiran_dosen) AS avg_kehadiran_dosen, AVG(pct_kehadiran_mahasiswa) AS avg_kehadiran_mahasiswa FROM mv_kelas WHERE {SCOPE_FILTER} AND semester = 1 AND tahun_ajaran = '2024/2025';",
        ),
    ],

    QueryType.COMPARATIVE: [
        (
            "Bandingkan skor evaluasi IF2210 dan IF3140 semester ini",
            "SELECT kode_mk, nama_mk, no_kelas, skor_avg_overall FROM mv_kelas WHERE {SCOPE_FILTER} AND kode_mk IN ('IF2210', 'IF3140') AND semester = 1 AND tahun_ajaran = '2024/2025' ORDER BY kode_mk, no_kelas LIMIT 100;",
        ),
        (
            "Perbandingan rata-rata nilai per dosen di prodi semester ini",
            "SELECT unnest(semua_dosen_nama) AS nama_dosen, AVG(rata_rata_nilai) AS avg_nilai FROM mv_kelas WHERE {SCOPE_FILTER} AND semester = 1 AND tahun_ajaran = '2024/2025' GROUP BY nama_dosen ORDER BY avg_nilai DESC LIMIT 100;",
        ),
    ],

    QueryType.DIAGNOSTIC: [
        (
            "Kenapa nilai kelas IF3140 K2 lebih rendah dari K1 semester ini?",
            "SELECT no_kelas, rata_rata_nilai, pct_kehadiran_dosen, pct_kehadiran_mahasiswa, skor_avg_overall FROM mv_kelas WHERE {SCOPE_FILTER} AND kode_mk = 'IF3140' AND semester = 1 AND tahun_ajaran = '2024/2025' ORDER BY no_kelas LIMIT 100;",
        ),
    ],

    QueryType.CHART_GENERATE: [
        (
            "Tunjukkan grafik distribusi nilai mahasiswa IF3140 K1",
            "SELECT 'A' AS grade, dist_jumlah_A AS jumlah FROM mv_kelas WHERE {SCOPE_FILTER} AND kode_mk = 'IF3140' AND no_kelas = '1' AND semester = 1 UNION ALL SELECT 'AB', dist_jumlah_AB FROM mv_kelas WHERE {SCOPE_FILTER} AND kode_mk = 'IF3140' AND no_kelas = '1' AND semester = 1 UNION ALL SELECT 'B', dist_jumlah_B FROM mv_kelas WHERE {SCOPE_FILTER} AND kode_mk = 'IF3140' AND no_kelas = '1' AND semester = 1 UNION ALL SELECT 'BC', dist_jumlah_BC FROM mv_kelas WHERE {SCOPE_FILTER} AND kode_mk = 'IF3140' AND no_kelas = '1' AND semester = 1 UNION ALL SELECT 'C', dist_jumlah_C FROM mv_kelas WHERE {SCOPE_FILTER} AND kode_mk = 'IF3140' AND no_kelas = '1' AND semester = 1 UNION ALL SELECT 'D', dist_jumlah_D FROM mv_kelas WHERE {SCOPE_FILTER} AND kode_mk = 'IF3140' AND no_kelas = '1' AND semester = 1 UNION ALL SELECT 'E', dist_jumlah_E FROM mv_kelas WHERE {SCOPE_FILTER} AND kode_mk = 'IF3140' AND no_kelas = '1' AND semester = 1;",
        ),
        (
            "Buat grafik tren rata-rata nilai per semester untuk matkul IF2210",
            "SELECT tahun_ajaran, semester, ROUND(AVG(rata_rata_nilai)::numeric, 2) AS avg_nilai FROM mv_kelas WHERE {SCOPE_FILTER} AND kode_mk = 'IF2210' GROUP BY tahun_ajaran, semester ORDER BY tahun_ajaran, semester LIMIT 100;",
        ),
    ],

    QueryType.DATA_LOOKUP: [
        # Dosen-scoped general info about their prodi (read-only, lookup tables)
        (
            "Berapa total prodi di fakultas saya?",
            "SELECT COUNT(*) AS total_prodi FROM program_studi WHERE {SCOPE_FILTER} AND is_active = TRUE;",
        ),
    ],
}


def retrieve_few_shots(query_type: QueryType, n: int = 3) -> str:
    """
    Returns example of question and sql queries.

    Args:
        query_type: The classified query type.
        n: Max number of examples to return.

    Returns:
        Formatted string ready for `{few_shot_examples}` in the prompt.
    """
    examples = _EXAMPLES.get(query_type, [])
    
    # Fallback to DATA_LOOKUP examples if none found for this type
    if not examples:
        examples = _EXAMPLES.get(QueryType.DATA_LOOKUP, [])

    selected = examples[:n]
    if not selected:
        return "(no examples available)"

    lines = []
    for i, (nl, sql) in enumerate(selected, 1):
        lines.append(f"Example {i}:\n  NL: {nl}\n  SQL: {sql}")

    return "\n\n".join(lines)
