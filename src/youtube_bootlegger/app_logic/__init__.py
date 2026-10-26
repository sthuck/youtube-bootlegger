"""UI-agnostic application logic shared by the widget, QML, and TUI front-ends."""

from .help_content import build_help_content
from .job_builder import FormError, FormField, JobForm, build_job
from .presentation import (
    PreviewSummary,
    VideoSummary,
    check_ai_assist_ready,
    format_progress_stage,
    summarize_preview,
    summarize_video,
)

__all__ = [
    "FormError",
    "FormField",
    "JobForm",
    "PreviewSummary",
    "VideoSummary",
    "build_help_content",
    "build_job",
    "check_ai_assist_ready",
    "format_progress_stage",
    "summarize_preview",
    "summarize_video",
]
