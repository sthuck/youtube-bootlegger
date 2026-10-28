"""Inspect track-list sources without downloading audio or calling AI.

Run: uv run python scripts/probe_video_track_sources.py URL --comments 20
Use --external yt-dlp to inspect an external executable instead of the library.
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
from youtube_bootlegger.core.video_info import DEFAULT_COMMENT_LIMIT, fetch_video_info


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url")
    parser.add_argument("--comments", type=int, default=DEFAULT_COMMENT_LIMIT,
                        help="Maximum top-level comments; 0 skips comment fetching")
    parser.add_argument("--external", metavar="EXECUTABLE")
    args = parser.parse_args()
    if args.comments < 0:
        parser.error("--comments must be nonnegative")

    # Select the yt-dlp mode from the command line without touching saved settings.
    class ProbeSettings:
        use_external_ytdlp = args.external is not None

        def resolved_ytdlp_command(self):
            return args.external

    try:
        info = fetch_video_info(args.url, ProbeSettings(), comment_limit=args.comments)
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
