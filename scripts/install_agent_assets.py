#!/usr/bin/env python3
"""Install KEEL Codex and Claude Code support assets."""

from __future__ import annotations

import argparse
from pathlib import Path

from keel.utils.agent_install import install_agent_assets


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Install KEEL Codex and Claude Code assets.")
    parser.add_argument("--codex-only", action="store_true", help="Install only Codex skills.")
    parser.add_argument("--claude-only", action="store_true", help="Install only Claude Code assets.")
    parser.add_argument("--no-hook", action="store_true", help="Skip installing the Claude preflight hook.")
    parser.add_argument("--no-repo-hooks", action="store_true", help="Skip installing repo git hooks.")
    parser.add_argument("--no-companion", action="store_true", help="Skip starting the KEEL companion.")
    parser.add_argument("--companion-interval", type=float, default=2.0, help="Polling interval for the KEEL companion.")
    parser.add_argument("--codex-home", type=Path, default=None, help="Override Codex home.")
    parser.add_argument("--claude-home", type=Path, default=None, help="Override Claude home.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(__file__).resolve().parent.parent
    messages = install_agent_assets(
        repo_root=repo_root,
        install_codex_assets=not args.claude_only,
        install_claude_assets=not args.codex_only,
        install_hook=not args.no_hook,
        install_repo_hooks=not args.no_repo_hooks,
        start_repo_companion=not args.no_companion,
        companion_interval=args.companion_interval,
        codex_target=args.codex_home,
        claude_target=args.claude_home,
    )

    if not messages:
        print("No agent assets were installed.")
        return 1

    for message in messages:
        print(message)
    print("Repo-local project guidance remains in AGENTS.md, CLAUDE.md, and .codex/config.toml.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
