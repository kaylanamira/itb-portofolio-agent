"""
Ingests kelas + pengajar_kelas from a JSON file produced by scraping SIX.

JSON format expected:
[
    {
        "kode_mk": "IF1210",
        "nama_mk": "Algoritma dan Pemrograman 1",
        "sks": 3,
        "kelas": "01",
        "dosen": ["Yani Widyani", "Tricya Esterina Widagdo"]
    },
    ...
]

Usage:
    uv run python ingestion/ingest_kelas_pengajar.py \
        --file data/processed/kelas_pengajar.json \
        --semester 1 \
        --tahun-ajaran 2024/2025
"""

import asyncio
import json
import argparse
import os
import sys
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()

import psycopg
from psycopg.rows import dict_row
from rich.console import Console
from rich.table import Table

console = Console()

DATABASE_URL = os.environ["DATABASE_URL"].replace(
    "postgresql+psycopg://", "postgresql://"
)


# ── Name matching ─────────────────────────────────────────────────────────────

def match_dosen_name(json_name: str, db_dosen: list[dict]) -> dict | None:
    json_name_clean = json_name.strip().lower()
    json_words = set(json_name_clean.split())

    # Pass 1: exact match
    for d in db_dosen:
        if d["nama_dosen"].strip().lower() == json_name_clean:
            return d

    # Pass 2: all JSON words appear in DB name
    for d in db_dosen:
        db_name_lower = d["nama_dosen"].lower()
        if all(w in db_name_lower for w in json_words):
            return d

    # Pass 3: last two words of DB name match last two words of JSON name
    # handles "Yani Widyani" matching "Dr. Ir. Yani Widyani, M.T."
    json_parts = json_name_clean.split()
    if len(json_parts) >= 2:
        for d in db_dosen:
            db_words = d["nama_dosen"].lower().replace(",", "").split()
            # Check if json words are a subset of db words
            if set(json_parts).issubset(set(db_words)):
                return d

    return None


# ── Core ingestion ─────────────────────────────────────────────────────────────

async def ingest(json_path: Path, semester: int, tahun_ajaran: str):
    raw = json.loads(json_path.read_text(encoding="utf-8"))

    console.print(f"\n[bold cyan]── Kelas + Pengajar Ingestion ──[/bold cyan]")
    console.print(f"File     : {json_path}")
    console.print(f"Semester : {semester}")
    console.print(f"TA       : {tahun_ajaran}")
    console.print(f"Rows     : {len(raw)}\n")

    async with await psycopg.AsyncConnection.connect(
        DATABASE_URL, row_factory=dict_row
    ) as conn:

        # ── Load lookup tables ────────────────────────────────────────────────

        async with conn.cursor() as cur:
            # matkul lookup: {kode_mk: matkul_id}
            await cur.execute("SELECT kode_mk, matkul_id FROM mata_kuliah")
            matkul_map = {r["kode_mk"]: str(r["matkul_id"]) async for r in cur}

            # dosen lookup: full list for fuzzy matching
            await cur.execute("SELECT dosen_id, nama_dosen FROM dosen WHERE is_active = TRUE")
            db_dosen = [{"dosen_id": str(r["dosen_id"]), "nama_dosen": r["nama_dosen"]}
                        async for r in cur]

        console.print(f"[dim]Loaded {len(matkul_map)} matkul, {len(db_dosen)} dosen from DB[/dim]\n")

        # ── Process rows ──────────────────────────────────────────────────────

        stats = {
            "kelas_inserted": 0,
            "kelas_skipped_exists": 0,
            "kelas_skipped_no_matkul": 0,
            "pengajar_inserted": 0,
            "dosen_not_found": [],
            "matkul_not_found": [],
        }

        async with conn.transaction():
            for row in raw:
                kode_mk   = row.get("kode_mk", "").strip()
                no_kelas  = str(row.get("kelas", "")).strip().lstrip("0") or "1"
                sks       = int(row.get("sks", 3))
                dosen_names = row.get("dosen", [])

                # ── Resolve matkul_id ─────────────────────────────────────────
                matkul_id = matkul_map.get(kode_mk)
                if not matkul_id:
                    console.print(f"[yellow]⚠ matkul not found: {kode_mk} — skipping[/yellow]")
                    stats["matkul_not_found"].append(kode_mk)
                    stats["kelas_skipped_no_matkul"] += 1
                    continue

                # ── Upsert kelas ──────────────────────────────────────────────
                async with conn.cursor() as cur:
                    await cur.execute("""
                        INSERT INTO kelas
                            (matkul_id, no_kelas, semester, tahun_ajaran, sks)
                        VALUES
                            (%(matkul_id)s, %(no_kelas)s, %(semester)s,
                             %(tahun_ajaran)s, %(sks)s)
                        ON CONFLICT (matkul_id, no_kelas, semester, tahun_ajaran)
                            DO UPDATE SET sks = EXCLUDED.sks
                        RETURNING kelas_id, xmax
                    """, {
                        "matkul_id":   matkul_id,
                        "no_kelas":    no_kelas,
                        "semester":    semester,
                        "tahun_ajaran": tahun_ajaran,
                        "sks":         sks,
                    })
                    result = await cur.fetchone()
                    kelas_id = str(result["kelas_id"])
                    was_inserted = result["xmax"] == 0  # xmax=0 means fresh insert

                if was_inserted:
                    stats["kelas_inserted"] += 1
                else:
                    stats["kelas_skipped_exists"] += 1

                # ── Resolve and insert pengajar ───────────────────────────────
                for dosen_name in dosen_names:
                    matched = match_dosen_name(dosen_name, db_dosen)

                    if not matched:
                        console.print(
                            f"[red]✗ Dosen not matched: '{dosen_name}' "
                            f"(kelas {kode_mk}-{no_kelas})[/red]"
                        )
                        stats["dosen_not_found"].append({
                            "name": dosen_name,
                            "kelas": f"{kode_mk}-K{no_kelas}"
                        })
                        continue

                    async with conn.cursor() as cur:
                        await cur.execute("""
                            INSERT INTO pengajar_kelas (kelas_id, dosen_id)
                            VALUES (%(kelas_id)s, %(dosen_id)s)
                            ON CONFLICT (kelas_id, dosen_id) DO NOTHING
                        """, {
                            "kelas_id": kelas_id,
                            "dosen_id": matched["dosen_id"],
                        })
                        stats["pengajar_inserted"] += 1

        # ── Summary ───────────────────────────────────────────────────────────

        table = Table(title="Ingestion Summary")
        table.add_column("Metric", style="cyan")
        table.add_column("Value",  style="green", justify="right")
        table.add_row("Kelas inserted",          str(stats["kelas_inserted"]))
        table.add_row("Kelas already existed",   str(stats["kelas_skipped_exists"]))
        table.add_row("Kelas skipped (no matkul)", str(stats["kelas_skipped_no_matkul"]))
        table.add_row("Pengajar rows inserted",  str(stats["pengajar_inserted"]))
        table.add_row("Dosen not matched",       str(len(stats["dosen_not_found"])))
        table.add_row("Matkul not in DB",        str(len(set(stats["matkul_not_found"]))))
        console.print(table)

        if stats["dosen_not_found"]:
            console.print("\n[red]Unmatched dosen — add manually or fix names in JSON:[/red]")
            for d in stats["dosen_not_found"]:
                console.print(f"  '{d['name']}' in {d['kelas']}")

        if stats["matkul_not_found"]:
            console.print("\n[yellow]Matkul not in DB — scrape or seed them first:[/yellow]")
            for mk in set(stats["matkul_not_found"]):
                console.print(f"  {mk}")

        console.print("\n[bold green]✓ Done[/bold green]\n")


# ── CLI ────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Ingest kelas + pengajar from JSON")
    parser.add_argument("--file",         required=True,  help="Path to JSON file")
    parser.add_argument("--semester",     required=True,  type=int, choices=[1, 2, 3],
                        help="1=Ganjil, 2=Genap, 3=Pendek")
    parser.add_argument("--tahun-ajaran", required=True,
                        help="Format YYYY/YYYY e.g. 2024/2025")
    args = parser.parse_args()

    # Validate tahun_ajaran format
    import re
    if not re.match(r"^\d{4}/\d{4}$", args.tahun_ajaran):
        console.print("[red]✗ tahun-ajaran must be YYYY/YYYY format[/red]")
        sys.exit(1)

    asyncio.run(ingest(
        json_path=Path(args.file),
        semester=args.semester,
        tahun_ajaran=args.tahun_ajaran,
    ))

if __name__ == "__main__":
    main()