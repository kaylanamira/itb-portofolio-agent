from langchain_groq import ChatGroq
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from core.config import settings
from dotenv import load_dotenv
load_dotenv()

def get_llm(task_type: str = "general", force_json: bool = True):
    """Get an LLM instance based on setting and task_type."""
    # if task_type == "sql_generation":
    if True:
        provider = getattr(settings, "HEAVY_LLM_PROVIDER", settings.LLM_PROVIDER).lower()
        model_name = getattr(settings, "HEAVY_LLM_MODEL", getattr(settings, "FAST_LLM_MODEL", ""))
    else:
        provider = settings.LLM_PROVIDER.lower()
        model_name = getattr(settings, "FAST_LLM_MODEL", "")
    
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
        
    kwargs = {
        "api_key": settings.GROQ_API_KEY,
        "model_name": model_name,
        "temperature": 0.0,
        "max_retries": 5,
    }
    if force_json:
        kwargs["model_kwargs"] = {"response_format": {"type": "json_object"}}
    return ChatGroq(**kwargs)
