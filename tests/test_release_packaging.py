"""Exercise the release packaging CLI with standalone build outputs."""

from pathlib import Path
import subprocess
import sys
import tarfile
import zipfile

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'package_release.py'


@pytest.mark.parametrize('ui', ['qml', 'tui'])
@pytest.mark.parametrize('platform', ['linux-x64', 'windows-x64', 'macos-arm64'])
def test_package_single_executable(tmp_path, ui, platform):
    mac_app = platform == 'macos-arm64' and ui == 'qml'
    if mac_app and sys.platform != 'darwin':
        pytest.skip('macOS app bundles require ditto on a macOS runner')
    dist = tmp_path / 'dist'
    dist.mkdir()
    name = f'youtube-bootlegger-{ui}'
    executable = dist / (name + ('.exe' if platform == 'windows-x64' else ''))
    if mac_app:
        executable = dist / f'{name}.app' / 'Contents' / 'MacOS' / name
        executable.parent.mkdir(parents=True)
    executable.write_bytes(b'standalone executable with embedded assets')
    executable.chmod(0o755)
    subprocess.run([sys.executable, str(SCRIPT), '--ui', ui, '--platform', platform,
                    '--version', 'v1.2.3'], cwd=tmp_path, check=True)
    asset = dist / 'release' / f'{name}-v1.2.3-{platform}'
    if mac_app:
        with zipfile.ZipFile(f'{asset}.zip') as archive:
            assert archive.read(f'{name}.app/Contents/MacOS/{name}') == executable.read_bytes()
    elif platform == 'windows-x64':
        assert Path(f'{asset}.exe').read_bytes() == executable.read_bytes()
    else:
        with tarfile.open(f'{asset}.tar.gz') as archive:
            assert archive.getnames() == [name]
            assert archive.extractfile(name).read() == executable.read_bytes()
            assert archive.getmember(name).mode & 0o111


def test_reject_old_folder_bundle(tmp_path):
    (tmp_path / 'dist' / 'youtube-bootlegger-tui').mkdir(parents=True)
    result = subprocess.run(
        [sys.executable, str(SCRIPT), '--ui', 'tui', '--platform', 'linux-x64',
         '--version', 'v1.2.3'], cwd=tmp_path, capture_output=True, text=True,
    )
    assert result.returncode != 0
    assert 'missing build output' in result.stderr
