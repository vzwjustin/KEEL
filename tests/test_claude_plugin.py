from __future__ import annotations

import json
from pathlib import Path


def test_claude_plugin_marketplace_and_manifest_are_valid() -> None:
    repo = Path(__file__).resolve().parent.parent
    marketplace = json.loads((repo / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))
    plugin_manifest = json.loads(
        (repo / "plugins" / "keel-companion-plugin" / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8")
    )
    hooks = json.loads((repo / "plugins" / "keel-companion-plugin" / "hooks" / "hooks.json").read_text(encoding="utf-8"))

    assert marketplace["name"] == "keel-marketplace"
    assert marketplace["plugins"][0]["name"] == plugin_manifest["name"]
    assert plugin_manifest["name"] == "keel-companion-plugin"
    assert "hooks" in hooks
    assert "PostToolUse" in hooks["hooks"]
