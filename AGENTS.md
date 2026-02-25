# AGENTS.md

## Cursor Cloud specific instructions

### Overview

YouTube Bootlegger is a PySide6 (Qt 6) desktop application that downloads YouTube live performance audio and splits it into individual song files with metadata tagging. It is a single-package Python project using `uv` as the package manager.

### Running the application

Widget UI (original):
```
uv run python main.py
```

QML UI (modern dark theme):
```
uv run python main_qml.py
```

### Running tests

```
uv run pytest -v
```

### Key caveats

- **PySide6 system libraries**: The Qt xcb platform plugin requires system packages `libegl1`, `libopengl0`, `libxcb-cursor0`, `libxkbcommon-x11-0`, `libxcb-xkb1`, `libxcb-xinerama0`, `libxcb-icccm4`, `libxcb-image0`, `libxcb-keysyms1`, `libxcb-render-util0`, and `libxcb-shape0`. These are installed in the VM snapshot and should persist. If `libqxcb.so` fails to load, run `ldd` on it to find missing shared libs.
- **FFmpeg**: Required at runtime for audio splitting (`shutil.which("ffmpeg")` is used). Pre-installed in the VM.
- **No linter configured**: The project does not include a linter (ruff, flake8, pylint, etc.) in its dev dependencies or `pyproject.toml`. Pytest is the only dev tool for validation.
- **`DISPLAY` env var**: Must be set (`:1` by default in Cloud VMs) for the Qt GUI to render. Use `QT_QPA_PLATFORM=offscreen` if headless testing is needed.
