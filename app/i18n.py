"""界面文案的多语言支持（中文 / 英文，默认中文）。

设计要点：

* 所有面向用户的字符串都从 :func:`t` 取，键名集中在 :data:`TRANSLATIONS`；
* **中文是默认语言**，且中文文案与本次改版前的界面完全一致，
  因此既有的界面测试可以直接当作回归网；
* 语言是进程级全局状态，切换后新建/重建的控件即使用新语言
  （``MainWindow`` 通过重建界面实现即时切换）；
* 日志与异常 detail 不翻译（它们是诊断信息，不是界面文案）。
"""

from __future__ import annotations

import ctypes
import locale
import sys

LANG_ZH = "zh"
LANG_EN = "en"
DEFAULT_LANGUAGE = LANG_ZH
VALID_LANGUAGES: tuple[str, ...] = (LANG_ZH, LANG_EN)

#: 中文的各种写法（Windows 返回的 UILanguage 可能是 zh-CN / zh-TW / zh-Hans 等）
_CHINESE_PREFIXES = ("zh", "chinese")
#: Windows 的 UILanguage 名称 → 语言前缀（如 "Chinese (Simplified)" → "zh"）
_WINDOWS_LANGUAGE_NAMES = {
    "chinese": "zh",
    "english": "en",
}

#: 语言选择器里显示的名称（自名，不随当前语言变化）
LANGUAGE_NAMES: dict[str, str] = {LANG_ZH: "中文", LANG_EN: "English"}

_current = DEFAULT_LANGUAGE


def language_from_tag(tag: str | None) -> str | None:
    """把语言标记（``zh-CN`` / ``Chinese (Simplified)`` / ``en-US``）映射成支持的语言。

    认不出来返回 ``None``（调用方决定回落策略）。判定只看语言本身，
    不看地区——中文不管简体繁体都算中文，其余一律英文。
    """
    if not isinstance(tag, str):
        return None
    text = tag.strip().lower()
    if not text:
        return None
    for prefix in _CHINESE_PREFIXES:
        if text.startswith(prefix):
            return LANG_ZH
    for name, language in _WINDOWS_LANGUAGE_NAMES.items():
        if text.startswith(name):
            return language
    # ``en-US`` / ``en_GB`` 这类：取主语言子标签再判一次
    primary = text.replace("_", "-").split("-")[0]
    if primary in VALID_LANGUAGES:
        return primary
    if primary in _WINDOWS_LANGUAGE_NAMES:
        return _WINDOWS_LANGUAGE_NAMES[primary]
    return None


def _windows_ui_language() -> str | None:
    """Windows 的系统界面语言（``GetUserDefaultUILanguage`` 的语言标记）。"""
    if sys.platform != "win32":  # pragma: no cover - 非 Windows
        return None
    try:
        import ctypes.wintypes as wt

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        lcid = kernel32.GetUserDefaultUILanguage()
        buffer = ctypes.create_unicode_buffer(85)  # LOCALE_NAME_MAX_LENGTH
        if kernel32.LCIDToLocaleName(wt.LCID(lcid), buffer, len(buffer), 0):
            return buffer.value
    except Exception:  # pragma: no cover - 老系统或调用失败
        return None
    return None


def system_language() -> str:
    """主机语言 → 应用语言（中文系统给中文，其余给英文，见 PRD D14）。

    三级兜底：Windows API → Python 的 ``locale`` → 默认中文。
    只用于"用户还没做过选择"的首次启动。
    """
    detected = language_from_tag(_windows_ui_language())
    if detected is not None:
        return detected
    try:
        detected = language_from_tag(locale.getdefaultlocale()[0])
    except Exception:  # pragma: no cover - 环境异常
        detected = None
    return detected if detected is not None else DEFAULT_LANGUAGE


def get_language() -> str:
    return _current


def set_language(language: str | None) -> str:
    """切换当前语言；非法值回落到默认语言。返回实际生效的语言。"""
    global _current
    _current = language if language in VALID_LANGUAGES else DEFAULT_LANGUAGE
    return _current


def t(key: str, **kwargs: object) -> str:
    """取界面文案并填充占位符。

    找不到的键会显式暴露成 ``⟦key⟧``（而不是静默返回空串），
    这样漏翻译会在界面上一眼可见、也会被"英文界面不得出现中文"的测试抓到。
    """
    table = TRANSLATIONS.get(_current) or TRANSLATIONS[DEFAULT_LANGUAGE]
    template = table.get(key)
    if template is None:
        template = TRANSLATIONS[DEFAULT_LANGUAGE].get(key)
    if template is None:
        return f"⟦{key}⟧"
    return template.format(**kwargs) if kwargs else template


TRANSLATIONS: dict[str, dict[str, str]] = {
    LANG_ZH: {
        # ---- 错误文案（PRD 5.7）----
        "err.no_key": "请先在设置中填写 Steam API Key",
        "err.empty_input": "请先输入 Steam ID 或资料地址",
        "err.bad_format": "无法解析该资料地址，请检查自定义名称或 API Key",
        "err.vanity_not_found": "无法解析该资料地址，请检查自定义名称或 API Key",
        "err.network": "网络连接失败，请检查网络后重试",
        "err.private_profile": "无法读取游戏库，请将 Steam 个人资料和游戏详情设为公开",
        "err.empty_library": "未找到任何游戏，请确认已拥有游戏且资料已公开",
        "err.invalid_key": "API Key 无效或已停用，请在设置中更新",
        "err.rate_limit": "请求太频繁，请稍等一分钟再试",
        "err.detail_failed": "无法获取详情（可稍后重试）",
        "err.tls_trust": "无法验证 Steam 服务器证书（可能被网络中间件拦截），请检查系统时间与网络代理设置",
        # ---- 状态行（PRD 5.7）----
        "status.saved": "设置已保存",
        "status.loading": "正在读取游戏库…",
        "status.detail_loading": "正在获取详情…",
        "status.loaded": "已加载 {total} 款 · {available} 款参与抽签 · 上次更新 {updated}",
        "status.offline": "当前离线，正在使用 {updated} 缓存的数据",
        "status.pool_empty": "当前范围内没有可抽签的游戏，请调整范围",
        "status.config_corrupt": "配置文件已损坏，已备份并重置为默认设置",
        "status.preset_applied": "已按『{preset}』重设选择，可继续手动调整",
        "status.idle": "输入 Steam ID 或资料地址后点击「加载游戏库」",
        # ---- 状态行附加按钮 ----
        "action.retry": "重试",
        "action.settings": "去设置",
        "action.cancel": "取消",
        # ---- 范围名称 ----
        "preset.all": "全部参与",
        "preset.never_played": "从未玩过",
        "preset.low_playtime": "玩得很少",
        "preset.never_low": "从未玩过 + 玩得很少",
        "preset.custom": "自定义",
        # ---- 主界面 ----
        "ui.about": "关于",
        "ui.settings": "设置",
        "ui.load_library": "加载游戏库",
        "ui.cancel": "取消",
        "ui.refresh": "刷新",
        "ui.range_label": "范围",
        "ui.range_summary": "当前：{preset} · {available}/{total} 款参与抽签",
        "ui.history_open": "抽签记录",
        "ui.bulk_all": "全选（当前 {count} 条）",
        "ui.bulk_none": "全不选（当前 {count} 条）",
        "ui.bulk_invert": "反选（当前 {count} 条）",
        "ui.selected_count": "已选中 {count} 款",
        "ui.column_name": "游戏名",
        "ui.column_playtime": "游玩时间",
        "ui.retry": "重试",
        "ui.no_cover": "（无封面）",
        "ui.unknown_time": "未知时间",
        "ui.rolling_placeholder": "点下面的按钮开始抽签",
        "ui.details_placeholder": "抽签后这里会显示游戏详情",
        "ui.draw": "抽签",
        "ui.draw_again": "再抽一次",
        "ui.drawing": "抽签中…",
        "ui.playtime_never": "未玩过",
        "ui.playtime_under_hour": "不足 1 小时",
        "ui.playtime_hours": "{hours} 小时",
        "ui.free": "免费",
        "ui.price_line": "售价 {price}",
        # ---- 设置窗口 ----
        "settings.title": "设置",
        "settings.first_run_title": "首次设置",
        "settings.first_run_heading": "首次使用需要填写 Steam API Key（只需一次）",
        "settings.first_run_hint": "Steam 不允许第三方读取未授权数据，请先申请一个免费 Key。",
        "settings.api_key_link": "前往 Steam 申请 API Key",
        "settings.api_key_label": "API Key",
        "settings.show_key": "显示",
        "settings.threshold_label": "「玩得很少」阈值（分钟）",
        "settings.ttl_label": "详情缓存有效期（天）",
        "settings.language_label": "界面语言",
        "settings.window_size_label": "窗口大小",
        "settings.window_size_option": "{width} × {height}",
        "settings.window_size_custom": "自定义",
        "settings.reset_window": "恢复所选窗口大小",
        "settings.window_size_hint": "当前：{size}",
        "settings.window_reset_done": "已按所选尺寸调整窗口",
        "settings.window_reset_needs_preset": "请先选择一个窗口大小，再点恢复",
        # ---- 抽签记录窗口 ----
        "history.title": "抽签记录",
        "history.summary": "最近 {count} 次抽签（双击可查看游戏详情）",
        "history.empty": "还没有抽签记录",
        "history.clear": "清空记录",
        "history.close": "关闭",
        "history.column_time": "时间",
        "settings.log_dir": "日志目录：{path}",
        "settings.open_log_dir": "打开日志目录",
        "settings.save": "保存",
        "settings.cancel": "取消",
        "settings.msg_key_empty": "请填写 Steam API Key",
        "settings.msg_key_format": "API Key 应为 32 位十六进制字符",
        "settings.msg_threshold": "「玩得很少」的阈值应为 1 到 100000 之间的整数",
        "settings.msg_ttl": "缓存有效期应为 1 到 365 之间的整数",
        "settings.save_failed": "配置保存失败，请检查磁盘权限",
        # ---- 关于窗口 ----
        "about.title": "关于",
        "about.version": "版本 v{version}",
        "about.privacy": "仅通过 Steam 公开 Web API 读取公开数据；\nAPI Key 只保存在本机，不上传、不硬编码。",
        "about.config_dir": "配置目录：{path}",
        "about.log_file": "日志文件：{path}",
        "about.open_log_dir": "打开日志目录",
        "about.close": "关闭",
        # ---- 命令行 ----
        "cli.description": "从 Steam 游戏库中随机抽一款游戏",
    },
    LANG_EN: {
        # ---- errors ----
        "err.no_key": "Set your Steam API Key in Settings first",
        "err.empty_input": "Enter a Steam ID or profile URL first",
        "err.bad_format": "Could not resolve that profile URL — check the custom name or your API Key",
        "err.vanity_not_found": "Could not resolve that profile URL — check the custom name or your API Key",
        "err.network": "Network request failed. Check your connection and try again",
        "err.private_profile": "Cannot read your library. Set your Steam profile and game details to public",
        "err.empty_library": "No games found. Make sure you own games and your profile is public",
        "err.invalid_key": "Your Steam API Key is invalid or disabled. Update it in Settings",
        "err.rate_limit": "Too many requests. Wait a minute and try again",
        "err.detail_failed": "Could not load details (try again later)",
        "err.tls_trust": "Could not verify Steam's server certificate (possibly intercepted). Check your system time and proxy settings",
        # ---- status line ----
        "status.saved": "Settings saved",
        "status.loading": "Loading your library…",
        "status.detail_loading": "Loading details…",
        "status.loaded": "{total} games loaded · {available} in the pool · updated {updated}",
        "status.offline": "Offline — using cached data from {updated}",
        "status.pool_empty": "No games in the current range. Adjust it to continue",
        "status.config_corrupt": "Config file was corrupted; backed up and reset to defaults",
        "status.preset_applied": "Selection reset to “{preset}” — you can still fine-tune it",
        "status.idle": "Enter your Steam ID or profile URL, then click “Load Library”",
        # ---- status line actions ----
        "action.retry": "Retry",
        "action.settings": "Open settings",
        "action.cancel": "Cancel",
        # ---- range presets ----
        "preset.all": "All games",
        "preset.never_played": "Never played",
        "preset.low_playtime": "Barely played",
        "preset.never_low": "Never played + Barely played",
        "preset.custom": "Custom",
        # ---- main window ----
        "ui.about": "About",
        "ui.settings": "Settings",
        "ui.load_library": "Load Library",
        "ui.cancel": "Cancel",
        "ui.refresh": "Refresh",
        "ui.range_label": "Range",
        "ui.range_summary": "Current: {preset} · {available}/{total} in the pool",
        "ui.history_open": "Pick history",
        "ui.bulk_all": "Select all ({count})",
        "ui.bulk_none": "Select none ({count})",
        "ui.bulk_invert": "Invert ({count})",
        "ui.selected_count": "{count} selected",
        "ui.column_name": "Game",
        "ui.column_playtime": "Playtime",
        "ui.retry": "Retry",
        "ui.no_cover": "(no cover)",
        "ui.unknown_time": "unknown time",
        "ui.rolling_placeholder": "Press the button below to pick a game",
        "ui.details_placeholder": "Game details will show up here after you pick",
        "ui.draw": "Pick a game",
        "ui.draw_again": "Pick again",
        "ui.drawing": "Picking…",
        "ui.playtime_never": "Never played",
        "ui.playtime_under_hour": "Under 1 hour",
        "ui.playtime_hours": "{hours} h",
        "ui.free": "Free",
        "ui.price_line": "Price {price}",
        # ---- settings dialog ----
        "settings.title": "Settings",
        "settings.first_run_title": "First-time setup",
        "settings.first_run_heading": "Enter your Steam API Key to get started (one time only)",
        "settings.first_run_hint": "Steam does not allow third parties to read unauthorized data. Apply for a free key first.",
        "settings.api_key_link": "Get a Steam API Key",
        "settings.api_key_label": "Steam API Key",
        "settings.show_key": "Show",
        "settings.threshold_label": "“Barely played” threshold (minutes)",
        "settings.ttl_label": "Details cache TTL (days)",
        "settings.language_label": "Language",
        "settings.window_size_label": "Window size",
        "settings.window_size_option": "{width} × {height}",
        "settings.window_size_custom": "Custom",
        "settings.reset_window": "Apply selected size",
        "settings.window_size_hint": "Current: {size}",
        "settings.window_reset_done": "Window resized to the selected size",
        "settings.window_reset_needs_preset": "Pick a window size first, then apply it",
        # ---- pick history dialog ----
        "history.title": "Pick history",
        "history.summary": "Last {count} picks (double-click for game details)",
        "history.empty": "No picks yet",
        "history.clear": "Clear history",
        "history.close": "Close",
        "history.column_time": "Time",
        "settings.log_dir": "Log folder: {path}",
        "settings.open_log_dir": "Open log folder",
        "settings.save": "Save",
        "settings.cancel": "Cancel",
        "settings.msg_key_empty": "Enter your Steam API Key",
        "settings.msg_key_format": "The API Key must be 32 hexadecimal characters",
        "settings.msg_threshold": "The threshold must be an integer between 1 and 100000",
        "settings.msg_ttl": "The cache TTL must be an integer between 1 and 365",
        "settings.save_failed": "Could not save the config. Check disk permissions",
        # ---- about dialog ----
        "about.title": "About",
        "about.version": "Version v{version}",
        "about.privacy": "Reads public data only, via Steam's public Web API.\nYour API Key stays on this machine — never uploaded, never hardcoded.",
        "about.config_dir": "Config folder: {path}",
        "about.log_file": "Log file: {path}",
        "about.open_log_dir": "Open log folder",
        "about.close": "Close",
        # ---- CLI ----
        "cli.description": "Pick a random game from your Steam library",
    },
}
