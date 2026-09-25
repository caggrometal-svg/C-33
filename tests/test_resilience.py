import asyncio
import os
import unittest

import httpx

from resilience.providers import DeadlineBudget, GenerationFailure, ProviderCascade, ProviderConfigurationError, ProviderSpec
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
        if behavior == "400":
            return httpx.Response(
                400,
                json={"error": {"message": "model_request_invalid"}},
                request=request,
            )
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
    async def test_replication_import_enforces_message_size_limits(self):
        source = __import__("inspect").getsource(PostgresState.import_replication_batch)
        self.assertIn("_MAX_REPLICATION_TEXT_CHARS", source)
        self.assertIn("len(content) > _MAX_REPLICATION_TEXT_CHARS", source)
        self.assertIn("len(conversation_id) > _MAX_REPLICATION_ID_CHARS", source)

    async def test_replication_import_validates_message_role_before_insert(self):
        source = __import__("inspect").getsource(PostgresState.import_replication_batch)
        self.assertIn('if role not in {"user", "assistant", "system"}:', source)
        self.assertIn("continue", source)

    async def test_durable_memory_match_uses_complete_tokens(self):
        self.assertEqual(PostgresState._memory_match_score("red", "credencial"), 0)
        self.assertEqual(PostgresState._memory_match_score("conexion", "conexión remota"), 1)
        self.assertEqual(PostgresState._memory_match_score("backend red", "backend conexión"), 1)

    async def test_metadata_helper_handles_postgres_json_values(self):
        self.assertEqual(PostgresState._metadata_dict(None), {})
        self.assertEqual(PostgresState._metadata_dict({"topic": "Hola"}), {"topic": "Hola"})
        self.assertEqual(PostgresState._metadata_dict('{"topic":"Hola"}'), {"topic": "Hola"})

    async def test_deadline_is_bounded_by_client(self):
        budget = DeadlineBudget(26000, int(__import__("time").time()*1000)+5000)
        self.assertLessEqual(budget.remaining_ms, 5000)

    async def test_provider_timeout_is_capped_for_failover_budget(self):
        budget = DeadlineBudget(18000)
        self.assertEqual(budget.provider_timeout_ms(9000), 6500)
        self.assertLessEqual(budget.provider_timeout_ms(9000), budget.remaining_ms)

    async def test_sequential_timeout_failover_reaches_third_provider(self):
        state = FakeState()
        specs = [
            ProviderSpec("a", "https://a.test/v1", "m-a", None, "a", 9000),
            ProviderSpec("b", "https://b.test/v1", "m-b", None, "b", 9000),
            ProviderSpec("c", "https://c.test/v1", "m-c", None, "c", 9000),
        ]
        cascade = ProviderCascade(
            state,
            specs,
            ["a", "b", "c"],
            transport=FaultTransport({"a.test": "timeout", "b.test": "timeout", "c.test": "ok"}),
        )
        result = await cascade.complete(
            [{"role": "user", "content": "x"}],
            DeadlineBudget(18000),
        )
        self.assertEqual(result.meta.provider_used, "c")
        self.assertEqual([failure[0] for failure in state.failures[:2]], ["a", "b"])

    async def test_dns_failure_fails_over(self):
        state = FakeState()
        specs = [
            ProviderSpec("a", "https://a.test/v1", "m-a", None, "a", 1000),
            ProviderSpec("b", "https://b.test/v1", "m-b", None, "b", 1000),
        ]
        cascade = ProviderCascade(state, specs, ["a","b"], transport=FaultTransport({"a.test":"dns","b.test":"ok"}))
        result = await cascade.complete([{"role":"user","content":"x"}], DeadlineBudget(5000))
        self.assertEqual(result.meta.provider_used, "b")

    async def test_nested_dns_failure_fails_over(self):
        class NestedDnsTransport(FaultTransport):
            async def handle_async_request(self, request):
                if request.url.host != "a.test":
                    return await super().handle_async_request(request)
                cause = OSError("Temporary failure in name resolution")
                exc = httpx.ConnectError("transport failed", request=request)
                exc.__cause__ = cause
                raise exc

        state = FakeState()
        specs = [
            ProviderSpec("a", "https://a.test/v1", "m-a", None, "a", 1000),
            ProviderSpec("b", "https://b.test/v1", "m-b", None, "b", 1000),
        ]
        cascade = ProviderCascade(
            state,
            specs,
            ["a", "b"],
            transport=NestedDnsTransport({"a.test": "dns", "b.test": "ok"}),
        )
        result = await cascade.complete([{"role": "user", "content": "x"}], DeadlineBudget(5000))
        self.assertEqual(result.meta.provider_used, "b")
        self.assertEqual(state.failures[0][1], "dns_failure")

    async def test_tls_failure_fails_over(self):
        state = FakeState()
        specs = [
            ProviderSpec("a", "https://a.test/v1", "m-a", None, "a", 1000),
            ProviderSpec("b", "https://b.test/v1", "m-b", None, "b", 1000),
        ]
        cascade = ProviderCascade(state, specs, ["a","b"], transport=FaultTransport({"a.test":"tls","b.test":"ok"}))
        result = await cascade.complete([{"role":"user","content":"x"}], DeadlineBudget(5000))
        self.assertEqual(result.meta.provider_used, "b")

    async def test_preferred_provider_is_attempted_first(self):
        state = FakeState()
        specs = [
            ProviderSpec("a", "https://a.test/v1", "m-a", None, "a", 1000),
            ProviderSpec("b", "https://b.test/v1", "m-b", None, "b", 1000),
        ]
        cascade = ProviderCascade(
            state,
            specs,
            ["a", "b"],
            transport=FaultTransport({"a.test": "ok", "b.test": "ok"}),
        )
        result = await cascade.complete(
            [{"role":"user","content":"x"}],
            DeadlineBudget(5000),
            preferred_provider="b",
        )
        self.assertEqual(result.meta.provider_used, "b")
        self.assertFalse(result.meta.failover_triggered)
        self.assertEqual(state.successes[-1], "b")

    async def test_preferred_provider_failure_fails_over_to_configured_peer(self):
        state = FakeState()
        specs = [
            ProviderSpec("a", "https://a.test/v1", "m-a", None, "a", 1000),
            ProviderSpec("b", "https://b.test/v1", "m-b", None, "b", 1000),
        ]
        cascade = ProviderCascade(
            state,
            specs,
            ["a", "b"],
            transport=FaultTransport({"a.test": "ok", "b.test": "502"}),
        )
        result = await cascade.complete(
            [{"role":"user","content":"x"}],
            DeadlineBudget(5000),
            preferred_provider="b",
        )
        self.assertEqual(result.meta.provider_used, "a")
        self.assertTrue(result.meta.failover_triggered)
        self.assertEqual(state.failures[0][0], "b")

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
        expected_reason = {
            "dns": "dns_failure",
            "tls": "tls_failure",
            "connection": "connection_reset",
            "stream_empty": "empty_stream",
        }[first_behavior]
        self.assertEqual(state.failures[0][1], expected_reason)

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
        before_successes = list(state.successes)
        before_failures = list(state.failures)
        result = await cascade.complete(
            [{"role":"user","content":"probe"}],
            DeadlineBudget(5000),
            probe=True,
        )
        self.assertEqual(result.text, "C33_OK")
        self.assertIn(result.meta.provider_used, {"a","b"})
        self.assertEqual(state.successes, before_successes)
        self.assertEqual(state.failures, before_failures)

    async def test_429_preserves_retry_after_on_terminal_failure(self):
        state = FakeState()
        specs = [ProviderSpec("a", "https://a.test/v1", "m-a", None, "a", 1000)]
        cascade = ProviderCascade(
            state,
            specs,
            ["a"],
            transport=FaultTransport({"a.test": "429"}),
        )
        with self.assertRaises(GenerationFailure) as ctx:
            await cascade.complete([{"role": "user", "content": "x"}], DeadlineBudget(5000))
        self.assertEqual(ctx.exception.http_status, 429)
        self.assertGreaterEqual(ctx.exception.retry_after_ms or 0, 1000)

    async def test_400_fails_over_to_second_provider(self):
        state = FakeState()
        specs = [
            ProviderSpec("a", "https://a.test/v1", "m-a", None, "a", 1000),
            ProviderSpec("b", "https://b.test/v1", "m-b", None, "b", 1000),
        ]
        cascade = ProviderCascade(
            state,
            specs,
            ["a", "b"],
            transport=FaultTransport({"a.test": "400", "b.test": "ok"}),
        )
        result = await cascade.complete([{"role": "user", "content": "x"}], DeadlineBudget(5000))
        self.assertEqual(result.meta.provider_used, "b")
        self.assertEqual(state.failures[0][1], "bad_request:model_request_invalid")

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
        self.assertEqual(state.state["a"], "OPEN")

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

    def test_retry_after_is_bounded(self):
        self.assertEqual(ProviderCascade._parse_retry_after_ms("2"), 2000)
        self.assertEqual(ProviderCascade._parse_retry_after_ms("99999"), 600000)
        self.assertEqual(ProviderCascade._parse_retry_after_ms("-5"), 0)
        self.assertEqual(ProviderCascade._parse_retry_after_ms("n/a"), 0)

    def test_final_reason_prioritizes_transport_failures(self):
        from resilience.providers import ProviderCascade

        self.assertEqual(
            ProviderCascade._final_reason([
                {"reason": "provider_5xx", "status": 502},
                {"reason": "timeout", "status": 504},
            ]),
            "timeout",
        )
        self.assertEqual(
            ProviderCascade._final_reason([
                {"reason": "provider_5xx", "status": 502},
                {"reason": "dns_failure", "status": 502},
            ]),
            "dns_failure",
        )
        self.assertEqual(
            ProviderCascade._final_reason([
                {"reason": "provider_5xx", "status": 502},
                {"reason": "auth_error", "status": 401},
            ]),
            "provider_auth_failure",
        )

    def test_provider_capabilities_are_loaded_from_environment(self):
        previous = {key: os.environ.get(key) for key in (
            "AI_PROVIDERS_JSON",
            "AI_PROVIDER_ORDER",
            "AI_PROVIDER_A_CAPABILITIES",
            "AI_PROVIDER_B_CAPABILITIES",
            "MODEL_BASE_URL",
            "MODEL_NAME",
        )}
        try:
            for key in previous:
                os.environ.pop(key, None)
            os.environ["AI_PROVIDERS_JSON"] = (
                '[{"id":"kilo","base_url":"https://api.kilo.ai/api/gateway","model":"legacy","failure_domain":"kilo.ai","timeout_ms":6500,"capabilities":["chat","stream","fast"]},'
                '{"id":"vireonix","base_url":"https://vireonix.ai/v1","model":"legacy","failure_domain":"vireonix.ai","timeout_ms":6500,"capabilities":["chat","stream","reasoning"]}]'
            )
            os.environ["AI_PROVIDER_ORDER"] = "kilo,vireonix"
            cascade = ProviderCascade.from_environment(FakeState())
            by_id = {spec.provider_id: spec for spec in cascade.providers}
            self.assertEqual(by_id["kilo"].capabilities, ("chat", "stream", "fast"))
            self.assertEqual(by_id["vireonix"].capabilities, ("chat", "stream", "reasoning"))
            self.assertEqual(by_id["kilo"].model, "kilo-auto/free")
            self.assertEqual(by_id["vireonix"].model, "auto")
        finally:
            for key, value in previous.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

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
            cascade = ProviderCascade.from_environment(FakeState())
            self.assertEqual(len(cascade.providers), 2)
            self.assertEqual([p.timeout_ms for p in cascade.providers], [6500, 6500])
            self.assertEqual(len(set(p.failure_domain for p in cascade.providers)), 2)
            self.assertEqual([p.provider_id for p in cascade.providers], ["kilo", "vireonix"])
            self.assertEqual([p.model for p in cascade.providers], ["kilo-auto/free", "auto"])
            self.assertTrue(all(p.api_key_env is None for p in cascade.providers))
        finally:
            for key, value in previous.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

    def test_explicit_order_rejects_missing_configured_provider(self):
        previous = {key: os.environ.get(key) for key in (
            "AI_PROVIDERS_JSON",
            "AI_PROVIDER_ORDER",
            "AI_DISABLED_PROVIDERS",
            "REQUIRE_PROVIDER_REDUNDANCY",
        )}
        try:
            os.environ["AI_PROVIDERS_JSON"] = (
                '[{"id":"kilo","base_url":"https://api.kilo.ai/api/gateway","model":"legacy","failure_domain":"kilo.ai","timeout_ms":6500},'
                '{"id":"vireonix","base_url":"https://vireonix.ai/v1","model":"auto","failure_domain":"vireonix.ai","timeout_ms":6500}]'
            )
            os.environ["AI_PROVIDER_ORDER"] = "kilo"
            os.environ["AI_DISABLED_PROVIDERS"] = ""
            os.environ["REQUIRE_PROVIDER_REDUNDANCY"] = "false"
            with self.assertRaises(ProviderConfigurationError) as ctx:
                ProviderCascade.from_environment(FakeState())
            self.assertIn("provider_order_mismatch", str(ctx.exception))
            self.assertIn("vireonix", str(ctx.exception))
        finally:
            for key, value in previous.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

    def test_explicit_order_is_deterministic_and_supports_disabled_provider(self):
        previous = {key: os.environ.get(key) for key in (
            "AI_PROVIDERS_JSON",
            "AI_PROVIDER_ORDER",
            "AI_DISABLED_PROVIDERS",
            "REQUIRE_PROVIDER_REDUNDANCY",
        )}
        try:
            os.environ["AI_PROVIDERS_JSON"] = (
                '[{"id":"kilo","base_url":"https://api.kilo.ai/api/gateway","model":"legacy","failure_domain":"kilo.ai","timeout_ms":6500},'
                '{"id":"vireonix","base_url":"https://vireonix.ai/v1","model":"auto","failure_domain":"vireonix.ai","timeout_ms":6500}]'
            )
            os.environ["AI_PROVIDER_ORDER"] = "vireonix,kilo"
            os.environ["AI_DISABLED_PROVIDERS"] = "kilo"
            os.environ["REQUIRE_PROVIDER_REDUNDANCY"] = "false"
            cascade = ProviderCascade.from_environment(FakeState())
            self.assertEqual([p.provider_id for p in cascade.providers], ["vireonix"])
            self.assertEqual(cascade.providers[0].model, "auto")
        finally:
            for key, value in previous.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

    def test_paid_provider_is_rejected(self):
        previous = {key: os.environ.get(key) for key in ("AI_PROVIDERS_JSON", "AI_PROVIDER_ORDER", "REQUIRE_PROVIDER_REDUNDANCY")}
        try:
            os.environ["AI_PROVIDERS_JSON"] = (
                '[{"id":"paid","base_url":"https://paid-provider.invalid/v1","model":"paid-model","failure_domain":"paid-provider.invalid","timeout_ms":6500}]'
            )
            os.environ["AI_PROVIDER_ORDER"] = "paid"
            os.environ["REQUIRE_PROVIDER_REDUNDANCY"] = "false"
            with self.assertRaisesRegex(ProviderConfigurationError, "paid_or_unapproved_provider_blocked"):
                ProviderCascade.from_environment(FakeState())
        finally:
            for key, value in previous.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

    def test_provider_api_key_is_rejected_in_free_mode(self):
        previous = {key: os.environ.get(key) for key in ("AI_PROVIDERS_JSON", "AI_PROVIDER_ORDER", "REQUIRE_PROVIDER_REDUNDANCY")}
        try:
            os.environ["AI_PROVIDERS_JSON"] = (
                '[{"id":"kilo","base_url":"https://api.kilo.ai/api/gateway","model":"kilo-auto/free","failure_domain":"kilo.ai","timeout_ms":6500,"api_key_env":"SOME_BILLABLE_KEY"},'
                '{"id":"vireonix","base_url":"https://vireonix.ai/v1","model":"auto","failure_domain":"vireonix.ai","timeout_ms":6500}]'
            )
            os.environ["AI_PROVIDER_ORDER"] = "kilo,vireonix"
            os.environ["REQUIRE_PROVIDER_REDUNDANCY"] = "true"
            with self.assertRaisesRegex(ProviderConfigurationError, "api_key_provider_blocked"):
                ProviderCascade.from_environment(FakeState())
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
