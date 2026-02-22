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
    """Widget displaying video thumbnail and details."""

    THUMBNAIL_WIDTH = 200
    THUMBNAIL_HEIGHT = 112  # 16:9 aspect ratio

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._network_manager = QNetworkAccessManager(self)
        self._network_manager.finished.connect(self._on_thumbnail_loaded)
        self._current_info: VideoInfo | None = None
        self._theme = ThemeColors()
        self._setup_ui()
        self.hide()

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
        self._thumbnail_label.setStyleSheet(f"""
            QLabel {{
                background-color: {self._theme.thumbnail_bg};
                border-radius: 4px;
                color: {self._theme.text_muted};
            }}
        """)
        self._thumbnail_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        frame_layout.addWidget(self._thumbnail_label)

        details_layout = QVBoxLayout()
        details_layout.setSpacing(5)

        self._title_label = QLabel()
        self._title_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._title_label.setWordWrap(True)
        self._title_label.setStyleSheet(f"""
            QLabel {{
                font-weight: bold;
                font-size: 14px;
                color: {self._theme.text_primary};
            }}
        """)
        details_layout.addWidget(self._title_label)

        self._channel_label = QLabel()
        self._channel_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._channel_label.setStyleSheet(f"""
            QLabel {{
                color: {self._theme.text_secondary};
                font-size: 12px;
            }}
        """)
        details_layout.addWidget(self._channel_label)

        info_row = QHBoxLayout()
        info_row.setSpacing(15)

        self._duration_label = QLabel()
        self._duration_label.setStyleSheet(f"""
            QLabel {{
                color: {self._theme.text_secondary};
                font-size: 12px;
            }}
        """)
        info_row.addWidget(self._duration_label)

        self._views_label = QLabel()
        self._views_label.setStyleSheet(f"""
            QLabel {{
                color: {self._theme.text_secondary};
                font-size: 12px;
            }}
        """)
        info_row.addWidget(self._views_label)

        self._date_label = QLabel()
        self._date_label.setStyleSheet(f"""
            QLabel {{
                color: {self._theme.text_secondary};
                font-size: 12px;
            }}
        """)
        info_row.addWidget(self._date_label)

        info_row.addStretch()
        details_layout.addLayout(info_row)

        details_layout.addStretch()
        frame_layout.addLayout(details_layout, 1)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(self._frame)

        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

    def _get_title_style(self, error: bool = False) -> str:
        """Get title label stylesheet."""
        color = self._theme.error_text if error else self._theme.text_primary
        return f"""
            QLabel {{
                font-weight: bold;
                font-size: 14px;
                color: {color};
            }}
        """

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

        self._channel_label.setText(info.channel)
        self._duration_label.setText(f"Duration: {info.duration_string}")
        self._views_label.setText(info.formatted_views)

        if info.formatted_date:
            self._date_label.setText(f"Uploaded: {info.formatted_date}")
            self._date_label.show()
        else:
            self._date_label.hide()

        self._load_thumbnail(info.thumbnail_url)
        self.show()

    def set_loading(self) -> None:
        """Show loading state."""
        self._title_label.setStyleSheet(self._get_title_style())
        self._title_label.setText("Loading video info...")
        self._channel_label.setText("")
        self._duration_label.setText("")
        self._views_label.setText("")
        self._date_label.setText("")
        self._thumbnail_label.setText("Loading...")
        self._thumbnail_label.setPixmap(QPixmap())
        self.show()

    def set_error(self, message: str) -> None:
        """Show error state.

        Args:
            message: Error message to display.
        """
        self._title_label.setText(f"Error: {message}")
        self._title_label.setStyleSheet(self._get_title_style(error=True))
        self._channel_label.setText("")
        self._duration_label.setText("")
        self._views_label.setText("")
        self._date_label.setText("")
        self._thumbnail_label.setText("")
        self._thumbnail_label.setPixmap(QPixmap())
        self.show()

    def clear(self) -> None:
        """Clear the preview and hide."""
        self._current_info = None
        self._title_label.setText("")
        self._title_label.setStyleSheet(self._get_title_style())
        self._channel_label.setText("")
        self._duration_label.setText("")
        self._views_label.setText("")
        self._date_label.setText("")
        self._thumbnail_label.setText("")
        self._thumbnail_label.setPixmap(QPixmap())
        self.hide()

    def get_video_info(self) -> VideoInfo | None:
        """Return the current video info."""
        return self._current_info

    def _load_thumbnail(self, url: str) -> None:
        """Load thumbnail from URL."""
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
