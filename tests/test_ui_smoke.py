"""界面主题与 Tk 环境冒烟测试 + 列表性能（AC-18 / AC-36 的一部分）。

这些测试需要真实 Tk 环境（Windows 桌面）；窗口创建后立即 withdraw，
不弹出可见窗口。
"""

from __future__ import annotations

import time
import tkinter as tk
from tkinter import ttk

import pytest

from app.errors import LEVEL_ERROR, LEVEL_MUTED, LEVEL_OK, LEVEL_WARN
from app.ui import theme


def test_theme_values_match_prd(root: tk.Tk) -> None:
    """Steam 深色改版后的主题契约（配色细节见 test_ui_theme.py）。"""
    assert theme.FONT_FAMILY in theme.FONT_FAMILY_CANDIDATES
    assert theme.FONT_TITLE == (theme.FONT_FAMILY, 20, "bold")
    assert theme.FONT_ROLLING == (theme.FONT_FAMILY, 26, "bold")
    assert theme.COLOR_OK == "#a4d007"
    assert theme.COLOR_ROLLING == "#c6d4df"
    assert theme.COLOR_BG == "#1b2838"
    assert (theme.WINDOW_DEFAULT_WIDTH, theme.WINDOW_DEFAULT_HEIGHT) == (800, 600)
    assert (theme.WINDOW_MIN_WIDTH, theme.WINDOW_MIN_HEIGHT) == (640, 480)


@pytest.mark.parametrize(
    ("level", "expected"),
    [
        (LEVEL_OK, theme.COLOR_OK),
        (LEVEL_WARN, theme.COLOR_WARN),
        (LEVEL_ERROR, theme.COLOR_ERROR),
        (LEVEL_MUTED, theme.COLOR_MUTED),
        ("未知级别", theme.COLOR_MUTED),
    ],
)
def test_color_for_level(level: str, expected: str) -> None:
    assert theme.color_for_level(level) == expected


@pytest.mark.parametrize(
    ("window_width", "expected_width"),
    [(800, 240), (900, 270), (1000, 300), (640, 240), (400, 240)],
)
def test_header_image_size_keeps_aspect(window_width: int, expected_width: int) -> None:
    """封面宽度 = clamp(窗口宽 × 0.30, 240, 300)，保证默认 800 宽窗口下不过度占高。"""
    width, height = theme.header_image_size(window_width)
    assert width == expected_width
    assert height == round(width * 215 / 460)


def test_widgets_accept_theme_fonts(root: tk.Tk) -> None:
    label = ttk.Label(root, text="测试", font=theme.FONT_BODY)
    assert label.cget("font")
    assert theme.CHECK_ON == "☑" and theme.CHECK_OFF == "☐"


def test_treeview_handles_1000_rows_within_budget(root: tk.Tk) -> None:
    """AC-18：1000 款游戏展开 ≤ 2 秒。"""
    tree = ttk.Treeview(root, columns=("check", "name", "playtime"), show="headings")
    started = time.perf_counter()
    for index in range(1000):
        tree.insert(
            "",
            "end",
            iid=str(index),
            values=(theme.CHECK_ON, f"游戏 {index}", "12.3 小时"),
        )
    elapsed = time.perf_counter() - started

    assert len(tree.get_children()) == 1000
    assert elapsed < 2.0, f"插入 1000 行耗时 {elapsed:.2f}s，超出 2s 预算"


def test_treeview_checkbox_toggle_is_cheap(root: tk.Tk) -> None:
    """AC-18：单次勾选响应无可感延迟（1000 次切换 < 0.5 秒）。"""
    tree = ttk.Treeview(root, columns=("check", "name"), show="headings")
    for index in range(1000):
        tree.insert("", "end", iid=str(index), values=(theme.CHECK_ON, f"游戏 {index}"))

    started = time.perf_counter()
    for index in range(1000):
        tree.set(str(index), "check", theme.CHECK_OFF)
    elapsed = time.perf_counter() - started

    assert tree.set("999", "check") == theme.CHECK_OFF
    assert elapsed < 0.5, f"1000 次勾选耗时 {elapsed:.2f}s，超出预算"
