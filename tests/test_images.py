"""T2.6 封面图处理测试（结果区封面渲染）。"""

from __future__ import annotations

import io
from pathlib import Path

from PIL import Image

from app.images import load_photo_image, load_photo_image_from_file

SIZE = (300, 140)


def make_jpeg(width: int = 460, height: int = 215, color: tuple[int, int, int] = (10, 20, 30)) -> bytes:
    image = Image.new("RGB", (width, height), color)
    buffer = io.BytesIO()
    image.save(buffer, "JPEG")
    return buffer.getvalue()


def test_missing_or_broken_data_returns_none(root) -> None:
    assert load_photo_image(None, SIZE) is None
    assert load_photo_image(b"", SIZE) is None
    assert load_photo_image("这不是图片".encode("utf-8"), SIZE) is None


def test_resizes_to_requested_size(root) -> None:
    photo = load_photo_image(make_jpeg(), SIZE)
    assert photo is not None
    assert (photo.width(), photo.height()) == SIZE


def test_accepts_png(root) -> None:
    buffer = io.BytesIO()
    Image.new("RGB", (460, 215), (200, 10, 10)).save(buffer, "PNG")
    photo = load_photo_image(buffer.getvalue(), (240, 112))
    assert photo is not None
    assert (photo.width(), photo.height()) == (240, 112)


def test_load_from_file(root, tmp_path: Path) -> None:
    path = tmp_path / "cover.jpg"
    path.write_bytes(make_jpeg())

    photo = load_photo_image_from_file(path, (240, 112))
    assert photo is not None
    assert photo.width() == 240
    assert load_photo_image_from_file(tmp_path / "缺失.jpg", SIZE) is None
    assert load_photo_image_from_file(None, SIZE) is None
