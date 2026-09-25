import unittest


class MemoryEngineTests(unittest.TestCase):
    def test_ranked_memory_matches_normalized_tokens(self):
        from nexo.memory_engine import MemoryEngine

        class Entry:
            user_text = "La interfaz quedó lista"
            assistant_text = "Matriz y conexión"
            summary = "conexión remota"
            debate_topic = ""
            user_position = ""
            tags = ["nexo"]
            central_arguments = ["backend"]

        hits = MemoryEngine.select([Entry()], "conexion", limit=3)
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].match, "token_match")
        self.assertGreater(hits[0].score, 0)

    def test_memory_match_uses_complete_tokens(self):
        from nexo.memory_engine import MemoryEngine

        class Entry:
            user_text = "credencial del usuario"
            assistant_text = ""
            summary = "credencial"
            debate_topic = ""
            user_position = ""
            tags = []
            central_arguments = []

        self.assertEqual(MemoryEngine.select([Entry()], "red", limit=3), [])

    def test_memory_store_uses_complete_tokens(self):
        import asyncio
        import tempfile
        from pathlib import Path
        from memory.store import MemoryStore

        async def exercise():
            with tempfile.TemporaryDirectory() as tmp:
                store = MemoryStore(str(Path(tmp) / "memory.json"), short_term_limit=1, long_term_limit=4)
                await store.save("credencial del usuario", "dato antiguo")
                recent = await store.save("saludo general", "dato reciente")
                hits = await store.search_context("red", limit=4)
                self.assertEqual([entry.id for entry in hits], [recent.id])
                self.assertEqual(hits[0].summary, "dato reciente")

        asyncio.run(exercise())

    def test_equal_relevance_prefers_newer_memory(self):
        from nexo.memory_engine import MemoryEngine

        class Entry:
            def __init__(self, created_at, summary):
                self.created_at = created_at
                self.user_text = summary
                self.assistant_text = ""
                self.summary = summary
                self.debate_topic = ""
                self.user_position = ""
                self.tags = []
                self.central_arguments = []

        older = Entry("2026-09-25T06:00:00+00:00", "backend conexión")
        newer = Entry("2026-09-25T06:30:00+00:00", "backend conexión")
        hits = MemoryEngine.select([older, newer], "conexion backend", limit=2)
        self.assertEqual(hits[0].entry, newer)
        self.assertEqual(hits[1].entry, older)


class PortableBundleTests(unittest.TestCase):
    def test_bundle_round_trip_shape(self):
        from nexo.portable import SCHEMA_VERSION, export_bundle, validate_bundle

        bundle = export_bundle(
            user_id="u1",
            messages=[{"role": "user", "content": "hola"}],
            memory=[{"summary": "saludo"}],
        )
        self.assertEqual(bundle["schema_version"], SCHEMA_VERSION)
        self.assertTrue(validate_bundle(bundle)[0])


    def test_bundle_preserves_identity_preferences_and_configuration(self):
        from nexo.portable import export_bundle, validate_bundle
        bundle = export_bundle(
            user_id="u1",
            messages=[{"role": "user", "content": "hola"}],
            memory=[],
            preferences={"font_size": "large"},
            configuration={"backend_urls": ["https://example.invalid"]},
            identity_id="u1",
            device_id="d1",
        )
        self.assertEqual(bundle["identity_id"], "u1")
        self.assertEqual(bundle["device_id"], "d1")
        self.assertEqual(bundle["preferences"]["font_size"], "large")
        self.assertTrue(validate_bundle(bundle)[0])

    def test_checksum_detects_tampering(self):
        from nexo.portable import export_bundle, validate_bundle
        bundle = export_bundle(user_id='u1', messages=[], memory=[])
        bundle['memory'].append({'tampered': True})
        ok, warnings = validate_bundle(bundle)
        self.assertFalse(ok)
        self.assertIn('checksum_mismatch', warnings)

    def test_invalid_bundle_is_rejected(self):
        from nexo.portable import validate_bundle

        ok, warnings = validate_bundle({"schema_version": "bad", "memory": {}})
        self.assertFalse(ok)
        self.assertIn("unsupported_schema_version", warnings)
        self.assertIn("user_id_required", warnings)
        self.assertIn("memory_must_be_list", warnings)

if __name__ == "__main__":
    unittest.main()
