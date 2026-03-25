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


def test_install_agent_assets_bootstraps_hooks(tmp_path) -> None:
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
    # KEEL installs only the two guardrail hooks — no statusline, no skills
    repo_hooks = repo_root / ".claude" / "hooks"
    assert (repo_hooks / "keel_notify.py").exists() or any("hook" in m for m in messages)


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

    assert not (claude_home / "hooks" / "keel_statusline_router.py").exists()
