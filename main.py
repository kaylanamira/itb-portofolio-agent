from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse

from contextlib import asynccontextmanager
import logging
import os

from core.database import init_db_pool, close_db_pool
from core.redis_client import close_redis, init_redis

from api.middlewares.scope_middleware import ScopeMiddleware
from api.routers import chat
from api.routers import auth as auth_router 
from api.routers import dashboard_akademik  
from api.limiter import limiter

from slowapi.errors import RateLimitExceeded
from slowapi import _rate_limit_exceeded_handler

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle application startup and shutdown events."""
    await init_db_pool()
    await init_redis()
    yield
    await close_redis()
    await close_db_pool()

app = FastAPI(title="ITB Analytics", lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error on %s %s: %s", request.method, request.url.path, exc)
    return JSONResponse(
        status_code=500,
        content={"detail": "Terjadi kesalahan internal pada server."},
    )

# CORS
_raw_origins = os.getenv("ALLOWED_ORIGINS")
ALLOWED_ORIGINS = [o.strip() for o in _raw_origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)

app.add_middleware(ScopeMiddleware)

# Router
app.include_router(chat.router) # nanti tambahin (..., prefix="/api")
app.include_router(auth_router.router)
app.include_router(dashboard_akademik.router)

@app.get("/")
async def root():
    return RedirectResponse(url="/docs")

@app.get("/health")
async def health_check():
    return {"status": "ok"}
