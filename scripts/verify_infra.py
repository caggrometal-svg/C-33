"""Verify the active C-33 cloud topology: Railway primary, Deplexo backup and external peer."""

from __future__ import annotations

import asyncio
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import httpx


ROOT = Path(__file__).resolve().parents[1]
ENDPOINTS_FILE = ROOT / "infra" / "c33-endpoints.json"


@dataclass(slots=True)
class ServiceCheck:
    name: str
    base_url: str
    health_ok: bool = False
    ready_ok: bool = False
    ai_ready_ok: bool = False
    status_ok: bool = False
    detail: str = ""


def _base_url(value: str) -> str:
    value = value.strip().rstrip("/") + "/"
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"invalid service URL: {value}")
    return value


def urljoin(base_url: str, path: str) -> str:
    return base_url.rstrip("/") + "/" + path.lstrip("/")


async def _check_service(
    client: httpx.AsyncClient,
    name: str,
    base_url: str,
) -> ServiceCheck:
    check = ServiceCheck(name=name, base_url=base_url)
    try:
        health = await client.get(urljoin(base_url, "health"))
        check.health_ok = health.status_code == 200
        if not check.health_ok:
            check.detail = f"health HTTP {health.status_code}: {health.text[:300]}"
            return check

        ready = await client.get(urljoin(base_url, "ready"))
        check.ready_ok = ready.status_code == 200
        if not check.ready_ok:
            check.detail = f"ready HTTP {ready.status_code}: {ready.text[:300]}"
            return check

        ai_ready = await client.get(urljoin(base_url, "v1/ai-ready"))
        check.ai_ready_ok = ai_ready.status_code == 200
        if not check.ai_ready_ok:
            check.detail = f"ai-ready HTTP {ai_ready.status_code}: {ai_ready.text[:300]}"
            return check

        status = await client.get(urljoin(base_url, "status"))
        check.status_ok = status.status_code == 200
        if not check.status_ok:
            check.detail = f"status HTTP {status.status_code}: {status.text[:300]}"
    except (httpx.HTTPError, ValueError) as exc:
        check.detail = str(exc)
    return check


def _load_endpoints() -> dict[str, str]:
    data = json.loads(ENDPOINTS_FILE.read_text(encoding="utf-8"))
    required = ("production", "runtime_backup", "peer")
    if any(not str(data.get(key, "")).strip() for key in required):
        raise ValueError("C-33 endpoint manifest is incomplete")
    return {key: _base_url(str(data[key])) for key in required}


def _validate_topology(endpoints: dict[str, str]) -> None:
    production_host = urlparse(endpoints["production"]).hostname or ""
    backup_host = urlparse(endpoints["runtime_backup"]).hostname or ""
    peer_host = urlparse(endpoints["peer"]).hostname or ""

    if not production_host.endswith(".up.railway.app"):
        raise ValueError("production endpoint is not Railway")
    if "deplexo.com" not in backup_host:
        raise ValueError("runtime_backup endpoint is not Deplexo")
    if len({production_host, backup_host, peer_host}) != 3:
        raise ValueError("C-33 topology endpoints must be distinct")


async def main() -> int:
    try:
        endpoints = _load_endpoints()
        _validate_topology(endpoints)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"C-33 topology: FAIL — {exc}", file=sys.stderr)
        return 2

    failures = 0
    timeout = httpx.Timeout(15.0, connect=6.0)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        for name, key in (("Railway primary", "production"), ("Deplexo backup", "runtime_backup")):
            result = await _check_service(client, name, endpoints[key])
            print(
                f"{result.name}: "
                f"health={'PASS' if result.health_ok else 'FAIL'} "
                f"ready={'PASS' if result.ready_ok else 'FAIL'} "
                f"ai_ready={'PASS' if result.ai_ready_ok else 'FAIL'} "
                f"status={'PASS' if result.status_ok else 'FAIL'}"
            )
            if result.detail:
                print(f"  {result.detail}")
            if not all((result.health_ok, result.ready_ok, result.ai_ready_ok, result.status_ok)):
                failures += 1

    print("C-33 topology: " + ("PASS" if failures == 0 else "FAIL"))
    print(f"Railway primary: {endpoints['production'].rstrip('/')}")
    print(f"Deplexo backup: {endpoints['runtime_backup'].rstrip('/')}")
    print(f"External peer: {endpoints['peer'].rstrip('/')}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
