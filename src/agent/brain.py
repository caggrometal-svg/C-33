from dataclasses import dataclass
from typing import Protocol

from memory.store import MemoryStore
from tools.web import WebTool


class Reasoner(Protocol):
    async def decide(self, prompt: str, context: list[str]) -> str: ...


class BaseReasoner:
    """Minimal deterministic reasoner used until an AI engine is connected."""

    async def decide(self, prompt: str, context: list[str]) -> str:
        return prompt.strip()


@dataclass
class Brain:
    memory: MemoryStore
    web: WebTool
    max_steps: int = 8
    reasoner: Reasoner | None = None

    async def run(self, prompt: str) -> dict[str, object]:
        reasoner = self.reasoner or BaseReasoner()
        context = await self.memory.recall(prompt)
        steps: list[dict[str, str]] = []

        for number in range(1, self.max_steps + 1):
            action = await reasoner.decide(prompt, context)
            steps.append({"step": str(number), "action": action})

            if action.startswith("tool:web:"):
                query = action.removeprefix("tool:web:").strip()
                result = await self.web.search(query)
                context.append(result)
                continue

            await self.memory.remember(prompt, action)
            return {
                "status": "ok",
                "response": action,
                "steps": steps,
            }

        return {
            "status": "max_steps_reached",
            "response": context[-1] if context else "",
            "steps": steps,
        }
