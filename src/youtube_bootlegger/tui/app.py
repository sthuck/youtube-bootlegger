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
    AiButtonMode,
    BannerAction,
    CancelReason,
    FormError,
    FormField,
    FormValues,
    JobForm,
    LogLine,
    TrackFinderSession,
    ai_button_label,
    ai_button_mode,
    build_job,
    check_ai_assist_ready,
    check_find_ready,
    fetch_config,
    format_progress_stage,
    preview_comment_limit,
    should_auto_find,
    should_refetch_video_info,
    summarize_preview,
    summarize_video,
    video_sources_log_line,
)
from ..app_logic.track_finder import (
    API_HINT_TEXT,
    OPEN_SETTINGS_LABEL,
    SEARCHING_TEXT,
    STOP_BUTTON_LABEL,
    TEMPLATE_SET_BY_AI_TEXT,
    UNDO_BUTTON_LABEL,
)
from ..core import DEFAULT_TEMPLATE, DownloadSplitPipeline, preview_parse, validate_template
from ..core.exceptions import YouTubeBootleggerError
from ..core.settings import AppSettings, LlmProvider, get_settings
from ..core.tool_installer import HttpGet, urlopen_get
from ..core.video_info import VideoInfo, fetch_video_info
from ..llm import (
    LlmExtractionError,
    TracklistExtraction,
    TracklistFindError,
    TracklistFindResult,
    build_lite_prompt,
    extract_tracklist_metadata,
    find_tracklist,
    launch_chatgpt_lite_assist,
)
from ..models import DownloadJob
from ..utils import is_valid_youtube_url
from .external import fetch_thumbnail, open_url_in_browser
from .runtime_tools import ToolsDownloader
from .screens import ConfirmScreen, DirectoryPickerScreen, HelpScreen, SettingsScreen
from .theme import BOOTLEGGER_THEME
from .widgets import ProgressPanel, StatusLog, ToolsBannerBar, TrackPreviewTable, VideoPanel

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

# Which message the row above the track list shows (at most one at a time).
FIND_ROW_SEARCHING = "searching"
FIND_ROW_BANNER = "banner"
FIND_ROW_HINT = "hint"

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
        tools_http_get: HttpGet = urlopen_get,
    ) -> None:
        super().__init__()
        self._settings = settings or get_settings()
        self._show_thumbnail = show_thumbnail
        self._video_info: VideoInfo | None = None
        self._last_fetched_url = ""
        self._video_request_id = 0
        self._url_timer: Timer | None = None
        self._pipeline: DownloadSplitPipeline | None = None
        self._pipeline_stopped = threading.Event()
        self._finder = TrackFinderSession()
        self._find_manual = False  # Whether the running search was a button click.
        self._find_row_state = ""
        self._tools = ToolsDownloader(
            self._settings,
            http_get=tools_http_get,
            run_in_background=self._in_background,
            post=self._post,
            on_change=self._refresh_tools_ui,
        )

    # ── Layout ──────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        yield Header()
        yield ToolsBannerBar(id="tools-banner")
        with Horizontal(id="main"):
            with Vertical(id="form"):
                yield Label("YouTube URL", classes="field-label")
                yield Input(placeholder="https://www.youtube.com/watch?v=...", id="url")
                yield Static("", id="url-error", classes="field-error")
                with Horizontal(id="tracks"):
                    with Vertical(id="tracklist-col"):
                        yield Label("Track list", classes="field-label")
                        with Vertical(id="find-row"):
                            yield Static("", id="find-text")
                            with Horizontal(id="find-buttons"):
                                yield Button(STOP_BUTTON_LABEL, id="find-stop", compact=True)
                                yield Button(UNDO_BUTTON_LABEL, id="find-undo", compact=True)
                                yield Button(
                                    OPEN_SETTINGS_LABEL, id="find-open-settings", compact=True
                                )
                                yield Button("✕", id="find-dismiss", compact=True)
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
                    yield Static(TEMPLATE_SET_BY_AI_TEXT, id="template-ai-marker")
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
        self._refresh_find_ui()
        self._tools.auto_start()

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
            self._log_line(self._finder.on_tracklist_edited(event.text_area.text))
            self._refresh_find_ui()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        actions = {
            "start": self.action_start,
            "cancel": self.action_cancel,
            "browse": self.action_browse,
            "ai-assist": self.action_ai_assist,
            "find-stop": self._stop_find,
            "find-undo": self._undo_find,
            "find-open-settings": self.action_settings,
            "find-dismiss": self._dismiss_find_row,
        }
        action = actions.get(event.button.id or "")
        if action:
            action()

    def watch_busy(self, busy: bool) -> None:
        self.query_one("#start", Button).disabled = busy
        self.query_one("#cancel", Button).disabled = not busy

    def watch_ai_running(self, running: bool) -> None:
        self._refresh_find_ui()

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
        self._video_request_id += 1
        self._clear_video()
        if not url or not is_valid_youtube_url(url):
            return
        self._url_timer = self.set_timer(
            URL_DEBOUNCE_SECONDS, lambda: self._start_video_info_fetch(url)
        )

    def _start_video_info_fetch(self, url: str) -> None:
        self._last_fetched_url = url
        self._video_info = None
        self._video_request_id += 1
        request_id = self._video_request_id
        self.query_one(VideoPanel).show_loading()
        self._in_background(self._load_video_info, url, request_id)

    def _load_video_info(self, url: str, request_id: int) -> None:
        try:
            info = fetch_video_info(
                url, self._settings, comment_limit=preview_comment_limit(self._settings)
            )
        except YouTubeBootleggerError as e:
            self._post(self._on_video_info_error, url, str(e), request_id)
            return
        except Exception as e:
            self._post(self._on_video_info_error, url, f"Unexpected error: {e}", request_id)
            return
        self._post(self._on_video_info_loaded, url, info, request_id)

    def _on_video_info_loaded(
        self, url: str, info: VideoInfo, request_id: int | None = None
    ) -> None:
        if url != self._last_fetched_url or (
            request_id is not None and request_id != self._video_request_id
        ):
            return  # A newer URL was entered while this one was loading.
        self._video_info = info
        self.query_one(VideoPanel).show_video(summarize_video(info))
        self.query_one("#album", Input).placeholder = info.title
        if self._show_thumbnail and info.thumbnail_url:
            self._in_background(self._load_thumbnail, info.video_id, info.thumbnail_url)
        self._log_line(video_sources_log_line(info, self._settings))
        self._refresh_find_ui()
        if should_auto_find(self._settings, info, self._tracklist_text()):
            self._start_find(info, manual=False)

    def _on_video_info_error(
        self, url: str, message: str, request_id: int | None = None
    ) -> None:
        if url != self._last_fetched_url or (
            request_id is not None and request_id != self._video_request_id
        ):
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
        values, line = self._finder.on_video_changed()
        self._log_line(line)
        if values is not None:
            self._write_form_values(values)
        self._refresh_find_ui()

    # ── Track list preview ──────────────────────────────────────────

    def _template(self) -> str:
        return self.query_one("#template", Input).value or DEFAULT_TEMPLATE

    def _on_template_changed(self, value: str) -> None:
        validation = validate_template(value)
        message = "" if validation.is_valid else (validation.error or "Invalid template")
        self._set_field_error(FormField.TEMPLATE, message)
        self._update_preview()
        self._refresh_find_ui()

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
        blocked = self._tools.session.start_blocked_reason()
        if blocked:
            self._log(blocked, "warn")
            self._notify(blocked, severity="warning", timeout=8)
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
        if self.ai_running or self._finder.searching:
            return
        tracklist = self.query_one("#tracklist", TextArea).text
        if ai_button_mode(tracklist) == AiButtonMode.FIND:
            problem = check_find_ready(self._video_info, self._settings)
            if problem:
                self._notify(problem, title="AI Assist", severity="warning")
                return
            self._start_find(self._video_info, manual=True)
            return
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

    # ── AI track-list finder ────────────────────────────────────────

    def _start_find(self, info: VideoInfo, *, manual: bool) -> None:
        token = self._finder.begin(info.video_id)
        cached = self._finder.cached(info.video_id)
        if cached is not None:
            self._on_find_finished(token, info.video_id, cached)
            return
        self._find_manual = manual
        self._refresh_find_ui()
        self._in_background(self._run_find, token, info)

    def _run_find(self, token: int, info: VideoInfo) -> None:
        try:
            result = find_tracklist(self._settings, info)
        except TracklistFindError as e:
            self._post(self._on_find_error, token, str(e))
            return
        except Exception as e:
            self._post(self._on_find_error, token, f"Unexpected error: {e}")
            return
        self._post(self._on_find_finished, token, info.video_id, result)

    def _on_find_finished(self, token: int, video_id: str, result: TracklistFindResult) -> None:
        application = self._finder.complete(token, video_id, result, self._form_values())
        if application is None:
            return  # Stopped, superseded, or the video changed meanwhile.
        if application.values is not None:
            self._write_form_values(application.values)
        for line in application.log:
            self._log_line(line)
        self._refresh_find_ui()

    def _on_find_error(self, token: int, message: str) -> None:
        line = self._finder.fail(token, message)
        if line is None:
            return
        self._log_line(line)
        if self._find_manual:
            self._notify(message, title="AI Assist", severity="error", timeout=10)
        self._refresh_find_ui()

    def _stop_find(self) -> None:
        self._log_line(self._finder.cancel(CancelReason.STOPPED))
        self._refresh_find_ui()

    def _undo_find(self) -> None:
        values = self._finder.undo()
        if values is not None:
            self._write_form_values(values)
        self._refresh_find_ui()

    def _dismiss_find_row(self) -> None:
        if self._find_row_state == FIND_ROW_BANNER:
            self._finder.dismiss_banner()
        elif self._find_row_state == FIND_ROW_HINT:
            self._finder.dismiss_api_hint()
        self._refresh_find_ui()

    def _form_values(self) -> FormValues:
        return FormValues(
            tracklist=self._tracklist_text(),
            template=self.query_one("#template", Input).value,
            artist=self.query_one("#artist", Input).value,
            album=self.query_one("#album", Input).value,
        )

    def _write_form_values(self, values: FormValues) -> None:
        # Template first, so the preview parses the new list with it.
        self.query_one("#template", Input).value = values.template
        self.query_one("#tracklist", TextArea).text = values.tracklist
        self.query_one("#artist", Input).value = values.artist
        self.query_one("#album", Input).value = values.album

    def _refresh_find_ui(self) -> None:
        tracklist = self._tracklist_text()
        button = self.query_one("#ai-assist", Button)
        button.disabled = self.ai_running or self._finder.searching
        if self.ai_running:
            button.label = "Analyzing…"
        else:
            button.label = f"✦ {ai_button_label(ai_button_mode(tracklist))}"

        if self._finder.searching:
            state, text = FIND_ROW_SEARCHING, SEARCHING_TEXT
        elif self._finder.banner:
            state, text = FIND_ROW_BANNER, self._finder.banner
        elif self._finder.show_api_hint(self._settings, self._video_info, tracklist):
            state, text = FIND_ROW_HINT, API_HINT_TEXT
        else:
            state, text = "", ""
        self._find_row_state = state
        self.query_one("#find-row").display = bool(state)
        self.query_one("#find-text", Static).update(Text(text))
        self.query_one("#find-row").set_class(state == FIND_ROW_HINT, "-hint")
        self.query_one("#find-stop").display = state == FIND_ROW_SEARCHING
        self.query_one("#find-undo").display = state == FIND_ROW_BANNER
        self.query_one("#find-open-settings").display = state == FIND_ROW_HINT
        self.query_one("#find-dismiss").display = state in (FIND_ROW_BANNER, FIND_ROW_HINT)

        template = self.query_one("#template", Input).value
        self.query_one("#template-ai-marker").display = self._finder.template_set_by_ai(template)

    # ── Runtime tools ───────────────────────────────────────────────

    def on_tools_banner_bar_action_pressed(self, event: ToolsBannerBar.ActionPressed) -> None:
        if event.action == BannerAction.CANCEL:
            self._tools.cancel()
        elif event.action == BannerAction.DOWNLOAD:
            self._tools.start()

    def _refresh_tools_ui(self) -> None:
        self.query_one(ToolsBannerBar).show(self._tools.session.banner())
        for screen in self.screen_stack:
            if isinstance(screen, SettingsScreen):
                screen.refresh_tools()

    # ── Dialogs ─────────────────────────────────────────────────────

    def action_help(self) -> None:
        self.push_screen(HelpScreen(self.BINDINGS))

    def action_settings(self) -> None:
        before = fetch_config(self._settings)

        def on_close(saved: bool | None) -> None:
            if saved:
                self._notify("Settings saved.")
                url = self.query_one("#url", Input).value.strip()
                if not self.busy and should_refetch_video_info(
                    before, fetch_config(self._settings), self._video_info, url
                ):
                    self._last_fetched_url = ""
                    self._on_url_changed(url)
                self._tools.auto_start()
            self._refresh_find_ui()
            self._refresh_tools_ui()

        self.push_screen(SettingsScreen(self._settings, self._tools), on_close)

    def action_browse(self) -> None:
        output_input = self.query_one("#output-dir", Input)

        def on_close(path: str | None) -> None:
            if path:
                output_input.value = path

        self.push_screen(DirectoryPickerScreen(output_input.value), on_close)

    async def action_quit(self) -> None:
        if not self.busy:
            self._tools.cancel()
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
            self._tools.cancel()
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

    def _log_line(self, line: LogLine | None) -> None:
        if line is not None:
            self._log(line.text, line.level)

    def _tracklist_text(self) -> str:
        return self.query_one("#tracklist", TextArea).text
