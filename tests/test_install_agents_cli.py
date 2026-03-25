from __future__ import annotations

import json
import time

from typer.testing import CliRunner

from keel.cli.app import app
from tests.conftest import keel_bootstrap


def test_install_command_installs_assets_and_starts_companion(tmp_path, fixture_repo) -> None:
    runner = CliRunner()
    codex_home = tmp_path / "codex-home"
    claude_home = tmp_path / "claude-home"
    repo = fixture_repo("messy_repo")
    (repo / ".git" / "hooks").mkdir(parents=True, exist_ok=True)

    result = runner.invoke(
        app,
        [
            "--repo",
            str(repo),
            "--json",
            "install",
            "--codex-home",
            str(codex_home),
            "--claude-home",
            str(claude_home),
        ],
    )

    assert result.exit_code == 0, result.stdout
    assert (repo / ".codex" / "config.toml").exists()
    assert (repo / ".claude" / "settings.json").exists()
    assert (repo / ".claude" / "hooks" / "keel_ui_context.py").exists()
    assert (repo / ".git" / "hooks" / "pre-commit").exists()

    status = runner.invoke(app, ["--repo", str(repo), "--json", "companion", "status"])
    assert status.exit_code == 0, status.stdout
    assert '"running": true' in status.stdout
    assert '"fresh": true' in status.stdout
    settings = json.loads((repo / ".claude" / "settings.json").read_text(encoding="utf-8"))
    assert "hooks" in settings

    stop = runner.invoke(app, ["--repo", str(repo), "--json", "companion", "stop"])
    assert stop.exit_code == 0, stop.stdout


def test_install_non_git_repo_reports_companion_only_mode(tmp_path, fixture_repo) -> None:
    runner = CliRunner()
    codex_home = tmp_path / "codex-home"
    claude_home = tmp_path / "claude-home"
    repo = fixture_repo("messy_repo")

    result = runner.invoke(
        app,
        [
            "--repo",
            str(repo),
            "--json",
            "install",
            "--codex-home",
            str(codex_home),
            "--claude-home",
            str(claude_home),
        ],
    )

    assert result.exit_code == 0, result.stdout
    assert "companion-only mode" in result.stdout
    assert (repo / ".claude" / "settings.json").exists()
    assert (repo / ".codex" / "config.toml").exists()
    stop = runner.invoke(app, ["--repo", str(repo), "--json", "companion", "stop"])
    assert stop.exit_code == 0, stop.stdout


def test_install_detects_stale_active_session_and_offers_recover_or_replan(tmp_path, fixture_repo) -> None:
    runner = CliRunner()
    codex_home = tmp_path / "codex-home"
    claude_home = tmp_path / "claude-home"
    repo = fixture_repo("messy_repo")

    keel_bootstrap(repo, runner, goal_mode="understand", success_criterion="Map the runtime path")

    drift_note = repo / "docs" / "drift-notes.md"
    drift_note.parent.mkdir(parents=True, exist_ok=True)
    drift_note.write_text("post-start drift trigger\n", encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "--repo",
            str(repo),
            "--json",
            "install",
            "--codex-home",
            str(codex_home),
            "--claude-home",
            str(claude_home),
        ],
    )

    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    handoff = payload["session_handoff"]
    assert handoff["stale_session_detected"] is False
    assert any("Auto-checkpointed existing KEEL session before install" in message for message in payload["messages"])
    assert "Existing KEEL session still looks aligned after install." in result.stdout

    stop = runner.invoke(app, ["--repo", str(repo), "--json", "companion", "stop"])
    assert stop.exit_code == 0, stop.stdout


def test_install_records_bootstrap_delta_and_checkpoint_before_drift(tmp_path, fixture_repo) -> None:
    runner = CliRunner()
    codex_home = tmp_path / "codex-home"
    claude_home = tmp_path / "claude-home"
    repo = fixture_repo("messy_repo")

    install = runner.invoke(
        app,
        [
            "--repo",
            str(repo),
            "--json",
            "install",
            "--codex-home",
            str(codex_home),
            "--claude-home",
            str(claude_home),
        ],
    )
    assert install.exit_code == 0, install.stdout

    payload = json.loads(install.stdout)
    assert any("KEEL install baseline recorded" in message for message in payload["messages"])
    assert list((repo / "keel" / "specs" / "deltas").glob("*.yaml"))

    drift = runner.invoke(app, ["--repo", str(repo), "--json", "drift"])
    assert drift.exit_code == 0, drift.stdout
    drift_payload = json.loads(drift.stdout)
    drift_codes = {finding["code"] for finding in drift_payload["findings"]}
    assert "KEE-DRF-001" not in drift_codes
    assert "KEE-DRF-009" not in drift_codes
    assert "KEE-DRF-019" not in drift_codes
    assert "KEE-DRF-021" not in drift_codes

    stop = runner.invoke(app, ["--repo", str(repo), "--json", "companion", "stop"])
    assert stop.exit_code == 0, stop.stdout


def test_reinstall_clears_managed_install_drift_memory(tmp_path, fixture_repo) -> None:
    runner = CliRunner()
    codex_home = tmp_path / "codex-home"
    claude_home = tmp_path / "claude-home"
    repo = fixture_repo("messy_repo")

    first = runner.invoke(
        app,
        [
            "--repo",
            str(repo),
            "--json",
            "install",
            "--codex-home",
            str(codex_home),
            "--claude-home",
            str(claude_home),
        ],
    )
    assert first.exit_code == 0, first.stdout

    drift_memory = repo / ".keel" / "session" / "drift-memory.yaml"
    drift_memory.write_text(
        "events:\n"
        "  - seen_at: '2026-03-24T10:00:00-05:00'\n"
        "    code: KEE-DRF-001\n"
        "    layer: session drift\n"
        "    severity: warning\n"
        "    confidence: inferred-high-confidence\n"
        "    summary: Repository changed after the latest scan\n"
        "    evidence:\n"
        "      - .claude/settings.json\n"
        "    changed_files:\n"
        "      - .claude/settings.json\n"
        "    cluster_key: session drift:.claude\n",
        encoding="utf-8",
    )
    (repo / ".keel" / "session" / "alerts.yaml").write_text(
        "alerts:\n"
        "  - alert_id: ALT-test\n"
        "    key: test\n"
        "    source: drift\n"
        "    rule: KEE-DRF-021\n"
        "    summary: install cluster\n"
        "    detail: install cluster\n"
        "    severity: warning\n"
        "    confidence: inferred-high-confidence\n"
        "    first_seen_at: '2026-03-24T10:00:00-05:00'\n"
        "    last_seen_at: '2026-03-24T10:00:00-05:00'\n"
        "    count: 1\n"
        "    evidence:\n"
        "      - .claude/settings.json\n"
        "    next_action: ignore\n",
        encoding="utf-8",
    )

    second = runner.invoke(
        app,
        [
            "--repo",
            str(repo),
            "--json",
            "install",
            "--codex-home",
            str(codex_home),
            "--claude-home",
            str(claude_home),
        ],
    )
    assert second.exit_code == 0, second.stdout

    assert ".claude/settings.json" not in drift_memory.read_text(encoding="utf-8")
    assert "ALT-test" not in (repo / ".keel" / "session" / "alerts.yaml").read_text(encoding="utf-8")

    stop = runner.invoke(app, ["--repo", str(repo), "--json", "companion", "stop"])
    assert stop.exit_code == 0, stop.stdout


def test_install_updates_existing_relative_claude_statusline_command(tmp_path, fixture_repo) -> None:
    runner = CliRunner()
    codex_home = tmp_path / "codex-home"
    claude_home = tmp_path / "claude-home"
    repo = fixture_repo("messy_repo")
    settings_path = repo / ".claude" / "settings.json"
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(
        json.dumps(
            {
                "statusLine": {
                    "type": "command",
                    "command": "python3 .claude/statusline.py",
                    "padding": 1,
                }
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    install = runner.invoke(
        app,
        [
            "--repo",
            str(repo),
            "--json",
            "install",
            "--codex-home",
            str(codex_home),
            "--claude-home",
            str(claude_home),
        ],
    )
    assert install.exit_code == 0, install.stdout
    payload = json.loads(install.stdout)
    assert any("Updated repo-local agent file" in message for message in payload["messages"])

    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    assert ".claude/statusline.py" in settings["statusLine"]["command"]
    assert "hooks" in settings

    stop = runner.invoke(app, ["--repo", str(repo), "--json", "companion", "stop"])
    assert stop.exit_code == 0, stop.stdout


def test_install_ignores_editable_install_egg_info_drift(tmp_path, fixture_repo) -> None:
    runner = CliRunner()
    codex_home = tmp_path / "codex-home"
    claude_home = tmp_path / "claude-home"
    repo = fixture_repo("messy_repo")

    keel_bootstrap(repo, runner, goal_mode="understand", success_criterion="Map the runtime path")

    install = runner.invoke(
        app,
        [
            "--repo",
            str(repo),
            "--json",
            "install",
            "--codex-home",
            str(codex_home),
            "--claude-home",
            str(claude_home),
        ],
    )
    assert install.exit_code == 0, install.stdout

    time.sleep(1)
    egg_info_dir = repo / "src" / "keel_cli.egg-info"
    egg_info_dir.mkdir(parents=True, exist_ok=True)
    (egg_info_dir / "PKG-INFO").write_text("editable install metadata\n", encoding="utf-8")
    (egg_info_dir / "SOURCES.txt").write_text("src/keel_cli.egg-info/PKG-INFO\n", encoding="utf-8")

    drift = runner.invoke(app, ["--repo", str(repo), "--json", "drift"])
    assert drift.exit_code == 0, drift.stdout
    drift_payload = json.loads(drift.stdout)
    drift_codes = {finding["code"] for finding in drift_payload["findings"]}
    assert "KEE-DRF-001" not in drift_codes
    assert "KEE-DRF-012" not in drift_codes
    assert "KEE-DRF-014" not in drift_codes

    stop = runner.invoke(app, ["--repo", str(repo), "--json", "companion", "stop"])
    assert stop.exit_code == 0, stop.stdout


def test_install_reports_path_guidance_when_user_bin_missing(tmp_path, fixture_repo, monkeypatch) -> None:
    runner = CliRunner()
    codex_home = tmp_path / "codex-home"
    claude_home = tmp_path / "claude-home"
    repo = fixture_repo("messy_repo")
    monkeypatch.setenv("PATH", "/usr/bin:/bin")

    install = runner.invoke(
        app,
        [
            "--repo",
            str(repo),
            "--json",
            "install",
            "--codex-home",
            str(codex_home),
            "--claude-home",
            str(claude_home),
        ],
    )
    assert install.exit_code == 0, install.stdout
    payload = json.loads(install.stdout)
    assert any("may not be on PATH yet" in message for message in payload["messages"])
    assert any("python3 -m keel" in message for message in payload["messages"])

    stop = runner.invoke(app, ["--repo", str(repo), "--json", "companion", "stop"])
    assert stop.exit_code == 0, stop.stdout
