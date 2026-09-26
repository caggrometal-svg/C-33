"""Server-side identity authentication for C-33/NEXO.

The client proves possession of a P-256 private key. The server derives the
identity from the public key and issues a short-lived HMAC-signed Bearer
session. No API/provider secret is shipped to the Android client.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass
from typing import Any

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature


class IdentityAuthError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class IdentitySession:
    identity_id: str
    device_id: str
    expires_at: int
    session_id: str


def _b64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64url_decode(value: str) -> bytes:
    try:
        padding = "=" * (-len(value) % 4)
        return base64.urlsafe_b64decode((value + padding).encode("ascii"))
    except (ValueError, UnicodeEncodeError) as exc:
        raise IdentityAuthError("invalid_base64url") from exc


def _canonical_public_jwk(public_key: dict[str, Any]) -> dict[str, str]:
    if not isinstance(public_key, dict):
        raise IdentityAuthError("public_key_required")
    normalized = {
        "kty": str(public_key.get("kty", "")),
        "crv": str(public_key.get("crv", "")),
        "x": str(public_key.get("x", "")),
        "y": str(public_key.get("y", "")),
    }
    if normalized["kty"] != "EC" or normalized["crv"] != "P-256":
        raise IdentityAuthError("unsupported_public_key")
    x = _b64url_decode(normalized["x"])
    y = _b64url_decode(normalized["y"])
    if len(x) != 32 or len(y) != 32:
        raise IdentityAuthError("invalid_public_key_coordinates")
    try:
        ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), b"\x04" + x + y)
    except ValueError as exc:
        raise IdentityAuthError("invalid_public_key") from exc
    return normalized


def identity_id_from_public_key(public_key: dict[str, Any]) -> str:
    normalized = _canonical_public_jwk(public_key)
    raw = json.dumps(normalized, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "c33_" + hashlib.sha256(raw).hexdigest()[:32]


def issue_challenge(secret_keys: tuple[str, ...], *, ttl_seconds: int = 120) -> tuple[str, int]:
    if not secret_keys:
        raise IdentityAuthError("server_auth_key_missing")
    expires_at = int(time.time()) + max(30, min(int(ttl_seconds), 300))
    payload = {
        "v": 1,
        "typ": "challenge",
        "nonce": secrets.token_urlsafe(24),
        "iat": expires_at - max(30, min(int(ttl_seconds), 300)),
        "exp": expires_at,
    }
    encoded = _b64url_encode(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    signature = hmac.new(secret_keys[0].encode("utf-8"), encoded.encode("ascii"), hashlib.sha256).digest()
    return encoded + "." + _b64url_encode(signature), expires_at


def _verify_signed_token(token: str, secret_keys: tuple[str, ...], expected_type: str) -> dict[str, Any]:
    if not secret_keys:
        raise IdentityAuthError("server_auth_key_missing")
    parts = str(token or "").split(".")
    if len(parts) != 2:
        raise IdentityAuthError("invalid_auth_token")
    encoded, supplied_signature = parts
    supplied = _b64url_decode(supplied_signature)
    payload: dict[str, Any] | None = None
    valid = False
    for secret in secret_keys:
        expected = hmac.new(secret.encode("utf-8"), encoded.encode("ascii"), hashlib.sha256).digest()
        if hmac.compare_digest(supplied, expected):
            valid = True
            break
    if not valid:
        raise IdentityAuthError("invalid_auth_signature")
    try:
        raw = _b64url_decode(encoded)
        parsed = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise IdentityAuthError("invalid_auth_payload") from exc
    if not isinstance(parsed, dict) or parsed.get("v") != 1 or parsed.get("typ") != expected_type:
        raise IdentityAuthError("invalid_auth_payload")
    try:
        expires_at = int(parsed["exp"])
    except (KeyError, TypeError, ValueError) as exc:
        raise IdentityAuthError("invalid_auth_expiry") from exc
    if expires_at <= int(time.time()):
        raise IdentityAuthError("auth_token_expired")
    return parsed


def verify_challenge(challenge: str, secret_keys: tuple[str, ...]) -> dict[str, Any]:
    return _verify_signed_token(challenge, secret_keys, "challenge")


def verify_client_signature(public_key: dict[str, Any], challenge: str, signature_b64url: str) -> None:
    normalized = _canonical_public_jwk(public_key)
    x = _b64url_decode(normalized["x"])
    y = _b64url_decode(normalized["y"])
    try:
        public = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), b"\x04" + x + y)
    except ValueError as exc:
        raise IdentityAuthError("invalid_public_key") from exc
    raw_signature = _b64url_decode(signature_b64url)
    if len(raw_signature) != 64:
        raise IdentityAuthError("invalid_client_signature")
    r = int.from_bytes(raw_signature[:32], "big")
    s = int.from_bytes(raw_signature[32:], "big")
    der_signature = encode_dss_signature(r, s)
    try:
        public.verify(der_signature, challenge.encode("utf-8"), ec.ECDSA(hashes.SHA256()))
    except ValueError as exc:
        raise IdentityAuthError("client_signature_invalid") from exc


def issue_session(
    secret_keys: tuple[str, ...],
    *,
    identity_id: str,
    device_id: str,
    ttl_seconds: int = 43_200,
) -> tuple[str, int]:
    identity_id = str(identity_id or "").strip()
    device_id = str(device_id or "").strip()
    if not identity_id:
        raise IdentityAuthError("identity_id_required")
    if not device_id:
        raise IdentityAuthError("device_id_required")
    if len(identity_id) > 128 or len(device_id) > 256:
        raise IdentityAuthError("identity_field_too_long")
    expires_at = int(time.time()) + max(300, min(int(ttl_seconds), 86_400))
    payload = {
        "v": 1,
        "typ": "session",
        "sid": secrets.token_urlsafe(18),
        "sub": identity_id,
        "did": device_id,
        "iat": int(time.time()),
        "exp": expires_at,
    }
    encoded = _b64url_encode(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    signature = hmac.new(secret_keys[0].encode("utf-8"), encoded.encode("ascii"), hashlib.sha256).digest()
    return encoded + "." + _b64url_encode(signature), expires_at


def verify_session(session_token: str, secret_keys: tuple[str, ...]) -> IdentitySession:
    payload = _verify_signed_token(session_token, secret_keys, "session")
    identity_id = str(payload.get("sub", "")).strip()
    device_id = str(payload.get("did", "")).strip()
    session_id = str(payload.get("sid", "")).strip()
    if not identity_id or not device_id or not session_id:
        raise IdentityAuthError("invalid_session_claims")
    return IdentitySession(
        identity_id=identity_id,
        device_id=device_id,
        expires_at=int(payload["exp"]),
        session_id=session_id,
    )


def session_from_authorization_header(authorization: str | None, secret_keys: tuple[str, ...]) -> IdentitySession:
    value = str(authorization or "").strip()
    scheme, _, token = value.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise IdentityAuthError("authorization_required")
    return verify_session(token.strip(), secret_keys)


def assert_identity_matches(session: IdentitySession, requested_user_id: str | None) -> None:
    requested = str(requested_user_id or "").strip()
    if not requested:
        raise IdentityAuthError("user_id_required")
    if not hmac.compare_digest(session.identity_id, requested):
        raise IdentityAuthError("identity_mismatch")


def assert_bundle_belongs_to_identity(session: IdentitySession, bundle: dict[str, Any]) -> None:
    if not isinstance(bundle, dict):
        raise IdentityAuthError("invalid_bundle")
    bundle_identity = str(bundle.get("identity_id") or "").strip()
    if bundle_identity and not hmac.compare_digest(session.identity_id, bundle_identity):
        raise IdentityAuthError("identity_mismatch")
    messages = bundle.get("messages", [])
    if not isinstance(messages, list):
        raise IdentityAuthError("invalid_bundle_messages")
    for message in messages:
        if not isinstance(message, dict):
            raise IdentityAuthError("invalid_bundle_message")
        message_user_id = str(message.get("user_id") or "").strip()
        if not hmac.compare_digest(session.identity_id, message_user_id):
            raise IdentityAuthError("cross_identity_import")
