import unittest


class ObservabilityTests(unittest.TestCase):
    def test_safe_request_id_is_preserved(self):
        from nexo.observability import normalize_request_id
        self.assertEqual(normalize_request_id("abc-123:trace"), "abc-123:trace")

    def test_unsafe_request_id_is_replaced(self):
        from nexo.observability import normalize_request_id
        value = normalize_request_id("bad id with spaces")
        self.assertNotEqual(value, "bad id with spaces")
        self.assertTrue(value)

    def test_request_id_length_is_bounded(self):
        from nexo.observability import normalize_request_id

        oversized = "a" * 129
        normalized = normalize_request_id(oversized)
        self.assertNotEqual(normalized, oversized)
        self.assertLessEqual(len(normalized), 128)

    def test_metrics_are_aggregate_and_bounded(self):
        from nexo.observability import RequestMetrics
        metrics = RequestMetrics(max_paths=2)
        metrics.record("GET", "/health", 200, 10)
        metrics.record("POST", "/v1/chat", 502, 40)
        metrics.record("GET", "/dynamic/1", 200, 20)
        metrics.record("GET", "/dynamic/2", 200, 30)
        snapshot = metrics.snapshot()
        self.assertEqual(snapshot["total_requests"], 4)
        self.assertIn("GET /health 2xx", snapshot["counts"])
        self.assertIn("_other 2xx", snapshot["counts"])
        self.assertEqual(snapshot["latency"]["GET /health"]["p50_ms"], 10)


if __name__ == "__main__":
    unittest.main()
