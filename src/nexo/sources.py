"""Per-turn web source provenance records."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True, slots=True)
class SourceRecord:
    source_id: str
    url: str
    title: str
    retrieval: str
    retrieved_at: str


class SourceLedger:
    def __init__(self, limit: int = 5) -> None:
        self.limit = max(1, min(limit, 20))
        self._records: list[SourceRecord] = []
        self._urls: set[str] = set()

    def add(self, url: str, *, title: str = "", retrieval: str = "search") -> SourceRecord | None:
        value = url.strip()
        if not value or value in self._urls or len(self._records) >= self.limit:
            return None
        record = SourceRecord(
            source_id=f"WEB-{len(self._records) + 1}",
            url=value,
            title=title.strip()[:300],
            retrieval=retrieval,
            retrieved_at=datetime.now(timezone.utc).isoformat(),
        )
        self._records.append(record)
        self._urls.add(value)
        return record

    @property
    def records(self) -> tuple[SourceRecord, ...]:
        return tuple(self._records)

    @property
    def urls(self) -> list[str]:
        return [item.url for item in self._records]

    def as_dicts(self) -> list[dict[str, Any]]:
        return [asdict(item) for item in self._records]
