"""
Loads scraped JSON files into PostgreSQL in dependency order:
fakultas → prodi → kk → dosen → matkul

Run: uv run python ingestion/ingest_master.py
"""
import asyncio
import json
import pathlib
import sys
import os
from dotenv import load_dotenv
load_dotenv()

import psycopg
from psycopg.rows import dict_row
from rich.console import Console
from rich.table import Table

console = Console()
DATA_DIR = pathlib.Path("data/raw")
DATABASE_URL = os.environ["DATABASE_URL"].replace(
    "postgresql+psycopg://", "postgresql://"
)

def load(filename: str) -> list[dict]:
    path = DATA_DIR / filename
    if not path.exists():
        console.print(f"[red]✗ File not found: {path}[/red]")
        sys.exit(1)
    data = json.loads(path.read_text())
    console.print(f"[dim]  Loaded {len(data)} rows from {filename}[/dim]")
    return data


def check_keys(data: list[dict], required: list[str], filename: str):
    if not data:
        console.print(f"[yellow]⚠ {filename} is empty[/yellow]")
        return
    actual = set(data[0].keys())
    missing = set(required) - actual
    if missing:
        console.print(f"[red]✗ {filename} missing keys: {missing}[/red]")
        console.print(f"  Got: {actual}")
        sys.exit(1)


# ── Step 1: Fakultas ──────────────────────────────────────────────────────────
async def ingest_fakultas(conn) -> dict[str, str]:
    rows = load("fakultas.json")
    check_keys(rows, ["kode_fakultas", "nama_fakultas"], "fakultas.json")

    async with conn.cursor() as cur:
        await cur.executemany("""
            INSERT INTO fakultas (kode_fakultas, nama_fakultas)
            VALUES (%(kode_fakultas)s, %(nama_fakultas)s)
            ON CONFLICT (kode_fakultas) DO UPDATE
                SET nama_fakultas = EXCLUDED.nama_fakultas,
                    updated_at    = NOW()
        """, rows)

        await cur.execute("SELECT kode_fakultas, fakultas_id FROM fakultas")
        mapping = {r["kode_fakultas"]: str(r["fakultas_id"]) async for r in cur}

    console.print(f"[green]✓ fakultas: {len(rows)} rows upserted[/green]")
    return mapping



# ── Step 2: Program Studi ─────────────────────────────────────────────────────

async def ingest_prodi(conn, fak_map: dict) -> dict[str, str]:
    rows = load("prodi.json")
    check_keys(rows, ["kode_prodi", "singkatan_prodi", "nama_prodi", "jenjang", "kode_fakultas"], "prodi.json")

    enriched, skipped = [], []
    for r in rows:
        fak_id = fak_map.get(r["kode_fakultas"])
        if not fak_id:
            skipped.append(r["kode_prodi"])
            continue
        enriched.append({
            "fakultas_id":     fak_id,
            "kode_prodi":      r["kode_prodi"],
            "singkatan_prodi": r["singkatan_prodi"],
            "nama_prodi":      r["nama_prodi"],
            "jenjang":         r["jenjang"],
        })

    if skipped:
        console.print(f"[yellow]⚠ prodi skipped (unknown fakultas): {skipped}[/yellow]")

    async with conn.cursor() as cur:
        await cur.executemany("""
            INSERT INTO program_studi
                (fakultas_id, kode_prodi, singkatan_prodi, nama_prodi, jenjang)
            VALUES
                (%(fakultas_id)s, %(kode_prodi)s, %(singkatan_prodi)s,
                 %(nama_prodi)s,  %(jenjang)s)
            ON CONFLICT (kode_prodi) DO UPDATE
                SET nama_prodi      = EXCLUDED.nama_prodi,
                    singkatan_prodi = EXCLUDED.singkatan_prodi,
                    updated_at      = NOW()
        """, enriched)

        await cur.execute("SELECT kode_prodi, prodi_id FROM program_studi")
        mapping = {r["kode_prodi"]: str(r["prodi_id"]) async for r in cur}

    console.print(f"[green]✓ prodi: {len(enriched)} rows upserted[/green]")
    return mapping


# ── Step 3: Kelompok Keahlian ─────────────────────────────────────────────────

async def ingest_kk(conn, fak_map: dict) -> dict[str, str]:
    rows = load("kk.json")
    check_keys(rows, ["nama_kk", "kode_fakultas"], "kk.json")

    enriched = []
    for r in rows:
        fak_id = fak_map.get(r["kode_fakultas"])
        if not fak_id:
            console.print(f"[yellow]⚠ KK skipped unknown fakultas: {r['kode_fakultas']}[/yellow]")
            continue
        enriched.append({"fakultas_id": fak_id, "nama_kk": r["nama_kk"]})

    
    async with conn.cursor() as cur:
        await cur.executemany("""
            INSERT INTO kelompok_keahlian (fakultas_id, nama_kk)
            VALUES (%(fakultas_id)s, %(nama_kk)s)
            ON CONFLICT DO NOTHING
        """, enriched)

    async with conn.cursor() as cur:
        await cur.execute("SELECT nama_kk, kk_id FROM kelompok_keahlian")
        mapping = {r["nama_kk"]: str(r["kk_id"]) async for r in cur}
    console.print(f"[green]✓ kk: {len(enriched)} rows upserted[/green]")
    return mapping


# ── Step 4: Dosen ─────────────────────────────────────────────────────────────

async def ingest_dosen(conn, kk_map: dict):
    rows = load("dosen.json")
    check_keys(rows, ["nama_dosen"], "dosen.json")

    enriched = []
    no_kk = 0
    for r in rows:
        kk_id = kk_map.get(r.get("nama_kk"))
        if not kk_id:
            no_kk += 1
        enriched.append({"nama_dosen": r["nama_dosen"], "kk_id": kk_id})

    async with conn.cursor() as cur:
        await cur.executemany("""
            INSERT INTO dosen (nama_dosen, kk_id)
        VALUES (%(nama_dosen)s, %(kk_id)s)
        ON CONFLICT DO NOTHING
    """, enriched)

    if no_kk:
        console.print(f"[yellow]⚠ {no_kk} dosen inserted without KK mapping[/yellow]")
    console.print(f"[green]✓ dosen: {len(enriched)} rows upserted[/green]")


# ── Step 5: Mata Kuliah ───────────────────────────────────────────────────────

async def ingest_matkul(conn, prodi_map: dict):
    rows = load("matkul.json")
    check_keys(rows, ["kode_mk", "nama_mk", "nama_mk_en", "kode_prodi", "kategori", "jenis_nilai"], "matkul.json")

    enriched = []
    skipped  = []
    for r in rows:
        prodi_id = prodi_map.get(str(r["kode_prodi"]))
        if not prodi_id:
            skipped.append(r["kode_mk"])
            continue
        enriched.append({
            "prodi_id": prodi_id,
            "kode_mk":  r["kode_mk"],
            "nama_mk":  r["nama_mk"],
            "nama_mk_en": r["nama_mk_en"],
            "kategori": r["kategori"],
            "jenis_nilai": r["jenis_nilai"]
        })

    if skipped:
        console.print(f"[yellow]⚠ matkul skipped (unknown prodi): {skipped[:5]}{'...' if len(skipped)>5 else ''}[/yellow]")

    async with conn.cursor() as cur:
        await cur.executemany("""
            INSERT INTO mata_kuliah (prodi_id, kode_mk, nama_mk, nama_mk_en, kategori, jenis_nilai)
            VALUES (%(prodi_id)s, %(kode_mk)s, %(nama_mk)s, %(nama_mk_en)s, %(kategori)s, %(jenis_nilai)s)
            ON CONFLICT (kode_mk, prodi_id) DO UPDATE
                SET nama_mk    = EXCLUDED.nama_mk,
                    nama_mk_en = EXCLUDED.nama_mk_en,
                    updated_at = NOW()
        """, enriched)

    console.print(f"[green]✓ matkul: {len(enriched)} rows upserted[/green]")


# ── Summary Table ─────────────────────────────────────────────────────────────

async def print_summary(conn):
    queries = {
        "fakultas":         "SELECT COUNT(*) FROM fakultas",
        "program_studi":    "SELECT COUNT(*) FROM program_studi",
        "kelompok_keahlian":"SELECT COUNT(*) FROM kelompok_keahlian",
        "dosen":            "SELECT COUNT(*) FROM dosen",
        "mata_kuliah":      "SELECT COUNT(*) FROM mata_kuliah",
    }
    table = Table(title="DB Row Counts After Ingestion")
    table.add_column("Table", style="cyan")
    table.add_column("Rows",  style="green", justify="right")

    for name, query in queries.items():
        cur = await conn.execute(query)
        row = await cur.fetchone()
        table.add_row(name, str(row[0]))

    console.print(table)


async def main():
    console.print("\n[bold cyan]── ITB Master Data Ingestion ──[/bold cyan]\n")

    async with await psycopg.AsyncConnection.connect(
        DATABASE_URL, row_factory=dict_row
    ) as conn:
        async with conn.transaction():
            fak_map   = await ingest_fakultas(conn)
            prodi_map = await ingest_prodi(conn, fak_map)
            kk_map    = await ingest_kk(conn, fak_map)
            await ingest_dosen(conn, kk_map)
            await ingest_matkul(conn, prodi_map)

        # await print_summary(conn)

    console.print("\n[bold green]✓ Ingestion complete[/bold green]\n")


if __name__ == "__main__":
    asyncio.run(main())