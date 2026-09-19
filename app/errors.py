"""错误与状态文案的唯一出处（对应 PRD 5.7）。

界面层不允许直接写中文提示，一律通过 :func:`message` / :func:`status_text`
取得文案，以保证「全中文、无英文报错」以及文案口径一致。

本模块是纯逻辑模块，禁止 import tkinter。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from app.i18n import t

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


_ERRORS: dict[Err, tuple[str, tuple[str, ...]]] = {
    Err.NO_KEY: (LEVEL_ERROR, (ACTION_SETTINGS,)),
    Err.EMPTY_INPUT: (LEVEL_ERROR, ()),
    Err.BAD_FORMAT: (LEVEL_ERROR, (ACTION_SETTINGS,)),
    Err.VANITY_NOT_FOUND: (LEVEL_ERROR, (ACTION_SETTINGS,)),
    Err.NETWORK: (LEVEL_ERROR, (ACTION_RETRY,)),
    Err.PRIVATE_PROFILE: (LEVEL_ERROR, (ACTION_RETRY,)),
    Err.EMPTY_LIBRARY: (LEVEL_ERROR, (ACTION_RETRY,)),
    Err.INVALID_KEY: (LEVEL_ERROR, (ACTION_SETTINGS,)),
    Err.RATE_LIMIT: (LEVEL_WARN, (ACTION_RETRY,)),
    Err.DETAIL_FAILED: (LEVEL_MUTED, (ACTION_RETRY,)),
    Err.TLS_TRUST: (LEVEL_ERROR, (ACTION_RETRY,)),
}


def message(err: Err) -> Message:
    """取得错误对应的状态行提示（文案按当前语言实时取，语言切换后立即生效）。"""
    level, actions = _ERRORS.get(err, (LEVEL_ERROR, (ACTION_RETRY,)))
    return Message(t(f"err.{err.value}"), level, actions)


# ---------------------------------------------------------------------------
# 非错误类的状态文案（文案表在 app/i18n.py）
# ---------------------------------------------------------------------------
_STATUS_KEYS: dict[str, str] = {
    "saved": "status.saved",
    "loading": "status.loading",
    "detail_loading": "status.detail_loading",
    "loaded": "status.loaded",
    "offline": "status.offline",
    "pool_empty": "status.pool_empty",
    "config_corrupt": "status.config_corrupt",
    "preset_applied": "status.preset_applied",
    "idle": "status.idle",
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
    translation_key = _STATUS_KEYS.get(key)
    if translation_key is None:  # pragma: no cover - 防御性分支
        return Message(str(key), LEVEL_MUTED)
    return Message(
        t(translation_key, **kwargs),
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
