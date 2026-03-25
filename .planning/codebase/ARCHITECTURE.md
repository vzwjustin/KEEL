# Architecture

**Analysis Date:** 2026-03-25

## Pattern Overview

**Overall:** Local-first artifact pipeline with a background companion watchdog

KEEL is a CLI tool that produces and consumes a chain of typed YAML artifacts: scan → baseline → goal → questions → alignment → plan → validation → trace → drift. Each artifact is an immutable timestamped file written to the repo's `keel/` directory tree. A long-running companion process (`keel watch`) continuously monitors the repo for change, reruns the awareness pipeline, and writes notifications and alerts. GSD integration is a read-only bridge that reads `.planning/STATE.md` and writes `.planning/KEEL-STATUS.md`.

**Key Characteristics:**
- Artifacts are append-only YAML files; the "active" artifact is resolved by session pointer or latest-by-filename sort
- All cross-module communication goes through the artifact layer, not in-memory objects
- The companion process runs as a detached subprocess (`start_new_session=True`), writing heartbeat and notification files rather than using IPC
- Validation and drift run on every awareness pass; the `done` gate blocks on their findings
- Confidence levels (`deterministic`, `inferred-high-confidence`, `inferred-medium-confidence`, `heuristic-low-confidence`, `unresolved`) propagate from scan findings through to every downstream artifact

---

## Layers

**CLI Layer:**
- Purpose: User-facing Typer commands; also the entry point for the companion watch loop
- Location: `src/keel/cli/app.py`, `src/keel/cli/main.py`
- Contains: One `@app.command()` per command, `AppState` context object, helper functions `_save_and_render`, `_load_latest`, `_load_preferred_report`, `_refresh_brief`
- Depends on: Every service module; `reporters`, `models`, `session`, `bridge`
- Key note: `_refresh_brief` also mirrors the brief into `.planning/KEEL-STATUS.md` via the GSD bridge after every state-changing command

**Models Layer:**
- Purpose: Pydantic artifact schemas — the shared contract between all modules
- Location: `src/keel/models/artifacts.py`, `src/keel/models/__init__.py`
- Contains: `ArtifactBase`, `ScanArtifact`, `BaselineArtifact`, `GoalArtifact`, `QuestionArtifact`, `AlignmentArtifact`, `PlanArtifact`, `ValidationArtifact`, `TraceArtifact`, `DriftArtifact`, `DeltaArtifact`, `RecoveryArtifact`, `SessionState`, plus enum types `ConfidenceLevel`, `SeverityLevel`, `GoalMode`
- Depends on: `pydantic` only
- Used by: Every other module

**Core Layer:**
- Purpose: Filesystem I/O primitives — paths resolution, YAML read/write, artifact save/load
- Location: `src/keel/core/paths.py`, `src/keel/core/artifacts.py`, `src/keel/core/bootstrap.py`
- Contains: `KeelPaths` (frozen dataclass with every path as a property), `resolve_paths()`, `save_yaml/load_yaml`, `save_artifact/load_latest_model/load_model_by_artifact_id`, `ensure_project()` (creates all directories and default files)
- Depends on: `models`, `config`
- Used by: All service modules

**Config Layer:**
- Purpose: `KeelConfig` Pydantic model and YAML serialization
- Location: `src/keel/config/settings.py`
- Contains: `StrictnessProfile` enum (`relaxed`, `standard`, `strict`, `paranoid`), `KeelConfig` with `strictness`, `research_enabled`, `max_scan_files`, `ignored_directories`

**Discovery Layer:**
- Purpose: Repo scanner that produces `ScanArtifact`
- Location: `src/keel/discovery/scanner.py`
- Contains: File-walk logic; detects languages by suffix, build systems by known filenames, entrypoints, modules, contracts, runtime surfaces
- Depends on: `config`, `models`, `core`

**Baseline Layer:**
- Purpose: Derives `BaselineArtifact` from a `ScanArtifact`; buckets findings into `exists_today`, `authoritative`, `partial`, `stale`, `broken_or_ambiguous`, `unknowns`
- Location: `src/keel/baseline/generator.py`
- Depends on: `models`

**Goal Layer:**
- Purpose: Produces `GoalArtifact` from user-supplied fields and a `GoalMode`
- Location: `src/keel/goal/service.py`
- Contains: `build_goal()` — pure function, no I/O
- Depends on: `models`

**Planner Layer:**
- Purpose: Produces `PlanArtifact` with phases and steps from the active bundle
- Location: `src/keel/planner/service.py`
- Contains: Phase-1 helpers (resolve unknowns, lock reality), subsequent phase builders keyed on `GoalMode`
- Depends on: `models`

**Validators Layer:**
- Purpose: Structural validation of session completeness — produces `ValidationArtifact`
- Location: `src/keel/validators/service.py`
- Contains: `run_validation()` — checks for missing success criteria (KEE-VAL-001), missing plan (KEE-VAL-002), missing delta for behavior-changing goal (KEE-VAL-003), open high-priority questions; severity escalates with strictness profile
- Depends on: `models`, `config`, `core/paths`

**Drift Layer:**
- Purpose: Detects drift between repo state and session artifacts — produces `DriftArtifact`
- Location: `src/keel/drift/service.py`
- Contains: `detect_drift()`, `dismiss_drift_codes()`, `clear_managed_install_drift()`; reads `drift-memory.yaml` for clustering; emits `DriftFinding` per code and `DriftCluster` for sustained patterns; supports `soft`, `hard`, `auto` modes
- Depends on: `models`, `core`, `config`

**Trace Layer:**
- Purpose: Produces `TraceArtifact` linking goal success criteria → plan steps → validation status
- Location: `src/keel/trace/service.py`
- Contains: `build_trace()` — pure function
- Depends on: `models`

**Recover Layer:**
- Purpose: Produces `RecoveryArtifact` suggesting recovery mode from active drift codes
- Location: `src/keel/recover/service.py`
- Contains: `MODE_RULES` dict mapping drift codes to recovery modes (`rewind-plan-only`, `update-goal-spec`, `create-delta-and-continue`, `rollback-code-path`)
- Depends on: `models`, `core`, `session`

**Session Layer:**
- Purpose: Manages `SessionState`, the companion process, awareness loop, alerts, and brief generation
- Location: `src/keel/session/` — `service.py`, `companion.py`, `awareness.py`, `alerts.py`, `ui.py`
- `service.py`: `SessionService` class — load/save session, advance step, record decisions, sync report state IDs
- `companion.py`: `start_companion()`, `stop_companion()`, `install_git_hooks()`, heartbeat token management
- `awareness.py`: `run_awareness_pass()` — orchestrates validation → trace → drift → alerts → notification → brief refresh; `load_active_bundle()`, `refresh_current_brief()`, `repo_watch_fingerprint()`, `latest_repo_change_at()`
- `alerts.py`: `update_alert_feed()`, `load_active_alerts()` — upsert-by-key alert list written to `.keel/session/alerts.yaml`
- `ui.py`: `build_statusline_text()`, `build_claude_context()`, `build_claude_system_message()`, `consume_pending_notification()`, `_vibe()` — terminal and agent-facing surfaces; also exposes `_write_drift_notification()` consumed by awareness

**Bridge Layer:**
- Purpose: Read-only integration with GSD; no GSD dependency at import time
- Location: `src/keel/bridge/gsd.py`
- Contains: `read_gsd_state()` — parses `.planning/STATE.md` with regex; `read_gsd_roadmap()` — parses `.planning/ROADMAP.md`; `sync_goal_from_gsd()` — returns goal text for active phase; `write_keel_brief_to_planning()` — writes `.planning/KEEL-STATUS.md`; `gsd_present()` — existence check
- Depends on: `pathlib`, `re` only

**Rules Layer:**
- Purpose: Static catalog of error codes and confidence explanations
- Location: `src/keel/rules/catalog.py`
- Contains: `ERROR_CODES` dict, `CONFIDENCE_EXPLANATIONS` dict — referenced in CLI output

**Reporters Layer:**
- Purpose: Render artifacts to Rich panels or JSON
- Location: `src/keel/reporters/render.py`
- Contains: `render_result()`, `render_artifact()` — both accept `json_output: bool`; JSON path calls `console.print_json`

---

## Data Flow

**Primary Wizard Flow (manual, sequential):**

1. `keel init` — `ensure_project()` creates `.keel/` dirs and `SessionState` stub
2. `keel scan` — `scan_repository()` walks repo, writes `keel/discovery/scans/<id>.yaml`
3. `keel baseline` — `build_baseline(scan)` writes `keel/discovery/baselines/<id>.yaml`
4. `keel goal --goal-mode <mode>` — `build_goal()` writes `keel/discovery/goals/<id>.yaml`; auto-activates in session; if GSD present and no `--goal-statement`, pulls goal from active GSD phase
5. `keel plan` — `build_plan(scan, baseline, goal, alignment, questions)` writes `keel/discovery/plans/<id>.yaml`; auto-activates in session
6. `keel validate` — `run_validation(goal, plan, questions, deltas)` writes `.keel/reports/validation/<id>.yaml`
7. `keel drift` — `detect_drift(...)` writes `.keel/reports/drift/<id>.yaml`
8. `keel done` — reads latest validation + drift artifacts; blocks if blockers present

**Companion Watch Loop (background, continuous):**

1. `keel companion start` → `start_companion()` launches `python -m keel watch` as detached subprocess
2. `watch` command polls `repo_watch_fingerprint()` every `--interval` seconds
3. On fingerprint change → `run_awareness_pass()` which runs: `run_validation()` → `build_trace()` → `detect_drift()`
4. Results written to `.keel/reports/{validation,trace,drift}/`
5. `update_alert_feed()` upserts findings into `.keel/session/alerts.yaml`
6. `_write_drift_notification()` writes `.keel/session/pending-notification.yaml` only on new drift code transition
7. `refresh_current_brief()` rewrites `.keel/session/current-brief.md`
8. `write_companion_heartbeat()` writes `.keel/session/companion-heartbeat.yaml` with token
9. Git hooks (`post-checkout`, `post-merge`, `pre-commit`) invoke `keel watch --once --mode auto` to trigger a one-shot pass on git events

**Notification Delivery (one-shot):**

1. `build_claude_system_message(repo_root)` called by Claude Code hook at session start
2. Calls `consume_pending_notification()` — reads AND deletes `.keel/session/pending-notification.yaml`
3. Returns the notification string (e.g., `"KEEL — you're drifting, heads up"`) if present, else falls back to top active alert summary

**Drift Detection Internal Flow:**

1. `detect_drift()` loads `drift-memory.yaml` for recent events (last 10 minutes)
2. Checks changed files via `_changed_files_since()` (mtime walk, ignores `.git`, `.keel`, managed agent roots)
3. Applies rule checks against goal scope, plan step references, active deltas, open questions, scan baseline
4. Each finding assigned a `code` (e.g., `KEE-DRF-001`), `layer`, `severity`, `confidence`
5. Active dismissals loaded from `drift-dismissals.yaml` and filtered out
6. Events appended to `drift-memory.yaml` ring buffer (max 80 events) for cluster detection
7. Returns `DriftArtifact` with `findings` list and `clusters` list

---

## Key Abstractions

**ArtifactBase:**
- Purpose: All produced outputs inherit from this; provides `artifact_id`, `artifact_type`, `created_at`, `repo_root`
- Examples: `src/keel/models/artifacts.py` — every `*Artifact` class
- Pattern: Pydantic `BaseModel`; saved to YAML via `save_artifact(paths, directory, prefix, model)`; loaded by `load_latest_model()` (latest by filename sort) or `load_model_by_artifact_id()` (session pointer)

**SessionState:**
- Purpose: Mutable pointer to active artifact IDs; persisted at `.keel/session/current.yaml`
- Examples: `src/keel/models/artifacts.py` (`SessionState`), `src/keel/session/service.py` (`SessionService`)
- Pattern: Load → mutate → save pattern via `SessionService`; `active_goal_id`, `active_plan_id`, `latest_drift_id`, etc. are artifact IDs used to resolve the preferred report

**KeelPaths:**
- Purpose: Single source of truth for every filesystem path; constructed from repo root
- Examples: `src/keel/core/paths.py`
- Pattern: Frozen dataclass with `@property` for each path; `ensure()` creates all required directories; passed by value to every service function

**ConfidenceLevel:**
- Purpose: Epistemic quality tag on every finding and conclusion
- Pattern: `deterministic` = proved by file evidence; `inferred-high-confidence` = multiple signals; `inferred-medium-confidence` = partial; `heuristic-low-confidence` = pattern match only; `unresolved` = cannot determine

---

## Entry Points

**CLI entry:**
- Location: `src/keel/cli/main.py` → `main()` → `app()`
- Triggers: `keel <command>` or `python -m keel`
- Responsibilities: Normalizes `--json` flag position, delegates to Typer app

**Package entry:**
- Location: `src/keel/__main__.py` (referenced but not shown; standard Python `-m keel` entry)

**Companion subprocess entry:**
- Location: `keel watch` command in `src/keel/cli/app.py`
- Triggers: `start_companion()` spawns `python -m keel watch --mode auto --interval 2.0`
- Responsibilities: Polling loop, fingerprint comparison, awareness passes, heartbeat writes

**Git hook entry:**
- Location: `.git/hooks/post-checkout`, `.git/hooks/post-merge`, `.git/hooks/pre-commit` (installed by `keel install`)
- Triggers: Git operations
- Responsibilities: `keel watch --once --mode auto` to capture one awareness pass on git events

**GSD hook entry:**
- Location: Invoked by Claude Code hook calling `build_claude_system_message(repo_root)` or `build_claude_context(repo_root)` from `src/keel/session/ui.py`
- Triggers: Claude Code session start
- Responsibilities: Emit pending notification or top alert as system message; inject brief + alerts + open questions into agent context

---

## Error Handling

**Strategy:** Functions return typed artifacts even on partial failure; error state encoded in `status` field of artifact (`"clear"`, `"warning"`, `"blocked"`, `"error"`). CLI raises `typer.Exit(code=1)` when a required prerequisite artifact is missing.

**Patterns:**
- `load_latest_model()` returns `None` if no artifact files exist; callers check before use
- `companion_status()` detects dead processes by PID probe (`os.kill(pid, 0)`); marks `fresh=False`
- Drift detection skips paths that raise `OSError` during `stat()`
- All YAML loads use `or {}` / `or []` defaults; malformed files return empty collections rather than raising
- `consume_pending_notification()` deletes the file on read to prevent double delivery; returns `None` on any `OSError`

---

## Cross-Cutting Concerns

**Logging:** Companion writes to `.keel/session/companion.log`; rotated at 512KB. All other modules are silent except for `render_result()` / `render_artifact()` to stdout via Rich.

**Validation:** Session completeness enforced by `run_validation()` in `src/keel/validators/service.py`; structural correctness enforced at load time by Pydantic model validation.

**Authentication:** None — fully local, no network calls except optional research feature (disabled by default via `research_enabled: false`).

**Strictness escalation:** `KeelConfig.strictness` (`relaxed` / `standard` / `strict` / `paranoid`) escalates finding severity in `run_validation()` and in the `done` gate. `paranoid` promotes warnings to blockers.

**Artifact ID format:** `<type>-YYYYMMDD-HHMMSS` (e.g., `scan-20260325-143022`). Delta IDs use `delta-<repo-name>-<slug>`. All IDs used as filenames: `<id>.yaml`.

**GSD coupling:** The bridge (`src/keel/bridge/gsd.py`) uses only `pathlib` and `re`; it is never imported at module load time in service modules — only called lazily inside CLI command bodies. KEEL makes no assumption that GSD is present.

---

## File Artifact Directory Map

```
<repo-root>/
├── .keel/                          # Runtime state (not committed)
│   ├── config.yaml                 # KeelConfig
│   ├── done-gate.yaml              # Done gate required checks
│   ├── glossary.yaml               # Term definitions
│   ├── session/
│   │   ├── current.yaml            # SessionState (active IDs)
│   │   ├── current-brief.md        # Human/agent-readable brief
│   │   ├── checkpoints.yaml        # Checkpoint history
│   │   ├── decisions.log           # Append-only decisions log
│   │   ├── unresolved-questions.yaml
│   │   ├── alerts.yaml             # Alert feed (max 25)
│   │   ├── companion.yaml          # Companion PID + token
│   │   ├── companion-heartbeat.yaml
│   │   ├── companion.log           # Companion stdout/stderr
│   │   ├── drift-memory.yaml       # Ring buffer of drift events
│   │   ├── drift-dismissals.yaml   # Active code dismissals
│   │   ├── drift-notification-state.yaml   # Last-emitted codes
│   │   └── pending-notification.yaml       # One-shot agent notification
│   ├── reports/
│   │   ├── validation/<id>.yaml
│   │   ├── drift/<id>.yaml
│   │   └── trace/<id>.yaml
│   ├── research/                   # (future use)
│   ├── prompts/                    # (future use)
│   └── templates/                  # (future use)
└── keel/                           # Artifact store (can be committed)
    ├── discovery/
    │   ├── scans/<id>.yaml
    │   ├── baselines/<id>.yaml
    │   ├── goals/<id>.yaml
    │   ├── questions/<id>.yaml
    │   ├── alignments/<id>.yaml
    │   ├── plans/<id>.yaml
    │   ├── checkpoints/<id>.yaml
    │   └── research/<id>.yaml
    └── specs/
        ├── requirements/<id>.yaml
        ├── decisions/<id>.yaml
        ├── contracts/<id>.yaml
        ├── examples/<id>.yaml
        ├── validation/<id>.yaml
        └── deltas/<id>.yaml
```

---

*Architecture analysis: 2026-03-25*
