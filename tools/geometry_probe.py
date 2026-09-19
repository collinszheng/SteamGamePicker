"""几何诊断：打印屏幕、窗口与各控件的真实坐标，用来定位视觉裁切问题。"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import tkinter as tk  # noqa: E402

from app.config import Config, ConfigStore  # noqa: E402
from app.models import Game  # noqa: E402
from app.ui.main_window import MainWindow  # noqa: E402


def dump(widget: tk.Misc, label: str, depth: int = 0) -> None:
    try:
        info = f"x={widget.winfo_x():>4} y={widget.winfo_y():>4} w={widget.winfo_width():>4} h={widget.winfo_height():>4}"
    except tk.TclError:  # pragma: no cover
        return
    style = str(widget.cget("style")) if "style" in widget.keys() else ""
    text = ""
    try:
        text = str(widget.cget("text"))[:14]
    except tk.TclError:
        pass
    print(f"{'  ' * depth}{label:<22} {info} style={style:<20} {text}")


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        store = ConfigStore(Path(tmp) / "appdata")
        store.ensure_dirs()
        root = tk.Tk()
        window = MainWindow(root, store=store, config=Config(api_key="K" * 32))
        window.set_games([Game(appid=i, name=f"游戏 {i}", playtime_forever=i * 30) for i in range(1, 9)])
        root.update_idletasks()
        root.update()

        print(
            f"屏幕: {root.winfo_screenwidth()}x{root.winfo_screenheight()} | "
            f"窗口客户区原点: ({root.winfo_rootx()},{root.winfo_rooty()}) "
            f"尺寸: {root.winfo_width()}x{root.winfo_height()}"
        )
        for child in root.winfo_children():
            dump(child, "root 子控件", 1)
            for zone in child.winfo_children():
                dump(zone, "  区", 2)
                for widget in zone.winfo_children():
                    dump(widget, "    控件", 3)
        root.destroy()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
