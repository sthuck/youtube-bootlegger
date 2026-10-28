# Video track-source discovery

Goal: fill the track list from what YouTube already has — chapters, the
description, and set lists posted in comments — instead of making the user
type it. All three come from the existing yt-dlp dependency; no YouTube API key
or new library is needed.

## What exists

| Source | Where | Treatment |
| --- | --- | --- |
| Chapters | `VideoInfo.chapters` (`VideoChapter`: title, start, end) | Convert directly to tracks; never send through an LLM |
| Description | `VideoInfo.description` | Source text for AI track-list discovery |
| Comments | `fetch_video_comments(url, settings, limit=20)` → `VideoComment`s | Each comment is a separate source for AI discovery |

- `core/ytdlp_metadata.py` is the single place that asks yt-dlp for metadata,
  in both library and external-executable modes. `fetch_video_info` and
  `fetch_video_comments` both use it, so the modes stay in parity and share
  error messages.
- Description and chapters arrive with the normal video preview at no extra
  cost. Comments need a separate, slower request (they re-fetch the page and
  then page through comments), so they're fetched only on demand.
- `scripts/probe_video_track_sources.py URL [--comments N] [--external yt-dlp]`
  prints all three as JSON, for checking real videos.

Behaviour worth knowing:

- Comments are top-level only, in YouTube's **Top** order as returned, not
  re-sorted by likes. Top ranking is dynamic: repeated requests, or library vs.
  external mode, can return different comments. `limit` is a maximum.
- yt-dlp derives chapters from player data or, failing that, timestamps in the
  description, so chapter names may be intros or talk segments, not songs.
  Show them for review rather than assuming they were authored as a track list.
- In library mode, comments are deferred by yt-dlp when not downloading;
  `ydl.post_extract(info)` must run inside the `YoutubeDL` context to get them.
- Comment fetches have a 120 s deadline in external mode; in library mode the
  socket timeout and retry limits bound each request, not the total time.
  YouTube bot checks and extractor changes can still block retrieval.

## Remaining work

1. **Use chapters.** In `app_logic/`, render valid chapters as an editable
   track list using the default `%songname% - %mm%:%ss%` template (total
   minutes for hour-long videos). Expose a "Use chapters" action in all three
   front-ends. If chapter end times or gaps must be kept exactly, build jobs
   from `Track` objects instead of a text round trip.
2. **Find a track list with AI.** `llm/tracklist.py` only infers a template
   from a list the user already has; it can't locate a list inside a
   description. Add a separate discovery operation and prompt that reuse the
   provider configuration (contract below). ChatGPT Lite needs its own
   copy/paste prompt flow.
3. **Wire comments into the UI** as part of (2): fetch on the discovery action
   from a worker / daemon thread, support cancellation, discard results if the
   URL changed, and never overwrite user edits. If comments fail, still offer
   description and chapter candidates. A comment status (not requested /
   available / empty / failed) would let the UI explain an empty result.
4. **Settings:** make the comment limit configurable (0–200, 0 disables).
   20 is a starting guess, not measured; tune with live probes on real
   concert videos.

## AI discovery contract

Input: title, duration, the description and each comment, with stable source
IDs (`description`, `comment:<id>`). No chapters (handled deterministically)
and no author identities. Source text is untrusted quoted data, not
instructions. Bound each source and the total prompt size, keeping whole lines
and recording truncation — a comment limit doesn't bound tokens.

Output:

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

- Empty `candidates` is a normal "no list found" result.
- An untimed list is useful but can't drive splitting: return it with null
  starts and let the user add timestamps through the existing editor.
- Never invent titles or times, infer times from order, or merge lists from
  different sources. Keep conflicting candidates; deduplicate identical ones
  while keeping provenance.
- Validate: known source IDs, each `source_line` present in its source, its
  timestamp matching `start_seconds`, nonempty titles, and starts that are
  finite, strictly increasing and below the video duration. A list may start
  after 0:00; don't invent an opening track.
- Show provenance, allow editing before applying, and don't silently replace a
  populated list. Chapters keep working with no AI configured.
