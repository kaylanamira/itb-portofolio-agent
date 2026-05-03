from fastapi import Request
from core.scope import UserScope

def get_user_scope(request: Request) -> UserScope:
    """Dependency to extract UserScope from request state."""
    return request.state.user_scope
