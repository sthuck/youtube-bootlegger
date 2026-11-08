# Build with: uv run pyinstaller --noconfirm main.spec -- --ui qml
# or:        uv run pyinstaller --noconfirm main.spec -- --ui tui
import argparse
from pathlib import Path
import sys

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

parser = argparse.ArgumentParser()
parser.add_argument('--ui', choices=('qml', 'tui'), required=True)
ui = parser.parse_args().ui
name = f'youtube-bootlegger-{ui}'
is_qml = ui == 'qml'

# Do not import the source package here: the pyinstaller console entry point
# doesn't add SPECPATH to sys.path until Analysis runs. collect_data_files()
# would silently return [] before that, unlike python -m PyInstaller.
root = Path(SPECPATH)
package = root / 'src' / 'youtube_bootlegger'
asset_dirs = ('assets', 'qml') if is_qml else ('assets', 'tui')
datas = []
for directory in asset_dirs:
    for source in sorted((package / directory).rglob('*')):
        if (source.is_file() and '__pycache__' not in source.parts
                and source.suffix not in {'.py', '.pyc', '.pyo', '.pyi'}):
            destination = Path('src/youtube_bootlegger') / source.parent.relative_to(package)
            datas.append((str(source), str(destination)))
hiddenimports = []
excludes = ['src.youtube_bootlegger.ui', 'youtube_bootlegger.ui']
if is_qml:
    # QML imports QtQuick dynamically; its hook collects Qt's QML plugins.
    hiddenimports += ['PySide6.QtQuick']
    excludes += ['textual', 'textual_image']
else:
    datas += collect_data_files('textual')
    datas += collect_data_files('textual_image')
    hiddenimports += collect_submodules('textual.widgets')
    # The TUI uses QtCore for settings/locks. Its injected browser/clipboard
    # handlers don't need the Qt GUI defaults in llm/chatgpt_lite.py.
    excludes += ['PySide6.QtGui', 'PySide6.QtWidgets', 'PySide6.QtQml',
                 'PySide6.QtQuick', 'src.youtube_bootlegger.qml_backend']

a = Analysis(
    [str(root / f'main_{ui}.py')],
    pathex=[SPECPATH],
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=excludes,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name=name,
    console=not is_qml,
    upx=False,
)
if sys.platform == 'darwin' and is_qml:
    app = BUNDLE(
        exe,
        name=f'{name}.app',
        bundle_identifier='com.youtube-bootlegger.qml',
        info_plist={'CFBundleDisplayName': 'YouTube Bootlegger'},
    )
