from __future__ import annotations

import importlib.util
import json
from pathlib import Path


def load_installer_module():
    script = Path(__file__).resolve().parent.parent / "scripts" / "install_agent_assets.py"
    spec = importlib.util.spec_from_file_location("install_agent_assets", script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_install_agent_assets_copies_codex_and_claude_assets(tmp_path) -> None:
    module = load_installer_module()
    repo_root = Path(__file__).resolve().parent.parent
    codex_home = tmp_path / "codex-home"
    claude_home = tmp_path / "claude-home"

    messages = module.install_agent_assets(
        repo_root=repo_root,
        codex_target=codex_home,
        claude_target=claude_home,
        install_hook=True,
        install_repo_hooks=False,
        start_repo_companion=False,
    )

    assert messages
    assert (codex_home / "skills" / "keel-session" / "SKILL.md").exists()
    assert (codex_home / "skills" / "keel-drift" / "SKILL.md").exists()
    assert (claude_home / "skills" / "keel-session" / "SKILL.md").exists()
    assert (claude_home / "skills" / "keel-drift" / "SKILL.md").exists()
    assert (claude_home / "hooks" / "keel_preflight.py").exists()
    assert (claude_home / "hooks" / "keel_statusline_router.py").exists()
    drift_skill = (claude_home / "skills" / "keel-drift" / "SKILL.md").read_text(encoding="utf-8")
    assert "keel --json drift --mode auto" in drift_skill or "keel drift --mode auto --json" in drift_skill

    settings = json.loads((claude_home / "settings.json").read_text(encoding="utf-8"))
    assert settings["statusLine"]["command"] == f"python3 {claude_home / 'hooks' / 'keel_statusline_router.py'}"


def test_install_agent_assets_preserves_previous_global_claude_statusline(tmp_path) -> None:
    module = load_installer_module()
    repo_root = Path(__file__).resolve().parent.parent
    claude_home = tmp_path / "claude-home"
    claude_home.mkdir(parents=True, exist_ok=True)
    (claude_home / "settings.json").write_text(
        json.dumps(
            {
                "statusLine": {
                    "type": "command",
                    "command": "python3 /tmp/gsd_statusline.py",
                    "padding": 2,
                }
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    module.install_agent_assets(
        repo_root=repo_root,
        claude_target=claude_home,
        codex_target=tmp_path / "codex-home",
        install_hook=False,
        install_repo_hooks=False,
        start_repo_companion=False,
    )

    settings = json.loads((claude_home / "settings.json").read_text(encoding="utf-8"))
    assert settings["statusLine"]["command"] == f"python3 {claude_home / 'hooks' / 'keel_statusline_router.py'}"
    assert settings["statusLine"]["padding"] == 2

    state = json.loads((claude_home / "keel" / "statusline-router-state.json").read_text(encoding="utf-8"))
    assert state["previous_statusline"]["command"] == "python3 /tmp/gsd_statusline.py"
