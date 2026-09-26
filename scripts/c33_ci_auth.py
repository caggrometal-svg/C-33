"""Create a resilient ephemeral C-33 CI identity session without exposing server/provider secrets."""

from __future__ import annotations

import base64
import json
import sys
import time
from typing import Callable

import httpx
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _post_json(
    client: httpx.Client,
    url: str,
    *,
    payload: dict[str, object] | None = None,
    attempts: int = 6,
) -> httpx.Response:
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            response = client.post(url, json=payload)
            if response.status_code < 500 and response.status_code != 429:
                response.raise_for_status()
                return response
            last_error = RuntimeError(f"transient_http_{response.status_code}: {response.text[:300]}")
        except (httpx.RequestError, httpx.HTTPStatusError) as exc:
            last_error = exc
        if attempt < attempts:
            time.sleep(min(6.0, 2 ** (attempt - 1)))
    raise RuntimeError(f"authentication_request_failed: {type(last_error).__name__}: {last_error}") from last_error


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

    timeout = httpx.Timeout(15.0, connect=6.0, read=15.0, write=10.0)
    with httpx.Client(timeout=timeout) as client:
        challenge = _post_json(client, base + "v1/auth/challenge")
        challenge_value = str(challenge.json().get("challenge", "")).strip()
        if not challenge_value:
            raise RuntimeError("missing_auth_challenge")

        der = key.sign(challenge_value.encode("utf-8"), ec.ECDSA(hashes.SHA256()))
        r, s = decode_dss_signature(der)
        raw_signature = r.to_bytes(32, "big") + s.to_bytes(32, "big")

        session = _post_json(
            client,
            base + "v1/auth/session",
            payload={
                "challenge": challenge_value,
                "device_id": str(device_id),
                "public_key": public_key,
                "signature": b64url(raw_signature),
            },
        )
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
