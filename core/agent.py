from dataclasses import dataclass
from typing import Protocol

from core.memory import Memory
from core.tools import ToolRegistry


class Reasoner(Protocol):
    async def decide(self, prompt: str, context: list[str]) -> str: ...


class BasicReasoner:
    """Deterministic placeholder until a real reasoning engine is selected."""

    async def decide(self, prompt: str, context: list[str]) -> str:
        return prompt


@dataclass
class Agent:
    memory: Memory
    tools: ToolRegistry
    reasoner: Reasoner | None = None
    max_steps: int = 8

    async def run(self, prompt: str) -> dict[str, object]:
        reasoner = self.reasoner or BasicReasoner()
        context = await self.memory.recall(prompt)
        steps: list[str] = []

        for _ in range(self.max_steps):
            action = await reasoner.decide(prompt, context)
            steps.append(action)

            if action.startswith("tool:"):
                name, _, argument = action[5:].partition(":")
                result = await self.tools.execute(name, argument)
                context.append(result)
                continue

            await self.memory.remember(prompt, action)
            return {"status": "ok", "response": action, "steps": steps}

        return {
            "status": "max_steps_reached",
            "response": context[-1] if context else "",
            "steps": steps,
        }
