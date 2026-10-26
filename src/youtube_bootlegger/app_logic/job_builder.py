"""Form validation and DownloadJob construction shared by all front-ends."""

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from ..core.exceptions import ParseError
from ..core.template_parser import (
    DEFAULT_TEMPLATE,
    parse_tracklist_with_template,
    validate_template,
)
from ..core.video_info import VideoInfo
from ..models import DownloadJob
from ..utils import is_valid_youtube_url


class FormField(StrEnum):
    """Form fields that can carry a validation error."""

    URL = "url"
    TEMPLATE = "template"
    TRACKLIST = "tracklist"
    METADATA = "metadata"
    OUTPUT_DIR = "output_dir"


@dataclass(frozen=True)
class JobForm:
    """Raw user input needed to start a download/split job."""

    url: str
    template: str
    tracklist_text: str
    artist: str
    album: str
    output_dir: str


@dataclass(frozen=True)
class FormError:
    """A validation error tied to the form field that caused it."""

    field: FormField
    message: str


def build_job(form: JobForm, video_info: VideoInfo | None) -> DownloadJob | FormError:
    """Validate the form and build a DownloadJob.

    Checks run in on-screen order so the first error reported is the one
    the user is most likely to reach first.

    Args:
        form: The user's raw input.
        video_info: Loaded video info, or None if not loaded yet.

    Returns:
        A DownloadJob on success, or the first FormError found.
    """
    url = form.url.strip()
    if not url:
        return FormError(FormField.URL, "Please enter a YouTube URL")
    if not is_valid_youtube_url(url):
        return FormError(FormField.URL, "Please enter a valid YouTube URL")
    if video_info is None:
        return FormError(FormField.URL, "Please wait for video info to load")

    template = form.template or DEFAULT_TEMPLATE
    validation = validate_template(template)
    if not validation.is_valid:
        return FormError(FormField.TEMPLATE, f"Invalid template: {validation.error}")

    if not form.tracklist_text.strip():
        return FormError(FormField.TRACKLIST, "Please enter a track list")
    try:
        tracks = parse_tracklist_with_template(form.tracklist_text, template)
    except ParseError as e:
        return FormError(FormField.TRACKLIST, str(e))
    if not tracks:
        return FormError(FormField.TRACKLIST, "No tracks found in track list")

    artist = form.artist.strip()
    album = form.album.strip()
    if not artist and not album:
        return FormError(FormField.METADATA, "Please enter an artist name or album name")

    output_dir = form.output_dir.strip()
    if not output_dir:
        return FormError(FormField.OUTPUT_DIR, "Please select an output directory")

    return DownloadJob(
        url=url,
        output_dir=Path(output_dir).expanduser(),
        tracks=tuple(tracks),
        artist=artist or None,
        album=album or video_info.title,
        thumbnail_url=video_info.thumbnail_url,
    )
