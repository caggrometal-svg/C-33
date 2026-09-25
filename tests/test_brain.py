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


if __name__ == "__main__":
    unittest.main()
