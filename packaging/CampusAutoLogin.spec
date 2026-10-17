from pathlib import Path
from PyInstaller.utils.hooks import collect_all

root = Path(SPECPATH).parent
datas, binaries, hiddenimports = collect_all('webview')
datas += [(str(root / 'assets'), 'assets'), (str(root / 'webui'), 'webui')]
a = Analysis(
    [str(root / 'campus_auto_login.py')], pathex=[str(root)],
    binaries=binaries, datas=datas, hiddenimports=hiddenimports,
    excludes=['numpy', 'tkinter', 'customtkinter', 'PyQt5', 'PyQt6', 'PySide2', 'PySide6',
              'webview.platforms.qt', 'webview.platforms.gtk', 'webview.platforms.cocoa',
              'webview.platforms.cef', 'webview.platforms.android'],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas, [], name='CampusAutoLogin',
    debug=False, strip=False, upx=False, console=False,
    version=str(root / 'packaging' / 'windows-version.txt'),
    icon=str(root / 'assets' / 'app-icon.ico'),
)
