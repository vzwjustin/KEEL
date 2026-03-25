from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

from keel.core.paths import resolve_paths
from keel.session import install_git_hooks, start_companion
from keel.utils.agent_templates import CLAUDE_STATUSLINE_ROUTER, repo_agent_templates


def copy_tree(source: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for item in source.iterdir():
        target = destination / item.name
        if item.is_dir():
            shutil.copytree(item, target, dirs_exist_ok=True)
        else:
            shutil.copy2(item, target)


def _write_repo_file(path: Path, content: str, executable: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    if executable:
        path.chmod(0o755)


def _merge_json_content(existing_text: str, incoming_text: str) -> str:
    try:
        existing = json.loads(existing_text) if existing_text.strip() else {}
    except json.JSONDecodeError:
        existing = {}
    try:
        incoming = json.loads(incoming_text) if incoming_text.strip() else {}
    except json.JSONDecodeError:
        incoming = {}

    def deep_merge(left: object, right: object) -> object:
        if isinstance(left, dict) and isinstance(right, dict):
            merged = dict(left)
            for key, value in right.items():
                if key in merged:
                    merged[key] = deep_merge(merged[key], value)
                else:
                    merged[key] = value
            return merged
        return right

    merged = deep_merge(existing, incoming)
    return json.dumps(merged, indent=2) + "\n"


def bootstrap_repo_agent_assets(
    repo_root: Path,
    *,
    include_codex: bool = True,
    include_claude: bool = True,
) -> list[str]:
    messages = []
    for relative_path, (content, executable) in repo_agent_templates(
        repo_root,
        include_codex=include_codex,
        include_claude=include_claude,
    ).items():
        target = repo_root / relative_path
        if target.exists():
            existing = target.read_text(encoding="utf-8")
            rendered = content
            if relative_path == Path(".claude/settings.json"):
                rendered = _merge_json_content(existing, content)
            if existing == rendered:
                continue
            _write_repo_file(target, rendered, executable)
            messages.append(f"Updated repo-local agent file {target}")
            continue
        _write_repo_file(target, content, executable)
        messages.append(f"Bootstrapped repo-local agent file {target}")
    return messages


def codex_home() -> Path:
    raw = os.environ.get("CODEX_HOME")
    if raw:
        return Path(raw).expanduser()
    return Path.home() / ".codex"


def claude_home() -> Path:
    return Path.home() / ".claude"


def install_codex(repo_root: Path, destination: Path) -> list[str]:
    installed = []
    source = repo_root / ".codex" / "skills"
    if not source.exists():
        return installed
    target = destination / "skills"
    copy_tree(source, target)
    installed.append(f"Installed Codex skills into {target}")
    return installed


def install_claude(repo_root: Path, destination: Path, install_hook: bool) -> list[str]:
    installed = []
    source = repo_root / ".claude" / "skills"
    if source.exists():
        target = destination / "skills"
        copy_tree(source, target)
        installed.append(f"Installed Claude Code skills into {target}")
    commands_source = repo_root / ".claude" / "commands" / "keel"
    if commands_source.exists():
        commands_target = destination / "commands" / "keel"
        copy_tree(commands_source, commands_target)
        installed.append(f"Installed Claude Code slash commands into {commands_target}")
    hooks_target = destination / "hooks"
    hooks_target.mkdir(parents=True, exist_ok=True)
    router_path = hooks_target / "keel_statusline_router.py"
    _write_repo_file(router_path, CLAUDE_STATUSLINE_ROUTER, True)
    installed.append(f"Installed Claude Code statusline router into {router_path}")
    if install_hook:
        hook_source = repo_root / ".claude" / "hooks" / "keel_preflight.py"
        if hook_source.exists():
            shutil.copy2(hook_source, hooks_target / hook_source.name)
            installed.append(f"Installed Claude Code hook into {hooks_target / hook_source.name}")
    installed.extend(_install_claude_global_statusline(destination, router_path))
    return installed


def _read_json_file(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _install_claude_global_statusline(destination: Path, router_path: Path) -> list[str]:
    settings_path = destination / "settings.json"
    state_path = destination / "keel" / "statusline-router-state.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)

    settings = _read_json_file(settings_path)
    router_command = f"python3 {router_path}"
    existing_statusline = settings.get("statusLine")
    current_command = existing_statusline.get("command") if isinstance(existing_statusline, dict) else None

    state_payload = _read_json_file(state_path)
    if current_command and current_command != router_command:
        state_payload["previous_statusline"] = existing_statusline
    state_path.write_text(json.dumps(state_payload, indent=2) + "\n", encoding="utf-8")

    padding = 1
    if isinstance(existing_statusline, dict):
        padding = existing_statusline.get("padding", 1)
    settings["statusLine"] = {
        "type": "command",
        "command": router_command,
        "padding": padding,
    }
    settings_path.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
    return [f"Installed Claude Code global statusline router in {settings_path}"]


def install_agent_assets(
    *,
    repo_root: Path,
    install_codex_assets: bool = True,
    install_claude_assets: bool = True,
    install_hook: bool = True,
    install_repo_hooks: bool = True,
    start_repo_companion: bool = True,
    companion_interval: float = 2.0,
    companion_mode: str = "auto",
    codex_target: Path | None = None,
    claude_target: Path | None = None,
) -> list[str]:
    messages = []
    repo_has_git_hooks = (repo_root / ".git" / "hooks").exists()
    messages.extend(
        bootstrap_repo_agent_assets(
            repo_root,
            include_codex=install_codex_assets,
            include_claude=install_claude_assets,
        )
    )
    if install_codex_assets:
        messages.extend(install_codex(repo_root, (codex_target or codex_home()).expanduser()))
    if install_claude_assets:
        messages.extend(
            install_claude(
                repo_root,
                (claude_target or claude_home()).expanduser(),
                install_hook=install_hook,
            )
        )
    paths = resolve_paths(repo_root)
    paths.ensure()
    if install_repo_hooks:
        messages.extend(install_git_hooks(paths))
        if not repo_has_git_hooks:
            messages.append("KEEL installed in companion-only mode because this repo is not using a local .git/hooks directory.")
    if start_repo_companion:
        status = start_companion(paths, interval=companion_interval, mode=companion_mode)
        if status.get("running"):
            messages.append(f"Started KEEL companion for {repo_root}")
        else:
            messages.append(f"KEEL companion did not stay running. Check {paths.companion_log_file}")
            messages.append(f"Retry with `keel --repo {repo_root} companion start`")
    return messages
