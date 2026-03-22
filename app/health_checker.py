"""Async HTTP health checker with in-memory result cache."""

import asyncio
import logging

import httpx

log = logging.getLogger(__name__)

PROBE_TIMEOUT = 5.0  # seconds per request

# In-memory cache: {service_id: "healthy" | "unhealthy" | "pending"}
_cache: dict[str, str] = {}


def get_health_status(service_id: str) -> str:
    return _cache.get(service_id, "pending")


def get_all_statuses() -> dict[str, str]:
    return dict(_cache)


async def _probe(url: str) -> bool:
    """Returns True if the URL responds with any HTTP reply (connection success)."""
    try:
        async with httpx.AsyncClient(verify=False, follow_redirects=True) as client:
            resp = await client.get(url, timeout=PROBE_TIMEOUT)
            # Accept any HTTP response — a 401/403 still means the service is up
            return True
    except Exception:
        return False


async def poll_health_checks(services: list[dict]):
    """Probe all services that have a health_check_url and update the cache."""
    targets = [(s["id"], s["health_check_url"]) for s in services if s.get("health_check_url")]
    if not targets:
        return

    results = await asyncio.gather(*(_probe(url) for _, url in targets), return_exceptions=True)

    for (sid, _url), result in zip(targets, results):
        if isinstance(result, Exception):
            log.warning("Health probe exception for %s: %s", sid, result)
            _cache[sid] = "unhealthy"
        else:
            _cache[sid] = "healthy" if result else "unhealthy"
