#!/bin/bash
# Sebelum pakai, generate session dev sekali:
#   uv run python dev_session.py --role direktorat
#   export DEV_SESSION_ID=<session_id_yang_dicetak>

QUERY="${1:-Berapa rata-rata kehadiran mahasiswa semester 1 2024? dan kelas mana yang mahasiswanya suka gak hadir}"

if [ -z "$DEV_SESSION_ID" ]; then
  echo "DEV_SESSION_ID belum di-set." >&2
  echo "Generate dulu: uv run python dev_session.py --role direktorat" >&2
  exit 1
fi

# Nama cookie sesuai SESSION_COOKIE_NAME di .env (default: sid)
COOKIE_NAME="${SESSION_COOKIE_NAME:-sid}"

curl -N -X POST http://127.0.0.1:8000/api/chat/stream \
  -H 'Content-Type: application/json' \
  -b "${COOKIE_NAME}=${DEV_SESSION_ID}" \
  -d "{
    \"query\": \"${QUERY}\",
    \"session_id\": \"test-session-1\"
  }"