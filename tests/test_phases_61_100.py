from __future__ import annotations

import unittest

from nexo.phases_61_100 import ContractState, Nexo61To100, RuntimeState


class Nexo61To100Tests(unittest.TestCase):
    def test_matrix_covers_61_through_100(self):
        self.assertTrue(Nexo61To100.validate())
        self.assertEqual(Nexo61To100.contract_green_sections(), tuple(range(61, 101)))
        self.assertEqual(Nexo61To100.green_sections(), tuple(range(61, 101)))
        self.assertEqual(len(Nexo61To100.matrix()), 40)

    def test_runtime_truth_is_not_inferred(self):
        self.assertEqual(Nexo61To100.runtime_green_sections(), ())
        self.assertEqual(
            Nexo61To100.not_applicable_runtime_sections(),
            tuple(range(61, 73)),
        )
        self.assertEqual(
            Nexo61To100.runtime_blue_sections(),
            tuple(range(73, 101)),
        )

    def test_no_red_state_exists(self):
        matrix = Nexo61To100.matrix()
        self.assertTrue(
            all(
                row["contract_state"] in {ContractState.GREEN.value, ContractState.BLUE.value}
                for row in matrix
            )
        )
        self.assertTrue(
            all(
                row["runtime_state"]
                in {
                    RuntimeState.GREEN.value,
                    RuntimeState.BLUE.value,
                    RuntimeState.NOT_APPLICABLE.value,
                }
                for row in matrix
            )
        )
        self.assertFalse(Nexo61To100.has_red())

    def test_no_runtime_green_without_current_evidence(self):
        for row in Nexo61To100.matrix():
            if row["runtime_state"] == RuntimeState.GREEN.value:
                self.assertIn("current-cycle runtime", row["runtime_evidence"])

    def test_every_section_has_named_acceptance_and_runtime_evidence(self):
        for row in Nexo61To100.matrix():
            self.assertTrue(row["acceptance"].strip())
            self.assertTrue(row["runtime_evidence"].strip())
        self.assertEqual(
            {row["number"] for row in Nexo61To100.matrix()},
            set(range(61, 101)),
        )

    def test_capability_states_are_not_claimed_closed(self):
        self.assertEqual(Nexo61To100.closed_capabilities(), ())
        self.assertIn("REAL_LOCAL_LLM", Nexo61To100.blue_capabilities())
        self.assertIn("PEER_REPLICATION_QUIESCED", Nexo61To100.blue_capabilities())
        self.assertIn(
            "REAL_LOCAL_LLM_CONTRACT",
            Nexo61To100.contractual_capabilities(),
        )

    def test_matrix_serialization_contains_both_axes(self):
        row = Nexo61To100.matrix()[0]
        self.assertEqual(row["contract_state"], ContractState.GREEN.value)
        self.assertIn("runtime_state", row)
        self.assertIn("runtime_evidence", row)

    def test_boundary_is_strict(self):
        self.assertFalse(
            any(row["number"] < 61 or row["number"] > 100 for row in Nexo61To100.matrix())
        )


if __name__ == "__main__":
    unittest.main()
