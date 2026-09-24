from collections.abc import Sequence
from typing import Protocol


class Memory(Protocol):
    async def remember(self, key: str, value: str) -> None: ...

    async def recall(self, key: str) -> list[str]: ...


class InMemoryMemory:
    def __init__(self) -> None:
        self._store: dict[str, list[str]] = {}

    async def remember(self, key: str, value: str) -> None:
        self._store.setdefault(key, []).append(value)

    async def recall(self, key: str) -> list[str]:
        return list(self._store.get(key, []))
