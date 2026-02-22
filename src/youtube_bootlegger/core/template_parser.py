"""Template-based tracklist parsing.

Supports templates like:
- %songname% - %mm%:%ss%
- %hh%:%mm%:%ss% - %songname%
- [%mm%:%ss%] %songname%
- %ignore:\\d+\\.% %songname% - %mm%:%ss%

Placeholders:
- %songname% - The song name (required)
- %hh% - Hours (optional, 0 if not present)
- %mm% - Minutes (required)
- %ss% - Seconds (required)
- %ignore:regex% - Match and ignore pattern (can use multiple)
"""

import re
from dataclasses import dataclass

from ..models import Track
from .exceptions import ParseError

DEFAULT_TEMPLATE = "%songname% - %mm%:%ss%"

PLACEHOLDER_PATTERNS = {
    "%songname%": r"(?P<songname>.+?)",
    "%hh%": r"(?P<hh>\d{1,2})",
    "%mm%": r"(?P<mm>\d{1,3})",  # Support up to 999 minutes for long recordings
    "%ss%": r"(?P<ss>\d{2})",
}

REQUIRED_PLACEHOLDERS = {"%songname%", "%mm%", "%ss%"}

# Pattern to match %ignore:...% placeholders in templates
IGNORE_PATTERN = re.compile(r"%ignore:(.+?)%")


@dataclass(frozen=True)
class ParsedTrack:
    """Result of parsing a single line."""

    name: str
    hours: int
    minutes: int
    seconds: int
    line_number: int

    @property
    def total_seconds(self) -> float:
        """Calculate total seconds from time components."""
        return self.hours * 3600 + self.minutes * 60 + self.seconds


@dataclass(frozen=True)
class TemplateValidation:
    """Result of template validation."""

    is_valid: bool
    error: str | None = None
    missing_placeholders: tuple[str, ...] = ()


def validate_template(template: str) -> TemplateValidation:
    """Validate a template string.

    Args:
        template: The template string to validate.

    Returns:
        TemplateValidation with validation result.
    """
    if not template or not template.strip():
        return TemplateValidation(
            is_valid=False,
            error="Template cannot be empty",
        )

    found_placeholders = set()
    for placeholder in PLACEHOLDER_PATTERNS:
        if placeholder in template:
            found_placeholders.add(placeholder)

    missing = REQUIRED_PLACEHOLDERS - found_placeholders
    if missing:
        return TemplateValidation(
            is_valid=False,
            error=f"Missing required placeholders: {', '.join(sorted(missing))}",
            missing_placeholders=tuple(sorted(missing)),
        )

    # Validate ignore patterns have valid regex
    for match in IGNORE_PATTERN.finditer(template):
        ignore_regex = match.group(1)
        try:
            re.compile(ignore_regex)
        except re.error as e:
            return TemplateValidation(
                is_valid=False,
                error=f"Invalid regex in %ignore:{ignore_regex}%: {e}",
            )

    try:
        _compile_template(template)
    except re.error as e:
        return TemplateValidation(
            is_valid=False,
            error=f"Invalid template pattern: {e}",
        )

    return TemplateValidation(is_valid=True)


def _compile_template(template: str) -> re.Pattern:
    """Compile a template string into a regex pattern.

    Args:
        template: The template string.

    Returns:
        Compiled regex pattern.
    """
    # First, extract and replace ignore patterns before escaping
    # We need to handle them specially since they contain user regex
    ignore_replacements: list[tuple[str, str]] = []
    for match in IGNORE_PATTERN.finditer(template):
        full_match = match.group(0)  # e.g., %ignore:\d+\.%
        ignore_regex = match.group(1)  # e.g., \d+\.
        # Create non-capturing group for the ignore pattern
        replacement = f"(?:{ignore_regex})"
        ignore_replacements.append((full_match, replacement))

    # Escape the template for regex
    pattern = re.escape(template)

    # Replace standard placeholders
    for placeholder, regex in PLACEHOLDER_PATTERNS.items():
        escaped_placeholder = re.escape(placeholder)
        pattern = pattern.replace(escaped_placeholder, regex)

    # Replace ignore patterns (need to escape the original to find it in escaped pattern)
    for original, replacement in ignore_replacements:
        escaped_original = re.escape(original)
        pattern = pattern.replace(escaped_original, replacement)

    return re.compile(f"^{pattern}$")


def parse_line(line: str, template: str, line_number: int) -> ParsedTrack:
    """Parse a single line using the template.

    Args:
        line: The input line to parse.
        template: The template string.
        line_number: Line number for error reporting.

    Returns:
        ParsedTrack with extracted data.

    Raises:
        ParseError: If the line doesn't match the template.
    """
    pattern = _compile_template(template)
    match = pattern.match(line.strip())

    if not match:
        raise ParseError(
            f"Line {line_number}: Does not match template format"
        )

    groups = match.groupdict()

    songname = groups.get("songname", "").strip()
    if not songname:
        raise ParseError(f"Line {line_number}: Song name is empty")

    try:
        hours = int(groups.get("hh", 0) or 0)
        minutes = int(groups["mm"])
        seconds = int(groups["ss"])
    except (ValueError, KeyError) as e:
        raise ParseError(f"Line {line_number}: Invalid time format") from e

    if seconds >= 60:
        raise ParseError(
            f"Line {line_number}: Seconds must be less than 60 (got {seconds})"
        )

    if minutes >= 60 and "%hh%" not in template:
        pass

    return ParsedTrack(
        name=songname,
        hours=hours,
        minutes=minutes,
        seconds=seconds,
        line_number=line_number,
    )


def parse_tracklist_with_template(
    text: str,
    template: str = DEFAULT_TEMPLATE,
) -> list[Track]:
    """Parse tracklist text using a template.

    Args:
        text: The tracklist text to parse.
        template: The template string.

    Returns:
        List of Track objects with calculated end times.

    Raises:
        ParseError: If parsing fails.
    """
    validation = validate_template(template)
    if not validation.is_valid:
        raise ParseError(f"Invalid template: {validation.error}")

    if not text or not text.strip():
        raise ParseError("Tracklist is empty")

    lines = text.strip().split("\n")
    parsed_tracks: list[ParsedTrack] = []
    errors: list[str] = []

    for i, line in enumerate(lines, 1):
        line = line.strip()
        if not line:
            continue

        try:
            parsed = parse_line(line, template, i)
            parsed_tracks.append(parsed)
        except ParseError as e:
            errors.append(str(e))

    if errors:
        raise ParseError("\n".join(errors))

    if not parsed_tracks:
        raise ParseError("No valid tracks found in tracklist")

    parsed_tracks.sort(key=lambda t: t.total_seconds)

    tracks: list[Track] = []
    for i, parsed in enumerate(parsed_tracks):
        start_seconds = parsed.total_seconds

        if i < len(parsed_tracks) - 1:
            end_seconds = parsed_tracks[i + 1].total_seconds
        else:
            end_seconds = None

        tracks.append(Track(
            name=parsed.name,
            start_seconds=start_seconds,
            end_seconds=end_seconds,
        ))

    return tracks


@dataclass(frozen=True)
class TrackPreview:
    """Preview of a parsed track for display."""

    line_number: int
    name: str
    timestamp: str
    is_valid: bool
    error: str | None = None


@dataclass(frozen=True)
class ParsePreview:
    """Preview of parsing results."""

    tracks: tuple[TrackPreview, ...]
    is_valid: bool
    error_count: int
    total_lines: int


def preview_parse(text: str, template: str = DEFAULT_TEMPLATE) -> ParsePreview:
    """Generate a preview of parsing without raising errors.

    Args:
        text: The tracklist text to preview.
        template: The template string.

    Returns:
        ParsePreview with track previews and validation status.
    """
    validation = validate_template(template)
    if not validation.is_valid:
        return ParsePreview(
            tracks=(),
            is_valid=False,
            error_count=1,
            total_lines=0,
        )

    if not text or not text.strip():
        return ParsePreview(
            tracks=(),
            is_valid=True,
            error_count=0,
            total_lines=0,
        )

    lines = text.strip().split("\n")
    previews: list[TrackPreview] = []
    error_count = 0
    valid_line_count = 0

    for i, line in enumerate(lines, 1):
        line = line.strip()
        if not line:
            continue

        valid_line_count += 1

        try:
            parsed = parse_line(line, template, i)
            if parsed.hours > 0:
                timestamp = f"{parsed.hours}:{parsed.minutes:02d}:{parsed.seconds:02d}"
            else:
                timestamp = f"{parsed.minutes}:{parsed.seconds:02d}"

            previews.append(TrackPreview(
                line_number=i,
                name=parsed.name,
                timestamp=timestamp,
                is_valid=True,
            ))
        except ParseError as e:
            error_count += 1
            previews.append(TrackPreview(
                line_number=i,
                name=line[:30] + "..." if len(line) > 30 else line,
                timestamp="--:--",
                is_valid=False,
                error=str(e),
            ))

    return ParsePreview(
        tracks=tuple(previews),
        is_valid=error_count == 0 and valid_line_count > 0,
        error_count=error_count,
        total_lines=valid_line_count,
    )
