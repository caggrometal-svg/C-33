from __future__ import annotations

import unittest

from nexo.phases_31_40 import (
    ActionModePolicy,
    AutoModeRouter,
    ChatModePlan,
    CooperationPlan,
    DeviceEndpoint,
    LocalRemoteCooperationPolicy,
    MemoryModePlan,
    NexoMode,
    PortableBundleContract,
    PortableIdentity,
    PrivacyByDefaultPolicy,
    ResearchPlan,
    ReplicationManifest,
)
from nexo.phases_23_30 import ExportBundle, NexoProtocol


class Phase31To40Tests(unittest.TestCase):
    def test_multidevice_manifest_and_protocol(self):
        identity = PortableIdentity("user-1")
        device = DeviceEndpoint("android-1", "android")
        manifest = ReplicationManifest(identity, (device,))
        self.assertTrue(manifest.validate())
        envelope = device.envelope("Request", {"message": "hola"})
        self.assertEqual(envelope["protocol"], "NEXO")
        self.assertEqual(envelope["kind"], "Request")

    def test_portable_bundle_round_trip_and_checksum(self):
        bundle = ExportBundle.build(
            memory=[{"content": "x"}],
            preferences={"tone": "neutral"},
            research=[{"question": "q"}],
            configuration={"version": "1"},
            metadata={"identity_id": "user-1"},
        )
        contract = PortableBundleContract()
        self.assertTrue(contract.validate_export(bundle))
        imported = contract.import_payload(bundle.to_dict())
        self.assertEqual(imported.checksum, bundle.checksum)
        self.assertTrue(imported.verify())

    def test_cooperation_keeps_private_work_local(self):
        plan = LocalRemoteCooperationPolicy.plan("analiza este documento privado")
        self.assertEqual(plan.remote_tasks, ())
        self.assertIn("memory", plan.local_tasks)
        self.assertEqual(plan.reason, "private_by_default")

    def test_cooperation_allows_heavy_remote_work_for_public_research(self):
        plan = LocalRemoteCooperationPolicy.plan("investiga y compara fuentes")
        self.assertIn("research", plan.remote_tasks)
        self.assertEqual(plan.reason, "heavy_remote_work_allowed")

    def test_private_by_default_blocks_network(self):
        decision = PrivacyByDefaultPolicy().decide("información confidencial")
        self.assertTrue(decision.local_required)
        self.assertFalse(decision.allow_network)

    def test_current_task_may_require_network(self):
        decision = PrivacyByDefaultPolicy().decide("precio actual")
        self.assertFalse(decision.local_required)
        self.assertTrue(decision.allow_network)

    def test_research_mode_plan_is_bounded(self):
        self.assertTrue(ResearchPlan().validate())
        self.assertEqual(len(ResearchPlan().steps), 8)

    def test_memory_mode_priorities_are_explicit(self):
        self.assertTrue(MemoryModePlan().validate())

    def test_action_mode_requires_authorization(self):
        policy = ActionModePolicy()
        denied = policy.decision(action="send_email", authorized=False)
        self.assertFalse(denied.allows("send_email"))
        allowed = policy.decision(action="send_email", authorized=True, scope=("send_email",))
        self.assertTrue(allowed.allows("send_email"))
        outside = policy.decision(action="delete_data", authorized=True, scope=("send_email",))
        self.assertFalse(outside.allows("delete_data"))

    def test_chat_mode_does_not_use_tools(self):
        self.assertTrue(ChatModePlan().validate())

    def test_auto_mode_selects_declared_modes(self):
        self.assertEqual(
            AutoModeRouter.choose("investiga esto actualmente").mode,
            NexoMode.RESEARCH,
        )
        self.assertEqual(
            AutoModeRouter.choose("recuerda lo que te dije").mode,
            NexoMode.MEMORY,
        )
        self.assertEqual(
            AutoModeRouter.choose("crea una tarea y programa el envío").mode,
            NexoMode.ACTION,
        )
        self.assertEqual(
            AutoModeRouter.choose("hola, conversemos").mode,
            NexoMode.CHAT,
        )
        self.assertEqual(
            AutoModeRouter.choose("esto es privado y confidencial").mode,
            NexoMode.LOCAL,
        )

    def test_auto_mode_plan_contains_mode_specific_contract(self):
        research = AutoModeRouter.plan("investiga fuentes")
        self.assertEqual(research["mode"], "RESEARCH")
        self.assertEqual(len(research["plan"]), 8)
        action = AutoModeRouter.plan("ejecuta esta acción")
        self.assertTrue(action["authorization_required"])
        chat = AutoModeRouter.plan("hola")
        self.assertTrue(chat["chat"])


if __name__ == "__main__":
    unittest.main()
