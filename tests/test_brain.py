import unittest


class FailingModel:
    async def complete(self, messages):
        raise RuntimeError("provider unavailable")


class NexoFallbackTests(unittest.IsolatedAsyncioTestCase):
    async def test_local_fallback_never_contains_internal_context(self):
        from agent.brain import Brain

        context = [
            "Memory 2026-09-24T12:54:51Z: topic=Hola | user_position=Hola | arguments=internal"
        ]
        response = Brain._fallback_synthesis("Hola", context)

        self.assertNotIn("Memory", response)
        self.assertNotIn("2026-09-24", response)
        self.assertNotIn("user_position", response)
        self.assertIn("modo local", response)

    async def test_configured_provider_failure_is_not_saved_as_fallback_context(self):
        from agent.brain import Brain

        brain = Brain.__new__(Brain)
        brain.model = FailingModel()

        with self.assertRaises(RuntimeError):
            await brain._synthesize("Hola", ["Memory internal"])

if __name__ == "__main__":
    unittest.main()
