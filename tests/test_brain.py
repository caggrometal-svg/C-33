import unittest

class NexoFallbackTests(unittest.TestCase):
    def test_local_fallback_is_explicit_and_hides_internal_context(self):
        from agent.brain import Brain
        response = Brain.local_fallback("Hola", "timeout")
        self.assertNotIn("Memory", response)
        self.assertNotIn("user_position", response)
        self.assertIn("respaldo local", response)
        self.assertIn("timeout", response)

class Phase20ArchitectureTests(unittest.TestCase):
    def test_tool_hub_has_replaceable_async_capabilities(self):
        from nexo.architecture import ToolHub

        hub = ToolHub()

        async def async_tool(value):
            return value + 1

        hub.register("math", async_tool)
        self.assertEqual(hub.names, ("math",))
        self.assertEqual(__import__("asyncio").run(hub.invoke("math", 41)), 42)

    def test_model_hub_exposes_profiles_and_selects_preference(self):
        from nexo.architecture import ModelHub

        class Spec:
            provider_id = "alpha"
            model = "m-alpha"
            failure_domain = "alpha.test"

        class FakeCascade:
            configured_provider_ids = ["alpha"]
            providers = [Spec()]

            async def complete(self, messages, budget):
                return "generation"

        hub = ModelHub(FakeCascade())
        self.assertEqual(hub.profiles[0].model_id, "m-alpha")
        self.assertEqual(hub.select("alpha").provider_id, "alpha")
        self.assertEqual(hub.select("missing").provider_id, "alpha")


    def test_web_tools_are_authorized_at_boundary(self):
        from agent.brain import Brain
        import inspect
        source = inspect.getsource(Brain.prepare_messages)
        self.assertIn("network_allowed=True", source)

    def test_model_hub_delegates_to_provider_cascade(self):
        from nexo.architecture import ModelHub

        class FakeCascade:
            configured_provider_ids = ["alpha", "beta"]

            async def complete(self, messages, budget):
                return "generation"

        hub = ModelHub(FakeCascade())
        self.assertEqual(hub.provider_ids, ("alpha", "beta"))
        self.assertEqual(__import__("asyncio").run(hub.complete([], None)), "generation")

    def test_local_model_is_explicit_and_non_deceptive(self):
        from nexo.architecture import LocalModel

        response = LocalModel.complete("Hola", "timeout")
        self.assertIn("respaldo local", response)
        self.assertIn("timeout", response)
        self.assertIn("no presentaré", response.lower())

    def test_verification_rejects_non_http_sources_and_bad_citations(self):
        from nexo.architecture import VerificationEngine

        engine = VerificationEngine()
        result = engine.verify_response("Dato [2]", ["https://example.com"])
        self.assertFalse(result.ok)
        self.assertIn("citation_out_of_range", result.warnings)

        zero = engine.verify_response("Dato [0]", ["https://example.com"])
        self.assertFalse(zero.ok)
        self.assertIn("citation_out_of_range", zero.warnings)

    def test_orchestrator_routes_current_web_and_memory(self):
        from nexo.architecture import NexoOrchestrator

        plan = NexoOrchestrator().plan("verifica esto en internet", [object()])
        self.assertTrue(plan.use_web)
        self.assertTrue(plan.use_memory)
        self.assertTrue(plan.verify)
        self.assertEqual(plan.reason, "web+memory")

    def test_orchestrator_avoids_substring_false_positive_for_web_marker(self):
        from nexo.architecture import NexoOrchestrator

        plan = NexoOrchestrator().plan("preciosos detalles del diseño", [])
        self.assertFalse(plan.use_web)

    def test_orchestrator_still_detects_standalone_web_marker(self):
        from nexo.architecture import NexoOrchestrator

        plan = NexoOrchestrator().plan("dame el precio actual", [])
        self.assertTrue(plan.use_web)


    def test_orchestrator_treats_bare_nexo_as_self_reference(self):
        from nexo.architecture import NexoOrchestrator

        bare = NexoOrchestrator().plan("Nexo", [object()])
        self.assertFalse(bare.use_web)
        self.assertFalse(bare.use_memory)
        self.assertFalse(bare.verify)
        self.assertEqual(bare.reason, "self-reference")

        greeting = NexoOrchestrator().plan("Hola Nexo", [object()])
        self.assertFalse(greeting.use_web)
        self.assertFalse(greeting.use_memory)

    def test_external_nexo_request_is_not_mistaken_for_self_reference(self):
        from agent.nexo import NexoCore

        self.assertFalse(NexoCore.is_self_reference("Nexo empresa de criptomonedas"))
        self.assertFalse(NexoCore.is_self_reference("Nexo plataforma de activos digitales"))

    def test_model_selection_policy_routes_by_capability(self):
        from nexo.architecture import ModelHub

        class Spec:
            def __init__(self, provider_id, model, failure_domain, capabilities):
                self.provider_id = provider_id
                self.model = model
                self.failure_domain = failure_domain
                self.capabilities = capabilities

        class FakeCascade:
            configured_provider_ids = ["fast", "deep", "cheap"]
            providers = [
                Spec("fast", "m-fast", "fast.test", ("chat", "stream", "fast")),
                Spec("deep", "m-deep", "deep.test", ("chat", "stream", "reasoning")),
                Spec("cheap", "m-cheap", "cheap.test", ("chat", "stream", "economical")),
            ]

        hub = ModelHub(FakeCascade())
        self.assertEqual(hub.select_for_task("hola").selected_provider, "fast")
        self.assertEqual(hub.select_for_task("analiza y depura este error").selected_provider, "deep")
        self.assertEqual(hub.select_for_task("haz un resumen").selected_provider, "cheap")

    def test_model_selection_policy_never_fakes_local(self):
        from nexo.architecture import ModelHub

        class Spec:
            provider_id = "remote"
            model = "m-remote"
            failure_domain = "remote.test"
            capabilities = ("chat", "stream")

        class FakeCascade:
            configured_provider_ids = ["remote"]
            providers = [Spec()]

        decision = ModelHub(FakeCascade()).select_for_task("procesa esto en modo privado y local")
        self.assertTrue(decision.local_required)
        self.assertIsNone(decision.selected_provider)
        self.assertEqual(decision.reason, "local_capability_unavailable")


    def test_tool_hub_exposes_memory_search_store_and_calculator(self):
        from nexo.architecture import ToolHub

        hub = ToolHub()

        async def memory_search(query, user_id="anonymous", limit=8):
            return [{"query": query, "user_id": user_id, "limit": limit}]

        async def memory_store(content, *, user_id="anonymous"):
            return {"stored": bool(content), "user_id": user_id}

        def calculator(expression):
            return 42

        hub.register("memory_search", memory_search)
        hub.register("memory_store", memory_store, mutates_state=True, risk="medium")
        hub.register("calculator", calculator)

        import asyncio
        self.assertEqual(
            asyncio.run(hub.invoke("memory_search", "nexo", user_id="u1")),
            [{"query": "nexo", "user_id": "u1", "limit": 8}],
        )
        self.assertEqual(
            asyncio.run(hub.invoke("calculator", "6*7")),
            42,
        )
        with self.assertRaises(PermissionError):
            asyncio.run(hub.invoke("memory_store", "dato", user_id="u1"))
        self.assertEqual(
            asyncio.run(hub.invoke("memory_store", "dato", user_id="u1", mutations_allowed=True)),
            {"stored": True, "user_id": "u1"},
        )


if __name__ == "__main__":
    unittest.main()
