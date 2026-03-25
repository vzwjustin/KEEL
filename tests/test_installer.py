from __future__ import annotations

import importlib.util
from pathlib import Path


def load_installer_module():
    script = Path(__file__).resolve().parent.parent / "scripts" / "install_agent_assets.py"
    spec = importlib.util.spec_from_file_location("install_agent_assets", script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_install_agent_assets_installs_slash_commands(tmp_path) -> None:
    module = load_installer_module()
    repo_root = Path(__file__).resolve().parent.parent
    claude_home = tmp_path / "claude-home"

    messages = module.install_agent_assets(
        repo_root=repo_root,
        codex_target=tmp_path / "codex-home",
        claude_target=claude_home,
        install_hook=False,
        install_repo_hooks=False,
        start_repo_companion=False,
    )

    assert messages
    commands_dir = claude_home / "commands" / "keel"
    assert commands_dir.exists()
    assert (commands_dir / "status.md").exists()
    assert (commands_dir / "drift.md").exists()
    assert (commands_dir / "done.md").exists()
    assert (commands_dir / "checkpoint.md").exists()
    assert (commands_dir / "companion.md").exists()


def test_install_does_not_touch_statusline(tmp_path) -> None:
    """KEEL install must not overwrite the statusline — GSD owns it."""
    module = load_installer_module()
    repo_root = Path(__file__).resolve().parent.parent
    claude_home = tmp_path / "claude-home"
    claude_home.mkdir(parents=True, exist_ok=True)

    module.install_agent_assets(
        repo_root=repo_root,
        codex_target=tmp_path / "codex-home",
        claude_target=claude_home,
        install_hook=False,
        install_repo_hooks=False,
        start_repo_companion=False,
    )

    # No statusline router should be installed
    assert not (claude_home / "hooks" / "keel_statusline_router.py").exists()
    # No settings.json statusLine override
    settings_path = claude_home / "settings.json"
    if settings_path.exists():
        import json
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
        assert "statusLine" not in settings or "keel" not in settings.get("statusLine", {}).get("command", "")
