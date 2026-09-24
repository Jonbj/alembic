"""Text sanitization for LLM input."""

import html
import re
import unicodedata

# HTML tags, matched conservatively: a tag opens with `<` immediately followed by a
# letter (or `</`), so a comparison like "revenue < 5%" is never eaten. A greedy
# `<[^>]+>` would swallow "< 5% and margin >" in one bite.
_HTML_TAG_RE = re.compile(r"</?[a-zA-Z][a-zA-Z0-9]*(?:\s[^<>]*)?/?>")


def sanitize_text(text: str) -> str:
    """
    Sanitize text before feeding to LLM.

    Mitigations:
    - HTML entity decoding (F-076: `&amp;` / `&#39;` reached the model verbatim)
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

    # F-076: decode HTML entities BEFORE anything else. The Alpaca connector strips
    # tags with a regex (`alpaca_news.py::_parse_article`) and leaves entities behind,
    # so up to 73.5% of scored rows reached the DK-CoT prompt carrying `&amp;`,
    # `&#39;` or `&rsquo;` (measured 2026-09-16, FORENSIC_DAILY_REPORT). That degrades
    # NER exactly on issuer names containing `&` and on possessives, and on the FinBERT
    # branch it burns the 512-character budget (5 chars per apostrophe).
    #
    # A SINGLE pass, deliberately: iterating would keep decoding text that legitimately
    # contains an entity-looking literal ("A &amp;amp; B" means "A &amp; B", not "A & B").
    text = html.unescape(text)

    # Decoding can resurrect markup: `&lt;b&gt;` becomes a live `<b>` that the upstream
    # tag strip never saw. Remove tags after unescaping, not before.
    text = _HTML_TAG_RE.sub(" ", text)

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
    return re.sub(r"[^A-Z0-9.]", "", ascii_only)
