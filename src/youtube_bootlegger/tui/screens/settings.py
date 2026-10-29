"""Settings dialog: external tools and AI assist provider."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from rich.text import Text

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Select, Static, Switch

from ...app_logic import (
    AI_PROVIDERS_NOTE,
    FFMPEG_PATH_PLACEHOLDER,
    LOG_AI_REQUESTS_LABEL,
    TOOLS_SECTION_TITLE,
    YTDLP_PATH_PLACEHOLDER,
    log_ai_requests_note,
    status_text,
)
from ...app_logic.track_finder import AUTO_FIND_SETTING_LABEL, AUTO_FIND_SETTING_NOTE
from ...core.settings import (
    COOKIE_BROWSER_OPTIONS,
    COOKIE_BROWSER_TOOLTIP,
    AppSettings,
    LlmProvider,
)
from ...llm import (
    DEFAULT_ANTHROPIC_MODEL,
    DEFAULT_COMPATIBLE_MODEL,
    DEFAULT_OPENAI_MODEL,
    DEFAULT_VERTEX_MODEL,
)
from ...core.tools import ToolSource, tool_status
from ...utils import is_ffmpeg_available

if TYPE_CHECKING:
    from ..runtime_tools import ToolsDownloader

PROVIDER_OPTIONS = (
    ("Lite (ChatGPT in browser, no API key)", LlmProvider.CHATGPT_LITE),
    ("OpenAI", LlmProvider.OPENAI),
    ("Anthropic", LlmProvider.ANTHROPIC),
    ("Google Gemini (API key)", LlmProvider.VERTEX),
    ("OpenAI compatible", LlmProvider.OPENAI_COMPATIBLE),
)

@dataclass(frozen=True)
class SettingField:
    """A text setting bound to an AppSettings attribute."""

    attr: str
    label: str
    placeholder: str = ""
    password: bool = False


PROVIDER_FIELDS: dict[LlmProvider, tuple[SettingField, ...]] = {
    LlmProvider.OPENAI: (
        SettingField("openai_api_key", "OpenAI API key", password=True),
        SettingField("openai_model", "Model", DEFAULT_OPENAI_MODEL),
    ),
    LlmProvider.ANTHROPIC: (
        SettingField("anthropic_api_key", "Anthropic API key", password=True),
        SettingField("anthropic_model", "Model", DEFAULT_ANTHROPIC_MODEL),
    ),
    LlmProvider.VERTEX: (
        SettingField("vertex_api_key", "Google AI Studio API key", password=True),
        SettingField("vertex_model", "Model", DEFAULT_VERTEX_MODEL),
    ),
    LlmProvider.OPENAI_COMPATIBLE: (
        SettingField("compatible_base_url", "Base URL", "http://localhost:11434/v1"),
        SettingField("compatible_bearer_token", "Bearer token (optional)", password=True),
        SettingField("compatible_model", "Model", DEFAULT_COMPATIBLE_MODEL),
    ),
}

TOOL_FIELDS = (
    SettingField("ytdlp_path", "yt-dlp path", YTDLP_PATH_PLACEHOLDER),
    SettingField("ffmpeg_path", "ffmpeg path", FFMPEG_PATH_PLACEHOLDER),
)

NO_TOOLS_FOLDER_NOTE = "No folder for downloaded tools: downloads are turned off."


def _input_id(field: SettingField) -> str:
    return f"setting-{field.attr.replace('_', '-')}"


def _field_widgets(field: SettingField, settings: AppSettings) -> ComposeResult:
    yield Label(field.label, classes="field-label")
    yield Input(
        getattr(settings, field.attr),
        placeholder=field.placeholder,
        password=field.password,
        id=_input_id(field),
    )


class SettingsScreen(ModalScreen[bool]):
    """Edits AppSettings; dismisses with True when saved."""

    BINDINGS = [
        Binding("escape", "dismiss(False)", "Cancel"),
        Binding("ctrl+s", "save", "Save"),
    ]

    def __init__(self, settings: AppSettings, tools: ToolsDownloader | None = None) -> None:
        super().__init__()
        self._settings = settings
        self._tools = tools
        # Save only stores the switch when the user changed it: its default
        # turns on once yt-dlp is downloaded, maybe while this screen is open.
        self._loaded_use_external = settings.use_external_ytdlp

    def compose(self) -> ComposeResult:
        s = self._settings
        with Vertical(id="settings-dialog", classes="dialog"):
            yield Static("Settings", classes="dialog-title")
            with VerticalScroll(id="settings-body"):
                if self._tools is not None:
                    yield Static(TOOLS_SECTION_TITLE.upper(), classes="section-title")
                    yield Static("", id="tools-statuses")
                    yield Static(self._tools_folder_text(), id="tools-folder", classes="muted")
                    with Horizontal(id="tools-buttons"):
                        yield Button("Download missing", id="tools-download-missing")
                        yield Button("Verify", id="tools-verify")

                yield Static("EXTERNAL TOOLS", classes="section-title")
                with Horizontal(classes="switch-row"):
                    yield Switch(self._loaded_use_external, id="setting-use-external-ytdlp")
                    yield Label("Use external yt-dlp executable")
                for field in TOOL_FIELDS:
                    yield from _field_widgets(field, s)
                yield Static("", id="ffmpeg-warning", classes="field-error")
                with Horizontal(classes="label-row"):
                    yield Label("Browser cookies (age-restricted videos)", classes="field-label")
                    yield Static(" ⓘ", id="cookies-browser-info", classes="info-icon")
                yield Select(
                    COOKIE_BROWSER_OPTIONS,
                    value=s.cookies_from_browser,
                    allow_blank=False,
                    id="setting-cookies-from-browser",
                )

                yield Static("AI ASSISTANT", classes="section-title")
                yield Static(AI_PROVIDERS_NOTE, classes="muted")
                yield Select(
                    PROVIDER_OPTIONS,
                    value=s.llm_provider,
                    allow_blank=False,
                    id="setting-llm-provider",
                )
                for provider, fields in PROVIDER_FIELDS.items():
                    with Vertical(id=f"provider-{provider.value}", classes="provider-fields"):
                        for field in fields:
                            yield from _field_widgets(field, s)
                with Horizontal(classes="switch-row"):
                    yield Switch(s.auto_find_tracklist, id="setting-auto-find-tracklist")
                    yield Label(AUTO_FIND_SETTING_LABEL)
                yield Static(AUTO_FIND_SETTING_NOTE, classes="muted")
                with Horizontal(classes="switch-row"):
                    yield Switch(s.log_ai_requests, id="setting-log-ai-requests")
                    yield Label(LOG_AI_REQUESTS_LABEL)
                yield Static(log_ai_requests_note(s), classes="muted")
            with Horizontal(classes="dialog-buttons"):
                yield Button("Cancel", id="settings-cancel")
                yield Button("Save", variant="primary", id="settings-save")

    def on_mount(self) -> None:
        self._show_provider_fields(self._settings.llm_provider)
        self._refresh_ffmpeg_warning(self._settings.ffmpeg_path)
        self.refresh_tools()
        self.query_one("#cookies-browser-info", Static).tooltip = COOKIE_BROWSER_TOOLTIP
        self.query_one("#setting-cookies-from-browser", Select).tooltip = COOKIE_BROWSER_TOOLTIP

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "setting-llm-provider":
            self._show_provider_fields(event.value)

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "setting-ffmpeg-path":
            self._refresh_ffmpeg_warning(event.value)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        button_id = event.button.id
        if button_id == "settings-save":
            self.action_save()
        elif button_id == "settings-cancel":
            self.dismiss(False)
        elif self._tools is not None and button_id == "tools-download-missing":
            self._tools.start()
        elif self._tools is not None and button_id == "tools-verify":
            self._tools.start(verify=True)

    def refresh_tools(self) -> None:
        """Re-render tool statuses; the app calls this when a download changes."""
        if self._tools is None:
            return
        session = self._tools.session
        lines = Text()
        for status in session.statuses():
            if lines:
                lines.append("\n")
            lines.append(f"{status.label}: ", style="bold")
            lines.append(status_text(status))
        self.query_one("#tools-statuses", Static).update(lines)
        for button_id in ("#tools-download-missing", "#tools-verify"):
            self.query_one(button_id, Button).disabled = session.downloading
        self._refresh_ffmpeg_warning(self.query_one("#setting-ffmpeg-path", Input).value)

    def action_save(self) -> None:
        s = self._settings
        use_external = self.query_one("#setting-use-external-ytdlp", Switch).value
        if use_external != self._loaded_use_external:
            s.use_external_ytdlp = use_external
        s.cookies_from_browser = self.query_one("#setting-cookies-from-browser", Select).value
        s.llm_provider = self.query_one("#setting-llm-provider", Select).value
        s.auto_find_tracklist = self.query_one("#setting-auto-find-tracklist", Switch).value
        s.log_ai_requests = self.query_one("#setting-log-ai-requests", Switch).value
        all_fields = TOOL_FIELDS + tuple(f for fs in PROVIDER_FIELDS.values() for f in fs)
        for field in all_fields:
            setattr(s, field.attr, self.query_one(f"#{_input_id(field)}", Input).value)
        s.sync()
        self.dismiss(True)

    def _show_provider_fields(self, provider: LlmProvider) -> None:
        for container in self.query(".provider-fields"):
            container.display = container.id == f"provider-{provider}"

    def _tools_folder_text(self) -> Text:
        folder = self._settings.tools_dir
        return Text(f"Downloaded tools folder: {folder}" if folder else NO_TOOLS_FOLDER_NOTE)

    def _refresh_ffmpeg_warning(self, path: str) -> None:
        command = path.strip()
        if command:
            warning = "" if is_ffmpeg_available(command) else "FFmpeg not found at this location"
        else:
            # Empty means "downloaded copy, then PATH": ask the same lookup Start uses.
            status = tool_status("ffmpeg", self._settings.tool_store)
            warning = status_text(status) if status.source == ToolSource.MISSING else ""
        self.query_one("#ffmpeg-warning", Static).update(Text(warning))
