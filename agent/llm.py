from langchain_openai import ChatOpenAI
from langchain_groq import ChatGroq
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_anthropic import ChatAnthropic
from core.config import settings
from dotenv import load_dotenv
import os

load_dotenv()

TASK_MODEL_MAPPING = {
    "intent_classification": os.getenv("INTENT_MODEL", "nvidia/nemotron-3-super-120b-a12b:free"),
    "query_rewriter": os.getenv("REWRITER_MODEL", "nvidia/nemotron-3-super-120b-a12b:free"),
    "planning": os.getenv("PLANNING_MODEL", "openai/gpt-oss-120b:free"),
    "schema_linking": os.getenv("LINKING_MODEL", "openai/gpt-oss-120b:free"),
    "sql_generation": os.getenv("SQL_GEN_MODEL", "openai/gpt-oss-120b:free"),
    "answer_validation": os.getenv("VALIDATION_MODEL", "nvidia/nemotron-3-super-120b-a12b:free"),
    "step_reasoning": os.getenv("REASONING_MODEL", "nvidia/nemotron-3-super-120b-a12b:free"), 
    "synthesis": os.getenv("SYNTHESIS_MODEL", "nvidia/nemotron-3-super-120b-a12b:free"),
    "clarification": os.getenv("CLARIFICATION_MODEL", "nvidia/nemotron-3-super-120b-a12b:free"),
    "general": "nvidia/nemotron-3-super-120b-a12b:free"
}

def get_llm(task_type: str = "general", force_json: bool = True):
    """
    Retrieves a LangChain Chat Model instance.
    If settings.OPENROUTER_API_KEY is defined, routes the task to a specific OpenRouter model
    (utilizing free/cost-effective models for simpler tasks and high-reasoning models for SQL/Planning).
    Otherwise, falls back to legacy provider configuration.
    """
    if settings.OPENROUTER_API_KEY:
        model_name = TASK_MODEL_MAPPING.get(task_type, TASK_MODEL_MAPPING["general"])
        kwargs = {
            "api_key": settings.OPENROUTER_API_KEY,
            "base_url": "https://openrouter.ai/api/v1",
            "model": model_name,
            "temperature": 0.0,
            "max_retries": 3,
            "default_headers": {
                "HTTP-Referer": "https://github.com/kaylanamira/itb-portofolio",
                "X-Title": "ITB Academic Portfolio Agent"
            }
        }
        if force_json:
            kwargs["model_kwargs"] = {"response_format": {"type": "json_object"}}
        return ChatOpenAI(**kwargs)

    provider = getattr(settings, "HEAVY_LLM_PROVIDER", settings.LLM_PROVIDER).lower()
    model_name = getattr(settings, "HEAVY_LLM_MODEL", getattr(settings, "FAST_LLM_MODEL", ""))

    if provider == "google":
        kwargs = {
            "api_key": settings.GOOGLE_API_KEY,
            "model": model_name,
            "temperature": 0.0,
            "max_retries": 3,
        }
        return ChatGoogleGenerativeAI(**kwargs)
        
    elif provider == "openai":
        kwargs = {
            "api_key": settings.OPENAI_API_KEY,
            "model": model_name,
            "temperature": 0.0,
            "max_retries": 3,
        }
        if force_json:
            kwargs["model_kwargs"] = {"response_format": {"type": "json_object"}}
        return ChatOpenAI(**kwargs)

    elif provider == "anthropic":
        kwargs = {
            "api_key": settings.ANTHROPIC_API_KEY,
            "model": model_name,
            "temperature": 0.0,
            "max_retries": 3,
        }
        return ChatAnthropic(**kwargs)

    elif provider == "ollama":
        # Local Ollama — OpenAI-compatible, no API key needed.
        # Run: ollama pull qwen2.5-coder:7b && ollama serve
        kwargs = {
            "base_url": settings.OLLAMA_BASE_URL,
            "model": model_name,
            "temperature": 0.0,
        }
        if force_json:
            kwargs["model_kwargs"] = {"response_format": {"type": "json_object"}}
        return ChatOpenAI(api_key="ollama", **kwargs)
        
    kwargs = {
        "api_key": settings.GROQ_API_KEY,
        "model_name": model_name,
        "temperature": 0.0,
        "max_retries": 5,
    }
    if force_json:
        kwargs["model_kwargs"] = {"response_format": {"type": "json_object"}}
    return ChatGroq(**kwargs)
