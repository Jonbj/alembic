"""Shared base for GDELT connectors.

This module provides a reusable mixin class `_GDELTBaseConnector` that implements
exponential-backoff HTTP fetching for all GDELT API connectors. It centralises
the retry logic that was previously duplicated in `GDELTConnector`, ensuring
consistent rate-limit handling across both the legacy artlist connector and the
new GKG connector introduced by the multi-asset news-driven architecture.

Why a mixin?
  - `GDELTConnector` (artlist mode) and `GDELTGKGConnector` (gkg mode) both
    need to talk to GDELT and both encounter HTTP 429. Extracting the logic
    avoids copy-paste and guarantees identical behaviour.
  - The mixin pattern was chosen over composition to keep the inheritance chain
    shallow: both connectors already inherit from `NewsConnector` (async iterator
    contract). Adding `_GDELTBaseConnector` as a second parent is the least
    intrusive refactor.

Backoff parameters (non-configurable by design — GDELT is a free public API
with aggressive rate limits, so hard-coded values are safer than user-tuned
knobs):
  - BASE  = 2.0 s   → first retry waits 2 s
  - MAX   = 60.0 s  → cap to avoid multi-minute stalls
  - TRIES = 5       → total 5 attempts = ~2 min worst case
"""

import logging

import aiohttp

logger = logging.getLogger(__name__)

_GDELT_BACKOFF_BASE = 2.0
_GDELT_BACKOFF_MAX = 60.0
_GDELT_MAX_RETRIES = 5


class _GDELTBaseConnector:
    """Mixin providing exponential-backoff fetch for GDELT API endpoints.

    Expected usage:
        class MyConnector(_GDELTBaseConnector, NewsConnector):
            async def fetch(self):
                async with aiohttp.ClientSession() as session:
                    data = await self._fetch_with_backoff(session, params, url=...)
    """

    async def _fetch_with_backoff(
        self,
        session: aiohttp.ClientSession,
        params: dict,
        url: str,
    ) -> dict | None:
        """Fetch a GDELT API URL with exponential backoff for HTTP 429.

        Args:
            session: Active aiohttp session (caller owns lifecycle).
            params: Query parameters dictionary sent as URL query string.
            url: Full GDELT endpoint URL (e.g. GDELT_DOC2_URL or GDELT_GKG_URL).

        Returns:
            Parsed JSON dict on success, None on permanent failure.

        Behaviour:
            1. Sends GET request.
            2. If HTTP 429 → computes wait = min(BASE * 2^attempt, MAX), logs,
               sleeps, and retries.
            3. If non-429 HTTP error or max retries exceeded → logs warning
               and returns None so the caller can decide whether to abort
               the entire batch or skip the current chunk.
        """
        import asyncio

        for attempt in range(_GDELT_MAX_RETRIES):
            try:
                async with session.get(url, params=params) as resp:
                    if resp.status == 429:
                        # Rate-limited by GDELT — exponential backoff before retry
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
                # Non-429 errors (5xx, 403, etc.) are not retried except 429
                if e.status == 429 and attempt < _GDELT_MAX_RETRIES - 1:
                    continue
                logger.warning("GDELT HTTP error %s: %s", e.status, e.message)
                return None
        logger.warning("GDELT: Max retries exceeded after rate limiting")
        return None
