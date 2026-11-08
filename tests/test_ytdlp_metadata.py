"""Tests for the shared yt-dlp metadata fetcher; no network calls."""

import json
import subprocess
from unittest.mock import Mock

import pytest

from src.youtube_bootlegger.core import ytdlp_metadata as metadata
from src.youtube_bootlegger.core.exceptions import ValidationError
from src.youtube_bootlegger.core.settings import CookieBrowser
from tests.test_downloader import make_settings

URL = "https://www.youtube.com/watch?v=fixture"
PAYLOAD = {"id": "fixture", "title": "Live 演奏", "description": "0:00 One"}


def fake_run(stdout="", returncode=0, stderr=""):
    return Mock(return_value=subprocess.CompletedProcess([], returncode, stdout, stderr))


def write_fake_ytdlp(tmp_path, body):
    script = tmp_path / "fake-yt-dlp.py"
    script.write_text("#!/usr/bin/env python3\nimport json, sys\n" + body)
    script.chmod(0o755)
    return str(script)


class TestFetch:
    """Running the yt-dlp executable, including the exact flags passed."""

    def test_invalid_output_suggests_checking_extra_options(self, monkeypatch):
        settings = make_settings()
        settings.ytdlp_extra_args = "--get-url"
        monkeypatch.setattr(metadata.subprocess, "run", fake_run("https://example.invalid/audio"))
        with pytest.raises(ValidationError, match="did not return valid video information.*Extra yt-dlp options"):
            metadata.fetch_info_dict(URL, settings)

    @pytest.mark.parametrize("limit", [0, 2])
    def test_flags(self, monkeypatch, limit):
        run = fake_run(json.dumps(PAYLOAD))
        monkeypatch.setattr(metadata.subprocess, "run", run)

        info = metadata.fetch_info_dict(
            URL, make_settings(ytdlp_path="/custom path/yt-dlp"),
            comment_limit=limit,
        )

        assert info == PAYLOAD
        args = run.call_args.args[0]
        assert args[0] == "/custom path/yt-dlp"
        assert args[-2:] == ["--", URL]
        assert {"--skip-download", "--no-playlist", "--dump-single-json"} <= set(args)
        assert ("--write-comments" in args) == bool(limit)
        if limit:
            assert args[args.index("--extractor-args") + 1] == (
                "youtube:comment_sort=top;max_comments=2,2,0,0"
            )
            assert run.call_args.kwargs["timeout"] == metadata.COMMENTS_TIMEOUT_SECONDS
        else:
            assert "--extractor-args" not in args
            assert run.call_args.kwargs["timeout"] == metadata.METADATA_TIMEOUT_SECONDS

    def test_parses_json_from_fake_executable(self, tmp_path):
        command = write_fake_ytdlp(tmp_path, f"print(json.dumps({PAYLOAD!r}))\n")
        info = metadata.fetch_info_dict(URL, make_settings(ytdlp_path=command))
        assert info == PAYLOAD

    def test_missing_executable_names_the_path(self):
        settings = make_settings(ytdlp_path="/nonexistent/yt-dlp")
        with pytest.raises(ValidationError, match="/nonexistent/yt-dlp"):
            metadata.fetch_info_dict(URL, settings)

    def test_unavailable_video_gets_friendly_message(self, tmp_path):
        command = write_fake_ytdlp(
            tmp_path, "print('ERROR: Video unavailable', file=sys.stderr)\nsys.exit(1)\n",
        )
        with pytest.raises(ValidationError, match="^This video is unavailable$"):
            metadata.fetch_info_dict(URL, make_settings(ytdlp_path=command))

    def test_passes_cookies_from_browser_and_handles_age_error(self, monkeypatch):
        run = fake_run(returncode=1, stderr="ERROR: Sign in to confirm your age")
        monkeypatch.setattr(metadata.subprocess, "run", run)
        settings = make_settings()
        settings.cookies_from_browser = CookieBrowser.FIREFOX

        with pytest.raises(ValidationError, match="Firefox"):
            metadata.fetch_info_dict(URL, settings)

        args = run.call_args.args[0]
        assert args[args.index("--cookies-from-browser") + 1] == "firefox"

    def test_other_failure_includes_diagnostic(self, monkeypatch):
        monkeypatch.setattr(metadata.subprocess, "run", fake_run(returncode=1, stderr="HTTP 429"))
        with pytest.raises(ValidationError, match="HTTP 429"):
            metadata.fetch_info_dict(URL, make_settings())

    def test_comment_failure_retries_once_without_comments(self, monkeypatch):
        run = Mock(side_effect=[
            subprocess.CompletedProcess([], 1, "", "ERROR: comment API failed"),
            subprocess.CompletedProcess([], 0, json.dumps(PAYLOAD), ""),
        ])
        monkeypatch.setattr(metadata.subprocess, "run", run)

        info = metadata.fetch_info_dict(URL, make_settings(), comment_limit=5)

        assert info == PAYLOAD
        first, retry = (call.args[0] for call in run.call_args_list)
        assert "--write-comments" in first
        assert "--write-comments" not in retry

    def test_unavailable_video_with_comments_reports_video_error(self, monkeypatch):
        run = fake_run(returncode=1, stderr="ERROR: Video unavailable")
        monkeypatch.setattr(metadata.subprocess, "run", run)
        with pytest.raises(ValidationError, match="^This video is unavailable$"):
            metadata.fetch_info_dict(URL, make_settings(), comment_limit=5)
        assert run.call_count == 2

    @pytest.mark.parametrize("error,match", [
        (subprocess.TimeoutExpired("yt-dlp", 30), "Timed out"),
        (PermissionError("denied"), "Could not run"),
    ])
    def test_process_errors(self, monkeypatch, error, match):
        monkeypatch.setattr(metadata.subprocess, "run", Mock(side_effect=error))
        with pytest.raises(ValidationError, match=match):
            metadata.fetch_info_dict(URL, make_settings())

    def test_private_video_gets_friendly_message(self, monkeypatch):
        monkeypatch.setattr(metadata.subprocess, "run", fake_run(returncode=1, stderr="ERROR: Private video"))
        with pytest.raises(ValidationError, match="^This video is private$"):
            metadata.fetch_info_dict(URL, make_settings())

    @pytest.mark.parametrize("output", [
        "garbage", "", "null", "[]", '{"_type": "playlist"}', '{"_type": "multi_video"}',
    ])
    def test_bad_output(self, monkeypatch, output):
        monkeypatch.setattr(metadata.subprocess, "run", fake_run(output))
        with pytest.raises(ValidationError):
            metadata.fetch_info_dict(URL, make_settings())
