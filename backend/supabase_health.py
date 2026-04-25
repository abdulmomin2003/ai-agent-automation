"""
Supabase and Postgres connectivity probes used by the health endpoint.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Optional

from config import settings

logger = logging.getLogger(__name__)


@dataclass
class ProbeResult:
    ok: bool
    detail: str
    data: Optional[dict[str, Any]] = None


def _masked_dsn(dsn: str) -> str:
    if not dsn:
        return ""

    try:
        prefix, rest = dsn.split("//", 1)
        if ":" not in rest or "@" not in rest:
            return dsn
        userinfo, hostpart = rest.split("@", 1)
        username = userinfo.split(":", 1)[0]
        return f"{prefix}//{username}:***@{hostpart}"
    except ValueError:
        return dsn


def check_supabase_http(timeout_seconds: int = 5) -> ProbeResult:
    url = settings.supabase_url
    api_key = settings.supabase_api_key

    if not url:
        return ProbeResult(False, "Supabase URL is not configured")

    if not api_key:
        return ProbeResult(False, "Supabase API key is not configured")

    endpoint = f"{url.rstrip('/')}/auth/v1/settings"
    request = urllib.request.Request(
        endpoint,
        headers={
            "apikey": api_key,
            "Authorization": f"Bearer {api_key}",
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return ProbeResult(True, "Supabase auth endpoint reachable", payload)
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        detail = f"HTTP {error.code} from Supabase auth endpoint"
        if body:
            detail = f"{detail}: {body[:200]}"
        return ProbeResult(False, detail)
    except Exception as error:
        return ProbeResult(False, str(error))


def check_postgres(timeout_seconds: int = 5) -> ProbeResult:
    candidates = settings.postgres_dsn_candidates

    if not candidates:
        return ProbeResult(False, "DATABASE_URL or Supabase DB password is not configured")

    try:
        import psycopg
    except Exception as error:
        psycopg = None
        psycopg_error = error
    else:
        psycopg_error = None

    attempts: list[dict[str, Any]] = []

    for dsn in candidates:
        if psycopg is not None:
            try:
                with psycopg.connect(dsn, connect_timeout=timeout_seconds) as connection:
                    with connection.cursor() as cursor:
                        cursor.execute(
                            "select current_database(), current_user, inet_server_addr()::text, inet_server_port();"
                        )
                        database, user, server_ip, server_port = cursor.fetchone()

                return ProbeResult(
                    True,
                    "Postgres connection succeeded",
                    {
                        "database": database,
                        "user": user,
                        "server_ip": server_ip,
                        "server_port": server_port,
                        "dsn": _masked_dsn(dsn),
                    },
                )
            except Exception as error:
                logger.warning("Postgres connectivity probe failed for %s: %s", _masked_dsn(dsn), error)
                attempts.append({"dsn": _masked_dsn(dsn), "error": str(error)})
                continue

        try:
            env = os.environ.copy()
            env["PGCONNECT_TIMEOUT"] = str(timeout_seconds)
            completed = subprocess.run(
                [
                    "psql",
                    dsn,
                    "-Atq",
                    "-c",
                    "select current_database(), current_user, inet_server_addr()::text, inet_server_port();",
                ],
                capture_output=True,
                text=True,
                env=env,
                check=False,
            )

            if completed.returncode == 0:
                raw_output = completed.stdout.strip()
                parts = raw_output.split("|") if raw_output else []
                database = parts[0] if len(parts) > 0 else ""
                user = parts[1] if len(parts) > 1 else ""
                server_ip = parts[2] if len(parts) > 2 else ""
                server_port = parts[3] if len(parts) > 3 else ""
                return ProbeResult(
                    True,
                    "Postgres connection succeeded",
                    {
                        "database": database,
                        "user": user,
                        "server_ip": server_ip,
                        "server_port": server_port,
                        "dsn": _masked_dsn(dsn),
                        "client": "psql",
                    },
                )

            error_output = (completed.stderr or completed.stdout or "").strip()
            attempts.append({"dsn": _masked_dsn(dsn), "error": error_output or f"psql exited {completed.returncode}"})
        except Exception as error:
            attempts.append({"dsn": _masked_dsn(dsn), "error": str(error)})

    if psycopg_error is not None and not attempts:
        return ProbeResult(False, f"psycopg is unavailable: {psycopg_error}")

    return ProbeResult(False, "No Supabase Postgres connection candidate succeeded", {"attempts": attempts})