"""Real provider cascade with persistent circuit breakers and bounded deadlines."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import time
from dataclasses import dataclass
from typing import Any, AsyncIterator
from urllib.parse import urlparse

import httpx

from .state import PostgresState

logger = logging.getLogger("nexo.c33.provider")

@dataclass(frozen=True, slots=True)
class ProviderSpec:
    provider_id: str
    base_url: str
    model: str
    api_key_env: str | None
    failure_domain: str
    timeout_ms: int

@dataclass(frozen=True, slots=True)
class ProviderMeta:
    provider_used: str
    model: str
    failover_triggered: bool
    attempts: int
    latency_ms: int
    final_reason: str
    system_status: str

@dataclass(frozen=True, slots=True)
class GenerationResult:
    text: str
    meta: ProviderMeta

class GenerationFailure(RuntimeError):
    def __init__(self, reason: str, *, http_status: int, attempts: list[dict[str, Any]], retry_after_ms: int = 0) -> None:
        super().__init__(reason)
        self.reason = reason
        self.http_status = http_status
        self.attempts = attempts
        self.retry_after_ms = retry_after_ms

class DeadlineBudget:
    def __init__(self, total_ms: int, client_deadline_epoch_ms: int | None = None) -> None:
        total_ms = max(1000, total_ms)
        local_deadline = time.monotonic() + total_ms / 1000
        if client_deadline_epoch_ms:
            remaining = (client_deadline_epoch_ms - time.time_ns() / 1_000_000) / 1000
            local_deadline = min(local_deadline, time.monotonic() + max(0.05, remaining))
        self.deadline = local_deadline

    @property
    def remaining_ms(self) -> int:
        return max(0, int((self.deadline - time.monotonic()) * 1000))

    def provider_timeout_ms(self, configured_ms: int, reserve_ms: int = 250) -> int:
        return max(250, min(configured_ms, self.remaining_ms - reserve_ms))

class ProviderCascade:
    """One bounded request across independent providers; never retries beyond the global deadline."""

    def __init__(self, state: PostgresState, specs: list[ProviderSpec], order: list[str], transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.state = state
        by_id = {spec.provider_id: spec for spec in specs}
        if order:
            # Explicit order is both priority and allowlist.
            self.providers = [by_id[name] for name in order if name in by_id]
        else:
            self.providers = list(specs)
        self.require_redundancy = os.getenv("REQUIRE_PROVIDER_REDUNDANCY", "true").strip().lower() == "true"
        self.transport = transport

    @classmethod
    def from_environment(cls, state: PostgresState) -> "ProviderCascade":
        raw = os.getenv("AI_PROVIDERS_JSON", "").strip()
        specs: list[ProviderSpec] = []
        if raw:
            data = json.loads(raw)
            if not isinstance(data, list):
                raise ValueError("AI_PROVIDERS_JSON must be a JSON array")
            for item in data:
                if not isinstance(item, dict):
                    raise ValueError("AI_PROVIDERS_JSON entries must be objects")
                base = str(item.get("base_url", "")).strip().rstrip("/")
                pid = str(item.get("id", "")).strip()
                model = str(item.get("model", "")).strip()
                if not pid or not base or not model:
                    raise ValueError("Each AI provider requires id, base_url and model")
                parsed = urlparse(base)
                if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                    raise ValueError(f"Invalid provider URL for {pid}")
                if pid == "kilo-m3-free":
                    model = "kilo-auto/free"
                    pid = "kilo"
                specs.append(ProviderSpec(pid, base, model, str(item.get("api_key_env", "")).strip() or None, str(item.get("failure_domain", parsed.netloc.lower())).strip(), max(500, int(item.get("timeout_ms", 7000)))))
        else:
            configured_base = os.getenv("MODEL_BASE_URL", "").strip().rstrip("/")
            configured_model = os.getenv("MODEL_NAME", "").strip()
            configured_key_env = "OPENAI_API_KEY" if os.getenv("OPENAI_API_KEY", "").strip() else ("MODEL_API_KEY" if os.getenv("MODEL_API_KEY", "").strip() else None)

            provider_a_url = os.getenv("AI_PROVIDER_A_BASE_URL", "").strip().rstrip("/")
            provider_b_url = os.getenv("AI_PROVIDER_B_BASE_URL", "").strip().rstrip("/")

            if provider_a_url:
                a_base = provider_a_url
                a_host = urlparse(a_base).netloc.lower()
                a_id = os.getenv("AI_PROVIDER_A_ID", "").strip() or "provider_a"
                a_model = os.getenv("AI_PROVIDER_A_MODEL", "").strip() or ("auto" if "vireonix.ai" in a_host else "nvidia/nemotron-3.5-lightning")
                a_key = os.getenv("AI_PROVIDER_A_KEY_ENV", "").strip() or configured_key_env
            elif configured_base:
                a_base = configured_base
                a_host = urlparse(a_base).netloc.lower()
                a_id = os.getenv("AI_PROVIDER_A_ID", "").strip() or ("vireonix" if "vireonix.ai" in a_host else ("blockrun" if "blockrun.ai" in a_host else a_host or "provider_a"))
                a_model = configured_model or ("auto" if "vireonix.ai" in a_host else "nvidia/nemotron-3.5-lightning")
                a_key = configured_key_env
            else:
                a_base = "https://vireonix.ai/v1"
                a_host = "vireonix.ai"
                a_id = "vireonix"
                a_model = "auto"
                a_key = None

            specs = [ProviderSpec(a_id, a_base, a_model, a_key, a_host, 6_000)]

            if provider_b_url:
                b_base = provider_b_url
                b_host = urlparse(b_base).netloc.lower()
                b_model = os.getenv("AI_PROVIDER_B_MODEL", "").strip() or ("nvidia/nemotron-3.5-lightning" if "blockrun.ai" in b_host else "auto")
            elif "vireonix.ai" in a_host:
                b_base, b_host, b_model = "https://blockrun.ai/api/v1", "blockrun.ai", "nvidia/nemotron-3.5-lightning"
            elif "blockrun.ai" in a_host:
                b_base, b_host, b_model = "https://vireonix.ai/v1", "vireonix.ai", "auto"
            else:
                b_base, b_host, b_model = "https://blockrun.ai/api/v1", "blockrun.ai", "nvidia/nemotron-3.5-lightning"

            specs.append(
                ProviderSpec(
                    os.getenv("AI_PROVIDER_B_ID", "").strip() or ("blockrun" if "blockrun.ai" in b_host else ("vireonix" if "vireonix.ai" in b_host else "provider_b")),
                    b_base,
                    b_model,
                    os.getenv("AI_PROVIDER_B_KEY_ENV", "").strip() or None,
                    b_host,
                    4_000,
                )
            )
        disabled = {x.strip() for x in os.getenv("AI_DISABLED_PROVIDERS", "").split(",") if x.strip()}
        if disabled:
            specs = [spec for spec in specs if spec.provider_id not in disabled]
        order = [x.strip() for x in os.getenv("AI_PROVIDER_ORDER", "provider_a,provider_b").split(",") if x.strip()]
        return cls(state, specs, order)

    @property
    def configured_provider_count(self) -> int:
        return len(self.providers)

    @property
    def failure_domains(self) -> list[str]:
        return list(dict.fromkeys(p.failure_domain for p in self.providers))

    def assert_ready_configuration(self) -> None:
        if not self.providers:
            raise GenerationFailure("no_providers_configured", http_status=503, attempts=[])
        if self.require_redundancy and len(self.providers) < 2:
            raise GenerationFailure("provider_redundancy_not_configured", http_status=503, attempts=[])
        if self.require_redundancy and len(self.failure_domains) < 2:
            raise GenerationFailure("provider_failure_domains_not_diverse", http_status=503, attempts=[])

    async def complete(self, messages: list[dict[str, str]], budget: DeadlineBudget, *, probe: bool = False) -> GenerationResult:
        self.assert_ready_configuration()
        if probe:
            return await self._probe_parallel(messages, budget)
        attempts: list[dict[str, Any]] = []
        if budget.remaining_ms < 1000:
            raise GenerationFailure("deadline_exhausted_before_provider", http_status=504, attempts=[])
        for index, spec in enumerate(self.providers):
            if budget.remaining_ms < 500:
                break
            decision = await self.state.circuit_before_call(spec.provider_id)
            if not decision.allowed:
                attempts.append({"provider":spec.provider_id,"reason":"circuit_open","cooldown_ms":decision.cooldown_ms})
                continue
            started = time.monotonic()
            timeout_ms = budget.provider_timeout_ms(spec.timeout_ms)
            logger.info("[NEXO_DEBUG_PROVIDER] complete_attempt provider=%s model=%s timeout_ms=%s remaining_ms=%s probe=%s", spec.provider_id, spec.model, timeout_ms, budget.remaining_ms, probe)
            try:
                text = await self._complete_one(spec, messages, timeout_ms, probe=probe)
                latency = int((time.monotonic()-started)*1000)
                await self.state.circuit_success(spec.provider_id, model=spec.model, latency_ms=latency)
                logger.info("[NEXO_DEBUG_PROVIDER] complete_success provider=%s latency_ms=%s", spec.provider_id, latency)
                attempts.append({"provider":spec.provider_id,"status":200,"latency_ms":latency})
                return GenerationResult(text=text, meta=ProviderMeta(spec.provider_id,spec.model,index>0,len(attempts),latency,"success_after_failover" if index>0 else "success","AI_READY" if index==0 else "DEGRADED"))
            except GenerationFailure as exc:
                latency = int((time.monotonic()-started)*1000)
                await self.state.circuit_failure(spec.provider_id, reason=exc.reason, status=exc.http_status, model=spec.model, latency_ms=latency, cooldown_ms=self._cooldown_ms(exc))
                logger.warning("[NEXO_DEBUG_PROVIDER] complete_failure provider=%s reason=%s http_status=%s latency_ms=%s", spec.provider_id, exc.reason, exc.http_status, latency)
                attempts.append({"provider":spec.provider_id,"status":exc.http_status,"reason":exc.reason,"latency_ms":latency,"retry_after_ms":exc.retry_after_ms})
                continue
        final_reason = self._final_reason(attempts)
        if final_reason == "rate_limited":
            raise GenerationFailure(final_reason,http_status=429,attempts=attempts,retry_after_ms=self._max_retry_after(attempts))
        if final_reason in {"timeout","deadline_exhausted","dns_failure","tls_failure","connection_reset"}:
            raise GenerationFailure(final_reason,http_status=504,attempts=attempts)
        raise GenerationFailure(final_reason,http_status=502,attempts=attempts)

    async def _probe_parallel(self, messages: list[dict[str, str]], budget: DeadlineBudget) -> GenerationResult:
        """Probe providers in configured order, bounded by the readiness deadline."""
        attempts: list[dict[str, Any]] = []
        for index, spec in enumerate(self.providers):
            if budget.remaining_ms < 1000:
                break
            decision = await self.state.circuit_before_call(spec.provider_id)
            if not decision.allowed:
                attempts.append({
                    "provider": spec.provider_id,
                    "reason": "circuit_open",
                    "cooldown_ms": decision.cooldown_ms,
                })
                continue
            started = time.monotonic()
            timeout_ms = budget.provider_timeout_ms(spec.timeout_ms, reserve_ms=250)
            if timeout_ms < 750:
                break
            try:
                text = await self._complete_one(spec, messages, timeout_ms, probe=True)
                latency = int((time.monotonic() - started) * 1000)
                await self.state.circuit_success(
                    spec.provider_id,
                    model=spec.model,
                    latency_ms=latency,
                )
                return GenerationResult(
                    text=text,
                    meta=ProviderMeta(
                        spec.provider_id,
                        spec.model,
                        index > 0,
                        len(attempts) + 1,
                        latency,
                        "success_after_failover" if index > 0 else "success",
                        "AI_READY" if index == 0 else "DEGRADED",
                    ),
                )
            except GenerationFailure as exc:
                latency = int((time.monotonic() - started) * 1000)
                await self.state.circuit_failure(
                    spec.provider_id,
                    reason=exc.reason,
                    status=exc.http_status,
                    model=spec.model,
                    latency_ms=latency,
                    cooldown_ms=self._cooldown_ms(exc),
                )
                attempts.append({
                    "provider": spec.provider_id,
                    "status": exc.http_status,
                    "reason": exc.reason,
                    "latency_ms": latency,
                    "retry_after_ms": exc.retry_after_ms,
                })

        final_reason = self._final_reason(attempts)
        if final_reason == "rate_limited":
            raise GenerationFailure(
                final_reason,
                http_status=429,
                attempts=attempts,
                retry_after_ms=self._max_retry_after(attempts),
            )
        if final_reason in {"timeout", "deadline_exhausted", "dns_failure", "tls_failure", "connection_reset"}:
            raise GenerationFailure(final_reason, http_status=504, attempts=attempts)
        raise GenerationFailure(final_reason, http_status=502, attempts=attempts)

    async def _complete_one(self, spec: ProviderSpec, messages: list[dict[str, str]], timeout_ms: int, *, probe: bool) -> str:
        headers = {"Content-Type":"application/json"}
        api_key = os.getenv(spec.api_key_env, "").strip() if spec.api_key_env else ""
        if api_key: headers["Authorization"] = f"Bearer {api_key}"
        probe_model = os.getenv("AI_PROBE_MODEL", "").strip() if probe else ""
        effective_model = probe_model if probe_model else spec.model
        payload: dict[str, Any] = {"model":effective_model,"messages":messages,"stream":False}
        if probe: payload.update({"max_tokens":1,"temperature":0})
        if probe:
            logger.info("[NEXO_DEBUG_PROVIDER] probe_model provider=%s model=%s configured_probe_model=%s", spec.provider_id, effective_model, bool(probe_model))
        timeout = httpx.Timeout(timeout_ms/1000, connect=min(2.0,timeout_ms/1000), read=timeout_ms/1000, write=min(2.0,timeout_ms/1000), pool=min(1.0,timeout_ms/1000))
        try:
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, transport=self.transport) as client:
                response = await client.post(f"{spec.base_url}/chat/completions",headers=headers,json=payload)
        except asyncio.CancelledError:
            raise
        except httpx.ConnectTimeout as exc:
            raise GenerationFailure("timeout",http_status=504,attempts=[]) from exc
        except httpx.ReadTimeout as exc:
            raise GenerationFailure("timeout",http_status=504,attempts=[]) from exc
        except httpx.ConnectError as exc:
            cause = exc.__cause__
            context = exc.__context__
            detail = " ".join(
                part
                for part in (
                    str(exc),
                    repr(exc),
                    str(exc.args),
                    str(cause) if cause else "",
                    repr(cause) if cause else "",
                    str(context) if context else "",
                    repr(context) if context else "",
                )
                if part
            ).lower()
            reason = (
                "tls_failure"
                if "ssl" in detail or "tls" in detail or "certificate" in detail
                else (
                    "dns_failure"
                    if "dns" in detail
                    or "name resolution" in detail
                    or "name or service not known" in detail
                    or "temporary failure in name resolution" in detail
                    or "nodename nor servname" in detail
                    else "connection_reset"
                )
            )
            raise GenerationFailure(reason,http_status=502,attempts=[]) from exc
        except httpx.HTTPError as exc:
            raise GenerationFailure("connection_error",http_status=502,attempts=[]) from exc
        status=response.status_code
        if status==429:
            raw=response.headers.get("retry-after","")
            try: retry_after_ms=max(0,int(float(raw)*1000))
            except ValueError: retry_after_ms=0
            raise GenerationFailure("rate_limited",http_status=429,attempts=[],retry_after_ms=retry_after_ms)
        if status in {401,403}: raise GenerationFailure("auth_error",http_status=status,attempts=[])
        if status==400:
            detail = ""
            try:
                body = response.json()
                error = body.get("error", {}) if isinstance(body, dict) else {}
                detail = str(error.get("message") or body.get("message") or "")[:180]
            except ValueError:
                detail = response.text[:180].strip()
            reason = "bad_request" if not detail else "bad_request:" + detail
            raise GenerationFailure(reason,http_status=400,attempts=[])
        if status==408: raise GenerationFailure("timeout",http_status=408,attempts=[])
        if 500<=status<=599: raise GenerationFailure("provider_5xx",http_status=status,attempts=[])
        if not 200<=status<=299: raise GenerationFailure(f"provider_http_{status}",http_status=status,attempts=[])
        try:
            data=response.json(); content=data["choices"][0]["message"]["content"]
        except (ValueError,KeyError,IndexError,TypeError) as exc:
            raise GenerationFailure("invalid_provider_response",http_status=502,attempts=[]) from exc
        if not isinstance(content,str) or not content.strip(): raise GenerationFailure("empty_provider_response",http_status=502,attempts=[])
        return content.strip()

    async def stream(self, messages: list[dict[str,str]], budget: DeadlineBudget) -> AsyncIterator[tuple[str,ProviderMeta]]:
        self.assert_ready_configuration()
        attempts: list[dict[str,Any]]=[]
        for index,spec in enumerate(self.providers):
            if budget.remaining_ms<1000: break
            decision=await self.state.circuit_before_call(spec.provider_id)
            if not decision.allowed:
                attempts.append({"provider":spec.provider_id,"reason":"circuit_open","cooldown_ms":decision.cooldown_ms}); continue
            timeout_ms=budget.provider_timeout_ms(spec.timeout_ms); started=time.monotonic(); got_token=False
            logger.info("[NEXO_DEBUG_PROVIDER] stream_attempt provider=%s model=%s timeout_ms=%s remaining_ms=%s", spec.provider_id, spec.model, timeout_ms, budget.remaining_ms)
            headers={"Content-Type":"application/json","Accept":"text/event-stream"}
            api_key=os.getenv(spec.api_key_env,"").strip() if spec.api_key_env else ""
            if api_key: headers["Authorization"]=f"Bearer {api_key}"
            payload={"model":spec.model,"messages":messages,"stream":True}
            try:
                timeout=httpx.Timeout(timeout_ms/1000,connect=min(2.0,timeout_ms/1000),read=timeout_ms/1000,write=2.0,pool=1.0)
                async with httpx.AsyncClient(timeout=timeout,follow_redirects=True,transport=self.transport) as client:
                    async with client.stream("POST",f"{spec.base_url}/chat/completions",headers=headers,json=payload) as response:
                        logger.info("[NEXO_DEBUG_PROVIDER] stream_http provider=%s status=%s", spec.provider_id, response.status_code)
                        if response.status_code!=200:
                            if response.status_code==429:
                                raw=response.headers.get("retry-after","0")
                                try: retry_after_ms=int(float(raw)*1000)
                                except ValueError: retry_after_ms=0
                                raise GenerationFailure("rate_limited",http_status=429,attempts=[],retry_after_ms=retry_after_ms)
                            if response.status_code in {401,403}: raise GenerationFailure("auth_error",http_status=response.status_code,attempts=[])
                            if response.status_code==408: raise GenerationFailure("timeout",http_status=408,attempts=[])
                            if response.status_code>=500: raise GenerationFailure("provider_5xx",http_status=response.status_code,attempts=[])
                            raise GenerationFailure(f"provider_http_{response.status_code}",http_status=response.status_code,attempts=[])
                        async for line in response.aiter_lines():
                            if not line.startswith("data:"): continue
                            item=line[5:].strip()
                            if item=="[DONE]":
                                if not got_token:
                                    raise GenerationFailure("empty_stream",http_status=502,attempts=[])
                                latency=int((time.monotonic()-started)*1000)
                                logger.info("[NEXO_DEBUG_PROVIDER] stream_success provider=%s latency_ms=%s tokens=%s", spec.provider_id, latency, got_token)
                                await self.state.circuit_success(spec.provider_id,model=spec.model,latency_ms=latency)
                                return
                            try:
                                data=json.loads(item); piece=data["choices"][0]["delta"].get("content","")
                            except (ValueError,KeyError,IndexError,TypeError): continue
                            if piece:
                                got_token=True
                                yield piece,ProviderMeta(spec.provider_id,spec.model,index>0,len(attempts)+1,int((time.monotonic()-started)*1000),"streaming","AI_READY" if index==0 else "DEGRADED")
                        if not got_token: raise GenerationFailure("empty_stream",http_status=502,attempts=[])
            except asyncio.CancelledError: raise
            except GenerationFailure as exc:
                latency=int((time.monotonic()-started)*1000)
                await self.state.circuit_failure(spec.provider_id,reason=exc.reason,status=exc.http_status,model=spec.model,latency_ms=latency,cooldown_ms=self._cooldown_ms(exc))
                logger.warning("[NEXO_DEBUG_PROVIDER] stream_generation_failure provider=%s reason=%s http_status=%s latency_ms=%s got_token=%s", spec.provider_id, exc.reason, exc.http_status, latency, got_token)
                attempts.append({"provider":spec.provider_id,"status":exc.http_status,"reason":exc.reason,"latency_ms":latency})
                if got_token: raise
            except (httpx.TimeoutException,httpx.ConnectError,httpx.HTTPError) as exc:
                latency=int((time.monotonic()-started)*1000)
                if isinstance(exc, httpx.TimeoutException):
                    reason = "timeout"
                elif isinstance(exc, httpx.ConnectError):
                    cause = exc.__cause__
                    context = exc.__context__
                    detail = " ".join(
                        part for part in (
                            str(exc),
                            repr(exc),
                            str(exc.args),
                            str(cause) if cause else "",
                            repr(cause) if cause else "",
                            str(context) if context else "",
                            repr(context) if context else "",
                        ) if part
                    ).lower()
                    reason = (
                        "tls_failure"
                        if "ssl" in detail or "tls" in detail or "certificate" in detail
                        else (
                            "dns_failure"
                            if "dns" in detail
                            or "name resolution" in detail
                            or "name or service not known" in detail
                            or "temporary failure in name resolution" in detail
                            or "nodename nor servname" in detail
                            else "connection_reset"
                        )
                    )
                else:
                    reason = "connection_error"
                status = 504 if reason == "timeout" else 502
                await self.state.circuit_failure(
                    spec.provider_id,
                    reason=reason,
                    status=status,
                    model=spec.model,
                    latency_ms=latency,
                    cooldown_ms=30_000,
                )
                logger.warning("[NEXO_DEBUG_PROVIDER] stream_http_failure provider=%s reason=%s status=%s latency_ms=%s got_token=%s", spec.provider_id, reason, status, latency, got_token)
                if got_token:
                    raise GenerationFailure("stream_interrupted",http_status=502,attempts=attempts) from exc
                attempts.append({"provider":spec.provider_id,"status":status,"reason":reason})
        raise GenerationFailure(self._final_reason(attempts),http_status=504 if any(a.get("status")==504 for a in attempts) else 502,attempts=attempts)

    @staticmethod
    def _cooldown_ms(exc: GenerationFailure) -> int:
        if exc.http_status==429:
            base=max(15_000,exc.retry_after_ms or 15_000); return min(10*60_000,int(base*random.uniform(0.8,1.2)))
        if exc.http_status in {401,403}: return 30*60_000
        if exc.http_status==400: return 5*60_000
        return min(5*60_000,int(30_000*(1+random.random()*0.25)))

    @staticmethod
    def _max_retry_after(attempts:list[dict[str,Any]]) -> int:
        return max((int(a.get("retry_after_ms",0)) for a in attempts),default=0)

    @staticmethod
    def _final_reason(attempts:list[dict[str,Any]]) -> str:
        if not attempts: return "no_provider_available"
        reasons=[str(a.get("reason","unknown")) for a in attempts]
        if all(r=="rate_limited" for r in reasons): return "rate_limited"
        if any(r in {"timeout","deadline_exhausted_before_provider"} for r in reasons): return "timeout"
        if any(r=="dns_failure" for r in reasons): return "dns_failure"
        if any(r=="tls_failure" for r in reasons): return "tls_failure"
        if any(r=="connection_reset" for r in reasons): return "connection_reset"
        if any(r=="auth_error" for r in reasons): return "provider_auth_failure"
        return "providers_exhausted"
