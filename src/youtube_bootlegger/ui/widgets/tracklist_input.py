"""Tracklist/timestamp input widget with template support."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ...core import (
    DEFAULT_TEMPLATE,
    ParseError,
    parse_tracklist_with_template,
    preview_parse,
    validate_template,
)


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

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
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
            "Placeholders: %songname%, %hh%, %mm%, %ss%"
        )
        placeholders_label.setStyleSheet("color: #666; font-size: 11px;")
        template_header.addWidget(placeholders_label)
        template_header.addStretch()

        template_layout.addLayout(template_header)

        self._template_input = QLineEdit()
        self._template_input.setText(DEFAULT_TEMPLATE)
        self._template_input.setPlaceholderText(DEFAULT_TEMPLATE)
        template_layout.addWidget(self._template_input)

        self._template_error = QLabel()
        self._template_error.setStyleSheet("color: red; font-size: 11px;")
        self._template_error.hide()
        template_layout.addWidget(self._template_error)

        layout.addLayout(template_layout)

        tracklist_label = QLabel("Track List:")
        tracklist_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(tracklist_label)

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
        self._preview_frame.setStyleSheet("""
            QFrame {
                background-color: #fafafa;
                border: 1px solid #ddd;
                border-radius: 4px;
            }
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
        self._error_label.setStyleSheet("color: red;")
        self._error_label.setWordWrap(True)
        self._error_label.hide()
        layout.addWidget(self._error_label)

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
            placeholder.setStyleSheet("color: #999; font-style: italic;")
            self._preview_layout.insertWidget(0, placeholder)
            return

        if preview.is_valid:
            self._status_label.setText(f"{preview.total_lines} tracks")
            self._status_label.setStyleSheet("color: green; font-size: 11px;")
        else:
            self._status_label.setText(
                f"{preview.error_count} error(s)"
            )
            self._status_label.setStyleSheet("color: red; font-size: 11px;")

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
        index_label.setStyleSheet("color: #666; font-size: 11px;")
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
            widget.setStyleSheet("background-color: #e8f5e9; border-radius: 3px;")
        else:
            widget.setStyleSheet("background-color: #ffebee; border-radius: 3px;")
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
