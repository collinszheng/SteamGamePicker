"""T8.3 异常矩阵：AC-12 / AC-33 / AC-35（不需要账号凭据即可验证的部分）。

账号矩阵（AC-06 / AC-07 / AC-08 的真实账号验证）需要用户提供 API Key，
见 tools/live_check.py 与 docs/ACCEPTANCE.md。
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from app.cache import GameCache
from app.config import Config, ConfigStore
from app.models import Game, GameDetails
from app.state import AppState


def seed_machine_a(base: Path) -> ConfigStore:
    store = ConfigStore(base)
    store.ensure_dirs()
    config = Config(
        api_key="A" * 32,
        last_steam_id="76561198260031749",
        excluded_appids={1, 3},
        playtime_threshold_minutes=90,
        details_cache_ttl_days=5,
    )
    store.save(config)
    cache = GameCache(store, ttl_days=5)
    cache.save_snapshot(
        "76561198260031749",
        [Game(appid=1, name="Alpha", playtime_forever=0), Game(appid=2, name="Beta", playtime_forever=30)],
    )
    cache.put_detail(GameDetails(appid=1, name="Alpha", price_initial="¥ 48"))
    cache.put_image(1, b"fake-jpeg")
    return store


def test_ac35_whole_directory_migration(tmp_path: Path) -> None:
    """AC-35：整个 %APPDATA%\\SteamGamePicker 目录拷到另一台机器后立即可用。"""
    machine_a = tmp_path / "机器A" / "SteamGamePicker"
    seed_machine_a(machine_a)

    machine_b = tmp_path / "机器B" / "SteamGamePicker"
    shutil.copytree(machine_a, machine_b)

    store_b = ConfigStore(machine_b)
    loaded = store_b.load()
    assert loaded.corrupted is False
    assert loaded.config.api_key == "A" * 32
    assert loaded.config.last_steam_id == "76561198260031749"
    assert loaded.config.excluded_appids == {1, 3}
    assert loaded.config.playtime_threshold_minutes == 90
    assert loaded.config.details_cache_ttl_days == 5

    cache_b = GameCache(store_b, ttl_days=5)
    snapshot = cache_b.load_snapshot("76561198260031749")
    assert snapshot is not None and len(snapshot) == 2
    assert cache_b.get_detail(1) == GameDetails(appid=1, name="Alpha", price_initial="¥ 48")
    assert cache_b.get_image_path(1) is not None


def test_ac12_cache_directory_deleted(tmp_path: Path) -> None:
    """AC-12：缓存目录被手工删除后程序仍正常，不报错。"""
    store = ConfigStore(tmp_path / "SteamGamePicker")
    seed_machine_a(store.base_dir)
    shutil.rmtree(store.cache_dir)
    assert not store.cache_dir.exists()

    cache = GameCache(store)
    assert cache.load_snapshot("76561198260031749") is None
    assert cache.newest_snapshot() is None
    assert cache.get_detail(1) is None
    assert cache.get_image_path(1) is None
    assert cache.total_bytes() == 0
    assert cache.prune() == 0
    # 配置文件不受影响
    assert store.load().config.has_api_key is True


def test_ac33_leftover_temp_file_does_not_break_loading(tmp_path: Path) -> None:
    """AC-33：进程被强杀留下的临时文件不能影响启动。"""
    store = seed_machine_a(tmp_path / "SteamGamePicker")
    leftovers = [
        store.base_dir / ".config.json.9999.tmp",
        store.cache_dir / ".games_76561198260031749.json.9999.tmp",
    ]
    for path in leftovers:
        path.write_text('{"api_key": "半截写入', encoding="utf-8")

    loaded = store.load()
    assert loaded.corrupted is False
    assert loaded.config.api_key == "A" * 32

    cache = GameCache(store)
    snapshot = cache.load_snapshot("76561198260031749")
    assert snapshot is not None and len(snapshot) == 2

    # 清理动作不应误删真实数据
    cache.prune()
    assert store.config_path.exists()


def test_corrupt_snapshot_does_not_block_window(root, tmp_path: Path) -> None:
    """缓存损坏时窗口照常可用（改为走网络重新拉取，而不是崩溃）。"""
    from app.config import Config
    from app.models import Game
    from app.ui.main_window import MainWindow

    class FakeTask:
        def cancel(self) -> None:  # pragma: no cover - 本用例不需要
            pass

    class FakeWorker:
        def __init__(self) -> None:
            self.submitted: list[dict[str, object]] = []

        def submit(self, fn, *, on_done=None, on_error=None, on_cancelled=None):  # type: ignore[no-untyped-def]
            self.submitted.append({"fn": fn, "on_done": on_done, "on_error": on_error})
            return FakeTask()

    class FakeClient:
        def get_owned_games(self, steamid: str, token=None):  # type: ignore[no-untyped-def]
            return [Game(appid=1, name="Alpha", playtime_forever=0)]

    store = ConfigStore(tmp_path / "SteamGamePicker")
    store.ensure_dirs()
    store.snapshot_path("76561198260031749").write_text("{坏掉的缓存", encoding="utf-8")

    window = MainWindow(
        root, store=store, config=Config(api_key="K" * 32, last_steam_id="76561198260031749")
    )
    window.client = FakeClient()
    window.worker = FakeWorker()

    window.startup_load()  # 不应抛异常

    assert window.games == []
    assert window.state is AppState.LOADING, "损坏缓存必须退化为重新加载，而不是直接可用或报错"
    assert window.status_text() == "正在读取游戏库…"
    assert len(window.worker.submitted) == 1  # type: ignore[attr-defined]


def test_json_config_written_is_always_parseable(tmp_path: Path) -> None:
    """任何一次保存之后，磁盘上的 config.json 都必须是完整可解析的 JSON。"""
    store = seed_machine_a(tmp_path / "SteamGamePicker")
    for index in range(20):
        config = store.load().config
        config.excluded_appids = set(range(index))
        store.save(config)
        payload = json.loads(store.config_path.read_text(encoding="utf-8"))
        assert payload["excluded_appids"] == sorted(range(index))
    assert not list(store.base_dir.glob("*.tmp"))
