"""P0-02 (WS-01) — JWT fail-fast + no hardcoded secrets.

Two safety properties:

1. JWT_SECRET_KEY must be set explicitly before the API server starts.
   Current behaviour: jwt_utils silently falls back to an ephemeral random key
   when JWT_SECRET_KEY is empty, which means tokens differ across workers/restarts.
   Fix: lifespan() raises RuntimeError when JWT_SECRET_KEY is not configured.

2. No API key literal may appear in tracked script files.
   Current offender: scripts/daily_analysis.sh line 51 has a hardcoded ADMIN key.
   Fix: read the key from env/ALEMBIC_API_KEY at runtime; inject via placeholder.
"""

from __future__ import annotations

import pathlib
import re

import pytest


class TestNoHardcodedSecrets:
    """No plaintext API key literals in tracked scripts."""

    def test_no_dangerously_skip_permissions_in_scripts(self):
        """scripts/ must not invoke claude --dangerously-skip-permissions."""
        offenders: list[str] = []
        for path in sorted(pathlib.Path("scripts").rglob("*")):
            if path.suffix in (".sh", ".py") and path.is_file():
                for lineno, line in enumerate(path.read_text().splitlines(), 1):
                    if "--dangerously-skip-permissions" in line and not line.strip().startswith("#"):
                        offenders.append(f"{path}:{lineno}: {line.strip()[:80]}")
        assert not offenders, (
            "Script invokes claude --dangerously-skip-permissions — replace with "
            "--allowedTools <whitelist>:\n" + "\n".join(offenders)
        )

    def test_no_hardcoded_api_key_in_scripts(self):
        """scripts/ must not embed API key literals (≥16-char alphanumeric after API_KEY=)."""
        # Match values ≥16 chars that are NOT dunder-bounded placeholders like __FOO__.
        # Real API keys are base64url or hex — they don't start with double underscores.
        pattern = re.compile(r'API_KEY=["\'](?!__)([A-Za-z0-9+/=_\-]{16,})["\']')
        offenders: list[str] = []
        for path in sorted(pathlib.Path("scripts").rglob("*")):
            if path.suffix in (".sh", ".py") and path.is_file():
                for lineno, line in enumerate(path.read_text().splitlines(), 1):
                    if pattern.search(line):
                        offenders.append(f"{path}:{lineno}: {line.strip()[:80]}")
        assert not offenders, (
            "Hardcoded API key literal found — replace with env var or .env lookup:\n"
            + "\n".join(offenders)
        )


class TestJWTFailFast:
    """API server lifespan must refuse to start without JWT_SECRET_KEY."""

    @pytest.mark.asyncio
    async def test_lifespan_raises_if_jwt_secret_missing(self):
        """lifespan() raises RuntimeError when JWT_SECRET_KEY is empty string."""
        from unittest.mock import MagicMock, patch

        from src.api.main import app, lifespan

        with patch("src.api.main.config") as mock_cfg, \
             patch("src.api.main.Redis") as mock_redis_cls, \
             patch("src.api.main.init_redis"):
            mock_cfg.JWT_SECRET_KEY = ""
            mock_cfg.REDIS_URL = "redis://localhost:6379/0"
            mock_redis_cls.from_url.return_value = MagicMock()

            with pytest.raises(RuntimeError, match="JWT_SECRET_KEY"):
                async with lifespan(app):
                    pass

    @pytest.mark.asyncio
    async def test_lifespan_starts_normally_with_jwt_secret(self):
        """lifespan() succeeds when JWT_SECRET_KEY is set to a non-empty value."""
        from unittest.mock import MagicMock, patch

        from src.api.main import app, lifespan

        with patch("src.api.main.config") as mock_cfg, \
             patch("src.api.main.Redis") as mock_redis_cls, \
             patch("src.api.main.init_redis"), \
             patch("src.api.main.close_redis"):
            mock_cfg.JWT_SECRET_KEY = "a-sufficiently-strong-jwt-secret-key"
            mock_cfg.REDIS_URL = "redis://localhost:6379/0"
            mock_redis_cls.from_url.return_value = MagicMock()

            # Must not raise
            async with lifespan(app):
                pass
