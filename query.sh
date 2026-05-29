#!/bin/bash

curl -N -X POST http://127.0.0.1:8000/chat/stream \
  -H 'Content-Type: application/json' \
  -d '{
    "query": "apa saja kk dan prodi di stei",
    "session_id": "test-session-1"
  }'
