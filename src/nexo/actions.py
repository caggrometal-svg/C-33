"""Explicitly authorized external action executor."""
from __future__ import annotations

import hashlib
import ipaddress
import os
import time
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx


class ActionPolicyError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ActionRequest:
    action: str
    url: str
    method: str = "POST"
    scope: tuple[str, ...] = ()
    authorized: bool = False
    headers: dict[str, str] | None = None
    body: object | None = None
    timeout_ms: int = 8000
    max_response_bytes: int = 100_000
    idempotency_key: str | None = None


@dataclass(frozen=True, slots=True)
class ActionResult:
    action: str
    ok: bool
    status_code: int | None
    body: str
    latency_ms: int
    response_sha256: str
    reason: str | None = None


class ExternalActionExecutor:
    """One bounded network action behind authorization and an exact host allowlist."""

    ALLOWED_METHODS = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE"})

    def __init__(self, allowed_hosts: tuple[str, ...] = (), transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.allowed_hosts = tuple(sorted({host.strip().lower() for host in allowed_hosts if host.strip()}))
        self.transport = transport

    @classmethod
    def from_environment(cls, transport: httpx.AsyncBaseTransport | None = None) -> "ExternalActionExecutor":
        raw = os.getenv("C33_ACTION_ALLOWLIST", "")
        return cls(tuple(part for part in raw.split(",") if part.strip()), transport=transport)

    def validate(self, request: ActionRequest) -> tuple[str, str]:
        action = request.action.strip()
        if not action:
            raise ActionPolicyError("action_required")
        if not request.authorized:
            raise ActionPolicyError("explicit_authorization_required")
        if request.scope and action not in request.scope:
            raise ActionPolicyError("action_outside_authorized_scope")
        method = request.method.strip().upper()
        if method not in self.ALLOWED_METHODS:
            raise ActionPolicyError("unsupported_action_method")
        if not self.allowed_hosts:
            raise ActionPolicyError("action_allowlist_not_configured")
        parsed = urlparse(request.url.strip())
        if parsed.scheme != "https" or not parsed.hostname:
            raise ActionPolicyError("action_requires_https_target")
        hostname = parsed.hostname.lower()
        try:
            literal = ipaddress.ip_address(hostname)
        except ValueError:
            literal = None
        if literal is not None and (literal.is_private or literal.is_loopback or literal.is_link_local or literal.is_reserved):
            raise ActionPolicyError("private_action_target_blocked")
        if hostname not in self.allowed_hosts:
            raise ActionPolicyError("action_target_not_allowlisted")
        if not 500 <= int(request.timeout_ms) <= 30000:
            raise ActionPolicyError("invalid_action_timeout")
        if not 1024 <= int(request.max_response_bytes) <= 2_000_000:
            raise ActionPolicyError("invalid_action_response_limit")
        return action, method

    async def execute(self, request: ActionRequest) -> ActionResult:
        action, method = self.validate(request)
        headers = {str(k): str(v) for k, v in (request.headers or {}).items()}
        headers.pop("Host", None)
        headers.pop("Content-Length", None)
        headers["Accept"] = "application/json, text/plain;q=0.9, */*;q=0.8"
        headers["X-C33-Action"] = action
        if request.idempotency_key:
            headers["Idempotency-Key"] = request.idempotency_key[:128]
        started = time.monotonic()
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(int(request.timeout_ms) / 1000, connect=min(2.0, int(request.timeout_ms) / 1000)),
                follow_redirects=False,
                transport=self.transport,
                trust_env=False,
            ) as client:
                response = await client.request(
                    method,
                    request.url,
                    headers=headers,
                    json=request.body if request.body is not None else None,
                )
                raw = (await response.aread())[: int(request.max_response_bytes)]
            return ActionResult(
                action=action,
                ok=200 <= response.status_code < 300,
                status_code=response.status_code,
                body=raw.decode("utf-8", errors="replace"),
                latency_ms=int((time.monotonic() - started) * 1000),
                response_sha256=hashlib.sha256(raw).hexdigest(),
                reason=None if 200 <= response.status_code < 300 else f"http_{response.status_code}",
            )
        except (httpx.HTTPError, OSError) as exc:
            return ActionResult(
                action=action,
                ok=False,
                status_code=None,
                body="",
                latency_ms=int((time.monotonic() - started) * 1000),
                response_sha256=hashlib.sha256(b"").hexdigest(),
                reason=type(exc).__name__,
            )
