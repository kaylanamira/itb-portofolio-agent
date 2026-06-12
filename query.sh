#!/bin/bash

QUERY="${1:-Berapa rata-rata skor kepuasan fasilitas ITB wisudawan S1??}"
ROLE="${2:-direktorat}"

curl -N -X POST http://127.0.0.1:8000/chat/stream \
  -H 'Content-Type: application/json' \
  -H "X-User-Role: ${ROLE}" \
  -d "{
    \"query\": \"${QUERY}\",
    \"session_id\": \"test-session-1\"
  }"
