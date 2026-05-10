from __future__ import annotations

import re
from typing import Literal

ContentFilterResult = Literal["safe", "prompt_injection", "pii", "sql_fragment"]

PROMPT_INJECTION_PATTERNS = [
    r"\bignore\s+(all\s+)?(previous|prior|above)\s+instructions\b",
    r"\babaikan\s+(semua\s+)?instruksi\b",
    r"\byou\s+are\s+now\b",
    r"\bsekarang\s+kamu\s+adalah\b",
    r"\bact\s+as\b",
    r"\bberperan\s+sebagai\b",
    r"\bDAN\b",
]

SQL_FRAGMENT_PATTERNS = [
    r";\s*\S",
    r"--",
    r"/\*",
    r"\b(drop|delete|insert|update|alter|truncate|create)\b",
]

PII_PATTERNS = [
    r"\b(?:\d[ -]*?){13,16}\b",
    r"\b\d{8,10}\b",
    r"\b\d{18}\b",
]


def filter_content(query: str) -> ContentFilterResult:
    for pattern in PROMPT_INJECTION_PATTERNS:
        if re.search(pattern, query, re.IGNORECASE):
            return "prompt_injection"
    for pattern in SQL_FRAGMENT_PATTERNS:
        if re.search(pattern, query, re.IGNORECASE):
            return "sql_fragment"
    for pattern in PII_PATTERNS:
        if re.search(pattern, query):
            return "pii"
    return "safe"
