"""M4 主窗口测试：区0–区2 的状态、过滤、勾选、搜索与持久化。

窗口创建后立即 withdraw，不弹出可见界面；所有网络调用由假客户端替代。
（AC-15 / AC-16 / AC-17 / AC-19 / AC-21 / AC-36 / AC-38 / AC-44）
"""

from __future__ import annotations

import threading
from pathlib import Path

import pytest

from app.cache import GameCache, parse_iso
from app.cancellation import CancelToken
from app.config import PRESET_ALL, PRESET_CUSTOM, PRESET_LOW, PRESET_NEVER, SORT_NAME, SORT_PLAYTIME, Config, ConfigStore
from app.errors import ACTION_EXPAND, AppError, Err, message, status
from app.models import Game
from app.pool import apply_preset
from app.state import DRAW_BUSY_LABEL, AppState
from app.ui import theme
from app.ui.main_window import MainWindow

STEAMID = "76561198260031749"
OTHER_ID = "76561197960287930"
KEY = "K" * 32


def make_games() -> list[Game]:
    return [
        Game(appid=1, name="Alpha 冒险", playtime_forever=0),
        Game(appid=2, name="Beta 射击", playtime_forever=30),
        Game(appid=3, name="Gamma 模拟", playtime_forever=5000),
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
        self.games = games if games is not None else make_games()
        self.vanity_calls: list[str] = []

    def resolve_vanity(self, vanity: str, token=None) -> str:  # type: ignore[no-untyped-def]
        self.vanity_calls.append(vanity)
        return STEAMID

    def get_owned_games(self, steamid: str, token=None) -> list[Game]:  # type: ignore[no-untyped-def]
        return list(self.games)


@pytest.fixture()
def store(tmp_path: Path) -> ConfigStore:
    instance = ConfigStore(tmp_path / "SteamGamePicker")
    instance.ensure_dirs()
    return instance


@pytest.fixture()
def window(root, store: ConfigStore) -> MainWindow:
    config = Config(api_key=KEY)
    return MainWindow(root, store=store, config=config)


# ------------------------------------------------------------------ 状态与启停
def test_s0_without_api_key(root, store: ConfigStore) -> None:
    instance = MainWindow(root, store=store, config=Config(api_key=""))
    instance.refresh_state()

    assert instance.state is AppState.NO_KEY
    assert str(instance.identity_entry.cget("state")) == "disabled"
    assert str(instance.load_button.cget("state")) == "disabled"
    assert str(instance.draw_button.cget("state")) == "disabled"
    assert instance.status_text() == "请先在设置中填写 Steam API Key"


def test_s1_with_key_is_idle(window: MainWindow) -> None:
    assert window.state is AppState.IDLE
    assert str(window.identity_entry.cget("state")) == "normal"
    assert str(window.draw_button.cget("state")) == "disabled"


def test_loaded_games_switch_to_ready(window: MainWindow) -> None:
    updated_at = "2026-09-19T15:04:05+08:00"
    expected_display = parse_iso(updated_at).astimezone().strftime("%m-%d %H:%M")  # type: ignore[union-attr]

    window.set_games(make_games(), updated_at=updated_at)

    assert window.state is AppState.READY
    assert str(window.draw_button.cget("state")) == "normal"
    assert window.status_text() == f"已加载 3 款 · 3 款参与抽签 · 上次更新 {expected_display}"
    assert len(window.tree.get_children()) == 3
    assert "3/3" in str(window.pool_toggle_button.cget("text"))


def test_rows_show_checkbox_and_playtime(window: MainWindow) -> None:
    window.set_games(make_games())
    rows = {iid: (check, name) for iid, check, name in window.iter_tree_rows()}

    assert rows["1"] == (theme.CHECK_ON, "Alpha 冒险")
    assert window.tree.set("1", "playtime") == "未玩过"
    assert window.tree.set("2", "playtime") == "不足 1 小时"
    assert window.tree.set("3", "playtime") == "83.3 小时"


def test_empty_pool_disables_draw_and_offers_expand(window: MainWindow) -> None:
    """AC-19。"""
    window.set_games(make_games())
    window.excluded = {1, 2, 3}
    window.refresh_state()

    assert window.state is AppState.EMPTY_POOL
    assert str(window.draw_button.cget("state")) == "disabled"
    assert "没有可抽签的游戏" in window.status_text()

    buttons = [child for child in window.status_actions.winfo_children()]
    assert any(str(button.cget("text")) == "展开范围设置" for button in buttons)
    window.toggle_pool_panel(expand=False)
    for button in buttons:
        if str(button.cget("text")) == "展开范围设置":
            button.invoke()
    assert window.pool_panel_expanded is True


def test_drawing_state_locks_inputs(window: MainWindow) -> None:
    """AC-21：动画期间输入 / 范围 / 加载全部锁定。"""
    window.set_games(make_games())
    window.set_state(AppState.DRAWING)

    assert str(window.identity_entry.cget("state")) == "disabled"
    assert str(window.load_button.cget("state")) == "disabled"
    assert str(window.tree.cget("selectmode")) == "none"
    assert str(window.draw_button.cget("text")) == DRAW_BUSY_LABEL
    assert str(window.draw_button.cget("state")) == "disabled"
    for button in window.preset_buttons.values():
        assert str(button.cget("state")) == "disabled"

    window.refresh_state()
    assert str(window.draw_button.cget("state")) == "normal"


# ------------------------------------------------------------------ 勾选与预设
def test_toggle_game_marks_custom_preset(window: MainWindow) -> None:
    """AC-15：手动改动后范围自动切到"自定义"。

    注意用 appid=2（30 分钟）来测：排除第 3 款（5000 分钟）在三款游戏的数据下
    恰好等于"从未玩过 + 玩得很少"的组合，会被正确识别成筛选而非自定义。
    """
    window.set_games(make_games())
    assert window.current_preset == PRESET_ALL

    window.toggle_game(2)

    assert 2 in window.excluded
    assert window.tree.set("2", "check") == theme.CHECK_OFF
    assert window.current_preset == PRESET_CUSTOM
    assert window.range_var.get() == PRESET_CUSTOM
    assert window.never_var.get() is False and window.low_var.get() is False
    assert "自定义" in str(window.pool_toggle_button.cget("text"))


def test_filter_overwrites_manual_selection(window: MainWindow) -> None:
    """AC-44（改造后）：快捷筛选直接覆盖手动结果，并用状态行轻提示。"""
    window.set_games(make_games())
    window.toggle_game(2)
    assert window.excluded == {2}

    window.never_var.set(True)
    window.on_filter_clicked()

    assert window.excluded == apply_preset(make_games(), PRESET_NEVER, 120) == {2, 3}
    assert window.current_preset == PRESET_NEVER
    assert window.status_text() == "已按『从未玩过』重设选择，可继续手动调整"
    assert window.tree.set("1", "check") == theme.CHECK_ON
    assert window.tree.set("2", "check") == theme.CHECK_OFF


def test_preset_low_playtime_uses_threshold(window: MainWindow) -> None:
    window.set_games(make_games())
    window.low_var.set(True)
    window.on_filter_clicked()

    assert window.excluded == {1, 3}
    assert window.current_preset == PRESET_LOW


def test_bulk_buttons_only_affect_current_search_results(window: MainWindow) -> None:
    """AC-17：批量按钮只作用于当前搜索结果，并显示条数。"""
    games = make_games() + [Game(appid=4, name="Delta 冒险", playtime_forever=10)]
    window.set_games(games)

    window.search_var.set("冒险")
    window.apply_search()
    assert [g.appid for g in window.filtered] == [1, 4]
    assert window.bulk_label("all") == "全选（当前 2 条）"

    window.apply_bulk("none")
    assert window.excluded == {1, 4}
    assert 3 not in window.excluded, "搜索结果之外的游戏不受影响"

    window.apply_bulk("invert")
    assert window.excluded == set(), "反选只作用于当前搜索结果"

    window.search_var.set("")
    window.apply_search()
    assert window.tree.set("3", "check") == theme.CHECK_ON

    window.apply_bulk("none")
    assert window.excluded == {1, 2, 3, 4}, "无搜索时等价于全量"

    with pytest.raises(ValueError):
        window.apply_bulk("bogus")


def test_search_debounce_then_apply(window: MainWindow) -> None:
    window.set_games(make_games())
    window.search_var.set("射击")
    assert window._search_job is not None, "搜索必须走 300ms 防抖"

    window.apply_search()
    assert window._search_job is None
    assert [g.appid for g in window.filtered] == [2]
    assert len(window.tree.get_children()) == 1


def test_search_is_case_insensitive_and_multi_token(window: MainWindow) -> None:
    games = [Game(appid=1, name="Hades II", playtime_forever=0), Game(appid=2, name="Hades", playtime_forever=0)]
    window.set_games(games)

    window.search_var.set("hades i")
    window.apply_search()
    assert [g.appid for g in window.filtered] == [1]


def test_sort_toggles_direction(window: MainWindow) -> None:
    window.set_games(make_games())
    window.sort_by(SORT_PLAYTIME)
    assert [g.appid for g in window.filtered] == [1, 2, 3]

    window.sort_by(SORT_PLAYTIME)
    assert window.sort_desc is True
    assert [g.appid for g in window.filtered] == [3, 2, 1]

    window.sort_by(SORT_NAME)
    assert window.sort_key == SORT_NAME and window.sort_desc is False
    assert [g.appid for g in window.filtered] == [1, 2, 3]


def test_pool_panel_toggle_persists(window: MainWindow, store: ConfigStore) -> None:
    assert window.pool_panel_expanded is False
    window.toggle_pool_panel()
    assert window.pool_panel_expanded is True
    assert str(window.pool_toggle_button.cget("text")).startswith("▾")

    window.flush_save()
    assert store.load().config.ui.pool_panel_expanded is True


def test_manual_selection_persists_to_disk(window: MainWindow, store: ConfigStore) -> None:
    """AC-16：勾选状态持久化（含"自定义"范围的识别）。"""
    window.set_games(make_games())
    window.toggle_game(2)
    window.flush_save()

    saved = store.load().config
    assert saved.excluded_appids == {2}
    assert saved.last_preset == PRESET_CUSTOM


def test_selection_matching_a_preset_is_recognised_as_that_preset(
    window: MainWindow, store: ConfigStore
) -> None:
    """手动凑巧等于某个预设时，范围显示该预设而不是"自定义"（classify_preset 的既有行为）。"""
    window.set_games(make_games())
    window.toggle_game(1)  # 游玩 0 分钟
    window.toggle_game(3)  # 游玩 5000 分钟
    window.flush_save()

    saved = store.load().config
    assert saved.excluded_appids == {1, 3}
    assert saved.last_preset == PRESET_LOW
    assert window.current_preset == PRESET_LOW


def test_save_is_debounced(window: MainWindow) -> None:
    window.set_games(make_games())
    window.toggle_game(1)
    assert window._save_job is not None, "勾选变更必须走 1 秒防抖"


# ------------------------------------------------------------------ 加载流程
def test_load_with_empty_input_reports_error(window: MainWindow) -> None:
    """AC-02。"""
    window.identity_var.set("")
    window.start_load()

    assert window.last_error is Err.EMPTY_INPUT
    assert window.status_text() == "请先输入 Steam ID 或资料地址"
    assert window.state is AppState.ERROR


def test_load_without_api_key_reports_no_key(root, store: ConfigStore) -> None:
    instance = MainWindow(root, store=store, config=Config(api_key=""))
    instance.identity_var.set(STEAMID)
    instance.start_load()

    assert instance.last_error is Err.NO_KEY
    assert instance.status_text() == "请先在设置中填写 Steam API Key"


def test_start_load_uses_worker_and_vanity_resolution(window: MainWindow, store: ConfigStore) -> None:
    window.client = FakeClient()
    window.worker = FakeWorker()
    window.identity_var.set("https://steamcommunity.com/id/customname")

    window.start_load()
    assert window.state is AppState.LOADING
    assert str(window.load_button.cget("text")) == "取消"

    job = window.worker.submitted[0]
    payload = job["fn"](CancelToken())  # type: ignore[operator]
    assert payload == (STEAMID, make_games())
    assert window.client.vanity_calls == ["customname"]  # type: ignore[attr-defined]

    job["on_done"](payload)  # type: ignore[operator]
    assert window.state is AppState.READY
    assert window.config.last_steam_id == STEAMID
    assert window.identity_var.get() == STEAMID
    assert store.snapshot_path(STEAMID).exists(), "加载成功必须写入库快照"
    assert "已加载 3 款" in window.status_text()


def test_load_error_reports_private_profile(window: MainWindow) -> None:
    """AC-06 的界面侧：给出"设为公开"而不是"库为空"。"""
    window.client = FakeClient()
    window.worker = FakeWorker()
    window.identity_var.set(STEAMID)
    window.start_load()

    job = window.worker.submitted[0]
    job["on_error"](AppError(Err.PRIVATE_PROFILE))  # type: ignore[operator]

    assert window.last_error is Err.PRIVATE_PROFILE
    assert "设为公开" in window.status_text()
    assert window.state is AppState.ERROR


def test_cancel_load_cancels_task(window: MainWindow) -> None:
    window.client = FakeClient()
    window.worker = FakeWorker()
    window.identity_var.set(STEAMID)
    window.start_load()

    task = window._load_task
    window.cancel_load()
    assert task is not None and task.cancelled is True


def test_switching_account_clears_exclusions(window: MainWindow, store: ConfigStore) -> None:
    """PRD 4.4：换账号时不静默沿用上一个账号的排除项。"""
    window.config.last_steam_id = "11111111111111111"
    window.set_games(make_games())
    window.excluded = {2}
    window.save_now()

    window.on_games_loaded((OTHER_ID, make_games()))

    assert window.excluded == set()
    assert window.identity_var.get() == OTHER_ID
    assert window.config.last_steam_id == OTHER_ID


def test_same_account_keeps_exclusions_and_drops_unknown(window: MainWindow) -> None:
    window.config.last_steam_id = STEAMID
    window.set_games(make_games())
    window.excluded = {2, 999}
    window.save_now()

    window.on_games_loaded((STEAMID, make_games()))

    assert window.excluded == {2}


# ------------------------------------------------------------------ 状态行与关闭
def test_status_line_keeps_loaded_message_after_toggle(window: MainWindow) -> None:
    updated_at = "2026-09-19T15:04:05+08:00"
    expected_display = parse_iso(updated_at).astimezone().strftime("%m-%d %H:%M")  # type: ignore[union-attr]

    window.set_games(make_games(), updated_at=updated_at)
    window.toggle_game(1)

    assert window.status_text() == f"已加载 3 款 · 3 款参与抽签 · 上次更新 {expected_display}"


def test_status_error_colors_and_actions(window: MainWindow) -> None:
    window.set_status(message(Err.NETWORK))
    assert window.status_text() == "网络连接失败，请检查网络后重试"
    assert window.status_color() == theme.COLOR_ERROR
    labels = [str(child.cget("text")) for child in window.status_actions.winfo_children()]
    assert labels == ["重试"]

    window.set_status(status("saved"))
    assert window.status_color() == theme.COLOR_OK
    assert window.status_actions.winfo_children() == []


def test_on_close_saves_and_destroys(root, store: ConfigStore) -> None:
    """AC-24：关窗时保存配置、收敛后台任务并销毁窗口。"""
    config = Config(api_key=KEY)
    instance = MainWindow(root, store=store, config=config)
    instance.set_games(make_games())
    instance.toggle_game(2)

    closed = threading.Event()
    destroyed = threading.Event()

    class FakeWorkerWithShutdown(FakeWorker):
        def shutdown(self, timeout: float = 0.5) -> None:
            closed.set()

    instance.worker = FakeWorkerWithShutdown()
    # 复用会话级窗口：用实例属性顶替 destroy，避免影响后续测试
    instance.root.destroy = lambda: destroyed.set()  # type: ignore[method-assign]
    instance.on_close()

    assert closed.is_set()
    assert destroyed.is_set()
    assert store.load().config.excluded_appids == {2}
