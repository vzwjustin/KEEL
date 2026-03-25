"""
KEEL → GSD bridge.

Reads GSD's .planning/ artifacts so KEEL commands can stay aligned with
the active GSD phase without requiring any changes to GSD itself.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional


def _planning_dir(repo_root: Path) -> Optional[Path]:
    d = repo_root / ".planning"
    return d if d.is_dir() else None


def read_gsd_state(repo_root: Path) -> dict:
    """Return current GSD state extracted from .planning/STATE.md."""
    planning = _planning_dir(repo_root)
    if not planning:
        return {}

    state_file = planning / "STATE.md"
    if not state_file.exists():
        return {}

    text = state_file.read_text(encoding="utf-8", errors="ignore")
    result: dict = {"source": "gsd"}

    # Extract current phase
    m = re.search(r"[Cc]urrent [Pp]hase[:\s]+(\d[\d.]*)", text)
    if m:
        result["current_phase"] = m.group(1)

    # Extract current position / active plan
    m = re.search(r"[Cc]urrent [Pp]osition[:\s]+([^\n]+)", text)
    if m:
        result["current_position"] = m.group(1).strip()

    # Extract blockers
    blockers = re.findall(r"[-*]\s+(blocker|concern)[:\s]+([^\n]+)", text, re.IGNORECASE)
    if blockers:
        result["blockers"] = [b[1].strip() for b in blockers]

    return result


def read_gsd_roadmap(repo_root: Path) -> dict:
    """Extract phase goals from .planning/ROADMAP.md."""
    planning = _planning_dir(repo_root)
    if not planning:
        return {}

    roadmap_file = planning / "ROADMAP.md"
    if not roadmap_file.exists():
        return {}

    text = roadmap_file.read_text(encoding="utf-8", errors="ignore")
    phases: dict[str, str] = {}

    # Match lines like "## Phase 1: Goal text" or "| 1 | Goal | ..."
    for m in re.finditer(r"#{1,3}\s+[Pp]hase\s+(\d[\d.]*)[:\s]+([^\n]+)", text):
        phases[m.group(1)] = m.group(2).strip()

    # Also match table rows: | 1 | Name | status |
    for m in re.finditer(r"\|\s*(\d[\d.]*)\s*\|\s*([^|]+)\|", text):
        phase_num = m.group(1).strip()
        if phase_num not in phases:
            phases[phase_num] = m.group(2).strip()

    return {"phases": phases}


def sync_goal_from_gsd(repo_root: Path) -> Optional[str]:
    """
    Return the goal statement for the current GSD phase, or None if GSD is not
    present or no active phase is found. The caller can pass this to keel goal.
    """
    state = read_gsd_state(repo_root)
    current_phase = state.get("current_phase")
    if not current_phase:
        return None

    roadmap = read_gsd_roadmap(repo_root)
    phases = roadmap.get("phases", {})
    return phases.get(current_phase)


def write_keel_brief_to_planning(repo_root: Path, brief_text: str) -> bool:
    """
    Write the current KEEL brief into .planning/KEEL-STATUS.md so GSD agents
    can read KEEL's guardrail state without calling keel directly.
    Returns True if written, False if .planning/ doesn't exist.
    """
    planning = _planning_dir(repo_root)
    if not planning:
        return False

    out = planning / "KEEL-STATUS.md"
    out.write_text(brief_text, encoding="utf-8")
    return True


def gsd_present(repo_root: Path) -> bool:
    """True if this repo is managed by GSD."""
    return _planning_dir(repo_root) is not None
