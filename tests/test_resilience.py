import asyncio
import os
import unittest

import httpx

from resilience.providers import DeadlineBudget, GenerationFailure, ProviderCascade, ProviderSpec

class FakeState:
    def __init__(self):
        self.state = {}
        self.successes = []
        self.failures = []
    async def circuit_before_call(self, provider_id):
        return type("Decision", (), {"allowed": True, "state": self.state.get(provider_id, "CLOSED"), "cooldown_ms": 0})()
    async def circuit_success(self, provider_id, *, model, latency_ms):
        self.state[provider_id] = "CLOSED"
        self.successes.append(provider_id)
    async def circuit_failure(self, provider_id, *, reason, status, model, latency_ms, cooldown_ms):
        self.state[provider_id] = "OPEN"
        self.failures.append((provider_id, reason, status, cooldown_ms))

class FaultTransport(httpx.AsyncBaseTransport):
    def __init__(self, responses):
        self.responses = responses
    async def handle_async_request(self, request):
        provider = request.url.host
        behavior = self.responses[provider]
        if behavior == "timeout":
            raise httpx.ReadTimeout("synthetic timeout", request=request)
        if behavior == "429":
            return httpx.Response(429, headers={"retry-after":"2"}, request=request)
        if behavior == "502":
            return httpx.Response(502, request=request)
        return httpx.Response(200, json={"choices":[{"message":{"content":"C33_OK"}}]}, request=request)

class ResilienceTests(unittest.IsolatedAsyncioTestCase):
    async def test_deadline_is_bounded_by_client(self):
        budget = DeadlineBudget(26000, int(__import__("time").time()*1000)+5000)
        self.assertLessEqual(budget.remaining_ms, 5000)

    async def test_429_fails_over_and_opens_first_circuit(self):
        state = FakeState()
        specs = [
            ProviderSpec("a", "https://a.test/v1", "m-a", None, "a", 1000),
            ProviderSpec("b", "https://b.test/v1", "m-b", None, "b", 1000),
        ]
        cascade = ProviderCascade(state, specs, ["a","b"], transport=FaultTransport({"a.test":"429","b.test":"ok"}))
        result = await cascade.complete([{"role":"user","content":"x"}], DeadlineBudget(5000))
        self.assertEqual(result.text, "C33_OK")
        self.assertEqual(result.meta.provider_used, "b")
        self.assertTrue(result.meta.failover_triggered)
        self.assertEqual(state.failures[0][1], "rate_limited")

    async def test_timeout_fails_over(self):
        state = FakeState()
        specs = [
            ProviderSpec("a", "https://a.test/v1", "m-a", None, "a", 1000),
            ProviderSpec("b", "https://b.test/v1", "m-b", None, "b", 1000),
        ]
        cascade = ProviderCascade(state, specs, ["a","b"], transport=FaultTransport({"a.test":"timeout","b.test":"ok"}))
        result = await cascade.complete([{"role":"user","content":"x"}], DeadlineBudget(5000))
        self.assertEqual(result.meta.provider_used, "b")

    async def test_all_rate_limits_return_429(self):
        state = FakeState()
        specs = [
            ProviderSpec("a", "https://a.test/v1", "m-a", None, "a", 1000),
            ProviderSpec("b", "https://b.test/v1", "m-b", None, "b", 1000),
        ]
        cascade = ProviderCascade(state, specs, ["a","b"], transport=FaultTransport({"a.test":"429","b.test":"429"}))
        with self.assertRaises(GenerationFailure) as ctx:
            await cascade.complete([{"role":"user","content":"x"}], DeadlineBudget(5000))
        self.assertEqual(ctx.exception.http_status, 429)

    def test_redundancy_configuration_rejects_single_provider(self):
        previous = os.environ.get("REQUIRE_PROVIDER_REDUNDANCY")
        os.environ["REQUIRE_PROVIDER_REDUNDANCY"] = "true"
        try:
            state = FakeState()
            cascade = ProviderCascade(state, [ProviderSpec("a", "https://a.test/v1", "m", None, "a", 1000)], ["a"])
            with self.assertRaises(GenerationFailure) as ctx:
                cascade.assert_ready_configuration()
            self.assertEqual(ctx.exception.reason, "provider_redundancy_not_configured")
        finally:
            if previous is None: os.environ.pop("REQUIRE_PROVIDER_REDUNDANCY", None)
            else: os.environ["REQUIRE_PROVIDER_REDUNDANCY"] = previous

if __name__ == "__main__":
    unittest.main()
