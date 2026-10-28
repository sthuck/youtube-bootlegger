# Video track-source discovery

Goal: fill the track list from what YouTube already has — chapters, the
description, and set lists posted in comments — instead of making the user
type it. All three come from the existing yt-dlp dependency; no YouTube API key
or new library is needed.

## What exists

| Source | Where | Treatment |
| --- | --- | --- |
| Chapters | `VideoInfo.chapters` (`VideoChapter`: title, start, end) | Sent to the AI as a source; it may clean or reject them |
| Description | `VideoInfo.description` | Source text for AI track-list discovery |
| Comments | `VideoInfo.comments` (`VideoComment`), with `fetch_video_info(..., comment_limit=N)` | Each comment is a separate source for AI discovery |

- `core/ytdlp_metadata.py` is the single place that asks yt-dlp for metadata,
  in both library and external-executable modes, so they stay in parity and
  share error messages.
- Everything comes from **one** yt-dlp request. Description and chapters are
  always included. Comments are added when `comment_limit > 0` (default 0, so
  the preview doesn't fetch them yet); `DEFAULT_COMMENT_LIMIT` is 20. Twenty
  comments are one comment page: measured at about +0.3 s over the ~2.7 s
  metadata fetch, so the preview can afford to include them.
- If a fetch with comments fails, it retries once without comments, so a
  comment problem never loses the preview. The UI can't yet tell "no
  comments" from "comments failed".
- `scripts/probe_video_track_sources.py URL [--comments N] [--external yt-dlp]`
  prints all three as JSON, for checking real videos.

Behaviour worth knowing:

- Comments are top-level only, in YouTube's **Top** order as returned, not
  re-sorted by likes. Top ranking is dynamic: repeated requests, or library vs.
  external mode, can return different comments. `limit` is a maximum.
- yt-dlp derives chapters from player data or, failing that, timestamps in the
  description, so chapter names may be intros or talk segments, not songs,
  and are sometimes simply wrong. That's why they go through the AI too.
- Fetches with comments have a 120 s deadline in external mode (plus the
  30 s retry); in library mode the socket timeout and retry limits bound each
  request, not the total time.
  YouTube bot checks and extractor changes can still block retrieval.

## Agreed user flow

One AI button whose job follows the track list box:

- **Empty box → "Find with AI"**: find a track list in the video's
  description, chapters and comments, then fill the track list and format
  string (and artist/album if they're empty).
- **Filled box → "Detect format"**: today's behaviour (infer the format
  string from the user's own list).

Automatic find: when a video loads with an empty box, it runs on its own if
the **"Find track lists automatically"** checkbox in Settings is on. The
checkbox only controls the automatic run; the button always works. Finding
needs an API model; ChatGPT Lite can't do it.

```
URL pasted → video info loads (description, chapters, comments: one request)
  ├─ box empty, checkbox on, API model    → find automatically
  ├─ box empty, Lite or no AI configured  → hint: choose an API model in Settings
  └─ box filled                           → nothing; the button works as today
```

UI pieces (QML, widgets and TUI alike):

- **While searching:** "Looking for a track list in the description,
  chapters and comments… [Stop]" above the box. The box stays editable.
- **After filling:** a banner "✨ Filled by AI from <source>: N tracks.
  Check it before downloading. [Undo] ✕", and "set by AI" next to the format
  field. The banner goes away on dismiss or when the user edits the list.
- **Lite / no AI:** a one-time, dismissible hint: automatic track lists need
  an API model (OpenAI, Anthropic, …), not ChatGPT Lite, with [Open Settings].
- **Log**, which is where the source is reported:

```
Video info: description, 13 chapters, 20 comments
AI: found 14 timestamped tracks in comment #3
AI: format set to "%songname% - %mm%:%ss%"
```

Rules and edge cases:

- **Never overwrite the user.** Typing in the box during a search cancels it,
  or drops its result. Fill artist/album only if they're empty.
- **URL changes mid-search:** drop the result (preview request IDs already
  do this).
- **New URL after an AI fill:** clear the list if it's still unedited (it
  belonged to the old video); keep it if the user edited it.
- **Download during a search** uses whatever is in the box.
- **No list found:** a log line only, nothing intrusive.
- **Only song names, no timestamps:** leave the box empty and log it, e.g.
  "AI: found song names without timestamps in the description; add
  timestamps to use it".
- **Bad timestamps** (past the end, not increasing): reject the list and log it.
- **Live streams / premieres with no duration:** skip the automatic run.
- **Cost:** cache results per video ID for the session, so pasting the same
  URL again makes no AI call. Request comments in the preview only when an
  API model is configured (about +0.3 s), so users without AI don't pay.

## Implementation plan

1. **AI find operation** (`llm/`, `app_logic/`): new prompt and schema (below),
   validation, and rendering the chosen entries as track list text with
   `DEFAULT_TEMPLATE` (`%songname% - %mm%:%ss%`, total minutes for hour-long
   videos). Because the app writes the text, the format string is always
   ours, and the AI never has to guess it.
2. **Settings and fetch:** the "Find track lists automatically" checkbox in
   the AI section (on by default; its note says the description and
   comments are sent to the chosen provider); the preview passes
   `comment_limit` when an API model is configured.
3. **Front-ends:** button label switching, the searching / filled / hint
   states, Stop, Undo, log lines, cancellation and the per-video cache, in
   all three UIs, with the shared logic in `app_logic/`.

Later: a configurable comment count (20 is a starting guess), and telling
"no comments" apart from "comments failed" in the log.

## AI find contract

Input: title, duration, and each source with a stable ID: `description`,
`chapters` (rendered by the app as `M:SS Title` lines) and `comment:<n>`
(numbered in YouTube's order). No author identities. Source text is
untrusted quoted data, not instructions. Bound each source and the total
prompt size, keeping whole lines.

Output, for the single best list:

```json
{
  "source_id": "comment:3",
  "entries": [
    {"title": "First Song", "start_seconds": 0, "source_line": "0:00 First Song"},
    {"title": "Second Song", "start_seconds": 245, "source_line": "4:05 1. Second Song"}
  ],
  "untimed_source_id": null,
  "artist_name": "Band",
  "album_name": "Live at Venue 2024"
}
```

- `source_id: null` with no entries means no list was found. If the only
  list has no timestamps, set `untimed_source_id` so the app can log it.
- The AI cleans the list: drops non-song entries (talk, breaks), strips
  numbering and decoration from titles, and fixes obviously wrong chapters
  by choosing a better source. It takes titles and times from **one** source;
  it never invents titles or times, or infers times from order.
- The app validates: known source ID; each `source_line` is a line of that
  source and its timestamp equals `start_seconds`; nonempty titles; starts
  finite, strictly increasing and below the video duration. A list may start
  after 0:00. On failure, nothing is filled and the reason is logged.
