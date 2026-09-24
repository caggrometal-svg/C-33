"""FastAPI service entry point for deploying C-33 on Railway or Render."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from agent.brain import AgentResult, Brain, CompatibleChatModel
from core.config import Settings, load_settings
from memory.store import MemoryStore
from tools.web import WebTool

settings: Settings = load_settings()


def build_brain() -> Brain:
    """Build the C-33 runtime graph from environment configuration."""
    model = None
    if settings.model_base_url and settings.model_name:
        model = CompatibleChatModel(
            settings.model_base_url,
            settings.model_name,
            settings.model_api_key,
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
    description="Backend API for the C-33 autonomous dialectical reasoning engine.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    """Request payload for the C-33 chat endpoint."""

    message: str = Field(min_length=1, max_length=20_000)
    user_id: str = Field(min_length=1, max_length=256)


class ChatResponse(BaseModel):
    """Response payload containing synthesis and web evidence."""

    user_id: str
    synthesis: str
    web_searches: list[str]
    trace: list[dict[str, str | int]]


@app.get("/health")
async def health() -> dict[str, str]:
    """Return a lightweight health response for platform probes."""
    return {
        "status": "ok",
        "service": "c33-api",
        "version": "0.2.0",
    }


@app.post("/api/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest) -> ChatResponse:
    """Process a message and return the dialectical synthesis plus web sources."""
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
    )
