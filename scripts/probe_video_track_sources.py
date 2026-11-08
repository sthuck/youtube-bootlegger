"""Inspect track-list sources without downloading audio or calling AI.

Run: uv run python scripts/probe_video_track_sources.py URL --comments 20
Runs the downloaded yt-dlp (or yt-dlp on PATH); --ytdlp picks another executable.
Prints the description, chapters and comments as JSON.
"""

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

# Support running the script from a checkout without an editable installation.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from youtube_bootlegger.core.exceptions import ValidationError
from youtube_bootlegger.core.settings import AppSettings
from youtube_bootlegger.core.tools import default_tools_dir
from youtube_bootlegger.core.video_info import DEFAULT_COMMENT_LIMIT, fetch_video_info


class _MemoryBackend(dict):
    def value(self, key, default=None):
        return self.get(key, default)

    def setValue(self, key, value):
        self[key] = value

    def sync(self):
        pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url")
    parser.add_argument("--comments", type=int, default=DEFAULT_COMMENT_LIMIT,
                        help="Maximum top-level comments; 0 skips comment fetching")
    parser.add_argument("--ytdlp", metavar="EXECUTABLE", default="")
    args = parser.parse_args()
    if args.comments < 0:
        parser.error("--comments must be nonnegative")

    # In-memory settings, so the probe never reads or changes saved settings.
    settings = AppSettings(_MemoryBackend(), tools_dir=default_tools_dir())
    settings.ytdlp_path = args.ytdlp

    try:
        info = fetch_video_info(args.url, settings, comment_limit=args.comments)
    except ValidationError as exc:
        parser.exit(1, f"Could not inspect video: {exc}\n")
    print(json.dumps({
        "video_id": info.video_id,
        "title": info.title,
        "description": info.description,
        "chapters": [asdict(chapter) for chapter in info.chapters],
        "comments": [asdict(comment) for comment in info.comments],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
