"""Steam 风格主题测试（PRD 11.2 / AC-51 / AC-52）。

界面改版无法靠"看一眼"来回归，所以这里把设计约束变成可执行断言：

* 配色必须等于 Steam 官方色板（写错的十六进制会立刻失败）；
* 所有前景/背景组合必须满足 WCAG AA（对比度 ≥ 4.5:1），避免深色主题下读不清；
* ``apply_theme`` 必须真的把样式装进 ttk（只定义常量、忘记 apply 会失败）；
* 控件必须挂上对应样式（主按钮用 Steam 绿、列表用深色卡片等）；
* 旧浅色主题的颜色不得残留。
"""

from __future__ import annotations

from pathlib import Path
from tkinter import font as tkfont
from tkinter import ttk

import pytest

from app.config import Config, ConfigStore
from app.i18n import LANG_EN, LANG_ZH, set_language
from app.models import Game
from app.state import AppState
from app.ui import theme
from app.ui.main_window import MainWindow

KEY = "K" * 32


@pytest.fixture()
def store(tmp_path: Path) -> ConfigStore:
    instance = ConfigStore(tmp_path / "SteamGamePicker")
    instance.ensure_dirs()
    return instance


@pytest.fixture()
def window(root, store: ConfigStore) -> MainWindow:
    instance = MainWindow(root, store=store, config=Config(api_key=KEY))
    instance.set_games(
        [
            Game(appid=1, name="Alpha 冒险", playtime_forever=0),
            Game(appid=2, name="Beta 射击", playtime_forever=30),
            Game(appid=3, name="Gamma 模拟", playtime_forever=5000),
        ]
    )
    return instance


# --------------------------------------------------------------------- 配色
def test_palette_matches_steam_official_colors() -> None:
    """基础色板锁定为 Steam 官方界面用色。"""
    assert theme.COLOR_HEADER == "#171a21"
    assert theme.COLOR_BG == "#1b2838"
    assert theme.COLOR_PANEL == "#2a475e"
    assert theme.COLOR_ACCENT == "#66c0f4"
    assert theme.COLOR_TEXT == "#c6d4df"
    assert theme.COLOR_CARD == "#16202d"
    assert theme.COLOR_BORDER == "#2a3f5a"


def test_main_button_uses_steam_store_green() -> None:
    """主行动按钮用 Steam 商店的绿色 CTA 配色。"""
    assert theme.COLOR_CTA == "#4c6b22"
    assert theme.COLOR_CTA_HOVER == "#75b022"
    assert theme.COLOR_CTA_TEXT == "#d2e885"


def test_legacy_light_theme_colors_are_gone() -> None:
    """改版前的浅色主题配色不得残留在主题模块里。"""
    legacy = {"#F5F6F8", "#1B7F3A", "#333333", "#B9C3CE", "#C0392B", "#B8860B", "#1B6AC9"}
    palette = {
        value
        for value in vars(theme).values()
        if isinstance(value, str) and value.startswith("#")
    }
    palette.update(theme.LEVEL_COLORS.values())
    assert not (palette & legacy), f"仍在使用旧配色：{palette & legacy}"


def test_status_level_colors_stay_mapped() -> None:
    assert theme.color_for_level("ok") == theme.COLOR_OK
    assert theme.color_for_level("warn") == theme.COLOR_WARN
    assert theme.color_for_level("error") == theme.COLOR_ERROR
    assert theme.color_for_level("muted") == theme.COLOR_MUTED
    assert theme.color_for_level("未知") == theme.COLOR_MUTED


# ------------------------------------------------------------------ 对比度
def test_contrast_helper_matches_wcag_reference() -> None:
    assert theme.contrast_ratio("#ffffff", "#000000") == pytest.approx(21.0, abs=0.05)
    assert theme.contrast_ratio("#000000", "#ffffff") == pytest.approx(21.0, abs=0.05)
    assert theme.contrast_ratio("#1b2838", "#1b2838") == pytest.approx(1.0, abs=0.01)
    assert theme.hex_to_rgb("#66c0f4") == (102, 192, 244)
    assert theme.hex_to_rgb("#fff") == (255, 255, 255)
    with pytest.raises(ValueError):
        theme.hex_to_rgb("不是颜色")


@pytest.mark.parametrize(
    ("name", "foreground", "background"),
    [
        ("正文 / 页面底", theme.COLOR_TEXT, theme.COLOR_BG),
        ("正文 / 卡片", theme.COLOR_TEXT, theme.COLOR_CARD),
        ("正文 / 斑马纹", theme.COLOR_TEXT, theme.COLOR_CARD_ALT),
        ("次要文字 / 页面底", theme.COLOR_MUTED, theme.COLOR_BG),
        ("次要文字 / 卡片", theme.COLOR_MUTED, theme.COLOR_CARD),
        ("Steam 蓝 / 页面底", theme.COLOR_ACCENT, theme.COLOR_BG),
        ("Steam 蓝 / 卡片", theme.COLOR_ACCENT, theme.COLOR_CARD),
        ("Steam 蓝 / 顶栏", theme.COLOR_ACCENT, theme.COLOR_HEADER),
        ("按钮文字 / 次按钮", theme.COLOR_BUTTON_TEXT, theme.COLOR_BUTTON),
        ("CTA 文字 / CTA 底", theme.COLOR_CTA_TEXT, theme.COLOR_CTA),
        ("中签绿 / 页面底", theme.COLOR_OK, theme.COLOR_BG),
        ("中签绿 / 卡片", theme.COLOR_OK, theme.COLOR_CARD),
        ("警告色 / 页面底", theme.COLOR_WARN, theme.COLOR_BG),
        ("错误色 / 页面底", theme.COLOR_ERROR, theme.COLOR_BG),
        ("滚动名 / 页面底", theme.COLOR_ROLLING, theme.COLOR_BG),
        ("选中行文字 / 选中底", theme.COLOR_TEXT_STRONG, theme.COLOR_SELECTION),
    ],
)
def test_palette_meets_wcag_aa(name: str, foreground: str, background: str) -> None:
    ratio = theme.contrast_ratio(foreground, background)
    assert ratio >= 4.5, f"{name} 对比度仅 {ratio:.2f}:1，低于 AA 要求的 4.5:1"


# -------------------------------------------------------------------- 样式
def test_apply_theme_installs_styles(root) -> None:
    style = theme.apply_theme(root)

    assert style.theme_use() == "clam", "必须换到 clam 才能自绘深色控件"
    assert style.lookup(theme.STYLE_FRAME, "background") == theme.COLOR_BG
    assert style.lookup(theme.STYLE_HEADER_FRAME, "background") == theme.COLOR_HEADER
    assert style.lookup(theme.STYLE_CARD_FRAME, "background") == theme.COLOR_CARD
    assert style.lookup(theme.STYLE_CARD_BORDER_FRAME, "background") == theme.COLOR_BORDER
    assert style.lookup(theme.STYLE_TITLE_LABEL, "foreground") == theme.COLOR_ACCENT
    assert style.lookup(theme.STYLE_BUTTON, "background") == theme.COLOR_BUTTON
    assert style.lookup(theme.STYLE_ACCENT_BUTTON, "background") == theme.COLOR_CTA
    assert style.lookup(theme.STYLE_ACCENT_BUTTON, "foreground") == theme.COLOR_CTA_TEXT
    assert style.lookup(theme.STYLE_HEADER_BUTTON, "background") == theme.COLOR_HEADER
    assert style.lookup(theme.STYLE_ENTRY, "fieldbackground") == theme.COLOR_INPUT_BG
    assert style.lookup(theme.STYLE_TREE, "fieldbackground") == theme.COLOR_CARD
    assert style.lookup(theme.STYLE_TREE, "rowheight") == theme.ROW_HEIGHT
    assert style.lookup("Treeview.Heading", "background") == theme.COLOR_PANEL
    assert style.lookup(theme.STYLE_SCROLLBAR, "troughcolor") == theme.COLOR_BG


def test_button_state_colors_are_mapped(root) -> None:
    style = theme.apply_theme(root)

    accent = style.map(theme.STYLE_ACCENT_BUTTON, "background")
    assert ("active", theme.COLOR_CTA_HOVER) in accent
    assert ("disabled", theme.COLOR_CTA_DISABLED) in accent

    secondary = style.map(theme.STYLE_BUTTON, "background")
    assert ("active", theme.COLOR_BUTTON_HOVER) in secondary
    assert ("disabled", theme.COLOR_BUTTON_DISABLED) in secondary

    tree_selection = style.map(theme.STYLE_TREE, "background")
    assert ("selected", theme.COLOR_SELECTION) in tree_selection


def test_apply_theme_is_idempotent(root) -> None:
    first = theme.apply_theme(root)
    first_value = first.lookup(theme.STYLE_ACCENT_BUTTON, "background")
    second = theme.apply_theme(root)

    assert second.lookup(theme.STYLE_ACCENT_BUTTON, "background") == first_value


def test_check_and_radio_indicators_are_dark_themed(root) -> None:
    """勾选框/单选框指示器必须跟随深色主题（clam 用 indicatorbackground，不是 indicatorcolor）。"""
    style = theme.apply_theme(root)

    for name in (theme.STYLE_CHECK, theme.STYLE_RADIO, theme.STYLE_CARD_CHECK, theme.STYLE_CARD_RADIO):
        assert style.lookup(name, "indicatorbackground") == theme.COLOR_INPUT_BG, name
        selected = style.map(name, "indicatorbackground")
        assert ("selected", theme.COLOR_ACCENT) in selected, name
        assert ("disabled", theme.COLOR_BUTTON_DISABLED) in selected, name
        glyph = style.map(name, "indicatorforeground")
        assert ("selected", theme.COLOR_HEADER) in glyph, name


def test_clam_supports_the_options_we_configure(root) -> None:
    """防止再写出被 clam 静默忽略的选项名（上次就是 indicatorcolor）。"""
    style = theme.apply_theme(root)
    supported = set(style.element_options("Checkbutton.indicator"))
    assert {"indicatorbackground", "indicatorforeground"} <= supported
    assert "indicatorcolor" not in supported


def test_rolling_font_is_compact_enough_for_800x600() -> None:
    """默认窗口只有 600 高，滚动大字不宜过大（改版实测：28pt 会挤掉游戏列表）。"""
    assert theme.FONT_ROLLING[1] <= 26
    assert theme.FONT_ROLLING_BOUNCE[1] == theme.FONT_ROLLING[1] + 2


# -------------------------------------------------------- 窄窗口的布局自适应
def test_short_window_auto_collapses_pool_panel(
    window: MainWindow, store: ConfigStore
) -> None:
    window.toggle_pool_panel(expand=True)
    window.flush_save()  # 先清掉"用户展开"这次待写盘

    assert window.should_auto_collapse(theme.POOL_AUTO_COLLAPSE_HEIGHT - 1) is True
    assert window.should_auto_collapse(theme.POOL_AUTO_COLLAPSE_HEIGHT) is False
    assert window.should_auto_collapse(0) is False

    window.toggle_pool_panel(expand=False, persist=False)

    assert window.pool_panel_expanded is False
    assert window._save_job is None, "自动收起是临时适配，不应触发配置写盘"
    assert store.load().config.ui.pool_panel_expanded is True, "用户的展开偏好不该被自动收起改掉"


def test_configure_binding_registered(window: MainWindow) -> None:
    assert window.root.bind("<Configure>")


def test_zone3_placeholder_uses_small_font(window: MainWindow) -> None:
    """占位/提示文案不能占用滚动大字（26pt 提示在 800px 窗口里会被截断）。"""
    assert window.winner is None
    font = str(window.rolling_label.cget("font"))
    assert str(theme.FONT_SECTION[1]) in font
    assert str(theme.FONT_ROLLING[1]) not in font
    assert str(window.rolling_label.cget("foreground")) == theme.COLOR_MUTED

    window.set_state(AppState.EMPTY_POOL)
    assert str(theme.FONT_SECTION[1]) in str(window.rolling_label.cget("font"))


def test_bulk_button_labels_are_on_their_own_row(window: MainWindow) -> None:
    """批量按钮换行，避免与搜索框同行时横向溢出被窗口裁掉。"""
    rows = {mode: int(button.grid_info()["row"]) for mode, button in window.bulk_buttons.items()}
    assert set(rows.values()) == {1}
    assert int(window.search_entry.grid_info()["row"]) == 0
    assert int(window.search_entry.grid_info()["columnspan"]) == 4
    assert int(window.selected_label.grid_info()["row"]) == 1


def test_cover_placeholder_is_hidden_until_a_result(window: MainWindow) -> None:
    """没抽签前不占封面位（约 112px），把高度留给游戏列表。"""
    assert window.cover_box.winfo_manager() == ""
    assert str(window.cover_label.cget("text")) == ""

    window.winner = window.games[0]
    window._set_cover(None)

    assert window.cover_box.winfo_manager() == "grid"
    assert str(window.cover_label.cget("text")) == "（无封面）"


def _overflow_offenders(window: MainWindow, width: int, height: int) -> tuple[int, list[str]]:
    """在当前窗口尺寸下逐控件判定越界，返回 (受检控件数, 越界描述)。"""
    window.root.geometry(f"{width}x{height}")
    window.root.deiconify()  # 需要真实映射才能取得几何数据
    window.root.update_idletasks()
    window.root.update()

    origin_x, origin_y = window.root.winfo_rootx(), window.root.winfo_rooty()
    offenders: list[str] = []
    checked = 0
    for widget in _walk(window.root):
        if widget is window.root or not widget.winfo_ismapped():
            continue
        checked += 1
        right = widget.winfo_rootx() - origin_x + widget.winfo_width()
        bottom = widget.winfo_rooty() - origin_y + widget.winfo_height()
        left = widget.winfo_rootx() - origin_x
        if right > width + 1 or bottom > height + 1 or left < -1:
            offenders.append(f"{widget.winfo_class()} right={right} bottom={bottom}")

    window.root.withdraw()
    return checked, offenders


@pytest.mark.parametrize(
    ("width", "height"),
    [(theme.WINDOW_DEFAULT_WIDTH, theme.WINDOW_DEFAULT_HEIGHT), (theme.WINDOW_MIN_WIDTH, theme.WINDOW_MIN_HEIGHT)],
)
def test_no_widget_overflows_the_window(window: MainWindow, width: int, height: int) -> None:
    """默认 800×600 与最小 640×480 下，任何控件都不得越出窗口边界。

    改版实测教训：批量按钮与搜索框同行时会把行撑宽，右侧按钮被窗口裁掉——
    这类问题肉眼容易漏，用 Tk 自己的几何数据判定最可靠。
    """
    checked, offenders = _overflow_offenders(window, width, height)

    assert checked >= 20, f"只检查到 {checked} 个控件，窗口可能没真正映射，测试无意义"
    assert not offenders, f"{width}x{height} 下有控件越界：{offenders}"


@pytest.mark.parametrize(
    ("width", "height"),
    [(theme.WINDOW_DEFAULT_WIDTH, theme.WINDOW_DEFAULT_HEIGHT), (theme.WINDOW_MIN_WIDTH, theme.WINDOW_MIN_HEIGHT)],
)
def test_no_widget_overflows_in_english(root, store: ConfigStore, width: int, height: int) -> None:
    """英文文案普遍更长（Select none / Never played / Load Library…），同样不得越界。

    这个用例是被"截屏自查"逼出来的：英文界面在第一版截图里看着像越界，
    查下来是截图工具没换算 DPI；顺手补上这条测试，把可能性彻底排掉。
    """
    set_language(LANG_EN)
    instance = MainWindow(root, store=store, config=Config(api_key=KEY))
    instance.set_games(
        [
            Game(appid=1, name="Alpha Adventure", playtime_forever=0),
            Game(appid=2, name="Beta Shooter", playtime_forever=30),
            Game(appid=3, name="Gamma Simulation", playtime_forever=5000),
        ]
    )
    checked, offenders = _overflow_offenders(instance, width, height)
    set_language(LANG_ZH)

    assert checked >= 20, f"只检查到 {checked} 个控件，窗口可能没真正映射，测试无意义"
    assert not offenders, f"{width}x{height} 英文界面有控件越界：{offenders}"


def test_pick_font_family_returns_installed_family(root) -> None:
    family = theme.pick_font_family(root)
    assert family in theme.FONT_FAMILY_CANDIDATES
    assert family in set(tkfont.families(root))


def test_default_family_is_chinese_ui_font_first() -> None:
    """中文界面优先用带中文字形的系统界面字体（Steam 的 Motiva Sans 不可分发）。"""
    assert theme.FONT_FAMILY_CANDIDATES[0] == "Microsoft YaHei UI"
    assert "Segoe UI" in theme.FONT_FAMILY_CANDIDATES


def test_card_helper_builds_bordered_panel(root) -> None:
    border, inner = theme.make_card(root)

    assert str(border.cget("style")) == theme.STYLE_CARD_BORDER_FRAME
    assert str(inner.cget("style")) == theme.STYLE_CARD_FRAME
    assert inner.master is border
    assert inner.winfo_manager() == "pack"


# ------------------------------------------------------------ 窗口实际应用
def test_window_applies_steam_theme(window: MainWindow) -> None:
    assert isinstance(window.style, ttk.Style)
    assert str(window.root.cget("bg")) == theme.COLOR_BG
    assert str(window.header.cget("style")) == theme.STYLE_HEADER_FRAME
    assert str(window.draw_button.cget("style")) == theme.STYLE_ACCENT_BUTTON
    assert str(window.load_button.cget("style")) == theme.STYLE_BUTTON
    assert str(window.settings_button.cget("style")) == theme.STYLE_HEADER_BUTTON
    assert str(window.identity_entry.cget("style")) == theme.STYLE_ENTRY
    assert str(window.search_entry.cget("style")) == theme.STYLE_ENTRY
    assert str(window.tree.cget("style")) == theme.STYLE_TREE
    assert str(window.pool_body.cget("style")) == theme.STYLE_CARD_BORDER_FRAME


def test_header_has_steam_blue_underline(window: MainWindow) -> None:
    accents = [
        child
        for child in window.root.winfo_children()
        if isinstance(child, ttk.Frame) and str(child.cget("style")) == theme.STYLE_ACCENT_FRAME
    ]
    assert accents, "顶栏下应有 Steam 蓝强调线"
    assert int(accents[0].cget("height")) == theme.HEADER_BAR_HEIGHT == 2


def test_draw_button_is_the_only_accent_cta(window: MainWindow) -> None:
    """绿色 CTA 只给"抽签"，避免主次不分。"""
    accent_style = theme.STYLE_ACCENT_BUTTON
    styled = [
        widget
        for widget in _walk(window.root)
        if _safe_cget(widget, "style") == accent_style
    ]
    assert len(styled) == 1
    assert styled[0] is window.draw_button


def test_tree_tags_configured_for_dimming_and_stripes(window: MainWindow) -> None:
    assert window.tree.tag_configure("excluded")["foreground"] == theme.COLOR_MUTED
    assert window.tree.tag_configure("included")["foreground"] == theme.COLOR_TEXT
    assert window.tree.tag_configure("even")["background"] == theme.COLOR_CARD
    assert window.tree.tag_configure("odd")["background"] == theme.COLOR_CARD_ALT


def test_rows_are_striped_and_excluded_rows_dimmed(window: MainWindow) -> None:
    assert window.tree.item("1", "tags") == ("even", "included")
    assert window.tree.item("2", "tags") == ("odd", "included")
    assert window.tree.item("3", "tags") == ("even", "included")

    window.toggle_game(2)

    tags = window.tree.item("2", "tags")
    assert "excluded" in tags, "被排除的游戏应灰显"
    assert "odd" in tags, "灰显不能破坏斑马纹"
    assert window.tree.set("2", "check") == theme.CHECK_OFF


def test_preset_change_keeps_tags_consistent(window: MainWindow) -> None:
    window.never_var.set(True)
    window.on_filter_clicked()

    assert "excluded" in window.tree.item("2", "tags")
    assert "included" in window.tree.item("1", "tags")


# ------------------------------------------------------------------ 工具
def _walk(widget) -> list:
    collected = [widget]
    for child in widget.winfo_children():
        collected.extend(_walk(child))
    return collected


def _safe_cget(widget, option: str) -> str:
    try:
        return str(widget.cget(option))
    except Exception:
        return ""
