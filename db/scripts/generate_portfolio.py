import pandas as pd
import numpy as np
import os, json, random, time
from sqlalchemy import create_engine
from google import genai
from google.genai import types
from dotenv import load_dotenv
load_dotenv()
# --- 1. CONFIGURATION ---
# Replace with your Gemini API Key
client = genai.Client(api_key=os.environ.get('GOOGLE_API_KEY'))
MODEL_ID = "gemini-3-flash-preview"
DB_URL = os.environ["DATABASE_URL"].replace(
    "postgresql+psycopg://", "postgresql://"
)

OUTPUT_DIR = "data/mock"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# --- 2. STATISTICAL HELPERS ---

def generate_sebaran_nilai(total_mhs):
    """Generates a realistic ITB grade distribution summing exactly to total_mhs."""
    weights = [0.3, 0.25, 0.2, 0.1, 0.08, 0.05, 0.02]  # A, AB, B, BC, C, D, E
    counts = np.random.multinomial(total_mhs, weights)
    grades = ['A', 'AB', 'B', 'BC', 'C', 'D', 'E']
    val_map = {'A':4, 'AB':3.5, 'B':3, 'BC':2.5, 'C':2, 'D':1, 'E':0}
    
    dist = []
    gpa_sum = 0
    for i, g in enumerate(grades):
        cnt = int(counts[i])
        dist.append({"nilai": g, "jumlah": cnt, "persen": round((cnt/total_mhs)*100, 2)})
        gpa_sum += cnt * val_map[g]
    
    return dist, round(gpa_sum/total_mhs, 2)

def get_llm_narratives(context):
    """Generates all 12+ narrative fields in a single LLM call for consistency."""
    prompt = f"""
    Bertindaklah sebagai dosen ITB untuk mata kuliah {context['nama_mk']} ({context['kode_mk']}).
    Data Statistik: Rata-rata Nilai {context['avg_nilai']}, Total Mahasiswa {context['total_mhs']}.
    Dosen Pengampu: {context['nama_dosen']}.

    Hasilkan data portofolio dalam format JSON dengan field berikut (Bahasa Indonesia):
    1. metode_perkuliahan: Narasi metode (ceramah, diskusi, pengerjaan proyek).
    2. sistem_penilaian_komponen: List JSON (UTS, UAS, Tugas, Kuis) dengan bobot total 100.
    3. sistem_penilaian_metode_bobot: List JSON (Case Method/Team-based project).
    4. sistem_penilaian_penjelasan: Paragraf detail penilaian.
    5. tambahan_statistik_kelas: Narasi singkat performa kelas.
    6. analisis_capaian_outcomes: Analisis detail pencapaian CPL/CPMK.
    7. komentar_mahasiswa: 5 komentar beragam dipisah dengan '||'. Sebutkan nama dosen secara natural di salah satu.
    8. komentar_dosen_kuesioner: Respon dosen terhadap feedback mahasiswa.
    9. refleksi_pelaksanaan: Refleksi mendalam dosen.
    10. usulan_perbaikan_dosen_berikutnya: Saran teknis untuk pengajar depan.
    11. usulan_perbaikan_itb: Saran sarana/prasarana untuk institusi.
    12. keterangan_nilai_portofolio: Catatan verifikasi (misal: portofolio lengkap).

    HANYA kembalikan JSON.
    """
    try:
        response = client.models.generate_content(
            model=MODEL_ID,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type='application/json', 
            )
        )
        return json.loads(response.text)
    except Exception as e:
        print(f"LLM Error for {context['kode_mk']}: {e}")
        return {k: "Data tidak tersedia karena limitasi API" for k in range(12)}

# --- 3. MAIN PROCESS ---

def run_generator():
    engine = create_engine(DB_URL)
    
    # Query real data from your seeded DB
    # query = """
    #     SELECT mk.kode_mk, mk.nama_mk, d.nama_dosen, ps.nama_prodi
    #     FROM mata_kuliah mk
    #     JOIN program_studi ps ON mk.prodi_id = ps.prodi_id
    #     JOIN fakultas f ON ps.fakultas_id = f.fakultas_id
    #     JOIN kelompok_keahlian kk ON kk.fakultas_id = f.fakultas_id
    #     JOIN dosen d ON d.kk_id = kk.kk_id
    #     WHERE f.kode_fakultas = 'STEI' AND ps.kode_prodi IN ('135', '182')
    #     LIMIT 5;
    # """
    query = """
        WITH target_kk AS (
            SELECT kk_id 
            FROM kelompok_keahlian 
            WHERE nama_kk IN (
                'Informatika', 
                'Rekayasa Perangkat Lunak dan Pengetahuan', 
                'Teknologi Informasi'
            )
        ),
        cte_matkul AS (
            SELECT mk.kode_mk, mk.nama_mk, ps.nama_prodi
            FROM mata_kuliah mk
            JOIN program_studi ps ON mk.prodi_id = ps.prodi_id
            WHERE ps.kode_prodi IN ('135', '182') 
        ),
        cte_dosen AS (
            SELECT d.nama_dosen
            FROM dosen d
            WHERE d.kk_id IN (SELECT kk_id FROM target_kk)
        )
        SELECT * FROM cte_matkul 
        CROSS JOIN cte_dosen
        ORDER BY RANDOM()
        LIMIT 5;
    """
    
    entities = pd.read_sql(query, engine)
    if entities.empty:
        print("Database master data masih kosong. Harap seed Fakultas/Dosen dulu.")
        return

    print(f"Memulai pembuatan 5 portofolio berbasis LLM...")

    for i, row in entities.iterrows():
        total_mhs = random.randint(25, 65)
        current_no_kelas = random.randint(1, 3)
        dist, avg_nilai = generate_sebaran_nilai(total_mhs)
        
        context = {
            "nama_mk": row['nama_mk'],
            "kode_mk": row['kode_mk'],
            "nama_dosen": row['nama_dosen'],
            "avg_nilai": avg_nilai,
            "total_mhs": total_mhs
        }
        
        narrative = get_llm_narratives(context)
        
        # Build the complete vertical CSV structure
        csv_data = [
            ("kode_kuliah", row['kode_mk']),
            ("nama_kuliah", row['nama_mk']),
            ("no_kelas", current_no_kelas),
            ("sks", random.choice([2, 3, 4])),
            ("semester", random.choice([1, 2])),
            ("tahun_akademik", "2024/2025"),
            ("nama_dosen", row['nama_dosen']),
            ("link_lms", "https://edunex.itb.ac.id"),
            ("metode_perkuliahan", narrative.get('metode_perkuliahan')),
            ("sistem_penilaian_komponen", json.dumps(narrative.get('sistem_penilaian_komponen'))),
            ("sistem_penilaian_metode_bobot", json.dumps(narrative.get('sistem_penilaian_metode_bobot'))),
            ("sistem_penilaian_penjelasan", narrative.get('sistem_penilaian_penjelasan')),
            ("kehadiran_dosen_pct", round(random.uniform(90, 100), 2)),
            ("kehadiran_mahasiswa_pct", round(random.uniform(70, 98), 2)),
            ("rata_rata_nilai", avg_nilai),
            ("total_mahasiswa", total_mhs),
            ("sebaran_nilai", json.dumps(dist)),
            ("tambahan_statistik_kelas", narrative.get('tambahan_statistik_kelas')),
            ("analisis_capaian_outcomes", narrative.get('analisis_capaian_outcomes'))
        ]
        
        # Add Q1-Q12 Scores
        for q in range(1, 13):
            csv_data.append((f"kuesioner_q{q}_skor", round(random.uniform(3.0, 4.0), 2)))
            
        # Add Qualitative & Verification
        csv_data.extend([
            ("komentar_mahasiswa", narrative.get('komentar_mahasiswa')),
            ("komentar_dosen_kuesioner", narrative.get('komentar_dosen_kuesioner')),
            ("refleksi_pelaksanaan", narrative.get('refleksi_pelaksanaan')),
            ("usulan_perbaikan_dosen_berikutnya", narrative.get('usulan_perbaikan_dosen_berikutnya')),
            ("usulan_perbaikan_itb", narrative.get('usulan_perbaikan_itb')),
            ("nilai_portofolio", random.randint(3, 4)),
            ("keterangan_nilai_portofolio", narrative.get('keterangan_nilai_portofolio'))
        ])
        
        # Save to CSV

        timestamp = int(time.time())
        filename = f"{row['kode_mk']}_K0{current_no_kelas}_{i}_{timestamp}.csv"
        
        df = pd.DataFrame(csv_data, columns=["field", "value"])
        df.to_csv(os.path.join(OUTPUT_DIR, filename), index=False)
        print(f"[{i+1}/5] Berhasil membuat: {filename}")
        
        time.sleep(2)

    print(f"\nBerhasil! 5 CSV tersedia di {OUTPUT_DIR}")

if __name__ == "__main__":
    run_generator()