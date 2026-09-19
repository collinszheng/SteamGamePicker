# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置（T7.1）。

用法（在项目根目录执行）：
    python -m PyInstaller packaging/SteamGamePicker.spec --noconfirm

产物：dist/SteamGamePicker.exe（单文件、无控制台）。
说明：PRD 7.3 规定使用 --onefile；冷启动实测若超过 3 秒，
可把 EXE 的 onefile 形式改为 COLLECT 目录形式（onedir）并同步更新 PRD。
"""

from pathlib import Path

ROOT = Path(SPECPATH).parent  # noqa: F821 - SPECPATH 由 PyInstaller 注入

a = Analysis(  # noqa: F821
    [str(ROOT / "main.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[],
    hiddenimports=["PIL._tkinter_finder", "truststore"],
    hookspath=[],
    runtime_hooks=[],
    excludes=["pytest", "unittest", "pydoc_data", "test"],
    noarchive=False,
)

pyz = PYZ(a.pure)  # noqa: F821

exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="SteamGamePicker",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    icon=str(ROOT / "assets" / "app.ico"),
    version=None,
)
