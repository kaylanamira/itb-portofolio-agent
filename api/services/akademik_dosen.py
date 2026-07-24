"""
api/services/akademik_dosen.py

Service layer untuk dashboard personal dosen. Semua fungsi discope ke 1
dosen lewat filter aplikasi (%s = ANY(semua_dosen_id)) di atas
analitik.v_akademik_kelas dan analitik.v_akademik_komponen_evaluasi_kelas
— BUKAN mengandalkan RLS. RLS role dosen di v_akademik_kelas sengaja
dibiarkan seluas prodi (lihat DB_REFERENCE.md) untuk kebutuhan chatbot;
dashboard menyempitkan lagi di sini karena kebutuhannya beda (data milik
diri sendiri, bukan seluruh prodi).

Semua fungsi menerima dosen_id: int eksplisit sebagai parameter (bukan
diambil dari scope di dalam fungsi) — konsisten dengan gaya fungsi lain
di akademik.py yang juga terima parameter entitas eksplisit (fakultas, no_ps),
dan supaya fungsi tetap gampang di-unit-test tanpa mock UserScope penuh.
"""

import logging

from core.scope         import UserScope
from core.sql_executor  import PsycopgExecutor
from api.schemas.dashboard_akademik import AkademikQueryFilters
from api.services.akademik_constants import (
    DOSEN_KATEGORI_SKOR,
    DOSEN_PERTANYAAN_PER_KATEGORI,
)
from api.services.akademik_scope_rules import period_label

logger    = logging.getLogger(__name__)
_executor = PsycopgExecutor()


# ─── Helper internal ───────────────────────────────────────────────────────────

def _period_clauses(filters: AkademikQueryFilters) -> tuple[list[str], list]:
    """Klausa periode yang dipakai berulang di semua query dosen."""
    clauses: list[str] = []
    params:  list       = []
    if filters.tahun_ajaran:
        clauses.append("tahun_ajaran = %s")
        params.append(filters.tahun_ajaran)
    if filters.semester:
        clauses.append("semester = ANY(%s)")
        params.append(filters.semester)
    if filters.jenjang:
        clauses.append("jenjang = ANY(%s)")
        params.append(filters.jenjang)
    return clauses, params


def _dosen_where(filters: AkademikQueryFilters, dosen_id: int) -> tuple[str, list]:
    """WHERE lengkap (periode + filter dosen) dipakai oleh mayoritas fungsi di file ini."""
    clauses, params = _period_clauses(filters)
    clauses.append("%s = ANY(semua_dosen_id)")
    params.append(dosen_id)
    return f"WHERE {' AND '.join(clauses)}", params


# ─── Phase 1: stats overview ────────────────────────────────────────────────────

async def get_dosen_stats_overview(
    scope: UserScope, filters: AkademikQueryFilters, dosen_id: int,
) -> dict | None:
    where_sql, params = _dosen_where(filters, dosen_id)
    sql = f"""
        SELECT
            COUNT(DISTINCT kode_matkul)::integer         AS jumlah_matkul,
            COUNT(*)::integer                            AS jumlah_kelas,
            COALESCE(SUM(sks), 0)::integer                AS total_sks_diajar,
            COALESCE(SUM(jumlah_mahasiswa), 0)::integer   AS jumlah_mahasiswa
        FROM analitik.v_akademik_kelas {where_sql}
    """
    result = await _executor.execute(sql, scope, params)
    if result.error:
        logger.error("get_dosen_stats_overview (dosen_id=%s): %s", dosen_id, result.error)
        return None
    return result.rows[0] if result.rows else None


# ─── Phase 2: tren temporal (Tab 1 baris 1) ────────────────────────────────────

async def get_dosen_trend(
    scope: UserScope, filters: AkademikQueryFilters, dosen_id: int, n_semester: int = 8,
) -> list[dict]:
    """
    Dibalik dari kronologis terbaru (untuk LIMIT n_semester yang benar),
    lalu dibalik lagi jadi kronologis terlama→terbaru untuk x-axis line chart
    — pola yang sama dipakai get_grade_trend() di akademik.py.
    """
    clauses, params = _period_clauses(filters)
    clauses.append("%s = ANY(semua_dosen_id)")
    params.append(dosen_id)
    where_sql = f"WHERE {' AND '.join(clauses)}"

    sql = f"""
        WITH per_periode AS (
            SELECT
                tahun_ajaran, semester,
                AVG(avg_ip_akhir_mahasiswa)                                  AS avg_ip_mahasiswa,
                AVG(avg_skor_overall)                                       AS avg_skor_overall,
                (AVG(skor_q24) + AVG(skor_q25) + AVG(skor_q26) + AVG(skor_q27)) / 4.0 AS avg_skor_q4_q7
            FROM analitik.v_akademik_kelas {where_sql}
            GROUP BY tahun_ajaran, semester
            ORDER BY tahun_ajaran DESC, semester DESC
            LIMIT %s
        )
        SELECT * FROM per_periode ORDER BY tahun_ajaran, semester
    """
    result = await _executor.execute(sql, scope, params + [n_semester])
    if result.error:
        logger.error("get_dosen_trend (dosen_id=%s): %s", dosen_id, result.error)
        return []
    return [
        {**row, "period_label": period_label(row["tahun_ajaran"], row["semester"])}
        for row in result.rows
    ]


# ─── Phase 3: tabel utama kelas (Tab 1 baris 2) ────────────────────────────────

async def get_dosen_kelas(
    scope: UserScope, filters: AkademikQueryFilters, dosen_id: int,
) -> list[dict]:
    where_sql, params = _dosen_where(filters, dosen_id)

    # LAG di-partition per (kode_matkul, no_kelas) supaya delta dibandingkan
    # dengan kelas paralel yang sama, bukan rata-rata semua kelas dosen.
    sql = f"""
        WITH periode AS (
            SELECT kelas_id, kode_matkul, nama_matkul_id, no_kelas,
                   tahun_ajaran, semester, jumlah_mahasiswa,
                   avg_ip_akhir_mahasiswa AS avg_ip,
                   avg_skor_overall,
                   pct_kehadiran_dosen, pct_kehadiran_mahasiswa
            FROM analitik.v_akademik_kelas {where_sql}
        )
        SELECT *,
            LAG(avg_ip)           OVER w AS prev_avg_ip,
            LAG(avg_skor_overall) OVER w AS prev_avg_skor_overall
        FROM periode
        WINDOW w AS (PARTITION BY kode_matkul, no_kelas ORDER BY tahun_ajaran, semester)
        ORDER BY tahun_ajaran DESC, semester DESC, kode_matkul, no_kelas
    """
    result = await _executor.execute(sql, scope, params)
    if result.error:
        logger.error("get_dosen_kelas (dosen_id=%s): %s", dosen_id, result.error)
        return []
    return result.rows


# ─── Phase 4: kelulusan A-C vs D-E (Tab 2 baris 1) ─────────────────────────────

async def get_dosen_kelulusan(
    scope: UserScope, filters: AkademikQueryFilters, dosen_id: int,
) -> dict:
    clauses, params = _period_clauses(filters)
    clauses.append("%s = ANY(semua_dosen_id)")
    params.append(dosen_id)
    where_sql = f"WHERE {' AND '.join(clauses)}"

    sql = f"""
        WITH per_periode AS (
            SELECT tahun_ajaran, semester, AVG(dist_pct_lulus_a_c) AS pct_lulus
            FROM analitik.v_akademik_kelas {where_sql}
            GROUP BY tahun_ajaran, semester
            ORDER BY tahun_ajaran DESC, semester DESC
            LIMIT 2
        )
        SELECT tahun_ajaran, semester, pct_lulus FROM per_periode
    """
    result = await _executor.execute(sql, scope, params)
    if result.error:
        logger.error("get_dosen_kelulusan (dosen_id=%s): %s", dosen_id, result.error)
        return {"pct_lulus_periode_ini": None, "pct_lulus_periode_lalu": None, "prev_period_label": None}

    rows = result.rows
    ini  = rows[0]["pct_lulus"] if len(rows) > 0 else None
    lalu = rows[1] if len(rows) > 1 else None
    return {
        "pct_lulus_periode_ini":  ini,
        "pct_lulus_periode_lalu": lalu["pct_lulus"] if lalu else None,
        "prev_period_label":      period_label(lalu["tahun_ajaran"], lalu["semester"]) if lalu else None,
    }


# ─── Phase 5: tabel luaran (Tab 2 baris 2) ─────────────────────────────────────

async def get_dosen_luaran(
    scope: UserScope, filters: AkademikQueryFilters, dosen_id: int,
) -> list[dict]:
    where_sql, params = _dosen_where(filters, dosen_id)
    sql = f"""
        SELECT
            kelas_id, kode_matkul, nama_matkul_id, no_kelas, jumlah_mahasiswa,
            avg_ip_akhir_mahasiswa AS avg_ip,
            dist_pct_lulus_a_c     AS pct_lulus_a_c
        FROM analitik.v_akademik_kelas {where_sql}
        ORDER BY tahun_ajaran DESC, semester DESC, kode_matkul, no_kelas
    """
    result = await _executor.execute(sql, scope, params)
    if result.error:
        logger.error("get_dosen_luaran (dosen_id=%s): %s", dosen_id, result.error)
        return []
    return result.rows


# ─── Phase 6: komposisi bobot penilaian (Tab 2 baris 3) ────────────────────────

async def get_dosen_grading_comp(
    scope: UserScope, filters: AkademikQueryFilters, dosen_id: int,
) -> list[dict]:
    where_sql, params = _dosen_where(filters, dosen_id)

    # Per-kelas, TANPA agregasi — beda dari get_grading_comp() di akademik.py
    # yang AVG() ke level fakultas/prodi. NULLIF(x, 0): bobot 0 berarti
    # komponen tidak dipakai, harus tampil None bukan 0 (lihat kontrak di
    # DosenGradingCompItem).
    sql = f"""
        SELECT
            kelas_id, kode_matkul, no_kelas,
            NULLIF(bobot_uts, 0)          AS bobot_uts,
            NULLIF(bobot_uas, 0)          AS bobot_uas,
            NULLIF(bobot_tugas, 0)        AS bobot_tugas,
            NULLIF(bobot_kuis, 0)         AS bobot_kuis,
            NULLIF(bobot_praktikum, 0)    AS bobot_praktikum,
            NULLIF(bobot_projek, 0)       AS bobot_projek,
            NULLIF(bobot_partisipatif, 0) AS bobot_partisipatif
        FROM analitik.v_akademik_komponen_evaluasi_kelas
        {where_sql}
        ORDER BY tahun_ajaran DESC, semester DESC, kode_matkul, no_kelas
    """
    result = await _executor.execute(sql, scope, params)
    if result.error:
        logger.error("get_dosen_grading_comp (dosen_id=%s): %s", dosen_id, result.error)
        return []
    return result.rows


# ─── Phase 7: skor per kategori (Tab 3, default view) ──────────────────────────

async def get_dosen_skor_kategori(
    scope: UserScope, filters: AkademikQueryFilters, dosen_id: int,
) -> list[dict]:
    where_sql, params = _dosen_where(filters, dosen_id)

    # 1 SELECT, 5 ekspresi AVG sekaligus — lebih efisien daripada 5 query
    # terpisah untuk 5 kategori (1 round-trip DB, bukan 5).
    select_exprs = ", ".join(
        f"{cfg['expr']} AS {kode}" for kode, cfg in DOSEN_KATEGORI_SKOR.items()
    )
    sql = f"SELECT {select_exprs} FROM analitik.v_akademik_kelas {where_sql}"

    result = await _executor.execute(sql, scope, params)
    if result.error:
        logger.error("get_dosen_skor_kategori (dosen_id=%s): %s", dosen_id, result.error)
        return []
    if not result.rows:
        return []

    row = result.rows[0]
    return [
        {"kode_kategori": kode, "label": cfg["label"], "skor": row[kode]}
        for kode, cfg in DOSEN_KATEGORI_SKOR.items()
    ]


# ─── Phase 8: drill-down per pertanyaan (Tab 3, saat 1 kategori diklik) ────────

async def get_dosen_skor_pertanyaan(
    scope: UserScope, filters: AkademikQueryFilters, dosen_id: int, kode_kategori: str,
) -> list[dict]:
    """
    kode_kategori sudah divalidasi FastAPI lewat tipe Literal (KategoriSkor)
    di router — di sini tinggal lookup, tidak perlu validasi ulang manual.
    """
    where_sql, params = _dosen_where(filters, dosen_id)
    pertanyaan_list = DOSEN_PERTANYAAN_PER_KATEGORI[kode_kategori]

    select_exprs = ", ".join(f"AVG({kolom}) AS {kolom}" for _, kolom, _ in pertanyaan_list)
    sql = f"SELECT {select_exprs} FROM analitik.v_akademik_kelas {where_sql}"

    result = await _executor.execute(sql, scope, params)
    if result.error:
        logger.error(
            "get_dosen_skor_pertanyaan (dosen_id=%s, kategori=%s): %s",
            dosen_id, kode_kategori, result.error,
        )
        return []
    if not result.rows:
        return []

    row = result.rows[0]
    return [
        {"kode_pertanyaan": kode_q, "pertanyaan": teks, "skor": row[kolom]}
        for kode_q, kolom, teks in pertanyaan_list
    ]

async def get_dosen_refleksi(
    scope: UserScope, filters: AkademikQueryFilters, dosen_id: int,
    page: int, page_size: int,
) -> tuple[list[dict], int]:
    """
    Refleksi & usulan perbaikan dari portofolio — DIBATASI ke portofolio milik
    dosen ini sendiri (dosen_id = ANY(semua_dosen_id) di aplikasi), BUKAN
    mengandalkan RLS. RLS v_akademik_portofolio untuk role dosen sengaja
    seluas prodi (lihat DB_REFERENCE.md) untuk kebutuhan eksplorasi chatbot;
    dashboard menyempitkan lagi di sini karena tujuannya beda: dosen melihat
    refleksi dirinya sendiri, bukan riset lintas dosen di prodinya.
    """
    clauses, params = _period_clauses(filters)
    clauses.append("%s = ANY(semua_dosen_id)")
    params.append(dosen_id)
    # Hanya baris yang benar-benar terisi salah satu field refleksi/usulan —
    # portofolio yang belum diisi tidak perlu muncul sebagai "komentar kosong".
    clauses.append("(refleksi_pelaksanaan_perkuliahan IS NOT NULL "
                    "OR usulan_perbaikan_oleh_dosen_berikutnya IS NOT NULL)")
    where_sql = f"WHERE {' AND '.join(clauses)}"

    count_sql = f"SELECT COUNT(*) AS total FROM analitik.v_akademik_portofolio {where_sql}"
    count_result = await _executor.execute(count_sql, scope, params)
    if count_result.error:
        logger.error("get_dosen_refleksi count (dosen_id=%s): %s", dosen_id, count_result.error)
        return [], 0
    total = count_result.rows[0]["total"] if count_result.rows else 0

    # teks gabungan: refleksi dulu, usulan perbaikan setelahnya (kalau
    # keduanya ada) -- 1 kartu per kelas, bukan dipecah 2 item terpisah,
    # supaya tetap 1 baris = 1 hasil pengisian dosen, mudah dibaca sekaligus.
    data_sql = f"""
        SELECT
            kelas_id, kode_matkul, nama_matkul_id, kode_prodi, nama_prodi_id,
            kode_fakultas, tahun_ajaran, semester,
            CONCAT_WS(
                E'\\n\\n',
                CASE WHEN refleksi_pelaksanaan_perkuliahan IS NOT NULL
                     THEN 'Refleksi: ' || refleksi_pelaksanaan_perkuliahan END,
                CASE WHEN usulan_perbaikan_oleh_dosen_berikutnya IS NOT NULL
                     THEN 'Usulan Perbaikan: ' || usulan_perbaikan_oleh_dosen_berikutnya END
            ) AS teks
        FROM analitik.v_akademik_portofolio {where_sql}
        ORDER BY tahun_ajaran DESC, semester DESC, kode_matkul
        LIMIT %s OFFSET %s
    """
    result = await _executor.execute(data_sql, scope, params + [page_size, (page - 1) * page_size])
    if result.error:
        logger.error("get_dosen_refleksi (dosen_id=%s): %s", dosen_id, result.error)
        return [], total
    return result.rows, total