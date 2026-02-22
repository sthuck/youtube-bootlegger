"""Video preview widget showing thumbnail and details."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ...core.video_info import VideoInfo
from ..theme import ThemeColors


class VideoPreviewWidget(QWidget):
    """Widget displaying video thumbnail and details with skeleton state."""

    THUMBNAIL_WIDTH = 200
    THUMBNAIL_HEIGHT = 112  # 16:9 aspect ratio

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._network_manager = QNetworkAccessManager(self)
        self._network_manager.finished.connect(self._on_thumbnail_loaded)
        self._current_info: VideoInfo | None = None
        self._theme = ThemeColors()
        self._setup_ui()
        self._show_skeleton()

    def _setup_ui(self) -> None:
        self._frame = QFrame()
        self._frame.setFrameStyle(QFrame.Shape.StyledPanel | QFrame.Shadow.Raised)
        self._frame.setStyleSheet(f"""
            QFrame {{
                background-color: {self._theme.preview_bg};
                border: 1px solid {self._theme.preview_border};
                border-radius: 8px;
                padding: 10px;
            }}
        """)

        frame_layout = QHBoxLayout(self._frame)
        frame_layout.setContentsMargins(10, 10, 10, 10)
        frame_layout.setSpacing(15)

        self._thumbnail_label = QLabel()
        self._thumbnail_label.setFixedSize(self.THUMBNAIL_WIDTH, self.THUMBNAIL_HEIGHT)
        self._thumbnail_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        frame_layout.addWidget(self._thumbnail_label)

        details_layout = QVBoxLayout()
        details_layout.setSpacing(5)

        self._title_label = QLabel()
        self._title_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._title_label.setWordWrap(True)
        self._title_label.setMinimumHeight(20)
        details_layout.addWidget(self._title_label)

        self._channel_label = QLabel()
        self._channel_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._channel_label.setMinimumHeight(16)
        details_layout.addWidget(self._channel_label)

        info_row = QHBoxLayout()
        info_row.setSpacing(15)

        self._duration_label = QLabel()
        self._duration_label.setMinimumHeight(16)
        info_row.addWidget(self._duration_label)

        self._views_label = QLabel()
        self._views_label.setMinimumHeight(16)
        info_row.addWidget(self._views_label)

        self._date_label = QLabel()
        self._date_label.setMinimumHeight(16)
        info_row.addWidget(self._date_label)

        info_row.addStretch()
        details_layout.addLayout(info_row)

        details_layout.addStretch()
        frame_layout.addLayout(details_layout, 1)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(self._frame)

        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.setMinimumHeight(self.THUMBNAIL_HEIGHT + 40)

    def _get_skeleton_style(self) -> str:
        """Get skeleton placeholder bar style."""
        return f"""
            QLabel {{
                background-color: {self._theme.input_border};
                border-radius: 4px;
                min-height: 12px;
            }}
        """

    def _get_thumbnail_style(self, skeleton: bool = False) -> str:
        """Get thumbnail label style."""
        return f"""
            QLabel {{
                background-color: {self._theme.thumbnail_bg};
                border-radius: 4px;
                color: {self._theme.thumbnail_text};
            }}
        """

    def _get_title_style(self, error: bool = False, skeleton: bool = False) -> str:
        """Get title label stylesheet."""
        if skeleton:
            return f"""
                QLabel {{
                    background-color: {self._theme.input_border};
                    border-radius: 4px;
                    min-height: 16px;
                    max-width: 300px;
                }}
            """
        color = self._theme.error_text if error else self._theme.text_primary
        return f"""
            QLabel {{
                font-weight: bold;
                font-size: 14px;
                color: {color};
                background-color: transparent;
            }}
        """

    def _get_secondary_style(self, skeleton: bool = False) -> str:
        """Get secondary text style."""
        if skeleton:
            return f"""
                QLabel {{
                    background-color: {self._theme.input_border};
                    border-radius: 3px;
                    min-height: 12px;
                    max-width: 120px;
                }}
            """
        return f"""
            QLabel {{
                color: {self._theme.text_secondary};
                font-size: 12px;
                background-color: transparent;
            }}
        """

    def _get_info_style(self, skeleton: bool = False) -> str:
        """Get info label style."""
        if skeleton:
            return f"""
                QLabel {{
                    background-color: {self._theme.input_border};
                    border-radius: 3px;
                    min-height: 10px;
                    min-width: 60px;
                    max-width: 80px;
                }}
            """
        return f"""
            QLabel {{
                color: {self._theme.text_secondary};
                font-size: 12px;
                background-color: transparent;
            }}
        """

    def _show_skeleton(self) -> None:
        """Show skeleton placeholder state."""
        self._current_info = None

        self._thumbnail_label.setText("")
        self._thumbnail_label.setPixmap(QPixmap())
        self._thumbnail_label.setStyleSheet(self._get_thumbnail_style(skeleton=True))

        # self._title_label.setText("")
        # self._title_label.setStyleSheet(self._get_title_style(skeleton=True))

        # self._channel_label.setText("")
        # self._channel_label.setStyleSheet(self._get_secondary_style(skeleton=True))

        # self._duration_label.setText("")
        # self._duration_label.setStyleSheet(self._get_info_style(skeleton=True))

        # self._views_label.setText("")
        # self._views_label.setStyleSheet(self._get_info_style(skeleton=True))

        # self._date_label.setText("")
        # self._date_label.setStyleSheet(self._get_info_style(skeleton=True))
        # self._date_label.show()

    def set_video_info(self, info: VideoInfo) -> None:
        """Display video information.

        Args:
            info: VideoInfo object with video details.
        """
        self._current_info = info

        self._title_label.setStyleSheet(self._get_title_style())
        title = info.title
        if len(title) > 80:
            title = title[:77] + "..."
        self._title_label.setText(title)

        self._channel_label.setStyleSheet(self._get_secondary_style())
        self._channel_label.setText(info.channel)

        self._duration_label.setStyleSheet(self._get_info_style())
        self._duration_label.setText(f"Duration: {info.duration_string}")

        self._views_label.setStyleSheet(self._get_info_style())
        self._views_label.setText(info.formatted_views)

        self._date_label.setStyleSheet(self._get_info_style())
        if info.formatted_date:
            self._date_label.setText(f"Uploaded: {info.formatted_date}")
            self._date_label.show()
        else:
            self._date_label.hide()

        self._load_thumbnail(info.thumbnail_url)

    def set_loading(self) -> None:
        """Show loading state."""
        self._current_info = None

        self._thumbnail_label.setStyleSheet(self._get_thumbnail_style())
        self._thumbnail_label.setText("Loading...")
        self._thumbnail_label.setPixmap(QPixmap())

        self._title_label.setStyleSheet(self._get_title_style())
        self._title_label.setText("Loading video info...")

        self._channel_label.setStyleSheet(self._get_secondary_style())
        self._channel_label.setText("")

        self._duration_label.setStyleSheet(self._get_info_style())
        self._duration_label.setText("")

        self._views_label.setStyleSheet(self._get_info_style())
        self._views_label.setText("")

        self._date_label.setStyleSheet(self._get_info_style())
        self._date_label.setText("")

    def set_error(self, message: str) -> None:
        """Show error state.

        Args:
            message: Error message to display.
        """
        self._current_info = None

        self._thumbnail_label.setStyleSheet(self._get_thumbnail_style())
        self._thumbnail_label.setText("")
        self._thumbnail_label.setPixmap(QPixmap())

        self._title_label.setStyleSheet(self._get_title_style(error=True))
        self._title_label.setText(f"Error: {message}")

        self._channel_label.setStyleSheet(self._get_secondary_style())
        self._channel_label.setText("")

        self._duration_label.setStyleSheet(self._get_info_style())
        self._duration_label.setText("")

        self._views_label.setStyleSheet(self._get_info_style())
        self._views_label.setText("")

        self._date_label.setStyleSheet(self._get_info_style())
        self._date_label.setText("")

    def clear(self) -> None:
        """Clear the preview and show skeleton."""
        self._show_skeleton()

    def get_video_info(self) -> VideoInfo | None:
        """Return the current video info."""
        return self._current_info

    def _load_thumbnail(self, url: str) -> None:
        """Load thumbnail from URL."""
        self._thumbnail_label.setStyleSheet(self._get_thumbnail_style())

        if not url:
            self._thumbnail_label.setText("No thumbnail")
            return

        self._thumbnail_label.setText("Loading...")
        request = QNetworkRequest(url)
        self._network_manager.get(request)

    def _on_thumbnail_loaded(self, reply: QNetworkReply) -> None:
        """Handle thumbnail download completion."""
        if reply.error() == QNetworkReply.NetworkError.NoError:
            data = reply.readAll()
            pixmap = QPixmap()
            if pixmap.loadFromData(data):
                scaled = pixmap.scaled(
                    self.THUMBNAIL_WIDTH,
                    self.THUMBNAIL_HEIGHT,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                self._thumbnail_label.setPixmap(scaled)
            else:
                self._thumbnail_label.setText("Load failed")
        else:
            self._thumbnail_label.setText("Load failed")

        reply.deleteLater()
