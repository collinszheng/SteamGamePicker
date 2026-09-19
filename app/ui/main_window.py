"""主窗口（PRD 第 3 章：区0 顶栏 / 区1 身份 / 区2 范围 / 区3 抽签 / 区4 结果）。

界面层的规矩：
* 所有中文提示都来自 :mod:`app.errors`，这里不写字面量文案；
* 所有网络调用都交给 :class:`app.worker.Worker`，主线程只更新控件；
* 控件启停只由 :meth:`set_state` 依据 PRD 11.1 统一设置，不做零散判断。

M4 阶段实装区0–区2；区3 / 区4 先建好控件，交互在 M5 接上。
"""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable, Iterable, Sequence
from logging import Logger
from tkinter import ttk
from typing import Any

from app import APP_NAME
from app.cache import GameCache, display_time
from app.config import (
    PRESET_ALL,
    PRESET_CUSTOM,
    SORT_NAME,
    SORT_PLAYTIME,
    Config,
    ConfigStore,
)
from app.errors import (
    ACTION_CANCEL,
    ACTION_EXPAND,
    ACTION_RETRY,
    ACTION_SETTINGS,
    LEVEL_MUTED,
    AppError,
    Err,
    Message,
    message,
    status,
)
from app.images import load_photo_image, load_photo_image_from_file
from app.logging_setup import get_logger
from app.models import (
    PLACEHOLDER,
    Game,
    GameDetails,
    details_meta_line,
    details_price_line,
    format_playtime,
)
from app.pool import (
    RANGE_ALL,
    RANGE_FILTERS,
    RangeState,
    apply_filters,
    available,
    classify_range,
    filter_games,
    pick,
    preset_key,
    preset_label,
    range_label,
    sort_games,
    summary,
)
from app.state import (
    LOAD_CANCEL,
    LOAD_DISABLED,
    LOAD_ENABLED,
    AppState,
    controls_for,
    infer_state,
)
from app.steamid import parse_input
from app.ui import theme
from app.ui.animator import BOUNCE_MS, DrawAnimator
from app.ui.settings_dialog import AboutDialog, SettingsDialog

SEARCH_DEBOUNCE_MS = 300
SAVE_DEBOUNCE_MS = 1000

ACTION_LABELS = {
    ACTION_RETRY: "重试",
    ACTION_SETTINGS: "去设置",
    ACTION_CANCEL: "取消",
    ACTION_EXPAND: "展开范围设置",
}

PLACEHOLDER_ROLLING = "点下面的按钮开始抽签"
PLACEHOLDER_DETAILS = "抽签后这里会显示游戏详情"


class MainWindow:
    """主窗口控制器 + 视图。测试可传入 withdrawn 的 Tk root 直接调用方法。"""

    def __init__(
        self,
        root: tk.Tk,
        *,
        store: ConfigStore,
        config: Config,
        cache: GameCache | None = None,
        client: Any | None = None,
        worker: Any | None = None,
        logger: Logger | None = None,
    ) -> None:
        self.root = root
        self.store = store
        self.config = config
        self.cache = cache or GameCache(store, ttl_days=config.details_cache_ttl_days)
        self.client = client
        self.worker = worker
        self.logger = logger or get_logger()

        self.games: list[Game] = []
        self.excluded: set[int] = set(config.excluded_appids)
        self.filtered: list[Game] = []
        self.query = ""
        self.sort_key = config.ui.sort_key
        self.sort_desc = config.ui.sort_desc
        self.range_state = RangeState(RANGE_ALL)
        self.winner: Game | None = None
        self.offline = False
        self.snapshot_updated = ""
        self.last_error: Err | None = None
        self.state = AppState.IDLE

        self._search_job: str | None = None
        self._save_job: str | None = None
        self._load_task: Any = None
        self._load_target: Any = None
        self._detail_task: Any = None
        self._detail_appid: int | None = None
        self._bounce_job: str | None = None
        self.cover_photo: Any = None
        self._animator = DrawAnimator(root)
        self._settings_dialog: SettingsDialog | None = None
        self._about_dialog: AboutDialog | None = None
        self._refresh_task: Any = None

        self._build()
        self.bind_shortcuts()
        self.refresh_state()

    # ================================================================= 构建
    def _build(self) -> None:
        self.root.title(APP_NAME)
        self.root.geometry(
            self.config.ui.window_geometry or f"{theme.WINDOW_DEFAULT_WIDTH}x{theme.WINDOW_DEFAULT_HEIGHT}"
        )
        self.root.minsize(theme.WINDOW_MIN_WIDTH, theme.WINDOW_MIN_HEIGHT)
        self.root.configure(bg=theme.COLOR_BG)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        outer = ttk.Frame(self.root, padding=theme.PAD_OUTER)
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(2, weight=1)  # 只有区2 吸收多余高度
        self.outer = outer

        self._build_header(outer)
        self._build_identity(outer)
        self._build_pool(outer)
        self._build_draw(outer)
        self._build_details(outer)

    # 区0 顶栏 ---------------------------------------------------------------
    def _build_header(self, parent: ttk.Frame) -> None:
        frame = ttk.Frame(parent)
        frame.grid(row=0, column=0, sticky="ew")
        frame.columnconfigure(0, weight=1)

        ttk.Label(frame, text=APP_NAME, font=theme.FONT_TITLE).grid(row=0, column=0, sticky="w")
        self.about_button = ttk.Button(frame, text="关于", command=self.on_about)
        self.about_button.grid(row=0, column=1, padx=(theme.PAD_TIGHT, 0))
        self.settings_button = ttk.Button(frame, text="设置", command=self.on_settings)
        self.settings_button.grid(row=0, column=2, padx=(theme.PAD_TIGHT, 0))
        self.header = frame

    # 区1 身份 ---------------------------------------------------------------
    def _build_identity(self, parent: ttk.Frame) -> None:
        frame = ttk.Frame(parent, padding=(0, theme.PAD_INNER, 0, 0))
        frame.grid(row=1, column=0, sticky="ew")
        frame.columnconfigure(0, weight=1)

        self.identity_var = tk.StringVar(value=self.config.last_steam_id)
        self.identity_entry = ttk.Entry(frame, textvariable=self.identity_var, font=theme.FONT_BODY)
        self.identity_entry.grid(row=0, column=0, sticky="ew", ipady=4)
        self.identity_entry.bind("<Return>", lambda _event: self.start_load())

        self.load_button = ttk.Button(frame, text="加载游戏库", command=self.on_load_button)
        self.load_button.grid(row=0, column=1, padx=(theme.PAD_INNER, 0))
        self.refresh_button = ttk.Button(frame, text="刷新", command=lambda: self.start_load(refresh=True))
        self.refresh_button.grid(row=0, column=2, padx=(theme.PAD_TIGHT, 0))

        status_row = ttk.Frame(frame)
        status_row.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(theme.PAD_TIGHT, 0))
        status_row.columnconfigure(1, weight=1)
        self.status_dot = ttk.Label(status_row, text="●", font=theme.FONT_SMALL, foreground=theme.COLOR_MUTED)
        self.status_dot.grid(row=0, column=0)
        self.status_label = ttk.Label(
            status_row, text="", font=theme.FONT_SMALL, foreground=theme.COLOR_MUTED, anchor="w"
        )
        self.status_label.grid(row=0, column=1, sticky="ew", padx=(theme.PAD_TIGHT, 0))
        self.status_actions = ttk.Frame(status_row)
        self.status_actions.grid(row=0, column=2, sticky="e")
        self.identity_frame = frame

    # 区2 范围 ---------------------------------------------------------------
    def _build_pool(self, parent: ttk.Frame) -> None:
        frame = ttk.Frame(parent, padding=(0, theme.PAD_INNER, 0, 0))
        frame.grid(row=2, column=0, sticky="nsew")
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(1, weight=1)

        self.pool_toggle_button = ttk.Button(frame, text="", command=self.toggle_pool_panel)
        self.pool_toggle_button.grid(row=0, column=0, sticky="w")

        body = ttk.Frame(frame)
        body.grid(row=1, column=0, sticky="nsew", pady=(theme.PAD_TIGHT, 0))
        body.columnconfigure(0, weight=1)
        body.rowconfigure(2, weight=1)
        self.pool_body = body

        preset_row = ttk.Frame(body)
        preset_row.grid(row=0, column=0, sticky="ew")
        ttk.Label(preset_row, text="范围", font=theme.FONT_BODY).grid(
            row=0, column=0, padx=(0, theme.PAD_TIGHT)
        )
        # 「全部参与」是单选项，点击即取消另外两个快捷筛选；
        # 「从未玩过」「玩得很少」是复选项，可同时勾选（并集）。
        self.range_var = tk.StringVar(value=PRESET_ALL)
        self.all_button = ttk.Radiobutton(
            preset_row,
            text=preset_label(PRESET_ALL),
            value=PRESET_ALL,
            variable=self.range_var,
            command=self.on_all_clicked,
        )
        self.all_button.grid(row=0, column=1, padx=(0, theme.PAD_INNER))

        self.never_var = tk.BooleanVar(value=False)
        self.never_button = ttk.Checkbutton(
            preset_row,
            text=preset_label("never_played"),
            variable=self.never_var,
            command=self.on_filter_clicked,
        )
        self.never_button.grid(row=0, column=2, padx=(0, theme.PAD_INNER))

        self.low_var = tk.BooleanVar(value=False)
        self.low_button = ttk.Checkbutton(
            preset_row,
            text=preset_label("low_playtime"),
            variable=self.low_var,
            command=self.on_filter_clicked,
        )
        self.low_button.grid(row=0, column=3, padx=(0, theme.PAD_INNER))

        #: 供状态机统一启停的范围控件
        self.preset_buttons: dict[str, ttk.Widget] = {
            PRESET_ALL: self.all_button,
            "never_played": self.never_button,
            "low_playtime": self.low_button,
        }

        self.custom_button = ttk.Radiobutton(
            preset_row,
            text=preset_label(PRESET_CUSTOM),
            value=PRESET_CUSTOM,
            variable=self.range_var,
            state="disabled",
        )
        self.custom_button.grid(row=0, column=4)

        search_row = ttk.Frame(body)
        search_row.grid(row=1, column=0, sticky="ew", pady=(theme.PAD_TIGHT, theme.PAD_TIGHT))
        search_row.columnconfigure(0, weight=1)
        self.search_var = tk.StringVar()
        self.search_entry = ttk.Entry(search_row, textvariable=self.search_var, font=theme.FONT_BODY)
        self.search_entry.grid(row=0, column=0, sticky="ew")
        self.search_var.trace_add("write", self._on_search_changed)

        self.bulk_buttons: dict[str, ttk.Button] = {}
        for index, (mode, command) in enumerate(
            (("all", lambda: self.apply_bulk("all")), ("none", lambda: self.apply_bulk("none")), ("invert", lambda: self.apply_bulk("invert"))),
            start=1,
        ):
            button = ttk.Button(search_row, text="", command=command)
            button.grid(row=0, column=index, padx=(theme.PAD_TIGHT, 0))
            self.bulk_buttons[mode] = button

        self.selected_label = ttk.Label(search_row, text="", font=theme.FONT_SMALL, foreground=theme.COLOR_MUTED)
        self.selected_label.grid(row=0, column=4, padx=(theme.PAD_INNER, 0))

        tree_frame = ttk.Frame(body)
        tree_frame.grid(row=2, column=0, sticky="nsew")
        tree_frame.columnconfigure(0, weight=1)
        tree_frame.rowconfigure(0, weight=1)

        self.tree = ttk.Treeview(
            tree_frame,
            columns=("check", "name", "playtime"),
            show="headings",
            selectmode="browse",
            height=8,
        )
        self.tree.heading("check", text="")
        self.tree.heading("name", text="游戏名", command=lambda: self.sort_by(SORT_NAME))
        self.tree.heading("playtime", text="游玩时间", command=lambda: self.sort_by(SORT_PLAYTIME))
        self.tree.column("check", width=34, minwidth=34, stretch=False, anchor="center")
        self.tree.column("name", width=380, minwidth=160, stretch=True)
        self.tree.column("playtime", width=110, minwidth=90, stretch=False, anchor="e")
        self.tree.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.bind("<Button-1>", self._on_tree_click)
        self.tree.bind("<Return>", self._on_tree_return)

        self.pool_frame = frame
        self.pool_panel_expanded = bool(self.config.ui.pool_panel_expanded)
        self._apply_pool_panel_visibility()

    # 区3 抽签 ---------------------------------------------------------------
    def _build_draw(self, parent: ttk.Frame) -> None:
        frame = ttk.Frame(parent, padding=(0, theme.PAD_INNER, 0, 0))
        frame.grid(row=3, column=0, sticky="ew")
        frame.columnconfigure(0, weight=1)

        self.rolling_label = ttk.Label(
            frame,
            text=PLACEHOLDER_ROLLING,
            font=theme.FONT_ROLLING,
            foreground=theme.COLOR_ROLLING,
            anchor="center",
        )
        self.rolling_label.grid(row=0, column=0, sticky="ew", pady=(theme.PAD_INNER, theme.PAD_INNER))

        self.draw_button = ttk.Button(frame, text="抽签", command=self.on_draw, width=16)
        self.draw_button.grid(row=1, column=0)
        self.draw_frame = frame

    # 区4 结果 ---------------------------------------------------------------
    def _build_details(self, parent: ttk.Frame) -> None:
        frame = ttk.Frame(parent, padding=(0, theme.PAD_INNER, 0, 0))
        frame.grid(row=4, column=0, sticky="ew")
        frame.columnconfigure(1, weight=1)

        self.cover_label = ttk.Label(frame, text="", anchor="nw")
        self.cover_label.grid(row=0, column=0, rowspan=4, sticky="nw")

        self.detail_name = ttk.Label(frame, text="", font=theme.FONT_GAME_NAME, anchor="w")
        self.detail_name.grid(row=0, column=1, sticky="ew", padx=(theme.PAD_INNER, 0))
        self.detail_description = ttk.Label(
            frame, text=PLACEHOLDER_DETAILS, font=theme.FONT_SMALL, foreground=theme.COLOR_MUTED,
            anchor="w", justify="left", wraplength=420,
        )
        self.detail_description.grid(row=1, column=1, sticky="ew", padx=(theme.PAD_INNER, 0), pady=(theme.PAD_TIGHT, 0))
        self.detail_meta = ttk.Label(frame, text="", font=theme.FONT_BODY, anchor="w")
        self.detail_meta.grid(row=2, column=1, sticky="ew", padx=(theme.PAD_INNER, 0), pady=(theme.PAD_TIGHT, 0))
        self.detail_extra = ttk.Label(frame, text="", font=theme.FONT_BODY, anchor="w", foreground=theme.COLOR_MUTED)
        self.detail_extra.grid(row=3, column=1, sticky="ew", padx=(theme.PAD_INNER, 0), pady=(theme.PAD_TIGHT, 0))
        self.detail_retry_button = ttk.Button(frame, text="重试", command=self.retry_details, width=10)
        self.detail_retry_button.grid(
            row=4, column=1, sticky="w", padx=(theme.PAD_INNER, 0), pady=(theme.PAD_TIGHT, 0)
        )
        self.detail_retry_button.grid_remove()
        self.details_frame = frame

    # ================================================================= 状态
    def refresh_state(self, *, loading: bool = False, drawing: bool = False, detail_loading: bool = False) -> None:
        total, pool_size = summary(self.games, self.excluded)
        state = infer_state(
            has_key=self.config.has_api_key,
            loading=loading,
            drawing=drawing,
            detail_loading=detail_loading,
            offline=self.offline,
            game_count=total,
            pool_size=pool_size,
            error=self.last_error is not None,
        )
        self.set_state(state)

    def set_state(self, state: AppState) -> None:
        """唯一的状态出口：按 PRD 11.1 设置控件启停。"""
        self.state = state
        controls = controls_for(state, has_result=self.winner is not None)

        self._set_enabled(self.identity_entry, controls.identity_enabled)
        if controls.load_mode == LOAD_CANCEL:
            self.load_button.configure(text="取消", command=self.cancel_load, state="normal")
        elif controls.load_mode == LOAD_DISABLED:
            self.load_button.configure(text="加载游戏库", command=self.on_load_button, state="disabled")
        else:
            self.load_button.configure(text="加载游戏库", command=self.on_load_button, state="normal")
        self._set_enabled(self.refresh_button, controls.load_mode == LOAD_ENABLED)
        self._set_enabled(self.pool_toggle_button, controls.pool_enabled or state is AppState.EMPTY_POOL)
        self._set_tree_enabled(controls.pool_enabled)
        for button in self.preset_buttons.values():
            self._set_enabled(button, controls.pool_enabled)
        self._set_enabled(self.search_entry, controls.pool_enabled)
        for button in self.bulk_buttons.values():
            self._set_enabled(button, controls.pool_enabled)

        self.draw_button.configure(
            text=controls.draw_label,
            state="normal" if controls.draw_enabled else "disabled",
        )
        if controls.zone3_hint is not None:
            self.rolling_label.configure(
                text=controls.zone3_hint.text,
                foreground=theme.color_for_level(controls.zone3_hint.level),
            )
        if controls.status_hint is not None:
            self.set_status(controls.status_hint)

    @staticmethod
    def _set_enabled(widget: Any, enabled: bool) -> None:
        try:
            widget.configure(state="normal" if enabled else "disabled")
        except tk.TclError:  # pragma: no cover - 控件已销毁
            pass

    def _set_tree_enabled(self, enabled: bool) -> None:
        self.tree.configure(selectmode="browse" if enabled else "none")

    # ================================================================= 状态行
    def set_status(self, msg: Message) -> None:
        self.status_label.configure(text=msg.text, foreground=theme.color_for_level(msg.level))
        self.status_dot.configure(foreground=theme.color_for_level(msg.level))
        for child in self.status_actions.winfo_children():
            child.destroy()
        for index, action in enumerate(msg.actions):
            button = ttk.Button(
                self.status_actions,
                text=ACTION_LABELS.get(action, action),
                command=lambda a=action: self.on_status_action(a),
                width=10,
            )
            button.grid(row=0, column=index, padx=(theme.PAD_TIGHT, 0))

    def status_text(self) -> str:
        return str(self.status_label.cget("text"))

    def status_color(self) -> str:
        return str(self.status_label.cget("foreground"))

    # ================================================================= 数据
    @property
    def current_preset(self) -> str:
        """当前范围对应的 config 取值（供持久化与断言使用）。"""
        return preset_key(self.range_state)

    def set_games(
        self,
        games: Sequence[Game],
        *,
        updated_at: str = "",
        offline: bool = False,
        keep_excluded: bool = True,
    ) -> None:
        """载入游戏库：恢复勾选、刷新列表与状态。"""
        self.games = list(games)
        if not keep_excluded:
            self.excluded = set()
        else:
            known = {g.appid for g in self.games}
            self.excluded &= known
        self._sync_range_widgets()
        self.snapshot_updated = updated_at
        self.offline = offline
        self.last_error = None
        self.apply_search()
        self.refresh_state()
        if offline:
            self.set_status(status("offline", updated=self.snapshot_display()))
        else:
            self.set_status(self.loaded_message())

    def snapshot_display(self) -> str:
        return display_time(self.snapshot_updated) if self.snapshot_updated else "未知时间"

    def loaded_message(self) -> Message:
        total, pool_size = summary(self.games, self.excluded)
        return status("loaded", total=total, available=pool_size, updated=self.snapshot_display())

    # ================================================================= 区2 行为
    def toggle_pool_panel(self, expand: bool | None = None) -> None:
        self.pool_panel_expanded = (
            (not self.pool_panel_expanded) if expand is None else bool(expand)
        )
        self._apply_pool_panel_visibility()
        self._schedule_save()

    def _apply_pool_panel_visibility(self) -> None:
        if self.pool_panel_expanded:
            self.pool_body.grid()
        else:
            self.pool_body.grid_remove()
        self._refresh_pool_header()

    def _refresh_pool_header(self) -> None:
        self._sync_range_widgets()
        arrow = "▾" if self.pool_panel_expanded else "▸"
        total, pool_size = summary(self.games, self.excluded)
        self.pool_toggle_button.configure(
            text=f"{arrow} 展开范围设置（当前：{range_label(self.range_state)} · {pool_size}/{total}）"
        )

    def on_all_clicked(self) -> None:
        """「全部参与」：保持互斥语义 —— 点击即取消另外两个快捷筛选（PRD 5.3）。"""
        self.never_var.set(False)
        self.low_var.set(False)
        self.excluded = set()
        self._apply_range_change(status("preset_applied", preset=preset_label(PRESET_ALL)))

    def on_filter_clicked(self) -> None:
        """「从未玩过」/「玩得很少」：可同时勾选，取并集；全不勾选则回落到全部参与。"""
        never = bool(self.never_var.get())
        low = bool(self.low_var.get())
        if not never and not low:
            self.range_var.set(PRESET_ALL)
            self.excluded = set()
            self._apply_range_change(status("preset_applied", preset=preset_label(PRESET_ALL)))
            return
        self.excluded = apply_filters(
            self.games,
            never=never,
            low=low,
            threshold_minutes=self.config.playtime_threshold_minutes,
        )
        label = range_label(RangeState(RANGE_FILTERS, never=never, low=low))
        self._apply_range_change(status("preset_applied", preset=label))

    def _apply_range_change(self, msg: Message) -> None:
        """范围控件的统一出口：重算 → 刷新 → 提示 → 存盘。"""
        self._sync_range_widgets()
        self._refresh_tree_checks()
        self._refresh_pool_header()
        self.set_status(msg)
        self.refresh_state()
        self._schedule_save()

    def _sync_range_widgets(self) -> None:
        """由 ``excluded`` 反推并回填范围控件（排除集合始终是唯一事实来源）。"""
        self.range_state = classify_range(
            self.games, self.excluded, self.config.playtime_threshold_minutes
        )
        state = self.range_state
        if state.mode == RANGE_FILTERS:
            self.range_var.set("")  # 两个单选项都不选中
            self.never_var.set(state.never)
            self.low_var.set(state.low)
            return
        self.range_var.set(PRESET_ALL if state.mode == RANGE_ALL else PRESET_CUSTOM)
        self.never_var.set(False)
        self.low_var.set(False)

    def toggle_game(self, appid: int, *, refresh_state: bool = True) -> None:
        """单击整行切换勾选（PRD 5.3）。"""
        if appid in self.excluded:
            self.excluded.discard(appid)
        else:
            self.excluded.add(appid)
        self._refresh_row(appid)
        self._after_manual_change(refresh_state=refresh_state)

    def _after_manual_change(self, *, refresh_state: bool = True) -> None:
        self._sync_range_widgets()
        self._refresh_pool_header()
        if refresh_state:
            self.refresh_state()
        else:
            self._refresh_counts()
        self._schedule_save()

    def apply_bulk(self, mode: str) -> None:
        """AC-17：只作用于**当前搜索结果**。"""
        targets = [g.appid for g in self.filtered]
        if mode == "all":
            self.excluded -= set(targets)
        elif mode == "none":
            self.excluded |= set(targets)
        elif mode == "invert":
            for appid in targets:
                if appid in self.excluded:
                    self.excluded.discard(appid)
                else:
                    self.excluded.add(appid)
        else:
            raise ValueError(f"未知批量操作：{mode}")
        self._refresh_tree_checks()
        self._after_manual_change()

    def bulk_label(self, mode: str) -> str:
        mapping = {"all": "全选", "none": "全不选", "invert": "反选"}
        return f"{mapping.get(mode, mode)}（当前 {len(self.filtered)} 条）"

    # 搜索 -------------------------------------------------------------------
    def _on_search_changed(self, *_args: object) -> None:
        if self._search_job is not None:
            try:
                self.root.after_cancel(self._search_job)
            except Exception:  # pragma: no cover
                pass
        self._search_job = self.root.after(SEARCH_DEBOUNCE_MS, self.apply_search)

    def apply_search(self) -> None:
        self._search_job = None
        self.query = self.search_var.get()
        ordered = sort_games(self.games, self.sort_key, self.sort_desc)
        self.filtered = filter_games(ordered, self.query)
        self._populate_tree()
        self._refresh_counts()

    def sort_by(self, key: str) -> None:
        if self.sort_key == key:
            self.sort_desc = not self.sort_desc
        else:
            self.sort_key = key
            self.sort_desc = False
        self.config.ui.sort_key = self.sort_key
        self.config.ui.sort_desc = self.sort_desc
        self.apply_search()
        self._schedule_save()

    # 列表渲染 ---------------------------------------------------------------
    def _populate_tree(self) -> None:
        self.tree.delete(*self.tree.get_children())
        for game in self.filtered:
            self.tree.insert(
                "",
                "end",
                iid=str(game.appid),
                values=(self._check_char(game.appid), game.name, format_playtime(game.playtime_forever)),
            )

    def _check_char(self, appid: int) -> str:
        return theme.CHECK_OFF if appid in self.excluded else theme.CHECK_ON

    def _refresh_tree_checks(self) -> None:
        for game in self.filtered:
            self._refresh_row(game.appid)

    def _refresh_row(self, appid: int) -> None:
        iid = str(appid)
        if self.tree.exists(iid):
            self.tree.set(iid, "check", self._check_char(appid))

    def _refresh_counts(self) -> None:
        for mode, button in self.bulk_buttons.items():
            button.configure(text=self.bulk_label(mode))
        total, pool_size = summary(self.games, self.excluded)
        self.selected_label.configure(text=f"已选中 {pool_size} 款")
        self._refresh_pool_header()

    def _on_tree_click(self, event: tk.Event) -> None:
        iid = self.tree.identify_row(event.y)
        if not iid:
            return
        self.tree.selection_set(iid)
        self.toggle_game(int(iid))

    def _on_tree_return(self, _event: tk.Event) -> str:
        selection = self.tree.selection()
        if not selection:
            return "break"
        self.toggle_game(int(selection[0]))
        return "break"

    # ================================================================= 加载
    def on_load_button(self) -> None:
        self.start_load()

    def start_load(self, *, refresh: bool = False) -> None:
        try:
            parsed = parse_input(self.identity_var.get())
        except AppError as exc:
            self.last_error = exc.err
            self.set_status(exc.message)
            self.refresh_state()
            return
        if not self.config.has_api_key:
            self.last_error = Err.NO_KEY
            self.set_status(message(Err.NO_KEY))
            self.refresh_state()
            return
        if self.client is None or self.worker is None:  # pragma: no cover - 组装期
            return
        self.last_error = None
        self.set_state(AppState.LOADING)
        self._load_target = parsed
        self._load_task = self.worker.submit(
            self._load_job,
            on_done=self.on_games_loaded,
            on_error=self.on_load_error,
            on_cancelled=self.on_load_cancelled,
        )

    def _load_job(self, token: Any) -> tuple[str, list[Game]]:
        """在工作线程执行：解析身份 → 拉取游戏库。"""
        assert self._load_target is not None
        steamid = self._load_target.value
        if self._load_target.needs_resolve:
            steamid = self.client.resolve_vanity(steamid, token)
        games = self.client.get_owned_games(steamid, token)
        return steamid, games

    def on_games_loaded(self, payload: tuple[str, list[Game]]) -> None:
        steamid, games = payload
        if steamid != self.config.last_steam_id:
            keep = False  # 换了账号：不沿用上一个账号的排除项（PRD 4.4）
        else:
            keep = True
        self.config.last_steam_id = steamid
        self.identity_var.set(steamid)
        snapshot = self.cache.save_snapshot(steamid, games)
        self._save_config()
        self.set_games(games, updated_at=snapshot.updated_at, offline=False, keep_excluded=keep)

    def on_load_error(self, exc: BaseException) -> None:
        if isinstance(exc, AppError):
            self.last_error = exc.err
            self.set_status(exc.message)
            self.logger.warning("加载失败：%s（%s）", exc.err.value, exc.detail)
        else:  # pragma: no cover - 兜底
            self.last_error = Err.NETWORK
            self.set_status(message(Err.NETWORK))
            self.logger.exception("加载时出现未预期异常", exc_info=exc)
        self.refresh_state()

    def on_load_cancelled(self) -> None:
        self.set_status(Message("已取消加载", LEVEL_MUTED))
        self.refresh_state()

    def cancel_load(self) -> None:
        if self._load_task is not None:
            self._load_task.cancel()

    # ================================================================= 保存
    def _schedule_save(self) -> None:
        if self._save_job is not None:
            try:
                self.root.after_cancel(self._save_job)
            except Exception:  # pragma: no cover
                pass
        self._save_job = self.root.after(SAVE_DEBOUNCE_MS, self.flush_save)

    def flush_save(self) -> None:
        self._save_job = None
        self.save_now()

    def save_now(self) -> None:
        self.config.excluded_appids = set(self.excluded)
        self.config.last_preset = preset_key(self.range_state)
        self.config.ui.pool_panel_expanded = self.pool_panel_expanded
        self.config.ui.sort_key = self.sort_key
        self.config.ui.sort_desc = self.sort_desc
        self.config.ui.window_geometry = self._current_geometry()
        self._save_config()

    def _current_geometry(self) -> str:
        try:
            return self.root.geometry()
        except tk.TclError:  # pragma: no cover
            return self.config.ui.window_geometry

    def _save_config(self) -> None:
        try:
            self.store.save(self.config)
        except OSError:  # pragma: no cover - 磁盘异常不应崩溃
            self.logger.exception("保存配置失败")

    # ================================================================= 其他
    def on_status_action(self, action: str) -> None:
        if action == ACTION_SETTINGS:
            self.on_settings()
        elif action == ACTION_RETRY:
            self.start_load()
        elif action == ACTION_EXPAND:
            self.toggle_pool_panel(expand=True)
        elif action == ACTION_CANCEL:
            self.cancel_load()

    def on_settings(self) -> None:
        """打开设置窗口 W2（PRD 5.6）。"""
        if self._settings_dialog is not None and self._settings_dialog.exists():
            self._settings_dialog.window.lift()
            return
        self._settings_dialog = SettingsDialog(
            self.root,
            config=self.config,
            store=self.store,
            on_saved=self.on_settings_saved,
            logger=self.logger,
        )

    def start_first_run_guide(self) -> SettingsDialog:
        """首次运行引导 W3（PRD 2.1）。"""
        dialog = SettingsDialog(
            self.root,
            config=self.config,
            store=self.store,
            on_saved=self.on_settings_saved,
            first_run=True,
            logger=self.logger,
        )
        self._settings_dialog = dialog
        return dialog

    def on_settings_saved(self) -> None:
        setter = getattr(self.client, "set_api_key", None)
        if callable(setter):
            setter(self.config.api_key)
        redactor = getattr(self.logger, "redactor", None)
        if redactor is not None and self.config.api_key:
            redactor.add_secret(self.config.api_key)
        self.cache.ttl_days = max(1, int(self.config.details_cache_ttl_days))
        self.last_error = None
        self.set_status(status("saved"))
        self.refresh_state()

    def on_about(self) -> None:
        """关于 / 帮助 W4。"""
        self._about_dialog = AboutDialog(self.root, store=self.store)

    # ================================================================= 启动
    def startup_load(self) -> None:
        """启动自动加载（PRD D5）：有缓存先秒开，再后台刷新。"""
        snapshot = self._startup_snapshot()
        if snapshot is not None:
            keep = snapshot.steamid64 == self.config.last_steam_id
            self.identity_var.set(snapshot.steamid64)
            self.set_games(
                snapshot.games, updated_at=snapshot.updated_at, offline=False, keep_excluded=keep
            )
            self._background_refresh(snapshot.steamid64)
            return
        if self.config.has_api_key and self.config.last_steam_id:
            self.identity_var.set(self.config.last_steam_id)
            self.start_load()

    def _startup_snapshot(self) -> Any:
        if self.config.last_steam_id:
            snapshot = self.cache.load_snapshot(self.config.last_steam_id)
            if snapshot is not None and len(snapshot):
                return snapshot
        snapshot = self.cache.newest_snapshot()
        if snapshot is not None and len(snapshot):
            return snapshot
        return None

    def _background_refresh(self, steamid: str) -> None:
        if self.client is None or self.worker is None:
            return
        self._refresh_task = self.worker.submit(
            lambda token: (steamid, self.client.get_owned_games(steamid, token)),
            on_done=self.on_games_loaded,
            on_error=self.on_refresh_failed,
        )

    def on_refresh_failed(self, exc: BaseException) -> None:
        """后台刷新失败：有缓存就降级为"离线可用"（AC-10），否则按普通错误处理。"""
        if not self.games:
            self.on_load_error(exc)
            return
        err = exc.err if isinstance(exc, AppError) else Err.NETWORK
        if err in (Err.NETWORK, Err.RATE_LIMIT):
            self.offline = True
            self.refresh_state()
            self.set_status(status("offline", updated=self.snapshot_display()))
            return
        self.last_error = err
        self.set_status(message(err))
        self.refresh_state()

    # ================================================================= 键盘
    #: 这些控件上的空格保留其原生含义（输入空格 / 激活按钮），避免一次按键触发两个动作
    NATIVE_SPACE_CLASSES = frozenset(
        {"Entry", "TEntry", "Text", "Spinbox", "TCombobox", "Button", "TButton"}
    )

    def bind_shortcuts(self) -> None:
        """PRD 11.4 的键盘映射；使用 root.bind（重复创建会替换而非叠加）。"""
        self.root.bind("<space>", self._on_space_key)
        self.root.bind("<F5>", self._on_refresh_key)
        self.root.bind("<Control-comma>", self._on_settings_key)
        self.root.bind("<Escape>", self._on_escape_key)

    def _focused_class(self) -> str:
        try:
            widget = self.root.focus_get()
        except (KeyError, tk.TclError):  # pragma: no cover - 焦点控件已销毁
            return ""
        if widget is None:
            return ""
        try:
            return str(widget.winfo_class())
        except tk.TclError:  # pragma: no cover
            return ""

    def _on_space_key(self, _event: tk.Event | None = None) -> str | None:
        """空格 = 抽签（PRD D7 / AC-45）。"""
        if self._focused_class() in self.NATIVE_SPACE_CLASSES:
            return None
        if str(self.draw_button.cget("state")) != "normal":
            return None
        self.on_draw()
        return "break"

    def _on_refresh_key(self, _event: tk.Event | None = None) -> str:
        if str(self.refresh_button.cget("state")) == "normal":
            self.start_load(refresh=True)
        return "break"

    def _on_settings_key(self, _event: tk.Event | None = None) -> str:
        self.on_settings()
        return "break"

    def _on_escape_key(self, _event: tk.Event | None = None) -> str:
        if self._settings_dialog is not None and self._settings_dialog.exists():
            self._settings_dialog.cancel()
            return "break"
        if self.state is AppState.LOADING:
            self.cancel_load()
        return "break"

    # ================================================================= 区3 抽签
    def on_draw(self) -> None:
        """抽签：先均匀随机选定 winner，再播动画（PRD 7.5）。"""
        pool = available(self.games, self.excluded)
        if not pool:
            self.refresh_state()  # 进入 S4 并提示调整范围
            return
        self.winner = pick(pool)
        self._show_detail_retry(False)
        self.set_state(AppState.DRAWING)
        self._animator.start(
            [game.name for game in pool],
            self.winner.name,
            on_frame=self._on_anim_frame,
            on_finish=self._on_anim_finish,
        )

    def _on_anim_frame(self, name: str, final: bool) -> None:
        self.rolling_label.configure(
            text=name,
            foreground=theme.COLOR_OK if final else theme.COLOR_ROLLING,
            font=theme.FONT_ROLLING_BOUNCE if final else theme.FONT_ROLLING,
        )
        if not final:
            return
        if self._bounce_job is not None:
            try:
                self.root.after_cancel(self._bounce_job)
            except Exception:  # pragma: no cover
                pass
        self._bounce_job = self.root.after(BOUNCE_MS, self._reset_rolling_font)

    def _reset_rolling_font(self) -> None:
        self._bounce_job = None
        self.rolling_label.configure(font=theme.FONT_ROLLING)

    def _on_anim_finish(self) -> None:
        if self.winner is None:
            return
        self.refresh_state(detail_loading=True)
        self.load_details(self.winner.appid)

    # ================================================================= 区4 详情
    def retry_details(self) -> None:
        if self.winner is not None:
            self.load_details(self.winner.appid)

    def load_details(self, appid: int) -> None:
        """先查缓存（AC-30），未命中再请求；失败走降级（AC-28）。"""
        cached = self.cache.get_detail(appid)
        if cached is not None:
            photo = load_photo_image_from_file(
                self.cache.get_image_path(appid), theme.header_image_size(self._window_width())
            )
            self.render_details(cached, photo)
            self.refresh_state()
            return

        if self.client is None or self.worker is None:
            self.on_details_error(AppError(Err.DETAIL_FAILED, "缺少网络层"))
            return

        self._detail_appid = appid
        self.refresh_state(detail_loading=True)
        self._show_detail_retry(False)  # 请求期间隐藏重试，避免连点
        self.detail_description.configure(
            text=status("detail_loading").text, foreground=theme.COLOR_MUTED
        )
        self._detail_task = self.worker.submit(
            self._detail_job,
            on_done=self.on_details_loaded,
            on_error=self.on_details_error,
        )

    def _detail_job(self, token: Any) -> tuple[GameDetails | None, bytes | None]:
        assert self._detail_appid is not None
        details = self.client.get_app_details(self._detail_appid, token)
        image: bytes | None = None
        if details is not None and details.header_image:
            image = self.client.download_image(details.header_image, token)
        return details, image

    def on_details_loaded(self, payload: tuple[GameDetails | None, bytes | None]) -> None:
        details, image = payload
        if details is None:
            self.on_details_error(AppError(Err.DETAIL_FAILED, "接口返回 success:false"))
            return
        self.cache.put_detail(details)
        if image:
            self.cache.put_image(details.appid, image)
        photo = load_photo_image(image, theme.header_image_size(self._window_width()))
        if photo is None:
            photo = load_photo_image_from_file(
                self.cache.get_image_path(details.appid),
                theme.header_image_size(self._window_width()),
            )
        self.render_details(details, photo)
        self.refresh_state()

    def render_details(self, details: GameDetails, photo: Any | None = None) -> None:
        fallback_name = self.winner.name if self.winner else ""
        self.detail_name.configure(text=details.name or fallback_name)
        self.detail_description.configure(
            text=details.short_description or PLACEHOLDER, foreground=theme.COLOR_MUTED
        )
        self.detail_meta.configure(text=details_meta_line(details))
        self.detail_extra.configure(text=details_price_line(details))
        self._set_cover(photo)
        self._show_detail_retry(False)

    def on_details_error(self, exc: BaseException) -> None:
        self.logger.warning("详情获取失败：%s", exc)
        self.detail_name.configure(text=self.winner.name if self.winner else "")
        self.detail_description.configure(
            text=message(Err.DETAIL_FAILED).text, foreground=theme.COLOR_MUTED
        )
        self.detail_meta.configure(text="")
        self.detail_extra.configure(text="")
        self._set_cover(None)
        self._show_detail_retry(True)
        self.set_status(message(Err.DETAIL_FAILED))
        self.refresh_state()

    def _set_cover(self, photo: Any | None) -> None:
        if photo is None:
            self.cover_photo = None
            self.cover_label.configure(image="", text="（无封面）", foreground=theme.COLOR_MUTED)
        else:
            self.cover_photo = photo  # 必须持有引用，否则被垃圾回收后图片消失
            self.cover_label.configure(image=photo, text="")

    def _show_detail_retry(self, visible: bool) -> None:
        if visible:
            self.detail_retry_button.grid()
        else:
            self.detail_retry_button.grid_remove()

    def _window_width(self) -> int:
        try:
            width = int(self.root.winfo_width())
        except (tk.TclError, TypeError):  # pragma: no cover
            return theme.WINDOW_DEFAULT_WIDTH
        return width if width > 1 else theme.WINDOW_DEFAULT_WIDTH

    def on_close(self) -> None:
        """关窗收尾：保存配置、停止后台任务、销毁窗口（PRD 5.5 / 7.4）。"""
        try:
            self.save_now()
        finally:
            self._animator.cancel()
            if self.worker is not None:
                self.worker.shutdown()
            for job in (self._search_job, self._save_job, self._bounce_job):
                if job is not None:
                    try:
                        self.root.after_cancel(job)
                    except Exception:  # pragma: no cover
                        pass
            self.root.destroy()

    # 供测试与调用方使用的小工具 -------------------------------------------
    def iter_tree_rows(self) -> Iterable[tuple[str, str, str]]:
        for iid in self.tree.get_children():
            values = self.tree.item(iid, "values")
            yield iid, str(values[0]), str(values[1])

    def call_later(self, ms: int, callback: Callable[[], None]) -> str:
        return self.root.after(ms, callback)
