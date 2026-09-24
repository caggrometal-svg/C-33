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
from resilience.providers import DeadlineBudget, GenerationFailure, ProviderCascade, ProviderConfigurationError
from resilience.state import PostgresState
from tools.web import WebTool

config: InfrastructureConfig = load_infrastructure_config()
db_pool: asyncpg.Pool | None = None
state: PostgresState | None = None
brain: Brain | None = None
cascade: ProviderCascade | None = None
replication_task: asyncio.Task[None] | None = None
remote_ai_ready: tuple[float, dict[str, Any]] | None = None
logger = logging.getLogger("nexo.c33")
READINESS_PROBE_TIMEOUT_SECONDS = 3.0

_RATE_LIMIT_WINDOW_SECONDS = 60.0
_RATE_LIMIT_GENERATION = 30
_RATE_LIMIT_AI_READY = 12
_rate_limit_lock = asyncio.Lock()
_rate_limit_buckets: dict[tuple[str, str], list[float]] = {}

async def _enforce_rate_limit(request: Request, scope: str, limit: int) -> None:
    client_host = request.client.host if request.client else "unknown"
    key = (scope, client_host)
    now = time.monotonic()
    async with _rate_limit_lock:
        hits = [stamp for stamp in _rate_limit_buckets.get(key, []) if now - stamp < _RATE_LIMIT_WINDOW_SECONDS]
        if len(hits) >= limit:
            retry_after = max(1, int(_RATE_LIMIT_WINDOW_SECONDS - (now - hits[0])) + 1)
            _rate_limit_buckets[key] = hits
            raise HTTPException(
                status_code=429,
                detail={"reason": "rate_limited", "scope": scope},
                headers={"Retry-After": str(retry_after)},
            )
        hits.append(now)
        _rate_limit_buckets[key] = hits
        if len(_rate_limit_buckets) > 4096:
            stale = [
                bucket_key
                for bucket_key, stamps in _rate_limit_buckets.items()
                if not stamps or now - stamps[-1] >= _RATE_LIMIT_WINDOW_SECONDS
            ]
            for bucket_key in stale[:1024]:
                _rate_limit_buckets.pop(bucket_key, None)

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
    global db_pool, state, brain, cascade, replication_task, remote_ai_ready
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
        try:
            cascade.validate_configuration()
        except ProviderConfigurationError:
            logger.exception(
                "[NEXO_DEBUG_CONFIG] provider_configuration_invalid "
                "deployment_sha=%s environment=%s",
                _deployment_sha(),
                config.environment,
            )
            raise
        logger.info(
            "[NEXO_DEBUG_CONFIG] provider_configuration_valid ids=%s "
            "count=%s failure_domains=%s redundancy_required=%s local_fallback_enabled=%s",
            cascade.configured_provider_ids,
            cascade.configured_provider_count,
            cascade.failure_domains,
            cascade.require_redundancy,
            config.local_fallback_enabled,
        )
        brain = Brain(state, WebTool(timeout=min(config.network_timeout_seconds, 8.0), max_results=5), cascade)
        replication_task = asyncio.create_task(_replication_loop())
    try:
        yield
    finally:
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
        remote_ai_ready = None

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
            logger.warning("[NEXO_DEBUG_READY] configuration_failed reason=%s http_status=%s attempts=%s", exc.reason, exc.http_status, exc.attempts)
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
        "providers_configured":cascade.configured_provider_count,
        "providers_ordered":cascade.configured_provider_count,
        "providers_selectable":cascade.configured_provider_count,
        "provider_order":cascade.configured_provider_ids,
        "provider_failure_domains":cascade.failure_domains,
        "provider_configuration_valid":True,
        "local_fallback_enabled":config.local_fallback_enabled,
        "last_successful_provider":(remote_ai_ready[1].get("provider_used") if remote_ai_ready else None),
        "providers":await state.all_circuit_snapshots([p.provider_id for p in cascade.providers]),
        "peer_status":await _peer_probe(),
        "replication_pending":await state.replication_pending_count(),
    }

@app.get("/v1/ai-ready")
async def ai_ready(request: Request) -> dict[str, Any]:
    """Actively validate the remote AI path with a bounded, non-fallback probe."""
    await _enforce_rate_limit(request, "ai-ready", _RATE_LIMIT_AI_READY)
    logger.info("[NEXO_DEBUG_READY] start")
    global remote_ai_ready
    _require_runtime()
    # /v1/ai-ready is a hard live probe. A cached success must never masquerade
    # as current provider readiness.
    remote_ai_ready = None
    probe_budget = DeadlineBudget(
        min(config.backend_total_timeout_ms, int(READINESS_PROBE_TIMEOUT_SECONDS * 1000)),
        int((time.time() + min(config.backend_total_timeout_ms, int(READINESS_PROBE_TIMEOUT_SECONDS * 1000)) / 1000) * 1000),
    )
    logger.info("[NEXO_DEBUG_READY] probe_begin timeout_s=%.1f configured_backend_timeout_ms=%s", READINESS_PROBE_TIMEOUT_SECONDS, config.backend_total_timeout_ms)
    try:
        result = await asyncio.wait_for(
            cascade.complete(
                [{"role": "user", "content": "Reply exactly C33_AI_READY_OK."}],
                probe_budget,
                probe=True,
            ),
            timeout=min(READINESS_PROBE_TIMEOUT_SECONDS, config.backend_total_timeout_ms / 1000),
        )
    except GenerationFailure as exc:
        logger.warning("[NEXO_DEBUG_READY] probe_failed reason=%s http_status=%s attempts=%s", exc.reason, exc.http_status, exc.attempts)
        raise HTTPException(
            status_code=503,
            detail={
                "status": "not_ready",
                "reason": exc.reason,
                "attempts": exc.attempts,
                "used_local_fallback": False,
            },
        ) from exc
    except asyncio.TimeoutError as exc:
        logger.warning("[NEXO_DEBUG_READY] probe_timeout")
        raise HTTPException(
            status_code=503,
            detail={
                "status": "not_ready",
                "reason": "readiness_probe_timeout",
                "used_local_fallback": False,
            },
        ) from exc

    logger.info("[NEXO_DEBUG_READY] probe_success provider=%s model=%s latency_ms=%s failover=%s", result.meta.provider_used, result.meta.model, result.meta.latency_ms, result.meta.failover_triggered)
    remote_ai_ready = (
        time.monotonic() + 5.0,
        {
            "status": "ai_ready",
            "service": "C-33",
            "provider_used": result.meta.provider_used,
            "model": result.meta.model,
            "latency_ms": result.meta.latency_ms,
            "failover_triggered": result.meta.failover_triggered,
            "deployment_sha": _deployment_sha(),
        },
    )
    return dict(remote_ai_ready[1])

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
    global remote_ai_ready
    remote_ai_ready = (
        time.monotonic() + 15.0,
        {
            "status": "ai_ready",
            "service": "C-33",
            "provider_used": result.model_meta.get("provider_used"),
            "model": result.model_meta.get("model"),
            "latency_ms": result.model_meta.get("latency_ms", 0),
            "failover_triggered": result.model_meta.get("failover_triggered", False),
            "deployment_sha": _deployment_sha(),
        },
    )
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
    await _enforce_rate_limit(request, "generation", _RATE_LIMIT_GENERATION)
    try:
        return await asyncio.wait_for(_handle_chat(payload, request), timeout=config.backend_total_timeout_ms / 1000)
    except ClientDisconnected as exc:
        # Proxies may emit HTTP 499; when the socket is still writable this is explicit in our API contract.
        raise HTTPException(status_code=499, detail={"reason":str(exc)}) from exc
    except asyncio.TimeoutError as exc:
        raise HTTPException(status_code=504, detail={"reason":"backend_deadline_exceeded"}) from exc

@app.post("/v1/ai/stream")
async def ai_stream(payload: ChatRequest, request: Request) -> StreamingResponse:
    await _enforce_rate_limit(request, "generation", _RATE_LIMIT_GENERATION)
    st, b, providers = _require_runtime()
    request_id = payload.request_id.strip() or os.urandom(12).hex()
    fingerprint = hashlib.sha256(payload.message.encode("utf-8")).hexdigest()[:12]
    logger.info("[NEXO_DEBUG_STREAM] start request_id=%s conversation_id=%s fingerprint=%s", request_id, payload.conversation_id, fingerprint)

    existing = await st.existing_assistant_for_request(payload.conversation_id, request_id)
    logger.info("[NEXO_DEBUG_STREAM] idempotency_check request_id=%s existing=%s", request_id, bool(existing))
    if existing:
        stored_meta = dict(existing.metadata.get("meta", {})) if isinstance(existing.metadata, dict) else {}
        stored_meta.setdefault("request_id", request_id)
        stored_meta.setdefault("conversation_id", payload.conversation_id)
        stored_meta.setdefault("used_local_fallback", existing.metadata.get("provider_used") == "local" if isinstance(existing.metadata, dict) else False)
        stored_meta["replayed"] = True

        async def replay_events():
            if stored_meta.get("used_local_fallback"):
                yield "event: fallback\n"
            else:
                yield "event: token\n"
            yield "data: " + json.dumps(
                ({"text": existing.content, "_meta": stored_meta} if stored_meta.get("used_local_fallback") else {"text": existing.content}),
                ensure_ascii=False,
            ) + "\n\n"
            yield "event: done\n"
            yield "data: " + json.dumps({"_meta": stored_meta}, ensure_ascii=False) + "\n\n"

        return StreamingResponse(
            replay_events(),
            media_type="text/event-stream",
            headers={"Cache-Control":"no-cache, no-transform","Connection":"keep-alive","X-Accel-Buffering":"no"},
        )

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

    logger.info("[NEXO_DEBUG_STREAM] prepare_begin request_id=%s", request_id)
    messages, sources, _ = await _run_with_disconnect(
        request,
        b.prepare_messages(
            payload.message,
            user_id=payload.user_id,
            conversation_id=payload.conversation_id,
            personality_mode=payload.personality,
            budget=budget,
        ),
    )
    logger.info("[NEXO_DEBUG_STREAM] prepare_done request_id=%s remaining_ms=%s sources=%s", request_id, budget.remaining_ms, len(sources))
    if budget.remaining_ms <= 0:
        raise HTTPException(status_code=504, detail={"reason":"backend_deadline_exceeded"})

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
            logger.info("[NEXO_DEBUG_STREAM] provider_stream_begin request_id=%s remaining_ms=%s", request_id, budget.remaining_ms)
            async for piece, meta in providers.stream(messages, budget):
                if await request.is_disconnected():
                    return
                stream_meta = meta
                if not pieces:
                    logger.info("[NEXO_DEBUG_STREAM] first_token request_id=%s provider=%s model=%s", request_id, meta.provider_used, meta.model)
                pieces.append(piece)
                yield "event: token\n"
                yield "data: " + json.dumps({"text":piece}, ensure_ascii=False) + "\n\n"
            final = "".join(pieces).strip()
            logger.info("[NEXO_DEBUG_STREAM] provider_stream_complete request_id=%s chars=%s provider=%s failover=%s remaining_ms=%s", request_id, len(final), stream_meta.provider_used if stream_meta else "unknown", stream_meta.failover_triggered if stream_meta else None, budget.remaining_ms)
            if not final or stream_meta is None:
                raise GenerationFailure("empty_stream", http_status=502, attempts=[])
            global remote_ai_ready
            remote_ai_ready = (
                time.monotonic() + 15.0,
                {
                    "status": "ai_ready",
                    "service": "C-33",
                    "provider_used": stream_meta.provider_used,
                    "model": stream_meta.model,
                    "latency_ms": int((time.monotonic() - started) * 1000),
                    "failover_triggered": stream_meta.failover_triggered,
                    "deployment_sha": _deployment_sha(),
                },
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
            await st.append_message(
                conversation_id=payload.conversation_id,
                user_id=payload.user_id,
                role="assistant",
                content=final,
                metadata={"provider_used":stream_meta.provider_used,"model":stream_meta.model,"stream":True,"sources":sources,"meta":final_meta},
                request_id=request_id,
            )
            yield "event: done\n"
            yield "data: " + json.dumps({"_meta":final_meta}, ensure_ascii=False) + "\n\n"
        except GenerationFailure as exc:
            logger.warning("[NEXO_DEBUG_STREAM] generation_failure request_id=%s reason=%s http_status=%s attempts=%s pieces=%s remaining_ms=%s", request_id, exc.reason, exc.http_status, exc.attempts, len(pieces), budget.remaining_ms)
            if await request.is_disconnected():
                return
            if pieces:
                yield "event: error\n"
                yield "data: " + json.dumps({
                    "reason":exc.reason,
                    "_meta":{"final_reason":exc.reason,"system_status":"DEGRADED","used_local_fallback":False},
                }, ensure_ascii=False) + "\n\n"
                return
            requested_local_fallback = request.headers.get("X-C33-Allow-Local-Fallback", "true").strip().lower() in {"1", "true", "yes", "on"}
            allow_local_fallback = (
                requested_local_fallback
                and config.local_fallback_enabled
                and config.environment != "production"
            )
            if not allow_local_fallback:
                if config.environment == "production" and requested_local_fallback:
                    logger.warning(
                        "[NEXO_DEBUG_STREAM] local_fallback_blocked_in_production request_id=%s reason=%s",
                        request_id,
                        exc.reason,
                    )
                yield "event: error\n"
                yield "data: " + json.dumps({"reason":exc.reason,"_meta":{"final_reason":exc.reason,"used_local_fallback":False}}, ensure_ascii=False) + "\n\n"
                return
            logger.warning("[NEXO_DEBUG_STREAM] fallback_activate request_id=%s reason=%s", request_id, exc.reason)
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
        except Exception as exc:
            logger.exception(
                "[NEXO_DEBUG_STREAM] unhandled_stream_crash request_id=%s pieces=%s",
                request_id,
                len(pieces),
            )
            if not await request.is_disconnected():
                yield "data: [NEXO_STREAM_CRASH]\n\n"
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
        headers={"Cache-Control":"no-cache, no-transform","Connection":"keep-alive","X-Accel-Buffering":"no"},
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
