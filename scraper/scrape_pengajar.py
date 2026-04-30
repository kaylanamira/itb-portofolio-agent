import os
import requests
import json
from bs4 import BeautifulSoup
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

# --- CONFIGURATION ---
DB_URL = os.environ["DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://")
NIM = os.environ["SIX_NIM"]
SIX_COOKIE = os.environ["SIX_COOKIE"]
COOKIES = {f"_shibsession_64656661756c7468747470733a2f2f73": SIX_COOKIE}
URL = f"https://six.itb.ac.id/app/mahasiswa:{NIM}+2025-2/kelas/jadwal/kuliah?fakultas=STEI&prodi=182&pekan=&kegiatan="
def scrape_six_jadwal():
    print(f"Fetching data ...")
    response = requests.get(URL, cookies=COOKIES)
    
    if response.status_code != 200:
        print(f"Failed to fetch. Status: {response.status_code}")
        return []

    soup = BeautifulSoup(response.text, 'lxml')
    # Cari baris tabel di jadwal
    rows = soup.find_all('tr')
    all_data = []

    for row in rows:
        cols = row.find_all('td')
        # Pastikan baris memiliki kolom yang cukup (biasanya baris jadwal memiliki > 5 kolom)
        if len(cols) < 5:
            continue

        try:
            kode_mk = cols[1].get_text(strip=True)
            nama_mk = cols[2].get_text(strip=True)
            sks = int(cols[3].get_text(strip=True))
            kelas = cols[4].get_text(strip=True)
            
            # Ambil Dosen (biasanya ada di dalam ul > li)
            dosen_list = []
            dosen_ul = cols[6].find('ul')
            if dosen_ul:
                dosen_list = [li.get_text(strip=True) for li in dosen_ul.find_all('li')]
            
            all_data.append({
                "kode_mk": kode_mk,
                "nama_mk": nama_mk,
                "sks": sks,
                "kelas": kelas,
                "dosen": dosen_list
            })
        except (IndexError, ValueError):
            continue

    return all_data

def insert_to_db(data):
    engine = create_engine(DB_URL)
    with engine.begin() as conn:
        print("Inserting to database...")
        for item in data:
            for dosen_name in item['dosen']:
                # Query untuk mencari ID Dosen berdasarkan nama (pencarian mirip/fuzzy)
                # Sesuaikan dengan skema tabel pengajar_sql kamu
                sql = text("""
                    INSERT INTO pengajar_sql (kode_mk, nama_mk, kelas, nama_dosen, nim_mahasiswa)
                    VALUES (:kode_mk, :nama_mk, :kelas, :dosen, :nim)
                """)
                conn.execute(sql, {
                    "kode_mk": item['kode_mk'],
                    "nama_mk": item['nama_mk'],
                    "kelas": item['kelas'],
                    "dosen": dosen_name,
                    "nim": NIM
                })
    print("Done!")

if __name__ == "__main__":
    extracted_data = scrape_six_jadwal()
    
    if extracted_data:
        # 1. Simpan ke JSON untuk backup
        with open("data/raw/six_jadwal2.json", "w") as f:
            json.dump(extracted_data, f, indent=4)
        
        # 2. Insert ke Database
        # insert_to_db(extracted_data)
    else:
        print("No data found. Check your Session Cookie!")