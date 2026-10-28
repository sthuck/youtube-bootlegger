"""Tests for the shared yt-dlp metadata fetcher; no network calls."""

import json
import subprocess
from unittest.mock import Mock

import pytest
import yt_dlp
from yt_dlp.extractor.common import InfoExtractor

from src.youtube_bootlegger.core import ytdlp_metadata as metadata
from src.youtube_bootlegger.core.exceptions import ValidationError
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

    def test_other_failure_includes_diagnostic(self, monkeypatch):
        monkeypatch.setattr(metadata.subprocess, "run", fake_run(returncode=1, stderr="HTTP 429"))
        with pytest.raises(ValidationError, match="HTTP 429"):
            metadata.fetch_info_dict(URL, make_settings(use_external=True))

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
    """Offline extractor whose comments are deferred, like YouTube's."""

    _VALID_URL = r"fixture:(?P<id>\w+)"

    def _real_extract(self, url):
        return {
            **PAYLOAD, "url": "https://example.com/audio.mp3",
            "__post_extractor": self.extract_comments(),
        }

    def _get_comments(self):
        yield {"id": "deferred", "text": "Set list", "parent": "root"}


class TestLibrary:
    """The bundled yt-dlp library path."""

    @pytest.mark.parametrize("limit", [0, 2])
    def test_runs_deferred_comments_only_when_requested(self, monkeypatch, limit):
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
            assert [c["id"] for c in info["comments"]] == ["deferred"]
            assert options_seen[0]["extractor_args"]["youtube"] == {
                "comment_sort": ["top"], "max_comments": ["2", "2", "0", "0"],
            }
        else:
            assert not info.get("comments")
            assert "getcomments" not in options_seen[0]

    def test_private_video_gets_friendly_message(self, monkeypatch):
        monkeypatch.setattr(metadata.yt_dlp, "YoutubeDL", Mock(
            side_effect=yt_dlp.utils.DownloadError("ERROR: Private video")))
        with pytest.raises(ValidationError, match="^This video is private$"):
            metadata.fetch_info_dict(URL, make_settings())

    def test_unexpected_error_is_validation_error(self, monkeypatch):
        monkeypatch.setattr(metadata.yt_dlp, "YoutubeDL", Mock(side_effect=RuntimeError("boom")))
        with pytest.raises(ValidationError, match="boom"):
            metadata.fetch_info_dict(URL, make_settings())

    @pytest.mark.parametrize("info", [None, {"_type": "playlist"}, {"_type": "multi_video"}])
    def test_rejects_non_single_video(self, monkeypatch, info):
        monkeypatch.setattr(metadata, "_fetch_library", lambda *args: info)
        with pytest.raises(ValidationError, match="single video"):
            metadata.fetch_info_dict(URL, make_settings())
