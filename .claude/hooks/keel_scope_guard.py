#!/usr/bin/env python3
"""PreToolUse hard stop — blocks file edits outside the active plan step.

Reads the tool input from stdin to extract the target file path, then checks
it against the active plan step's related_paths and goal scope. If the file
is outside scope and no delta covers it, the edit is blocked.

Returns {"decision": "block", "reason": "..."} to prevent the tool call,
or nothing to allow it.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def _load_yaml_safe(path: Path) -> dict:
    """Load YAML without requiring the yaml package."""
    if not path.exists():
        return {}
    try:
        import yaml
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except ImportError:
        return {}
    except Exception:
        return {}


def _extract_file_path(tool_input: dict) -> str | None:
    """Extract the target file path from Write or Edit tool input."""
    return tool_input.get("file_path") or tool_input.get("path")


def _is_within_scope(file_path: str, allowed_paths: list[str], scope_keywords: list[str]) -> bool:
    """Check if a file path is within the allowed scope."""
    if not allowed_paths and not scope_keywords:
        return True  # No scope defined = everything allowed

    rel = file_path
    # Normalize to relative path
    for prefix in [os.environ.get("CLAUDE_PROJECT_DIR", ""), str(Path.cwd())]:
        if prefix and rel.startswith(prefix):
            rel = rel[len(prefix):].lstrip("/")
            break

    # Check against explicit plan step paths
    for allowed in allowed_paths:
        allowed = allowed.strip("/")
        if rel.startswith(allowed) or allowed.startswith(rel.split("/")[0]):
            return True

    # Check against goal scope keywords (fuzzy — any scope keyword in the path)
    for keyword in scope_keywords:
        keyword_lower = keyword.lower().replace(" ", "").replace("-", "").replace("_", "")
        path_lower = rel.lower().replace("-", "").replace("_", "")
        if keyword_lower in path_lower:
            return True

    return False


def _has_delta_coverage(file_path: str, keel_dir: Path) -> bool:
    """Check if any delta artifact covers this file path."""
    deltas_dir = keel_dir.parent / "specs" / "deltas"
    if not deltas_dir.exists():
        return False
    try:
        import yaml
    except ImportError:
        return False
    for delta_file in deltas_dir.glob("*.yaml"):
        try:
            data = yaml.safe_load(delta_file.read_text(encoding="utf-8")) or {}
            impacted = data.get("impacted_paths", [])
            if any(file_path.endswith(p) or p in file_path for p in impacted):
                return True
        except Exception:
            continue
    return False


def _to_relative(file_path: str) -> str:
    """Normalize an absolute path to repo-relative."""
    for prefix in [os.environ.get("CLAUDE_PROJECT_DIR", ""), str(Path.cwd())]:
        if prefix and file_path.startswith(prefix):
            return file_path[len(prefix):].lstrip("/")
    return file_path


def _is_managed_path(file_path: str) -> bool:
    """KEEL/agent config files are always allowed."""
    managed_roots = {".keel", ".claude", ".codex", ".claude-plugin"}
    rel = _to_relative(file_path)
    parts = Path(rel).parts
    if parts and parts[0] in managed_roots:
        return True
    return False


def main() -> int:
    # Read tool input from stdin
    try:
        raw = sys.stdin.read()
        if not raw.strip():
            return 0
        payload = json.loads(raw)
    except (json.JSONDecodeError, Exception):
        return 0  # Can't parse = allow (don't break the session)

    tool_name = payload.get("tool_name", "")
    tool_input = payload.get("tool_input", {})

    # Only guard Write and Edit
    if tool_name not in ("Write", "Edit", "write", "edit"):
        return 0

    file_path = _extract_file_path(tool_input)
    if not file_path:
        return 0

    # Always allow managed config paths
    if _is_managed_path(file_path):
        return 0

    # Load KEEL state
    project_dir = os.environ.get("CLAUDE_PROJECT_DIR")
    repo = Path(project_dir).resolve() if project_dir else Path.cwd().resolve()
    keel_session = repo / ".keel" / "session"

    # Load current session
    session = _load_yaml_safe(keel_session / "current.yaml")
    if not session:
        return 0  # No KEEL session = allow everything

    active_step_id = session.get("active_step_id")
    active_plan_id = session.get("active_plan_id")
    if not active_plan_id:
        return 0  # No active plan = allow

    # Find the active plan artifact
    plans_dir = repo / "keel" / "discovery" / "plans"
    plan_data = _load_yaml_safe(plans_dir / f"{active_plan_id}.yaml")
    if not plan_data:
        return 0  # Can't load plan = allow

    # Find the active step's related_paths
    allowed_paths = []
    for phase in plan_data.get("phases", []):
        for step in phase.get("steps", []):
            if step.get("step_id") == active_step_id:
                allowed_paths = step.get("related_paths", [])
                break

    # Load goal scope
    active_goal_id = session.get("active_goal_id")
    scope_keywords = []
    if active_goal_id:
        goals_dir = repo / "keel" / "discovery" / "goals"
        goal_data = _load_yaml_safe(goals_dir / f"{active_goal_id}.yaml")
        scope_keywords = goal_data.get("scope", [])

    # Check if the file is in scope
    if _is_within_scope(file_path, allowed_paths, scope_keywords):
        return 0  # In scope = allow

    # Check if a delta covers this file
    if _has_delta_coverage(file_path, keel_session):
        return 0  # Delta exists = intentional change, allow

    # HARD STOP
    rel_path = file_path
    for prefix in [str(repo)]:
        if rel_path.startswith(prefix):
            rel_path = rel_path[len(prefix):].lstrip("/")
            break

    step_label = active_step_id or "unknown"
    result = {
        "decision": "block",
        "reason": (
            f"KEEL — '{rel_path}' is outside the active plan step ({step_label}). "
            "Use AskUserQuestion to ask the user: "
            "1) 'Allow this edit' — record as intentional change, "
            "2) 'Update plan' — replan to include this file, "
            "3) 'Switch step' — advance to a different plan step."
        ),
    }
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
