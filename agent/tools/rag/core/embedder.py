import asyncio
import logging
from typing import List, Union

from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type

from langchain_core.embeddings import Embeddings
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from core.config import settings

logger = logging.getLogger(__name__)

_E5_QUERY_PREFIX = "query: "
_E5_PASSAGE_PREFIX = "passage: "


class EmbedderFactory:
    @staticmethod
    def get_embedder() -> Embeddings:
        provider = settings.EMBEDDING_PROVIDER.lower()

        if provider == "local" or provider == "huggingface":
            from langchain_huggingface import HuggingFaceEmbeddings

            model = settings.EMBEDDING_MODEL or "intfloat/multilingual-e5-large"
            return HuggingFaceEmbeddings(
                model_name=model,
                model_kwargs={"device": "cpu"},
                encode_kwargs={"normalize_embeddings": True},
            )
        elif provider == "google":
            api_key = settings.GOOGLE_API_KEY
            model = settings.EMBEDDING_MODEL if settings.EMBEDDING_MODEL and "e5" not in settings.EMBEDDING_MODEL.lower() and "bge" not in settings.EMBEDDING_MODEL.lower() else "models/gemini-embedding-001"

            kwargs = {}
            if model == "models/gemini-embedding-001" or model == "models/text-embedding-004":
                kwargs["output_dimensionality"] = settings.EMBEDDING_DIMS

            return GoogleGenerativeAIEmbeddings(
                model=model,
                google_api_key=api_key,
                **kwargs
            )
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
def embed_query_text(text: str) -> List[float]:
    """Embeds a single search query. E5 convention: prefixed with 'query: '."""
    embedder = _get_instance()
    return embedder.embed_query(_E5_QUERY_PREFIX + text)


@retry(
    wait=wait_exponential(multiplier=1, min=2, max=20),
    stop=stop_after_attempt(5),
    retry=retry_if_exception_type(Exception),
    before_sleep=lambda retry_state: logger.warning(f"Embedding error: {retry_state.outcome.exception()}. Retrying in {retry_state.next_action.sleep}s...")
)
def embed_passage_texts(texts: List[str]) -> List[List[float]]:
    embedder = _get_instance()
    return embedder.embed_documents([_E5_PASSAGE_PREFIX + t for t in texts])


async def aembed_query_text(text: str) -> List[float]:
    return await asyncio.to_thread(embed_query_text, text)


async def aembed_passage_texts(texts: List[str]) -> List[List[float]]:
    return await asyncio.to_thread(embed_passage_texts, texts)


def embed_text(text: Union[str, List[str]]) -> Union[List[float], List[List[float]]]:
    """Deprecated. Currently using embed_query_text/embed_passage_texts (or their async variants)
    so the correct E5 query/passage prefix is applied.
    """
    logger.warning("embed_text() is deprecated; use embed_query_text/embed_passage_texts.")
    if isinstance(text, str):
        return embed_query_text(text)
    elif isinstance(text, list):
        return embed_passage_texts(text)
    else:
        raise ValueError("Input must be a string or a list of strings.")
