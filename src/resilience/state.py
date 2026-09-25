"""Durable distributed state: conversations, memory, circuits and replication outbox."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import random
import re
import time
import unicodedata
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import asyncpg
import httpx

from memory.store import MemoryEntry

_MAX_REPLICATION_TEXT_CHARS = 20_000
_MAX_REPLICATION_ID_CHARS = 256

class ReplicationConflictError(ValueError):
    """Raised when a replicated message collides with different durable state."""


def _normalize_created_at(value: Any) -> str:
    """Canonicalize imported timestamps before they reach asyncpg."""
    if value is None or value == "":
        return datetime.now(timezone.utc).isoformat()
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        raw = value.strip()
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(raw)
        except ValueError as exc:
            raise ValueError("created_at_invalid") from exc
    else:
        raise ValueError("created_at_must_be_string")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat()


SCHEMA = r'''
CREATE TABLE IF NOT EXISTS c33_conversation_heads (
    conversation_id TEXT PRIMARY KEY,
    next_seq BIGINT NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS c33_messages (
    id UUID PRIMARY KEY,
    conversation_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    seq BIGINT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('user','assistant','system')),
    content TEXT NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    request_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (conversation_id, seq),
    UNIQUE (conversation_id, id)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_c33_messages_request_role
    ON c33_messages(conversation_id, request_id, role)
    WHERE request_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_c33_messages_conversation
    ON c33_messages(conversation_id, seq DESC);
CREATE INDEX IF NOT EXISTS idx_c33_messages_user_created
    ON c33_messages(user_id, created_at DESC);

CREATE TABLE IF NOT EXISTS c33_replication_outbox (
    message_id UUID PRIMARY KEY REFERENCES c33_messages(id) ON DELETE CASCADE,
    attempts INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    synced_at TIMESTAMPTZ,
    last_error TEXT
);
CREATE INDEX IF NOT EXISTS idx_c33_outbox_pending
    ON c33_replication_outbox(next_attempt_at)
    WHERE synced_at IS NULL;

CREATE TABLE IF NOT EXISTS c33_circuit_breakers (
    provider_id TEXT PRIMARY KEY,
    state TEXT NOT NULL CHECK (state IN ('CLOSED','OPEN','HALF_OPEN')),
    consecutive_failures INTEGER NOT NULL DEFAULT 0,
    cooldown_until TIMESTAMPTZ,
    half_open_inflight BOOLEAN NOT NULL DEFAULT FALSE,
    last_reason TEXT,
    last_status INTEGER,
    last_model TEXT,
    last_latency_ms INTEGER,
    last_success_at TIMESTAMPTZ,
    last_failure_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
'''

@dataclass(frozen=True, slots=True)
class CircuitDecision:
    allowed: bool
    state: str
    cooldown_ms: int


@dataclass(frozen=True, slots=True)
class ReplicationMessage:
    message_id: str
    conversation_id: str
    user_id: str
    seq: int
    role: str
    content: str
    metadata: dict[str, Any]
    request_id: str | None
    created_at: str

class PostgresState:
    """Durable state store shared by all instances of one backend deployment."""

    def __init__(self, pool: asyncpg.Pool, *, schema: str = "public") -> None:
        self.pool = pool
        self.schema = schema

    async def initialize(self) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(f'CREATE SCHEMA IF NOT EXISTS "{self.schema}"')
            await conn.execute(f'SET search_path TO "{self.schema}", public')
            await conn.execute(SCHEMA)

    async def database_ping(self) -> bool:
        try:
            async with self.pool.acquire() as conn:
                return (await conn.fetchval("SELECT 1")) == 1
        except (OSError, asyncpg.PostgresError):
            return False

    @staticmethod
    def _metadata_dict(value: Any) -> dict[str, Any]:
        if value is None:
            return {}
        if isinstance(value, dict):
            return dict(value)
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                return {}
            return dict(parsed) if isinstance(parsed, dict) else {}
        try:
            return dict(value)
        except (TypeError, ValueError):
            return {}

    async def append_message(
        self,
        *,
        conversation_id: str,
        user_id: str,
        role: str,
        content: str,
        metadata: dict[str, Any] | None = None,
        request_id: str | None = None,
        message_id: str | None = None,
        enqueue_replication: bool = True,
    ) -> ReplicationMessage:
        """Append a message atomically and idempotently."""
        conversation_id = conversation_id.strip()
        user_id = user_id.strip()
        content = content.strip()
        if not conversation_id or not user_id or not content:
            raise ValueError("conversation_id, user_id and content are required")
        if role not in {"user", "assistant", "system"}:
            raise ValueError("unsupported message role")

        mid = uuid.UUID(message_id) if message_id else uuid.uuid4()
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                existing = await conn.fetchrow(
                    "SELECT id, conversation_id, user_id, seq, role, content, metadata, request_id, created_at "
                    "FROM c33_messages WHERE id=$1 OR (conversation_id=$2 AND request_id=$3 AND role=$4) "
                    "ORDER BY created_at LIMIT 1",
                    mid,
                    conversation_id,
                    request_id,
                    role,
                )
                if existing:
                    return self._row_to_message(existing)

                head = await conn.fetchrow(
                    "INSERT INTO c33_conversation_heads(conversation_id,next_seq) VALUES($1,2) "
                    "ON CONFLICT(conversation_id) DO UPDATE SET next_seq=c33_conversation_heads.next_seq+1 "
                    "RETURNING next_seq",
                    conversation_id,
                )
                seq = int(head["next_seq"]) - 1
                row = await conn.fetchrow(
                    "INSERT INTO c33_messages(id,conversation_id,user_id,seq,role,content,metadata,request_id) "
                    "VALUES($1,$2,$3,$4,$5,$6,$7::jsonb,$8) "
                    "RETURNING id,conversation_id,user_id,seq,role,content,metadata,request_id,created_at",
                    mid,
                    conversation_id,
                    user_id,
                    seq,
                    role,
                    content,
                    json.dumps(metadata or {}, ensure_ascii=False),
                    request_id,
                )
                if enqueue_replication:
                    await conn.execute(
                        "INSERT INTO c33_replication_outbox(message_id) VALUES($1) "
                        "ON CONFLICT(message_id) DO NOTHING",
                        mid,
                    )
        return self._row_to_message(row)

    async def existing_assistant_for_request(self, conversation_id: str, request_id: str) -> ReplicationMessage | None:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT id,conversation_id,user_id,seq,role,content,metadata,request_id,created_at "
                "FROM c33_messages WHERE conversation_id=$1 AND request_id=$2 AND role='assistant' LIMIT 1",
                conversation_id,
                request_id,
            )
        return self._row_to_message(row) if row else None

    async def conversation_context(self, conversation_id: str, limit: int = 12) -> list[dict[str, str]]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT role,content FROM c33_messages WHERE conversation_id=$1 ORDER BY seq DESC LIMIT $2",
                conversation_id,
                max(1, min(limit, 40)),
            )
        return [{"role": str(r["role"]), "content": str(r["content"])} for r in reversed(rows)]

    @staticmethod
    def _memory_tokens(value: str) -> list[str]:
        normalized = unicodedata.normalize("NFKD", value or "")
        normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch)).lower()
        return re.findall(r"[\w]{3,}", normalized)

    @classmethod
    def _memory_match_score(cls, query: str, content: str) -> int:
        query_tokens = set(cls._memory_tokens(query)[:8])
        content_tokens = set(cls._memory_tokens(content))
        return sum(1 for token in query_tokens if token in content_tokens)

    async def search_memory(self, user_id: str, query: str, limit: int = 16) -> list[MemoryEntry]:
        """Retrieve recent/relevant memory from durable Postgres storage."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT id::text,created_at,user_id,role,content,metadata,conversation_id "
                "FROM c33_messages WHERE user_id=$1 ORDER BY created_at DESC LIMIT 300",
                user_id,
            )
        recent = list(reversed(rows[:8]))
        scored: list[tuple[int, Any, int, Any]] = []
        for index, row in enumerate(rows[8:], start=8):
            score = self._memory_match_score(query, str(row["content"]))
            if score:
                scored.append((score, row["created_at"].astimezone(timezone.utc), index, row))
        scored.sort(key=lambda x: (x[0], x[1], x[2]), reverse=True)
        selected = recent + [row for _, _, _, row in scored[: max(0, limit - len(recent))]]
        result: list[MemoryEntry] = []
        for row in selected[:limit]:
            metadata = self._metadata_dict(row["metadata"])
            role = str(row["role"])
            result.append(
                MemoryEntry(
                    id=str(row["id"]),
                    created_at=row["created_at"].astimezone(timezone.utc).isoformat(),
                    user_text=str(metadata.get("user_text", row["content"] if role == "user" else "")),
                    assistant_text=str(metadata.get("assistant_text", row["content"] if role == "assistant" else "")),
                    summary=str(metadata.get("summary", row["content"][:240])),
                    tags=[str(x) for x in metadata.get("tags", [])],
                    debate_topic=str(metadata.get("debate_topic", "")),
                    user_position=str(metadata.get("user_position", "")),
                    central_arguments=[str(x) for x in metadata.get("central_arguments", [])],
                )
            )
        return result

    async def circuit_before_call(self, provider_id: str) -> CircuitDecision:
        now = datetime.now(timezone.utc)
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "INSERT INTO c33_circuit_breakers(provider_id,state) VALUES($1,'CLOSED') ON CONFLICT DO NOTHING",
                    provider_id,
                )
                row = await conn.fetchrow(
                    "SELECT state,cooldown_until,half_open_inflight FROM c33_circuit_breakers "
                    "WHERE provider_id=$1 FOR UPDATE",
                    provider_id,
                )
                state = str(row["state"])
                cooldown_until = row["cooldown_until"]
                inflight = bool(row["half_open_inflight"])
                if state == "CLOSED":
                    return CircuitDecision(True, state, 0)
                if state == "OPEN" and cooldown_until and cooldown_until > now:
                    remaining = max(0, int((cooldown_until - now).total_seconds() * 1000))
                    return CircuitDecision(False, state, remaining)
                if state == "OPEN":
                    await conn.execute(
                        "UPDATE c33_circuit_breakers SET state='HALF_OPEN',half_open_inflight=TRUE,updated_at=now() WHERE provider_id=$1",
                        provider_id,
                    )
                    return CircuitDecision(True, "HALF_OPEN", 0)
                if state == "HALF_OPEN" and not inflight:
                    await conn.execute(
                        "UPDATE c33_circuit_breakers SET half_open_inflight=TRUE,updated_at=now() WHERE provider_id=$1",
                        provider_id,
                    )
                    return CircuitDecision(True, state, 0)
                return CircuitDecision(False, state, 1000)

    async def circuit_success(self, provider_id: str, *, model: str, latency_ms: int) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE c33_circuit_breakers SET state='CLOSED',consecutive_failures=0,cooldown_until=NULL,"
                "half_open_inflight=FALSE,last_reason='success',last_status=200,last_model=$2,last_latency_ms=$3,"
                "last_success_at=now(),updated_at=now() WHERE provider_id=$1",
                provider_id,
                model,
                latency_ms,
            )

    async def circuit_failure(
        self,
        provider_id: str,
        *,
        reason: str,
        status: int | None,
        model: str,
        latency_ms: int,
        cooldown_ms: int,
    ) -> None:
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    "SELECT state,consecutive_failures FROM c33_circuit_breakers WHERE provider_id=$1 FOR UPDATE",
                    provider_id,
                )
                if not row:
                    await conn.execute(
                        "INSERT INTO c33_circuit_breakers(provider_id,state) VALUES($1,'CLOSED') ON CONFLICT DO NOTHING",
                        provider_id,
                    )
                    row = await conn.fetchrow(
                        "SELECT state,consecutive_failures FROM c33_circuit_breakers WHERE provider_id=$1 FOR UPDATE",
                        provider_id,
                    )
                state = str(row["state"])
                failures = int(row["consecutive_failures"]) + 1
                hard_failure = status in {400, 401, 403, 408, 429} or state == "HALF_OPEN" or failures >= 3
                if hard_failure:
                    new_state = "OPEN"
                    until = datetime.now(timezone.utc).timestamp() + max(1000, cooldown_ms) / 1000
                    await conn.execute(
                        "UPDATE c33_circuit_breakers SET state=$2,consecutive_failures=$3,cooldown_until=to_timestamp($4),"
                        "half_open_inflight=FALSE,last_reason=$5,last_status=$6,last_model=$7,last_latency_ms=$8,"
                        "last_failure_at=now(),updated_at=now() WHERE provider_id=$1",
                        provider_id,
                        new_state,
                        failures,
                        until,
                        reason[:240],
                        status,
                        model[:200],
                        latency_ms,
                    )
                else:
                    await conn.execute(
                        "UPDATE c33_circuit_breakers SET state='CLOSED',consecutive_failures=$2,half_open_inflight=FALSE,"
                        "last_reason=$3,last_status=$4,last_model=$5,last_latency_ms=$6,last_failure_at=now(),updated_at=now() WHERE provider_id=$1",
                        provider_id,
                        failures,
                        reason[:240],
                        status,
                        model[:200],
                        latency_ms,
                    )

    async def circuit_snapshot(self, provider_id: str) -> dict[str, Any]:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM c33_circuit_breakers WHERE provider_id=$1", provider_id)
        if not row:
            return {"provider_id": provider_id, "state": "CLOSED", "consecutive_failures": 0}
        now = datetime.now(timezone.utc)
        cooldown = row["cooldown_until"]
        cooldown_ms = max(0, int((cooldown - now).total_seconds() * 1000)) if cooldown else 0
        return {
            "provider_id": provider_id,
            "state": row["state"],
            "consecutive_failures": row["consecutive_failures"],
            "cooldown_ms": cooldown_ms,
            "last_reason": row["last_reason"],
            "last_status": row["last_status"],
            "last_model": row["last_model"],
            "last_latency_ms": row["last_latency_ms"],
            "last_success_at": row["last_success_at"].isoformat() if row["last_success_at"] else None,
            "last_failure_at": row["last_failure_at"].isoformat() if row["last_failure_at"] else None,
        }

    async def all_circuit_snapshots(self, provider_ids: list[str]) -> list[dict[str, Any]]:
        return [await self.circuit_snapshot(pid) for pid in provider_ids]

    async def pending_replication(self, limit: int = 20) -> list[ReplicationMessage]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT m.id,m.conversation_id,m.user_id,m.seq,m.role,m.content,m.metadata,m.request_id,m.created_at "
                "FROM c33_replication_outbox o JOIN c33_messages m ON m.id=o.message_id "
                "WHERE o.synced_at IS NULL AND o.next_attempt_at<=now() ORDER BY m.created_at LIMIT $1",
                max(1, min(limit, 100)),
            )
        return [self._row_to_message(r) for r in rows]

    async def mark_replication_result(self, message_id: str, *, ok: bool, error: str = "") -> None:
        if ok:
            async with self.pool.acquire() as conn:
                await conn.execute(
                    "UPDATE c33_replication_outbox SET synced_at=now(),last_error=NULL WHERE message_id=$1",
                    uuid.UUID(message_id),
                )
            return
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE c33_replication_outbox SET attempts=attempts+1, "
                "next_attempt_at=now()+make_interval(secs => LEAST(300, GREATEST(2, (2 ^ LEAST(attempts+1,8))) + $2)),"
                "last_error=$1 WHERE message_id=$3",
                error[:500],
                random.random(),
                uuid.UUID(message_id),
            )

    async def replicate_batch(
        self,
        peer_url: str,
        secret: str,
        *,
        limit: int = 20,
        timeout_ms: int = 900,
    ) -> tuple[int, int]:
        messages = await self.pending_replication(limit)
        if not messages or not peer_url:
            return 0, 0
        payload = {
            "messages": [
                {
                    "id": m.message_id,
                    "conversation_id": m.conversation_id,
                    "user_id": m.user_id,
                    "seq": m.seq,
                    "role": m.role,
                    "content": m.content,
                    "metadata": m.metadata,
                    "request_id": m.request_id,
                    "created_at": m.created_at,
                }
                for m in messages
            ]
        }
        raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        signature = hmac.new(secret.encode("utf-8"), raw, hashlib.sha256).hexdigest()
        ok_count = fail_count = 0
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(timeout_ms / 1000, connect=min(0.4, timeout_ms / 1000))) as client:
                response = await client.post(
                    peer_url.rstrip("/") + "/internal/replicate",
                    content=raw,
                    headers={
                        "Content-Type": "application/json",
                        "X-C33-Replication-Signature": signature,
                        "X-C33-Replication-Version": "1",
                    },
                )
                if response.status_code != 200:
                    raise RuntimeError(f"peer HTTP {response.status_code}")
                try:
                    body = response.json()
                except ValueError as exc:
                    raise RuntimeError("peer invalid replication response") from exc
                accepted = int(body.get("accepted", -1))
                received = int(body.get("received", -1))
                accepted_ids = body.get("accepted_ids")
                receipt_sha256 = str(body.get("receipt_sha256", "")).strip()
                expected_ids = [message.message_id for message in messages]
                expected_sha256 = hashlib.sha256(raw).hexdigest()
                if received != len(messages) or accepted != len(messages):
                    raise RuntimeError(
                        f"peer partial replication accepted={accepted} received={received} expected={len(messages)}"
                    )
                if accepted_ids != expected_ids:
                    raise RuntimeError("peer replication receipt ids mismatch")
                if receipt_sha256 != expected_sha256:
                    raise RuntimeError("peer replication receipt digest mismatch")
        except Exception as exc:  # bounded background replication
            for message in messages:
                await self.mark_replication_result(message.message_id, ok=False, error=str(exc))
                fail_count += 1
            return ok_count, fail_count

        for message in messages:
            await self.mark_replication_result(message.message_id, ok=True)
            ok_count += 1
        return ok_count, fail_count

    async def import_replication_batch(self, messages: list[dict[str, Any]], *, enqueue_replication: bool = False) -> int:
        """Import replicated messages idempotently and reject conflicting state."""
        accepted = 0
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                for item in messages[:100]:
                    try:
                        if not isinstance(item, dict):
                            raise ValueError("message_must_be_object")
                        mid = uuid.UUID(str(item["id"]))
                        conversation_id = item.get("conversation_id")
                        user_id = item.get("user_id")
                        role = item.get("role")
                        content = item.get("content")
                        if not isinstance(conversation_id, str):
                            raise ValueError("conversation_id_must_be_string")
                        if not isinstance(user_id, str):
                            raise ValueError("user_id_must_be_string")
                        if not isinstance(role, str):
                            raise ValueError("role_must_be_string")
                        if not isinstance(content, str):
                            raise ValueError("content_must_be_string")
                        conversation_id = conversation_id.strip()
                        user_id = user_id.strip()
                        role = role.strip()
                        content = content.strip()
                        if role not in {"user", "assistant", "system"}:
                            raise ValueError(f"invalid_role:{role}")
                        if not conversation_id:
                            raise ValueError("conversation_id_required")
                        if not user_id:
                            raise ValueError("user_id_required")
                        if len(conversation_id) > _MAX_REPLICATION_ID_CHARS:
                            raise ValueError("conversation_id_too_long")
                        if len(user_id) > _MAX_REPLICATION_ID_CHARS:
                            raise ValueError("user_id_too_long")
                        if not content:
                            raise ValueError("content_required")
                        if len(content) > _MAX_REPLICATION_TEXT_CHARS:
                            raise ValueError("content_too_long")
                        seq_raw = item.get("seq")
                        if isinstance(seq_raw, bool):
                            raise ValueError("seq_must_be_integer")
                        try:
                            seq = int(seq_raw)
                        except (TypeError, ValueError) as exc:
                            raise ValueError("seq_must_be_integer") from exc
                        if seq < 1:
                            raise ValueError("seq_must_be_positive")
                        raw_metadata = item.get("metadata")
                        if raw_metadata is None:
                            metadata: dict[str, Any] = {}
                        elif isinstance(raw_metadata, dict):
                            metadata = dict(raw_metadata)
                        else:
                            raise ValueError("metadata_must_be_object")
                        request_id = item.get("request_id")
                        if request_id is not None:
                            if not isinstance(request_id, str):
                                raise ValueError("request_id_must_be_string")
                            request_id = request_id.strip() or None
                            if request_id and len(request_id) > 128:
                                raise ValueError("request_id_too_long")
                        created_at = _normalize_created_at(item.get("created_at"))
                        existing = await conn.fetchrow(
                            "SELECT conversation_id,user_id,seq,role,content,metadata,request_id "
                            "FROM c33_messages WHERE id=$1",
                            mid,
                        )
                        if existing:
                            same = (
                                str(existing["conversation_id"]) == conversation_id
                                and str(existing["user_id"]) == user_id
                                and int(existing["seq"]) == seq
                                and str(existing["role"]) == role
                                and str(existing["content"]) == content
                                and self._metadata_dict(existing["metadata"]) == metadata
                                and existing["request_id"] == request_id
                            )
                            if not same:
                                raise ReplicationConflictError(f"message_id_conflict:{mid}")
                            accepted += 1
                            continue
                        sequence_owner = await conn.fetchrow(
                            "SELECT id FROM c33_messages WHERE conversation_id=$1 AND seq=$2",
                            conversation_id,
                            seq,
                        )
                        if sequence_owner and sequence_owner["id"] != mid:
                            raise ReplicationConflictError(f"sequence_conflict:{conversation_id}:{seq}")
                        if request_id is not None:
                            request_owner = await conn.fetchrow(
                                "SELECT id FROM c33_messages WHERE conversation_id=$1 AND request_id=$2 AND role=$3",
                                conversation_id,
                                request_id,
                                role,
                            )
                            if request_owner and request_owner["id"] != mid:
                                raise ReplicationConflictError(f"request_conflict:{conversation_id}:{request_id}:{role}")
                        await conn.execute(
                            "INSERT INTO c33_messages(id,conversation_id,user_id,seq,role,content,metadata,request_id,created_at) "
                            "VALUES($1,$2,$3,$4,$5,$6,$7::jsonb,$8,$9::timestamptz)",
                            mid, conversation_id, user_id, seq, role, content,
                            json.dumps(metadata, ensure_ascii=False), request_id, created_at,
                        )
                        if enqueue_replication:
                            await conn.execute(
                                "INSERT INTO c33_replication_outbox(message_id) VALUES($1) "
                                "ON CONFLICT(message_id) DO NOTHING",
                                mid,
                            )
                        await conn.execute(
                            "INSERT INTO c33_conversation_heads(conversation_id,next_seq) VALUES($1,$2) "
                            "ON CONFLICT(conversation_id) DO UPDATE SET next_seq=GREATEST(c33_conversation_heads.next_seq,EXCLUDED.next_seq)",
                            conversation_id, seq + 1,
                        )
                        accepted += 1
                    except ReplicationConflictError:
                        raise
                    except (KeyError, ValueError, TypeError) as exc:
                        raise ValueError(f"invalid_replication_message:{exc}") from exc
                    except asyncpg.PostgresError as exc:
                        raise ValueError(f"replication_storage_error:{exc.__class__.__name__}") from exc
        return accepted

    async def replication_integrity(self) -> dict[str, Any]:
        """Return a privacy-preserving deterministic digest of the durable message set."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT id::text,conversation_id,user_id,seq,role,content,metadata,request_id,created_at "
                "FROM c33_messages ORDER BY id"
            )
        digest = hashlib.sha256()
        id_digest = hashlib.sha256()
        unique_ids: set[str] = set()
        for row in rows:
            message_id = str(row["id"])
            unique_ids.add(message_id)
            id_digest.update(message_id.encode("utf-8"))
            id_digest.update(b"\n")
            record = {
                "id": message_id,
                "conversation_id": str(row["conversation_id"]),
                "user_id": str(row["user_id"]),
                "seq": int(row["seq"]),
                "role": str(row["role"]),
                "content": str(row["content"]),
                "metadata": self._metadata_dict(row["metadata"]),
                "request_id": str(row["request_id"]) if row["request_id"] is not None else None,
                "created_at": row["created_at"].astimezone(timezone.utc).isoformat(),
            }
            canonical = json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
            digest.update(canonical)
            digest.update(b"\n")
        return {
            "total_messages": len(rows),
            "unique_message_ids": len(unique_ids),
            "message_id_digest": id_digest.hexdigest(),
            "message_digest": digest.hexdigest(),
        }

    async def replication_pending_count(self) -> int:
        async with self.pool.acquire() as conn:
            return int(await conn.fetchval("SELECT COUNT(*) FROM c33_replication_outbox WHERE synced_at IS NULL"))

    @staticmethod
    def _row_to_message(row: asyncpg.Record) -> ReplicationMessage:
        return ReplicationMessage(
            message_id=str(row["id"]),
            conversation_id=str(row["conversation_id"]),
            user_id=str(row["user_id"]),
            seq=int(row["seq"]),
            role=str(row["role"]),
            content=str(row["content"]),
            metadata=PostgresState._metadata_dict(row["metadata"]),
            request_id=str(row["request_id"]) if row["request_id"] is not None else None,
            created_at=row["created_at"].astimezone(timezone.utc).isoformat(),
        )
