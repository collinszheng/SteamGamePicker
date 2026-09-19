"""T3.3 状态机测试：逐行锁定 PRD 11.1 的控件启停表。"""

from __future__ import annotations

import pytest

from app.errors import ACTION_EXPAND, ACTION_SETTINGS
from app.state import (
    DRAW_AGAIN_LABEL,
    DRAW_BUSY_LABEL,
    DRAW_IDLE_LABEL,
    LOAD_CANCEL,
    LOAD_DISABLED,
    LOAD_ENABLED,
    AppState,
    controls_for,
    infer_state,
)

ALL_STATES = list(AppState)


@pytest.mark.parametrize("state", ALL_STATES)
def test_every_state_has_controls(state: AppState) -> None:
    controls = controls_for(state)
    assert isinstance(controls.identity_enabled, bool)
    assert controls.load_mode in {LOAD_ENABLED, LOAD_CANCEL, LOAD_DISABLED}
    assert controls.draw_label


def test_s0_missing_api_key() -> None:
    controls = controls_for(AppState.NO_KEY)
    assert controls.identity_enabled is False
    assert controls.load_mode == LOAD_DISABLED
    assert controls.pool_enabled is False
    assert controls.draw_enabled is False
    assert controls.zone3_hint is not None
    assert controls.zone3_hint.text == "请先在设置中填写 Steam API Key"
    assert controls.zone3_hint.actions == (ACTION_SETTINGS,)


def test_s1_idle() -> None:
    controls = controls_for(AppState.IDLE)
    assert controls.identity_enabled is True
    assert controls.load_mode == LOAD_ENABLED
    assert controls.pool_enabled is False
    assert controls.draw_enabled is False


def test_s2_loading_turns_load_into_cancel() -> None:
    controls = controls_for(AppState.LOADING)
    assert controls.identity_enabled is False
    assert controls.load_mode == LOAD_CANCEL
    assert controls.draw_enabled is False
    assert controls.zone3_hint is not None
    assert controls.zone3_hint.text == "正在读取游戏库…"


def test_s3_ready_enables_everything() -> None:
    controls = controls_for(AppState.READY)
    assert (controls.identity_enabled, controls.pool_enabled, controls.draw_enabled) == (
        True,
        True,
        True,
    )
    assert controls.load_mode == LOAD_ENABLED
    assert controls.draw_label == DRAW_IDLE_LABEL


def test_draw_label_becomes_again_after_result() -> None:
    assert controls_for(AppState.READY, has_result=True).draw_label == DRAW_AGAIN_LABEL
    assert controls_for(AppState.DETAIL_LOADING, has_result=True).draw_label == DRAW_AGAIN_LABEL


def test_s4_empty_pool() -> None:
    """AC-19：池为空时抽签禁用并提示调整范围。"""
    controls = controls_for(AppState.EMPTY_POOL)
    assert controls.draw_enabled is False
    assert controls.pool_enabled is True
    assert controls.zone3_hint is not None
    assert "没有可抽签的游戏" in controls.zone3_hint.text
    assert controls.zone3_hint.actions == (ACTION_EXPAND,)


def test_s5_drawing_locks_inputs() -> None:
    """AC-21：抽签动画期间输入、范围、加载全部锁定。"""
    controls = controls_for(AppState.DRAWING)
    assert controls.identity_enabled is False
    assert controls.load_mode == LOAD_DISABLED
    assert controls.pool_enabled is False
    assert controls.draw_enabled is False
    assert controls.draw_label == DRAW_BUSY_LABEL
    assert controls.zone3_hint is None, "动画期间不要覆盖大字区域"


def test_s6_detail_loading_keeps_draw_available() -> None:
    """AC-29：详情加载不阻塞"再抽一次"。"""
    controls = controls_for(AppState.DETAIL_LOADING, has_result=True)
    assert controls.draw_enabled is True
    assert controls.identity_enabled is True
    assert controls.draw_label == DRAW_AGAIN_LABEL


def test_s7_offline_still_playable() -> None:
    """AC-10：离线但有缓存时仍可抽签。"""
    controls = controls_for(AppState.OFFLINE)
    assert controls.draw_enabled is True
    assert controls.pool_enabled is True
    assert controls.load_mode == LOAD_ENABLED


def test_s8_error_keeps_identity_usable() -> None:
    controls = controls_for(AppState.ERROR)
    assert controls.identity_enabled is True
    assert controls.load_mode == LOAD_ENABLED
    assert controls.draw_enabled is False


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        ({"has_key": False}, AppState.NO_KEY),
        ({"has_key": True}, AppState.IDLE),
        ({"has_key": True, "loading": True}, AppState.LOADING),
        ({"has_key": True, "loading": True, "drawing": True}, AppState.LOADING),
        ({"has_key": True, "drawing": True}, AppState.DRAWING),
        ({"has_key": True, "detail_loading": True, "game_count": 10, "pool_size": 5}, AppState.DETAIL_LOADING),
        ({"has_key": True, "game_count": 10, "pool_size": 5}, AppState.READY),
        ({"has_key": True, "game_count": 10, "pool_size": 0}, AppState.EMPTY_POOL),
        ({"has_key": True, "game_count": 10, "pool_size": 5, "offline": True}, AppState.OFFLINE),
        ({"has_key": True, "error": True}, AppState.ERROR),
        ({"has_key": True, "error": True, "game_count": 3, "pool_size": 2}, AppState.READY),
        ({"has_key": False, "error": True}, AppState.NO_KEY),
    ],
)
def test_infer_state_priority(kwargs: dict[str, object], expected: AppState) -> None:
    assert infer_state(**kwargs) == expected  # type: ignore[arg-type]


def test_status_hint_only_set_where_a_message_exists() -> None:
    """没有新信息的普通状态不得覆盖状态行（否则勾选一次就丢掉"已加载 N 款"）。"""
    for state in (
        AppState.IDLE,
        AppState.READY,
        AppState.DRAWING,
        AppState.DETAIL_LOADING,
        AppState.OFFLINE,
        AppState.ERROR,
    ):
        assert controls_for(state).status_hint is None, state

    assert controls_for(AppState.NO_KEY).status_hint is not None
    assert controls_for(AppState.NO_KEY).status_hint.text == "请先在设置中填写 Steam API Key"
    assert controls_for(AppState.LOADING).status_hint is not None
    assert controls_for(AppState.LOADING).status_hint.text == "正在读取游戏库…"
    empty = controls_for(AppState.EMPTY_POOL).status_hint
    assert empty is not None and empty.actions == (ACTION_EXPAND,)


def test_drawn_result_is_never_overwritten_by_placeholder() -> None:
    """问题 1 回归：抽出结果后，区3 不得再被"请输入…"占位文案覆盖。"""
    for state in (AppState.IDLE, AppState.READY, AppState.OFFLINE):
        assert controls_for(state, has_result=True).zone3_hint is None, state
        hint = controls_for(state, has_result=False).zone3_hint
        assert hint is not None and hint.text, state


def test_empty_pool_hint_still_shown_even_with_result() -> None:
    """池被清空时必须如实提示（PRD 11.1 S4），此时允许覆盖大字区。"""
    controls = controls_for(AppState.EMPTY_POOL, has_result=True)
    assert controls.zone3_hint is not None
    assert "没有可抽签的游戏" in controls.zone3_hint.text
