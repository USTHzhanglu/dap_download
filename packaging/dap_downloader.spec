# -*- mode: python ; coding: utf-8 -*-

import os
import sys
from PyInstaller.utils.hooks import (
    collect_data_files,
    collect_dynamic_libs,
    collect_entry_point,
    get_package_paths,
)
from PyInstaller.utils.win32.versioninfo import (
    VSVersionInfo,
    FixedFileInfo,
    StringFileInfo,
    StringTable,
    StringStruct,
    VarFileInfo,
    VarStruct,
)

SP = os.path.abspath(os.path.join(SPECPATH, '..'))

sys.path.insert(0, os.path.join(SP, 'src'))
from version import __appname__, __version__, __copyright__


def _ver_tuple(s):
    parts = s.split('.') + ['0'] * 4
    return tuple(int(p) for p in parts[:4])


_ver = _ver_tuple(__version__)
version_info = VSVersionInfo(
    ffi=FixedFileInfo(filevers=_ver, prodvers=_ver, mask=0x3f, flags=0x0,
                      OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
    kids=[
        StringFileInfo([StringTable('040904b0', [
            StringStruct('CompanyName', __copyright__),
            StringStruct('FileDescription', __appname__),
            StringStruct('FileVersion', __version__),
            StringStruct('InternalName', __appname__),
            StringStruct('OriginalFilename', __appname__ + '.exe'),
            StringStruct('ProductName', __appname__),
            StringStruct('ProductVersion', __version__),
        ])]),
        VarFileInfo([VarStruct('Translation', [1033, 1200])]),
    ],
)

datas_probe, hiddenimports_probe = collect_entry_point('pyocd.probe')
datas_rtos, hiddenimports_rtos = collect_entry_point('pyocd.rtos')


block_cipher = None


a = Analysis(
    [os.path.join(SP, 'src', 'dap_downloader.py')],
    pathex=[],
    binaries=collect_dynamic_libs('libusb_package'),
    datas=collect_data_files('pyocd', excludes=['debug/svd']) + [
        (get_package_paths('pylink')[1], 'pylink'),
    ] + datas_probe + datas_rtos,
    hiddenimports=hiddenimports_probe + hiddenimports_rtos,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['cmsis_pack_manager'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=__appname__,
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
    version=version_info,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name=__appname__,
)
