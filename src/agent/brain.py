"""Autonomous ReAct-style orchestration for C-33."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlparse

import httpx

from core.config import DEFAULT_DEBATE_SYSTEM_PROMPT
from memory.store import MemoryEntry, MemoryStore
from tools.web import SearchResult, WebPage, WebTool


class ChatModel(Protocol):
    """Protocol for any model that can produce text from chat messages."""

    async def complete(self, messages: list[dict[str, str]]) -> str: ...


class CompatibleChatModel:
    """Minimal OpenAI-compatible chat client usable with any compatible endpoint."""

    def __init__(
        self,
        base_url: str,
        model_name: str,
        api_key: str | None,
        *,
        timeout: float = 30.0,
        temperature: float = 0.2,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model_name = model_name.strip()
        self.api_key = api_key
        self.timeout = timeout
        self.temperature = temperature

    @property
    def available(self) -> bool:
        """Return whether enough configuration exists to call the model endpoint."""
        return bool(self.base_url and self.model_name)

    async def complete(self, messages: list[dict[str, str]]) -> str:
        """Call the configured compatible chat-completions endpoint."""
        if not self.available:
            raise RuntimeError("Model client is not configured")

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload = {
            "model": self.model_name,
            "messages": messages,
            "temperature": self.temperature,
        }
        url = f"{self.base_url}/chat/completions"
        async with httpx.AsyncClient(
            timeout=self.timeout,
            follow_redirects=True,
        ) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()

        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError("Model response did not contain message content") from exc
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError("Model returned an empty response")
        return content.strip()


@dataclass(slots=True)
class AgentTrace:
    """Observable action trace that excludes hidden chain-of-thought content."""

    step: int
    action: str
    detail: str


@dataclass(slots=True)
class AgentResult:
    """Final result returned by a Brain run."""

    response: str
    trace: list[AgentTrace]
    sources: list[str]
    memory_hits: list[MemoryEntry]


class Brain:
    """Coordinate planning, memory retrieval, web tools, and final synthesis."""

    def __init__(
        self,
        memory: MemoryStore,
        web: WebTool,
        *,
        max_steps: int = 8,
        model: ChatModel | None = None,
    ) -> None:
        if max_steps < 1:
            raise ValueError("max_steps must be >= 1")
        self.memory = memory
        self.web = web
        self.max_steps = max_steps
        self.model = model

    async def process(self, prompt: str) -> AgentResult:
        """Process a user message through the C-33 reasoning engine."""
        return await self.run(prompt)

    async def run(self, prompt: str) -> AgentResult:
        """Execute a bounded ReAct loop and persist the final interaction."""
        prompt = prompt.strip()
        if not prompt:
            raise ValueError("Prompt cannot be empty")

        memory_hits = await self.memory.search_context(prompt)
        context: list[str] = self._memory_context(memory_hits)
        trace: list[AgentTrace] = []
        sources: list[str] = []
        used_actions: set[str] = set()

        for step in range(1, self.max_steps + 1):
            decision = await self._decide(prompt, context, used_actions)
            action = decision["action"]
            argument = decision.get("argument", "").strip()
            used_actions.add(action)

            trace.append(AgentTrace(step=step, action=action, detail=argument))

            if action == "memory":
                memory_hits = await self.memory.search_context(argument or prompt)
                context.extend(self._memory_context(memory_hits))
                continue

            if action in {"web_search", "web_search_counter"}:
                query = argument or prompt
                if action == "web_search_counter":
                    query = f"{query} counterargument evidence criticism limitations alternative view"
                results = await self.web.search(query)
                context.extend(self._search_context(results, perspective=action))
                sources.extend(result.url for result in results)
                continue

            if action == "fetch_url":
                page = await self.web.fetch(argument)
                context.append(self._page_context(page))
                sources.append(page.url)
                continue

            if action == "final":
                response = await self._synthesize(prompt, context)
                await self.memory.save(
                    prompt,
                    response,
                    summary=response[:240],
                    tags=[trace[-1].action, "interaction"],
                    debate_topic=self._debate_topic(prompt),
                    user_position=prompt[:500],
                    central_arguments=self._central_arguments(prompt, response),
                )
                return AgentResult(
                    response=response,
                    trace=trace,
                    sources=self._unique(sources),
                    memory_hits=memory_hits,
                )

        response = await self._synthesize(prompt, context)
        await self.memory.save(prompt, response, summary=response[:240], tags=["max_steps"], debate_topic=self._debate_topic(prompt), user_position=prompt[:500], central_arguments=self._central_arguments(prompt, response))
        return AgentResult(
            response=response,
            trace=trace,
            sources=self._unique(sources),
            memory_hits=memory_hits,
        )

    async def _decide(
        self,
        prompt: str,
        context: list[str],
        used_actions: set[str],
    ) -> dict[str, str]:
        """Ask the configured model for a JSON action, or use a deterministic fallback."""
        if self.model is not None:
            try:
                raw = await self.model.complete(
                    [
                        {
                            "role": "system",
                            "content": (
                                "You are the C-33 planner. Decide the next observable action only. "
                                "Return JSON with action and argument. Actions: memory, web_search, web_search_counter, "
                                "fetch_url, web_search_counter, final. Never return hidden chain-of-thought or analysis. "
                                "Use web_search for current or externally verifiable information; "
                                "use memory for relevant prior context; use fetch_url when a concrete URL "
                                "is provided or discovered; use final when enough evidence exists."
                            ),
                        },
                        {
                            "role": "user",
                            "content": json.dumps(
                                {
                                    "prompt": prompt,
                                    "context": context[-12:],
                                    "used_actions": sorted(used_actions),
                                },
                                ensure_ascii=False,
                            ),
                        },
                    ]
                )
                parsed = self._parse_decision(raw)
                if parsed["action"] not in used_actions or parsed["action"] == "final":
                    return parsed
            except (RuntimeError, ValueError, KeyError, TypeError):
                return self._heuristic_decision(prompt, context, used_actions)
        return self._heuristic_decision(prompt, context, used_actions)

    async def _synthesize(self, prompt: str, context: list[str]) -> str:
        """Synthesize the final answer with the configured model or a safe local fallback."""
        if self.model is not None:
            try:
                return await self.model.complete(
                    [
                        {
                            "role": "system",
                            "content": (
                                "You are C-33. Answer the user's question directly using the supplied context. "
                                "Do not reveal hidden chain-of-thought. Distinguish retrieved facts from uncertainty. "
                                "When web evidence exists, cite the relevant URLs in a compact Sources section. " + DEFAULT_DEBATE_SYSTEM_PROMPT
                            ),
                        },
                        {
                            "role": "user",
                            "content": json.dumps(
                                {"prompt": prompt, "context": context[-16:]},
                                ensure_ascii=False,
                            ),
                        },
                    ]
                )
            except (RuntimeError, ValueError, KeyError, TypeError):
                return self._fallback_synthesis(prompt, context)
        return self._fallback_synthesis(prompt, context)

    @staticmethod
    def _parse_decision(raw: str) -> dict[str, str]:
        """Parse a model action without accepting arbitrary executable content."""
        candidate = raw.strip().replace(chr(96) * 3, "").strip()
        data = json.loads(candidate)
        if not isinstance(data, dict):
            raise ValueError("Planner response must be an object")
        action = str(data.get("action", "")).strip()
        argument = str(data.get("argument", "")).strip()
        if action not in {"memory", "web_search", "web_search_counter", "fetch_url", "final"}:
            raise ValueError(f"Unsupported planner action: {action!r}")
        if action == "fetch_url":
            parsed = urlparse(argument)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise ValueError("fetch_url requires a valid HTTP(S) URL")
        return {"action": action, "argument": argument}

    @staticmethod
    def _heuristic_decision(
        prompt: str,
        context: list[str],
        used_actions: set[str],
    ) -> dict[str, str]:
        """Choose a bounded action using currentness and context signals when no model is available."""
        lower = prompt.lower()
        if re.search(r"https?://\S+", prompt) and "fetch_url" not in used_actions:
            url = re.search(r"https?://\S+", prompt)
            return {
                "action": "fetch_url",
                "argument": url.group(0).rstrip(".,)") if url else prompt,
            }

        current_markers = {
            "latest",
            "today",
            "ahora",
            "actual",
            "current",
            "news",
            "noticia",
            "precio",
            "price",
            "2026",
        }
        debate_markers = {
            "debate", "argumento", "argumentos", "tesis", "antitesis", "antítesis",
            "controversia", "polémica", "polemica", "es verdad", "realmente",
            "evidencia", "prueba", "falacia", "versus", "vs", "discutir",
            "dispute", "claim", "counterargument", "hypothesis",
        }
        needs_web = any(marker in lower for marker in current_markers)
        contested = any(marker in lower for marker in debate_markers)
        if (needs_web or contested) and "web_search" not in used_actions:
            return {"action": "web_search", "argument": prompt}
        if (needs_web or contested) and "web_search_counter" not in used_actions:
            return {"action": "web_search_counter", "argument": prompt}
        if context and "memory" not in used_actions:
            return {"action": "memory", "argument": prompt}
        if not context and "web_search" not in used_actions and len(prompt.split()) >= 4:
            return {"action": "web_search", "argument": prompt}
        return {"action": "final", "argument": ""}

    @staticmethod
    def _memory_context(entries: list[MemoryEntry]) -> list[str]:
        """Format memory entries for the planner without exposing internal storage details."""
        return [
            (
                f"Memory {entry.created_at}: topic={entry.debate_topic or 'general'} | "
                f"user_position={entry.user_position or entry.user_text} | "
                f"arguments={'; '.join(entry.central_arguments) or entry.summary}"
            )
            for entry in entries
        ]

    @staticmethod
    def _search_context(results: list[SearchResult], *, perspective: str = "web_search") -> list[str]:
        """Format search results as concise evidence strings."""
        label = "counter-evidence" if perspective == "web_search_counter" else "evidence"
        return [
            f"Web {label}: {item.title} | {item.url} | {item.snippet}" for item in results
        ]

    @staticmethod
    def _page_context(page: WebPage) -> str:
        """Format a fetched page for model synthesis."""
        return (
            f"Web page: {page.title} | {page.url}\n"
            f"Summary: {page.summary}\n"
            f"Text: {page.text[:4000]}"
        )

    @staticmethod
    def _fallback_synthesis(prompt: str, context: list[str]) -> str:
        """Return a transparent local answer when no external model is configured."""
        if not context:
            return (
                "C-33 recibió la consulta, pero no hay un modelo configurado para generar una respuesta "
                "semántica. Configura MODEL_BASE_URL y MODEL_NAME en .env para activar síntesis de modelo."
            )
        evidence = "\n".join(f"- {item}" for item in context[-5:])
        return f"Contexto recuperado para: {prompt}\n\n{evidence}"

    @staticmethod
    def _debate_topic(prompt: str) -> str:
        return re.sub(r"\s+", " ", prompt).strip()[:180]

    @staticmethod
    def _central_arguments(prompt: str, response: str) -> list[str]:
        return [prompt.strip()[:500], response.strip()[:700]]

    @staticmethod
    def _unique(values: list[str]) -> list[str]:
        """Preserve order while removing duplicate URLs."""
        return list(dict.fromkeys(values))
