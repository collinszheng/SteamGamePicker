"""T1.2 数据模型与展示格式化测试（PRD 5.3 / 5.5 的显示规则）。"""

from __future__ import annotations

import pytest

from app.models import (
    PLACEHOLDER,
    Game,
    GameDetails,
    details_meta_line,
    details_price_line,
    display_or_placeholder,
    format_playtime,
)


@pytest.mark.parametrize(
    ("minutes", "expected"),
    [
        (0, "未玩过"),
        (-5, "未玩过"),
        (1, "不足 1 小时"),
        (59, "不足 1 小时"),
        (60, "1.0 小时"),
        (744, "12.4 小时"),
        (51726, "862.1 小时"),
    ],
)
def test_format_playtime(minutes: int, expected: str) -> None:
    assert format_playtime(minutes) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [(None, PLACEHOLDER), ("", PLACEHOLDER), ("   ", PLACEHOLDER), ("x", "x"), (0, "0")],
)
def test_display_or_placeholder(value: object, expected: str) -> None:
    assert display_or_placeholder(value) == expected


def test_game_roundtrip() -> None:
    game = Game(appid=570, name="Dota 2", playtime_forever=1234, img_icon_url="abc")
    assert Game.from_dict(game.to_dict()) == game


def test_game_from_dict_tolerates_dirty_data() -> None:
    game = Game.from_dict(
        {"appid": "570", "name": "X", "playtime_forever": "abc", "img_icon_url": None}
    )
    assert game.appid == 570
    assert game.playtime_forever == 0
    assert game.img_icon_url == ""


def test_game_icon_url() -> None:
    assert Game(appid=1, name="x").icon_url is None
    assert (
        Game(appid=570, name="x", img_icon_url="hash").icon_url
        == "https://media.steampowered.com/steamcommunity/public/images/apps/570/hash.jpg"
    )


def test_details_texts_use_placeholder_for_missing_values() -> None:
    details = GameDetails(appid=1)
    assert details.genres_text == PLACEHOLDER
    assert details.score_text == PLACEHOLDER
    assert details.release_text == PLACEHOLDER
    assert details.price_text == PLACEHOLDER


def test_details_texts_render_values() -> None:
    details = GameDetails(
        appid=1,
        name="游戏",
        genres=("模拟", "角色扮演"),
        release_date="2016-02-26",
        metacritic_score=89,
        price_initial="¥ 48",
    )
    assert details.genres_text == "模拟 · 角色扮演"
    assert details.score_text == "89"
    assert details.release_text == "2016-02-26"
    assert details.price_text == "¥ 48"


def test_free_game_shows_free_and_ignores_price() -> None:
    """AC-26：免费游戏显示"免费"。"""
    details = GameDetails(appid=1, is_free=True, price_initial="¥ 48")
    assert details.price_text == "免费"


def test_discounted_game_only_shows_original_price() -> None:
    """AC-27 / PRD D7：只显示未打折的原价，界面不出现折扣信息。"""
    details = GameDetails(appid=1, is_free=False, price_initial="¥ 48")
    assert details.price_text == "¥ 48"
    assert "%" not in details.price_text
    assert "折" not in details.price_text


def test_details_roundtrip() -> None:
    details = GameDetails(
        appid=570,
        name="Dota 2",
        header_image="https://cdn/x.jpg",
        short_description="简介",
        genres=("免费开玩",),
        release_date="2013-07-09",
        metacritic_score=90,
        is_free=True,
        price_initial=None,
        available=True,
    )
    assert GameDetails.from_dict(details.to_dict()) == details


def test_details_from_dict_tolerates_dirty_data() -> None:
    details = GameDetails.from_dict(
        {
            "appid": "570",
            "genres": "不是列表",
            "metacritic_score": "89",
            "is_free": 1,
            "price_initial": "",
        }
    )
    assert details.appid == 570
    assert details.genres == ()
    assert details.metacritic_score is None
    assert details.is_free is True
    assert details.price_initial is None


def test_details_meta_line_joins_available_fields() -> None:
    full = GameDetails(
        appid=1,
        genres=("模拟", "角色扮演"),
        release_date="2016-02-26",
        metacritic_score=89,
    )
    assert details_meta_line(full) == "模拟 · 角色扮演 · 2016-02-26 · Metacritic 89"

    partial = GameDetails(appid=1, genres=("模拟",))
    assert details_meta_line(partial) == "模拟"

    empty = GameDetails(appid=1)
    assert details_meta_line(empty) == PLACEHOLDER


def test_details_price_line() -> None:
    assert details_price_line(GameDetails(appid=1, price_initial="¥ 48")) == "售价 ¥ 48"
    assert details_price_line(GameDetails(appid=1, is_free=True)) == "售价 免费"
    assert details_price_line(GameDetails(appid=1)) == f"售价 {PLACEHOLDER}"
