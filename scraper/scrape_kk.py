"""
Source: itb.ac.id/kelompok-keahliankeilmuan
Gives: nama_kk grouped under nama_fakultas + kode_fakultas
Output: data/raw/kk.json
"""

import asyncio, json, re
from pathlib import Path
import httpx
from bs4 import BeautifulSoup
from rich.console import Console

console = Console()
URL = "https://itb.ac.id/kelompok-keahliankeilmuan"


async def scrape_kk() -> list[dict]:
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(URL)
        soup = BeautifulSoup(r.text, "lxml")

    results = []
    current_fak = {"kode": None, "nama": None}

    for tag in soup.find_all(["h4", "li"]):
        if tag.name == "h4":
            text = tag.get_text(strip=True)
            # e.g. "Fakultas Teknik Sipil dan Lingkungan (FTSL)"
            match = re.search(r"\(([A-Z]+)\)\s*$", text)
            if match:
                current_fak = {
                    "kode": match.group(1),
                    "nama": text[:match.start()].strip()
                }
        elif tag.name == "li" and current_fak["kode"]:
            nama_kk = tag.get_text(strip=True)
            if nama_kk:
                results.append({
                    "nama_kk":       nama_kk,
                    "kode_fakultas": current_fak["kode"],
                })

    console.print(f"[green]KK: scraped {len(results)} kelompok keahlian[/green]")
    return results


async def run():
    Path("data/raw").mkdir(parents=True, exist_ok=True)
    kk_list = await scrape_kk()
    Path("data/raw/kk.json").write_text(
        json.dumps(kk_list, indent=2, ensure_ascii=False)
    )
    console.print("[bold green]✓ KK saved[/bold green]")


if __name__ == "__main__":
    asyncio.run(run())