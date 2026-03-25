# ARCHITECTURE

## Current State

KEEL is a Python CLI with Typer, Pydantic, Rich, and YAML-backed local state. The implemented MVP foundation is local-first, terminal-first, and does not depend on MCP or a hosted service for core flows.

## Implemented Runtime Shape

- `keel init` creates and maintains the repo-local control plane and `.keel/` state.
- `keel scan` walks the repository, records confidence-labeled findings, and writes scan artifacts under `keel/discovery/scans/`.
- `keel baseline`, `keel goal`, `keel research`, `keel questions`, `keel align`, `keel plan`, and `keel next` build a discovery-first onboarding chain.
- Session state lives under `.keel/session/` and points to the active artifacts plus the current brief.
- Validation, traceability, drift, delta, and done commands use those artifacts to detect misalignment and missing links.
- `keel watch` runs a reusable awareness pass that refreshes validation, traceability, drift, and the current brief as the repo changes.
- `keel companion` manages a repo-local background watcher so KEEL can stay active even when the user forgets to run explicit checks. It tracks a tokenized heartbeat, preserves existing git hooks by chaining them, and exposes freshness in status output.
- Repo-local agent integration is provided through `AGENTS.md`, `CLAUDE.md`, `.codex/config.toml`, `.claude/settings.json`, `.claude/skills/`, and an optional Claude Code preflight hook script.
- `keel install` now bootstraps the missing repo-local Claude and Codex files for the current repo, records those KEEL-managed bootstrap changes as a delta plus install-specific checkpoint, starts the companion, and runs an install-time session handoff that recommends `recover` or `replan` when an older active session is stale.
- Drift warnings can now be temporarily dismissed by code, which clears both the live drift result and the alert feed for that code until the dismissal window expires.
- The Claude status line now has a CLI fallback path so it can still render KEEL state when Claude launches a different Python interpreter than the one that imported KEEL directly.

## Key Modules

- `src/keel/discovery/scanner.py`
  Scans repo structure and emits confidence-labeled findings for languages, build systems, entrypoints, modules, tests, configs, contracts, and debt markers.
- `src/keel/baseline/generator.py`
  Converts scan output into a flatline of what appears to exist now, what looks authoritative, what looks partial, and what remains unknown.
- `src/keel/goal/service.py`, `src/keel/questions/service.py`, `src/keel/align/service.py`, `src/keel/planner/service.py`
  Turn repo reality plus user intent into targeted questions, alignment output, a phased plan, and a current next step.
- `src/keel/session/service.py`
  Persists active state and writes the concise current brief for future AI or human sessions.
- `src/keel/session/awareness.py`
  Reconciles active artifacts into a one-shot awareness pass and provides the lightweight polling fingerprint used by `keel watch` and hooks.
- `src/keel/session/companion.py`
  Starts and stops the background KEEL companion, installs repo git hooks, and persists companion runtime state under `.keel/session/`.
- `src/keel/validators/service.py`, `src/keel/trace/service.py`, `src/keel/drift/service.py`
  Implement early anti-drift enforcement, traceability, and done-gate support.
  The drift service now also keeps short local drift memory and produces cluster-level warnings when repeated weak signals line up over time.
- `src/keel/recover/service.py`
  Turns drift and validation evidence into a recovery artifact that identifies a divergence anchor, proposes safe recovery modes, and rewrites the current brief around the next corrective move.
- `src/keel/cli/app.py`
  Exposes the CLI and binds commands to artifact creation, updates, and reporting.

## Gaps

- Deeper contract/test parsing and richer drift detection still have room to improve, but the current drift engine already covers goal, plan, spec, runtime-entrypoint, terminology, research, session, and unknown-scope signals.
- Research is bounded and honest, but still intentionally conservative: offline mode is explicit, and no hidden web provider is assumed.
- Runtime-path inference is still heuristic-first; it does not yet trace actual execution with language-aware parsers.
