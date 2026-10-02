"""Steam 官方深色风格的视觉规范（PRD 11.2，v1.5 改版）。

配色取 Steam 官方界面（商店 / 社区）的基础色板：

    #171a21  顶栏（最深）
    #1b2838  页面底色
    #2a475e  面板 / 次级按钮
    #66c0f4  Steam 蓝（强调色：标题、链接、高亮）
    #c7d5e0  正文亮色

辅以 Steam 商店的按钮配色：主行动按钮绿 #4c6b22 / 悬停 #75b022 / 文字 #d2e885，
中签高亮用 Steam 亮绿 #a4d007。

实现要点：Windows 原生 ttk 主题（vista）不允许自定义背景色，因此统一切换到
``clam`` 主题后再逐项配置，才能得到 Steam 那种深蓝灰底 + 蓝绿按钮的观感。

所有前景/背景组合在 ``tests/test_ui_theme.py`` 里按 WCAG AA（对比度 ≥ 4.5:1）
自动校验，避免"看起来还行但读不清"。
"""

from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

from app.errors import LEVEL_ERROR, LEVEL_MUTED, LEVEL_OK, LEVEL_WARN

# ---------------------------------------------------------------------------
# Steam 官方色板
# ---------------------------------------------------------------------------
COLOR_HEADER = "#171a21"  # 顶栏
COLOR_BG = "#1b2838"  # 页面底色
COLOR_PANEL = "#2a475e"  # 面板 / 次级按钮
COLOR_ACCENT = "#66c0f4"  # Steam 蓝：标题、链接、高亮
COLOR_TEXT = "#c6d4df"  # 正文
COLOR_TEXT_STRONG = "#ffffff"
COLOR_MUTED = "#8f98a0"  # 次要文字

COLOR_CARD = "#16202d"  # 卡片底
COLOR_CARD_ALT = "#1a2634"  # 列表斑马纹
COLOR_BORDER = "#2a3f5a"  # 卡片描边
COLOR_SELECTION = "#2a475e"  # 列表选中
COLOR_INPUT_BG = "#2a3f5a"  # 输入框底色

COLOR_BUTTON = "#2a475e"  # 次级按钮
COLOR_BUTTON_HOVER = "#3d6a8f"
COLOR_BUTTON_DISABLED = "#1e2c3c"
COLOR_BUTTON_TEXT = "#ffffff"

COLOR_CTA = "#4c6b22"  # 主行动按钮（Steam 绿）
COLOR_CTA_HOVER = "#75b022"
COLOR_CTA_TEXT = "#d2e885"
COLOR_CTA_DISABLED = "#2a3f5a"
COLOR_CTA_TEXT_DISABLED = "#6f7f8c"

#: 状态行 / 结果颜色
COLOR_OK = "#a4d007"  # Steam 亮绿：中签结果、成功提示
COLOR_WARN = "#e2b33c"
COLOR_ERROR = "#ff6b6b"
COLOR_ROLLING = "#c6d4df"  # 滚动中的游戏名
COLOR_WIN = COLOR_OK

# 兼容旧命名
COLOR_PRIMARY = COLOR_ACCENT
COLOR_DISABLED = COLOR_BUTTON_DISABLED

LEVEL_COLORS = {
    LEVEL_OK: COLOR_OK,
    LEVEL_WARN: COLOR_WARN,
    LEVEL_ERROR: COLOR_ERROR,
    LEVEL_MUTED: COLOR_MUTED,
}

# ---------------------------------------------------------------------------
# 字体：Steam 使用自有的 Motiva Sans（不可分发），改用系统最接近的中文界面字体
# ---------------------------------------------------------------------------
FONT_FAMILY_CANDIDATES: tuple[str, ...] = (
    "Microsoft YaHei UI",
    "Microsoft YaHei",
    "Segoe UI",
    "Arial",
)
FONT_FAMILY = FONT_FAMILY_CANDIDATES[0]

FONT_TITLE = (FONT_FAMILY, 20, "bold")
FONT_SECTION = (FONT_FAMILY, 12, "bold")
FONT_BODY = (FONT_FAMILY, 10)
FONT_BODY_BOLD = (FONT_FAMILY, 10, "bold")
FONT_SMALL = (FONT_FAMILY, 9)
FONT_ROLLING = (FONT_FAMILY, 26, "bold")
FONT_ROLLING_BOUNCE = (FONT_FAMILY, 28, "bold")
FONT_GAME_NAME = (FONT_FAMILY, 16, "bold")


def set_font_family(family: str) -> None:
    """重建全部字体常量（apply_theme 会按可用性挑选后调用）。"""
    global FONT_FAMILY, FONT_TITLE, FONT_SECTION, FONT_BODY, FONT_BODY_BOLD, FONT_SMALL
    global FONT_ROLLING, FONT_ROLLING_BOUNCE, FONT_GAME_NAME
    FONT_FAMILY = family
    FONT_TITLE = (family, 20, "bold")
    FONT_SECTION = (family, 12, "bold")
    FONT_BODY = (family, 10)
    FONT_BODY_BOLD = (family, 10, "bold")
    FONT_SMALL = (family, 9)
    FONT_ROLLING = (family, 26, "bold")
    FONT_ROLLING_BOUNCE = (family, 28, "bold")
    FONT_GAME_NAME = (family, 16, "bold")


def pick_font_family(root: tk.Misc | None = None) -> str:
    """在候选字体里挑第一个系统真实存在的（避免 Tk 静默回退到难看的默认字体）。"""
    try:
        available = set(tkfont.families(root))
    except Exception:  # pragma: no cover - 无 Tk 环境
        return FONT_FAMILY
    for candidate in FONT_FAMILY_CANDIDATES:
        if candidate in available:
            return candidate
    return FONT_FAMILY_CANDIDATES[-1]


# ---------------------------------------------------------------------------
# 尺寸与间距
# ---------------------------------------------------------------------------
PAD_OUTER = 12
PAD_INNER = 8
PAD_TIGHT = 4

#: 可选的窗口尺寸预设（宽, 高）。用户可在设置里用下拉条切换；默认取第一个。
#: 680×880 是最紧凑的一档（默认）；800×1100 更宽裕（简介与列表能多显示几行）；
#: 1100×800 是横版，适合宽屏并排看。
WINDOW_SIZE_PRESETS: tuple[tuple[int, int], ...] = ((680, 880), (800, 1100), (1100, 800))
#: 默认窗口尺寸（取预设第一项，避免两处各写一份）
WINDOW_DEFAULT_WIDTH, WINDOW_DEFAULT_HEIGHT = WINDOW_SIZE_PRESETS[0]


def best_fit_size(screen_width: int, screen_height: int) -> str:
    """屏幕装不下默认预设时，挑一个能放下的预设（PRD D16）。

    没有这个回退，1024×768 这类小屏上默认尺寸会被迫压缩，而下拉条随即显示
    「自定义」——用户明明没拖过窗口，却看到"自定义"，很困惑。
    选择顺序即预设顺序：取第一个能完整放下的；都放不下则仍用第一个（由 clamp 压缩）。
    """
    for width, height in WINDOW_SIZE_PRESETS:
        if width <= screen_width and height <= screen_height:
            return f"{width}x{height}"
    return f"{WINDOW_SIZE_PRESETS[0][0]}x{WINDOW_SIZE_PRESETS[0][1]}"
#: 最小尺寸：宽度取最窄的预设（再窄会挤坏封面与文字列），高度 620
#: （结果卡片是固定高度，再矮就会挤压各区块）
WINDOW_MIN_WIDTH = 680
WINDOW_MIN_HEIGHT = 620
POOL_AUTO_COLLAPSE_HEIGHT = 620
#: 游戏列表的固定行数（窗口变高时由区2 的 expand 吸收，不再靠加大行数）
POOL_TREE_HEIGHT = 4

#: 结果卡片固定高度（PRD D14）：封面 300×140 + 游戏名 + 简介 + 元信息 + 售价，
#: 不随游戏不同而伸缩，否则每次抽签窗口内容都会跳一下。
DETAILS_CARD_HEIGHT = 150
#: 卡片里简介之外的固定占用（游戏名 + 元信息 + 售价 + 内边距），用于反算简介能放几行。
#: 实测：32 + 23 + 23 + 2×4（网格间距）+ 2×7（内边距）= 96，故简介最多 2 行。
DETAILS_TEXT_RESERVE = 96
#: 抽签记录窗口的列表行数（记录最多 10 条，一次能看全）
HISTORY_VISIBLE_ROWS = 10
#: 抽签记录窗口的初始尺寸
HISTORY_DIALOG_WIDTH = 560
HISTORY_DIALOG_HEIGHT = 420

#: 默认窗口几何串（``800x1100``）：config 层也用它当默认值，避免两处各写一份
DEFAULT_GEOMETRY = f"{WINDOW_DEFAULT_WIDTH}x{WINDOW_DEFAULT_HEIGHT}"

DRAW_BUTTON_WIDTH = 18
DRAW_BUTTON_HEIGHT = 44
BUTTON_MIN_HEIGHT = 30
BUTTON_MIN_WIDTH = 84
#: 对话框底部按钮统一的内边距：主/次按钮样式不同，尺寸必须靠这个拉平
DIALOG_BUTTON_PAD_X = 24
DIALOG_BUTTON_PAD_Y = 8
HEADER_BAR_HEIGHT = 2  # 顶栏下的 Steam 蓝强调线

HEADER_ASPECT = 215 / 460
HEADER_MAX_WIDTH = 300
HEADER_MIN_WIDTH = 240
#: 封面宽度占窗口比例（0.30 让默认宽度窗口正好落在 300 上限，取整后仍是 300）
HEADER_WIDTH_RATIO = 0.30

CHECK_ON = "☑"
CHECK_OFF = "☐"

ROW_HEIGHT = 26


def color_for_level(level: str) -> str:
    return LEVEL_COLORS.get(level, COLOR_MUTED)


def header_image_size(window_width: int) -> tuple[int, int]:
    """封面尺寸 = min(300, 可用宽度 × 0.30)，保持 460:215 比例（PRD 2.3）。"""
    width = int(max(0, window_width) * HEADER_WIDTH_RATIO)
    width = max(HEADER_MIN_WIDTH, min(HEADER_MAX_WIDTH, width))
    height = max(1, round(width * HEADER_ASPECT))
    return width, height


# ---------------------------------------------------------------------------
# 对比度工具（供测试与设计校验使用）
# ---------------------------------------------------------------------------
def _channel(value: float) -> float:
    return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4


def hex_to_rgb(color: str) -> tuple[int, int, int]:
    text = color.lstrip("#")
    if len(text) == 3:
        text = "".join(char * 2 for char in text)
    if len(text) != 6:
        raise ValueError(f"不是合法的十六进制颜色：{color}")
    return int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16)


def relative_luminance(color: str) -> float:
    red, green, blue = (_channel(value / 255) for value in hex_to_rgb(color))
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def contrast_ratio(foreground: str, background: str) -> float:
    """WCAG 对比度（1 ~ 21）；正文建议 ≥ 4.5。"""
    first = relative_luminance(foreground)
    second = relative_luminance(background)
    lighter, darker = max(first, second), min(first, second)
    return (lighter + 0.05) / (darker + 0.05)


# ---------------------------------------------------------------------------
# ttk 样式
# ---------------------------------------------------------------------------
STYLE_FRAME = "Steam.TFrame"
STYLE_HEADER_FRAME = "Header.TFrame"
STYLE_ACCENT_FRAME = "Accent.TFrame"
STYLE_CARD_FRAME = "Card.TFrame"
STYLE_CARD_BORDER_FRAME = "CardBorder.TFrame"

STYLE_TITLE_LABEL = "HeaderTitle.TLabel"
STYLE_LABEL = "Steam.TLabel"
STYLE_MUTED_LABEL = "Muted.TLabel"
STYLE_SECTION_LABEL = "Section.TLabel"
STYLE_CARD_LABEL = "Card.TLabel"
STYLE_CARD_MUTED_LABEL = "CardMuted.TLabel"
STYLE_STRONG_LABEL = "Strong.TLabel"

STYLE_BUTTON = "Steam.TButton"
STYLE_HEADER_BUTTON = "HeaderButton.TButton"
STYLE_ACCENT_BUTTON = "Accent.TButton"
STYLE_LINK_BUTTON = "Link.TButton"
STYLE_ENTRY = "Steam.TEntry"
STYLE_COMBOBOX = "Steam.TCombobox"
STYLE_CHECK = "Steam.TCheckbutton"
STYLE_RADIO = "Steam.TRadiobutton"
STYLE_CARD_CHECK = "Card.TCheckbutton"
STYLE_CARD_RADIO = "Card.TRadiobutton"
STYLE_TREE = "Steam.Treeview"
STYLE_TREE_HEADING = "Steam.Treeview.Heading"
STYLE_SCROLLBAR = "Steam.Vertical.TScrollbar"


def apply_theme(root: tk.Misc, *, family: str | None = None) -> ttk.Style:
    """把 Steam 深色风格应用到整个 ttk 环境（幂等，可重复调用）。"""
    set_font_family(family or pick_font_family(root))
    style = ttk.Style(root)
    if "clam" in style.theme_names():
        # vista 主题忽略背景色配置，必须换到 clam 才能实现深色自绘
        style.theme_use("clam")

    style.configure(".", background=COLOR_BG, foreground=COLOR_TEXT, font=FONT_BODY)

    # 容器 ---------------------------------------------------------------
    style.configure(STYLE_FRAME, background=COLOR_BG)
    style.configure(STYLE_HEADER_FRAME, background=COLOR_HEADER)
    style.configure(STYLE_ACCENT_FRAME, background=COLOR_ACCENT)
    style.configure(STYLE_CARD_FRAME, background=COLOR_CARD)
    style.configure(STYLE_CARD_BORDER_FRAME, background=COLOR_BORDER)

    # 文本 ---------------------------------------------------------------
    style.configure(STYLE_LABEL, background=COLOR_BG, foreground=COLOR_TEXT, font=FONT_BODY)
    style.configure(
        STYLE_TITLE_LABEL, background=COLOR_HEADER, foreground=COLOR_ACCENT, font=FONT_TITLE
    )
    style.configure(STYLE_MUTED_LABEL, background=COLOR_BG, foreground=COLOR_MUTED, font=FONT_SMALL)
    style.configure(
        STYLE_SECTION_LABEL, background=COLOR_BG, foreground=COLOR_MUTED, font=FONT_SMALL
    )
    style.configure(STYLE_CARD_LABEL, background=COLOR_CARD, foreground=COLOR_TEXT, font=FONT_BODY)
    style.configure(
        STYLE_CARD_MUTED_LABEL, background=COLOR_CARD, foreground=COLOR_MUTED, font=FONT_SMALL
    )
    style.configure(
        STYLE_STRONG_LABEL, background=COLOR_BG, foreground=COLOR_TEXT_STRONG, font=FONT_BODY_BOLD
    )

    # 按钮 ---------------------------------------------------------------
    style.configure(
        STYLE_BUTTON,
        background=COLOR_BUTTON,
        foreground=COLOR_BUTTON_TEXT,
        bordercolor=COLOR_BORDER,
        focuscolor=COLOR_BUTTON,
        focusthickness=0,
        borderwidth=0,
        relief="flat",
        padding=(12, 6),
        font=FONT_BODY,
    )
    style.map(
        STYLE_BUTTON,
        background=[("disabled", COLOR_BUTTON_DISABLED), ("active", COLOR_BUTTON_HOVER)],
        foreground=[("disabled", COLOR_MUTED), ("active", COLOR_TEXT_STRONG)],
    )
    style.configure(
        STYLE_HEADER_BUTTON,
        background=COLOR_HEADER,
        foreground=COLOR_TEXT,
        focuscolor=COLOR_HEADER,
        focusthickness=0,
        borderwidth=0,
        relief="flat",
        padding=(10, 4),
        font=FONT_SMALL,
    )
    style.map(
        STYLE_HEADER_BUTTON,
        background=[("disabled", COLOR_HEADER), ("active", COLOR_PANEL)],
        foreground=[("disabled", COLOR_MUTED), ("active", COLOR_TEXT_STRONG)],
    )
    style.configure(
        STYLE_ACCENT_BUTTON,
        background=COLOR_CTA,
        foreground=COLOR_CTA_TEXT,
        bordercolor=COLOR_CTA_HOVER,
        focuscolor=COLOR_CTA,
        focusthickness=0,
        borderwidth=0,
        relief="flat",
        padding=(18, 10),
        font=FONT_BODY_BOLD,
    )
    style.map(
        STYLE_ACCENT_BUTTON,
        background=[("disabled", COLOR_CTA_DISABLED), ("active", COLOR_CTA_HOVER)],
        foreground=[("disabled", COLOR_CTA_TEXT_DISABLED), ("active", "#ffffff")],
    )
    style.configure(
        STYLE_LINK_BUTTON,
        background=COLOR_BG,
        foreground=COLOR_ACCENT,
        focuscolor=COLOR_BG,
        focusthickness=0,
        borderwidth=0,
        relief="flat",
        padding=(4, 2),
        font=FONT_BODY,
    )
    style.map(
        STYLE_LINK_BUTTON,
        background=[("active", COLOR_BG)],
        foreground=[("disabled", COLOR_MUTED), ("active", COLOR_TEXT_STRONG)],
    )

    # 输入与勾选 ---------------------------------------------------------
    style.configure(
        STYLE_ENTRY,
        fieldbackground=COLOR_INPUT_BG,
        foreground=COLOR_TEXT_STRONG,
        insertcolor=COLOR_TEXT_STRONG,
        bordercolor=COLOR_BORDER,
        lightcolor=COLOR_BORDER,
        darkcolor=COLOR_BORDER,
        padding=(6, 4),
    )
    style.map(
        STYLE_ENTRY,
        fieldbackground=[("disabled", COLOR_CARD), ("focus", COLOR_INPUT_BG)],
        foreground=[("disabled", COLOR_MUTED)],
        bordercolor=[("focus", COLOR_ACCENT)],
    )

    # 下拉条（窗口大小选择）：clam 下要把 field/arrow/下拉列表都染深色，
    # 否则未配置的默认值是浅灰底，在深色界面里非常刺眼。
    style.configure(
        STYLE_COMBOBOX,
        fieldbackground=COLOR_INPUT_BG,
        background=COLOR_BUTTON,
        foreground=COLOR_TEXT_STRONG,
        bordercolor=COLOR_BORDER,
        lightcolor=COLOR_BORDER,
        darkcolor=COLOR_BORDER,
        arrowcolor=COLOR_TEXT,
        selectbackground=COLOR_ACCENT,
        selectforeground=COLOR_HEADER,
        padding=(6, 4),
    )
    style.map(
        STYLE_COMBOBOX,
        fieldbackground=[("readonly", COLOR_INPUT_BG), ("disabled", COLOR_CARD)],
        foreground=[("disabled", COLOR_MUTED), ("readonly", COLOR_TEXT_STRONG)],
        background=[("active", COLOR_BUTTON_HOVER), ("readonly", COLOR_BUTTON)],
        arrowcolor=[("disabled", COLOR_MUTED), ("active", COLOR_TEXT_STRONG)],
        bordercolor=[("focus", COLOR_ACCENT)],
    )
    # 下拉列表本身由 Tk（不是 ttk）绘制，只能用 option 数据库染色
    try:
        root.tk.eval(
            "option add *TCombobox*Listbox.background {bg}".format(bg=COLOR_CARD)
        )
        root.tk.eval(
            "option add *TCombobox*Listbox.foreground {fg}".format(fg=COLOR_TEXT)
        )
        root.tk.eval(
            "option add *TCombobox*Listbox.selectBackground {bg}".format(bg=COLOR_ACCENT)
        )
        root.tk.eval(
            "option add *TCombobox*Listbox.selectForeground {fg}".format(fg=COLOR_HEADER)
        )
    except tk.TclError:  # pragma: no cover - 极简 Tk 环境
        pass
    for name, background in (
        (STYLE_CHECK, COLOR_BG),
        (STYLE_RADIO, COLOR_BG),
        (STYLE_CARD_CHECK, COLOR_CARD),
        (STYLE_CARD_RADIO, COLOR_CARD),
    ):
        # clam 主题的指示器选项是 indicatorbackground / indicatorforeground
        # （不是 indicatorcolor —— 写错会被静默忽略，勾选框会留在浅色）
        style.configure(
            name,
            background=background,
            foreground=COLOR_TEXT,
            focuscolor=background,
            font=FONT_BODY,
            padding=(2, 2),
            indicatorbackground=COLOR_INPUT_BG,
            indicatorforeground=COLOR_INPUT_BG,
            upperbordercolor=COLOR_BORDER,
            lowerbordercolor=COLOR_BORDER,
        )
        style.map(
            name,
            background=[("active", background)],
            foreground=[("disabled", COLOR_MUTED), ("active", COLOR_TEXT_STRONG)],
            indicatorbackground=[
                ("disabled", COLOR_BUTTON_DISABLED),
                ("selected", COLOR_ACCENT),
                ("!selected", COLOR_INPUT_BG),
            ],
            indicatorforeground=[
                ("disabled", COLOR_MUTED),
                ("selected", COLOR_HEADER),  # 深色勾/点在 Steam 蓝底上
                ("!selected", COLOR_INPUT_BG),
            ],
            upperbordercolor=[("selected", COLOR_ACCENT), ("!selected", COLOR_BORDER)],
            lowerbordercolor=[("selected", COLOR_ACCENT), ("!selected", COLOR_BORDER)],
        )

    # 列表 ---------------------------------------------------------------
    style.configure(
        STYLE_TREE,
        background=COLOR_CARD,
        fieldbackground=COLOR_CARD,
        foreground=COLOR_TEXT,
        bordercolor=COLOR_BORDER,
        lightcolor=COLOR_CARD,
        darkcolor=COLOR_CARD,
        rowheight=ROW_HEIGHT,
        font=FONT_BODY,
        borderwidth=0,
    )
    style.map(
        STYLE_TREE,
        background=[("selected", COLOR_SELECTION)],
        foreground=[("selected", COLOR_TEXT_STRONG)],
    )
    for heading in ("Treeview.Heading", STYLE_TREE_HEADING):
        style.configure(
            heading,
            background=COLOR_PANEL,
            foreground=COLOR_TEXT_STRONG,
            relief="flat",
            borderwidth=0,
            padding=(6, 5),
            font=FONT_SMALL,
        )
        style.map(heading, background=[("active", COLOR_BUTTON_HOVER)])

    style.configure(
        STYLE_SCROLLBAR,
        background=COLOR_PANEL,
        troughcolor=COLOR_BG,
        bordercolor=COLOR_BG,
        arrowcolor=COLOR_TEXT,
        lightcolor=COLOR_PANEL,
        darkcolor=COLOR_PANEL,
        relief="flat",
    )
    style.map(STYLE_SCROLLBAR, background=[("active", COLOR_BUTTON_HOVER)])
    return style


def make_card(parent: tk.Misc, *, padding: int = PAD_INNER) -> tuple[ttk.Frame, ttk.Frame]:
    """生成"1px 描边 + 深色底"的 Steam 卡片；返回 (外框, 内框)。

    外框负责画描边色，内框才是内容容器（ttk 无法直接给 Frame 只画边框）。
    """
    border = ttk.Frame(parent, style=STYLE_CARD_BORDER_FRAME)
    inner = ttk.Frame(border, style=STYLE_CARD_FRAME, padding=padding)
    inner.pack(fill="both", expand=True, padx=1, pady=1)
    return border, inner
