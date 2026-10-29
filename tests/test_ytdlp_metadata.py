"""Tests for the shared yt-dlp metadata fetcher; no network calls."""

import json
import subprocess
from unittest.mock import Mock

import pytest
import yt_dlp
from yt_dlp.extractor.common import InfoExtractor

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


class TestExternal:
    """The external executable path, including the exact flags passed."""

    @pytest.mark.parametrize("limit", [0, 2])
    def test_flags_parse_with_real_ytdlp_parser(self, monkeypatch, limit):
        run = fake_run(json.dumps(PAYLOAD))
        monkeypatch.setattr(metadata.subprocess, "run", run)

        info = metadata.fetch_info_dict(
            URL, make_settings(use_external=True, ytdlp_path="/custom path/yt-dlp"),
            comment_limit=limit,
        )

        assert info == PAYLOAD
        args = run.call_args.args[0]
        assert args[0] == "/custom path/yt-dlp"
        assert args[-2:] == ["--", URL]
        # Check our flags through yt-dlp's own parser, not just string matching.
        options = yt_dlp.parse_options(args[1:]).ydl_opts
        assert options["skip_download"] and options["noplaylist"] and options["dump_single_json"]
        assert bool(options["getcomments"]) == bool(limit)
        if limit:
            assert options["extractor_args"]["youtube"] == {
                "comment_sort": ["top"], "max_comments": ["2", "2", "0", "0"],
            }
            assert run.call_args.kwargs["timeout"] == metadata.COMMENTS_TIMEOUT_SECONDS
        else:
            assert "youtube" not in options["extractor_args"]
            assert run.call_args.kwargs["timeout"] == metadata.METADATA_TIMEOUT_SECONDS

    def test_parses_json_from_fake_executable(self, tmp_path):
        command = write_fake_ytdlp(tmp_path, f"print(json.dumps({PAYLOAD!r}))\n")
        info = metadata.fetch_info_dict(URL, make_settings(use_external=True, ytdlp_path=command))
        assert info == PAYLOAD

    def test_missing_executable_names_the_path(self):
        settings = make_settings(use_external=True, ytdlp_path="/nonexistent/yt-dlp")
        with pytest.raises(ValidationError, match="/nonexistent/yt-dlp"):
            metadata.fetch_info_dict(URL, settings)

    def test_unavailable_video_gets_friendly_message(self, tmp_path):
        command = write_fake_ytdlp(
            tmp_path, "print('ERROR: Video unavailable', file=sys.stderr)\nsys.exit(1)\n",
        )
        with pytest.raises(ValidationError, match="^This video is unavailable$"):
            metadata.fetch_info_dict(URL, make_settings(use_external=True, ytdlp_path=command))

    def test_passes_cookies_from_browser_and_handles_age_error(self, monkeypatch):
        run = fake_run(returncode=1, stderr="ERROR: Sign in to confirm your age")
        monkeypatch.setattr(metadata.subprocess, "run", run)
        settings = make_settings(use_external=True)
        settings.cookies_from_browser = CookieBrowser.FIREFOX

        with pytest.raises(ValidationError, match="Firefox"):
            metadata.fetch_info_dict(URL, settings)

        args = run.call_args.args[0]
        options = yt_dlp.parse_options(args[1:]).ydl_opts
        assert options["cookiesfrombrowser"][0] == "firefox"

    def test_other_failure_includes_diagnostic(self, monkeypatch):
        monkeypatch.setattr(metadata.subprocess, "run", fake_run(returncode=1, stderr="HTTP 429"))
        with pytest.raises(ValidationError, match="HTTP 429"):
            metadata.fetch_info_dict(URL, make_settings(use_external=True))

    def test_comment_failure_retries_once_without_comments(self, monkeypatch):
        run = Mock(side_effect=[
            subprocess.CompletedProcess([], 1, "", "ERROR: comment API failed"),
            subprocess.CompletedProcess([], 0, json.dumps(PAYLOAD), ""),
        ])
        monkeypatch.setattr(metadata.subprocess, "run", run)

        info = metadata.fetch_info_dict(URL, make_settings(use_external=True), comment_limit=5)

        assert info == PAYLOAD
        first, retry = (call.args[0] for call in run.call_args_list)
        assert "--write-comments" in first
        assert "--write-comments" not in retry

    def test_unavailable_video_with_comments_reports_video_error(self, monkeypatch):
        run = fake_run(returncode=1, stderr="ERROR: Video unavailable")
        monkeypatch.setattr(metadata.subprocess, "run", run)
        with pytest.raises(ValidationError, match="^This video is unavailable$"):
            metadata.fetch_info_dict(URL, make_settings(use_external=True), comment_limit=5)
        assert run.call_count == 2

    @pytest.mark.parametrize("error,match", [
        (subprocess.TimeoutExpired("yt-dlp", 30), "Timed out"),
        (PermissionError("denied"), "Could not run"),
    ])
    def test_process_errors(self, monkeypatch, error, match):
        monkeypatch.setattr(metadata.subprocess, "run", Mock(side_effect=error))
        with pytest.raises(ValidationError, match=match):
            metadata.fetch_info_dict(URL, make_settings(use_external=True))

    @pytest.mark.parametrize("output", ["garbage", "", "null", "[]", '{"_type": "playlist"}'])
    def test_bad_output(self, monkeypatch, output):
        monkeypatch.setattr(metadata.subprocess, "run", fake_run(output))
        with pytest.raises(ValidationError):
            metadata.fetch_info_dict(URL, make_settings(use_external=True))


class FixtureIE(InfoExtractor):
    """Offline extractor that provides comments the way YouTube's does."""

    _VALID_URL = r"fixture:(?P<id>\w+)"

    def _real_extract(self, url):
        return {
            **PAYLOAD, "url": "https://example.com/audio.mp3",
            "__post_extractor": self.extract_comments(),
        }

    def _get_comments(self):
        yield {"id": "fixture-comment", "text": "Set list", "parent": "root"}


class BrokenCommentsIE(FixtureIE):
    def _get_comments(self):
        raise RuntimeError("comment API changed")
        yield


class TestLibrary:
    """The bundled yt-dlp library path."""

    @pytest.mark.parametrize("limit", [0, 2])
    def test_fetches_comments_only_when_requested(self, monkeypatch, limit):
        original = yt_dlp.YoutubeDL
        options_seen = []

        def downloader(options):
            options_seen.append(options)
            ydl = original(options, auto_init=False)
            ydl.add_info_extractor(FixtureIE())
            return ydl

        monkeypatch.setattr(metadata.yt_dlp, "YoutubeDL", downloader)
        info = metadata.fetch_info_dict("fixture:test", make_settings(), comment_limit=limit)

        assert info["title"] == PAYLOAD["title"]
        assert options_seen[0]["noplaylist"] and options_seen[0]["skip_download"]
        if limit:
            assert [c["id"] for c in info["comments"]] == ["fixture-comment"]
            assert options_seen[0]["extractor_args"]["youtube"] == {
                "comment_sort": ["top"], "max_comments": ["2", "2", "0", "0"],
            }
        else:
            assert not info.get("comments")
            assert "getcomments" not in options_seen[0]

    def test_comment_failure_keeps_metadata(self, monkeypatch):
        original = yt_dlp.YoutubeDL

        def downloader(options):
            ydl = original(options, auto_init=False)
            ydl.add_info_extractor(BrokenCommentsIE())
            return ydl

        monkeypatch.setattr(metadata.yt_dlp, "YoutubeDL", downloader)
        info = metadata.fetch_info_dict("fixture:test", make_settings(), comment_limit=2)
        assert info["description"] == PAYLOAD["description"]
        assert not info.get("comments")

    def test_private_video_gets_friendly_message(self, monkeypatch):
        monkeypatch.setattr(metadata.yt_dlp, "YoutubeDL", Mock(
            side_effect=yt_dlp.utils.DownloadError("ERROR: Private video")))
        with pytest.raises(ValidationError, match="^This video is private$"):
            metadata.fetch_info_dict(URL, make_settings())

    def test_library_passes_cookiesfrombrowser_and_handles_age_error(self, monkeypatch):
        seen_opts = []

        def fake_ydl(opts):
            seen_opts.append(opts)
            raise yt_dlp.utils.DownloadError("ERROR: Sign in to confirm your age")

        monkeypatch.setattr(metadata.yt_dlp, "YoutubeDL", fake_ydl)
        settings = make_settings()
        settings.cookies_from_browser = CookieBrowser.BRAVE
        with pytest.raises(ValidationError, match="Brave"):
            metadata.fetch_info_dict(URL, settings)
        assert seen_opts[0]["cookiesfrombrowser"] == ("brave",)

    def test_unexpected_error_is_validation_error(self, monkeypatch):
        monkeypatch.setattr(metadata.yt_dlp, "YoutubeDL", Mock(side_effect=RuntimeError("boom")))
        with pytest.raises(ValidationError, match="boom"):
            metadata.fetch_info_dict(URL, make_settings())

    @pytest.mark.parametrize("info", [None, {"_type": "playlist"}, {"_type": "multi_video"}])
    def test_rejects_non_single_video(self, monkeypatch, info):
        monkeypatch.setattr(metadata, "_fetch_library", lambda *args: info)
        with pytest.raises(ValidationError, match="single video"):
            metadata.fetch_info_dict(URL, make_settings())
