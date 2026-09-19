"""错误与状态文案的唯一出处（对应 PRD 5.7）。

界面层不允许直接写中文提示，一律通过 :func:`message` / :func:`status_text`
取得文案，以保证「全中文、无英文报错」以及文案口径一致。

本模块是纯逻辑模块，禁止 import tkinter。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

# ---------------------------------------------------------------------------
# 提示级别：由 app.ui.theme 映射为具体颜色（PRD 5.7 的 绿 / 黄 / 红 / 灰）
# ---------------------------------------------------------------------------
LEVEL_OK = "ok"
LEVEL_WARN = "warn"
LEVEL_ERROR = "error"
LEVEL_MUTED = "muted"

# 状态行上可出现的附加操作按钮
ACTION_SETTINGS = "settings"
ACTION_RETRY = "retry"
ACTION_CANCEL = "cancel"
ACTION_EXPAND = "expand"


class Err(Enum):
    """可预期的业务错误类型（覆盖 PRD 5.7 的错误表）。"""

    NO_KEY = "no_key"
    EMPTY_INPUT = "empty_input"
    BAD_FORMAT = "bad_format"
    VANITY_NOT_FOUND = "vanity_not_found"
    NETWORK = "network"
    PRIVATE_PROFILE = "private_profile"
    EMPTY_LIBRARY = "empty_library"
    INVALID_KEY = "invalid_key"
    RATE_LIMIT = "rate_limit"
    DETAIL_FAILED = "detail_failed"
    TLS_TRUST = "tls_trust"


@dataclass(frozen=True)
class Message:
    """一条状态行提示：文案 + 级别 + 可选的附加操作按钮。"""

    text: str
    level: str = LEVEL_ERROR
    actions: tuple[str, ...] = ()


_ERRORS: dict[Err, Message] = {
    Err.NO_KEY: Message("请先在设置中填写 Steam API Key", LEVEL_ERROR, (ACTION_SETTINGS,)),
    Err.EMPTY_INPUT: Message("请先输入 Steam ID 或资料地址", LEVEL_ERROR),
    Err.BAD_FORMAT: Message(
        "无法解析该资料地址，请检查自定义名称或 API Key", LEVEL_ERROR, (ACTION_SETTINGS,)
    ),
    Err.VANITY_NOT_FOUND: Message(
        "无法解析该资料地址，请检查自定义名称或 API Key", LEVEL_ERROR, (ACTION_SETTINGS,)
    ),
    Err.NETWORK: Message("网络连接失败，请检查网络后重试", LEVEL_ERROR, (ACTION_RETRY,)),
    Err.PRIVATE_PROFILE: Message(
        "无法读取游戏库，请将 Steam 个人资料和游戏详情设为公开", LEVEL_ERROR, (ACTION_RETRY,)
    ),
    Err.EMPTY_LIBRARY: Message(
        "未找到任何游戏，请确认已拥有游戏且资料已公开", LEVEL_ERROR, (ACTION_RETRY,)
    ),
    Err.INVALID_KEY: Message("API Key 无效或已停用，请在设置中更新", LEVEL_ERROR, (ACTION_SETTINGS,)),
    Err.RATE_LIMIT: Message("请求太频繁，请稍等一分钟再试", LEVEL_WARN, (ACTION_RETRY,)),
    Err.DETAIL_FAILED: Message("无法获取详情（可稍后重试）", LEVEL_MUTED, (ACTION_RETRY,)),
    Err.TLS_TRUST: Message(
        "无法验证 Steam 服务器证书（可能被网络中间件拦截），请检查系统时间与网络代理设置",
        LEVEL_ERROR,
        (ACTION_RETRY,),
    ),
}


def message(err: Err) -> Message:
    """取得错误对应的状态行提示。"""
    try:
        return _ERRORS[err]
    except KeyError:  # pragma: no cover - 防御性分支，枚举已全覆盖
        return Message("发生未知错误，请重试", LEVEL_ERROR, (ACTION_RETRY,))


# ---------------------------------------------------------------------------
# 非错误类的状态文案
# ---------------------------------------------------------------------------
STATUS_TEMPLATES: dict[str, str] = {
    "saved": "设置已保存",
    "loading": "正在读取游戏库…",
    "detail_loading": "正在获取详情…",
    "loaded": "已加载 {total} 款 · {available} 款参与抽签 · 上次更新 {updated}",
    "offline": "当前离线，正在使用 {updated} 缓存的数据",
    "pool_empty": "当前范围内没有可抽签的游戏，请调整范围",
    "config_corrupt": "配置文件已损坏，已备份并重置为默认设置",
    "preset_applied": "已按『{preset}』重设选择，可继续手动调整",
    "idle": "输入 Steam ID 或资料地址后点击「加载游戏库」",
}

_STATUS_LEVELS: dict[str, str] = {
    "saved": LEVEL_OK,
    "loading": LEVEL_MUTED,
    "detail_loading": LEVEL_MUTED,
    "loaded": LEVEL_OK,
    "offline": LEVEL_WARN,
    "pool_empty": LEVEL_WARN,
    "config_corrupt": LEVEL_WARN,
    "preset_applied": LEVEL_OK,
    "idle": LEVEL_MUTED,
}

_STATUS_ACTIONS: dict[str, tuple[str, ...]] = {
    "pool_empty": (ACTION_EXPAND,),
    "loading": (ACTION_CANCEL,),
}


def status(key: str, **kwargs: object) -> Message:
    """按 key 取一条状态提示，支持 ``{name}`` 占位符。"""
    template = STATUS_TEMPLATES.get(key)
    if template is None:  # pragma: no cover - 防御性分支
        return Message(str(key), LEVEL_MUTED)
    return Message(
        template.format(**kwargs),
        _STATUS_LEVELS.get(key, LEVEL_MUTED),
        _STATUS_ACTIONS.get(key, ()),
    )


class AppError(Exception):
    """带业务类型的异常；网络层向上抛出的唯一异常类型。"""

    def __init__(self, err: Err, detail: str = "") -> None:
        super().__init__(detail or err.value)
        self.err = err
        self.detail = detail

    @property
    def message(self) -> Message:
        return message(self.err)
