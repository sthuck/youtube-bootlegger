"""Unit tests for template parser."""

import pytest

from src.youtube_bootlegger.core.exceptions import ParseError
from src.youtube_bootlegger.core.template_parser import (
    DEFAULT_TEMPLATE,
    ParsePreview,
    ParsedTrack,
    TrackPreview,
    parse_line,
    parse_tracklist_with_template,
    preview_parse,
    validate_template,
)
from src.youtube_bootlegger.models import Track


class TestValidateTemplate:
    """Tests for validate_template function."""

    def test_valid_default_template(self):
        """Default template should be valid."""
        result = validate_template(DEFAULT_TEMPLATE)
        assert result.is_valid is True
        assert result.error is None

    def test_valid_template_with_hours(self):
        """Template with hours placeholder should be valid."""
        result = validate_template("%songname% - %hh%:%mm%:%ss%")
        assert result.is_valid is True

    def test_valid_template_time_first(self):
        """Template with time before song name should be valid."""
        result = validate_template("%mm%:%ss% - %songname%")
        assert result.is_valid is True

    def test_valid_template_brackets(self):
        """Template with brackets should be valid."""
        result = validate_template("[%mm%:%ss%] %songname%")
        assert result.is_valid is True

    def test_invalid_empty_template(self):
        """Empty template should be invalid."""
        result = validate_template("")
        assert result.is_valid is False
        assert "empty" in result.error.lower()

    def test_invalid_whitespace_template(self):
        """Whitespace-only template should be invalid."""
        result = validate_template("   ")
        assert result.is_valid is False

    def test_invalid_missing_songname(self):
        """Template missing songname should be invalid."""
        result = validate_template("%mm%:%ss%")
        assert result.is_valid is False
        assert "%songname%" in result.error

    def test_invalid_missing_minutes(self):
        """Template missing minutes should be invalid."""
        result = validate_template("%songname% - %ss%")
        assert result.is_valid is False
        assert "%mm%" in result.error

    def test_invalid_missing_seconds(self):
        """Template missing seconds should be invalid."""
        result = validate_template("%songname% - %mm%")
        assert result.is_valid is False
        assert "%ss%" in result.error

    def test_invalid_missing_multiple(self):
        """Template missing multiple placeholders should report all."""
        result = validate_template("%songname%")
        assert result.is_valid is False
        assert "%mm%" in result.error
        assert "%ss%" in result.error


class TestParseLine:
    """Tests for parse_line function."""

    def test_parse_default_template(self):
        """Parse line with default template."""
        result = parse_line("My Song - 3:45", DEFAULT_TEMPLATE, 1)
        assert result.name == "My Song"
        assert result.minutes == 3
        assert result.seconds == 45
        assert result.hours == 0

    def test_parse_with_hours(self):
        """Parse line with hours."""
        result = parse_line(
            "Long Song - 1:23:45",
            "%songname% - %hh%:%mm%:%ss%",
            1
        )
        assert result.name == "Long Song"
        assert result.hours == 1
        assert result.minutes == 23
        assert result.seconds == 45

    def test_parse_time_first(self):
        """Parse line with time before song name."""
        result = parse_line("5:30 - Another Track", "%mm%:%ss% - %songname%", 1)
        assert result.name == "Another Track"
        assert result.minutes == 5
        assert result.seconds == 30

    def test_parse_brackets_format(self):
        """Parse line with brackets format."""
        result = parse_line("[12:00] Opening Act", "[%mm%:%ss%] %songname%", 1)
        assert result.name == "Opening Act"
        assert result.minutes == 12
        assert result.seconds == 0

    def test_parse_zero_timestamp(self):
        """Parse line with zero timestamp."""
        result = parse_line("First Song - 0:00", DEFAULT_TEMPLATE, 1)
        assert result.name == "First Song"
        assert result.minutes == 0
        assert result.seconds == 0
        assert result.total_seconds == 0

    def test_parse_large_minutes(self):
        """Parse line with large minutes value."""
        result = parse_line("Long Performance - 120:30", DEFAULT_TEMPLATE, 1)
        assert result.name == "Long Performance"
        assert result.minutes == 120
        assert result.seconds == 30
        assert result.total_seconds == 120 * 60 + 30

    def test_parse_song_with_dash(self):
        """Parse song name containing dash."""
        result = parse_line("Artist - Song Title - 5:00", DEFAULT_TEMPLATE, 1)
        assert result.name == "Artist - Song Title"
        assert result.minutes == 5

    def test_parse_song_with_numbers(self):
        """Parse song name containing numbers."""
        result = parse_line("Track 01 - 2:30", DEFAULT_TEMPLATE, 1)
        assert result.name == "Track 01"

    def test_parse_strips_whitespace(self):
        """Whitespace should be stripped from line."""
        result = parse_line("  My Song - 1:00  ", DEFAULT_TEMPLATE, 1)
        assert result.name == "My Song"

    def test_parse_invalid_format_raises(self):
        """Invalid format should raise ParseError."""
        with pytest.raises(ParseError) as exc_info:
            parse_line("This is not valid", DEFAULT_TEMPLATE, 5)
        assert "Line 5" in str(exc_info.value)

    def test_parse_invalid_seconds_over_59(self):
        """Seconds over 59 should raise ParseError."""
        with pytest.raises(ParseError) as exc_info:
            parse_line("Bad Time - 1:75", DEFAULT_TEMPLATE, 3)
        assert "Line 3" in str(exc_info.value)
        assert "60" in str(exc_info.value)

    def test_parse_empty_songname_raises(self):
        """Empty song name should raise ParseError."""
        with pytest.raises(ParseError):
            parse_line(" - 1:00", DEFAULT_TEMPLATE, 1)

    def test_total_seconds_calculation(self):
        """Total seconds should be calculated correctly."""
        result = parse_line("Test - 1:05:30", "%songname% - %hh%:%mm%:%ss%", 1)
        expected = 1 * 3600 + 5 * 60 + 30
        assert result.total_seconds == expected


class TestParseTracklistWithTemplate:
    """Tests for parse_tracklist_with_template function."""

    def test_parse_single_track(self):
        """Parse single track."""
        text = "Only Track - 0:00"
        tracks = parse_tracklist_with_template(text, DEFAULT_TEMPLATE)
        assert len(tracks) == 1
        assert tracks[0].name == "Only Track"
        assert tracks[0].start_seconds == 0
        assert tracks[0].end_seconds is None

    def test_parse_multiple_tracks(self):
        """Parse multiple tracks with correct end times."""
        text = """First - 0:00
Second - 3:00
Third - 6:30"""
        tracks = parse_tracklist_with_template(text, DEFAULT_TEMPLATE)

        assert len(tracks) == 3

        assert tracks[0].name == "First"
        assert tracks[0].start_seconds == 0
        assert tracks[0].end_seconds == 180

        assert tracks[1].name == "Second"
        assert tracks[1].start_seconds == 180
        assert tracks[1].end_seconds == 390

        assert tracks[2].name == "Third"
        assert tracks[2].start_seconds == 390
        assert tracks[2].end_seconds is None

    def test_parse_unordered_tracks_sorts(self):
        """Tracks should be sorted by start time."""
        text = """Third - 6:00
First - 0:00
Second - 3:00"""
        tracks = parse_tracklist_with_template(text, DEFAULT_TEMPLATE)

        assert tracks[0].name == "First"
        assert tracks[1].name == "Second"
        assert tracks[2].name == "Third"

    def test_parse_with_empty_lines(self):
        """Empty lines should be ignored."""
        text = """First - 0:00

Second - 3:00

Third - 6:00"""
        tracks = parse_tracklist_with_template(text, DEFAULT_TEMPLATE)
        assert len(tracks) == 3

    def test_parse_with_custom_template(self):
        """Custom template should work."""
        text = """[0:00] Opening
[3:30] Middle
[7:00] Closing"""
        tracks = parse_tracklist_with_template(text, "[%mm%:%ss%] %songname%")

        assert len(tracks) == 3
        assert tracks[0].name == "Opening"
        assert tracks[1].name == "Middle"
        assert tracks[2].name == "Closing"

    def test_parse_empty_text_raises(self):
        """Empty text should raise ParseError."""
        with pytest.raises(ParseError) as exc_info:
            parse_tracklist_with_template("", DEFAULT_TEMPLATE)
        assert "empty" in str(exc_info.value).lower()

    def test_parse_whitespace_only_raises(self):
        """Whitespace-only text should raise ParseError."""
        with pytest.raises(ParseError):
            parse_tracklist_with_template("   \n  \n  ", DEFAULT_TEMPLATE)

    def test_parse_invalid_template_raises(self):
        """Invalid template should raise ParseError."""
        with pytest.raises(ParseError) as exc_info:
            parse_tracklist_with_template("Test - 0:00", "%songname%")
        assert "template" in str(exc_info.value).lower()

    def test_parse_all_lines_invalid_raises(self):
        """All invalid lines should raise ParseError with all errors."""
        text = """not valid
also not valid
nope"""
        with pytest.raises(ParseError) as exc_info:
            parse_tracklist_with_template(text, DEFAULT_TEMPLATE)
        error = str(exc_info.value)
        assert "Line 1" in error
        assert "Line 2" in error
        assert "Line 3" in error

    def test_returns_track_objects(self):
        """Should return Track objects."""
        text = "Test - 0:00"
        tracks = parse_tracklist_with_template(text, DEFAULT_TEMPLATE)
        assert isinstance(tracks[0], Track)


class TestPreviewParse:
    """Tests for preview_parse function."""

    def test_preview_empty_text(self):
        """Preview of empty text should be valid with no tracks."""
        result = preview_parse("", DEFAULT_TEMPLATE)
        assert result.is_valid is True
        assert result.total_lines == 0
        assert result.error_count == 0
        assert len(result.tracks) == 0

    def test_preview_valid_tracks(self):
        """Preview valid tracks."""
        text = """First - 0:00
Second - 3:00"""
        result = preview_parse(text, DEFAULT_TEMPLATE)

        assert result.is_valid is True
        assert result.total_lines == 2
        assert result.error_count == 0
        assert len(result.tracks) == 2

        assert result.tracks[0].name == "First"
        assert result.tracks[0].timestamp == "0:00"
        assert result.tracks[0].is_valid is True

        assert result.tracks[1].name == "Second"
        assert result.tracks[1].timestamp == "3:00"
        assert result.tracks[1].is_valid is True

    def test_preview_invalid_tracks(self):
        """Preview with invalid tracks should show errors."""
        text = """Valid - 0:00
not valid
Also Valid - 5:00"""
        result = preview_parse(text, DEFAULT_TEMPLATE)

        assert result.is_valid is False
        assert result.total_lines == 3
        assert result.error_count == 1

        assert result.tracks[0].is_valid is True
        assert result.tracks[1].is_valid is False
        assert result.tracks[1].error is not None
        assert result.tracks[2].is_valid is True

    def test_preview_invalid_template(self):
        """Preview with invalid template should fail."""
        result = preview_parse("Test - 0:00", "%songname%")
        assert result.is_valid is False
        assert result.error_count == 1

    def test_preview_tracks_are_track_preview(self):
        """Preview tracks should be TrackPreview objects."""
        text = "Test - 0:00"
        result = preview_parse(text, DEFAULT_TEMPLATE)
        assert isinstance(result.tracks[0], TrackPreview)

    def test_preview_with_hours_format(self):
        """Preview should format hours correctly."""
        text = "Long - 1:30:45"
        result = preview_parse(text, "%songname% - %hh%:%mm%:%ss%")
        assert result.tracks[0].timestamp == "1:30:45"

    def test_preview_result_is_parse_preview(self):
        """Result should be ParsePreview object."""
        result = preview_parse("Test - 0:00", DEFAULT_TEMPLATE)
        assert isinstance(result, ParsePreview)


class TestTemplateVariations:
    """Tests for various template formats."""

    @pytest.mark.parametrize("template,line,expected_name,expected_seconds", [
        ("%songname% - %mm%:%ss%", "Test - 1:30", "Test", 90),
        ("%mm%:%ss% %songname%", "1:30 Test", "Test", 90),
        ("[%mm%:%ss%] %songname%", "[1:30] Test", "Test", 90),
        ("(%mm%:%ss%) %songname%", "(1:30) Test", "Test", 90),
        ("%songname% (%mm%:%ss%)", "Test (1:30)", "Test", 90),
        ("%songname%|%mm%:%ss%", "Test|1:30", "Test", 90),
        ("%mm%:%ss%-%songname%", "1:30-Test", "Test", 90),
    ])
    def test_various_templates(self, template, line, expected_name, expected_seconds):
        """Test various template formats."""
        result = parse_line(line, template, 1)
        assert result.name == expected_name
        assert result.total_seconds == expected_seconds

    def test_template_with_all_placeholders(self):
        """Template with all placeholders should work."""
        template = "%hh%:%mm%:%ss% - %songname%"
        result = parse_line("1:30:45 - Full Format", template, 1)
        assert result.hours == 1
        assert result.minutes == 30
        assert result.seconds == 45
        assert result.name == "Full Format"
        assert result.total_seconds == 3600 + 1800 + 45


class TestEdgeCases:
    """Tests for edge cases."""

    def test_song_name_with_special_characters(self):
        """Song names with special characters should work."""
        text = "Rock & Roll (Live!) [2024] - 0:00"
        tracks = parse_tracklist_with_template(text, DEFAULT_TEMPLATE)
        assert tracks[0].name == "Rock & Roll (Live!) [2024]"

    def test_song_name_with_unicode(self):
        """Song names with unicode should work."""
        text = "日本語の曲 - 0:00"
        tracks = parse_tracklist_with_template(text, DEFAULT_TEMPLATE)
        assert tracks[0].name == "日本語の曲"

    def test_very_long_song_name(self):
        """Very long song names should work."""
        long_name = "A" * 200
        text = f"{long_name} - 0:00"
        tracks = parse_tracklist_with_template(text, DEFAULT_TEMPLATE)
        assert tracks[0].name == long_name

    def test_single_digit_minutes(self):
        """Single digit minutes should work."""
        result = parse_line("Test - 5:30", DEFAULT_TEMPLATE, 1)
        assert result.minutes == 5

    def test_double_digit_minutes(self):
        """Double digit minutes should work."""
        result = parse_line("Test - 45:30", DEFAULT_TEMPLATE, 1)
        assert result.minutes == 45

    def test_zero_padded_minutes(self):
        """Zero-padded minutes should work."""
        result = parse_line("Test - 05:30", DEFAULT_TEMPLATE, 1)
        assert result.minutes == 5

    def test_seconds_must_be_two_digits(self):
        """Seconds must be two digits."""
        with pytest.raises(ParseError):
            parse_line("Test - 1:5", DEFAULT_TEMPLATE, 1)

    def test_many_tracks(self):
        """Many tracks should be handled."""
        lines = [f"Track {i} - {i}:00" for i in range(100)]
        text = "\n".join(lines)
        tracks = parse_tracklist_with_template(text, DEFAULT_TEMPLATE)
        assert len(tracks) == 100


class TestIgnorePlaceholder:
    """Tests for %ignore:regex% placeholder."""

    def test_ignore_simple_number(self):
        """Ignore a simple number prefix."""
        template = r"%ignore:\d+\.% %songname% - %mm%:%ss%"
        result = parse_line("1. My Song - 3:45", template, 1)
        assert result.name == "My Song"
        assert result.minutes == 3
        assert result.seconds == 45

    def test_ignore_double_digit_number(self):
        """Ignore double digit number prefix."""
        template = r"%ignore:\d+\.% %songname% - %mm%:%ss%"
        result = parse_line("10. Another Song - 5:30", template, 1)
        assert result.name == "Another Song"
        assert result.minutes == 5

    def test_ignore_bracket_number(self):
        """Ignore bracketed number prefix."""
        template = r"%ignore:\[\d+\]% %songname% - %mm%:%ss%"
        result = parse_line("[5] Cool Track - 2:15", template, 1)
        assert result.name == "Cool Track"

    def test_ignore_at_end(self):
        """Ignore pattern at end of line."""
        template = r"%songname% - %mm%:%ss%%ignore:\s*#\d+%"
        result = parse_line("Test Song - 1:30 #42", template, 1)
        assert result.name == "Test Song"

    def test_multiple_ignore_patterns(self):
        """Multiple ignore patterns in template."""
        template = r"%ignore:\d+\.% %songname% - %mm%:%ss%%ignore:\s*\[.*\]%"
        result = parse_line("3. Great Song - 4:00 [live]", template, 1)
        assert result.name == "Great Song"
        assert result.minutes == 4

    def test_ignore_with_hours(self):
        """Ignore pattern with hours template."""
        template = r"%ignore:\d+\.% %songname% - %hh%:%mm%:%ss%"
        result = parse_line("7. Long Track - 1:23:45", template, 1)
        assert result.name == "Long Track"
        assert result.hours == 1
        assert result.minutes == 23
        assert result.seconds == 45

    def test_validate_template_with_valid_ignore(self):
        """Template with valid ignore pattern should validate."""
        template = r"%ignore:\d+\.% %songname% - %mm%:%ss%"
        result = validate_template(template)
        assert result.is_valid is True

    def test_validate_template_with_invalid_ignore_regex(self):
        """Template with invalid ignore regex should fail validation."""
        template = r"%ignore:[unclosed% %songname% - %mm%:%ss%"
        result = validate_template(template)
        assert result.is_valid is False
        assert "regex" in result.error.lower() or "invalid" in result.error.lower()

    def test_ignore_empty_match(self):
        """Ignore pattern that matches empty string."""
        template = r"%ignore:\d*%%songname% - %mm%:%ss%"
        # Should work with no number prefix (since \d* matches empty)
        result = parse_line("Test - 1:00", template, 1)
        assert result.name == "Test"
        # Also works with number prefix
        result2 = parse_line("5Test - 2:00", template, 1)
        assert result2.name == "Test"

    def test_parse_tracklist_with_ignore(self):
        """Parse full tracklist with ignore pattern."""
        template = r"%ignore:\d+\.\s*% %songname% - %mm%:%ss%"
        text = """1. First Song - 0:00
2. Second Song - 3:30
3. Third Song - 7:15"""
        tracks = parse_tracklist_with_template(text, template)
        assert len(tracks) == 3
        assert tracks[0].name == "First Song"
        assert tracks[1].name == "Second Song"
        assert tracks[2].name == "Third Song"

    def test_preview_with_ignore(self):
        """Preview parsing with ignore pattern."""
        template = r"%ignore:\d+\.% %songname% - %mm%:%ss%"
        text = "1. My Track - 2:30"
        result = preview_parse(text, template)
        assert result.is_valid is True
        assert result.tracks[0].name == "My Track"

    def test_ignore_optional_pattern(self):
        """Ignore pattern with optional component."""
        template = r"%ignore:(?:\d+\.\s*)?%%songname% - %mm%:%ss%"
        # With number prefix
        result1 = parse_line("5. Song A - 1:00", template, 1)
        assert result1.name == "Song A"
        # Without number prefix
        result2 = parse_line("Song B - 2:00", template, 1)
        assert result2.name == "Song B"

    def test_ignore_word_pattern(self):
        """Ignore a word pattern."""
        template = r"%ignore:Track\s*%%songname% - %mm%:%ss%"
        result = parse_line("Track My Song - 3:00", template, 1)
        assert result.name == "My Song"

    def test_ignore_preserves_special_chars_in_template(self):
        """Template literal characters should still be escaped."""
        template = r"%ignore:\d+\.% [%songname%] - %mm%:%ss%"
        result = parse_line("1. [Cool Track] - 1:30", template, 1)
        assert result.name == "Cool Track"

    def test_multiple_ignore_different_positions(self):
        """Multiple ignore patterns in different positions."""
        template = r"%ignore:>>% %mm%:%ss% %songname%%ignore:<<\s*%"
        result = parse_line(">> 4:30 My Song<<  ", template, 1)
        assert result.name == "My Song"
        assert result.minutes == 4
        assert result.seconds == 30
