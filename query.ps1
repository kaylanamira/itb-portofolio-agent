# Sebelum pakai, generate session dev sekali:
#   uv run python dev_session.py --role direktorat
#   $env:DEV_SESSION_ID = "<session_id_yang_dicetak>"
#
# Lalu jalankan:
#   .\query.ps1 "Tampilkan daftar mata kuliah fsrd dengan SKS 4"

param(
    [string]$Query = "Berapa rata-rata skor kepuasan fasilitas ITB wisudawan S1?"
)

if (-not $env:DEV_SESSION_ID) {
    Write-Error "DEV_SESSION_ID belum di-set. Generate dulu: uv run python dev_session.py --role direktorat"
    exit 1
}

$cookieName = if ($env:SESSION_COOKIE_NAME) { $env:SESSION_COOKIE_NAME } else { "sid" }

# Tulis body ke file temp - menghindari masalah escaping quote saat pass ke curl.exe
$bodyObj = @{
    query      = $Query
    session_id = "test-session-1"
}
$tempFile = New-TemporaryFile
$bodyObj | ConvertTo-Json -Compress | Out-File -FilePath $tempFile -Encoding utf8 -NoNewline

try {
    curl.exe -N -X POST "http://127.0.0.1:8000/api/chat/stream" `
        -H "Content-Type: application/json" `
        -b "sid=$env:DEV_SESSION_ID" `
        -d "@$tempFile"
} finally {
    Remove-Item $tempFile -ErrorAction SilentlyContinue
}