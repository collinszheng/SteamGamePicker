"""图标测试（PRD D13 / AC-55）。

图标是「用户第一眼看到的东西」，但它最容易在后续改动里悄悄坏掉
（旧版就是一句话生成的中文单字，改名后没人再动它）。这里把能自动判定的
部分全部钉住：

* ``assets/app.ico`` 必须存在，且包含 Windows 真正会用到的全部尺寸；
* 每个尺寸都要有透明通道 —— 圆形/圆角图标不带 alpha 会在任务栏上出现黑角；
* 配色必须是 Steam 深蓝底 + 浅色骰子 + Steam 蓝描边（按像素采样判定，
  不是看源码里写了什么颜色）；
* 小尺寸必须**单独渲染并简化**（直接缩小大图会让点数糊掉）；
* 生成过程**不得使用任何文字/字体** —— 旧图标是「抽」字，应用已更名，
  中文单字不再合适，这条约束防止它回流；
* 打包脚本（PyInstaller spec / Inno Setup）引用的必须是同一个文件。
"""

from __future__ import annotations

import inspect
import sys
from pathlib import Path

import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import make_icon  # noqa: E402  （tools 不在包路径里，测试里按需加入）

ICON = ROOT / "assets" / "app.ico"
SPEC = ROOT / "packaging" / "SteamGamePicker.spec"
INSTALLER = ROOT / "packaging" / "installer.iss"

EXPECTED_SIZES = (16, 24, 32, 48, 64, 128, 256)


def _frames() -> dict[int, Image.Image]:
    with Image.open(ICON) as handle:
        frames = {}
        for size, _ in sorted(handle.info.get("sizes", [])):
            handle.size = (size, size)
            handle.load()
            frames[size] = handle.convert("RGBA").copy()
    return frames


# ---------------------------------------------------------------------------
# 文件与尺寸
# ---------------------------------------------------------------------------
def test_icon_exists():
    assert ICON.is_file(), "assets/app.ico 缺失，打包脚本会直接失败"


def test_icon_has_every_size_windows_uses():
    frames = _frames()
    assert set(frames) == set(EXPECTED_SIZES)


@pytest.mark.parametrize("size", EXPECTED_SIZES)
def test_each_frame_is_square_and_transparent(size):
    frame = _frames()[size]
    assert frame.size == (size, size)
    alpha = frame.getchannel("A")
    assert alpha.getextrema()[0] == 0, "圆角以外必须是全透明，否则任务栏上会有黑角"
    assert alpha.getextrema()[1] == 255


def test_icon_is_not_empty_bytes():
    assert ICON.stat().st_size > 4096


# ---------------------------------------------------------------------------
# 视觉：Steam 深蓝徽章 + 浅色骰子 + Steam 蓝描边
# ---------------------------------------------------------------------------
def _pixel(image: Image.Image, x: int, y: int) -> tuple[int, int, int, int]:
    return image.getpixel((x, y))


def test_badge_is_steam_dark_blue():
    """四角（徽章内部，不含圆角外的透明区）必须是深蓝：暗且蓝 > 红。"""
    frame = _frames()[256]
    for x, y in ((30, 30), (225, 30), (30, 225), (225, 225)):
        red, green, blue, alpha = _pixel(frame, x, y)
        assert alpha == 255
        assert max(red, green, blue) < 140, "徽章应该是深色"
        assert blue > red, "Steam 深色底是偏蓝的，不能是纯灰/纯黑"


def test_die_face_is_light():
    """骰子正面（中心偏左上、避开点数）必须接近白色。"""
    frame = _frames()[256]
    red, green, blue, alpha = _pixel(frame, 128, 96)
    assert alpha == 255
    assert min(red, green, blue) > 180, "骰子应是浅色，才有足够对比度"


def test_pips_are_dark_on_the_die():
    """五点布局的中心点必须是深色 —— 没有点就不成其为骰子。"""
    frame = _frames()[256]
    red, green, blue, _ = _pixel(frame, 128, 128)
    assert max(red, green, blue) < 90, "中心点应为深蓝"


def test_steam_blue_accent_is_used():
    """徽章描边里必须出现偏蓝的强调色（Steam 蓝 #66c0f4 系）。"""
    frame = _frames()[256]
    found = False
    for x in range(0, 256):
        red, green, blue, alpha = _pixel(frame, x, 12)
        if alpha > 200 and blue > 150 and blue > red + 20:
            found = True
            break
    assert found, "徽章上沿应有一圈 Steam 蓝描边"


# ---------------------------------------------------------------------------
# 生成过程
# ---------------------------------------------------------------------------
def test_small_sizes_are_rendered_separately_not_downscaled():
    """小尺寸单独出图并简化：16px 只有 3 点，256px 是 5 点。"""
    assert make_icon._pip_count(16, make_icon.STYLE_DEFAULT) == 3
    assert make_icon._pip_count(24, make_icon.STYLE_DEFAULT) == 3
    assert make_icon._pip_count(48, make_icon.STYLE_DEFAULT) == 5
    assert make_icon._pip_count(256, make_icon.STYLE_DEFAULT) == 5

    small = make_icon.render(16, make_icon.STYLE_DEFAULT)
    big = make_icon.render(256, make_icon.STYLE_DEFAULT)
    # 直接缩小 256 的图与单独渲染的 16px 必须不同，否则"光学尺寸"没生效
    naive = big.resize((16, 16), Image.Resampling.LANCZOS)
    assert small.tobytes() != naive.tobytes()


def test_render_is_deterministic():
    assert make_icon.render(64).tobytes() == make_icon.render(64).tobytes()


def test_icon_builder_uses_no_text_or_font():
    """旧图标是白色「抽」字；改名后不应再有任何文字。"""
    for function in (make_icon.render, make_icon.build_icon):
        source = inspect.getsource(function)
        assert "ImageFont" not in source
        assert "draw.text" not in source
    # 旧写法是 ``text = "抽"``：这里连字面量一起钉住
    assert '"抽"' not in Path(make_icon.__file__).read_text(encoding="utf-8")


def test_icon_palette_comes_from_the_theme():
    """颜色必须取自已锁定的 Steam 色板，不能各写一份。"""
    source = Path(make_icon.__file__).read_text(encoding="utf-8")
    assert "from app.ui.theme import" in source
    from app.ui import theme

    assert theme.COLOR_ACCENT == "#66c0f4"  # 描边用的就是主题里的 Steam 蓝
    assert make_icon.BADGE_STOPS[0][1].lower() != theme.COLOR_ACCENT


def test_preview_and_png_exports_are_committed():
    """README 与验收文档引用的图标产物必须在仓库里。"""
    for name in ("icon-preview.png", "icon-256.png"):
        path = ROOT / "docs" / "evidence" / name
        assert path.is_file(), f"缺少 {name}"
        assert path.stat().st_size > 2048


# ---------------------------------------------------------------------------
# 打包链路
# ---------------------------------------------------------------------------
def test_packaging_uses_the_same_icon():
    assert "app.ico" in SPEC.read_text(encoding="utf-8")
    assert "app.ico" in INSTALLER.read_text(encoding="utf-8")


def test_window_icon_is_applied_from_source(root, monkeypatch):
    """源码运行时也要显示应用图标（打包后由 exe 自带）。

    Tk 在 Windows 上查询 ``wm iconbitmap`` 永远返回空字符串，所以这里验证的是
    "设置过程不报错 + 找不到文件时安静放弃"，视觉效果由带标题栏的截图人工核对
    （``tools/capture_ui.py`` 的第 4 个参数）。
    """
    from app.ui import appicon

    assert appicon.icon_path() == ICON
    if sys.platform != "win32":  # pragma: no cover - CI 只在 Windows 上跑界面
        assert appicon.apply_window_icon(root) is False
        return

    assert appicon.apply_window_icon(root) is True

    monkeypatch.setattr(appicon, "icon_path", lambda: None)
    assert appicon.apply_window_icon(root) is False, "图标文件缺失时必须安静返回 False"
