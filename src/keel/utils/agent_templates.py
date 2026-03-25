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
    statusline_path = repo_root / ".claude" / "statusline.py"
    payload = {
        "statusLine": {
            "type": "command",
            "command": f"python3 {statusline_path}",
            "padding": 1,
        },
        "hooks": {
            "SessionStart": [
                {
                    "matcher": "startup|resume|clear|compact",
                    "hooks": [
                        {
                            "type": "command",
                            "command": "python3 \"$CLAUDE_PROJECT_DIR\"/.claude/hooks/keel_ui_context.py",
                        }
                    ],
                }
            ],
            "UserPromptSubmit": [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": "python3 \"$CLAUDE_PROJECT_DIR\"/.claude/hooks/keel_ui_context.py",
                        }
                    ]
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
                {
                    "matcher": "Write|Edit",
                    "hooks": [
                        {
                            "type": "command",
                            "command": "python3 \"$CLAUDE_PROJECT_DIR\"/.claude/hooks/keel_ui_context.py",
                            "async": True,
                            "timeout": 30,
                        }
                    ],
                },
            ],
        },
    }
    return json.dumps(payload, indent=2) + "\n"


CLAUDE_STATUSLINE_ROUTER = """#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

_STDIN_RAW: str = "{}"


def read_stdin() -> tuple[dict, str]:
    global _STDIN_RAW
    try:
        _STDIN_RAW = sys.stdin.read() if not sys.stdin.isatty() else "{}"
    except OSError:
        _STDIN_RAW = "{}"
    try:
        return json.loads(_STDIN_RAW or "{}"), _STDIN_RAW or "{}"
    except json.JSONDecodeError:
        return {}, "{}"


def resolve_repo_root(payload: dict) -> Path:
    cwd = payload.get("workspace", {}).get("current_dir")
    return Path(cwd).resolve() if cwd else Path.cwd().resolve()


def find_keel_repo(start: Path) -> Path | None:
    for candidate in [start, *start.parents]:
        if (candidate / ".keel").exists() and (candidate / ".claude" / "statusline.py").exists():
            return candidate
    return None


def state_file() -> Path:
    return Path(__file__).resolve().parent.parent / "keel" / "statusline-router-state.json"


def _strip_dim(text: str) -> str:
    import re
    return re.sub(r'\\x1b\\[2m', '', text)


def run_command(command: str, cwd: Path, stdin_data: str = "{}") -> tuple[int, str]:
    result = subprocess.run(
        command, shell=True, cwd=cwd, check=False,
        capture_output=True, text=True, input=stdin_data,
    )
    output = result.stdout.strip() or result.stderr.strip()
    return result.returncode, output


def route_to_keel(repo_root: Path, stdin_data: str) -> tuple[int, str]:
    command = f"python3 {repo_root / '.claude' / 'statusline.py'}"
    return run_command(command, repo_root, stdin_data)


def route_to_previous(repo_root: Path, stdin_data: str) -> tuple[int, str]:
    state_path = state_file()
    if not state_path.exists():
        return 0, ""
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return 0, ""
    statusline = state.get("previous_statusline") or {}
    command = statusline.get("command")
    if not command or Path(__file__).name in command:
        return 0, ""
    return run_command(command, repo_root, stdin_data)


def main() -> int:
    payload, stdin_raw = read_stdin()
    repo_root = resolve_repo_root(payload)
    keel_repo = find_keel_repo(repo_root)
    if keel_repo is not None:
        previous_code, previous_output = route_to_previous(keel_repo, stdin_raw)
        keel_code, keel_output = route_to_keel(keel_repo, stdin_raw)
        parts = [part for part in [_strip_dim(previous_output), keel_output] if part]
        if parts:
            print(" \u2502 ".join(parts))
        return keel_code if keel_output else previous_code
    previous_code, previous_output = route_to_previous(repo_root, stdin_raw)
    if previous_output:
        print(previous_output)
    return previous_code


if __name__ == "__main__":
    raise SystemExit(main())
"""

CLAUDE_STATUSLINE = """#!/usr/bin/env python3
\"\"\"KEEL statusline with built-in model, context bar, and folder display.

Works standalone -- no GSD or other plugins required.
\"\"\"
from __future__ import annotations

import json
import math
import os
import subprocess
import sys
from pathlib import Path

AUTO_COMPACT_BUFFER_PCT = 16.5


def _read_payload() -> tuple[dict, Path]:
    try:
        raw = sys.stdin.read() if not sys.stdin.isatty() else "{}"
    except OSError:
        raw = "{}"
    try:
        payload = json.loads(raw or "{}")
    except json.JSONDecodeError:
        payload = {}
    cwd = payload.get("workspace", {}).get("current_dir")
    root = Path(cwd).resolve() if cwd else Path.cwd().resolve()
    return payload, root


# -- session info (model + folder + context) --------------------------------

def _render_session(payload: dict, repo_root: Path) -> str:
    model_obj = payload.get("model")
    if isinstance(model_obj, dict):
        model = model_obj.get("display_name") or model_obj.get("id", "Claude")
    elif isinstance(model_obj, str):
        model = model_obj
    else:
        model = "Claude"

    dirname = repo_root.name

    ctx = ""
    remaining = (payload.get("context_window") or {}).get("remaining_percentage")
    if remaining is not None:
        usable = max(0.0, (remaining - AUTO_COMPACT_BUFFER_PCT) / (100 - AUTO_COMPACT_BUFFER_PCT) * 100)
        used = max(0, min(100, round(100 - usable)))
        filled = math.floor(used / 10)
        bar = "\\u2588" * filled + "\\u2591" * (10 - filled)
        if used < 50:
            ctx = f" \\033[32m{bar} {used}%\\033[0m"
        elif used < 65:
            ctx = f" \\033[33m{bar} {used}%\\033[0m"
        elif used < 80:
            ctx = f" \\033[38;5;208m{bar} {used}%\\033[0m"
        else:
            ctx = f" \\033[5;31m{bar} {used}%\\033[0m"

    return f"\\033[2m{model}\\033[0m \\u2502 \\033[2m{dirname}\\033[0m{ctx}"


# -- keel status -------------------------------------------------------------

def _env(repo_root: Path) -> dict[str, str]:
    env = os.environ.copy()
    src_dir = repo_root / "src"
    if src_dir.exists():
        existing = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = str(src_dir) if not existing else f"{src_dir}{os.pathsep}{existing}"
    return env


def _render_from_status(payload: dict) -> str:
    def _vibe(summary: str) -> str:
        s = summary.lower()
        if "no active plan" in s:
            return "needs plan"
        if "no active goal" in s:
            return "needs goal"
        if "next step" in s and "missing" in s:
            return "pick next step"
        if "delta" in s and "missing" in s:
            return "needs delta"
        if "question" in s and "open" in s:
            return "open question"
        if "drift" in s:
            return "drifting"
        return summary[:40]

    alerts = payload.get("recent_alerts", [])
    severities = [a.get("severity", "warning") for a in alerts]
    blockers = sum(1 for s in severities if s in {"error", "blocker"})
    top = alerts[0] if alerts else None
    companion = payload.get("companion", {})
    alive = companion.get("fresh", False)

    has_drift = any(
        a.get("source") == "drift" or "drift" in a.get("summary", "").lower()
        for a in alerts
    )

    if not alerts:
        state = "\\033[32mon track\\033[0m"
    elif blockers and top:
        state = "\\033[31m" + _vibe(top.get("summary", "blocked")) + "\\033[0m"
    elif top:
        state = "\\033[33m" + _vibe(top.get("summary", "heads up")) + "\\033[0m"
    else:
        state = "\\033[32mon track\\033[0m"

    if has_drift:
        drift_vis = "\\033[33m~ drifting\\033[0m"
    else:
        drift_vis = "\\033[32m= on course\\033[0m"

    companion_vis = "\\033[32m\\u25cf companion\\033[0m" if alive else "\\033[2m\\u25cb companion\\033[0m"
    return f"{state} \\u2502 {drift_vis} \\u2502 {companion_vis}"


def _status_via_cli(repo_root: Path) -> str | None:
    commands = [
        [sys.executable, "-m", "keel", "--repo", str(repo_root), "--json", "status"],
        [sys.executable, "-m", "keel.cli.main", "--repo", str(repo_root), "--json", "status"],
        ["keel", "--repo", str(repo_root), "--json", "status"],
    ]
    for command in commands:
        try:
            result = subprocess.run(
                command, cwd=repo_root, capture_output=True, text=True,
                check=False, env=_env(repo_root),
            )
        except OSError:
            continue
        if result.returncode != 0 or not result.stdout.strip():
            continue
        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError:
            continue
        return _render_from_status(data)
    return None


def _get_keel_text(repo_root: Path) -> str:
    try:
        from keel.session import build_statusline_text
        return build_statusline_text(repo_root)
    except ImportError:
        pass
    rendered = _status_via_cli(repo_root)
    if rendered:
        return rendered
    src_dir = repo_root / "src"
    if src_dir.exists():
        sys.path.insert(0, str(src_dir))
        try:
            from keel.session import build_statusline_text
            return build_statusline_text(repo_root)
        except ImportError:
            pass
    return "KEEL unavailable"


def main() -> int:
    payload, repo_root = _read_payload()
    session = _render_session(payload, repo_root)
    keel = _get_keel_text(repo_root)
    print(f"{session} \\u2502 {keel}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
"""

CLAUDE_PREFLIGHT_HOOK = """#!/usr/bin/env python3
\"\"\"Optional Claude Code preflight hook for KEEL-managed repositories.

This hook runs a one-shot KEEL awareness pass so the session brief, validation,
trace, and drift state stay current as coding moves forward.
\"\"\"

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
"""

CLAUDE_UI_CONTEXT_HOOK = """#!/usr/bin/env python3
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
"""

CLAUDE_KEEL_SESSION_SKILL = """---
description: Keep Claude aligned with KEEL's active alerts, brief, and next step in a KEEL-managed repository.
---

# KEEL Session

Use this skill when working in a repository that uses KEEL for companion-mode state.

## Workflow

1. Read `.keel/session/alerts.yaml` first when it exists, then `.keel/session/current-brief.md`.
2. Run `keel watch --once --mode auto` if the alert feed or brief looks stale.
3. Run `keel next` before starting a new change slice.
4. If current work no longer matches the brief, use `keel checkpoint` or `keel replan`.
5. After a meaningful slice, run `keel validate`, `keel drift --mode auto`, and `keel check`.

## Open Questions — MANDATORY

When the KEEL context includes "Questions to present:", you MUST use the `AskUserQuestion` tool
to present them as selectable options. Do NOT dump questions as plain text.

Format each question with 2-4 concise options. Use the `header` field as a short label (max 12 chars).
After the user selects answers, feed them back to KEEL:
- Goal/success criteria answers: `keel goal --success-criterion "..."`
- Config questions: `keel delta --title "..." --description "..."`
- Deferrals: note in the delta that the question was consciously deferred.

## Rules

- Treat active KEEL alerts as the highest-signal short-term warning feed.
- If changed files do not map to the active goal or step, assume drift until proven otherwise.
- Keep out-of-scope items and constraints stable unless KEEL artifacts are updated.
"""

CLAUDE_KEEL_DRIFT_SKILL = """---
description: Use KEEL drift and recovery artifacts to explain misalignment and get back on course.
---

# KEEL Drift

Use this skill when you need to sanity-check whether current work is still aligned with the active goal and plan.

## Workflow

1. Run `keel drift --mode auto --json`.
2. Check `.keel/session/alerts.yaml` for collapsed high-signal warnings.
3. Run `keel recover --json` if drift is real or repeated.
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
        files[Path(".claude/statusline.py")] = (CLAUDE_STATUSLINE, True)
        files[Path(".claude/hooks/keel_preflight.py")] = (CLAUDE_PREFLIGHT_HOOK, True)
        files[Path(".claude/hooks/keel_ui_context.py")] = (CLAUDE_UI_CONTEXT_HOOK, True)
        files[Path(".claude/hooks/keel_notify.py")] = (CLAUDE_NOTIFY_HOOK, True)
        files[Path(".claude/skills/keel-session/SKILL.md")] = (CLAUDE_KEEL_SESSION_SKILL, False)
        files[Path(".claude/skills/keel-drift/SKILL.md")] = (CLAUDE_KEEL_DRIFT_SKILL, False)
    return files
