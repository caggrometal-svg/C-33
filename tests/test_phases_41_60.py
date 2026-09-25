from __future__ import annotations

import unittest

from nexo.phases_23_30 import KnowledgeState, Research, ExportBundle
from nexo.phases_41_60 import (
    AutonomyPlan,
    ControlledAutonomyPolicy,
    DegradedMode,
    DegradedModePolicy,
    DecentralizationPlan,
    LongTermMemoryPolicy,
    MasterTestPlan,
    NexoModeMatrix,
    PermissionMatrix,
    ResearchObject,
    SuccessCriteria,
    TrustArchitecture,
)


class Phase41To60Tests(unittest.TestCase):
    def test_degraded_mode_preserves_useful_paths(self):
        decision = DegradedModePolicy.decide(web_available=False)
        self.assertEqual(decision.mode, DegradedMode.WEB_DEGRADED)
        self.assertIn("chat", decision.preserved_capabilities)
        self.assertIn("web", decision.disabled_capabilities)

        offline = DegradedModePolicy.decide(provider_available=False, local_available=True)
        self.assertEqual(offline.mode, DegradedMode.OFFLINE_LOCAL)
        self.assertIn("local_fallback", offline.preserved_capabilities)

    def test_research_is_a_structured_object(self):
        research = Research(
            question="precio actual",
            sources=("https://example.com",),
            findings=("dato",),
            confidence=0.8,
            summary="resumen",
        )
        obj = ResearchObject.from_research(research)
        self.assertTrue(obj.validate())
        self.assertEqual(obj.question, "precio actual")

    def test_long_term_memory_is_selective(self):
        policy = LongTermMemoryPolicy()
        low = policy.decide(content="detalle", importance=0.2, confidence=0.9)
        self.assertFalse(low.persist)
        accepted = policy.decide(content="dato útil", importance=0.9, confidence=0.9)
        self.assertTrue(accepted.persist)
        self.assertTrue(accepted.dedupe_key)

    def test_controlled_autonomy_is_bounded(self):
        plan = ControlledAutonomyPolicy.plan(
            ("search", "fetch", "compare", "calculate", "store"),
            authorized=False,
            max_steps=5,
        )
        self.assertTrue(plan.validate())
        self.assertTrue(plan.approval_required)
        self.assertEqual(len(plan.operations), 5)

    def test_permissions_are_least_privilege(self):
        matrix = PermissionMatrix()
        self.assertTrue(matrix.allows("WEB", "read"))
        self.assertFalse(matrix.allows("WEB", "write"))
        self.assertTrue(matrix.allows("MEMORY", "write"))
        self.assertTrue(matrix.allows("AUTOMATION", "action"))

    def test_trust_record_is_reconstructable(self):
        record = TrustArchitecture.record(
            request_id="r1",
            action="generate",
            reason="selected_model",
            knowledge_state=KnowledgeState.CAN_RESEARCH,
            source_count=2,
            model="remote",
        )
        self.assertTrue(record.reconstructable())
        self.assertEqual(record.event.request_id, "r1")

    def test_decentralization_path_is_explicit(self):
        self.assertTrue(DecentralizationPlan().validate())

    def test_mode_matrix_is_explicit(self):
        research = NexoModeMatrix.get("research")
        self.assertEqual(research.mode, "RESEARCH")
        self.assertEqual(research.internet, "sí")
        auto = NexoModeMatrix.get("auto")
        self.assertEqual(auto.tools, "dinámico")

    def test_master_test_battery_has_twelve_tests(self):
        self.assertTrue(MasterTestPlan.validate())
        self.assertEqual(len(MasterTestPlan.TESTS), 12)
        self.assertIn("import", MasterTestPlan.names())

    def test_success_criteria_are_explicit(self):
        criteria = SuccessCriteria()
        observed = criteria.required_capabilities
        self.assertTrue(criteria.validate_observed(observed))

    def test_export_contract_still_round_trips(self):
        bundle = ExportBundle.build(
            memory=[{"content": "nexo"}],
            preferences={},
            research=[],
            configuration={},
            metadata={},
        )
        self.assertTrue(bundle.verify())


if __name__ == "__main__":
    unittest.main()
