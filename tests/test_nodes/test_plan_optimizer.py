from agent.utils.plan_optimizer import optimize_plan, should_compact_ratio_plan
from agent.state import QueryType


def test_compacts_simple_ratio_sql_plan():
    query = "brp persen dosen di stei yg ada di bawah kelompok keahlian rpl"
    plan = [
        {"task": "Hitung total dosen di STEI", "tool": "sql"},
        {"task": "Hitung dosen di STEI yang ada di bawah kelompok keahlian RPL", "tool": "sql"},
        {"task": "Hitung persentase dosen di STEI yang ada di bawah kelompok keahlian RPL", "tool": "sql"},
    ]

    optimized, note = optimize_plan(query, plan, QueryType.DATA_LOOKUP)

    assert note is not None
    assert optimized == [
        {
            "task": (
                "Jawab query pengguna dalam satu SQL: hitung pembilang, penyebut, "
                "dan persentase/rasio menggunakan CTE atau conditional aggregation. "
                f"Query pengguna: {query}"
            ),
            "tool": "sql",
        }
    ]


def test_does_not_compact_diagnostic_plan():
    query = "kenapa persentase kelulusan IF3140 turun semester ini?"
    plan = [
        {"task": "Ambil tren persentase kelulusan IF3140", "tool": "sql"},
        {"task": "Ambil komentar mahasiswa IF3140", "tool": "rag"},
    ]

    assert not should_compact_ratio_plan(query, plan, QueryType.DIAGNOSTIC)


def test_does_not_compact_non_ratio_sql_plan():
    query = "siapa saja dosen di STEI?"
    plan = [
        {"task": "Ambil daftar dosen di STEI", "tool": "sql"},
        {"task": "Urutkan nama dosen di STEI", "tool": "sql"},
    ]

    optimized, note = optimize_plan(query, plan, QueryType.DATA_LOOKUP)

    assert note is None
    assert optimized == plan
