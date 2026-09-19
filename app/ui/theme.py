"""视觉规范常量（PRD 11.2）与尺寸计算。

界面层唯一允许出现字体 / 颜色字面量的地方；其他 ui 模块一律引用这里。
"""

from __future__ import annotations

from app.errors import LEVEL_ERROR, LEVEL_MUTED, LEVEL_OK, LEVEL_WARN

FONT_FAMILY = "Microsoft YaHei"
FONT_TITLE = (FONT_FAMILY, 20, "bold")
FONT_SECTION = (FONT_FAMILY, 12, "bold")
FONT_BODY = (FONT_FAMILY, 10)
FONT_BODY_BOLD = (FONT_FAMILY, 10, "bold")
FONT_SMALL = (FONT_FAMILY, 9)
FONT_ROLLING = (FONT_FAMILY, 28, "bold")
FONT_ROLLING_BOUNCE = (FONT_FAMILY, 30, "bold")
FONT_GAME_NAME = (FONT_FAMILY, 16, "bold")

COLOR_BG = "#F5F6F8"
COLOR_CARD = "#FFFFFF"
COLOR_TEXT = "#1F2328"
COLOR_MUTED = "#5B6470"
COLOR_PRIMARY = "#1B6AC9"
COLOR_DISABLED = "#B9C3CE"
COLOR_ERROR = "#C0392B"
COLOR_WARN = "#B8860B"
COLOR_OK = "#1B7F3A"
COLOR_ROLLING = "#333333"
COLOR_BORDER = "#D8DEE6"

LEVEL_COLORS = {
    LEVEL_OK: COLOR_OK,
    LEVEL_WARN: COLOR_WARN,
    LEVEL_ERROR: COLOR_ERROR,
    LEVEL_MUTED: COLOR_MUTED,
}

PAD_OUTER = 12
PAD_INNER = 8
PAD_TIGHT = 4

WINDOW_DEFAULT_WIDTH = 800
WINDOW_DEFAULT_HEIGHT = 600
WINDOW_MIN_WIDTH = 640
WINDOW_MIN_HEIGHT = 480
POOL_AUTO_COLLAPSE_HEIGHT = 520

DRAW_BUTTON_WIDTH = 160
DRAW_BUTTON_HEIGHT = 40
BUTTON_MIN_HEIGHT = 30
BUTTON_MIN_WIDTH = 84

HEADER_ASPECT = 215 / 460
HEADER_MAX_WIDTH = 300
HEADER_MIN_WIDTH = 240

CHECK_ON = "☑"
CHECK_OFF = "☐"


def color_for_level(level: str) -> str:
    return LEVEL_COLORS.get(level, COLOR_MUTED)


def header_image_size(window_width: int) -> tuple[int, int]:
    """封面尺寸 = min(300, 可用宽度 × 0.42)，保持 460:215 比例（PRD 2.3）。"""
    width = int(max(0, window_width) * 0.42)
    width = max(HEADER_MIN_WIDTH, min(HEADER_MAX_WIDTH, width))
    height = max(1, round(width * HEADER_ASPECT))
    return width, height
