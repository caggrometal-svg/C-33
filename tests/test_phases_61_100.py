from __future__ import annotations

import unittest

from nexo.phases_61_100 import ClosureState, Nexo61To100


class Nexo61To100Tests(unittest.TestCase):
    def test_matrix_covers_61_through_100(self):
        self.assertTrue(Nexo61To100.validate())
        self.assertEqual(Nexo61To100.green_sections(), tuple(range(61, 101)))
        self.assertEqual(len(Nexo61To100.matrix()), 40)

    def test_no_red_state_exists(self):
        matrix = Nexo61To100.matrix()
        self.assertTrue(all(row["state"] in {ClosureState.GREEN.value, ClosureState.BLUE.value} for row in matrix))
        self.assertFalse(Nexo61To100.has_red())
        self.assertFalse(Nexo61To100.has_red(row["state"] for row in matrix))

    def test_every_section_has_named_acceptance(self):
        self.assertTrue(all(row["acceptance"].strip() for row in Nexo61To100.matrix()))
        self.assertEqual({row["number"] for row in Nexo61To100.matrix()}, set(range(61, 101)))

    def test_closed_external_capabilities_are_closed(self):
        self.assertIn("REAL_LOCAL_LLM", Nexo61To100.closed_capabilities())
        self.assertIn("PEER_REPLICATION_QUIESCED", Nexo61To100.closed_capabilities())
        self.assertEqual(Nexo61To100.blue_capabilities(), ())
        self.assertNotIn("RED", Nexo61To100.closed_capabilities())

    def test_boundary_is_strict(self):
        self.assertFalse(
            any(row["number"] < 61 or row["number"] > 100 for row in Nexo61To100.matrix())
        )


if __name__ == "__main__":
    unittest.main()
