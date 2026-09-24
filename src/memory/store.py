from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Protocol


class Memory(Protocol):
    async def remember(self, key: str, value: str) -> None: ...

    async def recall(self, key: str) -> list[str]: ...


class FileMemory:
    """Small persistent JSON memory implementation."""

    def __init__(self, path: str = "data/memory.json") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    async def remember(self, key: str, value: str) -> None:
        await asyncio.to_thread(self._remember_sync, key, value)

    async def recall(self, key: str) -> list[str]:
        return await asyncio.to_thread(self._recall_sync, key)

    def _load(self) -> dict[str, list[str]]:
        if not self.path.exists():
            return {}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return {
            str(key): [str(item) for item in values]
            for key, values in data.items()
            if isinstance(values, list)
        }

    def _remember_sync(self, key: str, value: str) -> None:
        data = self._load()
        data.setdefault(key, []).append(value)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary.replace(self.path)

    def _recall_sync(self, key: str) -> list[str]:
        return list(self._load().get(key, []))
