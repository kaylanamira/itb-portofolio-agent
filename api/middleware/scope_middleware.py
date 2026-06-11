import logging

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from auth.session import get_session, session_to_user_scope
from core.config import settings

logger = logging.getLogger(__name__)

# def _int_header(request: Request, name: str) -> int | None:
#     """Parse an integer from an HTTP header, returning None if absent or invalid."""
#     val = request.headers.get(name)
#     if val is None:
#         return None
#     try:
#         return int(val)
#     except ValueError:
#         return None


# def _build_scope_from_headers(request: Request) -> UserScope:
#     """Build UserScope request headers.

#     Args:
#         request: The incoming FastAPI request.

#     Returns:
#         UserScope with active_role populated from headers.

#     TODO: Replace this with JWT decoding when integrating with the SSO.
#           The JWT payload should contain user_id, role, and scope context fields.
#           Factor that logic into a separate _build_scope_from_jwt(token: str) function.
#     """
#     role_str = request.headers.get("X-User-Role", "direktorat")
#     try:
#         role = UserRole(role_str.lower())
#     except ValueError:
#         role = UserRole.DOSEN

#     user_id = _int_header(request, "X-User-Id") or 100
#     dosen_id = _int_header(request, "X-Dosen-Id")
#     no_ps = _int_header(request, "X-No-Ps")
#     kd_fak = request.headers.get("X-Kd-Fak")

#     if role == UserRole.DOSEN and dosen_id is None:
#         dosen_id = 1
#     elif role in (UserRole.KAPRODI, UserRole.JAJARAN_PRODI) and no_ps is None:
#         no_ps = 135
#     elif role in (UserRole.DEKAN, UserRole.JAJARAN_DEKANAT) and kd_fak is None:
#         kd_fak = "STEI"

#     active_role = ScopeEntry(
#         user_role_id=1,
#         role=role,
#         dosen_id=dosen_id,
#         no_ps=no_ps,
#         kd_fak=kd_fak,
#         is_prime=True,
#     )
#     return UserScope(
#         user_id=user_id,
#         active_role=active_role,
#         available_roles=[active_role],
#     )


class ScopeMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # request.state.user_scope = _build_scope_from_headers(request)
        # return await call_next(request)

        session_id: str | None = request.cookies.get(settings.SESSION_COOKIE_NAME)

        if session_id:
            session_data = await get_session(session_id)
 
            if session_data is not None:
                try:
                    request.state.user_scope = session_to_user_scope(session_data)
                    request.state.session_id = session_id
                except Exception:
                    # Session data rusak / tidak bisa di-deserialize
                    # (misal: format session berubah setelah deploy baru)
                    logger.exception(
                        "Gagal deserialize session data untuk session_id=%s...",
                        session_id[:8],
                    )
                    request.state.user_scope = None
                    request.state.session_id = None
            else:
                # Cookie ada tapi session sudah expired di Redis
                request.state.user_scope = None
                request.state.session_id = None
        else:
            # Tidak ada cookie sama sekali
            request.state.user_scope = None
            request.state.session_id = None
 
        return await call_next(request)
