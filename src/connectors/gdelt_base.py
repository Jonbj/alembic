"""Shared base for GDELT connectors."""

import logging

import aiohttp

logger = logging.getLogger(__name__)

_GDELT_BACKOFF_BASE = 2.0
_GDELT_BACKOFF_MAX = 60.0
_GDELT_MAX_RETRIES = 5


class _GDELTBaseConnector:
    """Mixin providing exponential-backoff fetch for GDELT API endpoints."""

    async def _fetch_with_backoff(
        self,
        session: aiohttp.ClientSession,
        params: dict,
        url: str,
    ) -> dict | None:
        """Fetch a GDELT API URL with exponential backoff for HTTP 429."""
        import asyncio

        for attempt in range(_GDELT_MAX_RETRIES):
            try:
                async with session.get(url, params=params) as resp:
                    if resp.status == 429:
                        wait_time = min(
                            _GDELT_BACKOFF_BASE * (2**attempt), _GDELT_BACKOFF_MAX
                        )
                        logger.warning(
                            "GDELT rate limited, waiting %.1fs before retry", wait_time
                        )
                        await asyncio.sleep(wait_time)
                        continue
                    resp.raise_for_status()
                    return await resp.json()
            except aiohttp.ClientResponseError as e:
                if e.status == 429 and attempt < _GDELT_MAX_RETRIES - 1:
                    continue
                logger.warning("GDELT HTTP error %s: %s", e.status, e.message)
                return None
        logger.warning("GDELT: Max retries exceeded after rate limiting")
        return None
