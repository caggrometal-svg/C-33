import unittest

class NexoFallbackTests(unittest.TestCase):
    def test_local_fallback_is_explicit_and_hides_internal_context(self):
        from agent.brain import Brain
        response = Brain.local_fallback("Hola", "timeout")
        self.assertNotIn("Memory", response)
        self.assertNotIn("user_position", response)
        self.assertIn("respaldo local", response)
        self.assertIn("timeout", response)

if __name__ == "__main__":
    unittest.main()
