# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller macOS spec：产出 "Bytego Image Master.app"。

由 mac/build_mac.sh 调用，不要在 Windows 上运行本文件。
与 build.py（Windows）保持同一入口 main.py 与相同的数据文件。
"""
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(SPECPATH).resolve().parent
RES = ROOT / "bytego_image_master" / "resources"
APP_NAME = "Bytego Image Master"
DISPLAY_NAME = "Bytego中转站GPT-Image/Grok Image Master"
VERSION = "1.1.0"
BUNDLE_ID = "team.bytego.imagemaster"

ICON = RES / "icon.icns"
datas = [(str(RES / "icon.png"), "bytego_image_master/resources")]

a = Analysis(
    [str(ROOT / "main.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=collect_submodules("requests") + ["PIL.Image"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name=APP_NAME,
)

app = BUNDLE(
    coll,
    name=f"{APP_NAME}.app",
    icon=str(ICON) if ICON.exists() else None,
    bundle_identifier=BUNDLE_ID,
    info_plist={
        "CFBundleDisplayName": DISPLAY_NAME,
        "CFBundleName": APP_NAME,
        "CFBundleShortVersionString": VERSION,
        "CFBundleVersion": VERSION,
        "NSHighResolutionCapable": True,
        "NSHumanReadableCopyright": "Copyright (c) 2026 NL-1234 · QQ 2265242381",
    },
)
