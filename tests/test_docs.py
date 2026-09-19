"""文档一致性测试。

README 有中英两版，靠顶部的语言切换链接互相跳转；一旦有人只改一边、
或者把某个文档改名却忘了改链接，这里就会失败。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
README_ZH = ROOT / "README.md"
README_EN = ROOT / "README.en.md"

#: [文本](目标) —— 目标里不含空格与右括号（本项目的链接都符合）
LINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
SWITCHER_WITHIN_LINES = 12


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def markdown_files() -> list[Path]:
    files = [README_ZH, README_EN, ROOT / "CHANGELOG.md"]
    files.extend(sorted((ROOT / "docs").glob("*.md")))
    return [path for path in files if path.exists()]


def test_both_readmes_exist() -> None:
    assert README_ZH.exists(), "缺少中文 README"
    assert README_EN.exists(), "缺少英文 README"


def test_language_switcher_links_both_ways() -> None:
    zh_lines = read(README_ZH).splitlines()
    en_lines = read(README_EN).splitlines()

    zh_head = "\n".join(zh_lines[:SWITCHER_WITHIN_LINES])
    en_head = "\n".join(en_lines[:SWITCHER_WITHIN_LINES])

    assert "(README.en.md)" in zh_head, "中文 README 顶部缺少指向英文版的切换链接"
    assert "(README.md)" in en_head, "英文 README 顶部缺少指向中文版的切换链接"


def test_default_readme_is_chinese() -> None:
    """GitHub 默认渲染 README.md，所以它必须是中文版（默认显示中文）。"""
    assert "简体中文" in read(README_ZH)
    assert "**English**" in read(README_EN)


@pytest.mark.parametrize("path", [README_ZH, README_EN], ids=["zh", "en"])
def test_readmes_expose_the_download_entry(path: Path) -> None:
    content = read(path)
    assert "releases/latest" in content, "缺少安装包下载入口"
    assert "releases)" in content, "缺少 Releases 说明"


@pytest.mark.parametrize("path", [p for p in markdown_files()], ids=lambda p: p.name)
def test_relative_links_resolve(path: Path) -> None:
    """文档里的相对链接必须指向真实存在的文件（防止改名后留下死链）。"""
    broken: list[str] = []
    for target in LINK_RE.findall(read(path)):
        if target.startswith(("http://", "https://", "#", "mailto:")):
            continue
        candidate = (path.parent / target.split("#")[0]).resolve()
        if not candidate.exists():
            broken.append(target)
    assert not broken, f"{path.relative_to(ROOT)} 中的链接不存在：{broken}"


def test_feature_parity_between_languages() -> None:
    """两版 README 必须覆盖同一批功能要点（避免只更新一种语言）。"""
    keys = ["truststore", "MIT", "PyInstaller", "releases/latest"]
    for key in keys:
        assert key in read(README_ZH), f"中文 README 缺少 {key}"
        assert key in read(README_EN), f"英文 README 缺少 {key}"
