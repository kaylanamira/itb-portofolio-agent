from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from contextlib import asynccontextmanager
from core.database import init_db_pool, close_db_pool
from api.middleware.scope_middleware import ScopeMiddleware
from api.routers import chat
from api.limiter import limiter
from slowapi.errors import RateLimitExceeded
from slowapi import _rate_limit_exceeded_handler

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle application startup and shutdown events."""
    await init_db_pool()
    yield
    await close_db_pool()

app = FastAPI(title="ITB Portfolio Analytics", lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(ScopeMiddleware)
app.include_router(chat.router)

@app.get("/")
async def root():
    return RedirectResponse(url="/docs")

@app.get("/health")
async def health_check():
    return {"status": "ok"}
