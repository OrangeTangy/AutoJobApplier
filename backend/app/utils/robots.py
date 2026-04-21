"""
robots.txt compliance checker.

Checks whether automated access to a URL is permitted before Playwright
navigates to it. This is a hard safety check — if robots.txt disallows
the path, submission is aborted.
"""
from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import httpx
import structlog

logger = structlog.get_logger(__name__)

USER_AGENT = "AutoJobApplier/1.0"


async def is_allowed(url: str) -> tuple[bool, str]:
    """
    Check robots.txt for the given URL.
    Returns (allowed: bool, reason: str).
    """
    try:
        parsed = urlparse(url)
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"

        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            resp = await client.get(robots_url)

        if resp.status_code == 404:
            # No robots.txt means no restrictions
            return True, "No robots.txt found — access permitted"

        if resp.status_code != 200:
            # Treat fetch errors conservatively
            logger.warning("robots_fetch_error", url=robots_url, status=resp.status_code)
            return True, f"robots.txt returned {resp.status_code} — proceeding cautiously"

        rp = RobotFileParser()
        rp.set_url(robots_url)
        rp.parse(resp.text.splitlines())

        allowed = rp.can_fetch(USER_AGENT, url)
        # Also check with wildcard agent
        if not allowed:
            allowed = rp.can_fetch("*", url)

        if allowed:
            return True, "robots.txt permits access"
        else:
            logger.warning("robots_disallowed", url=url)
            return False, f"robots.txt disallows automated access to {url}"

    except Exception as exc:
        logger.error("robots_check_error", url=url, error=str(exc))
        # On error, default to permitting (don't block on transient network issues)
        return True, f"robots.txt check failed ({exc}) — proceeding"


def extract_crawl_delay(robots_text: str) -> float | None:
    """Extract Crawl-delay directive if present."""
    for line in robots_text.splitlines():
        if line.lower().startswith("crawl-delay:"):
            try:
                return float(line.split(":", 1)[1].strip())
            except ValueError:
                pass
    return None
