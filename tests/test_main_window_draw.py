"""M5 抽签与详情测试（AC-20 / AC-22 / AC-23 / AC-25 ~ AC-30）。

动画用确定性调度器推进，不等待真实时间；详情接口由假客户端替代。
"""

from __future__ import annotations

import dataclasses
import io
import random
from pathlib import Path

import pytest
from PIL import Image

from app.config import Config, ConfigStore
from app.errors import AppError, Err
from app.models import PLACEHOLDER, Game, GameDetails
from app.state import AppState
from app.ui import theme
from app.ui.animator import DrawAnimator
from app.ui.main_window import MainWindow
from support import FakeScheduler

STEAMID = "76561198260031749"
KEY = "K" * 32
IMAGE_URL = "https://cdn.example.invalid/steam/apps/413150/header.jpg"

DETAILS = GameDetails(
    appid=413150,
    name="Stardew Valley",
    header_image=IMAGE_URL,
    short_description="你继承了爷爷在星露谷留下的旧农场。",
    genres=("角色扮演", "模拟"),
    release_date="2016 年 2 月 26 日",
    metacritic_score=89,
    price_initial="¥ 48",
)


def make_games() -> list[Game]:
    return [
        Game(appid=1, name="Alpha 冒险", playtime_forever=0),
        Game(appid=2, name="Beta 射击", playtime_forever=30),
        Game(appid=3, name="Gamma 模拟", playtime_forever=5000),
    ]


def make_jpeg() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (460, 215), (30, 60, 90)).save(buffer, "JPEG")
    return buffer.getvalue()


class FakeTask:
    def __init__(self) -> None:
        self.cancelled = False

    def cancel(self) -> None:
        self.cancelled = True


class FakeWorker:
    def __init__(self) -> None:
        self.submitted: list[dict[str, object]] = []

    def submit(self, fn, *, on_done=None, on_error=None, on_cancelled=None):  # type: ignore[no-untyped-def]
        self.submitted.append(
            {"fn": fn, "on_done": on_done, "on_error": on_error, "on_cancelled": on_cancelled}
        )
        return FakeTask()


class FakeClient:
    def __init__(self, details: GameDetails | None = DETAILS, image: bytes | None = None) -> None:
        self.details = details
        self.image = image if image is not None else make_jpeg()
        self.detail_calls: list[int] = []
        self.image_calls: list[str] = []
        self.fail = False

    def get_app_details(self, appid: int, token=None):  # type: ignore[no-untyped-def]
        self.detail_calls.append(appid)
        if self.fail:
            raise AppError(Err.NETWORK)
        return self.details

    def download_image(self, url: str, token=None):  # type: ignore[no-untyped-def]
        self.image_calls.append(url)
        return self.image


@pytest.fixture()
def store(tmp_path: Path) -> ConfigStore:
    instance = ConfigStore(tmp_path / "SteamGamePicker")
    instance.ensure_dirs()
    return instance


@pytest.fixture()
def window(root, store: ConfigStore) -> MainWindow:
    instance = MainWindow(root, store=store, config=Config(api_key=KEY))
    instance.client = FakeClient()
    instance.worker = FakeWorker()
    instance.scheduler = FakeScheduler()  # type: ignore[attr-defined]
    instance._animator = DrawAnimator(instance.scheduler, random.Random(4))  # type: ignore[attr-defined]
    instance.set_games(make_games())
    return instance


def drive_draw(window: MainWindow) -> None:
    window.on_draw()
    assert window.state is AppState.DRAWING
    window.scheduler.run_all()  # type: ignore[attr-defined]


# ------------------------------------------------------------------- 抽签行为
def test_draw_only_picks_from_checked_pool(window: MainWindow) -> None:
    """AC-22：结果必然属于当前勾选集合。"""
    window.toggle_game(3)
    seen = set()
    for _ in range(20):
        drive_draw(window)
        assert window.winner is not None
        assert window.winner.appid in {1, 2}
        seen.add(window.winner.appid)
    assert seen, "至少抽出过结果"


def test_draw_reveals_winner_in_green_and_updates_button(window: MainWindow) -> None:
    drive_draw(window)

    assert window.winner is not None
    assert str(window.rolling_label.cget("text")) == window.winner.name
    assert str(window.rolling_label.cget("foreground")) == theme.COLOR_OK
    assert str(window.draw_button.cget("text")) == "再抽一次"
    assert str(window.draw_button.cget("state")) == "normal"
    assert window.state is AppState.DETAIL_LOADING
    assert window.scheduler.total_delay == 1800  # type: ignore[attr-defined]


def test_final_frame_bounces_then_resets(window: MainWindow) -> None:
    drive_draw(window)

    assert "30" in str(window.rolling_label.cget("font"))
    assert window._bounce_job is not None
    window._reset_rolling_font()
    assert window._bounce_job is None
    font = str(window.rolling_label.cget("font"))
    assert "28" in font and "bold" in font
    assert str(window.rolling_label.cget("foreground")) == theme.COLOR_OK


def test_single_game_pool_uses_short_path(window: MainWindow) -> None:
    """AC-23。"""
    window.toggle_game(1)
    window.toggle_game(3)
    assert window.state is AppState.READY

    drive_draw(window)

    assert window.scheduler.delays == [300]  # type: ignore[attr-defined]
    assert window.winner is not None and window.winner.appid == 2


def test_draw_with_empty_pool_does_nothing(window: MainWindow) -> None:
    """AC-19 / AC-21：没有可抽签的游戏时不启动动画。"""
    window.excluded = {1, 2, 3}
    window.refresh_state()
    window.on_draw()

    assert window.state is AppState.EMPTY_POOL
    assert window.scheduler.delays == []  # type: ignore[attr-defined]
    assert window._animator.running is False


# ------------------------------------------------------------------- 详情展示
def test_details_loaded_and_rendered(window: MainWindow, store: ConfigStore) -> None:
    """AC-25：封面、名称、简介、类型、发行日期、评分、售价齐全。"""
    drive_draw(window)

    job = window.worker.submitted[-1]  # type: ignore[attr-defined]
    payload = job["fn"](None)  # type: ignore[operator]
    details, image = payload
    assert details is DETAILS
    assert image

    job["on_done"](payload)  # type: ignore[operator]

    assert str(window.detail_name.cget("text")) == "Stardew Valley"
    assert str(window.detail_description.cget("text")) == DETAILS.short_description
    assert str(window.detail_meta.cget("text")) == "角色扮演 · 模拟 · 2016 年 2 月 26 日 · Metacritic 89"
    assert str(window.detail_extra.cget("text")) == "售价 ¥ 48"
    assert window.cover_photo is not None, "封面必须持有引用"
    assert window.detail_retry_button.winfo_manager() == ""
    assert window.state is AppState.READY

    assert (store.details_dir / f"{DETAILS.appid}.json").exists()
    assert (store.img_dir / f"{DETAILS.appid}.jpg").exists()


def test_details_missing_fields_use_placeholder(window: MainWindow) -> None:
    window.client = FakeClient(  # type: ignore[assignment]
        details=GameDetails(appid=9, name="信息缺失的游戏"), image=b"not-image"
    )
    drive_draw(window)
    job = window.worker.submitted[-1]  # type: ignore[attr-defined]
    job["on_done"](job["fn"](None))  # type: ignore[operator]

    assert str(window.detail_name.cget("text")) == "信息缺失的游戏"
    assert str(window.detail_description.cget("text")) == PLACEHOLDER
    assert str(window.detail_meta.cget("text")) == PLACEHOLDER
    assert str(window.detail_extra.cget("text")) == f"售价 {PLACEHOLDER}"
    assert window.cover_photo is None
    assert str(window.cover_label.cget("text")) == "（无封面）"


def test_details_failure_degrades_with_retry(window: MainWindow) -> None:
    """AC-28：只显示名称 + 无法获取详情，并提供 [重试]。"""
    drive_draw(window)
    winner_name = window.winner.name if window.winner else ""

    window.on_details_error(AppError(Err.NETWORK))

    assert str(window.detail_name.cget("text")) == winner_name
    assert str(window.detail_description.cget("text")) == "无法获取详情（可稍后重试）"
    assert str(window.detail_meta.cget("text")) == ""
    assert str(window.detail_extra.cget("text")) == ""
    assert window.detail_retry_button.winfo_manager() == "grid"
    assert window.status_text() == "无法获取详情（可稍后重试）"
    assert str(window.draw_button.cget("state")) == "normal", "详情失败不影响再抽一次"


def test_details_success_false_degrades(window: MainWindow) -> None:
    window.client = FakeClient(details=None)  # type: ignore[assignment]
    drive_draw(window)
    job = window.worker.submitted[-1]  # type: ignore[attr-defined]
    job["on_done"](job["fn"](None))  # type: ignore[operator]

    assert str(window.detail_description.cget("text")) == "无法获取详情（可稍后重试）"
    assert window.detail_retry_button.winfo_manager() == "grid"


def test_retry_resubmits_detail_request(window: MainWindow) -> None:
    drive_draw(window)
    window.on_details_error(AppError(Err.NETWORK))
    before = len(window.worker.submitted)  # type: ignore[attr-defined]

    window.retry_details()

    assert len(window.worker.submitted) == before + 1  # type: ignore[attr-defined]
    assert window.detail_retry_button.winfo_manager() == ""


def test_cached_details_skip_network(window: MainWindow, store: ConfigStore) -> None:
    """AC-30：同一款游戏第二次命中缓存，不再请求接口。"""
    cached = dataclasses.replace(DETAILS, appid=2, name="Beta 射击")
    window.cache.put_detail(cached)
    window.cache.put_image(cached.appid, make_jpeg())
    window.excluded = {1, 3}
    window.refresh_state()

    drive_draw(window)

    assert window.winner is not None and window.winner.appid == 2
    assert window.worker.submitted == []  # type: ignore[attr-defined]
    assert str(window.detail_name.cget("text")) == "Beta 射击"
    assert window.cover_photo is not None
    assert window.state is AppState.READY


def test_offline_detail_failure_keeps_draw_enabled(window: MainWindow) -> None:
    """AC-29：离线时抽签可用，详情降级。"""
    window.offline = True
    window.refresh_state()
    assert window.state is AppState.OFFLINE
    assert str(window.draw_button.cget("state")) == "normal"

    drive_draw(window)
    window.on_details_error(AppError(Err.NETWORK))

    assert str(window.detail_description.cget("text")) == "无法获取详情（可稍后重试）"
    assert str(window.draw_button.cget("state")) == "normal"
    assert window.state is AppState.OFFLINE


def test_detail_job_skips_image_when_url_missing(window: MainWindow) -> None:
    window.client = FakeClient(details=GameDetails(appid=5, name="无封面"))  # type: ignore[assignment]
    drive_draw(window)
    job = window.worker.submitted[-1]  # type: ignore[attr-defined]
    details, image = job["fn"](None)  # type: ignore[operator]

    assert details is not None
    assert image is None
    assert window.client.image_calls == []  # type: ignore[attr-defined]


# ------------------------------------------------- 问题 1：结果不被占位文案覆盖
def test_winner_stays_visible_after_details_loaded(window: MainWindow) -> None:
    """回归：详情加载完成后状态回到 S3，曾把中签游戏名覆盖成"请输入…"。"""
    drive_draw(window)
    winner_name = window.winner.name if window.winner else ""

    job = window.worker.submitted[-1]  # type: ignore[attr-defined]
    job["on_done"](job["fn"](None))  # type: ignore[operator]

    assert window.state is AppState.READY
    assert str(window.rolling_label.cget("text")) == winner_name
    assert str(window.rolling_label.cget("foreground")) == theme.COLOR_OK


def test_winner_stays_visible_after_details_failure(window: MainWindow) -> None:
    winner_name = None
    drive_draw(window)
    winner_name = window.winner.name if window.winner else ""

    window.on_details_error(AppError(Err.NETWORK))

    assert str(window.rolling_label.cget("text")) == winner_name


def test_winner_stays_visible_after_offline_refresh(window: MainWindow) -> None:
    """离线刷新失败切到 S7 时，同样不得覆盖已定格的结果。"""
    drive_draw(window)
    winner_name = window.winner.name if window.winner else ""
    window.offline = True
    window.refresh_state()

    assert window.state is AppState.OFFLINE
    assert str(window.rolling_label.cget("text")) == winner_name


def test_placeholder_still_shown_before_any_draw(window: MainWindow) -> None:
    """没有结果时占位提示必须保留（避免修过头）。"""
    assert "加载游戏库" in str(window.rolling_label.cget("text"))

    window.set_state(AppState.READY)
    assert "加载游戏库" in str(window.rolling_label.cget("text"))


def test_second_draw_replaces_the_previous_result(window: MainWindow) -> None:
    """再抽一次时，大字区必须换成新结果而不是留着旧的。"""
    window.toggle_game(3)
    drive_draw(window)
    first = window.winner.appid if window.winner else None

    drive_draw(window)

    assert window.winner is not None
    assert str(window.rolling_label.cget("text")) == window.winner.name
    assert first in {1, 2}
