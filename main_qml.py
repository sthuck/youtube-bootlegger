"""YouTube Bootlegger entry point – QML UI."""

import sys


def main() -> int:
    """Run the YouTube Bootlegger application with the QML UI."""
    from src.youtube_bootlegger.app_qml import run

    return run()


if __name__ == "__main__":
    sys.exit(main())
