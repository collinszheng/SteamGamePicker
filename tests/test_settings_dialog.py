"""T6.1 / T6.2 / T6.3 设置窗口、首次引导与关于窗口测试（AC-04 / AC-39）。"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.config import DEFAULT_THRESHOLD_MINUTES, DEFAULT_TTL_DAYS, Config, ConfigStore
from app.state import AppState
from app.ui import settings_dialog
from app.ui.main_window import MainWindow
from app.ui.settings_dialog import (
    API_KEY_URL,
    MSG_KEY_EMPTY,
    MSG_KEY_FORMAT,
    MSG_THRESHOLD,
    MSG_TTL,
    AboutDialog,
    SettingsDialog,
    validate_api_key,
    validate_positive_int,
)

VALID_KEY = "0123456789abcdef0123456789ABCDEF"


@pytest.fixture()
def store(tmp_path: Path) -> ConfigStore:
    instance = ConfigStore(tmp_path / "SteamGamePicker")
    instance.ensure_dirs()
    return instance


@pytest.fixture()
def dialogs():
    created: list[SettingsDialog | AboutDialog] = []
    yield created
    for dialog in created:
        dialog.close()


def make_dialog(root, store: ConfigStore, dialogs, **kwargs) -> SettingsDialog:
    dialog = SettingsDialog(root, config=kwargs.pop("config", Config()), store=store, **kwargs)
    dialogs.append(dialog)
    return dialog


# ------------------------------------------------------------------ 校验规则
@pytest.mark.parametrize(
    "value",
    [VALID_KEY, VALID_KEY.lower(), f"  {VALID_KEY}  "],
)
def test_validate_api_key_accepts_32_hex(value: str) -> None:
    assert validate_api_key(value) is None


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("", MSG_KEY_EMPTY),
        ("   ", MSG_KEY_EMPTY),
        (None, MSG_KEY_EMPTY),
        ("0123456789abcdef0123456789ABCDE", MSG_KEY_FORMAT),  # 31 位
        ("0123456789abcdef0123456789ABCDEF0", MSG_KEY_FORMAT),  # 33 位
        ("0123456789abcdef0123456789ABCDEG", MSG_KEY_FORMAT),  # 非十六进制
        ("这不是一个-key", MSG_KEY_FORMAT),
    ],
)
def test_validate_api_key_rejects_bad_values(value: str | None, expected: str) -> None:
    assert validate_api_key(value) == expected


def test_validate_positive_int() -> None:
    assert validate_positive_int("120", low=1, high=100000, message=MSG_THRESHOLD) == (120, None)
    assert validate_positive_int("abc", low=1, high=100000, message=MSG_THRESHOLD) == (
        None,
        MSG_THRESHOLD,
    )
    assert validate_positive_int("0", low=1, high=100000, message=MSG_THRESHOLD) == (
        None,
        MSG_THRESHOLD,
    )
    assert validate_positive_int("", low=1, high=365, message=MSG_TTL) == (None, MSG_TTL)
    assert validate_positive_int("-5", low=1, high=365, message=MSG_TTL) == (None, MSG_TTL)


# ------------------------------------------------------------------ 设置窗口
def test_save_rejects_invalid_key(root, store: ConfigStore, dialogs) -> None:
    """AC-04：非法 Key 必须被拒绝并说明格式要求。"""
    dialog = make_dialog(root, store, dialogs)
    dialog.key_var.set("short-key")

    assert dialog.save() is False
    assert dialog.error_text() == MSG_KEY_FORMAT
    assert store.config_path.exists() is False
    assert dialog.exists() is True


def test_save_rejects_invalid_threshold_and_ttl(root, store: ConfigStore, dialogs) -> None:
    dialog = make_dialog(root, store, dialogs)
    dialog.key_var.set(VALID_KEY)

    dialog.threshold_var.set("零")
    assert dialog.save() is False
    assert dialog.error_text() == MSG_THRESHOLD

    dialog.threshold_var.set(str(DEFAULT_THRESHOLD_MINUTES))
    dialog.ttl_var.set("0")
    assert dialog.save() is False
    assert dialog.error_text() == MSG_TTL


def test_save_persists_config_and_calls_back(root, store: ConfigStore, dialogs) -> None:
    saved: list[bool] = []
    dialog = make_dialog(root, store, dialogs, on_saved=lambda: saved.append(True))
    dialog.key_var.set(VALID_KEY)
    dialog.threshold_var.set("60")
    dialog.ttl_var.set("3")

    assert dialog.save() is True

    config = store.load().config
    assert config.api_key == VALID_KEY
    assert config.playtime_threshold_minutes == 60
    assert config.details_cache_ttl_days == 3
    assert saved == [True]
    assert dialog.exists() is False, "保存后窗口应关闭"


def test_show_toggle_switches_password_mode(root, store: ConfigStore, dialogs) -> None:
    dialog = make_dialog(root, store, dialogs)
    assert str(dialog.key_entry.cget("show")) == "*"

    dialog.show_check.invoke()
    assert str(dialog.key_entry.cget("show")) == ""

    dialog.show_check.invoke()
    assert str(dialog.key_entry.cget("show")) == "*"


def test_first_run_mode_differs_from_settings(root, store: ConfigStore, dialogs) -> None:
    normal = make_dialog(root, store, dialogs)
    first = make_dialog(root, store, dialogs, first_run=True)

    assert normal.window.title() == "设置"
    assert first.window.title() == "首次设置"


def test_api_key_link_opens_steam_page(root, store: ConfigStore, dialogs, monkeypatch) -> None:
    opened: list[str] = []
    monkeypatch.setattr(settings_dialog.webbrowser, "open", lambda url: opened.append(url))

    dialog = make_dialog(root, store, dialogs, first_run=True)
    dialog.link_button.invoke()

    assert opened == [API_KEY_URL]


def test_open_log_directory_button(root, store: ConfigStore, dialogs, monkeypatch) -> None:
    targets: list[Path] = []
    monkeypatch.setattr(settings_dialog, "open_directory", lambda path: targets.append(path))

    dialog = make_dialog(root, store, dialogs)
    dialog.log_button.invoke()

    assert targets == [store.logs_dir]


def test_cancel_closes_without_saving(root, store: ConfigStore, dialogs) -> None:
    dialog = make_dialog(root, store, dialogs)
    dialog.key_var.set(VALID_KEY)
    dialog.cancel()

    assert dialog.exists() is False
    assert store.config_path.exists() is False


# ------------------------------------------------------------------ 关于窗口
def test_about_dialog_shows_version_and_paths(root, store: ConfigStore, dialogs) -> None:
    dialog = AboutDialog(root, store=store)
    dialogs.append(dialog)

    texts = [
        str(child.cget("text"))
        for child in dialog.window.winfo_children()[0].winfo_children()
        if child.winfo_class() == "TLabel"
    ]
    joined = "\n".join(texts)
    assert "版本 v" in joined
    assert str(store.logs_dir) in joined
    assert "不上传" in joined


# ------------------------------------------------------------------ 主窗集成
def test_main_window_opens_settings_and_applies_key_change(root, store: ConfigStore) -> None:
    config = Config(api_key="")
    window = MainWindow(root, store=store, config=config)

    window.on_settings()
    dialog = window._settings_dialog
    assert dialog is not None and dialog.exists()

    dialog.key_var.set(VALID_KEY)
    assert dialog.save() is True

    assert window.config.api_key == VALID_KEY
    assert window.state is AppState.IDLE
    assert window.status_text() == "设置已保存"


def test_first_run_guide_can_be_closed_without_crash(root, store: ConfigStore) -> None:
    """AC-39：不填 Key 直接关掉引导窗，主窗停在 S0 且不报错。"""
    window = MainWindow(root, store=store, config=Config(api_key=""))
    dialog = window.start_first_run_guide()
    assert dialog.exists() is True

    dialog.cancel()

    assert window.state is AppState.NO_KEY
    assert str(window.draw_button.cget("state")) == "disabled"
    assert window.status_text() == "请先在设置中填写 Steam API Key"


def test_settings_dialog_is_reused_not_stacked(root, store: ConfigStore) -> None:
    window = MainWindow(root, store=store, config=Config(api_key=VALID_KEY))
    window.on_settings()
    first = window._settings_dialog

    window.on_settings()

    assert window._settings_dialog is first
    first.close()  # type: ignore[union-attr]
