"""
api/routers/auth.py

HTTP layer untuk autentikasi Microsoft SSO dan manajemen session/role.

Tanggung jawab:
    - Definisi endpoint dan HTTP contract-nya
    - Baca query params / cookie dari request
    - Set cookie pada response
    - Orchestrasi: panggil modul auth.* dan kembalikan hasilnya

Tidak boleh berisi:
    - Logic MSAL langsung (→ auth/microsoft.py)
    - Logic Redis langsung (→ auth/session.py)
    - Logic DB / role mapping (→ auth/role_mapper.py)
"""

import logging

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel

from auth.microsoft import build_login_flow, exchange_code_for_claims
from auth.role_mapper import AuthError, get_auth_user
from auth.session import (
    create_session,
    delete_session,
    get_session,
    pop_oauth_flow,
    store_oauth_flow,
    switch_active_role,
)

from core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])


# ─── Request / Response Models ────────────────────────────────────────────────

class SwitchRoleRequest(BaseModel):
    """Body untuk endpoint PATCH /role."""
    user_role_id: int


# ─── Helpers ──────────────────────────────────────────────────────────────────

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


# ─── Endpoints ────────────────────────────────────────────────────────────────

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
        auth_user.user_scope.active_role.role.value,
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

    Response:
        user_id         : int
        nama            : str
        active_role     : dict  (role, user_role_id, scope info)
        available_roles : list[dict]
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
        "active_role": {
            "role": data["active_role"]["role"],
            "user_role_id": data["active_role"]["user_role_id"],
            "scope_label": data["active_role"].get("scope_label"),
        },
        "available_roles": [
            {
                "role": r["role"],
                "user_role_id": r["user_role_id"],
                "is_prime": r["is_prime"],
                "scope_label": r.get("scope_label"),
            }
            for r in data["available_roles"]
        ],
    }


@router.patch("/role", summary="Ganti role aktif untuk session ini")
async def switch_role(request: Request, body: SwitchRoleRequest):
    """
    Ganti active_role ke salah satu role yang dimiliki user.

    Body: { "user_role_id": <int> }

    Syarat:
        - Session harus aktif
        - user_role_id harus ada di available_roles session ini
          (validasi dilakukan server-side, tidak percaya input frontend)

    Gunakan GET /me sebelumnya untuk dapat daftar available_roles + user_role_id-nya.

    Response:
        active_role  : dict  { role, user_role_id }
        available_roles: list (sama seperti /me)

    Returns 401 jika session tidak aktif.
    Returns 403 jika user_role_id tidak ada di available_roles user ini.
    """
    session_id = request.cookies.get(settings.SESSION_COOKIE_NAME)
    if not session_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Tidak ada session aktif. Silakan login.",
        )

    ok = await switch_active_role(session_id, body.user_role_id)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Role tidak valid atau tidak dimiliki akun ini.",
        )

    data = await get_session(session_id)
    return {
        "active_role": {
            "role": data["active_role"]["role"],
            "user_role_id": data["active_role"]["user_role_id"],
            "scope_label": data["active_role"].get("scope_label"),
        },
        "available_roles": [
            {
                "role": r["role"],
                "user_role_id": r["user_role_id"],
                "is_prime": r["is_prime"],
                "scope_label": r.get("scope_label"),
            }
            for r in data["available_roles"]
        ],
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