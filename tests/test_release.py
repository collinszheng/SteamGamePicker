"""发布一致性测试：版本号只写一处，其余地方必须对得上。

打包相关的东西最容易"改一半"——代码里升到 1.0.1 了，安装包脚本还是 1.0.0，
exe 的文件属性空白，CHANGELOG 没有对应小节。这里把它们全部钉住。

规则：**版本号的唯一出处是 :data:`app.APP_VERSION`**，
安装包脚本、exe 版本资源、CHANGELOG 小节都必须与它一致。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import version_info  # noqa: E402

from app import APP_NAME, APP_NAME_EN, APP_VERSION  # noqa: E402

INSTALLER = ROOT / "packaging" / "installer.iss"
SPEC = ROOT / "packaging" / "SteamGamePicker.spec"
CHANGELOG = ROOT / "CHANGELOG.md"

SEMVER = re.compile(r"^\d+\.\d+\.\d+$")


# ---------------------------------------------------------------------------
# 版本号本身
# ---------------------------------------------------------------------------
def test_version_looks_like_semver():
    assert SEMVER.match(APP_VERSION), f"版本号格式不对：{APP_VERSION}"


def test_names_are_consistent():
    assert APP_NAME == "Steam Game Picker"
    assert APP_NAME_EN.isascii(), "可执行文件名必须保持 ASCII"
    assert " " not in APP_NAME_EN


# ---------------------------------------------------------------------------
# 三处版本号必须一致
# ---------------------------------------------------------------------------
def test_installer_version_matches_app_version():
    match = re.search(r'#define AppVersion "([^"]+)"', INSTALLER.read_text(encoding="utf-8"))
    assert match, "installer.iss 里找不到 AppVersion"
    assert match.group(1) == APP_VERSION, "安装包版本与应用版本不一致"


def test_version_resource_carries_the_app_version():
    text = version_info.build_text()
    assert f"'{APP_VERSION}.0'" in text or f"'{APP_VERSION}'" in text
    assert version_info.version_tuple(APP_VERSION) == tuple(
        int(part) for part in (APP_VERSION.split(".") + ["0"])[:4]
    )


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1.0.1", (1, 0, 1, 0)),
        ("2.3", (2, 3, 0, 0)),
        # 预发布后缀整段忽略，而不是把 "beta1" 的数字当成第四段
        ("1.0.0-beta1", (1, 0, 0, 0)),
    ],
)
def test_version_tuple_is_windows_compatible(raw, expected):
    assert version_info.version_tuple(raw) == expected


def test_spec_embeds_the_version_resource():
    """spec 必须真的把版本资源交给 PyInstaller（此前是 version=None，文件属性空白）。"""
    text = SPEC.read_text(encoding="utf-8")
    assert "version_info" in text
    assert "version=None" not in text, "版本资源被关掉了，exe 的文件属性会变空白"
    assert "version=str(VERSION_FILE)" in text


def test_spec_uses_the_same_installer_name_and_icon():
    text = SPEC.read_text(encoding="utf-8")
    assert f'name="{APP_NAME_EN}"' in text
    assert 'assets" / "app.ico"' in text


# ---------------------------------------------------------------------------
# 覆盖升级（改名后的快捷方式清理）
# ---------------------------------------------------------------------------
def test_installer_keeps_the_install_dir_on_upgrade():
    """升级必须沿用上次的安装目录，否则用户会在两个目录里各有一份。"""
    text = INSTALLER.read_text(encoding="utf-8")
    assert "UsePreviousAppDir=yes" in text


def test_installer_switches_to_the_new_start_menu_group():
    """开始菜单目录不能沿用旧名（Inno 默认沿用，改名前后的名字并不一样）。"""
    text = INSTALLER.read_text(encoding="utf-8")
    assert "UsePreviousGroup=no" in text
    assert "DefaultGroupName={#AppName}" in text


def test_installer_cleans_up_legacy_shortcuts():
    """实测结论：不清理的话，升级后开始菜单里会新旧两套快捷方式并存。"""
    text = INSTALLER.read_text(encoding="utf-8")
    assert '#define LegacyAppName "Steam 游戏抽签器"' in text
    assert "[InstallDelete]" in text
    assert 'Name: "{userprograms}\\{#LegacyAppName}"' in text
    assert 'Name: "{autodesktop}\\{#LegacyAppName}.lnk"' in text


def test_desktop_task_is_checked_on_upgrade_too():
    """更名后旧名的桌面快捷方式会被删掉，因此桌面任务不能在升级时默认不勾。"""
    match = re.search(r'Name: "desktopicon".*', INSTALLER.read_text(encoding="utf-8"))
    assert match, "找不到 desktopicon 任务"
    assert "checkedonce" not in match.group(0), (
        "checkedonce 会让升级安装默认不创建桌面快捷方式，"
        "与“旧快捷方式被清理”叠加后用户桌面上会什么都不剩"
    )


# ---------------------------------------------------------------------------
# 文档
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# 安装时的语言选择必须与应用的注册表约定对齐（PRD D14）
# ---------------------------------------------------------------------------
def test_installer_and_app_agree_on_the_language_marker():
    text = INSTALLER.read_text(encoding="utf-8")
    assert "Software\\SteamGamePicker" in text, "安装脚本没写语言标记"
    assert 'ValueName: "Language"' in text
    assert "{code:AppLanguageCode}" in text, "注册表值必须来自所选语言"
    assert "ActiveLanguage" in text, "语言映射函数没用上安装时选中的语言"


def test_installer_can_ship_both_languages():
    """两种语言都要可用，且**中文优先**（列为第一项 = 向导默认语言）。

    中文语言包是可选输入：在则启用中文选项，不在也能编译（只用英文）。
    因此这里断言"引用完整 + 中文排在英文前 + 有获取说明"。
    """
    text = INSTALLER.read_text(encoding="utf-8")
    assert 'Name: "chinese"; MessagesFile: "ChineseSimplified.isl"' in text
    assert 'Name: "english"; MessagesFile: "compiler:Default.isl"' in text
    assert text.index('Name: "chinese"') < text.index('Name: "english"'), (
        "[Languages] 的第一项是向导默认语言，中文必须排在英文之前"
    )
    guide = ROOT / "packaging" / "README-installer-language.md"
    assert guide.exists(), "缺少如何获取中文语言包的说明"
    assert "ChineseSimplified.isl" in guide.read_text(encoding="utf-8")


def test_bundled_chinese_language_file_is_usable():
    """随仓库分发的语言包必须是 UTF-8 且含 Inno 必需的关键键。"""
    isl = ROOT / "packaging" / "ChineseSimplified.isl"
    assert isl.exists(), "仓库应随包提供中文语言包（installer.iss 会引用它）"

    raw = isl.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf"), "带 BOM 会让 Inno 的 .isl 解析出问题"
    text = raw.decode("utf-8")  # 解不出 UTF-8 就会在这里失败
    for key in ("[LangOptions]", "LanguageName", "LanguageID", "LanguageCodePage"):
        assert key in text, f"语言包缺少 {key}"
    assert "简体中文" in text
    # 语言必须声明为 6.5.0+ 的格式（本仓库用 Inno Setup 6.7.3 编译）
    assert "6.5.0" in text.splitlines()[0]
    for button in ("ButtonNext", "ButtonBack", "ButtonInstall", "ButtonCancel"):
        assert button in text, f"语言包缺少 {button}，向导按钮会退回英文"


def test_installer_language_codes_match_the_app():
    text = INSTALLER.read_text(encoding="utf-8")
    for code, language in (("LanguageZh", "zh"), ("LanguageEn", "en")):
        assert f'#define {code} "{language}"' in text


def test_changelog_documents_the_current_version():
    text = CHANGELOG.read_text(encoding="utf-8")
    assert f"## [{APP_VERSION}]" in text, f"CHANGELOG 缺少 [{APP_VERSION}] 小节"
    assert "## [未发布]" not in text, "发布后不该再留着「未发布」小节"


def test_changelog_release_notes_link_the_tag():
    text = CHANGELOG.read_text(encoding="utf-8")
    assert f"releases/tag/v{APP_VERSION}" in text


def test_readme_points_at_the_latest_release():
    for name in ("README.md", "README.en.md"):
        text = (ROOT / name).read_text(encoding="utf-8")
        assert "releases/latest" in text
