from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import yaml

from typer.testing import CliRunner

from keel.cli.app import app

PYTHON = sys.executable


def test_companion_start_status_stop_cycle(fixture_repo) -> None:
    repo = fixture_repo("multi_entry_repo")
    (repo / ".git" / "hooks").mkdir(parents=True, exist_ok=True)
    runner = CliRunner()

    start = runner.invoke(
        app,
        [
            "--repo",
            str(repo),
            "--json",
            "companion",
            "start",
            "--interval",
            "0.5",
        ],
    )
    assert start.exit_code == 0, start.stdout
    assert (repo / ".keel" / "session" / "companion.yaml").exists()

    time.sleep(0.4)
    status = runner.invoke(app, ["--repo", str(repo), "--json", "companion", "status"])
    assert status.exit_code == 0, status.stdout
    assert '"running": true' in status.stdout
    payload = yaml.safe_load(status.stdout)
    assert payload["fresh"] is True
    assert payload["last_awareness_at"]

    stop = runner.invoke(app, ["--repo", str(repo), "--json", "companion", "stop"])
    assert stop.exit_code == 0, stop.stdout

    status_after = runner.invoke(app, ["--repo", str(repo), "--json", "companion", "status"])
    assert status_after.exit_code == 0, status_after.stdout
    assert '"running": false' in status_after.stdout


def test_install_git_hooks_preserves_existing_hook(fixture_repo) -> None:
    repo = fixture_repo("messy_repo")
    hooks_dir = repo / ".git" / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    existing = hooks_dir / "pre-commit"
    existing.write_text("#!/bin/sh\necho existing hook\n", encoding="utf-8")
    existing.chmod(0o755)
    runner = CliRunner()

    result = runner.invoke(app, ["--repo", str(repo), "companion", "start"])

    assert result.exit_code == 0, result.stdout
    local_hook = hooks_dir / "pre-commit.local"
    assert local_hook.exists()
    assert "existing hook" in local_hook.read_text(encoding="utf-8")
    managed = existing.read_text(encoding="utf-8")
    assert "KEEL managed hook" in managed
    stop = runner.invoke(app, ["--repo", str(repo), "--json", "companion", "stop"])
    assert stop.exit_code == 0, stop.stdout


def test_drift_dismiss_clears_cluster_and_alert_feed(fixture_repo) -> None:
    repo = fixture_repo("messy_repo")
    runner = CliRunner()

    start = runner.invoke(
        app,
        [
            "--repo",
            str(repo),
            "--json",
            "start",
            "--goal-mode",
            "understand",
            "--success-criterion",
            "Map the runtime path",
        ],
    )
    assert start.exit_code == 0, start.stdout

    time.sleep(1)
    changed = repo / "docs" / "drift-cluster.md"
    changed.parent.mkdir(parents=True, exist_ok=True)
    changed.write_text("cluster drift\n", encoding="utf-8")

    cluster_seen = False
    for _ in range(3):
        drift = runner.invoke(app, ["--repo", str(repo), "--json", "drift", "--mode", "auto"])
        assert drift.exit_code == 0, drift.stdout
        payload = yaml.safe_load(drift.stdout)
        codes = {finding["code"] for finding in payload["findings"]}
        if "KEE-DRF-021" in codes:
            cluster_seen = True
            break

    assert cluster_seen is True

    dismiss = runner.invoke(app, ["--repo", str(repo), "--json", "drift", "--dismiss", "KEE-DRF-021"])
    assert dismiss.exit_code == 0, dismiss.stdout

    drift_after = runner.invoke(app, ["--repo", str(repo), "--json", "drift", "--mode", "auto"])
    assert drift_after.exit_code == 0, drift_after.stdout
    payload_after = yaml.safe_load(drift_after.stdout)
    codes_after = {finding["code"] for finding in payload_after["findings"]}
    assert "KEE-DRF-021" not in codes_after

    alerts_payload = yaml.safe_load((repo / ".keel" / "session" / "alerts.yaml").read_text(encoding="utf-8"))
    assert all(alert.get("rule") != "KEE-DRF-021" for alert in alerts_payload.get("alerts", []))


def test_command_local_json_flags_work_after_command_name(fixture_repo) -> None:
    repo = fixture_repo("messy_repo")
    runner = CliRunner()

    start = runner.invoke(
        app,
        [
            "--repo",
            str(repo),
            "start",
            "--goal-mode",
            "understand",
            "--success-criterion",
            "Map the runtime path",
        ],
    )
    assert start.exit_code == 0, start.stdout

    base = [PYTHON, "-m", "keel.cli.main", "--repo", str(repo)]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).resolve().parent.parent / "src")

    validate = subprocess.run(base + ["validate", "--json"], capture_output=True, text=True, env=env, check=True)
    validate_payload = yaml.safe_load(validate.stdout)
    assert "status" in validate_payload

    drift = subprocess.run(base + ["drift", "--json"], capture_output=True, text=True, env=env, check=True)
    drift_payload = yaml.safe_load(drift.stdout)
    assert "findings" in drift_payload
