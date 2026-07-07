# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files
from PyInstaller.utils.hooks import collect_dynamic_libs
from PyInstaller.utils.hooks import collect_submodules

datas = []
binaries = []
hiddenimports = ['PySide6.QtSvg']
datas += collect_data_files('ctranslate2')
binaries += collect_dynamic_libs('ctranslate2')
hiddenimports += collect_submodules('faster_whisper')


a = Analysis(
    ['C:\\Users\\tanzir\\Desktop\\projects\\voice_tray\\build\\voicetray_entry.py'],
    pathex=['C:\\Users\\tanzir\\Desktop\\projects\\voice_tray'],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['webrtcvad', 'torch', 'transformers', 'sklearn', 'scipy', 'pandas', 'django', 'PIL', 'pygame', 'yt_dlp'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='VoiceTray',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version='C:\\Users\\tanzir\\Desktop\\projects\\voice_tray\\build\\version_info.txt',
    icon=['assets\\tray\\mic_idle.ico'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='VoiceTray',
)
