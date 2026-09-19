"""T0.2 日志脱敏测试（AC-34）。"""

from __future__ import annotations

from logging.handlers import RotatingFileHandler
from pathlib import Path

from app.logging_setup import BACKUP_COUNT, MAX_BYTES, mask, setup_logging

SECRET = "1234567890ABCDEF1234567890ABCDEF"


def _read(log_dir: Path) -> str:
    return (log_dir / "app.log").read_text(encoding="utf-8")


def test_writes_log_file_with_rotation_settings(tmp_path: Path) -> None:
    logger = setup_logging(tmp_path)
    logger.info("普通日志")
    text = _read(tmp_path)
    assert "普通日志" in text

    rotating = [h for h in logger.handlers if isinstance(h, RotatingFileHandler)]
    assert len(rotating) == 1
    assert rotating[0].maxBytes == MAX_BYTES
    assert rotating[0].backupCount == BACKUP_COUNT
    assert MAX_BYTES == 1024 * 1024
    assert BACKUP_COUNT == 3


def test_redacts_key_query_parameter(tmp_path: Path) -> None:
    logger = setup_logging(tmp_path)
    logger.info(
        "GET https://api.steampowered.com/IPlayerService/GetOwnedGames/v1/?key=%s&steamid=1",
        SECRET,
    )
    text = _read(tmp_path)
    assert SECRET not in text
    assert "key=****" in text


def test_redacts_registered_secret(tmp_path: Path) -> None:
    logger = setup_logging(tmp_path, secrets=[SECRET])
    logger.info("使用 API Key %s 发起请求", SECRET)
    text = _read(tmp_path)
    assert SECRET not in text
    assert "1234****" in text


def test_redacts_json_api_key_field(tmp_path: Path) -> None:
    logger = setup_logging(tmp_path)
    logger.info('写入配置 {"api_key": "%s"}', SECRET)
    text = _read(tmp_path)
    assert SECRET not in text
    assert '"api_key": "****"' in text


def test_register_secret_after_setup(tmp_path: Path) -> None:
    logger = setup_logging(tmp_path)
    logger.redactor.add_secret(SECRET)  # type: ignore[attr-defined]
    logger.info("运行期登记的密钥 %s", SECRET)
    assert SECRET not in _read(tmp_path)


def test_mask_helper() -> None:
    assert mask("abcdefgh") == "abcd****"
    assert mask("abc") == "****"
    assert mask("") == "****"
