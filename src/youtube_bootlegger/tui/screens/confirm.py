"""Generic yes/no confirmation dialog."""

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Static


class ConfirmScreen(ModalScreen[bool]):
    """Asks a yes/no question; dismisses with True when confirmed."""

    BINDINGS = [Binding("escape", "dismiss(False)", "Cancel")]

    def __init__(self, title: str, message: str, confirm_label: str = "OK") -> None:
        super().__init__()
        self._title = title
        self._message = message
        self._confirm_label = confirm_label

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm-dialog", classes="dialog"):
            yield Static(self._title, classes="dialog-title")
            yield Static(self._message, id="confirm-message")
            with Horizontal(classes="dialog-buttons"):
                yield Button("Cancel", id="confirm-no")
                yield Button(self._confirm_label, variant="error", id="confirm-yes")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        self.dismiss(event.button.id == "confirm-yes")
