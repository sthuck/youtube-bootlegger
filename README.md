
## Runtime tools

Releases don't include yt-dlp, FFmpeg/ffprobe or Deno. On first start the app
downloads the pinned versions once into a per-user folder
(`%LOCALAPPDATA%\YouTubeBootlegger\tools` on Windows,
`~/.local/share/youtube-bootlegger/tools` on Linux and macOS) and reuses them.
FFmpeg and Deno already on PATH are used instead, and paths set in Settings take
priority over both. See [how the downloader works](docs/runtime-tools.md).

## Release builds

Each release publishes **QML desktop** and **TUI terminal** downloads for Linux
x64, Windows x64 and macOS arm64 (six assets). The widgets UI is not released.
Extract the entire archive before launching:

| Platform | QML | TUI |
| --- | --- | --- |
| Linux | `.tar.gz`, run `youtube-bootlegger-qml` | `.tar.gz`, run `youtube-bootlegger-tui` in a terminal |
| Windows | `.zip`, launch `youtube-bootlegger-qml.exe` | `.zip`, run `youtube-bootlegger-tui.exe` in a terminal |
| macOS | `.zip` containing `youtube-bootlegger-qml.app` | `.tar.gz`, run `youtube-bootlegger-tui` in a terminal |

Release builds use PyInstaller rather than `pyside6-deploy`/Nuitka. Bundling
Python avoids compiling the application and its dependencies to C, and folder
bundles avoid single-file compression and extraction on every launch. Python
does not need to be installed on the user's machine. These builds do not have
Nuitka's compiled-code optimizations; download/splitting work runs in external
tools either way. The TUI bundles QtCore for shared settings and locks, but
excludes the Qt GUI libraries.

To build locally on the target OS:

```sh
uv sync --dev --locked
uv run --no-sync pyinstaller --noconfirm --workpath build/qml main.spec -- --ui qml
uv run --no-sync pyinstaller --noconfirm --workpath build/tui main.spec -- --ui tui
uv run --no-sync python scripts/package_release.py --ui qml --platform linux-x64 --version v0.1.0
uv run --no-sync python scripts/package_release.py --ui tui --platform linux-x64 --version v0.1.0
```

Use `windows-x64` or `macos-arm64` when packaging on those platforms. Output is
under `dist/release/`. Keep each executable with its accompanying files.
The Release workflow builds all six combinations in parallel; manual runs
upload workflow artifacts without publishing a release. Release events publish
assets only after all six builds succeed. Linux builds use Ubuntu 22.04 to
avoid requiring the newest runner's glibc on users' machines.

`pysidedeploy.spec` remains available for optional QML builds with Nuitka. If
using it in CI, persist `NUITKA_CACHE_DIR` between runs and install `ccache` on
Linux/macOS to reduce repeated C compilation. Caching helps warm builds; it
does not eliminate the initial compilation cost.
