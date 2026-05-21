"""
seed_admin.py — Seed akun admin + akun testing lengkap
========================================================
Menjalankan dua fungsi utama:
  1. seed_admin()          : buat/update akun admin (email+password)
  2. seed_test_accounts()  : buat akun SSO dummy untuk testing RLS

Akun yang dibuat:
  [admin]          itb.ta.analytics@gmail.com          → peran: admin
  [direktorat]     direktorat.wram@itb.ac.id            → peran: direktorat
  [dekan]          dekan.fmipa@itb.ac.id                → peran: dekan (FMIPA)
  [jajaran_dekanat] wakildekan.fmipa@itb.ac.id          → peran: jajaran_dekanat (FMIPA)
  [dekan]          dekan.fti@itb.ac.id                  → peran: dekan (FTI)
  [jajaran_dekanat] wakildekan.fti@itb.ac.id            → peran: jajaran_dekanat (FTI)
  [kaprodi]        kaprodi.fisika@itb.ac.id             → peran: kaprodi (prodi 102 Fisika S1)
  [kaprodi]        kaprodi.teknik-kimia@itb.ac.id       → peran: kaprodi (prodi 230 TK S2)
  [dosen]          5 dosen Fisika S1  (dari dosen.csv)  → peran: dosen (prodi 102)
  [dosen]          5 dosen Teknik Kimia S2 (dosen.csv)  → peran: dosen (prodi 230)

Prasyarat:
  - schema_portofolio_kuesioner.sql + schema_auth_and_ingestion.sql sudah dijalankan
  - ingest_academic.py sudah dijalankan (tabel dosen, program_studi, fakultas terisi)
  - .env berisi DATABASE_URL atau DB_HOST/DB_PORT/DB_NAME/DB_USER/DB_PASSWORD
  - ADMIN_PASSWORD di .env (atau diinput interaktif)

Jalankan:
  uv run python seed_admin.py
  uv run python seed_admin.py --email other@gmail.com --nama "Nama Lain"
  uv run python seed_admin.py --skip-test   # hanya seed admin, skip akun testing
"""

import argparse
import asyncio
import getpass
import os
import sys

import bcrypt
import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row
from rich.console import Console
from rich.table import Table

load_dotenv()
console = Console()


# ── Dosen dari dosen.csv yang akan dibuat akun (six_dosen_id: nama) ──────────
# Prodi 102 — Fisika S1 (FMIPA)
DOSEN_PRODI_102 = [
    (594, "Farhan Ramadhan"),
    (441, "Maya Suhendra"),
    (335, "Wahyu Hartono"),
    (287, "Setyo Efendi"),
    (475, "Nina Sulistyo"),
]

# Prodi 230 — Teknik Kimia S2 (FTI)
DOSEN_PRODI_230 = [
    (796, "Nugroho Laksana"),
    (525, "Ratna Suryadi"),
    (395, "Endah Nasution"),
    (265, "Mulyono Yulianto"),
    (763, "Joko Handoko"),
]


# ══════════════════════════════════════════════════════════════════════════════
# KONEKSI DB
# ══════════════════════════════════════════════════════════════════════════════

def _build_dsn() -> str:
    raw = os.getenv("DATABASE_URL", "")
    if raw:
        return raw.replace("postgresql+psycopg://", "postgresql://")
    host = os.getenv("DB_HOST", "localhost")
    port = os.getenv("DB_PORT", "5432")
    name = os.getenv("DB_NAME", os.getenv("POSTGRES_DB"))
    user = os.getenv("DB_USER", os.getenv("POSTGRES_USER"))
    pwd  = os.getenv("DB_PASSWORD", os.getenv("POSTGRES_PASSWORD"))
    return f"postgresql://{user}:{pwd}@{host}:{port}/{name}"


def hash_password(plaintext: str) -> str:
    return bcrypt.hashpw(plaintext.encode("utf-8"), bcrypt.gensalt(12)).decode("utf-8")


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════════

async def upsert_user(cur, email: str, name: str,
                       auth_method: str = "sso_microsoft",
                       password_hash: str | None = None) -> str:
    """
    Insert atau update user. Return user_id (str).
    Tidak mengubah password_hash jika user sudah ada dan password_hash=None.
    """
    await cur.execute(
        "SELECT user_id, auth_method FROM users WHERE email = %(email)s",
        {"email": email},
    )
    existing = await cur.fetchone()

    if existing:
        if password_hash:
            await cur.execute("""
                UPDATE users
                SET name = %(name)s, auth_method = %(auth_method)s,
                    password_hash = %(pw)s, updated_at = NOW()
                WHERE user_id = %(user_id)s
            """, {"name": name, "auth_method": auth_method,
                  "pw": password_hash, "user_id": str(existing["user_id"])})
        else:
            await cur.execute("""
                UPDATE users
                SET name = %(name)s, updated_at = NOW()
                WHERE user_id = %(user_id)s
            """, {"name": name, "user_id": str(existing["user_id"])})
        return str(existing["user_id"])

    await cur.execute("""
        INSERT INTO users (email, name, auth_method, password_hash, is_active)
        VALUES (%(email)s, %(name)s, %(auth_method)s, %(pw)s, TRUE)
        RETURNING user_id
    """, {"email": email, "name": name,
          "auth_method": auth_method, "pw": password_hash})
    row = await cur.fetchone()
    return str(row["user_id"])


async def upsert_scope(cur, user_id: str, user_role: str,
                        fakultas_id: str | None = None,
                        prodi_id: str | None = None,
                        dosen_id: str | None = None):
    """Tambah/aktifkan scope untuk user. Unik per (user_id, user_role, prodi_id, fakultas_id)."""
    await cur.execute("""
        INSERT INTO user_scopes
            (user_id, user_role, fakultas_id, prodi_id, dosen_id, is_active)
        VALUES
            (%(user_id)s, %(user_role)s, %(fakultas_id)s,
             %(prodi_id)s, %(dosen_id)s, TRUE)
        ON CONFLICT DO NOTHING
    """, {
        "user_id":     user_id,
        "user_role":   user_role,
        "fakultas_id": fakultas_id,
        "prodi_id":    prodi_id,
        "dosen_id":    dosen_id,
    })


async def get_fakultas_id(cur, kode_fakultas: str) -> str | None:
    await cur.execute(
        "SELECT fakultas_id FROM fakultas WHERE kode_fakultas = %(kode)s",
        {"kode": kode_fakultas},
    )
    row = await cur.fetchone()
    return str(row["fakultas_id"]) if row else None


async def get_prodi_id(cur, kode_prodi: str) -> str | None:
    await cur.execute(
        "SELECT prodi_id FROM program_studi WHERE kode_prodi = %(kode)s",
        {"kode": kode_prodi},
    )
    row = await cur.fetchone()
    return str(row["prodi_id"]) if row else None


async def get_dosen_id_by_six(cur, six_dosen_id: int) -> str | None:
    await cur.execute(
        "SELECT dosen_id FROM dosen WHERE six_dosen_id = %(sid)s",
        {"sid": six_dosen_id},
    )
    row = await cur.fetchone()
    return str(row["dosen_id"]) if row else None


def email_from_nama(nama: str) -> str:
    """Buat email dummy ITB dari nama dosen."""
    return nama.lower().replace(" ", ".") + "@itb.ac.id"


# ══════════════════════════════════════════════════════════════════════════════
# SEED ADMIN (password-based)
# ══════════════════════════════════════════════════════════════════════════════

async def seed_admin(email: str, nama: str, password: str):
    dsn = _build_dsn()
    console.print(f"\n[dim]DB: {dsn.split('@')[-1]}[/dim]")

    async with await psycopg.AsyncConnection.connect(dsn, row_factory=dict_row) as conn:
        async with conn.cursor() as cur:
            pw_hash = hash_password(password)
            user_id = await upsert_user(
                cur, email, nama,
                auth_method="password", password_hash=pw_hash,
            )
            await upsert_scope(cur, user_id, "admin")
        await conn.commit()

    console.print(f"\n[green]✓ Admin berhasil dibuat/diupdate[/green]")
    console.print(f"  email       : {email}")
    console.print(f"  nama        : {nama}")
    console.print(f"  metode_auth : password")
    console.print(f"  peran       : admin\n")


# ══════════════════════════════════════════════════════════════════════════════
# SEED TEST ACCOUNTS (SSO-based, tanpa password)
# ══════════════════════════════════════════════════════════════════════════════

async def seed_test_accounts(conn):
    """
    Buat akun dummy untuk testing RLS dan materialized view.
    Semua akun SSO (tidak perlu password). Gunakan data nyata dari dosen.csv.
    """
    results: list[dict] = []

    async with conn.cursor() as cur:

        # ── Lookup referensi ──────────────────────────────────────────────────
        fak_fmipa = await get_fakultas_id(cur, "FMIPA")
        fak_fti   = await get_fakultas_id(cur, "FTI")
        prodi_102 = await get_prodi_id(cur, "102")   # Fisika S1
        prodi_230 = await get_prodi_id(cur, "230")   # Teknik Kimia S2

        # Validasi — ingestion harus sudah jalan dulu
        missing = []
        if not fak_fmipa: missing.append("fakultas FMIPA")
        if not fak_fti:   missing.append("fakultas FTI")
        if not prodi_102: missing.append("program_studi kode 102")
        if not prodi_230: missing.append("program_studi kode 230")

        if missing:
            console.print(
                f"[red]✗ Data referensi tidak ditemukan: {', '.join(missing)}[/red]\n"
                f"  Pastikan ingest_academic.py sudah dijalankan terlebih dahulu."
            )
            return results

        # ── 1. Direktorat (scope global) ─────────────────────────────────────
        uid = await upsert_user(cur, "direktorat.wram@itb.ac.id",
                                 "Direktorat WRAM ITB")
        await upsert_scope(cur, uid, "direktorat")
        results.append({"email": "direktorat.wram@itb.ac.id",
                         "peran": "direktorat", "scope": "global"})

        # ── 2. Dekanat FMIPA ─────────────────────────────────────────────────
        uid = await upsert_user(cur, "dekan.fmipa@itb.ac.id",
                                 "Dekan FMIPA ITB")
        await upsert_scope(cur, uid, "dekan", fakultas_id=fak_fmipa)
        results.append({"email": "dekan.fmipa@itb.ac.id",
                         "peran": "dekan", "scope": "FMIPA"})

        uid = await upsert_user(cur, "wakildekan.fmipa@itb.ac.id",
                                 "Wakil Dekan FMIPA ITB")
        await upsert_scope(cur, uid, "jajaran_dekanat", fakultas_id=fak_fmipa)
        results.append({"email": "wakildekan.fmipa@itb.ac.id",
                         "peran": "jajaran_dekanat", "scope": "FMIPA"})

        # ── 3. Dekanat FTI ───────────────────────────────────────────────────
        uid = await upsert_user(cur, "dekan.fti@itb.ac.id",
                                 "Dekan FTI ITB")
        await upsert_scope(cur, uid, "dekan", fakultas_id=fak_fti)
        results.append({"email": "dekan.fti@itb.ac.id",
                         "peran": "dekan", "scope": "FTI"})

        uid = await upsert_user(cur, "wakildekan.fti@itb.ac.id",
                                 "Wakil Dekan FTI ITB")
        await upsert_scope(cur, uid, "jajaran_dekanat", fakultas_id=fak_fti)
        results.append({"email": "wakildekan.fti@itb.ac.id",
                         "peran": "jajaran_dekanat", "scope": "FTI"})

        # ── 4. Kaprodi ───────────────────────────────────────────────────────
        uid = await upsert_user(cur, "kaprodi.fisika@itb.ac.id",
                                 "Kaprodi Fisika S1")
        await upsert_scope(cur, uid, "kaprodi", prodi_id=prodi_102)
        results.append({"email": "kaprodi.fisika@itb.ac.id",
                         "peran": "kaprodi", "scope": "102-Fisika-S1"})

        uid = await upsert_user(cur, "kaprodi.teknik-kimia@itb.ac.id",
                                 "Kaprodi Teknik Kimia S2")
        await upsert_scope(cur, uid, "kaprodi", prodi_id=prodi_230)
        results.append({"email": "kaprodi.teknik-kimia@itb.ac.id",
                         "peran": "kaprodi", "scope": "230-TeknikKimia-S2"})

        # Jajaran prodi (sekretaris/staf)
        uid = await upsert_user(cur, "sekretaris.fisika@itb.ac.id",
                                 "Sekretaris Prodi Fisika S1")
        await upsert_scope(cur, uid, "jajaran_prodi", prodi_id=prodi_102)
        results.append({"email": "sekretaris.fisika@itb.ac.id",
                         "peran": "jajaran_prodi", "scope": "102-Fisika-S1"})

        uid = await upsert_user(cur, "sekretaris.teknik-kimia@itb.ac.id",
                                 "Sekretaris Prodi Teknik Kimia S2")
        await upsert_scope(cur, uid, "jajaran_prodi", prodi_id=prodi_230)
        results.append({"email": "sekretaris.teknik-kimia@itb.ac.id",
                         "peran": "jajaran_prodi", "scope": "230-TeknikKimia-S2"})

        # ── 5. Dosen Fisika S1 (prodi 102) ───────────────────────────────────
        for six_id, nama in DOSEN_PRODI_102:
            dosen_uuid = await get_dosen_id_by_six(cur, six_id)
            if not dosen_uuid:
                console.print(
                    f"[yellow]  ⚠ Dosen six_id={six_id} ({nama}) tidak ditemukan di DB, "
                    f"skip. Pastikan ingest sudah jalan.[/yellow]"
                )
                continue
            email = email_from_nama(nama)
            uid   = await upsert_user(cur, email, nama)
            await upsert_scope(cur, uid, "dosen",
                                prodi_id=prodi_102, dosen_id=dosen_uuid)
            results.append({"email": email, "peran": "dosen",
                             "scope": f"102-{nama}"})

        # ── 6. Dosen Teknik Kimia S2 (prodi 230) ─────────────────────────────
        for six_id, nama in DOSEN_PRODI_230:
            dosen_uuid = await get_dosen_id_by_six(cur, six_id)
            if not dosen_uuid:
                console.print(
                    f"[yellow]  ⚠ Dosen six_id={six_id} ({nama}) tidak ditemukan di DB, "
                    f"skip. Pastikan ingest sudah jalan.[/yellow]"
                )
                continue
            email = email_from_nama(nama)
            uid   = await upsert_user(cur, email, nama)
            await upsert_scope(cur, uid, "dosen",
                                prodi_id=prodi_230, dosen_id=dosen_uuid)
            results.append({"email": email, "peran": "dosen",
                             "scope": f"230-{nama}"})

    return results


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def _get_password_interaktif() -> str:
    """Ambil password dari env atau input interaktif."""
    password = os.getenv("ADMIN_PASSWORD", "")
    if password:
        if len(password) < 8:
            console.print("[red]✗ ADMIN_PASSWORD di .env minimal 8 karakter[/red]")
            sys.exit(1)
        console.print("[dim]Password diambil dari ADMIN_PASSWORD di .env[/dim]")
        return password
    while True:
        password = getpass.getpass("Password admin: ")
        if len(password) < 8:
            console.print("[red]✗ Password minimal 8 karakter[/red]")
            continue
        confirm = getpass.getpass("Konfirmasi password: ")
        if password != confirm:
            console.print("[red]✗ Password tidak cocok, coba lagi[/red]\n")
            continue
        return password


async def run(admin_email: str, admin_nama: str,
               admin_password: str, skip_test: bool, only_test: bool):
    dsn = _build_dsn()
    console.print(f"[dim]DB: {dsn.split('@')[-1]}[/dim]\n")

    # 1. Admin (password-based)
    console.print("[bold cyan]── 1. Seed akun admin ──[/bold cyan]")
    await seed_admin(admin_email, admin_nama, admin_password)

    if not only_test:
        console.print("[bold cyan]── 1. Seed akun admin ──[/bold cyan]")
        await seed_admin(admin_email, admin_nama, admin_password)

    if skip_test:
        console.print("[dim]--skip-test aktif, akun testing dilewati.[/dim]")
        return

    # 2. Test accounts (SSO-based)
    console.print("[bold cyan]── 2. Seed akun testing ──[/bold cyan]")
    async with await psycopg.AsyncConnection.connect(dsn, row_factory=dict_row) as conn:
        results = await seed_test_accounts(conn)
        await conn.commit()

    if not results:
        console.print("[yellow]⚠ Tidak ada akun testing yang berhasil dibuat.[/yellow]")
        return

    tbl = Table(title="Akun Testing Berhasil Dibuat/Diupdate",
                border_style="green")
    tbl.add_column("Email",  style="cyan",   no_wrap=True)
    tbl.add_column("Peran",  style="yellow")
    tbl.add_column("Scope",  style="dim")
    for row in results:
        tbl.add_row(row["email"], row["peran"], row["scope"])
    console.print(tbl)

    console.print(
        "\n[bold green]✓ Selesai.[/bold green] "
        "Semua akun SSO tidak memerlukan password — login via SSO Microsoft ITB.\n"
    )

    # Petunjuk testing RLS
    console.print("[bold]── Petunjuk Testing RLS ──[/bold]")
    console.print(
        "Untuk menguji RLS, set session variables sebelum query:\n\n"
        "  -- Contoh sebagai dosen:\n"
        "  SET app.role = 'dosen';\n"
        "  SET app.dosen_id = '<dosen_uuid>';\n"
        "  SET app.prodi_id = '<prodi_uuid>';\n\n"
        "  -- Contoh sebagai kaprodi:\n"
        "  SET app.role = 'kaprodi';\n"
        "  SET app.prodi_id = '<prodi_uuid>';\n\n"
        "  -- Contoh sebagai dekan FMIPA:\n"
        "  SET app.role = 'dekan';\n"
        "  SET app.fakultas_id = '<fmipa_uuid>';\n\n"
        "  -- Global reader (direktorat/admin):\n"
        "  SET app.role = 'direktorat';\n\n"
        "Gunakan query berikut untuk mendapatkan UUID:\n"
        "  SELECT u.email, us.user_role, us.prodi_id, us.fakultas_id, us.dosen_id\n"
        "  FROM users u JOIN user_scopes us ON us.user_id = u.user_id\n"
        "  WHERE u.email = '<email>';\n"
    )

    console.print(
        "[bold]── Refresh Materialized View ──[/bold]\n"
        "Setelah ingestion selesai, refresh MV secara berurutan:\n\n"
        "  REFRESH MATERIALIZED VIEW CONCURRENTLY mv_kelas;\n"
        "  REFRESH MATERIALIZED VIEW CONCURRENTLY mv_statistik_prodi;\n"
        "  REFRESH MATERIALIZED VIEW CONCURRENTLY mv_statistik_dosen;\n"
    )


def main():
    parser = argparse.ArgumentParser(
        description="Seed akun admin dan akun testing database ITB Analytics"
    )
    parser.add_argument("--email", default="itb.ta.analytics@gmail.com",
                        help="Email akun admin")
    parser.add_argument("--nama", default="Admin ITB Analytics",
                        help="Nama lengkap admin")
    parser.add_argument("--skip-test", action="store_true",
                        help="Lewati seeding akun testing, hanya buat admin")
    parser.add_argument("--only-test", action="store_true",
                    help="Hanya seed akun testing (skip admin), jalankan setelah ingestion")
    args = parser.parse_args()


    console.print("\n[bold cyan]══════════════════════════════════════════════[/bold cyan]")
    console.print("[bold cyan]  ITB Analytics — Seed Admin & Test Accounts  [/bold cyan]")
    console.print("[bold cyan]══════════════════════════════════════════════[/bold cyan]\n")
    console.print(f"Admin email : {args.email}")
    console.print(f"Admin nama  : {args.nama}\n")

    if args.only_test:
        password = ""
    else:
        password = _get_password_interaktif()

    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(run(args.email, args.nama, password, args.skip_test, args.only_test))


if __name__ == "__main__":
    main()