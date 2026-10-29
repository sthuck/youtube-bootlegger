"""Include native companion executables in Nuitka's Windows onefile payload."""

import argparse
import configparser
import json
import shlex
from pathlib import Path


def nuitka_tool_args(tools_dir: Path, config_file: Path, *, module_name: str) -> list[str]:
    """Declare EXEs as executable dependencies, rather than ordinary data files."""
    tools_dir = tools_dir.resolve()
    names = ["yt-dlp", "ffmpeg", "ffprobe", "deno"]
    for name in names:
        if not (tools_dir / f"{name}.exe").is_file():
            raise ValueError(f"Missing Windows companion: {name}.exe")
    for name in ("licenses", "manifest.json", "README.md"):
        if not (tools_dir / name).exists():
            raise ValueError(f"Missing bundled tool notices: {name}")
    # JSON is valid YAML. Absolute paths locate inputs outside the project tree;
    # dest_path puts the EXEs together at tools/ inside the extracted payload.
    config_file = config_file.resolve()
    config_file.parent.mkdir(parents=True, exist_ok=True)
    config_file.write_text(json.dumps([{
        "module-name": module_name,
        "dlls": [{
            "from_filenames": {
                "relative_path": str(tools_dir),
                "prefixes": names,
                "suffixes": ["exe"],
                "executable": "yes",
            },
            "dest_path": "tools",
        }],
    }], indent=2), encoding="utf-8")
    return [
        f"--user-package-configuration-file={config_file}",
        f"--include-data-dir={tools_dir / 'licenses'}=tools/licenses",
        f"--include-data-files={tools_dir / 'manifest.json'}=tools/manifest.json",
        f"--include-data-files={tools_dir / 'README.md'}=tools/README.md",
    ]


def prepare(tools_dir: Path, config_file: Path, deploy_config: Path) -> None:
    args = nuitka_tool_args(tools_dir, config_file, module_name="src.youtube_bootlegger.core.tools")
    spec = configparser.ConfigParser(interpolation=None)
    with deploy_config.open(encoding="utf-8") as source:
        spec.read_file(source)
    # PySide6 parses this field with shlex.split on Windows as well as POSIX.
    spec["nuitka"]["extra_args"] = spec["nuitka"].get("extra_args", "") + " " + shlex.join(args)
    with deploy_config.open("w", encoding="utf-8") as target:
        spec.write(target)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tools-dir", type=Path, required=True)
    parser.add_argument("--config-file", type=Path, required=True)
    parser.add_argument("--deploy-config", type=Path, default=Path("pysidedeploy.spec"))
    args = parser.parse_args()
    prepare(args.tools_dir, args.config_file, args.deploy_config)
