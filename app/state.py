"""应用状态机 S0–S8（PRD 11.1）与控件启停映射。

把"当前该让用户做什么"收敛成一个纯函数，界面只负责照着设置控件，
避免出现"按钮该灰没灰、该亮没亮"的零散判断。纯逻辑模块，禁止 import tkinter。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from app.errors import LEVEL_MUTED, Message, message, status
from app.errors import Err

LOAD_ENABLED = "enabled"
LOAD_CANCEL = "cancel"
LOAD_DISABLED = "disabled"

DRAW_IDLE_LABEL = "抽签"
DRAW_AGAIN_LABEL = "再抽一次"
DRAW_BUSY_LABEL = "抽签中…"


class AppState(Enum):
    NO_KEY = "S0"
    IDLE = "S1"
    LOADING = "S2"
    READY = "S3"
    EMPTY_POOL = "S4"
    DRAWING = "S5"
    DETAIL_LOADING = "S6"
    OFFLINE = "S7"
    ERROR = "S8"


@dataclass(frozen=True)
class Controls:
    """某一状态下各控件应有的样子。"""

    identity_enabled: bool
    load_mode: str
    pool_enabled: bool
    draw_enabled: bool
    draw_label: str
    zone3_hint: Message | None  # None 表示"不要覆盖当前内容"
    status_hint: Message | None = None  # None 表示"保留状态行现有文案"


_PLACEHOLDER = Message(status("idle").text, LEVEL_MUTED)


def controls_for(state: AppState, *, has_result: bool = False) -> Controls:
    """状态 → 控件启停（严格对齐 PRD 11.1 的表格）。"""
    idle_label = DRAW_AGAIN_LABEL if has_result else DRAW_IDLE_LABEL

    if state is AppState.NO_KEY:
        return Controls(
            False, LOAD_DISABLED, False, False, idle_label, message(Err.NO_KEY), message(Err.NO_KEY)
        )
    if state is AppState.LOADING:
        loading = status("loading")
        return Controls(False, LOAD_CANCEL, False, False, idle_label, loading, loading)
    if state is AppState.READY:
        # 已经抽出结果时不得用占位文案覆盖中签游戏名（PRD 11.1 S3："灰色占位**或上次结果**"）
        return Controls(
            True, LOAD_ENABLED, True, True, idle_label, None if has_result else _PLACEHOLDER
        )
    if state is AppState.EMPTY_POOL:
        empty = status("pool_empty")
        return Controls(True, LOAD_ENABLED, True, False, idle_label, empty, empty)
    if state is AppState.DRAWING:
        return Controls(False, LOAD_DISABLED, False, False, DRAW_BUSY_LABEL, None)
    if state is AppState.DETAIL_LOADING:
        return Controls(True, LOAD_ENABLED, True, True, idle_label, None)
    if state is AppState.OFFLINE:
        return Controls(
            True, LOAD_ENABLED, True, True, idle_label, None if has_result else _PLACEHOLDER
        )
    if state is AppState.ERROR:
        return Controls(True, LOAD_ENABLED, False, False, idle_label, None)
    # AppState.IDLE
    return Controls(
        True, LOAD_ENABLED, False, False, idle_label, None if has_result else _PLACEHOLDER
    )


def infer_state(
    *,
    has_key: bool,
    loading: bool = False,
    drawing: bool = False,
    detail_loading: bool = False,
    offline: bool = False,
    game_count: int = 0,
    pool_size: int = 0,
    error: bool = False,
) -> AppState:
    """由界面事实反推当前状态（顺序即优先级）。"""
    if not has_key:
        return AppState.NO_KEY
    if loading:
        return AppState.LOADING
    if drawing:
        return AppState.DRAWING
    if detail_loading:
        return AppState.DETAIL_LOADING
    if game_count > 0:
        if offline:
            return AppState.OFFLINE
        if pool_size == 0:
            return AppState.EMPTY_POOL
        return AppState.READY
    if error:
        return AppState.ERROR
    return AppState.IDLE
