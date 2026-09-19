"""T0.4 错误与状态文案表测试（AC-38 的文案一致性要求）。

界面层不写中文提示，因此这里逐条锁定 PRD 5.7 的口径。
"""

from __future__ import annotations

import pytest

from app import errors
from app.errors import (
    ACTION_EXPAND,
    ACTION_RETRY,
    ACTION_SETTINGS,
    LEVEL_ERROR,
    LEVEL_MUTED,
    LEVEL_OK,
    LEVEL_WARN,
    AppError,
    Err,
    message,
    status,
)


@pytest.mark.parametrize("err", list(Err))
def test_every_err_has_chinese_message(err: Err) -> None:
    msg = message(err)
    assert msg.text
    assert any("\u4e00" <= ch <= "\u9fff" for ch in msg.text), f"{err} 的文案不是中文"
    assert msg.level in {LEVEL_OK, LEVEL_WARN, LEVEL_ERROR, LEVEL_MUTED}


@pytest.mark.parametrize(
    ("err", "text", "level", "actions"),
    [
        (Err.NO_KEY, "请先在设置中填写 Steam API Key", LEVEL_ERROR, (ACTION_SETTINGS,)),
        (Err.EMPTY_INPUT, "请先输入 Steam ID 或资料地址", LEVEL_ERROR, ()),
        (
            Err.PRIVATE_PROFILE,
            "无法读取游戏库，请将 Steam 个人资料和游戏详情设为公开",
            LEVEL_ERROR,
            (ACTION_RETRY,),
        ),
        (
            Err.EMPTY_LIBRARY,
            "未找到任何游戏，请确认已拥有游戏且资料已公开",
            LEVEL_ERROR,
            (ACTION_RETRY,),
        ),
        (Err.INVALID_KEY, "API Key 无效或已停用，请在设置中更新", LEVEL_ERROR, (ACTION_SETTINGS,)),
        (Err.NETWORK, "网络连接失败，请检查网络后重试", LEVEL_ERROR, (ACTION_RETRY,)),
        (Err.RATE_LIMIT, "请求太频繁，请稍等一分钟再试", LEVEL_WARN, (ACTION_RETRY,)),
        (Err.DETAIL_FAILED, "无法获取详情（可稍后重试）", LEVEL_MUTED, (ACTION_RETRY,)),
        (
            Err.BAD_FORMAT,
            "无法解析该资料地址，请检查自定义名称或 API Key",
            LEVEL_ERROR,
            (ACTION_SETTINGS,),
        ),
        (
            Err.VANITY_NOT_FOUND,
            "无法解析该资料地址，请检查自定义名称或 API Key",
            LEVEL_ERROR,
            (ACTION_SETTINGS,),
        ),
    ],
)
def test_prd_5_7_wording_is_locked(
    err: Err, text: str, level: str, actions: tuple[str, ...]
) -> None:
    msg = message(err)
    assert (msg.text, msg.level, msg.actions) == (text, level, actions)


def test_status_templates_render() -> None:
    assert status("saved").text == "设置已保存"
    assert status("loading").level == LEVEL_MUTED
    assert status("loading").actions == (errors.ACTION_CANCEL,)
    assert (
        status("loaded", total=128, available=96, updated="09-19 15:04").text
        == "已加载 128 款 · 96 款参与抽签 · 上次更新 09-19 15:04"
    )
    assert status("offline", updated="09-19 15:04").level == LEVEL_WARN
    pool_empty = status("pool_empty")
    assert pool_empty.actions == (ACTION_EXPAND,)
    assert "没有可抽签的游戏" in pool_empty.text
    assert status("preset_applied", preset="从未玩过").text == "已按『从未玩过』重设选择，可继续手动调整"
    assert status("config_corrupt").level == LEVEL_WARN


def test_app_error_carries_business_type() -> None:
    error = AppError(Err.INVALID_KEY, "HTTP 401")
    assert error.err is Err.INVALID_KEY
    assert error.message.text == "API Key 无效或已停用，请在设置中更新"
    assert str(error) == "HTTP 401"
