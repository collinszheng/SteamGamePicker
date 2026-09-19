"""渲染主窗口并截图，供人工核对界面（开发辅助脚本，不参与打包）。

用法::

    python tools/capture_ui.py 抽签后.png [抽签前.png] [英文界面.png] [带标题栏.png]

第 4 个参数会把标题栏一起抓进来，用来核对窗口图标这类边框上的东西。
"""

from __future__ import annotations

import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import tkinter as tk  # noqa: E402

from PIL import ImageGrab  # noqa: E402

from app.config import Config, ConfigStore  # noqa: E402
from app.models import Game, GameDetails  # noqa: E402
from app.ui.main_window import MainWindow  # noqa: E402

SAMPLE = [
    ("Half-Life", 0),
    ("Left 4 Dead 2", 41),
    ("Counter-Strike 2", 933),
    ("RPG Maker XP", 0),
    ("The Binding of Isaac: Rebirth", 0),
    ("Portal 2", 186),
    ("Stardew Valley", 0),
    ("Hades", 0),
    ("Slay the Spire", 74),
    ("Terraria", 1520),
]

DETAILS = GameDetails(
    appid=413150,
    name="Stardew Valley",
    short_description="你继承了爷爷在星露谷留下的旧农场，还有他留下的旧工具和几枚硬币。",
    genres=("角色扮演", "模拟", "独立"),
    release_date="2016 年 2 月 26 日",
    metacritic_score=89,
    price_initial="¥ 48.00",
)


def build_window(root: tk.Tk, store: ConfigStore) -> MainWindow:
    window = MainWindow(root, store=store, config=Config(api_key="K" * 32))
    window.set_games(
        [Game(appid=index, name=name, playtime_forever=minutes) for index, (name, minutes) in enumerate(SAMPLE, 1)],
        updated_at="2026-09-19T15:04:05+08:00",
    )
    window.toggle_pool_panel(expand=True)
    window.toggle_game(4)  # 展示"被排除的行灰显"
    window.toggle_game(7)
    # 展示抽签结果与详情卡片
    window.winner = window.games[6]
    window._on_anim_frame(window.winner.name, True)
    window.render_details(DETAILS)
    window.refresh_state()
    return window


def _dpi_scale(root: tk.Tk) -> float:
    """屏幕物理像素 ÷ Tk 逻辑像素。

    本程序没做 DPI 感知（Windows 会把窗口整体放大），Tk 的 ``winfo_*`` 是逻辑像素，
    而 ``ImageGrab`` 抓的是物理像素。不换算的话，在 125% 缩放的屏幕上
    截图只会拍到窗口左上角的 80%，而且整体偏移十几像素。
    """
    logical = root.winfo_screenwidth()
    if logical <= 0:  # pragma: no cover - 防御
        return 1.0
    return round(ImageGrab.grab().width / logical, 4)


def _physical(root: tk.Tk, box: tuple[float, float, float, float]) -> tuple[int, int, int, int]:
    scale = _dpi_scale(root)
    return tuple(round(value * scale) for value in box)  # type: ignore[return-value]


def grab(root: tk.Tk, out: Path) -> None:
    root.attributes("-topmost", True)
    root.update_idletasks()
    root.update()
    time.sleep(0.8)
    root.update()
    # 只抓"客户区"：winfo_rootx/rooty 即客户区左上角，避免猜标题栏高度导致取景偏移
    x, y = root.winfo_rootx(), root.winfo_rooty()
    width, height = root.winfo_width(), root.winfo_height()
    ImageGrab.grab(bbox=_physical(root, (x, y, x + width, y + height))).save(out)
    print(f"截图已保存：{out}（{out.stat().st_size} 字节，{width}x{height} 逻辑像素）")


def grab_framed(root: tk.Tk, out: Path) -> None:
    """连标题栏一起抓（客户区之外），用来核对窗口图标/标题这类边框上的东西。"""
    root.attributes("-topmost", True)
    root.update_idletasks()
    root.update()
    time.sleep(0.6)
    root.update()
    x, y = root.winfo_rootx(), root.winfo_rooty()
    width, height = root.winfo_width(), root.winfo_height()
    box = (x - 24, y - 64, x + width + 24, y + height + 24)
    ImageGrab.grab(bbox=_physical(root, box)).save(out)
    print(f"带边框截图已保存：{out}（{out.stat().st_size} 字节）")


def report(root: tk.Tk) -> None:
    root.update_idletasks()
    root.update()
    print(f"窗口尺寸: {root.winfo_width()}x{root.winfo_height()}（请求 {root.winfo_reqwidth()}x{root.winfo_reqheight()}）")
    for child in root.winfo_children():
        style = str(child.cget("style")) if "style" in child.keys() else ""
        print(
            f"  [root] {child.winfo_class():<10} style={style:<22} "
            f"请求 {child.winfo_reqwidth()}x{child.winfo_reqheight()} 实际 {child.winfo_width()}x{child.winfo_height()}"
        )
        for zone in child.winfo_children():
            zstyle = str(zone.cget("style")) if "style" in zone.keys() else ""
            flag = "  <<< 超宽" if zone.winfo_reqwidth() > root.winfo_width() - 24 else ""
            print(
                f"      └ {zone.winfo_class():<10} style={zstyle:<20} "
                f"请求 {zone.winfo_reqwidth()}x{zone.winfo_reqheight()}{flag}"
            )


def main(target: str, second: str | None = None, english: str | None = None, framed: str | None = None) -> int:
    out = Path(target).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out2 = Path(second).resolve() if second else None
    out3 = Path(english).resolve() if english else None
    out4 = Path(framed).resolve() if framed else None
    with tempfile.TemporaryDirectory() as tmp:
        store = ConfigStore(Path(tmp) / "appdata")
        store.ensure_dirs()
        root = tk.Tk()
        window = MainWindow(root, store=store, config=Config(api_key="K" * 32))
        root.geometry("800x600+40+40")  # 固定默认尺寸与位置，保证截图可比

        if out3 is not None:  # 英文界面（证明语言切换真的换了文案）
            window.config.language = "en"
            window.on_settings_saved()
            window.set_games(
                [Game(appid=index, name=name, playtime_forever=minutes) for index, (name, minutes) in enumerate(SAMPLE, 1)],
                updated_at="2026-09-19T15:04:05+08:00",
            )
            window.toggle_pool_panel(expand=True)
            window.toggle_game(4)
            window.winner = window.games[6]
            window._on_anim_frame(window.winner.name, True)
            window.render_details(DETAILS)
            window.refresh_state()
            if out4 is not None:
                grab_framed(root, out4)
            grab(root, out3)
            window.config.language = "zh"
            window.on_settings_saved()
            root.destroy()
            return 0

        window.set_games(
            [Game(appid=index, name=name, playtime_forever=minutes) for index, (name, minutes) in enumerate(SAMPLE, 1)],
            updated_at="2026-09-19T15:04:05+08:00",
        )
        window.toggle_pool_panel(expand=True)
        window.toggle_game(4)  # 展示"被排除的行灰显"
        window.toggle_game(7)

        report(root)
        if out2 is not None:  # 抽签前：没有封面占位，列表更高
            grab(root, out2)
        # 抽签后：大字 + 绿色 CTA + 详情卡片
        window.winner = window.games[6]
        window._on_anim_frame(window.winner.name, True)
        window.render_details(DETAILS)
        window.refresh_state()
        grab(root, out)
        root.destroy()
    return 0


if __name__ == "__main__":
    arguments = sys.argv[1:] or ["ui-capture.png"]
    raise SystemExit(main(*arguments))
