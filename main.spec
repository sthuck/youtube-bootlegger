# Build with: uv run pyinstaller --noconfirm main.spec -- --ui qml
# or:        uv run pyinstaller --noconfirm main.spec -- --ui tui
import argparse
import sys

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

parser = argparse.ArgumentParser()
parser.add_argument('--ui', choices=('qml', 'tui'), required=True)
ui = parser.parse_args().ui
name = f'youtube-bootlegger-{ui}'
is_qml = ui == 'qml'

# Keep the package-relative layout used by resources.py, QML and Textual CSS.
datas = collect_data_files('src.youtube_bootlegger')
hiddenimports = []
excludes = ['src.youtube_bootlegger.ui', 'youtube_bootlegger.ui']
if is_qml:
    # QML imports QtQuick dynamically; its hook collects Qt's QML plugins.
    hiddenimports += ['PySide6.QtQuick']
    excludes += ['textual', 'textual_image']
else:
    datas += collect_data_files('textual')
    hiddenimports += collect_submodules('textual.widgets')
    # The TUI uses QtCore for settings/locks. Its injected browser/clipboard
    # handlers don't need the Qt GUI defaults in llm/chatgpt_lite.py.
    excludes += ['PySide6.QtGui', 'PySide6.QtWidgets', 'PySide6.QtQml',
                 'PySide6.QtQuick', 'src.youtube_bootlegger.qml_backend']

a = Analysis(
    [f'main_{ui}.py'],
    pathex=[SPECPATH],
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=excludes,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=name,
    console=not is_qml,
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name=name, upx=False)
if sys.platform == 'darwin' and is_qml:
    app = BUNDLE(
        coll,
        name=f'{name}.app',
        bundle_identifier='com.youtube-bootlegger.qml',
        info_plist={'CFBundleDisplayName': 'YouTube Bootlegger'},
    )
