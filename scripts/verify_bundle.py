"""Check the finished onefile archive, not just PyInstaller's build inputs."""

import argparse
from pathlib import Path
import sys

from PyInstaller.archive.readers import CArchiveReader
from PyInstaller.utils.hooks import collect_data_files

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / 'src' / 'youtube_bootlegger'


def verify_bundle(executable: Path, ui: str) -> None:
    archive = CArchiveReader(str(executable))
    expected = []
    directories = ('assets', 'qml') if ui == 'qml' else ('assets', 'tui')
    for directory in directories:
        for source in sorted((PACKAGE / directory).rglob('*')):
            if (source.is_file() and '__pycache__' not in source.parts
                    and source.suffix not in {'.py', '.pyc', '.pyo', '.pyi'}):
                expected.append((source, source.relative_to(ROOT).as_posix()))

    # Requests' CA roots, Textual's syntax highlighting queries, and
    # textual-image's fallback pictures are also loaded from files at runtime.
    dependencies = ['certifi']
    if ui == 'tui':
        dependencies += ['textual', 'textual_image']
    for dependency in dependencies:
        for source, destination in collect_data_files(dependency):
            expected.append((Path(source), (Path(destination) / Path(source).name).as_posix()))

    # Windows archives use backslashes; keep the original key for extract().
    names = {name.replace('\\', '/'): name for name in archive.toc}
    errors = []
    for source, destination in expected:
        if destination not in names:
            errors.append(f'missing {destination}')
        elif archive.extract(names[destination]) != source.read_bytes():
            errors.append(f'contents differ: {destination}')

    if ui == 'qml':
        for component in ('/qml/QtQuick/Controls/', '/plugins/platforms/'):
            if not any(component in name for name in names):
                errors.append(f'missing Qt runtime files matching {component}')
    if errors:
        raise SystemExit('\n'.join(errors))
    print(f'Verified {len(expected)} embedded resource files in {executable}')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ui', choices=('qml', 'tui'), required=True)
    parser.add_argument('--executable', type=Path)
    args = parser.parse_args()
    name = f'youtube-bootlegger-{args.ui}'
    executable = ROOT / 'dist' / (name + ('.exe' if sys.platform == 'win32' else ''))
    if sys.platform == 'darwin' and args.ui == 'qml':
        executable = ROOT / 'dist' / f'{name}.app' / 'Contents' / 'MacOS' / name
    verify_bundle(args.executable or executable, args.ui)


if __name__ == '__main__':
    main()
