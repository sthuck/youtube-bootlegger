"""Prompt templates for LLM tracklist extraction."""

TEMPLATE_HELP = """\
YouTube Bootlegger parses a raw track list using a template string. Each line in the \
track list must match the template. Available placeholders:
- %songname% (required): song title
- %mm% (required): minutes
- %ss% (required in the template): seconds as two digits
- %hh% (only needed if any timestamp includes an hour component): hours
- %ignore:regex% (optional): regex segment to skip, e.g. %ignore:\\d+\\.%
Default template: %songname% - %mm%:%ss%
When a template uses %hh%:%mm%:%ss%, each line may give either hh:mm or hh:mm:ss \
(seconds default to 0 if omitted), so the same template can match a mix of both \
within one track list. Never use %hh% for timestamps that are actually mm:ss - only \
use it when at least one line has a real hour component.
Examples:
- Opening Number - 0:00
- 1:23:45 - Long Song with template %hh%:%mm%:%ss% - %songname%
- [12:00] Opening Act with template [%mm%:%ss%] %songname%
- Mixed hours, template %hh%:%mm%:%ss% - %songname%:
  50:25 - Foo (50 hours, 25 minutes)
  01:05:30 - Bar (1 hour, 5 minutes, 30 seconds)"""

SYSTEM_PROMPT = (
    "You help users configure YouTube Bootlegger, a tool that splits "
    "live performance audio using timestamped track lists. "
    "Respond only with JSON matching the requested schema."
)


def build_extraction_prompt(video_title: str, raw_tracklist: str) -> str:
    """Build the user prompt sent to the LLM."""
    return (
        f"{TEMPLATE_HELP}\n\n"
        f"Video title: {video_title}\n\n"
        "Raw track list (one song per line):\n"
        f"{raw_tracklist.strip()}\n\n"
        "Analyze the raw track list and video title. Return:\n"
        "1. template - the best matching template string\n"
        "2. artist_name - performer or band name\n"
        "3. album_name - album or release title (often based on the video title)"
    )
