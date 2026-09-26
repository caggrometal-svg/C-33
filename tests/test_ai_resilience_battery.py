from __future__ import annotations

import asyncio
import statistics
import sys
import time
from types import SimpleNamespace

import httpx

sys.path.insert(0, "src")
from resilience.providers import DeadlineBudget, ProviderCascade, ProviderSpec


class CircuitState:
    def __init__(self) -> None:
        self.open_until: dict[str, float] = {}

    async def circuit_before_call(self, provider_id: str):
        remaining = max(0.0, self.open_until.get(provider_id, 0.0) - time.monotonic())
        if remaining > 0:
            return SimpleNamespace(allowed=False, cooldown_ms=int(remaining * 1000))
        return SimpleNamespace(allowed=True, cooldown_ms=0)

    async def circuit_success(self, provider_id: str, **kwargs):
        self.open_until.pop(provider_id, None)

    async def circuit_failure(self, provider_id: str, cooldown_ms: int = 0, **kwargs):
        # Short test cooldown so recovery can be proven without waiting 30s.
        self.open_until[provider_id] = time.monotonic() + min(max(cooldown_ms, 0), 1000) / 1000


class ScenarioTransport(httpx.AsyncBaseTransport):
    def __init__(self) -> None:
        self.mode = "healthy"
        self.primary_fail = False
        self.primary_delay = 0.0

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        host = request.url.host
        payload = {}
        try:
            payload = request.content and __import__("json").loads(request.content.decode())
        except Exception:
            pass
        prompt = ""
        try:
            prompt = str(payload["messages"][0]["content"])
        except Exception:
            pass

        if host == "primary.test":
            if self.primary_fail:
                return httpx.Response(503, request=request, json={"error": "forced_primary_outage"})
            if self.primary_delay:
                await asyncio.sleep(self.primary_delay)
            provider = "primary"
        else:
            provider = "backup"

        return httpx.Response(
            200,
            request=request,
            json={
                "choices": [{
                    "message": {
                        "content": f"{provider}:{prompt}"
                    }
                }]
            },
        )


def build_cascade(state: CircuitState, transport: ScenarioTransport) -> ProviderCascade:
    specs = [
        ProviderSpec("primary", "https://primary.test/v1", "free-primary", None, "domain-a", 5000),
        ProviderSpec("backup", "https://backup.test/v1", "free-backup", None, "domain-b", 5000),
    ]
    return ProviderCascade(state, specs, ["primary", "backup"], transport=transport)


async def complete(cascade: ProviderCascade, prompt: str, budget_ms: int = 8000):
    return await cascade.complete(
        [{"role": "user", "content": prompt}],
        DeadlineBudget(budget_ms),
        preferred_provider="primary",
    )


async def test_stress(cascade: ProviderCascade):
    latencies = []
    for i in range(50):
        started = time.monotonic()
        result = await complete(cascade, f"STRESS-{i}")
        latencies.append((time.monotonic() - started) * 1000)
        assert result.text == f"primary:STRESS-{i}", result
        assert result.meta.provider_used == "primary", result
        assert result.meta.failover_triggered is False, result
    p50 = statistics.median(latencies)
    p95 = sorted(latencies)[max(0, int(len(latencies) * 0.95) - 1)]
    print({"status": "PASS", "test": "1_stress_50_sequential", "requests": 50,
           "p50_ms": round(p50, 1), "p95_ms": round(p95, 1)})


async def test_outage(cascade: ProviderCascade, transport: ScenarioTransport):
    transport.primary_fail = True
    result = await complete(cascade, "OUTAGE")
    assert result.text == "backup:OUTAGE", result
    assert result.meta.provider_used == "backup", result
    assert result.meta.failover_triggered is True, result
    assert result.meta.attempts >= 2, result
    print({"status": "PASS", "test": "2_forced_primary_outage", "provider_used": result.meta.provider_used,
           "attempts": result.meta.attempts, "failover_triggered": result.meta.failover_triggered})


async def test_recovery(cascade: ProviderCascade, state: CircuitState, transport: ScenarioTransport):
    # Primary remains unavailable in the circuit briefly; backup must carry traffic.
    second = await complete(cascade, "RECOVERY-HOLD")
    assert second.meta.provider_used == "backup", second
    # After the half-open window, primary is restored and must be selectable again.
    await asyncio.sleep(1.1)
    transport.primary_fail = False
    third = await complete(cascade, "RECOVERY-RESTORED")
    assert third.text == "primary:RECOVERY-RESTORED", third
    assert third.meta.provider_used == "primary", third
    assert third.meta.failover_triggered is False, third
    assert "primary" not in state.open_until, state.open_until
    print({"status": "PASS", "test": "3_circuit_recovery", "provider_before_recovery": "backup",
           "provider_after_recovery": third.meta.provider_used})


async def test_timeout(cascade: ProviderCascade, transport: ScenarioTransport):
    transport.primary_delay = 5.8
    started = time.monotonic()
    result = await complete(cascade, "TIMEOUT-CUTOFF", budget_ms=8000)
    elapsed_ms = (time.monotonic() - started) * 1000
    assert DeadlineBudget(8000).provider_timeout_ms(9000) == 5000
    assert result.text == "backup:TIMEOUT-CUTOFF", result
    assert result.meta.provider_used == "backup", result
    assert result.meta.failover_triggered is True, result
    # Backup is immediate; the whole request must not wait for the 5.8s primary.
    assert elapsed_ms < 3000, elapsed_ms
    print({"status": "PASS", "test": "4_slow_primary_cutoff", "provider_used": result.meta.provider_used,
           "elapsed_ms": round(elapsed_ms, 1), "per_provider_cap_ms": 5000})


async def test_concurrency(cascade: ProviderCascade, transport: ScenarioTransport):
    transport.primary_delay = 0.0
    prompts = [f"CONCURRENT-{i}" for i in range(20)]
    results = await asyncio.gather(*(complete(cascade, prompt) for prompt in prompts))
    texts = [result.text for result in results]
    assert len(texts) == 20
    assert len(set(texts)) == 20, texts
    for i, result in enumerate(results):
        assert result.text == f"primary:CONCURRENT-{i}", result
        assert result.meta.provider_used == "primary", result
    print({"status": "PASS", "test": "5_concurrency_20_parallel", "requests": 20,
           "unique_responses": len(set(texts)), "crossed_responses": 0})


async def main():
    state = CircuitState()
    transport = ScenarioTransport()
    cascade = build_cascade(state, transport)

    await test_stress(cascade)
    await test_outage(cascade, transport)
    await test_recovery(cascade, state, transport)
    await test_timeout(cascade, transport)
    await test_concurrency(cascade, transport)

    print({
        "status": "PASS",
        "gate": "C33_AI_RESILIENCE_BATTERY",
        "tests": 5,
        "result": "GREEN",
    })


if __name__ == "__main__":
    asyncio.run(main())
