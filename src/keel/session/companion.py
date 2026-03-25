from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from keel.core.artifacts import load_yaml, save_yaml
from keel.core.paths import KeelPaths, now_iso


HOOK_NAMES = ("post-checkout", "post-merge", "pre-commit")
HOOK_HEADER = "# KEEL managed hook"
LOG_ROTATE_BYTES = 512 * 1024
HEARTBEAT_STALE_SECONDS = 20


def _is_process_running(pid: int | None) -> bool:
    if not pid or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _base_status(paths: KeelPaths) -> dict[str, Any]:
    payload = load_yaml(paths.companion_file)
    status = payload if payload else {}
    pid = status.get("pid")
    running = _is_process_running(pid if isinstance(pid, int) else None)
    status["running"] = running
    status.setdefault("repo_root", str(paths.root))
    status.setdefault("log_path", str(paths.companion_log_file))
    heartbeat = load_yaml(paths.companion_heartbeat_file)
    heartbeat_token = heartbeat.get("token")
    status_token = status.get("token")
    token_matches = bool(status_token and heartbeat_token and status_token == heartbeat_token)
    heartbeat_updated_at = heartbeat.get("updated_at")
    heartbeat_stale = True
    if heartbeat_updated_at:
        try:
            heartbeat_time = datetime.fromisoformat(heartbeat_updated_at)
            heartbeat_stale = heartbeat_time < datetime.now().astimezone() - timedelta(seconds=HEARTBEAT_STALE_SECONDS)
        except ValueError:
            heartbeat_stale = True
    status["heartbeat"] = heartbeat
    status["token_matches"] = token_matches
    status["last_awareness_at"] = heartbeat_updated_at
    status["last_repo_change_at"] = heartbeat.get("latest_repo_change_at")
    status["fresh"] = bool(running and token_matches and not heartbeat_stale)
    return status


def companion_status(paths: KeelPaths) -> dict[str, Any]:
    status = _base_status(paths)
    # If the process was supposed to be running but is now dead, record the death
    had_pid = status.get("pid") is not None
    is_dead = had_pid and not status.get("running")
    if is_dead:
        status["died_at"] = status.get("died_at") or now_iso()
        status["token"] = None
        status["token_matches"] = False
        status["fresh"] = False
    if paths.companion_file.exists():
        save_yaml(paths.companion_file, status)
    return status


def _companion_env(repo_root: Path) -> dict[str, str]:
    env = os.environ.copy()
    package_root = Path(__file__).resolve().parents[2]
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(package_root) if not existing else f"{package_root}{os.pathsep}{existing}"
    env.setdefault("PYTHONUNBUFFERED", "1")
    env["KEEL_COMPANION_REPO"] = str(repo_root)
    return env


def _rotate_companion_log(paths: KeelPaths) -> None:
    if not paths.companion_log_file.exists():
        return
    try:
        if paths.companion_log_file.stat().st_size < LOG_ROTATE_BYTES:
            return
    except OSError:
        return
    rotated = paths.companion_log_file.with_suffix(".log.1")
    if rotated.exists():
        rotated.unlink()
    paths.companion_log_file.replace(rotated)


def _hook_script(paths: KeelPaths, hook_name: str) -> str:
    return f"""#!/bin/sh
{HOOK_HEADER}
set -e
if [ -x "$(dirname "$0")/{hook_name}.local" ]; then
  "$(dirname "$0")/{hook_name}.local" "$@" || exit $?
fi
cd "{paths.root}" || exit 0
keel --json watch --once --mode auto >/dev/null 2>&1 || python3 -m keel --repo "{paths.root}" --json watch --once --mode auto >/dev/null 2>&1 || true
exit 0
"""


def start_companion(paths: KeelPaths, *, interval: float = 2.0, mode: str = "auto") -> dict[str, Any]:
    status = _base_status(paths)
    if status.get("running"):
        return status
    _rotate_companion_log(paths)
    token = uuid.uuid4().hex

    command = [
        sys.executable,
        "-m",
        "keel",
        "--repo",
        str(paths.root),
        "watch",
        "--mode",
        mode,
        "--interval",
        str(interval),
        "--heartbeat-file",
        str(paths.companion_heartbeat_file),
        "--companion-token",
        token,
    ]
    paths.companion_log_file.parent.mkdir(parents=True, exist_ok=True)
    with paths.companion_log_file.open("w", encoding="utf-8") as handle:
        handle.write(f"[{now_iso()}] starting companion\n")

    log_handle = paths.companion_log_file.open("a", encoding="utf-8")
    process = None
    exit_code = None
    running = False
    for _ in range(2):
        process = subprocess.Popen(
            command,
            cwd=paths.root,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            env=_companion_env(paths.root),
            text=True,
        )
        time.sleep(0.3)
        exit_code = process.poll()
        running = exit_code is None
        if running:
            break
        with paths.companion_log_file.open("a", encoding="utf-8") as handle:
            handle.write(f"[{now_iso()}] companion exited early with code {exit_code}; retrying\n")
    payload = {
        "pid": process.pid if process else None,
        "running": running,
        "token": token,
        "mode": mode,
        "interval_seconds": interval,
        "started_at": now_iso(),
        "repo_root": str(paths.root),
        "log_path": str(paths.companion_log_file),
        "command": command,
        "startup_exit_code": exit_code if not running else None,
    }
    save_yaml(paths.companion_file, payload)
    return payload


def stop_companion(paths: KeelPaths) -> dict[str, Any]:
    status = _base_status(paths)
    pid = status.get("pid")
    if isinstance(pid, int) and _is_process_running(pid):
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass
        time.sleep(0.3)
        if _is_process_running(pid):
            try:
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass
            time.sleep(0.1)
    status["last_pid"] = pid
    status["pid"] = None
    status["running"] = False
    status["token"] = None
    status["token_matches"] = False
    status["fresh"] = False
    status["stopped_at"] = now_iso()
    save_yaml(paths.companion_file, status)
    return status


def install_git_hooks(paths: KeelPaths) -> list[str]:
    hooks_dir = paths.root / ".git" / "hooks"
    if not hooks_dir.exists():
        return ["Skipped git hook installation because this repo has no .git/hooks directory."]

    messages = []
    for hook_name in HOOK_NAMES:
        hook_path = hooks_dir / hook_name
        local_hook_path = hooks_dir / f"{hook_name}.local"
        if hook_path.exists():
            current = hook_path.read_text(encoding="utf-8", errors="ignore")
            if HOOK_HEADER not in current:
                hook_path.replace(local_hook_path)
                messages.append(f"Preserved existing hook as {local_hook_path}")
        hook_path.write_text(_hook_script(paths, hook_name), encoding="utf-8")
        hook_path.chmod(0o755)
        messages.append(f"Installed repo git hook {hook_path}")
    return messages
