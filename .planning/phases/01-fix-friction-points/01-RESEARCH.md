# Phase 1: Fix Friction Points - Research

**Researched:** 2026-03-25
**Domain:** Python CLI service layer — goal persistence, drift detection, plan entrypoint selection, GSD bridge parsing
**Confidence:** HIGH (all findings are from direct source code inspection of the live codebase)

---

## Summary

All four requirements in this phase target well-isolated bugs or missing features in existing service modules. The code is already partially correct in some areas, and the changes required are surgical — no architectural redesign is needed. The partial fix for REQ-101 already exists in `app.py` but has a latent call-site bug. REQ-103 requires a single guard in `detect_drift()`. REQ-102 requires extending one scoring function in `planner/service.py`. REQ-104 requires converting silent `return {}` paths in `gsd.py` into logged warning paths.

The test infrastructure is mature (pytest, 343 passing tests, `tmp_path`/CliRunner patterns), and all four fixes can be covered by new unit or CLI-level tests following existing patterns.

**Primary recommendation:** Fix each requirement in its designated module with no cross-module rework. Add one test per requirement using the established `keel_bootstrap` + `CliRunner` or direct service-layer patterns.

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| REQ-101 | `keel goal --unresolved-question` must append to existing goal, not silently overwrite | Partial fix exists at app.py:350-385. A latent missing-argument bug at line 360 will cause a runtime TypeError. The guard only covers the `only_questions` case — other partial invocations still silently overwrite. |
| REQ-102 | Plan entrypoint selection must weight goal keywords and git-hot files | `_related_paths()` in `planner/service.py` uses only `scan.entrypoints[:2] + scan.modules[:3] + scan.configs[:2]`, with no goal-keyword or git-recency weighting. |
| REQ-103 | Suppress alerts that fire before first checkpoint exists | `detect_drift()` computes `changed_files` using `checkpoint_time or scan.created_at` as the baseline. When no checkpoint exists, every file touched since scan fires KEE-DRF-001. No guard exists to suppress this for a fresh session. |
| REQ-104 | GSD bridge should log parse warnings instead of silently returning empty dicts | `read_gsd_state()` and `read_gsd_roadmap()` return `{}` on regex miss with no log output. `sync_goal_from_gsd()` returns `None` with no indication of why. No warnings are written anywhere. |
</phase_requirements>

---

## Project Constraints (from CLAUDE.md)

- Keep KEEL local-first. Local files and git state are the source of truth.
- Preserve confidence label distinctions: `repo-fact`, `external-guidance`, `inferred`, `unresolved`.
- Do not present heuristics as proof.
- Prefer small finished vertical slices over broad scaffolding.
- Update `WORKLOG.md`, `TASKS.md`, and `ARCHITECTURE.md` after meaningful slices.
- Refresh `.keel/session/current-brief.md` whenever the active goal, phase, next step, blockers, or invariants change.
- Treat drift detection as a core product behavior, not an optional report.
- Anti-drift: one active goal locked at a time; changed files must map to active goal.

---

## Standard Stack

### Core (already in use — no new dependencies)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| typer | existing | CLI framework | Used throughout `app.py` |
| pydantic | existing | Model validation | All artifacts use Pydantic BaseModel |
| pytest | existing | Test runner | 343 tests already passing |
| subprocess | stdlib | git log / git diff for hot-file detection | Already used in drift/service.py |

### No new packages required
All four fixes are internal to the existing Python service layer. No new pip dependencies.

---

## Architecture Patterns

### Recommended Project Structure (no changes)
The module layout is unchanged. Edits touch these files only:
```
src/keel/
├── cli/app.py               # REQ-101: goal command guard
├── goal/service.py          # REQ-101: build_goal() (no change needed — already correct)
├── drift/service.py         # REQ-103: detect_drift() first-checkpoint guard
├── planner/service.py       # REQ-102: _related_paths() keyword+git-hot scoring
└── bridge/gsd.py            # REQ-104: parse warning logging

tests/
└── test_bridge.py           # NEW: covers REQ-104 (currently zero bridge tests)
```

---

## REQ-101: Goal Silent Reset — Detailed Findings

### Current State

The partial fix at `app.py:350-385` correctly handles one specific case: when `--unresolved-question` is the **only** flag and a goal already exists, it appends rather than replacing.

**The guard condition (lines 352-358):**
```python
only_questions = (
    goal_statement is None
    and not scope and not out_of_scope and not constraint
    and not success_criterion and not risk and not assumption
    and unresolved_question
    and session.active_goal_id
)
```

This guard is correct and was deliberately added. The `only_questions` branch correctly:
1. Loads the existing goal via `load_model_by_artifact_id`
2. Appends new questions to existing ones
3. Calls `build_goal()` preserving all other fields
4. Saves and updates `session.active_goal_id`

**Latent bug at line 360:** The call is:
```python
existing = load_model_by_artifact_id(paths.goals_dir, session.active_goal_id)
```
The function signature (confirmed at runtime) is:
```python
def load_model_by_artifact_id(directory, artifact_id, model_type) -> Optional[ModelT]
```
This call is missing the third argument `GoalArtifact`. It will raise `TypeError` at runtime when the `only_questions` branch is executed. This is a real bug that must be fixed.

**Correct call:**
```python
from keel.models import GoalArtifact
existing = load_model_by_artifact_id(paths.goals_dir, session.active_goal_id, GoalArtifact)
```

**Uncovered case (REQ-101 scope):** When any other flag is passed without `--goal-statement` (e.g., `--goal-mode fix`, `--scope src/foo`), `build_goal()` is called with `goal_statement=None`. This resolves to the mode-specific default string, overwriting the existing goal silently. The CONCERNS.md documents this at lines 78-81.

**Fix for REQ-101:** The fix should:
1. Repair the missing `GoalArtifact` argument at line 360.
2. Broaden the guard to protect against partial-flag invocations that omit `--goal-statement`. The pattern: if `session.active_goal_id` is set and `goal_statement is None` and **any** non-question flag is passed, default `goal_statement` from the existing active goal before calling `build_goal()`. This preserves user intent without requiring `--force`.

The `build_goal()` function in `goal/service.py` does **not** need changes — its behavior is correct as called. The issue is entirely in how `app.py` constructs the arguments.

### Edge Cases

- `session.active_goal_id` is set but the file is missing (deleted manually): `load_model_by_artifact_id` returns `None`. The existing branch handles this gracefully (falls through to create a new goal). Acceptable.
- Goal exists, user passes `--goal-mode fix` without `--goal-statement`: Currently replaces. After fix, should inherit existing goal statement.
- GSD automated call with no arguments (`keel goal`): After fix, this becomes a no-op that preserves the existing goal.

---

## REQ-103: Pre-Checkpoint Alert Suppression — Detailed Findings

### Current State

In `detect_drift()` at `service.py:615-617`:
```python
checkpoint_time = _latest_checkpoint_time(paths)
since = checkpoint_time or (scan.created_at if scan else now)
changed_files = _changed_files_since(paths.root, since)
```

When no checkpoint exists (`checkpoint_time is None`), `since` falls back to `scan.created_at`. During a fresh bootstrap (`init` + `scan` + `baseline` + `goal`), KEEL itself writes artifact files to `.keel/` during the bootstrap sequence. However, the `_changed_files_since` function filters out `.keel/` and `keel/` directories (line 69). So KEEL's own writes are excluded.

**The actual trigger:** In a real repo session, between `keel scan` and the first `keel checkpoint`, the developer modifies files (that is the point of working). These show up as `changed_files`, which triggers `KEE-DRF-001` on every `keel drift` call and every companion poll cycle. This is semantically correct but noisy for a fresh session where no checkpoint has ever been recorded.

**REQ-103 scope:** Suppress alerts that fire **before the first checkpoint exists**. The REQUIREMENTS.md says "suppress alerts that fire before first checkpoint exists." This is about `KEE-DRF-001` specifically — and potentially the entire `detect_drift()` result for pre-checkpoint sessions.

**Option A — Full early return:**
```python
checkpoint_time = _latest_checkpoint_time(paths)
if checkpoint_time is None:
    return DriftArtifact(
        artifact_id=f"drift-{now.strftime('%Y%m%d-%H%M%S')}",
        created_at=now,
        repo_root=".",
        mode=mode,
        status="clean",
        findings=[],
        clusters=[],
    )
```
This suppresses all alerts before the first checkpoint. Risk: hides real alerts like `KEE-DRF-003` (no delta for behavior-change goal), which are valid even before a checkpoint.

**Option B — Targeted suppression:**
Guard only `KEE-DRF-001` and `KEE-DRF-015` (the ones driven by `changed_files` with no checkpoint anchor) when `checkpoint_time is None`:
```python
if changed_files and checkpoint_time is not None:
    findings.append(DriftFinding(code="KEE-DRF-001", ...))
```
This preserves goal-mode and spec-drift alerts which are valid regardless of checkpoint state.

**Recommendation:** Option B is safer. REQ-103's literal text is "suppress alerts that fire before first checkpoint exists," and the friction point (#6) was specifically about alert volume from `changed_files` rules. Goal-mode violations (`KEE-DRF-003`, `KEE-DRF-007`) should still fire since they are not about file changes.

**Exact lines to guard with `checkpoint_time is not None`:**
- Line 625: `KEE-DRF-001` (Repository changed after latest scan) — guard with `checkpoint_time is not None`
- Line 698: `KEE-DRF-015` (Risky change set without checkpoint) — this is already conditioned on `checkpoint_time is None`, but only fires for large or risky sets. This one can stay as-is or be suppressed entirely before first checkpoint.

**`_latest_checkpoint_time` behavior:** It returns `None` if `checkpoints.yaml` is empty or absent. It skips `install-bootstrap` kind checkpoints (line 107). The first user-created checkpoint is any other kind.

---

## REQ-102: Entrypoint Selection Weighting — Detailed Findings

### Current State

`_related_paths()` in `planner/service.py:19-27`:
```python
def _related_paths(scan: Optional[ScanArtifact]) -> list[str]:
    paths: list[str] = []
    if not scan:
        return paths
    for item in scan.entrypoints[:2] + scan.modules[:3] + scan.configs[:2]:
        for path in item.paths:
            if path not in paths:
                paths.append(path)
    return paths[:6]
```

This function takes only `scan`. The `goal` object is available in every calling context but is not passed here. The function is called from `build_plan()`.

**Current scoring:** Pure position in the scan artifact. The scan returns entrypoints in filesystem walk order (sorted alphabetically), not by relevance to the goal.

**Goal keyword weighting:** The `GoalArtifact` has:
- `goal_statement: str`
- `scope: list[str]` — already path hints from the user
- `success_criteria: list[str]`

If `goal.scope` is non-empty, those paths are already used downstream in `_build_phase2()` (line 124: `scope_paths = goal.scope if goal and goal.scope else related_paths`). The gap is in Phase 1 (`_build_phase1_steps()`), which always uses `related_paths` from `_related_paths(scan)`.

**Git-hot files:** "Git-hot" means files changed most frequently in recent git history. The `subprocess` module is already imported in `drift/service.py` for `_git_has_changes()`. A lightweight implementation:
```python
import subprocess

def _git_hot_files(root: Path, n: int = 10) -> list[str]:
    try:
        result = subprocess.run(
            ["git", "log", "--name-only", "--pretty=format:", "-20"],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
        counts: Counter[str] = Counter()
        for line in result.stdout.splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                counts[line] += 1
        return [path for path, _ in counts.most_common(n)]
    except OSError:
        return []
```

**Recommended approach for REQ-102:**
1. Add `goal: Optional[GoalArtifact] = None` parameter to `_related_paths()`.
2. If `goal.scope` is non-empty, prepend those paths (they are the most explicit signal).
3. Compute `_git_hot_files()` from `paths.root` and intersect with the scan's entrypoints and modules.
4. Score each candidate: +2 for appearing in `goal.scope`, +1 for appearing in git-hot list, +1 for keyword match against `goal.goal_statement` (lowercased path stem vs lowercased statement tokens).
5. Return top 6 by score.

**Calling context:** `build_plan()` receives both `scan` and `goal`. The call to `_related_paths(scan)` at line 23 should be updated to `_related_paths(scan, goal=goal, root=paths.root)` or similar.

**Risk:** `_git_hot_files()` requires a git repo. Must handle `OSError` and empty output gracefully. The function should return `[]` on any failure, which makes the weighting fall back to scan order.

---

## REQ-104: GSD Bridge Parse Warnings — Detailed Findings

### Current State

`read_gsd_state()` in `bridge/gsd.py:19-47`:
- Returns `{}` when `STATE.md` doesn't exist (line 27: silent return)
- Returns `{}` when no regex matches (falls through with partial result dict)
- When `current_phase` key is absent, `sync_goal_from_gsd()` returns `None` silently

`read_gsd_roadmap()` in `bridge/gsd.py:50-73`:
- Returns `{}` when `ROADMAP.md` doesn't exist (line 56: silent return)
- Returns `{"phases": {}}` when no headers or table rows match (empty `phases` dict)
- No logging at any level anywhere in the file

**Where warnings should go:** The CONCERNS.md recommends logging to stderr or `.keel/session/companion.log`. The existing codebase does not have a centralized logger — other modules use `console.print()` (Rich) at the CLI layer or bare file writes. The bridge module is imported both from the CLI and potentially from automation scripts, so `stderr` is the correct target for structured warnings.

**Recommended implementation:**

Add a `warnings: list[str]` field to the return dicts from `read_gsd_state()` and `read_gsd_roadmap()`, and also write to `sys.stderr` using a simple `_warn()` helper:

```python
import sys

def _warn(msg: str) -> None:
    print(f"[keel:bridge:gsd] WARNING: {msg}", file=sys.stderr)
```

**Specific warning sites:**
1. `read_gsd_state()`: warn when `STATE.md` is present but `current_phase` is not found (regex miss, not file-absent). File absent is not a warning — it means GSD is not in use.
2. `read_gsd_state()`: warn when `STATE.md` is present but completely empty or unreadable.
3. `read_gsd_roadmap()`: warn when `ROADMAP.md` is present but no phase entries were parsed.
4. `sync_goal_from_gsd()`: warn when `current_phase` was found but no matching entry exists in the roadmap phases dict.

**What NOT to warn on:** When `.planning/` does not exist — this means GSD is not present, not a parse error.

**Test gap:** `src/keel/bridge/gsd.py` has zero tests (confirmed in QUALITY.md line 144). A new `tests/test_bridge.py` must be created for REQ-104 coverage. The existing test patterns use `tmp_path` to write fixture files and then call the function directly — no CliRunner needed for the bridge.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead |
|---------|-------------|-------------|
| Git file frequency analysis | Custom git log parser | `subprocess.run(["git", "log", "--name-only", ...])` + `Counter` — lightweight, already the pattern in `drift/service.py` |
| Warning logging | New logging framework | `sys.stderr` print — no new dependency, consistent with the module's no-logger architecture |
| Goal field merging | New merge service | Directly construct `build_goal(...)` with merged fields — already what the `only_questions` branch does |

---

## Common Pitfalls

### Pitfall 1: load_model_by_artifact_id Missing model_type Argument
**What goes wrong:** `load_model_by_artifact_id(paths.goals_dir, session.active_goal_id)` raises `TypeError` at runtime because the third argument is required. The existing code at app.py line 360 is missing `GoalArtifact`.
**Why it happens:** The function was likely called with a different overload or default at an earlier version, and the argument was dropped during refactor.
**How to avoid:** Always pass all three arguments. The function is typed — mypy would catch this.
**Warning signs:** The `only_questions` branch is never exercised in the current test suite, so this bug is masked by test coverage gaps.

### Pitfall 2: Broadening the Goal Guard Too Aggressively
**What goes wrong:** If the guard in `app.py` defaults goal_statement from the existing goal for ALL partial invocations, a user who deliberately wants to reset the goal with just `--goal-mode` loses that ability.
**How to avoid:** Only inherit existing `goal_statement` when `goal_statement is None` and `session.active_goal_id` is set. The mode can still change independently.

### Pitfall 3: Suppressing All Drift Before First Checkpoint (Option A for REQ-103)
**What goes wrong:** Goal-mode violations like `KEE-DRF-003` (behavior-change work with no delta) would be silenced on a fresh session, which is exactly when they are most actionable.
**How to avoid:** Guard only the file-change-driven rules (`KEE-DRF-001`, and optionally `KEE-DRF-015`). Leave goal-mode and spec-drift rules unguarded.

### Pitfall 4: Git-Hot File Detection in Non-Git Repos
**What goes wrong:** `subprocess.run(["git", "log", ...])` returns non-zero exit code or raises `OSError` in a non-git directory.
**How to avoid:** Always `check=False` and wrap in try/except OSError. Return `[]` on failure. `_git_has_changes()` in `drift/service.py` already demonstrates this pattern.

### Pitfall 5: Bridge Warnings Generating Noise in Repos Without GSD
**What goes wrong:** If the bridge warns when `.planning/` is absent, it generates noise in every non-GSD repo.
**How to avoid:** Only warn when the file EXISTS but parsing fails. Absent `.planning/` = GSD not present = silent. Present file with no regex matches = configuration or format issue = warn.

---

## Code Examples

### REQ-101: Fixing the load_model_by_artifact_id call

Current (broken):
```python
# app.py line 360
existing = load_model_by_artifact_id(paths.goals_dir, session.active_goal_id)
```

Fixed:
```python
from keel.models import GoalArtifact
existing = load_model_by_artifact_id(paths.goals_dir, session.active_goal_id, GoalArtifact)
```

`GoalArtifact` is already imported at the top of `app.py` via `from keel.models import GoalArtifact`.

### REQ-101: Broadening the guard to cover non-question partial invocations

Add before the main `build_goal()` call (after the `only_questions` branch returns):
```python
# If an active goal exists and no goal_statement was given,
# inherit the existing goal_statement rather than silently applying a default.
if goal_statement is None and session.active_goal_id:
    existing_for_statement = load_model_by_artifact_id(
        paths.goals_dir, session.active_goal_id, GoalArtifact
    )
    if existing_for_statement:
        goal_statement = existing_for_statement.goal_statement
```

### REQ-103: Guarding KEE-DRF-001 with checkpoint presence

Current (lines 625-641):
```python
if changed_files:
    findings.append(DriftFinding(code="KEE-DRF-001", ...))
```

Fixed:
```python
if changed_files and checkpoint_time is not None:
    findings.append(DriftFinding(code="KEE-DRF-001", ...))
```

### REQ-104: Adding parse warnings to read_gsd_state

```python
import sys

def _warn(msg: str) -> None:
    print(f"[keel:bridge:gsd] WARNING: {msg}", file=sys.stderr)

def read_gsd_state(repo_root: Path) -> dict:
    planning = _planning_dir(repo_root)
    if not planning:
        return {}
    state_file = planning / "STATE.md"
    if not state_file.exists():
        return {}

    text = state_file.read_text(encoding="utf-8", errors="ignore")
    result: dict = {"source": "gsd"}

    m = re.search(r"[Cc]urrent [Pp]hase[:\s]+(\d[\d.]*)", text)
    if m:
        result["current_phase"] = m.group(1)
    else:
        _warn(f"STATE.md found but 'Current Phase' not parsed: {state_file}")

    m = re.search(r"[Cc]urrent [Pp]osition[:\s]+([^\n]+)", text)
    if m:
        result["current_position"] = m.group(1).strip()

    blockers = re.findall(r"[-*]\s+(blocker|concern)[:\s]+([^\n]+)", text, re.IGNORECASE)
    if blockers:
        result["blockers"] = [b[1].strip() for b in blockers]

    return result
```

### REQ-102: _related_paths with goal keywords and git-hot weighting

```python
import subprocess
from collections import Counter

def _git_hot_files(root: Path, n: int = 10) -> list[str]:
    try:
        result = subprocess.run(
            ["git", "log", "--name-only", "--pretty=format:", "-20"],
            cwd=root, capture_output=True, text=True, check=False,
        )
        counts: Counter[str] = Counter()
        for line in result.stdout.splitlines():
            line = line.strip()
            if line:
                counts[line] += 1
        return [path for path, _ in counts.most_common(n)]
    except OSError:
        return []

def _related_paths(
    scan: Optional[ScanArtifact],
    goal: Optional[GoalArtifact] = None,
    root: Optional[Path] = None,
) -> list[str]:
    if not scan:
        return []
    candidates: list[str] = []
    for item in scan.entrypoints[:2] + scan.modules[:3] + scan.configs[:2]:
        for path in item.paths:
            if path not in candidates:
                candidates.append(path)

    if not goal and not root:
        return candidates[:6]

    hot = set(_git_hot_files(root)) if root else set()
    scope_set = set(goal.scope) if goal and goal.scope else set()
    goal_tokens = set(
        (goal.goal_statement or "").lower().split()
    ) if goal else set()

    def _score(path: str) -> int:
        score = 0
        if path in scope_set:
            score += 2
        if path in hot:
            score += 1
        stem = Path(path).stem.lower()
        if any(tok in stem for tok in goal_tokens if len(tok) > 3):
            score += 1
        return score

    # Also add scope paths not already in candidates
    for path in (goal.scope if goal and goal.scope else []):
        if path not in candidates:
            candidates.append(path)

    candidates.sort(key=_score, reverse=True)
    return candidates[:6]
```

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (no version pinned in pyproject.toml — current install confirmed working) |
| Config file | `pyproject.toml` at repo root |
| Quick run command | `python3 -m pytest tests/ -q --tb=short` |
| Full suite command | `python3 -m pytest tests/ -q` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| REQ-101 | `--unresolved-question` appends, does not overwrite | CLI integration | `python3 -m pytest tests/test_services.py -k goal -x` | Partial — needs new test case |
| REQ-101 | Missing `model_type` arg in `only_questions` branch | Unit | Same as above | No — new test needed |
| REQ-101 | Partial flag invocation inherits existing goal_statement | CLI integration | `python3 -m pytest tests/test_services.py -k goal -x` | No — new test needed |
| REQ-103 | No KEE-DRF-001 when no checkpoint exists | Unit | `python3 -m pytest tests/test_drift.py -x` | Partial — new assertion in existing test |
| REQ-102 | Entrypoints weighted by goal scope paths | Unit | `python3 -m pytest tests/test_services.py -k plan -x` | No — new test needed |
| REQ-102 | Entrypoints weighted by git-hot files | Unit | Same | No — new test needed |
| REQ-104 | Parse warning on STATE.md present but unparseable | Unit | `python3 -m pytest tests/test_bridge.py -x` | No — file does not exist |
| REQ-104 | No warning when .planning/ absent | Unit | Same | No — file does not exist |

### Wave 0 Gaps
- [ ] `tests/test_bridge.py` — covers REQ-104 (bridge module has zero tests)
- [ ] REQ-101 test cases in `tests/test_services.py` — test the `only_questions` path with GoalArtifact argument, and the partial-flag inheritance path
- [ ] REQ-102 test cases in `tests/test_services.py` — test `_related_paths()` with goal and root arguments
- [ ] REQ-103 assertion in `tests/test_drift.py` — verify KEE-DRF-001 absent when `checkpoint_time is None`

---

## Open Questions

1. **REQ-103: Should KEE-DRF-015 also be suppressed before first checkpoint?**
   - What we know: `KEE-DRF-015` is already conditioned on `checkpoint_time is None` (it fires when no checkpoint AND risky changes detected). It is arguably the most important alert in the pre-checkpoint state, since it tells the user to checkpoint before a broad change set.
   - What's unclear: Does suppressing it before first checkpoint mean users never get warned to checkpoint at all?
   - Recommendation: Keep `KEE-DRF-015` active. Only suppress `KEE-DRF-001` (pure noise) before first checkpoint.

2. **REQ-102: Should goal-keyword weighting apply to Phase 1 plan steps only, or all phases?**
   - What we know: `_related_paths()` feeds Phase 1 and also fallback paths in Phase 2 and Phase 3. The goal's `scope` field already dominates Phase 2+ via `scope_paths = goal.scope if goal and goal.scope else related_paths`.
   - What's unclear: Whether Phase 2 plan steps should also pick up git-hot weighting.
   - Recommendation: Apply to all phases via `_related_paths()`. The `goal.scope` already provides explicit user intent for Phase 2+; git-hot weighting is a fallback signal that is harmless in Phase 2 since `goal.scope` takes precedence there.

3. **REQ-101: Should `--goal-mode` without `--goal-statement` also inherit the existing mode or always override?**
   - What we know: The user explicitly passes `--goal-mode`; inheriting the mode would silently ignore their flag.
   - Recommendation: Always use the passed `--goal-mode`. Only inherit `goal_statement` when it is absent.

---

## Environment Availability

Step 2.6: All dependencies are stdlib or already installed. No external services required.

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| python3 | All source | yes | 3.x (confirmed) | — |
| pytest | Test suite | yes | confirmed (343 tests run) | — |
| git | REQ-102 git-hot | yes | git is present (repo is git-managed) | Return [] from _git_hot_files |
| subprocess | REQ-102 | stdlib | — | — |
| sys.stderr | REQ-104 | stdlib | — | — |

---

## Sources

### Primary (HIGH confidence)
All findings are direct source code inspection — no external sources required for this phase.

| File | Lines Inspected | Finding |
|------|----------------|---------|
| `src/keel/cli/app.py` | 334-426 | REQ-101 partial fix, latent TypeError at line 360 |
| `src/keel/goal/service.py` | 1-48 | build_goal() signature — no changes needed |
| `src/keel/drift/service.py` | 582-641 | detect_drift() — KEE-DRF-001 trigger, checkpoint guard location |
| `src/keel/planner/service.py` | 19-27, 34-109 | _related_paths() — current scoring, no goal param |
| `src/keel/bridge/gsd.py` | 1-109 | read_gsd_state(), read_gsd_roadmap() — zero warnings |
| `src/keel/core/artifacts.py` | 57-61 | load_model_by_artifact_id signature — 3 required args |
| `.planning/codebase/CONCERNS.md` | all | CONCERNS audit confirming all 4 issues |
| `.planning/codebase/QUALITY.md` | all | Test coverage gaps — bridge has 0 tests |
| `tests/conftest.py` | all | keel_bootstrap() pattern |
| `tests/test_services.py` | 1-60 | Factory patterns for unit tests |

---

## Metadata

**Confidence breakdown:**
- REQ-101 fix: HIGH — root cause is a verifiable missing argument at a specific line
- REQ-103 fix: HIGH — the guard condition is clear; only the scope question (which rules) is a judgment call
- REQ-102 fix: HIGH for scoring approach; MEDIUM for git-hot implementation detail (subprocess behavior in edge cases)
- REQ-104 fix: HIGH — file structure and fix location are clear

**Research date:** 2026-03-25
**Valid until:** Stable — these findings are tied to specific line numbers in the current codebase. Valid until code changes.
