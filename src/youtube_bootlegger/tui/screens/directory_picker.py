"""Directory browser dialog replacing the native folder picker."""

from pathlib import Path

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, DirectoryTree, Input, Static


class FoldersOnlyTree(DirectoryTree):
    """DirectoryTree that hides files and dot-directories."""

    def filter_paths(self, paths):
        return [p for p in paths if p.is_dir() and not p.name.startswith(".")]


def _starting_root(initial: str) -> Path:
    """Pick an existing directory to root the tree at."""
    path = Path(initial).expanduser() if initial.strip() else Path.home()
    while not path.is_dir() and path != path.parent:
        path = path.parent
    return path if path.is_dir() else Path.home()


class DirectoryPickerScreen(ModalScreen[str | None]):
    """Pick a directory by browsing or typing; dismisses with the path or None."""

    BINDINGS = [
        Binding("escape", "dismiss(None)", "Cancel"),
        Binding("backspace", "go_up", "Parent folder", show=False),
    ]

    def __init__(self, initial: str) -> None:
        super().__init__()
        self._initial = initial

    def compose(self) -> ComposeResult:
        root = _starting_root(self._initial)
        with Vertical(id="dir-dialog", classes="dialog"):
            yield Static("Choose output directory", classes="dialog-title")
            with Horizontal(id="dir-path-row"):
                yield Button("↑ Up", id="dir-up")
                yield Input(str(root), id="dir-path")
            yield FoldersOnlyTree(root, id="dir-tree")
            with Horizontal(classes="dialog-buttons"):
                yield Button("Cancel", id="dir-cancel")
                yield Button("Select", variant="primary", id="dir-select")

    def on_mount(self) -> None:
        self.query_one("#dir-tree").focus()

    def on_directory_tree_directory_selected(
        self, event: DirectoryTree.DirectorySelected
    ) -> None:
        self.query_one("#dir-path", Input).value = str(event.path)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        event.stop()
        path = Path(event.value).expanduser()
        if path.is_dir():
            self._set_root(path)
        else:
            self.notify(f"Not a directory: {path}", severity="error", markup=False)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        if event.button.id == "dir-up":
            self.action_go_up()
        elif event.button.id == "dir-select":
            self.dismiss(self.query_one("#dir-path", Input).value.strip() or None)
        else:
            self.dismiss(None)

    def action_go_up(self) -> None:
        if isinstance(self.focused, Input):
            return
        tree = self.query_one("#dir-tree", FoldersOnlyTree)
        self._set_root(Path(tree.path).parent)

    def _set_root(self, path: Path) -> None:
        self.query_one("#dir-tree", FoldersOnlyTree).path = path
        self.query_one("#dir-path", Input).value = str(path)
