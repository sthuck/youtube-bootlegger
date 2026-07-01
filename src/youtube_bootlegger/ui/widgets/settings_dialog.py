"""Settings dialog for configuring external tool paths and LLM providers."""

from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QFileDialog,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ...llm import (
    DEFAULT_ANTHROPIC_MODEL,
    DEFAULT_COMPATIBLE_MODEL,
    DEFAULT_OPENAI_MODEL,
    DEFAULT_VERTEX_MODEL,
)
from ...core.settings import AppSettings, LlmProvider, get_settings


class SettingsDialog(QDialog):
    """Modal dialog for editing persisted application settings."""

    def __init__(self, parent: QWidget | None = None, settings: AppSettings | None = None):
        super().__init__(parent)
        self._settings = settings or get_settings()
        self.setWindowTitle("Settings")
        self.setMinimumWidth(520)
        self.setMinimumHeight(560)
        self._setup_ui()
        self._load_settings()

    def _setup_ui(self) -> None:
        outer = QVBoxLayout(self)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        outer.addWidget(scroll)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setSpacing(16)

        tools_group = QGroupBox("Tools")
        tools_form = QFormLayout(tools_group)
        tools_form.setSpacing(10)

        self._use_external_checkbox = QCheckBox("Use external yt-dlp executable")
        self._use_external_checkbox.toggled.connect(self._on_use_external_toggled)
        tools_form.addRow(self._use_external_checkbox)

        self._ytdlp_path_input, ytdlp_row = self._make_path_row(
            "Select yt-dlp executable",
            placeholder='Leave empty to use "yt-dlp" from PATH',
        )
        tools_form.addRow("yt-dlp path:", ytdlp_row)

        self._ffmpeg_path_input, ffmpeg_row = self._make_path_row(
            "Select ffmpeg executable",
            placeholder='Leave empty to use "ffmpeg" from PATH',
        )
        tools_form.addRow("ffmpeg path:", ffmpeg_row)
        layout.addWidget(tools_group)

        llm_group = QGroupBox("AI Assistant")
        llm_layout = QVBoxLayout(llm_group)
        llm_layout.setSpacing(10)

        self._llm_button_group = QButtonGroup(self)

        self._none_radio = QRadioButton("Disabled")
        self._openai_radio = QRadioButton("OpenAI")
        self._anthropic_radio = QRadioButton("Anthropic")
        self._vertex_radio = QRadioButton("Google Gemini (API key)")
        self._compatible_radio = QRadioButton("OpenAI compatible")

        for index, radio in enumerate(
            (
                self._none_radio,
                self._openai_radio,
                self._anthropic_radio,
                self._vertex_radio,
                self._compatible_radio,
            )
        ):
            self._llm_button_group.addButton(radio, index)
            llm_layout.addWidget(radio)

        llm_note = QLabel(
            "Credentials are stored locally. Track list text and video title "
            "are sent to the selected provider."
        )
        llm_note.setWordWrap(True)
        llm_note.setStyleSheet("color: gray; font-size: 11px;")
        llm_layout.addWidget(llm_note)

        self._openai_api_key = QLineEdit()
        self._openai_api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self._openai_model = QLineEdit()
        self._openai_model.setPlaceholderText(DEFAULT_OPENAI_MODEL)

        self._anthropic_api_key = QLineEdit()
        self._anthropic_api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self._anthropic_model = QLineEdit()
        self._anthropic_model.setPlaceholderText(DEFAULT_ANTHROPIC_MODEL)

        self._vertex_api_key = QLineEdit()
        self._vertex_api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self._vertex_model = QLineEdit()
        self._vertex_model.setPlaceholderText(DEFAULT_VERTEX_MODEL)

        self._compatible_base_url = QLineEdit()
        self._compatible_base_url.setPlaceholderText("https://api.example.com/v1")
        self._compatible_bearer_token = QLineEdit()
        self._compatible_bearer_token.setEchoMode(QLineEdit.EchoMode.Password)
        self._compatible_bearer_token.setPlaceholderText("Optional")
        self._compatible_model = QLineEdit()
        self._compatible_model.setPlaceholderText(DEFAULT_COMPATIBLE_MODEL)

        openai_form = QFormLayout()
        openai_form.addRow("API key:", self._openai_api_key)
        openai_form.addRow("Model:", self._openai_model)
        self._openai_form_widget = QWidget()
        self._openai_form_widget.setLayout(openai_form)
        llm_layout.addWidget(self._openai_form_widget)

        anthropic_form = QFormLayout()
        anthropic_form.addRow("API key:", self._anthropic_api_key)
        anthropic_form.addRow("Model:", self._anthropic_model)
        self._anthropic_form_widget = QWidget()
        self._anthropic_form_widget.setLayout(anthropic_form)
        llm_layout.addWidget(self._anthropic_form_widget)

        vertex_form = QFormLayout()
        vertex_form.addRow("Google AI Studio API key:", self._vertex_api_key)
        vertex_form.addRow("Model:", self._vertex_model)
        self._vertex_form_widget = QWidget()
        self._vertex_form_widget.setLayout(vertex_form)
        llm_layout.addWidget(self._vertex_form_widget)

        compatible_form = QFormLayout()
        compatible_form.addRow("Base URL:", self._compatible_base_url)
        compatible_form.addRow("Bearer token:", self._compatible_bearer_token)
        compatible_form.addRow("Model:", self._compatible_model)
        self._compatible_form_widget = QWidget()
        self._compatible_form_widget.setLayout(compatible_form)
        llm_layout.addWidget(self._compatible_form_widget)

        self._llm_provider_fields = {
            LlmProvider.OPENAI: (
                self._openai_radio,
                self._openai_form_widget,
            ),
            LlmProvider.ANTHROPIC: (
                self._anthropic_radio,
                self._anthropic_form_widget,
            ),
            LlmProvider.VERTEX: (
                self._vertex_radio,
                self._vertex_form_widget,
            ),
            LlmProvider.OPENAI_COMPATIBLE: (
                self._compatible_radio,
                self._compatible_form_widget,
            ),
        }

        self._llm_button_group.idClicked.connect(self._on_llm_provider_changed)
        self._update_llm_field_visibility()
        layout.addWidget(llm_group)

        scroll.setWidget(content)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

    def _make_path_row(self, dialog_title: str, placeholder: str) -> tuple[QLineEdit, QWidget]:
        """Build a text input + browse button row for picking an executable path."""
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)

        path_input = QLineEdit()
        path_input.setPlaceholderText(placeholder)
        row_layout.addWidget(path_input)

        browse_button = QPushButton("Browse...")
        browse_button.clicked.connect(lambda: self._on_browse(path_input, dialog_title))
        row_layout.addWidget(browse_button)

        return path_input, row

    def _on_browse(self, target: QLineEdit, dialog_title: str) -> None:
        """Open a file picker and write the chosen path into the target field."""
        path, _ = QFileDialog.getOpenFileName(self, dialog_title)
        if path:
            target.setText(path)

    def _on_use_external_toggled(self, checked: bool) -> None:
        """Enable the yt-dlp path field only when external mode is active."""
        self._ytdlp_path_input.setEnabled(checked)

    def _on_llm_provider_changed(self, _button_id: int) -> None:
        self._update_llm_field_visibility()

    def _update_llm_field_visibility(self) -> None:
        active = self._selected_llm_provider()
        for provider, (_radio, form_widget) in self._llm_provider_fields.items():
            form_widget.setVisible(provider == active)

    def _selected_llm_provider(self) -> LlmProvider:
        if self._none_radio.isChecked():
            return LlmProvider.NONE
        if self._openai_radio.isChecked():
            return LlmProvider.OPENAI
        if self._anthropic_radio.isChecked():
            return LlmProvider.ANTHROPIC
        if self._vertex_radio.isChecked():
            return LlmProvider.VERTEX
        if self._compatible_radio.isChecked():
            return LlmProvider.OPENAI_COMPATIBLE
        return LlmProvider.NONE

    def _load_settings(self) -> None:
        """Populate the form from the current persisted settings."""
        self._use_external_checkbox.setChecked(self._settings.use_external_ytdlp)
        self._ytdlp_path_input.setText(self._settings.ytdlp_path)
        self._ffmpeg_path_input.setText(self._settings.ffmpeg_path)
        self._ytdlp_path_input.setEnabled(self._settings.use_external_ytdlp)

        self._openai_api_key.setText(self._settings.openai_api_key)
        self._openai_model.setText(self._settings.openai_model)
        self._anthropic_api_key.setText(self._settings.anthropic_api_key)
        self._anthropic_model.setText(self._settings.anthropic_model)
        self._vertex_api_key.setText(self._settings.vertex_api_key)
        self._vertex_model.setText(self._settings.vertex_model)
        self._compatible_base_url.setText(self._settings.compatible_base_url)
        self._compatible_bearer_token.setText(self._settings.compatible_bearer_token)
        self._compatible_model.setText(self._settings.compatible_model)

        provider = self._settings.llm_provider
        radio_map = {
            LlmProvider.NONE: self._none_radio,
            LlmProvider.OPENAI: self._openai_radio,
            LlmProvider.ANTHROPIC: self._anthropic_radio,
            LlmProvider.VERTEX: self._vertex_radio,
            LlmProvider.OPENAI_COMPATIBLE: self._compatible_radio,
        }
        radio = radio_map.get(provider, self._none_radio)
        radio.setChecked(True)
        self._update_llm_field_visibility()

    def _on_save(self) -> None:
        """Persist the form values and close the dialog."""
        self._settings.use_external_ytdlp = self._use_external_checkbox.isChecked()
        self._settings.ytdlp_path = self._ytdlp_path_input.text()
        self._settings.ffmpeg_path = self._ffmpeg_path_input.text()

        self._settings.openai_api_key = self._openai_api_key.text()
        self._settings.openai_model = self._openai_model.text()
        self._settings.anthropic_api_key = self._anthropic_api_key.text()
        self._settings.anthropic_model = self._anthropic_model.text()
        self._settings.vertex_api_key = self._vertex_api_key.text()
        self._settings.vertex_model = self._vertex_model.text()
        self._settings.compatible_base_url = self._compatible_base_url.text()
        self._settings.compatible_bearer_token = self._compatible_bearer_token.text()
        self._settings.compatible_model = self._compatible_model.text()

        self._settings.llm_provider = self._selected_llm_provider()

        self._settings.sync()
        self.accept()
