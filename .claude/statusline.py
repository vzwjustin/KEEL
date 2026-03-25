#!/usr/bin/env python3
"""KEEL statusline with built-in model, context bar, and folder display.

Works standalone -- no GSD or other plugins required.
"""
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
        bar = "\u2588" * filled + "\u2591" * (10 - filled)
        if used < 50:
            ctx = f" \033[32m{bar} {used}%\033[0m"
        elif used < 65:
            ctx = f" \033[33m{bar} {used}%\033[0m"
        elif used < 80:
            ctx = f" \033[38;5;208m{bar} {used}%\033[0m"
        else:
            ctx = f" \033[5;31m{bar} {used}%\033[0m"

    return f"\033[2m{model}\033[0m \u2502 \033[2m{dirname}\033[0m{ctx}"


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
        state = "\033[32mon track\033[0m"
    elif blockers and top:
        state = "\033[31m" + _vibe(top.get("summary", "blocked")) + "\033[0m"
    elif top:
        state = "\033[33m" + _vibe(top.get("summary", "heads up")) + "\033[0m"
    else:
        state = "\033[32mon track\033[0m"

    if has_drift:
        drift_vis = "\033[33m~ drifting\033[0m"
    else:
        drift_vis = "\033[32m= on course\033[0m"

    companion_vis = "\033[32m\u25cf companion\033[0m" if alive else "\033[2m\u25cb companion\033[0m"
    return f"{state} \u2502 {drift_vis} \u2502 {companion_vis}"


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
    print(f"{session} \u2502 {keel}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
