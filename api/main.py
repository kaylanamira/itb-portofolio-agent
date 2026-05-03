from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from contextlib import asynccontextmanager
from core.database import init_db_pool, close_db_pool
from api.middleware.scope_middleware import ScopeMiddleware
from api.routers import chat

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db_pool()
    yield
    await close_db_pool()

app = FastAPI(title="ITB Portfolio Analytics", lifespan=lifespan)

app.add_middleware(ScopeMiddleware)
app.include_router(chat.router)

@app.get("/")
async def root():
    return RedirectResponse(url="/docs")

@app.get("/health")
async def health_check():
    return {"status": "ok"}
