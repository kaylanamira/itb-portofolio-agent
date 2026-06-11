"""
api/routers/auth.py

HTTP layer untuk autentikasi Microsoft SSO.

Tanggung jawab:
    - Definisi endpoint dan HTTP contract-nya
    - Baca query params / cookie dari request
    - Set cookie pada response
    - Orchestrasi: panggil modul auth.* dan kembalikan hasilnya

Tidak boleh berisi:
    - Logic MSAL langsung (→ auth/microsoft.py)
    - Logic Redis langsung (→ auth/session.py)
    - Logic DB / role mapping (→ auth/role_mapper.py, hari 4)
"""

import logging

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import JSONResponse, RedirectResponse

from auth.microsoft import build_login_flow, exchange_code_for_claims
from auth.role_mapper import AuthError, get_auth_user
from auth.session import (
    create_session,
    delete_session,
    get_session,
    pop_oauth_flow,
    store_oauth_flow,
)

from core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])

# Helper
def _set_session_cookie(response: RedirectResponse | JSONResponse, session_id: str) -> None:
    """
    Set cookie session pada response.
 
    Flag yang dipakai:
        httponly=True  → JS di browser tidak bisa baca cookie ini (cegah XSS)
        samesite="lax" → cookie dikirim saat navigasi top-level (redirect)
                         dan request same-site. Aman untuk localhost dev.
        secure=...     → False di lokal (HTTP), True di VM (HTTPS)
        path="/"       → cookie berlaku untuk semua path di domain ini
    """
    response.set_cookie(
        key=settings.SESSION_COOKIE_NAME,
        value=session_id,
        httponly=True,
        samesite="lax",
        secure=settings.SESSION_COOKIE_SECURE,
        max_age=settings.SESSION_TTL_SECONDS,
        path="/",
    )
 
 
def _clear_session_cookie(response: JSONResponse) -> None:
    """Hapus cookie session dari browser."""
    response.delete_cookie(
        key=settings.SESSION_COOKIE_NAME,
        path="/",
        samesite="lax",
    )

# Endpoint
@router.get("/login")
async def login():
    """
    Endpoint ini dipanggil oleh frontend saat user klik tombol "Login dengan Microsoft".

    Flow:
        1. Buat MSAL auth code flow (generate auth_uri + state untuk CSRF)
        2. Simpan flow dict di Redis (TTL 5 menit, cukup untuk user isi form login)
        3. Redirect browser ke halaman login Microsoft

    Frontend cukup arahkan user ke URL ini:
        window.location.href = "http://localhost:8000/api/v1/auth/login"
    """
    flow = await build_login_flow()
    await store_oauth_flow(flow)

    # 302 agar browser langsung ikuti redirect (bukan 307 yang preserve method)
    return RedirectResponse(url=flow["auth_uri"], status_code=status.HTTP_302_FOUND)


@router.get("/callback/microsoft", summary="Callback dari Microsoft setelah login")
async def microsoft_callback(request: Request):
    """
    Microsoft meredirect browser ke sini setelah user login.

    Query params yang dikirim Microsoft:
        code          → authorization code, tukar dengan token (satu kali pakai)
        state         → nilai yang kita set di /login, untuk validasi CSRF
        session_state → opsional, metadata session dari Microsoft
        error         → ada jika login gagal di sisi Microsoft
        error_description → penjelasan error

    Flow saat ini (Hari 2 — verifikasi):
        1. Cek error dari Microsoft
        2. Ambil + hapus flow dict dari Redis berdasarkan state
        3. Tukar code → id_token_claims via MSAL
        4. Return JSON dengan oid untuk verifikasi manual

    TODO Hari 5: ganti step 4 dengan:
        - Lookup user di DB by oid (auth/role_mapper.py)
        - Buat session di Redis (auth/session.py)
        - Set cookie sid pada response
        - Redirect ke frontend (http://localhost:5173/dashboard)
    """
    params = dict(request.query_params)

    # ── 1. Error dari Microsoft (user cancel, akun diblokir, dll) ─────────────
    if "error" in params:
        logger.warning(
            "Microsoft OAuth error: %s — %s",
            params.get("error"),
            params.get("error_description", ""),
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Login Microsoft gagal: {params['error']}",
        )

    # ── 2. Validasi state ada di query params ─────────────────────────────────
    state = params.get("state")
    if not state:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Parameter 'state' tidak ditemukan pada callback.",
        )
 
    stored_flow = await pop_oauth_flow(state)
    if stored_flow is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Login session tidak ditemukan atau sudah expired. Silakan ulangi login.",
        )

    # ── 3. Tukar code → id_token_claims ───────────────────────────────────────
    try:
        claims = await exchange_code_for_claims(stored_flow, params)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))
 
    oid: str | None = claims.get("oid")
    if not oid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="ID token tidak mengandung 'oid'. Hubungi administrator.",
        )

     # ── 4. Lookup user di DB → AuthUser (user_id + nama + UserScope) ──────────
    try:
        auth_user = await get_auth_user(oid)
    except AuthError as e:
        # AuthError adalah kondisi bisnis normal (user tidak aktif, tidak punya akses)
        # http_status sudah di-set di AuthError (403)
        raise HTTPException(status_code=e.http_status, detail=e.reason)
 
    # ── 5. Buat session di Redis ───────────────────────────────────────────────
    session_id = await create_session(auth_user.user_scope, auth_user.nama)
 
    # ── 6 & 7. Set cookie + redirect ke frontend ──────────────────────────────
    response = RedirectResponse(
        url=settings.FRONTEND_URL,
        status_code=status.HTTP_302_FOUND,
    )
    _set_session_cookie(response, session_id)
 
    logger.info(
        "Login sukses | user_id=%s | nama=%s | role=%s → redirect ke %s",
        auth_user.user_id,
        auth_user.nama,
        auth_user.user_scope.role.value,
        settings.FRONTEND_URL,
    )
    return response

@router.get("/me", summary="Info user yang sedang login")
async def me(request: Request):
    """
    Dipakai frontend untuk cek apakah user sudah login dan ambil info dasarnya.
 
    Biasanya dipanggil saat:
        - Halaman pertama kali dimuat (untuk cek auth state)
        - Setelah redirect dari callback (untuk dapat nama + role)
 
    Returns 401 jika tidak ada session aktif.
    """
    session_id = request.cookies.get(settings.SESSION_COOKIE_NAME)
    if not session_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Tidak ada session aktif. Silakan login.",
        )
 
    data = await get_session(session_id)
    if data is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired. Silakan login ulang.",
        )
 
    return {
        "user_id": data["user_id"],
        "nama": data["nama"],
        "role": data["active_role"]["role"],
        "available_roles": [r["role"] for r in data["available_roles"]],
    }

@router.post("/logout", summary="Logout — hapus session dan clear cookie")
async def logout(request: Request):
    """
    Hapus session dari Redis dan instruksikan browser untuk menghapus cookie.
 
    Silent jika tidak ada session (sudah expired sebelumnya) — tidak perlu error.
    """
    session_id = request.cookies.get(settings.SESSION_COOKIE_NAME)
 
    if session_id:
        await delete_session(session_id)
 
    response = JSONResponse({"status": "logged_out"})
    _clear_session_cookie(response)
    return response