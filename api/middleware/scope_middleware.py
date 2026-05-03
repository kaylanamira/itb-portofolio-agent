from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from core.scope import UserScope, UserRole
import uuid

class ScopeMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        role_str = request.headers.get("X-User-Role", "dosen")
        try:
            role = UserRole(role_str.lower())
        except ValueError:
            role = UserRole.DOSEN
            
        user_scope = UserScope(
            user_id=uuid.uuid4(),
            role=role,
            dosen_id=uuid.uuid4() if role == UserRole.DOSEN else None,
            prodi_id=uuid.uuid4() if role in (UserRole.KAPRODI, UserRole.JAJARAN_PRODI) else None,
            fakultas_id=uuid.uuid4() if role in (UserRole.DEKAN, UserRole.JAJARAN_DEKANAT) else None,
        )
        
        request.state.user_scope = user_scope
        response = await call_next(request)
        return response
