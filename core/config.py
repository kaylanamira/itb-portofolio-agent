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
    
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
