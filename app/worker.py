"""后台任务执行器（PRD 7.4）。

铁律：
1. **主线程只做 UI** —— 所有网络调用在这里的工作线程执行，结果经队列回到主线程；
2. 主线程用 ``after(poll_ms)`` 轮询结果队列（PRD 5.5「避免阻塞 UI」）；
3. 每个任务持有取消令牌；关窗 / 取消 / 换目标时旧结果必须被丢弃，
   且绝不允许操作已销毁的控件（回调只在主线程被调用）。

本模块自身不 import tkinter —— 只依赖一个"能安排定时回调"的调度器，
这样既可以在真实 Tk 上跑，也能在测试里用确定性调度器跑。
"""

from __future__ import annotations

import queue
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from logging import Logger
from typing import Any, Protocol

from app.cancellation import CancelToken, Cancelled
from app.logging_setup import get_logger

POLL_MS = 50


class Scheduler(Protocol):
    """最小调度接口；Tk 的 ``after`` / ``after_cancel`` 天然满足。"""

    def after(self, ms: int, callback: Callable[[], None]) -> Any: ...

    def after_cancel(self, identifier: Any) -> None: ...


class Task:
    """提交后的任务句柄。"""

    def __init__(self, token: CancelToken) -> None:
        self._token = token

    @property
    def cancelled(self) -> bool:
        return self._token.cancelled

    def cancel(self) -> None:
        self._token.cancel()


@dataclass
class _Job:
    fn: Callable[[CancelToken], Any]
    token: CancelToken
    on_done: Callable[[Any], None] | None = None
    on_error: Callable[[BaseException], None] | None = None
    on_cancelled: Callable[[], None] | None = None


class Worker:
    """串行后台执行器：任务按提交顺序执行，结果回主线程。"""

    def __init__(
        self,
        scheduler: Scheduler,
        *,
        poll_ms: int = POLL_MS,
        logger: Logger | None = None,
    ) -> None:
        self._scheduler = scheduler
        self._poll_ms = poll_ms
        self._logger = logger or get_logger()
        self._jobs: queue.Queue[_Job | None] = queue.Queue()
        self._results: queue.Queue[tuple[str, _Job, Any, BaseException | None]] = queue.Queue()
        self._thread: threading.Thread | None = None
        self._after_id: Any = None
        self._stopped = False
        self._active = False
        self._active_token: CancelToken | None = None
        self._condition = threading.Condition()
        self._tasks: list[Task] = []

    # ------------------------------------------------------------------ 生命周期
    def start(self) -> None:
        if self._thread is None or not self._thread.is_alive():
            self._stopped = False
            self._thread = threading.Thread(target=self._loop, name="sgp-worker", daemon=True)
            self._thread.start()
        self._schedule_pump()

    def shutdown(self, timeout: float = 0.5) -> None:
        """关窗收尾：停止轮询、取消当前任务，不等待长时间网络调用（PRD 7.4）。"""
        self._stopped = True
        self.cancel_all()
        if self._after_id is not None:
            try:
                self._scheduler.after_cancel(self._after_id)
            except Exception:  # pragma: no cover - 控件已销毁
                pass
            self._after_id = None
        self._jobs.put(None)
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout)

    # ------------------------------------------------------------------ 提交/取消
    def submit(
        self,
        fn: Callable[[CancelToken], Any],
        *,
        on_done: Callable[[Any], None] | None = None,
        on_error: Callable[[BaseException], None] | None = None,
        on_cancelled: Callable[[], None] | None = None,
    ) -> Task:
        self.start()
        token = CancelToken()
        task = Task(token)
        self._tasks.append(task)
        self._jobs.put(_Job(fn, token, on_done, on_error, on_cancelled))
        return task

    def cancel_all(self) -> None:
        with self._condition:
            token = self._active_token
            pending = list(self._jobs.queue)
            self._condition.notify_all()
        for job in pending:
            if job is not None:
                job.token.cancel()
        if token is not None:
            token.cancel()
        for task in self._tasks:
            task.cancel()

    # ------------------------------------------------------------------ 工作线程
    def _loop(self) -> None:
        while True:
            job = self._jobs.get()
            if job is None:  # 关窗哨兵
                break
            with self._condition:
                self._active = True
                self._active_token = job.token
                self._condition.notify_all()
            try:
                if job.token.cancelled:
                    raise Cancelled()
                result = job.fn(job.token)
            except Cancelled:
                self._results.put(("cancelled", job, None, None))
            except BaseException as exc:  # noqa: BLE001 - 交给主线程统一处理
                self._results.put(("error", job, None, exc))
            else:
                self._results.put(("done", job, result, None))
            finally:
                with self._condition:
                    self._active = False
                    self._active_token = None
                    self._condition.notify_all()

    # ------------------------------------------------------------------ 主线程
    def pump(self) -> None:
        """主线程轮询：派发结果给自己的回调。"""
        self._after_id = None
        while True:
            try:
                status, job, result, error = self._results.get_nowait()
            except queue.Empty:
                break
            if job.token.cancelled:
                # 旧结果一律丢弃（AC-11），但仍通知"已取消"以便界面复位
                self._safe_call(job.on_cancelled)
                continue
            if status == "done":
                self._safe_call(job.on_done, result)
            elif status == "error":
                self._safe_call(job.on_error, error)
            else:
                self._safe_call(job.on_cancelled)
        self._schedule_pump()

    def _schedule_pump(self) -> None:
        if self._stopped:
            return
        try:
            self._after_id = self._scheduler.after(self._poll_ms, self.pump)
        except Exception:  # pragma: no cover - 控件已销毁
            self._after_id = None

    def _safe_call(self, callback: Callable[..., None] | None, *args: Any) -> None:
        if callback is None:
            return
        try:
            callback(*args)
        except Exception:  # pragma: no cover - 回调异常不能拖垮轮询
            self._logger.exception("后台任务回调异常")

    # ------------------------------------------------------------------ 测试辅助
    def wait_idle(self, timeout: float = 5.0) -> bool:
        """等待"队列空且无正在执行的任务"；测试与关窗时使用。"""
        deadline = time.monotonic() + timeout
        with self._condition:
            while True:
                if self._jobs.empty() and not self._active:
                    return True
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                self._condition.wait(remaining)

    @property
    def pending_results(self) -> int:
        return self._results.qsize()
