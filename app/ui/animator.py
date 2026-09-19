"""抽签动画调度（PRD 5.5 / 7.5）。

时序（总计 1800 ms）：
* 快滚阶段：固定 50 ms × 24 次 = 1200 ms；
* 减速阶段：55 → 70 → 90 → 110 → 130 → 145 ms = 600 ms；
* 结束后定格显示 winner（绿色加粗 + 轻微放大回弹）。

与 :mod:`app.worker` 一样，只依赖"能安排定时回调"的调度器，
因此可以用确定性调度器做逐帧测试。
"""

from __future__ import annotations

import random
from collections.abc import Callable, Sequence
from typing import Any, Protocol

FAST_INTERVAL_MS = 50
FAST_TICKS = 24
DECEL_INTERVALS_MS: tuple[int, ...] = (55, 70, 90, 110, 130, 145)
#: 池中只有 1 款游戏时跳过滚动，直接高亮定格（PRD 7.5）
SINGLE_POOL_DELAY_MS = 300
#: 定格后的放大回弹时长
BOUNCE_MS = 120


class Scheduler(Protocol):
    def after(self, ms: int, callback: Callable[[], None]) -> Any: ...

    def after_cancel(self, identifier: Any) -> None: ...


def interval_plan() -> list[int]:
    """完整的帧间隔序列（长度 = 帧数）。"""
    return [FAST_INTERVAL_MS] * FAST_TICKS + list(DECEL_INTERVALS_MS)


#: 动画总时长 = 1800 ms（AC-20 的硬指标）
TOTAL_DURATION_MS = sum(interval_plan())


class DrawAnimator:
    """滚动名字的调度器；不关心界面，只回调"该显示哪个名字"。"""

    def __init__(self, scheduler: Scheduler, rng: random.Random | None = None) -> None:
        self._scheduler = scheduler
        self._rng = rng or random.Random()
        self._after_id: Any = None
        self._names: list[str] = []
        self._winner = ""
        self._on_frame: Callable[[str, bool], None] | None = None
        self._on_finish: Callable[[], None] | None = None
        self._plan: list[int] = []
        self._tick = 0
        self._last_name: str | None = None
        self._running = False

    @property
    def running(self) -> bool:
        return self._running

    def start(
        self,
        names: Sequence[str],
        winner: str,
        *,
        on_frame: Callable[[str, bool], None],
        on_finish: Callable[[], None],
    ) -> None:
        self.cancel()
        self._names = [name for name in names] or [winner]
        self._winner = winner
        self._on_frame = on_frame
        self._on_finish = on_finish
        self._plan = interval_plan()
        self._tick = 0
        self._last_name = None
        self._running = True

        if len(self._names) <= 1:
            self._after_id = self._scheduler.after(SINGLE_POOL_DELAY_MS, self._finish)
            return
        self._step()

    def cancel(self) -> None:
        self._running = False
        if self._after_id is not None:
            try:
                self._scheduler.after_cancel(self._after_id)
            except Exception:  # pragma: no cover - 控件已销毁
                pass
            self._after_id = None

    # ------------------------------------------------------------------ 内部
    def _step(self) -> None:
        if not self._running:
            return
        self._after_id = None
        name = self._pick_name()
        self._emit(name, final=False)

        delay = self._plan[self._tick]
        self._tick += 1
        target = self._finish if self._tick >= len(self._plan) else self._step
        self._after_id = self._scheduler.after(delay, target)

    def _finish(self) -> None:
        if not self._running:
            return
        self._after_id = None
        self._running = False
        self._emit(self._winner, final=True)
        if self._on_finish is not None:
            self._on_finish()

    def _emit(self, name: str, *, final: bool) -> None:
        self._last_name = name
        if self._on_frame is not None:
            self._on_frame(name, final)

    def _pick_name(self) -> str:
        if len(self._names) == 1:
            return self._names[0]
        candidate = self._rng.choice(self._names)
        # 不连续显示同一个名字（池中多于 1 款时）
        guard = 0
        while candidate == self._last_name and guard < 10:
            candidate = self._rng.choice(self._names)
            guard += 1
        return candidate
