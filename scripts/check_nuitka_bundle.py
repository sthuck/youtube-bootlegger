"""Compile the discovery helper and exercise the real release tool layout."""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from prepare_windows_onefile import nuitka_tool_args


def check(tools_dir: Path, *, macos_app: bool = False) -> None:
    tools_dir = tools_dir.resolve()
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        helper = Path(__file__).parents[1] / "src/youtube_bootlegger/core/tools.py"
        (root / "runtime_tools.py").write_text(helper.read_text())
        probe = root / "probe.py"
        probe.write_text('''
from runtime_tools import bundled_tool, bundled_tools_dir
if __name__ == "__main__":
    import subprocess
    print("TOOL_DIR=" + str(bundled_tools_dir()), flush=True)
    for name, flag in (("yt-dlp", "--version"), ("ffmpeg", "-version"),
                       ("ffprobe", "-version"), ("deno", "--version")):
        path = bundled_tool(name)
        assert path is not None, (name, bundled_tools_dir())
        subprocess.run([str(path), flag], check=True, stdout=subprocess.DEVNULL)
    print("Compiled discovery OK")
''')
        args = [sys.executable, "-m", "nuitka", "--assume-yes-for-downloads",
                "--output-dir=" + str(root / "output")]
        if macos_app:
            args.append("--mode=app")
        else:
            args.append("--mode=onefile")
        if sys.platform == "win32":
            args.extend(nuitka_tool_args(
                tools_dir, root / "tools.nuitka-package.config.yml", module_name="runtime_tools",
            ))
        subprocess.run([*args, str(probe)], check=True)
        output = root / "output"
        if macos_app:
            app = output / "probe.app"
            shutil.copytree(tools_dir, app / "Contents/Resources/tools")
            subprocess.run([
                "codesign", "--force", "--sign", "-", "--preserve-metadata=entitlements", str(app),
            ], check=True)
            subprocess.run(["codesign", "--verify", "--deep", "--strict", str(app)], check=True)
            executable = app / "Contents/MacOS/probe"
        elif sys.platform == "win32":
            # This directory contains ONLY the downloaded .exe. Source tools and
            # compiler output are elsewhere, so sidecar fallback cannot pass.
            download = root / "Single Download With Spaces"
            download.mkdir()
            executable = download / "YouTubeBootlegger.exe"
            shutil.copyfile(output / "probe.exe", executable)
        else:
            shutil.copytree(tools_dir, output / "tools")
            executable = output / "probe.bin"
        # A second launch also exercises extraction after the first launch exits.
        for _ in range(2 if sys.platform == "win32" else 1):
            result = subprocess.run(
                [str(executable)], check=True, cwd=root, capture_output=True,
                text=True, encoding="utf-8", timeout=180,
                env={**os.environ, "PATH": ""},
            )
            print(result.stdout)
            if sys.platform == "win32":
                extracted = Path(next(line.removeprefix("TOOL_DIR=") for line in result.stdout.splitlines()
                                      if line.startswith("TOOL_DIR=")))
                assert extracted.parent != executable.parent
                assert not extracted.exists(), f"Temporary tools were not cleaned up: {extracted}"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tools-dir", type=Path, required=True)
    parser.add_argument("--macos-app", action="store_true")
    args = parser.parse_args()
    check(args.tools_dir, macos_app=args.macos_app)
