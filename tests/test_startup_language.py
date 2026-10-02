"""安装时选择的语言在首次运行时生效（PRD D14 / AC-58）。

规则：已有 config.json → 听配置；没有配置 → 用安装时写下的语言；标记取走即删。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app import language_marker
from app.config import LANGUAGE_EN, LANGUAGE_ZH, Config, ConfigStore, LoadResult
from main import resolve_startup_language


@pytest.fixture()
def store(tmp_path: Path) -> ConfigStore:
    instance = ConfigStore(tmp_path / "SteamGamePicker")
    instance.ensure_dirs()
    return instance


def test_first_run_uses_the_installed_language(
    store: ConfigStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(language_marker, "take_first_run_language", lambda: LANGUAGE_EN)

    result = LoadResult(Config())
    assert resolve_startup_language(store, result, None) == LANGUAGE_EN
    assert result.config.language == LANGUAGE_EN
    # 立刻落盘：否则标记已删除，下次启动会退回默认语言
    assert store.load().config.language == LANGUAGE_EN


def test_marker_applies_even_when_a_config_already_exists(
    store: ConfigStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    """标记只在"全新安装的首次运行"存在，所以它出现时就应该生效。

    升级安装不会写这个值（只写在新装时），因此不存在"覆盖老用户选择"的问题。
    """
    store.save(Config(language=LANGUAGE_ZH))
    monkeypatch.setattr(language_marker, "take_first_run_language", lambda: LANGUAGE_EN)

    result = store.load()
    assert resolve_startup_language(store, result, None) == LANGUAGE_EN
    assert store.load().config.language == LANGUAGE_EN


def test_no_marker_keeps_the_configured_language(
    store: ConfigStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(language_marker, "take_first_run_language", lambda: None)
    result = LoadResult(Config())
    assert resolve_startup_language(store, result, None) == LANGUAGE_ZH


def test_corrupted_config_is_not_treated_as_first_run(
    store: ConfigStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    """配置损坏会被重置为默认值，但那不是"首次运行"，不该套用安装语言。"""
    store.ensure_dirs()
    store.config_path.write_text("{坏了", encoding="utf-8")
    result = store.load()
    assert result.corrupted is True

    called: list[int] = []
    monkeypatch.setattr(
        language_marker, "take_first_run_language", lambda: called.append(1) or LANGUAGE_EN
    )

    assert resolve_startup_language(store, result, None) == LANGUAGE_ZH
    assert called == [1], "陈旧标记仍应被清掉，只是不生效"


def test_save_failure_does_not_break_startup(
    store: ConfigStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(language_marker, "take_first_run_language", lambda: LANGUAGE_EN)

    def boom(_config: Config) -> None:
        raise OSError("磁盘满了")

    monkeypatch.setattr(store, "save", boom)

    class Logger:
        warnings: list[str] = []

        def warning(self, message: str, *_args: object) -> None:
            self.warnings.append(message)

    logger = Logger()
    assert resolve_startup_language(store, LoadResult(Config()), logger) == LANGUAGE_EN
    assert logger.warnings, "写盘失败要留下日志，但不影响启动"
