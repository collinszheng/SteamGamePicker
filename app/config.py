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
import time
from dataclasses import dataclass, field
from pathlib import Path

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

DEFAULT_GEOMETRY = "800x600"


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


@dataclass
class UiState:
    """界面状态（PRD 6.2 的 ``ui`` 段）。"""

    pool_panel_expanded: bool = False
    window_geometry: str = DEFAULT_GEOMETRY
    sort_key: str = SORT_NAME
    sort_desc: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "pool_panel_expanded": self.pool_panel_expanded,
            "window_geometry": self.window_geometry,
            "sort_key": self.sort_key,
            "sort_desc": self.sort_desc,
        }

    @classmethod
    def from_dict(cls, data: object) -> UiState:
        if not isinstance(data, dict):
            return cls()
        sort_key = data.get("sort_key")
        return cls(
            pool_panel_expanded=_as_bool(data.get("pool_panel_expanded")),
            window_geometry=_as_str(data.get("window_geometry"), DEFAULT_GEOMETRY)
            or DEFAULT_GEOMETRY,
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
