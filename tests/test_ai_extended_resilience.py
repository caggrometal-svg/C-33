from __future__ import annotations

import asyncio
import json
import sys
from types import SimpleNamespace

import httpx

sys.path.insert(0, "src")

from resilience.providers import DeadlineBudget, GenerationFailure, ProviderCascade, ProviderSpec


class AlwaysDownTransport(httpx.AsyncBaseTransport):
    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, request=request, json={"error": "forced_all_providers_down"})


class StreamFailoverTransport(httpx.AsyncBaseTransport):
    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        if request.url.host == "primary.test":
            return httpx.Response(503, request=request, json={"error": "forced_stream_primary_down"})
        body = (
            b'data: {"choices":[{"delta":{"content":"C33_STREAM_FAILOVER_OK"}}]}\n\n'
            b'data: [DONE]\n\n'
        )
        return httpx.Response(200, request=request, headers={"content-type": "text/event-stream"}, content=body)


class NoopState:
    async def circuit_before_call(self, provider_id: str):
        return SimpleNamespace(allowed=True, cooldown_ms=0)

    async def circuit_success(self, provider_id: str, **kwargs):
        return None

    async def circuit_failure(self, provider_id: str, **kwargs):
        return None


def build_cascade(transport: httpx.AsyncBaseTransport) -> ProviderCascade:
    specs = [
        ProviderSpec("primary", "https://primary.test/v1", "free-primary", None, "domain-a", 5000),
        ProviderSpec("backup", "https://backup.test/v1", "free-backup", None, "domain-b", 5000),
        ProviderSpec("last", "https://last.test/v1", "free-last", None, "domain-c", 5000),
    ]
    return ProviderCascade(NoopState(), specs, ["primary", "backup", "last"], transport=transport)


async def test_all_providers_down() -> None:
    cascade = build_cascade(AlwaysDownTransport())
    try:
        await cascade.complete(
            [{"role": "user", "content": "ALL-DOWN"}],
            DeadlineBudget(8000),
        )
    except GenerationFailure as exc:
        assert exc.http_status == 502, exc
        assert exc.reason == "providers_exhausted", exc
        assert len(exc.attempts) == 3, exc
        assert all(item["reason"] == "provider_5xx" for item in exc.attempts), exc
        print({
            "status": "PASS",
            "test": "6_all_providers_down",
            "attempts": len(exc.attempts),
            "local_fallback": False,
            "final_reason": exc.reason,
        })
        return
    raise AssertionError("all providers down unexpectedly succeeded")


async def test_rate_limit() -> None:
    import api

    api._rate_limit_buckets.clear()

    class Client:
        host = "203.0.113.33"

    request = SimpleNamespace(client=Client())
    lock = asyncio.Lock()
    async def one() -> bool:
        try:
            await api._enforce_rate_limit(request, "generation-test", 30)
            return True
        except Exception as exc:
            if getattr(exc, "status_code", None) == 429:
                assert getattr(exc, "headers", {}).get("Retry-After"), exc
                return False
            raise

    # Concurrent callers must be serialized by the limiter lock.
    results = await asyncio.gather(*(one() for _ in range(31)))
    assert sum(results) == 30, results
    assert results.count(False) == 1, results
    print({
        "status": "PASS",
        "test": "8_rate_limit_concurrency",
        "requests": 31,
        "accepted": 30,
        "rejected_429": 1,
    })


async def test_stream_failover() -> None:
    cascade = build_cascade(StreamFailoverTransport())
    pieces: list[str] = []
    final_meta = None
    async for piece, meta in cascade.stream(
        [{"role": "user", "content": "STREAM-FAILOVER"}],
        DeadlineBudget(8000),
        preferred_provider="primary",
    ):
        pieces.append(piece)
        final_meta = meta

    assert "".join(pieces) == "C33_STREAM_FAILOVER_OK", pieces
    assert final_meta is not None
    assert final_meta.provider_used == "backup", final_meta
    assert final_meta.failover_triggered is True, final_meta
    assert final_meta.attempts >= 2, final_meta
    print({
        "status": "PASS",
        "test": "9_stream_failover",
        "provider_used": final_meta.provider_used,
        "attempts": final_meta.attempts,
        "failover_triggered": final_meta.failover_triggered,
    })


async def main() -> None:
    await test_all_providers_down()
    await test_rate_limit()
    await test_stream_failover()
    print({
        "status": "PASS",
        "gate": "C33_AI_EXTENDED_RESILIENCE_CORE",
        "deterministic_tests": 3,
        "result": "GREEN",
    })


if __name__ == "__main__":
    asyncio.run(main())
