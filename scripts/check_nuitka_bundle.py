"""Compile the real discovery helper and verify tools outside a onefile payload."""

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def check(tools_dir: Path, *, macos_app: bool = False) -> None:
    tools_dir = tools_dir.resolve()
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        helper = Path(__file__).parents[1] / "src/youtube_bootlegger/core/tools.py"
        probe = root / "probe.py"
        probe.write_text(helper.read_text() + '''
if __name__ == "__main__":
    import subprocess
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
        subprocess.run([*args, str(probe)], check=True)
        output = root / "output"
        if macos_app:
            app = output / "probe.app"
            shutil.copytree(tools_dir, app / "Contents/Resources/tools")
            executable = app / "Contents/MacOS/probe"
        else:
            shutil.copytree(tools_dir, output / "tools")
            executable = output / ("probe.exe" if sys.platform == "win32" else "probe.bin")
        # Deliberately launch away from the executable and without PATH tools.
        subprocess.run([str(executable)], check=True, cwd=root)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tools-dir", type=Path, required=True)
    parser.add_argument("--macos-app", action="store_true")
    args = parser.parse_args()
    check(args.tools_dir, macos_app=args.macos_app)
