"""Steam 游戏抽签器入口。

职责：初始化目录与日志 → 读取配置 → 组装主窗口与后台执行器 →
首次运行弹引导 / 否则从缓存秒开并后台刷新。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import tkinter as tk
from pathlib import Path

from app import APP_NAME, APP_VERSION
from app.cache import GameCache
from app.config import ConfigStore, LoadResult
from app.errors import AppError, status
from app.logging_setup import setup_logging
from app.steam_api import SteamClient
from app.trust import system_trust_available
from app.ui.main_window import MainWindow
from app.worker import Worker


def bootstrap() -> tuple[ConfigStore, object, LoadResult]:
    """初始化目录、日志与配置；返回 (store, logger, load_result)。"""
    store = ConfigStore()
    store.ensure_dirs()
    result = store.load()
    logger = setup_logging(store.logs_dir, secrets=[result.config.api_key])
    logger.info("%s v%s 启动", APP_NAME, APP_VERSION)
    if result.corrupted:
        logger.warning("配置文件损坏，已备份为 %s", result.corrupted_backup)
    return store, logger, result


def build_app() -> tuple[tk.Tk, MainWindow]:
    """组装可运行的应用（测试与 main() 共用）。"""
    store, logger, result = bootstrap()
    root = tk.Tk()
    worker = Worker(root, logger=logger)  # type: ignore[arg-type]
    client = SteamClient(result.config.api_key)
    window = MainWindow(
        root,
        store=store,
        config=result.config,
        client=client,
        worker=worker,
        logger=logger,  # type: ignore[arg-type]
    )
    if result.corrupted:
        window.set_status(status("config_corrupt"))
    if not result.config.has_api_key:
        window.start_first_run_guide()
    else:
        window.startup_load()
    return root, window


def selftest(report_path: Path | None, *, live: bool = False) -> int:
    """打包产物自检：验证依赖被正确打进包里，并测量启动耗时。

    ``--selftest --report=<文件>`` 供打包验证使用（窗口化 exe 没有控制台输出）；
    追加 ``--live`` 时会用环境变量里的 API Key 真实请求一次 Steam，
    验证打包产物的联网链路（含证书信任回退）。
    """
    started = time.perf_counter()
    report: dict[str, object] = {"version": APP_VERSION, "frozen": bool(getattr(sys, "frozen", False))}
    store = ConfigStore()
    store.ensure_dirs()
    logger = setup_logging(store.logs_dir)
    result = store.load()
    cache = GameCache(store, ttl_days=result.config.details_cache_ttl_days)
    snapshot = None
    if result.config.last_steam_id:
        snapshot = cache.load_snapshot(result.config.last_steam_id)
    report["config_corrupted"] = result.corrupted
    report["has_api_key"] = result.config.has_api_key
    report["snapshot_games"] = len(snapshot) if snapshot is not None else 0
    report["cache_bytes"] = cache.total_bytes()

    # 关键：验证 tkinter / Tcl-Tk 数据文件 / Pillow / requests 都被打进了包
    probe = tk.Tk()
    probe.withdraw()
    probe.update()
    probe.destroy()
    report["tk_ok"] = True
    from PIL import Image  # noqa: F401  # 触发导入，验证 Pillow 已打包

    import requests  # noqa: F401

    report["pillow_ok"] = True
    report["requests_ok"] = True
    report["truststore_ok"] = system_trust_available()

    if live:
        api_key = os.environ.get("STEAM_API_KEY", "").strip()
        if not api_key:
            report["live_api"] = "skipped(no STEAM_API_KEY)"
        else:
            client = SteamClient(api_key)
            try:
                steamid = client.resolve_vanity("gaben")
            except AppError as exc:
                # 只记录错误类型；detail 里可能含带 key 的 URL，绝不写入报告
                report["live_api"] = exc.err.value
            except Exception as exc:  # pragma: no cover - 兜底
                report["live_api"] = f"unexpected:{type(exc).__name__}"
            else:
                report["live_api"] = "ok" if len(steamid) == 17 else "unexpected-steamid"

    report["startup_ms"] = round((time.perf_counter() - started) * 1000, 1)

    logger.info("自检完成：%s", report)
    if report_path is not None:
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    else:  # pragma: no cover - 源码运行时可见
        print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog=APP_NAME, description="Steam 游戏抽签器")
    parser.add_argument("--selftest", action="store_true", help="自检并退出（打包验证用）")
    parser.add_argument("--report", type=Path, default=None, help="自检报告输出路径")
    parser.add_argument("--live", action="store_true", help="自检时额外真实请求一次 Steam")
    args = parser.parse_args(argv)

    if args.selftest:
        return selftest(args.report, live=args.live)

    root, _window = build_app()
    try:
        root.mainloop()
    finally:
        from app.logging_setup import get_logger

        get_logger().info("程序退出")
    return 0


if __name__ == "__main__":  # pragma: no cover - 手工运行入口
    sys.exit(main())
