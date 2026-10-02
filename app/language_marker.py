"""安装时选择的语言 → 首次运行的语言（PRD D14）。

背景：Inno Setup 的语言选择对话框（``[Languages]``）只决定**安装程序自己**的
界面语言，不会传给被安装的应用。用户希望"安装时选什么语言，装完软件就是什么
语言"，所以安装脚本在 ``[Registry]`` 里写一个标记值，应用首次运行时读取它。

规则（与 PRD 6.2 的优先级一致）：

1. 已经有 ``config.json`` → **完全听配置的**（用户在应用里改过语言，不能被安装
   时的选择覆盖）；
2. 没有配置（全新安装的首次运行）→ 用安装时写下的语言；
3. 标记不存在或值不认识 → 中文（默认语言）。

无论走哪条分支，标记值都会被删除：它只服务"首次运行"这一次。这样即使用户
删掉配置目录重装，也不会被一份陈旧的安装语言反复影响。

非 Windows 平台没有注册表，读取一律返回 ``None``（走默认语言），不影响测试与
源码运行。
"""

from __future__ import annotations

import sys

#: Inno Setup 写标记用的注册表位置（与 packaging/installer.iss 保持一致）
MARKER_KEY = r"Software\SteamGamePicker"
MARKER_VALUE = "Language"

VALID_LANGUAGES = ("zh", "en")


def _backend():  # type: ignore[no-untyped-def]
    """返回 ``winreg``；非 Windows 或不可用时返回 ``None``。"""
    if sys.platform != "win32":  # pragma: no cover - 非 Windows 环境
        return None
    try:
        import winreg  # noqa: PLC0415 - 只在 Windows 上导入
    except ImportError:  # pragma: no cover - 极简 Windows 环境
        return None
    return winreg


def read_language(backend=None) -> str | None:  # type: ignore[no-untyped-def]
    """读取安装时写下的语言；不存在或值不合法返回 ``None``。"""
    module = backend or _backend()
    if module is None:
        return None
    try:
        with module.OpenKey(module.HKEY_CURRENT_USER, MARKER_KEY) as key:
            value, _kind = module.QueryValueEx(key, MARKER_VALUE)
    except OSError:  # 键或值不存在都归到这里
        return None
    except Exception:  # pragma: no cover - 注册表异常不应影响启动
        return None
    text = str(value).strip().lower()
    return text if text in VALID_LANGUAGES else None


def delete_language(backend=None) -> bool:  # type: ignore[no-untyped-def]
    """删除标记值；删除成功返回 True。

    整个键都是为这个标记建的，因此删掉值之后顺手把空键删掉，不留垃圾。
    """
    module = backend or _backend()
    if module is None:
        return False
    try:
        with module.OpenKey(module.HKEY_CURRENT_USER, MARKER_KEY, 0, module.KEY_SET_VALUE) as key:
            module.DeleteValue(key, MARKER_VALUE)
    except OSError:
        return False
    except Exception:  # pragma: no cover
        return False
    try:
        module.DeleteKey(module.HKEY_CURRENT_USER, MARKER_KEY)
    except OSError:  # 键里还有别的东西时保留它
        pass
    except Exception:  # pragma: no cover
        pass
    return True


def take_first_run_language(backend=None) -> str | None:  # type: ignore[no-untyped-def]
    """取出并删除标记，供"没有配置文件"的首次运行使用。"""
    language = read_language(backend)
    delete_language(backend)
    return language
