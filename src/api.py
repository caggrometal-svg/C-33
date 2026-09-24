"""Production FastAPI service for C-33/NEXO with real readiness, failover and cancellation."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import asyncpg
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

_SRC_DIR = str(Path(__file__).resolve().parent)
if _SRC_DIR not in __import__("sys").path:
    __import__("sys").path.insert(0, _SRC_DIR)

from agent.brain import AgentResult, Brain
from config import InfrastructureConfig, load_infrastructure_config
from resilience.providers import DeadlineBudget, GenerationFailure, ProviderCascade
from resilience.state import PostgresState
from tools.web import WebTool

config: InfrastructureConfig = load_infrastructure_config()
db_pool: asyncpg.Pool | None = None
state: PostgresState | None = None
brain: Brain | None = None
cascade: ProviderCascade | None = None
replication_task: asyncio.Task[None] | None = None
startup_probe_task: asyncio.Task[None] | None = None
ai_ready_probe_lock: asyncio.Lock | None = None
ai_ready_cache: tuple[float, dict[str, Any]] | None = None
logger = logging.getLogger("c33")

class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=20_000)
    user_id: str = Field(default="anonymous", min_length=1, max_length=256)
    conversation_id: str = Field(default="default", min_length=1, max_length=256)
    request_id: str = Field(default="", max_length=128)
    stream: bool = False
    personality: str = Field(default="base", max_length=32)
    voice_tone: str = Field(default="neutral", max_length=32)

class ResponseMeta(BaseModel):
    provider_used: str
    model: str
    failover_triggered: bool
    latency_ms: int
    final_reason: str
    system_status: str
    backend_role: str
    backend_url: str
    request_id: str
    conversation_id: str
    memory_sync: str
    peer_status: str
    provider_attempts: int
    used_local_fallback: bool = False

class ChatResponse(BaseModel):
    status: str
    service: str
    user_id: str
    conversation_id: str
    request_id: str
    synthesis: str
    web_searches: list[str]
    meta: ResponseMeta = Field(alias="_meta")
    model_config = {"populate_by_name": True}

class ReadyResponse(BaseModel):
    status: str
    service: str
    deployment_sha: str
    database: str
    peer_configured: bool
    provider_count: int

class ClientDisconnected(RuntimeError):
    pass

def _deployment_sha() -> str:
    return os.getenv("RAILWAY_GIT_COMMIT_SHA") or os.getenv("RENDER_GIT_COMMIT") or os.getenv("GIT_COMMIT_SHA") or "unknown"

def _backend_url() -> str:
    configured = os.getenv("PUBLIC_BASE_URL", "").strip().rstrip("/")
    if configured:
        return configured
    return "https://c33-backend.onrender.com" if config.role == "secondary" else "https://iac33-backup-production.up.railway.app"

def _require_runtime() -> tuple[PostgresState, Brain, ProviderCascade]:
    if state is None or brain is None or cascade is None:
        raise HTTPException(status_code=503, detail="backend_state_not_initialized")
    return state, brain, cascade

async def _database_ping() -> bool:
    return bool(state and await state.database_ping())

async def _peer_probe() -> str:
    if not config.peer_url:
        return "NOT_CONFIGURED"
    import httpx
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(0.8, connect=0.4)) as client:
            response = await client.get(config.peer_url + "/health", headers={"Cache-Control":"no-cache"})
        return "ONLINE" if response.status_code == 200 else "OFFLINE"
    except httpx.HTTPError:
        return "OFFLINE"

async def _remote_ai_probe(*, force: bool = False) -> dict[str, Any]:
    global ai_ready_probe_lock, ai_ready_cache
    if cascade is None:
        raise GenerationFailure("runtime_not_initialized", http_status=503, attempts=[])
    now = time.monotonic()
    if not force and ai_ready_cache and ai_ready_cache[0] > now:
        return dict(ai_ready_cache[1])
    if ai_ready_probe_lock is None:
        ai_ready_probe_lock = asyncio.Lock()
    async with ai_ready_probe_lock:
        now = time.monotonic()
        if not force and ai_ready_cache and ai_ready_cache[0] > now:
            return dict(ai_ready_cache[1])
        result = await cascade.complete(
            [
                {"role": "system", "content": "Respond with a short health-check acknowledgement."},
                {"role": "user", "content": "C33_AI_READY_PROBE"},
            ],
            DeadlineBudget(6_000),
            probe=True,
        )
        if not result.text.strip():
            raise GenerationFailure("empty_remote_response", http_status=502, attempts=[])
        payload = {
            "status": "ai_ready",
            "service": "C-33",
            "provider_used": result.meta.provider_used,
            "model": result.meta.model,
            "latency_ms": result.meta.latency_ms,
            "failover_triggered": result.meta.failover_triggered,
            "deployment_sha": _deployment_sha(),
        }
        ai_ready_cache = (time.monotonic() + 8.0, payload)
        return dict(payload)

async def _startup_ai_probe() -> None:
    if cascade is None:
        return
    try:
        result = await cascade.complete(
            [
                {"role": "system", "content": "Respond with a short health-check acknowledgement."},
                {"role": "user", "content": "C33_STARTUP_AI_PROBE"},
            ],
            DeadlineBudget(6_000),
            probe=True,
        )
        ai_ready_cache_set = {
            "status": "ai_ready",
            "service": "C-33",
            "provider_used": result.meta.provider_used,
            "model": result.meta.model,
            "latency_ms": result.meta.latency_ms,
            "failover_triggered": result.meta.failover_triggered,
            "deployment_sha": _deployment_sha(),
        }
        global ai_ready_cache
        ai_ready_cache = (time.monotonic() + 8.0, ai_ready_cache_set)
        logger.info(
            "C33_STARTUP_AI_PROBE success provider=%s model=%s latency_ms=%s",
            result.meta.provider_used,
            result.meta.model,
            result.meta.latency_ms,
        )
    except GenerationFailure as exc:
        logger.warning(
            "C33_STARTUP_AI_PROBE failure reason=%s status=%s attempts=%s",
            exc.reason,
            exc.http_status,
            json.dumps(exc.attempts, ensure_ascii=False),
        )
    except Exception as exc:
        logger.exception("C33_STARTUP_AI_PROBE unexpected error: %s", exc)

async def _replication_loop() -> None:
    assert state is not None
    while True:
        try:
            if config.peer_url and config.peer_replication_secret:
                await state.replicate_batch(config.peer_url, config.peer_replication_secret, limit=25, timeout_ms=800)
        except asyncio.CancelledError:
            raise
        except Exception:
            pass
        await asyncio.sleep(2.0)

@asynccontextmanager
async def lifespan(_: FastAPI):
    global db_pool, state, brain, cascade, replication_task, startup_probe_task
    if config.database_url:
        db_pool = await asyncpg.create_pool(
            dsn=config.database_url,
            min_size=1,
            max_size=8,
            command_timeout=5,
            timeout=5,
        )
        state = PostgresState(db_pool)
        await state.initialize()
        cascade = ProviderCascade.from_environment(state)
        brain = Brain(state, WebTool(timeout=min(config.network_timeout_seconds, 8.0), max_results=5), cascade)
        replication_task = asyncio.create_task(_replication_loop())
        startup_probe_task = asyncio.create_task(_startup_ai_probe())
    try:
        yield
    finally:
        if startup_probe_task:
            startup_probe_task.cancel()
            try:
                await startup_probe_task
            except asyncio.CancelledError:
                pass
            startup_probe_task = None
        if replication_task:
            replication_task.cancel()
            try:
                await replication_task
            except asyncio.CancelledError:
                pass
        if db_pool:
            await db_pool.close()
        db_pool = None
        state = None
        brain = None
        cascade = None
        startup_probe_task = None
        ai_ready_probe_lock = None
        ai_ready_cache = None

app = FastAPI(title="C-33 / NEXO API", version="2.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

@app.get("/health")
async def health() -> dict[str, Any]:
    """Pure liveness: process is alive; no DB/AI check and no false readiness."""
    return {"status":"alive","service":"C-33","deployment_sha":_deployment_sha(),"role":config.role}

@app.get("/ready", response_model=ReadyResponse)
async def ready() -> ReadyResponse:
    """Infrastructure readiness: local process + durable PostgreSQL + redundancy configuration."""
    if state is None or cascade is None or not await _database_ping():
        raise HTTPException(status_code=503, detail={"status":"not_ready","reason":"database_unavailable"})
    if config.environment == "production" and config.peer_url and not config.peer_replication_secret:
        raise HTTPException(status_code=503, detail={"status":"not_ready","reason":"peer_replication_secret_missing"})
    if config.environment == "production":
        try:
            cascade.assert_ready_configuration()
        except GenerationFailure as exc:
            raise HTTPException(status_code=503, detail={"status":"not_ready","reason":exc.reason}) from exc
    return ReadyResponse(
        status="ready", service="C-33", deployment_sha=_deployment_sha(), database="ok",
        peer_configured=bool(config.peer_url and config.peer_replication_secret),
        provider_count=cascade.configured_provider_count,
    )

@app.get("/v1/time")
async def api_time() -> dict[str, str]:
    return {"utc":"%.3f" % time.time(),"deployment_sha":_deployment_sha()}

@app.get("/status")
async def status() -> dict[str, Any]:
    db_ok = await _database_ping()
    providers = []
    if cascade and state:
        providers = await state.all_circuit_snapshots([p.provider_id for p in cascade.providers])
    peer = await _peer_probe()
    system_status = "OFFLINE" if not db_ok else "READY"
    return {
        "status":"ok" if db_ok else "degraded",
        "service":"C-33",
        "deployment_sha":_deployment_sha(),
        "backend_role":config.role,
        "database":"ONLINE" if db_ok else "OFFLINE",
        "internet":"UNKNOWN",
        "ai":"CONFIGURED" if cascade and cascade.configured_provider_count else "NOT_CONFIGURED",
        "provider_count": cascade.configured_provider_count if cascade else 0,
        "provider_failure_domains": cascade.failure_domains if cascade else [],
        "providers":providers,
        "peer":peer,
        "system_status":system_status,
        "replication_pending":await state.replication_pending_count() if state else None,
    }

@app.get("/v1/ai/diagnostics")
async def ai_diagnostics() -> dict[str, Any]:
    if state is None or cascade is None:
        raise HTTPException(status_code=503, detail="runtime_not_initialized")
    return {
        "status":"ok",
        "deployment_sha":_deployment_sha(),
        "provider_count":cascade.configured_provider_count,
        "provider_failure_domains":cascade.failure_domains,
        "providers":await state.all_circuit_snapshots([p.provider_id for p in cascade.providers]),
        "peer_status":await _peer_probe(),
        "replication_pending":await state.replication_pending_count(),
    }

@app.get("/v1/ai-ready")
async def ai_ready() -> dict[str, Any]:
    """Real remote-AI probe. Local fallback never counts as AI_READY."""
    _require_runtime()
    try:
        return await _remote_ai_probe()
    except GenerationFailure as exc:
        raise HTTPException(
            status_code=exc.http_status,
            detail={"status":"not_ready","reason":exc.reason,"attempts":exc.attempts},
        ) from exc

async def _run_with_disconnect(request: Request, operation: asyncio.Future | asyncio.Task | Any) -> Any:
    task = asyncio.create_task(operation)
    try:
        while not task.done():
            if await request.is_disconnected():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                raise ClientDisconnected("client_disconnected")
            await asyncio.sleep(0.08)
        return await task
    finally:
        if not task.done():
            task.cancel()

async def _commit_turn(st: PostgresState, payload: ChatRequest, synthesis: str, meta: dict[str, Any]) -> str:
    await st.append_message(
        conversation_id=payload.conversation_id,
        user_id=payload.user_id,
        role="assistant",
        content=synthesis,
        metadata={"provider_used":meta.get("provider_used"),"model":meta.get("model"),"meta":meta},
        request_id=payload.request_id,
    )
    if config.peer_url and config.peer_replication_secret:
        try:
            await asyncio.wait_for(
                st.replicate_batch(config.peer_url, config.peer_replication_secret, limit=10, timeout_ms=650),
                timeout=min(0.75, max(0.05, (meta.get("remaining_ms", 750) or 750) / 1000)),
            )
        except Exception:
            pass
    return "SYNCED" if await st.replication_pending_count() == 0 else "PENDING"

async def _handle_chat(payload: ChatRequest, request: Request) -> ChatResponse:
    st, b, providers = _require_runtime()
    request_id = payload.request_id.strip() or os.urandom(12).hex()
    effective_payload = payload.model_copy(update={"request_id":request_id})
    existing = await st.existing_assistant_for_request(effective_payload.conversation_id, request_id)
    if existing:
        stored_meta = dict(existing.metadata.get("meta", {})) if isinstance(existing.metadata, dict) else {}
        stored_meta.setdefault("request_id", request_id)
        stored_meta.setdefault("conversation_id", effective_payload.conversation_id)
        return ChatResponse(status="ok",service="C-33",user_id=effective_payload.user_id,conversation_id=effective_payload.conversation_id,request_id=request_id,synthesis=existing.content,web_searches=[],meta=stored_meta)

    await st.append_message(
        conversation_id=effective_payload.conversation_id,
        user_id=effective_payload.user_id,
        role="user",
        content=effective_payload.message,
        metadata={"voice_tone":effective_payload.voice_tone,"personality":effective_payload.personality},
        request_id=request_id,
    )
    # Outbox makes the user's turn durable before generation; the backup can also idempotently accept the same request.
    client_deadline = request.headers.get("X-C33-Deadline-Epoch-Ms")
    try:
        deadline_epoch = int(client_deadline) if client_deadline else None
    except ValueError:
        deadline_epoch = None
    budget = DeadlineBudget(config.backend_total_timeout_ms, deadline_epoch)

    async def work() -> tuple[AgentResult | None, str | None, GenerationFailure | None]:
        try:
            result = await b.process(
                effective_payload.message,
                user_id=effective_payload.user_id,
                conversation_id=effective_payload.conversation_id,
                personality_mode=effective_payload.personality,
                budget=budget,
            )
            return result, None, None
        except GenerationFailure as exc:
            return None, None, exc

    result, _, generation_failure = await _run_with_disconnect(request, work())
    if generation_failure:
        allow_local_fallback = request.headers.get("X-C33-Allow-Local-Fallback", "true").strip().lower() in {"1", "true", "yes", "on"}
        if not allow_local_fallback:
            raise HTTPException(
                status_code=generation_failure.http_status,
                detail={"reason": generation_failure.reason, "attempts": generation_failure.attempts, "used_local_fallback": False},
            )
        if config.local_fallback_enabled:
            synthesis = b.local_fallback(effective_payload.message, generation_failure.reason)
            meta = {
                "provider_used":"local",
                "model":"local-fallback",
                "failover_triggered":True,
                "latency_ms":config.backend_total_timeout_ms - budget.remaining_ms,
                "final_reason":generation_failure.reason,
                "system_status":"DEGRADED",
                "backend_role":config.role,
                "backend_url":_backend_url(),
                "request_id":request_id,
                "conversation_id":effective_payload.conversation_id,
                "memory_sync":"PENDING",
                "peer_status":await _peer_probe(),
                "provider_attempts":len(generation_failure.attempts),
                "used_local_fallback":True,
            }
            sync = await _commit_turn(st, effective_payload, synthesis, {**meta,"remaining_ms":budget.remaining_ms})
            meta["memory_sync"] = sync
            return ChatResponse(status="ok",service="C-33",user_id=effective_payload.user_id,conversation_id=effective_payload.conversation_id,request_id=request_id,synthesis=synthesis,web_searches=[],meta=meta)
        raise HTTPException(status_code=generation_failure.http_status, detail={"reason":generation_failure.reason,"attempts":generation_failure.attempts})

    assert result is not None
    meta = {
        **result.model_meta,
        "backend_role":config.role,
        "backend_url":_backend_url(),
        "request_id":request_id,
        "conversation_id":effective_payload.conversation_id,
        "memory_sync":"PENDING",
        "peer_status":await _peer_probe(),
        "provider_attempts":int(result.model_meta.get("attempts",1)),
        "used_local_fallback":False,
    }
    sync = await _commit_turn(st, effective_payload, result.response, {**meta,"remaining_ms":budget.remaining_ms})
    meta["memory_sync"] = sync
    meta["system_status"] = (
        "DEGRADED"
        if meta.get("failover_triggered") or sync != "SYNCED"
        else "AI_READY"
    )
    return ChatResponse(status="ok",service="C-33",user_id=effective_payload.user_id,conversation_id=effective_payload.conversation_id,request_id=request_id,synthesis=result.response,web_searches=result.sources,meta=meta)

@app.post("/v1/chat", response_model=ChatResponse)
@app.post("/api/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest, request: Request) -> ChatResponse:
    try:
        return await asyncio.wait_for(_handle_chat(payload, request), timeout=config.backend_total_timeout_ms / 1000)
    except ClientDisconnected as exc:
        # Proxies may emit HTTP 499; when the socket is still writable this is explicit in our API contract.
        raise HTTPException(status_code=499, detail={"reason":str(exc)}) from exc
    except asyncio.TimeoutError as exc:
        raise HTTPException(status_code=504, detail={"reason":"backend_deadline_exceeded"}) from exc

@app.post("/v1/ai/stream")
async def ai_stream(payload: ChatRequest, request: Request) -> StreamingResponse:
    st, b, providers = _require_runtime()
    request_id = payload.request_id.strip() or os.urandom(12).hex()
    await st.append_message(
        conversation_id=payload.conversation_id,
        user_id=payload.user_id,
        role="user",
        content=payload.message,
        metadata={"personality":payload.personality,"voice_tone":payload.voice_tone},
        request_id=request_id,
    )
    client_deadline = request.headers.get("X-C33-Deadline-Epoch-Ms")
    try: deadline_epoch = int(client_deadline) if client_deadline else None
    except ValueError: deadline_epoch = None
    budget = DeadlineBudget(config.backend_total_timeout_ms, deadline_epoch)

    messages, sources, _ = await b.prepare_messages(
        payload.message,
        user_id=payload.user_id,
        conversation_id=payload.conversation_id,
        personality_mode=payload.personality,
        budget=budget,
    )

    async def events():
        pieces: list[str] = []
        stream_meta: Any = None
        started = time.monotonic()
        parent_task = asyncio.current_task()

        async def cancel_on_disconnect() -> None:
            assert parent_task is not None
            while True:
                if await request.is_disconnected():
                    parent_task.cancel()
                    return
                await asyncio.sleep(0.05)

        watcher = asyncio.create_task(cancel_on_disconnect())
        try:
            async for piece, meta in providers.stream(messages, budget):
                if await request.is_disconnected():
                    return
                stream_meta = meta
                pieces.append(piece)
                yield "event: token\n"
                yield "data: " + json.dumps({"text":piece}, ensure_ascii=False) + "\n\n"
            final = "".join(pieces).strip()
            if not final or stream_meta is None:
                raise GenerationFailure("empty_stream", http_status=502, attempts=[])
            await st.append_message(
                conversation_id=payload.conversation_id,
                user_id=payload.user_id,
                role="assistant",
                content=final,
                metadata={"provider_used":stream_meta.provider_used,"model":stream_meta.model,"stream":True,"sources":sources},
                request_id=request_id,
            )
            final_meta = {
                "provider_used":stream_meta.provider_used,
                "model":stream_meta.model,
                "failover_triggered":stream_meta.failover_triggered,
                "latency_ms":int((time.monotonic() - started) * 1000),
                "final_reason":"stream_complete",
                "system_status":stream_meta.system_status,
                "backend_role":config.role,
                "backend_url":_backend_url(),
                "request_id":request_id,
                "conversation_id":payload.conversation_id,
                "provider_attempts":stream_meta.attempts,
                "used_local_fallback":False,
            }
            yield "event: done\n"
            yield "data: " + json.dumps({"_meta":final_meta}, ensure_ascii=False) + "\n\n"
        except GenerationFailure as exc:
            if await request.is_disconnected():
                return
            if pieces:
                yield "event: error\n"
                yield "data: " + json.dumps({
                    "reason":exc.reason,
                    "_meta":{"final_reason":exc.reason,"system_status":"DEGRADED","used_local_fallback":False},
                }, ensure_ascii=False) + "\n\n"
                return
            allow_local_fallback = request.headers.get("X-C33-Allow-Local-Fallback", "true").strip().lower() in {"1", "true", "yes", "on"}
            if not allow_local_fallback or not config.local_fallback_enabled:
                yield "event: error\n"
                yield "data: " + json.dumps({"reason":exc.reason,"_meta":{"final_reason":exc.reason,"used_local_fallback":False}}, ensure_ascii=False) + "\n\n"
                return
            fallback = b.local_fallback(payload.message, exc.reason)
            fallback_meta = {
                "provider_used":"local",
                "model":"local-fallback",
                "failover_triggered":True,
                "latency_ms":int((time.monotonic() - started) * 1000),
                "final_reason":exc.reason,
                "system_status":"DEGRADED",
                "backend_role":config.role,
                "backend_url":_backend_url(),
                "request_id":request_id,
                "conversation_id":payload.conversation_id,
                "provider_attempts":len(exc.attempts),
                "used_local_fallback":True,
            }
            await st.append_message(
                conversation_id=payload.conversation_id,
                user_id=payload.user_id,
                role="assistant",
                content=fallback,
                metadata={"provider_used":"local","model":"local-fallback","stream":True,"sources":sources,"meta":fallback_meta},
                request_id=request_id,
            )
            yield "event: fallback\n"
            yield "data: " + json.dumps({"text":fallback,"_meta":fallback_meta}, ensure_ascii=False) + "\n\n"
            yield "event: done\n"
            yield "data: " + json.dumps({"_meta":fallback_meta}, ensure_ascii=False) + "\n\n"
        except asyncio.CancelledError:
            raise
        finally:
            watcher.cancel()
            try:
                await watcher
            except asyncio.CancelledError:
                pass

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control":"no-cache","Connection":"keep-alive","X-Accel-Buffering":"no"},
    )

@app.post("/internal/replicate")
async def replicate(request: Request) -> JSONResponse:
    if not config.peer_replication_secret:
        raise HTTPException(status_code=404, detail="replication_disabled")
    raw = await request.body()
    supplied = request.headers.get("X-C33-Replication-Signature", "")
    expected = hmac.new(config.peer_replication_secret.encode("utf-8"), raw, hashlib.sha256).hexdigest()
    if not supplied or not hmac.compare_digest(supplied, expected):
        raise HTTPException(status_code=401, detail="invalid_replication_signature")
    try:
        body = json.loads(raw.decode("utf-8"))
        messages = body["messages"]
        if not isinstance(messages, list): raise ValueError
    except (ValueError, KeyError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail="invalid_replication_payload") from exc
    st, _, _ = _require_runtime()
    imported = await st.import_replication_batch(messages)
    return JSONResponse({"status":"ok","imported":imported})
