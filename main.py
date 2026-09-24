from fastapi import FastAPI

from agent.base import Agent
from memory.base import InMemoryMemory
from tools.registry import ToolRegistry

app = FastAPI(title="C-33", version="0.1.0")

agent = Agent(memory=InMemoryMemory(), tools=ToolRegistry())


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "C-33"}


@app.post("/agent/run")
async def run_agent(prompt: str) -> dict[str, object]:
    return await agent.run(prompt)
