# scraper/scrape_matkul.py
import asyncio
import os
import httpx
from bs4 import BeautifulSoup
from pydantic import BaseModel
from typing import Optional
import asyncio, json, re
from pathlib import Path
from dotenv import load_dotenv
from rich.console import Console

load_dotenv()
console = Console()

SIX_BASE    = "https://six.itb.ac.id"
MATKUL_PATH = "/app/mahasiswa:{nim}/kurikulum/rpmk/list"
TH_KUR      = "2024"  # curriculum year to scrape

SESSION_COOKIE = {"_shibsession_64656661756c7468747470733a2f2f73": os.environ["SIX_COOKIE"]}
NIM =  os.environ["SIX_NIM"]


class MatkulRow(BaseModel):
    kode_mk:      str
    nama_mk:      str
    nama_mk_en:   Optional[str]
    sks:          int
    kategori:     str            # Kuliah / Kerja Praktik / Tugas Akhir
    jenis_nilai:  str            # ABCDE / Pass/Fail
    kode_prodi:   str            # from query param, e.g. "135"


# ── Parser ────────────────────────────────────────────────────────────────────

def parse_matkul_table(html: str, kode_prodi: str) -> list[MatkulRow]:
    soup = BeautifulSoup(html, "lxml")
    rows = []

    # The table has thead + tbody, each data row is a <tr> in tbody
    tbody = soup.select_one("table.table tbody")
    if not tbody:
        return []

    for tr in tbody.find_all("tr"):
        tds = tr.find_all("td")
        # Row structure: [checkbox_td, no_th, kode, thn_kur, no_prodi,
        #                  nama_mk, nama_mk_en, sks, kategori, jenis_nilai]
        # but no_th is actually a <th>, so tds gives us only the <td> cells
        # tds[0]=checkbox, tds[1]=kode, tds[2]=thn_kur, tds[3]=no_prodi
        # tds[4]=nama_mk, tds[5]=nama_mk_en, tds[6]=sks
        # tds[7]=kategori, tds[8]=jenis_nilai
        if len(tds) < 9:
            continue

        rows.append(MatkulRow(
            kode_mk     = tds[1].get_text(strip=True),
            nama_mk     = tds[4].get_text(strip=True),
            nama_mk_en  = tds[5].get_text(strip=True) or None,
            sks         = int(tds[6].get_text(strip=True)),
            kategori    = tds[7].get_text(strip=True),
            jenis_nilai = tds[8].get_text(strip=True),
            kode_prodi  = kode_prodi,
        ))

    return rows


# ── Fetcher ───────────────────────────────────────────────────────────────────

async def fetch_matkul_for_prodi(
    client:     httpx.AsyncClient,
    kode_prodi: str,
) -> list[MatkulRow]:
    url = f"{SIX_BASE}{MATKUL_PATH.format(nim=NIM)}"
    params = {"prodi": kode_prodi, "th_kur": TH_KUR}

    r = await client.get(url, params=params)

    # Session expired → SIX redirects to login page
    if "login" in str(r.url).lower() or r.status_code == 401:
        raise RuntimeError("Session expired. Refresh your cookie from the browser.")

    r.raise_for_status()
    return parse_matkul_table(r.text, kode_prodi)


# ── Orchestrator ──────────────────────────────────────────────────────────────

async def scrape_all_matkul(prodi_list: list[str]) -> list[dict]:
    """
    prodi_list: list of kode_prodi strings, e.g. ["135", "182", "132"]
    Returns list of dicts ready for DB insertion.
    """
    all_rows: list[MatkulRow] = []

    async with httpx.AsyncClient(
        cookies=SESSION_COOKIE,
        headers={"User-Agent": "Mozilla/5.0"},
        follow_redirects=True,
        timeout=30,
    ) as client:
        for kode_prodi in prodi_list:
            try:
                rows = await fetch_matkul_for_prodi(client, kode_prodi)
                all_rows.extend(rows)
                print(f"✓ prodi {kode_prodi}: {len(rows)} matkul")

                # Be polite — don't hammer the server
                await asyncio.sleep(0.5)

            except RuntimeError as e:
                print(f"✗ Session error: {e}")
                break
            except Exception as e:
                print(f"✗ prodi {kode_prodi} failed: {e}")
                continue

    return [r.model_dump() for r in all_rows]


async def run():
    sample_prodi = ["135", "182", "132"]
    Path("data/raw").mkdir(parents=True, exist_ok=True)
    matkul_list = await scrape_all_matkul(sample_prodi)
    Path("data/raw/matkul.json").write_text(
        json.dumps(matkul_list, indent=2, ensure_ascii=False)
    )
    console.print("[bold green]✓ matkul saved[/bold green]")


if __name__ == "__main__":
    asyncio.run(run())