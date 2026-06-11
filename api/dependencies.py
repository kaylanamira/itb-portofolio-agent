from fastapi import HTTPException, Request, status
from core.scope import UserScope

def get_user_scope(request: Request) -> UserScope:
    """
    Require authenticated user. Raise 401 jika tidak ada session aktif.

    UserScope diisi oleh ScopeMiddleware dari session Redis.
    Dipakai sebagai: Depends(get_user_scope)
    """
     
    scope: UserScope | None = getattr(request.state, "user_scope", None)
    if scope is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Tidak terautentikasi. Silakan login terlebih dahulu.",
            headers={"WWW-Authenticate": "Cookie"},
        )
    return scope
