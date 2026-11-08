
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
Each build contains its assets inside a single executable. Extract downloads
where an archive is used:

| Platform | QML | TUI |
| --- | --- | --- |
| Linux | `.tar.gz`, run `youtube-bootlegger-qml` | `.tar.gz`, run `youtube-bootlegger-tui` in a terminal |
| Windows | `.exe`, launch directly | `.exe`, run in a terminal |
| macOS | `.zip` containing `youtube-bootlegger-qml.app` | `.tar.gz`, run `youtube-bootlegger-tui` in a terminal |

Release builds use PyInstaller rather than `pyside6-deploy`/Nuitka. Bundling
Python avoids compiling the application and its dependencies to C. Onefile
executables unpack their dependencies into a temporary directory at launch,
so startup takes longer than a folder bundle. Python does not need to be
installed on the user's machine. These builds do not have
Nuitka's compiled-code optimizations; download/splitting work runs in external
tools either way. The TUI bundles QtCore for shared settings and locks, but
excludes the Qt GUI libraries.

To build locally on the target OS:

```sh
uv sync --dev --locked
uv run --no-sync pyinstaller --noconfirm --workpath build/qml main.spec -- --ui qml
uv run --no-sync pyinstaller --noconfirm --workpath build/tui main.spec -- --ui tui
uv run --no-sync python scripts/verify_bundle.py --ui qml
uv run --no-sync python scripts/verify_bundle.py --ui tui
uv run --no-sync python scripts/package_release.py --ui qml --platform linux-x64 --version v0.1.0
uv run --no-sync python scripts/package_release.py --ui tui --platform linux-x64 --version v0.1.0
```

Use `windows-x64` or `macos-arm64` when packaging on those platforms. Output is
under `dist/release/`. The QML build on macOS is a `.app` wrapping its onefile
executable; keep that app bundle intact.
The Release workflow builds all six combinations in parallel; manual runs
upload workflow artifacts without publishing a release. Release events publish
assets only after all six builds succeed. Linux builds use Ubuntu 22.04 to
avoid requiring the newest runner's glibc on users' machines.

App assets are collected directly from the checkout, preserving paths relative
to the Python modules: all QML components and logos for QML; Textual CSS and
logos for TUI. Dependency hooks collect Qt libraries/plugins, image decoders,
and CA certificates. The TUI also includes Textual's syntax-highlighting data
and textual-image's fallback pictures. CI checks the completed executable for
these data files before packaging, including byte-for-byte comparisons with
the source assets. Runtime tools remain separate first-run downloads.
Python HTTPS downloads explicitly load the bundled certificate roots in
addition to system/configured roots, so macOS builds don't depend on
certificate paths from the build machine. Certificate and hostname validation
remain enabled.

`pysidedeploy.spec` remains available for optional QML builds with Nuitka. If
using it in CI, persist `NUITKA_CACHE_DIR` between runs and install `ccache` on
Linux/macOS to reduce repeated C compilation. Caching helps warm builds; it
does not eliminate the initial compilation cost.
