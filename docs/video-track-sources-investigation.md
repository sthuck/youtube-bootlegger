# Video track-source discovery

Investigated 2026-10-27, starting at `1b3cbed`, using installed yt-dlp
`2026.10.26`; rebased onto `qml-e2e-tests` (`df9a30e`) on 2026-10-28.
This branch contains an investigation, shared fetching functions
and a metadata-only probe; the application UI and AI behavior are not changed.

## Implemented fetching API

`core/video_sources.py` provides:

```python
from youtube_bootlegger.core.video_sources import fetch_video_sources

sources = fetch_video_sources(url, settings, comment_limit=20)
sources.description  # str
sources.chapters     # tuple[VideoChapter]: title, start_seconds, end_seconds
sources.comments     # tuple[VideoComment]: comment_id, text, in YouTube Top order
```

Settings default to the shared application settings. The function dispatches to
the bundled Python library or `settings.resolved_ytdlp_command()` according to
`use_external_ytdlp`. `comment_limit=0` skips comment retrieval. Negative or
non-integer limits raise `ValidationError`. Missing sources produce empty fields;
extraction/process failures raise `ValidationError`. The result also contains
`video_id` and `title`. This synchronous API must run off the UI thread.

The probe now calls this API directly. Its JSON uses the dataclass field names
above. No UI integration, AI discovery or partial-failure recovery is implemented
in this change; the remaining sections describe the proposed integration.

## Recommendation

Use the existing yt-dlp dependency for all three sources. Keep chapter import
deterministic and separate from AI discovery in descriptions/comments.
No new YouTube API key or library is needed for this approach.

| Source | yt-dlp output | Treatment |
| --- | --- | --- |
| Description | `description` string | Give to AI as source text to locate a track list |
| Leading comments | `comments` with `id`, `text`, `parent`, optional `like_count`/`is_pinned` | Fetch up to X top-level comments in YouTube top order; give each to AI as a distinct source |
| Chapters | `chapters` with `title`, `start_time`, `end_time` | Convert directly to track candidates; never send through an LLM |

“Top” means YouTube's server-side ranking, not the globally highest like counts.
Pinned comments can affect ordering. X is a maximum, not a guarantee: fewer
comments may exist or be accessible. Recommend X=20 initially, configurable
between 0 and 200; zero disables comment extraction. This default is a design
proposal, not a measured optimum.

Confirmed user preference: use YouTube's Top comments order as returned. Do not
sort by like count. The goal is to find set lists in those leading comments.

yt-dlp already extracts chapters from player data, engagement panels, or
timestamped descriptions as a fallback. Chapter names can describe introductions,
interviews or arbitrary segments rather than songs, so show them for review.
Do not imply that all chapter records were explicitly authored by the uploader.

## Existing code and the required integration

- `core/video_info.py`: both library and external executable paths already
  retrieve metadata, but `_build_video_info` discards descriptions and chapters.
  Add immutable chapter records and description to `VideoInfo`, with defaults
  so existing constructors remain valid. This costs no separate comment request.
- Fetch comments separately on a discovery action, keeping initial video preview
  responsive. Use a shared `core/video_sources.py` service for library and CLI
  parity. Return comment status (`not_requested`, `available`, `empty_or_disabled`,
  `failed`) alongside any available text. Do not treat absent comments as proof
  that comments are disabled. A comment failure must preserve description and
  chapter candidates already loaded.
- `llm/tracklist.py` currently returns only `template`, `artist_name`, `album_name`.
  Its input is already a raw track list. Sending an entire description or comment
  dump to that operation cannot identify and return the actual list. Add a
  separate discovery operation and prompt, reusing provider configuration and
  request handling. Keep current manual track-list assistance working.
- `app_logic/` should coordinate candidates, validation and formatting for all
  three front-ends. Widget/QML workers and TUI daemon threads should only wrap
  that behavior. Discard stale results if the loaded URL changes, and do not
  overwrite user edits when background discovery finishes.
- `app_logic/job_builder.py` currently builds jobs by parsing editable track-list
  text. For an initial version, render accepted candidates with the existing
  default `%songname% - %mm%:%ss%` template, using total minutes for hour-long
  videos. This avoids the existing mixed-hour template ambiguity. Chapter titles
  and timing come directly from data, with no AI call or template inference.
  The parser derives end times from the next start (and the splitter handles
  the last track). If exact chapter end times or gaps must be preserved, extend
  job construction to accept validated `Track` objects instead of text round trips.

## Extraction details and executable probe

Run from this worktree after `uv sync`:

```sh
uv run python scripts/probe_video_track_sources.py 'VIDEO_URL' --comments 20
uv run python scripts/probe_video_track_sources.py 'VIDEO_URL' --comments 0
uv run python scripts/probe_video_track_sources.py 'VIDEO_URL' --comments 20 --external yt-dlp
```

The script prints just the relevant metadata as JSON, makes no AI calls and
downloads no audio/video. It does not write a description or info JSON sidecar.
Warnings go to stderr. It is a diagnostic, not the fault-tolerant application
service described above; an extraction failure exits nonzero.

Library options:

```python
{
    "skip_download": True,
    "noplaylist": True,
    "getcomments": True,
    "extractor_args": {"youtube": {
        "comment_sort": ["top"],
        "max_comments": [str(x), str(x), "0", "0"],
    }},
}
```

`max_comments` specifies total comments, parents, replies, replies per thread.
Zero replies makes the total limit apply to top-level comments. The probe also
filters parents and slices to X before output. Use one `youtube:` prefix in CLI
extractor arguments: `youtube:comment_sort=top;max_comments=20,20,0,0`.
The corresponding CLI requires `--write-comments --dump-single-json
--skip-download --no-playlist`; no `--write-info-json` is necessary.

Important: the Python path uses `extract_info(url, download=False)` followed by
`ydl.post_extract(info)` **inside** the downloader context. Comments are deferred
via `__post_extractor`; metadata-only Python calls can otherwise leave them
unfetched. `post_extract` consumes that callback, so calling it after extraction
does not fetch comments a second time if they were already processed. The CLI
JSON-output path handles deferred extraction itself.

Comment extraction adds requests and latency. The probe sets socket timeout and
retry limits; its external process has a 120-second deadline. The library socket
timeout is not a total wall-clock deadline. Production code needs cancellation
and a bounded background operation, with partial-source fallback. YouTube bot
checks, authentication restrictions and extractor changes can still prevent
retrieval. Honor the app's external-yt-dlp setting in production.

## AI contract

Supply video title, duration, description and comments with stable source IDs
(`description`, `comment:<id>`). Do not include chapter data in the AI request.
Treat source text as untrusted quoted data, not instructions. Send no author
identity or unrelated comment metadata unless needed for the feature.

Return a structured collection of candidates, for example:

```json
{
  "candidates": [{
    "source_id": "comment:example",
    "timestamped": true,
    "entries": [
      {"title": "First Song", "start_seconds": 0, "source_line": "0:00 First Song"},
      {"title": "Second Song", "start_seconds": 245, "source_line": "4:05 Second Song"}
    ]
  }]
}
```

An empty candidates array is a normal “no list found” result. A song list without
timestamps is useful evidence, but cannot drive splitting: return it as an
untimed candidate with null starts and ask for timestamps through the existing
editing flow. Never invent titles or timing, infer timing from track order, or
combine unrelated lists from different comments. Preserve alternate candidates
when description and comments disagree; deduplicate identical candidates while
retaining provenance.

Validate response schema, source IDs, source-line membership and timestamp
agreement against the supplied text. Independently require nonempty names,
finite nonnegative starts, strictly increasing times and starts less than known
video duration for any candidate offered for splitting. Reject or flag duplicate,
decreasing and out-of-range starts. Apply equivalent time checks to chapters,
including positive end intervals and no overlap. A list starting after zero is
valid; do not invent an opening track. Show provenance and allow editing before
applying a candidate. Avoid silently replacing a populated list.

Bound source size and the combined prompt budget, retaining source boundaries
and recording truncation. A maximum number of comments does not bound tokens:
one comment can contain a long set list. Preserve complete lines where possible
and warn when truncation could make a candidate incomplete. Browser-based
ChatGPT Lite needs its own discovery prompt and copy/paste result flow; it cannot
use the automatic API result path. With no AI configured, chapters still work.

## Suggested implementation sequence and validation

1. Preserve description/chapters in metadata; add shared chapter validation and
   deterministic editable-list formatting. Verify no LLM calls for chapter import.
2. Add bounded comments service for library and external executable, X setting,
   source-status reporting, cancellation and stale-result protection.
3. Add the separate AI discovery contract and candidate validation, then expose
   “Use chapters” and “Find track list” actions across widgets, QML and TUI.

Cover absent metadata, disabled/empty comments, X=0, top/reply limits, deferred
extraction, library/CLI parity, Unicode titles, hour-long timings, invalid chapter
intervals, no-list/untimed-list results, conflicting lists, fabricated AI entries,
source truncation, partial failure and a URL change during discovery. Use mocked
network/AI for deterministic tests. Run live probes on representative concert
URLs to evaluate list-discovery quality and latency before choosing the default X.

## Verification performed

- After rebasing onto `qml-e2e-tests`, the non-TUI suite passed: **336 tests**,
  including QML and pipeline E2E tests. The full run was interrupted after
  prolonged TUI execution; no full-suite pass is claimed.
- Implemented API: live checks with X=5 succeeded in library and external modes;
  each returned a 722-character description, 13 named chapters with start/end
  times, and five nonempty comments with IDs.
- After implementation, the non-TUI suite passed: **271 tests**, using
  `QT_QPA_PLATFORM=offscreen python -m pytest -q --ignore=tests/test_tui.py`.
  This includes new coverage for library/CLI parity, actual yt-dlp CLI option
  parsing, deferred comment extraction, zero/invalid limits, source normalization,
  missing data, playlists, process errors, bad JSON and default settings.
- Live library probe of `https://www.youtube.com/watch?v=qVv6vCqciTM` with X=3
  returned a 722-character description, 13 chapters (first: `OP`, 0–77 seconds),
  and three comments, all with `parent=root`. This verifies extraction on one
  public video, not general availability or AI discovery quality. Raw fetched
  comments were kept outside the repository in `/tmp`.
- Follow-up live probes with X=20 succeeded in **both** modes: the Python
  library and a separately invoked external `yt-dlp` executable, both version
  `2026.10.26`. Each returned the 722-character description, 13 chapters with
  names and start/end times, and 20 nonempty top-level comments. Assertions on
  those fields passed. Descriptions and chapters matched exactly across modes.
  Comment selections/order differed between requests, demonstrating that
  YouTube's Top ranking is dynamic; identical comments across modes should not
  be required. No local reordering is needed or desired.
- An offline synthetic yt-dlp extractor verified deferred comment execution,
  X=0 disabling comments, and preservation of chapter names/times. The external
  command was also checked using yt-dlp's actual option parser.
- The probe's `--help` invocation succeeded. No AI request was made.
- Focused existing tests for video metadata, prompts, LLM API and shared app
  logic passed: 70 tests. The full suite was interrupted after it stopped
  producing progress late in the run; no full-suite pass is claimed.

## References

- [yt-dlp extractor arguments](https://github.com/yt-dlp/yt-dlp#extractor-arguments)
  documents `comment_sort` and `max_comments`.
- [YouTube extractor](https://github.com/yt-dlp/yt-dlp/blob/master/yt_dlp/extractor/youtube/_video.py)
  implements chapter fallback, comment ranking and deferred extraction.
- [Extractor base](https://github.com/yt-dlp/yt-dlp/blob/master/yt_dlp/extractor/common.py)
  implements `extract_comments` and disabled-comment behavior.
- [YoutubeDL](https://github.com/yt-dlp/yt-dlp/blob/master/yt_dlp/YoutubeDL.py)
  implements `post_extract` and metadata JSON processing.
