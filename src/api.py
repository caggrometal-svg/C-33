"""Production FastAPI service for C-33."""

from __future__ import annotations

import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import asyncpg
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

_SRC_DIR = str(Path(__file__).resolve().parent)
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

from agent.brain import AgentResult, Brain, CompatibleChatModel
from config import InfrastructureConfig, load_infrastructure_config
from core.config import load_settings
from memory.store import MemoryStore
from tools.web import WebTool


config: InfrastructureConfig = load_infrastructure_config()
core_settings = load_settings()
db_pool: asyncpg.Pool | None = None


async def _database_check() -> bool:
    """Validate that PostgreSQL is reachable from the running service."""
    if db_pool is None:
        return config.database_url is None
    try:
        async with db_pool.acquire() as connection:
            await connection.fetchval("SELECT 1")
        return True
    except (OSError, asyncpg.PostgresError):
        return False


async def _initialize_database() -> asyncpg.Pool | None:
    """Create a bounded PostgreSQL pool when DATABASE_URL is configured."""
    if not config.database_url:
        return None
    return await asyncpg.create_pool(
        dsn=config.database_url,
        min_size=1,
        max_size=5,
        command_timeout=10,
        timeout=10,
    )


def build_brain() -> Brain:
    """Build the C-33 reasoning runtime."""
    model_base_url = config.model_base_url or core_settings.model_base_url
    model_api_key = config.model_api_key or core_settings.model_api_key

    model = None
    if model_base_url and config.model_name:
        model = CompatibleChatModel(
            model_base_url,
            config.model_name,
            model_api_key,
            timeout=config.network_timeout_seconds,
            temperature=core_settings.model_temperature,
        )

    memory = MemoryStore(
        core_settings.memory_file,
        short_term_limit=core_settings.short_term_limit,
        long_term_limit=core_settings.long_term_limit,
    )
    web = WebTool(
        config.network_timeout_seconds,
        max_results=core_settings.search_max_results,
    )
    return Brain(
        memory,
        web,
        max_steps=core_settings.agent_max_steps,
        model=model,
    )


brain = build_brain()


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Open and close PostgreSQL when configured; keep edge mode stateless otherwise."""
    global db_pool
    db_pool = await _initialize_database()
    try:
        if config.database_url and not await _database_check():
            raise RuntimeError("DATABASE_URL is configured but PostgreSQL is unreachable")
        yield
    finally:
        if db_pool is not None:
            await db_pool.close()
            db_pool = None


app = FastAPI(
    title="C-33 API",
    version="1.0.0",
    description="Production API for C-33.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    """Request model for the C-33 reasoning endpoint."""

    message: str = Field(min_length=1, max_length=20_000)
    user_id: str = Field(default="anonymous", min_length=1, max_length=256)
    stream: bool = False


class ChatResponse(BaseModel):
    """Observable response without exposing hidden reasoning."""

    status: str
    service: str
    user_id: str
    synthesis: str
    web_searches: list[str]
    trace: list[dict[str, str | int]]
    stream_requested: bool


async def _chat(payload: ChatRequest) -> ChatResponse:
    """Run Brain.process."""
    try:
        result: AgentResult = await brain.process(payload.message)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="C-33 processing failed") from exc

    return ChatResponse(
        status="ok",
        service="C-33",
        user_id=payload.user_id,
        synthesis=result.response,
        web_searches=result.sources,
        trace=[
            {
                "step": item.step,
                "action": item.action,
                "detail": item.detail,
            }
            for item in result.trace
        ],
        stream_requested=payload.stream,
    )


@app.get("/health")
async def health() -> dict[str, Any]:
    """Healthcheck with process and optional PostgreSQL state."""
    database_ok = await _database_check()
    database_state = "ok" if config.database_url and database_ok else (
        "not_configured" if config.database_url is None else "unavailable"
    )
    return {
        "status": "ok" if database_ok else "degraded",
        "service": "C-33",
        "database": database_state,
    }


@app.get("/status")
async def status() -> dict[str, Any]:
    """Runtime status with infrastructure and model state."""
    database_ok = await _database_check()
    database_state = "ok" if config.database_url and database_ok else (
        "not_configured" if config.database_url is None else "unavailable"
    )
    return {
        "status": "ok" if database_ok else "degraded",
        "service": "C-33",
        "database": database_state,
        "ai": "configured" if brain.model is not None else "local-fallback",
        "internet": "available",
        "environment": config.environment,
    }


@app.post("/api/chat", response_model=ChatResponse)
async def api_chat(payload: ChatRequest, request: Request) -> ChatResponse:
    """Compatibility chat endpoint."""
    request.state.api_service = "C-33"
    return await _chat(payload)


@app.post("/v1/chat", response_model=ChatResponse)
async def v1_chat(payload: ChatRequest, request: Request) -> ChatResponse:
    """Versioned chat endpoint."""
    request.state.api_service = "C-33"
    return await _chat(payload)
