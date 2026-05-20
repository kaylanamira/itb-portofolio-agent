1. Copy dan isi .env:
   - Copy .env.example → .env
   - Isi ADMIN_PASSWORD (bebas, min 8 karakter)

2. Install dependencies Python:
   uv sync

3. Pastiin semua file CSV dan JSON sudah ada di folder data/raw/

4. Jalankan database:
   docker compose up -d

5. Buat akun admin:
   uv run python seed_admin.py

6. Jalankan ingestion:
   uv run python ingest.py --data-dir ./data/raw