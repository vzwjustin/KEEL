# KEEL — Invisible Anti-Drift Guardrail for GSD

## Vision

KEEL is the invisible guardrail layer underneath GSD. GSD runs the show — planning, discussion, research, execution, verification. KEEL watches silently in the background, detects when work drifts from the plan, and surfaces interactive drift notifications via `AskUserQuestion`. Users never interact with KEEL directly.

## What KEEL Does

- **Companion**: background process polling every 2s, watching for file changes
- **Drift detection**: layered signals (session, plan, goal, scope, terminology, cluster)
- **Scope guard**: PreToolUse hook blocks edits outside the active plan step
- **Done-gate**: `keel done` refuses to pass until reality matches intent
- **Checkpoint anchors**: snapshots of repo state at phase boundaries
- **GSD bridge**: reads `.planning/STATE.md` and `ROADMAP.md`, syncs goal from active phase

## What KEEL Does NOT Do

- Planning (GSD owns this)
- Questions/discussion (GSD owns this)
- Research (GSD owns this)
- Guides/tips (GSD owns this)
- Statusline (GSD's `gsd-statusline.js` shows `⚓` from KEEL heartbeat)

## Current State

- 343 tests passing, 0 failures
- Python 3.9+, Typer CLI, Pydantic models
- Installed globally via `uv tool install`
- GSD workflows call `keel` automatically at phase boundaries

## Known Issues (from real usage)

1. **Goal silent reset** — `keel goal` with only `--unresolved-question` flags silently overwrites existing goal
2. **Questions can't be resolved from outside** — `align` regenerates from heuristics, ignoring edits (modules removed, but pattern persists in planner)
3. **False-positive structural questions** — monorepo patterns always fire; no suppression mechanism
4. **`research_enabled: false` not surfaced during init** — partially fixed (now prints notice)
5. **Wrong plan entrypoints** — scan heuristics pick wrong anchor from scan
6. **Alert volume on fresh session** — too many alerts before first checkpoint

## Tech Stack

- Python 3.9+, setuptools, uv
- Typer (CLI), Pydantic (models), Rich (output), PyYAML (state)
- No external APIs, no cloud, fully local-first
- All state in `.keel/` within the target repo

## Architecture

```
src/keel/
├── bridge/       ← GSD integration (reads .planning/)
├── cli/          ← Typer CLI (app.py, ~1200 lines)
├── core/         ← paths, artifacts, bootstrap
├── drift/        ← layered drift detection engine
├── discovery/    ← repo scanner
├── goal/         ← goal capture
├── models/       ← Pydantic artifact models
├── planner/      ← plan generation
├── recover/      ← drift → recovery plan
├── session/      ← companion, awareness, alerts
├── trace/        ← file → goal/plan mapping
├── validators/   ← goal/plan validation
└── utils/        ← agent install, templates

.claude/hooks/
├── keel_notify.py       ← PostToolUse: drift → AskUserQuestion
└── keel_scope_guard.py  ← PreToolUse: blocks out-of-scope edits
```
