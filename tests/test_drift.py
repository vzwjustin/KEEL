from __future__ import annotations

import time

import yaml
from typer.testing import CliRunner

from keel.cli.app import app


def test_drift_flags_unmapped_changes_and_updates_brief(fixture_repo) -> None:
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
    sidequest = repo / "docs" / "notes.md"
    sidequest.parent.mkdir(parents=True, exist_ok=True)
    sidequest.write_text("side quest\n", encoding="utf-8")

    drift = runner.invoke(app, ["--repo", str(repo), "--json", "drift", "--mode", "hard"])
    assert drift.exit_code == 0, drift.stdout
    assert "KEE-DRF-009" in drift.stdout or "KEE-DRF-019" in drift.stdout

    brief = (repo / ".keel" / "session" / "current-brief.md").read_text(encoding="utf-8")
    assert "Blockers:" in brief


def test_done_blocks_when_feature_goal_has_no_delta(fixture_repo) -> None:
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
            "add-feature",
        ],
    )
    assert start.exit_code == 0, start.stdout

    drift = runner.invoke(app, ["--repo", str(repo), "--json", "drift", "--mode", "hard"])
    assert drift.exit_code == 0, drift.stdout
    assert "KEE-DRF-003" in drift.stdout

    done = runner.invoke(app, ["--repo", str(repo), "--json", "done"])
    assert done.exit_code == 0, done.stdout
    assert '"status": "blocked"' in done.stdout


def test_strict_mode_blocks_done_on_validation_warning(fixture_repo) -> None:
    repo = fixture_repo("messy_repo")
    config = repo / ".keel" / "config.yaml"
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text(
        "\n".join(
            [
                "strictness: strict",
                "research_enabled: false",
                "research_timeout_seconds: 6",
                "max_scan_files: 4000",
                "ignored_directories:",
                "  - .git",
                "  - __pycache__",
                "authoritative_config_names:",
                "  - pyproject.toml",
                "output_format: text",
                "non_authoritative_path_parts:",
                "  - fixtures",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    runner = CliRunner()

    start = runner.invoke(app, ["--repo", str(repo), "--json", "start", "--goal-mode", "ship-mvp"])
    assert start.exit_code == 0, start.stdout

    validate = runner.invoke(app, ["--repo", str(repo), "--json", "validate"])
    assert validate.exit_code == 0, validate.stdout
    assert '"KEE-VAL-003"' in validate.stdout or '"KEE-VAL-004"' in validate.stdout

    done = runner.invoke(app, ["--repo", str(repo), "--json", "done"])
    assert done.exit_code == 0, done.stdout
    assert '"status": "blocked"' in done.stdout


def test_delta_accepts_summary_option(fixture_repo) -> None:
    repo = fixture_repo("messy_repo")
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "--repo",
            str(repo),
            "--json",
            "delta",
            "--summary",
            "Record the intended feature delta",
            "--impacted-path",
            "src/messy_app",
        ],
    )

    assert result.exit_code == 0, result.stdout
    payload = yaml.safe_load(result.stdout)
    assert payload["summary"] == "Record the intended feature delta"


def test_drift_builds_cluster_from_repeated_weak_signals(fixture_repo) -> None:
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

    for index in range(4):
        time.sleep(1)
        note = repo / "docs" / f"notes-{index}.md"
        note.parent.mkdir(parents=True, exist_ok=True)
        note.write_text(f"side quest {index}\n", encoding="utf-8")
        drift = runner.invoke(app, ["--repo", str(repo), "--json", "drift", "--mode", "soft"])
        assert drift.exit_code == 0, drift.stdout

    payload = yaml.safe_load(drift.stdout)
    assert payload["clusters"]
    cluster = payload["clusters"][0]
    assert cluster["event_count"] >= 3
    assert cluster["timeline"]
    assert "KEE-DRF-021" in drift.stdout


def test_drift_cluster_has_cooldown_and_does_not_reemit_immediately(fixture_repo) -> None:
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

    drift = None
    for index in range(4):
        time.sleep(1)
        note = repo / "docs" / f"cooldown-{index}.md"
        note.parent.mkdir(parents=True, exist_ok=True)
        note.write_text(f"cooldown {index}\n", encoding="utf-8")
        drift = runner.invoke(app, ["--repo", str(repo), "--json", "drift", "--mode", "soft"])
        assert drift.exit_code == 0, drift.stdout

    first_payload = yaml.safe_load(drift.stdout)
    assert any(finding["code"] == "KEE-DRF-021" for finding in first_payload["findings"])

    repeat = runner.invoke(app, ["--repo", str(repo), "--json", "drift", "--mode", "soft"])
    assert repeat.exit_code == 0, repeat.stdout
    repeat_payload = yaml.safe_load(repeat.stdout)
    assert all(finding["code"] != "KEE-DRF-021" for finding in repeat_payload["findings"])
    assert not repeat_payload["clusters"]
