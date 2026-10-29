
## Runtime tools

Releases don't include yt-dlp, FFmpeg/ffprobe or Deno. On first start the app
downloads the pinned versions once into a per-user folder
(`%LOCALAPPDATA%\YouTubeBootlegger\tools` on Windows,
`~/.local/share/youtube-bootlegger/tools` on Linux and macOS) and reuses them.
FFmpeg and Deno already on PATH are used instead, and paths set in Settings take
priority over both. See [how the downloader works](docs/runtime-tools.md).
