"""操作系统信任库支持。

背景（用户实测缺陷）：部分 Windows 环境（企业网络中间层、杀软 HTTPS 扫描、
本机 TLS 代理）的根证书不在 ``certifi`` 内置清单里，于是 ``requests`` 抛出
``SSLCertVerificationError``，用户只看到笼统的"网络连接失败"，实际无法使用。

处理策略（**不放宽任何证书校验**）：
1. 默认仍用 requests 的标准校验（certifi）；
2. 只有在确认为"证书链校验失败"时，才尝试切换到**操作系统原生信任库**
   （Windows 证书存储 / macOS Keychain），再重试一次；
3. 切换失败或仍然失败 → 给出可执行的中文提示，而不是继续报"网络连接失败"。

切换依赖可选包 ``truststore``；未安装时行为与以前完全一致。
环境变量 ``SGP_SYSTEM_TRUST=1`` 可在启动时直接启用（=0 则禁止自动切换）。
"""

from __future__ import annotations

import os
import ssl

from app.logging_setup import get_logger

ENV_FLAG = "SGP_SYSTEM_TRUST"

#: 证书校验失败时出现的特征串（OpenSSL / 各平台措辞）
_CERT_MARKERS = (
    "CERTIFICATE_VERIFY_FAILED",
    "certificate verify failed",
    "unable to get local issuer certificate",
    "self-signed certificate",
    "self signed certificate",
    "hostname mismatch",
    "certificate has expired",
)

_injected = False


def env_flag() -> str:
    return os.environ.get(ENV_FLAG, "").strip().lower()


def is_certificate_error(exc: BaseException | None) -> bool:
    """判断异常（含 ``__cause__`` / ``__context__`` 链）是否为证书校验失败。

    必须是"证书问题"才允许切换信任库；断网、超时、协议错误一律不受影响。
    """
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, ssl.SSLCertVerificationError):
            return True
        text = str(current)
        if any(marker.lower() in text.lower() for marker in _CERT_MARKERS):
            return True
        current = current.__cause__ or current.__context__
    return False


def system_trust_available() -> bool:
    try:
        import truststore  # noqa: F401
    except Exception:  # pragma: no cover - 未安装可选依赖
        return False
    return True


def enable_system_trust(*, force: bool = False) -> bool:
    """把进程的 SSL 校验切换到操作系统信任库；成功（或此前已启用）返回 True。

    幂等；``truststore`` 不可用时返回 False，调用方应保持原行为。
    """
    global _injected
    if _injected:
        return True
    if not force and env_flag() in {"0", "false", "no", "off"}:
        return False
    try:
        import truststore
    except Exception:
        return False
    try:
        truststore.inject_into_ssl()
    except Exception:
        get_logger().warning("系统信任库注入失败", exc_info=True)
        return False
    _injected = True
    get_logger().info("已切换到操作系统信任库进行 SSL 证书校验")
    return True


def reset_for_tests() -> None:
    """仅供测试：清掉"已注入"标记。"""
    global _injected
    _injected = False
