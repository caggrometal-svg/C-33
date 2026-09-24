from fastapi import FastAPI

from core.agent import Agent
from core.memory import InMemoryMemory
from core.tools import ToolRegistry

app = FastAPI(title="C-33", version="0.1.0")

agent = Agent(memory=InMemoryMemory(), tools=ToolRegistry())


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "C-33"}


@app.post("/agent/run")
async def run_agent(prompt: str) -> dict[str, object]:
    result = await agent.run(prompt)
    return result
