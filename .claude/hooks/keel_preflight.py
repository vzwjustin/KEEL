#!/usr/bin/env python3
"""Optional Claude Code preflight hook for KEEL-managed repositories.

This hook runs a one-shot KEEL awareness pass so the session brief, validation,
trace, and drift state stay current as coding moves forward.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def run_keel(cwd: Path) -> dict:
    env = os.environ.copy()
    src_dir = cwd / "src"
    if src_dir.exists():
        existing = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = str(src_dir) if not existing else f"{src_dir}{os.pathsep}{existing}"

    commands = [
        [sys.executable, "-m", "keel", "--json", "watch", "--once", "--mode", "auto"],
        [sys.executable, "-m", "keel.cli.main", "--json", "watch", "--once", "--mode", "auto"],
        ["keel", "--json", "watch", "--once", "--mode", "auto"],
    ]
    last_failure: dict | None = None
    for args in commands:
        try:
            result = subprocess.run(
                args,
                cwd=cwd,
                capture_output=True,
                text=True,
                check=False,
                env=env,
            )
        except OSError as exc:
            last_failure = {"ok": False, "command": args, "stdout": "", "stderr": str(exc)}
            continue
        if result.returncode != 0:
            last_failure = {"ok": False, "command": args, "stdout": result.stdout, "stderr": result.stderr}
            continue
        try:
            return {"ok": True, "data": json.loads(result.stdout)}
        except json.JSONDecodeError:
            last_failure = {"ok": False, "command": args, "stdout": result.stdout, "stderr": "invalid json"}
    return last_failure or {"ok": False, "command": [], "stdout": "", "stderr": "unknown failure"}


def main() -> int:
    repo = Path.cwd()
    awareness = run_keel(repo)

    if not awareness["ok"]:
        print("KEEL preflight could not complete cleanly.")
        print(f"awareness error: {awareness.get('stderr') or awareness.get('stdout')}")
        return 0

    payload = awareness["data"]
    print(f"KEEL goal: {payload.get('active_goal_id') or 'none'}")
    print(f"KEEL next: {payload.get('current_next_step') or 'none'}")
    print(f"KEEL validation: {payload.get('validation_status')}")
    print(f"KEEL drift: {payload.get('drift_status')}")
    for alert in payload.get("recent_alerts", [])[:3]:
        print(
            f"- alert [{alert.get('severity')}/{alert.get('confidence')}]: "
            f"{alert.get('summary')} | rule={alert.get('rule')} | next={alert.get('next_action')}"
        )

    return 2 if payload.get("status") == "blocked" else 0


if __name__ == "__main__":
    sys.exit(main())
