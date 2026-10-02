"""配置持久化：``%APPDATA%\\SteamGamePicker\\config.json``（PRD 6.2 / 6.4）。

必须满足（验收 AC-31 / AC-32 / AC-33）：
* 原子写：临时文件 + ``os.replace``，任何时刻磁盘上都是完整 JSON；
* 损坏（非法 JSON / 顶层不是对象）→ 备份改名为 ``config.corrupt-<时间戳>.json``
  并按默认值启动，保留最新 3 份备份；
* 任意字段缺失或类型异常 → 使用默认值，绝不因此启动失败；
* ``%APPDATA%`` 不存在时回退到用户主目录。

纯逻辑模块，禁止 import tkinter。
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

from app.ui import theme

SCHEMA_VERSION = 1
APP_DIR_NAME = "SteamGamePicker"
DEFAULT_THRESHOLD_MINUTES = 120
DEFAULT_TTL_DAYS = 7
CORRUPT_BACKUP_KEEP = 3

PRESET_ALL = "all"
PRESET_NEVER = "never_played"
PRESET_LOW = "low_playtime"
PRESET_NEVER_LOW = "never_low"  # 两个快捷筛选同时勾选（用户要求：可并存）
PRESET_CUSTOM = "custom"
VALID_PRESETS = (PRESET_ALL, PRESET_NEVER, PRESET_LOW, PRESET_NEVER_LOW, PRESET_CUSTOM)

SORT_NAME = "name"
SORT_PLAYTIME = "playtime"
VALID_SORT_KEYS = (SORT_NAME, SORT_PLAYTIME)

LANGUAGE_ZH = "zh"
LANGUAGE_EN = "en"
DEFAULT_LANGUAGE = LANGUAGE_ZH
VALID_LANGUAGES = (LANGUAGE_ZH, LANGUAGE_EN)

#: 默认窗口尺寸取自 app.ui.theme（布局的唯一出处）；纯逻辑层不 import tkinter，
#: 但可以同源复用常量，避免"两处各写一份尺寸"。
DEFAULT_GEOMETRY = theme.DEFAULT_GEOMETRY
#: 可选尺寸预设（字符串形式，用于配置与设置窗口）
WINDOW_SIZE_CHOICES: tuple[str, ...] = tuple(
    f"{width}x{height}" for width, height in theme.WINDOW_SIZE_PRESETS
)
#: 用户手动拖过窗口、尺寸不属于任何预设时的取值
WINDOW_SIZE_CUSTOM = "custom"
#: 旧版默认尺寸。老用户的 config.json 里存的是自己那次退出时的几何串
#: （``800x600``，通常还带 ``+x+y`` 位置后缀），所以迁移必须按**尺寸**判断，
#: 不能只比较字符串——否则带位置后缀的老配置永远升不到新默认值。
LEGACY_DEFAULT_WIDTH = 800
LEGACY_DEFAULT_HEIGHT = 600
#: 小于这个尺寸就认为"装不下新版界面"（固定高度结果卡片等），一次性升到默认预设；
#: 大于等于它的尺寸是用户自己拉出来的，保持不动。
MIN_USABLE_WIDTH = 960
MIN_USABLE_HEIGHT = 700
LEGACY_DEFAULT_GEOMETRY = f"{LEGACY_DEFAULT_WIDTH}x{LEGACY_DEFAULT_HEIGHT}"

#: Tk 几何串：``1100x800``，可选 ``+20+20`` / ``-5+5`` 位置后缀
_GEOMETRY_RE = re.compile(r"^(?P<w>\d+)x(?P<h>\d+)(?:[+-]\d+[+-]\d+)?$")
#: 同上，但要求**带位置后缀**（用于判断用户是否摆过窗口位置）
_GEOMETRY_WITH_POS_RE = re.compile(r"^\d+x\d+[+-]\d+[+-]\d+$")
#: 从几何串里取出位置后缀
_GEOMETRY_POSITION_RE = re.compile(r"[+-]\d+[+-]\d+$")
#: 拆开位置后缀（``+120-80`` → 120, -80）
_POSITION_PARTS_RE = re.compile(r"([+-]\d+)([+-]\d+)$")
#: 位置可用性判定：窗口至少要在屏幕上露出这么宽 / 这么高，否则视为"跑到屏幕外了"
MIN_VISIBLE_WIDTH = 120
MIN_VISIBLE_HEIGHT = 40


def geometry_has_position(text: object) -> bool:
    """几何串里是否包含窗口位置（``+x+y``）。

    用于决定"要不要居中"：没有位置的（首次运行、或旧配置只存了尺寸）
    摆到屏幕正中；用户自己拖过的位置必须保留。
    """
    return isinstance(text, str) and _GEOMETRY_WITH_POS_RE.match(text.strip()) is not None


def geometry_position(text: object) -> str:
    """取出几何串的位置后缀（``+120+80``）；没有则返回空串。"""
    if not isinstance(text, str):
        return ""
    match = _GEOMETRY_POSITION_RE.search(text.strip())
    return match.group(0) if match else ""


# ---------------------------------------------------------------------------
# 容错读取辅助
# ---------------------------------------------------------------------------
def _as_str(value: object, default: str = "") -> str:
    return value if isinstance(value, str) else default


def _as_int(value: object, default: int, *, minimum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    if minimum is not None and parsed < minimum:
        return default
    return parsed


def _as_bool(value: object, default: bool = False) -> bool:
    return value if isinstance(value, bool) else default


def _as_appid_set(value: object) -> set[int]:
    if not isinstance(value, (list, tuple, set)):
        return set()
    result: set[int] = set()
    for item in value:
        if isinstance(item, bool):
            continue
        if isinstance(item, int):
            result.add(item)
        elif isinstance(item, str) and item.strip().lstrip("-").isdigit():
            result.add(int(item.strip()))
    return result


def parse_geometry(text: str) -> tuple[int, int] | None:
    """解析 Tk 的 ``<宽>x<高>`` 几何串；不合法返回 ``None``。

    只接受纯尺寸（可带 ``+x+y`` 位置后缀），不合法一律交回默认值——
    配置文件是用户可编辑的，不能因为一个手改错的字符串让程序起不来。
    """
    if not isinstance(text, str):
        return None
    match = _GEOMETRY_RE.match(text.strip())
    if match is None:
        return None
    width, height = int(match.group("w")), int(match.group("h"))
    if width <= 0 or height <= 0:
        return None
    return width, height


def size_matches_geometry(
    size: str, geometry: str, screen_width: int, screen_height: int
) -> tuple[bool, bool]:
    """判断"当前窗口几何"是否等于某个预设尺寸。

    返回 ``(是否匹配, 是否属于"屏幕装不下、被压缩过"的情形)``。

    两种情形都算匹配：
    1. 几何正好等于预设（可信匹配）；
    2. 几何等于**该预设被屏幕压缩后**的结果（小屏上必然发生，但可信度低——
       别的尺寸被压缩后也可能长成这样）。

    第 2 条用于显示：没有它，1024×768 的小屏上窗口被压成 680×768，下拉条就会显示
    「自定义」，而用户明明选的是 680×880。第 2 个返回值用于**判定用户是否真的拖过窗口**：
    只有"可信匹配"才敢断言尺寸没被改过。
    """
    preset = parse_geometry(size)
    actual = parse_geometry(geometry)
    if preset is None or actual is None:
        return (False, False)
    if actual == preset:
        return (True, False)
    clamped = parse_geometry(clamp_geometry(size, screen_width, screen_height))
    if clamped is not None and actual == clamped:
        return (True, True)
    return (False, False)


def resolve_window_size(
    size: object,
    geometry: object,
    screen_width: int,
    screen_height: int,
) -> str:
    """决定"窗口大小"这一选项该显示什么。

    优先级：显式选定且与当前窗口一致的预设 → 当前窗口恰好等于某个预设（或其被压缩后的
    结果）→ 自定义。最后一步是对旧配置的兜底：老版本没有 ``window_size`` 字段，
    但窗口尺寸可能正好是某个预设值。
    """
    text = _as_str(size, "")
    geometry_text = _as_str(geometry, DEFAULT_GEOMETRY)
    if text in WINDOW_SIZE_CHOICES:
        matched, _compressed = size_matches_geometry(
            text, geometry_text, screen_width, screen_height
        )
        if matched:
            return text
    for choice in WINDOW_SIZE_CHOICES:
        matched, _compressed = size_matches_geometry(
            choice, geometry_text, screen_width, screen_height
        )
        if matched:
            return choice
    return WINDOW_SIZE_CUSTOM


def geometry_proves_a_manual_resize(
    size: object,
    geometry: object,
    screen_width: int,
    screen_height: int,
) -> bool:
    """当前尺寸能否**断定**用户手动调过窗口。

    仅在"几何既不等于预设、也不等于预设被屏幕压缩后的结果"时返回 True。
    含糊的情况（只匹配压缩后的尺寸）返回 False——小屏上多个尺寸压缩后会长得一样，
    此时宁可保留用户选定的预设，也不要误报成「自定义」。

    顺序上必须先比对预设（含被压缩后的结果）：否则 680×768 在 768 高的屏上会先撞上
    "高度正好等于屏幕"而被误判成手动调整，而它其实正是 680×880 被压下来的样子。
    """
    text = _as_str(size, "")
    candidates = (text,) if text in WINDOW_SIZE_CHOICES else WINDOW_SIZE_CHOICES
    for choice in candidates:
        matched, _compressed = size_matches_geometry(
            choice, _as_str(geometry, DEFAULT_GEOMETRY), screen_width, screen_height
        )
        if matched:
            # 正好等于预设，或等于预设被屏幕压缩后的结果 → 不能断定用户改过尺寸
            return False
    # 与任何预设（含压缩后）都不匹配 → 用户改过尺寸
    return True


def migrate_geometry(text: str) -> str:
    """把旧版留下的过小窗口尺寸一次性升到默认值。

    只动"装不下新版界面"的尺寸（例如旧默认 800×600，通常带 ``+x+y`` 位置后缀），
    用户自己拉大的尺寸原样保留；位置偏移一律丢弃，避免窗口出现在屏幕外。
    """
    parsed = parse_geometry(text)
    if parsed is None:
        return DEFAULT_GEOMETRY
    width, height = parsed
    if width < MIN_USABLE_WIDTH or height < MIN_USABLE_HEIGHT:
        return DEFAULT_GEOMETRY
    return f"{width}x{height}"


def clamp_geometry(text: str, screen_width: int, screen_height: int) -> str:
    """把尺寸限制在屏幕内，并在位置落到屏幕外时丢弃位置。

    场景：用户把窗口拖到副屏后拔掉副屏，或换了更小的显示器——
    存下来的几何串会让窗口"消失在屏幕外"，看起来像打不开。

    **屏幕内**的位置原样保留：用户摆过的窗口下次打开还在原地。
    （早期版本无条件丢弃位置，导致"用户摆过位置"这一信息在启动时就丢了。）
    判定标准是"至少露出标题栏可抓取的一角"，而不是"完全在屏幕内"——
    与 Steam、浏览器等程序一致，允许窗口贴边露出一部分。
    """
    parsed = parse_geometry(text)
    if parsed is None:
        return DEFAULT_GEOMETRY
    width, height = parsed
    screen_width = max(320, int(screen_width or 0) or 320)
    screen_height = max(240, int(screen_height or 0) or 240)
    width = min(width, screen_width)
    height = min(height, screen_height)

    position_match = _GEOMETRY_POSITION_RE.search(text.strip())
    if position_match:
        parts = _POSITION_PARTS_RE.match(position_match.group(0))
        if parts is not None:
            left, top = int(parts.group(1)), int(parts.group(2))
            if _position_is_usable(left, top, width, height, screen_width, screen_height):
                return f"{width}x{height}{left:+d}{top:+d}"
    return f"{width}x{height}"


def _position_is_usable(
    left: int, top: int, width: int, height: int, screen_width: int, screen_height: int
) -> bool:
    """窗口位置是否还能用：宽高各留出至少一个"可抓取"的边距。"""
    if left > screen_width - MIN_VISIBLE_WIDTH or top > screen_height - MIN_VISIBLE_HEIGHT:
        return False
    if left + width < MIN_VISIBLE_WIDTH or top + height < MIN_VISIBLE_HEIGHT:
        return False
    return True


@dataclass
class UiState:
    """界面状态（PRD 6.2 的 ``ui`` 段）。"""

    window_geometry: str = DEFAULT_GEOMETRY
    #: 用户选定的尺寸预设（``800x1100`` / ``1100x800``），手动拖过则为 ``custom``
    window_size: str = DEFAULT_GEOMETRY
    sort_key: str = SORT_NAME
    sort_desc: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "window_geometry": self.window_geometry,
            "window_size": self.window_size,
            "sort_key": self.sort_key,
            "sort_desc": self.sort_desc,
        }

    @classmethod
    def from_dict(cls, data: object) -> UiState:
        if not isinstance(data, dict):
            return cls()
        sort_key = data.get("sort_key")
        raw_geometry = _as_str(data.get("window_geometry"), DEFAULT_GEOMETRY) or DEFAULT_GEOMETRY
        # 几何串**保留位置后缀**：它同时记录用户摆过的位置，并让"要不要居中"可判断
        # （见 geometry_has_position）。早期版本在这里统一剥掉位置，导致用户自己
        # 拖过的窗口下次启动会被重新居中。
        #
        # 但**迁移过尺寸**时不保留位置：旧默认 800×600 几乎总带位置后缀，而新默认
        # 800×1100 高得多，沿用旧位置容易把窗口顶到屏幕上方甚至屏幕外——丢弃位置、
        # 让界面重新居中更稳。尺寸没变（用户自己拉大的）则原样保留位置。
        geometry = migrate_geometry(raw_geometry)
        if geometry_has_position(raw_geometry) and not geometry_has_position(geometry):
            if parse_geometry(geometry) == parse_geometry(raw_geometry):
                geometry = f"{geometry}{geometry_position(raw_geometry)}"
        size = _as_str(data.get("window_size"), "")
        if size not in WINDOW_SIZE_CHOICES:
            # 认不出的取值（含旧配置没有该字段）先落默认预设；
            # 真正的比对需要屏幕尺寸，由界面层的 resolve_window_size 完成。
            size = DEFAULT_GEOMETRY
        return cls(
            window_geometry=geometry,
            window_size=size,
            sort_key=sort_key if sort_key in VALID_SORT_KEYS else SORT_NAME,
            sort_desc=_as_bool(data.get("sort_desc")),
        )


@dataclass
class Config:
    """应用配置；``excluded_appids`` 是抽签池的**唯一事实来源**（PRD D3）。"""

    api_key: str = ""
    last_steam_id: str = ""
    excluded_appids: set[int] = field(default_factory=set)
    last_preset: str = PRESET_ALL
    playtime_threshold_minutes: int = DEFAULT_THRESHOLD_MINUTES
    details_cache_ttl_days: int = DEFAULT_TTL_DAYS
    language: str = DEFAULT_LANGUAGE
    ui: UiState = field(default_factory=UiState)

    @property
    def has_api_key(self) -> bool:
        return bool(self.api_key.strip())

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": SCHEMA_VERSION,
            "api_key": self.api_key,
            "last_steam_id": self.last_steam_id,
            "excluded_appids": sorted(self.excluded_appids),
            "last_preset": self.last_preset,
            "playtime_threshold_minutes": self.playtime_threshold_minutes,
            "details_cache_ttl_days": self.details_cache_ttl_days,
            "language": self.language,
            "ui": self.ui.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> Config:
        preset = data.get("last_preset")
        language = data.get("language")
        return cls(
            api_key=_as_str(data.get("api_key")),
            last_steam_id=_as_str(data.get("last_steam_id")),
            excluded_appids=_as_appid_set(data.get("excluded_appids")),
            last_preset=preset if preset in VALID_PRESETS else PRESET_ALL,
            playtime_threshold_minutes=_as_int(
                data.get("playtime_threshold_minutes"), DEFAULT_THRESHOLD_MINUTES, minimum=1
            ),
            details_cache_ttl_days=_as_int(
                data.get("details_cache_ttl_days"), DEFAULT_TTL_DAYS, minimum=1
            ),
            language=language if language in VALID_LANGUAGES else DEFAULT_LANGUAGE,
            ui=UiState.from_dict(data.get("ui")),
        )


@dataclass
class LoadResult:
    """load() 的结果；``corrupted_backup`` 非空表示发生过损坏重置。"""

    config: Config
    corrupted_backup: Path | None = None

    @property
    def corrupted(self) -> bool:
        return self.corrupted_backup is not None


def default_base_dir() -> Path:
    """``%APPDATA%\\SteamGamePicker``；%APPDATA% 缺失时回退到用户主目录。"""
    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / APP_DIR_NAME
    return Path.home() / f".{APP_DIR_NAME.lower()}"


class ConfigStore:
    """配置文件与缓存目录的统一入口。"""

    def __init__(self, base_dir: str | os.PathLike[str] | None = None) -> None:
        self.base_dir = Path(base_dir) if base_dir is not None else default_base_dir()

    # -- 路径 ---------------------------------------------------------------
    @property
    def config_path(self) -> Path:
        return self.base_dir / "config.json"

    @property
    def cache_dir(self) -> Path:
        return self.base_dir / "cache"

    @property
    def details_dir(self) -> Path:
        return self.cache_dir / "details"

    @property
    def img_dir(self) -> Path:
        return self.cache_dir / "img"

    @property
    def logs_dir(self) -> Path:
        return self.base_dir / "logs"

    def snapshot_path(self, steamid64: str) -> Path:
        return self.cache_dir / f"games_{steamid64}.json"

    def ensure_dirs(self) -> None:
        for path in (self.base_dir, self.cache_dir, self.details_dir, self.img_dir, self.logs_dir):
            path.mkdir(parents=True, exist_ok=True)

    # -- 读写 ---------------------------------------------------------------
    def load(self) -> LoadResult:
        path = self.config_path
        if not path.exists():
            return LoadResult(Config())
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise ValueError("config.json 顶层不是 JSON 对象")
        except (json.JSONDecodeError, ValueError, UnicodeDecodeError, OSError):
            backup = self._backup_corrupt(path)
            return LoadResult(Config(), backup)
        return LoadResult(Config.from_dict(raw))

    def save(self, config: Config) -> None:
        self.base_dir.mkdir(parents=True, exist_ok=True)
        atomic_write_json(self.config_path, config.to_dict())

    # -- 损坏处理 -----------------------------------------------------------
    def _backup_corrupt(self, path: Path) -> Path | None:
        stamp = time.strftime("%Y%m%d-%H%M%S")
        target = self.base_dir / f"config.corrupt-{stamp}.json"
        suffix = 1
        while target.exists():
            target = self.base_dir / f"config.corrupt-{stamp}-{suffix}.json"
            suffix += 1
        try:
            path.replace(target)
        except OSError:
            return None
        self._prune_corrupt_backups()
        return target

    def _prune_corrupt_backups(self) -> None:
        backups = sorted(self.base_dir.glob("config.corrupt-*.json"))
        for stale in backups[:-CORRUPT_BACKUP_KEEP]:
            try:
                stale.unlink()
            except OSError:  # pragma: no cover - 清理失败不影响启动
                pass


def atomic_write_json(path: Path, payload: object) -> None:
    """原子写 JSON：先写同目录临时文件，再 ``os.replace`` 覆盖。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.parent / f".{path.name}.{os.getpid()}.tmp"
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    try:
        with open(tmp, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:  # pragma: no cover
                pass
