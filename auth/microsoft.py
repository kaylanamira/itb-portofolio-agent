"""
auth/microsoft.py

Wrapper tipis di atas MSAL untuk OAuth 2.0 Authorization Code Flow + PKCE.

Tanggung jawab file ini HANYA:
    - Inisialisasi MSAL ConfidentialClientApplication (singleton)
    - Mulai login flow  → build_login_flow()
    - Selesaikan login flow → exchange_code_for_claims()

Tidak tahu tentang:
    - Redis / session  (auth/session.py)
    - Database / roles (auth/role_mapper.py — hari 4)
    - HTTP request     (api/routers/auth.py)
"""

import asyncio
import logging
from typing import Any

import msal

from core.config import settings

logger = logging.getLogger(__name__)

# ─── Singleton MSAL App ───────────────────────────────────────────────────────
# ConfidentialClientApplication tidak menyimpan state per-user,
# aman dipakai bersama di seluruh request.
_msal_app: msal.ConfidentialClientApplication | None = None


def _get_msal_app() -> msal.ConfidentialClientApplication:
    """Lazy-init singleton MSAL app. Error jelas jika .env belum diisi."""
    global _msal_app
    if _msal_app is not None:
        return _msal_app

    missing = [
        name for name, val in [
            ("MS365_CLIENT_ID",     settings.MS365_CLIENT_ID),
            ("MS365_CLIENT_SECRET", settings.MS365_CLIENT_SECRET),
            ("MS365_TENANT_ID",     settings.MS365_TENANT_ID),
        ] if not val
    ]
    if missing:
        raise RuntimeError(
            f"Microsoft SSO belum dikonfigurasi. "
            f"Variabel berikut kosong di .env: {', '.join(missing)}"
        )

    _msal_app = msal.ConfidentialClientApplication(
        client_id=settings.MS365_CLIENT_ID,
        client_credential=settings.MS365_CLIENT_SECRET,
        authority=f"https://login.microsoftonline.com/{settings.MS365_TENANT_ID}",
    )
    logger.info("MSAL app initialized (tenant: %s...)", settings.MS365_TENANT_ID[:8])
    return _msal_app


# ─── Public Functions ─────────────────────────────────────────────────────────

async def build_login_flow() -> dict[str, Any]:
    """
    Mulai OAuth 2.0 Authorization Code Flow dengan PKCE.

    Kembalikan flow dict dari MSAL yang berisi:
        auth_uri  → URL untuk redirect browser ke halaman login Microsoft
        state     → random string untuk CSRF protection (dipakai sebagai Redis key)
        code_verifier, nonce → dipakai MSAL saat exchange code nanti

    Flow dict ini wajib disimpan di Redis (session.store_oauth_flow)
    sebelum browser di-redirect.

    Raises:
        RuntimeError: jika MSAL gagal membuat flow (config salah, dll).
    """
    app = _get_msal_app()

    # MSAL adalah library sinkronus. asyncio.to_thread agar tidak
    # memblokir event loop FastAPI.
    flow: dict = await asyncio.to_thread(
        app.initiate_auth_code_flow,
        scopes=settings.MS365_SCOPES,
        redirect_uri=settings.MS365_REDIRECT_URI,
    )

    if "error" in flow:
        raise RuntimeError(f"MSAL gagal membuat login flow: {flow}")

    return flow


async def exchange_code_for_claims(
    stored_flow: dict[str, Any],
    callback_params: dict[str, str],
) -> dict[str, Any]:
    """
    Tukar authorization code dari Microsoft dengan ID token claims.

    Args:
        stored_flow:     Flow dict yang sebelumnya disimpan di Redis.
                         MSAL butuh ini untuk verifikasi state dan code_verifier (PKCE).
        callback_params: Semua query parameter dari URL callback Microsoft.
                         Minimal berisi: code, state.
                         MSAL akan memvalidasi state secara internal.

    Returns:
        id_token_claims (dict). Key yang kita butuhkan:
            oid                → Microsoft Object ID = users.user.ms365_id di DB
            preferred_username → UPN / email Microsoft (contoh: 13522xxx@mahasiswa.itb.ac.id)
            name               → nama display dari direktori Microsoft

    Raises:
        ValueError: jika exchange gagal (code expired, state mismatch, dll).
    """
    app = _get_msal_app()

    result: dict = await asyncio.to_thread(
        app.acquire_token_by_auth_code_flow,
        stored_flow,
        callback_params,
    )

    if "error" in result:
        desc = result.get("error_description", "tanpa deskripsi")
        logger.error("Token exchange gagal: %s — %s", result["error"], desc)
        raise ValueError(f"Token exchange gagal: {result['error']} — {desc}")

    claims: dict | None = result.get("id_token_claims")
    if not claims:
        raise ValueError("ID token tidak ditemukan dalam response Microsoft.")

    logger.info(
        "Token exchange sukses | oid=%s... | upn=%s",
        str(claims.get("oid", ""))[:8],
        claims.get("preferred_username", "?"),
    )
    return claims