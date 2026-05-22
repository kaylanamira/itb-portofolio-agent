from __future__ import annotations

import logging
from functools import lru_cache
from typing import Optional

logger = logging.getLogger(__name__)

_MIN_LENGTH = 15

@lru_cache(maxsize=1)
def _get_detector():
    try:
        from lingua import Language, LanguageDetectorBuilder
        detector = (
            LanguageDetectorBuilder
            .from_languages(Language.INDONESIAN, Language.ENGLISH)
            .with_minimum_relative_distance(0.1)
            .build()
        )
        return detector, Language.INDONESIAN, Language.ENGLISH
    except ImportError:
        logger.warning(
            "lingua-language-detector not installed. "
            "All chunks will be tagged lang='id'. "
            "Install with: pip install lingua-language-detector"
        )
        return None, None, None

def detect_language(text: str) -> str:
    if not text or len(text.strip()) < _MIN_LENGTH:
        return "id"

    detector, INDONESIAN, ENGLISH = _get_detector()
    if detector is None:
        return "id"

    try:
        confidences = {
            lang: conf
            for lang, conf in detector.compute_language_confidence_values(text)
        }

        id_conf = confidences.get(INDONESIAN, 0.0)
        en_conf = confidences.get(ENGLISH, 0.0)

        if id_conf < 0.2 and en_conf < 0.2:
            return "id"

        if id_conf >= 0.35 and en_conf >= 0.35:
            return "mixed"

        return "en" if en_conf > id_conf else "id"

    except Exception as e:
        logger.debug(f"Language detection failed: {e}")
        return "id"


def pg_fts_config(lang: str) -> str:
    """
    Map a detected language code to the Postgres text search config name.
    'mixed' and anything unknown → 'simple' (language-agnostic stemming).
    """
    return {
        "id": "indonesian",
        "en": "english",
        "mixed": "simple",
    }.get(lang, "simple")