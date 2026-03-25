from __future__ import annotations

import time

import yaml
from typer.testing import CliRunner

from keel.cli.app import app
from tests.conftest import keel_bootstrap


def test_recover_generates_recovery_route_and_updates_brief(fixture_repo) -> None:
    repo = fixture_repo("messy_repo")
    runner = CliRunner()

    keel_bootstrap(repo, runner, goal_mode="add-feature", success_criterion="Ship the intended feature safely", json=True)

    time.sleep(1)
    changed = repo / "src" / "messy_app" / "behavior.py"
    changed.parent.mkdir(parents=True, exist_ok=True)
    changed.write_text("print('new behavior')\n", encoding="utf-8")

    drift = runner.invoke(app, ["--repo", str(repo), "--json", "drift", "--mode", "hard"])
    assert drift.exit_code == 0, drift.stdout

    validate = runner.invoke(app, ["--repo", str(repo), "--json", "validate"])
    assert validate.exit_code == 0, validate.stdout

    recover = runner.invoke(app, ["--repo", str(repo), "--json", "recover"])
    assert recover.exit_code == 0, recover.stdout
    payload = yaml.safe_load(recover.stdout)
    assert payload["recommended_mode"]
    assert payload["steps"]
    assert payload["issues"]
    assert payload["brief_path"].endswith(".keel/session/current-brief.md")

    brief = (repo / ".keel" / "session" / "current-brief.md").read_text(encoding="utf-8")
    assert "Recovery mode selected" in brief


def test_recover_surfaces_step_titles_in_terminal_output(fixture_repo) -> None:
    repo = fixture_repo("messy_repo")
    runner = CliRunner()

    keel_bootstrap(repo, runner, goal_mode="add-feature", success_criterion="Ship the intended feature safely")

    time.sleep(1)
    changed = repo / "src" / "messy_app" / "behavior.py"
    changed.parent.mkdir(parents=True, exist_ok=True)
    changed.write_text("print('new behavior')\n", encoding="utf-8")

    assert runner.invoke(app, ["--repo", str(repo), "drift", "--mode", "hard"]).exit_code == 0
    assert runner.invoke(app, ["--repo", str(repo), "validate"]).exit_code == 0

    recover = runner.invoke(app, ["--repo", str(repo), "recover"])
    assert recover.exit_code == 0, recover.stdout
    assert "step: Replay the intended work" in recover.stdout
    assert "step: Prove the recovery worked" in recover.stdout
