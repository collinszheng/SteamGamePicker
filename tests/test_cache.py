"""T1.5 缓存测试（AC-10 / AC-12 / AC-30）。"""

from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path

import pytest

from app.cache import (
    DEFAULT_MAX_CACHE_BYTES,
    GameCache,
    display_time,
    parse_iso,
    to_iso,
)
from app.config import ConfigStore
from app.models import Game, GameDetails

NOW = dt.datetime(2026, 9, 19, 15, 4, 5, tzinfo=dt.timezone(dt.timedelta(hours=8)))


class FakeClock:
    def __init__(self, moment: dt.datetime) -> None:
        self.moment = moment

    def __call__(self) -> dt.datetime:
        return self.moment

    def advance(self, **kwargs: float) -> None:
        self.moment += dt.timedelta(**kwargs)


@pytest.fixture()
def clock() -> FakeClock:
    return FakeClock(NOW)


@pytest.fixture()
def store(tmp_path: Path) -> ConfigStore:
    config_store = ConfigStore(tmp_path / "SteamGamePicker")
    config_store.ensure_dirs()
    return config_store


@pytest.fixture()
def cache(store: ConfigStore, clock: FakeClock) -> GameCache:
    return GameCache(store, ttl_days=7, now=clock)


def test_snapshot_roundtrip(cache: GameCache) -> None:
    games = [Game(570, "Dota 2", 1234, "abc"), Game(730, "CS2", 0, "")]
    saved = cache.save_snapshot("76561198260031749", games)

    loaded = cache.load_snapshot("76561198260031749")
    assert loaded == saved
    assert len(loaded) == 2  # type: ignore[arg-type]
    assert saved.updated_at == to_iso(NOW)
    assert saved.updated_display == "09-19 15:04"


def test_snapshot_drops_dirty_entries(cache: GameCache, store: ConfigStore) -> None:
    payload = {
        "schema_version": 1,
        "steamid64": "1",
        "updated_at": to_iso(NOW),
        "games": [
            {"appid": 0, "name": "脏数据"},
            {"appid": "570", "name": "X", "playtime_forever": 10},
            "不是对象",
        ],
    }
    store.snapshot_path("1").write_text(json.dumps(payload), encoding="utf-8")

    snapshot = cache.load_snapshot("1")
    assert snapshot is not None
    assert [g.appid for g in snapshot.games] == [570]


def test_corrupt_snapshot_is_ignored(cache: GameCache, store: ConfigStore) -> None:
    """AC-12：缓存损坏时当作没有缓存，不打断使用。"""
    store.snapshot_path("1").write_text("{不是 JSON", encoding="utf-8")
    assert cache.load_snapshot("1") is None


def test_unknown_schema_is_ignored(cache: GameCache, store: ConfigStore) -> None:
    store.snapshot_path("1").write_text(
        json.dumps({"schema_version": 99, "games": []}), encoding="utf-8"
    )
    assert cache.load_snapshot("1") is None


def test_missing_snapshot_returns_none(cache: GameCache) -> None:
    assert cache.load_snapshot("999") is None


def test_detail_roundtrip_then_expires(cache: GameCache, store: ConfigStore, clock: FakeClock) -> None:
    details = GameDetails(appid=570, name="Dota 2", is_free=True, price_initial=None)
    cache.put_detail(details)
    assert cache.get_detail(570) == details

    clock.advance(days=7, hours=1)
    assert cache.get_detail(570) is None
    assert not (store.details_dir / "570.json").exists()


def test_detail_fresh_within_ttl(cache: GameCache, clock: FakeClock) -> None:
    cache.put_detail(GameDetails(appid=1, name="A"))
    clock.advance(days=6, hours=23)
    assert cache.get_detail(1) is not None


def test_corrupt_detail_is_ignored(cache: GameCache, store: ConfigStore) -> None:
    (store.details_dir / "1.json").write_text("{坏了", encoding="utf-8")
    assert cache.get_detail(1) is None


def test_image_roundtrip_then_expires(cache: GameCache, clock: FakeClock) -> None:
    path = cache.put_image(570, b"\xff\xd8\xff\xe0fakejpeg")
    assert path.exists()
    assert cache.get_image_path(570) == path

    clock.advance(days=8)
    assert cache.get_image_path(570) is None


def test_missing_image_returns_none(cache: GameCache) -> None:
    assert cache.get_image_path(999) is None


def test_detail_expiry_removes_image(cache: GameCache, clock: FakeClock) -> None:
    cache.put_detail(GameDetails(appid=5))
    cache.put_image(5, b"x")
    clock.advance(days=30)
    assert cache.get_detail(5) is None
    assert cache.get_image_path(5) is None


def test_newest_snapshot(store: ConfigStore, clock: FakeClock) -> None:
    cache = GameCache(store, now=clock)
    cache.save_snapshot("111", [Game(1, "a")])
    cache.save_snapshot("222", [Game(2, "b")])
    os.utime(store.snapshot_path("111"), (1000, 1000))

    snapshot = cache.newest_snapshot()
    assert snapshot is not None
    assert snapshot.steamid64 == "222"

    os.utime(store.snapshot_path("222"), (500, 500))
    older = cache.newest_snapshot()
    assert older is not None and older.steamid64 == "111"


def test_prune_removes_oldest_until_under_limit(store: ConfigStore, clock: FakeClock) -> None:
    probe = GameCache(store, now=clock)
    probe.save_snapshot("1", [Game(1, "a")])
    snapshot_size = probe.total_bytes()

    old = store.details_dir / "1.json"
    old.write_bytes(b"x" * 150)
    os.utime(old, (1000, 1000))
    newer = store.details_dir / "2.json"
    newer.write_bytes(b"y" * 150)
    os.utime(newer, (2000, 2000))

    cache = GameCache(store, max_bytes=snapshot_size + 100, now=clock)
    assert cache.total_bytes() == snapshot_size + 300

    removed = cache.prune()
    assert removed == 2
    assert cache.total_bytes() <= cache.max_bytes
    assert not old.exists(), "最旧的缓存应先被清理"
    assert not newer.exists()
    assert store.snapshot_path("1").exists(), "最新库快照排在最后，应被保留"


def test_prune_honours_limit_even_if_only_snapshot_left(
    store: ConfigStore, clock: FakeClock
) -> None:
    """上限是硬保证：小到连快照都装不下时，快照也会被清理。"""
    cache = GameCache(store, max_bytes=1, now=clock)
    cache.save_snapshot("1", [Game(1, "a")])
    assert cache.total_bytes() > 1

    cache.prune()
    assert cache.total_bytes() <= 1
    assert not store.snapshot_path("1").exists()


def test_prune_does_nothing_when_under_limit(cache: GameCache) -> None:
    cache.save_snapshot("1", [Game(1, "a")])
    assert cache.prune() == 0


def test_clear_removes_cached_files(cache: GameCache) -> None:
    cache.save_snapshot("1", [Game(1, "a")])
    cache.put_detail(GameDetails(appid=1))
    cache.put_image(1, b"x")
    assert cache.total_bytes() > 0

    cache.clear()
    assert cache.total_bytes() == 0


def test_operations_are_safe_without_cache_dir(tmp_path: Path) -> None:
    store = ConfigStore(tmp_path / "还没有建目录")
    cache = GameCache(store)
    assert cache.total_bytes() == 0
    assert cache.prune() == 0
    assert cache.load_snapshot("1") is None
    assert cache.get_detail(1) is None
    assert cache.get_image_path(1) is None
    assert cache.newest_snapshot() is None


def test_default_capacity_limit_is_200mb() -> None:
    assert DEFAULT_MAX_CACHE_BYTES == 200 * 1024 * 1024


def test_time_helpers() -> None:
    assert display_time(to_iso(NOW)) == "09-19 15:04"
    assert display_time("") == ""
    assert display_time(None) == ""
    assert display_time("不是时间") == "不是时间"
    assert parse_iso(None) is None
    assert parse_iso(123) is None
    naive = parse_iso("2026-09-19T15:04:05")
    assert naive is not None and naive.tzinfo is not None
