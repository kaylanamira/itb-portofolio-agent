import os
import logging
from typing import List, Union
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type

from langchain_core.embeddings import Embeddings
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from core.config import settings

logger = logging.getLogger(__name__)

class EmbedderFactory:
    @staticmethod
    def get_embedder() -> Embeddings:
        provider = settings.LLM_PROVIDER.lower()
        
        if provider == "google":
            api_key = settings.GOOGLE_API_KEY
            model = settings.EMBEDDING_MODEL if settings.EMBEDDING_MODEL and "bge" not in settings.EMBEDDING_MODEL.lower() else "models/gemini-embedding-001"
            
            # Additional kwargs to support dimensionality reduction
            kwargs = {}
            if model == "models/gemini-embedding-001" or model == "models/text-embedding-004":
                kwargs["output_dimensionality"] = 768
                
            return GoogleGenerativeAIEmbeddings(
                model=model,
                google_api_key=api_key,
                **kwargs
            )
        # elif provider == "local" or provider == "huggingface":
        #     from langchain_huggingface import HuggingFaceEmbeddings
        #     model = settings.EMBEDDING_MODEL if settings.EMBEDDING_MODEL else "BAAI/bge-m3"
        #     return HuggingFaceEmbeddings(
        #         model_name=model,
        #         model_kwargs={'device': 'cpu'},
        #         encode_kwargs={'normalize_embeddings': True}
        #     )
        else:
            raise ValueError(f"Unsupported embedding provider: {provider}")

_embedder_instance = None

def _get_instance() -> Embeddings:
    global _embedder_instance
    if _embedder_instance is None:
        _embedder_instance = EmbedderFactory.get_embedder()
    return _embedder_instance

@retry(
    wait=wait_exponential(multiplier=1, min=2, max=20),
    stop=stop_after_attempt(5),
    retry=retry_if_exception_type(Exception),
    before_sleep=lambda retry_state: logger.warning(f"Embedding error: {retry_state.outcome.exception()}. Retrying in {retry_state.next_action.sleep}s...")
)
def embed_text(text: Union[str, List[str]]) -> Union[List[float], List[List[float]]]:
    embedder = _get_instance()
    if isinstance(text, str):
        return embedder.embed_query(text)
    elif isinstance(text, list):
        return embedder.embed_documents(text)
    else:
        raise ValueError("Input must be a string or a list of strings.")
