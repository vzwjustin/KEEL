from __future__ import annotations

from pathlib import Path

import yaml
from typer.testing import CliRunner

from keel.cli.app import app


def test_start_writes_session_and_brief(fixture_repo) -> None:
    repo = fixture_repo("messy_repo")
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "--repo",
            str(repo),
            "--json",
            "start",
            "--goal-mode",
            "understand",
            "--success-criterion",
            "Produce a useful baseline",
        ],
    )

    assert result.exit_code == 0, result.stdout
    assert (repo / ".keel" / "session" / "current.yaml").exists()
    brief = (repo / ".keel" / "session" / "current-brief.md").read_text()
    assert "Current goal:" in brief
    assert "Next step:" in brief
    assert "Ran `keel start`" in brief

    unresolved = yaml.safe_load((repo / ".keel" / "session" / "unresolved-questions.yaml").read_text())
    assert "questions" in unresolved


def test_wizard_command_runs_interactive_first_run(fixture_repo) -> None:
    repo = fixture_repo("messy_repo")
    runner = CliRunner()
    answers = "\n".join(
        [
            "understand",
            "Understand the real repo shape",
            "scan the current repo",
            "",
            "",
            "local-only",
            "",
            "produce a baseline",
            "",
            "",
            "",
            "",
            "n",
        ]
    ) + "\n"

    result = runner.invoke(
        app,
        ["--repo", str(repo), "wizard"],
        input=answers,
    )

    assert result.exit_code == 0, result.stdout
    assert "KEEL First-Run Wizard" in result.stdout
    brief = (repo / ".keel" / "session" / "current-brief.md").read_text(encoding="utf-8")
    assert "Understand the real repo shape" in brief
