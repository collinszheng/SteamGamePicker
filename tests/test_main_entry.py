"""M7 打包相关：入口自检模式测试（验证打包产物用）。"""

from __future__ import annotations

import json
from pathlib import Path

from main import main


def test_selftest_writes_report(tmp_path: Path, monkeypatch) -> None:
    """自检模式必须报告 Tk / Pillow / requests 可用（被打进包的关键依赖）。"""
    monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))
    report = tmp_path / "report.json"

    code = main(["--selftest", "--report", str(report)])

    assert code == 0
    data = json.loads(report.read_text(encoding="utf-8"))
    assert data["tk_ok"] is True
    assert data["pillow_ok"] is True
    assert data["requests_ok"] is True
    assert data["frozen"] is False, "源码运行时不应报告为已打包"
    assert isinstance(data["startup_ms"], (int, float))
    assert "version" in data


def test_selftest_tolerates_corrupt_config(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))
    config_dir = tmp_path / "Roaming" / "SteamGamePicker"
    config_dir.mkdir(parents=True)
    (config_dir / "config.json").write_text("{损坏", encoding="utf-8")
    report = tmp_path / "report.json"

    assert main(["--selftest", "--report", str(report)]) == 0

    data = json.loads(report.read_text(encoding="utf-8"))
    assert data["config_corrupted"] is True
    assert list(config_dir.glob("config.corrupt-*.json")), "损坏配置应被备份"
