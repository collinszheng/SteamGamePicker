"""封面图处理：把下载到的字节变成 Tk 能显示的图片（PRD 5.5 / T2.6）。

失败一律返回 ``None``，由界面显示占位（不阻塞抽签主流程）。
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any


def _resampling() -> Any:
    from PIL import Image

    return getattr(Image, "Resampling", Image).LANCZOS


def load_photo_image(data: bytes | None, size: tuple[int, int]) -> Any | None:
    """字节 → ``ImageTk.PhotoImage``；数据缺失 / 损坏 / 缺 Pillow 时返回 ``None``。"""
    if not data:
        return None
    try:
        from PIL import Image, ImageTk
    except ImportError:  # pragma: no cover - Pillow 是运行依赖
        return None
    try:
        with Image.open(io.BytesIO(data)) as source:
            image = source.convert("RGB").resize(size, _resampling())
        return ImageTk.PhotoImage(image)
    except Exception:
        return None


def load_photo_image_from_file(path: Path | None, size: tuple[int, int]) -> Any | None:
    if path is None:
        return None
    try:
        return load_photo_image(path.read_bytes(), size)
    except OSError:
        return None
