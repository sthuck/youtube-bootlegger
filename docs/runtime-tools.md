# Runtime tools

The app needs yt-dlp, FFmpeg (with ffprobe) and Deno. Releases don't include
them. On first start, the app downloads the pinned versions from their upstream
release pages into a per-user folder and reuses them from then on. Nothing needs
administrator rights, Homebrew, or PATH changes.

| OS | Folder |
| --- | --- |
| Windows | `%LOCALAPPDATA%\YouTubeBootlegger\tools\` |
| Linux, macOS | `$XDG_DATA_HOME/youtube-bootlegger/tools/`, by default `~/.local/share/youtube-bootlegger/tools/` |

Windows uses the local (not roaming) AppData folder because these are large,
machine-specific binaries.

## What gets downloaded

| Tool | Source | Downloaded when |
| --- | --- | --- |
| yt-dlp 2026.10.26 | Official yt-dlp release executables | Always, unless a yt-dlp path is set in Settings |
| FFmpeg + ffprobe 9.0.2, Linux x64 and macOS ARM64 | [Martin Riedl's static builds](https://ffmpeg.martin-riedl.de/) ([build script](https://git.martin-riedl.de/ffmpeg/build-script)) | Not set in Settings and not both on PATH |
| FFmpeg + ffprobe 9.0.2, Windows x64 | [Gyan's essentials build](https://github.com/GyanD/codexffmpeg/releases/tag/9.0.2) | Same |
| Deno 2.9.8 | Official Deno release | Not on PATH, or the one on PATH is older than 2.0 |

`src/youtube_bootlegger/core/tool_manifest.py` pins every URL, size and SHA-256
per platform. Other platforms (Linux ARM, Intel Macs) have no downloads; the app
uses tools on PATH or paths set in Settings, and says so when FFmpeg is missing.

## How the downloader works

- **Finding past downloads.** Each tool lives in `<folder>/<tool>/<version>-<hash>/`,
  where the hash covers the pinned checksums. A folder counts as installed once
  its `installed.json` exists. The installer writes that file last, so checking
  for a tool needs no network access and doesn't re-hash anything.
- **Only what's needed.** See the table above. FFmpeg and ffprobe are one tool:
  yt-dlp expects ffprobe next to FFmpeg.
- **Safe installs.** Downloads go into a hidden `.staging-*` folder, are checked
  against the pinned size and SHA-256, and only the named executables are taken
  from each archive (no paths, links or duplicates). The finished folder is
  renamed into place in one step. Cancelling, a failed check or a crash leaves no
  half-installed tool; leftover staging folders are removed on the next install.
- **One installer at a time.** A lock file in the tools folder makes a second
  running copy of the app wait, then skip whatever the first one installed.
- **Upgrades.** A release that pins a new version downloads only the tools whose
  pins changed and deletes their older folders.
- **Verify.** Settings → Runtime tools → Verify re-hashes the downloaded files
  against `installed.json` and downloads again any tool that changed.

The download starts automatically at start-up, and again after Settings change
if a tool became needed. A banner shows progress with Cancel; after a cancel or a
failure it offers Download or Retry. Start is blocked only while FFmpeg (or yt-dlp
in external mode) is missing.

## Lookup order and yt-dlp flags

`AppSettings` resolves each tool as: a path set in Settings, then the downloaded
copy, then PATH. Once the downloaded yt-dlp exists, external yt-dlp mode becomes
the default; an explicit choice in Settings is kept.

Every yt-dlp run gets `--ffmpeg-location <resolved FFmpeg>` and, when Deno was
downloaded, `--js-runtimes deno:<path>` (or the equivalent library options).
`--js-runtimes` is left out for a yt-dlp path set in Settings, because yt-dlp
versions before 2025.11 reject it; such a yt-dlp finds Deno on PATH by itself.
`--ignore-config` keeps a global yt-dlp config from changing the app's behaviour.

## Checks

`tests/test_runtime_tools.py` covers lookup, the installer and the flags with
fake downloads. Its `test_real_tools_download_and_run` downloads the real pins,
encodes an MP3 with the downloaded FFmpeg, probes it with ffprobe, checks yt-dlp
detects Deno and FFmpeg, and runs JavaScript in Deno. It runs only with
`RUNTIME_TOOLS_E2E=1`; the `Runtime tool downloads` workflow runs it on Linux,
Windows and macOS for pull requests that touch the pins and weekly, because
upstream files can disappear.

## Licensing

The app doesn't distribute these executables: each user's copy of the app
downloads them directly from their publishers, who provide the source and
licence terms (yt-dlp's standalone builds and these FFmpeg builds are GPL; Deno
is MIT). Hosting copies of the binaries, or putting them back into release
archives, would make this project a distributor with GPL source obligations.

The app itself still compiles in Mutagen (GPLv2+) and PySide6/Qt (LGPLv3), which
have their own obligations, which this document doesn't cover.

References:

- https://github.com/yt-dlp/yt-dlp#licensing
- https://github.com/yt-dlp/yt-dlp/wiki/EJS
- https://www.ffmpeg.org/legal.html
- https://github.com/denoland/deno/blob/v2.9.8/LICENSE.md
