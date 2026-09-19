"""数据结构与纯展示格式化（PRD 5.3 / 5.5）。

纯逻辑模块，禁止 import tkinter。
"""

from __future__ import annotations

from dataclasses import dataclass

from app.i18n import t

#: 缺值统一显示为破折号（PRD 5.5）
PLACEHOLDER = "—"

ICON_URL_TEMPLATE = (
    "https://media.steampowered.com/steamcommunity/public/images/apps/{appid}/{hash}.jpg"
)
HEADER_IMAGE_MIN_WIDTH = 460  # Steam header_image 原图 460x215


@dataclass(frozen=True, slots=True)
class Game:
    """GetOwnedGames 返回的一款游戏（PRD 5.3 库与范围所需字段）。"""

    appid: int
    name: str
    playtime_forever: int = 0
    img_icon_url: str = ""

    @property
    def icon_url(self) -> str | None:
        if not self.img_icon_url:
            return None
        return ICON_URL_TEMPLATE.format(appid=self.appid, hash=self.img_icon_url)

    def to_dict(self) -> dict[str, object]:
        return {
            "appid": self.appid,
            "name": self.name,
            "playtime_forever": self.playtime_forever,
            "img_icon_url": self.img_icon_url,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> Game:
        return cls(
            appid=_as_int(data.get("appid"), 0),
            name=str(data.get("name") or ""),
            playtime_forever=_as_int(data.get("playtime_forever"), 0),
            img_icon_url=str(data.get("img_icon_url") or ""),
        )


@dataclass(frozen=True, slots=True)
class GameDetails:
    """appdetails 取回、并被界面使用的字段（PRD 5.5）。

    ``price_initial`` 只保存**未打折的原价**（PRD D7）。
    """

    appid: int
    name: str = ""
    header_image: str = ""
    short_description: str = ""
    genres: tuple[str, ...] = ()
    release_date: str = ""
    metacritic_score: int | None = None
    is_free: bool = False
    price_initial: str | None = None
    available: bool = True  # 对应接口的 success 字段

    def to_dict(self) -> dict[str, object]:
        return {
            "appid": self.appid,
            "name": self.name,
            "header_image": self.header_image,
            "short_description": self.short_description,
            "genres": list(self.genres),
            "release_date": self.release_date,
            "metacritic_score": self.metacritic_score,
            "is_free": self.is_free,
            "price_initial": self.price_initial,
            "available": self.available,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> GameDetails:
        genres_raw = data.get("genres") or []
        genres = tuple(str(g) for g in genres_raw) if isinstance(genres_raw, (list, tuple)) else ()
        score = data.get("metacritic_score")
        return cls(
            appid=int(data.get("appid") or 0),
            name=str(data.get("name") or ""),
            header_image=str(data.get("header_image") or ""),
            short_description=str(data.get("short_description") or ""),
            genres=genres,
            release_date=str(data.get("release_date") or ""),
            metacritic_score=int(score) if isinstance(score, (int, float)) else None,
            is_free=bool(data.get("is_free")),
            price_initial=(
                str(data["price_initial"]) if data.get("price_initial") not in (None, "") else None
            ),
            available=bool(data.get("available", True)),
        )

    @property
    def genres_text(self) -> str:
        return " · ".join(self.genres) if self.genres else PLACEHOLDER

    @property
    def score_text(self) -> str:
        return str(self.metacritic_score) if self.metacritic_score is not None else PLACEHOLDER

    @property
    def release_text(self) -> str:
        return display_or_placeholder(self.release_date)

    @property
    def price_text(self) -> str:
        """售价展示：免费游戏显示「免费」，其余只显示未打折的原价（PRD D7）。"""
        if self.is_free:
            return t("ui.free")
        return display_or_placeholder(self.price_initial)


def _as_int(value: object, default: int) -> int:
    """尽力把 JSON 里的数字转成 int，失败则使用默认值。"""
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        text = value.strip()
        if text.lstrip("-").isdigit():
            return int(text)
    return default


def display_or_placeholder(value: object) -> str:
    """空值统一显示为 ``—``。"""
    if value is None:
        return PLACEHOLDER
    text = str(value).strip()
    return text if text else PLACEHOLDER


def format_playtime(minutes: int) -> str:
    """游玩时长展示规则（PRD 5.3）：未玩过 / 不足 1 小时 / 12.4 小时。"""
    if minutes <= 0:
        return t("ui.playtime_never")
    if minutes < 60:
        return t("ui.playtime_under_hour")
    return t("ui.playtime_hours", hours=f"{minutes / 60:.1f}")


def details_meta_line(details: GameDetails) -> str:
    """结果区第二行：类型 · 发行日期 · Metacritic 评分（缺失项自动省略）。"""
    parts = list(details.genres)
    if details.release_date.strip():
        parts.append(details.release_date.strip())
    if details.metacritic_score is not None:
        parts.append(f"Metacritic {details.metacritic_score}")
    return " · ".join(parts) if parts else PLACEHOLDER


def details_price_line(details: GameDetails) -> str:
    """结果区售价行：只显示未打折原价 / 免费（PRD D7）。"""
    return t("ui.price_line", price=details.price_text)
