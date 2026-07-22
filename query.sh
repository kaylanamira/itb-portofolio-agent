#!/bin/bash
set -euo pipefail

API_URL="${API_URL:-http://127.0.0.1:8000/api/chat/stream}"
if [ -z "${SESSION_COOKIE_NAME:-}" ] && [ -f .env ]; then
  COOKIE_NAME="$(sed -n 's/^SESSION_COOKIE_NAME=//p' .env | tail -n 1 | tr -d '"'\''')"
else
  COOKIE_NAME="${SESSION_COOKIE_NAME:-itb_session}"
fi
COOKIE_NAME="${COOKIE_NAME:-itb_session}"
SESSION_ID="${CHAT_SESSION_ID:-test-session-1}"

if [ -z "${DEV_SESSION_ID:-}" ]; then
  echo "DEV_SESSION_ID belum di-set." >&2
  echo "Generate dulu: uv run python dev_session.py --role jajaran_dekanat --user-id 210015 --dosen-id 3 --kd-fak SF" >&2
  echo "Lalu export session id yang dicetak: export DEV_SESSION_ID=<session_id>" >&2
  exit 1
fi

if [ "${1:-}" = "--chart" ]; then
  QUERY="${2:-Insight apa yang bisa saya ambil dari grafik ini?}"
  BODY=$(cat <<JSON
{
  "query": "${QUERY}",
  "session_id": "${SESSION_ID}",
  "chart_context": {
    "chart_type": "entity_comparison_bar_chart",
    "title": "Peringkat — Rata-Rata Q4-Q7 (Performa Dosen)",
    "y_axis_label": "Skor rata-rata (skala 1-4)",
    "series": [
      {
        "kode_fakultas": "STEI",
        "nama_fakultas_id": "Sekolah Teknik Elektro dan Informatika",
        "rata_rata_dari_kolom": ["skor_q24", "skor_q25", "skor_q26", "skor_q27"],
        "nilai": 3.79,
        "delta_periode_lalu": 0.03
      },
      {
        "kode_fakultas": "FTMD",
        "nama_fakultas_id": "Fakultas Teknik Mesin dan Dirgantara",
        "rata_rata_dari_kolom": ["skor_q24", "skor_q25", "skor_q26", "skor_q27"],
        "nilai": 3.71,
        "delta_periode_lalu": -0.02
      },
      {
        "kode_fakultas": "SF",
        "nama_fakultas_id": "Sekolah Farmasi",
        "rata_rata_dari_kolom": ["skor_q24", "skor_q25", "skor_q26", "skor_q27"],
        "nilai": 3.65,
        "delta_periode_lalu": null
      }
    ],
    "filters_applied": {
      "tahun_ajaran": "2024/2025",
      "semester": [1]
    },
    "hint": [
      "Identifikasi fakultas dengan nilai tertinggi dan terendah pada metrik ini.",
      "Identifikasi seberapa lebar kesenjangan antarfakultas (apakah merata, atau ada outlier jauh di bawah rata-rata)",
      "Untuk metrik skor kuesioner (skor_q21 sampai skor_q37), nilai di bawah 3.0 (skala 1-4) mengindikasikan area yang perlu perhatian; ambang ini tidak berlaku untuk metrik avg_ip."
    ],
    "question_reference": {
      "skor_q24": { "kode_pertanyaan_frontend": "Q4", "pertanyaan": "Pelaksanaan perkuliahan terorganisir dengan baik" },
      "skor_q25": { "kode_pertanyaan_frontend": "Q5", "pertanyaan": "Dosen berkomunikasi dengan efektif" },
      "skor_q26": { "kode_pertanyaan_frontend": "Q6", "pertanyaan": "Dosen peduli terhadap pencapaian mahasiswa akan luaran mata kuliah" },
      "skor_q27": { "kode_pertanyaan_frontend": "Q7", "pertanyaan": "Dosen berlaku adil kepada mahasiswa" }
    }
  }
}
JSON
)
elif [ "${1:-}" = "--chart2" ]; then
  QUERY="${2:-Insight apa yang bisa saya ambil dari grafik ini?}"
  BODY=$(cat <<JSON
{
  "query": "${QUERY}",
  "session_id": "${SESSION_ID}",
  "chart_context": {
  "chart_type": "score_heatmap_matrix_chart",
  "title": "Heatmap Rata-Rata Skor per Fakultas × Pertanyaan",
  "series": [
    {
      "kode_fakultas": "STEI",
      "nama_fakultas_id": "Sekolah Teknik Elektro dan Informatika",
      "skor_q21": 3.72, "skor_q22": 3.68, "skor_q23": 3.75,
      "skor_q24": 3.81, "skor_q25": 3.79, "skor_q26": 3.70, "skor_q27": 3.65,
      "skor_q28": 3.38,
      "skor_q29": 3.55, "skor_q30": 3.50,
      "skor_q35": 3.81, "skor_q37": 3.73,
      "bottom_3_kolom": ["skor_q28", "skor_q30", "skor_q27"]
    },
    {
      "kode_fakultas": "FTMD",
      "nama_fakultas_id": "Fakultas Teknik Mesin dan Dirgantara",
      "skor_q21": 3.65, "skor_q22": 3.60, "skor_q23": 3.70,
      "skor_q24": 3.75, "skor_q25": 3.72, "skor_q26": 3.66, "skor_q27": 3.58,
      "skor_q28": 3.30,
      "skor_q29": 3.48, "skor_q30": 3.42,
      "skor_q35": 3.74, "skor_q37": 3.68,
      "bottom_3_kolom": ["skor_q28", "skor_q30", "skor_q29"]
    }
  ],
  "filters_applied": {
    "tahun_ajaran": "2024/2025",
    "semester": [1],
    "kode_fakultas": ["STEI", "FTMD"]
  },
  "hint": [
    "Identifikasi pertanyaan (kolom) yang konsisten rendah di banyak fakultas.",
    "Identifikasi pertanyaan (kolom) bottom_3_kolom (3 pertanyaan dengan skor terendah) di setiap fakultas untuk mengidentifikasi poin pertanyaan apa yang perlu menjadi perhatian untuk evaluasi setiap fakultas"
  ],
  "question_reference": {
    "skor_q21": { "kode_pertanyaan_frontend": "Q1", "pertanyaan": "Mahasiswa memperoleh cukup informasi luaran mata kuliah" },
    "skor_q22": { "kode_pertanyaan_frontend": "Q2", "pertanyaan": "Perkuliahan diarahkan agar mahasiswa mencapai luaran mata kuliah" },
    "skor_q23": { "kode_pertanyaan_frontend": "Q3", "pertanyaan": "Mahasiswa mencapai luaran mata kuliah" },
    "skor_q24": { "kode_pertanyaan_frontend": "Q4", "pertanyaan": "Pelaksanaan perkuliahan terorganisir dengan baik" },
    "skor_q25": { "kode_pertanyaan_frontend": "Q5", "pertanyaan": "Dosen berkomunikasi dengan efektif" },
    "skor_q26": { "kode_pertanyaan_frontend": "Q6", "pertanyaan": "Dosen peduli terhadap pencapaian mahasiswa akan luaran mata kuliah" },
    "skor_q27": { "kode_pertanyaan_frontend": "Q7", "pertanyaan": "Dosen berlaku adil kepada mahasiswa" },
    "skor_q28": { "kode_pertanyaan_frontend": "Q8", "pertanyaan": "Kesesuaian beban kerja dengan SKS" },
    "skor_q29": { "kode_pertanyaan_frontend": "Q9", "pertanyaan": "Sarana prasarana untuk mata kuliah tersedia dengan memadai" },
    "skor_q30": { "kode_pertanyaan_frontend": "Q10", "pertanyaan": "Tersedia cukup fasilitas pendukung di luar kuliah" },
    "skor_q35": { "kode_pertanyaan_frontend": "Q11", "pertanyaan": "Mahasiswa berusaha dengan sungguh-sungguh mengikuti mata kuliah" },
    "skor_q37": { "kode_pertanyaan_frontend": "Q12", "pertanyaan": "Mahasiswa memperoleh pengalaman belajar yang positif" }
  }
}
}
JSON
)
else
  QUERY="${1:-Identifikasi semester dengan skor keseluruhan IF paling rendah dalam 3 tahun terakhir, lalu analisis dimensi mana (capaian/pelaksanaan/sarana/perilaku) yang paling berkontribusi terhadap rendahnya skor tersebut. ?}"
  BODY=$(cat <<JSON
{
  "query": "${QUERY}",
  "session_id": "${SESSION_ID}"
}
JSON
)
fi

curl -N -X POST "${API_URL}" \
  -H "Content-Type: application/json" \
  -b "${COOKIE_NAME}=${DEV_SESSION_ID}" \
  -d "${BODY}"
