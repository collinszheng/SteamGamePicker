"""窗口尺寸：默认值、旧配置迁移、屏幕外位置修正、设置里的「恢复默认大小」
（PRD D14 / AC-54）。

背景：v1.0.1 及更早版本把 800×600 当作默认值，而窗口几何是**写进配置**的，
所以光改代码不会让老用户看到新默认尺寸——必须有一次性迁移。
"""

from __future__ import annotations

import tkinter as tk
from pathlib import Path

import pytest

from app.config import (
    DEFAULT_GEOMETRY,
    LEGACY_DEFAULT_GEOMETRY,
    WINDOW_SIZE_CHOICES,
    WINDOW_SIZE_CUSTOM,
    Config,
    ConfigStore,
    clamp_geometry,
    geometry_proves_a_manual_resize,
    migrate_geometry,
    parse_geometry,
    resolve_window_size,
)
from app.ui import theme
from app.ui.main_window import MainWindow
from app.ui.settings_dialog import SettingsDialog

#: 必须是合法的 32 位十六进制（保存设置要走 API Key 校验）
KEY = "0123456789ABCDEF0123456789ABCDEF"


@pytest.fixture()
def store(tmp_path: Path) -> ConfigStore:
    instance = ConfigStore(tmp_path / "SteamGamePicker")
    instance.ensure_dirs()
    return instance


def screen_size(root: tk.Tk) -> tuple[int, int]:
    """当前屏幕尺寸。CI 运行器是 1024×768，装不下我们的预设，测试必须据此调整。"""
    return int(root.winfo_screenwidth()), int(root.winfo_screenheight())


def clamped(text: str, root: tk.Tk) -> tuple[int, int]:
    """把几何按屏幕收敛后的尺寸（模拟"窗口被压到屏幕内"）。"""
    width, height = screen_size(root)
    parsed = parse_geometry(clamp_geometry(text, width, height))
    assert parsed is not None
    return parsed


# ---------------------------------------------------------------- 纯逻辑：解析
@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("1100x800", (1100, 800)),
        ("800x600+100+100", (800, 600)),
        ("800x600-5+5", (800, 600)),
        ("  640x620  ", (640, 620)),
    ],
)
def test_parse_geometry_accepts_tk_forms(text: str, expected: tuple[int, int]) -> None:
    assert parse_geometry(text) == expected


@pytest.mark.parametrize("text", ["", "abc", "800", "800x", "x600", "0x600", "800x0", "-1x5"])
def test_parse_geometry_rejects_junk(text: str) -> None:
    assert parse_geometry(text) is None


# ---------------------------------------------------------------- 纯逻辑：迁移
def test_legacy_default_is_upgraded() -> None:
    assert migrate_geometry(LEGACY_DEFAULT_GEOMETRY) == DEFAULT_GEOMETRY


def test_legacy_default_with_position_suffix_is_upgraded() -> None:
    """老用户存的是带位置的几何串——只比较字符串会漏掉绝大多数人。"""
    assert migrate_geometry("800x600+120+80") == DEFAULT_GEOMETRY


def test_user_chosen_larger_size_is_kept() -> None:
    assert migrate_geometry("1400x900") == "1400x900"
    assert migrate_geometry("1400x900+10+10") == "1400x900", "位置偏移要丢掉"


def test_size_that_cannot_fit_the_new_layout_is_upgraded() -> None:
    assert migrate_geometry("860x700") == DEFAULT_GEOMETRY  # 太窄
    assert migrate_geometry("1200x640") == DEFAULT_GEOMETRY  # 太矮


def test_junk_falls_back_to_default() -> None:
    assert migrate_geometry("不是几何") == DEFAULT_GEOMETRY


# ---------------------------------------------------------------- 纯逻辑：限制
def test_clamp_fits_inside_the_screen() -> None:
    assert clamp_geometry("1600x1200", 1280, 800) == "1280x800"
    assert clamp_geometry("1600x1200", 2560, 1440) == "1600x1200"
    assert clamp_geometry("1600x1200", 1920, 1080) == "1600x1080", "高度超屏也要压回来"
    assert clamp_geometry("800x600+3000+2000", 1920, 1080) == "800x600"


def test_clamp_handles_missing_screen_size() -> None:
    assert clamp_geometry("1100x800", 0, 0) == "320x240"


# ---------------------------------------------------------------- 配置读写
def test_config_roundtrip_keeps_geometry(store: ConfigStore) -> None:
    config = Config(api_key=KEY)
    config.ui.window_geometry = "1400x900"
    store.save(config)
    assert store.load().config.ui.window_geometry == "1400x900"


def test_loading_an_old_config_upgrades_the_geometry(store: ConfigStore) -> None:
    store.ensure_dirs()
    store.config_path.write_text(
        '{"schema_version": 1, "ui": {"window_geometry": "800x600+100+100"}}', encoding="utf-8"
    )
    assert store.load().config.ui.window_geometry == DEFAULT_GEOMETRY


def test_config_no_longer_stores_the_pool_panel_flag(store: ConfigStore) -> None:
    store.save(Config(api_key=KEY))
    assert "pool_panel_expanded" not in store.config_path.read_text(encoding="utf-8")


# ---------------------------------------------------------------- 窗口行为
def test_window_uses_the_new_default(root: tk.Tk, store: ConfigStore) -> None:
    """没有历史配置时，启动就应请求**当前屏幕下最合适的预设**（默认 680×880）。

    断言的是"向窗口请求的几何"：窗口未映射时 Tk 的 ``geometry()`` 读回来的是
    minsize，拿它判断默认值会得到假失败。
    屏幕比预设矮时（例如 CI 的 1024×768）窗口会被压到屏幕内，这是预期行为。
    """
    world_width, world_height = screen_size(root)
    expected = theme.best_fit_size(world_width, world_height)

    window = MainWindow(root, store=store, config=Config(api_key=KEY))
    assert window._initial_geometry() == clamp_geometry(expected, world_width, world_height)
    # 屏幕够大时必须就是预设本身（本机 2560×1440 会走到这里）
    if world_width >= 680 and world_height >= 880:
        assert window._initial_geometry() == DEFAULT_GEOMETRY == "680x880"


def test_all_size_presets_are_offered() -> None:
    """用户要求的三档尺寸都必须可选，且默认是 680×880（安装后的初始值）。"""
    assert WINDOW_SIZE_CHOICES == ("680x880", "800x1100", "1100x800")
    assert DEFAULT_GEOMETRY == "680x880"


def test_best_fit_prefers_the_first_preset_that_fits() -> None:
    """屏幕装不下默认预设时降级到能放下的那一档（PRD D16）。"""
    assert theme.best_fit_size(2560, 1440) == "680x880"  # 都放得下 → 取第一档
    assert theme.best_fit_size(1024, 768) == "680x880"  # 都放不下 → 仍取第一档（会被压缩）
    assert theme.best_fit_size(1100, 820) == "1100x800"  # 只放得下 1100×800 → 降级到它


def test_small_screen_does_not_look_like_custom() -> None:
    """小屏上把预设压缩后，下拉条不能显示「自定义」（CI 暴露的真实缺陷）。"""
    # 1024×768：680×880 放不下 → 压缩成 680×768，但仍应识别为"选了 680×880"
    assert resolve_window_size("680x880", "680x768", 1024, 768) == "680x880"
    assert resolve_window_size(None, "680x768", 1024, 768) == "680x880"
    # 真正的自定义（用户拖出来的尺寸）仍要判成 custom
    assert resolve_window_size(None, "900x700", 1024, 768) == WINDOW_SIZE_CUSTOM
    assert resolve_window_size("680x880", "900x700", 1024, 768) == WINDOW_SIZE_CUSTOM


def test_manual_resize_is_detected_without_ambiguous_false_positives() -> None:
    """小屏上"窗口被压缩"与"用户拖过"必须分得清。"""
    # 正好等于预设 → 不是手动调整
    assert geometry_proves_a_manual_resize("680x880", "680x880", 1024, 768) is False
    # 恰好等于预设被压缩的结果 → 含糊，保守判为"没拖过"
    assert geometry_proves_a_manual_resize("680x880", "680x768", 1024, 768) is False
    # 明显不同的尺寸 → 判为手动调整
    assert geometry_proves_a_manual_resize("680x880", "900x700", 1024, 768) is True
    # 拉满整屏 → 判为手动调整（预设都放不下，说明用户改了）
    assert geometry_proves_a_manual_resize("680x880", "1024x768", 1024, 768) is True


def test_first_run_centers_the_window(root: tk.Tk, store: ConfigStore) -> None:
    """首次运行（配置里没有位置）时窗口应被摆到屏幕中间，而不是左上角。"""
    window = MainWindow(root, store=store, config=Config(api_key=KEY))
    window._initial_geometry()  # 居中与否在这里判定（_build 已调用过一次）
    assert window._needs_centering is True, "没存过位置就该居中"


def test_saved_position_is_kept(root: tk.Tk, store: ConfigStore) -> None:
    """用户自己摆过的位置不能被"居中"覆盖。"""
    config = Config(api_key=KEY)
    config.ui.window_geometry = "1000x760+120+80"
    window = MainWindow(root, store=store, config=config)
    window._initial_geometry()
    assert window._needs_centering is False


def test_migrated_legacy_size_drops_the_stale_position(root: tk.Tk, store: ConfigStore) -> None:
    """旧默认 800×600 带位置后缀迁移到 800×1100 时，位置要丢弃（尺寸变了）。

    必须走**真实读盘路径**（``Config.from_dict``）：迁移就发生在那一步，
    直接构造 ``Config`` 对象会绕过它。
    """
    store.ensure_dirs()
    store.config_path.write_text(
        '{"schema_version": 1, "api_key": "' + KEY + '",'
        ' "ui": {"window_geometry": "800x600+100+100"}}',
        encoding="utf-8",
    )
    result = store.load()
    assert result.config.ui.window_geometry == DEFAULT_GEOMETRY, "迁移应改写尺寸并丢弃旧位置"

    window = MainWindow(root, store=store, config=result.config)
    assert "+100" not in window._initial_geometry()
    assert window._needs_centering is True, "尺寸被迁移过就应该重新居中"


def test_user_chosen_size_keeps_its_position(root: tk.Tk, store: ConfigStore) -> None:
    """用户自己拉大的尺寸不属于迁移范围，位置必须保留（尺寸本身会按屏幕收敛）。"""
    store.ensure_dirs()
    store.config_path.write_text(
        '{"schema_version": 1, "api_key": "' + KEY + '",'
        ' "ui": {"window_geometry": "1400x900+120+80"}}',
        encoding="utf-8",
    )
    result = store.load()
    window = MainWindow(root, store=store, config=result.config)

    world_width, world_height = screen_size(root)
    expected = clamp_geometry("1400x900+120+80", world_width, world_height)
    assert window._initial_geometry() == expected
    assert window._needs_centering is False
    assert "+120+80" in expected


def test_offscreen_saved_position_is_discarded(root: tk.Tk, store: ConfigStore) -> None:
    config = Config(api_key=KEY)
    config.ui.window_geometry = "1000x760+5000+5000"  # 例如拔掉副屏后留下的位置
    window = MainWindow(root, store=store, config=config)
    assert "+5000" not in window._initial_geometry()


def test_apply_default_geometry_resets_and_persists(root: tk.Tk, store: ConfigStore) -> None:
    config = Config(api_key=KEY)
    config.ui.window_geometry = "1500x950"
    window = MainWindow(root, store=store, config=config)
    window.save_now()

    geometry = window.apply_default_geometry("1100x800")

    assert parse_geometry(geometry) == clamped("1100x800", root)
    assert window.config.ui.window_size == "1100x800"
    assert window.config.ui.window_geometry == geometry
    assert store.load().config.ui.window_geometry == geometry


def test_reset_uses_the_selected_preset(root: tk.Tk, store: ConfigStore) -> None:
    """用户明确要求：恢复默认的值 = 尺寸选择框里的值。"""
    window = MainWindow(root, store=store, config=Config(api_key=KEY))

    assert parse_geometry(window.apply_default_geometry("680x880")) == clamped("680x880", root)
    assert parse_geometry(window.apply_default_geometry("1100x800")) == clamped("1100x800", root)
    assert window.config.ui.window_size == "1100x800"


def test_settings_dialog_exposes_the_size_dropdown(root: tk.Tk, store: ConfigStore) -> None:
    """用户要求：尺寸选择改成**下拉条**，点一下展开全部预设值。"""
    window = MainWindow(root, store=store, config=Config(api_key=KEY))
    window.config.ui.window_geometry = "1500x950"  # 手动拖过 → 自定义
    window.on_settings()
    dialog = window._settings_dialog
    assert dialog is not None
    try:
        # 下拉条必须是只读的 Combobox，且列出全部预设 + 自定义
        assert str(dialog.window_size_combo.cget("state")) == "readonly"
        values = tuple(dialog.window_size_combo.cget("values"))
        for choice in WINDOW_SIZE_CHOICES:
            assert dialog._size_label(choice) in values
        assert dialog._size_label(WINDOW_SIZE_CUSTOM) in values
        assert dialog.selected_window_size() == WINDOW_SIZE_CUSTOM

        # 选中一个预设再点恢复 → 窗口按该预设调整
        dialog.select_window_size("1100x800")
        assert dialog.selected_window_size() == "1100x800"
        dialog.reset_window_size()
        assert window.config.ui.window_size == "1100x800"
        assert parse_geometry(window.config.ui.window_geometry) == clamped("1100x800", root)
        assert "已按所选尺寸" in dialog.error_text()
    finally:
        dialog.close()


def test_default_selection_is_the_first_preset(root: tk.Tk, store: ConfigStore) -> None:
    """全新配置下，下拉条默认选中当前屏幕下最合适的预设（够大时就是 680×880）。"""
    world_width, world_height = screen_size(root)
    expected = theme.best_fit_size(world_width, world_height)

    window = MainWindow(root, store=store, config=Config(api_key=KEY))
    window.on_settings()
    dialog = window._settings_dialog
    assert dialog is not None
    try:
        assert dialog.selected_window_size() == expected
        assert dialog.window_size_var.get() == dialog._size_label(expected)
        if world_width >= 680 and world_height >= 880:
            assert expected == DEFAULT_GEOMETRY == "680x880"
    finally:
        dialog.close()


def test_settings_reset_without_a_preset_asks_for_one(root: tk.Tk, store: ConfigStore) -> None:
    """选中「自定义」时没有可恢复的目标，应给提示而不是默默套别的尺寸。"""
    window = MainWindow(root, store=store, config=Config(api_key=KEY))
    window.on_settings()
    dialog = window._settings_dialog
    assert dialog is not None
    try:
        dialog.select_window_size(WINDOW_SIZE_CUSTOM)
        before = window.config.ui.window_geometry
        dialog.reset_window_size()
        assert window.config.ui.window_geometry == before, "不该偷偷改尺寸"
        assert "请先选择" in dialog.error_text()
    finally:
        dialog.close()


def test_save_applies_the_selected_size(root: tk.Tk, store: ConfigStore) -> None:
    """保存设置时若选了预设，窗口尺寸立即生效并落盘。"""
    window = MainWindow(root, store=store, config=Config(api_key=KEY))
    window.on_settings()
    dialog = window._settings_dialog
    assert dialog is not None
    try:
        dialog.select_window_size("1100x800")
        assert dialog.save() is True
    finally:
        dialog.close()

    saved = store.load().config
    assert saved.ui.window_size == "1100x800"
    assert parse_geometry(saved.ui.window_geometry) == clamped("1100x800", root)


def test_settings_buttons_have_equal_size(root: tk.Tk, store: ConfigStore) -> None:
    """用户反馈：保存与取消按钮一大一小，必须一样大。"""
    dialog = SettingsDialog(root, config=Config(api_key=KEY), store=store)
    try:
        dialog.window.update_idletasks()
        save = (
            dialog.save_button.winfo_reqwidth(),
            dialog.save_button.winfo_reqheight(),
        )
        cancel = (
            dialog.cancel_button.winfo_reqwidth(),
            dialog.cancel_button.winfo_reqheight(),
        )
        assert save == cancel, f"保存按钮 {save} 与取消按钮 {cancel} 尺寸不一致"
    finally:
        dialog.close()


def test_settings_dialog_is_centered(root: tk.Tk, store: ConfigStore) -> None:
    """用户反馈：设置窗口每次都弹在屏幕左上角，应该居中。"""
    dialog = SettingsDialog(root, config=Config(api_key=KEY), store=store)
    try:
        dialog.window.update_idletasks()
        left, top = dialog.center_on_screen()
        expected_left = max(0, (dialog.window.winfo_screenwidth() - dialog.window.winfo_reqwidth()) // 2)
        expected_top = max(0, (dialog.window.winfo_screenheight() - dialog.window.winfo_reqheight()) // 2)
        assert (left, top) == (expected_left, expected_top)
        assert left > 0 and top > 0, "屏幕中间不可能贴着左上角"
    finally:
        dialog.close()


def test_history_dialog_is_centered(root: tk.Tk, store: ConfigStore, tmp_path: Path) -> None:
    window = MainWindow(root, store=store, config=Config(api_key=KEY))
    dialog = window.open_history()
    try:
        dialog.window.update_idletasks()
        geometry = dialog.window.geometry()
        left = int(geometry.split("+")[1])
        top = int(geometry.split("+")[2])
        assert left > 0 and top > 0, f"记录窗口没有居中：{geometry}"
    finally:
        dialog.close()


def test_settings_reset_callback_is_optional(root: tk.Tk, store: ConfigStore) -> None:
    """首次引导窗也复用同一个对话框；没传回调时点按钮不能崩。"""
    dialog = SettingsDialog(
        root, config=Config(api_key=KEY), store=store, on_reset_geometry=None
    )
    try:
        dialog.reset_window_size()  # 不应抛异常
    finally:
        dialog.close()
