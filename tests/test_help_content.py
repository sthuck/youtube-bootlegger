"""Tests for QML help panel content."""

from src.youtube_bootlegger.core.template_parser import DEFAULT_TEMPLATE
from src.youtube_bootlegger.qml_backend.help_content import build_help_content


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
