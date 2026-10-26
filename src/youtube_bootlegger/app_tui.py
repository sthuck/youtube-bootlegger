"""TUI application entry point."""

# Terminal graphics detection (Kitty/Sixel/Unicode fallback) queries the
# terminal, so it must happen before Textual takes over stdin/stdout.
import textual_image.renderable  # noqa: F401

from .tui import BootleggerApp


def run() -> int:
    """Launch the terminal UI."""
    BootleggerApp().run()
    return 0
