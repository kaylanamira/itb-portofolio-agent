from __future__ import annotations

import re

INDONESIAN_STOPWORDS = frozenset({
    "apa", "yang", "dan", "di", "ke", "dari", "untuk", "dengan", "pada",
    "ini", "itu", "ada", "berapa", "bagaimana", "kenapa", "mengapa",
    "kelas", "mata", "kuliah", "mahasiswa", "dosen",
})

TOKEN_PATTERN = re.compile(r"[A-Za-z]{2,}\d{2,}|[A-Za-z]{3,}|\d{4}/\d{4}|\d+")


def extract_keywords(query: str) -> list[str]:
    tokens = TOKEN_PATTERN.findall(query)
    keywords: list[str] = []
    seen: set[str] = set()
    for token in tokens:
        normalized = token.strip().lower()
        if normalized in INDONESIAN_STOPWORDS or len(normalized) < 2:
            continue
        if normalized not in seen:
            seen.add(normalized)
            keywords.append(token.upper() if re.search(r"\d", token) else normalized)
    return keywords
