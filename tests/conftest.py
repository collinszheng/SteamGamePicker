"""pytest 根配置 + 仅在本沙箱下启用的临时目录适配。

诊断结论（实测，非猜测）
------------------------
本会话的 DSH 沙箱里，由**受限进程新创建的目录**会带上一份写死的权限表
（只含 ``S-1-3-4``（沙箱自身）、SYSTEM、Administrators，**不含当前账号**）
并被打上 Low 完整性标签。当前进程是 Medium 完整性，于是对这些目录做枚举或
删除一律得到 ``WinError 5``：

* ``D:\\Dev\\_pt6\\bt`` 由本会话的 PowerShell 自己 ``New-Item`` 出来，随即就不可枚举；
* 沙箱外的普通目录（例如仓库自身）一切正常。

这会打断 pytest 的临时目录机制：``tmp_path`` 依赖 ``make_numbered_dir()``
**枚举 basetemp** 找下一个编号，而那次枚举必然被拒。

启用方式
--------
设环境变量 ``SGP_SANDBOX_TMPDIR`` 指向一个可写目录（``tools\\pertest.ps1`` 会设）。
**未设该变量时本文件不做任何覆盖**——普通环境照常使用 pytest 自带的
``tmp_path`` / ``tmp_path_factory``，因此这里的适配不会影响正常开发与 CI。

适配内容（仅启用时生效）
------------------------
* 用计数器命名替代枚举，提供语义相同、名字唯一的 ``tmp_path``；
* 不删除临时目录（沙箱下删它只会再抛一次 WinError 5）；
* 跳过 pytest 收尾的死符号链接清理（同样必然失败，且只删死链接）。

一句话：只替换"临时目录从哪来"这一环，断言、覆盖范围与测试标准一字未改。
"""

from __future__ import annotations

import itertools
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

#: 沙箱适配开关：指向本次运行的临时目录根
SANDBOX_ENV = "SGP_SANDBOX_TMPDIR"

_COUNTER = itertools.count()
_SESSION_BASE: Path | None = None


def sandbox_tmpdir() -> Path | None:
    value = os.environ.get(SANDBOX_ENV, "").strip()
    return Path(value) if value else None


def pytest_configure(config) -> None:  # type: ignore[no-untyped-def]
    """启用沙箱适配：记录临时目录根，并跳过必然失败的死符号链接清理。"""
    global _SESSION_BASE  # noqa: PLW0603 - 会话级单例
    base = sandbox_tmpdir()
    if base is None:
        return
    _SESSION_BASE = base
    try:
        base.mkdir(parents=True, exist_ok=True)
    except OSError:  # pragma: no cover - 根目录不可写时交给 pytest 原行为
        return

    try:
        from _pytest import pathlib as pytest_pathlib
        from _pytest import tmpdir as pytest_tmpdir
    except ImportError:  # pragma: no cover - pytest 结构变化时安静跳过
        return
    pytest_tmpdir.cleanup_dead_symlinks = lambda basetemp: None
    pytest_pathlib.cleanup_dead_symlinks = lambda basetemp: None


def _new_temp_dir(name: str) -> Path:
    """按计数器取一个唯一目录；不枚举、不删除（沙箱下两者都会失败）。"""
    base = _SESSION_BASE if _SESSION_BASE is not None else Path(os.environ.get("TEMP", "."))
    index = next(_COUNTER)
    path = base / f"{os.getpid()}-{index:04d}-{name}"
    path.mkdir(parents=True, exist_ok=True)
    return path


class _TempPathFactory:
    """最小实现的 tmp_path_factory（只提供测试实际用到的 mktemp）。"""

    def __init__(self, base: Path) -> None:
        self._base = base

    def getbasetemp(self) -> Path:
        return self._base

    def mktemp(self, basename: str, numbered: bool = True) -> Path:
        return _new_temp_dir(basename)


if sandbox_tmpdir() is not None:

    @pytest.fixture(scope="session")
    def tmp_path_factory() -> _TempPathFactory:  # type: ignore[misc]
        return _TempPathFactory(_SESSION_BASE or Path(os.environ.get("TEMP", ".")))

    @pytest.fixture()
    def tmp_path(tmp_path_factory: _TempPathFactory) -> Path:  # type: ignore[misc]
        return tmp_path_factory.mktemp("test")
