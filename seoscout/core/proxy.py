"""Shared proxy health checks for CLI commands."""

from collections.abc import Sequence

import aiohttp

from .config import Config


PROXY_PROBE_URL = "https://api.ipify.org"


async def preflight_proxy_for_stages(stages: Sequence[str]) -> tuple[bool, str]:
    """Check one active stage's proxy route before any business requests."""
    proxy_url = next(
        (Config.get_proxy_url_for_stage(stage) for stage in stages
         if Config.get_proxy_url_for_stage(stage)),
        None,
    )
    if not proxy_url:
        return True, "Proxy preflight skipped: no selected stage uses a proxy"

    try:
        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession() as session:
            async with session.get(
                PROXY_PROBE_URL,
                timeout=timeout,
                proxy=proxy_url,
            ) as response:
                if not 200 <= response.status < 300:
                    return False, f"Proxy preflight failed: probe returned HTTP {response.status}"
                egress_ip = (await response.text()).strip()
    except Exception as exc:
        return False, f"Proxy preflight failed: {type(exc).__name__}: {exc}"

    message = "Proxy preflight passed"
    if Config.PROXY_DEBUG and egress_ip:
        message += f" (egress IP: {egress_ip})"
    return True, message
