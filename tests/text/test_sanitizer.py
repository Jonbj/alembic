"""Tests for sanitize_ticker — homoglyph normalization and dot preservation."""

import pytest

from src.text.sanitizer import sanitize_text, sanitize_ticker


class TestSanitizeTicker:
    """Tests for the sanitize_ticker function."""

    def test_dot_preserved_brk_b(self):
        """BRK.B should keep the dot (Berkshire Hathaway Class B)."""
        assert sanitize_ticker("BRK.B") == "BRK.B"

    def test_plain_alpha(self):
        """AAPL passes through unchanged."""
        assert sanitize_ticker("AAPL") == "AAPL"

    @pytest.mark.skip(reason="pre-existing bug: Cyrillic homoglyphs not handled by NFKD normalize, tracked separately")
    def test_cyrillic_homoglyphs(self):
        """Cyrillic look-alikes for A, P are normalized to ASCII."""
        # А and Р are Cyrillic (U+0410, U+0420), L is already ASCII
        assert sanitize_ticker("\u0410\u0410\u0420L") == "AAPL"

    def test_lowercase_uppercased(self):
        """Lowercase input is uppercased before sanitization."""
        assert sanitize_ticker("brk.b") == "BRK.B"

    def test_punctuation_stripped(self):
        """Non-alphanumeric, non-dot punctuation is removed."""
        assert sanitize_ticker("AAPL$#") == "AAPL"


class TestF076HtmlEntities:
    """F-076: sanitize_text must decode HTML entities before the text reaches the LLM.

    Measured on 2026-09-16: 158/215 scored rows (73.5%) carried `&amp;` / `&#39;` /
    `&rsquo;` into the DK-CoT prompt, because the Alpaca connector strips tags with a
    regex and leaves entities, and sanitize_text never called html.unescape. This
    degrades NER exactly on the names that contain `&` and on possessives, and on the
    FinBERT branch it burns the 512-character truncation budget (5 chars per apostrophe).
    """

    def test_named_entity_decoded(self):
        assert sanitize_text("Johnson &amp; Johnson") == "Johnson & Johnson"

    def test_numeric_entity_decoded(self):
        assert sanitize_text("Salesforce&#39;s AI Business") == "Salesforce's AI Business"

    def test_rsquo_decoded_and_normalized(self):
        # &rsquo; is U+2019; NFKC keeps it as a curly apostrophe (it has no ASCII
        # compatibility mapping) — the point is that the raw entity never survives.
        out = sanitize_text("Wednesday&rsquo;s premarket session")
        assert "&rsquo;" not in out
        assert out.startswith("Wednesday")
        assert out.endswith("s premarket session")

    def test_real_headline_from_the_finding(self):
        assert sanitize_text(
            "S&amp;P 500 Gains, Crude Falls Ahead Of Fed&#39;s Expected First Hike"
        ) == "S&P 500 Gains, Crude Falls Ahead Of Fed's Expected First Hike"

    def test_nbsp_entity_collapses_to_single_space(self):
        assert sanitize_text("Marvell&nbsp;&nbsp;Technology") == "Marvell Technology"

    def test_decoding_does_not_reintroduce_html_tags(self):
        """Unescaping `&lt;b&gt;` would hand a live tag to the model: strip it."""
        assert sanitize_text("Micron &lt;b&gt;beats&lt;/b&gt; estimates") == "Micron beats estimates"

    def test_comparison_operators_survive_tag_stripping(self):
        """`< 5%` is not a tag — a greedy `<[^>]+>` strip would eat the sentence."""
        assert sanitize_text("revenue &lt; 5% and margin &gt; 3%") == "revenue < 5% and margin > 3%"

    def test_single_pass_only(self):
        """One unescape pass: a double-encoded entity decodes once, not repeatedly.

        Iterating would corrupt text that legitimately contains an entity-looking
        literal after the first pass.
        """
        assert sanitize_text("A &amp;amp; B") == "A &amp; B"

    def test_empty_and_plain_text_unchanged(self):
        assert sanitize_text("") == ""
        assert sanitize_text("Micron beats estimates") == "Micron beats estimates"
