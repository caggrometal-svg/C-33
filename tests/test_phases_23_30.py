from __future__ import annotations

import asyncio
import time
import unittest

from nexo.phases_23_30 import (
    BoundedOrchestrator, ExportBundle, KnowledgeState, NexoProtocol,
    PrivacyPolicy, RequestCycle, TTLCache, VerificationPolicy, redact_secrets,
)


class Phase23To30Tests(unittest.TestCase):
    def test_request_cycle_is_complete(self):
        self.assertTrue(RequestCycle().validate())

    def test_bounded_orchestrator_stops_at_budget(self):
        async def run():
            return await BoundedOrchestrator(max_steps=2).run([lambda: 1, lambda: 2])
        self.assertEqual(asyncio.run(run()), [1, 2])

        async def overflow():
            return await BoundedOrchestrator(max_steps=1).run([lambda: 1, lambda: 2])
        with self.assertRaises(RuntimeError):
            asyncio.run(overflow())

    def test_verification_has_three_honest_states(self):
        policy = VerificationPolicy()
        self.assertEqual(policy.state(has_answer=True, can_research=True, verified=True), KnowledgeState.KNOW)
        self.assertEqual(policy.state(has_answer=False, can_research=True, verified=False), KnowledgeState.CAN_RESEARCH)
        self.assertEqual(policy.state(has_answer=False, can_research=False, verified=False), KnowledgeState.UNDETERMINED)

    def test_ttl_cache_expires(self):
        cache = TTLCache()
        cache.set("x", 7, 0.01)
        self.assertEqual(cache.get("x"), 7)
        time.sleep(0.02)
        self.assertIsNone(cache.get("x"))

    def test_secrets_are_redacted(self):
        value = redact_secrets("Bearer abc123 api_key=secret123 password=hunter2")
        self.assertNotIn("abc123", value)
        self.assertNotIn("secret123", value)
        self.assertNotIn("hunter2", value)

    def test_privacy_minimizes_context(self):
        result = PrivacyPolicy().minimize({
            "message": "hola", "relevant_memory": ["x"], "research": [], "api_key": "secret"
        })
        self.assertNotIn("api_key", result)
        self.assertEqual(set(result), {"message", "relevant_memory", "research"})

    def test_export_round_trip_checksum(self):
        bundle = ExportBundle.build(
            memory=[{"content": "x"}],
            preferences={"tone": "neutral"},
            research=[{"question": "q"}],
            configuration={"version": "1"},
            metadata={"user": "anonymous"},
        )
        self.assertTrue(bundle.verify())
        self.assertEqual(bundle.to_dict()["version"], "1")

    def test_protocol_kinds_and_trust_envelope(self):
        event = NexoProtocol.envelope("Event", {"action": "memory_search"}, request_id="r1")
        self.assertEqual(event["protocol"], "NEXO")
        self.assertEqual(event["kind"], "Event")
        self.assertEqual(event["request_id"], "r1")


if __name__ == "__main__":
    unittest.main()
