"""抽签记录窗口 W6（PRD D14）。

用户要求把抽签记录从主窗口底部挪出来：主界面只留一个「抽签记录」按钮，
点开这个窗口看完整记录。好处是主窗口不用再为记录区预留高度，
游戏列表能长一点，界面也不再"下面挂着一长条"。

窗口职责：

* 列出最近 10 次抽签（时间 + 游戏名，最新在前）；
* 双击 / 回车某条 → 回调主窗口打开那款游戏的详情；
* 「清空记录」→ 清空 ``history.json`` 并刷新自身；
* 打开时居中显示（见 :mod:`app.ui.dialog_utils`）。

它不持有业务状态：数据来自 :class:`app.history.PickHistory`，
展示需要的文案来自 :mod:`app.i18n`，与主窗口保持同一套语言。
"""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from tkinter import ttk

from app.history import PickHistory
from app.i18n import t
from app.ui import theme
from app.ui.dialog_utils import center_window


class HistoryDialog:
    """独立的 ``Toplevel``；可重复打开（关闭后销毁，重新打开重建）。"""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        history: PickHistory,
        on_activate: Callable[[int], None] | None = None,
    ) -> None:
        self.parent = parent
        self.history = history
        self.on_activate = on_activate

        self.window = tk.Toplevel(parent)
        theme.apply_theme(self.window)
        self.window.configure(bg=theme.COLOR_BG)
        self.window.title(t("history.title"))
        self.window.transient(parent)
        self.window.geometry(f"{theme.HISTORY_DIALOG_WIDTH}x{theme.HISTORY_DIALOG_HEIGHT}")
        self.window.minsize(360, 240)
        self.window.protocol("WM_DELETE_WINDOW", self.close)

        self._build()
        self.refresh()
        center_window(self.window)
        self.window.bind("<Escape>", lambda _event: self.close())
        self.window.focus_set()

    # ------------------------------------------------------------------ 构建
    def _build(self) -> None:
        frame = ttk.Frame(self.window, padding=theme.PAD_OUTER, style=theme.STYLE_FRAME)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(1, weight=1)

        self.summary_label = ttk.Label(
            frame, text="", style=theme.STYLE_SECTION_LABEL, foreground=theme.COLOR_MUTED
        )
        self.summary_label.grid(row=0, column=0, sticky="w")

        border, card = theme.make_card(frame, padding=4)
        border.grid(row=1, column=0, sticky="nsew", pady=(theme.PAD_INNER, 0))
        card.columnconfigure(0, weight=1)
        card.rowconfigure(0, weight=1)

        self.tree = ttk.Treeview(
            card,
            columns=("time", "name"),
            show="headings",
            selectmode="browse",
            height=theme.HISTORY_VISIBLE_ROWS,
            style=theme.STYLE_TREE,
        )
        self.tree.heading("time", text=t("history.column_time"))
        self.tree.heading("name", text=t("ui.column_name"))
        self.tree.column("time", width=150, minwidth=120, stretch=False, anchor="w")
        self.tree.column("name", width=340, minwidth=180, stretch=True)
        self.tree.tag_configure("even", background=theme.COLOR_CARD)
        self.tree.tag_configure("odd", background=theme.COLOR_CARD_ALT)
        self.tree.grid(row=0, column=0, sticky="nsew")
        self.tree.bind("<Double-1>", self._on_activate)
        self.tree.bind("<Return>", self._on_activate)

        scroll = ttk.Scrollbar(
            card, orient="vertical", command=self.tree.yview, style=theme.STYLE_SCROLLBAR
        )
        scroll.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=scroll.set)

        buttons = ttk.Frame(frame, style=theme.STYLE_FRAME)
        buttons.grid(row=2, column=0, sticky="ew", pady=(theme.PAD_INNER, 0))
        buttons.columnconfigure(0, weight=1, uniform="history_button")
        buttons.columnconfigure(1, weight=1, uniform="history_button")
        self.clear_button = ttk.Button(
            buttons,
            text=t("history.clear"),
            style=theme.STYLE_BUTTON,
            command=self.clear,
            padding=(theme.DIALOG_BUTTON_PAD_X, theme.DIALOG_BUTTON_PAD_Y),
        )
        self.clear_button.grid(row=0, column=0, sticky="ew", padx=(0, theme.PAD_TIGHT))
        self.close_button = ttk.Button(
            buttons,
            text=t("history.close"),
            style=theme.STYLE_ACCENT_BUTTON,
            command=self.close,
            padding=(theme.DIALOG_BUTTON_PAD_X, theme.DIALOG_BUTTON_PAD_Y),
        )
        self.close_button.grid(row=0, column=1, sticky="ew")

    # ------------------------------------------------------------------ 行为
    def refresh(self) -> None:
        """重画列表与标题（数据变了就调用它）。"""
        tree = self.tree
        tree.delete(*tree.get_children())
        for index, record in enumerate(self.history.entries):
            tree.insert(
                "",
                "end",
                iid=str(index),
                values=(record.display_time, record.name),
                tags=("even" if index % 2 == 0 else "odd",),
            )
        if self.history.entries:
            self.summary_label.configure(
                text=t("history.summary", count=len(self.history.entries))
            )
        else:
            self.summary_label.configure(text=t("history.empty"))
        self.clear_button.configure(state="normal" if self.history.entries else "disabled")

    def clear(self) -> None:
        self.history.clear()
        self.refresh()

    def _on_activate(self, _event: tk.Event | None = None) -> str:
        selection = self.tree.selection()
        if not selection or self.on_activate is None:
            return "break"
        try:
            index = int(selection[0])
        except ValueError:  # pragma: no cover - iid 一定是我们写进去的序号
            return "break"
        if 0 <= index < len(self.history.entries):
            self.on_activate(self.history.entries[index].appid)
        return "break"

    def exists(self) -> bool:
        try:
            return bool(self.window.winfo_exists())
        except tk.TclError:  # pragma: no cover
            return False

    def lift(self) -> None:
        try:
            self.window.lift()
            self.window.focus_set()
        except tk.TclError:  # pragma: no cover
            pass

    def close(self) -> None:
        try:
            self.window.destroy()
        except tk.TclError:  # pragma: no cover
            pass
