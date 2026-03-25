# Claude Code Integration

KEEL includes repo-local assets that make Claude Code sessions more consistent without making the CLI depend on Claude Code. For normal users, `keel install` should be the only setup command they need.

## Default Setup

```bash
keel install
```

That command bootstraps this repo's Claude Code files if they are missing:

- `.claude/settings.json`
- `.claude/statusline.py`
- `.claude/hooks/keel_ui_context.py`
- `.claude/hooks/keel_preflight.py`
- `.claude/skills/keel-session/SKILL.md`
- `.claude/skills/keel-drift/SKILL.md`

It also installs the reusable Claude skills into `~/.claude/skills`, installs the optional KEEL preflight hook into `~/.claude/hooks/`, installs repo git hooks, and starts the KEEL companion.
If the repo already has an older KEEL session that looks stale, install output tells the user to recover or replan instead of leaving them to interpret drift on their own.

## Hook Wiring

KEEL now wires the repo-local Claude settings itself through `.claude/settings.json`, so users do not have to manually choose hook slots in the normal case.

What KEEL does provide:

- a repo-local status line
- prompt-time context injection
- a one-shot awareness refresh after write/edit tool use
- a blocking preflight hook available in `~/.claude/hooks/keel_preflight.py`

## Why This Split Exists

KEEL keeps core functionality local and tool-agnostic. Claude support is an integration layer around the CLI, not a hidden product dependency.

## Advanced Plugin Packaging

This repo also contains a reusable Claude plugin marketplace under `.claude-plugin/` and `plugins/keel-companion-plugin/`. Treat that as an advanced distribution or export path for teams, not the normal user setup flow.
