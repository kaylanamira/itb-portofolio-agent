"""
api/services/akademik_constants.py

Konstanta & mapping murni untuk dashboard akademik.
"""

SEMESTER_MAP: dict[int, str] = {
    1: "Ganjil",
    2: "Genap",
    3: "Pendek",
}

STRATA_LABEL: dict[str, str] = {
    "S1": "S1", "S2": "S2", "S3": "S3", "PR": "Profesi",
}
STRATA_ORDER: dict[str, int] = {"S1": 0, "S2": 1, "S3": 2, "PR": 3}

# Dipakai get_skor_pertanyaan(): kolom MENTAH dari v_akademik_statistik_prodi.
# AVG() ditambahkan manual di query, kondisional (hanya saat granularity=fakultas).
KODE_GRUP_TO_COL: dict[str, str] = {
    "capaian":            "avg_skor_capaian",
    "pelaksanaan":        "avg_skor_pelaksanaan",
    "sarana_prasarana":   "avg_skor_sarana_prasarana",
    "perilaku_mahasiswa": "avg_skor_perilaku_mahasiswa",
    "overall":            "avg_skor_overall",
    "q21": "avg_skor_q21", "q22": "avg_skor_q22", "q23": "avg_skor_q23",
    "q24": "avg_skor_q24", "q25": "avg_skor_q25", "q26": "avg_skor_q26",
    "q27": "avg_skor_q27", "q28": "avg_skor_q28", "q29": "avg_skor_q29",
    "q30": "avg_skor_q30", "q35": "avg_skor_q35", "q37": "avg_skor_q37",
}
VALID_KODE_GRUP: frozenset[str] = frozenset(KODE_GRUP_TO_COL)

# Dipakai _course_ranking_query(): ekspresi AGREGAT LENGKAP dari v_akademik_kelas
# (kolom mentah beda nama: skor_qXX, bukan avg_skor_qXX). Selalu di-GROUP BY,
# jadi AVG() sudah termasuk di sini, bukan ditambahkan lagi di query.
METRIC_TO_EXPR: dict[str, str] = {
    "overall":            "AVG(avg_skor_overall)",
    "capaian":            "AVG(avg_skor_capaian)",
    "sarana_prasarana":   "AVG(avg_skor_sarana_prasarana)",
    "perilaku_mahasiswa": "AVG(avg_skor_perilaku_mahasiswa)",
    "avg_ip":             "AVG(avg_ip_akhir_mahasiswa)",
    "q4_q7": "(AVG(skor_q24) + AVG(skor_q25) + AVG(skor_q26) + AVG(skor_q27)) / 4.0",
    **{f"q{n}": f"AVG(skor_q{n})" for n in (21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 35, 37)},
}
VALID_RANKING_METRIC: frozenset[str] = frozenset(METRIC_TO_EXPR)

KOMENTAR_SOURCE: dict[str, dict] = {
    "mahasiswa": {
        "view":        "analitik.v_akademik_komentar_mahasiswa",
        "teks_col":    "komentar_teks",
        "order":       "ts_jawaban DESC",
        "null_filter": "komentar_teks IS NOT NULL AND komentar_teks != ''",
    },
    "dosen": {
        "view":        "analitik.v_akademik_portofolio",
        "teks_col":    "usulan_perbaikan_oleh_dosen_berikutnya",
        "order":       "tahun_ajaran DESC, semester DESC, kode_matkul",
        "null_filter": "usulan_perbaikan_oleh_dosen_berikutnya IS NOT NULL AND usulan_perbaikan_oleh_dosen_berikutnya != ''",
    },
    "itb": {
        "view":        "analitik.v_akademik_portofolio",
        "teks_col":    "usulan_perbaikan_oleh_itb",
        "order":       "tahun_ajaran DESC, semester DESC, kode_matkul",
        "null_filter": "usulan_perbaikan_oleh_itb IS NOT NULL AND usulan_perbaikan_oleh_itb != ''",
    },
}

DOSEN_KATEGORI_SKOR: dict[str, dict[str, str]] = {
    "capaian":            {"label": "Luaran Mata Kuliah (Q1-Q3)",     "expr": METRIC_TO_EXPR["capaian"]},
    "pelaksanaan":        {"label": "Performa Dosen (Q4-Q7)",         "expr": METRIC_TO_EXPR["q4_q7"]},
    "q28":                {"label": "Kesesuaian SKS (Q8)",            "expr": METRIC_TO_EXPR["q28"]},
    "sarana_prasarana":   {"label": "Sarana Prasarana (Q9-Q10)",      "expr": METRIC_TO_EXPR["sarana_prasarana"]},
    "perilaku_mahasiswa": {"label": "Pengalaman Mahasiswa (Q11-Q12)", "expr": METRIC_TO_EXPR["perilaku_mahasiswa"]},
}

# Pertanyaan individual per kategori, untuk endpoint drill-down.
# Teks & kode Q sengaja identik dengan frontend (metricFieldMap.ts) --
# satu sumber kebenaran, cuma disalin ke sisi backend karena backend
# butuh teks ini untuk dikirim di response, bukan cuma dipakai di UI.
DOSEN_PERTANYAAN_PER_KATEGORI: dict[str, list[tuple[str, str, str]]] = {
    # (kode_pertanyaan, kolom_db, teks_pertanyaan)
    "capaian": [
        ("Q1", "skor_q21", "Mahasiswa memperoleh cukup informasi luaran mata kuliah"),
        ("Q2", "skor_q22", "Perkuliahan diarahkan agar mahasiswa mencapai luaran mata kuliah"),
        ("Q3", "skor_q23", "Mahasiswa mencapai luaran mata kuliah"),
    ],
    "pelaksanaan": [
        ("Q4", "skor_q24", "Pelaksanaan perkuliahan terorganisir dengan baik"),
        ("Q5", "skor_q25", "Dosen berkomunikasi dengan efektif"),
        ("Q6", "skor_q26", "Dosen peduli terhadap pencapaian mahasiswa akan luaran mata kuliah"),
        ("Q7", "skor_q27", "Dosen berlaku adil kepada mahasiswa"),
    ],
    "q28": [
        ("Q8", "skor_q28", "Kesesuaian beban kerja dengan SKS"),
    ],
    "sarana_prasarana": [
        ("Q9",  "skor_q29", "Sarana prasarana untuk mata kuliah tersedia dengan memadai"),
        ("Q10", "skor_q30", "Tersedia cukup fasilitas pendukung di luar kuliah"),
    ],
    "perilaku_mahasiswa": [
        ("Q11", "skor_q35", "Mahasiswa berusaha dengan sungguh-sungguh mengikuti mata kuliah"),
        ("Q12", "skor_q37", "Mahasiswa memperoleh pengalaman belajar yang positif"),
    ],
}