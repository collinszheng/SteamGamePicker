"""本地缓存：库快照、详情缓存、封面图缓存（PRD 6.3 / 6.5）。

要求（对应 AC-10 / AC-12 / AC-30）：
* 快照损坏或结构不认识 → 视为无缓存，绝不打断使用；
* 详情有 TTL（默认 7 天），过期即失效；
* 封面图与详情同生命周期；
* 缓存总量超上限时，按修改时间从旧到新清理，但永远保留最新的库快照。
"""

from __future__ import annotations

import datetime as dt
import json
import os
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from app.config import ConfigStore, atomic_write_json
from app.models import Game, GameDetails

SNAPSHOT_SCHEMA = 1
DETAIL_SCHEMA = 1
DEFAULT_MAX_CACHE_BYTES = 200 * 1024 * 1024


def now_local() -> dt.datetime:
    return dt.datetime.now().astimezone()


def to_iso(moment: dt.datetime) -> str:
    return moment.astimezone().isoformat(timespec="seconds")


def parse_iso(text: object) -> dt.datetime | None:
    if not isinstance(text, str) or not text:
        return None
    try:
        parsed = dt.datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=now_local().tzinfo)
    return parsed


def display_time(iso_text: str | None) -> str:
    """把 ISO 时间显示为 ``09-19 15:04``；无法解析时返回原文本。"""
    moment = parse_iso(iso_text)
    if moment is None:
        return iso_text or ""
    return moment.strftime("%m-%d %H:%M")


@dataclass(frozen=True, slots=True)
class Snapshot:
    """游戏库快照（用于秒开与离线抽签）。"""

    steamid64: str
    updated_at: str
    games: tuple[Game, ...]

    def __len__(self) -> int:
        return len(self.games)

    @property
    def updated_display(self) -> str:
        return display_time(self.updated_at)


class GameCache:
    def __init__(
        self,
        store: ConfigStore,
        *,
        ttl_days: int = 7,
        max_bytes: int = DEFAULT_MAX_CACHE_BYTES,
        now: Callable[[], dt.datetime] | None = None,
    ) -> None:
        self.store = store
        self.ttl_days = max(1, int(ttl_days))
        self.max_bytes = max(0, int(max_bytes))
        self._now = now or now_local

    # ------------------------------------------------------------------ 快照
    def save_snapshot(
        self, steamid64: str, games: Sequence[Game], *, moment: dt.datetime | None = None
    ) -> Snapshot:
        stamp = to_iso(moment or self._now())
        payload = {
            "schema_version": SNAPSHOT_SCHEMA,
            "steamid64": steamid64,
            "updated_at": stamp,
            "games": [g.to_dict() for g in games],
        }
        atomic_write_json(self.store.snapshot_path(steamid64), payload)
        return Snapshot(steamid64, stamp, tuple(games))

    def load_snapshot(self, steamid64: str) -> Snapshot | None:
        path = self.store.snapshot_path(steamid64)
        if not path.exists():
            return None
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError, OSError):
            return None
        if not isinstance(raw, dict) or raw.get("schema_version") != SNAPSHOT_SCHEMA:
            return None
        games_raw = raw.get("games")
        if not isinstance(games_raw, list):
            return None
        games: list[Game] = []
        for item in games_raw:
            if not isinstance(item, dict):
                continue
            game = Game.from_dict(item)
            if game.appid > 0:
                games.append(game)
        updated_at = raw.get("updated_at")
        return Snapshot(
            steamid64=str(raw.get("steamid64") or steamid64),
            updated_at=updated_at if isinstance(updated_at, str) else "",
            games=tuple(games),
        )

    def newest_snapshot(self) -> Snapshot | None:
        """取最近更新的快照（启动时用于"上次的库"秒开）。"""
        candidates = sorted(
            self.store.cache_dir.glob("games_*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        for path in candidates:
            steamid64 = path.stem.removeprefix("games_")
            snapshot = self.load_snapshot(steamid64)
            if snapshot is not None:
                return snapshot
        return None

    # ------------------------------------------------------------------ 详情
    def _detail_path(self, appid: int) -> Path:
        return self.store.details_dir / f"{appid}.json"

    def put_detail(self, details: GameDetails, *, moment: dt.datetime | None = None) -> None:
        payload = details.to_dict()
        payload["schema_version"] = DETAIL_SCHEMA
        payload["cached_at"] = to_iso(moment or self._now())
        atomic_write_json(self._detail_path(details.appid), payload)

    def get_detail(self, appid: int) -> GameDetails | None:
        path = self._detail_path(appid)
        if not path.exists():
            return None
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError, OSError):
            return None
        if not isinstance(raw, dict) or raw.get("schema_version") != DETAIL_SCHEMA:
            return None
        cached_at = parse_iso(raw.get("cached_at"))
        if cached_at is None or self._expired(cached_at):
            self._remove(path)
            self._remove(self._image_path(appid))
            return None
        return GameDetails.from_dict(raw)

    def _expired(self, cached_at: dt.datetime) -> bool:
        return self._now() - cached_at > dt.timedelta(days=self.ttl_days)

    # ------------------------------------------------------------------ 图片
    def _image_path(self, appid: int) -> Path:
        return self.store.img_dir / f"{appid}.jpg"

    def put_image(self, appid: int, data: bytes) -> Path:
        path = self._image_path(appid)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.parent / f".{path.name}.{os.getpid()}.tmp"
        with open(tmp, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
        return path

    def get_image_path(self, appid: int) -> Path | None:
        path = self._image_path(appid)
        if not path.exists():
            return None
        try:
            modified = dt.datetime.fromtimestamp(path.stat().st_mtime).astimezone()
        except OSError:  # pragma: no cover - 文件刚被删除
            return None
        if self._expired(modified):
            self._remove(path)
            return None
        return path

    # -------------------------------------------------------------- 容量管理
    def total_bytes(self) -> int:
        total = 0
        if not self.store.cache_dir.exists():
            return 0
        for path in self.store.cache_dir.rglob("*"):
            if path.is_file():
                try:
                    total += path.stat().st_size
                except OSError:  # pragma: no cover
                    continue
        return total

    def prune(self) -> int:
        """超限时按修改时间从旧到新清理，返回删除的文件数（PRD 6.4）。

        最新库快照同时也是最新的文件，因此天然排在删除顺序的最后；
        只有在上限小到连快照都装不下时它才会被删掉——上限是硬保证。
        """
        if not self.store.cache_dir.exists():
            return 0
        files = [p for p in self.store.cache_dir.rglob("*") if p.is_file()]
        total = sum(_safe_size(p) for p in files)
        if total <= self.max_bytes:
            return 0
        removed = 0
        for path in sorted(files, key=_safe_mtime):
            if total <= self.max_bytes:
                break
            size = _safe_size(path)
            if self._remove(path):
                total -= size
                removed += 1
        return removed

    def clear(self) -> None:
        for path in list(self.store.cache_dir.rglob("*")) if self.store.cache_dir.exists() else []:
            if path.is_file():
                self._remove(path)

    @staticmethod
    def _remove(path: Path) -> bool:
        try:
            path.unlink()
            return True
        except OSError:
            return False


def _safe_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:  # pragma: no cover
        return 0


def _safe_mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:  # pragma: no cover
        return 0.0
