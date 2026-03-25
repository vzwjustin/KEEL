# WORKLOG

## 2026-03-24

- Bootstrapped the repository layout for KEEL.
- Created the repo-local control plane: `AGENTS.md`, `WORKLOG.md`, `TASKS.md`, `ARCHITECTURE.md`, and `.keel/` state directories.
- Started the MVP foundation slice for packaging, discovery, baseline, planning, and session persistence.
- Noted an environment gap: the root-level `CLAUDE.md` referenced by incoming instructions did not exist when work began.
- Added a repo-local `CLAUDE.md` so Claude Code sessions can re-enter with the same anti-drift workflow and state files.
- Added repo-local Claude Code skills, an optional KEEL preflight hook script, and an installer helper for skill deployment.
- Implemented the Python CLI with Typer, Pydantic, Rich, YAML-backed artifact persistence, and a pipx-friendly `keel` entrypoint.
- Implemented `keel start`, `scan`, `baseline`, `goal`, `research`, `questions`, `align`, `plan`, `next`, `checkpoint`, `validate`, `trace`, `drift`, `delta`, `done`, `status`, `check`, `doctor`, `scaffold`, `explain`, and `export`.
- Landed a layered drift detector covering goal, plan, spec, runtime-entrypoint, research, terminology, session, unknown-scope, and duplicate-implementation signals with soft and hard modes.
- Added pytest fixture repos and CLI/integration tests. Current MVP suite passes locally with `python3 -m pytest -q`.
- Tightened state authority and anti-drift enforcement: unresolved questions and decisions now persist into session files, strict/paranoid mode escalates missing delta and unresolved-question warnings into blockers, changed-file mapping checks managed artifacts before flagging unmapped drift, and `keel delta` accepts both positional summaries and `--summary`.
- Added installable Codex skills, a unified Codex/Claude asset installer, and automatic Claude hook installation support.
- Added a shared awareness pass plus `keel watch` so KEEL can refresh validation, traceability, drift, and the current brief continuously while coding instead of waiting for a manual check.
- Promoted KEEL toward a real companion by adding a repo-local background companion process, repo git hooks, and install-time auto-start so users do not have to remember to run checks manually.
- Hardened the companion path: existing git hooks are preserved and chained instead of overwritten, the companion now publishes a heartbeat and freshness signal, install output distinguishes companion-only mode on non-git repos, and startup/log handling is less brittle.
- Added a first drift cluster engine: KEEL now keeps short-lived drift memory, groups repeated weak signals by layer and touched scope, and emits a timeline-backed probable drift cluster instead of only isolated warnings.
- Added `keel recover`, a first recovery engine that turns live drift into a divergence anchor, recovery modes, a concrete reconciliation route, and a recovery-oriented current brief.
- Added a real Claude Code plugin packaging path: this repo now exposes a local plugin marketplace plus a reusable `keel-companion-plugin`, while keeping project `.claude/settings.json` for the UI surfaces plugins cannot currently own.
- Tightened the setup path for vibe coders: `keel install` now bootstraps missing repo-local `.claude/` and `.codex/` files for arbitrary repos instead of assuming those files already exist, and the docs now treat the Claude plugin as advanced and optional.
- Added install-time stale-session handoff: `keel install` now refreshes awareness for an existing active session and explicitly recommends `keel recover` or `keel replan` instead of leaving drift interpretation to the user.
- Tightened the companion UX from real setup feedback: install no longer poisons its own drift scan with `.claude` and `.codex` bootstrap changes, drift clusters can be dismissed temporarily, `recover` surfaces step titles inline, the shipped skills use the correct global `--json` flag order, and the Claude status line can fall back through the CLI when imports are unavailable.
