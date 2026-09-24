from fastapi import FastAPI
from pydantic import BaseModel

from agent.brain import Brain
from core.config import load_settings
from core.logging import configure_logging
from memory.store import FileMemory
from tools.web import WebTool

configure_logging()
settings = load_settings()

app = FastAPI(title=settings.app_name, version="0.1.0")

brain = Brain(
    memory=FileMemory(settings.memory_file),
    web=WebTool(settings.web_timeout_seconds),
    max_steps=settings.agent_max_steps,
)


class AgentRequest(BaseModel):
    prompt: str


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": settings.app_name}


@app.post("/agent/run")
async def run_agent(request: AgentRequest) -> dict[str, object]:
    return await brain.run(request.prompt)
