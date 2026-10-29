"""Download pinned runtime tools into a release's tools directory.

Uses only the standard library. Stage outside the project before Nuitka for the
Windows payload, or after Nuitka for sidecars. Never extracts arbitrary paths.
"""

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import zipfile
from pathlib import Path

MANIFEST = Path(__file__).with_name("runtime-tools.json")
NOTICES = {
    "yt-dlp-LICENSE.txt": "https://raw.githubusercontent.com/yt-dlp/yt-dlp/2026.10.26/LICENSE",
    "yt-dlp-THIRD_PARTY_LICENSES.txt": "https://raw.githubusercontent.com/yt-dlp/yt-dlp/2026.10.26/THIRD_PARTY_LICENSES.txt",
    "deno-LICENSE.txt": "https://raw.githubusercontent.com/denoland/deno/v2.9.8/LICENSE.md",
    "deno-node-LICENSE.txt": "https://raw.githubusercontent.com/denoland/deno/v2.9.8/cli/tsc/dts/node/LICENSE",
    "deno-undici-LICENSE.txt": "https://raw.githubusercontent.com/denoland/deno/v2.9.8/cli/tsc/dts/node/undici/LICENSE",
    "FFmpeg-COPYING.GPLv3.txt": "https://raw.githubusercontent.com/FFmpeg/FFmpeg/n9.0.2/COPYING.GPLv3",
    "FFmpeg-COPYING.LGPLv2.1.txt": "https://raw.githubusercontent.com/FFmpeg/FFmpeg/n9.0.2/COPYING.LGPLv2.1",
}


def download(url: str, destination: Path) -> None:
    print(f"Downloading {url}", flush=True)
    request = urllib.request.Request(url, headers={"User-Agent": "YouTubeBootlegger-release"})
    with urllib.request.urlopen(request, timeout=120) as response:
        with destination.open("wb") as output:
            shutil.copyfileobj(response, output)


def verify(path: Path, expected: str) -> None:
    with path.open("rb") as source:
        actual = hashlib.file_digest(source, "sha256").hexdigest()
    if actual != expected:
        raise ValueError(f"SHA256 mismatch for {path.name}: expected {expected}, got {actual}")


def extract_asset(archive: Path, asset: dict, destination: Path) -> None:
    """Copy only named regular files, rejecting ambiguous matches and links."""
    if asset["archive"] == "raw":
        shutil.copyfile(archive, destination / asset["files"][0])
    elif asset["archive"] == "zip":
        with zipfile.ZipFile(archive) as bundle:
            for name in asset["files"]:
                members = [m for m in bundle.infolist() if not m.is_dir() and Path(m.filename).name == name]
                if len(members) != 1 or (members[0].external_attr >> 16) & 0o170000 == 0o120000:
                    raise ValueError(f"Expected one regular {name} in {archive.name}")
                with bundle.open(members[0]) as source, (destination / name).open("wb") as target:
                    shutil.copyfileobj(source, target)
    elif asset["archive"] == "tar":
        with tarfile.open(archive) as bundle:
            for name in asset["files"]:
                members = [m for m in bundle.getmembers() if m.isfile() and Path(m.name).name == name]
                if len(members) != 1:
                    raise ValueError(f"Expected one regular {name} in {archive.name}")
                with bundle.extractfile(members[0]) as source, (destination / name).open("wb") as target:
                    shutil.copyfileobj(source, target)
    else:
        raise ValueError(f"Unsupported archive type: {asset['archive']}")
    for name in asset["files"]:
        path = destination / name
        if "binary_sha256" in asset:
            verify(path, asset["binary_sha256"])
        path.chmod(0o755)


def run_tool(directory: Path, name: str, *args: str) -> str:
    suffix = ".exe" if sys.platform == "win32" else ""
    # Match the application's output encoding when yt-dlp initializes its API.
    encoding_args = ["--encoding", "utf-8"] if name == "yt-dlp" else []
    result = subprocess.run(
        [str(directory / f"{name}{suffix}"), *encoding_args, *args],
        check=True, capture_output=True, text=True, encoding="utf-8", timeout=90,
    )
    return result.stdout + result.stderr


def smoke_check(directory: Path) -> None:
    """Exercise the actual native binaries, not just archive filenames."""
    for name, flag in (("yt-dlp", "--version"), ("ffmpeg", "-version"),
                       ("ffprobe", "-version"), ("deno", "--version")):
        print(run_tool(directory, name, flag).splitlines()[0])
    ffmpeg_license = run_tool(directory, "ffmpeg", "-L")
    if "--enable-nonfree" in ffmpeg_license:
        raise ValueError("Refusing to distribute an FFmpeg build configured with --enable-nonfree")
    (directory / "licenses" / "FFmpeg-build-license.txt").write_text(ffmpeg_license, encoding="utf-8")
    if "bundled deno OK" not in run_tool(directory, "deno", "eval", "console.log('bundled deno OK')"):
        raise ValueError("Deno could not execute JavaScript")
    # Includes the explicit Deno/FFmpeg path syntax; does not access YouTube.
    suffix = ".exe" if sys.platform == "win32" else ""
    run_tool(directory, "yt-dlp", "--ignore-config", "--js-runtimes",
             f"deno:{directory / ('deno' + suffix)}", "--ffmpeg-location",
             str(directory / ("ffmpeg" + suffix)), "--version")


def bundle_tools(platform: str, destination: Path) -> None:
    assets = json.loads(MANIFEST.read_text())[platform]
    destination = destination.resolve()
    if destination.exists():
        raise ValueError(f"Destination already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination.parent) as temporary:
        staging = Path(temporary)
        tools = staging / "tools"
        tools.mkdir()
        for index, asset in enumerate(assets):
            archive = staging / f"download-{index}"
            download(asset["url"], archive)
            if "sha256" in asset:
                verify(archive, asset["sha256"])
            elif "binary_sha256" not in asset:
                raise ValueError("Every download must have a pinned checksum")
            extract_asset(archive, asset, tools)
        licenses = tools / "licenses"
        licenses.mkdir()
        for name, url in NOTICES.items():
            download(url, licenses / name)
        shutil.copyfile(Path(__file__).parents[1] / "docs" / "bundled-tools.md", tools / "README.md")
        (tools / "manifest.json").write_text(json.dumps({"platform": platform, "assets": assets}, indent=2) + "\n")
        # osxexperts binaries may need a local ad-hoc signature on ARM Macs.
        # Keep Deno's own signature and entitlements intact (no --deep resign).
        if platform == "macos-arm64":
            for name in ("ffmpeg", "ffprobe"):
                subprocess.run(["codesign", "--force", "--sign", "-", str(tools / name)], check=True)
        smoke_check(tools)
        tools.rename(destination)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform", choices=json.loads(MANIFEST.read_text()), required=True)
    parser.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()
    bundle_tools(args.platform, args.destination)
