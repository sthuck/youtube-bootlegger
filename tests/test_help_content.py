"""Tests for help panel content."""

from src.youtube_bootlegger.core.template_parser import DEFAULT_TEMPLATE
from src.youtube_bootlegger.app_logic.help_content import build_help_content
from src.youtube_bootlegger.app_logic.track_finder import (
    AUTO_FIND_SETTING_LABEL,
    DETECT_FORMAT_BUTTON_LABEL,
    FIND_BUTTON_LABEL,
)


class TestHelpContent:
    def test_build_help_content_has_expected_sections(self):
        content = build_help_content()
        assert content["title"]
        assert content["intro"]
        assert content["steps"]
        assert content["templatePlaceholders"]
        assert content["templateExamples"]
        assert content["requirements"]
        assert content["troubleshooting"]

    def test_steps_enter_tracklist_before_template(self):
        steps = build_help_content()["steps"]
        assert steps[1]["title"] == "Enter the track list"
        assert steps[2]["title"] == "Set the track list template"

    def test_default_template_used_in_content(self):
        content = build_help_content()
        assert DEFAULT_TEMPLATE in content["steps"][2]["body"]
        assert content["templateExamples"][0]["code"] == DEFAULT_TEMPLATE

    def test_step_numbers_are_sequential(self):
        steps = build_help_content()["steps"]
        assert [step["n"] for step in steps] == ["1", "2", "3", "4", "5", "6"]


    def test_ai_help_covers_both_button_modes_and_the_setting(self):
        body = build_help_content()["aiBody"]
        assert FIND_BUTTON_LABEL in body
        assert DETECT_FORMAT_BUTTON_LABEL in body
        assert AUTO_FIND_SETTING_LABEL in body
        assert "ChatGPT Lite" in body
