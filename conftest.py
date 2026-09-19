"""让 tests/ 可以直接 ``import app``，并提供共享的 Tk 测试窗口。

关于 Tk：Python 安装目录被整体搬运后，Tcl 可能找不到 ``init.tcl``，
因此在导入期显式设置 TCL_LIBRARY / TK_LIBRARY（标准做法）。
另外整个测试会话只创建一个隐藏窗口并复用 —— 反复创建 / 销毁 Tk 解释器
在本机会偶发初始化失败（"invalid command name tcl_findLibrary"）。
"""

from __future__ import annotations

import os
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_BASE = Path(sys.base_prefix)
for _var, _parts in (("TCL_LIBRARY", ("tcl", "tcl8.6")), ("TK_LIBRARY", ("tcl", "tk8.6"))):
    _candidate = _BASE.joinpath(*_parts)
    if _candidate.is_dir():
        os.environ.setdefault(_var, str(_candidate))


@pytest.fixture(scope="session")
def tk_root() -> Iterator[object]:
    import tkinter as tk

    try:
        instance = tk.Tk()
    except tk.TclError as exc:  # pragma: no cover - 无图形环境
        pytest.skip(f"当前环境无法创建 Tk 窗口：{exc}")
    instance.withdraw()
    try:
        yield instance
    finally:
        try:
            instance.destroy()
        except tk.TclError:  # pragma: no cover
            pass


@pytest.fixture()
def root(tk_root: object) -> Iterator[object]:
    """每个测试复用的隐藏窗口，测试前后清空子控件，保证互不干扰。"""
    for child in tk_root.winfo_children():  # type: ignore[attr-defined]
        child.destroy()
    yield tk_root
    for child in tk_root.winfo_children():  # type: ignore[attr-defined]
        child.destroy()
