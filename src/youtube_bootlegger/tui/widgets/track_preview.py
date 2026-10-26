"""Table showing how each track list line parses against the template."""

from rich.text import Text
from textual.widgets import DataTable

from ...core.template_parser import TrackPreview


class TrackPreviewTable(DataTable):
    """Read-only preview of parsed tracks; invalid lines are shown in red."""

    COLUMNS = ("#", "Start", "Track")

    def on_mount(self) -> None:
        self.cursor_type = "row"
        self.zebra_stripes = True
        self.add_columns(*self.COLUMNS)

    def show_tracks(self, tracks: tuple[TrackPreview, ...]) -> None:
        # Reset columns too, so widths shrink back after a long error row.
        self.clear(columns=True)
        self.add_columns(*self.COLUMNS)
        for index, track in enumerate(tracks, 1):
            # Cells are Text, never str: DataTable parses str as markup, and
            # user-typed names like "Song [/feat]" would raise MarkupError.
            if track.is_valid:
                row = (Text(str(index)), Text(track.timestamp), Text(track.name))
            else:
                row = (
                    Text(str(index), style="bold red"),
                    Text(track.timestamp, style="red"),
                    Text(f"{track.name}  ({track.error})", style="red"),
                )
            self.add_row(*row, key=str(track.line_number))
