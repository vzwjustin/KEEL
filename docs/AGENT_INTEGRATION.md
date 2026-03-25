# Agent Integration

KEEL ships repo-local support assets for both Codex and Claude Code, and `keel install` is the default way to wire them up.

## What Gets Installed

- Repo-local `.codex/config.toml` and `.codex/skills/` when they are missing
- Repo-local `.claude/settings.json`, `.claude/statusline.py`, `.claude/hooks/`, and `.claude/skills/` when they are missing
- Codex skills from `.codex/skills/` into `${CODEX_HOME:-~/.codex}/skills/`
- Claude Code skills from `.claude/skills/` into `~/.claude/skills/`
- Claude Code hook from `.claude/hooks/keel_preflight.py` into `~/.claude/hooks/` unless `--no-hook` is passed
- Repo git hooks under `.git/hooks/` unless `--no-repo-hooks` is passed. Existing hooks are preserved as `*.local` and chained instead of being overwritten.
- A local background KEEL companion for the current repo unless `--no-companion` is passed

## Install Everything

```bash
keel install
```

That one command bootstraps the repo-local Codex and Claude files, installs the home-directory agent assets, installs repo-local git hooks, and starts the current repo's background KEEL companion.
If KEEL finds an older active session that no longer matches repo reality, `keel install` will immediately steer the user toward `keel recover` and offer `keel replan` as the intentional-pivot path.

If KEEL is not installed yet, use:

```bash
python3 scripts/install_agent_assets.py
```

Or in one repo-local step:

```bash
make dev-install
```

## Vibe-Coder Default

Use this and stop thinking about setup details:

```bash
python3 -m pip install -e .
keel install
```

## Install Only One Side

```bash
keel install --codex-only
keel install --claude-only
```

## Companion Controls

```bash
keel companion status
keel companion stop
keel companion start
```

`keel companion status` reports whether the companion is running, whether its heartbeat is fresh, and the last repo change it observed.

## Override Homes

```bash
keel install --codex-home /tmp/codex-home --claude-home /tmp/claude-home
```

## What Stays Repo-Local

- `AGENTS.md`
- `CLAUDE.md`
- `.codex/config.toml`
- `.claude/settings.json`
- `.keel/session/*`

Those files are part of the project’s durable operating state and should remain inside the repository.

## Advanced Claude Plugin Path

The Claude plugin marketplace in this repo is optional and mainly useful for sharing KEEL automation across teams. It is not the normal setup path for users. For normal use, stick with `keel install`.
