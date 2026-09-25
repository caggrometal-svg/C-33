import unittest

from nexo.phases_61_100 import Nexo61To100


class SixCapabilityBoundaryTests(unittest.TestCase):
    def test_all_six_are_explicitly_tracked(self):
        required = {
            "REAL_LOCAL_LLM",
            "USER_EXPORT_IMPORT_ROUNDTRIP",
            "REAL_EXTERNAL_ACTIONS",
            "FULL_PORTABILITY",
            "FULL_DECENTRALIZATION",
            "PEER_REPLICATION_QUIESCED",
        }
        self.assertTrue(required.issubset(set(Nexo61To100.BLUE_CAPABILITIES)))

    def test_no_red_state(self):
        self.assertFalse(Nexo61To100.has_red())


if __name__ == "__main__":
    unittest.main()
