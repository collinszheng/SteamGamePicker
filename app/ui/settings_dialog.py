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

API_KEY_URL = "https://steamcommunity.com/dev/apikey"
API_KEY_LENGTH = 32
_KEY_RE = re.compile(r"^[0-9A-Fa-f]{32}$")

MSG_KEY_EMPTY = "请填写 Steam API Key"
MSG_KEY_FORMAT = f"API Key 应为 {API_KEY_LENGTH} 位十六进制字符"
MSG_THRESHOLD = "「玩得很少」的阈值应为 1 到 100000 之间的整数"
MSG_TTL = "缓存有效期应为 1 到 365 之间的整数"


def validate_api_key(text: str | None) -> str | None:
    """合法返回 ``None``，否则返回中文错误文案（AC-04）。"""
    value = (text or "").strip()
    if not value:
        return MSG_KEY_EMPTY
    if len(value) != API_KEY_LENGTH or not _KEY_RE.match(value):
        return MSG_KEY_FORMAT
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
        self.window.title("首次设置" if first_run else "设置")
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
                text="首次使用需要填写 Steam API Key（只需一次）",
                style=theme.STYLE_LABEL,
                font=theme.FONT_SECTION,
                foreground=theme.COLOR_ACCENT,
            ).grid(row=row, column=0, sticky="w")
            row += 1
            ttk.Label(
                frame,
                text="Steam 不允许第三方读取未授权数据，请先申请一个免费 Key。",
                font=theme.FONT_SMALL,
                foreground=theme.COLOR_MUTED,
            ).grid(row=row, column=0, sticky="w", pady=(theme.PAD_TIGHT, theme.PAD_INNER))
            row += 1

        link_row = ttk.Frame(frame)
        link_row.grid(row=row, column=0, sticky="w", pady=(0, theme.PAD_INNER))
        self.link_button = ttk.Button(
            link_row,
            text="前往 Steam 申请 API Key",
            style=theme.STYLE_LINK_BUTTON,
            command=open_api_key_page,
        )
        self.link_button.grid(row=0, column=0)
        row += 1

        ttk.Label(frame, text="API Key", font=theme.FONT_BODY).grid(row=row, column=0, sticky="w")
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
            text="显示",
            variable=self.show_var,
            style=theme.STYLE_CHECK,
            command=self._toggle_show,
        )
        self.show_check.grid(row=0, column=1, padx=(theme.PAD_INNER, 0))
        row += 1

        ttk.Label(frame, text="「玩得很少」阈值（分钟）", font=theme.FONT_BODY).grid(
            row=row, column=0, sticky="w", pady=(theme.PAD_INNER, 0)
        )
        row += 1
        self.threshold_var = tk.StringVar(value=str(self.config.playtime_threshold_minutes))
        self.threshold_entry = ttk.Entry(
            frame, textvariable=self.threshold_var, width=12, style=theme.STYLE_ENTRY
        )
        self.threshold_entry.grid(row=row, column=0, sticky="w")
        row += 1

        ttk.Label(frame, text="详情缓存有效期（天）", font=theme.FONT_BODY).grid(
            row=row, column=0, sticky="w", pady=(theme.PAD_INNER, 0)
        )
        row += 1
        self.ttl_var = tk.StringVar(value=str(self.config.details_cache_ttl_days))
        self.ttl_entry = ttk.Entry(
            frame, textvariable=self.ttl_var, width=12, style=theme.STYLE_ENTRY
        )
        self.ttl_entry.grid(row=row, column=0, sticky="w")
        row += 1

        log_row = ttk.Frame(frame)
        log_row.grid(row=row, column=0, sticky="ew", pady=(theme.PAD_INNER, 0))
        log_row.columnconfigure(0, weight=1)
        ttk.Label(
            log_row,
            text=f"日志目录：{self.store.logs_dir}",
            font=theme.FONT_SMALL,
            foreground=theme.COLOR_MUTED,
        ).grid(row=0, column=0, sticky="w")
        self.log_button = ttk.Button(
            log_row,
            text="打开日志目录",
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
            button_row, text="保存", style=theme.STYLE_ACCENT_BUTTON, command=self.save
        )
        self.save_button.grid(row=0, column=0, padx=(0, theme.PAD_TIGHT))
        self.cancel_button = ttk.Button(
            button_row, text="取消", style=theme.STYLE_BUTTON, command=self.cancel
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
            self.threshold_var.get(), low=1, high=100000, message=MSG_THRESHOLD
        )
        if threshold_error:
            self.error_label.configure(text=threshold_error)
            return False

        ttl, ttl_error = validate_positive_int(
            self.ttl_var.get(), low=1, high=365, message=MSG_TTL
        )
        if ttl_error:
            self.error_label.configure(text=ttl_error)
            return False

        self.error_label.configure(text="")
        self.config.api_key = self.key_var.get().strip()
        self.config.playtime_threshold_minutes = threshold or DEFAULT_THRESHOLD_MINUTES
        self.config.details_cache_ttl_days = ttl or DEFAULT_TTL_DAYS
        try:
            self.store.save(self.config)
        except OSError:
            self.error_label.configure(text="配置保存失败，请检查磁盘权限")
            return False

        if self.logger is not None:
            self.logger.info("设置已保存")
        if self.on_saved is not None:
            self.on_saved()
        self.close()
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
        self.window.title("关于")
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
        ttk.Label(frame, text=f"版本 v{APP_VERSION}", style=theme.STYLE_LABEL).pack(
            anchor="w", pady=(theme.PAD_TIGHT, theme.PAD_INNER)
        )
        ttk.Label(
            frame,
            text="仅通过 Steam 公开 Web API 读取公开数据；\n"
            "API Key 只保存在本机，不上传、不硬编码。",
            font=theme.FONT_SMALL,
            foreground=theme.COLOR_MUTED,
            justify="left",
        ).pack(anchor="w")
        ttk.Label(
            frame,
            text=f"配置目录：{store.base_dir}",
            font=theme.FONT_SMALL,
            foreground=theme.COLOR_MUTED,
            wraplength=380,
            justify="left",
        ).pack(anchor="w", pady=(theme.PAD_INNER, 0))
        ttk.Label(
            frame,
            text=f"日志文件：{store.logs_dir / 'app.log'}",
            font=theme.FONT_SMALL,
            foreground=theme.COLOR_MUTED,
            wraplength=380,
            justify="left",
        ).pack(anchor="w")

        buttons = ttk.Frame(frame)
        buttons.pack(anchor="e", pady=(theme.PAD_INNER, 0))
        ttk.Button(
            buttons,
            text="打开日志目录",
            style=theme.STYLE_BUTTON,
            command=lambda: open_directory(store.logs_dir),
        ).grid(row=0, column=0, padx=(0, theme.PAD_TIGHT))
        ttk.Button(buttons, text="关闭", style=theme.STYLE_BUTTON, command=self.close).grid(
            row=0, column=1
        )

    def close(self) -> None:
        try:
            self.window.destroy()
        except tk.TclError:  # pragma: no cover
            pass
