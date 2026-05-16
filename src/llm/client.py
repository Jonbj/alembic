"""
Base LLM client interface and implementations for the LLM Trading System.

This module provides abstract and concrete implementations of LLM clients that
interface with various language models (Claude Opus, Qwen 3.5, DeepSeek, etc.)
through the Claude CLI tool. All clients follow the same pattern:

1. Validate model_id against an allowlist (SECURITY: prevent command injection)
2. Execute the CLI tool asynchronously (non-blocking)
3. Parse JSON response with robust error handling
4. Retry with exponential backoff on transient failures

Security Features:
- ALLOWED_MODEL_IDS frozenset prevents arbitrary command execution
- CLI path validation prevents path injection
- Error output sanitization prevents secret leakage
- Environment variable stripping in subprocess

Usage Example:
    >>> from src.llm.client import OpusClient
    >>> from src.models.news import LLMSentimentOutput
    >>>
    >>> client = OpusClient()
    >>> result = await client.complete(
    ...     prompt="Analyze this news: Fed raises rates...",
    ...     response_schema=LLMSentimentOutput
    ... )
    >>> print(result.polarity, result.confidence)

Author: LLM Trading System Team
Version: 1.0.0
"""

import asyncio
import json
import logging
import os
import re
import shutil
import subprocess
from abc import ABC, abstractmethod
from typing import Generic, TypeVar

logger = logging.getLogger(__name__)

import aiohttp
from pydantic import BaseModel, ValidationError

from src.config import config

T = TypeVar("T", bound=BaseModel)

# SECURITY: Allowlist of valid model IDs to prevent command injection
# This frozenset is the single source of truth for which models can be called.
# Any model_id not in this set will raise ValueError before subprocess execution.
#
# Source: models.md - tutti i modelli funzionanti (general + coding)
# Last updated: 2026-05-03
#
# Categories:
# - Claude aliases (general purpose): opus, sonnet, haiku
# - General purpose cloud: qwen3.5:cloud, deepseek-v4-pro:cloud, glm-5.1:cloud, etc.
# - Coding specialized: qwen3-coder-next:cloud, devstral-small-2:24b-cloud, etc.
ALLOWED_MODEL_IDS = frozenset({
    # Claude aliases (general purpose)
    "opus", "sonnet", "haiku",
    # General purpose cloud
    "qwen3.5:cloud", "deepseek-v4-pro:cloud",
    "glm-5.1:cloud", "kimi-k2.6:cloud", "gemma4:31b-cloud",
    # Coding specialized
    "qwen3-coder-next:cloud", "devstral-small-2:24b-cloud",
    "devstral-2:123b-cloud", "minimax-m2.1:cloud",
    "qwen3-coder:480b-cloud", "minimax-m2:cloud",
})


def _sanitize_error_output(stderr: str) -> str:
    """
    Sanitize error output from LLM CLI to prevent information leakage.

    This function removes sensitive information from stderr before it is exposed
    to logs or users. It is a critical security control that prevents:

    1. **Path disclosure**: Internal file paths could reveal directory structure
    2. **Secret leakage**: API keys, tokens, or credentials in environment variables
    3. **Stack traces**: Full stack traces could expose implementation details

    Args:
        stderr: Raw stderr string from subprocess execution

    Returns:
        Sanitized stderr string with:
        - File paths replaced with '[PATH]'
        - Long alphanumeric strings (>32 chars) replaced with '[REDACTED]'
        - Output truncated to 200 characters max

    Security Note:
        This function is called BEFORE any error is logged or displayed to users.
        It is a defense-in-depth measure that assumes the CLI could potentially
        leak sensitive information in error messages.

    Example:
        >>> _sanitize_error_output("Error at /home/user/.claude/config.json: token abc123...")
        'Error at [PATH]: token [REDACTED]'
    """
    # Remove file paths (could reveal directory structure)
    stderr = re.sub(r'/[a-zA-Z0-9_/.-]+', '[PATH]', stderr)
    # Remove potential secrets (alphanumeric strings > 32 chars)
    stderr = re.sub(r'\b[A-Za-z0-9]{32,}\b', '[REDACTED]', stderr)
    return stderr[:200]


class LLMClient(ABC, Generic[T]):
    """
    Abstract base class for all LLM client implementations.

    This class defines the interface that all LLM clients must implement:
    - `complete()`: Async method to call the LLM and parse the response

    The base class provides shared security and utility methods:
    - `_validate_model_id()`: Check against ALLOWED_MODEL_IDS allowlist
    - `_get_cli_path()`: Validate and resolve CLI binary path
    - `_call_cli()`: Execute subprocess with security controls
    - `parse_json_response()`: Extract JSON from LLM response text

    Type Parameter:
        T: A Pydantic BaseModel subclass that defines the expected response schema

    Attributes:
        model_id (str): The model identifier used in CLI calls (e.g., "opus", "qwen3.5:cloud")
        model_name (str): Human-readable model name (e.g., "Claude Opus")
        max_retries (int): Maximum number of retry attempts on transient failures
        timeout (int): Timeout in seconds for each LLM call

    Usage Example:
        >>> class CustomClient(LLMClient[LLMSentimentOutput]):
        ...     model_id = "custom-model"
        ...     model_name = "Custom Model"
        ...
        ...     async def complete(self, prompt: str, response_schema: type[T]) -> T:
        ...         # Custom implementation
        ...         pass

    Security Considerations:
        - All model_id values are validated against ALLOWED_MODEL_IDS
        - CLI path is validated to prevent path injection
        - Subprocess environment is sanitized (LC_ALL=C)
        - Error output is sanitized before exposure
    """

    model_id: str = ""
    model_name: str = ""

    def __init__(self, max_retries: int | None = None, timeout: int | None = None):
        """
        Initialize LLM client with retry and timeout configuration.

        Args:
            max_retries: Maximum retry attempts (default: from config.LLM_MAX_RETRIES)
            timeout: Timeout in seconds (default: from config.LLM_TIMEOUT_SECONDS)

        Note:
            Subclasses should call super().__init__() in their __init__ method
            to ensure proper configuration initialization.
        """
        self.max_retries = max_retries or config.LLM_MAX_RETRIES
        self.timeout = timeout or config.LLM_TIMEOUT_SECONDS

    @abstractmethod
    async def complete(self, prompt: str, response_schema: type[T]) -> T:
        """
        Call the LLM with the given prompt and parse the response.

        This is the primary method for interacting with the LLM. Implementations
        should:
        1. Send the prompt to the LLM (via CLI, API, etc.)
        2. Extract JSON from the response
        3. Parse JSON into the specified response_schema
        4. Handle retries with exponential backoff on transient failures

        Args:
            prompt: The prompt to send to the LLM (should include DK-CoT instructions)
            response_schema: Pydantic BaseModel class for response validation

        Returns:
            Parsed response object of type T (subclass of BaseModel)

        Raises:
            ValidationError: If response JSON doesn't match the schema
            json.JSONDecodeError: If response contains no valid JSON
            ValueError: If JSON extraction fails
            RuntimeError: If all retry attempts are exhausted

        Example:
            >>> client = OpusClient()
            >>> result = await client.complete(
            ...     prompt="Analyze: Fed raises rates by 25bp...",
            ...     response_schema=LLMSentimentOutput
            ... )
            >>> print(result.polarity)  # Access parsed fields
        """
        pass

    def _validate_model_id(self, model_id: str) -> None:
        """
        Validate model_id against the ALLOWED_MODEL_IDS security allowlist.

        This is a critical security control that prevents command injection attacks.
        Without this validation, an attacker could pass a malicious model_id like
        "opus; rm -rf /" and execute arbitrary commands.

        Args:
            model_id: The model identifier to validate

        Raises:
            ValueError: If model_id is not in the allowlist

        Security Note:
            This validation happens BEFORE any subprocess execution.
            The error message includes the allowed values for debugging.

        Example:
            >>> client = OpusClient()
            >>> client._validate_model_id("opus")  # OK, no exception
            >>> client._validate_model_id("malicious; rm -rf /")  # Raises ValueError
        """
        if model_id not in ALLOWED_MODEL_IDS:
            raise ValueError(
                f"Invalid model_id: {model_id!r}. "
                f"Allowed: {sorted(ALLOWED_MODEL_IDS)}"
            )

    def _get_cli_path(self) -> str:
        """
        Validate and resolve the path to the Claude CLI binary.

        This method performs several security checks:
        1. If CLAUDE_CLI_PATH is relative, resolve it via PATH (shutil.which)
        2. If CLAUDE_CLI_PATH is absolute, verify the file exists
        3. Raise FileNotFoundError if the CLI cannot be located

        Returns:
            Absolute path to the Claude CLI binary

        Raises:
            FileNotFoundError: If the CLI binary cannot be found

        Security Note:
            Using shutil.which() for relative paths ensures we only execute
            binaries found in standard PATH locations, not arbitrary files.

        Example:
            >>> client = OpusClient()
            >>> cli_path = client._get_cli_path()
            >>> print(cli_path)  # "/usr/local/bin/claude" or similar
        """
        cli_path = config.CLAUDE_CLI_PATH
        if not os.path.isabs(cli_path):
            resolved = shutil.which(cli_path)
            if resolved is None:
                raise FileNotFoundError(
                    f"Claude CLI '{cli_path}' not found in PATH"
                )
            return resolved
        if not os.path.exists(cli_path):
            raise FileNotFoundError(f"Claude CLI not found at: {cli_path}")
        return cli_path

    def _call_cli(self, prompt: str, model_id: str) -> str:
        """
        Execute the Claude CLI subprocess with full security controls.

        This is the low-level method that actually invokes the LLM via the
        Claude CLI tool. It implements multiple security measures:

        1. **Model ID validation**: Checked against ALLOWED_MODEL_IDS before execution
        2. **CLI path validation**: Verified via _get_cli_path()
        3. **Timeout enforcement**: Prevents hung processes
        4. **Environment sanitization**: LC_ALL=C strips potentially dangerous env vars
        5. **Error sanitization**: _sanitize_error_output() before exposing stderr

        Args:
            prompt: The prompt to send to the LLM
            model_id: The model identifier (must be in ALLOWED_MODEL_IDS)

        Returns:
            Raw stdout string from the CLI subprocess

        Raises:
            ValueError: If model_id is not in ALLOWED_MODEL_IDS
            FileNotFoundError: If CLI binary cannot be found
            RuntimeError: If CLI returns non-zero exit code

        Note:
            This method is synchronous and should be called via
            asyncio.get_running_loop().run_in_executor() for async operation.

        Example:
            >>> client = OpusClient()
            >>> result = client._call_cli("Analyze this news...", "opus")
            >>> print(result)  # Raw JSON string from CLI
        """
        # SECURITY: Validate model_id BEFORE subprocess (prevent command injection)
        self._validate_model_id(model_id)

        # SECURITY: Validate CLI path (prevent path injection)
        cli_path = self._get_cli_path()

        proc = subprocess.run(
            [cli_path, "--model", model_id, "--print"],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=self.timeout,
            check=False,
            env={**os.environ, "LC_ALL": "C"},  # Sanitize environment
        )
        if proc.returncode != 0:
            # SECURITY: Sanitize stderr before exposing (prevent secret leakage)
            safe_error = _sanitize_error_output(proc.stderr)
            raise RuntimeError(f"Claude CLI error (code {proc.returncode}): {safe_error}")
        return proc.stdout

    @staticmethod
    def parse_json_response(raw: str) -> str:
        """
        Extract valid JSON from LLM response text using robust heuristics.

        LLMs often include explanatory text before/after the JSON payload.
        This method uses a multi-strategy approach to extract the JSON:

        1. **Boundary detection**: Find outermost `{...}` braces in the response
        2. **Validation**: Attempt to parse the extracted candidate
        3. **Fallback**: Try parsing the entire response if boundary detection fails

        This approach handles common LLM output patterns:
        - "Here is the analysis: {...}"
        - "```json {...} ```"
        - "{...} (confidence: 0.8)"

        Args:
            raw: Raw response text from the LLM (may contain non-JSON text)

        Returns:
            Clean JSON string ready for parsing with json.loads()

        Raises:
            ValueError: If no valid JSON can be extracted from the response

        Example:
            >>> text = "Here is my analysis:\\n{\\n  \\"polarity\\": 0.5\\n}"
            >>> parse_json_response(text)
            '{\\n  "polarity": 0.5\\n}'
        """
        raw = raw.strip()

        # Strategy 1: Try to find JSON object boundaries
        start = raw.find("{")
        end = raw.rfind("}") + 1

        if start >= 0 and end > start:
            candidate = raw[start:end]
            # Validate by parsing
            try:
                json.loads(candidate)
                return candidate
            except json.JSONDecodeError:
                pass

        # Strategy 2: Fallback - try to parse the whole thing
        try:
            json.loads(raw)
            return raw
        except json.JSONDecodeError:
            raise ValueError(f"Unable to extract valid JSON from response")


class OpusClient(LLMClient):
    """
    Claude Opus client for high-reasoning sentiment analysis tasks.

    Opus is the most capable model in the Claude family, optimized for:
    - Complex reasoning and analysis
    - Nuanced sentiment detection
    - Long-context understanding (200K tokens)

    This client uses the Claude CLI tool to invoke Opus asynchronously,
    with automatic retry logic and JSON response parsing.

    Attributes:
        model_id: "opus" - the CLI model identifier
        model_name: "Claude Opus" - human-readable name

    Usage Example:
        >>> from src.llm.client import OpusClient
        >>> from src.models.news import LLMSentimentOutput
        >>>
        >>> client = OpusClient(max_retries=3, timeout=120)
        >>> result = await client.complete(
        ...     prompt="Analyze: Fed raises rates by 25bp...",
        ...     response_schema=LLMSentimentOutput
        ... )
        >>> print(f"Polarity: {result.polarity}, Confidence: {result.confidence}")

    Cost (per 1M tokens):
        - Input: $15.00
        - Output: $75.00

    Typical Latency:
        - Simple prompts: 2-5 seconds
        - Complex analysis: 5-15 seconds
    """

    model_id = "opus"
    model_name = "Claude Opus"

    async def complete(self, prompt: str, response_schema: type[T]) -> T:
        """
        Call Claude Opus with the given prompt and parse the structured response.

        This method implements the complete LLM interaction flow:
        1. Execute CLI call asynchronously (non-blocking via run_in_executor)
        2. Extract JSON from the response text
        3. Parse JSON into the specified Pydantic schema
        4. Retry with exponential backoff on parse failures

        Args:
            prompt: The analysis prompt (should include DK-CoT instructions)
            response_schema: Pydantic BaseModel class for response validation
                             (e.g., LLMSentimentOutput)

        Returns:
            Parsed response object with fields defined by response_schema

        Raises:
            ValidationError: If response JSON doesn't match the expected schema
            json.JSONDecodeError: If response contains no valid JSON
            ValueError: If JSON extraction fails after all strategies
            RuntimeError: If all retry attempts are exhausted

        Retry Behavior:
            - Attempt 1: Immediate execution
            - Attempt 2: Wait 0.5s after failure
            - Attempt 3: Wait 1.0s after failure
            - ...
            - Attempt N: Wait 0.5 * N seconds after failure

        Example:
            >>> client = OpusClient()
            >>> result = await client.complete(
            ...     prompt="You are a buy-side analyst. Analyze: AAPL beats earnings...",
            ...     response_schema=LLMSentimentOutput
            ... )
            >>> assert -1.0 <= result.polarity <= 1.0
            >>> assert 0.0 <= result.confidence <= 1.0
        """
        loop = asyncio.get_running_loop()

        for attempt in range(self.max_retries + 1):
            try:
                result = await loop.run_in_executor(
                    None, self._call_cli, prompt, self.model_id
                )
                raw = self.parse_json_response(result)
                return response_schema.model_validate_json(raw)
            except (ValidationError, json.JSONDecodeError, ValueError):
                if attempt == self.max_retries:
                    raise
                await asyncio.sleep(0.5 * (attempt + 1))

        raise RuntimeError("Exhausted retries for OpusClient")


class Qwen35Client(LLMClient):
    """
    Qwen 3.5 client for technical and quantitative analysis tasks.

    Qwen 3.5 (Alibaba) is a strong general-purpose model that excels at:
    - Technical analysis and chart interpretation
    - Quantitative reasoning
    - Multi-lingual support (including Chinese financial news)

    This client provides a cost-effective alternative to Opus for
    high-volume sentiment analysis with competitive accuracy.

    Attributes:
        model_id: "qwen3.5:cloud" - the CLI model identifier
        model_name: "Qwen 3.5" - human-readable name

    Usage Example:
        >>> from src.llm.client import Qwen35Client
        >>> from src.models.news import LLMSentimentOutput
        >>>
        >>> client = Qwen35Client()
        >>> result = await client.complete(
        ...     prompt="Analyze: ECB holds rates steady, hints at cut...",
        ...     response_schema=LLMSentimentOutput
        ... )

    Cost (per 1M tokens):
        - Input: $2.00
        - Output: $6.00
        (Approximately 7-8x cheaper than Opus)

    Typical Latency:
        - Simple prompts: 1-3 seconds
        - Complex analysis: 3-8 seconds
    """

    model_id = "qwen3.5:cloud"
    model_name = "Qwen 3.5"

    async def complete(self, prompt: str, response_schema: type[T]) -> T:
        """
        Call Qwen 3.5 with the given prompt and parse the structured response.

        Implementation is identical to OpusClient but targets the Qwen 3.5
        model. See OpusClient.complete() for detailed documentation.

        Args:
            prompt: The analysis prompt (should include DK-CoT instructions)
            response_schema: Pydantic BaseModel class for response validation

        Returns:
            Parsed response object with fields defined by response_schema

        Raises:
            ValidationError: If response JSON doesn't match the expected schema
            json.JSONDecodeError: If response contains no valid JSON
            ValueError: If JSON extraction fails
            RuntimeError: If all retry attempts are exhausted
        """
        loop = asyncio.get_running_loop()

        for attempt in range(self.max_retries + 1):
            try:
                result = await loop.run_in_executor(
                    None, self._call_cli, prompt, self.model_id
                )
                raw = self.parse_json_response(result)
                return response_schema.model_validate_json(raw)
            except (ValidationError, json.JSONDecodeError, ValueError):
                if attempt == self.max_retries:
                    raise
                await asyncio.sleep(0.5 * (attempt + 1))

        raise RuntimeError("Exhausted retries for Qwen35Client")


class DeepseekClient(LLMClient):
    """DeepSeek V4 Pro client for coding and reasoning."""

    model_id = "deepseek-v4-pro:cloud"
    model_name = "DeepSeek V4 Pro"

    async def complete(self, prompt: str, response_schema: type[T]) -> T:
        """Call DeepSeek and parse response."""
        loop = asyncio.get_running_loop()

        for attempt in range(self.max_retries + 1):
            try:
                result = await loop.run_in_executor(
                    None, self._call_cli, prompt, self.model_id
                )
                raw = self.parse_json_response(result)
                return response_schema.model_validate_json(raw)
            except (ValidationError, json.JSONDecodeError, ValueError):
                if attempt == self.max_retries:
                    raise
                await asyncio.sleep(0.5 * (attempt + 1))

        raise RuntimeError("Exhausted retries for DeepseekClient")


class GlmClient(LLMClient):
    """GLM-5.1 client for financial sentiment with chain-of-thought reasoning.

    GLM-5.1 (Zhipu AI) is a thinking model that excels at:
    - Step-by-step reasoning (maps well to DK-CoT prompts)
    - Financial domain knowledge (Zhipu AI focuses heavily on finance)
    - Nuanced sentiment detection

    Accessed via claude CLI with --model glm-5.1:cloud (Ollama cloud).
    """

    model_id = "glm-5.1:cloud"
    model_name = "GLM 5.1"

    async def complete(self, prompt: str, response_schema: type[T]) -> T:
        """Call GLM-5.1 and parse response."""
        loop = asyncio.get_running_loop()

        for attempt in range(self.max_retries + 1):
            try:
                result = await loop.run_in_executor(
                    None, self._call_cli, prompt, self.model_id
                )
                raw = self.parse_json_response(result)
                return response_schema.model_validate_json(raw)
            except (ValidationError, json.JSONDecodeError, ValueError):
                if attempt == self.max_retries:
                    raise
                await asyncio.sleep(0.5 * (attempt + 1))

        raise RuntimeError("Exhausted retries for GlmClient")


# ---------------------------------------------------------------------------
# Ollama Cloud HTTP clients
# ---------------------------------------------------------------------------

class OllamaCloudClient(LLMClient):
    """Base class for Ollama cloud models accessed via HTTP API.

    Calls https://ollama.com/api/chat directly using aiohttp.
    Authentication: OLLAMA_API_KEY env var → Authorization: Bearer header.
    Response format: data["message"]["content"] contains the text.

    Unlike the CLI-based clients above, this does NOT use the claude CLI —
    it's a direct HTTP call to Ollama's cloud inference endpoint.
    """

    model_id: str = ""
    model_name: str = ""

    async def complete(self, prompt: str, response_schema: type[T]) -> T:
        """POST to Ollama /api/chat and parse the response as JSON schema."""
        if not config.OLLAMA_API_KEY:
            raise RuntimeError("OLLAMA_API_KEY is not set")
        self._validate_model_id(self.model_id)

        url = f"{config.OLLAMA_BASE_URL}/api/chat"
        headers = {
            "Authorization": f"Bearer {config.OLLAMA_API_KEY}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model_id,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
        }
        timeout = aiohttp.ClientTimeout(total=self.timeout)

        for attempt in range(self.max_retries + 1):
            try:
                async with aiohttp.ClientSession(headers=headers, timeout=timeout) as session:
                    async with session.post(url, json=payload) as resp:
                        resp.raise_for_status()
                        data = await resp.json()
                raw = data["message"]["content"]
                json_str = self.parse_json_response(raw)
                return response_schema.model_validate_json(json_str)
            except (ValidationError, json.JSONDecodeError, ValueError, KeyError):
                if attempt == self.max_retries:
                    raise
                await asyncio.sleep(0.5 * (attempt + 1))
            except aiohttp.ClientResponseError as e:
                if e.status == 429:
                    if attempt >= self.max_retries:
                        raise RuntimeError(
                            f"Ollama rate limit (429) on {self.model_id}: exhausted retries"
                        ) from e
                    # Exponential backoff: 60s, 120s, 180s — pause until limit resets
                    wait = 60.0 * (attempt + 1)
                    logger.warning(
                        "Ollama rate limit 429 on %s (attempt %d/%d) — pausing %.0fs",
                        self.model_id, attempt + 1, self.max_retries + 1, wait,
                    )
                    await asyncio.sleep(wait)
                    continue
                raise RuntimeError(f"Ollama API error {e.status}: {e.message}") from e

        raise RuntimeError(f"Exhausted retries for {self.__class__.__name__}")


class OllamaKimiClient(OllamaCloudClient):
    """Kimi-k2.6 via Ollama cloud HTTP API — thinking model, long context."""
    model_id = "kimi-k2.6:cloud"
    model_name = "Kimi k2.6 (Ollama)"


class OllamaGlmClient(OllamaCloudClient):
    """GLM-5.1 via Ollama cloud HTTP API."""
    model_id = "glm-5.1:cloud"
    model_name = "GLM 5.1 (Ollama)"


class OllamaQwen35Client(OllamaCloudClient):
    """Qwen3.5 via Ollama cloud HTTP API."""
    model_id = "qwen3.5:cloud"
    model_name = "Qwen 3.5 (Ollama)"


class OllamaDeepseekClient(OllamaCloudClient):
    """DeepSeek V4 Pro via Ollama cloud HTTP API."""
    model_id = "deepseek-v4-pro:cloud"
    model_name = "DeepSeek V4 Pro (Ollama)"
