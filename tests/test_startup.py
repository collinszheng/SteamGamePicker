"""T6.4 启动自动加载、缓存秒开与离线模式测试（AC-09 / AC-10）。"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.cache import GameCache
from app.config import Config, ConfigStore
from app.errors import AppError, Err
from app.models import Game
from app.state import AppState
from app.ui import theme
from app.ui.main_window import MainWindow

STEAMID = "76561198260031749"
KEY = "K" * 32
UPDATED_AT = "2026-09-19T15:04:05+08:00"


def make_games() -> list[Game]:
    return [
        Game(appid=1, name="Alpha 冒险", playtime_forever=0),
        Game(appid=2, name="Beta 射击", playtime_forever=30),
    ]


class FakeTask:
    def __init__(self) -> None:
        self.cancelled = False

    def cancel(self) -> None:
        self.cancelled = True


class FakeWorker:
    def __init__(self) -> None:
        self.submitted: list[dict[str, object]] = []

    def submit(self, fn, *, on_done=None, on_error=None, on_cancelled=None):  # type: ignore[no-untyped-def]
        self.submitted.append(
            {"fn": fn, "on_done": on_done, "on_error": on_error, "on_cancelled": on_cancelled}
        )
        return FakeTask()


class FakeClient:
    def __init__(self, games: list[Game] | None = None) -> None:
        self.games = games or make_games()

    def get_owned_games(self, steamid: str, token=None):  # type: ignore[no-untyped-def]
        return list(self.games)


@pytest.fixture()
def store(tmp_path: Path) -> ConfigStore:
    instance = ConfigStore(tmp_path / "SteamGamePicker")
    instance.ensure_dirs()
    return instance


def build(root, store: ConfigStore, *, seed_cache: bool = True, **config_kwargs) -> MainWindow:
    config = Config(api_key=KEY, **config_kwargs)
    config.last_steam_id = STEAMID
    if seed_cache:
        GameCache(store).save_snapshot(STEAMID, make_games(), moment=None)
    window = MainWindow(root, store=store, config=config)
    window.client = FakeClient()
    window.worker = FakeWorker()
    return window


def test_startup_uses_cache_then_refreshes(root, store: ConfigStore) -> None:
    """AC-09：有缓存时启动即可用，并显示"上次更新于"。"""
    window = build(root, store)

    window.startup_load()

    assert [g.appid for g in window.games] == [1, 2]
    assert window.state is AppState.READY
    assert window.identity_var.get() == STEAMID
    assert "已加载 2 款 · 2 款参与抽签" in window.status_text()
    assert "上次更新" in window.status_text()
    assert len(window.worker.submitted) == 1, "必须后台刷新一次"  # type: ignore[attr-defined]


def test_refresh_success_updates_snapshot_time(root, store: ConfigStore) -> None:
    window = build(root, store, seed_cache=False)
    window.startup_load()

    job = window.worker.submitted[-1]  # type: ignore[attr-defined]
    steamid, games = job["fn"](None)  # type: ignore[operator]
    job["on_done"]((steamid, games))  # type: ignore[operator]

    assert window.offline is False
    assert window.state is AppState.READY
    assert window.cache.load_snapshot(STEAMID) is not None


def test_refresh_failure_falls_back_to_offline(root, store: ConfigStore) -> None:
    """AC-10：后台刷新失败但有缓存 → 黄条提示，抽签仍可用。"""
    window = build(root, store)
    window.startup_load()

    window.on_refresh_failed(AppError(Err.NETWORK))

    assert window.offline is True
    assert window.state is AppState.OFFLINE
    assert window.status_text().startswith("当前离线，正在使用")
    assert window.status_color() == theme.COLOR_WARN
    assert str(window.draw_button.cget("state")) == "normal"


def test_refresh_rate_limit_also_goes_offline(root, store: ConfigStore) -> None:
    window = build(root, store)
    window.startup_load()

    window.on_refresh_failed(AppError(Err.RATE_LIMIT))

    assert window.offline is True
    assert window.state is AppState.OFFLINE


def test_refresh_private_profile_keeps_cached_games_usable(root, store: ConfigStore) -> None:
    """资料被改成私密时，缓存仍然可用，但要如实提示原因。"""
    window = build(root, store)
    window.startup_load()

    window.on_refresh_failed(AppError(Err.PRIVATE_PROFILE))

    assert "设为公开" in window.status_text()
    assert window.offline is False
    assert window.state is AppState.READY
    assert str(window.draw_button.cget("state")) == "normal"


def test_refresh_failure_without_games_reports_error(root, store: ConfigStore) -> None:
    window = build(root, store, seed_cache=False)
    window.startup_load()

    window.on_refresh_failed(AppError(Err.NETWORK))

    assert window.state is AppState.ERROR
    assert window.status_text() == "网络连接失败，请检查网络后重试"


def test_startup_without_cache_loads_from_network(root, store: ConfigStore) -> None:
    window = build(root, store, seed_cache=False)

    window.startup_load()

    assert window.state is AppState.LOADING
    assert window.identity_var.get() == STEAMID
    assert len(window.worker.submitted) == 1  # type: ignore[attr-defined]


def test_startup_without_key_does_nothing(root, store: ConfigStore) -> None:
    window = MainWindow(root, store=store, config=Config(api_key=""))
    window.client = FakeClient()
    window.worker = FakeWorker()

    window.startup_load()

    assert window.state is AppState.NO_KEY
    assert window.worker.submitted == []  # type: ignore[attr-defined]


def test_startup_prefers_last_steam_id_snapshot(root, store: ConfigStore) -> None:
    other = "76561197960287930"
    GameCache(store).save_snapshot(other, [Game(appid=9, name="别的账号")])
    window = build(root, store)

    window.startup_load()

    assert [g.appid for g in window.games] == [1, 2], "应优先使用上次账号的快照"
