"""Steam Web API 封装（PRD 7.6）。

本模块把 Steam 的各类失败**统一映射成** :class:`~app.errors.AppError`，
界面层只需要看 ``err`` 就能取到中文文案。必须处理的已知行为：

1. 资料非公开不是错误码 —— ``GetOwnedGames`` 对私密库返回 HTTP 200，
   且 ``response`` 里**没有** ``games`` 键 ⇒ 必须判为 PRIVATE_PROFILE；
2. ``ResolveVanityURL`` 未匹配时返回 ``success: 42``（HTTP 200）；
3. ``appdetails`` 返回 ``{"<appid>": {"success": bool, "data": {...}}}``；
4. 免费游戏没有 ``price_overview``；只保留未打折原价（PRD D7）。

纯逻辑模块（不 import tkinter），网络访问通过注入的 session 完成，便于脱机测试。
"""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from typing import Any

import requests

from app.cancellation import CancelToken, NEVER_CANCELLED
from app.errors import AppError, Err
from app.logging_setup import get_logger
from app.models import Game, GameDetails
from app.trust import enable_system_trust, env_flag, is_certificate_error

API_BASE = "https://api.steampowered.com"
STORE_BASE = "https://store.steampowered.com"
MEDIA_BASE = "https://media.steampowered.com"

REQUEST_TIMEOUT = 10
RETRY_DELAYS: tuple[float, ...] = (1.0, 3.0)
RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})
KEY_REQUIRED_STATUSES = frozenset({401, 403})

DEFAULT_CC = "CN"
DEFAULT_LANGUAGE = "schinese"


def parse_app_details(appid: int, payload: Mapping[str, Any]) -> GameDetails:
    """把 ``appdetails`` 的 ``data`` 段转成 :class:`GameDetails`（纯函数）。"""
    genres_raw = payload.get("genres")
    genres: list[str] = []
    if isinstance(genres_raw, list):
        for item in genres_raw:
            if isinstance(item, Mapping):
                description = item.get("description")
                if isinstance(description, str) and description.strip():
                    genres.append(description.strip())

    release_raw = payload.get("release_date")
    release_date = ""
    if isinstance(release_raw, Mapping):
        date_text = release_raw.get("date")
        if isinstance(date_text, str):
            release_date = date_text.strip()

    metacritic_raw = payload.get("metacritic")
    score: int | None = None
    if isinstance(metacritic_raw, Mapping):
        raw_score = metacritic_raw.get("score")
        if isinstance(raw_score, (int, float)) and not isinstance(raw_score, bool):
            score = int(raw_score)
        elif isinstance(raw_score, str) and raw_score.strip().isdigit():
            score = int(raw_score.strip())

    is_free = bool(payload.get("is_free"))

    price_initial: str | None = None
    price_raw = payload.get("price_overview")
    if isinstance(price_raw, Mapping) and not is_free:
        # PRD D7：只显示未打折的原价；缺少 initial 时退回 final
        for field in ("initial_formatted", "final_formatted"):
            value = price_raw.get(field)
            if isinstance(value, str) and value.strip():
                price_initial = value.strip()
                break

    name = payload.get("name")
    header_image = payload.get("header_image")
    short_description = payload.get("short_description")
    return GameDetails(
        appid=appid,
        name=name.strip() if isinstance(name, str) else "",
        header_image=header_image.strip() if isinstance(header_image, str) else "",
        short_description=(
            short_description.strip() if isinstance(short_description, str) else ""
        ),
        genres=tuple(genres),
        release_date=release_date,
        metacritic_score=score,
        is_free=is_free,
        price_initial=price_initial,
        available=True,
    )


class SteamClient:
    """三个接口 + 图片下载的统一入口。"""

    def __init__(
        self,
        api_key: str = "",
        *,
        session: Any | None = None,
        sleeper: Callable[[float], None] | None = None,
        timeout: float = REQUEST_TIMEOUT,
        country: str = DEFAULT_CC,
        language: str = DEFAULT_LANGUAGE,
    ) -> None:
        self.api_key = (api_key or "").strip()
        self._session = session or requests.Session()
        self._sleep = sleeper or time.sleep
        self.timeout = timeout
        self.country = country
        self.language = language
        self._logger = get_logger()
        if env_flag() in {"1", "true", "yes", "on"}:
            # 显式要求：启动时就使用操作系统信任库
            enable_system_trust(force=True)

    def set_api_key(self, api_key: str) -> None:
        self.api_key = (api_key or "").strip()

    # ------------------------------------------------------------------ 底层
    def _require_key(self) -> str:
        if not self.api_key:
            raise AppError(Err.NO_KEY)
        return self.api_key

    def _request(
        self,
        url: str,
        params: Mapping[str, Any] | None,
        token: CancelToken,
        *,
        raw: bool = False,
    ) -> Any:
        """带超时、重试与取消的 GET；返回 JSON 或原始字节。

        证书链校验失败时，允许**每个请求最多一次**切换到操作系统信任库后重试
        （见 app/trust.py）：既不会无限循环，也能让后续请求同样受益，且全程
        不关闭证书校验。
        """
        attempt = 0
        trust_retried = False
        while True:
            token.raise_if_cancelled()
            try:
                response = self._session.get(url, params=dict(params or {}), timeout=self.timeout)
            except requests.Timeout as exc:
                raise AppError(Err.NETWORK, f"请求超时：{exc}") from exc
            except requests.exceptions.SSLError as exc:
                if (
                    not trust_retried
                    and is_certificate_error(exc)
                    and enable_system_trust()
                ):
                    trust_retried = True
                    self._logger.warning("证书校验失败，已切换到操作系统信任库并重试一次")
                    token.raise_if_cancelled()
                    continue
                kind = Err.TLS_TRUST if is_certificate_error(exc) else Err.NETWORK
                raise AppError(kind, f"TLS 校验失败：{exc}") from exc
            except requests.RequestException as exc:
                raise AppError(Err.NETWORK, f"请求失败：{exc}") from exc

            status = int(getattr(response, "status_code", 0) or 0)
            if status in RETRY_STATUSES and attempt < len(RETRY_DELAYS):
                delay = RETRY_DELAYS[attempt]
                attempt += 1
                self._logger.warning("HTTP %s，%s 秒后重试（第 %s 次）", status, delay, attempt)
                self._sleep(delay)
                token.raise_if_cancelled()
                continue

            self._raise_for_status(status)

            if raw:
                content = getattr(response, "content", b"")
                return content if isinstance(content, bytes) else b""
            try:
                return response.json()
            except ValueError as exc:
                raise AppError(Err.NETWORK, f"响应不是合法 JSON：{exc}") from exc

    @staticmethod
    def _raise_for_status(status: int) -> None:
        if status == 200:
            return
        if status in KEY_REQUIRED_STATUSES:
            raise AppError(Err.INVALID_KEY, f"HTTP {status}")
        if status == 429:
            raise AppError(Err.RATE_LIMIT, "HTTP 429")
        raise AppError(Err.NETWORK, f"HTTP {status}")

    # ------------------------------------------------------------- 业务接口
    def resolve_vanity(self, vanity: str, token: CancelToken | None = None) -> str:
        """自定义名 → SteamID64（PRD 5.2 / F2）。"""
        key = self._require_key()
        payload = self._request(
            f"{API_BASE}/ISteamUser/ResolveVanityURL/v1/",
            {"key": key, "vanityurl": vanity},
            token or NEVER_CANCELLED,
        )
        response = payload.get("response") if isinstance(payload, Mapping) else None
        if not isinstance(response, Mapping):
            raise AppError(Err.NETWORK, "解析响应结构异常")
        success = response.get("success")
        steamid = response.get("steamid")
        if success == 1 and isinstance(steamid, str) and steamid.strip():
            return steamid.strip()
        raise AppError(Err.VANITY_NOT_FOUND, f"success={success!r}")

    def get_owned_games(self, steamid64: str, token: CancelToken | None = None) -> list[Game]:
        """拉取游戏库（PRD F3 / 7.6 关键语义）。"""
        key = self._require_key()
        payload = self._request(
            f"{API_BASE}/IPlayerService/GetOwnedGames/v1/",
            {
                "key": key,
                "steamid": steamid64,
                "include_appinfo": "true",
                "include_played_free_games": "true",
                "format": "json",
            },
            token or NEVER_CANCELLED,
        )
        response = payload.get("response") if isinstance(payload, Mapping) else None
        if not isinstance(response, Mapping):
            raise AppError(Err.NETWORK, "游戏库响应结构异常")

        games_raw = response.get("games")
        if games_raw is None:
            # 私密资料：HTTP 200 但没有 games 键
            raise AppError(Err.PRIVATE_PROFILE, "response 中缺少 games 键")
        if not isinstance(games_raw, list):
            raise AppError(Err.NETWORK, "games 字段类型异常")

        games: list[Game] = []
        for item in games_raw:
            if not isinstance(item, Mapping):
                continue
            appid_raw = item.get("appid")
            appid = int(appid_raw) if isinstance(appid_raw, (int, float)) and not isinstance(
                appid_raw, bool
            ) else 0
            name_raw = item.get("name")
            name = name_raw.strip() if isinstance(name_raw, str) else ""
            if appid <= 0 or not name:
                continue  # 过滤脏数据（appid<=0 / 无名条目）
            playtime_raw = item.get("playtime_forever")
            playtime = int(playtime_raw) if isinstance(playtime_raw, (int, float)) and not isinstance(
                playtime_raw, bool
            ) else 0
            icon_raw = item.get("img_icon_url")
            games.append(
                Game(
                    appid=appid,
                    name=name,
                    playtime_forever=max(0, playtime),
                    img_icon_url=icon_raw.strip() if isinstance(icon_raw, str) else "",
                )
            )

        if not games:
            raise AppError(Err.EMPTY_LIBRARY, "games 为空")
        return games

    def get_app_details(self, appid: int, token: CancelToken | None = None) -> GameDetails | None:
        """取详情；``success: false`` 时返回 ``None`` 走降级（PRD F6）。"""
        payload = self._request(
            f"{STORE_BASE}/api/appdetails",
            {
                "appids": str(appid),
                "cc": self.country,
                "l": self.language,
            },
            token or NEVER_CANCELLED,
        )
        if not isinstance(payload, Mapping):
            raise AppError(Err.NETWORK, "详情响应结构异常")
        entry = payload.get(str(appid))
        if not isinstance(entry, Mapping):
            return None
        if not entry.get("success"):
            return None
        data = entry.get("data")
        if not isinstance(data, Mapping):
            return None
        return parse_app_details(appid, data)

    def download_image(self, url: str, token: CancelToken | None = None) -> bytes | None:
        """下载封面图；失败返回 ``None``，由界面显示默认图（不阻塞主流程）。"""
        if not url:
            return None
        try:
            content = self._request(url, None, token or NEVER_CANCELLED, raw=True)
        except AppError as exc:
            self._logger.warning("封面下载失败：%s", exc.detail or exc.err.value)
            return None
        return content or None
