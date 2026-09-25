"""Deterministic memory selection contracts independent of storage."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True, slots=True)
class MemoryHit:
    entry: Any
    score: int
    match: str


class MemoryEngine:
    """Rank already-retrieved memory without coupling ranking to Postgres."""

    @staticmethod
    def normalize(value: str) -> str:
        value = unicodedata.normalize("NFKD", value or "")
        return "".join(ch for ch in value if not unicodedata.combining(ch)).lower()

    @classmethod
    def tokens(cls, value: str) -> list[str]:
        stop = {"que", "para", "con", "por", "una", "las", "los", "del", "uno"}
        return [t for t in re.findall(r"[\w]{3,}", cls.normalize(value)) if t not in stop]

    @staticmethod
    def _recency_key(entry: Any) -> datetime:
        """Return a comparable UTC timestamp, treating malformed/missing values as oldest."""
        raw = str(getattr(entry, "created_at", "") or "").strip()
        if not raw:
            return datetime.min.replace(tzinfo=timezone.utc)
        try:
            value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return datetime.min.replace(tzinfo=timezone.utc)
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    @classmethod
    def select(cls, entries: list[Any], query: str, limit: int = 12) -> list[MemoryHit]:
        limit = max(1, min(limit, 40))
        tokens = cls.tokens(query)
        ranked: list[tuple[int, datetime, int, MemoryHit]] = []
        for index, entry in enumerate(entries):
            haystack = cls.normalize(" ".join(
                str(getattr(entry, name, "")) for name in (
                    "user_text", "assistant_text", "summary", "debate_topic",
                    "user_position", "tags", "central_arguments",
                )
            ))
            haystack_tokens = set(re.findall(r"[\\w]{3,}", haystack))
            score = sum(1 for token in tokens if token in haystack_tokens)
            if score:
                ranked.append(
                    (score, cls._recency_key(entry), index, MemoryHit(entry, score, "token_match"))
                )
        ranked.sort(key=lambda item: (item[0], item[1], item[2]), reverse=True)
        return [item[3] for item in ranked[:limit]]


def context_text(hit: MemoryHit, max_chars: int = 700) -> str:
    entry = hit.entry
    text = str(getattr(entry, "summary", "") or getattr(entry, "assistant_text", ""))
    return text[: max(1, max_chars)].strip()
