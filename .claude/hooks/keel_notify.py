#!/usr/bin/env python3
"""Lightweight sync hook — checks for pending companion notifications.

Runs on every PostToolUse (Write|Edit|Bash). If the companion detected drift,
this consumes the one-shot notification file and injects a system message.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

def main() -> int:
    project_dir = os.environ.get("CLAUDE_PROJECT_DIR")
    repo = Path(project_dir).resolve() if project_dir else Path.cwd().resolve()
    keel_dir = repo / ".keel" / "session"
    nf = keel_dir / "pending-notification.yaml"
    if not nf.exists():
        return 0
    try:
        import yaml
        data = yaml.safe_load(nf.read_text(encoding="utf-8")) or {}
        nf.unlink(missing_ok=True)
    except Exception:
        # Fallback: try without yaml
        try:
            raw = nf.read_text(encoding="utf-8")
            nf.unlink(missing_ok=True)
            msg = "drifting"
            for line in raw.splitlines():
                if line.strip().startswith("message:"):
                    msg = line.split(":", 1)[1].strip().strip("'\"")
                    break
            data = {"message": msg}
        except Exception:
            return 0
    msg = data.get("message", "drifting")
    payload = {
        "systemMessage": (
            f"KEEL — {msg}. "
            "Present this to the user with AskUserQuestion. Options: "
            "1) 'Acknowledge' — record as intentional with keel delta, "
            "2) 'Replan' — update the plan with keel replan, "
            "3) 'Ignore' — continue working, dismiss this warning."
        )
    }
    print(json.dumps(payload))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
