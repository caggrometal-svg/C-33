import hashlib
import os
import sys
import unittest

os.environ.setdefault("PORT", "8080")
os.environ.setdefault("SECRET_KEYS", "test-secret-key-123456")
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("AI_ZERO_COST_MODE", "true")
os.environ.setdefault("MODEL_BASE_URL", "https://vireonix.ai/v1")
os.environ.setdefault("REQUIRE_PROVIDER_REDUNDANCY", "true")
sys.path.insert(0, "src")

from resilience.state import PostgresState


class FakeTransaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class FakeConn:
    def __init__(self, row=None):
        self.row = row
        self.executed = []

    def transaction(self):
        return FakeTransaction()

    async def fetchrow(self, query, *args):
        return self.row

    async def execute(self, query, *args):
        self.executed.append((query, args))


class FakeAcquire:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, exc_type, exc, tb):
        return False


class FakePool:
    def __init__(self, conn):
        self.conn = conn

    def acquire(self):
        return FakeAcquire(self.conn)


class PeerRebootstrapTests(unittest.IsolatedAsyncioTestCase):
    def test_peer_fingerprint_is_stable_and_host_case_normalized(self):
        a = PostgresState.replication_peer_fingerprint("https://Peer.Example.test/path/")
        b = PostgresState.replication_peer_fingerprint("https://peer.example.test/path")
        self.assertEqual(a, b)
        self.assertEqual(len(a), hashlib.sha256().digest_size * 2)

    async def test_first_peer_registration_requeues_everything(self):
        conn = FakeConn(row=None)
        state = PostgresState(FakePool(conn))
        result = await state.ensure_replication_peer("https://peer.example.test")

        self.assertTrue(result["changed"])
        self.assertEqual(len(conn.executed), 2)
        self.assertIn("INSERT INTO c33_replication_meta", conn.executed[0][0])
        self.assertIn("SET synced_at=NULL", conn.executed[1][0])

    async def test_same_peer_does_not_requeue(self):
        fp = PostgresState.replication_peer_fingerprint("https://peer.example.test")
        conn = FakeConn(row={"peer_url": "https://peer.example.test", "peer_fingerprint": fp})
        state = PostgresState(FakePool(conn))
        result = await state.ensure_replication_peer("https://peer.example.test/")

        self.assertFalse(result["changed"])
        self.assertEqual(conn.executed, [])

    async def test_peer_change_requeues_and_resets_attempts(self):
        old_fp = PostgresState.replication_peer_fingerprint("https://old.example.test")
        conn = FakeConn(row={"peer_url": "https://old.example.test", "peer_fingerprint": old_fp})
        state = PostgresState(FakePool(conn))
        result = await state.ensure_replication_peer("https://new.example.test")

        self.assertTrue(result["changed"])
        self.assertEqual(len(conn.executed), 2)
        self.assertIn("UPDATE c33_replication_meta", conn.executed[0][0])
        self.assertIn("attempts=0", conn.executed[1][0])
        self.assertIn("last_error=NULL", conn.executed[1][0])


if __name__ == "__main__":
    unittest.main()
