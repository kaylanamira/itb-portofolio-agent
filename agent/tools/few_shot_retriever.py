"""
Few-shot example retriever for SQL generator.

Strategy: Hardcoded examples grouped by QueryType.
These are derived from `core/dashboard_queries.py`.

Future migration path:
    The `retrieve_few_shots()` function accepts an optional `loader` callable
    with signature `(QueryType, int) -> list[tuple[str, str]]`.
    To migrate to YAML/DB-backed examples, pass a custom loader here without
    changing any node code.

    Example:
        from agent.tools.few_shot_retriever import retrieve_few_shots
        from my_yaml_loader import yaml_loader

        # In tests or production DI:
        result = retrieve_few_shots(query_type, loader=yaml_loader)
"""

from typing import Callable, Optional
from agent.state import QueryType

_EXAMPLES: dict[QueryType, list[tuple[str, str]]] = {

    QueryType.DATA_LOOKUP: [
        (
            "Berapa rata-rata nilai mahasiswa di kelas IF3140 K1 semester ini?",
            "SELECT rata_rata_nilai FROM mv_kelas WHERE {SCOPE_FILTER} AND kode_mk = 'IF3140' AND no_kelas = '1' AND semester = 1 AND tahun_ajaran = '2024/2025' LIMIT 1;",
        ),
        (
            "Siapa saja dosen yang mengajar matkul basis data semester ini?",
            "SELECT DISTINCT unnest(semua_dosen_nama) AS nama_dosen FROM analitik.mv_kelas WHERE {SCOPE_FILTER} AND nama_mk ILIKE '%basis data%' AND semester = 1 AND tahun_ajaran = '2024/2025' ORDER BY nama_dosen LIMIT 100;",
        ),
        (
            "Berapa jumlah kelas di prodi IF semester ini?",
            "SELECT COUNT(*) AS jumlah_kelas FROM analitik.mv_kelas WHERE {SCOPE_FILTER} AND singkatan_prodi = 'IF' AND semester = 1 AND tahun_ajaran = '2024/2025';",
        ),
        (
            "Ada berapa fakultas di ITB?",
            "SELECT COUNT(*) AS total_fakultas FROM fakultas WHERE {SCOPE_FILTER} AND is_active = TRUE;",
        ),
        (
            "Berapa persentase kehadiran dosen IF3140?",
            "SELECT kode_mk, no_kelas, pct_kehadiran_dosen FROM mv_kelas WHERE {SCOPE_FILTER} AND kode_mk = 'IF3140';",
        ),
        (
            "Brp persen dosen di STEI yg ada di bawah kelompok keahlian RPL?",
            "WITH stei_dosen AS (SELECT DISTINCT d.dosen_id, kk.nama_kk, f.kode_fakultas, f.nama_fakultas FROM dosen d JOIN kelompok_keahlian kk ON kk.kk_id = d.kk_id JOIN fakultas f ON f.fakultas_id = kk.fakultas_id WHERE {SCOPE_FILTER} AND f.kode_fakultas = 'STEI' AND d.is_active = TRUE AND f.is_active = TRUE), summary AS (SELECT kode_fakultas, nama_fakultas, COUNT(*) AS total_dosen, COUNT(*) FILTER (WHERE nama_kk ILIKE '%%Rekayasa Perangkat Lunak%%') AS total_dosen_rpl FROM stei_dosen GROUP BY kode_fakultas, nama_fakultas) SELECT nama_fakultas, kode_fakultas, total_dosen, total_dosen_rpl, ROUND(total_dosen_rpl * 100.0 / NULLIF(total_dosen, 0), 2) AS persentase_dosen_rpl FROM summary;",
        ),
        (
            "Berapa total prodi di fakultas saya?",
            "SELECT COUNT(*) AS total_prodi FROM program_studi WHERE {SCOPE_FILTER} AND is_active = TRUE;",
        ),
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
        (
            # HAVING example: filter on aggregated values
            "Prodi mana yang rata-rata nilai mahasiswanya di atas 3.0 semester ini?",
            "SELECT singkatan_prodi, nama_prodi, AVG(rata_rata_nilai) AS avg_nilai FROM mv_kelas WHERE {SCOPE_FILTER} AND semester = 1 AND tahun_ajaran = '2024/2025' GROUP BY prodi_id, singkatan_prodi, nama_prodi HAVING AVG(rata_rata_nilai) > 3.0 ORDER BY avg_nilai DESC LIMIT 100;",
        ),
        (
            # WINDOW FUNCTION example: ranking within partitions
            "Ranking dosen berdasarkan skor evaluasi per prodi semester ini?",
            "SELECT singkatan_prodi, unnest(semua_dosen_nama) AS nama_dosen, skor_avg_overall, RANK() OVER (PARTITION BY prodi_id ORDER BY skor_avg_overall DESC) AS rank_dalam_prodi FROM mv_kelas WHERE {SCOPE_FILTER} AND semester = 1 AND tahun_ajaran = '2024/2025' ORDER BY singkatan_prodi, rank_dalam_prodi LIMIT 100;",
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
            # UNION ALL with {SCOPE_FILTER} repeated in each branch
            "SELECT 'A' AS grade, COALESCE(dist_jumlah_A, 0) AS jumlah FROM mv_kelas WHERE {SCOPE_FILTER} AND kode_mk = 'IF3140' AND no_kelas = '1' AND semester = 1 UNION ALL SELECT 'AB', COALESCE(dist_jumlah_AB, 0) FROM mv_kelas WHERE {SCOPE_FILTER} AND kode_mk = 'IF3140' AND no_kelas = '1' AND semester = 1 UNION ALL SELECT 'B', COALESCE(dist_jumlah_B, 0) FROM mv_kelas WHERE {SCOPE_FILTER} AND kode_mk = 'IF3140' AND no_kelas = '1' AND semester = 1 UNION ALL SELECT 'BC', COALESCE(dist_jumlah_BC, 0) FROM mv_kelas WHERE {SCOPE_FILTER} AND kode_mk = 'IF3140' AND no_kelas = '1' AND semester = 1 UNION ALL SELECT 'C', COALESCE(dist_jumlah_C, 0) FROM mv_kelas WHERE {SCOPE_FILTER} AND kode_mk = 'IF3140' AND no_kelas = '1' AND semester = 1 UNION ALL SELECT 'D', COALESCE(dist_jumlah_D, 0) FROM mv_kelas WHERE {SCOPE_FILTER} AND kode_mk = 'IF3140' AND no_kelas = '1' AND semester = 1 UNION ALL SELECT 'E', COALESCE(dist_jumlah_E, 0) FROM mv_kelas WHERE {SCOPE_FILTER} AND kode_mk = 'IF3140' AND no_kelas = '1' AND semester = 1;",
        ),
        (
            "Buat grafik tren rata-rata nilai per semester untuk matkul IF2210",
            "SELECT tahun_ajaran, semester, ROUND(AVG(rata_rata_nilai)::numeric, 2) AS avg_nilai FROM mv_kelas WHERE {SCOPE_FILTER} AND kode_mk = 'IF2210' GROUP BY tahun_ajaran, semester ORDER BY tahun_ajaran, semester LIMIT 100;",
        ),
    ],

}


def retrieve_few_shots(
    query_type: QueryType,
    n: int = 3,
    loader: Optional[Callable[[QueryType, int], list[tuple[str, str]]]] = None,
) -> str:
    """
    Returns formatted few-shot SQL examples for the given query type.

    Args:
        query_type: The classified query type.
        n: Max number of examples to return.
        loader: Optional external loader callable with signature
                (QueryType, int) -> list[tuple[str, str]].
                When provided, the built-in _EXAMPLES dict is bypassed.
                This enables YAML/DB-backed examples without changing node code.

    Returns:
        Formatted string ready for `{few_shot_examples}` in the SQL generator prompt.
    """
    if loader is not None:
        examples = loader(query_type, n)
    else:
        examples = _EXAMPLES.get(query_type, [])
        if not examples:
            examples = _EXAMPLES.get(QueryType.DATA_LOOKUP, [])

    selected = examples[:n]
    if not selected:
        return "(no examples available)"

    lines = []
    for i, (nl, sql) in enumerate(selected, 1):
        lines.append(f"Example {i}:\n  NL: {nl}\n  SQL: {sql}")

    return "\n\n".join(lines)
