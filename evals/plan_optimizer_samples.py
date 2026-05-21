from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import sys
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.utils.plan_optimizer import optimize_plan 
from agent.state import QueryType 


@dataclass(frozen=True)
class PlanSample:
    name: str
    query: str
    query_type: QueryType
    plan: list[dict[str, Any]]
    should_be_single_sql: bool
    sql_pattern: str
    note: str


SAMPLES: list[PlanSample] = [
    PlanSample(
        name="percentage_ratio",
        query="brp persen dosen di stei yg ada di bawah kelompok keahlian rpl",
        query_type=QueryType.DATA_LOOKUP,
        plan=[
            {"task": "Hitung total dosen di STEI", "tool": "sql"},
            {"task": "Hitung dosen di STEI yang ada di bawah kelompok keahlian RPL", "tool": "sql"},
            {"task": "Hitung persentase dosen di STEI yang ada di bawah kelompok keahlian RPL", "tool": "sql"},
        ],
        should_be_single_sql=True,
        sql_pattern="CTE + conditional aggregation + ratio of aggregates",
        note="Current optimizer should compact this because it is a simple numerator/denominator metric.",
    ),
    PlanSample(
        name="conditional_counts_no_percentage",
        query="ada berapa kelas STEI dengan kelulusan tinggi dan rendah semester ini",
        query_type=QueryType.DATA_LOOKUP,
        plan=[
            {"task": "Hitung jumlah kelas STEI dengan kelulusan tinggi", "tool": "sql"},
            {"task": "Hitung jumlah kelas STEI dengan kelulusan rendah", "tool": "sql"},
        ],
        should_be_single_sql=True,
        sql_pattern="conditional aggregation with multiple COUNT(*) FILTER metrics",
        note="Should be one SQL in principle, but the current optimizer intentionally does not compact non-ratio plans yet.",
    ),
    PlanSample(
        name="kpi_bundle_cross_tables",
        query="berapa total dosen, total kk, dan total prodi di STEI",
        query_type=QueryType.DATA_LOOKUP,
        plan=[
            {"task": "Hitung total dosen di STEI", "tool": "sql"},
            {"task": "Hitung total kelompok keahlian di STEI", "tool": "sql"},
            {"task": "Hitung total prodi di STEI", "tool": "sql"},
        ],
        should_be_single_sql=True,
        sql_pattern="single-row KPI bundle using CTEs or scalar subqueries",
        note="Can be combined, but needs stronger safeguards because metrics may come from different lookup tables.",
    ),
    PlanSample(
        name="grouped_breakdown",
        query="jumlah dosen aktif per kelompok keahlian di STEI",
        query_type=QueryType.DATA_LOOKUP,
        plan=[
            {"task": "Ambil daftar KK di STEI", "tool": "sql"},
            {"task": "Hitung jumlah dosen aktif untuk setiap KK di STEI", "tool": "sql"},
        ],
        should_be_single_sql=True,
        sql_pattern="GROUP BY aggregation",
        note="This should usually be planned as one grouped query, not as loop-like per-KK counting.",
    ),
    PlanSample(
        name="comparative_multi_metric",
        query="bandingkan rata-rata nilai dan kehadiran dosen antara IF3140 dan IF2210 semester ini",
        query_type=QueryType.COMPARATIVE,
        plan=[
            {"task": "Hitung rata-rata nilai IF3140", "tool": "sql"},
            {"task": "Hitung rata-rata kehadiran dosen IF3140", "tool": "sql"},
            {"task": "Hitung rata-rata nilai IF2210", "tool": "sql"},
            {"task": "Hitung rata-rata kehadiran dosen IF2210", "tool": "sql"},
        ],
        should_be_single_sql=True,
        sql_pattern="GROUP BY comparison with multiple aggregate metrics",
        note="Best SQL shape is one grouped SELECT over kode_mk with AVG metrics.",
    ),
    PlanSample(
        name="top_n_ranking",
        query="siapa 5 dosen STEI dengan rata-rata skor evaluasi tertinggi dan berapa jumlah kelasnya",
        query_type=QueryType.COMPARATIVE,
        plan=[
            {"task": "Hitung rata-rata skor evaluasi tiap dosen STEI", "tool": "sql"},
            {"task": "Hitung jumlah kelas tiap dosen STEI", "tool": "sql"},
            {"task": "Ambil 5 dosen dengan skor tertinggi", "tool": "sql"},
        ],
        should_be_single_sql=True,
        sql_pattern="GROUP BY + ORDER BY + LIMIT ranking query",
        note="A ranking query should not be decomposed if all metrics share the same grouping grain.",
    ),
    PlanSample(
        name="window_rank_by_group",
        query="ranking prodi STEI berdasarkan rata-rata skor evaluasi dan jumlah kelas semester ini",
        query_type=QueryType.COMPARATIVE,
        plan=[
            {"task": "Hitung rata-rata skor evaluasi per prodi STEI", "tool": "sql"},
            {"task": "Hitung jumlah kelas per prodi STEI", "tool": "sql"},
            {"task": "Beri ranking prodi berdasarkan rata-rata skor evaluasi", "tool": "sql"},
        ],
        should_be_single_sql=True,
        sql_pattern="GROUP BY aggregate CTE + window function RANK()",
        note="This can be one SQL using an aggregate CTE and a window rank over the aggregate result.",
    ),
    PlanSample(
        name="diagnostic_keep_multi_step",
        query="kenapa persentase kelulusan IF3140 turun semester ini",
        query_type=QueryType.DIAGNOSTIC,
        plan=[
            {"task": "Ambil tren persentase kelulusan IF3140 beberapa semester terakhir", "tool": "sql"},
            {"task": "Ambil komentar atau refleksi terkait IF3140 semester ini", "tool": "rag"},
            {"task": "Hubungkan perubahan angka dengan konteks naratif", "tool": "rag"},
        ],
        should_be_single_sql=False,
        sql_pattern="multi-step diagnostic SQL + RAG",
        note="Even though it contains a percentage, this should stay decomposed because the user asks why.",
    ),
    PlanSample(
        name="hybrid_keep_multi_step",
        query="apakah kelas IF3140 berjalan baik dilihat dari skor evaluasi dan komentar mahasiswa",
        query_type=QueryType.ANALYTICAL_HYBRID,
        plan=[
            {"task": "Ambil skor evaluasi IF3140", "tool": "sql"},
            {"task": "Ambil komentar mahasiswa IF3140", "tool": "rag"},
        ],
        should_be_single_sql=False,
        sql_pattern="hybrid SQL + RAG",
        note="Different tools and evidence types should remain separate.",
    ),
]


def _status(value: bool) -> Text:
    return Text("yes", style="bold green") if value else Text("no", style="bold red")


def _format_plan(plan: list[dict[str, Any]]) -> str:
    lines = []
    for idx, step in enumerate(plan, 1):
        lines.append(f"{idx}. ({step.get('tool', 'sql')}) {step.get('task', '')}")
    return "\n".join(lines)


def render_summary(console: Console, samples: list[PlanSample]) -> None:
    table = Table(title="Plan Optimizer Sample Queries", show_lines=True)
    table.add_column("#", justify="right", style="dim")
    table.add_column("Case")
    table.add_column("Query Type")
    table.add_column("Should Be 1 SQL?")
    table.add_column("Optimizer Compacts?")
    table.add_column("SQL Pattern")

    for idx, sample in enumerate(samples, 1):
        optimized_plan, _ = optimize_plan(sample.query, sample.plan, sample.query_type)
        did_compact = len(optimized_plan) < len(sample.plan)
        table.add_row(
            str(idx),
            sample.name,
            sample.query_type.value,
            _status(sample.should_be_single_sql),
            _status(did_compact),
            sample.sql_pattern,
        )

    console.print(table)


def render_details(console: Console, samples: list[PlanSample]) -> None:
    for idx, sample in enumerate(samples, 1):
        optimized_plan, note = optimize_plan(sample.query, sample.plan, sample.query_type)
        did_compact = len(optimized_plan) < len(sample.plan)
        body = (
            f"[bold]Query:[/bold] {sample.query}\n"
            f"[bold]Query type:[/bold] {sample.query_type.value}\n"
            f"[bold]Should be single SQL:[/bold] {'yes' if sample.should_be_single_sql else 'no'}\n"
            f"[bold]Optimizer compacts:[/bold] {'yes' if did_compact else 'no'}\n"
            f"[bold]Pattern:[/bold] {sample.sql_pattern}\n"
            f"[bold]Note:[/bold] {sample.note}\n"
            f"[bold]Optimizer note:[/bold] {note or '-'}\n\n"
            f"[bold]Input plan[/bold]\n{_format_plan(sample.plan)}\n\n"
            f"[bold]Optimized plan[/bold]\n{_format_plan(optimized_plan)}"
        )
        console.print(Panel(body, title=f"{idx}. {sample.name}", expand=False))


def main() -> None:
    parser = argparse.ArgumentParser(description="Pretty-print plan optimizer sample cases.")
    parser.add_argument(
        "--details",
        action="store_true",
        help="Show each sample query, input plan, and optimized plan.",
    )
    args = parser.parse_args()

    console = Console()
    render_summary(console, SAMPLES)
    if args.details:
        console.print()
        render_details(console, SAMPLES)


if __name__ == "__main__":
    main()
