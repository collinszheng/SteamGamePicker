"""T2.1–T2.6 网络层测试（AC-03 / AC-06 / AC-07 / AC-08 / AC-25 ~ AC-28）。

全部脱机运行：用 tests/support.py 的假会话 + fixtures 样本，
断言的是 PRD 7.6 记录的 Steam 行为契约。
"""

from __future__ import annotations

import json

import pytest
import requests

from app.cancellation import CancelToken, Cancelled
from app.errors import AppError, Err
from app.steam_api import (
    REQUEST_TIMEOUT,
    RETRY_DELAYS,
    SteamClient,
    parse_app_details,
)
from support import FakeResponse, FakeSession, load_fixture

STEAMID = "76561198260031749"
KEY = "A" * 32
CANCELLED_TOKEN = CancelToken()


@pytest.fixture()
def sleeps() -> list[float]:
    return []


@pytest.fixture()
def session() -> FakeSession:
    return FakeSession()


@pytest.fixture()
def client(session: FakeSession, sleeps: list[float]) -> SteamClient:
    return SteamClient(KEY, session=session, sleeper=sleeps.append)


# ---------------------------------------------------------------- 自定义名解析
def test_resolve_vanity_ok(client: SteamClient, session: FakeSession) -> None:
    session.add("ResolveVanityURL", FakeResponse(200, load_fixture("resolve_vanity_ok.json")))
    assert client.resolve_vanity("customname") == STEAMID

    call = session.calls[0]
    assert call["params"]["vanityurl"] == "customname"
    assert call["params"]["key"] == KEY
    assert call["timeout"] == REQUEST_TIMEOUT == 10


def test_resolve_vanity_no_match_returns_success_42(
    client: SteamClient, session: FakeSession
) -> None:
    """AC-03：success:42（HTTP 200）必须映射为"无法解析该资料地址"。"""
    session.add("ResolveVanityURL", FakeResponse(200, load_fixture("resolve_vanity_notfound.json")))
    with pytest.raises(AppError) as info:
        client.resolve_vanity("nobody")
    assert info.value.err is Err.VANITY_NOT_FOUND
    assert "无法解析该资料地址" in info.value.message.text


def test_resolve_vanity_missing_steamid(client: SteamClient, session: FakeSession) -> None:
    session.add("ResolveVanityURL", FakeResponse(200, {"response": {"success": 1}}))
    with pytest.raises(AppError) as info:
        client.resolve_vanity("x")
    assert info.value.err is Err.VANITY_NOT_FOUND


def test_api_key_is_required_for_identity_calls(session: FakeSession) -> None:
    client = SteamClient("", session=session)
    with pytest.raises(AppError) as info:
        client.resolve_vanity("x")
    assert info.value.err is Err.NO_KEY
    assert session.calls == []


# ------------------------------------------------------------------ 错误分类
@pytest.mark.parametrize("status", [401, 403])
def test_invalid_key_mapping(client: SteamClient, session: FakeSession, status: int) -> None:
    """AC-08：无效 Key 必须提示"Key 无效或已停用"。"""
    session.add("ResolveVanityURL", FakeResponse(status, {}))
    with pytest.raises(AppError) as info:
        client.resolve_vanity("x")
    assert info.value.err is Err.INVALID_KEY


def test_rate_limit_retries_then_reports(
    client: SteamClient, session: FakeSession, sleeps: list[float]
) -> None:
    session.add("ResolveVanityURL", FakeResponse(429, {}))
    with pytest.raises(AppError) as info:
        client.resolve_vanity("x")
    assert info.value.err is Err.RATE_LIMIT
    assert len(session.calls) == 3
    assert sleeps == list(RETRY_DELAYS) == [1.0, 3.0]


def test_rate_limit_then_success(
    client: SteamClient, session: FakeSession, sleeps: list[float]
) -> None:
    session.add(
        "ResolveVanityURL",
        [FakeResponse(429, {}), FakeResponse(200, load_fixture("resolve_vanity_ok.json"))],
    )
    assert client.resolve_vanity("x") == STEAMID
    assert sleeps == [1.0]
    assert len(session.calls) == 2


@pytest.mark.parametrize("status", [500, 502, 503, 504])
def test_server_errors_retry_then_report(
    client: SteamClient, session: FakeSession, sleeps: list[float], status: int
) -> None:
    session.add("ResolveVanityURL", FakeResponse(status, {}))
    with pytest.raises(AppError) as info:
        client.resolve_vanity("x")
    assert info.value.err is Err.NETWORK
    assert sleeps == [1.0, 3.0]


@pytest.mark.parametrize(
    "exception",
    [requests.Timeout("超时"), requests.ConnectionError("断网"), requests.RequestException("err")],
)
def test_transport_errors_map_to_network(
    client: SteamClient, session: FakeSession, exception: Exception
) -> None:
    session.add("ResolveVanityURL", exception)
    with pytest.raises(AppError) as info:
        client.resolve_vanity("x")
    assert info.value.err is Err.NETWORK
    assert len(session.calls) == 1, "传输层错误不做重试"


def test_unexpected_status_maps_to_network(client: SteamClient, session: FakeSession) -> None:
    session.add("ResolveVanityURL", FakeResponse(418, {}))
    with pytest.raises(AppError) as info:
        client.resolve_vanity("x")
    assert info.value.err is Err.NETWORK


def test_non_json_body_maps_to_network(client: SteamClient, session: FakeSession) -> None:
    session.add("ResolveVanityURL", FakeResponse(200, None))
    with pytest.raises(AppError) as info:
        client.resolve_vanity("x")
    assert info.value.err is Err.NETWORK


# -------------------------------------------------------------------- 游戏库
def test_owned_games_ok_and_dirty_data_filtered(
    client: SteamClient, session: FakeSession
) -> None:
    session.add("GetOwnedGames", FakeResponse(200, load_fixture("owned_games_public.json")))
    games = client.get_owned_games(STEAMID)

    assert [g.appid for g in games] == [570, 413150, 730]
    assert games[0].name == "Dota 2"
    assert games[0].playtime_forever == 12345
    assert games[0].icon_url is not None and "icon-570" in games[0].icon_url
    assert games[2].icon_url is None

    params = session.calls[0]["params"]
    assert params["steamid"] == STEAMID
    assert params["include_appinfo"] == "true"
    assert params["include_played_free_games"] == "true"


def test_private_profile_is_distinguished_from_empty_library(
    client: SteamClient, session: FakeSession
) -> None:
    """AC-06：私密资料是 HTTP 200 + 无 games 键，绝不能报成"库为空"。"""
    session.add("GetOwnedGames", FakeResponse(200, load_fixture("owned_games_private.json")))
    with pytest.raises(AppError) as info:
        client.get_owned_games(STEAMID)
    assert info.value.err is Err.PRIVATE_PROFILE
    assert "设为公开" in info.value.message.text


def test_empty_library_reports_empty_library(
    client: SteamClient, session: FakeSession
) -> None:
    """AC-07：真的没有游戏才提示"未找到任何游戏"。"""
    session.add("GetOwnedGames", FakeResponse(200, load_fixture("owned_games_empty.json")))
    with pytest.raises(AppError) as info:
        client.get_owned_games(STEAMID)
    assert info.value.err is Err.EMPTY_LIBRARY


def test_owned_games_wrong_type_maps_to_network(
    client: SteamClient, session: FakeSession
) -> None:
    session.add("GetOwnedGames", FakeResponse(200, {"response": {"games": "不是列表"}}))
    with pytest.raises(AppError) as info:
        client.get_owned_games(STEAMID)
    assert info.value.err is Err.NETWORK


def test_owned_games_response_not_object(client: SteamClient, session: FakeSession) -> None:
    session.add("GetOwnedGames", FakeResponse(200, {"response": []}))
    with pytest.raises(AppError) as info:
        client.get_owned_games(STEAMID)
    assert info.value.err is Err.NETWORK


# ---------------------------------------------------------------------- 详情
def test_app_details_free_game(client: SteamClient, session: FakeSession) -> None:
    """AC-26：免费游戏无 price_overview，售价显示"免费"。"""
    session.add("appdetails", FakeResponse(200, load_fixture("appdetails_free.json")))
    details = client.get_app_details(570)
    assert details is not None
    assert details.name == "Dota 2"
    assert details.is_free is True
    assert details.price_initial is None
    assert details.price_text == "免费"
    assert details.metacritic_score == 90
    assert details.genres == ("动作", "免费开玩")
    assert details.release_date == "2013 年 7 月 9 日"

    params = session.calls[0]["params"]
    assert params["cc"] == "CN"
    assert params["l"] == "schinese"
    assert "key" not in params, "详情接口不需要 API Key"


def test_app_details_discounted_game_keeps_original_price(
    client: SteamClient, session: FakeSession
) -> None:
    """AC-27 / PRD D7：只保留未打折原价 ¥ 48，不得使用折扣价 ¥ 41。"""
    session.add("appdetails", FakeResponse(200, load_fixture("appdetails_paid_discounted.json")))
    details = client.get_app_details(413150)
    assert details is not None
    assert details.price_initial == "¥ 48"
    assert details.price_text == "¥ 48"
    assert details.metacritic_score is None
    assert details.score_text == "—"


def test_app_details_without_api_key_is_allowed(session: FakeSession) -> None:
    client = SteamClient("", session=session)
    session.add("appdetails", FakeResponse(200, load_fixture("appdetails_free.json")))
    assert client.get_app_details(570) is not None


def test_app_details_success_false_returns_none(
    client: SteamClient, session: FakeSession
) -> None:
    """AC-28：success:false → 返回 None，界面走降级提示。"""
    session.add("appdetails", FakeResponse(200, load_fixture("appdetails_failed.json")))
    assert client.get_app_details(999999) is None


def test_app_details_missing_entry_returns_none(client: SteamClient, session: FakeSession) -> None:
    session.add("appdetails", FakeResponse(200, {}))
    assert client.get_app_details(1) is None


def test_app_details_missing_data_returns_none(client: SteamClient, session: FakeSession) -> None:
    session.add("appdetails", FakeResponse(200, {"1": {"success": True}}))
    assert client.get_app_details(1) is None


def test_parse_app_details_price_fallback_and_dirty_data() -> None:
    details = parse_app_details(
        1,
        {
            "name": "  带空格  ",
            "genres": ["不是字典", {"description": "  "}, {"description": "动作"}],
            "release_date": "不是字典",
            "metacritic": {"score": "88"},
            "price_overview": {"final_formatted": "¥ 10"},
        },
    )
    assert details.name == "带空格"
    assert details.genres == ("动作",)
    assert details.release_date == ""
    assert details.metacritic_score == 88
    assert details.price_initial == "¥ 10"


def test_parse_app_details_ignores_price_for_free_games() -> None:
    details = parse_app_details(1, {"is_free": True, "price_overview": {"initial_formatted": "¥ 1"}})
    assert details.price_initial is None
    assert details.price_text == "免费"


# ---------------------------------------------------------------------- 图片
def test_download_image_ok(client: SteamClient, session: FakeSession) -> None:
    session.add("media.steampowered.com", FakeResponse(200, None, content=b"\xff\xd8jpeg"))
    assert client.download_image("https://media.steampowered.com/x.jpg") == b"\xff\xd8jpeg"


def test_download_image_failure_returns_none(client: SteamClient, session: FakeSession) -> None:
    session.add("media.steampowered.com", FakeResponse(500, {}))
    assert client.download_image("https://media.steampowered.com/x.jpg") is None


def test_download_image_empty_url_skips_request(client: SteamClient, session: FakeSession) -> None:
    assert client.download_image("") is None
    assert session.calls == []


# ---------------------------------------------------------------------- 取消
def test_cancel_before_request(client: SteamClient, session: FakeSession) -> None:
    token = CancelToken()
    token.cancel()
    with pytest.raises(Cancelled):
        client.resolve_vanity("x", token)
    assert session.calls == []


def test_cancel_during_retry_wait(session: FakeSession) -> None:
    token = CancelToken()
    client = SteamClient(KEY, session=session, sleeper=lambda _delay: token.cancel())
    session.add("ResolveVanityURL", FakeResponse(429, {}))
    with pytest.raises(Cancelled):
        client.resolve_vanity("x", token)
    assert len(session.calls) == 1


def test_api_key_can_be_updated() -> None:
    client = SteamClient("")
    client.set_api_key(KEY)
    assert client.api_key == KEY
    client.set_api_key("   ")
    assert client.api_key == ""


def test_json_body_helper_is_used_by_session() -> None:
    payload = load_fixture("resolve_vanity_ok.json")
    assert json.dumps(payload)  # 样本可被序列化，便于其他测试复用
