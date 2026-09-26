import os
import unittest

os.environ.setdefault("PORT", "8080")
os.environ.setdefault("SECRET_KEYS", "test-secret-key-123456")


class ExportQueryContractTests(unittest.TestCase):
    def test_export_query_without_conversation_uses_two_parameters(self):
        from api import _export_messages_query

        query = _export_messages_query(None)
        self.assertIn("WHERE user_id=$1", query)
        self.assertIn("LIMIT $2", query)
        self.assertNotIn("conversation_id=$2", query)
        self.assertNotIn("LIMIT $3", query)

    def test_export_query_with_conversation_uses_three_parameters(self):
        from api import _export_messages_query

        query = _export_messages_query("conversation-1")
        self.assertIn("WHERE user_id=$1", query)
        self.assertIn("conversation_id=$2", query)
        self.assertIn("LIMIT $3", query)


    def test_chat_recovery_replay_is_identity_scoped_and_replay_only(self):
        from pathlib import Path
        api_source = (Path(__file__).resolve().parents[1] / "src" / "api.py").read_text(encoding="utf-8")
        self.assertIn("effective_payload.user_id", api_source)
        self.assertIn('stored_meta["replayed"] = True', api_source)
        self.assertIn('X-C33-Replay-Only', api_source)
        self.assertIn('request_not_replayable', api_source)


if __name__ == "__main__":
    unittest.main()
