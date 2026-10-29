"""Tracklist/timestamp input widget with template support."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ...app_logic.track_finder import (
    API_HINT_TEXT,
    FIND_BUTTON_LABEL,
    OPEN_SETTINGS_LABEL,
    SEARCHING_TEXT,
    STOP_BUTTON_LABEL,
    TEMPLATE_SET_BY_AI_TEXT,
    UNDO_BUTTON_LABEL,
)
from ...core import (
    DEFAULT_TEMPLATE,
    ParseError,
    parse_tracklist_with_template,
    preview_parse,
    validate_template,
)
from ..theme import ThemeColors


class TracklistInputWidget(QWidget):
    """Widget for tracklist/timestamp input with template support."""

    PLACEHOLDER = """Enter one track per line matching your template.

Example (with default template):
Opening Number - 0:00
Second Song - 4:32
Third Song - 8:15
Final Song - 12:47"""

    template_changed = Signal(str)
    tracklist_changed = Signal()
    ai_requested = Signal()
    stop_find_requested = Signal()
    undo_find_requested = Signal()
    find_banner_dismissed = Signal()
    open_settings_requested = Signal()
    api_hint_dismissed = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._theme = ThemeColors()
        self._ai_available = False
        self._ai_loading = False
        self._setup_ui()
        self._connect_signals()
        self._update_preview()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        template_layout = QVBoxLayout()
        template_layout.setSpacing(4)

        template_header = QHBoxLayout()
        template_label = QLabel("Template:")
        template_label.setStyleSheet("font-weight: bold;")
        template_header.addWidget(template_label)

        placeholders_label = QLabel(
            "Placeholders: %songname%, %hh%, %mm%, %ss%, %ignore:regex%"
        )
        placeholders_label.setStyleSheet(
            f"color: {self._theme.text_secondary}; font-size: 11px;"
        )
        template_header.addWidget(placeholders_label)
        template_header.addStretch()

        self._template_ai_marker = QLabel(f"✨ {TEMPLATE_SET_BY_AI_TEXT}")
        self._template_ai_marker.setStyleSheet(
            f"color: {self._theme.primary}; font-size: 11px;"
        )
        self._template_ai_marker.hide()
        template_header.addWidget(self._template_ai_marker)

        template_layout.addLayout(template_header)

        self._template_input = QLineEdit()
        self._template_input.setText(DEFAULT_TEMPLATE)
        self._template_input.setPlaceholderText(DEFAULT_TEMPLATE)
        template_layout.addWidget(self._template_input)

        self._template_error = QLabel()
        self._template_error.setStyleSheet(
            f"color: {self._theme.error_text}; font-size: 11px;"
        )
        self._template_error.hide()
        template_layout.addWidget(self._template_error)

        layout.addLayout(template_layout)

        tracklist_header = QHBoxLayout()
        tracklist_label = QLabel("Track List:")
        tracklist_label.setStyleSheet("font-weight: bold;")
        tracklist_header.addWidget(tracklist_label)
        tracklist_header.addStretch()

        self._ai_button = QPushButton(FIND_BUTTON_LABEL)
        self._ai_button.setToolTip(
            "Empty track list: find one in the video with AI. "
            "Filled track list: infer the template and metadata with AI."
        )
        self._ai_button.setEnabled(False)
        self._ai_button.clicked.connect(self.ai_requested.emit)
        tracklist_header.addWidget(self._ai_button)

        self._ai_spinner = QProgressBar()
        self._ai_spinner.setRange(0, 0)
        self._ai_spinner.setFixedWidth(80)
        self._ai_spinner.hide()
        tracklist_header.addWidget(self._ai_spinner)

        layout.addLayout(tracklist_header)

        # Only one of these rows shows at a time (MainWindow decides which).
        self._searching_row, self._searching_label = self._make_notice_row(
            SEARCHING_TEXT, [(STOP_BUTTON_LABEL, self.stop_find_requested)]
        )
        layout.addWidget(self._searching_row)

        self._banner_row, self._banner_label = self._make_notice_row(
            "",
            [
                (UNDO_BUTTON_LABEL, self.undo_find_requested),
                ("✕", self.find_banner_dismissed),
            ],
        )
        layout.addWidget(self._banner_row)

        self._hint_row, self._hint_label = self._make_notice_row(
            f"ⓘ {API_HINT_TEXT}",
            [
                (OPEN_SETTINGS_LABEL, self.open_settings_requested),
                ("✕", self.api_hint_dismissed),
            ],
        )
        layout.addWidget(self._hint_row)

        input_preview_layout = QHBoxLayout()
        input_preview_layout.setSpacing(10)

        input_container = QVBoxLayout()
        self._input = QPlainTextEdit()
        self._input.setPlaceholderText(self.PLACEHOLDER)
        self._input.setMinimumHeight(120)
        self._input.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        input_container.addWidget(self._input)
        input_preview_layout.addLayout(input_container, 1)

        preview_container = QVBoxLayout()
        preview_header = QHBoxLayout()

        preview_title = QLabel("Preview:")
        preview_title.setStyleSheet("font-weight: bold;")
        preview_header.addWidget(preview_title)

        self._status_label = QLabel()
        self._status_label.setStyleSheet("font-size: 11px;")
        preview_header.addWidget(self._status_label)
        preview_header.addStretch()

        preview_container.addLayout(preview_header)

        self._preview_frame = QFrame()
        self._preview_frame.setFrameStyle(
            QFrame.Shape.StyledPanel | QFrame.Shadow.Sunken
        )
        self._preview_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {self._theme.input_bg};
                border: 1px solid {self._theme.input_border};
                border-radius: 4px;
            }}
        """)

        preview_frame_layout = QVBoxLayout(self._preview_frame)
        preview_frame_layout.setContentsMargins(0, 0, 0, 0)

        self._preview_scroll = QScrollArea()
        self._preview_scroll.setWidgetResizable(True)
        self._preview_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._preview_scroll.setStyleSheet("""
            QScrollArea {
                border: none;
                background-color: transparent;
            }
        """)

        self._preview_content = QWidget()
        self._preview_layout = QVBoxLayout(self._preview_content)
        self._preview_layout.setContentsMargins(8, 8, 8, 8)
        self._preview_layout.setSpacing(4)
        self._preview_layout.addStretch()

        self._preview_scroll.setWidget(self._preview_content)
        preview_frame_layout.addWidget(self._preview_scroll)

        self._preview_frame.setMinimumHeight(120)
        self._preview_frame.setMinimumWidth(250)
        preview_container.addWidget(self._preview_frame)

        input_preview_layout.addLayout(preview_container, 1)
        layout.addLayout(input_preview_layout)

        self._error_label = QLabel()
        self._error_label.setStyleSheet(f"color: {self._theme.error_text};")
        self._error_label.setWordWrap(True)
        self._error_label.hide()
        layout.addWidget(self._error_label)

    def _make_notice_row(
        self, text: str, buttons: list[tuple[str, Signal]]
    ) -> tuple[QFrame, QLabel]:
        """Build a hidden row of wrapped text plus buttons that emit the given signals."""
        row = QFrame()
        row.setStyleSheet(f"""
            QFrame {{
                background-color: {self._theme.preview_bg};
                border: 1px solid {self._theme.preview_border};
                border-radius: 4px;
            }}
            QLabel {{ border: none; }}
        """)
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(8, 4, 8, 4)

        label = QLabel(text)
        label.setWordWrap(True)
        row_layout.addWidget(label, 1)

        for button_text, signal in buttons:
            button = QPushButton(button_text)
            if button_text == "✕":
                button.setFixedWidth(28)
                button.setToolTip("Dismiss")
            button.clicked.connect(signal.emit)
            row_layout.addWidget(button)

        row.hide()
        return row, label

    def _connect_signals(self) -> None:
        self._template_input.textChanged.connect(self._on_template_changed)
        self._input.textChanged.connect(self._on_tracklist_changed)

    def _on_template_changed(self, text: str) -> None:
        validation = validate_template(text)
        if validation.is_valid:
            self._template_error.hide()
            self._template_input.setStyleSheet("")
        else:
            self._template_error.setText(validation.error or "Invalid template")
            self._template_error.show()
            self._template_input.setStyleSheet("border: 1px solid orange;")

        self._update_preview()
        self.template_changed.emit(text)

    def _on_tracklist_changed(self) -> None:
        self._update_preview()
        self.tracklist_changed.emit()

    def set_ai_available(self, available: bool) -> None:
        """Enable or disable the AI assist button when not loading."""
        self._ai_available = available
        self._refresh_ai_state()

    def set_ai_loading(self, loading: bool) -> None:
        """Show or hide the AI loading spinner."""
        self._ai_loading = loading
        self._ai_button.setVisible(not loading)
        self._ai_spinner.setVisible(loading)
        self._refresh_ai_state()

    def _refresh_ai_state(self) -> None:
        self._ai_button.setEnabled(self._ai_available and not self._ai_loading)

    def set_ai_button_label(self, label: str) -> None:
        """Set the AI button's label (it follows the button's mode)."""
        self._ai_button.setText(label)

    def set_find_state(self, searching: bool, banner: str, show_hint: bool) -> None:
        """Show at most one of the searching row, the AI banner and the API hint.

        Priority: searching, then banner (non-empty text), then hint.
        """
        self._searching_row.setVisible(searching)
        self._banner_label.setText(banner)
        self._banner_row.setVisible(not searching and bool(banner))
        self._hint_row.setVisible(not searching and not banner and show_hint)

    def set_template_set_by_ai(self, visible: bool) -> None:
        """Show or hide the "set by AI" marker next to the template field."""
        self._template_ai_marker.setVisible(visible)

    def set_text(self, text: str) -> None:
        """Set the tracklist text programmatically."""
        self._input.setPlainText(text)

    def set_template(self, template: str) -> None:
        """Set the template text programmatically."""
        self._template_input.setText(template)
        self._on_template_changed(template)

    def _update_preview(self) -> None:
        while self._preview_layout.count() > 1:
            item = self._preview_layout.takeAt(0)
            if item:
                widget = item.widget()
                if widget:
                    widget.deleteLater()

        template = self._template_input.text() or DEFAULT_TEMPLATE
        text = self._input.toPlainText()

        preview = preview_parse(text, template)

        if preview.total_lines == 0:
            self._status_label.setText("")
            self._status_label.setStyleSheet("font-size: 11px;")
            placeholder = QLabel("Enter tracks to see preview")
            placeholder.setStyleSheet(
                f"color: {self._theme.text_muted}; font-style: italic;"
            )
            self._preview_layout.insertWidget(0, placeholder)
            return

        if preview.is_valid:
            self._status_label.setText(f"{preview.total_lines} tracks")
            self._status_label.setStyleSheet(
                f"color: {self._theme.success_text}; font-size: 11px;"
            )
        else:
            self._status_label.setText(
                f"{preview.error_count} error(s)"
            )
            self._status_label.setStyleSheet(
                f"color: {self._theme.error_text}; font-size: 11px;"
            )

        for i, track in enumerate(preview.tracks):
            track_widget = self._create_track_preview_widget(i + 1, track)
            self._preview_layout.insertWidget(
                self._preview_layout.count() - 1, track_widget
            )

    def _create_track_preview_widget(self, index: int, track) -> QWidget:
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(8)

        index_label = QLabel(f"{index:02d}.")
        index_label.setFixedWidth(25)
        index_label.setStyleSheet(
            f"color: {self._theme.text_secondary}; font-size: 11px;"
        )
        layout.addWidget(index_label)

        time_label = QLabel(track.timestamp)
        time_label.setFixedWidth(50)
        time_label.setStyleSheet("font-family: monospace; font-size: 11px;")
        layout.addWidget(time_label)

        name_label = QLabel(track.name)
        name_label.setStyleSheet("font-size: 11px;")
        name_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        layout.addWidget(name_label)

        if track.is_valid:
            widget.setStyleSheet(
                f"background-color: {self._theme.success_bg}; border-radius: 3px;"
            )
        else:
            widget.setStyleSheet(
                f"background-color: {self._theme.error_bg}; border-radius: 3px;"
            )
            name_label.setToolTip(track.error or "Parse error")

        return widget

    def get_text(self) -> str:
        """Return the tracklist text."""
        return self._input.toPlainText()

    def get_template(self) -> str:
        """Return the current template."""
        return self._template_input.text() or DEFAULT_TEMPLATE

    def validate(self) -> tuple[bool, str]:
        """Validate template and tracklist.

        Returns:
            Tuple of (is_valid, error_message).
        """
        template = self.get_template()
        template_validation = validate_template(template)
        if not template_validation.is_valid:
            return False, f"Invalid template: {template_validation.error}"

        text = self.get_text()
        if not text.strip():
            return False, "Please enter at least one track"

        try:
            tracks = parse_tracklist_with_template(text, template)
            if not tracks:
                return False, "No valid tracks found"
            return True, ""
        except ParseError as e:
            return False, str(e)

    def set_error(self, message: str) -> None:
        """Display validation error."""
        self._error_label.setText(message)
        self._error_label.show()
        self._input.setStyleSheet("border: 1px solid red;")

    def clear_error(self) -> None:
        """Clear validation error display."""
        self._error_label.hide()
        self._input.setStyleSheet("")

    def set_enabled(self, enabled: bool) -> None:
        """Enable or disable the inputs."""
        self._template_input.setEnabled(enabled)
        self._input.setEnabled(enabled)
