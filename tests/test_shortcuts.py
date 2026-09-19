"""T6.5 键盘映射测试（PRD 11.4 / AC-37 / AC-45 / AC-46）。

焦点无法在 withdraw 的窗口上稳定设置，因此直接替换 ``_focused_class``
来验证"按焦点分流"的分支。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.config import Config, ConfigStore
from app.models import Game
from app.state import AppState
from app.ui.main_window import MainWindow

KEY = "K" * 32


class FakeTask:
    def __init__(self) -> None:
        self.cancelled = False

    def cancel(self) -> None:
        self.cancelled = True


class FakeWorker:
    def __init__(self) -> None:
        self.submitted: list[dict[str, object]] = []

    def submit(self, fn, *, on_done=None, on_error=None, on_cancelled=None):  # type: ignore[no-untyped-def]
        self.submitted.append({"fn": fn, "on_done": on_done, "on_error": on_error})
        return FakeTask()


class FakeClient:
    def get_owned_games(self, steamid: str, token=None):  # type: ignore[no-untyped-def]
        return [Game(appid=1, name="Alpha", playtime_forever=0)]


@pytest.fixture()
def store(tmp_path: Path) -> ConfigStore:
    instance = ConfigStore(tmp_path / "SteamGamePicker")
    instance.ensure_dirs()
    return instance


@pytest.fixture()
def window(root, store: ConfigStore) -> MainWindow:
    instance = MainWindow(root, store=store, config=Config(api_key=KEY))
    instance.worker = FakeWorker()
    instance.client = FakeClient()
    instance.set_games(
        [Game(appid=1, name="Alpha", playtime_forever=0), Game(appid=2, name="Beta", playtime_forever=9)]
    )
    return instance


def test_shortcuts_are_bound_on_root(window: MainWindow) -> None:
    for sequence in ("<space>", "<F5>", "<Control-comma>", "<Escape>"):
        assert window.root.bind(sequence), f"{sequence} 未绑定"


def test_space_starts_draw(window: MainWindow) -> None:
    """AC-45：焦点不在输入框/按钮上时空格触发抽签。"""
    window._focused_class = lambda: "TTreeview"  # type: ignore[method-assign]

    result = window._on_space_key(None)

    assert result == "break"
    assert window.state is AppState.DRAWING
    assert window.winner is not None


def test_space_does_nothing_when_draw_disabled(root, store: ConfigStore) -> None:
    instance = MainWindow(root, store=store, config=Config(api_key=KEY))
    instance._focused_class = lambda: "TTreeview"  # type: ignore[method-assign]

    assert instance._on_space_key(None) is None
    assert instance.winner is None


@pytest.mark.parametrize("widget_class", ["TEntry", "Entry", "Text", "TButton", "Button"])
def test_space_defers_to_native_widget(window: MainWindow, widget_class: str) -> None:
    """输入框里的空格仍是输入空格；按钮上的空格交给按钮本身（避免一次按键两个动作）。"""
    window._focused_class = lambda: widget_class  # type: ignore[method-assign]

    assert window._on_space_key(None) is None
    assert window.winner is None


def test_f5_triggers_refresh(window: MainWindow) -> None:
    calls: list[bool] = []
    window.start_load = lambda refresh=False: calls.append(refresh)  # type: ignore[method-assign]

    window._on_refresh_key(None)

    assert calls == [True]


def test_f5_ignored_while_loading(window: MainWindow) -> None:
    calls: list[bool] = []
    window.start_load = lambda refresh=False: calls.append(refresh)  # type: ignore[method-assign]
    window.set_state(AppState.LOADING)

    window._on_refresh_key(None)

    assert calls == []


def test_ctrl_comma_opens_settings(window: MainWindow) -> None:
    calls: list[bool] = []
    window.on_settings = lambda: calls.append(True)  # type: ignore[method-assign]

    window._on_settings_key(None)

    assert calls == [True]


def test_escape_cancels_running_load(window: MainWindow) -> None:
    window.identity_var.set("76561198260031749")
    window.start_load()
    task = window._load_task
    assert task is not None

    window._on_escape_key(None)

    assert task.cancelled is True


def test_escape_closes_settings_dialog(window: MainWindow) -> None:
    window.on_settings()
    dialog = window._settings_dialog
    assert dialog is not None and dialog.exists()

    window._on_escape_key(None)

    assert dialog.exists() is False
