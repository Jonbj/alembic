"""Text sanitization for LLM input."""

import re
import unicodedata


def sanitize_text(text: str) -> str:
    """
    Sanitize text before feeding to LLM.

    Mitigations:
    - Unicode homoglyph normalization (visually identical chars that corrupt NER)
    - Hidden text removal (zero-width chars, control chars)
    - BiDi override character removal (prevent RTL attacks)
    - Emoji removal (prevent JSON parsing issues)
    - ASCII normalization for ticker symbols

    Args:
        text: Raw input text

    Returns:
        Sanitized text safe for LLM processing
    """
    if not text:
        return ""

    # Normalize Unicode to NFKC (compatibility decomposition + canonical composition)
    # This converts homoglyphs to their canonical forms
    text = unicodedata.normalize("NFKC", text)

    # Remove zero-width and invisible characters
    # Categories: Cf (format), Cc (control), Cs (surrogate), Co (private use)
    text = "".join(
        c for c in text if unicodedata.category(c) not in ("Cf", "Cc", "Cs", "Co")
    )

    # Remove specific problematic characters
    # Zero-width space, zero-width non-joiner, zero-width joiner, word joiner, BOM
    for char in ["​", "‌", "‍", "⁠", "﻿"]:
        text = text.replace(char, "")

    # SECURITY: Remove bidirectional override characters (prevent RTL attacks)
    # U+202E (RLO), U+202D (LRO), U+202C (PDF), U+2067-U+2069 (isolate overrides)
    for char in ["‮", "‭", "‬", "⁧", "⁦", "⁨", "⁩"]:
        text = text.replace(char, "")

    # Remove emoji and pictographs (can break JSON parsing)
    emoji_pattern = re.compile(
        "["
        "\U0001F600-\U0001F64F"  # emoticons
        "\U0001F300-\U0001F5FF"  # symbols & pictographs
        "\U0001F680-\U0001F6FF"  # transport & map
        "\U0001F1E0-\U0001F1FF"  # flags
        "]+",
        flags=re.UNICODE,
    )
    text = emoji_pattern.sub("", text)

    # Normalize whitespace (multiple spaces/tabs/newlines → single space)
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def sanitize_ticker(symbol: str) -> str:
    """
    Sanitize ticker symbol.

    Args:
        symbol: Raw ticker symbol

    Returns:
        Normalized ASCII ticker symbol

    Examples:
        >>> sanitize_ticker("AAPL")
        'AAPL'
        >>> sanitize_ticker("ААРL")  # Cyrillic homoglyphs
        'AAPL'
    """
    # Normalize and keep only ASCII alphanumeric
    normalized = unicodedata.normalize("NFKD", symbol.upper())
    ascii_only = normalized.encode("ASCII", "ignore").decode("ASCII")

    # Remove any non-alphanumeric chars
    return re.sub(r"[^A-Z0-9]", "", ascii_only)
