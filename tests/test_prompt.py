"""Unit tests for LLM prompt building."""

from src.youtube_bootlegger.llm.prompt import TEMPLATE_HELP, build_extraction_prompt


class TestBuildExtractionPrompt:
    def test_includes_video_title_and_tracklist(self):
        prompt = build_extraction_prompt(
            "Phish - 12/31/2023",
            "Tweezer - 0:00\nHarry Hood - 12:34",
        )
        assert "Phish - 12/31/2023" in prompt
        assert "Tweezer - 0:00" in prompt
        assert "%songname%" in prompt
        assert "template" in prompt.lower()

    def test_template_help_is_included(self):
        prompt = build_extraction_prompt("Show", "Song - 0:00")
        assert TEMPLATE_HELP.splitlines()[0] in prompt
