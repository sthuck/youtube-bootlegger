"""YouTube Bootlegger entry point."""

import sys


def main() -> int:
    """Run the YouTube Bootlegger application."""
    from src.youtube_bootlegger.app import run

    return run()


if __name__ == "__main__":
    sys.exit(main())
