"""Reachability probing for URL-based integrations (SearXNG, Home Assistant, Ollama).

Probed once at startup; re-probed every PROBE_INTERVAL seconds in the background.
Skills read is_reachable() inside their enabled_check so they are only offered
when the backing service is both configured AND reachable.
On a runtime call failure, call mark_unreachable() to immediately withdraw
the skill from the next request without waiting for the re-probe cycle.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

PROBE_INTERVAL = 5 * 60  # seconds between background re-probes

# service name → True (reachable) / False (unreachable or not yet probed)
# A service is absent until its first probe; is_reachable() returns False for absent keys.
_reachable: dict[str, bool] = {}
_probe_task: Optional[asyncio.Task] = None


# ── Per-service probe functions ────────────────────────────────────────────────


async def probe_searxng(url: str, timeout: float = 3.0) -> tuple[bool, str]:
    """GET /search?q=test&format=json — expect JSON with 'results' or 'query' key."""
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(
                f"{url}/search",
                params={"q": "test", "format": "json"},
            )
            if resp.status_code == 200:
                data = resp.json()
                if "results" in data or "query" in data:
                    return True, f"SearXNG at {url}"
                return False, (
                    f"SearXNG at {url} returned JSON but 'results' key missing — "
                    "JSON format may not be enabled in SearXNG settings"
                )
            if resp.status_code == 403:
                return False, (
                    f"SearXNG at {url} returned 403, "
                    "JSON format not enabled in SearXNG settings"
                )
            return False, f"SearXNG at {url} returned HTTP {resp.status_code}"
    except httpx.ConnectError:
        return False, f"SearXNG at {url} refused connection"
    except httpx.TimeoutException:
        return False, f"SearXNG at {url} timed out"
    except Exception as exc:
        return False, f"SearXNG at {url}: {exc}"


async def probe_hass(url: str, token: str, timeout: float = 3.0) -> tuple[bool, str]:
    """GET /api/ with Bearer token — expect 200."""
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(
                f"{url}/api/",
                headers={"Authorization": f"Bearer {token}"},
            )
            if resp.status_code == 200:
                return True, f"Home Assistant at {url}"
            if resp.status_code == 401:
                return False, f"Home Assistant at {url} returned 401 (invalid token)"
            return False, f"Home Assistant at {url} returned HTTP {resp.status_code}"
    except httpx.ConnectError:
        return False, f"Home Assistant at {url} refused connection"
    except httpx.TimeoutException:
        return False, f"Home Assistant at {url} timed out"
    except Exception as exc:
        return False, f"Home Assistant at {url}: {exc}"


async def probe_ollama(url: str, timeout: float = 3.0) -> tuple[bool, str]:
    """GET /api/tags — expect 200."""
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(f"{url}/api/tags")
            if resp.status_code == 200:
                return True, f"Ollama at {url}"
            return False, f"Ollama at {url} returned HTTP {resp.status_code}"
    except httpx.ConnectError:
        return False, f"Ollama at {url} refused connection"
    except httpx.TimeoutException:
        return False, f"Ollama at {url} timed out"
    except Exception as exc:
        return False, f"Ollama at {url}: {exc}"


# ── State accessors ────────────────────────────────────────────────────────────


def is_reachable(service: str) -> bool:
    """True only when the service has been probed and found reachable."""
    return _reachable.get(service, False)


def mark_unreachable(service: str) -> None:
    """Called on runtime call failure to immediately withdraw the skill."""
    was = _reachable.get(service)
    _reachable[service] = False
    if was is not False:
        logger.warning("%s marked unreachable after runtime failure", service)


# ── Probe runner ───────────────────────────────────────────────────────────────


async def _run_all_probes() -> None:
    """Probe every configured URL-based integration; log one line per service."""
    from app.config import get_settings
    settings = get_settings()

    async def _check(service: str, coro) -> None:
        prev = _reachable.get(service)
        ok, detail = await coro
        _reachable[service] = ok
        if ok:
            if prev is not True:
                logger.info("%s available: %s", service, detail)
        else:
            if prev is not False:
                logger.warning("%s unavailable: %s", service, detail)
            else:
                logger.info("%s unavailable: %s", service, detail)

    tasks = []
    if settings.web_search_enabled:
        tasks.append(_check("web_search", probe_searxng(settings.searxng_url)))
    if settings.smart_home_enabled:
        tasks.append(_check("smart_home", probe_hass(settings.hass_url, settings.hass_token)))
    if settings.ollama_enabled:
        tasks.append(_check("ollama", probe_ollama(settings.ollama_base_url)))

    if tasks:
        await asyncio.gather(*tasks)


# ── Lifecycle ──────────────────────────────────────────────────────────────────


async def _background_loop() -> None:
    while True:
        await asyncio.sleep(PROBE_INTERVAL)
        try:
            await _run_all_probes()
        except Exception:
            logger.exception("Availability probe loop error")


async def startup_probe() -> None:
    """Run initial probes and launch the background re-probe task."""
    await _run_all_probes()
    global _probe_task
    _probe_task = asyncio.create_task(_background_loop())
    _probe_task.set_name("availability-probe-loop")


def shutdown() -> None:
    """Cancel the background probe task on app shutdown."""
    global _probe_task
    if _probe_task and not _probe_task.done():
        _probe_task.cancel()
    _probe_task = None
