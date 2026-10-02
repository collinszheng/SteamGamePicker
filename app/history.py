"""抽签记录：保留最近 10 次抽签结果（PRD D14）。

设计取舍：

* **单独一个文件**（``history.json``）而不是塞进 ``config.json``：
  记录是"使用痕迹"，配置是"用户设置"；清空记录不该动设置，损坏的记录也不该
  影响启动；
* 纯逻辑模块，禁止 import tkinter（界面层只拿数据去渲染）；
* 与缓存一样把所有异常都当作"没有记录"，绝不让损坏的数据打断使用；
* 时间沿用 :mod:`app.cache` 的 ISO 格式与显示规则（存本地偏移、显示时换算）。
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from app.cache import display_time, now_local, to_iso
from app.config import ConfigStore, atomic_write_json

SCHEMA_VERSION = 1
#: 保留的抽签条数（用户要求：记录 10 次抽取结果）
MAX_ENTRIES = 10


@dataclass(frozen=True, slots=True)
class PickRecord:
    """一次抽签结果。"""

    appid: int
    name: str
    picked_at: str

    @property
    def display_time(self) -> str:
        """按当前本地时区显示的时间（``09-19 15:04``）。"""
        return display_time(self.picked_at)

    def to_dict(self) -> dict[str, object]:
        return {"appid": self.appid, "name": self.name, "picked_at": self.picked_at}

    @classmethod
    def from_dict(cls, data: object) -> PickRecord | None:
        if not isinstance(data, dict):
            return None
        appid = data.get("appid")
        if isinstance(appid, bool) or not isinstance(appid, (int, float, str)):
            return None
        try:
            parsed_appid = int(appid)
        except (TypeError, ValueError):
            return None
        name = data.get("name")
        picked_at = data.get("picked_at")
        return cls(
            appid=parsed_appid,
            name=str(name) if isinstance(name, str) else "",
            picked_at=str(picked_at) if isinstance(picked_at, str) else "",
        )


class PickHistory:
    """``%APPDATA%\\SteamGamePicker\\history.json`` 的读写入口。"""

    def __init__(self, store: ConfigStore) -> None:
        self.store = store
        self.entries: list[PickRecord] = []

    # -- 路径 ---------------------------------------------------------------
    @property
    def path(self) -> Path:
        return self.store.base_dir / "history.json"

    # -- 读写 ---------------------------------------------------------------
    def load(self) -> list[PickRecord]:
        """读盘；文件缺失、损坏或结构不认识时一律当作"没有记录"。"""
        self.entries = self._read()
        return list(self.entries)

    def _read(self) -> list[PickRecord]:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            return []
        if not isinstance(raw, dict):
            return []
        items = raw.get("entries")
        if not isinstance(items, list):
            return []
        records: list[PickRecord] = []
        for item in items:
            record = PickRecord.from_dict(item)
            if record is not None:
                records.append(record)
            if len(records) >= MAX_ENTRIES:
                break
        return records

    def save(self) -> None:
        payload = {
            "schema_version": SCHEMA_VERSION,
            "entries": [record.to_dict() for record in self.entries[:MAX_ENTRIES]],
        }
        atomic_write_json(self.path, payload)

    # -- 记录 ---------------------------------------------------------------
    def record(self, appid: int, name: str, *, picked_at: str | None = None) -> PickRecord:
        """把一次抽签插到最前，只保留最近 ``MAX_ENTRIES`` 条，并立即写盘。

        写盘失败（磁盘异常）只是丢记录，不能影响抽签本身，因此吞掉 OSError。
        """
        entry = PickRecord(
            appid=int(appid),
            name=str(name),
            picked_at=picked_at or to_iso(now_local()),
        )
        self.entries = [entry, *self.entries][:MAX_ENTRIES]
        try:
            self.save()
        except OSError:  # pragma: no cover - 磁盘异常不应打断抽签
            pass
        return entry

    def clear(self) -> None:
        """清空记录（界面上的「清空记录」）。"""
        self.entries = []
        try:
            if self.path.exists():
                os.remove(self.path)
        except OSError:  # pragma: no cover - 删除失败时保留文件即可
            try:
                self.save()
            except OSError:
                pass

    def __len__(self) -> int:
        return len(self.entries)
