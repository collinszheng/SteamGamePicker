"""对话框的公共小工具（PRD D14）。

目前只有一件事：**把窗口摆到屏幕正中**。

Tk 的 ``Toplevel`` 默认出现在屏幕左上角，用户每次都要先把窗口拖到眼前，
体验很差。这里统一按"屏幕尺寸 − 窗口请求尺寸"取一半偏移。

要点：

* 必须在 ``update_idletasks()`` 之后取尺寸——之前 ``winfo_reqwidth()`` 还是 1，
  会把窗口"居中"到左上角（看起来像没生效）；
* 多显示器下用 ``winfo_screenwidth/height``（主显示器尺寸），不做跨屏居中，
  以免窗口被摆到两块屏的缝里；
* 任何取不到尺寸的异常都安静退回 Tk 默认位置，不影响窗口能打开。
"""

from __future__ import annotations

import tkinter as tk


def center_window(window: tk.Misc) -> tuple[int, int]:
    """把窗口摆到屏幕正中；返回实际使用的 (left, top) 偏移。"""
    try:
        window.update_idletasks()
        width = max(1, window.winfo_reqwidth())
        height = max(1, window.winfo_reqheight())
        screen_width = int(window.winfo_screenwidth())
        screen_height = int(window.winfo_screenheight())
    except (tk.TclError, TypeError):  # pragma: no cover - 无显示环境
        return (0, 0)
    left = max(0, (screen_width - width) // 2)
    top = max(0, (screen_height - height) // 2)
    try:
        window.geometry(f"+{left}+{top}")
    except tk.TclError:  # pragma: no cover - 控件已销毁
        return (0, 0)
    return left, top
