"""T1.3 / T1.4 预设与抽签池测试（AC-13 / AC-14 / AC-22）。"""

from __future__ import annotations

import random

import pytest

from app.config import PRESET_ALL, PRESET_CUSTOM, PRESET_LOW, PRESET_NEVER
from app.models import Game
from app.pool import (
    PRESET_ORDER,
    apply_preset,
    available,
    classify_preset,
    matches_preset,
    pick,
    preset_label,
    summary,
)


def make_games() -> list[Game]:
    return [
        Game(appid=1, name="从未玩过", playtime_forever=0),
        Game(appid=2, name="半小时", playtime_forever=30),
        Game(appid=3, name="差一分钟两小时", playtime_forever=119),
        Game(appid=4, name="正好两小时", playtime_forever=120),
        Game(appid=5, name="老游戏", playtime_forever=5000),
    ]


def test_preset_all_excludes_nothing() -> None:
    assert apply_preset(make_games(), PRESET_ALL, 120) == set()


def test_preset_never_played() -> None:
    """AC-13：从未玩过 = 游玩时间恰为 0。"""
    assert apply_preset(make_games(), PRESET_NEVER, 120) == {2, 3, 4, 5}


def test_preset_low_playtime_threshold() -> None:
    """AC-14：0 < 游玩时间 < 阈值（阈值可改）。"""
    assert apply_preset(make_games(), PRESET_LOW, 120) == {1, 4, 5}
    assert apply_preset(make_games(), PRESET_LOW, 60) == {1, 3, 4, 5}


def test_custom_and_unknown_presets_are_rejected() -> None:
    with pytest.raises(ValueError):
        apply_preset(make_games(), PRESET_CUSTOM, 120)
    with pytest.raises(ValueError):
        apply_preset(make_games(), "bogus", 120)
    with pytest.raises(ValueError):
        matches_preset(make_games()[0], PRESET_CUSTOM, 120)
    with pytest.raises(ValueError):
        matches_preset(make_games()[0], "bogus", 120)


def test_classify_preset_roundtrip() -> None:
    games = make_games()
    for preset in PRESET_ORDER:
        excluded = apply_preset(games, preset, 120)
        assert classify_preset(games, excluded, 120) == preset


def test_classify_preset_manual_changes_become_custom() -> None:
    """AC-15：手动改动后范围识别为"自定义"。"""
    games = make_games()
    excluded = apply_preset(games, PRESET_NEVER, 120)
    excluded.add(1)
    assert classify_preset(games, excluded, 120) == PRESET_CUSTOM
    assert classify_preset(games, {999}, 120) == PRESET_CUSTOM


def test_available_and_summary() -> None:
    games = make_games()
    pool = available(games, {2, 3})
    assert [g.appid for g in pool] == [1, 4, 5]
    assert summary(games, {2, 3}) == (5, 3)
    assert summary(games, set()) == (5, 5)


def test_pick_empty_pool_raises() -> None:
    with pytest.raises(ValueError):
        pick([])


def test_pick_single_game_is_deterministic() -> None:
    game = Game(appid=7, name="唯一")
    assert pick([game]) is game


def test_pick_is_uniform_without_bias() -> None:
    """AC-22：抽 10000 次，各游戏频次偏差 < 8%，且没有游戏永远抽不到。"""
    games = make_games()
    rng = random.Random(20260919)
    draws = 10000
    counts = {g.appid: 0 for g in games}
    for _ in range(draws):
        counts[pick(games, rng).appid] += 1

    expected = draws / len(games)
    for appid, count in counts.items():
        assert count > 0, f"appid={appid} 从未被抽中"
        assert abs(count - expected) <= expected * 0.08, f"appid={appid} 频次异常：{count}"


def test_preset_labels_cover_all() -> None:
    assert preset_label(PRESET_ALL) == "全部参与"
    assert preset_label(PRESET_NEVER) == "从未玩过"
    assert preset_label(PRESET_LOW) == "玩得很少"
    assert preset_label(PRESET_CUSTOM) == "自定义"
    assert preset_label("bogus") == "自定义"
