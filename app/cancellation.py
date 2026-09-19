"""取消令牌：让后台请求可以被关窗 / 取消按钮打断（PRD 7.4 第 3 条）。

放在独立模块里，避免 ``steam_api``（被 worker 调用）反过来依赖 worker。
"""

from __future__ import annotations

import threading


class Cancelled(Exception):
    """请求被取消；由调用方静默丢弃，不作为错误提示给用户。"""


class CancelToken:
    """线程安全的取消标志。"""

    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def raise_if_cancelled(self) -> None:
        if self._event.is_set():
            raise Cancelled()


#: 不关心取消时的占位令牌
NEVER_CANCELLED = CancelToken()
