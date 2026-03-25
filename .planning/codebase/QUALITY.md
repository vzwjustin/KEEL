# Code Quality Analysis

**Analysis Date:** 2026-03-25

---

## Test Suite

### Framework and Configuration

- **Runner:** pytest (invoked via `python -m pytest`)
- **Config:** `pyproject.toml` at repo root
- **Test root:** `tests/`
- **Fixtures root:** `tests/fixtures/`
- **Conftest:** `tests/conftest.py`

### Test File Inventory

| File | Tests | Lines | Coverage Area |
|------|-------|-------|---------------|
| `tests/test_core.py` | 88 | 532 | `core/artifacts.py`, `core/paths.py`, `core/bootstrap.py` |
| `tests/test_drift_dismiss.py` | 71 | 1001 | `drift/service.py` (dismissal, model validation) |
| `tests/test_session.py` | 73 | 979 | `session/service.py`, `session/alerts.py` |
| `tests/test_planner_validators.py` | 53 | 1046 | `planner/service.py`, `validators/service.py` |
| `tests/test_services.py` | 21 | 342 | `goal/service.py`, `baseline/generator.py`, `trace/service.py` |
| `tests/test_install_agents_cli.py` | 8 | 346 | CLI `install` command end-to-end |
| `tests/test_companion.py` | 4 | 128 | `session/companion.py`, git hooks |
| `tests/test_drift.py` | 6 | 150 | Drift detection end-to-end (clusters, done-gate) |
| `tests/test_session.py` | 73 | 979 | SessionService CRUD, alert helpers |
| `tests/test_watch.py` | 2 | 59 | `watch --once` command |
| `tests/test_recover.py` | 2 | 58 | `recover` command |
| `tests/test_claude_ui.py` | 2 | 62 | `session/ui.py` context and system message |
| `tests/test_scan.py` | 1 | 17 | `discovery/scanner.py` |
| `tests/test_installer.py` | 2 | 52 | `scripts/install_agent_assets.py` |
| `tests/test_claude_plugin.py` | 1 | 19 | Plugin manifest validity |

**Total: ~334 test functions, 4836 test lines**

### Test Patterns

**Unit tests** use `tmp_path` pytest fixture and `KeelPaths(tmp_path)`. Pattern:

```python
@pytest.fixture()
def paths(tmp_path: Path) -> KeelPaths:
    p = KeelPaths(tmp_path)
    p.ensure()
    return p

@pytest.fixture()
def svc(paths: KeelPaths) -> SessionService:
    return SessionService(paths)
```

**Integration/CLI tests** use `typer.testing.CliRunner` and the `fixture_repo` fixture from `tests/conftest.py`:

```python
@pytest.fixture()
def fixture_repo(tmp_path: Path):
    def _copy(name: str) -> Path:
        source = Path(__file__).parent / "fixtures" / name
        target = tmp_path / name
        shutil.copytree(source, target)
        return target
    return _copy
```

**Bootstrap helper** in conftest replaces a removed `keel start` command:

```python
def keel_bootstrap(repo: Path, runner: CliRunner | None = None, **goal_kwargs) -> None:
    """Replace the removed 'keel start' by running init + scan + baseline + goal."""
    r.invoke(app, base + ["init"])
    r.invoke(app, base + ["scan"])
    r.invoke(app, base + ["baseline"])
    r.invoke(app, base + ["goal", "--goal-mode", goal_mode])
```

**Factory helpers** are inline per test module (no shared factory library):
- `_make_scan()`, `_make_baseline()`, `_make_goal()`, `_make_plan()` in `test_session.py`
- `_scan()`, `_goal()`, `_plan()`, `_session()`, `_baseline()` in `test_services.py`
- `_minimal_scan()`, `_rich_scan()` in `test_planner_validators.py`

### Test Fixture Repos

Two fixture repos live under `tests/fixtures/`:

- `tests/fixtures/messy_repo/` — has wip features, TODO markers, partial keel config. Used for drift/validate/recover tests.
- `tests/fixtures/multi_entry_repo/` — has multiple entrypoints (`cli.py`, `main.py`, `server.py`). Used for entrypoint drift detection tests.

---

## Coverage Gaps

### Explicitly Hollow Test Sections

**`tests/test_services.py` has two empty test sections:**

```python
# ===================================================================
# Questions tests
# ===================================================================

# ===================================================================

# ===================================================================

class TestBuildBaseline:
    ...

# ===================================================================
# Guide tests
# ===================================================================
```

Lines 206–213 and 340–342 are placeholder stubs. No `QuestionArtifact` generation logic is tested. The guide module (`build/lib/keel/guide/` exists in build but `src/keel/guide/` does not) has no tests at all.

### Untested Modules and Functions

**`src/keel/session/ui.py`** (`build_statusline_text`, `build_claude_context`, `build_claude_system_message`, `consume_pending_notification`):
- `test_claude_ui.py` has only 2 tests covering alert summary output and system message. `build_statusline_text` has zero direct tests. `consume_pending_notification` has zero tests.

**`src/keel/drift/service.py` drift rules with no dedicated unit test:**
- `KEE-DRF-006` (research drift) — no test
- `KEE-DRF-007` (code change during non-implementation goal) — no test
- `KEE-DRF-008` (refactor with behavior-change signals) — no test
- `KEE-DRF-010` (spec artifacts changed without delta) — no test
- `KEE-DRF-011` (implementation moved without spec updates) — no test
- `KEE-DRF-012` (recent work doesn't match goal scope) — no test
- `KEE-DRF-013` (terminology drift) — no test
- `KEE-DRF-014` (stale brief) — no test
- `KEE-DRF-015` (risky change set without checkpoint) — no test
- `KEE-DRF-016` (behavior-heavy code without tests) — no test
- `KEE-DRF-017` (multiple entrypoints without resolved owner) — no test
- `KEE-DRF-018` (entrypoint-like files changed outside step) — no test
- `KEE-DRF-019` (scope expanding beyond planned subsystems) — no direct rule test
- `KEE-DRF-020` (duplicate implementation drift) — no test

`KEE-DRF-001`, `KEE-DRF-002`, `KEE-DRF-003`, `KEE-DRF-005`, `KEE-DRF-009`, `KEE-DRF-021` have integration-level test coverage in `test_drift.py`.

**`src/keel/session/awareness.py`** `_write_drift_notification()`:
- The transition-state logic (only notify on new drift codes, not repeated codes) has no dedicated test. `test_watch.py` covers the happy path through `run_awareness_pass` but not notification deduplication.

**`src/keel/bridge/gsd.py`** — the GSD bridge has zero tests.

**Empty module directories with no code:**
- `src/keel/lint/` — directory exists, contains no `.py` files
- `src/keel/git/` — directory exists, contains no `.py` files
- `src/keel/templates/` — directory exists, contains no `.py` files

These are filesystem artifacts with no imports pointing to them.

**`src/keel/cli/app.py` commands with no dedicated tests:**
- `done` command (tested indirectly in `test_drift.py` via done-gate blocking)
- `delta` command (tested only by `test_delta_accepts_summary_option` in `test_drift.py`)
- `advance` command — no test
- `replan` command (alias for `plan`) — no test
- `next` command — if present, no test found
- `check` command — no test

---

## Known Issues and UX Friction Points

### 1. Goal Silent Reset

**Problem:** Running `keel goal` without `--goal-statement` replaces the active goal with a generic default statement based only on the mode.

**File:** `src/keel/cli/app.py` lines 395–425

**Mitigation added:** Lines 351–385 have a guard: if `only_questions` is `True` (only `--unresolved-question` flags were passed, no `--goal-statement`, and a goal already exists), it appends questions to the existing goal instead of replacing it. However, any other combination of flags without `--goal-statement` still silently overwrites.

**Gap:** Passing `--scope` or `--constraint` without `--goal-statement` on an existing goal replaces the entire goal with a generic default statement. There is no test for this failure mode.

### 2. Unresolved Questions Cannot Be Resolved

**Problem:** `QuestionArtifact` items written to `keel/discovery/questions/` have no CLI command to mark them resolved or update their status. The `unresolved-questions.yaml` session file is populated by `SessionService.sync_questions()` but `sync_questions` is only called when a `QuestionArtifact` is saved — there is no `keel questions resolve` or equivalent command.

**Files:** `src/keel/session/service.py` lines 55–61, `src/keel/validators/service.py` lines 77–90 (`KEE-VAL-004`)

**Effect:** High-priority questions will continuously trigger `KEE-VAL-004` (`ValidationFinding`) with no user-accessible path to clear them short of editing YAML files directly.

### 3. False-Positive Structural Questions (research_enabled default)

**Problem:** `KeelConfig.research_enabled` defaults to `False`. The `init` command prints a dim notice when research is disabled, but `drift` detection in `_research_drift()` (`src/keel/drift/service.py` lines 503–543) and `_terminology_drift()` (lines 546–579) still fires on research and glossary artifacts if those files were previously created.

**Separately:** `KEE-DRF-017` (multiple entrypoints without resolved owner) fires on any repo with more than one entrypoint and no `"entrypoint"` or `"runtime path"` in the decisions log. On a fresh project with `multi_entry_repo` fixture, this fires immediately after `keel goal`. There is no way to suppress it other than adding a decision log entry — a low-friction dismissal path is missing.

**File:** `src/keel/drift/service.py` lines 849–868

### 4. research_enabled Hidden from Primary Workflow

**Problem:** `research_enabled: false` is the default (line 19, `src/keel/config/settings.py`) but the config key is mentioned only in the `doctor` command output and a dim `init` print. No validation finding or drift rule warns when research artifacts exist but `research_enabled` is `False`. Users who enabled research previously and then disabled it get silent inconsistency.

**Files:** `src/keel/config/settings.py:19`, `src/keel/cli/app.py:269–270`

### 5. Wrong Entrypoints Causing Spurious Drift (KEE-DRF-017)

**Problem:** `KEE-DRF-017` uses `scan.entrypoints` and checks `_entrypoint_family()` against `decision_log`. The `multi_entry_repo` fixture has three entry files (`cli.py`, `main.py`, `server.py`). Any fresh bootstrap without a prior decision triggers this rule immediately and continuously. The only suppression mechanism is manual decisions log text matching `"entrypoint"` or `"runtime path"` — no structured way to pin the canonical entrypoint exists.

**File:** `src/keel/drift/service.py` lines 849–868

**Test coverage:** `tests/test_planner_validators.py:464` (`test_multiple_entrypoints_add_ph1_step`) tests the planner behavior but not `KEE-DRF-017` suppression.

### 6. Alert Volume (MAX_ALERTS cap and ALERT_WINDOW_MINUTES)

**Problem:** `src/keel/session/alerts.py` caps alerts at `MAX_ALERTS = 25` and considers alerts active for `ALERT_WINDOW_MINUTES = 20`. With many drift rules firing simultaneously (14+ rules in `detect_drift`), the 25-alert cap is reachable in a single session. Alerts use a SHA1 key based on `"drift:{code}:{layer}:{summary}"` — identical findings from different code paths hash to the same key and upsert, but structurally different findings with the same `code` on different files produce separate alerts.

**File:** `src/keel/session/alerts.py` lines 11–12, 103

**Effect:** In a large diverged repo, nearly every alert slot fills quickly. Older actionable alerts are silently dropped (list slicing `alerts[-MAX_ALERTS:]`) with no eviction notice.

### 7. Companion Silently Fails on Process Death

**Problem:** `companion_status()` in `src/keel/session/companion.py` (lines 61–73) detects a dead PID and records `died_at`, but this is only detected when `companion status` is explicitly invoked. The background process (`src/keel/session/awareness.py:run_awareness_pass`) called inside the companion subprocess (`companion_loop`) can crash silently — the parent companion process may not propagate the exception back to the heartbeat file in all failure modes.

**The heartbeat check:** `HEARTBEAT_STALE_SECONDS = 20` means `status["fresh"]` goes `False` after 20 seconds without a heartbeat write. This is a passive detection mechanism only — no alert or notification is written when the companion goes stale.

**Files:** `src/keel/session/companion.py` lines 18–20, 61–73

**Tests:** `test_companion.py:test_companion_start_status_stop_cycle` verifies the happy path but does not test companion crash detection or stale heartbeat behavior.

### 8. Fresh Repo Shows Drifting

**Problem:** On a fresh `keel init; keel scan; keel baseline; keel goal`, running `keel drift` immediately fires `KEE-DRF-001` ("Repository changed after the latest scan") because `_changed_files_since()` uses `checkpoint_time or scan.created_at` as the baseline. Any file modification at the OS level during the bootstrap sequence (even by KEEL itself writing artifacts) registers as a post-scan change.

**File:** `src/keel/drift/service.py` lines 615–617, 625–641

**Context:** The `keel install` command works around this by calling `clear_managed_install_drift()` after install, and by recording an install-bootstrap checkpoint. But `keel init; keel scan; keel baseline; keel goal` run in sequence (as `keel_bootstrap` does in tests) does not call `keel checkpoint` afterward, so `drift` on a fresh repo still fires `KEE-DRF-001`.

**Note:** `conftest.py` comment on line 24 acknowledges this: `"""Replace the removed 'keel start' by running init + scan + baseline + goal."""`

---

## Tech Debt

### Removed Module Directories (lint, git, templates)

**Files:** `src/keel/lint/`, `src/keel/git/`, `src/keel/templates/` — empty directories with no `__init__.py` and no source files. They appear to be remnants of a prior architecture. No imports reference them.

**Fix approach:** Delete these directories. Verify no setup.py/pyproject.toml package discovery will break.

### Removed Module Artifacts in Build Tree

**File:** `build/lib/keel/` contains `align/`, `guide/`, `questions/`, `research/` modules. These were removed from `src/keel/` but remain in `build/`. Build artifacts are not committed but could confuse a developer running tests from the build tree.

**Fix approach:** Add `build/` to `.gitignore` if not already present. Confirm `pyproject.toml` `packages` setting targets only `src/`.

### Orphaned Path Properties (questions_dir, alignments_dir, research_artifacts_dir)

`KeelPaths` in `src/keel/core/paths.py` still has `questions_dir` (line 130), `alignments_dir` (line 134), and `research_artifacts_dir` (line 146). These directories are created by `paths.ensure()` (lines 188–192) and referenced by `src/keel/session/awareness.py` (lines 51–53) and `src/keel/cli/app.py` (lines 231–233).

There are no `questions`, `align`, or `research` service modules in `src/keel/`. The modules that would write artifacts to those directories were removed. The directories are created empty on every `init`. The `load_latest_model()` calls on those dirs return `None` at runtime, which is handled gracefully downstream.

**Impact:** Low — no crashes, but `keel/discovery/questions/`, `keel/discovery/alignments/`, and `keel/discovery/research/` are always empty directories. The `AlignmentArtifact` model exists (`src/keel/models/artifacts.py` lines 173–179) and is passed to `build_plan()` and `build_recovery()` where it is accepted as an optional argument.

**Fix approach:** Either restore these modules or remove the path properties and references from `awareness.py` and `app.py`. Removing requires also updating `run_validation()` which accepts `questions` as an optional arg and `detect_drift()` which accepts `questions`.

### Empty Test Section Stubs

`tests/test_services.py` lines 206–213 and 340–342 have comment stubs for "Questions tests" and "Guide tests" with no test code. These are dead sections from removed modules.

**Fix approach:** Delete the stub comment blocks.

### `_latest_bundle` vs `load_active_bundle` Duplication

`src/keel/cli/app.py` defines `_latest_bundle()` (line 226) which simply calls `_load_latest()` for each artifact type. `src/keel/session/awareness.py` defines `load_active_bundle()` (line 45) which uses `_preferred_model()` (prefers by artifact_id from session, falls back to latest). Both are used in different commands — `check` and `watch` use `load_active_bundle()`, while most CLI commands use `_latest_bundle()`. The behavior differs when session has explicit artifact IDs.

**Files:** `src/keel/cli/app.py:226–238`, `src/keel/session/awareness.py:45–58`

**Impact:** Commands like `drift` and `validate` use `_latest_bundle()` (ignores active session IDs), while `check` and `watch` use `load_active_bundle()` (honors session IDs). A session pointing to a non-latest goal or plan will be respected by `watch` but ignored by `drift`.

### Large CLI File

`src/keel/cli/app.py` is 1209 lines. It contains both command definitions and non-trivial logic (`_preinstall_checkpoint`, `_install_session_handoff`, `_install_bootstrap_paths`, `_record_install_bootstrap`). This makes the file hard to test in isolation.

---

## Test Quality Notes

### Strengths

- Unit tests for `core/` are thorough: all `KeelPaths` properties tested, `save_yaml`/`load_yaml` edge cases covered, `ensure_project` idempotency tested.
- `test_drift_dismiss.py` (71 tests) covers the dismissal persistence, expiry, alert pruning, and cooldown cycle comprehensively.
- `test_session.py` (73 tests) covers `SessionService` CRUD, decision deduplication, question sync, checkpoint kinds, alert helpers, and brief writing.
- `test_planner_validators.py` (53 tests) covers all `GoalMode` combinations for `build_plan()` and all `KEE-VAL-*` code severity escalations.
- Integration tests use real fixture repos (`messy_repo`, `multi_entry_repo`) which catches CLI wiring regressions.

### Weaknesses

- No test for `build_statusline_text()` — the function that drives the GSD/Claude statusline integration.
- No test for `consume_pending_notification()` — the one-shot drift notification mechanism.
- No tests for 14 of 21 KEE-DRF drift rules at unit level.
- No tests for the GSD bridge (`src/keel/bridge/gsd.py`).
- `test_scan.py` has a single test — the most complex module (`src/keel/discovery/scanner.py`, 434 lines) is undertested.
- Several CLI commands (`advance`, `delta` detail, `done`, `replan`, `check`) have only thin or no test coverage.
- Integration tests use `time.sleep(1)` for file-mtime ordering — these are slow and fragile on loaded CI systems.

---

*Quality analysis: 2026-03-25*
