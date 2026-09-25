"""Asynchronous web search, page extraction, and lightweight summarization."""

from __future__ import annotations

import asyncio

import hashlib
import ipaddress
import logging
import re
import socket
import time
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import parse_qs, unquote, urljoin, urlparse

import httpx

logger = logging.getLogger("nexo.c33.web")


@dataclass(slots=True)
class SearchResult:
    """Search result with a title, target URL, and extracted snippet."""

    title: str
    url: str
    snippet: str


@dataclass(slots=True)
class WebPage:
    """Clean text extracted from a web page."""

    url: str
    title: str
    text: str
    summary: str


class _PageParser(HTMLParser):
    """Small HTML parser that keeps visible textual content and metadata."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title_parts: list[str] = []
        self.text_parts: list[str] = []
        self.meta_description = ""
        self._in_title = False
        self._ignored_depth = 0

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        tag = tag.lower()
        if tag in {"script", "style", "noscript", "svg", "template"}:
            self._ignored_depth += 1
            return
        if tag == "title":
            self._in_title = True
            return
        if tag == "meta":
            values = {key.lower(): value or "" for key, value in attrs}
            if values.get("name", "").lower() == "description":
                self.meta_description = values.get("content", "").strip()

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if (
            tag in {"script", "style", "noscript", "svg", "template"}
            and self._ignored_depth
        ):
            self._ignored_depth -= 1
        elif tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._ignored_depth:
            return
        cleaned = re.sub(r"\s+", " ", data).strip()
        if not cleaned:
            return
        if self._in_title:
            self.title_parts.append(cleaned)
        else:
            self.text_parts.append(cleaned)


class _SearchParser(HTMLParser):
    """Parse the small subset of DuckDuckGo result markup we need."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.results: list[SearchResult] = []
        self._current_url = ""
        self._current_title: list[str] = []
        self._current_snippet: list[str] = []
        self._section: str | None = None

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        classes = {
            value
            for key, value in attrs
            if key.lower() == "class"
            for value in (value or "").split()
        }
        href = next(
            (value for key, value in attrs if key.lower() == "href" and value),
            "",
        )
        if tag == "a" and "result__a" in classes:
            self._flush()
            self._current_url = self._normalize_ddg_url(href)
            self._section = "title"
        elif "result__snippet" in classes:
            self._section = "snippet"

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._section == "title":
            self._section = None

    def handle_data(self, data: str) -> None:
        cleaned = re.sub(r"\s+", " ", data).strip()
        if not cleaned:
            return
        if self._section == "title":
            self._current_title.append(cleaned)
        elif self._section == "snippet":
            self._current_snippet.append(cleaned)

    def close(self) -> None:
        super().close()
        self._flush()

    def _flush(self) -> None:
        if self._current_url and self._current_title:
            self.results.append(
                SearchResult(
                    title=" ".join(self._current_title).strip(),
                    url=self._current_url,
                    snippet=" ".join(self._current_snippet).strip(),
                )
            )
        self._current_url = ""
        self._current_title = []
        self._current_snippet = []
        self._section = None

    @staticmethod
    def _normalize_ddg_url(href: str) -> str:
        parsed = urlparse(href)
        if (
            parsed.netloc
            and parsed.netloc.endswith("duckduckgo.com")
            and parsed.path == "/l/"
        ):
            target = parse_qs(parsed.query).get("uddg", [""])[0]
            return unquote(target)
        return urljoin("https://html.duckduckgo.com", href)


class WebTool:
    """HTTP web tool isolated from the agent loop and model provider."""

    def __init__(self, timeout: float = 15.0, *, max_results: int = 5) -> None:
        if timeout <= 0:
            raise ValueError("timeout must be > 0")
        if max_results < 1:
            raise ValueError("max_results must be >= 1")
        self.timeout = timeout
        self.max_results = max_results
        self._headers = {
            "User-Agent": "C-33/0.2 (+https://github.com/caggrometal-svg/C-33)"
        }

    async def search(self, query: str) -> list[SearchResult]:
        """Search DuckDuckGo HTML results without requiring a paid API key."""
        query = query.strip()
        if not query:
            return []

        query_hash = hashlib.sha256(query.encode("utf-8")).hexdigest()[:12]
        started = time.monotonic()
        logger.info(
            "[NEXO_DEBUG_WEB] search_begin query_hash=%s timeout_s=%.2f host=html.duckduckgo.com",
            query_hash,
            self.timeout,
        )
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout,
                follow_redirects=True,
                headers=self._headers,
            ) as client:
                response = await client.post(
                    "https://html.duckduckgo.com/html/",
                    data={"q": query},
                )
                response.raise_for_status()
                results = self._parse_search_results(response.text)[: self.max_results]
                if not results:
                    raise RuntimeError("no_search_results_parsed")
        except Exception as exc:
            logger.warning(
                "[NEXO_DEBUG_WEB] search_failed query_hash=%s error_class=%s latency_ms=%s",
                query_hash,
                type(exc).__name__,
                int((time.monotonic() - started) * 1000),
            )
            raise

        logger.info(
            "[NEXO_DEBUG_WEB] search_success query_hash=%s status=%s results=%s latency_ms=%s",
            query_hash,
            response.status_code,
            len(results),
            int((time.monotonic() - started) * 1000),
        )
        return results

    async def fetch(self, url: str) -> WebPage:
        """Fetch a public HTTP(S) URL and extract a short deterministic summary."""
        current_url = url.strip()
        for _ in range(4):
            await self._validate_public_url(current_url)
            async with httpx.AsyncClient(
                timeout=self.timeout,
                follow_redirects=False,
                headers=self._headers,
            ) as client:
                response = await client.get(current_url)
            if 300 <= response.status_code < 400:
                location = response.headers.get("location", "").strip()
                if not location:
                    raise RuntimeError("redirect_without_location")
                current_url = urljoin(current_url, location)
                continue
            response.raise_for_status()
            final_url = str(response.url)
            await self._validate_public_url(final_url)
            content_type = response.headers.get("content-type", "")
            if (
                "text/html" not in content_type
                and "application/xhtml+xml" not in content_type
            ):
                text = response.text.strip()
                return WebPage(
                    url=final_url,
                    title=final_url,
                    text=text,
                    summary=self.summarize(text),
                )

            body = response.text

        parser = _PageParser()
        parser.feed(body)
        parser.close()
        title = " ".join(parser.title_parts).strip() or final_url
        text = self._clean_text(" ".join(parser.text_parts))
        if parser.meta_description:
            text = f"{parser.meta_description}\n\n{text}".strip()
        return WebPage(
            url=final_url,
            title=title,
            text=text,
            summary=self.summarize(text),
        )

    def summarize(self, text: str, *, max_chars: int = 700) -> str:
        """Create a lightweight extractive summary from visible page text."""
        clean = self._clean_text(text)
        if len(clean) <= max_chars:
            return clean
        sentences = re.split(r"(?<=[.!?])\s+", clean)
        selected: list[str] = []
        size = 0
        for sentence in sentences:
            if not sentence:
                continue
            addition = len(sentence) + (1 if selected else 0)
            if size + addition > max_chars:
                break
            selected.append(sentence)
            size += addition
        result = " ".join(selected).strip()
        return result if result else clean[:max_chars].rstrip() + "…"

    @staticmethod
    async def _validate_public_url(url: str) -> None:
        """Reject non-HTTP URLs and private/internal destinations to prevent SSRF."""
        parsed = urlparse(url.strip())
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError(f"Unsupported URL: {url!r}")
        if parsed.username or parsed.password:
            raise ValueError("URLs with embedded credentials are not allowed")
        host = parsed.hostname
        if not host:
            raise ValueError(f"URL host missing: {url!r}")
        try:
            ip_values = [ipaddress.ip_address(host)]
        except ValueError:
            infos = await asyncio.to_thread(socket.getaddrinfo, host, None, type=socket.SOCK_STREAM)
            ip_values = [ipaddress.ip_address(info[4][0]) for info in infos]
        if any(
            not ip.is_global
            or ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            for ip in ip_values
        ):
            raise ValueError("Private or non-public network destination blocked")

    @staticmethod
    def _clean_text(text: str) -> str:
        """Collapse repeated whitespace and remove obvious navigation noise."""
        lines = []
        seen: set[str] = set()
        for raw_line in text.splitlines():
            line = re.sub(r"\s+", " ", raw_line).strip()
            if not line or line in seen:
                continue
            seen.add(line)
            lines.append(line)
        return "\n".join(lines)

    @staticmethod
    def _parse_search_results(html: str) -> list[SearchResult]:
        """Parse DuckDuckGo result blocks using the standard library parser."""
        parser = _SearchParser()
        parser.feed(html)
        parser.close()
        return parser.results
