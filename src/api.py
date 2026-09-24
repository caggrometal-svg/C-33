"""FastAPI service entry point for C-33."""

from __future__ import annotations

import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from agent.brain import AgentResult, Brain, CompatibleChatModel
from core.config import Settings, load_settings
from memory.store import MemoryStore
from tools.web import WebTool

settings: Settings = load_settings()


def build_brain() -> Brain:
    """Build the C-33 runtime using environment configuration."""
    model_base_url = settings.model_base_url
    api_key = settings.model_api_key or os.getenv("OPENAI_API_KEY", "").strip() or None

    if not model_base_url and api_key:
        model_base_url = "https://api.openai.com/v1"

    model = None
    if model_base_url and settings.model_name:
        model = CompatibleChatModel(
            model_base_url,
            settings.model_name,
            api_key,
            timeout=settings.network_timeout_seconds,
            temperature=settings.model_temperature,
        )

    memory = MemoryStore(
        settings.memory_file,
        short_term_limit=settings.short_term_limit,
        long_term_limit=settings.long_term_limit,
    )
    web = WebTool(
        settings.network_timeout_seconds,
        max_results=settings.search_max_results,
    )
    return Brain(
        memory,
        web,
        max_steps=settings.agent_max_steps,
        model=model,
    )


brain = build_brain()

app = FastAPI(
    title="C-33 API",
    version="0.2.0",
    description="Backend API for the C-33 dialectical reasoning engine.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    """Chat request accepted by both mobile API routes."""

    message: str = Field(min_length=1, max_length=20_000)
    user_id: str = Field(min_length=1, max_length=256)
    stream: bool = False


class ChatResponse(BaseModel):
    """Observable C-33 response. Trace contains actions, not hidden chain-of-thought."""

    user_id: str
    synthesis: str
    web_searches: list[str]
    trace: list[dict[str, str | int]]
    stream_requested: bool


@app.get("/health")
async def health() -> dict[str, str]:
    """Health probe for Railway and Render."""
    return {"status": "ok", "service": "c33-api", "version": "0.2.0"}


@app.get("/status")
async def status() -> dict[str, str]:
    """Runtime status probe for Railway and Render."""
    model_configured = bool(
        settings.model_name
        and (settings.model_base_url or os.getenv("OPENAI_API_KEY", "").strip())
    )
    return {
        "status": "ok",
        "service": "c33-api",
        "environment": settings.environment,
        "model": "configured" if model_configured else "local-fallback",
    }


async def _chat(payload: ChatRequest) -> ChatResponse:
    """Run Brain.process and expose synthesis plus observable evidence."""
    try:
        result: AgentResult = await brain.process(payload.message)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="C-33 processing failed") from exc

    return ChatResponse(
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


@app.post("/v1/chat", response_model=ChatResponse)
async def v1_chat(payload: ChatRequest) -> ChatResponse:
    """Primary versioned chat endpoint."""
    return await _chat(payload)


@app.post("/api/chat", response_model=ChatResponse)
async def api_chat(payload: ChatRequest) -> ChatResponse:
    """Compatibility chat endpoint."""
    return await _chat(payload)
