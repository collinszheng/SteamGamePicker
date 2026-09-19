"""生成应用图标 assets/app.ico（蓝色圆角底 + 白色「抽」字）。

用法：python tools/make_icon.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "assets" / "app.ico"
SIZE = 256
FONT_CANDIDATES = (
    r"C:\Windows\Fonts\msyhbd.ttc",
    r"C:\Windows\Fonts\msyh.ttc",
    r"C:\Windows\Fonts\simhei.ttf",
)


def load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for candidate in FONT_CANDIDATES:
        if Path(candidate).exists():
            try:
                return ImageFont.truetype(candidate, size)
            except OSError:  # pragma: no cover
                continue
    return ImageFont.load_default()  # pragma: no cover


def build() -> Path:
    image = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((8, 8, SIZE - 8, SIZE - 8), radius=52, fill=(27, 106, 201, 255))
    draw.rounded_rectangle((8, 8, SIZE - 8, SIZE - 8), radius=52, outline=(255, 255, 255, 60), width=4)

    font = load_font(150)
    text = "抽"
    box = draw.textbbox((0, 0), text, font=font)
    draw.text(
        ((SIZE - (box[2] - box[0])) / 2 - box[0], (SIZE - (box[3] - box[1])) / 2 - box[1]),
        text,
        font=font,
        fill=(255, 255, 255, 255),
    )

    TARGET.parent.mkdir(parents=True, exist_ok=True)
    image.save(
        TARGET,
        format="ICO",
        sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    return TARGET


if __name__ == "__main__":
    path = build()
    print(f"图标已生成：{path}（{path.stat().st_size} 字节）")
    sys.exit(0)
