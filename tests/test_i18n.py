"""多语言（中文 / 英文）测试。

核心思路：

* **中文是默认语言**，且中文文案与改版前完全一致，因此既有的 400+ 项测试
  本身就是中文模式的回归网；
* 英文模式最怕"漏译"（界面上残留中文），所以有一条**扫描全部控件文本、
  断言不含中日韩字符**的测试 —— 漏一个键就会失败；
* 语言切换是"就地重建界面"，必须保证已加载的库、勾选状态与抽签结果不丢。

注意：语言选择器里的「中文」是**自名**（不随当前语言变化），属白名单。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from tkinter import ttk

from app import i18n
from app.cache import GameCache
from app.config import LANGUAGE_EN, LANGUAGE_ZH, VALID_LANGUAGES, Config, ConfigStore
from app.errors import Err, message, status
from app.models import Game, GameDetails, format_playtime
from app.pool import PRESET_ALL, preset_label
from app.state import AppState, controls_for
from app.ui.main_window import MainWindow
from app.ui.settings_dialog import AboutDialog, SettingsDialog

CJK = re.compile(r"[\u3000-\u303f\u3400-\u4dbf\u4e00-\u9fff\uff00-\uffef]")
KEY = "K" * 32
VALID_KEY_HEX = "0123456789abcdef0123456789ABCDEF"

GAMES = [
    Game(appid=1, name="Alpha Quest", playtime_forever=0),
    Game(appid=2, name="Beta Shooter", playtime_forever=30),
    Game(appid=3, name="Gamma Sim", playtime_forever=5000),
]

DETAILS = GameDetails(
    appid=3,
    name="Gamma Sim",
    short_description="A short description.",
    genres=("Simulation",),
    release_date="2016-02-26",
    metacritic_score=89,
    price_initial="¥ 48",
)


@pytest.fixture()
def store(tmp_path: Path) -> ConfigStore:
    instance = ConfigStore(tmp_path / "SteamGamePicker")
    instance.ensure_dirs()
    return instance


def make_window(root, store: ConfigStore, language: str) -> MainWindow:
    config = Config(api_key=KEY, language=language)
    window = MainWindow(root, store=store, config=config)
    window.set_games(GAMES, updated_at="2026-09-19T15:04:05+08:00")
    return window


def widget_texts(widget) -> list[str]:
    """递归收集控件上的可见文本（Label/Button/勾选项/表头）。"""
    collected: list[str] = []
    try:
        collected.append(str(widget.cget("text")))
    except Exception:
        pass
    try:
        if isinstance(widget, ttk.Treeview):
            for column in widget["columns"]:
                collected.append(str(widget.heading(column, "text")))
    except Exception:
        pass
    for child in widget.winfo_children():
        collected.extend(widget_texts(child))
    return [text for text in collected if text.strip()]


def allowed_cjk(text: str) -> bool:
    """语言选择器里的自名（中文 / English）以及占位符不算漏译。"""
    return any(name in text for name in i18n.LANGUAGE_NAMES.values())


# ------------------------------------------------------------------ 文案表
def test_default_language_is_chinese() -> None:
    assert i18n.DEFAULT_LANGUAGE == LANGUAGE_ZH
    i18n.set_language(None)
    assert i18n.get_language() == LANGUAGE_ZH


def test_both_tables_have_the_same_keys() -> None:
    """键集合必须完全一致，否则某种语言下一定漏译。"""
    zh_keys = set(i18n.TRANSLATIONS[LANGUAGE_ZH])
    en_keys = set(i18n.TRANSLATIONS[LANGUAGE_EN])
    assert zh_keys == en_keys, f"仅中文有：{zh_keys - en_keys}；仅英文有：{en_keys - zh_keys}"


@pytest.mark.parametrize("language", VALID_LANGUAGES)
def test_no_empty_translations(language: str) -> None:
    empty = [key for key, value in i18n.TRANSLATIONS[language].items() if not value.strip()]
    assert not empty, f"{language} 下这些键为空：{empty}"


def test_placeholders_match_between_languages() -> None:
    """同名占位符必须在两种语言里都出现，否则 format 会抛 KeyError/留下花括号。"""
    pattern = re.compile(r"\{(\w+)\}")
    for key, zh_text in i18n.TRANSLATIONS[LANGUAGE_ZH].items():
        en_text = i18n.TRANSLATIONS[LANGUAGE_EN][key]
        assert set(pattern.findall(zh_text)) == set(pattern.findall(en_text)), key


def test_missing_key_is_loud() -> None:
    """漏键要显式暴露，而不是静默显示空白。"""
    assert i18n.t("no.such.key") == "⟦no.such.key⟧"


def test_invalid_language_falls_back() -> None:
    assert i18n.set_language("fr") == LANGUAGE_ZH
    assert i18n.set_language("") == LANGUAGE_ZH
    assert i18n.set_language(LANGUAGE_EN) == LANGUAGE_EN


def test_english_messages_are_english() -> None:
    i18n.set_language(LANGUAGE_EN)
    assert not CJK.search(message(Err.PRIVATE_PROFILE).text)
    assert "public" in message(Err.PRIVATE_PROFILE).text
    assert not CJK.search(status("pool_empty").text)
    assert not CJK.search(format_playtime(0))
    assert not CJK.search(preset_label(PRESET_ALL))
    assert not CJK.search(controls_for(AppState.DRAWING).draw_label)


def test_chinese_messages_unchanged() -> None:
    """中文模式必须与改造前逐字一致（既有测试也依赖这一点）。"""
    i18n.set_language(LANGUAGE_ZH)
    assert message(Err.PRIVATE_PROFILE).text == "无法读取游戏库，请将 Steam 个人资料和游戏详情设为公开"
    assert status("pool_empty").text == "当前范围内没有可抽签的游戏，请调整范围"
    assert format_playtime(744) == "12.4 小时"
    assert preset_label(PRESET_ALL) == "全部参与"
    assert controls_for(AppState.DRAWING).draw_label == "抽签中…"


# ------------------------------------------------------- 英文界面不得残留中文
def test_english_main_window_has_no_chinese(root, store: ConfigStore) -> None:
    window = make_window(root, store, LANGUAGE_EN)
    window.toggle_pool_panel(expand=True)
    window.toggle_game(2)
    window.winner = GAMES[2]
    window._on_anim_frame(window.winner.name, True)
    window.render_details(DETAILS)
    window.refresh_state()

    leftovers = [
        text for text in widget_texts(window.root) if CJK.search(text) and not allowed_cjk(text)
    ]
    assert not leftovers, f"英文界面残留中文：{leftovers[:8]}"


def test_english_dialogs_have_no_chinese(root, store: ConfigStore) -> None:
    i18n.set_language(LANGUAGE_EN)
    settings = SettingsDialog(root, config=Config(api_key=KEY), store=store)
    about = AboutDialog(root, store=store)
    try:
        for dialog in (settings, about):
            leftovers = [
                text
                for text in widget_texts(dialog.window)
                if CJK.search(text) and not allowed_cjk(text)
            ]
            assert not leftovers, f"{dialog.window.title()} 残留中文：{leftovers[:8]}"
    finally:
        settings.close()
        about.close()


def test_chinese_main_window_has_chinese(root, store: ConfigStore) -> None:
    """反向确认：中文模式下界面确实是中文（避免"两种语言都一样"）。"""
    window = make_window(root, store, LANGUAGE_ZH)
    texts = widget_texts(window.root)
    assert any("加载游戏库" in text for text in texts)
    assert any("抽签" in text for text in texts)


# ------------------------------------------------------------------ 语言切换
def test_language_switch_rebuilds_ui_and_keeps_state(root, store: ConfigStore) -> None:
    window = make_window(root, store, LANGUAGE_ZH)
    window.toggle_pool_panel(expand=True)
    window.toggle_game(2)
    window.search_var.set("Gamma")
    window.apply_search()
    window.winner = GAMES[2]
    window._on_anim_frame(window.winner.name, True)
    window.render_details(DETAILS)
    window.refresh_state()

    before_state = window.state
    window.config.language = LANGUAGE_EN
    window.on_settings_saved()  # 设置窗保存后走的就是这条路径

    assert i18n.get_language() == LANGUAGE_EN
    texts = widget_texts(window.root)
    assert any("Load Library" in text for text in texts)
    assert not [t for t in texts if CJK.search(t) and not allowed_cjk(t)]

    # 数据与状态必须原样保留
    assert [g.appid for g in window.games] == [1, 2, 3]
    assert window.excluded == {2}
    assert window.query == "Gamma"
    assert [g.appid for g in window.filtered] == [3]
    assert window.winner is not None and window.winner.appid == 3
    assert str(window.rolling_label.cget("text")) == "Gamma Sim"
    assert str(window.detail_name.cget("text")) == "Gamma Sim"
    assert window.pool_panel_expanded is True
    assert window.state is before_state


def test_settings_dialog_exposes_language_and_persists_it(
    root, store: ConfigStore
) -> None:
    config = Config(api_key=KEY)
    window = MainWindow(root, store=store, config=config)
    window.on_settings()
    dialog = window._settings_dialog
    assert dialog is not None

    assert set(dialog.language_buttons) == set(VALID_LANGUAGES)
    assert dialog.language_var.get() == LANGUAGE_ZH, "默认必须是中文"
    assert str(dialog.language_buttons[LANGUAGE_ZH].cget("text")) == "中文"
    assert str(dialog.language_buttons[LANGUAGE_EN].cget("text")) == "English"

    dialog.key_var.set(VALID_KEY_HEX)  # 通过 API Key 格式校验才能走到保存
    dialog.language_var.set(LANGUAGE_EN)
    assert dialog.save() is True

    assert store.load().config.language == LANGUAGE_EN
    assert i18n.get_language() == LANGUAGE_EN
    assert str(window.load_button.cget("text")) == "Load Library"
    window._settings_dialog = None


def test_language_persists_across_restart(root, store: ConfigStore) -> None:
    config = Config(api_key=KEY, language=LANGUAGE_EN)
    MainWindow(root, store=store, config=config)
    config_store = store
    config_store.save(config)

    reopened = MainWindow(root, store=store, config=store.load().config)
    assert reopened.config.language == LANGUAGE_EN
    assert str(reopened.load_button.cget("text")) == "Load Library"


def test_invalid_language_in_config_falls_back_to_chinese(store: ConfigStore) -> None:
    store.save(Config(api_key=KEY, language="klingon"))
    assert store.load().config.language == LANGUAGE_ZH


def test_english_snapshot_message(root, store: ConfigStore) -> None:
    window = make_window(root, store, LANGUAGE_EN)
    assert "games loaded" in window.status_text()
    assert "updated" in window.status_text()


def test_english_empty_pool_hint(root, store: ConfigStore) -> None:
    window = make_window(root, store, LANGUAGE_EN)
    window.excluded = {1, 2, 3}
    window.refresh_state()
    assert window.state is AppState.EMPTY_POOL
    assert "No games in the current range" in window.status_text()


def test_cache_and_details_still_work_in_english(root, store: ConfigStore) -> None:
    """英文模式下缓存与详情渲染不受影响（顺手覆盖 detail 文案）。"""
    cache = GameCache(store)
    cache.put_detail(DETAILS)
    window = make_window(root, store, LANGUAGE_EN)
    window.load_details(DETAILS.appid)
    assert str(window.detail_name.cget("text")) == "Gamma Sim"
    assert str(window.detail_extra.cget("text")).startswith("Price")
