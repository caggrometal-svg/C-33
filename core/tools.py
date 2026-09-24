from collections.abc import Awaitable, Callable
from dataclasses import dataclass


ToolHandler = Callable[[str], Awaitable[str]]


@dataclass(frozen=True)
class Tool:
    name: str
    handler: ToolHandler
    description: str = ""


class ToolRegistry:
    def __init__(self, tools: list[Tool] | None = None) -> None:
        self._tools = {tool.name: tool for tool in tools or []}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    async def execute(self, name: str, argument: str) -> str:
        tool = self._tools.get(name)
        if tool is None:
            return f"tool_error: unknown tool '{name}'"
        return await tool.handler(argument)

    def names(self) -> Sequence[str]:
        return tuple(self._tools)
