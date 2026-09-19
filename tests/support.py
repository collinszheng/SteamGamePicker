"""测试替身：脱机 HTTP 会话与样本加载（T2.7）。

样本文件只用于脱机回归：它们如实反映 PRD 7.6 记录的结构
（私密库 200 且无 games 键、success:42、免费游戏无 price_overview 等），
不是线上抓包数据，也不包含任何真实密钥。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> dict[str, Any]:
    path = FIXTURES / name
    return json.loads(path.read_text(encoding="utf-8"))


class FakeResponse:
    def __init__(self, status_code: int = 200, payload: Any = None, content: bytes = b"") -> None:
        self.status_code = status_code
        self._payload = payload
        self.content = content

    def json(self) -> Any:
        if self._payload is None:
            raise ValueError("no json body")
        return self._payload


class FakeSession:
    """按 URL 子串匹配的假会话；可用列表模拟"先失败后成功"。"""

    def __init__(self) -> None:
        self.routes: list[tuple[str, Any]] = []
        self.calls: list[dict[str, Any]] = []
        self.default = FakeResponse(404, {"error": "no route"})

    def add(self, substring: str, response: Any) -> FakeSession:
        self.routes.append((substring, response))
        return self

    def get(self, url: str, params: Any = None, timeout: Any = None) -> FakeResponse:
        self.calls.append({"url": url, "params": dict(params or {}), "timeout": timeout})
        for substring, response in self.routes:
            if substring not in url:
                continue
            if isinstance(response, Exception):
                raise response
            if isinstance(response, list):
                item = response.pop(0) if len(response) > 1 else response[0]
                if isinstance(item, Exception):
                    raise item
                return item
            if callable(response):
                return response(url, params)
            return response
        return self.default


class FakeScheduler:
    """确定性调度器：把 after 回调存起来，由测试显式推进。"""

    def __init__(self) -> None:
        self.jobs: dict[int, Any] = {}
        self.delays: list[int] = []
        self.cancelled: list[int] = []
        self._next = 1

    def after(self, ms: int, callback: Any) -> int:
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

    def run_all(self, limit: int = 500) -> None:
        """反复执行队首回调，直到没有排程（用于跑完整段动画）。"""
        steps = 0
        while self.jobs and steps < limit:
            identifier = next(iter(self.jobs))
            callback = self.jobs.pop(identifier)
            callback()
            steps += 1

    @property
    def pending(self) -> int:
        return len(self.jobs)

    @property
    def total_delay(self) -> int:
        return sum(self.delays)
