"""
Ingestion penuh data Portofolio & Kuesioner Akademik ITB
=====================================================================
Menjalankan 6 phase secara berurutan:

  Phase 1 — JSON  : fakultas → program_studi → kelompok_keahlian
  Phase 2 — CSV   : pertanyaan_kuesioner → pertanyaan_grup_portofolio
                    → pertanyaan_portofolio → dosen → mata_kuliah
  Phase 3 — JSON  : enrich dosen (update kk_id + insert baru dari JSON)
  Phase 4 — CSV   : kelas → pengajar_kelas
  Phase 5 — CSV   : nilai_kelas (→ statistik_kelas + skor_kuesioner_kelas)
                    nilai_dosen (→ nilai_dosen + skor_kuesioner_dosen + skor_dimensi_dosen)
  Phase 6 — CSV   : portofolio (→ teks_portofolio + komentar_verifikator)

Setiap file dicatat ke ingestion_batch + ingestion_file_log.

Prasyarat:
  - schema_portofolio_kuesioner.sql + schema_auth_and_ingestion.sql sudah dijalankan
  - File .env berisi DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD
    (atau DATABASE_URL langsung)
  - Dependensi: psycopg[binary], rapidfuzz, python-dotenv, rich

Jalankan:
  python ingest.py
  python ingest.py --data-dir /path/ke/folder/csv-dan-json
"""

import asyncio
import csv
import html
import json
import os
import sys
from pathlib import Path

import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row
from rapidfuzz import fuzz, process
from rich.console import Console
from rich.table import Table

load_dotenv()
console = Console()


# ══════════════════════════════════════════════════════════════════════════════
# KONFIGURASI
# ══════════════════════════════════════════════════════════════════════════════

def _build_dsn() -> str:
    raw = os.getenv("DATABASE_URL", "")
    if raw:
        return raw.replace("postgresql+psycopg://", "postgresql://")
    host = os.getenv("DB_HOST", "localhost")
    port = os.getenv("DB_PORT", "5432")
    name = os.getenv("DB_NAME", "akademik_itb")
    user = os.getenv("DB_USER", "postgres")
    pwd  = os.getenv("DB_PASSWORD", "")
    return f"postgresql://{user}:{pwd}@{host}:{port}/{name}"

DSN = _build_dsn()
FUZZY_THRESHOLD = 88   # RapidFuzz token_sort_ratio minimum score untuk match nama dosen


# ══════════════════════════════════════════════════════════════════════════════
# MAPPING STATIS (dikonfirmasi dari schema + instruksi)
# ══════════════════════════════════════════════════════════════════════════════

# kd_pertanyaan → dimensi (kolom di pertanyaan_kuesioner)
DIMENSI_MAP: dict[int, str | None] = {
    21: "capaian_pembelajaran",
    22: "capaian_pembelajaran",
    23: "capaian_pembelajaran",
    24: "pelaksanaan_perkuliahan",
    25: "performa_dosen",
    26: "performa_dosen",
    27: "performa_dosen",
    28: "pelaksanaan_perkuliahan",
    29: "sarana_prasarana",
    30: "sarana_prasarana",
    35: "performa_mahasiswa",
    37: "performa_mahasiswa",
    103: "komentar_mahasiswa",
    # Q128–Q152 tidak ada di dict → default None
}

ACTIVE_KD         = {21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 35, 37, 103}
SPESIFIK_DOSEN_KD = {25, 26, 27}
TEKS_BEBAS_KD     = {103}

# Prefix kode MK yang selalu NULL prodi_id (wajib institut, lintas prodi)
LINTAS_PRODI_PREFIX = {"WI"}

# Prefix kode MK untuk jenjang Profesi
PROFESI_PREFIX = {"FP", "PA", "PI"}


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS UMUM
# ══════════════════════════════════════════════════════════════════════════════

def load_json(path: Path) -> list[dict]:
    if not path.exists():
        console.print(f"[red]✗ File tidak ditemukan: {path}[/red]")
        sys.exit(1)
    data = json.loads(path.read_text(encoding="utf-8"))
    console.print(f"[dim]  → {len(data):,} baris dari {path.name}[/dim]")
    return data


def load_csv(path: Path) -> list[dict]:
    if not path.exists():
        console.print(f"[red]✗ File tidak ditemukan: {path}[/red]")
        sys.exit(1)
    with open(path, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    console.print(f"[dim]  → {len(rows):,} baris dari {path.name}[/dim]")
    return rows


def decode_entities(teks: str | None) -> str | None:
    """Decode HTML entities (&amp; &nbsp; &#39; dll) sebelum disimpan ke teks_raw.
    HTML tags sengaja dibiarkan — dihapus otomatis oleh generated column
    teks_bersih / komentar_bersih di PostgreSQL."""
    if not teks:
        return teks
    return html.unescape(teks)


def prefix_from_kd(kd_kuliah: str) -> str:
    return "".join(c for c in kd_kuliah if c.isalpha())


def jenjang_from_kd(kd_kuliah: str) -> str | None:
    """Tentukan jenjang dari kode MK berdasarkan prefix + digit pertama."""
    prefix = prefix_from_kd(kd_kuliah)
    digits = "".join(c for c in kd_kuliah if c.isdigit())
    if not digits:
        return None
    if prefix in PROFESI_PREFIX:
        return "Profesi"
    first = int(digits[0])
    if 1 <= first <= 4:
        return "S1"
    if first in (5, 6):
        return "S2"
    if 7 <= first <= 9:
        return "S3"
    return None


def fuzzy_match_nama(target: str, choices: list[str]) -> str | None:
    """Kembalikan string terbaik dari choices menggunakan token_sort_ratio,
    atau None jika tidak ada yang melewati FUZZY_THRESHOLD."""
    if not choices:
        return None
    result = process.extractOne(
        target, choices,
        scorer=fuzz.token_sort_ratio,
        score_cutoff=FUZZY_THRESHOLD,
    )
    return result[0] if result else None


def parse_ts_dna(raw: str | None):
    """Parse ts_dna CSV ('2022-01-03 10:37:54.419101 +07:00') ke datetime tz-aware."""
    if not raw:
        return None
    try:
        return __import__("datetime").datetime.fromisoformat(raw)
    except ValueError:
        return None


# ══════════════════════════════════════════════════════════════════════════════
# INGESTION BATCH & FILE LOG
# ══════════════════════════════════════════════════════════════════════════════

# GANTI fungsi buat_batch yang lama (sekitar baris 170–182) dengan ini:

ADMIN_EMAIL = "itb.ta.analytics@gmail.com"

async def buat_batch(conn) -> str:
    # Lookup user_id admin dari DB — harus sudah ada (jalankan seed_admin.py dulu)
    async with conn.cursor() as cur:
        await cur.execute(
            "SELECT pengguna_id FROM pengguna WHERE email = %(email)s AND is_active = TRUE",
            {"email": ADMIN_EMAIL},
        )
        row = await cur.fetchone()

    if not row:
        console.print(
            f"[red]✗ Admin '{ADMIN_EMAIL}' tidak ditemukan di DB.[/red]\n"
            f"  Jalankan dulu: python seed_admin.py"
        )
        raise SystemExit(1)

    user_id = str(row["pengguna_id"])

    async with conn.cursor() as cur:
        await cur.execute("""
            INSERT INTO ingestion_batch (user_id, notes, status, started_at)
            VALUES (%(user_id)s, 'Initial full ingestion — CSV + JSON', 'processing', NOW())
            RETURNING batch_id
        """, {"user_id": user_id})
        row = await cur.fetchone()

    batch_id = str(row["batch_id"])
    console.print(f"[cyan]  Batch ID : {batch_id}[/cyan]")
    return batch_id


async def log_file_start(conn, batch_id: str, jenis_file: str,
                          filename: str, total_row: int,
                          tahun_ajaran: str | None = None,
                          semester: int | None = None) -> str:
    async with conn.cursor() as cur:
        await cur.execute("""
            INSERT INTO ingestion_file_log
                (batch_id, jenis_file, original_filename,
                 tahun_ajaran, semester, status, total_row, started_at)
            VALUES
                (%(batch_id)s, %(jenis_file)s, %(filename)s,
                 %(tahun_ajaran)s, %(semester)s, 'processing', %(total_row)s, NOW())
            RETURNING log_id
        """, {
            "batch_id":    batch_id,
            "jenis_file":  jenis_file,
            "filename":    filename,
            "tahun_ajaran": tahun_ajaran,
            "semester":    semester,
            "total_row":   total_row,
        })
        row = await cur.fetchone()
    return str(row["log_id"])


async def log_file_done(conn, log_id: str, new: int, upd: int,
                         skip: int, fail: int, errors: list[dict]):
    processed = new + upd + skip
    status = "success" if fail == 0 else ("partial" if processed > 0 else "failed")
    async with conn.cursor() as cur:
        await cur.execute("""
            UPDATE ingestion_file_log SET
                status        = %(status)s,
                processed_row = %(processed)s,
                new_row       = %(new)s,
                updated_row   = %(upd)s,
                skipped_row   = %(skip)s,
                failed_row    = %(fail)s,
                error_detail  = %(errors)s,
                finished_at   = NOW()
            WHERE log_id = %(log_id)s
        """, {
            "log_id":    log_id,
            "status":    status,
            "processed": processed,
            "new":       new,
            "upd":       upd,
            "skip":      skip,
            "fail":      fail,
            "errors":    json.dumps(errors[:500]) if errors else None,
            # Batasi 500 error pertama agar JSONB tidak terlalu besar
        })


async def selesaikan_batch(conn, batch_id: str):
    async with conn.cursor() as cur:
        await cur.execute("""
            UPDATE ingestion_batch
            SET status = 'success', finished_at = NOW()
            WHERE batch_id = %(batch_id)s
        """, {"batch_id": batch_id})


# Helper: jalankan satu file dengan otomatis catat ke file log
async def run_file(conn, batch_id: str, jenis_file: str, filename: str,
                   total_row: int, coro):
    """Buat log entry, jalankan coroutine, update log saat selesai."""
    log_id = await log_file_start(conn, batch_id, jenis_file, filename, total_row)
    stats = await coro
    await log_file_done(conn, log_id,
                        stats["new"], stats["upd"], stats["skip"], stats["fail"],
                        stats.get("errors", []))
    return stats


# ══════════════════════════════════════════════════════════════════════════════
# PHASE 1 — JSON: Fakultas, Program Studi, Kelompok Keahlian
# ══════════════════════════════════════════════════════════════════════════════

async def ingest_fakultas(conn, rows: list[dict]) -> tuple[dict, dict]:
    """Return ({kode_fakultas: fakultas_id}, stats)"""
    new = upd = skip = fail = 0
    errors: list[dict] = []

    async with conn.cursor() as cur:
        for r in rows:
            try:
                await cur.execute("""
                    INSERT INTO fakultas (kode_fakultas, nama_fakultas)
                    VALUES (%(kode_fakultas)s, %(nama_fakultas)s)
                    ON CONFLICT (kode_fakultas) DO UPDATE
                        SET nama_fakultas = EXCLUDED.nama_fakultas,
                            updated_at    = NOW()
                    RETURNING (xmax = 0) AS is_new
                """, r)
                if (await cur.fetchone())["is_new"]:
                    new += 1
                else:
                    upd += 1
            except Exception as e:
                fail += 1
                errors.append({"kode": r.get("kode_fakultas"), "pesan": str(e)})

        await cur.execute("SELECT kode_fakultas, fakultas_id FROM fakultas")
        mapping = {r["kode_fakultas"]: str(r["fakultas_id"]) async for r in cur}

    console.print(f"  fakultas → new={new} upd={upd} skip={skip} fail={fail}")
    return mapping, {"new": new, "upd": upd, "skip": skip, "fail": fail, "errors": errors}


async def ingest_prodi(conn, rows: list[dict],
                       fak_map: dict) -> tuple[dict, dict]:
    """Return ({kode_prodi: prodi_id}, stats)"""
    new = upd = skip = fail = 0
    errors: list[dict] = []

    async with conn.cursor() as cur:
        for r in rows:
            fak_id = fak_map.get(r.get("kode_fakultas", ""))
            if not fak_id:
                skip += 1
                errors.append({"kode": r.get("kode_prodi"),
                                "pesan": f"kode_fakultas tidak dikenal: {r.get('kode_fakultas')}"})
                continue
            try:
                await cur.execute("""
                    INSERT INTO program_studi
                        (fakultas_id, kode_prodi, singkatan_prodi, nama_prodi, jenjang)
                    VALUES
                        (%(fak_id)s, %(kode_prodi)s, %(singkatan_prodi)s,
                         %(nama_prodi)s, %(jenjang)s)
                    ON CONFLICT (kode_prodi) DO UPDATE
                        SET nama_prodi      = EXCLUDED.nama_prodi,
                            singkatan_prodi = EXCLUDED.singkatan_prodi,
                            fakultas_id     = EXCLUDED.fakultas_id,
                            updated_at      = NOW()
                    RETURNING (xmax = 0) AS is_new
                """, {
                    "fak_id":        fak_id,
                    "kode_prodi":    r["kode_prodi"],
                    "singkatan_prodi": r.get("singkatan_prodi"),
                    "nama_prodi":    r["nama_prodi"],
                    "jenjang":       r["jenjang"],
                })
                if (await cur.fetchone())["is_new"]:
                    new += 1
                else:
                    upd += 1
            except Exception as e:
                fail += 1
                errors.append({"kode": r.get("kode_prodi"), "pesan": str(e)})

        await cur.execute("SELECT kode_prodi, prodi_id FROM program_studi")
        mapping = {r["kode_prodi"]: str(r["prodi_id"]) async for r in cur}

    console.print(f"  program_studi → new={new} upd={upd} skip={skip} fail={fail}")
    return mapping, {"new": new, "upd": upd, "skip": skip, "fail": fail, "errors": errors}


async def ingest_kk(conn, rows: list[dict],
                    fak_map: dict) -> tuple[dict, dict]:
    """Return ({nama_kk: kk_id}, stats)"""
    new = upd = skip = fail = 0
    errors: list[dict] = []

    async with conn.cursor() as cur:
        for r in rows:
            fak_id = fak_map.get(r.get("kode_fakultas", ""))
            if not fak_id:
                skip += 1
                errors.append({"nama_kk": r.get("nama_kk"),
                                "pesan": f"kode_fakultas tidak dikenal: {r.get('kode_fakultas')}"})
                continue
            try:
                await cur.execute("""
                    INSERT INTO kelompok_keahlian (fakultas_id, nama_kk)
                    VALUES (%(fak_id)s, %(nama_kk)s)
                    ON CONFLICT DO NOTHING
                    RETURNING kk_id
                """, {"fak_id": fak_id, "nama_kk": r["nama_kk"]})
                row = await cur.fetchone()
                if row:
                    new += 1
                else:
                    skip += 1  # sudah ada
            except Exception as e:
                fail += 1
                errors.append({"nama_kk": r.get("nama_kk"), "pesan": str(e)})

        await cur.execute("SELECT nama_kk, kk_id FROM kelompok_keahlian")
        mapping = {r["nama_kk"]: str(r["kk_id"]) async for r in cur}

    console.print(f"  kelompok_keahlian → new={new} upd={upd} skip={skip} fail={fail}")
    return mapping, {"new": new, "upd": upd, "skip": skip, "fail": fail, "errors": errors}


# ══════════════════════════════════════════════════════════════════════════════
# PHASE 2 — CSV: Reference tables
# ══════════════════════════════════════════════════════════════════════════════

async def ingest_pertanyaan_kuesioner(conn, rows: list[dict]) -> tuple[dict, dict]:
    """Return ({kd_pertanyaan: pertanyaan_kuesioner_id}, stats)"""
    new = upd = skip = fail = 0
    errors: list[dict] = []

    async with conn.cursor() as cur:
        for r in rows:
            kd = int(r["kd_pertanyaan"])
            try:
                await cur.execute("""
                    INSERT INTO pertanyaan_kuesioner
                        (kd_pertanyaan, pertanyaan, dimensi,
                         is_spesifik_dosen, is_teks_bebas, is_active)
                    VALUES
                        (%(kd)s, %(pertanyaan)s, %(dimensi)s,
                         %(is_spesifik_dosen)s, %(is_teks_bebas)s, %(is_active)s)
                    ON CONFLICT (kd_pertanyaan) DO UPDATE
                        SET pertanyaan        = EXCLUDED.pertanyaan,
                            dimensi           = EXCLUDED.dimensi,
                            is_spesifik_dosen = EXCLUDED.is_spesifik_dosen,
                            is_teks_bebas     = EXCLUDED.is_teks_bebas,
                            is_active         = EXCLUDED.is_active
                    RETURNING (xmax = 0) AS is_new
                """, {
                    "kd":               kd,
                    "pertanyaan":       r["pertanyaan"],
                    "dimensi":          DIMENSI_MAP.get(kd),
                    "is_spesifik_dosen": kd in SPESIFIK_DOSEN_KD,
                    "is_teks_bebas":    kd in TEKS_BEBAS_KD,
                    "is_active":        kd in ACTIVE_KD,
                })
                if (await cur.fetchone())["is_new"]:
                    new += 1
                else:
                    upd += 1
            except Exception as e:
                fail += 1
                errors.append({"kd": kd, "pesan": str(e)})

        await cur.execute("SELECT kd_pertanyaan, pertanyaan_kuesioner_id FROM pertanyaan_kuesioner")
        mapping = {int(r["kd_pertanyaan"]): str(r["pertanyaan_kuesioner_id"]) async for r in cur}

    console.print(f"  pertanyaan_kuesioner → new={new} upd={upd} skip={skip} fail={fail}")
    return mapping, {"new": new, "upd": upd, "skip": skip, "fail": fail, "errors": errors}


async def ingest_pertanyaan_grup(conn, rows: list[dict]) -> tuple[dict, dict]:
    """Return ({kd_grup: pertanyaan_grup_id}, stats)"""
    new = upd = skip = fail = 0
    errors: list[dict] = []

    async with conn.cursor() as cur:
        for r in rows:
            kd = int(r["kd_grup"])
            # kd_grup 1–5 = format lama (is_active=FALSE), 6–9 = baru (is_active=TRUE)
            is_active = kd >= 6
            try:
                await cur.execute("""
                    INSERT INTO pertanyaan_grup_portofolio (kd_grup, nama_grup, is_active)
                    VALUES (%(kd)s, %(nama_grup)s, %(is_active)s)
                    ON CONFLICT (kd_grup) DO UPDATE
                        SET nama_grup = EXCLUDED.nama_grup,
                            is_active = EXCLUDED.is_active
                    RETURNING (xmax = 0) AS is_new
                """, {"kd": kd, "nama_grup": r["pertanyaan"], "is_active": is_active})
                if (await cur.fetchone())["is_new"]:
                    new += 1
                else:
                    upd += 1
            except Exception as e:
                fail += 1
                errors.append({"kd_grup": kd, "pesan": str(e)})

        await cur.execute("SELECT kd_grup, pertanyaan_grup_id FROM pertanyaan_grup_portofolio")
        mapping = {int(r["kd_grup"]): str(r["pertanyaan_grup_id"]) async for r in cur}

    console.print(f"  pertanyaan_grup_portofolio → new={new} upd={upd} skip={skip} fail={fail}")
    return mapping, {"new": new, "upd": upd, "skip": skip, "fail": fail, "errors": errors}


async def ingest_pertanyaan_portofolio(conn, rows: list[dict],
                                        grup_map: dict) -> tuple[dict, dict]:
    """Return ({kd_pertanyaan: pertanyaan_portofolio_id}, stats)"""
    new = upd = skip = fail = 0
    errors: list[dict] = []

    async with conn.cursor() as cur:
        for r in rows:
            kd     = int(r["kd_pertanyaan"])
            grup_id = grup_map.get(int(r["kd_grup"]))
            if not grup_id:
                skip += 1
                errors.append({"kd": kd, "pesan": f"kd_grup {r['kd_grup']} tidak ditemukan"})
                continue
            # kd 1–11 = lama (is_active=FALSE), kd 12–19 = baru (is_active=TRUE)
            is_active = kd >= 12
            try:
                await cur.execute("""
                    INSERT INTO pertanyaan_portofolio
                        (pertanyaan_grup_id, kd_pertanyaan, pertanyaan, deskripsi, is_active)
                    VALUES
                        (%(grup_id)s, %(kd)s, %(pertanyaan)s, %(deskripsi)s, %(is_active)s)
                    ON CONFLICT (kd_pertanyaan) DO UPDATE
                        SET pertanyaan_grup_id = EXCLUDED.pertanyaan_grup_id,
                            pertanyaan         = EXCLUDED.pertanyaan,
                            deskripsi          = EXCLUDED.deskripsi,
                            is_active          = EXCLUDED.is_active
                    RETURNING (xmax = 0) AS is_new
                """, {
                    "grup_id":   grup_id,
                    "kd":        kd,
                    "pertanyaan": r["pertanyaan"],
                    "deskripsi": r.get("deskripsi") or None,
                    "is_active": is_active,
                })
                if (await cur.fetchone())["is_new"]:
                    new += 1
                else:
                    upd += 1
            except Exception as e:
                fail += 1
                errors.append({"kd": kd, "pesan": str(e)})

        await cur.execute("SELECT kd_pertanyaan, pertanyaan_portofolio_id FROM pertanyaan_portofolio")
        mapping = {int(r["kd_pertanyaan"]): str(r["pertanyaan_portofolio_id"]) async for r in cur}

    console.print(f"  pertanyaan_portofolio → new={new} upd={upd} skip={skip} fail={fail}")
    return mapping, {"new": new, "upd": upd, "skip": skip, "fail": fail, "errors": errors}


async def ingest_dosen_csv(conn, rows: list[dict]) -> tuple[dict, dict]:
    """INSERT dosen dari dosen.csv. Return ({six_dosen_id(int): dosen_id(str)}, stats)"""
    new = upd = skip = fail = 0
    errors: list[dict] = []

    async with conn.cursor() as cur:
        for r in rows:
            six_id = int(r["dosen_id"])
            try:
                await cur.execute("""
                    INSERT INTO dosen (six_dosen_id, nama_dosen)
                    VALUES (%(six_id)s, %(nama)s)
                    ON CONFLICT (six_dosen_id) DO UPDATE
                        SET nama_dosen = EXCLUDED.nama_dosen,
                            updated_at = NOW()
                    RETURNING (xmax = 0) AS is_new
                """, {"six_id": six_id, "nama": r["nama"]})
                if (await cur.fetchone())["is_new"]:
                    new += 1
                else:
                    upd += 1
            except Exception as e:
                fail += 1
                errors.append({"six_dosen_id": six_id, "pesan": str(e)})

        await cur.execute("""
            SELECT six_dosen_id, dosen_id FROM dosen
            WHERE six_dosen_id IS NOT NULL
        """)
        mapping = {int(r["six_dosen_id"]): str(r["dosen_id"]) async for r in cur}

    console.print(f"  dosen (CSV) → new={new} upd={upd} skip={skip} fail={fail}")
    return mapping, {"new": new, "upd": upd, "skip": skip, "fail": fail, "errors": errors}


async def ingest_matkul_csv(conn, rows: list[dict],
                            nama_mk_en_map: dict[str, str] | None = None) -> tuple[dict, dict]:
    """INSERT mata_kuliah dari CSV dengan Opsi B prefix matching.
    nama_mk_en_map: {kd_kuliah: nama_mk_en} dari matkul.json (opsional).
    Return ({six_matkul_id(int): matkul_id(str)}, stats)"""
    if nama_mk_en_map is None:
        nama_mk_en_map = {}

    # Build singkatan_prodi lookup dari DB (sudah diisi Phase 1)
    async with conn.cursor() as cur:
        await cur.execute("SELECT singkatan_prodi, jenjang, prodi_id FROM program_studi")
        singkatan_map: dict[str, list[dict]] = {}
        async for r in cur:
            sing = r["singkatan_prodi"]
            if sing and sing != "None":
                singkatan_map.setdefault(sing, []).append(dict(r))

    new = upd = skip = fail = 0
    errors: list[dict] = []

    async with conn.cursor() as cur:
        for r in rows:
            six_id = int(r["mata_kuliah_id"])
            kd     = r["kd_kuliah"]
            prefix = prefix_from_kd(kd)

            # Opsi B: resolve prodi_id dari prefix + jenjang
            prodi_id = None
            if prefix not in LINTAS_PRODI_PREFIX:
                jenjang    = jenjang_from_kd(kd)
                candidates = singkatan_map.get(prefix, [])
                if jenjang:
                    candidates = [p for p in candidates if p["jenjang"] == jenjang]
                if len(candidates) == 1:
                    prodi_id = str(candidates[0]["prodi_id"])
                elif len(candidates) > 1:
                    errors.append({
                        "kd_kuliah": kd,
                        "pesan": f"Prefix {prefix!r} ambigu → {[p['jenjang'] for p in candidates]}",
                    })

            nama_mk_en = nama_mk_en_map.get(kd) or None

            try:
                await cur.execute("""
                    INSERT INTO mata_kuliah
                        (six_matkul_id, prodi_id, kd_kuliah, nama_mk, nama_mk_en, th_kur, sks)
                    VALUES
                        (%(six_id)s, %(prodi_id)s, %(kd_kuliah)s, %(nama_mk)s,
                         %(nama_mk_en)s, %(th_kur)s, %(sks)s)
                    ON CONFLICT (six_matkul_id) DO UPDATE
                        SET kd_kuliah  = EXCLUDED.kd_kuliah,
                            nama_mk    = EXCLUDED.nama_mk,
                            nama_mk_en = COALESCE(EXCLUDED.nama_mk_en, mata_kuliah.nama_mk_en),
                            th_kur     = EXCLUDED.th_kur,
                            sks        = EXCLUDED.sks,
                            prodi_id   = COALESCE(mata_kuliah.prodi_id, EXCLUDED.prodi_id),
                            updated_at = NOW()
                    RETURNING (xmax = 0) AS is_new
                """, {
                    "six_id":     six_id,
                    "prodi_id":   prodi_id,
                    "kd_kuliah":  kd,
                    "nama_mk":    r["nama"],
                    "nama_mk_en": nama_mk_en,
                    "th_kur":     int(r["th_kur"]) if r.get("th_kur") else None,
                    "sks":        int(r["sks"]),
                })
                if (await cur.fetchone())["is_new"]:
                    new += 1
                else:
                    upd += 1
            except Exception as e:
                fail += 1
                errors.append({"six_matkul_id": six_id, "kd_kuliah": kd, "pesan": str(e)})

        await cur.execute("""
            SELECT six_matkul_id, matkul_id FROM mata_kuliah
            WHERE six_matkul_id IS NOT NULL
        """)
        mapping = {int(r["six_matkul_id"]): str(r["matkul_id"]) async for r in cur}

    console.print(f"  mata_kuliah (CSV) → new={new} upd={upd} skip={skip} fail={fail}")
    return mapping, {"new": new, "upd": upd, "skip": skip, "fail": fail, "errors": errors}


# ══════════════════════════════════════════════════════════════════════════════
# PHASE 3 — JSON: Enrich dosen (kk_id update + insert baru)
# ══════════════════════════════════════════════════════════════════════════════

async def ingest_dosen_json(conn, rows: list[dict],
                             kk_map: dict) -> tuple[list[dict], dict]:
    """UPDATE kk_id dosen CSV yang sudah ada + INSERT dosen baru dari JSON.
    Return (all_db_dosen_list, stats)"""

    # Load semua dosen dari CSV yang sudah masuk DB
    async with conn.cursor() as cur:
        await cur.execute("""
            SELECT dosen_id, nama_dosen FROM dosen
            WHERE six_dosen_id IS NOT NULL
        """)
        csv_dosen = [{"dosen_id": str(r["dosen_id"]), "nama_dosen": r["nama_dosen"]}
                     async for r in cur]

    nama_csv_list = [d["nama_dosen"] for d in csv_dosen]
    nama_to_id    = {d["nama_dosen"]: d["dosen_id"] for d in csv_dosen}

    new = 0     # dosen baru dari JSON
    upd = 0     # kk_id berhasil diupdate
    skip = 0    # match ditemukan tapi kk_id sudah ada atau tidak ada kk_id di JSON
    fail = 0
    errors: list[dict] = []

    async with conn.cursor() as cur:
        for r in rows:
            nama_json = r.get("nama_dosen", "").strip()
            if not nama_json:
                skip += 1
                continue

            kk_id = kk_map.get(r.get("nama_kk", ""))

            # Cari match: exact dulu, lalu rapidfuzz
            matched_nama = (nama_json if nama_json in nama_to_id
                            else fuzzy_match_nama(nama_json, nama_csv_list))

            if matched_nama:
                # Dosen sudah ada di CSV → update kk_id hanya jika belum ada
                dosen_uuid = nama_to_id[matched_nama]
                if kk_id:
                    try:
                        await cur.execute("""
                            UPDATE dosen
                            SET kk_id = %(kk_id)s, updated_at = NOW()
                            WHERE dosen_id = %(dosen_id)s AND kk_id IS NULL
                        """, {"kk_id": kk_id, "dosen_id": dosen_uuid})
                        if cur.rowcount > 0:
                            upd += 1
                        else:
                            skip += 1  # kk_id sudah ada, tidak perlu update
                    except Exception as e:
                        fail += 1
                        errors.append({"nama": nama_json, "pesan": str(e)})
                else:
                    skip += 1  # tidak ada kk_id di JSON untuk dosen ini
            else:
                # Tidak match → INSERT sebagai dosen baru (six_dosen_id = NULL)
                try:
                    await cur.execute("""
                        INSERT INTO dosen (six_dosen_id, nama_dosen, kk_id)
                        VALUES (NULL, %(nama)s, %(kk_id)s)
                        ON CONFLICT DO NOTHING
                        RETURNING dosen_id
                    """, {"nama": nama_json, "kk_id": kk_id})
                    row = await cur.fetchone()
                    if row:
                        new += 1
                    else:
                        skip += 1  # nama sudah ada (duplikat dari JSON)
                except Exception as e:
                    fail += 1
                    errors.append({"nama": nama_json, "pesan": str(e)})

    # Rebuild daftar semua dosen (CSV + JSON) untuk Phase 4 pengajar
    async with conn.cursor() as cur:
        await cur.execute("SELECT dosen_id, nama_dosen FROM dosen")
        all_db_dosen = [{"dosen_id": str(r["dosen_id"]), "nama_dosen": r["nama_dosen"]}
                        async for r in cur]

    console.print(
        f"  dosen (JSON enrich) → kk_id updated={upd} "
        f"dosen baru={new} skip={skip} fail={fail}"
    )
    return all_db_dosen, {"new": new, "upd": upd, "skip": skip, "fail": fail, "errors": errors}


# ══════════════════════════════════════════════════════════════════════════════
# PHASE 4 — CSV: Kelas + Pengajar
# ══════════════════════════════════════════════════════════════════════════════

async def ingest_kelas(conn, rows: list[dict],
                       matkul_map: dict,
                       prodi_map: dict) -> tuple[dict, dict]:
    """Return ({six_kelas_id(int): kelas_id(str)}, stats)"""
    new = upd = skip = fail = 0
    errors: list[dict] = []

    async with conn.cursor() as cur:
        for i, r in enumerate(rows):
            six_kelas_id  = int(r["kelas_id"])
            six_matkul_id = int(r["mata_kuliah_id"])
            no_ps_str     = str(r["no_ps"])

            matkul_id = matkul_map.get(six_matkul_id)
            prodi_id  = prodi_map.get(no_ps_str)

            if not matkul_id:
                skip += 1
                errors.append({"baris": i + 2, "six_kelas_id": six_kelas_id,
                                "pesan": f"mata_kuliah_id {six_matkul_id} tidak ditemukan"})
                continue
            if not prodi_id:
                skip += 1
                errors.append({"baris": i + 2, "six_kelas_id": six_kelas_id,
                                "pesan": f"no_ps {no_ps_str} tidak ditemukan di program_studi"})
                continue

            try:
                await cur.execute("""
                    INSERT INTO kelas
                        (six_kelas_id, matkul_id, prodi_id, no_ps,
                         tahun, semester, no_kelas)
                    VALUES
                        (%(six_kelas_id)s, %(matkul_id)s, %(prodi_id)s, %(no_ps)s,
                         %(tahun)s, %(semester)s, %(no_kelas)s)
                    ON CONFLICT (six_kelas_id) DO UPDATE
                        SET matkul_id  = EXCLUDED.matkul_id,
                            prodi_id   = EXCLUDED.prodi_id,
                            tahun      = EXCLUDED.tahun,
                            semester   = EXCLUDED.semester,
                            no_kelas   = EXCLUDED.no_kelas,
                            updated_at = NOW()
                    RETURNING (xmax = 0) AS is_new
                """, {
                    "six_kelas_id": six_kelas_id,
                    "matkul_id":    matkul_id,
                    "prodi_id":     prodi_id,
                    "no_ps":        int(no_ps_str),
                    "tahun":        int(r["tahun"]),
                    "semester":     int(r["semester"]),
                    "no_kelas":     int(r["no_kelas"]),
                })
                if (await cur.fetchone())["is_new"]:
                    new += 1
                else:
                    upd += 1
            except Exception as e:
                fail += 1
                errors.append({"baris": i + 2, "six_kelas_id": six_kelas_id, "pesan": str(e)})

        await cur.execute("""
            SELECT six_kelas_id, kelas_id FROM kelas WHERE six_kelas_id IS NOT NULL
        """)
        mapping = {int(r["six_kelas_id"]): str(r["kelas_id"]) async for r in cur}

    console.print(f"  kelas → new={new} upd={upd} skip={skip} fail={fail}")
    return mapping, {"new": new, "upd": upd, "skip": skip, "fail": fail, "errors": errors}


async def ingest_pengajar(conn, rows: list[dict],
                           kelas_map: dict,
                           dosen_six_map: dict) -> dict:
    new = upd = skip = fail = 0
    errors: list[dict] = []

    async with conn.cursor() as cur:
        for i, r in enumerate(rows):
            kelas_id = kelas_map.get(int(r["kelas_id"]))
            dosen_id = dosen_six_map.get(int(r["dosen_id"]))

            if not kelas_id:
                skip += 1
                errors.append({"baris": i + 2, "pesan": f"kelas_id {r['kelas_id']} tidak ditemukan"})
                continue
            if not dosen_id:
                skip += 1
                errors.append({"baris": i + 2, "pesan": f"dosen_id {r['dosen_id']} tidak ditemukan"})
                continue

            weight   = int(r["weight"]) if r.get("weight") else 100
            is_utama = str(r.get("utama", "true")).strip().lower() in ("true", "1", "t", "yes")

            try:
                await cur.execute("""
                    INSERT INTO pengajar_kelas (kelas_id, dosen_id, weight, is_utama)
                    VALUES (%(kelas_id)s, %(dosen_id)s, %(weight)s, %(is_utama)s)
                    ON CONFLICT (kelas_id, dosen_id) DO UPDATE
                        SET weight     = EXCLUDED.weight,
                            is_utama   = EXCLUDED.is_utama,
                            updated_at = NOW()
                    RETURNING (xmax = 0) AS is_new
                """, {
                    "kelas_id": kelas_id, "dosen_id": dosen_id,
                    "weight": weight, "is_utama": is_utama,
                })
                if (await cur.fetchone())["is_new"]:
                    new += 1
                else:
                    upd += 1
            except Exception as e:
                fail += 1
                errors.append({"baris": i + 2, "pesan": str(e)})

    console.print(f"  pengajar_kelas → new={new} upd={upd} skip={skip} fail={fail}")
    return {"new": new, "upd": upd, "skip": skip, "fail": fail, "errors": errors}


# ══════════════════════════════════════════════════════════════════════════════
# PHASE 5 — CSV: nilai_kelas + nilai_dosen
# ══════════════════════════════════════════════════════════════════════════════

async def ingest_nilai_kelas(conn, rows: list[dict],
                              kelas_map: dict, kues_map: dict) -> dict:
    """Isi statistik_kelas + skor_kuesioner_kelas dari nilai_kelas.csv."""
    sk_new = sk_upd = sk_fail = 0
    skor_new = skor_upd = skor_skip = skor_fail = 0
    errors: list[dict] = []

    async with conn.cursor() as cur:
        for i, r in enumerate(rows):
            kelas_id = kelas_map.get(int(r["kelas_id"]))
            if not kelas_id:
                sk_fail += 1
                errors.append({"baris": i + 2,
                                "pesan": f"kelas_id {r['kelas_id']} tidak ditemukan"})
                continue

            # ── statistik_kelas ───────────────────────────────────────────────
            ts_raw    = r.get("ts_dna") or None
            ts_parsed = parse_ts_dna(ts_raw)
            try:
                await cur.execute("""
                    INSERT INTO statistik_kelas
                        (kelas_id, hadir_mhs, ip_mhs, skor_dna,
                         ts_dna_raw, ts_dna, ip_mhs_dna)
                    VALUES
                        (%(kelas_id)s, %(hadir_mhs)s, %(ip_mhs)s, %(skor_dna)s,
                         %(ts_dna_raw)s, %(ts_dna)s, %(ip_mhs_dna)s)
                    ON CONFLICT (kelas_id) DO UPDATE
                        SET hadir_mhs   = EXCLUDED.hadir_mhs,
                            ip_mhs      = EXCLUDED.ip_mhs,
                            skor_dna    = EXCLUDED.skor_dna,
                            ts_dna_raw  = EXCLUDED.ts_dna_raw,
                            ts_dna      = EXCLUDED.ts_dna,
                            ip_mhs_dna  = EXCLUDED.ip_mhs_dna,
                            updated_at  = NOW()
                    RETURNING (xmax = 0) AS is_new
                """, {
                    "kelas_id":   kelas_id,
                    "hadir_mhs":  float(r["hadir_mhs"]) if r.get("hadir_mhs") else None,
                    "ip_mhs":     float(r["ip_mhs"])    if r.get("ip_mhs")    else None,
                    "skor_dna":   int(r["skor_dna"])    if r.get("skor_dna")  else None,
                    "ts_dna_raw": ts_raw,
                    "ts_dna":     ts_parsed,
                    "ip_mhs_dna": float(r["ip_mhs_dna"]) if r.get("ip_mhs_dna") else None,
                })
                if (await cur.fetchone())["is_new"]:
                    sk_new += 1
                else:
                    sk_upd += 1
            except Exception as e:
                sk_fail += 1
                errors.append({"baris": i + 2, "tabel": "statistik_kelas", "pesan": str(e)})
                continue  # skip skor jika statistik_kelas gagal

            # ── skor_kuesioner_kelas ──────────────────────────────────────────
            try:
                kuesioner_data = json.loads(r.get("kuesioner") or "{}")
            except json.JSONDecodeError:
                skor_fail += 1
                errors.append({"baris": i + 2, "pesan": "kolom kuesioner bukan JSON valid"})
                continue

            for kd_str, skor_val in kuesioner_data.items():
                kd    = int(kd_str)
                pk_id = kues_map.get(kd)
                if not pk_id:
                    skor_skip += 1
                    continue
                try:
                    await cur.execute("""
                        INSERT INTO skor_kuesioner_kelas
                            (kelas_id, pertanyaan_kuesioner_id, skor)
                        VALUES (%(kelas_id)s, %(pk_id)s, %(skor)s)
                        ON CONFLICT (kelas_id, pertanyaan_kuesioner_id) DO UPDATE
                            SET skor = EXCLUDED.skor, updated_at = NOW()
                        RETURNING (xmax = 0) AS is_new
                    """, {"kelas_id": kelas_id, "pk_id": pk_id, "skor": float(skor_val)})
                    if (await cur.fetchone())["is_new"]:
                        skor_new += 1
                    else:
                        skor_upd += 1
                except Exception as e:
                    skor_fail += 1
                    errors.append({"baris": i + 2, "kd": kd,
                                   "tabel": "skor_kuesioner_kelas", "pesan": str(e)})

    console.print(
        f"  statistik_kelas    → new={sk_new} upd={sk_upd} fail={sk_fail}\n"
        f"  skor_kues_kelas    → new={skor_new} upd={skor_upd} "
        f"skip={skor_skip} fail={skor_fail}"
    )
    total_new  = sk_new  + skor_new
    total_upd  = sk_upd  + skor_upd
    total_fail = sk_fail + skor_fail
    return {"new": total_new, "upd": total_upd, "skip": skor_skip,
            "fail": total_fail, "errors": errors}


async def ingest_nilai_dosen(conn, rows: list[dict],
                              kelas_map: dict,
                              dosen_six_map: dict,
                              kues_map: dict) -> dict:
    """Isi nilai_dosen + skor_kuesioner_dosen + skor_dimensi_dosen."""
    nd_new = nd_upd = nd_fail = 0
    skd_new = skd_upd = skd_fail = 0
    sdd_new = sdd_upd = sdd_fail = 0
    errors: list[dict] = []

    async with conn.cursor() as cur:
        for i, r in enumerate(rows):
            kelas_id = kelas_map.get(int(r["kelas_id"]))
            dosen_id = dosen_six_map.get(int(r["dosen_id"]))

            if not kelas_id or not dosen_id:
                nd_fail += 1
                errors.append({
                    "baris": i + 2,
                    "pesan": (f"kelas_id {r['kelas_id']} atau "
                              f"dosen_id {r['dosen_id']} tidak ditemukan"),
                })
                continue

            # ── nilai_dosen ───────────────────────────────────────────────────
            nilai_akhir = float(r["nilai_akhir"]) if r.get("nilai_akhir") else None
            try:
                await cur.execute("""
                    INSERT INTO nilai_dosen (kelas_id, dosen_id, nilai_akhir)
                    VALUES (%(kelas_id)s, %(dosen_id)s, %(nilai_akhir)s)
                    ON CONFLICT (kelas_id, dosen_id) DO UPDATE
                        SET nilai_akhir = EXCLUDED.nilai_akhir, updated_at = NOW()
                    RETURNING (xmax = 0) AS is_new
                """, {"kelas_id": kelas_id, "dosen_id": dosen_id, "nilai_akhir": nilai_akhir})
                if (await cur.fetchone())["is_new"]:
                    nd_new += 1
                else:
                    nd_upd += 1
            except Exception as e:
                nd_fail += 1
                errors.append({"baris": i + 2, "tabel": "nilai_dosen", "pesan": str(e)})
                continue

            # ── skor_kuesioner_dosen (Q25, Q26, Q27) ─────────────────────────
            try:
                kuesioner_data = json.loads(r.get("kuesioner") or "{}")
            except json.JSONDecodeError:
                kuesioner_data = {}

            for kd_str, skor_val in kuesioner_data.items():
                kd    = int(kd_str)
                pk_id = kues_map.get(kd)
                if not pk_id:
                    continue
                try:
                    await cur.execute("""
                        INSERT INTO skor_kuesioner_dosen
                            (kelas_id, dosen_id, pertanyaan_kuesioner_id, skor)
                        VALUES (%(kelas_id)s, %(dosen_id)s, %(pk_id)s, %(skor)s)
                        ON CONFLICT (kelas_id, dosen_id, pertanyaan_kuesioner_id) DO UPDATE
                            SET skor = EXCLUDED.skor, updated_at = NOW()
                        RETURNING (xmax = 0) AS is_new
                    """, {"kelas_id": kelas_id, "dosen_id": dosen_id,
                          "pk_id": pk_id, "skor": float(skor_val)})
                    if (await cur.fetchone())["is_new"]:
                        skd_new += 1
                    else:
                        skd_upd += 1
                except Exception as e:
                    skd_fail += 1
                    errors.append({"baris": i + 2, "kd": kd,
                                   "tabel": "skor_kuesioner_dosen", "pesan": str(e)})

            # ── skor_dimensi_dosen (key 1, 2, 3) ─────────────────────────────
            try:
                skor_kues_data = json.loads(r.get("skor_kues") or "{}")
            except json.JSONDecodeError:
                skor_kues_data = {}

            for dim_str, skor_val in skor_kues_data.items():
                dim_key = int(dim_str)
                try:
                    await cur.execute("""
                        INSERT INTO skor_dimensi_dosen
                            (kelas_id, dosen_id, dimensi_key, skor)
                        VALUES (%(kelas_id)s, %(dosen_id)s, %(dim_key)s, %(skor)s)
                        ON CONFLICT (kelas_id, dosen_id, dimensi_key) DO UPDATE
                            SET skor = EXCLUDED.skor, updated_at = NOW()
                        RETURNING (xmax = 0) AS is_new
                    """, {"kelas_id": kelas_id, "dosen_id": dosen_id,
                          "dim_key": dim_key, "skor": float(skor_val)})
                    if (await cur.fetchone())["is_new"]:
                        sdd_new += 1
                    else:
                        sdd_upd += 1
                except Exception as e:
                    sdd_fail += 1
                    errors.append({"baris": i + 2, "dim": dim_key,
                                   "tabel": "skor_dimensi_dosen", "pesan": str(e)})

    console.print(
        f"  nilai_dosen        → new={nd_new} upd={nd_upd} fail={nd_fail}\n"
        f"  skor_kues_dosen    → new={skd_new} upd={skd_upd} fail={skd_fail}\n"
        f"  skor_dimensi_dosen → new={sdd_new} upd={sdd_upd} fail={sdd_fail}"
    )
    return {
        "new":  nd_new  + skd_new  + sdd_new,
        "upd":  nd_upd  + skd_upd  + sdd_upd,
        "skip": 0,
        "fail": nd_fail + skd_fail + sdd_fail,
        "errors": errors,
    }


# ══════════════════════════════════════════════════════════════════════════════
# PHASE 6 — CSV: Portofolio
# ══════════════════════════════════════════════════════════════════════════════

async def ingest_portofolio(conn, rows: list[dict],
                             kelas_map: dict,
                             porto_map: dict,
                             grup_map: dict) -> dict:
    """Isi teks_portofolio + komentar_verifikator dari portofolio.csv."""
    tp_new = tp_upd = tp_skip = tp_fail = 0
    kv_new = kv_upd = kv_skip = kv_fail = 0
    errors: list[dict] = []

    async with conn.cursor() as cur:
        for i, r in enumerate(rows):
            kelas_id = kelas_map.get(int(r["kelas_id"]))
            if not kelas_id:
                tp_fail += 1
                errors.append({"baris": i + 2,
                                "pesan": f"kelas_id {r['kelas_id']} tidak ditemukan"})
                continue

            # ── teks_portofolio ───────────────────────────────────────────────
            try:
                isian_data = json.loads(r.get("isian") or "{}")
                if not isinstance(isian_data, dict):
                    isian_data = {}
            except json.JSONDecodeError:
                tp_fail += 1
                errors.append({"baris": i + 2, "kelas": r["kelas_id"],
                                "pesan": "kolom isian bukan JSON valid"})
                isian_data = {}

            for kd_str, teks_val in isian_data.items():
                kd    = int(kd_str)
                pp_id = porto_map.get(kd)
                if not pp_id:
                    tp_skip += 1
                    continue

                # Decode HTML entities; tags dibiarkan untuk generated column DB
                teks_cleaned = decode_entities(str(teks_val) if teks_val else None)

                try:
                    await cur.execute("""
                        INSERT INTO teks_portofolio
                            (kelas_id, pertanyaan_portofolio_id, teks_raw)
                        VALUES (%(kelas_id)s, %(pp_id)s, %(teks_raw)s)
                        ON CONFLICT (kelas_id, pertanyaan_portofolio_id) DO UPDATE
                            SET teks_raw   = EXCLUDED.teks_raw,
                                updated_at = NOW()
                        RETURNING (xmax = 0) AS is_new
                    """, {"kelas_id": kelas_id, "pp_id": pp_id, "teks_raw": teks_cleaned})
                    if (await cur.fetchone())["is_new"]:
                        tp_new += 1
                    else:
                        tp_upd += 1
                except Exception as e:
                    tp_fail += 1
                    errors.append({"baris": i + 2, "kd": kd,
                                   "tabel": "teks_portofolio", "pesan": str(e)})

            # ── komentar_verifikator ──────────────────────────────────────────
            try:
                komentar_data = json.loads(r.get("komentar") or "{}")
            except json.JSONDecodeError:
                kv_fail += 1
                errors.append({"baris": i + 2, "kelas": r["kelas_id"],
                                "pesan": "kolom komentar bukan JSON valid"})
                komentar_data = {}

            for kd_str, komentar_val in komentar_data.items():
                kd_grup = int(kd_str)
                pg_id   = grup_map.get(kd_grup)
                if not pg_id:
                    kv_skip += 1
                    continue

                komentar_cleaned = decode_entities(
                    str(komentar_val) if komentar_val else None
                )

                try:
                    await cur.execute("""
                        INSERT INTO komentar_verifikator
                            (kelas_id, pertanyaan_grup_id, komentar_raw)
                        VALUES (%(kelas_id)s, %(pg_id)s, %(komentar_raw)s)
                        ON CONFLICT (kelas_id, pertanyaan_grup_id) DO UPDATE
                            SET komentar_raw = EXCLUDED.komentar_raw,
                                updated_at   = NOW()
                        RETURNING (xmax = 0) AS is_new
                    """, {"kelas_id": kelas_id, "pg_id": pg_id,
                          "komentar_raw": komentar_cleaned})
                    if (await cur.fetchone())["is_new"]:
                        kv_new += 1
                    else:
                        kv_upd += 1
                except Exception as e:
                    kv_fail += 1
                    errors.append({"baris": i + 2, "kd_grup": kd_grup,
                                   "tabel": "komentar_verifikator", "pesan": str(e)})

    console.print(
        f"  teks_portofolio      → new={tp_new} upd={tp_upd} "
        f"skip={tp_skip} fail={tp_fail}\n"
        f"  komentar_verifikator → new={kv_new} upd={kv_upd} "
        f"skip={kv_skip} fail={kv_fail}"
    )
    return {
        "new":  tp_new  + kv_new,
        "upd":  tp_upd  + kv_upd,
        "skip": tp_skip + kv_skip,
        "fail": tp_fail + kv_fail,
        "errors": errors,
    }


# ══════════════════════════════════════════════════════════════════════════════
# RINGKASAN AKHIR
# ══════════════════════════════════════════════════════════════════════════════

async def cetak_ringkasan(conn):
    queries = [
        ("fakultas",                   "SELECT COUNT(*) FROM fakultas"),
        ("kelompok_keahlian",          "SELECT COUNT(*) FROM kelompok_keahlian"),
        ("program_studi",              "SELECT COUNT(*) FROM program_studi"),
        ("dosen (total)",              "SELECT COUNT(*) FROM dosen"),
        ("  ↳ dari CSV (six_id ada)",  "SELECT COUNT(*) FROM dosen WHERE six_dosen_id IS NOT NULL"),
        ("  ↳ dari JSON (six_id NULL)","SELECT COUNT(*) FROM dosen WHERE six_dosen_id IS NULL"),
        ("mata_kuliah",                "SELECT COUNT(*) FROM mata_kuliah"),
        ("  ↳ dengan prodi_id",        "SELECT COUNT(*) FROM mata_kuliah WHERE prodi_id IS NOT NULL"),
        ("pertanyaan_kuesioner",       "SELECT COUNT(*) FROM pertanyaan_kuesioner"),
        ("pertanyaan_grup_portofolio", "SELECT COUNT(*) FROM pertanyaan_grup_portofolio"),
        ("pertanyaan_portofolio",      "SELECT COUNT(*) FROM pertanyaan_portofolio"),
        ("kelas",                      "SELECT COUNT(*) FROM kelas"),
        ("pengajar_kelas",             "SELECT COUNT(*) FROM pengajar_kelas"),
        ("statistik_kelas",            "SELECT COUNT(*) FROM statistik_kelas"),
        ("nilai_dosen",                "SELECT COUNT(*) FROM nilai_dosen"),
        ("skor_kuesioner_kelas",       "SELECT COUNT(*) FROM skor_kuesioner_kelas"),
        ("skor_kuesioner_dosen",       "SELECT COUNT(*) FROM skor_kuesioner_dosen"),
        ("skor_dimensi_dosen",         "SELECT COUNT(*) FROM skor_dimensi_dosen"),
        ("teks_portofolio",            "SELECT COUNT(*) FROM teks_portofolio"),
        ("komentar_verifikator",       "SELECT COUNT(*) FROM komentar_verifikator"),
    ]
    tbl = Table(title="Ringkasan Row Count Setelah Ingestion", border_style="cyan")
    tbl.add_column("Tabel", style="cyan",  no_wrap=True)
    tbl.add_column("Rows",  style="green", justify="right")
    async with conn.cursor() as cur:
        for label, q in queries:
            await cur.execute(q)
            row = await cur.fetchone()
            count = row["count"] if row else 0   # "count" = nama kolom COUNT(*)
            tbl.add_row(label, f"{count:,}")
    console.print(tbl)


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

async def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="ITB Portofolio & Kuesioner — Full Ingestion"
    )
    parser.add_argument(
        "--data-dir", default=".",
        help="Direktori berisi file CSV + JSON (default: direktori saat ini)"
    )
    args   = parser.parse_args()
    d      = Path(args.data_dir)

    console.print("\n[bold cyan]══════════════════════════════════════════[/bold cyan]")
    console.print("[bold cyan]  ITB — Ingestion Portofolio & Kuesioner  [/bold cyan]")
    console.print("[bold cyan]══════════════════════════════════════════[/bold cyan]\n")
    console.print(f"[dim]Data dir : {d.resolve()}[/dim]")
    console.print(f"[dim]DB       : {DSN.split('@')[-1]}[/dim]\n")

    async with await psycopg.AsyncConnection.connect(DSN, row_factory=dict_row) as conn:

        # ── Buat ingestion batch ──────────────────────────────────────────────
        console.print("[bold]Membuat ingestion batch...[/bold]")
        batch_id = await buat_batch(conn)
        await conn.commit()
        console.print()

        # ════════════════════════════════════════════════════════════════════
        # PHASE 1 — JSON: Fakultas, Prodi, KK
        # ════════════════════════════════════════════════════════════════════
        console.print("[bold yellow]── PHASE 1: JSON Reference Data ──[/bold yellow]")

        rows_fak   = load_json(d / "fakultas.json")
        log_id = await log_file_start(conn, batch_id, "dosen", "fakultas.json", len(rows_fak))
        fak_map, stats = await ingest_fakultas(conn, rows_fak)
        await log_file_done(conn, log_id, stats["new"], stats["upd"],
                            stats["skip"], stats["fail"], stats["errors"])
        await conn.commit()

        rows_prodi = load_json(d / "prodi.json")
        log_id = await log_file_start(conn, batch_id, "dosen", "prodi.json", len(rows_prodi))
        prodi_map, stats = await ingest_prodi(conn, rows_prodi, fak_map)
        await log_file_done(conn, log_id, stats["new"], stats["upd"],
                            stats["skip"], stats["fail"], stats["errors"])
        await conn.commit()

        rows_kk    = load_json(d / "kk.json")
        log_id = await log_file_start(conn, batch_id, "dosen", "kk.json", len(rows_kk))
        kk_map, stats = await ingest_kk(conn, rows_kk, fak_map)
        await log_file_done(conn, log_id, stats["new"], stats["upd"],
                            stats["skip"], stats["fail"], stats["errors"])
        await conn.commit()
        console.print()

        # ════════════════════════════════════════════════════════════════════
        # PHASE 2 — CSV: Reference tables
        # ════════════════════════════════════════════════════════════════════
        console.print("[bold yellow]── PHASE 2: CSV Reference Tables ──[/bold yellow]")

        rows_pk = load_csv(d / "pertanyaan_kuesioner.csv")
        log_id  = await log_file_start(conn, batch_id, "pertanyaan_kuesioner",
                                       "pertanyaan_kuesioner.csv", len(rows_pk))
        kues_map, stats = await ingest_pertanyaan_kuesioner(conn, rows_pk)
        await log_file_done(conn, log_id, stats["new"], stats["upd"],
                            stats["skip"], stats["fail"], stats["errors"])
        await conn.commit()

        rows_pg = load_csv(d / "pertanyaan_grup_portofolio.csv")
        log_id  = await log_file_start(conn, batch_id, "pertanyaan_grup_portofolio",
                                       "pertanyaan_grup_portofolio.csv", len(rows_pg))
        grup_map, stats = await ingest_pertanyaan_grup(conn, rows_pg)
        await log_file_done(conn, log_id, stats["new"], stats["upd"],
                            stats["skip"], stats["fail"], stats["errors"])
        await conn.commit()

        rows_pp = load_csv(d / "pertanyaan_portofolio.csv")
        log_id  = await log_file_start(conn, batch_id, "pertanyaan_portofolio",
                                       "pertanyaan_portofolio.csv", len(rows_pp))
        porto_qmap, stats = await ingest_pertanyaan_portofolio(conn, rows_pp, grup_map)
        await log_file_done(conn, log_id, stats["new"], stats["upd"],
                            stats["skip"], stats["fail"], stats["errors"])
        await conn.commit()

        rows_dos = load_csv(d / "dosen.csv")
        log_id   = await log_file_start(conn, batch_id, "dosen", "dosen.csv", len(rows_dos))
        dosen_six_map, stats = await ingest_dosen_csv(conn, rows_dos)
        await log_file_done(conn, log_id, stats["new"], stats["upd"],
                            stats["skip"], stats["fail"], stats["errors"])
        await conn.commit()

        rows_mk = load_csv(d / "mata_kuliah.csv")
        matkul_json_path = d / "matkul.json"
        if matkul_json_path.exists():
            rows_mkj = load_json(matkul_json_path)
            nama_mk_en_map = {r["kode_mk"]: r.get("nama_mk_en") or None for r in rows_mkj}
        else:
            nama_mk_en_map = {}
            console.print("[yellow]  ⚠ matkul.json tidak ditemukan, nama_mk_en akan NULL[/yellow]")
        log_id  = await log_file_start(conn, batch_id, "mata_kuliah",
                                       "mata_kuliah.csv", len(rows_mk))
        matkul_map, stats = await ingest_matkul_csv(conn, rows_mk, nama_mk_en_map)
        await log_file_done(conn, log_id, stats["new"], stats["upd"],
                            stats["skip"], stats["fail"], stats["errors"])
        await conn.commit()
        console.print()

        # ════════════════════════════════════════════════════════════════════
        # PHASE 3 — JSON: Enrich dosen
        # ════════════════════════════════════════════════════════════════════
        console.print("[bold yellow]── PHASE 3: JSON Enrich Dosen ──[/bold yellow]")

        rows_dj = load_json(d / "dosen.json")
        log_id  = await log_file_start(conn, batch_id, "dosen", "dosen.json", len(rows_dj))
        all_db_dosen, stats = await ingest_dosen_json(conn, rows_dj, kk_map)
        await log_file_done(conn, log_id, stats["new"], stats["upd"],
                            stats["skip"], stats["fail"], stats["errors"])
        await conn.commit()
        console.print()

        # ════════════════════════════════════════════════════════════════════
        # PHASE 4 — CSV: Kelas + Pengajar
        # ════════════════════════════════════════════════════════════════════
        console.print("[bold yellow]── PHASE 4: CSV Kelas & Pengajar ──[/bold yellow]")

        rows_kl = load_csv(d / "kelas.csv")
        log_id  = await log_file_start(conn, batch_id, "kelas", "kelas.csv", len(rows_kl))
        kelas_map, stats = await ingest_kelas(conn, rows_kl, matkul_map, prodi_map)
        await log_file_done(conn, log_id, stats["new"], stats["upd"],
                            stats["skip"], stats["fail"], stats["errors"])
        await conn.commit()

        rows_pg2 = load_csv(d / "pengajar.csv")
        log_id   = await log_file_start(conn, batch_id, "pengajar", "pengajar.csv", len(rows_pg2))
        stats    = await ingest_pengajar(conn, rows_pg2, kelas_map, dosen_six_map)
        await log_file_done(conn, log_id, stats["new"], stats["upd"],
                            stats["skip"], stats["fail"], stats["errors"])
        await conn.commit()
        console.print()

        # ════════════════════════════════════════════════════════════════════
        # PHASE 5 — CSV: Assessment
        # ════════════════════════════════════════════════════════════════════
        console.print("[bold yellow]── PHASE 5: CSV Assessment Data ──[/bold yellow]")

        rows_nk = load_csv(d / "nilai_kelas.csv")
        log_id  = await log_file_start(conn, batch_id, "nilai_kelas",
                                       "nilai_kelas.csv", len(rows_nk))
        stats   = await ingest_nilai_kelas(conn, rows_nk, kelas_map, kues_map)
        await log_file_done(conn, log_id, stats["new"], stats["upd"],
                            stats["skip"], stats["fail"], stats["errors"])
        await conn.commit()

        rows_nd = load_csv(d / "nilai_dosen.csv")
        log_id  = await log_file_start(conn, batch_id, "nilai_dosen",
                                       "nilai_dosen.csv", len(rows_nd))
        stats   = await ingest_nilai_dosen(conn, rows_nd, kelas_map, dosen_six_map, kues_map)
        await log_file_done(conn, log_id, stats["new"], stats["upd"],
                            stats["skip"], stats["fail"], stats["errors"])
        await conn.commit()
        console.print()

        # ════════════════════════════════════════════════════════════════════
        # PHASE 6 — CSV: Portofolio
        # ════════════════════════════════════════════════════════════════════
        console.print("[bold yellow]── PHASE 6: CSV Portofolio Teks ──[/bold yellow]")

        rows_po = load_csv(d / "portofolio.csv")
        log_id  = await log_file_start(conn, batch_id, "portofolio",
                                       "portofolio.csv", len(rows_po))
        stats   = await ingest_portofolio(conn, rows_po, kelas_map, porto_qmap, grup_map)
        await log_file_done(conn, log_id, stats["new"], stats["upd"],
                            stats["skip"], stats["fail"], stats["errors"])
        await conn.commit()
        console.print()

        # ── Tutup batch + ringkasan ───────────────────────────────────────────
        await selesaikan_batch(conn, batch_id)
        await conn.commit()

        await cetak_ringkasan(conn)

    console.print("\n[bold green]✓ Ingestion selesai.[/bold green]\n")


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())