"""User-facing help text for the QML help panel."""

from ..core.template_parser import DEFAULT_TEMPLATE


def build_help_content() -> dict:
    """Return structured help text consumed by HelpPanel.qml."""
    return {
        "title": "How to Use YouTube Bootlegger",
        "intro": (
            "Download live performance audio from YouTube, split it into individual "
            "songs using timestamped track lists, and save tagged MP3 files."
        ),
        "quickStartTitle": "QUICK START",
        "quickStartIntro": "Follow these steps from top to bottom, left to right.",
        "steps": [
            {
                "n": "1",
                "title": "Paste a YouTube URL",
                "body": (
                    "Enter a watch or youtu.be link in the URL field. The app fetches "
                    "video info automatically and shows a preview with title, channel, "
                    "duration, and thumbnail."
                ),
            },
            {
                "n": "2",
                "title": "Enter the track list",
                "body": (
                    "Paste or type your track list in the text area — one song per line, "
                    "as copied from a setlist or video description. You can refine the "
                    "format in the next step."
                ),
            },
            {
                "n": "3",
                "title": "Set the track list template",
                "body": (
                    f"Define how each line is parsed. The default template is "
                    f"{DEFAULT_TEMPLATE}. Adjust placeholders if your timestamps or song "
                    "names appear in a different order, and use the preview panel to "
                    "validate each line."
                ),
            },
            {
                "n": "4",
                "title": "Fill in metadata",
                "body": (
                    "Enter an artist name (required). Album is optional — if left blank, "
                    "the video title is used when saving files."
                ),
            },
            {
                "n": "5",
                "title": "Choose an output directory",
                "body": (
                    "Pick where to save files. Defaults to your Music folder. Songs are "
                    "saved in a subfolder named Artist - Album."
                ),
            },
            {
                "n": "6",
                "title": "Start Download & Split",
                "body": (
                    "The app downloads audio with yt-dlp, splits it at each timestamp "
                    "with FFmpeg, and writes tagged MP3 files with cover art from the "
                    "video thumbnail. Progress and status appear in the log panel."
                ),
            },
        ],
        "templateTitle": "TRACK LIST TEMPLATES",
        "templateIntro": (
            "Each line in your track list must match the template. Available placeholders:"
        ),
        "templatePlaceholders": [
            "%songname% — song title (required)",
            "%mm% — minutes (required)",
            "%ss% — seconds as two digits (required in template)",
            "%hh% — hours (only when timestamps include hours)",
            "%ignore:regex% — skip a pattern, e.g. %ignore:\\d+\\.% for track numbers",
        ],
        "templateExamples": [
            {"label": "Default template", "code": DEFAULT_TEMPLATE},
            {
                "label": "Example track list",
                "code": (
                    "Opening Number - 0:00\n"
                    "Second Song - 4:32\n"
                    "Third Song - 8:15\n"
                    "Final Song - 12:47"
                ),
            },
            {
                "label": "Hour-long sets (template: %hh%:%mm%:%ss% - %songname%)",
                "code": "0:00 - Intro\n1:23:45 - Long Song\n2:05:30 - Encore",
            },
            {
                "label": "Brackets around timestamps (template: [%mm%:%ss%] %songname%)",
                "code": "[0:00] Opening Act\n[12:30] Main Set",
            },
        ],
        "templateNote": (
            "When using %hh%:%mm%:%ss%, each line may use either hh:mm or hh:mm:ss. "
            "Only add %hh% when at least one timestamp has a real hour component — do "
            "not use it for mm:ss timestamps."
        ),
        "aiTitle": "AI ASSIST",
        "aiBody": (
            "Click the AI button next to the track list to auto-detect the best "
            "template, artist, and album from your raw track list and video title. "
            "Requires an LLM provider configured in Settings (gear icon). Track list "
            "text and video title are sent to the selected provider."
        ),
        "outputTitle": "OUTPUT",
        "outputBody": (
            "Files are saved as MP3s in a subfolder under your chosen output directory:\n\n"
            "  OutputDir / Artist - Album / 01 - Song Name.mp3\n\n"
            "Each file includes artist, album, title, and track number tags, plus cover "
            "art from the video thumbnail."
        ),
        "requirementsTitle": "REQUIREMENTS",
        "requirements": [
            "FFmpeg — required for splitting audio. Install it or set a custom path in Settings.",
            "yt-dlp — bundled with the app. An external binary is optional in Settings.",
            "LLM provider — optional, only needed for AI Assist.",
        ],
        "troubleshootingTitle": "TROUBLESHOOTING",
        "troubleshooting": [
            "FFmpeg not found — install FFmpeg or set its path in Settings.",
            "Invalid URL — use a standard YouTube watch or youtu.be link.",
            "Red preview rows — a line does not match the template. Check placeholders and timestamp format.",
            "Cannot start — artist name is required. Fix any template or directory errors shown in red.",
            "Cancel — use the Cancel button while a download or split is in progress.",
        ],
    }
