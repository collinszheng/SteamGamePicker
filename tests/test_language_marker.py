"""安装时选择的语言 → 首次运行继承（PRD D14 / AC-58）。

用假注册表后端测试，不依赖真实的 Windows 注册表；真实路径只有
``packaging/installer.iss`` 会写，两端常量必须一致（见 test_release.py）。
"""

from __future__ import annotations

import pytest

from app import language_marker
from app.language_marker import MARKER_KEY, MARKER_VALUE

HKEY_CURRENT_USER = 0x80000001
KEY_SET_VALUE = 0x0002


class FakeKey:
    def __init__(self, backend: FakeRegistry) -> None:
        self.backend = backend

    def __enter__(self) -> FakeKey:
        return self

    def __exit__(self, *_exc: object) -> None:
        return None


class FakeRegistry:
    """最小可用的 winreg 替身（只实现本模块用到的 4 个函数）。"""

    HKEY_CURRENT_USER = HKEY_CURRENT_USER
    KEY_SET_VALUE = KEY_SET_VALUE

    def __init__(self, value: str | None = None) -> None:
        self.values: dict[tuple[int, str], str] = {}
        self.deleted_keys: list[tuple[int, str]] = []
        if value is not None:
            self.values[(HKEY_CURRENT_USER, MARKER_KEY)] = value

    def OpenKey(self, root: int, path: str, _reserved: int = 0, _access: int = 0) -> FakeKey:
        if (root, path) not in self.values and path not in [
            key[1] for key in self.values
        ]:
            raise FileNotFoundError(path)
        return FakeKey(self)

    def QueryValueEx(self, _key: FakeKey, name: str) -> tuple[str, int]:
        for (_root, path), value in self.values.items():
            if name == MARKER_VALUE and path == MARKER_KEY:
                return value, 1
        raise FileNotFoundError(name)

    def DeleteValue(self, _key: FakeKey, name: str) -> None:
        if (HKEY_CURRENT_USER, MARKER_KEY) not in self.values:
            raise FileNotFoundError(name)
        del self.values[(HKEY_CURRENT_USER, MARKER_KEY)]

    def DeleteKey(self, root: int, path: str) -> None:
        self.deleted_keys.append((root, path))


def test_reads_the_installed_language() -> None:
    assert language_marker.read_language(FakeRegistry("en")) == "en"
    assert language_marker.read_language(FakeRegistry("zh")) == "zh"


@pytest.mark.parametrize("value", ["fr", "", "english", "  "])
def test_unknown_values_are_rejected(value: str) -> None:
    assert language_marker.read_language(FakeRegistry(value)) is None


@pytest.mark.parametrize("value", ["ZH", "En", " EN "])
def test_values_are_case_insensitive(value: str) -> None:
    """安装脚本写的是小写，但注册表是人可编辑的，大小写差异不该让语言失效。"""
    assert language_marker.read_language(FakeRegistry(value)) in ("zh", "en")


def test_missing_value_returns_none() -> None:
    assert language_marker.read_language(FakeRegistry()) is None


def test_delete_removes_value_and_empty_key() -> None:
    backend = FakeRegistry("en")
    assert language_marker.delete_language(backend) is True
    assert backend.values == {}
    assert backend.deleted_keys == [(HKEY_CURRENT_USER, MARKER_KEY)]


def test_delete_reports_false_when_absent() -> None:
    assert language_marker.delete_language(FakeRegistry()) is False


def test_take_returns_and_clears() -> None:
    """标记只服务首次运行：取走一次之后必须消失，避免下次启动再被它影响。"""
    backend = FakeRegistry("en")
    assert language_marker.take_first_run_language(backend) == "en"
    assert language_marker.take_first_run_language(backend) is None


def test_non_windows_is_a_no_op(monkeypatch: pytest.MonkeyPatch) -> None:
    """非 Windows 环境没有注册表：读取返回 None，删除返回 False，且不抛异常。"""
    monkeypatch.setattr(language_marker.sys, "platform", "linux")
    assert language_marker.read_language() is None
    assert language_marker.delete_language() is False
    assert language_marker.take_first_run_language() is None


def test_key_layout_is_documented() -> None:
    """注册表位置是安装脚本与应用之间的契约，改动必须是有意识的。"""
    assert MARKER_KEY == r"Software\SteamGamePicker"
    assert MARKER_VALUE == "Language"
