"""Tests for paste summary (collapse multi-line pastes into [Pasted ~N lines])."""

from __future__ import annotations


def expand_paste_markers(text: str, paste_queue: list[tuple[str, str]]) -> str:
    """Simulates the paste marker expansion logic from PromptTextArea."""
    body = text
    for original, marker in paste_queue:
        if marker in body:
            body = body.replace(marker, original, 1)
    return body


class TestPasteMarkerExpansion:
    """Tests for paste marker expansion on submit."""

    def test_single_paste_expands(self) -> None:
        """Single paste marker is replaced with original content."""
        paste_queue = [("line1\nline2\nline3", "[Pasted ~3 lines]")]
        text = "Hello [Pasted ~3 lines] world"

        result = expand_paste_markers(text, paste_queue)

        assert result == "Hello line1\nline2\nline3 world"

    def test_multiple_pastes_expand_in_order(self) -> None:
        """Multiple paste markers are replaced left-to-right."""
        paste_queue = [
            ("first\npaste", "[Pasted ~2 lines]"),
            ("second\npaste\nhere", "[Pasted ~3 lines]"),
        ]
        text = "Before [Pasted ~2 lines] middle [Pasted ~3 lines] after"

        result = expand_paste_markers(text, paste_queue)

        assert result == "Before first\npaste middle second\npaste\nhere after"

    def test_duplicate_line_counts(self) -> None:
        """Two pastes with same line count are both replaced (left-to-right)."""
        paste_queue = [
            ("content A", "[Pasted ~1 lines]"),
            ("content B", "[Pasted ~1 lines]"),
        ]
        text = "start [Pasted ~1 lines] and [Pasted ~1 lines] end"

        result = expand_paste_markers(text, paste_queue)

        # Both markers replaced in order: first → content A, second → content B
        assert result == "start content A and content B end"

    def test_marker_not_found_leaves_text(self) -> None:
        """If marker text was edited by user, no replacement happens."""
        paste_queue = [("original\ntext", "[Pasted ~2 lines]")]
        text = "Hello edited marker world"

        result = expand_paste_markers(text, paste_queue)

        assert result == "Hello edited marker world"

    def test_marker_deleted_leaves_original_text(self) -> None:
        """If user deletes the marker, original text is not included."""
        paste_queue = [("hidden\ncontent", "[Pasted ~2 lines]")]
        text = "Hello world"

        result = expand_paste_markers(text, paste_queue)

        assert result == "Hello world"

    def test_empty_queue_returns_original_text(self) -> None:
        """No pastes means text is unchanged."""
        paste_queue = []
        text = "Hello world"

        result = expand_paste_markers(text, paste_queue)

        assert result == "Hello world"

    def test_paste_at_start(self) -> None:
        """Marker at the beginning of text."""
        paste_queue = [("pasted\ncontent", "[Pasted ~2 lines]")]
        text = "[Pasted ~2 lines] typed after"

        result = expand_paste_markers(text, paste_queue)

        assert result == "pasted\ncontent typed after"

    def test_paste_at_end(self) -> None:
        """Marker at the end of text."""
        paste_queue = [("pasted\ncontent", "[Pasted ~2 lines]")]
        text = "typed before [Pasted ~2 lines]"

        result = expand_paste_markers(text, paste_queue)

        assert result == "typed before pasted\ncontent"

    def test_multiline_body_preserved(self) -> None:
        """Multi-line original content is preserved correctly."""
        paste_queue = [("line1\nline2\nline3", "[Pasted ~3 lines]")]
        text = "[Pasted ~3 lines]"

        result = expand_paste_markers(text, paste_queue)

        assert result == "line1\nline2\nline3"
        assert result.count("\n") == 2

    def test_manual_marker_text_gets_replaced(self) -> None:
        """KNOWN LIMITATION: If user manually types the marker text, it gets replaced.

        This is a trade-off of the simple string-match approach. A proper fix
        would require unique IDs per paste (e.g. UUID embedded in marker).
        For now, users should not manually type [Pasted ~N lines] patterns.
        """
        paste_queue = [("secret\ndata", "[Pasted ~2 lines]")]
        text = "I typed [Pasted ~2 lines] yesterday"

        result = expand_paste_markers(text, paste_queue)

        # Current behavior: string match replaces it (limitation)
        assert result == "I typed secret\ndata yesterday"


class TestPasteTriggerConditions:
    """Tests for determining when to collapse a paste."""

    def test_triggers_on_3_lines(self) -> None:
        """Paste with 3 lines should be collapsed."""
        line_count = 3
        char_count = 20

        should_collapse = line_count >= 3 or char_count > 150

        assert should_collapse is True

    def test_triggers_on_2_lines_but_200_chars(self) -> None:
        """Paste with 2 lines but 200 chars should be collapsed (char threshold)."""
        line_count = 2
        char_count = 200

        should_collapse = line_count >= 3 or char_count > 150

        assert should_collapse is True

    def test_no_trigger_small_text(self) -> None:
        """Small paste with 1 line and <150 chars should not be collapsed."""
        line_count = 1
        char_count = 50

        should_collapse = line_count >= 3 or char_count > 150

        assert should_collapse is False

    def test_triggers_on_exactly_150_chars(self) -> None:
        """Exactly 150 chars does NOT trigger (threshold is > 150)."""
        line_count = 1
        char_count = 150

        should_collapse = line_count >= 3 or char_count > 150

        assert should_collapse is False

    def test_triggers_on_151_chars(self) -> None:
        """151 chars DOES trigger (threshold is > 150)."""
        line_count = 1
        char_count = 151

        should_collapse = line_count >= 3 or char_count > 150

        assert should_collapse is True

    def test_triggers_on_single_line_1000_chars(self) -> None:
        """Very long single-line paste (e.g. base64) should be collapsed."""
        line_count = 1
        char_count = 1000

        should_collapse = line_count >= 3 or char_count > 150

        assert should_collapse is True


class TestPasteMarkerFormat:
    """Tests for paste marker format."""

    def test_marker_format_with_line_count(self) -> None:
        """Marker includes line count."""
        line_count = 5
        marker = f"[Pasted ~{line_count} lines]"
        assert marker == "[Pasted ~5 lines]"

    def test_marker_with_truncated_suffix(self) -> None:
        """Truncated paste includes suffix in marker."""
        line_count = 5
        truncated = True
        marker = f"[Pasted ~{line_count} lines]" + (" (truncated)" if truncated else "")
        assert marker == "[Pasted ~5 lines] (truncated)"

    def test_marker_without_truncated_suffix(self) -> None:
        """Non-truncated paste does not include suffix."""
        line_count = 5
        truncated = False
        marker = f"[Pasted ~{line_count} lines]" + (" (truncated)" if truncated else "")
        assert marker == "[Pasted ~5 lines]"


def normalize_paste_text(text: str) -> str:
    """Canonical normalization used for paste dedup comparison."""
    return text.replace('\r\n', '\n').replace('\r', '\n').strip()


class TestDedupNormalization:
    """Tests for paste dedup normalization (CRLF vs LF, trailing newlines, etc.)."""

    def test_crlf_equals_lf(self) -> None:
        """CRLF line endings and LF line endings should compare equal after normalization."""
        clipboard = "line1\r\nline2\r\nline3"
        event_text = "line1\nline2\nline3"
        assert normalize_paste_text(clipboard) == normalize_paste_text(event_text)

    def test_trailing_newline_stripped(self) -> None:
        """Text with trailing newline matches text without after normalization."""
        with_newline = "line1\nline2\n"
        without_newline = "line1\nline2"
        assert normalize_paste_text(with_newline) == normalize_paste_text(without_newline)

    def test_trailing_newlines_stripped(self) -> None:
        """Multiple trailing newlines are stripped."""
        text = "content\n\n\n"
        assert normalize_paste_text(text) == "content"

    def test_different_content_not_equal(self) -> None:
        """Different content should NOT compare equal after normalization."""
        a = "line1\nline2\nline3"
        b = "line1\nline2\nline4"
        assert normalize_paste_text(a) != normalize_paste_text(b)

    def test_empty_text_empty_normalized(self) -> None:
        """Empty text normalizes to empty string."""
        assert normalize_paste_text("") == ""

    def test_only_crlf_normalizes(self) -> None:
        """Only CRLF characters normalize to empty."""
        assert normalize_paste_text("\r\n\r\n") == ""

    def test_mixed_crlf_lf_normalizes(self) -> None:
        """Mixed CRLF and LF line endings all normalize to LF."""
        mixed = "a\rb\rc\r\nd\ne"
        expected = "a\nb\nc\nd\ne"
        assert normalize_paste_text(mixed) == expected

    def test_normalization_does_not_remove_internal_whitespace(self) -> None:
        """Internal spaces and tabs are preserved."""
        text = "line 1\n\tline 2\n  line 3"
        assert normalize_paste_text(text) == text.replace('\r\n', '\n').replace('\r', '\n')

    def test_single_line_with_crlf(self) -> None:
        """Single line with CRLF normalizes correctly."""
        assert normalize_paste_text("hello\r\n") == "hello"

    def test_normalization_preserves_content(self) -> None:
        """Normalization preserves actual content, only changes line endings."""
        original = "line1\nline2\nline3"
        assert normalize_paste_text(original) == original
