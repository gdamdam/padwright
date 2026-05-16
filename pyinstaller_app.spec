# PyInstaller spec for bundling web/app.py into a single-file executable
# that Tauri can invoke as a sidecar.
#
# Build (from repo root):
#   pip install pyinstaller
#   pyinstaller --clean pyinstaller_app.spec
#
# Output:
#   dist/sp404-server (or sp404-server.exe on Windows)
#
# Run scripts/install_sidecar.mjs to rename it with the target-triple
# suffix that Tauri expects (e.g. sp404-server-aarch64-apple-darwin) and
# copy it into src-tauri/binaries/.

# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

datas = []
# Bundle the Jinja templates and static assets that web/app.py serves.
datas += [('web/templates', 'web/templates'),
          ('web/static',    'web/static')]

# uvicorn pulls in dynamic deps; collect them aggressively.
hiddenimports = []
hiddenimports += collect_submodules('uvicorn')
hiddenimports += collect_submodules('starlette')
hiddenimports += collect_submodules('fastapi')
hiddenimports += [
    'multipart',           # python-multipart (Form support)
    'jinja2',
    'anyio._backends._asyncio',
    'email.mime.multipart',
    'email.mime.text',
]

a = Analysis(
    ['web/app.py'],
    pathex=['.'],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'PyQt5', 'PyQt6', 'PySide6'],
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='sp404-server',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,                # keep stdout/stderr for Tauri to read
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
