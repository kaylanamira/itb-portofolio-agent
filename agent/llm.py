from langchain_groq import ChatGroq
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from core.config import settings

def get_llm(force_json: bool = True):
    """Get an LLM instance based on setting."""
    provider = settings.LLM_PROVIDER.lower()
    
    if provider == "google":
        kwargs = {
            "api_key": settings.GOOGLE_API_KEY,
            "model": settings.GOOGLE_MODEL,
            "temperature": 0.0,
            "max_retries": 3,
        }
        return ChatGoogleGenerativeAI(**kwargs)
        
    elif provider == "openai":
        kwargs = {
            "api_key": settings.OPENAI_API_KEY,
            "model": settings.OPENAI_MODEL,
            "temperature": 0.0,
            "max_retries": 3,
        }
        if force_json:
            kwargs["model_kwargs"] = {"response_format": {"type": "json_object"}}
        return ChatOpenAI(**kwargs)

    elif provider == "anthropic":
        kwargs = {
            "api_key": settings.ANTHROPIC_API_KEY,
            "model": settings.ANTHROPIC_MODEL,
            "temperature": 0.0,
            "max_retries": 3,
        }
        return ChatAnthropic(**kwargs)
        
    kwargs = {
        "api_key": settings.GROQ_API_KEY,
        "model_name": settings.GROQ_MODEL,
        "temperature": 0.0,
        "max_retries": 5,
    }
    if force_json:
        kwargs["model_kwargs"] = {"response_format": {"type": "json_object"}}
    return ChatGroq(**kwargs)
