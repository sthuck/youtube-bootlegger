"""Help screen rendered from the shared help content."""

from collections.abc import Iterable

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Markdown

from ...app_logic import build_help_content

EXTRA_SHORTCUTS = (
    ("Tab / Shift+Tab", "Move between fields"),
    ("Escape", "Close dialogs"),
)


def _format_key(key: str) -> str:
    """Format a Textual key name for display, e.g. "ctrl+r" -> "Ctrl+R"."""
    return "+".join(
        part.capitalize() if len(part) > 1 else part.upper() for part in key.split("+")
    )


def keyboard_shortcuts(bindings: Iterable[Binding]) -> list[tuple[str, str]]:
    """List (keys, action) rows for the visible app bindings, plus extras."""
    rows = [
        (" / ".join(_format_key(k) for k in b.key.split(",")), b.description)
        for b in bindings
        if b.show and b.description
    ]
    return rows + list(EXTRA_SHORTCUTS)


def _code_block(code: str) -> str:
    return f"```\n{code}\n```"


def _placeholder_item(text: str) -> str:
    """Format "%name% — description" as a list item with the name as code."""
    name, _, description = text.partition(" — ")
    return f"- `{name}` — {description}" if description else f"- {text}"


def build_help_markdown(
    content: dict | None = None, bindings: Iterable[Binding] = ()
) -> str:
    """Render the shared help content dict as Markdown."""
    c = content or build_help_content()
    parts = [f"# {c['title']}", c["intro"], f"## {c['quickStartTitle']}", c["quickStartIntro"]]
    parts += [f"{s['n']}. **{s['title']}:** {s['body']}" for s in c["steps"]]

    parts += [f"## {c['templateTitle']}", c["templateIntro"]]
    parts.append("\n".join(_placeholder_item(p) for p in c["templatePlaceholders"]))
    for example in c["templateExamples"]:
        parts += [f"**{example['label']}**", _code_block(example["code"])]
    parts.append(c["templateNote"])

    parts += [f"## {c['aiTitle']}", c["aiBody"]]
    parts += [f"## {c['outputTitle']}", c["outputBody"].replace("\n\n  ", "\n\n    ")]
    parts += [f"## {c['requirementsTitle']}", "\n".join(f"- {r}" for r in c["requirements"])]
    parts += [
        f"## {c['troubleshootingTitle']}",
        "\n".join(f"- {t}" for t in c["troubleshooting"]),
    ]
    parts += [
        "## KEYBOARD SHORTCUTS",
        "| Key | Action |\n|---|---|\n"
        + "\n".join(f"| {key} | {action} |" for key, action in keyboard_shortcuts(bindings)),
    ]
    return "\n\n".join(parts)


class HelpScreen(ModalScreen[None]):
    """Scrollable help dialog."""

    BINDINGS = [Binding("escape,f1", "dismiss", "Close")]

    def __init__(self, app_bindings: Iterable[Binding] = ()) -> None:
        super().__init__()
        self._app_bindings = tuple(app_bindings)

    def compose(self) -> ComposeResult:
        with Vertical(id="help-dialog", classes="dialog"):
            with VerticalScroll():
                yield Markdown(build_help_markdown(bindings=self._app_bindings))
            yield Button("Close", variant="primary", id="help-close")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        self.dismiss()
