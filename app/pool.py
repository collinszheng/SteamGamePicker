"""抽签池：快捷范围预设、可抽池与均匀随机（PRD D3 / 5.3 / 7.5）。

核心约定：``excluded_appids`` 是抽签范围的**唯一事实来源**，
预设只是"按规则批量重写勾选"的便捷入口（PRD D7：直接覆盖，不弹确认框）。

纯逻辑模块，禁止 import tkinter。
"""

from __future__ import annotations

import random
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from app.config import (
    PRESET_ALL,
    PRESET_CUSTOM,
    PRESET_LOW,
    PRESET_NEVER,
    PRESET_NEVER_LOW,
    SORT_NAME,
    SORT_PLAYTIME,
)
from app.i18n import t
from app.models import Game

#: 界面上的预设顺序（不含"自定义"，它由系统自动切换）
PRESET_ORDER: tuple[str, ...] = (PRESET_ALL, PRESET_NEVER, PRESET_LOW)

#: 范围模式：全部参与 / 快捷筛选 / 自定义
RANGE_ALL = "all"
RANGE_FILTERS = "filters"
RANGE_CUSTOM = "custom"


@dataclass(frozen=True, slots=True)
class RangeState:
    """当前抽签范围的可读状态（由 ``excluded_appids`` 反推而来）。"""

    mode: str
    never: bool = False
    low: bool = False


def preset_label(preset: str) -> str:
    """预设名称（按当前语言实时取）。"""
    if preset in (PRESET_ALL, PRESET_NEVER, PRESET_LOW, PRESET_NEVER_LOW, PRESET_CUSTOM):
        return t(f"preset.{preset}")
    return t("preset.custom")


def matches_preset(game: Game, preset: str, threshold_minutes: int) -> bool:
    """该游戏是否落入预设范围。"""
    if preset == PRESET_ALL:
        return True
    if preset == PRESET_NEVER:
        return game.playtime_forever == 0
    if preset == PRESET_LOW:
        return 0 < game.playtime_forever < threshold_minutes
    if preset == PRESET_CUSTOM:
        raise ValueError("自定义不是可计算的预设")
    raise ValueError(f"未知预设：{preset}")


def apply_preset(
    games: Sequence[Game], preset: str, threshold_minutes: int
) -> set[int]:
    """按预设算出**被排除**的 appid 集合（即勾选结果的反面）。

    PRD D7：直接覆盖原有手动结果，不做交集。
    """
    if preset == PRESET_CUSTOM:
        raise ValueError("自定义不是可应用的预设")
    return {g.appid for g in games if not matches_preset(g, preset, threshold_minutes)}


def classify_preset(
    games: Sequence[Game], excluded_appids: Iterable[int], threshold_minutes: int
) -> str:
    """反推当前勾选状态对应哪个预设；都不匹配则返回 ``custom``。

    用于启动恢复与"手动改动后自动切到自定义"（PRD 5.3）。
    """
    excluded = set(excluded_appids)
    for preset in PRESET_ORDER:
        if apply_preset(games, preset, threshold_minutes) == excluded:
            return preset
    return PRESET_CUSTOM


def available(games: Sequence[Game], excluded_appids: Iterable[int]) -> list[Game]:
    """可抽池 = 全部游戏 − 排除集合（PRD 7.5）。"""
    excluded = set(excluded_appids)
    return [g for g in games if g.appid not in excluded]


def pick(available_games: Sequence[Game], rng: random.Random | None = None) -> Game:
    """均匀随机选出一款；池为空时抛 ``ValueError``（调用方负责在 S4 禁用按钮）。"""
    if not available_games:
        raise ValueError("可抽池为空")
    chooser = rng or random
    return chooser.choice(list(available_games))


def summary(games: Sequence[Game], excluded_appids: Iterable[int]) -> tuple[int, int]:
    """返回 (总数, 参与抽签数)，用于状态行文案。"""
    pool = available(games, excluded_appids)
    return len(games), len(pool)


# ---------------------------------------------------------------------------
# 可并存的快捷筛选（用户要求：从未玩过 + 玩得很少 可同时勾选）
# ---------------------------------------------------------------------------
def matches_filters(
    game: Game, *, never: bool, low: bool, threshold_minutes: int
) -> bool:
    """是否被当前勾选的快捷筛选中选（多个筛选之间是**或**的关系）。"""
    if never and game.playtime_forever == 0:
        return True
    if low and 0 < game.playtime_forever < threshold_minutes:
        return True
    return False


def apply_filters(
    games: Sequence[Game], *, never: bool, low: bool, threshold_minutes: int
) -> set[int]:
    """按勾选的筛选取并集，返回**被排除**的 appid 集合。

    两个都不勾选等同于「全部参与」（返回空集合），因此不会出现"全部未勾选导致空池"。
    """
    if not never and not low:
        return set()
    return {
        game.appid
        for game in games
        if not matches_filters(game, never=never, low=low, threshold_minutes=threshold_minutes)
    }


def classify_range(
    games: Sequence[Game], excluded_appids: Iterable[int], threshold_minutes: int
) -> RangeState:
    """由 ``excluded_appids`` 反推范围状态（界面唯一事实来源仍是排除集合）。"""
    excluded = set(excluded_appids)
    if not excluded:
        return RangeState(RANGE_ALL)
    if excluded == apply_filters(games, never=False, low=True, threshold_minutes=threshold_minutes):
        return RangeState(RANGE_FILTERS, never=False, low=True)
    if excluded == apply_filters(games, never=True, low=False, threshold_minutes=threshold_minutes):
        return RangeState(RANGE_FILTERS, never=True, low=False)
    if excluded == apply_filters(games, never=True, low=True, threshold_minutes=threshold_minutes):
        return RangeState(RANGE_FILTERS, never=True, low=True)
    return RangeState(RANGE_CUSTOM)


def range_label(state: RangeState) -> str:
    """范围的人类可读名称：全部参与 / 从未玩过 / 玩得很少 / 两者组合 / 自定义。"""
    if state.mode == RANGE_ALL:
        return t("preset.all")
    if state.mode == RANGE_CUSTOM:
        return t("preset.custom")
    names = []
    if state.never:
        names.append(t("preset.never_played"))
    if state.low:
        names.append(t("preset.low_playtime"))
    return " + ".join(names) if names else t("preset.all")


def preset_key(state: RangeState) -> str:
    """把范围状态映射成写入 config 的 ``last_preset`` 取值。"""
    if state.mode == RANGE_ALL:
        return PRESET_ALL
    if state.mode == RANGE_CUSTOM:
        return PRESET_CUSTOM
    if state.never and state.low:
        return PRESET_NEVER_LOW
    return PRESET_NEVER if state.never else PRESET_LOW


# ---------------------------------------------------------------------------
# 搜索与排序（PRD 5.3：300ms 防抖、大小写不敏感、多关键词同时包含）
# ---------------------------------------------------------------------------
def match_query(name: str, query: str) -> bool:
    """空查询匹配全部；否则按空格分词，要求**全部**关键词都被包含。"""
    tokens = [token for token in query.lower().split() if token]
    if not tokens:
        return True
    lowered = name.lower()
    return all(token in lowered for token in tokens)


def filter_games(games: Sequence[Game], query: str) -> list[Game]:
    return [g for g in games if match_query(g.name, query)]


def sort_games(games: Sequence[Game], key: str = SORT_NAME, desc: bool = False) -> list[Game]:
    """按名称或游玩时间排序；名称排序不区分大小写。"""
    if key == SORT_PLAYTIME:
        ordered = sorted(games, key=lambda g: (g.playtime_forever, g.name.lower()))
    else:
        ordered = sorted(games, key=lambda g: g.name.lower())
    if desc:
        ordered.reverse()
    return ordered
