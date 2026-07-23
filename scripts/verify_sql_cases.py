"""
Pure Ground-Truth SQL Case Verifier (No LLM).

Executes pure hand-crafted SQL ground-truth queries for all dataset v2 SQL cases directly
against PostgreSQL using ADMIN credentials.

Usage:
    # Run interactively (press Enter to go 1-by-1 through SQL cases)
    uv run python scripts/verify_sql_cases.py

    # Run non-interactively for all SQL cases
    uv run python scripts/verify_sql_cases.py --all

    # Filter for a specific case ID
    uv run python scripts/verify_sql_cases.py --case ARCH-DATA-C1-001

    # Filter for a specific query type (e.g. comparative, analytical_numeric)
    uv run python scripts/verify_sql_cases.py --type comparative
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import sys

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.database import init_db_pool, close_db_pool
from core.scope import UserScope, ScopeEntry, UserRole
from core.sql_executor import PsycopgExecutor


DATASET_PATH = Path("evals/datasets/experiments/architecture_orchestration_cases_v2.json")


# ── Pure Ground Truth SQL Mapping for Dataset Cases ─────────────────────────
GROUND_TRUTH_SQL_MAP = {
    # ── data_lookup ──
    "ARCH-DATA-C1-001": [
        "SELECT kode_matkul, semester, tahun, ROUND(AVG(avg_skor_overall), 2) AS avg_skor_overall, SUM(jumlah_mahasiswa) AS total_responden FROM analitik.v_akademik_kelas WHERE kode_matkul = 'IF3170' AND tahun = 2024 GROUP BY kode_matkul, semester, tahun;"
    ],
    "ARCH-DATA-C1-002": [
        "SELECT DISTINCT kode_matkul, no_kelas, semua_dosen_nama_gelar, semester, tahun FROM analitik.v_akademik_kelas WHERE kode_matkul = 'IF3110' AND semester = 2 AND tahun = 2024;"
    ],
    "ARCH-DATA-C2-001": [
        "SELECT kode_prodi, ROUND(AVG(pct_kehadiran_mahasiswa), 2) AS avg_kehadiran_mahasiswa FROM analitik.v_akademik_kelas WHERE kode_prodi IN ('IF', 'EL') AND semester = 1 AND tahun = 2024 GROUP BY kode_prodi;"
    ],
    "ARCH-DATA-C2-002": [
        "SELECT kode_matkul, COUNT(DISTINCT no_kelas) AS jumlah_kelas_aktif FROM analitik.v_akademik_kelas WHERE kode_matkul IN ('IF3170', 'IF3230') AND semester = 1 AND tahun = 2024 GROUP BY kode_matkul;"
    ],
    "ARCH-DATA-C3-001": [
        "SELECT kode_prodi, semester, tahun, ROUND(AVG(avg_skor_pelaksanaan), 2) AS avg_skor_pelaksanaan FROM analitik.v_akademik_kelas WHERE kode_prodi = 'IF' AND semester = 1 AND tahun = 2024 GROUP BY kode_prodi, semester, tahun;"
    ],
    "ARCH-DATA-C3-002": [
        "SELECT kode_prodi, semester, tahun, ROUND(AVG(avg_skor_capaian), 2) AS avg_capaian, ROUND(AVG(avg_skor_pelaksanaan), 2) AS avg_pelaksanaan, ROUND(AVG(avg_skor_sarana_prasarana), 2) AS avg_sarana, ROUND(AVG(avg_skor_perilaku_mahasiswa), 2) AS avg_perilaku FROM analitik.v_akademik_kelas WHERE kode_prodi = 'IF' AND semester = 1 AND tahun = 2024 GROUP BY kode_prodi, semester, tahun;"
    ],
    "ARCH-DATA-C4-001": [
        "SELECT kode_matkul, nama_matkul_id, ROUND(AVG(dist_pct_lulus_a_c), 2) AS avg_pct_lulus, SUM(dist_jumlah_a) AS total_a, SUM(dist_jumlah_ab) AS total_ab, SUM(dist_jumlah_b) AS total_b, SUM(dist_jumlah_bc) AS total_bc, SUM(dist_jumlah_c) AS total_c, SUM(dist_jumlah_d) AS total_d, SUM(dist_jumlah_e) AS total_e FROM analitik.v_akademik_kelas WHERE kode_prodi = 'IF' AND semester = 1 AND tahun = 2024 GROUP BY kode_matkul, nama_matkul_id ORDER BY avg_pct_lulus ASC LIMIT 1;"
    ],
    "ARCH-DATA-C4-002": [
        "SELECT semester, tahun, ROUND(AVG(avg_skor_overall), 2) AS avg_overall, ROUND(AVG(avg_skor_capaian), 2) AS avg_capaian, ROUND(AVG(avg_skor_pelaksanaan), 2) AS avg_pelaksanaan, ROUND(AVG(avg_skor_sarana_prasarana), 2) AS avg_sarana, ROUND(AVG(avg_skor_perilaku_mahasiswa), 2) AS avg_perilaku FROM analitik.v_akademik_kelas WHERE tahun >= 2022 GROUP BY semester, tahun ORDER BY avg_overall ASC LIMIT 1;"
    ],

    # ── analytical_numeric ──
    "ARCH-ANUM-C1-001": [
        "SELECT kode_prodi, semester, tahun, ROUND(AVG(avg_skor_overall), 2) AS avg_skor_overall FROM analitik.v_akademik_kelas WHERE kode_prodi = 'IF' AND semester = 1 AND tahun = 2024 GROUP BY kode_prodi, semester, tahun;"
    ],
    "ARCH-ANUM-C1-002": [
        "SELECT kode_matkul, semester, tahun, ROUND(AVG(dist_pct_lulus_a_c), 2) AS avg_pct_lulus FROM analitik.v_akademik_kelas WHERE kode_matkul = 'IF3170' AND semester = 1 AND tahun = 2024 GROUP BY kode_matkul, semester, tahun;"
    ],
    "ARCH-ANUM-C2-001": [
        "SELECT kode_prodi, ROUND(AVG(pct_kehadiran_mahasiswa), 2) AS avg_kehadiran FROM analitik.v_akademik_kelas WHERE kode_prodi IN ('IF', 'STI') AND semester = 1 AND tahun = 2024 GROUP BY kode_prodi;"
    ],
    "ARCH-ANUM-C2-002": [
        "SELECT kode_prodi, semester, tahun, SUM(dist_jumlah_a + dist_jumlah_ab) AS total_a_ab, SUM(jumlah_mahasiswa) AS total_mahasiswa, ROUND(SUM(dist_jumlah_a + dist_jumlah_ab)::numeric / NULLIF(SUM(jumlah_mahasiswa), 0) * 100, 2) AS pct_a_ab FROM analitik.v_akademik_kelas WHERE kode_prodi = 'IF' AND semester = 1 AND tahun = 2024 GROUP BY kode_prodi, semester, tahun;"
    ],
    "ARCH-ANUM-C3-001": [
        "SELECT kode_prodi, semester, tahun, ROUND(AVG(avg_skor_perilaku_mahasiswa), 2) AS avg_skor_perilaku FROM analitik.v_akademik_kelas WHERE kode_prodi = 'IF' AND semester = 1 AND tahun = 2024 GROUP BY kode_prodi, semester, tahun;"
    ],
    "ARCH-ANUM-C3-002": [
        "SELECT kode_prodi, semester, tahun, ROUND(AVG(avg_skor_sarana_prasarana), 2) AS avg_skor_sarana FROM analitik.v_akademik_kelas WHERE kode_prodi = 'IF' AND semester = 1 AND tahun = 2024 GROUP BY kode_prodi, semester, tahun;"
    ],
    "ARCH-ANUM-C4-001": [
        "SELECT semester, tahun, ROUND(AVG(avg_skor_overall), 2) AS avg_overall, ROUND(AVG(avg_skor_capaian), 2) AS avg_capaian, ROUND(AVG(avg_skor_pelaksanaan), 2) AS avg_pelaksanaan, ROUND(AVG(avg_skor_sarana_prasarana), 2) AS avg_sarana, ROUND(AVG(avg_skor_perilaku_mahasiswa), 2) AS avg_perilaku FROM analitik.v_akademik_kelas WHERE kode_prodi = 'IF' AND tahun >= 2022 GROUP BY semester, tahun ORDER BY avg_overall ASC LIMIT 1;"
    ],
    "ARCH-ANUM-C4-002": [
        "SELECT kode_matkul, nama_matkul_id, ROUND(AVG(dist_pct_lulus_a_c), 2) AS avg_pct_lulus, ROUND(AVG(avg_skor_overall), 2) AS avg_skor_overall, ROUND(AVG(pct_kehadiran_dosen), 2) AS avg_kehadiran_dosen FROM analitik.v_akademik_kelas WHERE kode_prodi = 'IF' AND semester = 1 AND tahun = 2024 GROUP BY kode_matkul, nama_matkul_id HAVING AVG(dist_pct_lulus_a_c) < 70 ORDER BY avg_pct_lulus ASC;"
    ],

    # ── analytical_text / analytical_hybrid ──
    "ARCH-ATXT-C3-001": [
        "SELECT kode_matkul, no_kelas, ROUND(AVG(avg_skor_overall), 2) AS avg_skor_overall FROM analitik.v_akademik_kelas WHERE kode_matkul = 'IF3170' AND semester = 1 AND tahun = 2024 GROUP BY kode_matkul, no_kelas ORDER BY avg_skor_overall ASC LIMIT 1;"
    ],
    "ARCH-ATXT-C3-002": [
        "SELECT kode_prodi, ROUND(AVG(pct_kehadiran_dosen), 2) AS avg_kehadiran FROM analitik.v_akademik_kelas WHERE semester = 1 AND tahun = 2024 GROUP BY kode_prodi ORDER BY avg_kehadiran ASC LIMIT 1;"
    ],
    "ARCH-ATXT-C4-001": [
        "SELECT kode_matkul, no_kelas, semester, tahun, ROUND(AVG(avg_skor_overall), 2) AS avg_overall FROM analitik.v_akademik_kelas WHERE kode_prodi = 'IF' AND tahun IN (2023, 2024) GROUP BY kode_matkul, no_kelas, semester, tahun ORDER BY kode_matkul, no_kelas, tahun, semester;"
    ],
    "ARCH-ATXT-C4-002": [
        "SELECT kode_matkul, semester, tahun, ROUND(AVG(avg_skor_overall), 2) AS avg_skor_overall, ROUND(AVG(avg_skor_pelaksanaan), 2) AS avg_pelaksanaan FROM analitik.v_akademik_kelas WHERE kode_matkul = 'IF3110' AND semester = 1 AND tahun = 2024 GROUP BY kode_matkul, semester, tahun;"
    ],
    "ARCH-AHYB-C1-001": [
        "SELECT kode_matkul, semester, tahun, ROUND(AVG(avg_skor_overall), 2) AS avg_overall, ROUND(AVG(avg_skor_pelaksanaan), 2) AS avg_pelaksanaan FROM analitik.v_akademik_kelas WHERE kode_matkul = 'IF3170' AND semester = 1 AND tahun = 2024 GROUP BY kode_matkul, semester, tahun;"
    ],
    "ARCH-AHYB-C1-002": [
        "SELECT kode_matkul, semester, tahun, ROUND(AVG(avg_skor_overall), 2) AS avg_overall, ROUND(AVG(dist_pct_lulus_a_c), 2) AS avg_lulus FROM analitik.v_akademik_kelas WHERE kode_matkul = 'IF3240' AND semester = 1 AND tahun = 2024 GROUP BY kode_matkul, semester, tahun;"
    ],
    "ARCH-AHYB-C2-001": [
        "SELECT kode_matkul, semua_dosen_nama_gelar, semester, tahun, ROUND(AVG(avg_skor_overall), 2) AS avg_skor, ROUND(AVG(pct_kehadiran_dosen), 2) AS kehadiran_dosen FROM analitik.v_akademik_kelas WHERE kode_matkul = 'IF3170' AND tahun = 2024 GROUP BY kode_matkul, semua_dosen_nama_gelar, semester, tahun;"
    ],
    "ARCH-AHYB-C2-002": [
        "SELECT kode_prodi, semester, tahun, ROUND(AVG(avg_skor_sarana_prasarana), 2) AS avg_skor_sarana FROM analitik.v_akademik_kelas WHERE kode_prodi = 'IF' AND semester = 1 AND tahun = 2024 GROUP BY kode_prodi, semester, tahun;"
    ],
    "ARCH-AHYB-C3-001": [
        "SELECT kode_prodi, semester, tahun, ROUND(AVG(avg_skor_pelaksanaan), 2) AS avg_skor_beban FROM analitik.v_akademik_kelas WHERE kode_prodi = 'IF' AND semester = 1 AND tahun = 2024 GROUP BY kode_prodi, semester, tahun;"
    ],
    "ARCH-AHYB-C3-002": [
        "SELECT kode_matkul, nama_matkul_id, ROUND(AVG(avg_skor_overall), 2) AS avg_skor_overall FROM analitik.v_akademik_kelas WHERE kode_prodi = 'IF' AND semester = 1 AND tahun = 2024 GROUP BY kode_matkul, nama_matkul_id ORDER BY avg_skor_overall ASC LIMIT 1;"
    ],
    "ARCH-AHYB-C4-001": [
        "SELECT kode_matkul, no_kelas, semester, tahun, ROUND(AVG(avg_skor_overall), 2) AS avg_skor_overall FROM analitik.v_akademik_kelas WHERE kode_prodi = 'IF' AND (tahun = 2023 OR tahun = 2024) GROUP BY kode_matkul, no_kelas, semester, tahun ORDER BY kode_matkul, no_kelas, tahun, semester;"
    ],
    "ARCH-AHYB-C4-002": [
        "SELECT semester, tahun, ROUND(AVG(avg_skor_sarana_prasarana), 2) AS avg_sarana FROM analitik.v_akademik_kelas WHERE kode_prodi = 'IF' GROUP BY semester, tahun ORDER BY tahun ASC, semester ASC;"
    ],

    # ── diagnostic ──
    "ARCH-DIAG-C1-001": [
        "SELECT kode_matkul, nama_matkul_id, no_kelas, ROUND(AVG(dist_pct_lulus_a_c), 2) AS avg_pct_lulus FROM analitik.v_akademik_kelas WHERE kode_prodi = 'IF' AND semester = 1 AND tahun = 2024 GROUP BY kode_matkul, nama_matkul_id, no_kelas HAVING AVG(dist_pct_lulus_a_c) < 50 ORDER BY avg_pct_lulus ASC;"
    ],
    "ARCH-DIAG-C1-002": [
        "SELECT kode_matkul, no_kelas, semua_dosen_nama_gelar, ROUND(AVG(avg_skor_overall), 2) AS avg_skor_overall, ROUND(AVG(pct_kehadiran_mahasiswa), 2) AS avg_kehadiran_mhs FROM analitik.v_akademik_kelas WHERE kode_matkul = 'IF3170' AND semester = 1 AND tahun = 2024 GROUP BY kode_matkul, no_kelas, semua_dosen_nama_gelar;"
    ],
    "ARCH-DIAG-C2-001": [
        "SELECT kode_prodi, semester, tahun, ROUND(AVG(avg_skor_sarana_prasarana), 2) AS avg_skor_sarana FROM analitik.v_akademik_kelas WHERE kode_prodi = 'IF' AND semester = 1 AND tahun = 2024 GROUP BY kode_prodi, semester, tahun;"
    ],
    "ARCH-DIAG-C2-002": [
        "SELECT kode_prodi, ROUND(AVG(dist_pct_lulus_a_c), 2) AS avg_pct_lulus, ROUND(AVG(pct_kehadiran_dosen), 2) AS avg_kehadiran_dosen FROM analitik.v_akademik_kelas WHERE kode_prodi IN ('IF', 'EL') AND semester = 1 AND tahun = 2024 GROUP BY kode_prodi;"
    ],
    "ARCH-DIAG-C3-001": [
        "SELECT kode_matkul, no_kelas, semua_dosen_nama_gelar, ROUND(AVG(avg_skor_overall), 2) AS avg_skor_overall, ROUND(AVG(avg_skor_capaian), 2) AS avg_capaian, ROUND(AVG(avg_skor_pelaksanaan), 2) AS avg_pelaksanaan FROM analitik.v_akademik_kelas WHERE kode_matkul = 'IF3170' AND no_kelas IN (1, 2) AND semester = 1 AND tahun = 2024 GROUP BY kode_matkul, no_kelas, semua_dosen_nama_gelar;"
    ],
    "ARCH-DIAG-C3-002": [
        "SELECT kode_matkul, semester, tahun, ROUND(AVG(dist_pct_lulus_a_c), 2) AS avg_pct_lulus FROM analitik.v_akademik_kelas WHERE kode_matkul = 'IF3240' GROUP BY kode_matkul, semester, tahun ORDER BY tahun ASC, semester ASC;"
    ],
    "ARCH-DIAG-C4-001": [
        "SELECT kode_matkul, nama_matkul_id, kode_prodi, ROUND(AVG(pct_kehadiran_dosen), 2) AS kehadiran_dosen, ROUND(AVG(avg_skor_overall), 2) AS skor_overall FROM analitik.v_akademik_kelas WHERE semester = 1 AND tahun = 2024 GROUP BY kode_matkul, nama_matkul_id, kode_prodi HAVING AVG(pct_kehadiran_dosen) < 85 AND AVG(avg_skor_overall) < 3.4;"
    ],
    "ARCH-DIAG-C4-002": [
        "SELECT kode_matkul, no_kelas, semester, tahun, ROUND(AVG(avg_skor_overall), 2) AS avg_overall FROM analitik.v_akademik_kelas WHERE kode_prodi = 'IF' AND (tahun = 2023 OR tahun = 2024) GROUP BY kode_matkul, no_kelas, semester, tahun ORDER BY kode_matkul, no_kelas, tahun, semester;"
    ],

    # ── comparative ──
    "ARCH-COMP-C1-001": [
        "SELECT kode_matkul, semester, tahun, ROUND(AVG(avg_skor_overall), 2) AS avg_skor_overall FROM analitik.v_akademik_kelas WHERE kode_matkul IN ('IF3170', 'IF3110') AND semester = 1 AND tahun = 2024 GROUP BY kode_matkul, semester, tahun;"
    ],
    "ARCH-COMP-C1-002": [
        "SELECT kode_prodi, ROUND(AVG(pct_kehadiran_dosen), 2) AS avg_kehadiran_dosen FROM analitik.v_akademik_kelas WHERE semester = 1 AND tahun = 2024 GROUP BY kode_prodi ORDER BY avg_kehadiran_dosen DESC;"
    ],
    "ARCH-COMP-C2-001": [
        "SELECT kode_prodi, ROUND(AVG(avg_skor_overall), 2) AS avg_skor_overall FROM analitik.v_akademik_kelas WHERE kode_prodi IN ('IF', 'EL') AND semester = 1 AND tahun = 2024 GROUP BY kode_prodi;"
    ],
    "ARCH-COMP-C3-001": [
        "SELECT kode_matkul, no_kelas, ROUND(AVG(avg_skor_overall), 2) AS avg_overall, ROUND(AVG(avg_skor_capaian), 2) AS avg_capaian, ROUND(AVG(avg_skor_pelaksanaan), 2) AS avg_pelaksanaan, ROUND(AVG(avg_skor_sarana_prasarana), 2) AS avg_sarana, ROUND(AVG(avg_skor_perilaku_mahasiswa), 2) AS avg_perilaku FROM analitik.v_akademik_kelas WHERE kode_matkul = 'IF3170' AND semester = 1 AND tahun = 2024 GROUP BY kode_matkul, no_kelas ORDER BY avg_overall DESC;"
    ],
    "ARCH-COMP-C3-002": [
        "SELECT kode_matkul, semester, tahun, ROUND(AVG(avg_skor_overall), 2) AS avg_overall, ROUND(AVG(avg_skor_capaian), 2) AS avg_capaian, ROUND(AVG(avg_skor_pelaksanaan), 2) AS avg_pelaksanaan FROM analitik.v_akademik_kelas WHERE kode_matkul = 'IF3170' AND ((semester = 2 AND tahun = 2023) OR (semester = 1 AND tahun = 2024)) GROUP BY kode_matkul, semester, tahun ORDER BY tahun ASC, semester ASC;"
    ],
    "ARCH-COMP-C4-001": [
        "SELECT kode_prodi, semester, tahun, ROUND(AVG(avg_skor_overall), 2) AS avg_skor_overall FROM analitik.v_akademik_kelas WHERE tahun >= 2023 GROUP BY kode_prodi, semester, tahun ORDER BY kode_prodi, tahun ASC, semester ASC;"
    ],
    "ARCH-COMP-C4-002": [
        "SELECT semester, tahun, ROUND(AVG(avg_skor_overall), 2) AS avg_overall, ROUND(AVG(pct_kehadiran_mahasiswa), 2) AS avg_kehadiran_mhs, ROUND(AVG(dist_pct_lulus_a_c), 2) AS avg_pct_lulus FROM analitik.v_akademik_kelas WHERE tahun >= 2022 GROUP BY semester, tahun ORDER BY avg_overall DESC;"
    ],

    # ── chart_generate ──
    "ARCH-CGNT-C1-001": [
        "SELECT tahun, semester, ROUND(AVG(avg_skor_overall), 2) AS avg_skor_overall FROM analitik.v_akademik_kelas WHERE kode_matkul = 'IF3170' AND tahun BETWEEN 2022 AND 2024 GROUP BY tahun, semester ORDER BY tahun ASC, semester ASC;"
    ],
    "ARCH-CGNT-C1-002": [
        "SELECT SUM(dist_jumlah_a) AS total_a, SUM(dist_jumlah_ab) AS total_ab, SUM(dist_jumlah_b) AS total_b, SUM(dist_jumlah_bc) AS total_bc, SUM(dist_jumlah_c) AS total_c, SUM(dist_jumlah_d) AS total_d, SUM(dist_jumlah_e) AS total_e FROM analitik.v_akademik_kelas WHERE kode_prodi = 'IF' AND semester = 1 AND tahun = 2024;"
    ],
    "ARCH-CGNT-C2-001": [
        "SELECT kode_prodi, semester, tahun, ROUND(AVG(avg_skor_overall), 2) AS avg_skor_overall FROM analitik.v_akademik_kelas WHERE kode_prodi IN ('IF', 'EL') AND tahun >= 2023 GROUP BY kode_prodi, semester, tahun ORDER BY tahun ASC, semester ASC;"
    ],
    "ARCH-CGNT-C2-002": [
        "SELECT kode_prodi, ROUND(AVG(avg_kehadiran_dosen), 2) AS avg_kehadiran_dosen FROM analitik.v_akademik_kelas WHERE semester = 1 AND tahun = 2024 GROUP BY kode_prodi;"
    ],
    "ARCH-CGNT-C3-001": [
        "SELECT kode_matkul, semester, tahun, ROUND(AVG(avg_skor_overall), 2) AS avg_skor_overall FROM analitik.v_akademik_kelas WHERE kode_prodi = 'IF' AND tahun >= 2023 GROUP BY kode_matkul, semester, tahun ORDER BY kode_matkul, tahun ASC, semester ASC;"
    ],
    "ARCH-CGNT-C3-002": [
        "SELECT kode_prodi, ROUND(AVG(dist_pct_lulus), 2) AS avg_pct_lulus, SUM(dist_jumlah_a) AS total_a, SUM(dist_jumlah_ab) AS total_ab, SUM(dist_jumlah_b) AS total_b, SUM(dist_jumlah_bc) AS total_bc, SUM(dist_jumlah_c) AS total_c, SUM(dist_jumlah_d) AS total_d, SUM(dist_jumlah_e) AS total_e FROM analitik.v_akademik_kelas WHERE semester = 1 AND tahun = 2024 GROUP BY kode_prodi ORDER BY avg_pct_lulus ASC LIMIT 1;"
    ],
    "ARCH-CGNT-C4-001": [
        "SELECT kode_matkul, nama_matkul, ROUND(AVG(avg_kehadiran_dosen), 2) AS avg_kehadiran_dosen, ROUND(AVG(avg_skor_overall), 2) AS avg_skor_overall FROM analitik.v_akademik_kelas WHERE semester = 1 AND tahun = 2024 GROUP BY kode_matkul, nama_matkul;"
    ],
    "ARCH-CGNT-C4-002": [
        "SELECT semester, tahun, ROUND(AVG(avg_skor_capaian), 2) AS avg_capaian, ROUND(AVG(avg_skor_pelaksanaan), 2) AS avg_pelaksanaan, ROUND(AVG(avg_skor_sarana_prasarana), 2) AS avg_sarana, ROUND(AVG(avg_skor_perilaku_mahasiswa), 2) AS avg_perilaku FROM analitik.v_akademik_kelas WHERE tahun >= 2022 GROUP BY semester, tahun ORDER BY tahun ASC, semester ASC;"
    ],

    # ── chart_interpret ──
    "ARCH-CINT-C2-001": [
        "SELECT kode_prodi, semester, tahun, ROUND(AVG(avg_skor_overall), 2) AS avg_skor_overall FROM analitik.v_akademik_kelas WHERE kode_prodi = 'EL' AND semester = 1 AND tahun = 2024 GROUP BY kode_prodi, semester, tahun;"
    ],
    "ARCH-CINT-C2-002": [
        "SELECT kode_prodi, SUM(dist_jumlah_a) AS total_a, SUM(dist_jumlah_ab) AS total_ab, SUM(dist_jumlah_b) AS total_b, SUM(dist_jumlah_bc) AS total_bc, SUM(dist_jumlah_c) AS total_c, SUM(dist_jumlah_d) AS total_d, SUM(dist_jumlah_e) AS total_e FROM analitik.v_akademik_kelas WHERE kode_prodi = 'EL' AND semester = 1 AND tahun = 2024 GROUP BY kode_prodi;"
    ],
    "ARCH-CINT-C3-001": [
        "SELECT kode_matkul, no_kelas, semester, tahun, ROUND(AVG(avg_skor_overall), 2) AS avg_skor_overall FROM analitik.v_akademik_kelas WHERE kode_matkul = 'IF3110' AND tahun >= 2023 GROUP BY kode_matkul, no_kelas, semester, tahun ORDER BY no_kelas, tahun ASC, semester ASC;"
    ],
    "ARCH-CINT-C4-001": [
        "SELECT kode_matkul, semester, tahun, ROUND(AVG(avg_skor_overall), 2) AS avg_skor_overall, ROUND(AVG(avg_kehadiran_dosen), 2) AS avg_kehadiran_dosen FROM analitik.v_akademik_kelas WHERE kode_matkul = 'IF3110' GROUP BY kode_matkul, semester, tahun ORDER BY tahun ASC, semester ASC;"
    ],
    "ARCH-CINT-C4-002": [
        "SELECT kode_prodi, semester, tahun, ROUND(AVG(avg_skor_sarana_prasarana), 2) AS avg_skor_sarana FROM analitik.v_akademik_kelas WHERE semester = 1 AND tahun = 2024 GROUP BY kode_prodi, semester, tahun;"
    ],
}


def load_dataset_cases() -> list[dict]:
    try:
        from generate_dataset_v2 import CASES
        if CASES:
            return CASES
    except Exception:
        pass

    if not DATASET_PATH.exists():
        print(f"Error: Dataset file not found at {DATASET_PATH}")
        sys.exit(1)
    with open(DATASET_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("cases", [])


async def process_case(
    case: dict,
    executor: PsycopgExecutor,
    admin_scope: UserScope,
    step_by_step: bool,
    current_idx: int = 1,
    total_count: int = 1,
    is_last: bool = False,
):
    case_id = case.get("id")
    query_type = case.get("query_type")
    complexity = case.get("orchestration_complexity")
    raw_query = case.get("raw_query")

    sql_queries = GROUND_TRUTH_SQL_MAP.get(case_id)
    if not sql_queries:
        sql_queries = [
            f"SELECT kode_matkul, no_kelas, semester, tahun, ROUND(AVG(avg_skor_overall), 2) AS avg_skor_overall FROM analitik.v_akademik_kelas WHERE kode_prodi = 'IF' AND semester = 1 AND tahun = 2024 GROUP BY kode_matkul, no_kelas, semester, tahun LIMIT 5;"
        ]

    print("=" * 80)
    print(f"📌 CASE ID        : {case_id}  [{current_idx}/{total_count}]")
    print(f"🏷️  CATEGORY / TYPE: {query_type} ({complexity})")
    print(f"❓ RAW QUESTION   : {raw_query}")

    for idx, sql in enumerate(sql_queries, 1):
        print("-" * 80)
        if len(sql_queries) > 1:
            print(f"💻 PURE GROUND-TRUTH SQL #{idx}:")
        else:
            print("💻 PURE GROUND-TRUTH SQL:")
        print(f"{sql}\n")

        scoped_sql = sql.replace("{SCOPE_FILTER}", "1=1")

        try:
            res = await executor.execute(scoped_sql, user_scope=admin_scope)
            if res.error:
                print(f"❌ EXECUTION ERROR : {res.error}")
            else:
                sql_result = res.rows
                row_count = res.row_count

                print(f"📊 ROW COUNT       : {row_count}")
                print("📋 EXECUTION RESULT:")
                if sql_result:
                    preview_rows = sql_result[:5]
                    print(json.dumps(preview_rows, indent=2, ensure_ascii=False, default=str))
                    if len(sql_result) > 5:
                        print(f"   ... ({len(sql_result) - 5} more rows omitted)")
                else:
                    print("   [Empty result set / No rows returned]")

        except Exception as exc:
            print(f"❌ EXECUTION ERROR : {exc}")

    print("=" * 80 + "\n")

    if step_by_step:
        if is_last:
            print("🏁 Finished verifying all matching cases.")
        else:
            inp = input("Press [Enter] for next case, or 'q' to quit: ")
            if inp.strip().lower() == "q":
                return False
    return True


async def main():
    parser = argparse.ArgumentParser(description="Verify Ground-Truth SQL Queries directly against DB")
    parser.add_argument("--all", action="store_true", help="Run all cases continuously without pausing")
    parser.add_argument("--case", type=str, help="Filter for specific Case ID (e.g. ARCH-DATA-C1-001)")
    parser.add_argument("--type", type=str, help="Filter for specific Query Type (e.g. comparative)")
    args = parser.parse_args()

    cases = load_dataset_cases()

    # Filter cases in ground truth map or with SQL tool
    sql_cases = []
    for c in cases:
        cid = c.get("id")
        tools = c.get("expected_behavior", {}).get("expected_tool_sequence", [])
        if cid in GROUND_TRUTH_SQL_MAP or "sql" in tools:
            sql_cases.append(c)

    if args.case:
        sql_cases = [c for c in sql_cases if c.get("id") == args.case]
    elif args.type:
        sql_cases = [c for c in sql_cases if c.get("query_type") == args.type]

    total_selected = len(sql_cases)
    print(f"Found {total_selected} SQL cases out of {len(cases)} total cases.\n")

    await init_db_pool()
    try:
        admin_entry = ScopeEntry(user_role_id=1, role=UserRole.ADMIN)
        admin_scope = UserScope(user_id=1, active_role=admin_entry)
        executor = PsycopgExecutor()

        step_by_step = not args.all

        for i, case in enumerate(sql_cases, 1):
            is_last = (i == total_selected)
            cont = await process_case(
                case,
                executor,
                admin_scope,
                step_by_step=step_by_step,
                current_idx=i,
                total_count=total_selected,
                is_last=is_last,
            )
            if cont is False:
                break
    finally:
        await close_db_pool()


if __name__ == "__main__":
    asyncio.run(main())
