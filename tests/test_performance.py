"""T8.2 性能验收（AC-05 / AC-18 的本地部分）。

网络耗时不受本机控制，这里测的是"拿到数据之后我们自己的处理开销"
以及 1000 款规模下的界面响应，全部为真实测量，不是估算。
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from app.config import PRESET_LOW, PRESET_NEVER, Config, ConfigStore
from app.models import Game
from app.pool import apply_preset, available, classify_preset, filter_games, sort_games
from app.steam_api import SteamClient
from app.ui.main_window import MainWindow
from support import FakeResponse, FakeSession

KEY = "K" * 32
LIBRARY_SIZE = 1000


def make_library(size: int = LIBRARY_SIZE) -> list[Game]:
    return [
        Game(
            appid=1000 + index,
            name=f"游戏 {index:04d}",
            playtime_forever=(index % 7) * 60,
            img_icon_url=f"icon-{index}",
        )
        for index in range(size)
    ]


def make_payload(size: int = LIBRARY_SIZE) -> dict[str, object]:
    return {
        "response": {
            "game_count": size,
            "games": [
                {
                    "appid": game.appid,
                    "name": game.name,
                    "playtime_forever": game.playtime_forever,
                    "img_icon_url": game.img_icon_url,
                }
                for game in make_library(size)
            ],
        }
    }


@pytest.fixture()
def store(tmp_path: Path) -> ConfigStore:
    instance = ConfigStore(tmp_path / "SteamGamePicker")
    instance.ensure_dirs()
    return instance


def test_parsing_1000_games_is_fast() -> None:
    """AC-05 的本地部分：解析 1000 款游戏必须远快于 5 秒预算。"""
    session = FakeSession().add("GetOwnedGames", FakeResponse(200, make_payload()))
    client = SteamClient(KEY, session=session)

    started = time.perf_counter()
    games = client.get_owned_games("76561198260031749")
    elapsed = time.perf_counter() - started

    assert len(games) == LIBRARY_SIZE
    assert elapsed < 1.0, f"解析 1000 款耗时 {elapsed:.3f}s"


def test_pool_operations_on_1000_games_are_fast() -> None:
    """预设计算 / 可抽池 / 搜索 / 排序在 1000 款规模下的耗时。"""
    games = make_library()

    started = time.perf_counter()
    excluded = apply_preset(games, PRESET_NEVER, 120)
    pool = available(games, excluded)
    filtered = filter_games(games, "03")
    ordered = sort_games(games, "playtime", True)
    detected = classify_preset(games, excluded, 120)
    elapsed = time.perf_counter() - started

    assert detected == PRESET_NEVER
    assert len(pool) + len(excluded) == LIBRARY_SIZE
    assert filtered and ordered
    assert elapsed < 1.0, f"1000 款的池操作耗时 {elapsed:.3f}s"


def test_window_handles_1000_games_within_budget(root, store: ConfigStore) -> None:
    """AC-18：1000 款游戏载入列表 + 搜索 + 勾选的整体响应。"""
    window = MainWindow(root, store=store, config=Config(api_key=KEY))

    started = time.perf_counter()
    window.set_games(make_library())
    load_elapsed = time.perf_counter() - started

    assert len(window.tree.get_children()) == LIBRARY_SIZE
    assert load_elapsed < 2.0, f"载入 1000 款到列表耗时 {load_elapsed:.3f}s"

    started = time.perf_counter()
    window.search_var.set("游戏 01")
    window.apply_search()
    search_elapsed = time.perf_counter() - started
    assert 0 < len(window.filtered) < LIBRARY_SIZE
    assert search_elapsed < 1.0, f"搜索耗时 {search_elapsed:.3f}s"

    window.search_var.set("")
    window.apply_search()
    started = time.perf_counter()
    window.toggle_game(1000)
    window.toggle_game(1001)
    toggle_elapsed = time.perf_counter() - started
    assert toggle_elapsed < 0.2, f"两次勾选耗时 {toggle_elapsed:.3f}s"


def test_preset_switch_on_1000_games_is_fast(root, store: ConfigStore) -> None:
    """切换预设 = 重算全部勾选 + 刷新列表，必须在可感范围内。"""
    window = MainWindow(root, store=store, config=Config(api_key=KEY))
    window.set_games(make_library())

    started = time.perf_counter()
    window.low_var.set(True)
    window.on_filter_clicked()
    elapsed = time.perf_counter() - started

    assert window.current_preset == PRESET_LOW
    assert elapsed < 2.0, f"切换预设耗时 {elapsed:.3f}s"
