"""T1.1 输入解析测试（AC-01 / AC-02 / AC-03 的解析部分）。"""

from __future__ import annotations

import pytest

from app.errors import AppError, Err
from app.steamid import KIND_STEAMID64, KIND_VANITY, parse_input

STEAMID = "76561198260031749"


@pytest.mark.parametrize(
    "raw",
    [
        STEAMID,
        f"  {STEAMID}  ",
        f"https://steamcommunity.com/profiles/{STEAMID}",
        f"https://steamcommunity.com/profiles/{STEAMID}/",
        f"https://steamcommunity.com/profiles/{STEAMID}?tab=games",
        f"https://steamcommunity.com/profiles/{STEAMID}/games?tab=all",
        f"https://STEAMCOMMUNITY.com/profiles/{STEAMID}",
    ],
)
def test_steamid64_inputs(raw: str) -> None:
    parsed = parse_input(raw)
    assert parsed.kind == KIND_STEAMID64
    assert parsed.value == STEAMID
    assert parsed.is_steamid64 is True
    assert parsed.needs_resolve is False


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("https://steamcommunity.com/id/customname", "customname"),
        ("https://steamcommunity.com/id/Custom-Name_123/", "Custom-Name_123"),
        ("https://steamcommunity.com/id/xxx?tab=games", "xxx"),
        ("https://steamcommunity.com/id/name/games", "name"),
        ("customname", "customname"),
        ("  my_name  ", "my_name"),
        ("ab", "ab"),
        # PRD 5.2 规则 4：其余非空字符串一律视为自定义名，
        # 由 ResolveVanityURL 判定是否存在，因此"数字+字母"的输错也走这条路。
        ("7656119826003174a", "7656119826003174a"),
    ],
)
def test_vanity_inputs(raw: str, expected: str) -> None:
    parsed = parse_input(raw)
    assert parsed.kind == KIND_VANITY
    assert parsed.value == expected
    assert parsed.needs_resolve is True


@pytest.mark.parametrize("raw", ["", "   ", None])
def test_empty_input(raw: str | None) -> None:
    """AC-02：空输入给出"请先输入"，不发起请求。"""
    with pytest.raises(AppError) as info:
        parse_input(raw)
    assert info.value.err is Err.EMPTY_INPUT


@pytest.mark.parametrize(
    "raw",
    [
        "12345",
        "7656119826003174",  # 16 位
        "765611982600317490",  # 18 位
        "https://steamcommunity.com/profiles/12345",
        "https://steamcommunity.com/profiles/",
        "a",
        "not a valid name!",
        "https://example.com/foo",
    ],
)
def test_unrecognized_input(raw: str) -> None:
    with pytest.raises(AppError) as info:
        parse_input(raw)
    assert info.value.err is Err.BAD_FORMAT
