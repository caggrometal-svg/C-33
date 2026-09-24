"""Live Render/Railway and PostgreSQL infrastructure verifier."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

import asyncpg
import httpx


@dataclass(slots=True)
class ServiceCheck:
    name: str
    base_url: str
    health_ok: bool = False
    status_ok: bool = False
    chat_ok: bool = False
    detail: str = ""


def _base_url(value: str) -> str:
    value = value.strip().rstrip("/") + "/"
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"Invalid service URL: {value}")
    return value


async def _check_service(client: httpx.AsyncClient, name: str, base_url: str) -> ServiceCheck:
    check = ServiceCheck(name=name, base_url=base_url)
    try:
        health = await client.get(urljoin(base_url, "health"))
        check.health_ok = health.status_code == 200
        if not check.health_ok:
            check.detail = f"health HTTP {health.status_code}: {health.text[:300]}"
            return check

        status = await client.get(urljoin(base_url, "status"))
        check.status_ok = status.status_code == 200
        if not check.status_ok:
            check.detail = f"status HTTP {status.status_code}: {status.text[:300]}"
            return check

        secret_keys = [
            item.strip()
            for item in os.getenv("SECRET_KEYS", "").split(",")
            if item.strip()
        ]
        headers = {"X-C33-Secret": secret_keys[0]} if secret_keys else {}

        payload = {
            "message": "infra verification",
            "user_id": "infra-verifier",
            "stream": False,
        }
        response = await client.post(
            urljoin(base_url, "v1/chat"),
            headers=headers,
            json=payload,
        )
        check.chat_ok = response.status_code == 200
        if not check.chat_ok:
            check.detail = f"chat HTTP {response.status_code}: {response.text[:300]}"
        else:
            data = response.json()
            if data.get("service") != "C-33" or not data.get("synthesis"):
                check.chat_ok = False
                check.detail = "chat returned an invalid C-33 response"
    except (httpx.HTTPError, ValueError) as exc:
        check.detail = str(exc)
    return check


async def _check_database(database_url: str) -> tuple[bool, str]:
    try:
        connection = await asyncpg.connect(
            database_url,
            timeout=10,
            command_timeout=10,
        )
        try:
            result = await connection.fetchval("SELECT 1")
            if result != 1:
                return False, f"unexpected SELECT 1 result: {result!r}"
        finally:
            await connection.close()
        return True, "SELECT 1 OK"
    except (OSError, asyncpg.PostgresError, ValueError) as exc:
        return False, str(exc)


async def main() -> int:
    parser = argparse.ArgumentParser(description="Verify C-33 Render/Railway infrastructure.")
    parser.add_argument("--render-url", default=os.getenv("RENDER_URL", ""))
    parser.add_argument("--railway-url", default=os.getenv("RAILWAY_URL", ""))
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL", ""))
    args = parser.parse_args()

    service_urls = [
        ("Render", args.render_url),
        ("Railway", args.railway_url),
    ]
    service_urls = [
        (name, _base_url(url))
        for name, url in service_urls
        if url.strip()
    ]

    if not service_urls and not args.database_url.strip():
        print("ERROR: provide RENDER_URL, RAILWAY_URL and/or DATABASE_URL", file=sys.stderr)
        return 2

    failures = 0
    timeout = httpx.Timeout(30.0, connect=10.0)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        for name, url in service_urls:
            result = await _check_service(client, name, url)
            print(
                f"{result.name}: "
                f"health={'PASS' if result.health_ok else 'FAIL'} "
                f"status={'PASS' if result.status_ok else 'FAIL'} "
                f"chat={'PASS' if result.chat_ok else 'FAIL'}"
            )
            if result.detail:
                print(f"  {result.detail}")
            if not (result.health_ok and result.status_ok and result.chat_ok):
                failures += 1

    if args.database_url.strip():
        ok, detail = await _check_database(args.database_url.strip())
        print(f"PostgreSQL: {'PASS' if ok else 'FAIL'}")
        print(f"  {detail}")
        if not ok:
            failures += 1

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
