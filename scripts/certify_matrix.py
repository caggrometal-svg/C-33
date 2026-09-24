"""Strict C-33 production certification: both backends, real AI probe, exact deployment SHA and provider diversity."""

from __future__ import annotations

import argparse
import asyncio
import sys
import uuid
from urllib.parse import urljoin

import httpx

EXPECTED_PROVIDER_STATUSES = {"AI_READY", "DEGRADED"}

async def get_json(client: httpx.AsyncClient, url: str) -> tuple[int, dict]:
    response = await client.get(url, headers={"Cache-Control": "no-cache"})
    try:
        data = response.json()
    except ValueError:
        data = {"raw": response.text[:500]}
    return response.status_code, data

async def certify_service(
    client: httpx.AsyncClient,
    name: str,
    base: str,
    expected_sha: str,
    *,
    provider_diversity_only: bool = False,
) -> list[str]:
    errors: list[str] = []
    base = base.rstrip("/") + "/"

    code, health = await get_json(client, urljoin(base, "health"))
    if code != 200 or health.get("status") != "alive":
        errors.append(f"{name}: /health not alive: HTTP {code} {health}")
        return errors

    sha = health.get("deployment_sha")
    if sha != expected_sha:
        errors.append(f"{name}: deployment SHA mismatch: expected {expected_sha}, got {sha}")

    code, ready = await get_json(client, urljoin(base, "ready"))
    if code != 200 or ready.get("status") != "ready":
        errors.append(f"{name}: /ready failed: HTTP {code} {ready}")
        return errors

    code, diag = await get_json(client, urljoin(base, "status"))
    if code != 200:
        errors.append(f"{name}: /status failed: HTTP {code} {diag}")
        return errors

    domains = diag.get("provider_failure_domains") or []
    if int(diag.get("provider_count") or 0) < 2:
        errors.append(f"{name}: fewer than 2 configured AI providers")
    if len(set(domains)) < 2:
        errors.append(f"{name}: fewer than 2 AI provider failure domains")

    if provider_diversity_only:
        return errors

    code, ai = await get_json(client, urljoin(base, "v1/ai-ready"))
    if code != 200 or ai.get("status") != "ai_ready":
        errors.append(f"{name}: /v1/ai-ready failed: HTTP {code} {ai}")
        return errors

    payload = {
        "message": "Return exactly C33_PRODUCTION_CERT_OK",
        "user_id": "github-certifier",
        "conversation_id": "cert-" + uuid.uuid4().hex,
        "request_id": uuid.uuid4().hex,
        "stream": False,
        "personality": "base",
        "voice_tone": "neutral",
    }
    response = await client.post(
        urljoin(base, "v1/chat"),
        headers={
            "Content-Type": "application/json",
            "X-C33-Deadline-Epoch-Ms": str(int(__import__("time").time() * 1000) + 28000),
        },
        json=payload,
    )
    try:
        chat = response.json()
    except ValueError:
        chat = {"raw": response.text[:500]}
    if response.status_code != 200:
        errors.append(f"{name}: /v1/chat failed: HTTP {response.status_code} {chat}")
    elif not str(chat.get("synthesis", "")).strip():
        errors.append(f"{name}: empty synthesis")
    meta = chat.get("_meta") or {}
    if meta.get("used_local_fallback"):
        errors.append(f"{name}: production certification received local fallback: {meta}")
    if meta.get("system_status") not in EXPECTED_PROVIDER_STATUSES:
        errors.append(f"{name}: unexpected system_status: {meta}")
    if not meta.get("provider_used") or meta.get("provider_used") == "local":
        errors.append(f"{name}: no real provider used: {meta}")
    return errors

async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--render-url", required=True)
    parser.add_argument("--railway-url", required=True)
    parser.add_argument("--expected-sha", required=True)
    parser.add_argument("--provider-diversity-only", action="store_true")
    args = parser.parse_args()

    timeout = httpx.Timeout(30.0, connect=4.0, read=30.0, write=4.0, pool=2.0)
    errors: list[str] = []
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        for name, url in (("Render", args.render_url), ("Railway", args.railway_url)):
            try:
                errors.extend(await certify_service(
                    client, name, url, args.expected_sha,
                    provider_diversity_only=args.provider_diversity_only,
                ))
            except httpx.HTTPError as exc:
                errors.append(f"{name}: network verification failure: {exc}")

        if not args.provider_diversity_only:
            # Require different provider failure domains between the two deployments.
            try:
                _, render_status = await get_json(client, args.render_url.rstrip("/") + "/status")
                _, railway_status = await get_json(client, args.railway_url.rstrip("/") + "/status")
                rdomains = set(render_status.get("provider_failure_domains") or [])
                wdomains = set(railway_status.get("provider_failure_domains") or [])
                if not (rdomains - wdomains) and not (wdomains - rdomains):
                    errors.append("Render and Railway expose identical provider failure domains; redundancy is not independent.")
            except httpx.HTTPError as exc:
                errors.append(f"provider-domain comparison failed: {exc}")

    if errors:
        for error in errors:
            print("FAIL:", error, file=sys.stderr)
        return 1
    print("C33_PRODUCTION_CERTIFICATION_PASS")
    return 0

if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
