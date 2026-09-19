"""T3.1 / T3.2 / T3.4 后台任务执行器测试（AC-05 / AC-11 / AC-24）。"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable

import pytest

from app.cancellation import Cancelled
from app.worker import POLL_MS, Worker


class FakeScheduler:
    """确定性调度器：把 after 回调存起来，由测试显式触发。"""

    def __init__(self) -> None:
        self.jobs: dict[int, Callable[[], None]] = {}
        self.cancelled: list[int] = []
        self.delays: list[int] = []
        self._next = 1

    def after(self, ms: int, callback: Callable[[], None]) -> int:
        identifier = self._next
        self._next += 1
        self.jobs[identifier] = callback
        self.delays.append(ms)
        return identifier

    def after_cancel(self, identifier: int) -> None:
        self.cancelled.append(identifier)
        self.jobs.pop(identifier, None)

    def run_pending(self) -> None:
        for identifier, callback in list(self.jobs.items()):
            self.jobs.pop(identifier, None)
            callback()

    @property
    def pending(self) -> int:
        return len(self.jobs)


@pytest.fixture()
def scheduler() -> FakeScheduler:
    return FakeScheduler()


@pytest.fixture()
def worker(scheduler: FakeScheduler):
    instance = Worker(scheduler, poll_ms=1)
    yield instance
    instance.shutdown()


def test_task_runs_off_main_thread(scheduler: FakeScheduler, worker: Worker) -> None:
    seen: dict[str, object] = {}
    done = threading.Event()

    def fn(token):  # type: ignore[no-untyped-def]
        seen["thread"] = threading.current_thread().name
        return 42

    worker.submit(fn, on_done=lambda result: (seen.__setitem__("result", result), done.set()))

    assert worker.wait_idle(5) is True
    scheduler.run_pending()
    assert done.wait(5) is True
    assert seen["result"] == 42
    assert seen["thread"] == "sgp-worker"
    assert seen["thread"] != threading.main_thread().name


def test_callbacks_run_on_main_thread(scheduler: FakeScheduler, worker: Worker) -> None:
    seen: dict[str, bool] = {}
    worker.submit(lambda token: 1, on_done=lambda _r: seen.__setitem__("main", True))
    assert worker.wait_idle(5) is True
    scheduler.run_pending()
    assert seen == {"main": True}
    # 回调由主线程的 pump 触发，因此这里能直接看到结果
    assert threading.current_thread() is threading.main_thread()


def test_error_callback_receives_exception(scheduler: FakeScheduler, worker: Worker) -> None:
    captured: list[BaseException] = []

    def boom(token):  # type: ignore[no-untyped-def]
        raise RuntimeError("炸了")

    worker.submit(boom, on_error=captured.append)
    assert worker.wait_idle(5) is True
    scheduler.run_pending()
    assert len(captured) == 1
    assert isinstance(captured[0], RuntimeError)


def test_cancelled_exception_marks_cancelled(scheduler: FakeScheduler, worker: Worker) -> None:
    events: list[str] = []

    def fn(token):  # type: ignore[no-untyped-def]
        raise Cancelled()

    worker.submit(fn, on_done=lambda _r: events.append("done"), on_cancelled=lambda: events.append("cancelled"))
    assert worker.wait_idle(5) is True
    scheduler.run_pending()
    assert events == ["cancelled"]


def test_result_of_cancelled_task_is_dropped(scheduler: FakeScheduler) -> None:
    """AC-11：取消后旧结果必须丢弃，不能刷新界面。"""
    worker = Worker(scheduler, poll_ms=1)
    started = threading.Event()
    release = threading.Event()
    events: list[object] = []

    def fn(token):  # type: ignore[no-untyped-def]
        started.set()
        release.wait(5)
        return "旧结果"

    task = worker.submit(fn, on_done=events.append, on_cancelled=lambda: events.append("cancelled"))
    assert started.wait(5) is True

    task.cancel()
    release.set()
    assert worker.wait_idle(5) is True
    scheduler.run_pending()

    assert "旧结果" not in events
    assert events == ["cancelled"]
    worker.shutdown()


def test_jobs_run_serially_in_order(scheduler: FakeScheduler, worker: Worker) -> None:
    lock = threading.Lock()
    order: list[int] = []
    active = 0
    peak = 0

    def make(index: int):
        def run(token):  # type: ignore[no-untyped-def]
            nonlocal active, peak
            with lock:
                active += 1
                peak = max(peak, active)
            time.sleep(0.02)
            with lock:
                active -= 1
                order.append(index)
            return index

        return run

    for index in range(5):
        worker.submit(make(index))

    assert worker.wait_idle(5) is True
    scheduler.run_pending()
    assert order == [0, 1, 2, 3, 4]
    assert peak == 1, "任务必须串行执行"


def test_cancel_all_cancels_queued_jobs(scheduler: FakeScheduler) -> None:
    worker = Worker(scheduler, poll_ms=1)
    release = threading.Event()
    events: list[object] = []

    worker.submit(lambda token: release.wait(5))
    worker.submit(
        lambda token: "第二个",
        on_done=events.append,
        on_cancelled=lambda: events.append("cancelled"),
    )
    worker.cancel_all()
    release.set()

    assert worker.wait_idle(5) is True
    scheduler.run_pending()
    assert events == ["cancelled"]
    worker.shutdown()


def test_callback_exception_does_not_break_pump(scheduler: FakeScheduler) -> None:
    worker = Worker(scheduler, poll_ms=1)
    received: list[int] = []

    def boom(_result: object) -> None:
        raise RuntimeError("回调炸了")

    worker.submit(lambda token: 1, on_done=boom)
    worker.submit(lambda token: 2, on_done=received.append)

    assert worker.wait_idle(5) is True
    scheduler.run_pending()
    assert received == [2]
    worker.shutdown()


def test_wait_idle_times_out_while_running(scheduler: FakeScheduler) -> None:
    worker = Worker(scheduler, poll_ms=1)
    release = threading.Event()
    worker.submit(lambda token: release.wait(5))

    assert worker.wait_idle(0.05) is False
    release.set()
    assert worker.wait_idle(5) is True
    worker.shutdown()


def test_shutdown_stops_polling(scheduler: FakeScheduler) -> None:
    """AC-24：关窗后不再有排程，回调不会再打到已销毁的控件上。"""
    worker = Worker(scheduler, poll_ms=1)
    worker.start()
    assert scheduler.pending >= 1

    worker.shutdown()

    assert scheduler.pending == 0
    assert scheduler.cancelled, "必须调用 after_cancel"
    worker.pump()  # 关停后再 pump 不应重新排程
    assert scheduler.pending == 0


def test_default_poll_interval_is_50ms(scheduler: FakeScheduler) -> None:
    assert POLL_MS == 50
    worker = Worker(scheduler)
    worker.start()
    assert 50 in scheduler.delays
    worker.shutdown()
