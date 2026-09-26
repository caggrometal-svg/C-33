"""Create an ephemeral C-33 CI identity session without exposing server/provider secrets."""

from __future__ import annotations

import base64
import json
import sys
from urllib.parse import urljoin

import httpx
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def create_session(base_url: str, device_id: str) -> dict[str, str]:
    base = str(base_url).rstrip("/") + "/"
    key = ec.generate_private_key(ec.SECP256R1())
    numbers = key.public_key().public_numbers()
    public_key = {
        "kty": "EC",
        "crv": "P-256",
        "x": b64url(numbers.x.to_bytes(32, "big")),
        "y": b64url(numbers.y.to_bytes(32, "big")),
    }

    with httpx.Client(timeout=15.0) as client:
        challenge = client.post(urljoin(base, "v1/auth/challenge"))
        challenge.raise_for_status()
        challenge_value = str(challenge.json().get("challenge", "")).strip()
        if not challenge_value:
            raise RuntimeError("missing_auth_challenge")

        der = key.sign(challenge_value.encode("utf-8"), ec.ECDSA(hashes.SHA256()))
        r, s = decode_dss_signature(der)
        raw_signature = r.to_bytes(32, "big") + s.to_bytes(32, "big")

        session = client.post(
            urljoin(base, "v1/auth/session"),
            json={
                "challenge": challenge_value,
                "device_id": str(device_id),
                "public_key": public_key,
                "signature": b64url(raw_signature),
            },
        )
        session.raise_for_status()
        data = session.json()
        token = str(data.get("session_token", "")).strip()
        identity = str(data.get("identity_id", "")).strip()
        if not token or not identity:
            raise RuntimeError("incomplete_auth_session")
        return {
            "authorization": "Bearer " + token,
            "identity_id": identity,
            "device_id": str(device_id),
        }


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("usage: c33_ci_auth.py BASE_URL DEVICE_ID")
    print(json.dumps(create_session(sys.argv[1], sys.argv[2]), separators=(",", ":")))
