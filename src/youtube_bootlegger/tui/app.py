"""Textual application: the terminal front-end for YouTube Bootlegger."""

import asyncio
import threading
from collections.abc import Callable
from pathlib import Path

from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.timer import Timer
from textual.widgets import Button, Footer, Header, Input, Label, Static, TextArea

from ..app_logic import (
    FormError,
    FormField,
    JobForm,
    build_job,
    check_ai_assist_ready,
    format_progress_stage,
    summarize_preview,
    summarize_video,
)
from ..core import DEFAULT_TEMPLATE, DownloadSplitPipeline, preview_parse, validate_template
from ..core.exceptions import YouTubeBootleggerError
from ..core.settings import AppSettings, LlmProvider, get_settings
from ..core.video_info import VideoInfo, fetch_video_info
from ..llm import (
    LlmExtractionError,
    TracklistExtraction,
    build_lite_prompt,
    extract_tracklist_metadata,
    launch_chatgpt_lite_assist,
)
from ..models import DownloadJob
from ..utils import is_ffmpeg_available, is_valid_youtube_url
from .external import fetch_thumbnail, open_url_in_browser
from .screens import ConfirmScreen, DirectoryPickerScreen, HelpScreen, SettingsScreen
from .theme import BOOTLEGGER_THEME
from .widgets import ProgressPanel, StatusLog, TrackPreviewTable, VideoPanel

URL_DEBOUNCE_SECONDS = 0.5
# On quit mid-job: how long to let a cancelled pipeline kill its child
# processes and delete partial files before exiting anyway.
QUIT_CLEANUP_TIMEOUT_SECONDS = 5

ERROR_WIDGET_IDS = {
    FormField.URL: "url-error",
    FormField.TEMPLATE: "template-error",
    FormField.TRACKLIST: "tracklist-error",
    FormField.METADATA: "metadata-error",
    FormField.OUTPUT_DIR: "output-dir-error",
}

FOCUS_TARGET_IDS = {
    FormField.URL: "url",
    FormField.TEMPLATE: "template",
    FormField.TRACKLIST: "tracklist",
    FormField.METADATA: "artist",
    FormField.OUTPUT_DIR: "output-dir",
}

TRACKLIST_PLACEHOLDER = "Paste the track list here, one song per line:\nIntro - 0:00\nFirst Song - 3:15"


class BootleggerApp(App[None]):
    """Download a YouTube live set and split it into tagged tracks."""

    TITLE = "YouTube Bootlegger"
    CSS_PATH = "app.tcss"

    BINDINGS = [
        Binding("f1", "help", "Help"),
        Binding("f2", "settings", "Settings"),
        Binding("f3", "ai_assist", "AI assist"),
        Binding("ctrl+o", "browse", "Output dir"),
        Binding("f5,ctrl+r", "start", "Start"),
        Binding("f8", "cancel", "Cancel"),
        Binding("ctrl+q", "quit", "Quit", priority=True),
    ]

    busy: reactive[bool] = reactive(False)
    ai_running: reactive[bool] = reactive(False)

    def __init__(
        self,
        settings: AppSettings | None = None,
        *,
        show_thumbnail: bool = True,
    ) -> None:
        super().__init__()
        self._settings = settings or get_settings()
        self._show_thumbnail = show_thumbnail
        self._video_info: VideoInfo | None = None
        self._last_fetched_url = ""
        self._url_timer: Timer | None = None
        self._pipeline: DownloadSplitPipeline | None = None
        self._pipeline_stopped = threading.Event()

    # ── Layout ──────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="main"):
            with Vertical(id="form"):
                yield Label("YouTube URL", classes="field-label")
                yield Input(placeholder="https://www.youtube.com/watch?v=...", id="url")
                yield Static("", id="url-error", classes="field-error")
                with Horizontal(id="tracks"):
                    with Vertical(id="tracklist-col"):
                        yield Label("Track list", classes="field-label")
                        yield TextArea(id="tracklist", placeholder=TRACKLIST_PLACEHOLDER)
                        yield Static("", id="tracklist-error", classes="field-error")
                    with Vertical(id="preview-col"):
                        with Horizontal(classes="label-row"):
                            yield Label("Preview", classes="field-label")
                            yield Static("", id="preview-status")
                        yield TrackPreviewTable(id="preview")
                yield Label("Track list template", classes="field-label")
                with Horizontal(id="template-row"):
                    yield Input(DEFAULT_TEMPLATE, id="template")
                    yield Button("✦ AI Assist", id="ai-assist")
                yield Static("", id="template-error", classes="field-error")
                with Horizontal(id="metadata-row"):
                    with Vertical():
                        yield Label("Artist", classes="field-label")
                        yield Input(placeholder="Artist name", id="artist")
                    with Vertical():
                        yield Label("Album", classes="field-label")
                        yield Input(placeholder="Defaults to video title", id="album")
                yield Static("", id="metadata-error", classes="field-error")
                yield Label("Output directory", classes="field-label")
                with Horizontal(id="output-row"):
                    yield Input(str(Path.home() / "Music"), id="output-dir")
                    yield Button("Browse", id="browse")
                yield Static("", id="output-dir-error", classes="field-error")
            yield VideoPanel(id="video", show_thumbnail=self._show_thumbnail)
        with Horizontal(id="actions"):
            yield Button("▶ Start", variant="primary", id="start")
            yield Button("■ Cancel", variant="error", id="cancel", disabled=True)
            yield ProgressPanel(id="progress")
        yield StatusLog(id="status-log")
        yield Footer()

    def on_mount(self) -> None:
        self.register_theme(BOOTLEGGER_THEME)
        self.theme = BOOTLEGGER_THEME.name
        self.query_one("#url", Input).focus()
        if not is_ffmpeg_available(self._settings.resolved_ffmpeg_command()):
            self._log("FFmpeg not found — install it or set its path in Settings (F2).", "warn")
            self._notify(
                "FFmpeg not found. Set its path in Settings (F2).",
                severity="warning",
                timeout=8,
            )

    # ── Input handling ──────────────────────────────────────────────

    def on_input_changed(self, event: Input.Changed) -> None:
        input_id = event.input.id
        if input_id == "url":
            self._on_url_changed(event.value)
        elif input_id == "template":
            self._on_template_changed(event.value)
        elif input_id in ("artist", "album"):
            self._set_field_error(FormField.METADATA, "")
        elif input_id == "output-dir":
            self._set_field_error(FormField.OUTPUT_DIR, "")

    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        if event.text_area.id == "tracklist":
            self._set_field_error(FormField.TRACKLIST, "")
            self._update_preview()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        actions = {
            "start": self.action_start,
            "cancel": self.action_cancel,
            "browse": self.action_browse,
            "ai-assist": self.action_ai_assist,
        }
        action = actions.get(event.button.id or "")
        if action:
            action()

    def watch_busy(self, busy: bool) -> None:
        self.query_one("#start", Button).disabled = busy
        self.query_one("#cancel", Button).disabled = not busy

    def watch_ai_running(self, running: bool) -> None:
        button = self.query_one("#ai-assist", Button)
        button.disabled = running
        button.label = "Analyzing…" if running else "✦ AI Assist"

    # ── Video info ──────────────────────────────────────────────────

    def _on_url_changed(self, value: str) -> None:
        url = value.strip()
        self._set_field_error(FormField.URL, "")
        if self._url_timer is not None:
            self._url_timer.stop()

        if url and url == self._last_fetched_url:
            return  # Same URL (e.g. only whitespace changed); keep what's loaded.

        # Invalidate immediately: the debounce window must not leave the
        # previous video attached to a new URL, and in-flight results for the
        # old URL are dropped because they no longer match _last_fetched_url.
        self._last_fetched_url = ""
        self._clear_video()
        if not url or not is_valid_youtube_url(url):
            return
        self._url_timer = self.set_timer(
            URL_DEBOUNCE_SECONDS, lambda: self._start_video_info_fetch(url)
        )

    def _start_video_info_fetch(self, url: str) -> None:
        self._last_fetched_url = url
        self._video_info = None
        self.query_one(VideoPanel).show_loading()
        self._in_background(self._load_video_info, url)

    def _load_video_info(self, url: str) -> None:
        try:
            info = fetch_video_info(url, self._settings)
        except YouTubeBootleggerError as e:
            self._post(self._on_video_info_error, url, str(e))
            return
        except Exception as e:
            self._post(self._on_video_info_error, url, f"Unexpected error: {e}")
            return
        self._post(self._on_video_info_loaded, url, info)

    def _on_video_info_loaded(self, url: str, info: VideoInfo) -> None:
        if url != self._last_fetched_url:
            return  # A newer URL was entered while this one was loading.
        self._video_info = info
        self.query_one(VideoPanel).show_video(summarize_video(info))
        self.query_one("#album", Input).placeholder = info.title
        if self._show_thumbnail and info.thumbnail_url:
            self._in_background(self._load_thumbnail, info.video_id, info.thumbnail_url)

    def _on_video_info_error(self, url: str, message: str) -> None:
        if url != self._last_fetched_url:
            return
        self._video_info = None
        self._last_fetched_url = ""  # Allow retrying by re-entering the URL.
        self.query_one(VideoPanel).show_error(message)
        self._set_field_error(FormField.URL, message)

    def _load_thumbnail(self, video_id: str, thumbnail_url: str) -> None:
        try:
            image = fetch_thumbnail(thumbnail_url)
        except OSError:
            return  # The thumbnail is decorative; text info is already shown.
        self._post(self._on_thumbnail_loaded, video_id, image)

    def _on_thumbnail_loaded(self, video_id: str, image) -> None:
        if self._video_info is not None and self._video_info.video_id == video_id:
            self.query_one(VideoPanel).show_thumbnail(image)

    def _clear_video(self) -> None:
        self._video_info = None
        self.query_one(VideoPanel).show_placeholder()
        self.query_one("#album", Input).placeholder = "Defaults to video title"

    # ── Track list preview ──────────────────────────────────────────

    def _template(self) -> str:
        return self.query_one("#template", Input).value or DEFAULT_TEMPLATE

    def _on_template_changed(self, value: str) -> None:
        validation = validate_template(value)
        message = "" if validation.is_valid else (validation.error or "Invalid template")
        self._set_field_error(FormField.TEMPLATE, message)
        self._update_preview()

    def _update_preview(self) -> None:
        text = self.query_one("#tracklist", TextArea).text
        preview = preview_parse(text, self._template())
        self.query_one(TrackPreviewTable).show_tracks(preview.tracks)
        summary = summarize_preview(preview)
        status = self.query_one("#preview-status", Static)
        status.update(summary.status)
        status.set_class(not summary.is_valid, "-invalid")

    # ── Pipeline ────────────────────────────────────────────────────

    def action_start(self) -> None:
        if self.busy:
            return
        for field in FormField:
            self._set_field_error(field, "")
        result = build_job(self._read_form(), self._video_info)
        if isinstance(result, FormError):
            self._set_field_error(result.field, result.message)
            self.query_one(f"#{FOCUS_TARGET_IDS[result.field]}").focus()
            self.bell()
            return
        self._run_pipeline(result)

    def action_cancel(self) -> None:
        if self._pipeline is not None and self.busy:
            self._pipeline.cancel()
            self._log("Cancelling...", "warn")

    def _read_form(self) -> JobForm:
        return JobForm(
            url=self.query_one("#url", Input).value,
            template=self.query_one("#template", Input).value,
            tracklist_text=self.query_one("#tracklist", TextArea).text,
            artist=self.query_one("#artist", Input).value,
            album=self.query_one("#album", Input).value,
            output_dir=self.query_one("#output-dir", Input).value,
        )

    def _run_pipeline(self, job: DownloadJob) -> None:
        self.busy = True
        self.query_one(StatusLog).clear()
        self.query_one(ProgressPanel).set_progress("Starting...", 0)
        self._log(f"Starting: {job.track_count} track(s) → {job.output_dir}")
        self._pipeline_stopped.clear()
        self._pipeline = DownloadSplitPipeline(
            progress_callback=lambda *args: self._post(self._on_progress, *args),
            log_callback=lambda msg: self._post(self._log, msg, "debug"),
            settings=self._settings,
        )
        self._in_background(self._execute_pipeline, self._pipeline, job)

    def _execute_pipeline(self, pipeline: DownloadSplitPipeline, job: DownloadJob) -> None:
        try:
            output_files = pipeline.execute(job)
        except YouTubeBootleggerError as e:
            self._post(self._on_pipeline_error, str(e))
            return
        except Exception as e:
            self._post(self._on_pipeline_error, f"Unexpected error: {e}")
            return
        finally:
            self._pipeline_stopped.set()
        self._post(self._on_pipeline_finished, output_files)

    def _on_progress(self, stage: str, percent: float, message: str) -> None:
        self.query_one(ProgressPanel).set_progress(format_progress_stage(stage, percent), percent)
        self._log(message)

    def _on_pipeline_finished(self, output_files: list[Path]) -> None:
        self.busy = False
        self._pipeline = None
        if not output_files:
            self.query_one(ProgressPanel).set_progress("Cancelled")
            self._log("Cancelled.", "warn")
            return
        self.query_one(ProgressPanel).set_progress("Complete!", 100)
        self._log(f"Successfully created {len(output_files)} track(s)!")
        for path in output_files:
            self._log(f"  → {path}")
        self._notify(
            f"Successfully split audio into {len(output_files)} track(s)!",
            title="Complete",
        )

    def _on_pipeline_error(self, message: str) -> None:
        self.busy = False
        self._pipeline = None
        self.query_one(ProgressPanel).set_progress("Error")
        self._log(message, "error")
        self._notify(message, title="Error", severity="error", timeout=10)

    # ── AI assist ───────────────────────────────────────────────────

    def action_ai_assist(self) -> None:
        if self.ai_running:
            return
        tracklist = self.query_one("#tracklist", TextArea).text
        problem = check_ai_assist_ready(self._video_info, tracklist, self._settings)
        if problem:
            self._notify(problem, title="AI Assist", severity="warning")
            return
        title = self._video_info.title
        if self._settings.llm_provider == LlmProvider.CHATGPT_LITE:
            self._launch_chatgpt_lite(title, tracklist)
            return
        self.ai_running = True
        self._in_background(
            self._run_ai_extraction, self._video_info.video_id, title, tracklist
        )

    def _launch_chatgpt_lite(self, title: str, tracklist: str) -> None:
        ok, message = launch_chatgpt_lite_assist(
            title,
            tracklist,
            open_url=open_url_in_browser,
            copy_text=self.copy_to_clipboard,
        )
        if ok:
            self._notify(message, title="AI Assist", timeout=10)
            return
        # No GUI browser (e.g. over SSH): hand the prompt over via the clipboard.
        self.copy_to_clipboard(build_lite_prompt(title, tracklist))
        self._log("AI Assist: paste the copied prompt at https://chatgpt.com/", "warn")
        self._notify(
            "Couldn't open a browser here. The ChatGPT prompt was copied to your "
            "clipboard — paste it at https://chatgpt.com/ and copy the suggested "
            "template back.",
            title="AI Assist",
            severity="warning",
            timeout=15,
        )

    def _run_ai_extraction(self, video_id: str, title: str, tracklist: str) -> None:
        try:
            result = extract_tracklist_metadata(self._settings, title, tracklist)
        except LlmExtractionError as e:
            self._post(self._on_ai_error, str(e))
            return
        except Exception as e:
            self._post(self._on_ai_error, f"Unexpected error: {e}")
            return
        self._post(self._on_ai_finished, video_id, result)

    def _on_ai_finished(self, video_id: str, result: TracklistExtraction) -> None:
        self.ai_running = False
        if self._video_info is None or self._video_info.video_id != video_id:
            self._notify("Video changed during AI analysis; suggestion discarded.",
                         title="AI Assist", severity="warning")
            return
        self.query_one("#template", Input).value = result.template
        if result.artist_name:
            self.query_one("#artist", Input).value = result.artist_name
        if result.album_name:
            self.query_one("#album", Input).value = result.album_name
        self._notify("Template and metadata updated from AI suggestion.", title="AI Assist")

    def _on_ai_error(self, message: str) -> None:
        self.ai_running = False
        self._notify(message, title="AI Assist", severity="error", timeout=10)

    # ── Dialogs ─────────────────────────────────────────────────────

    def action_help(self) -> None:
        self.push_screen(HelpScreen(self.BINDINGS))

    def action_settings(self) -> None:
        def on_close(saved: bool | None) -> None:
            if saved:
                self._notify("Settings saved.")

        self.push_screen(SettingsScreen(self._settings), on_close)

    def action_browse(self) -> None:
        output_input = self.query_one("#output-dir", Input)

        def on_close(path: str | None) -> None:
            if path:
                output_input.value = path

        self.push_screen(DirectoryPickerScreen(output_input.value), on_close)

    async def action_quit(self) -> None:
        if not self.busy:
            self.exit()
            return

        async def on_close(confirmed: bool | None) -> None:
            if not confirmed:
                return
            if self._pipeline is not None:
                self._pipeline.cancel()
                self._log("Stopping...", "warn")
                # Cancel kills the running yt-dlp/ffmpeg at once; give the
                # worker a moment to delete temp and partial files. Wait off
                # the UI thread: the worker posts log lines to it while
                # cleaning up, so blocking here would deadlock.
                await asyncio.to_thread(
                    self._pipeline_stopped.wait, QUIT_CLEANUP_TIMEOUT_SECONDS
                )
            self.exit()

        self.push_screen(
            ConfirmScreen(
                "Quit?",
                "A download is still running. Quit anyway?",
                confirm_label="Quit",
            ),
            on_close,
        )

    # ── Helpers ─────────────────────────────────────────────────────

    def _in_background(self, fn: Callable[..., None], *args) -> None:
        """Run blocking work on a daemon thread.

        Textual's thread workers are joined on shutdown, so quitting during a
        long download would leave the terminal frozen until it finished.
        Daemon threads die with the process instead; results reach the UI
        through _post.
        """
        threading.Thread(target=fn, args=args, daemon=True).start()

    def _post(self, callback: Callable[..., None], *args) -> None:
        """Run callback on the UI thread; drop it if the app has exited."""
        if not self.is_running:
            return
        try:
            self.call_from_thread(callback, *args)
        except RuntimeError:
            if self.is_running:
                raise
            # Otherwise the app shut down mid-call (quit while a job ran).

    def _notify(self, message: str, **kwargs) -> None:
        """notify() with markup off: messages often carry titles and errors."""
        self.notify(message, markup=False, **kwargs)

    def _set_field_error(self, field: FormField, message: str) -> None:
        error = self.query_one(f"#{ERROR_WIDGET_IDS[field]}", Static)
        error.update(Text(message))
        error.display = bool(message)

    def _log(self, message: str, level: str = "info") -> None:
        self.query_one(StatusLog).log_message(message, level)
