#!/usr/bin/env python3
"""Minimal C-33 replication peer using only the Python standard library."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

MAX_BODY = 2_000_000
STORE = Path(os.getenv("C33_PEER_STORE", "/tmp/c33-peer.json"))
LOCK = threading.Lock()


def load_state() -> dict[str, dict[str, Any]]:
    try:
        data = json.loads(STORE.read_text("utf-8"))
        if isinstance(data, dict) and isinstance(data.get("messages"), dict):
            return data
    except (OSError, ValueError, TypeError):
        pass
    return {"messages": {}}


state = load_state()


def persist() -> None:
    STORE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STORE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, separators=(",", ":")), "utf-8")
    tmp.replace(STORE)


def canonical(value: Any) -> Any:
    if isinstance(value, list):
        return [canonical(item) for item in value]
    if isinstance(value, dict):
        return {key: canonical(value[key]) for key in sorted(value)}
    return value


def integrity() -> dict[str, Any]:
    with LOCK:
        messages = dict(state["messages"])
    ids = sorted(messages)
    id_digest = hashlib.sha256()
    message_digest = hashlib.sha256()
    for message_id in ids:
        id_digest.update(message_id.encode("utf-8"))
        id_digest.update(b"\n")
        msg = messages[message_id]
        record = {
            "id": str(msg["id"]),
            "conversation_id": str(msg["conversation_id"]),
            "user_id": str(msg["user_id"]),
            "seq": int(msg["seq"]),
            "role": str(msg["role"]),
            "content": str(msg["content"]),
            "metadata": canonical(msg.get("metadata") if isinstance(msg.get("metadata"), dict) else {}),
            "request_id": None if msg.get("request_id") is None else str(msg["request_id"]),
            "created_at": str(msg["created_at"]),
        }
        payload = json.dumps(canonical(record), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        message_digest.update(payload)
        message_digest.update(b"\n")
    return {
        "total_messages": len(ids),
        "unique_message_ids": len(ids),
        "message_id_digest": id_digest.hexdigest(),
        "message_digest": message_digest.hexdigest(),
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "C33Peer/1.0"

    def log_message(self, format: str, *args: object) -> None:
        return

    def send_json(self, status: int, body: dict[str, Any]) -> None:
        raw = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:
        if self.path == "/health":
            self.send_json(200, {
                "status": "alive",
                "service": "C-33",
                "deployment_sha": os.getenv("RAILWAY_GIT_COMMIT_SHA", "peer"),
                "role": "secondary",
            })
            return
        if self.path == "/ready":
            self.send_json(200, {
                "status": "ready",
                "service": "C-33",
                "deployment_sha": os.getenv("RAILWAY_GIT_COMMIT_SHA", "peer"),
                "database": "file",
                "peer_configured": False,
                "provider_count": 0,
            })
            return
        if self.path == "/v1/replication/status":
            self.send_json(200, {
                "status": "ok",
                "deployment_sha": os.getenv("RAILWAY_GIT_COMMIT_SHA", "peer"),
                "backend_role": "secondary",
                "peer_url_configured": False,
                "peer_status": "NOT_CONFIGURED",
                "replication_pending": 0,
                **integrity(),
                "quiesced": True,
            })
            return
        self.send_json(404, {"detail": "not_found"})

    def do_POST(self) -> None:
        if self.path != "/internal/replicate":
            self.send_json(404, {"detail": "not_found"})
            return
        if self.headers.get("X-C33-Replication-Version", "") != "1":
            self.send_json(400, {"detail": "unsupported_replication_version"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self.send_json(400, {"detail": "invalid_content_length"})
            return
        if length < 0 or length > MAX_BODY:
            self.send_json(413, {"detail": "replication_payload_too_large"})
            return
        raw = self.rfile.read(length)
        secret = os.getenv("PEER_REPLICATION_SECRET", "").encode("utf-8")
        supplied = self.headers.get("X-C33-Replication-Signature", "").encode("utf-8")
        expected = hmac.new(secret, raw, hashlib.sha256).hexdigest().encode("utf-8")
        if not secret or not supplied or not hmac.compare_digest(supplied, expected):
            self.send_json(401, {"detail": "invalid_replication_signature"})
            return
        try:
            body = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            self.send_json(400, {"detail": "invalid_replication_payload"})
            return
        messages = body.get("messages")
        if not isinstance(messages, list):
            self.send_json(400, {"detail": "invalid_replication_payload"})
            return
        if len(messages) > 100:
            self.send_json(413, {"detail": "replication_batch_too_large"})
            return
        accepted: list[str] = []
        with LOCK:
            next_messages = dict(state["messages"])
            for message in messages:
                if not isinstance(message, dict) or not message.get("id"):
                    self.send_json(400, {"detail": "invalid_replication_message"})
                    return
                message_id = str(message["id"])
                existing = next_messages.get(message_id)
                if existing is not None and existing != message:
                    self.send_json(409, {"detail": f"message_id_conflict:{message_id}"})
                    return
                if existing is None:
                    next_messages[message_id] = message
                accepted.append(message_id)
            state["messages"] = next_messages
            persist()
        self.send_json(200, {
            "status": "ok",
            "accepted": len(accepted),
            "received": len(messages),
            "accepted_ids": accepted,
            "receipt_sha256": hashlib.sha256(raw).hexdigest(),
        })


def main() -> None:
    port = int(os.getenv("PORT", "8000"))
    STORE.parent.mkdir(parents=True, exist_ok=True)
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()


if __name__ == "__main__":
    main()
