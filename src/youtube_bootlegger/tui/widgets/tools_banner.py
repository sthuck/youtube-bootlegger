"""Banner above the form: runtime-tool download progress, errors and actions."""

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.message import Message
from textual.widgets import Button, ProgressBar, Static

from ...app_logic import BannerAction, ToolsBanner


class ToolsBannerBar(Horizontal):
    """Renders an app_logic.ToolsBanner; posts ActionPressed for its button."""

    class ActionPressed(Message):
        def __init__(self, action: BannerAction) -> None:
            super().__init__()
            self.action = action

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._action = BannerAction.NONE

    def compose(self) -> ComposeResult:
        yield Static("", id="tools-banner-text")
        yield ProgressBar(total=None, show_eta=False, id="tools-banner-progress")
        yield Button("", id="tools-banner-action", compact=True)

    def show(self, banner: ToolsBanner) -> None:
        self.display = banner.visible
        self.set_class(banner.is_error, "-error")
        self._action = banner.action
        self.query_one("#tools-banner-text", Static).update(Text(banner.text))

        bar = self.query_one("#tools-banner-progress", ProgressBar)
        downloading = banner.action == BannerAction.CANCEL
        bar.display = downloading or banner.progress is not None
        if banner.progress is None:
            bar.update(total=None)
        else:
            bar.update(total=100, progress=banner.progress * 100)

        button = self.query_one("#tools-banner-action", Button)
        button.display = banner.action != BannerAction.NONE
        button.label = banner.action_label

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        if self._action != BannerAction.NONE:
            self.post_message(self.ActionPressed(self._action))
