"""问题 2：「从未玩过」与「玩得很少」可同时勾选（含「全部参与」的互斥语义）。

规则（本次确认）：
* 「全部参与」：单选，点击即取消另外两个筛选，范围为全部游戏；
* 「从未玩过」「玩得很少」：复选，可同时勾选，取**并集**（有任一条件满足即参与）；
* 两个筛选全部取消 → 回落到「全部参与」，避免出现"空池陷阱"；
* 手动改动列表后 → 范围显示「自定义」，两个筛选自动取消勾选；
* ``excluded_appids`` 仍是唯一事实来源，重启后按它反推界面状态。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.config import (
    PRESET_ALL,
    PRESET_CUSTOM,
    PRESET_LOW,
    PRESET_NEVER,
    PRESET_NEVER_LOW,
    Config,
    ConfigStore,
)
from app.models import Game
from app.pool import (
    RANGE_ALL,
    RANGE_CUSTOM,
    RANGE_FILTERS,
    RangeState,
    apply_filters,
    classify_range,
    preset_key,
    range_label,
)
from app.ui.main_window import MainWindow

KEY = "K" * 32
THRESHOLD = 120


def make_games() -> list[Game]:
    """游玩时间分布：0 / 30 / 119 / 120 / 5000 分钟。"""
    return [
        Game(appid=1, name="从未玩过", playtime_forever=0),
        Game(appid=2, name="半小时", playtime_forever=30),
        Game(appid=3, name="差一分钟两小时", playtime_forever=119),
        Game(appid=4, name="正好两小时", playtime_forever=120),
        Game(appid=5, name="老游戏", playtime_forever=5000),
    ]


@pytest.fixture()
def store(tmp_path: Path) -> ConfigStore:
    instance = ConfigStore(tmp_path / "SteamGamePicker")
    instance.ensure_dirs()
    return instance


@pytest.fixture()
def window(root, store: ConfigStore) -> MainWindow:
    instance = MainWindow(root, store=store, config=Config(api_key=KEY))
    instance.set_games(make_games())
    return instance


# ------------------------------------------------------------------ 纯逻辑
def test_apply_filters_single_and_combined() -> None:
    games = make_games()
    assert apply_filters(games, never=False, low=False, threshold_minutes=THRESHOLD) == set()
    assert apply_filters(games, never=True, low=False, threshold_minutes=THRESHOLD) == {2, 3, 4, 5}
    assert apply_filters(games, never=False, low=True, threshold_minutes=THRESHOLD) == {1, 4, 5}
    # 并集：只排除"两个条件都不满足"的游戏（即游玩时间 ≥ 阈值）
    assert apply_filters(games, never=True, low=True, threshold_minutes=THRESHOLD) == {4, 5}


def test_combined_filters_keep_everything_below_threshold() -> None:
    games = make_games()
    excluded = apply_filters(games, never=True, low=True, threshold_minutes=THRESHOLD)
    included = [g.appid for g in games if g.appid not in excluded]
    assert included == [1, 2, 3], "同时勾选时，游玩时间低于阈值的游戏都应参与"


@pytest.mark.parametrize(
    ("never", "low", "expected_mode", "expected_key", "expected_label"),
    [
        (False, False, RANGE_ALL, PRESET_ALL, "全部参与"),
        (True, False, RANGE_FILTERS, PRESET_NEVER, "从未玩过"),
        (False, True, RANGE_FILTERS, PRESET_LOW, "玩得很少"),
        (True, True, RANGE_FILTERS, PRESET_NEVER_LOW, "从未玩过 + 玩得很少"),
    ],
)
def test_classify_range_roundtrip(
    never: bool, low: bool, expected_mode: str, expected_key: str, expected_label: str
) -> None:
    games = make_games()
    excluded = apply_filters(games, never=never, low=low, threshold_minutes=THRESHOLD)

    state = classify_range(games, excluded, THRESHOLD)

    assert state.mode == expected_mode
    assert state.never is never
    assert state.low is low
    assert preset_key(state) == expected_key
    assert range_label(state) == expected_label


def test_classify_range_custom() -> None:
    games = make_games()
    state = classify_range(games, {2}, THRESHOLD)
    assert state == RangeState(RANGE_CUSTOM)
    assert range_label(state) == "自定义"
    assert preset_key(state) == PRESET_CUSTOM


# ------------------------------------------------------------------ 界面行为
def test_both_filters_can_be_checked_together(window: MainWindow) -> None:
    window.never_var.set(True)
    window.on_filter_clicked()
    window.low_var.set(True)
    window.on_filter_clicked()

    assert window.never_var.get() is True
    assert window.low_var.get() is True
    assert window.excluded == {4, 5}, "两个筛选并存时取并集"
    assert window.current_preset == PRESET_NEVER_LOW
    assert "从未玩过 + 玩得很少" in str(window.pool_toggle_button.cget("text"))
    assert window.status_text() == "已按『从未玩过 + 玩得很少』重设选择，可继续手动调整"


def test_unchecking_one_filter_keeps_the_other(window: MainWindow) -> None:
    window.never_var.set(True)
    window.on_filter_clicked()
    window.low_var.set(True)
    window.on_filter_clicked()

    window.never_var.set(False)
    window.on_filter_clicked()

    assert window.excluded == {1, 4, 5}
    assert window.current_preset == PRESET_LOW


def test_all_button_clears_both_filters(window: MainWindow) -> None:
    """「全部参与」保持互斥：一点就把另外两个取消掉。"""
    window.never_var.set(True)
    window.low_var.set(True)
    window.on_filter_clicked()
    assert window.excluded

    window.all_button.invoke()  # 等价于用户点击

    assert window.never_var.get() is False
    assert window.low_var.get() is False
    assert window.excluded == set()
    assert window.current_preset == PRESET_ALL
    assert window.range_var.get() == PRESET_ALL
    assert window.status_text() == "已按『全部参与』重设选择，可继续手动调整"


def test_unchecking_last_filter_falls_back_to_all(window: MainWindow) -> None:
    """两个筛选全取消 = 不筛选，回落到全部参与，不制造空池。"""
    window.never_var.set(True)
    window.on_filter_clicked()

    window.never_var.set(False)
    window.on_filter_clicked()

    assert window.excluded == set()
    assert window.current_preset == PRESET_ALL
    assert window.range_var.get() == PRESET_ALL
    assert window.state.name == "READY"


def test_manual_change_switches_to_custom_and_clears_filters(window: MainWindow) -> None:
    window.never_var.set(True)
    window.on_filter_clicked()
    assert window.current_preset == PRESET_NEVER

    window.toggle_game(1)  # 手动把"从未玩过"的那款也排除掉

    assert window.current_preset == PRESET_CUSTOM
    assert window.range_var.get() == PRESET_CUSTOM
    assert window.never_var.get() is False
    assert window.low_var.get() is False


def test_filters_persist_and_restore(window: MainWindow, store: ConfigStore, root) -> None:
    """勾选状态持久化：重启后按 excluded 反推出同样的筛选勾选。"""
    window.never_var.set(True)
    window.on_filter_clicked()
    window.low_var.set(True)
    window.on_filter_clicked()
    window.flush_save()

    saved = store.load().config
    assert saved.last_preset == PRESET_NEVER_LOW

    reopened = MainWindow(root, store=store, config=store.load().config)
    reopened.set_games(make_games())

    assert reopened.excluded == {4, 5}
    assert reopened.never_var.get() is True
    assert reopened.low_var.get() is True
    assert reopened.current_preset == PRESET_NEVER_LOW


def test_combined_filters_drive_the_draw_pool(window: MainWindow) -> None:
    """两个筛选并存时的可抽池 = 游玩时间 < 阈值。"""
    window.never_var.set(True)
    window.on_filter_clicked()
    window.low_var.set(True)
    window.on_filter_clicked()

    seen = set()
    for _ in range(30):
        window.on_draw()
        assert window.winner is not None
        seen.add(window.winner.appid)
        window._animator.cancel()
        window.winner = None

    assert seen <= {1, 2, 3}
    assert seen, "至少要抽出过结果"
