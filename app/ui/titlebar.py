"""标题栏跟随应用配色（PRD D14）。

问题：Windows 自己画标题栏。系统主题是浅色时，标题栏是浅灰的，跟应用的
Steam 深色界面并排看非常割裂。

做法：Windows 11（build 22000+）提供了 ``DwmSetWindowAttribute``，可以指定
标题栏底色与"深色模式"标志。这里就用它把标题栏刷成应用底色
:data:`app.ui.theme.COLOR_BG`，并把窗口边框也交给系统按深色绘制。

约束与降级：

* Windows 10 及更早版本没有这两个属性，调用无效但有返回值——
  此时**安静返回 False**，标题栏保持系统原样，不报错、不影响启动；
* 非 Windows 平台直接返回 False；
* 只依赖 ctypes 调用系统 DLL，不新增第三方依赖；
* 颜色取自 :mod:`app.ui.theme`，不在这里另立色板。
"""

from __future__ import annotations

import ctypes
import sys
import tkinter as tk

from app.ui import theme

#: DwmSetWindowAttribute 的属性编号（见 dwmapi.h）
DWMWA_USE_IMMERSIVE_DARK_MODE = 20
DWMWA_BORDER_COLOR = 34
DWMWA_CAPTION_COLOR = 35

#: 允许设置标题栏底色的最低 Windows 版本（Windows 11 21H2）
MIN_BUILD_FOR_CAPTION_COLOR = 22000


def on_windows() -> bool:
    """是否运行在 Windows 上。

    单独抽成函数是为了让测试可以只替换**本模块**的行为——直接改
    ``sys.platform`` 会污染整个解释器（``titlebar.sys`` 就是全局 ``sys`` 模块），
    让后续测试莫名其妙地走进"非 Windows"分支。
    """
    return sys.platform == "win32"


def _build_number() -> int:
    """当前 Windows 的 build 号；非 Windows 或取不到时返回 0。"""
    if not on_windows():
        return 0
    try:
        return int(sys.getwindowsversion().build)  # type: ignore[attr-defined]
    except Exception:  # pragma: no cover - 老 Python 或异常环境
        return 0


def colorref(color: str) -> int:
    """把 ``#rrggbb`` 转成 Windows 的 COLORREF（0x00BBGGRR）。"""
    red, green, blue = theme.hex_to_rgb(color)
    return red | (green << 8) | (blue << 16)


def supports_caption_color() -> bool:
    """当前系统是否支持自定义标题栏底色。"""
    return _build_number() >= MIN_BUILD_FOR_CAPTION_COLOR


def _set_attribute(dwm: object, handle: int, attribute: int, value: ctypes._SimpleCData) -> bool:  # type: ignore[name-defined]
    """调用一次 ``DwmSetWindowAttribute``；返回是否成功（HRESULT == 0）。

    长度取自传入的 ctypes 对象本身。**不要**写成 ``ctypes.sizeof(ctypes.byref(x))``：
    ``byref`` 返回的对象没有 size，会抛 ``TypeError``；一旦外面还有宽泛的
    ``except: continue``，就变成"调用全部静默失败、界面只是颜色没变"，极难定位
    （这个坑踩过一次，见 ``tests/test_titlebar.py``）。
    """
    result = dwm.DwmSetWindowAttribute(  # type: ignore[attr-defined]
        ctypes.c_void_p(handle),
        ctypes.c_uint(attribute),
        ctypes.byref(value),
        ctypes.sizeof(value),
    )
    return int(result) == 0


def apply_window_colors(window: tk.Misc, color: str | None = None) -> bool:
    """把标题栏刷成应用底色；任一属性设置成功即返回 True，全失败返回 False。"""
    if not on_windows():
        return False
    if not supports_caption_color():
        return False

    # Tk 的 winfo_id() 在 Windows 上给的是子窗口句柄，标题栏由它的顶层父窗口绘制
    try:
        child = int(window.winfo_id())
        parent = ctypes.windll.user32.GetParent(child)  # type: ignore[attr-defined]
    except Exception:  # pragma: no cover - 无窗口句柄
        return False
    handle = int(parent or child)
    if not handle:
        return False

    try:
        dwm = ctypes.windll.dwmapi  # type: ignore[attr-defined]
    except (AttributeError, OSError):  # pragma: no cover - 缺少 dwmapi
        return False

    # 逐条独立调用：某一条被系统拒绝不影响其它两条，也不吞掉"根本没调用"的情况
    applied = False
    colors = (
        (DWMWA_CAPTION_COLOR, ctypes.c_uint(colorref(color or theme.COLOR_BG))),
        (DWMWA_BORDER_COLOR, ctypes.c_uint(colorref(theme.COLOR_BORDER))),
        (DWMWA_USE_IMMERSIVE_DARK_MODE, ctypes.c_int(1)),
    )
    for attribute, value in colors:
        if _set_attribute(dwm, handle, attribute, value):
            applied = True
    return applied
