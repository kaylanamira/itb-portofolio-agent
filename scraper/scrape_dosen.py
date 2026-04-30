"""
Source: itb.ac.id/staf/fakultas-sekolah/{slug}
        itb.ac.id/staf/listby/{A..Z}  ← fallback for KK detail

Strategy: Playwright renders JS, then we parse dosen name + KK from the page.
The per-fakultas URL gives: nama_dosen + kode_fakultas (from slug mapping).
Output: data/raw/dosen.json
"""

import asyncio, json, re
from pathlib import Path
from playwright.async_api import async_playwright
from rich.console import Console

console = Console()

FAKULTAS_SLUGS = {
    "fakultas-ilmu-dan-teknologi-kebumian":                    "FITB",
    "fakultas-matematika-dan-ilmu-pengetahuan-alam":           "FMIPA",
    "fakultas-seni-rupa-dan-desain":                           "FSRD",
    "fakultas-teknik-mesin-dan-dirgantara":                    "FTMD",
    "fakultas-teknik-pertambangan-dan-perminyakan":            "FTTM",
    "fakultas-teknik-sipil-dan-lingkungan":                    "FTSL",
    "fakultas-teknologi-industri":                             "FTI",
    "sekolah-arsitektur-perencanaan-dan-pengembangan-kebijakan": "SAPPK",
    "sekolah-bisnis-dan-manajemen":                            "SBM",
    "sekolah-farmasi":                                         "SF",
    "sekolah-ilmu-dan-teknologi-hayati":                       "SITH",
    "sekolah-teknik-elektro-dan-informatika":                  "STEI",
}

BASE_URL = "https://itb.ac.id/staf/fakultas-sekolah/{slug}"


async def scrape_dosen_per_fakultas(page, slug: str, kode_fak: str) -> list[dict]:
    url = BASE_URL.format(slug=slug)
    await page.goto(url, wait_until="networkidle", timeout=60000)

    # Wait for dosen list to render
    # Inspect the page — dosen are typically in .staff-item or similar
    # We'll try common selectors; adjust after first run if needed
    await page.wait_for_selector("body", timeout=10000)

    results = []

    # The page groups dosen by KK under headings
    # Parse headings (KK names) and dosen names under each

    # Modified logic to specifically target the table structure seen in ITB staff lists
    content = await page.evaluate("""
        () => {
            const items = [];
            // Target the rows in the staff table
            const rows = document.querySelectorAll('table tr, .staff-list-item');
            
            rows.forEach(row => {
                const cols = row.querySelectorAll('td');
                if (cols.length >= 2) {
                    const nameCell = cols[0];
                    const kkCell = cols[1];
                    
                    const nameLink = nameCell.querySelector('a');
                    const nameText = nameCell.innerText.trim();
                    const kkText = kkCell.innerText.trim();

                    // Ensure we aren't picking up table headers like "Nama" or "Kelompok Keahlian"
                    if (nameText && nameText !== "Nama" && kkText !== "Kelompok Keahlian") {
                        items.push({
                            nama_dosen: nameText,
                            nama_kk: kkText,
                            url_profil: nameLink ? nameLink.href : null
                        });
                    }
                }
            });
            
            // Fallback for non-table layouts (some pages use list divs)
            if (items.length === 0) {
                let currentKK = "";
                const elements = document.querySelectorAll('h3, h4, .staff-name');
                elements.forEach(el => {
                    if (el.tagName.startsWith('H')) {
                        currentKK = el.innerText.trim();
                    } else {
                        items.push({
                            nama_dosen: el.innerText.trim(),
                            nama_kk: currentKK
                        });
                    }
                });
            }
            
            return items;
        }
    """)

    for item in content:
        if item.get("nama_dosen"):
            results.append({
                "nama_dosen":    item["nama_dosen"],
                "nama_kk":       item.get("nama_kk").removeprefix("KK ").strip() if item.get("nama_kk") else None,
                "kode_fakultas": kode_fak,
                "url_profil":    item.get("url_profil"),
            })

    console.print(f"[green]{kode_fak}: {len(results)} dosen[/green]")
    return results


async def run():
    Path("data/raw").mkdir(parents=True, exist_ok=True)
    all_dosen = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        for slug, kode_fak in FAKULTAS_SLUGS.items():
            try:
                dosen = await scrape_dosen_per_fakultas(page, slug, kode_fak)
                all_dosen.extend(dosen)
                await asyncio.sleep(1)  # polite delay
            except Exception as e:
                console.print(f"[red]✗ {kode_fak} failed: {e}[/red]")

        await browser.close()

    # Deduplicate by nama_dosen (same person may appear under multiple KK)
    seen = set()
    deduped = []
    for d in all_dosen:
        key = d["nama_dosen"].lower().strip()
        if key not in seen:
            seen.add(key)
            deduped.append(d)

    Path("data/raw/dosen.json").write_text(
        json.dumps(deduped, indent=2, ensure_ascii=False)
    )
    console.print(f"[bold green]✓ {len(deduped)} dosen saved[/bold green]")


if __name__ == "__main__":
    asyncio.run(run())