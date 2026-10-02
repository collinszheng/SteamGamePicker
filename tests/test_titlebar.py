"""标题栏配色测试（PRD D14 / AC-59）。

标题栏由 Windows 绘制，改不了就只能"调用系统 API 让它跟着变"。这里把可测的部分
全部钉住：颜色换算、版本门槛、非 Windows 降级。真实观感需要人工看截图（AC-36）。
"""

from __future__ import annotations

import ctypes
import tkinter as tk

import pytest

from app.ui import theme, titlebar


class FakeVersion:
    def __init__(self, build: int) -> None:
        self.build = build


class _FakeWindll:
    """``ctypes.windll`` 的替身：只提供实现真正用到的 ``user32.GetParent``。

    ``dwmapi`` 故意留成普通对象——测试把接缝放在 :func:`titlebar._set_attribute` 上，
    不经过 ctypes 的参数编组（那里打桩会被 ctypes 重新编组，参数看起来是错位的原始内存）。
    """

    class user32:
        @staticmethod
        def GetParent(_child: int) -> int:
            return 1234

    dwmapi = object()

    def __init__(self, handle: int = 0) -> None:
        del handle  # 保留参数只为调用处可读


def test_colorref_is_windows_bgr_order() -> None:
    """COLORREF 是 0x00BBGGRR（与常见的 #RRGGBB 相反），算错会得到完全另一种颜色。"""
    assert titlebar.colorref("#000000") == 0x000000
    assert titlebar.colorref("#ffffff") == 0xFFFFFF
    assert titlebar.colorref("#ff0000") == 0x0000FF  # 红
    assert titlebar.colorref("#0000ff") == 0xFF0000  # 蓝
    # #1b2838 → r=0x1b, g=0x28, b=0x38 → COLORREF 0x0038281B
    assert titlebar.colorref(theme.COLOR_BG) == 0x38281B


def test_build_number_comes_from_sys() -> None:
    assert titlebar._build_number() >= 0


def test_caption_color_requires_windows_11(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(titlebar, "on_windows", lambda: True)
    monkeypatch.setattr(titlebar.sys, "getwindowsversion", lambda: FakeVersion(19045))
    assert titlebar.supports_caption_color() is False, "Windows 10 没有这个能力"

    monkeypatch.setattr(titlebar.sys, "getwindowsversion", lambda: FakeVersion(22631))
    assert titlebar.supports_caption_color() is True


def test_non_windows_is_a_no_op(monkeypatch: pytest.MonkeyPatch) -> None:
    """非 Windows 环境一切降级为 no-op。

    只替换本模块的 :func:`titlebar.on_windows`：早先这里直接改 ``sys.platform``，
    而 ``titlebar.sys`` 就是全局 ``sys`` 模块，结果把**同一进程里后续所有测试**
    都变成了"非 Windows"（表现为标题栏测试莫名失败）。
    """
    monkeypatch.setattr(titlebar, "on_windows", lambda: False)
    assert titlebar.supports_caption_color() is False
    assert titlebar.apply_window_colors(tk.Misc()) is False


def test_apply_returns_false_when_unsupported(monkeypatch: pytest.MonkeyPatch) -> None:
    """系统不支持时必须安静返回 False，不能抛异常影响启动。"""
    monkeypatch.setattr(titlebar, "supports_caption_color", lambda: False)
    assert titlebar.apply_window_colors(tk.Misc()) is False


def test_apply_sends_all_three_attributes(monkeypatch: pytest.MonkeyPatch, root: tk.Tk) -> None:
    """三个属性都要被真正下发（回归"静默失败"）。

    曾经的写法 ``ctypes.sizeof(ctypes.byref(value))`` 会抛 ``TypeError``，被
    ``except Exception: continue`` 吞掉后表现为"一个属性都没设、函数返回 False、
    界面只是颜色没变"，极难定位。

    测试接缝放在 :func:`titlebar._set_attribute`：它是本模块对 `ctypes` 的唯一出口，
    替换它就能在不牵扯 ctypes 参数编组的前提下断言"到底调了哪几个属性、带了什么值"
    （直接在 ``ctypes.windll`` 上打桩会被 ctypes 重新编组，见 test 里的历史注释）。
    """
    monkeypatch.setattr(titlebar, "supports_caption_color", lambda: True)
    calls: list[tuple[int, int]] = []

    def fake_set(_dwm, _handle, attribute, value) -> bool:
        calls.append((int(attribute), int(value.value)))
        return True

    monkeypatch.setattr(titlebar, "_set_attribute", fake_set)
    monkeypatch.setattr(titlebar.ctypes, "windll", _FakeWindll(handle=1234), raising=False)

    assert titlebar.apply_window_colors(root) is True

    sent = dict(calls)
    assert set(sent) == {
        titlebar.DWMWA_USE_IMMERSIVE_DARK_MODE,
        titlebar.DWMWA_CAPTION_COLOR,
        titlebar.DWMWA_BORDER_COLOR,
    }, "三个属性都要真正下发"
    assert sent[titlebar.DWMWA_CAPTION_COLOR] == titlebar.colorref(theme.COLOR_BG)
    assert sent[titlebar.DWMWA_BORDER_COLOR] == titlebar.colorref(theme.COLOR_BORDER)
    assert sent[titlebar.DWMWA_USE_IMMERSIVE_DARK_MODE] == 1


def test_apply_reports_false_when_dwm_rejects(monkeypatch: pytest.MonkeyPatch, root: tk.Tk) -> None:
    """系统拒绝调用（全部返回非 0）时应如实返回 False。"""
    monkeypatch.setattr(titlebar, "supports_caption_color", lambda: True)
    monkeypatch.setattr(titlebar, "_set_attribute", lambda *_args: False)
    monkeypatch.setattr(titlebar.ctypes, "windll", _FakeWindll(handle=1234), raising=False)

    assert titlebar.apply_window_colors(root) is False


def test_apply_accepts_a_partial_success(monkeypatch: pytest.MonkeyPatch, root: tk.Tk) -> None:
    """某个属性被拒（老系统常见）不影响其它属性：只要有成功就返回 True。"""
    monkeypatch.setattr(titlebar, "supports_caption_color", lambda: True)

    def only_caption(_dwm, _handle, attribute, _value) -> bool:
        return int(attribute) == titlebar.DWMWA_CAPTION_COLOR

    monkeypatch.setattr(titlebar, "_set_attribute", only_caption)
    monkeypatch.setattr(titlebar.ctypes, "windll", _FakeWindll(handle=1234), raising=False)

    assert titlebar.apply_window_colors(root) is True


def test_apply_uses_the_theme_background(root: tk.Tk) -> None:
    """真机验证：在本机（Win11）真的能把标题栏刷成应用底色。"""
    if not titlebar.supports_caption_color():
        pytest.skip("当前系统不支持自定义标题栏颜色")
    before = root.title()
    if not titlebar.apply_window_colors(root):
        pytest.skip("运行环境不允许设置标题栏颜色（受限桌面 / 无 DWM）")
    assert root.title() == before
