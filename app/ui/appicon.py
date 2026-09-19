"""窗口 / 任务栏图标（PRD D13 / AC-55）。

打包后的 exe 自带图标（PyInstaller 与 Inno Setup 都用同一个 ``assets/app.ico``），
Windows 会直接从 exe 里取。这个模块解决的是**源码运行**时的观感：
不设置的话，开发与测试时窗口和任务栏显示的是 Python 解释器的图标，
与「应用长什么样」不符。

要点：
* 只处理 Windows —— ``wm iconbitmap`` 在其它平台上不接受 ``.ico``；
* 找不到图标文件时安静返回 ``False``（图标属于装饰，缺了不能影响启动）；
* 用 ``default`` 形式设置，之后创建的设置窗、关于窗会自动继承。
"""

from __future__ import annotations

import sys
import tkinter as tk
from pathlib import Path

#: 相对仓库根（或 PyInstaller 解包目录）的图标位置
ICON_RELATIVE = Path("assets") / "app.ico"


def icon_path() -> Path | None:
    """返回可用的图标文件路径；找不到返回 ``None``。"""
    candidates: list[Path] = []
    bundle = getattr(sys, "_MEIPASS", None)  # PyInstaller 单文件解包目录
    if bundle:
        candidates.append(Path(bundle) / ICON_RELATIVE)
    candidates.append(Path(__file__).resolve().parents[2] / ICON_RELATIVE)
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def apply_window_icon(window: tk.Misc) -> bool:
    """把应用图标设为该窗口（及其后创建的顶层窗口）的图标。

    返回是否设置成功；任何失败都只是"没图标"，不抛给调用方。
    """
    if sys.platform != "win32":
        return False
    path = icon_path()
    if path is None:
        return False
    try:
        # 直接设置：让主窗口自身带上图标（可在截图/标题栏里看到）
        window.wm_iconbitmap(str(path))
        # default 形式：之后创建的设置窗、关于窗等顶层窗口自动继承
        window.wm_iconbitmap(default=str(path))
    except tk.TclError:  # pragma: no cover - 缺少图标支持的精简 Tk
        return False
    return True
