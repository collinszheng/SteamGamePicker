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
from app.config import DEFAULT_THRESHOLD_MINUTES, DEFAULT_TTL_DAYS, Config, ConfigStore
from app.ui import theme
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
        first_run: bool = False,
        logger: Logger | None = None,
    ) -> None:
        self.parent = parent
        self.config = config
        self.store = store
        self.on_saved = on_saved
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
        self.window.bind("<Escape>", lambda _event: self.cancel())
        self.key_entry.focus_set()

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

        self.error_label = ttk.Label(
            frame, text="", font=theme.FONT_SMALL, foreground=theme.COLOR_ERROR, wraplength=380
        )
        self.error_label.grid(row=row, column=0, sticky="w", pady=(theme.PAD_INNER, 0))
        row += 1

        button_row = ttk.Frame(frame)
        button_row.grid(row=row, column=0, sticky="e", pady=(theme.PAD_INNER, 0))
        self.save_button = ttk.Button(
            button_row, text=t("settings.save"), style=theme.STYLE_ACCENT_BUTTON, command=self.save
        )
        self.save_button.grid(row=0, column=0, padx=(0, theme.PAD_TIGHT))
        self.cancel_button = ttk.Button(
            button_row, text=t("settings.cancel"), style=theme.STYLE_BUTTON, command=self.cancel
        )
        self.cancel_button.grid(row=0, column=1)

    def _toggle_show(self) -> None:
        self.key_entry.configure(show="" if self.show_var.get() else "*")

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
