import asyncio
import os
import unittest

import httpx

from resilience.providers import DeadlineBudget, GenerationFailure, ProviderCascade, ProviderSpec
from resilience.state import PostgresState

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
        if behavior == "dns":
            raise httpx.ConnectError("Name or service not known", request=request)
        if behavior == "tls":
            raise httpx.ConnectError("SSL: CERTIFICATE_VERIFY_FAILED", request=request)
        if behavior == "connection":
            raise httpx.ConnectError("connection reset by peer", request=request)
        if behavior == "429":
            return httpx.Response(429, headers={"retry-after":"2"}, request=request)
        if behavior == "502":
            return httpx.Response(502, request=request)
        if behavior == "invalid":
            return httpx.Response(200, json={"choices":[]}, request=request)
        if behavior == "stream_ok":
            return httpx.Response(
                200,
                content=b'data: {"choices":[{"delta":{"content":"C33_STREAM_OK"}}]}\n\ndata: [DONE]\n\n',
                headers={"content-type":"text/event-stream"},
                request=request,
            )
        if behavior == "stream_empty":
            return httpx.Response(
                200,
                content=b'data: [DONE]\n\n',
                headers={"content-type":"text/event-stream"},
                request=request,
            )
        return httpx.Response(200, json={"choices":[{"message":{"content":"C33_OK"}}]}, request=request)

class ResilienceTests(unittest.IsolatedAsyncioTestCase):
    async def test_metadata_helper_handles_postgres_json_values(self):
        self.assertEqual(PostgresState._metadata_dict(None), {})
        self.assertEqual(PostgresState._metadata_dict({"topic": "Hola"}), {"topic": "Hola"})
        self.assertEqual(PostgresState._metadata_dict('{"topic":"Hola"}'), {"topic": "Hola"})

    async def test_deadline_is_bounded_by_client(self):
        budget = DeadlineBudget(26000, int(__import__("time").time()*1000)+5000)
        self.assertLessEqual(budget.remaining_ms, 5000)

    async def test_dns_failure_fails_over(self):
        state = FakeState()
        specs = [
            ProviderSpec("a", "https://a.test/v1", "m-a", None, "a", 1000),
            ProviderSpec("b", "https://b.test/v1", "m-b", None, "b", 1000),
        ]
        cascade = ProviderCascade(state, specs, ["a","b"], transport=FaultTransport({"a.test":"dns","b.test":"ok"}))
        result = await cascade.complete([{"role":"user","content":"x"}], DeadlineBudget(5000))
        self.assertEqual(result.meta.provider_used, "b")

    async def test_tls_failure_fails_over(self):
        state = FakeState()
        specs = [
            ProviderSpec("a", "https://a.test/v1", "m-a", None, "a", 1000),
            ProviderSpec("b", "https://b.test/v1", "m-b", None, "b", 1000),
        ]
        cascade = ProviderCascade(state, specs, ["a","b"], transport=FaultTransport({"a.test":"tls","b.test":"ok"}))
        result = await cascade.complete([{"role":"user","content":"x"}], DeadlineBudget(5000))
        self.assertEqual(result.meta.provider_used, "b")

    async def test_5xx_fails_over_to_second_provider(self):
        state = FakeState()
        specs = [
            ProviderSpec("a", "https://a.test/v1", "m-a", None, "a", 1000),
            ProviderSpec("b", "https://b.test/v1", "m-b", None, "b", 1000),
        ]
        cascade = ProviderCascade(state, specs, ["a","b"], transport=FaultTransport({"a.test":"502","b.test":"ok"}))
        result = await cascade.complete([{"role":"user","content":"x"}], DeadlineBudget(5000))
        self.assertEqual(result.text, "C33_OK")
        self.assertEqual(result.meta.provider_used, "b")

    async def test_invalid_provider_response_fails_over(self):
        state = FakeState()
        specs = [
            ProviderSpec("a", "https://a.test/v1", "m-a", None, "a", 1000),
            ProviderSpec("b", "https://b.test/v1", "m-b", None, "b", 1000),
        ]
        cascade = ProviderCascade(state, specs, ["a","b"], transport=FaultTransport({"a.test":"invalid","b.test":"ok"}))
        result = await cascade.complete([{"role":"user","content":"x"}], DeadlineBudget(5000))
        self.assertEqual(result.text, "C33_OK")
        self.assertEqual(result.meta.provider_used, "b")

    async def _assert_stream_failover(self, first_behavior):
        state = FakeState()
        specs = [
            ProviderSpec("a", "https://a.test/v1", "m-a", None, "a", 1000),
            ProviderSpec("b", "https://b.test/v1", "m-b", None, "b", 1000),
        ]
        cascade = ProviderCascade(
            state,
            specs,
            ["a", "b"],
            transport=FaultTransport({"a.test": first_behavior, "b.test": "stream_ok"}),
        )
        pieces = []
        async for piece, _ in cascade.stream([{"role": "user", "content": "x"}], DeadlineBudget(5000)):
            pieces.append(piece)
        self.assertEqual("".join(pieces), "C33_STREAM_OK")
        self.assertEqual(state.successes[-1], "b")
        self.assertEqual(state.failures[0][1], first_behavior)

    async def test_stream_dns_failure_fails_over(self):
        await self._assert_stream_failover("dns")

    async def test_stream_tls_failure_fails_over(self):
        await self._assert_stream_failover("tls")

    async def test_stream_connection_failure_fails_over(self):
        state = FakeState()
        specs = [
            ProviderSpec("a", "https://a.test/v1", "m-a", None, "a", 1000),
            ProviderSpec("b", "https://b.test/v1", "m-b", None, "b", 1000),
        ]
        cascade = ProviderCascade(
            state,
            specs,
            ["a", "b"],
            transport=FaultTransport({"a.test": "connection", "b.test": "stream_ok"}),
        )
        pieces = []
        async for piece, _ in cascade.stream([{"role": "user", "content": "x"}], DeadlineBudget(5000)):
            pieces.append(piece)
        self.assertEqual("".join(pieces), "C33_STREAM_OK")
        self.assertEqual(state.successes[-1], "b")
        self.assertEqual(state.failures[0][1], "connection_reset")

    async def test_stream_empty_fails_over(self):
        await self._assert_stream_failover("stream_empty")

    async def test_stream_fails_over_to_second_provider(self):
        state = FakeState()
        specs = [
            ProviderSpec("a", "https://a.test/v1", "m-a", None, "a", 1000),
            ProviderSpec("b", "https://b.test/v1", "m-b", None, "b", 1000),
        ]
        cascade = ProviderCascade(state, specs, ["a","b"], transport=FaultTransport({"a.test":"timeout","b.test":"stream_ok"}))
        pieces = []
        async for piece, meta in cascade.stream([{"role":"user","content":"x"}], DeadlineBudget(5000)):
            pieces.append(piece)
        self.assertEqual("".join(pieces), "C33_STREAM_OK")
        self.assertEqual(state.successes[-1], "b")

    async def test_probe_ignores_stale_open_circuit_and_recovers(self):
        class StaleOpenState(FakeState):
            async def circuit_before_call(self, provider_id):
                return type("Decision", (), {"allowed": False, "state": "OPEN", "cooldown_ms": 600000})()

        state = StaleOpenState()
        specs = [
            ProviderSpec("a", "https://a.test/v1", "m-a", None, "a", 1000),
            ProviderSpec("b", "https://b.test/v1", "m-b", None, "b", 1000),
        ]
        cascade = ProviderCascade(state, specs, ["a","b"], transport=FaultTransport({"a.test":"timeout","b.test":"ok"}))
        result = await cascade.complete(
            [{"role":"user","content":"probe"}],
            DeadlineBudget(5000),
            probe=True,
        )
        self.assertEqual(result.text, "C33_OK")
        self.assertIn(result.meta.provider_used, {"a","b"})

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

    def test_default_provider_contract_is_two_independent_bounded_providers(self):
        previous = {key: os.environ.get(key) for key in (
            "AI_PROVIDERS_JSON",
            "AI_PROVIDER_A_BASE_URL",
            "AI_PROVIDER_B_BASE_URL",
            "MODEL_BASE_URL",
            "MODEL_NAME",
            "AI_PROVIDER_ORDER",
        )}
        try:
            for key in previous:
                os.environ.pop(key, None)
            os.environ["MODEL_BASE_URL"] = "https://vireonix.ai/v1"
            os.environ["MODEL_NAME"] = "auto"
            os.environ["AI_PROVIDER_ORDER"] = "vireonix,blockrun"
            cascade = ProviderCascade.from_environment(FakeState())
            self.assertEqual(len(cascade.providers), 2)
            self.assertEqual([p.timeout_ms for p in cascade.providers], [6000, 4000])
            self.assertEqual(len(set(p.failure_domain for p in cascade.providers)), 2)
            self.assertEqual([p.provider_id for p in cascade.providers], ["vireonix", "blockrun"])
        finally:
            for key, value in previous.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

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
