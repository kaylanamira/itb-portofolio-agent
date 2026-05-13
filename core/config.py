import os
from dotenv import load_dotenv
load_dotenv() 

from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    PROJECT_NAME: str = "ITB Academic Portfolio Analytics"
    VERSION: str = "0.1.0"

    # DB
    DATABASE_URL: str = os.getenv("DATABASE_URL")
    
    # LLM Routing
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "google")
    FAST_LLM_MODEL: str = os.getenv("FAST_LLM_MODEL", "gemini-2.5-flash")
    
    HEAVY_LLM_PROVIDER: str = os.getenv("HEAVY_LLM_PROVIDER", "groq")
    HEAVY_LLM_MODEL: str = os.getenv("HEAVY_LLM_MODEL", "llama-3.3-70b-versatile")
    
    # API Keys
    GROQ_API_KEY: str | None = os.getenv("GROQ_API_KEY")
    GOOGLE_API_KEY: str | None = os.getenv("GOOGLE_API_KEY")
    OPENAI_API_KEY: str | None = os.getenv("OPENAI_API_KEY")
    ANTHROPIC_API_KEY: str | None = os.getenv("ANTHROPIC_API_KEY")
    OPENROUTER_API_KEY: str | None = os.getenv("OPENROUTER_API_KEY")
    
    # Agent
    MAX_SQL_ATTEMPTS: int = 3
    
    # Retrieval
    RAG_RRF_K: int = 60
    RAG_TOP_K_AFTER_RRF: int = 50
    RAG_TOP_K_FINAL: int = 10
    RAG_MMR_LAMBDA: float = 0.7
    RAG_MMR_ENABLED_SOURCES: list[str] = ["komentar_mahasiswa"]
    RAG_PARENT_EXPAND_THRESHOLD: float = 0.70

    # CRAG
    CRAG_CONFIDENCE_ACCEPT: float = 0.70
    CRAG_CONFIDENCE_REFINE: float = 0.40
    RAG_MAX_ATTEMPTS: int = 2

    # Faithfulness
    FAITH_ACCEPT: float = 0.85
    FAITH_REVISE: float = 0.60
    FAITH_DISCLAIMER: str = "Ringkasan ini berdasarkan data portofolio yang tersedia dan mungkin tidak mencerminkan semua faktor."

    # Chunking
    CHUNK_TOKEN_MIN: int = 10
    CHUNK_TOKEN_MAX: int = 600
    CHUNK_PARENT_MAX_CHUNKS: int = 20

    # Embedding
    EMBEDDING_MODEL: str = "BAAI/bge-m3"
    EMBEDDING_DIMS: int = 1024
    EMBEDDING_API_URL: str | None = os.getenv("EMBEDDING_API_URL")
    EMBEDDING_API_KEY: str | None = os.getenv("EMBEDDING_API_KEY")
    EMBEDDING_TIMEOUT_SECONDS: float = 30.0

    # Cache & Redis
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    CACHE_SQL_TTL_SECONDS: int = 300
    CACHE_RAG_SESSION_TTL_SECONDS: int = 3600
    CACHE_RAG_SEMANTIC_THRESHOLD: float = 0.95
    CACHE_RAG_SEMANTIC_INDEX_SIZE: int = 25

    # Memory
    MEMORY_SHORT_TERM_TURNS: int = 10
    MEMORY_SESSION_TTL_SECONDS: int = 1800
    MEMORY_LONG_TERM_DAYS: int = 90
    MEMORY_SUMMARY_MAX_WORDS: int = 50

    # Content filter
    CONTENT_FILTER_ENABLED: bool = True

    # Dashboard job
    ISSUE_CLUSTER_K: int = 10
    ISSUE_TOP_N: int = 5

    # Rate Limits
    RATE_LIMIT_DEFAULT: list[str] = ["100/minute"]
    RATE_LIMIT_ENDPOINTS: dict[str, list[str]] = {
        "chat_stream": ["10/minute"],
        "chat": ["20/minute"]
    }
    
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
