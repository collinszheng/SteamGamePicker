"""Steam Game Picker：从 Steam 游戏库里随机抽一款游戏（Windows 桌面端）。"""

from __future__ import annotations

#: 应用显示名（窗口标题、关于窗、安装包与快捷方式都用它）
APP_NAME = "Steam Game Picker"
#: 纯 ASCII 名称：用于目录名与可执行文件名，改名时保持不变
APP_NAME_EN = "SteamGamePicker"
APP_VERSION = "1.0.0"

__all__ = ["APP_NAME", "APP_NAME_EN", "APP_VERSION"]
