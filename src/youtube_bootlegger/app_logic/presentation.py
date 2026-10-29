"""Display-text helpers shared by all front-ends."""

from dataclasses import dataclass

from ..core.settings import AppSettings
from ..core.template_parser import ParsePreview
from ..core.video_info import VideoInfo
from ..llm import is_llm_configured

MAX_TITLE_LENGTH = 80

AI_PROVIDERS_NOTE = (
    "Lite opens ChatGPT in your browser — no API key. Built-in providers send "
    "the track list, video title, description, chapters and top comments to "
    "the selected API using credentials stored locally."
)
LOG_AI_REQUESTS_LABEL = "Log AI requests (for debugging)"

STAGE_LABELS = {
    "download": "Downloading",
    "split": "Splitting",
    "tagging": "Tagging",
    "complete": "Complete",
}


@dataclass(frozen=True)
class PreviewSummary:
    """One-line status for a track list preview."""

    status: str
    is_valid: bool


@dataclass(frozen=True)
class VideoSummary:
    """Display strings for a loaded video."""

    title: str
    channel: str
    duration: str
    views: str
    date: str


def summarize_preview(preview: ParsePreview) -> PreviewSummary:
    """Summarize a parse preview as a short status string."""
    if preview.total_lines == 0:
        return PreviewSummary("", True)
    if preview.is_valid:
        return PreviewSummary(f"{preview.total_lines} tracks", True)
    return PreviewSummary(f"{preview.error_count} error(s)", False)


def format_progress_stage(stage: str, percent: float) -> str:
    """Format a pipeline progress update as e.g. "Downloading: 42%"."""
    label = STAGE_LABELS.get(stage, stage.title())
    return f"{label}: {int(percent)}%"


def summarize_video(info: VideoInfo) -> VideoSummary:
    """Build display strings for a loaded video."""
    title = info.title
    if len(title) > MAX_TITLE_LENGTH:
        title = title[: MAX_TITLE_LENGTH - 3] + "..."
    return VideoSummary(
        title=title,
        channel=info.channel,
        duration=f"Duration: {info.duration_string}",
        views=info.formatted_views,
        date=f"Uploaded: {info.formatted_date}" if info.formatted_date else "",
    )


def check_ai_assist_ready(
    video_info: VideoInfo | None,
    tracklist_text: str,
    settings: AppSettings,
) -> str | None:
    """Return a user-facing reason AI assist cannot run, or None if it can."""
    if video_info is None:
        return "Please wait for video info to load before using AI."
    if not tracklist_text.strip():
        return "Track list is empty."
    if not is_llm_configured(settings):
        return "LLM is not configured. Add API credentials in Settings."
    return None


def log_ai_requests_note(settings: AppSettings) -> str:
    """Settings note under LOG_AI_REQUESTS_LABEL, naming the log file."""
    path = settings.ai_request_log_path
    where = str(path) if path else "ai-requests.log in the settings folder"
    return f"Saves each AI request and response, without API keys, to {where}."
