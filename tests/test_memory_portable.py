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
