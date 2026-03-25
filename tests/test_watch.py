from __future__ import annotations

import time

import yaml
from typer.testing import CliRunner

from keel.cli.app import app


def test_watch_once_runs_awareness_and_updates_reports(fixture_repo) -> None:
    repo = fixture_repo("multi_entry_repo")
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
    notes = repo / "docs" / "notes.md"
    notes.parent.mkdir(parents=True, exist_ok=True)
    notes.write_text("implementation drift notes\n", encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "--repo",
            str(repo),
            "--json",
            "watch",
            "--once",
            "--mode",
            "hard",
        ],
    )

    assert result.exit_code == 0, result.stdout
    payload = yaml.safe_load(result.stdout)
    assert payload["mode"] == "once"
    assert payload["events_observed"] == 1
    assert payload["validation_id"].startswith("validation-")
    assert payload["drift_id"].startswith("drift-")
    assert payload["trace_id"].startswith("trace-")
    assert payload["brief"].endswith(".keel/session/current-brief.md")
    assert payload["alerts_count"] >= 1
    assert payload["recent_alerts"]
    assert (repo / ".keel" / "reports" / "validation").exists()
    assert (repo / ".keel" / "reports" / "drift").exists()
    assert (repo / ".keel" / "reports" / "trace").exists()
    assert (repo / ".keel" / "session" / "alerts.yaml").exists()


def test_watch_json_requires_once(fixture_repo) -> None:
    repo = fixture_repo("messy_repo")
    runner = CliRunner()

    result = runner.invoke(app, ["--repo", str(repo), "--json", "watch"])

    assert result.exit_code != 0
    assert "--once" in result.output
