#!/usr/bin/env python3
"""
ingest_evaluasi_wisudawan.py
============================
ETL: resultssurvey926755_2.csv → schema evaluasi_wisudawan (dev_six)

Fase yang dijalankan:
  Phase 1 – DDL      : Buat schema + tabel (aman dijalankan ulang)
  Phase 2 – Seed Ref : Isi ref_grup_opsi dan ref_opsi
  Phase 3 – Seed Q   : Isi katalog pertanyaan dari header CSV
  Phase 4 – Load     : Transform + insert ke tabel respons
  Phase 5 – Impute   : Imputasi periode_ijazah_id yang NULL → periode_ijazah_id_final

Prasyarat:
  SSH tunnel aktif di terminal lain:
    ssh -L 5433:127.0.0.1:5432 root@35.219.15.98 -N -f

  Jalankan dari folder project (tempat CSV berada):
    uv run python ingest_evaluasi_wisudawan.py
    uv run python ingest_evaluasi_wisudawan.py --dry-run
    uv run python ingest_evaluasi_wisudawan.py --skip-ddl   # jika Phase 1-3 sudah pernah jalan
    uv run python ingest_evaluasi_wisudawan.py --skip-ddl --impute-only  # hanya jalankan Phase 5
"""

# ──────────────────────────────────────────────────────────────────────────────
# IMPORTS
# ──────────────────────────────────────────────────────────────────────────────
import re
import sys
import csv
import json
import logging
import argparse
import os
from pathlib import Path
from datetime import datetime

import pandas as pd
import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb   # adapter agar dict Python → JSONB PostgreSQL
from dotenv import load_dotenv
load_dotenv()

# ──────────────────────────────────────────────────────────────────────────────
# KONFIGURASI — ubah di sini jika path atau kredensial berbeda
# ──────────────────────────────────────────────────────────────────────────────
DB_URL = os.environ["DATABASE_URL"]
USER_ID = int(os.environ["USER_ID"])

CSV_PATH = Path("./data/raw/results-survey926755.csv")

REJECT_LOG = Path(f"/./data/log/reject_log_{datetime.now():%Y%m%d_%H%M%S}.csv")

BATCH_SIZE = 500

# ──────────────────────────────────────────────────────────────────────────────
# LOGGING — INFO ke terminal, DEBUG jika diperlukan
# ──────────────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    handlers=[logging.StreamHandler()],
)
log = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# METADATA COLUMNS — kolom CSV yang bukan pertanyaan (tidak masuk JSONB jawaban)
# ──────────────────────────────────────────────────────────────────────────────
META_COLS = {
    "id. Response ID",
    "submitdate. Date submitted",
    "lastpage. Last page",
    "startlanguage. Start language",
    "seed. Seed",
    "startdate. Date started",
    "datestamp. Date last action",
    "attribute_1. kd_strata",
    "attribute_2. kd_fak",
    "attribute_3. no_ps",
    "attribute_6. periode_ijazah_id",
}

# kd_pertanyaan yang dikecualikan dari JSONB (kolom kosong per desain kuesioner)
EXCLUDED_KD = {"SBM01_SQ032"}


# ──────────────────────────────────────────────────────────────────────────────
# QUESTION CONFIG
# Menentukan kd_grup_opsi dan batasan untuk setiap kd_pertanyaan.
# Diurutkan dari prefix TERPANJANG → terpendek (longest-match).
# Jika tidak ada yang cocok → free-text (kd_grup_opsi = None).
# ──────────────────────────────────────────────────────────────────────────────
_Q_CONFIG_RAW = [
    # prefix             kd_grup_opsi         batasan (JSON string atau None)
    ("SBM01_SQ",  "PERKEMBANGAN_SBM", '{"fakultas": ["SBM"]}'),
    ("FSRD05_SQ", "HARAPAN_FSRD",     '{"fakultas": ["FSRD"]}'),
    ("FSRD04_SQ", "HARAPAN_FSRD",     '{"fakultas": ["FSRD"]}'),
    ("FSRD03_SQ", "HARAPAN_FSRD",     '{"fakultas": ["FSRD"]}'),
    ("FSRD02_SQ", "HARAPAN_FSRD",     '{"fakultas": ["FSRD"]}'),
    ("FSRD01_SQ", "HARAPAN_FSRD",     '{"fakultas": ["FSRD"]}'),
    ("S104_SQ",   "SETUJU",           '{"strata": ["S1"]}'),
    ("S103",      "BIDANG_STUDI_LANJUT", '{"strata": ["S1"]}'),
    ("S102",      "LOKASI_STUDI_LANJUT", '{"strata": ["S1"]}'),
    ("S101",      "YA_TIDAK",         '{"strata": ["S1"]}'),
    ("M03",       "BIDANG_STUDI_LANJUT", '{"strata": ["S2"]}'),
    ("M02",       "LOKASI_STUDI_LANJUT", '{"strata": ["S2"]}'),
    ("M01",       "YA_TIDAK",         '{"strata": ["S2"]}'),
    ("D01_SQ",    "SETUJU",           '{"strata": ["S3"]}'),
    ("U07_SQ",    "HARAPAN",          None),
    ("U06_SQ",    "FREKUENSI",        None),
    ("U05_SQ",    "SETUJU",           None),
    ("U04_SQ",    "SETUJU",           None),
    ("U03_SQ",    "SETUJU",           None),
    ("U01_SQ",    "SETUJU",           None),
    ("U02",       "REKOMENDASI_PRODI", None),
    ("G",         None,               None),   # G01Qxx, G10Qxx, G11Qxx → free-text
]
Q_CONFIG = sorted(_Q_CONFIG_RAW, key=lambda x: len(x[0]), reverse=True)

# Mapping prefix → kd_grup untuk tabel pertanyaan
_GRUP_MAP = [
    ("SBM01",  "SBM01"),
    ("FSRD05", "FSRD05"), ("FSRD04", "FSRD04"), ("FSRD03", "FSRD03"),
    ("FSRD02", "FSRD02"), ("FSRD01", "FSRD01"),
    ("D01",    "D01"),
    ("S1",     "S1"),    # S101, S102, S103, S104_SQxxx semuanya → kd_grup "S1"
    ("M0",     "M"),     # M01, M02, M03
    ("U07",    "U07"),   ("U06", "U06"),   ("U05", "U05"),
    ("U04",    "U04"),   ("U03", "U03"),   ("U02", "U02"),   ("U01", "U01"),
    ("G01",    "G01"),   ("G10", "G10"),   ("G11", "G11"),
]


# ──────────────────────────────────────────────────────────────────────────────
# SEED DATA — ref_grup_opsi
# Konfirmasi dari: resultssurvey926755_2.csv (7535 responden)
# ──────────────────────────────────────────────────────────────────────────────
REF_GRUP_OPSI = [
    ("SETUJU",
     {"id": "Persetujuan 4-poin", "en": "4-point Agreement"}, "O"),
    ("FREKUENSI",
     {"id": "Frekuensi 4-poin", "en": "4-point Frequency"}, "O"),
    ("HARAPAN",
     {"id": "Pemenuhan Harapan 5-poin", "en": "5-point Expectation Fulfillment"}, "O"),
    ("HARAPAN_FSRD",
     {"id": "Pemenuhan Harapan 5-poin (FSRD)", "en": "5-point Expectation Fulfillment (FSRD)"}, "O"),
    ("PERKEMBANGAN_SBM",
     {"id": "Tingkat Perkembangan 5-poin (SBM)", "en": "5-point Level of Development (SBM)"}, "O"),
    ("YA_TIDAK",
     {"id": "Ya/Tidak", "en": "Yes/No"}, "N"),
    ("LOKASI_STUDI_LANJUT",
     {"id": "Lokasi Studi Lanjut", "en": "Further Study Location"}, "N"),
    ("BIDANG_STUDI_LANJUT",
     {"id": "Kelanjutan Bidang Studi", "en": "Field of Study Continuation"}, "N"),
    ("REKOMENDASI_PRODI",
     {"id": "Rekomendasi Prodi", "en": "Study Program Recommendation"}, "N"),
]


# ──────────────────────────────────────────────────────────────────────────────
# SEED DATA — ref_opsi
# Label dikonfirmasi dari nilai aktual di CSV (bukan asumsi).
# ──────────────────────────────────────────────────────────────────────────────
REF_OPSI = [
    # SETUJU (1=negatif → 4=positif)
    ("SETUJU", 1, {"id": "Tidak Setuju",            "en": "Disagree"}),
    ("SETUJU", 2, {"id": "Cenderung Tidak Setuju",  "en": "Somewhat Disagree"}),
    ("SETUJU", 3, {"id": "Cenderung Setuju",         "en": "Somewhat Agree"}),
    ("SETUJU", 4, {"id": "Setuju",                   "en": "Agree"}),

    # FREKUENSI (1=tidak pernah → 4=selalu)
    ("FREKUENSI", 1, {"id": "Tidak pernah atau sama sekali tidak", "en": "Never"}),
    ("FREKUENSI", 2, {"id": "Jarang atau kecil",                   "en": "Rarely"}),
    ("FREKUENSI", 3, {"id": "Sering atau cukup",                   "en": "Often"}),
    ("FREKUENSI", 4, {"id": "Selalu atau besar",                   "en": "Always"}),

    # HARAPAN — 5-poin, nilai=4 "Sepenuhnya memenuhi harapan" (BERBEDA dari HARAPAN_FSRD)
    ("HARAPAN", 1, {"id": "Tidak sesuai harapan",             "en": "Does not meet expectations"}),
    ("HARAPAN", 2, {"id": "Ada yang memenuhi harapan",        "en": "Partially meets expectations"}),
    ("HARAPAN", 3, {"id": "Sebagian besar memenuhi harapan",  "en": "Mostly meets expectations"}),
    ("HARAPAN", 4, {"id": "Sepenuhnya memenuhi harapan",      "en": "Fully meets expectations"}),
    ("HARAPAN", 5, {"id": "Melampaui harapan",                "en": "Exceeds expectations"}),

    # HARAPAN_FSRD — 5-poin, nilai=4 "Memenuhi harapan" (BERBEDA dari HARAPAN)
    ("HARAPAN_FSRD", 1, {"id": "Tidak sesuai harapan",            "en": "Does not meet expectations"}),
    ("HARAPAN_FSRD", 2, {"id": "Ada yang memenuhi harapan",       "en": "Partially meets expectations"}),
    ("HARAPAN_FSRD", 3, {"id": "Sebagian besar memenuhi harapan", "en": "Mostly meets expectations"}),
    ("HARAPAN_FSRD", 4, {"id": "Memenuhi harapan",                "en": "Meets expectations"}),
    ("HARAPAN_FSRD", 5, {"id": "Melampaui harapan",               "en": "Exceeds expectations"}),

    # PERKEMBANGAN_SBM — label dikonfirmasi langsung dari CSV
    ("PERKEMBANGAN_SBM", 1, {"id": "Undeveloped \u2013 Tidak berkembang",                               "en": "Undeveloped"}),
    ("PERKEMBANGAN_SBM", 2, {"id": "Slightly Developed \u2013 Sedikit berkembang",                      "en": "Slightly Developed"}),
    ("PERKEMBANGAN_SBM", 3, {"id": "Moderately Developed \u2013 Cukup berkembang",                      "en": "Moderately Developed"}),
    ("PERKEMBANGAN_SBM", 4, {"id": "Substantially Developed \u2013 Berkembang secara substansial",       "en": "Substantially Developed"}),
    ("PERKEMBANGAN_SBM", 5, {"id": "Highly Developed \u2013 Berkembang dengan sangat tinggi",           "en": "Highly Developed"}),

    # YA_TIDAK
    ("YA_TIDAK", 1, {"id": "Ya",     "en": "Yes"}),
    ("YA_TIDAK", 2, {"id": "Tidak",  "en": "No"}),

    # LOKASI_STUDI_LANJUT
    ("LOKASI_STUDI_LANJUT", 1, {"id": "ITB",                                          "en": "ITB"}),
    ("LOKASI_STUDI_LANJUT", 2, {"id": "Perguruan tinggi dalam negeri selain ITB",     "en": "Other domestic university"}),
    ("LOKASI_STUDI_LANJUT", 3, {"id": "Di luar negeri",                              "en": "Abroad"}),
    ("LOKASI_STUDI_LANJUT", 4, {"id": "Tidak ada rencana studi lanjut",              "en": "No further study plans"}),

    # BIDANG_STUDI_LANJUT (label panjang — harus cocok persis dengan CSV)
    ("BIDANG_STUDI_LANJUT", 1, {"id": "Ya, bidang studi tersebut merupakan kelanjutan dari bidang studi yang baru saya selesaikan di ITB",                             "en": "Yes, continuation of current ITB field"}),
    ("BIDANG_STUDI_LANJUT", 2, {"id": "Tidak, tetapi bidang studi tersebut masih serumpun dengan bidang studi yang baru saya selesaikan di ITB",                       "en": "No, but related field"}),
    ("BIDANG_STUDI_LANJUT", 3, {"id": "Tidak, tetapi bidang studi tersebut masih membutuhkan pengetahuan dari bidang studi yang baru saya selesaikan di ITB",           "en": "No, but requires ITB field knowledge"}),
    ("BIDANG_STUDI_LANJUT", 4, {"id": "Tidak, bidang studi tersebut sangat berbeda dari bidang studi yang baru saya selesaikan di ITB",                                "en": "No, very different field"}),
    ("BIDANG_STUDI_LANJUT", 5, {"id": "Tidak ada rencana studi lanjut",                                                                                                "en": "No further study plans"}),

    # REKOMENDASI_PRODI
    ("REKOMENDASI_PRODI", 1, {"id": "Kualitas dosen",         "en": "Lecturer quality"}),
    ("REKOMENDASI_PRODI", 2, {"id": "Suasana akademik",       "en": "Academic atmosphere"}),
    ("REKOMENDASI_PRODI", 3, {"id": "Jejaring alumni",        "en": "Alumni network"}),
    ("REKOMENDASI_PRODI", 4, {"id": "Lapangan pekerjaan",     "en": "Job prospects"}),
    ("REKOMENDASI_PRODI", 5, {"id": "Fasilitas akademik",     "en": "Academic facilities"}),
    ("REKOMENDASI_PRODI", 6, {"id": "Tidak merekomendasikan", "en": "Would not recommend"}),
    ("REKOMENDASI_PRODI", 7, {"id": "Other",                  "en": "Other"}),
]


# ──────────────────────────────────────────────────────────────────────────────
# DDL — schema dan tabel
# CATATAN: FK ke wisuda.periode_ijazah DIHAPUS karena dev_six adalah sample DB
#          yang tidak memiliki semua periode. Aktifkan kembali di prod.
# ──────────────────────────────────────────────────────────────────────────────
DDL = """
CREATE SCHEMA IF NOT EXISTS evaluasi_wisudawan;

CREATE TABLE IF NOT EXISTS evaluasi_wisudawan.ref_grup_opsi (
    kd_grup_opsi  VARCHAR(30) PRIMARY KEY,
    nama          JSONB       NOT NULL,
    tipe          CHAR(1)     NOT NULL CHECK (tipe IN ('O','N')),
    active        BOOLEAN     NOT NULL DEFAULT true,
    ts_entry      TIMESTAMPTZ NOT NULL DEFAULT now(),
    user_id_entry INTEGER     NOT NULL
);

CREATE TABLE IF NOT EXISTS evaluasi_wisudawan.ref_opsi (
    kd_grup_opsi  VARCHAR(30) NOT NULL
                      REFERENCES evaluasi_wisudawan.ref_grup_opsi(kd_grup_opsi)
                      ON UPDATE CASCADE ON DELETE RESTRICT
                      DEFERRABLE INITIALLY DEFERRED,
    nilai         SMALLINT    NOT NULL,
    label         JSONB       NOT NULL,
    active        BOOLEAN     NOT NULL DEFAULT true,
    ts_entry      TIMESTAMPTZ NOT NULL DEFAULT now(),
    user_id_entry INTEGER     NOT NULL,
    PRIMARY KEY (kd_grup_opsi, nilai)
);

CREATE TABLE IF NOT EXISTS evaluasi_wisudawan.pertanyaan (
    kd_pertanyaan  VARCHAR(20) PRIMARY KEY,
    header_csv_raw VARCHAR(500),
    kd_grup        VARCHAR(15) NOT NULL,
    pertanyaan     JSONB       NOT NULL,
    kd_grup_opsi   VARCHAR(30)
                       REFERENCES evaluasi_wisudawan.ref_grup_opsi(kd_grup_opsi)
                       ON UPDATE CASCADE ON DELETE RESTRICT
                       DEFERRABLE INITIALLY DEFERRED,
    batasan        JSONB,
    urutan         SMALLINT,
    active         BOOLEAN     NOT NULL DEFAULT true,
    ts_entry       TIMESTAMPTZ NOT NULL DEFAULT now(),
    user_id_entry  INTEGER     NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_pertanyaan_kd_grup
    ON evaluasi_wisudawan.pertanyaan (kd_grup);
CREATE INDEX IF NOT EXISTS idx_pertanyaan_kd_grup_opsi
    ON evaluasi_wisudawan.pertanyaan (kd_grup_opsi);

CREATE TABLE IF NOT EXISTS evaluasi_wisudawan.respons (
    response_id                 SERIAL      PRIMARY KEY,
    survey_platform_response_id INTEGER,
    submit_date                 TIMESTAMPTZ,
    start_date                  TIMESTAMPTZ,
    last_page                   SMALLINT,
    kd_strata                   CHAR(2)     NOT NULL,
    kd_fak                      VARCHAR     NOT NULL
                                    REFERENCES utama.fakultas(kd_fak)
                                    ON UPDATE CASCADE ON DELETE RESTRICT
                                    DEFERRABLE INITIALLY DEFERRED,
    no_ps                       INTEGER     NOT NULL
                                    REFERENCES utama.program_studi(no_ps)
                                    ON UPDATE CASCADE ON DELETE RESTRICT
                                    DEFERRABLE INITIALLY DEFERRED,
    -- FK ke wisuda.periode_ijazah DINONAKTIFKAN di dev_six (sample DB).
    -- Di prod (DB SIX asli), aktifkan kembali dengan:
    --   ALTER TABLE evaluasi_wisudawan.respons
    --   ADD CONSTRAINT respons_periode_ijazah_id_fkey
    --   FOREIGN KEY (periode_ijazah_id)
    --   REFERENCES wisuda.periode_ijazah(periode_ijazah_id)
    --   ON UPDATE CASCADE ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED;
    periode_ijazah_id           INTEGER,
    jawaban                     JSONB,
    -- Kolom imputasi periode_ijazah_id (Phase 5)
    -- periode_ijazah_id_final : nilai siap pakai untuk analisis per periode wisuda.
    --   = periode_ijazah_id asli jika tidak null
    --   = nilai imputasi (nearest-period-before berbasis timestamp) jika aslinya null
    -- is_imputed : TRUE jika nilai final berasal dari imputasi, FALSE jika dari sumber asli.
    -- JANGAN hapus/overwrite periode_ijazah_id asli — simpan sebagai data forensik.
    periode_ijazah_id_final     INTEGER,
    is_imputed                  BOOLEAN     NOT NULL DEFAULT false,
    ts_entry                    TIMESTAMPTZ NOT NULL DEFAULT now(),
    user_id_entry               INTEGER     NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_respons_kd_strata
    ON evaluasi_wisudawan.respons (kd_strata);
CREATE INDEX IF NOT EXISTS idx_respons_kd_fak
    ON evaluasi_wisudawan.respons (kd_fak);
CREATE INDEX IF NOT EXISTS idx_respons_no_ps
    ON evaluasi_wisudawan.respons (no_ps);
CREATE INDEX IF NOT EXISTS idx_respons_periode
    ON evaluasi_wisudawan.respons (periode_ijazah_id);
CREATE INDEX IF NOT EXISTS idx_respons_strata_fak
    ON evaluasi_wisudawan.respons (kd_strata, kd_fak);
CREATE INDEX IF NOT EXISTS idx_respons_strata_periode
    ON evaluasi_wisudawan.respons (kd_strata, periode_ijazah_id);
CREATE INDEX IF NOT EXISTS idx_respons_periode_final
    ON evaluasi_wisudawan.respons (periode_ijazah_id_final);
CREATE INDEX IF NOT EXISTS idx_respons_jawaban_gin
    ON evaluasi_wisudawan.respons USING GIN (jawaban);

CREATE UNIQUE INDEX IF NOT EXISTS idx_respons_survey_id_uniq
    ON evaluasi_wisudawan.respons (survey_platform_response_id)
    WHERE survey_platform_response_id IS NOT NULL;
"""


# ══════════════════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ══════════════════════════════════════════════════════════════════════════════

def is_empty(val) -> bool:
    """True jika val merepresentasikan nilai kosong/tidak diisi."""
    if val is None:
        return True
    return str(val).strip() in ("", "nan", "NaN", "None", "NaT")


def parse_kd_pertanyaan(header: str) -> str | None:
    """
    Mengekstrak kd_pertanyaan dari header kolom CSV LimeSurvey.
    Contoh:
      "U03[SQ001]. Pernyataan..." → "U03_SQ001"
      "U02[other]. ..."           → "U02_other"
      "G01Q23. Kesan-kesan..."    → "G01Q23"
      "attribute_1. kd_strata"   → None  (metadata, bukan pertanyaan)
    """
    if header in META_COLS:
        return None
    code_part = header.split(".")[0].strip()
    # Ubah [SQ001] → _SQ001, [other] → _other
    return re.sub(r"\[(\w+)\]", r"_\1", code_part)


def get_opsi_config(kd: str) -> tuple[str | None, str | None]:
    """
    Mengembalikan (kd_grup_opsi, batasan_json_str) untuk suatu kd_pertanyaan.
    Menggunakan longest-prefix match dari Q_CONFIG.
    Mengembalikan (None, None) jika tidak ada cocok → free-text.
    """
    for prefix, kd_grup_opsi, batasan in Q_CONFIG:
        if kd.startswith(prefix):
            return kd_grup_opsi, batasan
    return None, None


def get_kd_grup(kd: str) -> str:
    """Mengembalikan kd_grup dari kd_pertanyaan (prefix match)."""
    for prefix, grup in _GRUP_MAP:
        if kd.startswith(prefix):
            return grup
    return kd  # fallback: gunakan kd_pertanyaan itu sendiri


def extract_question_text(header: str) -> str:
    """
    Mengekstrak teks pertanyaan dari header CSV LimeSurvey.
    Untuk sub-pertanyaan: ambil teks dalam [...] terakhir.
    Untuk pertanyaan utama: ambil semua teks setelah kode.
    Contoh:
      "U03[SQ001]. Pernyataan... [Tersedia cukup ruang kelas]"
        → "Tersedia cukup ruang kelas"
      "G01Q23. Kesan-kesan dan prestasi dalam belajar..."
        → "Kesan-kesan dan prestasi dalam belajar..."
    """
    if ". " not in header:
        return header
    text_part = header.split(". ", 1)[1].strip()
    matches = re.findall(r"\[([^\[\]]+)\]", text_part)
    if matches:
        return matches[-1].strip()
    return text_part


def build_kd_map(columns: list[str]) -> dict[str, str | None]:
    """
    Membuat mapping {header_kolom_csv → kd_pertanyaan}.
    kd_pertanyaan = None artinya kolom metadata, tidak diproses ke JSONB.
    """
    return {col: parse_kd_pertanyaan(col) for col in columns}


def build_label_lookup(conn) -> dict[str, dict[str, int]]:
    """
    Query ref_opsi dari DB dan bangun lookup:
      {kd_grup_opsi: {label_text_id: nilai_integer}}
    Digunakan untuk mengkonversi teks jawaban LimeSurvey → integer.
    """
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            "SELECT kd_grup_opsi, nilai, label->>'id' AS label_id "
            "FROM evaluasi_wisudawan.ref_opsi"
        )
        lookup: dict[str, dict[str, int]] = {}
        for row in cur.fetchall():
            g = row["kd_grup_opsi"]
            lookup.setdefault(g, {})[row["label_id"].strip()] = row["nilai"]
    total = sum(len(v) for v in lookup.values())
    log.info(f"  Label lookup: {len(lookup)} grup, {total} label total")
    return lookup


# ══════════════════════════════════════════════════════════════════════════════
# TRANSFORM — inti logika konversi per baris CSV
# ══════════════════════════════════════════════════════════════════════════════

def transform_row(
    row: dict,
    kd_map: dict[str, str | None],
    label_lookup: dict[str, dict[str, int]],
) -> tuple[dict | None, list[str]]:
    """
    Mengkonversi satu baris CSV menjadi dict siap INSERT ke tabel respons.

    Return:
      (respons_dict, warnings)
      respons_dict = None → baris ini ditolak sepenuhnya (masuk reject log)
      warnings = list pesan non-fatal (dicatat tapi baris tetap diingest)
    """
    warnings: list[str] = []

    try:
        survey_id = int(row["id. Response ID"])

        # ── Metadata ───────────────────────────────────────────────────
        def _ts(col: str) -> str | None:
            v = row.get(col, "")
            return None if is_empty(v) else v

        submit_date = _ts("submitdate. Date submitted")
        start_date  = _ts("startdate. Date started")

        lp_raw    = row.get("lastpage. Last page", "")
        last_page = None if is_empty(lp_raw) else int(float(lp_raw))

        kd_strata = row.get("attribute_1. kd_strata", "").strip()
        kd_fak    = row.get("attribute_2. kd_fak", "").strip()

        no_ps_raw = row.get("attribute_3. no_ps", "")
        no_ps     = None if is_empty(no_ps_raw) else int(float(no_ps_raw))

        prd_raw           = row.get("attribute_6. periode_ijazah_id", "")
        periode_ijazah_id = None if is_empty(prd_raw) else int(float(prd_raw))

        # ── Validasi metadata wajib ────────────────────────────────────
        if not kd_strata:
            return None, ["kd_strata kosong"]
        if not kd_fak:
            return None, ["kd_fak kosong"]
        if no_ps is None:
            return None, ["no_ps kosong"]

        # ── Build JSONB jawaban ────────────────────────────────────────
        jawaban: dict = {}
        u02_other: str | None = None

        for col_header, kd in kd_map.items():
            # Skip kolom metadata
            if kd is None:
                continue
            # Skip kolom yang dikecualikan per desain kuesioner
            if kd in EXCLUDED_KD:
                continue

            val = row.get(col_header, "")
            # Skip sel kosong — filosofi schema: hanya key yang dijawab masuk JSONB
            if is_empty(val):
                continue
            val_str = val.strip()

            # U02[other] → simpan terpisah, nanti tambahkan sebagai "U02_other"
            if kd == "U02_other":
                u02_other = val_str
                continue

            kd_grup_opsi, _ = get_opsi_config(kd)

            if kd_grup_opsi is None:
                # Free-text: simpan string apa adanya
                jawaban[kd] = val_str
            else:
                # Ordinal/Nominal: cari integer via label lookup
                grup_lkp = label_lookup.get(kd_grup_opsi, {})
                int_val  = grup_lkp.get(val_str)
                if int_val is None:
                    # Label tidak dikenal → warn, skip field ini (bukan reject baris)
                    warnings.append(
                        f"{kd} [{kd_grup_opsi}]: label tidak dikenal → \"{val_str[:50]}\""
                    )
                else:
                    jawaban[kd] = int_val

        # Tambahkan U02_other jika ada dan U02 terjawab
        if u02_other and "U02" in jawaban:
            jawaban["U02_other"] = u02_other

        return {
            "survey_platform_response_id": survey_id,
            "submit_date":       submit_date,
            "start_date":        start_date,
            "last_page":         last_page,
            "kd_strata":         kd_strata,
            "kd_fak":            kd_fak,
            "no_ps":             no_ps,
            "periode_ijazah_id": periode_ijazah_id,
            "jawaban":           jawaban,   # dict → akan dibungkus Jsonb() di phase_4
            "user_id_entry":     USER_ID,
        }, warnings

    except Exception as exc:
        return None, [f"Exception: {exc}"]


# ══════════════════════════════════════════════════════════════════════════════
# PHASE FUNCTIONS
# ══════════════════════════════════════════════════════════════════════════════

def phase_1_ddl(conn: psycopg.Connection) -> None:
    """Membuat schema dan seluruh tabel. Aman dijalankan ulang (IF NOT EXISTS)."""
    log.info("Phase 1 — DDL ...")
    with conn.cursor() as cur:
        cur.execute(DDL)
    conn.commit()
    log.info("  ✓ Schema dan tabel siap")


def phase_2_seed_ref(conn: psycopg.Connection) -> None:
    """Mengisi ref_grup_opsi dan ref_opsi. ON CONFLICT DO NOTHING = aman diulang."""
    log.info("Phase 2 — Seed ref_grup_opsi + ref_opsi ...")
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO evaluasi_wisudawan.ref_grup_opsi
                (kd_grup_opsi, nama, tipe, user_id_entry)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (kd_grup_opsi) DO NOTHING
            """,
            [(kd, Jsonb(nama), tipe, USER_ID) for kd, nama, tipe in REF_GRUP_OPSI],
        )
        cur.executemany(
            """
            INSERT INTO evaluasi_wisudawan.ref_opsi
                (kd_grup_opsi, nilai, label, user_id_entry)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (kd_grup_opsi, nilai) DO NOTHING
            """,
            [(kd, nilai, Jsonb(label), USER_ID) for kd, nilai, label in REF_OPSI],
        )
    conn.commit()
    log.info(f"  ✓ {len(REF_GRUP_OPSI)} grup opsi, {len(REF_OPSI)} opsi jawaban")


def phase_3_seed_pertanyaan(conn: psycopg.Connection, df: pd.DataFrame) -> None:
    """
    Membaca header kolom CSV dan mengisi tabel pertanyaan.
    kd_pertanyaan, kd_grup, teks pertanyaan semua diturunkan dari header CSV.
    """
    log.info("Phase 3 — Seed pertanyaan dari header CSV ...")
    seen_kd: set[str] = set()
    rows: list[tuple] = []
    urutan = 0

    for col in df.columns:
        if col in META_COLS:
            continue
        kd = parse_kd_pertanyaan(col)
        if kd is None or kd == "U02_other" or kd in EXCLUDED_KD:
            continue
        if kd in seen_kd:
            continue
        seen_kd.add(kd)

        kd_grup_opsi, batasan_str = get_opsi_config(kd)
        kd_grup   = get_kd_grup(kd)
        text      = extract_question_text(col)
        ptanyaan  = {"id": text, "en": text}   # en = id untuk sekarang, update manual jika perlu
        batasan   = json.loads(batasan_str) if batasan_str else None
        urutan   += 1

        rows.append((
            kd,
            col[:500],
            kd_grup,
            Jsonb(ptanyaan),
            kd_grup_opsi,
            Jsonb(batasan) if batasan else None,
            urutan,
            USER_ID,
        ))

    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO evaluasi_wisudawan.pertanyaan
                (kd_pertanyaan, header_csv_raw, kd_grup, pertanyaan,
                 kd_grup_opsi, batasan, urutan, user_id_entry)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (kd_pertanyaan) DO NOTHING
            """,
            rows,
        )
    conn.commit()
    log.info(f"  ✓ {len(rows)} pertanyaan di-seed")


def phase_4_load(
    conn: psycopg.Connection,
    df: pd.DataFrame,
    dry_run: bool,
) -> None:
    """
    Phase utama: transform setiap baris CSV dan insert ke tabel respons.
    - ON CONFLICT DO NOTHING: baris duplikat dilewati tanpa error
    - Reject log: baris yang gagal validasi ditulis ke CSV terpisah
    """
    log.info(
        f"Phase 4 — Load {'(DRY RUN) ' if dry_run else ''}"
        f"{len(df)} baris ..."
    )

    kd_map      = build_kd_map(list(df.columns))
    label_lookup = build_label_lookup(conn)
    records     = df.to_dict("records")   # convert sekali di sini, lebih efisien

    INSERT_SQL = """
        INSERT INTO evaluasi_wisudawan.respons (
            survey_platform_response_id, submit_date, start_date, last_page,
            kd_strata, kd_fak, no_ps, periode_ijazah_id, jawaban, user_id_entry
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (survey_platform_response_id)
            WHERE survey_platform_response_id IS NOT NULL
        DO NOTHING
    """

    def rec_to_tuple(r: dict) -> tuple:
        """Konversi dict respons ke tuple positional untuk executemany."""
        return (
            r["survey_platform_response_id"],
            r["submit_date"],
            r["start_date"],
            r["last_page"],
            r["kd_strata"],
            r["kd_fak"],
            r["no_ps"],
            r["periode_ijazah_id"],
            Jsonb(r["jawaban"]),   # dict → JSONB via psycopg3 Jsonb adapter
            r["user_id_entry"],
        )

    stats = {"attempted": 0, "rejected": 0, "warned": 0}
    reject_rows: list[dict] = []
    batch: list[tuple] = []

    with conn.cursor() as cur:
        for record in records:
            rec, warns = transform_row(record, kd_map, label_lookup)

            if rec is None:
                stats["rejected"] += 1
                reject_rows.append({
                    "survey_id": record.get("id. Response ID"),
                    "kd_strata": record.get("attribute_1. kd_strata"),
                    "kd_fak":    record.get("attribute_2. kd_fak"),
                    "no_ps":     record.get("attribute_3. no_ps"),
                    "last_page": record.get("lastpage. Last page"),
                    "reason":    " | ".join(warns),
                })
                continue

            if warns:
                stats["warned"] += 1
                log.debug(
                    f"  WARN survey_id={record.get('id. Response ID')}: "
                    + "; ".join(warns)
                )

            stats["attempted"] += 1
            if not dry_run:
                batch.append(rec_to_tuple(rec))
                if len(batch) >= BATCH_SIZE:
                    cur.executemany(INSERT_SQL, batch)
                    log.info(f"  ... {stats['attempted']} baris diproses")
                    batch.clear()

        # Flush sisa batch yang belum terkirim
        if not dry_run and batch:
            cur.executemany(INSERT_SQL, batch)

    if not dry_run:
        conn.commit()

    # ── Reject log ────────────────────────────────────────────────────────────
    if reject_rows:
        fields = ["survey_id", "kd_strata", "kd_fak", "no_ps", "last_page", "reason"]
        with open(REJECT_LOG, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            writer.writerows(reject_rows)
        log.warning(f"  Reject log → {REJECT_LOG} ({len(reject_rows)} baris)")

    # ── Summary ───────────────────────────────────────────────────────────────
    mode = "DRY RUN — tidak ada data yang ditulis ke DB" if dry_run else "INSERT selesai"
    log.info(
        f"\n{'='*50}\n"
        f"  {mode}\n"
        f"  Diproses : {stats['attempted']:>6} baris\n"
        f"  Ditolak  : {stats['rejected']:>6} baris (lihat {REJECT_LOG if reject_rows else 'tidak ada reject'})\n"
        f"  Peringatan: {stats['warned']:>5} baris (label tidak dikenal, lihat log)\n"
        f"{'='*50}"
    )


 
# ══════════════════════════════════════════════════════════════════════════════
# IMPUTATION CONFIG
# Batas waktu pembukaan survey per periode, diturunkan dari min(submitdate)
# di data filled (responden yang punya periode_ijazah_id terisi).
#
# Dasar pemilihan strategi:
#   1. Null SISTEMATIS (bukan acak): 95%+ null di Agt-Nov 2025 karena
#      LimeSurvey tidak men-set attribute_6 untuk batch survey tertentu.
#   2. Imputasi berbasis TIMESTAMP (bukan bulan): menggunakan momen pertama
#      ada responden filled per periode sebagai proxy "survey dibuka".
#      Ini menyelesaikan ambiguitas Oktober 2025 (split 202507/202509)
#      yang kalau pakai bulan hanya 57% akurat, tapi pakai timestamp
#      menjadi ~99% akurat (2009 dari 2033 baris → 202509).
#   3. TIDAK overwrite kolom asli: periode_ijazah_id tetap NULL untuk
#      forensik. Kolom baru periode_ijazah_id_final yang dipakai analitik.
# ══════════════════════════════════════════════════════════════════════════════
 
# Timestamp pertama ada responden untuk tiap periode (proxy "survey dibuka")
# Diperoleh dari: df.groupby('periode_ijazah_id')['submitdate'].min()
IMPUTE_PERIOD_BOUNDARIES: dict[int, datetime] = {
    202502: datetime(2025,  2, 1, 0, 0, 0),
    202504: datetime(2025,  4, 1, 0, 0, 0),
    202507: datetime(2025,  7, 1, 0, 0,  0),
    202509: datetime(2025, 9,  1, 0, 0, 0),
    202602: datetime(2026,  2,  1,  0, 0, 0),
    202604: datetime(2026,  4, 1, 0, 0, 0),
}
_IMPUTE_PERIODS_SORTED = sorted(IMPUTE_PERIOD_BOUNDARIES.keys())
 
 
def impute_periode(submit_ts: datetime | None) -> int | None:
    """
    Impute periode_ijazah_id dari submit timestamp.
 
    Logika: assign ke periode dengan boundary terbesar yang masih ≤ submit_ts.
    Ini adalah "nearest-period-before" berbasis timestamp exact.
 
    Contoh:
      submit 2025-08-15 → 202507 (boundary 2025-07-29, paling dekat sebelumnya)
      submit 2025-10-07 → 202509 (boundary 2025-10-06, sudah dibuka)
      submit 2025-10-05 → 202507 (202509 belum dibuka saat itu)
    """
    if submit_ts is None or pd.isna(submit_ts):
        return None
    # psycopg3 mengembalikan TIMESTAMPTZ sebagai timezone-aware datetime,
    # sedangkan IMPUTE_PERIOD_BOUNDARIES adalah naive (tanpa timezone).
    # Strip tzinfo agar bisa dibandingkan — urutan relatif tetap terjaga.
    if getattr(submit_ts, "tzinfo", None) is not None:
        submit_ts = submit_ts.replace(tzinfo=None)
    best = None
    for p in _IMPUTE_PERIODS_SORTED:
        if IMPUTE_PERIOD_BOUNDARIES[p] <= submit_ts:
            best = p
    return best
 
 
def phase_5_impute(conn: psycopg.Connection, dry_run: bool) -> None:
    """
    Phase 5 — Imputasi periode_ijazah_id_final untuk semua baris di tabel respons.
 
    Untuk setiap baris di respons:
      - Jika periode_ijazah_id NOT NULL → final = periode_ijazah_id, is_imputed = FALSE
      - Jika periode_ijazah_id IS NULL  → final = impute_periode(submit_date), is_imputed = TRUE
 
    UPDATE dilakukan dalam batch untuk efisiensi.
    Aman dijalankan ulang: menggunakan WHERE untuk skip baris yang sudah diupdate.
    """
    log.info(f"Phase 5 — Impute periode_ijazah_id {'(DRY RUN) ' if dry_run else ''}...")
 
    if dry_run:
        # Hitung saja berapa yang akan diupdate
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("""
                SELECT
                    COUNT(*) FILTER (WHERE periode_ijazah_id IS NOT NULL) AS n_filled,
                    COUNT(*) FILTER (WHERE periode_ijazah_id IS NULL)     AS n_null
                FROM evaluasi_wisudawan.respons
            """)
            row = cur.fetchone()
        log.info(
            f"  [DRY RUN] Akan diupdate:\n"
            f"    {row['n_filled']} baris → final = periode_ijazah_id asli, is_imputed = FALSE\n"
            f"    {row['n_null']} baris → final = hasil imputasi timestamp, is_imputed = TRUE\n"
            f"  Tidak ada yang ditulis."
        )
        return
 
    stats = {"filled": 0, "imputed_ok": 0, "imputed_null": 0}
 
    with conn.cursor(row_factory=dict_row) as cur:
        # ── Step A: Update baris yang periode_ijazah_id sudah terisi ──────────
        # Cukup satu UPDATE massal, tidak perlu looping
        cur.execute("""
            UPDATE evaluasi_wisudawan.respons
            SET
                periode_ijazah_id_final = periode_ijazah_id,
                is_imputed              = FALSE
            WHERE
                periode_ijazah_id IS NOT NULL
                AND periode_ijazah_id_final IS DISTINCT FROM periode_ijazah_id
        """)
        stats["filled"] = cur.rowcount
        log.info(f"  Step A: {stats['filled']} baris filled → periode_ijazah_id_final = asli")
 
        # ── Step B: Fetch baris NULL dan impute per-baris ─────────────────────
        # Fetch semua baris null untuk diimputasi di Python
        cur.execute("""
            SELECT response_id, submit_date
            FROM evaluasi_wisudawan.respons
            WHERE periode_ijazah_id IS NULL
              AND is_imputed = FALSE
            ORDER BY response_id
        """)
        null_rows = cur.fetchall()
        log.info(f"  Step B: {len(null_rows)} baris null akan diimputasi...")
 
        # Siapkan batch update
        batch_ok: list[tuple]   = []   # (imputed_id, response_id)
        batch_fail: list[tuple] = []   # response_id yang submit_date juga null
 
        for row in null_rows:
            imputed = impute_periode(row["submit_date"])
            if imputed is not None:
                batch_ok.append((imputed, row["response_id"]))
            else:
                batch_fail.append((row["response_id"],))
 
        # Update baris yang berhasil diimputasi
        if batch_ok:
            cur.executemany(
                """
                UPDATE evaluasi_wisudawan.respons
                SET periode_ijazah_id_final = %s,
                    is_imputed              = TRUE
                WHERE response_id = %s
                """,
                batch_ok,
            )
            stats["imputed_ok"] = len(batch_ok)
 
        # Update baris yang tidak bisa diimputasi (submit_date juga null)
        # Tetap set is_imputed = TRUE untuk menandai sudah diproses Phase 5
        if batch_fail:
            cur.executemany(
                """
                UPDATE evaluasi_wisudawan.respons
                SET periode_ijazah_id_final = NULL,
                    is_imputed              = TRUE
                WHERE response_id = %s
                """,
                batch_fail,
            )
            stats["imputed_null"] = len(batch_fail)
 
    conn.commit()
 
    # ── Laporan distribusi hasil imputasi ─────────────────────────────────────
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("""
            SELECT
                periode_ijazah_id_final,
                is_imputed,
                COUNT(*) AS n
            FROM evaluasi_wisudawan.respons
            GROUP BY periode_ijazah_id_final, is_imputed
            ORDER BY periode_ijazah_id_final NULLS LAST, is_imputed
        """)
        rows = cur.fetchall()
 
    log.info(
        f"\n{'='*55}\n"
        f"  Phase 5 selesai\n"
        f"  Filled (asli)  : {stats['filled']:>6} baris\n"
        f"  Imputed (ok)   : {stats['imputed_ok']:>6} baris\n"
        f"  Imputed (null) : {stats['imputed_null']:>6} baris (submit_date juga null)\n"
        f"\n  Distribusi periode_ijazah_id_final:\n"
        f"  {'periode_final':<20} {'is_imputed':<12} {'jumlah':>7}\n"
        f"  {'-'*40}"
    )
    for r in rows:
        pid = str(int(r["periode_ijazah_id_final"])) if r["periode_ijazah_id_final"] else "NULL"
        flag = "IMPUTED" if r["is_imputed"] else "original"
        log.info(f"  {pid:<20} {flag:<12} {r['n']:>7}")
    log.info("="*55)




def main() -> None:
    parser = argparse.ArgumentParser(
        description="ETL: LimeSurvey CSV → evaluasi_wisudawan (dev_six)"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Jalankan transform tapi tidak INSERT/UPDATE ke DB.",
    )
    parser.add_argument(
        "--skip-ddl", action="store_true",
        help="Lewati Phase 1-3 (DDL + seed ref + seed pertanyaan). "
             "Pakai jika schema sudah pernah dibuat sebelumnya.",
    )
    parser.add_argument(
        "--impute-only", action="store_true",
        help="Hanya jalankan Phase 5 (imputasi). "
             "Gunakan bersama --skip-ddl setelah Phase 4 selesai.",
    )
    args = parser.parse_args()

    # ── Validasi file CSV ──────────────────────────────────────────────────────
    if not CSV_PATH.exists():
        log.error(f"File CSV tidak ditemukan: {CSV_PATH.resolve()}")
        log.error("Pastikan script dijalankan dari folder yang sama dengan CSV.")
        sys.exit(1)

    # ── Baca CSV ───────────────────────────────────────────────────────────────
    log.info(f"Membaca {CSV_PATH} ...")
    df = pd.read_csv(CSV_PATH, encoding="utf-8-sig", dtype=str, keep_default_na=False)
    log.info(f"  {len(df)} baris, {len(df.columns)} kolom")

    # ── Koneksi DB ─────────────────────────────────────────────────────────────
    log.info("Koneksi ke DB ...")
    try:
        conn = psycopg.connect(DB_URL, autocommit=False)
    except Exception as exc:
        log.error(f"Gagal koneksi ke DB: {exc}")
        log.error("Pastikan SSH tunnel aktif: ssh -L 5433:127.0.0.1:5432 root@35.219.15.98 -N -f")
        sys.exit(1)
    log.info("  ✓ Koneksi berhasil")

    try:
        if args.impute_only:
            # Hanya Phase 5
            phase_5_impute(conn, dry_run=args.dry_run)
        else:
            if not args.skip_ddl:
                phase_1_ddl(conn)
                phase_2_seed_ref(conn)
                phase_3_seed_pertanyaan(conn, df)

            phase_4_load(conn, df, dry_run=args.dry_run)

            # Phase 5 selalu dijalankan setelah Phase 4 (kecuali dry-run)
            phase_5_impute(conn, dry_run=args.dry_run)

    except Exception as exc:
        conn.rollback()
        log.error(f"ETL gagal, rollback dijalankan: {exc}", exc_info=True)
        sys.exit(1)
    finally:
        conn.close()

    log.info("✓ ETL selesai")


if __name__ == "__main__":
    main()