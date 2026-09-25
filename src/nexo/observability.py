"""Bounded request observability for NEXO.

Only aggregate counters and correlation IDs are retained; prompts and responses
are never stored by this module.
"""

from __future__ import annotations

import re
import time
import uuid
from collections import Counter
from dataclasses import dataclass, field
from typing import Any


_SAFE_ID = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


def normalize_request_id(value: str | None) -> str:
    candidate = (value or "").strip()
    if _SAFE_ID.fullmatch(candidate):
        return candidate
    return uuid.uuid4().hex


@dataclass(slots=True)
class RequestMetrics:
    max_paths: int = 64
    _counts: Counter[str] = field(default_factory=Counter)
    _latencies: dict[str, list[int]] = field(default_factory=dict)
    _started_at: float = field(default_factory=time.time)

    def record(self, method: str, path: str, status_code: int, latency_ms: int) -> None:
        key = f"{method.upper()} {path[:160]}"
        if key not in self._counts and len(self._counts) >= self.max_paths:
            key = "_other"
        outcome = "2xx" if 200 <= status_code < 300 else ("4xx" if status_code < 500 else "5xx")
        self._counts[f"{key} {outcome}"] += 1
        bucket = self._latencies.setdefault(key, [])
        if len(bucket) < 256:
            bucket.append(max(0, int(latency_ms)))
        else:
            bucket[len(bucket) % 256] = max(0, int(latency_ms))

    def snapshot(self) -> dict[str, Any]:
        latency_summary: dict[str, dict[str, int]] = {}
        for key, values in self._latencies.items():
            if not values:
                continue
            ordered = sorted(values)
            latency_summary[key] = {
                "count": len(values),
                "p50_ms": ordered[len(ordered) // 2],
                "p95_ms": ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))],
                "max_ms": ordered[-1],
            }
        return {
            "uptime_s": max(0, int(time.time() - self._started_at)),
            "total_requests": sum(self._counts.values()),
            "counts": dict(sorted(self._counts.items())),
            "latency": latency_summary,
        }
