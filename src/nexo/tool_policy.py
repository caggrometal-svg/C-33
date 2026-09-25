"""Explicit tool capability policy for the NEXO tool hub."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ToolCapability:
    name: str
    network: bool = False
    mutates_state: bool = False
    risk: str = "low"


class ToolPolicy:
    def __init__(self, capabilities: list[ToolCapability] | None = None) -> None:
        self._caps = {item.name: item for item in (capabilities or [])}

    def register(self, capability: ToolCapability) -> None:
        if not capability.name.strip():
            raise ValueError("tool_capability_name_required")
        self._caps[capability.name.strip()] = capability

    def get(self, name: str) -> ToolCapability | None:
        return self._caps.get(name.strip())

    def allows(self, name: str, *, network_allowed: bool = True, mutations_allowed: bool = False) -> bool:
        capability = self.get(name)
        if capability is None:
            return False
        if capability.network and not network_allowed:
            return False
        if capability.mutates_state and not mutations_allowed:
            return False
        return True

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._caps))
