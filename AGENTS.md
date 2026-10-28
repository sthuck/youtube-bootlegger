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

Terminal UI (Textual; no display server needed):
```
uv run python main_tui.py
```

### Architecture

- `core/`, `llm/`, `models/`, `utils/`: business logic. Only `PySide6.QtCore` (`QSettings`) is required, so all three UIs share `core/settings.py` and the same settings file.
- `app_logic/`: UI-agnostic glue shared by the front-ends (form validation → `DownloadJob`, preview/progress/video display strings, help content). Put behaviour here rather than duplicating it per UI.
- `core/ytdlp_metadata.py` is the only place that asks yt-dlp for metadata (bundled library or external executable per settings); `fetch_video_info` builds on it and returns description, chapters and (with `comment_limit`) comments from a single request. Track-source plans are in `docs/video-track-sources-investigation.md`.
- `ui/` (widgets), `qml/` + `qml_backend/` (QML), `tui/` (Textual) are the three front-ends.
- `llm/chatgpt_lite.py` takes injectable `open_url`/`copy_text` callables; Qt implementations are the default, the TUI passes its own.

### Running tests

```
uv run pytest -v              # everything (~20s)
uv run pytest -m "not e2e"    # skip the full-stack ffmpeg test
uv run pytest tests/test_qml.py tests/test_e2e_pipeline.py   # QML UI only (~3s)
```

### Testing methodology

Layers, from fast and narrow to slow and wide:

1. **Unit tests** for `core/`, `llm/`, `app_logic/`, `utils/` (`test_template_parser.py`, `test_llm_client.py`, ...). Pure Python; prefer these for any logic that can live outside a UI.
2. **UI interaction tests** drive a real front-end headlessly against the real backend, with only the outside world faked:
   - QML: `tests/test_qml.py` loads `Main.qml` + `AppBackend` with `QQmlApplicationEngine` (`QT_QPA_PLATFORM=offscreen`) and drives it with `QTest`.
   - TUI: `tests/test_tui.py` uses Textual's `App.run_test()` / Pilot (pytest-asyncio, `asyncio_mode = "auto"`). Network and the pipeline are monkeypatched on `src.youtube_bootlegger.tui.app`.
3. **Full-stack smoke test** (`tests/test_e2e_pipeline.py`, marked `e2e`): QML UI -> `PipelineWorker` -> real FFmpeg splitting -> real Mutagen tagging on a synthesized MP3. Only the video-info fetch and the yt-dlp download are stubbed. It skips when ffmpeg or its `libmp3lame` encoder is missing.

QML test infrastructure lives in `tests/qml_support.py` (helpers, fakes) and `tests/conftest.py` (fixtures). Import helpers from `tests.qml_support`, never from another test module.

- `qml_harness` yields `(window, backend, app_settings)`. Settings are an in-memory `DictBackend`, so tests never touch the real config; the network is faked (`fake_video`); the debounce is 10 ms. The fixture **fails the test if any QML warning was logged**, captured with a message handler installed before `engine.load()`.
- Use `open_window(backend)` when a test needs its own window (a custom backend, or a "restart" that reloads the same `settings_store`).
- Fakes sit only at external boundaries: `fetch_video_info` (`fake_video`, or `gated_fetch` for ordering control), `DownloadSplitPipeline` (`fake_pipeline`), HTTP for AI Assist (`use_ai_http` injects `http_post` into `TracklistAiWorker`), `launch_chatgpt_lite_assist`, `is_ffmpeg_available`. Don't patch backend internals.

### Guidelines for new tests

- **Interact like a user; assert what the user sees.** Find controls by `objectName` (add one to any QML element a test touches) and assert on rendered QML properties (`prop(window, "videoTitleText")`), not only backend state.
- **Typed input goes through `type_text`** (focus plus real key events). `set_text` assigns the whole value at once and is only for pasted input (URLs, multi-line tracklists). Assigning the property directly skips keystroke handlers, `editingFinished` and focus. That once hid a bug where the artist field could not hold a space.
- **Click with `click_item`**, which scrolls the control into view and sends a real mouse click, rather than calling slots on the backend. Calling `backend.someSlot()` directly is acceptable only to check a guard, e.g. a second start while busy.
- **Never call private methods or set private state to stage a scenario.** For async ordering (late, stale or out-of-order worker results), use `gated_fetch`: each call blocks until the test resolves it with `calls[i].succeed(...)` or `.fail(...)`, in whatever order the test needs.
- **Wait on conditions, not time.** Use `wait_until(...)`, or `wait_for_workers(backend)` before asserting that something did *not* happen. Avoid fixed `qWait` sleeps in assertions.
- **"Persists" means it survives a restart**: build a new `AppBackend(settings=AppSettings(settings_store))` in `open_window` and check that the UI shows the saved values.
- **Keep fakes honest.** `FakePipeline` mirrors `DownloadSplitPipeline`'s constructor (enforced by `test_fake_pipeline_matches_real_constructor`) and its cancel contract (a cancelled run returns `[]`). Update both when the real interface changes.
- **Don't reshape production code for monkeypatching.** Inject through constructors (`AppBackend(settings=...)`, `TracklistAiWorker(http_post=...)`), or patch module-level names at the boundary.
- **Check that a regression test really fails.** Run a new test against the unfixed code, or temporarily break the fix, and confirm it fails.
- **Mark slow, real-tool tests with `@pytest.mark.e2e`**, and skip, rather than error, when the tool is unavailable.
- Coverage numbers under-report `workers/*`: their `run()` executes on `QThreadPool` threads, which coverage does not trace.

### Key caveats

- **PySide6 system libraries**: The Qt xcb platform plugin requires system packages `libegl1`, `libopengl0`, `libxcb-cursor0`, `libxkbcommon-x11-0`, `libxcb-xkb1`, `libxcb-xinerama0`, `libxcb-icccm4`, `libxcb-image0`, `libxcb-keysyms1`, `libxcb-render-util0`, and `libxcb-shape0`. These are installed in the VM snapshot and should persist. If `libqxcb.so` fails to load, run `ldd` on it to find missing shared libs.
- **FFmpeg**: Required at runtime for audio splitting (`shutil.which("ffmpeg")` is used). Pre-installed in the VM.
- **No linter configured**: The project does not include a linter (ruff, flake8, pylint, etc.) in its dev dependencies or `pyproject.toml`. Pytest is the only dev tool for validation.
- **QML worker lifetime**: `AppBackend` holds every in-flight `VideoInfoWorker` until it reports back, and drops superseded results with a request id. Don't rely on replacing the worker attribute to drop old results. That frees the signals object while its thread can still emit on it.
- **QML text fields**: keep one sync path (`text: backend.x` plus `onTextChanged` with an equality guard). Backend setters must store text as typed. Normalise (strip) when building the job, otherwise the value written back into the field fights the user's typing.
- **TUI thumbnails**: `textual-image` auto-detects Kitty TGP / Sixel / Unicode half-cell rendering. Detection queries the terminal, so `app_tui.py` imports `textual_image.renderable` before Textual starts.
- **TUI background work** runs on daemon threads (`BootleggerApp._in_background`), not Textual thread workers, because Textual joins worker threads on exit and quitting mid-download would hang.
- **`DISPLAY` env var**: Must be set (`:1` by default in Cloud VMs) for the Qt GUI to render. Use `QT_QPA_PLATFORM=offscreen` if headless testing is needed.
