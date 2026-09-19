"""生成应用图标 assets/app.ico（Steam 官方风格 + 骰子图案）。

设计（PRD D13 / AC-55）
--------------------------------------------------------------------------
* **徽章**：圆角方形，填充 Steam 页面底色渐变
  （``#2a475e`` → ``#1b2838`` → ``#101720``，左上到右下），
  外沿一圈 Steam 蓝 ``#66c0f4`` 低透明度描边 —— 深色任务栏上靠描边立住，
  浅色背景上靠深色底立住。
* **主体**：白色骰子（略带倾斜），点数为深蓝 ``#16202d``。
  骰子 = 「随机抽一款」，与应用的抽签语义一致。
* **光学尺寸**：16 / 24 / 32 像素**单独出图**并简化（点数更少、点更大、
  徽章占比更高）。直接缩小 256 的图会让点数糊成一团，这是 Windows 图标
  的通行做法，Pillow 的 ICO 写入支持 ``append_images`` 按尺寸提供不同图。
* **不使用任何文字或字体**：旧图标是蓝色底 + 白色「抽」字，应用更名后
  中文单字不再合适（由 ``tests/test_icon.py`` 强制这一约束）。

用法::

    python tools/make_icon.py                    # 写 assets/app.ico 与预览图
    python tools/make_icon.py --variants 文件.png  # 只出候选对比图（选型用）
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:  # 让 --variants 也能直接用仓库内的正式色板
    sys.path.insert(0, str(ROOT))

from app.ui.theme import (  # noqa: E402  （必须在 sys.path 调整之后导入）
    COLOR_ACCENT,
    COLOR_BG,
    COLOR_OK,
    COLOR_PANEL,
)

TARGET = ROOT / "assets" / "app.ico"
PREVIEW = ROOT / "docs" / "evidence" / "icon-preview.png"

ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)
SUPERSAMPLE = 4  # 每个尺寸先按 4 倍画再降采样，边缘才干净

# 徽章渐变（取自 Steam 页面：面板蓝 → 页面底色 → 近黑）
BADGE_STOPS = ((0.00, "#3a6d94"), (0.46, "#1f3f5b"), (1.00, "#0e141b"))
FACE_STOPS = ((0.00, "#f8fbfe"), (1.00, "#c2d3e2"))  # 骰子正面
PIP_COLOR = "#16202d"
PIP_COLOR_OK = COLOR_OK  # Steam 亮绿（应用中签色），用于中心点变体


# ---------------------------------------------------------------------------
# 基础绘制工具
# ---------------------------------------------------------------------------
def _rgb(color: str) -> tuple[int, int, int]:
    text = color.lstrip("#")
    return int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16)


def _lerp(first: tuple[int, int, int], second: tuple[int, int, int], t: float):
    return tuple(round(a + (b - a) * t) for a, b in zip(first, second))


def _gradient(size: int, stops, angle: str = "diagonal") -> Image.Image:
    """生成渐变底图；angle 支持 ``diagonal``（左上→右下）与 ``vertical``。"""
    base = 128  # 先在 128 上逐像素算，再放大，避免 1024² 的纯 Python 循环
    image = Image.new("RGB", (base, base))
    pixels = image.load()
    for y in range(base):
        for x in range(base):
            if angle == "vertical":
                t = y / (base - 1)
            else:
                t = (x + y) / (2 * (base - 1))
            color = _rgb(stops[-1][1])
            for index in range(len(stops) - 1):
                left, right = stops[index], stops[index + 1]
                if left[0] <= t <= right[0]:
                    local = (t - left[0]) / (right[0] - left[0]) if right[0] > left[0] else 0.0
                    color = _lerp(_rgb(left[1]), _rgb(right[1]), local)
                    break
                if t < left[0]:
                    color = _rgb(left[1])
                    break
            pixels[x, y] = color
    return image.resize((size, size), Image.Resampling.BICUBIC).convert("RGBA")


def _rounded_mask(size: int, box: tuple[int, int, int, int], radius: int) -> Image.Image:
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle(box, radius=radius, fill=255)
    return mask


def _paste_masked(canvas: Image.Image, fill: Image.Image, mask: Image.Image) -> None:
    canvas.paste(fill, (0, 0), mask)


# ---------------------------------------------------------------------------
# 图标本体
# ---------------------------------------------------------------------------
class Style:
    """一套图标风格参数（供选型对比使用）。"""

    def __init__(
        self,
        *,
        tilt: float = -12.0,
        face=("white", FACE_STOPS),
        pips: str = PIP_COLOR,
        center_pip: str | None = None,
        glow: bool = True,
    ) -> None:
        self.tilt = tilt
        self.face = face
        self.pips = pips
        self.center_pip = center_pip
        self.glow = glow


STYLE_DEFAULT = Style()
STYLE_GREEN = Style(center_pip=PIP_COLOR_OK)
STYLE_FLAT = Style(tilt=0.0)
STYLE_BLUE_PIPS = Style(pips=COLOR_PANEL, center_pip=None)
STYLE_BLUE_FACE = Style(face=("blue", ((0.0, "#8fd4ff"), (1.0, "#4a9ed6"))), pips=PIP_COLOR)


def _pip_count(size: int, style: Style) -> int:
    """按尺寸决定点数：大尺寸五点（骰子最好认），小尺寸退化为对角三点。

    16 像素下五点会糊成一团、单点又认不出是骰子，三点是实测最稳的折中
    （见 ``--tiny`` 研究图）。
    """
    return 5 if size >= 48 else 3


def render(size: int, style: Style = STYLE_DEFAULT, *, pips: int | None = None) -> Image.Image:
    """渲染单个尺寸的图标（内部按 SUPERSAMPLE 倍超采样）。"""
    scale = SUPERSAMPLE if size >= 24 else 8  # 极小尺寸多超采样一点
    big = size * scale
    canvas = Image.new("RGBA", (big, big), (0, 0, 0, 0))

    # --- 徽章 -------------------------------------------------------------
    margin = round(big * 0.035)
    box = (margin, margin, big - margin - 1, big - margin - 1)
    radius = round((big - 2 * margin) * 0.22)
    badge_mask = _rounded_mask(big, box, radius)
    _paste_masked(canvas, _gradient(big, BADGE_STOPS, "diagonal"), badge_mask)

    # 顶部内高光：让徽章有"玻璃面板"的层次
    gloss = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    ImageDraw.Draw(gloss).rounded_rectangle(
        (margin + round(big * 0.012),) * 2
        + (big - margin - round(big * 0.012) - 1, big - margin - round(big * 0.012) - 1),
        radius=max(1, radius - round(big * 0.012)),
        outline=(255, 255, 255, 34),
        width=max(1, round(big * 0.006)),
    )
    canvas.alpha_composite(Image.composite(gloss, Image.new("RGBA", (big, big)), badge_mask))

    # Steam 蓝描边（低透明度，深/浅背景都能立住）
    # 描边往内缩一点，否则一半线宽落在遮罩外，边缘会显得缺一块
    rim = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    rim_inset = max(1, round(big * 0.008))
    ImageDraw.Draw(rim).rounded_rectangle(
        (box[0] + rim_inset, box[1] + rim_inset, box[2] - rim_inset, box[3] - rim_inset),
        radius=radius,
        outline=_rgb(COLOR_ACCENT) + (140,),
        width=max(1, round(big * 0.013)),
    )
    canvas.alpha_composite(Image.composite(rim, Image.new("RGBA", (big, big)), badge_mask))

    # --- 骰子 -------------------------------------------------------------
    die_side = round(big * (0.60 if size < 24 else 0.52 if size < 48 else 0.485))
    die = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    die_box = (
        (big - die_side) // 2,
        (big - die_side) // 2,
        (big - die_side) // 2 + die_side - 1,
        (big - die_side) // 2 + die_side - 1,
    )
    die_radius = round(die_side * 0.20)
    die_mask = _rounded_mask(big, die_box, die_radius)
    face_stops = style.face[1]
    _paste_masked(die, _gradient(big, face_stops, "vertical"), die_mask)

    # 骰子描边：与徽章拉开层次
    outline = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    ImageDraw.Draw(outline).rounded_rectangle(
        die_box,
        radius=die_radius,
        outline=(13, 20, 28, 90),
        width=max(1, round(die_side * 0.035)),
    )
    die.alpha_composite(Image.composite(outline, Image.new("RGBA", (big, big)), die_mask))

    # 点数：五点用「四点 + 中心」，小尺寸退化为对角三点 / 单点
    count = _pip_count(size, style) if pips is None else pips
    offset = die_side * (0.265 if count == 5 else 0.245)
    radius_pip = die_side * (0.105 if count == 5 else 0.125 if count == 3 else 0.155)
    center = big / 2
    draw = ImageDraw.Draw(die)
    spots: list[tuple[float, float, str]] = []
    if count == 5:
        for dx, dy in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
            spots.append((center + dx * offset, center + dy * offset, style.pips))
        spots.append((center, center, style.center_pip or style.pips))
    elif count == 3:
        spots = [
            (center - offset, center - offset, style.pips),
            (center, center, style.center_pip or style.pips),
            (center + offset, center + offset, style.pips),
        ]
    else:
        spots = [(center, center, style.center_pip or style.pips)]
    for cx, cy, color in spots:
        draw.ellipse(
            (cx - radius_pip, cy - radius_pip, cx + radius_pip, cy + radius_pip),
            fill=_rgb(color) + (255,),
        )

    if style.tilt:
        die = die.rotate(style.tilt, resample=Image.Resampling.BICUBIC, center=(center, center))

    # 骰子投影：让骰子从徽章上"浮"起来
    shadow = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    shadow.paste((6, 12, 20, 130), (0, 0), die.split()[3])
    shadow = shadow.filter(ImageFilter.GaussianBlur(big * 0.022))
    canvas.alpha_composite(shadow, (0, round(big * 0.018)))

    if style.glow:
        glow = Image.new("RGBA", (big, big), (0, 0, 0, 0))
        glow_draw = ImageDraw.Draw(glow)
        steps = 26
        for index in range(steps):
            ratio = index / (steps - 1)
            radius_glow = big * (0.30 + 0.16 * ratio)
            alpha = round(34 * (1 - ratio))
            glow_draw.ellipse(
                (
                    center - radius_glow,
                    center - radius_glow,
                    center + radius_glow,
                    center + radius_glow,
                ),
                fill=_rgb(COLOR_ACCENT) + (alpha,),
            )
        canvas.alpha_composite(glow.filter(ImageFilter.GaussianBlur(big * 0.05)))

    canvas.alpha_composite(die)
    return canvas.resize((size, size), Image.Resampling.LANCZOS)


def build_icon(target: Path = TARGET, style: Style = STYLE_DEFAULT) -> Path:
    """写出多尺寸 ICO：小尺寸单独渲染（光学尺寸），不靠缩小大图。"""
    frames = {size: render(size, style) for size in ICO_SIZES}
    master = frames[256]
    target.parent.mkdir(parents=True, exist_ok=True)
    master.save(
        target,
        format="ICO",
        sizes=[(size, size) for size in ICO_SIZES],
        append_images=[frames[size] for size in ICO_SIZES if size != 256],
    )
    return target


def load_frames(path: Path = TARGET) -> dict[int, Image.Image]:
    """把 ICO 里的每一帧读回来（预览必须展示"Windows 真正会画的那张图"）。"""
    with Image.open(path) as handle:
        sizes = sorted(handle.info.get("sizes", []))
        frames = {}
        for size, _ in sizes:
            handle.size = (size, size)
            handle.load()
            frames[size] = handle.convert("RGBA").copy()
    return frames


# ---------------------------------------------------------------------------
# 预览图
# ---------------------------------------------------------------------------
def _label(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str) -> None:
    draw.text(xy, text, fill=_rgb("#c6d4df") + (255,), font=_preview_font())


_FONT = None


def _preview_font():
    global _FONT
    if _FONT is None:
        from PIL import ImageFont

        for candidate in (r"C:\Windows\Fonts\segoeui.ttf", r"C:\Windows\Fonts\arial.ttf"):
            if Path(candidate).exists():
                _FONT = ImageFont.truetype(candidate, 15)
                break
        else:
            _FONT = ImageFont.load_default()
    return _FONT


def _place(
    sheet: Image.Image, image: Image.Image, x: int, y: int, *, zoom: int = 1, center_y: int | None = None
) -> int:
    if zoom > 1:
        image = image.resize(
            (image.width * zoom, image.height * zoom), Image.Resampling.NEAREST
        )
    if center_y is not None:
        y = center_y - image.height // 2
    sheet.alpha_composite(image, (x, y))
    return x + image.width


def build_preview(path: Path = PREVIEW, icon: Path = TARGET) -> Path:
    """把 ICO 里的真实帧铺在一张图上：深色行 / 浅色行 / 放大检查行。"""
    frames = load_frames(icon)
    width, height = 1180, 660
    sheet = Image.new("RGBA", (width, height), _rgb("#0f151c") + (255,))
    draw = ImageDraw.Draw(sheet)

    # 深色背景行（Steam 页面底色）
    draw.rectangle((0, 0, width, 300), fill=_rgb("#1b2838") + (255,))
    _label(draw, (24, 14), "on Steam dark  #1b2838   (actual pixels)")
    x = 24
    for size in (256, 128, 64, 48, 32, 24, 16):
        x = _place(sheet, frames[size], x + 18, 0, center_y=165) + 0
    # 浅色背景行
    draw.rectangle((0, 300, width, 470), fill=_rgb("#eceff1") + (255,))
    _label(draw, (24, 312), "on light  #eceff1   (actual pixels)")
    x = 24
    for size in (128, 64, 48, 32, 24, 16):
        x = _place(sheet, frames[size], x + 18, 0, center_y=398) + 0
    # 放大检查行
    draw.rectangle((0, 470, width, height), fill=_rgb("#0f151c") + (255,))
    _label(draw, (24, 482), "zoomed to inspect pixels")
    x = 24
    for size, zoom in ((16, 8), (24, 6), (32, 5), (48, 4)):
        x = _place(sheet, frames[size], x + 24, 0, zoom=zoom, center_y=580) + 0

    path.parent.mkdir(parents=True, exist_ok=True)
    sheet.convert("RGB").save(path, format="PNG")
    return path


def build_choices(path: Path) -> Path:
    """候选方案对比（供确认）：推荐方案 A 与两个备选 B / E。"""
    choices = [
        ("A  recommended: white die, navy pips", STYLE_DEFAULT),
        ("B  alternative: green centre pip", STYLE_GREEN),
        ("C  alternative: Steam blue die", STYLE_BLUE_FACE),
    ]
    cell_w, cell_h = 420, 380
    width = 40 + cell_w * len(choices)
    height = 420
    sheet = Image.new("RGBA", (width, height), _rgb("#1b2838") + (255,))
    draw = ImageDraw.Draw(sheet)
    for column, (name, style) in enumerate(choices):
        x = 20 + column * cell_w
        _label(draw, (x + 20, 28), name)
        _place(sheet, render(256, style), x + 20, 70)
        _place(sheet, render(128, style), x + 300, 70)
        _place(sheet, render(64, style), x + 300, 220)
        _place(sheet, render(48, style), x + 300, 300)
        _place(sheet, render(32, style), x + 360, 300)
    path.parent.mkdir(parents=True, exist_ok=True)
    sheet.convert("RGB").save(path, format="PNG")
    return path


def build_variants(path: Path) -> Path:
    """候选风格对比图：每个候选一行，左侧 256 原尺寸，右侧依次缩小到 16px。"""
    styles = [
        ("A  tilt / navy pips", STYLE_DEFAULT, None),
        ("B  tilt / green center pip", STYLE_GREEN, None),
        ("C  no tilt / navy pips", STYLE_FLAT, None),
        ("D  tilt / blue pips", STYLE_BLUE_PIPS, None),
        ("E  tilt / blue die", STYLE_BLUE_FACE, None),
        ("F  tilt / 3 pips (forced)", STYLE_DEFAULT, 3),
        ("G  tilt / 1 pip (forced)", STYLE_DEFAULT, 1),
        ("H  tilt / green die", Style(face=("green", ((0.0, "#cbe86b"), (1.0, "#8fbf1e")))), None),
    ]
    slots = ((256, 280), (128, 150), (64, 80), (48, 80), (32, 80), (24, 80), (16, 80))
    row_h = 320
    columns = 2
    rows = -(-len(styles) // columns)
    width = 32 + columns * (24 + sum(slot[1] for slot in slots))
    height = 40 + rows * row_h
    sheet = Image.new("RGBA", (width, height), _rgb("#1b2838") + (255,))
    draw = ImageDraw.Draw(sheet)
    for index, (name, style, pips) in enumerate(styles):
        column, row = divmod(index, rows)
        x = 24 + column * (24 + sum(slot[1] for slot in slots))
        center_y = 40 + row * row_h + row_h // 2
        _label(draw, (x, center_y - row_h // 2 + 8), name)
        for size, slot in slots:
            x = _place(sheet, render(size, style, pips=pips), x + 8, 0, center_y=center_y) + 8
    path.parent.mkdir(parents=True, exist_ok=True)
    sheet.convert("RGB").save(path, format="PNG")
    return path


def build_tiny_study(path: Path) -> Path:
    """小尺寸点数研究：16 / 24 / 32 像素下 1 / 3 / 5 点的可辨识度（放大 8 倍看）。"""
    sizes = (16, 24, 32)
    counts = (1, 3, 5)
    zooms = {16: 10, 24: 8, 32: 6}
    cell_w, cell_h = 210, 380
    width = 40 + cell_w * len(counts)
    height = 70 + cell_h * len(sizes)
    sheet = Image.new("RGBA", (width, height), _rgb("#1b2838") + (255,))
    draw = ImageDraw.Draw(sheet)
    for column, count in enumerate(counts):
        _label(draw, (24 + column * cell_w, 26), f"{count} pip(s) at tiny sizes")
    for row, size in enumerate(sizes):
        for column, count in enumerate(counts):
            image = render(size, STYLE_DEFAULT, pips=count)
            zoom = zooms[size]
            top = 70 + row * cell_h
            _place(sheet, image, 24 + column * cell_w, top + 30)
            _place(sheet, image, 24 + column * cell_w, top + 30 + size * zoom + 26, zoom=zoom)
            _label(draw, (24 + column * cell_w + size + 14, top + 30 + size // 2 - 8), f"{size}px")
    path.parent.mkdir(parents=True, exist_ok=True)
    sheet.convert("RGB").save(path, format="PNG")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="生成 Steam 风格骰子图标")
    parser.add_argument("--variants", type=Path, help="只输出候选风格对比图到指定路径")
    parser.add_argument("--tiny", type=Path, help="输出小尺寸点数研究图到指定路径")
    parser.add_argument("--choices", type=Path, help="输出候选方案对比图到指定路径")
    parser.add_argument("--png", type=Path, help="把单个尺寸另存为 PNG（1:1 检查用）")
    parser.add_argument("--size", type=int, default=256, help="配合 --png 使用，默认 256")
    args = parser.parse_args(argv)

    if args.variants:
        path = build_variants(args.variants)
        print(f"候选对比图：{path}")
        return 0

    if args.tiny:
        path = build_tiny_study(args.tiny)
        print(f"小尺寸研究图：{path}")
        return 0

    if args.choices:
        path = build_choices(args.choices)
        print(f"候选方案对比图：{path}")
        return 0

    if args.png:
        args.png.parent.mkdir(parents=True, exist_ok=True)
        render(args.size).save(args.png, format="PNG")
        print(f"单帧：{args.png}（{args.size}px）")
        return 0

    icon = build_icon()
    preview = build_preview()
    print(f"图标已生成：{icon}（{icon.stat().st_size} 字节）")
    print(f"预览图已生成：{preview}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
