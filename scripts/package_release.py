"""Archive a PyInstaller folder bundle (or the macOS QML app bundle)."""

import argparse
from pathlib import Path
import shutil
import subprocess
import tarfile


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ui', choices=('qml', 'tui'), required=True)
    parser.add_argument('--platform', choices=('linux-x64', 'windows-x64', 'macos-arm64'), required=True)
    parser.add_argument('--version', required=True)
    args = parser.parse_args()
    # Release tags must remain a filename, not a path.
    if any(c in args.version for c in '/\\') or args.version in ('', '.', '..'):
        parser.error('version must be a nonempty filename component')

    name = f'youtube-bootlegger-{args.ui}'
    bundle = Path('dist') / name
    mac_app = args.platform.startswith('macos') and args.ui == 'qml'
    if mac_app:
        bundle = bundle.with_suffix('.app')
    if not bundle.is_dir():
        parser.error(f'missing build output: {bundle}')

    Path('dist/release').mkdir(parents=True, exist_ok=True)
    target = Path('dist/release') / f'{name}-{args.version}-{args.platform}'
    if mac_app:
        # Preserve framework symlinks, executable bits and app metadata.
        subprocess.run(['ditto', '-c', '-k', '--sequesterRsrc', '--keepParent',
                        str(bundle), f'{target}.zip'], check=True)
    elif args.platform.startswith('windows'):
        shutil.make_archive(str(target), 'zip', bundle.parent, bundle.name)
    else:
        # Qt's libraries are large; prefer quick packaging over maximum gzip
        # compression. tar preserves executable bits and framework symlinks.
        with tarfile.open(f'{target}.tar.gz', 'w:gz', compresslevel=1) as archive:
            archive.add(bundle, arcname=bundle.name)


if __name__ == '__main__':
    main()
