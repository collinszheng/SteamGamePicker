"""T0.3 配置持久化测试（AC-31 / AC-32 / AC-33）。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.config import (
    DEFAULT_GEOMETRY,
    DEFAULT_THRESHOLD_MINUTES,
    DEFAULT_TTL_DAYS,
    PRESET_ALL,
    PRESET_NEVER,
    SORT_NAME,
    SORT_PLAYTIME,
    Config,
    ConfigStore,
)


@pytest.fixture()
def store(tmp_path: Path) -> ConfigStore:
    return ConfigStore(tmp_path / "SteamGamePicker")


def test_missing_file_returns_defaults(store: ConfigStore) -> None:
    result = store.load()
    assert result.corrupted is False
    assert result.config.api_key == ""
    assert result.config.excluded_appids == set()
    assert result.config.last_preset == PRESET_ALL
    assert store.config_path.exists() is False


def test_save_load_roundtrip(store: ConfigStore) -> None:
    config = Config(
        api_key="A" * 32,
        last_steam_id="76561198260031749",
        excluded_appids={570, 730},
        last_preset=PRESET_NEVER,
        playtime_threshold_minutes=60,
        details_cache_ttl_days=3,
    )
    config.ui.pool_panel_expanded = True
    config.ui.sort_key = SORT_PLAYTIME
    config.ui.sort_desc = True
    store.save(config)

    loaded = store.load()
    assert loaded.corrupted is False
    assert loaded.config == config
    assert loaded.config.excluded_appids == {570, 730}


def test_corrupt_json_is_backed_up_and_reset(store: ConfigStore) -> None:
    """AC-31：损坏的 config.json 必须被改名备份，程序按默认值继续。"""
    store.ensure_dirs()
    store.config_path.write_text("{ 这不是合法 JSON", encoding="utf-8")

    result = store.load()
    assert result.corrupted is True
    assert result.corrupted_backup is not None
    assert result.corrupted_backup.exists()
    assert result.corrupted_backup.name.startswith("config.corrupt-")
    assert result.config.api_key == ""
    # 原文件已改名，因此不存在半截配置
    assert not store.config_path.exists()


def test_non_object_json_is_treated_as_corrupt(store: ConfigStore) -> None:
    store.ensure_dirs()
    store.config_path.write_text("[1, 2, 3]", encoding="utf-8")
    result = store.load()
    assert result.corrupted is True
    assert result.config.last_preset == PRESET_ALL


def test_missing_fields_use_defaults(store: ConfigStore) -> None:
    """AC-32：字段缺失时使用默认值，不报错。"""
    store.ensure_dirs()
    store.config_path.write_text(json.dumps({"api_key": "K" * 32}), encoding="utf-8")

    config = store.load().config
    assert config.api_key == "K" * 32
    assert config.playtime_threshold_minutes == DEFAULT_THRESHOLD_MINUTES
    assert config.details_cache_ttl_days == DEFAULT_TTL_DAYS
    assert config.excluded_appids == set()
    assert config.ui.window_geometry == DEFAULT_GEOMETRY
    assert config.ui.sort_key == SORT_NAME
    assert config.ui.sort_desc is False


def test_wrong_types_are_coerced(store: ConfigStore) -> None:
    store.ensure_dirs()
    payload = {
        "api_key": 12345,
        "last_steam_id": None,
        "excluded_appids": ["570", 730, "abc", True, None, -5],
        "playtime_threshold_minutes": "abc",
        "details_cache_ttl_days": -5,
        "last_preset": "nope",
        "ui": {
            "sort_key": "bogus",
            "sort_desc": "yes",
            "pool_panel_expanded": 1,
            "window_geometry": 5,
        },
    }
    store.config_path.write_text(json.dumps(payload), encoding="utf-8")

    result = store.load()
    assert result.corrupted is False
    config = result.config
    assert config.api_key == ""
    assert config.last_steam_id == ""
    assert config.excluded_appids == {570, 730, -5}
    assert config.playtime_threshold_minutes == DEFAULT_THRESHOLD_MINUTES
    assert config.details_cache_ttl_days == DEFAULT_TTL_DAYS
    assert config.last_preset == PRESET_ALL
    assert config.ui.sort_key == SORT_NAME
    assert config.ui.sort_desc is False
    assert config.ui.pool_panel_expanded is False
    assert config.ui.window_geometry == DEFAULT_GEOMETRY


def test_atomic_write_leaves_no_temp_file(store: ConfigStore) -> None:
    """AC-33 的一部分：写盘后目录里不能残留临时文件，且内容始终是合法 JSON。"""
    store.save(Config(api_key="X" * 32))
    assert json.loads(store.config_path.read_text(encoding="utf-8"))["api_key"] == "X" * 32
    leftovers = [p for p in store.base_dir.iterdir() if p.name.endswith(".tmp")]
    assert leftovers == []


def test_corrupt_backups_keep_latest_three(store: ConfigStore) -> None:
    store.ensure_dirs()
    for _ in range(5):
        store.config_path.write_text("bad json", encoding="utf-8")
        assert store.load().corrupted is True
    backups = list(store.base_dir.glob("config.corrupt-*.json"))
    assert len(backups) == 3


def test_default_base_dir_uses_appdata(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))
    assert ConfigStore().base_dir == tmp_path / "Roaming" / "SteamGamePicker"


def test_default_base_dir_falls_back_without_appdata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("APPDATA", raising=False)
    assert ConfigStore().base_dir.name == ".steamgamepicker"


def test_has_api_key_ignores_whitespace() -> None:
    assert Config().has_api_key is False
    assert Config(api_key="   ").has_api_key is False
    assert Config(api_key="abc").has_api_key is True
