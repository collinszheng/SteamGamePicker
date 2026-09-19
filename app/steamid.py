"""Steam 身份输入解析（PRD 5.2 输入识别规则）。

支持的四种写法（按顺序匹配）：
1. 17 位纯数字 SteamID64；
2. ``https://steamcommunity.com/profiles/<17位数字>``；
3. ``https://steamcommunity.com/id/<自定义名>``；
4. 裸自定义名。

纯逻辑模块，禁止 import tkinter，也不发网络请求——自定义名如何解析由网络层负责。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.errors import AppError, Err

STEAMID64_LENGTH = 17

KIND_STEAMID64 = "steamid64"
KIND_VANITY = "vanity"

_PROFILES_RE = re.compile(r"/profiles/(\d+)", re.IGNORECASE)
_ID_RE = re.compile(r"/id/([^/?#\s]+)", re.IGNORECASE)
_VANITY_RE = re.compile(r"^[A-Za-z0-9_.\-]{2,64}$")


@dataclass(frozen=True, slots=True)
class ParsedInput:
    """解析结果：``kind`` 为 steamid64 时可直接使用，为 vanity 时需调用接口。"""

    kind: str
    value: str

    @property
    def is_steamid64(self) -> bool:
        return self.kind == KIND_STEAMID64

    @property
    def needs_resolve(self) -> bool:
        return self.kind == KIND_VANITY


def parse_input(raw: str | None) -> ParsedInput:
    """解析用户输入；失败时抛 :class:`AppError`（EMPTY_INPUT / BAD_FORMAT）。"""
    text = (raw or "").strip()
    if not text:
        raise AppError(Err.EMPTY_INPUT)

    # 1) 纯数字：只有 17 位才视为 SteamID64
    if text.isdigit():
        if len(text) == STEAMID64_LENGTH:
            return ParsedInput(KIND_STEAMID64, text)
        raise AppError(Err.BAD_FORMAT, f"数字长度 {len(text)} 不是 17 位")

    # 2) /profiles/<数字>
    profile_match = _PROFILES_RE.search(text)
    if profile_match:
        digits = profile_match.group(1)
        if len(digits) == STEAMID64_LENGTH:
            return ParsedInput(KIND_STEAMID64, digits)
        raise AppError(Err.BAD_FORMAT, f"/profiles/ 后的数字长度 {len(digits)} 不是 17 位")

    # 3) /id/<自定义名>
    vanity_match = _ID_RE.search(text)
    if vanity_match:
        return ParsedInput(KIND_VANITY, vanity_match.group(1))

    # 4) 裸自定义名
    if _VANITY_RE.match(text):
        return ParsedInput(KIND_VANITY, text)

    raise AppError(Err.BAD_FORMAT, "无法识别的输入格式")
