"""
seed_admin.py — Seed satu akun admin ke tabel pengguna
=======================================================
Jalankan SETELAH schema_auth_session.sql sudah dieksekusi,
dan SEBELUM ingest.py.

Usage:
    python seed_admin.py
    python seed_admin.py --email other@gmail.com --nama "Nama Lain"
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
from rich.prompt import Prompt

load_dotenv()
console = Console()


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


async def seed(email: str, nama: str, password: str):
    dsn = _build_dsn()
    console.print(f"\n[dim]DB: {dsn.split('@')[-1]}[/dim]")

    async with await psycopg.AsyncConnection.connect(dsn, row_factory=dict_row) as conn:
        async with conn.cursor() as cur:

            # Cek apakah sudah ada
            await cur.execute(
                "SELECT pengguna_id, email, metode_auth FROM pengguna WHERE email = %(email)s",
                {"email": email},
            )
            existing = await cur.fetchone()

            if existing:
                # Akun ada — update password saja
                console.print(f"⚠ Akun sudah ada")
                console.print("  Mengupdate ke metode_auth=password dan menyimpan password hash...")

                pw_hash = hash_password(password)
                await cur.execute("""
                    UPDATE pengguna
                    SET metode_auth   = 'password',
                        password_hash = %(pw_hash)s,
                        updated_at    = NOW()
                    WHERE pengguna_id = %(pengguna_id)s
                """, {"pw_hash": pw_hash, "pengguna_id": str(existing["pengguna_id"])})

                await conn.commit()
                console.print(f"\n[green]✓ Password berhasil diset[/green]")
                console.print(f"  pengguna_id : {existing['pengguna_id']}")
                console.print(f"  email       : {email}")
                console.print(f"  metode_auth : password\n")
                return

            # Insert admin baru dengan password
            pw_hash = hash_password(password)
            await cur.execute("""
                INSERT INTO pengguna
                    (email, nama_lengkap, metode_auth, password_hash, is_active)
                VALUES
                    (%(email)s, %(nama)s, 'password', %(pw_hash)s, TRUE)
                RETURNING pengguna_id
            """, {"email": email, "nama": nama, "pw_hash": pw_hash})
            row = await cur.fetchone()
            pengguna_id = str(row["pengguna_id"])

            # Assign peran admin
            await cur.execute("""
                INSERT INTO pengguna_peran (pengguna_id, kode_peran, is_active)
                VALUES (%(pengguna_id)s, 'admin', TRUE)
            """, {"pengguna_id": pengguna_id})

        await conn.commit()

    console.print(f"\n[green]✓ Admin berhasil dibuat[/green]")
    console.print(f"  pengguna_id : {pengguna_id}")
    console.print(f"  email       : {email}")
    console.print(f"  nama        : {nama}")
    console.print(f"  metode_auth : password")
    console.print(f"  peran       : admin\n")


def main():
    parser = argparse.ArgumentParser(description="Seed akun admin dengan password")
    parser.add_argument(
        "--email", default="itb.ta.analytics@gmail.com",
        help="Email admin"
    )
    parser.add_argument(
        "--nama", default="Admin ITB Analytics",
        help="Nama lengkap admin"
    )
    args = parser.parse_args()

    console.print("\n[bold cyan]── Seed Admin Account ──[/bold cyan]")
    console.print(f"Email : {args.email}")
    console.print(f"Nama  : {args.nama}\n")

    # Ambil password dari env, fallback ke input interaktif
    password = os.getenv("ADMIN_PASSWORD", "")
    if password:
        if len(password) < 8:
            console.print("[red]✗ ADMIN_PASSWORD di .env minimal 8 karakter[/red]")
            sys.exit(1)
        console.print("[dim]Password diambil dari ADMIN_PASSWORD di .env[/dim]")
    else:
        # Minta password secara interaktif (tidak tampil di terminal)
        while True:
            password = getpass.getpass("Password: ")
            if len(password) < 8:
                console.print("[red]✗ Password minimal 8 karakter[/red]")
                continue
            confirm = getpass.getpass("Konfirmasi password: ")
            if password != confirm:
                console.print("[red]✗ Password tidak cocok, coba lagi[/red]\n")
                continue
            break

    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(seed(args.email, args.nama, password))


if __name__ == "__main__":
    main()