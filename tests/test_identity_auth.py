import base64
import json
import unittest
from datetime import datetime, timezone

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature

from nexo.identity import (
    IdentityAuthError,
    assert_bundle_belongs_to_identity,
    assert_identity_matches,
    identity_id_from_public_key,
    issue_challenge,
    issue_session,
    session_from_authorization_header,
    verify_challenge,
    verify_client_signature,
    verify_session,
)
from resilience.state import PostgresState


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def public_jwk(key) -> dict[str, str]:
    numbers = key.public_key().public_numbers()
    return {
        "kty": "EC",
        "crv": "P-256",
        "x": b64url(numbers.x.to_bytes(32, "big")),
        "y": b64url(numbers.y.to_bytes(32, "big")),
    }


class IdentityAuthTests(unittest.TestCase):
    SECRET = ("A" * 48, "B" * 48)

    def setUp(self):
        self.key_a = ec.generate_private_key(ec.SECP256R1())
        self.key_b = ec.generate_private_key(ec.SECP256R1())
        self.jwk_a = public_jwk(self.key_a)
        self.jwk_b = public_jwk(self.key_b)
        self.identity_a = identity_id_from_public_key(self.jwk_a)
        self.identity_b = identity_id_from_public_key(self.jwk_b)

    def test_challenge_and_client_proof(self):
        challenge, expires_at = issue_challenge(self.SECRET)
        self.assertGreater(expires_at, int(datetime.now(timezone.utc).timestamp()))
        verified = verify_challenge(challenge, self.SECRET)
        self.assertEqual(verified["typ"], "challenge")

        der = self.key_a.sign(challenge.encode("utf-8"), ec.ECDSA(hashes.SHA256()))
        r, s = decode_dss_signature(der)
        raw = r.to_bytes(32, "big") + s.to_bytes(32, "big")
        verify_client_signature(self.jwk_a, challenge, b64url(raw))

    def test_tampered_challenge_or_signature_is_rejected(self):
        challenge, _ = issue_challenge(self.SECRET)
        replacement = "A" if challenge[-1] != "A" else "B"
        tampered_challenge = challenge[:-1] + replacement
        with self.assertRaises(IdentityAuthError):
            verify_challenge(tampered_challenge, self.SECRET)
        with self.assertRaisesRegex(IdentityAuthError, "client_signature_invalid"):
            verify_client_signature(self.jwk_a, challenge, b64url(b"0" * 64))

    def test_session_is_bound_to_identity_and_device(self):
        token, _ = issue_session(
            self.SECRET,
            identity_id=self.identity_a,
            device_id="device-a",
        )
        session = verify_session(token, self.SECRET)
        self.assertEqual(session.identity_id, self.identity_a)
        self.assertEqual(session.device_id, "device-a")
        session2 = session_from_authorization_header("Bearer " + token, self.SECRET)
        self.assertEqual(session2.session_id, session.session_id)

    def test_cross_identity_access_is_rejected(self):
        token, _ = issue_session(
            self.SECRET,
            identity_id=self.identity_a,
            device_id="device-a",
        )
        session = verify_session(token, self.SECRET)
        assert_identity_matches(session, self.identity_a)
        with self.assertRaisesRegex(IdentityAuthError, "identity_mismatch"):
            assert_identity_matches(session, self.identity_b)

    def test_cross_identity_import_is_rejected(self):
        token, _ = issue_session(
            self.SECRET,
            identity_id=self.identity_a,
            device_id="device-a",
        )
        session = verify_session(token, self.SECRET)
        bundle = {
            "user_id": self.identity_a,
            "identity_id": self.identity_a,
            "messages": [
                {"user_id": self.identity_b, "content": "private B data"}
            ],
        }
        with self.assertRaisesRegex(IdentityAuthError, "cross_identity_import"):
            assert_bundle_belongs_to_identity(session, bundle)

    def test_tampered_session_is_rejected(self):
        token, _ = issue_session(
            self.SECRET,
            identity_id=self.identity_a,
            device_id="device-a",
        )
        encoded, signature = token.split(".", 1)
        replacement = "A" if signature[0] != "A" else "B"
        tampered = encoded + "." + replacement + signature[1:]
        with self.assertRaises(IdentityAuthError):
            verify_session(tampered, self.SECRET)

    def test_identity_is_deterministic_per_public_key(self):
        self.assertEqual(
            self.identity_a,
            identity_id_from_public_key(json.loads(json.dumps(self.jwk_a))),
        )
        self.assertNotEqual(self.identity_a, self.identity_b)


class _FakeConnection:
    def __init__(self):
        self.calls = []

    async def fetch(self, query, *args):
        self.calls.append((query, args))
        if len(args) >= 2 and args[1] == "identity-a":
            return [{"role": "user", "content": "A private message"}]
        return []

    async def fetchrow(self, query, *args):
        self.calls.append((query, args))
        if len(args) >= 3 and args[2] == "identity-a":
            return {
                "id": "00000000-0000-0000-0000-000000000001",
                "conversation_id": "conversation-1",
                "user_id": "identity-a",
                "seq": 1,
                "role": "assistant",
                "content": "A private reply",
                "metadata": {},
                "request_id": "request-1",
                "created_at": datetime.now(timezone.utc),
            }
        return None


class _FakeAcquire:
    def __init__(self, connection):
        self.connection = connection

    async def __aenter__(self):
        return self.connection

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakePool:
    def __init__(self):
        self.connection = _FakeConnection()

    def acquire(self):
        return _FakeAcquire(self.connection)


class StorageIdentityScopeTests(unittest.IsolatedAsyncioTestCase):
    async def test_storage_queries_are_identity_scoped(self):
        pool = _FakePool()
        state = PostgresState(pool)

        context_a = await state.conversation_context("conversation-1", "identity-a", limit=12)
        context_b = await state.conversation_context("conversation-1", "identity-b", limit=12)
        replay_a = await state.existing_assistant_for_request("conversation-1", "request-1", "identity-a")
        replay_b = await state.existing_assistant_for_request("conversation-1", "request-1", "identity-b")

        self.assertEqual(context_a[0]["content"], "A private message")
        self.assertEqual(context_b, [])
        self.assertIsNotNone(replay_a)
        self.assertIsNone(replay_b)

        queries = [query for query, _ in pool.connection.calls]
        self.assertTrue(any("user_id=$2" in query for query in queries))
        self.assertTrue(any("user_id=$3" in query for query in queries))


if __name__ == "__main__":
    unittest.main()
