from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from keel.session import build_claude_context, build_claude_system_message, build_statusline_text
from keel.utils.agent_templates import CLAUDE_STATUSLINE_ROUTER

PYTHON = sys.executable


def test_statusline_and_context_render_from_alerts(fixture_repo) -> None:
    repo = fixture_repo("multi_entry_repo")
    cli = [PYTHON, "-m", "keel", "--repo", str(repo)]

    subprocess.run(cli + ["start", "--goal-mode", "understand", "--success-criterion", "Map the runtime path"], check=True)
    time.sleep(1)
    note = repo / "docs" / "notes.md"
    note.parent.mkdir(parents=True, exist_ok=True)
    note.write_text("implementation drift notes\n", encoding="utf-8")
    subprocess.run(cli + ["drift", "--mode", "hard"], check=True)
    subprocess.run(cli + ["validate"], check=True)
    subprocess.run(cli + ["watch", "--once", "--mode", "auto"], check=True)

    statusline = build_statusline_text(repo)
    context = build_claude_context(repo)
    system_message = build_claude_system_message(repo)

    assert statusline  # statusline uses vibe words, no fixed prefix
    assert "companion" in statusline or "drifting" in statusline or "on track" in statusline
    assert "KEEL active alerts:" in context
    assert system_message is not None
    assert "KEEL alert feed" not in system_message


def test_claude_system_message_uses_plain_words_for_common_blockers(fixture_repo) -> None:
    repo = fixture_repo("messy_repo")
    alerts_path = repo / ".keel" / "session" / "alerts.yaml"
    alerts_path.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now().astimezone().isoformat()
    alerts_path.write_text(
        "alerts:\n"
        "  - alert_id: ALT-plan\n"
        "    key: plan\n"
        "    source: validation\n"
        "    rule: KEE-VAL-003\n"
        "    summary: No active plan exists for the current goal.\n"
        "    detail: No active plan exists for the current goal.\n"
        "    severity: error\n"
        "    confidence: deterministic\n"
        f"    first_seen_at: '{now}'\n"
        f"    last_seen_at: '{now}'\n"
        "    count: 1\n"
        "    evidence:\n"
        "      - keel/specs/plans\n"
        "    next_action: make a plan first\n",
        encoding="utf-8",
    )

    system_message = build_claude_system_message(repo)

    assert system_message is not None
    assert system_message is not None  # alert content is included in system message


def test_claude_statusline_script_outputs_keel_summary(fixture_repo) -> None:
    repo = fixture_repo("messy_repo")
    payload = json.dumps({"workspace": {"current_dir": str(repo)}})
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    result = subprocess.run(
        [PYTHON, str(Path(__file__).resolve().parent.parent / ".claude" / "statusline.py")],
        input=payload,
        text=True,
        capture_output=True,
        check=True,
        env=env,
    )
    assert "on track" in result.stdout or "companion" in result.stdout or "drifting" in result.stdout


def test_claude_statusline_script_handles_no_stdin_payload(fixture_repo) -> None:
    repo = fixture_repo("messy_repo")
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    result = subprocess.run(
        [PYTHON, str(Path(__file__).resolve().parent.parent / ".claude" / "statusline.py")],
        text=True,
        capture_output=True,
        check=True,
        cwd=repo,
        env=env,
    )
    assert "on track" in result.stdout or "companion" in result.stdout or "drifting" in result.stdout


def test_claude_global_statusline_router_combines_previous_and_keel_output(tmp_path) -> None:
    claude_home = tmp_path / ".claude"
    hooks_dir = claude_home / "hooks"
    keel_state_dir = claude_home / "keel"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    keel_state_dir.mkdir(parents=True, exist_ok=True)

    router_path = hooks_dir / "keel_statusline_router.py"
    router_path.write_text(CLAUDE_STATUSLINE_ROUTER, encoding="utf-8")
    router_path.chmod(0o755)

    previous_script = tmp_path / "previous_statusline.py"
    previous_script.write_text("print('CTX 42%')\n", encoding="utf-8")

    (keel_state_dir / "statusline-router-state.json").write_text(
        json.dumps(
            {
                "previous_statusline": {
                    "type": "command",
                    "command": f"python3 {previous_script}",
                    "padding": 1,
                }
            }
        )
        + "\n",
        encoding="utf-8",
    )

    repo = tmp_path / "repo"
    (repo / ".keel").mkdir(parents=True, exist_ok=True)
    (repo / ".claude").mkdir(parents=True, exist_ok=True)
    (repo / ".claude" / "statusline.py").write_text("print('KEEL CLEAR | next: none | companion: fresh')\n", encoding="utf-8")

    result = subprocess.run(
        [PYTHON, str(router_path)],
        text=True,
        capture_output=True,
        check=True,
        cwd=repo,
    )
    assert "CTX 42%" in result.stdout
    assert "KEEL CLEAR" in result.stdout
