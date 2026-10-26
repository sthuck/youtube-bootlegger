"""Video info card with an optional terminal-rendered thumbnail."""

from PIL import Image as PILImage
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static
from textual_image.widget import Image

from ...app_logic import VideoSummary

PLACEHOLDER = "Paste a YouTube URL to see video info."


class VideoPanel(Vertical):
    """Shows thumbnail, title, channel, duration, views and upload date."""

    def __init__(self, *, show_thumbnail: bool = True, **kwargs) -> None:
        super().__init__(**kwargs)
        self._show_thumbnail = show_thumbnail

    def compose(self) -> ComposeResult:
        if self._show_thumbnail:
            yield Image(id="thumbnail")
        yield Static(PLACEHOLDER, id="video-title")
        yield Static("", id="video-channel")
        yield Static("", id="video-details")

    def show_loading(self) -> None:
        self._clear_thumbnail()
        self._set_text("Loading video info...", "", "")
        self.remove_class("-error")

    def show_error(self, message: str) -> None:
        self._clear_thumbnail()
        self._set_text(message, "", "")
        self.add_class("-error")

    def show_placeholder(self) -> None:
        self._clear_thumbnail()
        self._set_text(PLACEHOLDER, "", "")
        self.remove_class("-error")

    def show_video(self, summary: VideoSummary) -> None:
        details = "\n".join(
            part for part in (summary.duration, summary.views, summary.date) if part
        )
        self._set_text(summary.title, summary.channel, details)
        self.remove_class("-error")

    def show_thumbnail(self, image: PILImage.Image) -> None:
        if self._show_thumbnail:
            self.query_one("#thumbnail", Image).image = image

    def _clear_thumbnail(self) -> None:
        if self._show_thumbnail:
            self.query_one("#thumbnail", Image).image = None

    def _set_text(self, title: str, channel: str, details: str) -> None:
        # Text (not str) so titles like "Live [Full Concert]" aren't parsed as markup.
        self.query_one("#video-title", Static).update(Text(title))
        self.query_one("#video-channel", Static).update(Text(channel))
        self.query_one("#video-details", Static).update(Text(details))
