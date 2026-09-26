"""C-33 secondary replication peer as a FastAPI application."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import threading
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request

MAX_BODY = 2_000_000
STORE = Path(os.getenv("C33_PEER_STORE", "/tmp/c33-peer.json"))
LOCK = threading.Lock()


def _load() -> dict[str, dict[str, Any]]:
    try:
        data = json.loads(STORE.read_text("utf-8"))
        if isinstance(data, dict) and isinstance(data.get("messages"), dict):
            return data
    except (OSError, ValueError, TypeError):
        pass
    return {"messages": {}}


STATE = _load()


def _persist() -> None:
    STORE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STORE.with_suffix(".tmp")
    tmp.write_text(json.dumps(STATE, ensure_ascii=False, separators=(",", ":")), "utf-8")
    tmp.replace(STORE)


def _canonical(value: Any) -> Any:
    if isinstance(value, list):
        return [_canonical(item) for item in value]
    if isinstance(value, dict):
        return {key: _canonical(value[key]) for key in sorted(value)}
    return value


def _integrity() -> dict[str, Any]:
    with LOCK:
        messages = dict(STATE["messages"])
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
            "metadata": _canonical(msg.get("metadata") if isinstance(msg.get("metadata"), dict) else {}),
            "request_id": None if msg.get("request_id") is None else str(msg["request_id"]),
            "created_at": str(msg["created_at"]),
        }
        raw = json.dumps(
            _canonical(record),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        message_digest.update(raw)
        message_digest.update(b"\n")
    return {
        "total_messages": len(ids),
        "unique_message_ids": len(ids),
        "message_id_digest": id_digest.hexdigest(),
        "message_digest": message_digest.hexdigest(),
    }


app = FastAPI(title="C-33 Secondary Peer", version="1.0.0")


@app.get("/health")
async def health() -> dict[str, Any]:
    return {
        "status": "alive",
        "service": "C-33",
        "deployment_sha": os.getenv("RAILWAY_GIT_COMMIT_SHA", "peer"),
        "role": "secondary",
    }


@app.get("/ready")
async def ready() -> dict[str, Any]:
    return {
        "status": "ready",
        "service": "C-33",
        "deployment_sha": os.getenv("RAILWAY_GIT_COMMIT_SHA", "peer"),
        "database": "file",
        "peer_configured": False,
        "provider_count": 0,
    }


@app.get("/v1/replication/status")
async def replication_status() -> dict[str, Any]:
    return {
        "status": "ok",
        "deployment_sha": os.getenv("RAILWAY_GIT_COMMIT_SHA", "peer"),
        "backend_role": "secondary",
        "peer_url_configured": False,
        "peer_status": "NOT_CONFIGURED",
        "replication_pending": 0,
        **_integrity(),
        "quiesced": True,
    }


@app.post("/internal/replicate")
async def replicate(request: Request) -> dict[str, Any]:
    if request.headers.get("X-C33-Replication-Version", "") != "1":
        raise HTTPException(status_code=400, detail="unsupported_replication_version")
    try:
        length = int(request.headers.get("Content-Length", "0"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid_content_length") from exc
    if length < 0 or length > MAX_BODY:
        raise HTTPException(status_code=413, detail="replication_payload_too_large")

    raw = await request.body()
    if len(raw) > MAX_BODY:
        raise HTTPException(status_code=413, detail="replication_payload_too_large")

    secret = os.getenv("PEER_REPLICATION_SECRET", "").encode("utf-8")
    supplied = request.headers.get("X-C33-Replication-Signature", "").encode("utf-8")
    expected = hmac.new(secret, raw, hashlib.sha256).hexdigest().encode("utf-8")
    if not secret or not supplied or not hmac.compare_digest(supplied, expected):
        raise HTTPException(status_code=401, detail="invalid_replication_signature")

    try:
        body = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="invalid_replication_payload") from exc

    messages = body.get("messages")
    if not isinstance(messages, list):
        raise HTTPException(status_code=400, detail="invalid_replication_payload")
    if len(messages) > 100:
        raise HTTPException(status_code=413, detail="replication_batch_too_large")

    with LOCK:
        next_messages = dict(STATE["messages"])
        accepted: list[str] = []
        for message in messages:
            if not isinstance(message, dict) or not message.get("id"):
                raise HTTPException(status_code=400, detail="invalid_replication_message")
            message_id = str(message["id"])
            existing = next_messages.get(message_id)
            if existing is not None and existing != message:
                raise HTTPException(status_code=409, detail=f"message_id_conflict:{message_id}")
            if existing is None:
                next_messages[message_id] = message
            accepted.append(message_id)
        STATE["messages"] = next_messages
        _persist()

    return {
        "status": "ok",
        "accepted": len(accepted),
        "received": len(messages),
        "accepted_ids": accepted,
        "receipt_sha256": hashlib.sha256(raw).hexdigest(),
    }
