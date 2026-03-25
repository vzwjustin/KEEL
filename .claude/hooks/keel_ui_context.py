#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def load_event() -> dict:
    try:
        return json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        return {}


def repo_root(event: dict) -> Path:
    project_dir = os.environ.get("CLAUDE_PROJECT_DIR")
    if project_dir:
        return Path(project_dir).resolve()
    cwd = event.get("cwd")
    return Path(cwd).resolve() if cwd else Path.cwd().resolve()


def ensure_keel_import(repo: Path) -> None:
    try:
        import keel  # noqa: F401
        return
    except ImportError:
        src_dir = repo / "src"
        if src_dir.exists():
            sys.path.insert(0, str(src_dir))


def run_keel_awareness(repo: Path) -> dict | None:
    env = os.environ.copy()
    src_dir = repo / "src"
    if src_dir.exists():
        existing = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = str(src_dir) if not existing else f"{src_dir}{os.pathsep}{existing}"
    commands = [
        [sys.executable, "-m", "keel", "--json", "watch", "--once", "--mode", "auto"],
        [sys.executable, "-m", "keel.cli.main", "--json", "watch", "--once", "--mode", "auto"],
        ["keel", "--json", "watch", "--once", "--mode", "auto"],
    ]
    for command in commands:
        try:
            result = subprocess.run(command, cwd=repo, capture_output=True, text=True, check=False, env=env)
        except OSError:
            continue
        if result.returncode == 0:
            try:
                return json.loads(result.stdout)
            except json.JSONDecodeError:
                return None
    return None


def main() -> int:
    event = load_event()
    repo = repo_root(event)
    ensure_keel_import(repo)
    from keel.session import build_claude_context, build_claude_system_message

    event_name = event.get("hook_event_name")
    if event_name == "PostToolUse":
        run_keel_awareness(repo)

    system_message = build_claude_system_message(repo)
    context = build_claude_context(repo)
    payload: dict = {}
    if system_message:
        payload["systemMessage"] = system_message
    if event_name in {"SessionStart", "UserPromptSubmit"} and context:
        payload["hookSpecificOutput"] = {
            "hookEventName": event_name,
            "additionalContext": context,
        }
    if not payload:
        return 0
    print(json.dumps(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
