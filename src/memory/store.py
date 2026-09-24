"""Persistent short-term and long-term memory for C-33."""

from __future__ import annotations

import asyncio
import json
import re
import unicodedata
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path


@dataclass(slots=True)
class MemoryEntry:
    """Single persisted user/assistant interaction."""

    id: str
    created_at: str
    user_text: str
    assistant_text: str
    summary: str
    tags: list[str] = field(default_factory=list)
    debate_topic: str = ""
    user_position: str = ""
    central_arguments: list[str] = field(default_factory=list)


class MemoryStore:
    """JSON-backed memory with asynchronous short- and long-term retrieval."""

    def __init__(
        self,
        path: str = "data/memory.json",
        *,
        short_term_limit: int = 8,
        long_term_limit: int = 12,
    ) -> None:
        if short_term_limit < 1 or long_term_limit < 1:
            raise ValueError("Memory limits must be >= 1")
        self.path = Path(path)
        self.short_term_limit = short_term_limit
        self.long_term_limit = long_term_limit
        self._lock = asyncio.Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)

    async def save(
        self,
        user_text: str,
        assistant_text: str,
        *,
        summary: str | None = None,
        tags: list[str] | None = None,
        debate_topic: str = "",
        user_position: str = "",
        central_arguments: list[str] | None = None,
    ) -> MemoryEntry:
        """Save an interaction and return the persisted entry."""
        user_text = user_text.strip()
        assistant_text = assistant_text.strip()
        if not user_text:
            raise ValueError("user_text cannot be empty")

        entry = MemoryEntry(
            id=uuid.uuid4().hex,
            created_at=datetime.now(timezone.utc).isoformat(),
            user_text=user_text,
            assistant_text=assistant_text,
            summary=(summary or assistant_text[:240]).strip(),
            tags=sorted({tag.strip().lower() for tag in (tags or []) if tag.strip()}),
            debate_topic=debate_topic.strip(),
            user_position=user_position.strip(),
            central_arguments=[
                item.strip()
                for item in (central_arguments or [])
                if item.strip()
            ],
        )
        async with self._lock:
            entries = await asyncio.to_thread(self._load_sync)
            entries.append(entry)
            await asyncio.to_thread(self._write_sync, entries)
        return entry

    async def learn(
        self,
        *,
        topic: str,
        knowledge: str,
        sources: list[str] | None = None,
    ) -> MemoryEntry:
        """Persist useful new knowledge for future retrieval."""
        topic = topic.strip()
        knowledge = knowledge.strip()
        if not topic or not knowledge:
            raise ValueError("topic and knowledge cannot be empty")

        source_tags = [
            f"source:{item}"
            for item in (sources or [])
            if item.strip()
        ]
        return await self.save(
            f"NEXO learning: {topic[:180]}",
            knowledge,
            summary=knowledge[:240],
            tags=["nexo", "learned", "knowledge", *source_tags],
            debate_topic=topic[:180],
            user_position="acquired during interaction",
            central_arguments=[knowledge[:700]],
        )

    async def search_context(
        self,
        query: str,
        limit: int | None = None,
    ) -> list[MemoryEntry]:
        """Return recent and semantically relevant local memories for a query."""
        limit = limit or self.short_term_limit + self.long_term_limit
        if limit < 1:
            raise ValueError("limit must be >= 1")

        async with self._lock:
            entries = await asyncio.to_thread(self._load_sync)

        if not entries:
            return []

        recent = list(reversed(entries[-self.short_term_limit :]))
        recent_ids = {entry.id for entry in recent}
        tokens = self._tokens(query)

        scored: list[tuple[int, int, MemoryEntry]] = []
        for index, entry in enumerate(entries):
            if entry.id in recent_ids:
                continue
            haystack = self._normalize(
                " ".join(
                    [
                        entry.user_text,
                        entry.assistant_text,
                        entry.summary,
                        entry.debate_topic,
                        entry.user_position,
                        *entry.central_arguments,
                        *entry.tags,
                    ]
                )
            )
            score = sum(1 for token in tokens if token in haystack)
            if score > 0:
                scored.append((score, index, entry))

        scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
        long_term = [item[2] for item in scored[: self.long_term_limit]]
        return (recent + long_term)[:limit]

    async def clear_history(self) -> None:
        """Delete all persisted interactions while keeping the storage directory."""
        async with self._lock:
            await asyncio.to_thread(self._write_sync, [])

    async def count(self) -> int:
        """Return the number of persisted memory entries."""
        async with self._lock:
            entries = await asyncio.to_thread(self._load_sync)
        return len(entries)

    def _load_sync(self) -> list[MemoryEntry]:
        """Read and validate the JSON memory file in a worker thread."""
        if not self.path.exists():
            return []
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        if not isinstance(raw, list):
            return []

        entries: list[MemoryEntry] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            try:
                entries.append(
                    MemoryEntry(
                        id=str(item["id"]),
                        created_at=str(item["created_at"]),
                        user_text=str(item["user_text"]),
                        assistant_text=str(item["assistant_text"]),
                        summary=str(item.get("summary", "")),
                        tags=[str(tag) for tag in item.get("tags", [])],
                        debate_topic=str(item.get("debate_topic", "")),
                        user_position=str(item.get("user_position", "")),
                        central_arguments=[
                            str(value) for value in item.get("central_arguments", [])
                        ],
                    )
                )
            except (KeyError, TypeError, ValueError):
                continue
        return entries

    def _write_sync(self, entries: list[MemoryEntry]) -> None:
        """Atomically write all memory entries to disk."""
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        payload = [asdict(entry) for entry in entries]
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary.replace(self.path)

    @staticmethod
    def _normalize(value: str) -> str:
        """Normalize text to make lightweight matching accent- and case-insensitive."""
        normalized = unicodedata.normalize("NFKD", value)
        without_marks = "".join(
            char for char in normalized if not unicodedata.combining(char)
        )
        return without_marks.lower()

    @classmethod
    def _tokens(cls, value: str) -> list[str]:
        """Extract useful query tokens for local relevance scoring."""
        normalized = cls._normalize(value)
        stopwords = {"que", "para", "con", "por", "una", "las", "los", "del"}
        return [
            token
            for token in re.findall(r"[\w]{3,}", normalized)
            if token not in stopwords
        ]
