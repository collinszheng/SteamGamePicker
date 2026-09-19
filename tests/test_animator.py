"""T5.2 抽签动画调度测试（AC-20 / AC-23）。

用确定性调度器逐帧推进，不依赖真实时间。
"""

from __future__ import annotations

import random

from app.ui.animator import (
    DECEL_INTERVALS_MS,
    FAST_INTERVAL_MS,
    FAST_TICKS,
    SINGLE_POOL_DELAY_MS,
    TOTAL_DURATION_MS,
    DrawAnimator,
    interval_plan,
)
from support import FakeScheduler

NAMES = ["游戏 A", "游戏 B", "游戏 C", "游戏 D"]
WINNER = "游戏 C"


def run(names: list[str], winner: str, seed: int = 7):
    scheduler = FakeScheduler()
    frames: list[tuple[str, bool]] = []
    finished: list[bool] = []
    animator = DrawAnimator(scheduler, random.Random(seed))
    animator.start(
        names,
        winner,
        on_frame=lambda name, final: frames.append((name, final)),
        on_finish=lambda: finished.append(True),
    )
    scheduler.run_all()
    return scheduler, animator, frames, finished


def test_interval_plan_matches_prd_timing() -> None:
    plan = interval_plan()
    assert len(plan) == FAST_TICKS + len(DECEL_INTERVALS_MS) == 30
    assert plan[:FAST_TICKS] == [FAST_INTERVAL_MS] * FAST_TICKS == [50] * 24
    assert plan[FAST_TICKS:] == [55, 70, 90, 110, 130, 145]
    assert sum(plan[:FAST_TICKS]) == 1200
    assert sum(plan[FAST_TICKS:]) == 600
    assert sum(plan) == TOTAL_DURATION_MS == 1800


def test_full_animation_timing_and_frames() -> None:
    """AC-20：总时长 1800 ms，先快后慢，最后一帧定格 winner。"""
    scheduler, animator, frames, finished = run(NAMES, WINNER)

    assert len(frames) == 31, "30 帧滚动 + 1 帧定格"
    assert frames[-1] == (WINNER, True)
    assert all(final is False for _name, final in frames[:-1])
    assert scheduler.total_delay == 1800
    assert finished == [True]
    assert animator.running is False
    assert scheduler.pending == 0


def test_frames_only_use_pool_names() -> None:
    _scheduler, _animator, frames, _finished = run(NAMES, WINNER)
    assert {name for name, _final in frames} <= set(NAMES)


def test_no_consecutive_duplicate_frames() -> None:
    """滚动过程中不连续显示同一名字；定格帧允许与上一帧同名（真随机不干预）。"""
    _scheduler, _animator, frames, _finished = run(NAMES, WINNER)
    rolling = [name for name, final in frames if not final]
    assert all(a != b for a, b in zip(rolling, rolling[1:])), rolling
    assert len(rolling) == 30


def test_deceleration_is_monotonic() -> None:
    """减速阶段间隔递增，肉眼可分辨（PRD 5.5）。"""
    plan = interval_plan()[FAST_TICKS:]
    assert plan == sorted(plan)
    assert plan[-1] > plan[0]


def test_single_pool_skips_rolling() -> None:
    """AC-23：池中只有 1 款时跳过滚动，300 ms 后直接定格。"""
    scheduler, animator, frames, finished = run(["唯一游戏"], "唯一游戏")

    assert scheduler.delays == [SINGLE_POOL_DELAY_MS] == [300]
    assert frames == [("唯一游戏", True)]
    assert finished == [True]
    assert animator.running is False


def test_empty_names_falls_back_to_winner() -> None:
    scheduler, _animator, frames, _finished = run([], "兜底")
    assert frames == [("兜底", True)]
    assert scheduler.delays == [SINGLE_POOL_DELAY_MS]


def test_cancel_stops_animation() -> None:
    scheduler = FakeScheduler()
    frames: list[tuple[str, bool]] = []
    animator = DrawAnimator(scheduler, random.Random(1))
    animator.start(NAMES, WINNER, on_frame=lambda n, f: frames.append((n, f)), on_finish=lambda: None)

    assert len(frames) == 1, "start 后立即显示第一帧"
    assert scheduler.pending == 1

    animator.cancel()
    assert animator.running is False
    assert scheduler.pending == 0
    assert scheduler.cancelled

    scheduler.run_all()
    assert len(frames) == 1, "取消后不得再出帧"


def test_restart_cancels_previous_run() -> None:
    scheduler = FakeScheduler()
    frames: list[tuple[str, bool]] = []
    animator = DrawAnimator(scheduler, random.Random(2))
    animator.start(NAMES, WINNER, on_frame=lambda n, f: frames.append((n, f)), on_finish=lambda: None)
    first_job = max(scheduler.jobs) if scheduler.jobs else None

    animator.start(["另一个"], "另一个", on_frame=lambda n, f: frames.append((n, f)), on_finish=lambda: None)

    assert first_job is not None and first_job in scheduler.cancelled
    scheduler.run_all()
    assert frames[-1] == ("另一个", True)
