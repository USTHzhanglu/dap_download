# -*- mode: python ; coding: utf-8 -*-

import os
from PyInstaller.utils.hooks import collect_data_files

SP = os.path.abspath(os.path.join(SPECPATH, '..'))
VENV_SP = os.path.join(SP, 'venv', 'Lib', 'site-packages')


block_cipher = None


a = Analysis(
    [os.path.join(SP, 'src', 'dap_downloader.py')],
    pathex=[],
    binaries=[],
    datas=collect_data_files('pyocd') + [
        (os.path.join(VENV_SP, 'libusb_package', 'libusb-1.0.dll'), '.'),
        (os.path.join(VENV_SP, 'cmsis_pack_manager', 'cmsis_pack_manager', 'cmsis_pack_manager.dll'), 'cmsis_pack_manager/cmsis_pack_manager'),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
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
    name='dap_downloader',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
