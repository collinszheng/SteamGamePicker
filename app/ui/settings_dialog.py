"""设置窗口 W2 / 首次运行引导 W3 / 关于窗口 W4（PRD 2.1 / 5.6）。

W3 就是 W2 的「首次模式」（只显示 Key 相关部分 + 一段说明），避免两套代码。
"""

from __future__ import annotations

import os
import re
import tkinter as tk
import webbrowser
from collections.abc import Callable
from logging import Logger
from pathlib import Path
from tkinter import ttk
from typing import Any

from app import APP_NAME, APP_VERSION
from app.config import (
    DEFAULT_THRESHOLD_MINUTES,
    DEFAULT_TTL_DAYS,
    WINDOW_SIZE_CHOICES,
    WINDOW_SIZE_CUSTOM,
    Config,
    ConfigStore,
    parse_geometry,
    resolve_window_size,
)
from app.ui import theme
from app.ui.dialog_utils import center_window
from app.i18n import LANGUAGE_NAMES, VALID_LANGUAGES, t

API_KEY_URL = "https://steamcommunity.com/dev/apikey"
API_KEY_LENGTH = 32
_KEY_RE = re.compile(r"^[0-9A-Fa-f]{32}$")


def msg_key_empty() -> str:
    return t("settings.msg_key_empty")


def msg_key_format() -> str:
    return t("settings.msg_key_format")


def msg_threshold() -> str:
    return t("settings.msg_threshold")


def msg_ttl() -> str:
    return t("settings.msg_ttl")


def validate_api_key(text: str | None) -> str | None:
    """合法返回 ``None``，否则返回当前语言下的错误文案（AC-04）。"""
    value = (text or "").strip()
    if not value:
        return msg_key_empty()
    if len(value) != API_KEY_LENGTH or not _KEY_RE.match(value):
        return msg_key_format()
    return None


def validate_positive_int(text: str | None, *, low: int, high: int, message: str) -> tuple[int | None, str | None]:
    value = (text or "").strip()
    if not value.isdigit():
        return None, message
    number = int(value)
    if not low <= number <= high:
        return None, message
    return number, None


def open_api_key_page() -> None:  # pragma: no cover - 依赖系统浏览器
    webbrowser.open(API_KEY_URL)


def open_directory(path: Path) -> None:  # pragma: no cover - 依赖资源管理器
    try:
        os.startfile(str(path))  # type: ignore[attr-defined]
    except OSError:
        pass


class SettingsDialog:
    """独立的 Toplevel；保存成功后回调 ``on_saved``。"""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        config: Config,
        store: ConfigStore,
        on_saved: Callable[[], None] | None = None,
        on_reset_geometry: Callable[[str], None] | None = None,
        first_run: bool = False,
        logger: Logger | None = None,
    ) -> None:
        self.parent = parent
        self.config = config
        self.store = store
        self.on_saved = on_saved
        self.on_reset_geometry = on_reset_geometry
        self.first_run = first_run
        self.logger = logger

        self.window = tk.Toplevel(parent)
        theme.apply_theme(self.window)
        self.window.configure(bg=theme.COLOR_BG)
        self.window.title(t("settings.first_run_title") if first_run else t("settings.title"))
        self.window.transient(parent)
        self.window.resizable(False, False)
        self.window.protocol("WM_DELETE_WINDOW", self.cancel)

        self._build()
        self.center_on_screen()  # 不居中会默认弹在屏幕左上角，很难看也很难点
        self.window.bind("<Escape>", lambda _event: self.cancel())
        self.key_entry.focus_set()

    # ------------------------------------------------------------------ 位置
    def center_on_screen(self) -> tuple[int, int]:
        """把窗口摆到屏幕正中（见 :mod:`app.ui.dialog_utils`）。"""
        return center_window(self.window)

    # ------------------------------------------------------------------ 构建
    def _build(self) -> None:
        frame = ttk.Frame(self.window, padding=theme.PAD_OUTER)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(0, weight=1)

        row = 0
        if self.first_run:
            ttk.Label(
                frame,
                text=t("settings.first_run_heading"),
                style=theme.STYLE_LABEL,
                font=theme.FONT_SECTION,
                foreground=theme.COLOR_ACCENT,
            ).grid(row=row, column=0, sticky="w")
            row += 1
            ttk.Label(
                frame,
                text=t("settings.first_run_hint"),
                font=theme.FONT_SMALL,
                foreground=theme.COLOR_MUTED,
            ).grid(row=row, column=0, sticky="w", pady=(theme.PAD_TIGHT, theme.PAD_INNER))
            row += 1

        link_row = ttk.Frame(frame)
        link_row.grid(row=row, column=0, sticky="w", pady=(0, theme.PAD_INNER))
        self.link_button = ttk.Button(
            link_row,
            text=t("settings.api_key_link"),
            style=theme.STYLE_LINK_BUTTON,
            command=open_api_key_page,
        )
        self.link_button.grid(row=0, column=0)
        row += 1

        ttk.Label(frame, text=t("settings.api_key_label"), font=theme.FONT_BODY).grid(
            row=row, column=0, sticky="w"
        )
        row += 1
        key_row = ttk.Frame(frame)
        key_row.grid(row=row, column=0, sticky="ew")
        key_row.columnconfigure(0, weight=1)
        self.key_var = tk.StringVar(value=self.config.api_key)
        self.key_entry = ttk.Entry(
            key_row,
            textvariable=self.key_var,
            show="*",
            width=40,
            font=theme.FONT_BODY,
            style=theme.STYLE_ENTRY,
        )
        self.key_entry.grid(row=0, column=0, sticky="ew")
        self.show_var = tk.BooleanVar(value=False)
        self.show_check = ttk.Checkbutton(
            key_row,
            text=t("settings.show_key"),
            variable=self.show_var,
            style=theme.STYLE_CHECK,
            command=self._toggle_show,
        )
        self.show_check.grid(row=0, column=1, padx=(theme.PAD_INNER, 0))
        row += 1

        ttk.Label(frame, text=t("settings.threshold_label"), font=theme.FONT_BODY).grid(
            row=row, column=0, sticky="w", pady=(theme.PAD_INNER, 0)
        )
        row += 1
        self.threshold_var = tk.StringVar(value=str(self.config.playtime_threshold_minutes))
        self.threshold_entry = ttk.Entry(
            frame, textvariable=self.threshold_var, width=12, style=theme.STYLE_ENTRY
        )
        self.threshold_entry.grid(row=row, column=0, sticky="w")
        row += 1

        ttk.Label(frame, text=t("settings.ttl_label"), font=theme.FONT_BODY).grid(
            row=row, column=0, sticky="w", pady=(theme.PAD_INNER, 0)
        )
        row += 1
        self.ttl_var = tk.StringVar(value=str(self.config.details_cache_ttl_days))
        self.ttl_entry = ttk.Entry(
            frame, textvariable=self.ttl_var, width=12, style=theme.STYLE_ENTRY
        )
        self.ttl_entry.grid(row=row, column=0, sticky="w")
        row += 1

        # 界面语言：选项名用各自语言的自名（中文 / English），不随当前语言变化
        ttk.Label(frame, text=t("settings.language_label"), font=theme.FONT_BODY).grid(
            row=row, column=0, sticky="w", pady=(theme.PAD_INNER, 0)
        )
        row += 1
        language_row = ttk.Frame(frame)
        language_row.grid(row=row, column=0, sticky="w")
        self.language_var = tk.StringVar(value=self.config.language)
        self.language_buttons: dict[str, ttk.Radiobutton] = {}
        for index, language in enumerate(VALID_LANGUAGES):
            option = ttk.Radiobutton(
                language_row,
                text=LANGUAGE_NAMES.get(language, language),
                value=language,
                variable=self.language_var,
                style=theme.STYLE_RADIO,
            )
            option.grid(row=0, column=index, padx=(0, theme.PAD_INNER))
            self.language_buttons[language] = option
        row += 1

        log_row = ttk.Frame(frame)
        log_row.grid(row=row, column=0, sticky="ew", pady=(theme.PAD_INNER, 0))
        log_row.columnconfigure(0, weight=1)
        ttk.Label(
            log_row,
            text=t("settings.log_dir", path=self.store.logs_dir),
            font=theme.FONT_SMALL,
            foreground=theme.COLOR_MUTED,
        ).grid(row=0, column=0, sticky="w")
        self.log_button = ttk.Button(
            log_row,
            text=t("settings.open_log_dir"),
            style=theme.STYLE_BUTTON,
            command=lambda: open_directory(self.store.logs_dir),
        )
        self.log_button.grid(row=0, column=1, padx=(theme.PAD_INNER, 0))
        row += 1

        # 窗口大小：下拉条选预设（用户要求：点一下展开全部预设值）+ 「恢复所选窗口大小」
        # （恢复的目标 = 下拉条里的值）
        ttk.Label(frame, text=t("settings.window_size_label"), font=theme.FONT_BODY).grid(
            row=row, column=0, sticky="w", pady=(theme.PAD_INNER, 0)
        )
        row += 1
        self.window_size_var = tk.StringVar(value=self._initial_window_size())
        #: 下拉条里显示的值（含「自定义」，表示当前窗口尺寸不属于任何预设）
        self._size_values: tuple[str, ...] = tuple(WINDOW_SIZE_CHOICES) + (WINDOW_SIZE_CUSTOM,)
        self.window_size_combo = ttk.Combobox(
            frame,
            textvariable=self.window_size_var,
            values=[self._size_label(value) for value in self._size_values],
            state="readonly",  # 只允许选预设，不允许手打
            width=18,
            style=theme.STYLE_COMBOBOX,
            font=theme.FONT_BODY,
        )
        self.window_size_combo.grid(row=row, column=0, sticky="w")
        # ttk 的 Combobox 用显示文案绑定，这里把它映射回配置值
        self.window_size_combo.bind("<<ComboboxSelected>>", self._on_size_selected)
        self.current_size_label = ttk.Label(
            frame,
            text=t("settings.window_size_hint", size=self.config.ui.window_geometry),
            font=theme.FONT_SMALL,
            foreground=theme.COLOR_MUTED,
        )
        self.current_size_label.grid(row=row + 1, column=0, sticky="w", pady=(theme.PAD_TIGHT, 0))
        row += 2

        self.reset_window_button = ttk.Button(
            frame,
            text=t("settings.reset_window"),
            style=theme.STYLE_BUTTON,
            command=self.reset_window_size,
        )
        self.reset_window_button.grid(row=row, column=0, sticky="w", pady=(theme.PAD_TIGHT, 0))
        row += 1

        self.error_label = ttk.Label(
            frame, text="", font=theme.FONT_SMALL, foreground=theme.COLOR_ERROR, wraplength=380
        )
        self.error_label.grid(row=row, column=0, sticky="w", pady=(theme.PAD_INNER, 0))
        row += 1

        # 两个按钮必须一样大：样式不同（主按钮 padding 更大）会让它们一大一小。
        # 这里统一内边距，并让两列等宽（uniform），两者尺寸必然一致。
        button_row = ttk.Frame(frame)
        button_row.grid(row=row, column=0, sticky="ew", pady=(theme.PAD_INNER, 0))
        button_row.columnconfigure(0, weight=1, uniform="dialog_button")
        button_row.columnconfigure(1, weight=1, uniform="dialog_button")
        save_button = ttk.Button(
            button_row,
            text=t("settings.save"),
            style=theme.STYLE_ACCENT_BUTTON,
            command=self.save,
            padding=(theme.DIALOG_BUTTON_PAD_X, theme.DIALOG_BUTTON_PAD_Y),
        )
        save_button.grid(row=0, column=0, sticky="ew", padx=(0, theme.PAD_TIGHT))
        cancel_button = ttk.Button(
            button_row,
            text=t("settings.cancel"),
            style=theme.STYLE_BUTTON,
            command=self.cancel,
            padding=(theme.DIALOG_BUTTON_PAD_X, theme.DIALOG_BUTTON_PAD_Y),
        )
        cancel_button.grid(row=0, column=1, sticky="ew")
        self.save_button = save_button
        self.cancel_button = cancel_button
        # 构建完成后再回填下拉条的选中项（那时 `_size_values` 已就绪）
        self.select_window_size(self._initial_window_size())

    def _initial_window_size(self) -> str:
        """按当前窗口几何推断该选中哪个尺寸选项（含屏幕装不下的情况）。"""
        parent = self.parent
        try:
            screen_width = int(parent.winfo_screenwidth())
            screen_height = int(parent.winfo_screenheight())
        except (AttributeError, tk.TclError):  # pragma: no cover - 无显示环境
            screen_width, screen_height = 0, 0
        return resolve_window_size(
            self.config.ui.window_size,
            self.config.ui.window_geometry,
            screen_width,
            screen_height,
        )

    @staticmethod
    def _size_label(choice: str) -> str:
        """把 ``680x880`` 显示成人读的尺寸标签（下拉条里的文案）。"""
        parsed = parse_geometry(choice)
        if parsed is None:
            # 「自定义」没有具体尺寸，直接用文案
            return t("settings.window_size_custom")
        return t("settings.window_size_option", width=parsed[0], height=parsed[1])

    def selected_window_size(self) -> str:
        """下拉条当前选中的**配置值**（``680x880`` / ``800x1100`` / ``1100x800`` / ``custom``）。

        下拉条里显示的是人读文案（``680 × 880``），这里用显示文案反查配置值；
        认不出来时按「自定义」处理（例如手动拖过窗口后的状态）。
        """
        display = self.window_size_var.get()
        labels = [self._size_label(value) for value in self._size_values]
        if display in labels:
            return self._size_values[labels.index(display)]
        return WINDOW_SIZE_CUSTOM

    def select_window_size(self, size: str) -> None:
        """按配置值选中下拉条里的选项（同时刷新「自定义」提示行的措辞）。"""
        if size in self._size_values:
            self.window_size_var.set(self._size_label(size))
        else:
            self.window_size_var.set(self._size_label(WINDOW_SIZE_CUSTOM))
        self.current_size_label.configure(
            text=t("settings.window_size_hint", size=size)
            if size != WINDOW_SIZE_CUSTOM
            else t("settings.window_size_detected", size=self.config.ui.window_geometry)
        )

    def _on_size_selected(self, _event: tk.Event | None = None) -> None:
        self.select_window_size(self.selected_window_size())

    def _toggle_show(self) -> None:
        self.key_entry.configure(show="" if self.show_var.get() else "*")

    def reset_window_size(self) -> None:
        """把主窗口恢复到**选择框里选中的**尺寸（PRD D14）。

        用户明确要求：恢复默认的值 = 尺寸选择框内的值，而不是写死某个尺寸。
        选了「自定义」时没有可恢复的目标，给出提示而不是默默套用别的尺寸。
        """
        target = self.selected_window_size()
        if target == WINDOW_SIZE_CUSTOM:
            self.error_label.configure(text=t("settings.window_reset_needs_preset"))
            return
        if self.on_reset_geometry is not None:
            self.on_reset_geometry(target)
            self.current_size_label.configure(text=t("settings.window_size_hint", size=target))
            self.error_label.configure(text=t("settings.window_reset_done"))

    # ------------------------------------------------------------------ 行为
    def error_text(self) -> str:
        return str(self.error_label.cget("text"))

    def save(self) -> bool:
        """校验并写盘；成功返回 True（AC-04：格式不对必须被拒绝）。"""
        key_error = validate_api_key(self.key_var.get())
        if key_error:
            self.error_label.configure(text=key_error)
            return False

        threshold, threshold_error = validate_positive_int(
            self.threshold_var.get(), low=1, high=100000, message=msg_threshold()
        )
        if threshold_error:
            self.error_label.configure(text=threshold_error)
            return False

        ttl, ttl_error = validate_positive_int(
            self.ttl_var.get(), low=1, high=365, message=msg_ttl()
        )
        if ttl_error:
            self.error_label.configure(text=ttl_error)
            return False

        self.error_label.configure(text="")
        self.config.api_key = self.key_var.get().strip()
        self.config.playtime_threshold_minutes = threshold or DEFAULT_THRESHOLD_MINUTES
        self.config.details_cache_ttl_days = ttl or DEFAULT_TTL_DAYS
        self.config.language = self.language_var.get()
        # 选了预设就即时套用（用户要求：选择框的值既是显示值，也是「恢复默认」的目标）
        chosen_size = self.selected_window_size()
        self.config.ui.window_size = chosen_size
        if chosen_size != WINDOW_SIZE_CUSTOM and self.on_reset_geometry is not None:
            self.on_reset_geometry(chosen_size)
        try:
            self.store.save(self.config)
        except OSError:
            self.error_label.configure(text=t("settings.save_failed"))
            return False

        # 先关窗再回调：on_saved 在语言切换时会重建主界面
        self.close()
        if self.logger is not None:
            self.logger.info("设置已保存")
        if self.on_saved is not None:
            self.on_saved()
        return True

    def cancel(self) -> None:
        self.close()

    def close(self) -> None:
        try:
            self.window.destroy()
        except tk.TclError:  # pragma: no cover
            pass

    def exists(self) -> bool:
        try:
            return bool(self.window.winfo_exists())
        except tk.TclError:  # pragma: no cover
            return False


class AboutDialog:
    """关于 / 帮助窗口 W4。"""

    def __init__(self, parent: tk.Misc, *, store: ConfigStore) -> None:
        self.store = store
        self.window = tk.Toplevel(parent)
        theme.apply_theme(self.window)
        self.window.configure(bg=theme.COLOR_BG)
        self.window.title(t("about.title"))
        self.window.transient(parent)
        self.window.resizable(False, False)

        frame = ttk.Frame(self.window, padding=theme.PAD_OUTER)
        frame.pack(fill="both", expand=True)

        ttk.Label(
            frame,
            text=APP_NAME,
            style=theme.STYLE_LABEL,
            font=theme.FONT_SECTION,
            foreground=theme.COLOR_ACCENT,
        ).pack(anchor="w")
        ttk.Label(frame, text=t("about.version", version=APP_VERSION), style=theme.STYLE_LABEL).pack(
            anchor="w", pady=(theme.PAD_TIGHT, theme.PAD_INNER)
        )
        ttk.Label(
            frame,
            text=t("about.privacy"),
            font=theme.FONT_SMALL,
            foreground=theme.COLOR_MUTED,
            justify="left",
        ).pack(anchor="w")
        ttk.Label(
            frame,
            text=t("about.config_dir", path=store.base_dir),
            font=theme.FONT_SMALL,
            foreground=theme.COLOR_MUTED,
            wraplength=380,
            justify="left",
        ).pack(anchor="w", pady=(theme.PAD_INNER, 0))
        ttk.Label(
            frame,
            text=t("about.log_file", path=store.logs_dir / "app.log"),
            font=theme.FONT_SMALL,
            foreground=theme.COLOR_MUTED,
            wraplength=380,
            justify="left",
        ).pack(anchor="w")

        buttons = ttk.Frame(frame)
        buttons.pack(anchor="e", pady=(theme.PAD_INNER, 0))
        ttk.Button(
            buttons,
            text=t("about.open_log_dir"),
            style=theme.STYLE_BUTTON,
            command=lambda: open_directory(store.logs_dir),
        ).grid(row=0, column=0, padx=(0, theme.PAD_TIGHT))
        ttk.Button(buttons, text=t("about.close"), style=theme.STYLE_BUTTON, command=self.close).grid(
            row=0, column=1
        )

    def close(self) -> None:
        try:
            self.window.destroy()
        except tk.TclError:  # pragma: no cover
            pass
