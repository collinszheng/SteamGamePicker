"""抽签记录测试（PRD D14 / AC-57）。

要点：只保留最近 10 条、最新在前、损坏文件不影响使用、清空后不再落盘。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cache import display_time
from app.config import ConfigStore
from app.history import MAX_ENTRIES, PickHistory


@pytest.fixture()
def store(tmp_path: Path) -> ConfigStore:
    instance = ConfigStore(tmp_path / "SteamGamePicker")
    instance.ensure_dirs()
    return instance


def test_missing_file_means_no_history(store: ConfigStore) -> None:
    history = PickHistory(store)
    assert history.load() == []
    assert len(history) == 0


def test_records_are_newest_first_and_persisted(store: ConfigStore) -> None:
    history = PickHistory(store)
    history.record(570, "Dota 2", picked_at="2026-09-19T15:04:05+08:00")
    history.record(730, "CS2", picked_at="2026-09-19T16:04:05+08:00")

    assert [entry.appid for entry in history.entries] == [730, 570]
    assert Path(history.path).exists()

    reloaded = PickHistory(store)
    assert [entry.appid for entry in reloaded.load()] == [730, 570]
    assert reloaded.entries[0].name == "CS2"


def test_only_the_last_ten_are_kept(store: ConfigStore) -> None:
    history = PickHistory(store)
    for index in range(MAX_ENTRIES + 5):
        history.record(1000 + index, f"Game {index}")

    assert len(history.entries) == MAX_ENTRIES
    # 最新的一条在最前，最老的 5 条已经被挤掉
    assert history.entries[0].name == f"Game {MAX_ENTRIES + 4}"
    assert all(entry.appid >= 1005 for entry in history.entries)

    reloaded = PickHistory(store)
    assert len(reloaded.load()) == MAX_ENTRIES


def test_display_time_uses_local_timezone(store: ConfigStore) -> None:
    history = PickHistory(store)
    entry = history.record(570, "Dota 2", picked_at="2026-09-19T15:04:05+08:00")
    assert entry.display_time == display_time("2026-09-19T15:04:05+08:00")


def test_clear_removes_the_file(store: ConfigStore) -> None:
    history = PickHistory(store)
    history.record(570, "Dota 2")
    assert Path(history.path).exists()

    history.clear()
    assert history.entries == []
    assert not Path(history.path).exists(), "清空后不该留下空记录文件"
    assert PickHistory(store).load() == []


@pytest.mark.parametrize(
    "payload",
    [
        "{ 这不是 JSON",
        "[]",
        '{"entries": "不是列表"}',
        '{"entries": [1, 2, 3]}',
        '{"entries": [{"appid": "abc"}]}',
    ],
)
def test_corrupt_or_unknown_payload_is_ignored(store: ConfigStore, payload: str) -> None:
    """损坏的记录文件绝不能影响启动，一律当作"没有记录"。"""
    store.ensure_dirs()
    Path(store.base_dir / "history.json").write_text(payload, encoding="utf-8")

    history = PickHistory(store)
    assert history.load() == []
    assert len(history) == 0


def test_entries_are_capped_when_loading_a_long_file(store: ConfigStore) -> None:
    """磁盘上被人为塞了 50 条，也只读最近 10 条。"""
    store.ensure_dirs()
    payload = {
        "schema_version": 1,
        "entries": [
            {"appid": index, "name": f"Game {index}", "picked_at": "2026-09-19T15:04:05+08:00"}
            for index in range(50)
        ],
    }
    Path(store.base_dir / "history.json").write_text(json.dumps(payload), encoding="utf-8")

    assert len(PickHistory(store).load()) == MAX_ENTRIES
