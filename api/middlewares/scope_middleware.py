import logging

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from auth.session import get_session, session_to_user_scope
from core.config import settings
from core.scope import UserRole, ScopeEntry, UserScope

logger = logging.getLogger(__name__)
class ScopeMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        session_id: str | None = request.cookies.get(settings.SESSION_COOKIE_NAME)

        if session_id:
            session_data = await get_session(session_id)
 
            if session_data is not None:
                try:
                    request.state.user_scope = session_to_user_scope(session_data)
                    request.state.session_id = session_id
                except Exception:
                    logger.exception(
                        "Gagal deserialize session data untuk session_id=%s...",
                        session_id[:8],
                    )
                    request.state.user_scope = None
                    request.state.session_id = None
            else:
                request.state.user_scope = None
                request.state.session_id = None
        else:
            request.state.user_scope = None
            request.state.session_id = None
 
        return await call_next(request)
