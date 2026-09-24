from __future__ import annotations

import httpx


class WebTool:
    """Small HTTP/web access boundary for the agent."""

    def __init__(self, timeout: float = 15.0) -> None:
        self.timeout = timeout

    async def fetch(self, url: str) -> str:
        async with httpx.AsyncClient(
            timeout=self.timeout,
            follow_redirects=True,
        ) as client:
            response = await client.get(
                url,
                headers={"User-Agent": "C-33/0.1"},
            )
            response.raise_for_status()
            return response.text

    async def search(self, query: str) -> str:
        url = "https://html.duckduckgo.com/html/"
        async with httpx.AsyncClient(
            timeout=self.timeout,
            follow_redirects=True,
        ) as client:
            response = await client.get(
                url,
                params={"q": query},
                headers={"User-Agent": "C-33/0.1"},
            )
            response.raise_for_status()
            return response.text
