"""证书信任库回退测试（用户实测缺陷的修复，对应 AC-47）。

故障：部分 Windows 环境（企业网络中间层 / 杀软 HTTPS 扫描）的根证书不在
certifi 内置清单中，requests 抛 ``SSLCertVerificationError``，用户只看到
笼统的"网络连接失败"，应用完全不可用。

修复要求（本次测试锁定的行为）：
1. 只有**证书链校验失败**才允许切换到操作系统信任库，并且**不关闭证书校验**；
2. 每个客户端最多自动重试一次，绝不无限循环；
3. 无法切换或重试仍失败时，给出可执行的中文提示（而不是"网络连接失败"）；
4. 断网、超时、协议错误等一律保持原行为（不得误触发信任库切换）。
"""

from __future__ import annotations

import ssl
import sys
import types

import pytest
import requests

from app import trust
from app.errors import ACTION_RETRY, AppError, Err, message
from app.steam_api import SteamClient
from support import FakeResponse, FakeSession

KEY = "K" * 32
STEAMID = "76561198260031749"
CERT_TEXT = (
    "[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: "
    "unable to get local issuer certificate (_ssl.c:1010)"
)


def make_cert_error() -> requests.exceptions.SSLError:
    """构造与真实链路一致的异常：SSLError 包装 SSLCertVerificationError。"""
    try:
        try:
            raise ssl.SSLCertVerificationError(1, CERT_TEXT)
        except ssl.SSLCertVerificationError as inner:
            raise requests.exceptions.SSLError(CERT_TEXT) from inner
    except requests.exceptions.SSLError as outer:
        return outer


class FakeTruststore(types.ModuleType):
    def __init__(self) -> None:
        super().__init__("truststore")
        self.inject_calls = 0

    def inject_into_ssl(self) -> None:
        self.inject_calls += 1


@pytest.fixture(autouse=True)
def clean_state():
    trust.reset_for_tests()
    yield
    trust.reset_for_tests()


@pytest.fixture()
def fake_truststore(monkeypatch) -> FakeTruststore:
    module = FakeTruststore()
    monkeypatch.setitem(sys.modules, "truststore", module)
    return module


def without_truststore(monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "truststore", None)  # import 时抛 ImportError


# ------------------------------------------------------------------ 异常识别
def test_detects_cert_verify_failure() -> None:
    assert trust.is_certificate_error(make_cert_error()) is True


def test_detects_bare_ssl_cert_error() -> None:
    assert trust.is_certificate_error(ssl.SSLCertVerificationError(1, CERT_TEXT)) is True


def test_detects_by_message_when_type_is_generic() -> None:
    assert trust.is_certificate_error(requests.exceptions.SSLError(CERT_TEXT)) is True
    assert trust.is_certificate_error(Exception("self-signed certificate in chain")) is True


@pytest.mark.parametrize(
    "exc",
    [
        None,
        requests.ConnectionError("断网"),
        requests.Timeout("超时"),
        requests.exceptions.SSLError("SSLV3_ALERT_HANDSHAKE_FAILURE"),
        ValueError("随便什么错"),
    ],
)
def test_ignores_non_certificate_errors(exc: BaseException | None) -> None:
    assert trust.is_certificate_error(exc) is False


# ------------------------------------------------------------------ 信任库开关
def test_unavailable_without_package(monkeypatch) -> None:
    without_truststore(monkeypatch)
    assert trust.system_trust_available() is False
    assert trust.enable_system_trust() is False


def test_enable_is_idempotent(fake_truststore: FakeTruststore) -> None:
    assert trust.enable_system_trust() is True
    assert trust.enable_system_trust() is True
    assert fake_truststore.inject_calls == 1


def test_env_flag_zero_disables_auto_but_force_wins(
    fake_truststore: FakeTruststore, monkeypatch
) -> None:
    monkeypatch.setenv("SGP_SYSTEM_TRUST", "0")
    assert trust.enable_system_trust() is False
    assert fake_truststore.inject_calls == 0

    assert trust.enable_system_trust(force=True) is True
    assert fake_truststore.inject_calls == 1


# ------------------------------------------------------------------ 客户端行为
def test_retries_once_with_system_trust(fake_truststore: FakeTruststore) -> None:
    """证书失败 → 切到系统信任库 → 重试一次并成功。"""
    session = FakeSession().add(
        "ResolveVanityURL",
        [make_cert_error(), FakeResponse(200, {"response": {"success": 1, "steamid": STEAMID}})],
    )
    client = SteamClient(KEY, session=session)

    assert client.resolve_vanity("gaben") == STEAMID
    assert len(session.calls) == 2
    assert fake_truststore.inject_calls == 1


def test_tls_trust_error_when_package_missing(monkeypatch) -> None:
    without_truststore(monkeypatch)
    session = FakeSession().add("ResolveVanityURL", make_cert_error())
    client = SteamClient(KEY, session=session)

    with pytest.raises(AppError) as info:
        client.resolve_vanity("gaben")

    assert info.value.err is Err.TLS_TRUST
    assert len(session.calls) == 1, "没有可用信任库时不应反复重试"
    assert "证书" in info.value.message.text


def test_tls_trust_error_after_failed_retry(fake_truststore: FakeTruststore) -> None:
    """切换信任库后仍然失败 → 同样给出证书相关提示，且只重试一次。"""
    session = FakeSession().add("ResolveVanityURL", make_cert_error())
    client = SteamClient(KEY, session=session)

    with pytest.raises(AppError) as info:
        client.resolve_vanity("gaben")

    assert info.value.err is Err.TLS_TRUST
    assert len(session.calls) == 2, "只允许自动重试一次"


def test_plain_connection_error_does_not_touch_truststore(fake_truststore: FakeTruststore) -> None:
    """断网必须保持原行为：不触发信任库切换，也不改文案。"""
    session = FakeSession().add("ResolveVanityURL", requests.ConnectionError("断网"))
    client = SteamClient(KEY, session=session)

    with pytest.raises(AppError) as info:
        client.resolve_vanity("gaben")

    assert info.value.err is Err.NETWORK
    assert info.value.message.text == "网络连接失败，请检查网络后重试"
    assert len(session.calls) == 1
    assert fake_truststore.inject_calls == 0


def test_non_certificate_ssl_error_is_network(fake_truststore: FakeTruststore) -> None:
    session = FakeSession().add(
        "ResolveVanityURL", requests.exceptions.SSLError("SSLV3_ALERT_HANDSHAKE_FAILURE")
    )
    client = SteamClient(KEY, session=session)

    with pytest.raises(AppError) as info:
        client.resolve_vanity("gaben")

    assert info.value.err is Err.NETWORK
    assert fake_truststore.inject_calls == 0


def test_env_flag_enables_trust_at_construction(
    fake_truststore: FakeTruststore, monkeypatch
) -> None:
    monkeypatch.setenv("SGP_SYSTEM_TRUST", "1")
    SteamClient(KEY, session=FakeSession())
    assert fake_truststore.inject_calls == 1


def test_retry_also_works_for_library_and_details(fake_truststore: FakeTruststore) -> None:
    """三个接口共用同一套底层请求逻辑，此处验证库与详情两条路径。"""
    session = FakeSession()
    session.add(
        "GetOwnedGames",
        [make_cert_error(), FakeResponse(200, {"response": {"games": [{"appid": 1, "name": "Alpha"}]}})],
    )
    session.add(
        "appdetails",
        [make_cert_error(), FakeResponse(200, {"570": {"success": True, "data": {"name": "Dota 2"}}})],
    )
    client = SteamClient(KEY, session=session)

    assert [g.name for g in client.get_owned_games(STEAMID)] == ["Alpha"]
    details = client.get_app_details(570)
    assert details is not None and details.name == "Dota 2"


def test_tls_trust_message_is_actionable() -> None:
    msg = message(Err.TLS_TRUST)
    assert "证书" in msg.text
    assert "网络代理" in msg.text
    assert msg.actions == (ACTION_RETRY,)
