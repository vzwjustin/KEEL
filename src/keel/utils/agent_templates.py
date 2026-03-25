from __future__ import annotations

import json
from pathlib import Path


CODEX_CONFIG = """[project]
name = "keel"
path_boundary_mode = "repo-only"
update_current_brief_on_state_change = true
checkpoint_before_risky_change = true

[guards]
prefer_library_calls_over_shell = true
block_writes_outside_repo = true
require_delta_for_behavior_change = true
warn_on_unmapped_changed_files = true
warn_on_stale_current_brief = true

[session]
brief_path = ".keel/session/current-brief.md"
current_state_path = ".keel/session/current.yaml"
tasks_path = "TASKS.md"
worklog_path = "WORKLOG.md"
"""

CODEX_KEEL_SESSION_SKILL = """# KEEL Session

Use this skill when working in a KEEL-managed repository and you need to re-enter the current slice cleanly.

## Workflow

1. Read `.keel/session/alerts.yaml` first when it exists, then `.keel/session/current-brief.md`.
2. Run `keel watch --once --mode auto` if the brief or alert feed looks stale or incomplete.
3. Run `keel next` before starting a new change slice.
4. If current work no longer matches the brief, use `keel checkpoint` or `keel replan`.
5. When staying in the repo for a while, keep `keel watch` running in another terminal.
6. After a meaningful slice, run `keel validate`, `keel drift --mode auto`, and `keel check`.

## Rules

- Treat active KEEL alerts as the highest-signal short-term warning feed.
- If changed files do not map to the active goal or step, assume drift until proven otherwise.
- Keep out-of-scope items and constraints stable unless KEEL artifacts are updated.
"""

CODEX_KEEL_DRIFT_SKILL = """# KEEL Drift

Use this skill when you need to sanity-check whether current work is still aligned with the active goal and plan.

## Workflow

1. Run `keel --json drift --mode auto`.
2. Check `.keel/session/alerts.yaml` for collapsed high-signal warnings.
3. Run `keel --json recover` if drift is real or repeated.
4. If the recovery path is accepted, reconcile the matching goal, plan, delta, or spec artifacts.

## What To Look For

- goal drift
- plan drift
- spec drift
- runtime-entrypoint drift
- terminology drift
- session drift
- clustered weak signals becoming a real drift pattern
"""

def build_claude_settings(repo_root: Path) -> str:
    payload = {
        "hooks": {
            "PreToolUse": [
                {
                    "matcher": "Write|Edit",
                    "hooks": [
                        {
                            "type": "command",
                            "command": "python3 \"$CLAUDE_PROJECT_DIR\"/.claude/hooks/keel_scope_guard.py",
                            "timeout": 3,
                        }
                    ],
                }
            ],
            "PostToolUse": [
                {
                    "matcher": "Write|Edit|Bash",
                    "hooks": [
                        {
                            "type": "command",
                            "command": "python3 \"$CLAUDE_PROJECT_DIR\"/.claude/hooks/keel_notify.py",
                            "timeout": 5,
                        }
                    ],
                },
            ],
        },
    }
    return json.dumps(payload, indent=2) + "\n"

CLAUDE_NOTIFY_HOOK = """#!/usr/bin/env python3
\"\"\"Lightweight sync hook — checks for pending companion notifications.

Runs on every PostToolUse (Write|Edit|Bash). If the companion detected drift,
this consumes the one-shot notification file and injects a system message.
\"\"\"
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
                    msg = line.split(":", 1)[1].strip().strip("'\\\"")
                    break
            data = {"message": msg}
        except Exception:
            return 0
    msg = data.get("message", "drifting")
    payload = {"systemMessage": f"KEEL — you're {msg}, heads up"}
    print(json.dumps(payload))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
"""

# Read scope guard from the repo file at install time
def _load_scope_guard() -> str:
    path = Path(__file__).resolve().parent.parent.parent.parent / ".claude" / "hooks" / "keel_scope_guard.py"
    if path.exists():
        return path.read_text(encoding="utf-8")
    return "# keel_scope_guard.py not found\n"

CLAUDE_SCOPE_GUARD_HOOK = _load_scope_guard()


def repo_agent_templates(
    repo_root: Path,
    *,
    include_codex: bool = True,
    include_claude: bool = True,
) -> dict[Path, tuple[str, bool]]:
    files: dict[Path, tuple[str, bool]] = {}
    if include_codex:
        files[Path(".codex/config.toml")] = (CODEX_CONFIG, False)
        files[Path(".codex/skills/keel-session/SKILL.md")] = (CODEX_KEEL_SESSION_SKILL, False)
        files[Path(".codex/skills/keel-drift/SKILL.md")] = (CODEX_KEEL_DRIFT_SKILL, False)
    if include_claude:
        files[Path(".claude/settings.json")] = (build_claude_settings(repo_root), False)
        files[Path(".claude/hooks/keel_notify.py")] = (CLAUDE_NOTIFY_HOOK, True)
        files[Path(".claude/hooks/keel_scope_guard.py")] = (CLAUDE_SCOPE_GUARD_HOOK, True)
    return files
