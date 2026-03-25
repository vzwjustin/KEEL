# KEEL

**Local-first anti-drift companion for AI coding agents.**

KEEL keeps AI agents (Claude Code, Codex, Cursor, etc.) honest while they work on your codebase. It tracks what the agent said it would do, detects when work drifts from the plan, and blocks "done" until reality matches intent.

No cloud. No MCP runtime dependency. Just YAML artifacts in `.keel/` and a CLI.

> **Early alpha / proof of concept.** The core ideas work and the companion loop is real, but expect rough edges, breaking changes, and missing features. Feedback and contributions welcome.

## The Companion — Why KEEL Exists

The companion is what makes KEEL fundamentally different from a linter or a one-shot audit tool. It's a **persistent, real-time awareness loop** that runs alongside your AI agent and catches drift *as it happens*, not after.

AI agents don't self-correct. They commit to a plan, then silently wander. By the time a human reviews the PR, the damage is done — wrong files touched, scope ballooned, the "done" claim doesn't match the goal. The companion closes that feedback loop in real-time. The agent gets a drift warning *while it's still in the session*, early enough to course-correct.

**What it does:**
- Polls the repo every 2 seconds in the background
- On every file change: re-runs validation, drift detection, traceability, and cluster analysis
- Updates the current brief, alert feed, and heartbeat in real-time
- Pushes drift notifications into the agent's status line and hooks — the agent sees drift *during* the tool call that caused it, not 10 minutes later
- Writes a heartbeat so the status line, hooks, and other tools can verify the companion is alive and fresh

**Resilience:**
- Per-cycle error handling with exponential backoff — a single bad awareness pass doesn't kill the companion
- Logs exit reason on any shutdown (crash, signal, error cascade)
- Detects dead processes and writes truthful state — no stale "running: true" lies
- Heartbeat staleness detection tells you if the companion is alive but stuck vs. actually dead

```bash
keel companion status   # check if alive, fresh, and token-matched
keel companion start    # start if not running
keel companion stop     # stop gracefully
```

## Guardrails — What's Working Now, What's WIP

KEEL is being built to create **hard stops** that prevent AI agents from causing further damage once drift is detected. Some guardrails are already in place. Others are work in progress.

**Working now:**
- **Real-time drift detection** — the companion catches scope creep, plan drift, and goal drift as files change
- **Done-gate blocking** — `keel done` refuses to pass until reality matches the declared goal and plan
- **Confidence labeling** — every signal says whether it's proven or a guess, so agents can't treat heuristics as facts
- **Alert feed into agent context** — Claude Code sees drift warnings in its status line and hooks *during* the session, not after
- **Cluster detection** — repeated weak signals roll up into a probable drift warning before they become a real problem
- **Checkpoint/recover flow** — `keel recover` automatically creates a checkpoint the moment it detects drift, freezing the current state as a recovery anchor before producing a concrete route back — the agent can't lose the "last known good" point
- **Development guide** — `keel guide` gives contextual coaching for the current step: what to do, what to avoid, when you're done — adapts to your phase, goal mode, and active warnings
- **Teaching drift** — every drift rule includes a plain-language explanation of *why* it matters, so agents learn spec-driven development instead of just getting flagged
- **Repo-aware planning** — `keel plan` generates steps specific to your actual codebase: real file paths, real unknowns, real entrypoints — not a generic template
- **Step advancement** — `keel advance` marks the current step done, auto-checkpoints, and advances to the next step in the plan
- **Auto-replan detection** — the companion watches for accumulating drift warnings and suggests `keel replan` when the plan no longer matches reality
- **Pre-edit hard stop** — a `PreToolUse` hook intercepts Write/Edit *before* they execute. If the target file is outside the active plan step and no delta covers it, the edit is blocked. The agent must `keel delta`, `keel replan`, or `keel advance` to proceed. Managed paths (`.keel/`, `.claude/`, `.codex/`) are always allowed.

**WIP — building toward more hard stops:**
- **Automatic session pause** — when drift severity hits a threshold, force the agent to stop and get human confirmation before continuing
- **Budget/token guardrails** — detect when an agent is churning (lots of edits, no progress) and interrupt the loop
- **Cross-agent consistency** — if Claude Code and Codex both touch the same repo, detect conflicting intent

The goal is a system where the agent literally *cannot* keep writing code that doesn't match the plan — not just a warning it can ignore, but a wall it has to stop at.

## Why

AI coding agents are powerful but forgetful. They lose track of goals mid-session, silently change scope, present heuristics as proof, and declare "done" before the work actually matches the plan. KEEL is the guardrail layer — it watches the repo, detects drift in real-time, and keeps the agent (and you) aligned.

## Quick Start

```bash
# Install from source
pip install -e .

# Set up any repo
cd your-project/
keel install    # bootstraps .claude/, .codex/, hooks, companion
keel start      # scan, goal, plan, baseline — one command
```

That's it. The companion is now watching your repo in the background.

## What `keel install` Does

- Bootstraps `.claude/` and `.codex/` agent config files
- Installs Claude Code skills and hooks
- Installs Codex skills
- Installs lightweight repo git hooks (preserves existing ones)
- Starts a background companion process
- Records its own bootstrap as a KEEL delta so it doesn't trigger false drift

## What `keel start` Does

- Scans the repo (languages, entrypoints, structure)
- Generates a current-state baseline
- Captures a goal (what you're trying to do)
- Generates targeted questions about unknowns
- Aligns context and produces a phased plan
- Writes a human-readable brief to `.keel/session/current-brief.md`

## Core Commands

| Command | What it does |
|---------|-------------|
| `keel start` | Full onboarding flow: scan → goal → plan |
| `keel wizard` | Interactive first-run wizard |
| `keel scan` | Discover repo structure and entrypoints |
| `keel goal` | Capture or update the active goal |
| `keel plan` | Generate or update the active plan |
| `keel next` | Show the next step from the active plan |
| `keel watch` | Continuous awareness loop (foreground) |
| `keel companion start/stop/status` | Background companion process |
| `keel validate` | Check goal/plan/question alignment |
| `keel drift` | Detect drift between plan and reality |
| `keel trace` | Map changed files to goals and plan steps |
| `keel delta` | Record a behavior/contract/surface change |
| `keel checkpoint` | Snapshot the current repo state |
| `keel recover` | Turn drift into a recovery plan |
| `keel done` | Gate: only passes when reality matches intent |
| `keel check` | Quick health check of KEEL state |
| `keel status` | Show current session state |
| `keel install` | Bootstrap agent integrations + companion |
| `keel guide` / `keel tips` | Contextual development coaching for the current step |
| `keel advance` | Mark current step done and move to the next one |
| `keel doctor` | Diagnose KEEL installation issues |
| `keel export` | Export session state as JSON |

## How Drift Detection Works

KEEL layers multiple drift signals:

- **Session drift** — files changed after the latest scan/checkpoint
- **Plan drift** — changed files outside the active plan step
- **Goal drift** — work doesn't match the declared goal scope
- **Scope expansion** — edits spanning more subsystems than planned
- **Brief staleness** — the current brief is outdated
- **Terminology drift** — competing terms for the same concept
- **Cluster detection** — repeated weak signals rolled up into probable drift

Each signal carries a confidence level (`deterministic`, `inferred-high`, `inferred-medium`, `heuristic-low`) so you know what's proven vs. what's a guess.

## Claude Code Integration

After `keel install`, Claude Code gets:
- **Status line** showing drift state, companion health, and current goal
- **PostToolUse hook** that syncs real-time drift notifications
- **Skills** for session alignment and drift recovery
- **Preflight hook** that loads the current brief into context

## Codex Integration

After `keel install`, Codex gets:
- Skills for session alignment and drift recovery
- Config in `.codex/config.toml`

## Architecture

```
.keel/
├── config.yaml              # KEEL configuration
├── done-gate.yaml           # Done-gate rules
├── glossary.yaml            # Canonical terms
├── prompts/                 # Agent prompt templates
├── reports/
│   ├── drift/               # Timestamped drift reports
│   ├── trace/               # Traceability reports
│   └── validation/          # Validation reports
├── session/
│   ├── alerts.yaml          # Active alert feed
│   ├── current.yaml         # Session state
│   ├── current-brief.md     # Human-readable brief
│   ├── companion.yaml       # Companion process state
│   ├── companion-heartbeat.yaml
│   ├── checkpoints.yaml     # Checkpoint history
│   └── decisions.log        # Decision log
└── templates/               # Artifact templates
```

Source code:
```
src/keel/
├── cli/          # Typer CLI (app.py)
├── session/      # Companion, awareness, alerts, UI
├── drift/        # Layered drift detection engine
├── discovery/    # Repo scanner
├── models/       # Pydantic artifact models
├── validators/   # Goal/plan/question validation
├── trace/        # Changed-file → goal/plan mapping
├── recover/      # Drift → recovery plan engine
├── goal/         # Goal capture
├── planner/      # Plan generation
├── questions/    # Question generation
├── align/        # Context alignment
├── baseline/     # Baseline generation
├── research/     # Bounded research service
├── rules/        # Drift rule catalog
└── utils/        # Agent install, statusline, text
```

## Known Issues

See [GitHub Issues](https://github.com/vzwjustin/KEEL/issues) for the current list. Key ones:

1. **Companion dies silently** (#1) — poll loop now has error resilience, but auto-restart not yet implemented
2. **Fresh repo shows "drifting"** (#2) — `keel start` needs a post-bootstrap checkpoint
3. **5 test failures from UX changes** (#3) — test assertions need updating for new status line wording
4. **Cluster evidence leaks managed paths** (#4) — `.claude/` paths show up in drift cluster evidence

## Design Principles

- **Local-first**: Git and local files are the source of truth. No cloud, no accounts.
- **Honest confidence**: Every signal is labeled `repo-fact`, `external-guidance`, `inferred`, or `unresolved`. KEEL never presents heuristics as proof.
- **Vertical slices**: Small finished slices over broad scaffolding.
- **Anti-drift as product behavior**: Drift detection is core, not an optional report.

## Running Tests

```bash
python3 -m pytest -q
```

29 passing, 5 failing (see #3).
