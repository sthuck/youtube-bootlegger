"""YouTube Bootlegger entry point – terminal UI."""

import sys


def main() -> int:
    """Run the YouTube Bootlegger application with the terminal UI."""
    from src.youtube_bootlegger.app_tui import run

    return run()


if __name__ == "__main__":
    sys.exit(main())
