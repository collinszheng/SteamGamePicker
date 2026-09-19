"""运行日志：轮转 + API Key 脱敏（PRD 6.4 第 4、5 条，验收 AC-34）。

约束：
* 单文件 1 MB、保留 3 份；
* 日志中不得出现完整 API Key —— ``key=...`` 查询参数、``"api_key": "..."``
  以及任何已登记的密钥一律脱敏为 ``前4位****``。
"""

from __future__ import annotations

import logging
import re
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Iterable

LOG_FILE_NAME = "app.log"
MAX_BYTES = 1024 * 1024
BACKUP_COUNT = 3
LOGGER_NAME = "steamgp"

# ?key=XXXX / &key=XXXX
_KEY_QUERY_RE = re.compile(r"(key=)[0-9A-Za-z_\-]{6,}", re.IGNORECASE)
# "api_key": "XXXX"
_API_KEY_JSON_RE = re.compile(r'("api_key"\s*:\s*")[^"]*(")', re.IGNORECASE)


def mask(secret: str) -> str:
    """脱敏：保留前 4 位，其余替换为 ``****``。"""
    if not secret:
        return "****"
    return f"{secret[:4]}****" if len(secret) > 4 else "****"


class RedactingFilter(logging.Filter):
    """在日志落盘前抹掉密钥。"""

    def __init__(self, secrets: Iterable[str] = ()) -> None:
        super().__init__()
        self._secrets: set[str] = set()
        for secret in secrets:
            self.add_secret(secret)

    def add_secret(self, secret: str | None) -> None:
        if secret and len(secret) >= 6:
            self._secrets.add(secret)

    def redact(self, text: str) -> str:
        text = _KEY_QUERY_RE.sub(r"\1****", text)
        text = _API_KEY_JSON_RE.sub(r"\1****\2", text)
        for secret in self._secrets:
            if secret in text:
                text = text.replace(secret, mask(secret))
        return text

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            rendered = record.getMessage()
        except Exception:  # pragma: no cover - 格式化失败时不阻断日志
            return True
        redacted = self.redact(rendered)
        if redacted != rendered:
            record.msg = redacted
            record.args = ()
        return True


def setup_logging(
    log_dir: Path,
    *,
    level: int = logging.INFO,
    console: bool = False,
    secrets: Iterable[str] = (),
) -> logging.Logger:
    """初始化并返回应用日志器；重复调用会替换旧 handler（便于测试）。"""
    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(level)
    logger.propagate = False
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()

    redactor = RedactingFilter(secrets)
    formatter = logging.Formatter(
        fmt="%(asctime)s %(levelname)s %(name)s %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )

    file_handler = RotatingFileHandler(
        log_dir / LOG_FILE_NAME,
        maxBytes=MAX_BYTES,
        backupCount=BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.addFilter(redactor)
    logger.addHandler(file_handler)

    if console:  # 开发期使用；打包后为 windowed，无控制台
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)
        stream_handler.addFilter(redactor)
        logger.addHandler(stream_handler)

    logger.redactor = redactor  # type: ignore[attr-defined]  # 便于运行期登记新密钥
    return logger


def get_logger() -> logging.Logger:
    return logging.getLogger(LOGGER_NAME)
