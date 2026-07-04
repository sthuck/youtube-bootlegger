# YouTube Bootlegger

Download live performance audio from YouTube, split it into individual songs using a timestamped track list, and save tagged MP3 files with cover art.

YouTube Bootlegger is a desktop app for turning full concert or live-session videos into a proper album folder on your machine — one file per song, with artist, album, title, and track number metadata already filled in.

## What it does

1. **Downloads audio** from a YouTube watch or youtu.be URL using yt-dlp (bundled with the app).
2. **Parses your track list** — one song per line with timestamps — using a flexible template.
3. **Splits the audio** at each timestamp with FFmpeg.
4. **Tags each MP3** with metadata and embeds the video thumbnail as cover art.

Files are saved under your chosen output folder as:

```
OutputDir / Artist - Album / 01 - Song Name.mp3
```

Optional **AI Assist** can suggest the track list template, artist, and album from your raw text. That requires an LLM provider configured in Settings.

## Quick start

1. Paste a YouTube URL — the app fetches title, channel, duration, and thumbnail.
2. Paste or type your track list (one song per line, with timestamps).
3. Confirm the track list template matches your format (default: `%songname% - %mm%:%ss%`).
4. Enter an artist name (required) and optionally an album.
5. Choose an output directory (defaults to your Music folder).
6. Click **Download & Split**.

For template syntax, AI Assist, troubleshooting, and more detail, open the in-app **Help** panel (question-mark icon).

## Download & install

Pre-built binaries are published on the [Releases](https://github.com/sthuck/youtube-bootlegger/releases) page when a version is tagged.

| Platform | Download | Notes |
|----------|----------|-------|
| **macOS (Apple Silicon)** | `youtube-bootlegger-*-macos-arm64.zip` | See [macOS setup](#macos) below |
| **Windows** | `youtube-bootlegger-*-windows-x64.zip` | Run `YouTubeBootlegger.exe` |
| **Linux** | `youtube-bootlegger-*-linux-x64.tar.gz` | Run `YouTubeBootlegger.bin` |

### Requirements

- **FFmpeg** — required for splitting audio. The app does not bundle FFmpeg.
  - macOS: `brew install ffmpeg`
  - Linux: install via your package manager (e.g. `sudo apt install ffmpeg`)
  - Windows: download from [ffmpeg.org](https://ffmpeg.org/download.html) or use a package manager

If FFmpeg is not on your PATH, set a custom path in the app’s **Settings** (gear icon).

---

## macOS

macOS builds are **not code-signed or notarized**. Apple Gatekeeper will block the app on first launch — this is expected for unsigned software distributed outside the App Store.

### Install

1. Download `youtube-bootlegger-*-macos-arm64.zip` from [Releases](https://github.com/sthuck/youtube-bootlegger/releases).
2. Unzip the archive. You should get `YouTubeBootlegger.app`.
3. Drag `YouTubeBootlegger.app` to **Applications** (recommended).

> **Apple Silicon only:** Current release builds target `macos-arm64`. Intel Macs are not supported by the published binary.

### First launch (unsigned app)

Because the app is unsigned, macOS may show **“YouTube Bootlegger” cannot be opened because the developer cannot be verified** or **the application is damaged**.

Use one of these approaches:

**Option A — Right-click Open (easiest)**

1. In Finder, **right-click** (or Control-click) `YouTubeBootlegger.app`.
2. Choose **Open**.
3. Click **Open** in the confirmation dialog.

You only need to do this once. After that, double-click works normally.

**Option B — Privacy & Security**

1. Try to open the app normally (double-click).
2. Open **System Settings → Privacy & Security**.
3. Scroll down and click **Open Anyway** next to the blocked app message.
4. Confirm when prompted.

**Option C — Remove quarantine flag (Terminal)**

If macOS still refuses to open the app after download, clear the quarantine attribute macOS applies to files from the internet:

```bash
xattr -dr com.apple.quarantine /Applications/YouTubeBootlegger.app
```

Then use Option A or B for the first launch.

### Install FFmpeg

```bash
brew install ffmpeg
```

Verify FFmpeg is available:

```bash
ffmpeg -version
```

---

## Run from source

For development or if you prefer running from Python:

**Prerequisites:** Python 3.12+, [uv](https://docs.astral.sh/uv/), and FFmpeg on your PATH.

```bash
git clone https://github.com/sthuck/youtube-bootlegger.git
cd youtube-bootlegger
uv sync --dev
```

**QML UI (modern dark theme):**

```bash
uv run python main_qml.py
```

**Widget UI (original):**

```bash
uv run python main.py
```

**Tests:**

```bash
uv run pytest -v
```

---

## License

See the repository for license information.
