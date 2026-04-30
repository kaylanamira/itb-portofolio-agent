"""
Mock Portfolio CSV Generator
============================
Queries kelas + pengajar from PostgreSQL DB, then uses LLM
to generate realistic Indonesian text fields for each portfolio.

"""

import csv
import json
import os
import sys
import time
import random
import numpy as np
import psycopg2
import psycopg2.extras
from pathlib import Path
from collections import defaultdict, Counter
from dotenv import load_dotenv
from google import genai

load_dotenv()

client   = genai.Client(api_key=os.environ.get("GOOGLE_API_KEY"))
MODEL_ID = "gemini-3-flash-preview"
DB_URL   = os.environ["DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://")
OUTPUT_DIR = Path("data/mock")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

random.seed(42)
np.random.seed(42)

TARGET_MIN = 20
TARGET_MAX = 40


def fetch_kelas() -> tuple[list[dict], list[dict]]:
    conn = psycopg2.connect(DB_URL, cursor_factory=psycopg2.extras.RealDictCursor)
    cur  = conn.cursor()

    cur.execute("""
        SELECT
            k.kelas_id,
            k.no_kelas,
            k.semester,
            k.tahun_ajaran,
            k.sks,
            mk.kode_mk,
            mk.nama_mk,
            ps.kode_prodi,
            ps.singkatan_prodi,
            ps.nama_prodi,
            f.kode_fakultas,
            f.nama_fakultas,
            array_agg(DISTINCT d.nama_dosen ORDER BY d.nama_dosen)
                FILTER (WHERE d.nama_dosen IS NOT NULL) AS dosen_list
        FROM kelas k
        JOIN mata_kuliah mk    ON mk.matkul_id   = k.matkul_id
        JOIN program_studi ps  ON ps.prodi_id    = mk.prodi_id
        JOIN fakultas f        ON f.fakultas_id  = ps.fakultas_id
        LEFT JOIN pengajar_kelas pk ON pk.kelas_id = k.kelas_id
        LEFT JOIN dosen d      ON d.dosen_id     = pk.dosen_id
        LEFT JOIN kelompok_keahlian kk ON kk.kk_id = d.kk_id
        WHERE ps.kode_prodi IN ('135', '182')
          AND (
              kk.nama_kk IN (
                  'Informatika',
                  'Rekayasa Perangkat Lunak dan Pengetahuan',
                  'Teknologi Informasi'
              )
              OR d.dosen_id IS NULL
          )
        GROUP BY
            k.kelas_id, k.no_kelas, k.semester, k.tahun_ajaran, k.sks,
            mk.kode_mk, mk.nama_mk,
            ps.kode_prodi, ps.singkatan_prodi, ps.nama_prodi,
            f.kode_fakultas, f.nama_fakultas
        ORDER BY mk.kode_mk, k.no_kelas, k.tahun_ajaran
    """)
    stei_rows = [dict(r) for r in cur.fetchall()]

    # Non-STEI: at least one other fakultas
    cur.execute("""
        SELECT
            k.kelas_id::text,
            k.no_kelas,
            k.semester,
            k.tahun_ajaran,
            k.sks,
            mk.kode_mk,
            mk.nama_mk,
            ps.kode_prodi,
            ps.singkatan_prodi,
            ps.nama_prodi,
            f.kode_fakultas,
            f.nama_fakultas,
            array_agg(DISTINCT d.nama_dosen ORDER BY d.nama_dosen)
                FILTER (WHERE d.nama_dosen IS NOT NULL) AS dosen_list
        FROM kelas k
        JOIN mata_kuliah mk    ON mk.matkul_id   = k.matkul_id
        JOIN program_studi ps  ON ps.prodi_id    = mk.prodi_id
        JOIN fakultas f        ON f.fakultas_id  = ps.fakultas_id
        LEFT JOIN pengajar_kelas pk ON pk.kelas_id = k.kelas_id
        LEFT JOIN dosen d      ON d.dosen_id     = pk.dosen_id
        WHERE f.kode_fakultas != 'STEI'
        GROUP BY
            k.kelas_id, k.no_kelas, k.semester, k.tahun_ajaran, k.sks,
            mk.kode_mk, mk.nama_mk,
            ps.kode_prodi, ps.singkatan_prodi, ps.nama_prodi,
            f.kode_fakultas, f.nama_fakultas
        ORDER BY f.kode_fakultas, mk.kode_mk, k.no_kelas
        LIMIT 40
    """)
    other_rows = [dict(r) for r in cur.fetchall()]
    conn.close()

    print(f"  DB → STEI kelas: {len(stei_rows)}, non-STEI kelas: {len(other_rows)}")
    return stei_rows, other_rows


def select_kelas(stei_rows: list[dict], other_rows: list[dict]) -> list[dict]:
    """Select 20-40 kelas satisfying all requirements."""
    selected = []

    # Group STEI by (kode_mk, kode_prodi)
    stei_by_mk: dict[tuple, list] = defaultdict(list)
    for r in stei_rows:
        stei_by_mk[(r["kode_mk"], r["kode_prodi"])].append(r)

    # IF (135): pick at least 3 matkul, each with 2-3 kelas
    if_keys = [(mk, pr) for (mk, pr) in stei_by_mk if pr == "135"]
    random.shuffle(if_keys)
    if_keys = if_keys[:6]  # up to 6 matkul
    for key in if_keys:
        opts = stei_by_mk[key]
        n = min(len(opts), random.choice([2, 3]))
        selected.extend(random.sample(opts, n))

    # STI (182): pick 2-3 matkul, 2 kelas each
    sti_keys = [(mk, pr) for (mk, pr) in stei_by_mk if pr == "182"]
    random.shuffle(sti_keys)
    for key in sti_keys[:3]:
        opts = stei_by_mk[key]
        n = min(len(opts), 2)
        selected.extend(random.sample(opts, n))

    # Non-STEI: pick from up to 2 distinct fakultas
    other_by_fak: dict[str, list] = defaultdict(list)
    for r in other_rows:
        other_by_fak[r["kode_fakultas"]].append(r)

    for fak, rows in list(other_by_fak.items())[:2]:
        by_mk: dict[str, list] = defaultdict(list)
        for r in rows:
            by_mk[r["kode_mk"]].append(r)
        for mk_key in list(by_mk.keys())[:2]:
            opts = by_mk[mk_key]
            n = min(len(opts), 2)
            selected.extend(random.sample(opts, n))

    # Deduplicate and trim
    seen: set[str] = set()
    deduped = []
    for r in selected:
        if r["kelas_id"] not in seen:
            seen.add(r["kelas_id"])
            deduped.append(r)

    if len(deduped) > TARGET_MAX:
        # Keep all IF first, then trim others
        if_rows   = [r for r in deduped if r["kode_prodi"] == "135"]
        rest_rows = [r for r in deduped if r["kode_prodi"] != "135"]
        deduped   = if_rows + rest_rows[:TARGET_MAX - len(if_rows)]

    return deduped


# ── Step 2: Numeric fields ────────────────────────────────────────────────────

def infer_archetype(kode_mk: str, nama_mk: str) -> str:
    nama_l = nama_mk.lower()
    if any(k in nama_l for k in ["proyek", "project", "tugas akhir", "kerja praktik",
                                   "big data", "capstone", "pengembangan"]):
        return "project"
    if any(k in nama_l for k in ["algoritma", "kalkulus", "matematika", "statistika",
                                   "otomata", "logika", "teori", "pembuktian"]):
        return "hard"
    return "core"


def gen_stats(archetype: str, anomaly: str | None) -> dict:
    if anomaly == "low_attendance":
        return {
            "had_dosen":  round(random.uniform(50, 68), 2),
            "had_mhs":    round(random.uniform(45, 62), 2),
            "rata_nilai": round(random.uniform(1.8, 2.4), 2),
            "n_students": random.randint(20, 55),
            "anomaly":    anomaly,
        }
    if anomaly == "grade_inflation":
        return {
            "had_dosen":  round(random.uniform(95, 100), 2),
            "had_mhs":    round(random.uniform(85, 95), 2),
            "rata_nilai": round(random.uniform(3.5, 4.0), 2),
            "n_students": random.randint(20, 55),
            "anomaly":    anomaly,
        }
    rata = {
        "hard":    round(random.uniform(2.2, 2.85), 2),
        "project": round(random.uniform(2.9, 3.7),  2),
        "core":    round(random.uniform(2.5, 3.3),  2),
    }[archetype]
    return {
        "had_dosen":  round(random.uniform(80, 100), 2),
        "had_mhs":    round(random.uniform(65, 90),  2),
        "rata_nilai": rata,
        "n_students": random.randint(20, 55),
        "anomaly":    None,
    }


def gen_grade_dist(archetype: str, n: int, anomaly: str | None) -> dict:
    w_map = {
        "grade_inflation": [0.45, 0.30, 0.15, 0.07, 0.02, 0.01, 0.00],
        "low_attendance":  [0.05, 0.08, 0.15, 0.22, 0.25, 0.15, 0.10],
        "hard":            [0.08, 0.12, 0.20, 0.25, 0.20, 0.10, 0.05],
        "project":         [0.35, 0.30, 0.20, 0.10, 0.04, 0.01, 0.00],
        "core":            [0.18, 0.20, 0.25, 0.20, 0.12, 0.04, 0.01],
    }
    key = anomaly if anomaly in w_map else archetype
    w   = [max(0.001, x + np.random.normal(0, 0.015)) for x in w_map[key]]
    w   = [x / sum(w) for x in w]
    counts = list(np.random.multinomial(n, w))
    return {g: int(c) for g, c in zip(["A","AB","B","BC","C","D","E"], counts)}


def gen_skor(rata_nilai: float, had_dosen: float) -> dict:
    def clamp(v): return round(min(4.0, max(1.5, v)), 2)
    bc = 2.5 + (rata_nilai / 4.0) * 1.4
    bp = 2.2 + (had_dosen / 100) * 1.6
    return {
        "q1":  clamp(bc + np.random.normal(0,    0.14)),
        "q2":  clamp(bc + np.random.normal(0.05, 0.12)),
        "q3":  clamp(bc + np.random.normal(-0.05,0.14)),
        "q4":  clamp(bp + np.random.normal(0,    0.12)),
        "q5":  clamp(bp + np.random.normal(0,    0.14)),
        "q6":  clamp(bp + np.random.normal(0.05, 0.11)),
        "q7":  clamp(bp + np.random.normal(0.08, 0.10)),
        "q8":  clamp(bp + np.random.normal(-0.08,0.14)),
        "q9":  clamp(3.1 + np.random.normal(0,   0.24)),
        "q10": clamp(3.2 + np.random.normal(0,   0.20)),
        "q11": clamp(3.3 + np.random.normal(0,   0.34)),
        "q12": clamp(3.2 + np.random.normal(0,   0.34)),
    }


# ── Step 3: Gemini text generation ───────────────────────────────────────────

def call_gemini(prompt: str, retries: int = 3) -> str:
    for attempt in range(retries):
        try:
            resp = client.models.generate_content(model=MODEL_ID, contents=prompt)
            return resp.text.strip()
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
            else:
                print(f"  [WARN] Gemini error: {e}")
                return "{}"


def gen_text_fields(kelas: dict, stats: dict, dist: dict, skor: dict) -> dict:
    dosen_list = kelas.get("dosen_list") or []
    dosen_str  = ", ".join(dosen_list) if dosen_list else "Dosen tidak tercatat"
    archetype  = infer_archetype(kelas["kode_mk"], kelas["nama_mk"])
    skor_avg   = round(sum(skor.values()) / len(skor), 2)
    pct_lulus  = sum(dist[g] for g in ["A","AB","B","BC","C"]) / stats["n_students"] * 100
    n_komen    = random.randint(8, 16)

    anomaly_ctx = {
        "low_attendance": (
            "PENTING: Kehadiran dosen sangat rendah (<70%). "
            "Refleksi harus jujur menyebut kendala dan dampaknya terhadap mahasiswa."
        ),
        "grade_inflation": (
            "PENTING: Hampir semua mahasiswa mendapat A/AB. "
            "Analisis harus natural, menyebut metode evaluasi yang mungkin membedakan."
        ),
    }.get(stats.get("anomaly"), "")

    prompt = f"""Anda adalah dosen ITB yang menulis portofolio perkuliahan. Gunakan bahasa Indonesia dengan tone natural, dan spesifik.

        DATA KELAS:
        - Mata Kuliah  : {kelas['nama_mk']} ({kelas['kode_mk']})
        - Kelas        : {kelas['no_kelas']} | Prodi: {kelas['singkatan_prodi']} | Fakultas: {kelas['kode_fakultas']}
        - Semester     : {kelas['semester']} TA {kelas['tahun_ajaran']}
        - Dosen        : {dosen_str}
        - SKS          : {kelas['sks']}
        - Kehadiran Dosen   : {stats['had_dosen']}%
        - Kehadiran Mahasiswa: {stats['had_mhs']}%
        - Rata-rata Nilai    : {stats['rata_nilai']}/4.0
        - Distribusi Nilai   : A={dist['A']}, AB={dist['AB']}, B={dist['B']}, BC={dist['BC']}, C={dist['C']}, D={dist['D']}, E={dist['E']}
        - Total Mahasiswa    : {stats['n_students']} orang
        - Pct Lulus          : {pct_lulus:.1f}%
        - Rata Kuesioner     : {skor_avg}/4.0
        - Tipe Matkul        : {archetype}
        {anomaly_ctx}

        INSTRUKSI:
        1. Sebutkan nama dosen secara eksplisit (pakai nama dari "{dosen_str}") di metode_perkuliahan dan refleksi.
        2. komentar_mahasiswa_list harus berisi tepat {n_komen} komentar. Sebagian menyebut nama belakang dosen.
        Sentimen: {'positif dominan' if skor_avg >= 3.5 else 'campuran positif-negatif' if skor_avg >= 3.0 else 'banyak keluhan'}.
        3. Semua field harus konsisten satu sama lain (metode, nilai, kuesioner, refleksi saling terhubung).

        Kembalikan HANYA JSON valid berikut (tanpa markdown fence, tanpa teks tambahan):
        {{
            "metode_perkuliahan": "string panjang 2-4 paragraf",
            "sistem_penilaian_penjelasan": "string 1-2 paragraf",
            "tambahan_statistik_kelas": "string 1-2 paragraf",
            "analisis_capaian_outcomes": "string 2-3 paragraf",
            "komentar_dosen_kuesioner": "string 1-2 paragraf",
            "refleksi_pelaksanaan": "string 2-3 paragraf",
            "usulan_perbaikan_dosen_berikutnya": "string berisi 3-5 poin bernomor",
            "usulan_perbaikan_itb": "string berisi 2-3 poin bernomor",
            "komentar_mahasiswa_list": ["komentar1", "komentar2", ...]
        }}"""

    raw = call_gemini(prompt)

    # Strip markdown fences if present
    if "```" in raw:
        raw = raw.split("```", 1)[-1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.rsplit("```", 1)[0]
    raw = raw.strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        print(f"  [WARN] JSON parse failed for {kelas['kode_mk']}-K{kelas['no_kelas']}, using raw text")
        return {
            "metode_perkuliahan":                raw[:600] if raw else "",
            "sistem_penilaian_penjelasan":       "",
            "tambahan_statistik_kelas":          "",
            "analisis_capaian_outcomes":         "",
            "komentar_dosen_kuesioner":          "",
            "refleksi_pelaksanaan":              "",
            "usulan_perbaikan_dosen_berikutnya": "",
            "usulan_perbaikan_itb":              "",
            "komentar_mahasiswa_list":           [],
        }


# ── Step 4: Assemble + write CSV ──────────────────────────────────────────────

def build_and_write(kelas: dict, stats: dict, dist: dict, skor: dict, text: dict):
    n  = stats["n_students"]
    sebaran = [
        {"nilai": g, "jumlah": dist[g], "persen": round(dist[g] / n * 100, 2)}
        for g in ["A","AB","B","BC","C","D","E"]
    ]
    komponen = [
        {"no": 1, "bobot": 25, "nama": "Ujian Tengah Semester", "kategori_pddikti": "Ujian Tengah Semester"},
        {"no": 2, "bobot": 25, "nama": "Ujian Akhir Semester",  "kategori_pddikti": "Ujian Akhir Semester"},
        {"no": 3, "bobot": 20, "nama": "Tugas",                 "kategori_pddikti": "Tugas"},
        {"no": 4, "bobot": 20, "nama": "Kuis",                  "kategori_pddikti": "Kuis"},
        {"no": 5, "bobot": 10, "nama": "Praktikum",             "kategori_pddikti": "Praktikum"},
    ]
    metode_bobot = [
        {"metode": "Team-based project",            "bobot": 20},
        {"metode": "Pemecahan Kasus (Case Method)", "bobot": 0},
    ]

    skor_avg = sum(skor.values()) / len(skor)
    if skor_avg >= 3.5 and stats["had_dosen"] >= 85:
        nilai_porto = 4
        ket = "Dosen pengampu menjelaskan dengan rinci proses pembelajaran, penilaian, evaluasi pembelajaran, dan rekomendasi."
    elif skor_avg >= 3.0:
        nilai_porto = 3
        ket = "Dosen pengampu menjelaskan proses pembelajaran dan penilaian dengan cukup baik."
    else:
        nilai_porto = 2
        ket = "Portofolio telah diisi namun beberapa bagian masih perlu dilengkapi."

    dosen_str  = " | ".join(kelas.get("dosen_list") or []) or "Tidak tercatat"
    komen_raw  = text.get("komentar_mahasiswa_list", [])
    komen_str  = "||".join(str(k) for k in komen_raw) if isinstance(komen_raw, list) else str(komen_raw)

    # Portfolio fields (matches real CSV format)
    portfolio_fields = [
        ("kode_kuliah",                       kelas["kode_mk"]),
        ("nama_kuliah",                       kelas["nama_mk"]),
        ("no_kelas",                          kelas["no_kelas"]),
        ("sks",                               kelas["sks"]),
        ("semester",                          kelas["semester"]),
        ("tahun_akademik",                    kelas["tahun_ajaran"]),
        ("nama_dosen",                        dosen_str),
        ("link_lms",                          random.choice(["Edunex", "Edunex", "Moodle"])),
        ("metode_perkuliahan",                text.get("metode_perkuliahan", "")),
        ("sistem_penilaian_komponen",         json.dumps(komponen, ensure_ascii=False)),
        ("sistem_penilaian_metode_bobot",     json.dumps(metode_bobot, ensure_ascii=False)),
        ("sistem_penilaian_penjelasan",       text.get("sistem_penilaian_penjelasan", "")),
        ("kehadiran_dosen_pct",               stats["had_dosen"]),
        ("kehadiran_mahasiswa_pct",           stats["had_mhs"]),
        ("rata_rata_nilai",                   stats["rata_nilai"]),
        ("total_mahasiswa",                   n),
        ("sebaran_nilai",                     json.dumps(sebaran, ensure_ascii=False)),
        ("tambahan_statistik_kelas",          text.get("tambahan_statistik_kelas", "")),
        ("analisis_capaian_outcomes",         text.get("analisis_capaian_outcomes", "")),
        ("kuesioner_q1_skor",                 skor["q1"]),
        ("kuesioner_q2_skor",                 skor["q2"]),
        ("kuesioner_q3_skor",                 skor["q3"]),
        ("kuesioner_q4_skor",                 skor["q4"]),
        ("kuesioner_q5_skor",                 skor["q5"]),
        ("kuesioner_q6_skor",                 skor["q6"]),
        ("kuesioner_q7_skor",                 skor["q7"]),
        ("kuesioner_q8_skor",                 skor["q8"]),
        ("kuesioner_q9_skor",                 skor["q9"]),
        ("kuesioner_q10_skor",                skor["q10"]),
        ("kuesioner_q11_skor",                skor["q11"]),
        ("kuesioner_q12_skor",                skor["q12"]),
        ("komentar_mahasiswa",                komen_str),
        ("komentar_dosen_kuesioner",          text.get("komentar_dosen_kuesioner", "")),
        ("refleksi_pelaksanaan",              text.get("refleksi_pelaksanaan", "")),
        ("usulan_perbaikan_dosen_berikutnya", text.get("usulan_perbaikan_dosen_berikutnya", "")),
        ("usulan_perbaikan_itb",              text.get("usulan_perbaikan_itb", "")),
        ("nilai_portofolio",                  nilai_porto),
        ("keterangan_nilai_portofolio",       ket),
    ]

    ta_clean = kelas["tahun_ajaran"].replace("/", "-")
    fname    = f"{kelas['kode_mk']}_K{kelas['no_kelas']}_{ta_clean}_sem{kelas['semester']}_portofolio.csv"
    fpath    = OUTPUT_DIR / fname

    with open(fpath, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["field", "value"])
        for field, value in portfolio_fields:
            writer.writerow([field, value])

    meta = {
        "kelas_id":      kelas["kelas_id"],
        "kode_prodi":    kelas["kode_prodi"],
        "kode_fakultas": kelas["kode_fakultas"],
        "csv_file":      fname,
    }
    (OUTPUT_DIR / fname.replace(".csv", ".meta.json")).write_text(
        json.dumps(meta, indent=2)
    )

    return fpath


# ── Step 5: Anomaly assignment ────────────────────────────────────────────────

def assign_anomaly(idx: int, total: int) -> str | None:
    # Inject ~10%: 1 low_attendance early, 1 grade_inflation late, 1 low_attendance mid
    triggers = {2: "low_attendance", total - 2: "grade_inflation", total // 2: "low_attendance"}
    return triggers.get(idx)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("\n── Mock Portfolio Generator ──\n")

    # Phase 1: Query DB
    print("[1/3] Querying real kelas from database...")
    stei_rows, other_rows = fetch_kelas()
    selected = select_kelas(stei_rows, other_rows)

    if not selected:
        print("ERROR: No kelas found in DB. Make sure kelas + pengajar_kelas are ingested first.")
        sys.exit(1)

    if len(selected) < TARGET_MIN:
        print(f"[WARN] Only {len(selected)} kelas available. "
              f"Ingest more kelas data to reach {TARGET_MIN}+.")

    # Validate constraints
    if_matkul_count  = len({r["kode_mk"] for r in selected if r["kode_prodi"] == "135"})
    fakultas_count   = len({r["kode_fakultas"] for r in selected})
    print(f"\n  Constraint check:")
    print(f"  IF matkul (≥3)  : {if_matkul_count} {'✓' if if_matkul_count >= 3 else '✗ WARN'}")
    print(f"  Fakultas (≥2)   : {fakultas_count}  {'✓' if fakultas_count >= 2 else '✗ WARN'}")
    print(f"  Total kelas     : {len(selected)} (target {TARGET_MIN}–{TARGET_MAX})")

    # Phase 2: Generate per kelas
    print(f"\n[2/3] Generating portfolios via Gemini (rate limited to ~15 RPM)...\n")
    generated = []

    for idx, kelas in enumerate(selected):
        anomaly   = assign_anomaly(idx, len(selected))
        archetype = infer_archetype(kelas["kode_mk"], kelas["nama_mk"])

        stats = gen_stats(archetype, anomaly)
        dist  = gen_grade_dist(archetype, stats["n_students"], anomaly)
        skor  = gen_skor(stats["rata_nilai"], stats["had_dosen"])

        label  = f"{kelas['kode_mk']}-K{kelas['no_kelas']} [{kelas['kode_prodi']}] {kelas['tahun_ajaran']}"
        marker = f" ⚑ ANOMALY:{anomaly}" if anomaly else ""
        print(f"  [{idx+1:02d}/{len(selected)}] {label}{marker}")

        text  = gen_text_fields(kelas, stats, dist, skor)
        fpath = build_and_write(kelas, stats, dist, skor, text)
        generated.append(fpath)

        # Gemini free tier: 15 RPM → sleep 4s between calls
        if idx < len(selected) - 1:
            time.sleep(4)

    # Phase 3: Summary
    print(f"\n[3/3] Complete. {len(generated)} files written to {OUTPUT_DIR}/\n")

    prodi_counts = Counter(r["kode_prodi"]    for r in selected)
    fak_counts   = Counter(r["kode_fakultas"] for r in selected)
    mk_counts    = Counter(r["kode_mk"]       for r in selected)

    print("  By prodi:")
    for p, c in sorted(prodi_counts.items()): print(f"    {p}: {c} kelas")
    print("  By fakultas:")
    for f, c in sorted(fak_counts.items()):   print(f"    {f}: {c} kelas")
    print("  Matkul coverage:")
    for m, c in sorted(mk_counts.items()):    print(f"    {m}: {c} kelas")

    print(f"\n  CSV  → {OUTPUT_DIR}/*.csv")
    print(f"  Meta → {OUTPUT_DIR}/*.meta.json  (kelas_id for ingestion pipeline)\n")


if __name__ == "__main__":
    main()