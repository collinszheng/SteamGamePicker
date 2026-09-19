"""关口 1 实测工具：用**真实** Steam 接口校验网络层的错误语义（PRD 7.6）。

用法：
    python tools/live_check.py
        # 只跑不需要 API Key 的商店详情接口

    set STEAM_API_KEY=<你的Key>
    set SGP_PUBLIC_ID=<公开且有游戏的 SteamID64>
    set SGP_PRIVATE_ID=<资料非公开的 SteamID64>
    set SGP_EMPTY_ID=<没有游戏的 SteamID64>
    set SGP_INVALID_KEY=<一个无效或已撤销的 Key>
    set SGP_SYSTEM_TRUST=1        （可选：本机有 TLS 中间层时改用系统信任库）
    python tools/live_check.py

退出码 0 表示全部通过；未设置账号凭据时对应项记为 SKIP 并不影响退出码。

说明：产品本身使用 requests 的标准证书校验；SGP_SYSTEM_TRUST 只影响本工具的
测试连接（部分企业网络 / 沙箱存在 TLS 中间层，需要走 Windows 原生信任库）。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.errors import AppError, Err  # noqa: E402
from app.steam_api import SteamClient  # noqa: E402
from app.steamid import parse_input  # noqa: E402

RESULTS: list[tuple[bool, str]] = []
SKIPPED: list[str] = []


def enable_system_trust_if_requested() -> None:
    if os.environ.get("SGP_SYSTEM_TRUST", "").strip() not in {"1", "true", "yes"}:
        return
    try:
        import truststore

        truststore.inject_into_ssl()
        print("[INFO] 已注入系统信任库（truststore）\n")
    except Exception as exc:  # pragma: no cover - 仅实测工具
        print(f"[WARN] 系统信任库注入失败：{exc}\n")


def check(name: str, condition: bool, detail: str = "") -> None:
    RESULTS.append((condition, name))
    print(f"[{'PASS' if condition else 'FAIL'}] {name}{(' | ' + detail) if detail else ''}")


def check_error(name: str, expected: Err, func) -> None:
    try:
        func()
    except AppError as exc:
        check(name, exc.err is expected, f"实际={exc.err.value}")
    except Exception as exc:
        check(name, False, f"非预期异常 {type(exc).__name__}: {exc}")
    else:
        check(name, False, "没有抛出 AppError")


def run_store_checks() -> None:
    print("- 商店详情接口（无需 API Key）-")
    client = SteamClient("")

    try:
        free = client.get_app_details(570)  # Dota 2：免费游戏
    except AppError as exc:
        check("详情：免费游戏接口可用", False, f"{exc.err.value}: {exc.detail[:120]}")
        return
    check(
        "详情：免费游戏 is_free 且售价显示『免费』",
        bool(free) and free.is_free and free.price_text == "免费",
        f"name={free.name if free else None}",
    )
    check("详情：免费游戏没有价格字段", bool(free) and free.price_initial is None)
    check(
        "详情：能解析类型与发行日期",
        bool(free) and bool(free.genres) and bool(free.release_date),
        f"genres={free.genres if free else None} release={free.release_text if free else None}",
    )

    try:
        paid = client.get_app_details(413150)  # Stardew Valley：付费游戏
    except AppError as exc:
        check("详情：付费游戏接口可用", False, f"{exc.err.value}: {exc.detail[:120]}")
        return
    check(
        "详情：付费游戏取到名称与封面",
        bool(paid) and bool(paid.name) and bool(paid.header_image),
        f"name={paid.name if paid else None}",
    )
    check(
        "详情：售价不含折扣符号（PRD D7 只显示原价）",
        bool(paid) and "%" not in paid.price_text and "折" not in paid.price_text,
        f"price={paid.price_text if paid else None}",
    )

    check("详情：不存在的 appid 返回 None（走降级）", client.get_app_details(99999999) is None)


def run_end_to_end_check() -> None:
    """端到端复现用户操作：粘贴 Steam 资料 URL → 解析 → 拉取游戏库。

    使用 SGP_VANITY_URL（默认 Valve 官方公开账号 gaben）。
    """
    key = os.environ.get("STEAM_API_KEY", "").strip()
    if not key:
        SKIPPED.append("端到端 URL→库 流程（未设置 STEAM_API_KEY）")
        return

    url = os.environ.get("SGP_VANITY_URL", "https://steamcommunity.com/id/gaben").strip()
    print("\n- 端到端：输入 URL → 解析 → 拉取游戏库 -")
    client = SteamClient(key)
    try:
        parsed = parse_input(url)
        steamid = parsed.value
        if parsed.needs_resolve:
            steamid = client.resolve_vanity(parsed.value)
        check("端到端：URL 能解析出 SteamID64", len(steamid) == 17, f"输入={url}")
        try:
            games = client.get_owned_games(steamid)
        except AppError as exc:
            # 资料非公开属于账号设置问题，但说明网络链路是通的
            ok = exc.err is Err.PRIVATE_PROFILE
            check(
                "端到端：网络链路通畅（该账号资料非公开属正常结果）",
                ok,
                f"{exc.err.value}",
            )
        else:
            check("端到端：取到游戏库", len(games) > 0, f"{len(games)} 款")
    except AppError as exc:
        check("端到端：URL → SteamID64 → 游戏库", False, f"{exc.err.value}: {exc.detail[:120]}")


def run_account_checks() -> None:
    key = os.environ.get("STEAM_API_KEY", "").strip()
    if not key:
        SKIPPED.append("账号矩阵（未设置 STEAM_API_KEY）")
        return

    print("\n- 账号矩阵（真实 Key）-")
    client = SteamClient(key)
    public_id = os.environ.get("SGP_PUBLIC_ID", "").strip()

    if public_id:
        try:
            games = client.get_owned_games(public_id)
        except AppError as exc:
            check("库：公开账号能取到游戏列表", False, f"{exc.err.value}: {exc.detail[:120]}")
        else:
            check("库：公开账号能取到游戏列表", len(games) > 0, f"{len(games)} 款")
            check("库：所有条目 appid>0 且有名称", all(g.appid > 0 and g.name for g in games))
    else:
        SKIPPED.append("公开账号库拉取（未设置 SGP_PUBLIC_ID）")

    private_id = os.environ.get("SGP_PRIVATE_ID", "").strip()
    if private_id:
        check_error(
            "AC-06：非公开账号判为 PRIVATE_PROFILE（而不是库为空）",
            Err.PRIVATE_PROFILE,
            lambda: client.get_owned_games(private_id),
        )
    else:
        SKIPPED.append("AC-06 非公开账号判定（未设置 SGP_PRIVATE_ID）")

    empty_id = os.environ.get("SGP_EMPTY_ID", "").strip()
    if empty_id:
        check_error(
            "AC-07：确实没有游戏才判为 EMPTY_LIBRARY",
            Err.EMPTY_LIBRARY,
            lambda: client.get_owned_games(empty_id),
        )
    else:
        SKIPPED.append("AC-07 空库判定（未设置 SGP_EMPTY_ID）")

    invalid = os.environ.get("SGP_INVALID_KEY", "").strip()
    if invalid:
        bad_client = SteamClient(invalid)
        check_error(
            "AC-08：无效 Key 判为 INVALID_KEY",
            Err.INVALID_KEY,
            lambda: bad_client.get_owned_games(public_id or "76561197960287930"),
        )
    else:
        SKIPPED.append("AC-08 无效 Key 判定（未设置 SGP_INVALID_KEY）")


def main() -> int:
    enable_system_trust_if_requested()
    run_store_checks()
    run_end_to_end_check()
    run_account_checks()

    failed = [name for ok, name in RESULTS if not ok]
    print(f"\n合计 {len(RESULTS)} 项：通过 {len(RESULTS) - len(failed)}，失败 {len(failed)}")
    if SKIPPED:
        print("跳过（缺少凭据，需在具备真实账号的环境补测）：")
        for name in SKIPPED:
            print(f"  - {name}")
    if failed:
        print("失败项：")
        for name in failed:
            print(f"  - {name}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
