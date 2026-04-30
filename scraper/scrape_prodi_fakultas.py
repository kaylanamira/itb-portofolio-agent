"""
Combines two sources to build complete fakultas + prodi data:
  Source A: six.itb.ac.id/pub/kur2024         → kode_fakultas, kode_prodi, nama_prodi, jenjang
  Source B: itb.ac.id/program-studi-{jenjang} → kode_fakultas, nama_fakultas, singkatan_prodi, nama_prodi

Join key: normalize(nama_prodi) across both sources.
Output: data/raw/prodi_fakultas.json
"""

import asyncio, json, re
from pathlib import Path
import httpx
from bs4 import BeautifulSoup
from rich.console import Console

console = Console()

JENJANG_URLS = {
    "S1":      "https://itb.ac.id/program-studi-sarjana",
    "S2":      "https://itb.ac.id/program-studi-magister",
    "S3":      "https://itb.ac.id/program-studi-doktor",
    "Profesi": "https://itb.ac.id/program-profesi",
}

SIX_KUR_URL = "https://six.itb.ac.id/pub/kur2024"

def normalize(s: str) -> str:
    """Lowercase, strip whitespace, remove punctuation for fuzzy matching."""
    return re.sub(r"[^a-z0-9]", "", s.lower().strip())


async def fetch_html(url: str) -> BeautifulSoup:
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        r = await client.get(url)
        r.raise_for_status()
        return BeautifulSoup(r.text, "lxml")


async def scrape_six_kur() -> list[dict]:
    """
    Returns list of:
    {"kode_fakultas": "STEI", "kode_prodi": "135", "nama_prodi": "Teknik Informatika", "jenjang": "S1"}
    """
    soup = await fetch_html(SIX_KUR_URL)
    results = []

    # SIX page has 4 sections: Sarjana, Magister, Doktor, Profesi
    # Each section has an <h2> anchor then a <table>
    jenjang_map = {
        "sarjana": "S1", "magister": "S2",
        "doktor": "S3", "profesi": "Profesi"
    }

    current_jenjang = "S1"
    for tag in soup.find_all(["h2", "table"]):
        if tag.name == "h2":
            text = tag.get_text(strip=True).lower()
            for key, val in jenjang_map.items():
                if key in text:
                    current_jenjang = val
                    break
        elif tag.name == "table":
            for row in tag.find_all("tr")[1:]:  # skip header
                cols = row.find_all("td")
                if len(cols) < 3:
                    continue
                results.append({
                    "kode_fakultas": cols[0].get_text(strip=True),
                    "kode_prodi":    cols[1].get_text(strip=True),
                    "nama_prodi":    cols[2].get_text(strip=True),
                    "jenjang":       current_jenjang,
                })

    console.print(f"[green]SIX: scraped {len(results)} prodi rows[/green]")
    return results


async def scrape_itb_prodi(jenjang: str, url: str) -> list[dict]:
    """
    Returns list of:
    {"kode_fakultas": "STEI", "nama_fakultas": "Sekolah Teknik Elektro...",
     "nama_prodi": "Informatika", "singkatan_prodi": "IF", "jenjang": "S1"}
    """
    soup = await fetch_html(url)
    results = []
    current_fak = {"kode": "", "nama": ""}

    # Page structure: <h4>Nama Fakultas (KODE)</h4> then <ol><li><a>Nama (SINGKATAN)</a></li>
    for tag in soup.find_all(["h4", "li"]):
        if tag.name == "h4":
            text = tag.get_text(strip=True)
            # Extract kode from parentheses e.g. "Sekolah Teknik Elektro dan Informatika (STEI)"
            match = re.search(r"\(([A-Z]+)\)\s*$", text)
            if match:
                current_fak = {
                    "kode": match.group(1),
                    "nama": text[:match.start()].strip()
                }
        elif tag.name == "li" and current_fak["kode"]:
            a = tag.find("a")
            if not a:
                continue
            text = a.get_text(strip=True)
            # Extract singkatan from parentheses e.g. "Informatika (IF)"
            match = re.search(r"\(([A-Z]+)\)\s*$", text)
            if match:
                results.append({
                    "kode_fakultas":   current_fak["kode"],
                    "nama_fakultas":   current_fak["nama"],
                    "nama_prodi":      text[:match.start()].strip(),
                    "singkatan_prodi": match.group(1),
                    "jenjang":         jenjang,
                })

    console.print(f"[green]itb.ac.id {jenjang}: scraped {len(results)} prodi[/green]")
    return results


def merge_prodi_sources(
    six_rows: list[dict],
    itb_rows: list[dict]
) -> tuple[list[dict], list[dict]]:
    """
    Joins SIX data (has kode_prodi) with ITB data (has singkatan + nama_fakultas).
    Join key: normalize(nama_prodi) + kode_fakultas + jenjang.
    Returns (fakultas_list, prodi_list).
    """
    # Build lookup from ITB rows
    itb_lookup: dict[str, dict] = {}
    for r in itb_rows:
        key = (r["kode_fakultas"], normalize(r["nama_prodi"]), r["jenjang"])
        itb_lookup[key] = r

    # Build fakultas dedup map
    fak_map: dict[str, dict] = {}
    prodi_list = []
    unmatched = []

    for six in six_rows:
        key = (six["kode_fakultas"], normalize(six["nama_prodi"]), six["jenjang"])
        itb = itb_lookup.get(key)

        if itb:
            # Matched — merge
            fak_map[six["kode_fakultas"]] = {
                "kode_fakultas": six["kode_fakultas"],
                "nama_fakultas": itb["nama_fakultas"],
            }
            prodi_list.append({
                "kode_prodi":      six["kode_prodi"],
                "nama_prodi":      itb["nama_prodi"],      # use ITB version (cleaner)
                "singkatan_prodi": itb["singkatan_prodi"],
                "jenjang":         six["jenjang"],
                "kode_fakultas":   six["kode_fakultas"],
            })
        else:
            # Unmatched — keep from SIX, flag for manual review
            unmatched.append(six)
            prodi_list.append({
                "kode_prodi":      six["kode_prodi"],
                "nama_prodi":      six["nama_prodi"],
                "singkatan_prodi": None,   # needs manual fill
                "jenjang":         six["jenjang"],
                "kode_fakultas":   six["kode_fakultas"],
            })

    if unmatched:
        console.print(f"[yellow]⚠ {len(unmatched)} prodi unmatched — check data/raw/unmatched_prodi.json[/yellow]")
        Path("data/raw/unmatched_prodi.json").write_text(
            json.dumps(unmatched, indent=2, ensure_ascii=False)
        )

    return list(fak_map.values()), prodi_list


async def run():
    Path("data/raw").mkdir(parents=True, exist_ok=True)

    # Fetch from all sources concurrently
    six_task = asyncio.create_task(scrape_six_kur())
    itb_tasks = [
        asyncio.create_task(scrape_itb_prodi(j, url))
        for j, url in JENJANG_URLS.items()
    ]
    six_rows = await six_task
    itb_rows_nested = await asyncio.gather(*itb_tasks)
    itb_rows = [r for sublist in itb_rows_nested for r in sublist]

    fakultas_list, prodi_list = merge_prodi_sources(six_rows, itb_rows)

    # Save raw outputs
    Path("data/raw/fakultas.json").write_text(
        json.dumps(fakultas_list, indent=2, ensure_ascii=False)
    )
    Path("data/raw/prodi.json").write_text(
        json.dumps(prodi_list, indent=2, ensure_ascii=False)
    )

    console.print(f"[bold green]✓ {len(fakultas_list)} fakultas, {len(prodi_list)} prodi saved[/bold green]")


if __name__ == "__main__":
    asyncio.run(run())