from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_groq import ChatGroq
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_anthropic import ChatAnthropic
from core.config import settings
import os

load_dotenv()
OPENROUTER_MODEL_ENVS: dict[str, tuple[str, ...]] = {
    "intent_classification": ("INTENT_MODEL", "INTENT_CLASSIFICATION_MODEL"),
    "query_rewriter": ("REWRITER_MODEL", "QUERY_REWRITER_MODEL"),
    "planning": ("PLANNING_MODEL",),
    "schema_linking": ("LINKING_MODEL", "SCHEMA_LINKING_MODEL"),
    "sql_generation": ("SQL_GEN_MODEL", "SQL_GENERATION_MODEL"),
    "answer_validation": ("VALIDATION_MODEL", "ANSWER_VALIDATION_MODEL"),
    "step_reasoning": ("REASONING_MODEL", "STEP_REASONING_MODEL"),
    "synthesis": ("SYNTHESIS_MODEL",),
    "chart_interpretation": ("CHART_INTERPRETATION_MODEL", "SYNTHESIS_MODEL"),
    "clarification": ("CLARIFICATION_MODEL",),
    "llm_evaluation": ("EVAL_MODEL", "LLM_EVALUATION_MODEL"),
    "rag_generation": ("RAG_GEN_MODEL",),
    "rag_faithfulness": ("RAG_FAITH_MODEL",),
    "rag_hyde": ("RAG_HYDE_MODEL",),
    "rag_entity_extraction": ("RAG_ENTITY_MODEL",),
}


def _default_provider() -> str:
    return (settings.HEAVY_LLM_PROVIDER or settings.LLM_PROVIDER).lower()


def _default_model(provider: str) -> str:
    if provider == "google":
        return os.getenv("GOOGLE_MODEL", settings.FAST_LLM_MODEL)

    explicit_heavy_model = os.getenv("HEAVY_LLM_MODEL")
    if explicit_heavy_model:
        return explicit_heavy_model

    if provider == "groq":
        return os.getenv("GROQ_MODEL", settings.HEAVY_LLM_MODEL)
    if provider == "openai":
        return os.getenv("OPENAI_MODEL", settings.HEAVY_LLM_MODEL)
    if provider == "anthropic":
        return os.getenv("ANTHROPIC_MODEL", settings.HEAVY_LLM_MODEL)
    if provider == "ollama":
        return os.getenv("OLLAMA_MODEL", settings.HEAVY_LLM_MODEL)
    if provider == "openrouter":
        return os.getenv("OPENROUTER_MODEL", settings.HEAVY_LLM_MODEL)

    return settings.HEAVY_LLM_MODEL


def _openrouter_model(task_type: str, default_model: str) -> str:
    env_names = OPENROUTER_MODEL_ENVS.get(task_type, ())
    for env_name in env_names:
        model_name = os.getenv(env_name)
        if model_name:
            return model_name
    return default_model


DEFAULT_PROVIDER = _default_provider()
DEFAULT_MODEL = _default_model(DEFAULT_PROVIDER)

TASK_MODEL_MAPPING: dict[str, dict[str, str]] = {
    task_type: {"provider": DEFAULT_PROVIDER, "model": DEFAULT_MODEL}
    for task_type in (
        "intent_classification",
        "query_rewriter",
        "answer_validation",
        "step_reasoning",
        "clarification",
        "synthesis",
        "chart_interpretation",
        "planning",
        "schema_linking",
        "sql_generation",
        "general",
        "llm_evaluation",
        "rag_hyde",
        "rag_entity_extraction",
    )
}
TASK_MODEL_MAPPING["llm_evaluation"] = {
    "provider": os.getenv("EVAL_PROVIDER", "google"),
    "model": os.getenv("EVAL_MODEL", os.getenv("GOOGLE_MODEL", "gemini-1.5-pro"))
}

TASK_MODEL_MAPPING["rag_generation"] = {
    "provider": os.getenv("RAG_GEN_PROVIDER", "google"),
    "model": os.getenv("RAG_GEN_MODEL", os.getenv("GOOGLE_MODEL", "gemini-2.5-flash")),
}
TASK_MODEL_MAPPING["rag_faithfulness"] = {
    "provider": os.getenv("RAG_FAITH_PROVIDER", "google"),
    "model": os.getenv("RAG_FAITH_MODEL", os.getenv("GOOGLE_MODEL", "gemini-2.5-flash")),
}


def get_llm(task_type: str = "general", force_json: bool = True):
    """Returns a LangChain Chat Model instance for the given task.

    Args:
        task_type: Key from TASK_MODEL_MAPPING.
        force_json: If True, requests JSON output format where supported.
    """
    mapping = TASK_MODEL_MAPPING.get(
        task_type,
        {"provider": DEFAULT_PROVIDER, "model": DEFAULT_MODEL},
    )
    provider = mapping["provider"].lower()
    model_name = mapping["model"]

    if provider == "openrouter":
        kwargs = {
            "api_key": settings.OPENROUTER_API_KEY,
            "base_url": "https://openrouter.ai/api/v1",
            "model": _openrouter_model(task_type, model_name),
            "temperature": 0.0,
            "max_retries": 3,
            "default_headers": {
                "HTTP-Referer": "https://github.com/kaylanamira/itb-portofolio",
                "X-Title": "ITB Academic Portfolio Agent",
            },
        }
        if force_json:
            kwargs["model_kwargs"] = {"response_format": {"type": "json_object"}}
        return ChatOpenAI(**kwargs)

    if provider == "google":
        kwargs = {
            "api_key": settings.GOOGLE_API_KEY,
            "model": model_name,
            "temperature": 0.0,
            "max_retries": 3,
        }
        if force_json:
            kwargs["response_mime_type"] = "application/json"
        return ChatGoogleGenerativeAI(**kwargs)

    if provider == "groq":
        kwargs = {
            "api_key": settings.GROQ_API_KEY,
            "model_name": model_name,
            "temperature": 0.0,
            "max_retries": 5,
        }
        if force_json:
            kwargs["model_kwargs"] = {"response_format": {"type": "json_object"}}
        return ChatGroq(**kwargs)

    if provider == "anthropic":
        return ChatAnthropic(
            api_key=settings.ANTHROPIC_API_KEY,
            model=model_name,
            temperature=0.0,
            max_retries=3,
        )

    if provider == "ollama":
        kwargs = {
            "base_url": settings.OLLAMA_BASE_URL,
            "model": model_name,
            "temperature": 0.0,
        }
        if force_json:
            kwargs["model_kwargs"] = {"response_format": {"type": "json_object"}}
        return ChatOpenAI(api_key="ollama", **kwargs)

    if provider == "openai":
        kwargs = {
            "api_key": settings.OPENAI_API_KEY,
            "model": model_name,
            "temperature": 0.0,
            "max_retries": 3,
        }
        if force_json:
            kwargs["model_kwargs"] = {"response_format": {"type": "json_object"}}
        return ChatOpenAI(**kwargs)

    raise ValueError(f"Unsupported LLM provider '{provider}' for task '{task_type}'.")
