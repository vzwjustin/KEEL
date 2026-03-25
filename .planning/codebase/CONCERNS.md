# Codebase Concerns

**Analysis Date:** 2026-03-25

---

## GSD Bridge: Fragile Regex Parsing of .planning/ State

**Area:** `src/keel/bridge/gsd.py` — `read_gsd_state()`, `read_gsd_roadmap()`

- Issue: GSD state is parsed with ad hoc regexes against free-form Markdown (`STATE.md`, `ROADMAP.md`). Any formatting deviation in those files silently returns empty dicts. `sync_goal_from_gsd()` returns `None` without indicating why — the `keel goal` command falls through to a generic default goal rather than surfacing a parse miss.
- Files: `src/keel/bridge/gsd.py` lines 19–88, `src/keel/cli/app.py` lines 388–393
- Impact: GSD workflows that call `keel goal` automatically will silently get the wrong goal statement if `STATE.md` or `ROADMAP.md` are formatted differently than the expected patterns. No error is raised, no log entry is written.
- Fix approach: Add a `parse_warnings` list to the return dict from `read_gsd_state()`. Log a warning to stderr (or to `.keel/session/companion.log`) when expected keys are absent. Consider a structured format (YAML front-matter in STATE.md) rather than free-form regex matching.

---

## GSD Bridge: write_keel_brief_to_planning Has No Error Feedback

**Area:** `src/keel/bridge/gsd.py` — `write_keel_brief_to_planning()`

- Issue: The function silently does nothing if `.planning/` does not exist (returns `False`). The call site in `src/keel/cli/app.py` (`_refresh_brief`) never checks the return value or logs a failure. GSD agents consuming `.planning/KEEL-STATUS.md` will read stale content without knowing the write was skipped.
- Files: `src/keel/bridge/gsd.py` lines 91–103, `src/keel/cli/app.py` lines 125–133
- Impact: If a GSD workflow triggers a KEEL command and then immediately reads `KEEL-STATUS.md`, it may act on stale or absent status data.
- Fix approach: Log at `DEBUG` level when the write is skipped. At minimum, update `_refresh_brief` in `app.py` to emit a `[dim]` console notice when the write is skipped in a GSD-managed repo.

---

## Companion: Silent Death Not Surfaced to User

**Area:** `src/keel/session/companion.py` — `start_companion()`, `companion_status()`; `src/keel/cli/app.py` `watch` command

- Issue: When the companion process dies (OS kills the PID, Python crash, etc.), `companion_status()` detects the death and marks `died_at` in `.keel/session/companion.yaml`. However nothing proactively notifies the active session — no pending notification is written, no alert is appended to `alerts.yaml`. The next `keel status` call will show `fresh: no`, but GSD automated calls that do not surface `keel status` output will never learn the companion is gone.
- Current evidence: `.keel/session/companion.yaml` has `running: true` and a stale heartbeat from the last watch cycle. `HEARTBEAT_STALE_SECONDS = 20` means the companion is considered dead after 20 seconds of silence, but no hook fires on that transition.
- Files: `src/keel/session/companion.py` lines 61–73, `src/keel/session/awareness.py` lines 141–194
- Impact: The companion is the only source of proactive drift notifications via `pending-notification.yaml`. If the companion dies silently, drift accumulates without any hook interrupting the GSD workflow.
- Fix approach: In `companion_status()`, when `is_dead` is set to `True`, write a `pending-notification.yaml` entry with message "companion process died — drift detection paused". This reuses the existing hook delivery path.

---

## Companion: Single Log File Rotation Only Keeps One Backup

**Area:** `src/keel/session/companion.py` — `_rotate_companion_log()`

- Issue: Log rotation keeps exactly one backup (`companion.log.1`). The rotate threshold is 512 KB. Existing `.log.1` is deleted unconditionally before renaming. In a busy session, diagnostic history is lost after the first rotation.
- Files: `src/keel/session/companion.py` lines 86–97
- Impact: Diagnosing a companion crash from before the last rotation is impossible. This was already observed — `companion.log` shows only 4 watch update entries with no history of why prior cycles ended.
- Fix approach: Rotate to up to 3 numbered backups (`.log.1`, `.log.2`, `.log.3`) or reduce the 512 KB threshold.

---

## Hook Integration: CLAUDE_PROJECT_DIR Is the Only Repo Resolution Strategy

**Area:** `.claude/hooks/keel_notify.py` line 16, `.claude/hooks/keel_scope_guard.py` lines 44, 87, 129

- Issue: Both hooks resolve the repo root by reading `CLAUDE_PROJECT_DIR` from the environment, falling back to `Path.cwd()`. When GSD workflows spawn sub-agents or run keel hooks from a different working directory, `Path.cwd()` may not be the repo root. This would cause the hook to open the wrong `.keel/` directory, silently pass all scope checks (no session loaded), and never deliver notifications.
- Files: `.claude/hooks/keel_notify.py` lines 15–17, `.claude/hooks/keel_scope_guard.py` lines 43–47, 86–90, 128–131
- Impact: In multi-repo or sub-agent scenarios where GSD invokes keel commands, the hook may operate on the wrong repo or silently no-op.
- Fix approach: Walk upward from `Path.cwd()` to find the nearest `.keel/` directory as a third resolution strategy. Document the fallback chain in a comment.

---

## Hook Integration: keel_scope_guard Blocks Only Write and Edit, Not Bash

**Area:** `.claude/hooks/keel_scope_guard.py` lines 116–118

- Issue: The scope guard only intercepts `Write` and `Edit` tool calls. `Bash` commands that write files (e.g., `cat > file`, `tee`, `cp`, `mv`, shell redirects) are not checked. An agent can bypass the scope guard entirely by using Bash to write out-of-scope files.
- Files: `.claude/hooks/keel_scope_guard.py` lines 116–118
- Impact: The hard-stop guarantee is incomplete. Any GSD phase that uses Bash for file generation will not be checked against the active plan step.
- Fix approach: Add `Bash` to the guarded tool list and attempt to extract the target file path from `tool_input["command"]` using a lightweight heuristic (look for redirect targets `> path`, `tee path`, `cp src dst`). Block if a recognizable out-of-scope path is found; allow if extraction fails (prefer false-negatives over blocking legitimate shell use).

---

## Goal Silent Reset: Running `keel goal` Without --goal-statement Overwrites the Active Goal

**Area:** `src/keel/cli/app.py` — `goal()` command, lines 334–425

- Issue: The guard at lines 350–385 only protects against overwrite when `unresolved_question` is the **only** flag passed and a goal already exists. Any other partial invocation — such as `keel goal --goal-mode ship_mvp` without `--goal-statement` — will call `build_goal()` with `goal_statement=None`, which resolves to a generic default string for that mode. The previous goal is permanently replaced and `session.active_goal_id` is updated to the new artifact ID. The old goal file remains on disk but is orphaned from the session.
- Files: `src/keel/cli/app.py` lines 334–425, `src/keel/goal/service.py` lines 9–48
- Impact: This was called out as a real friction point (session 2026-03-25). GSD workflows that call `keel goal` to add context (e.g., add a question) without all original parameters will silently reset the goal statement. Recovery requires manual YAML inspection.
- Fix approach: Before calling `build_goal()`, if `session.active_goal_id` is set and `goal_statement is None`, require an explicit `--force` flag or prompt the user for confirmation. Alternatively, default `goal_mode` and `goal_statement` from the existing active goal when any flag is omitted.

---

## Question Resolution: No Workflow to Mark a Question Answered

**Area:** `src/keel/session/service.py` — `sync_questions()`, `load_unresolved_questions()`; `src/keel/validators/service.py` lines 77–90

- Issue: Questions are written to `keel/discovery/questions/` and tracked by ID in `session.unresolved_question_ids`. There is no CLI command to mark a question as resolved. `sync_questions()` replaces the entire question set; if the caller passes a subset, resolved questions reappear. The only way to remove a question is to rebuild questions from scratch (rerun `keel start` or `keel questions`).
- Files: `src/keel/session/service.py` lines 51–61, `src/keel/cli/app.py` (no `questions resolve` command present)
- Impact: High-priority unresolved questions continuously trigger `KEE-DRF-005` and `KEE-VAL-004` drift and validation findings. Because there is no resolution path, these alerts are permanent for the session. This directly contributes to alert volume fatigue (friction point 6).
- Fix approach: Add `keel questions resolve --id <question_id>` that sets a `resolved_at` timestamp on the question artifact and removes it from `unresolved-questions.yaml`. `sync_questions()` should skip questions with `resolved_at` set.

---

## False-Positive Suppression: Dismissals Are Timed, Not Semantic

**Area:** `src/keel/drift/service.py` — `dismiss_drift_codes()` lines 325–358; `src/keel/session/alerts.py` lines 50–103

- Issue: Drift code dismissals expire after a fixed window (default 30 minutes). After expiry, the same finding re-fires even if the underlying situation has not changed (e.g., KEE-DRF-001 fires every session because the repo always has uncommitted changes while the companion runs). There is no semantic suppression tied to a specific resolved state or delta.
- Files: `src/keel/drift/service.py` lines 325–358, `src/keel/session/awareness.py` `_write_drift_notification()` lines 141–194
- Impact: The notification system correctly uses a transition-based guard (`_write_drift_notification` only fires on new codes), but dismissals reset after 30 minutes, guaranteeing repeated re-presentation of known-acceptable warnings. This was identified as a real friction point (session 2026-03-25).
- Fix approach: Add a `keel dismiss --code <code> --until-checkpoint` option that suppresses the code until the next `keel checkpoint` call, rather than a fixed time window. Implement by writing a `until_kind: checkpoint` field in the dismissal record and checking for a newer checkpoint timestamp before re-firing.

---

## Research Toggle: Off by Default, No Visible State in Brief

**Area:** `src/keel/config/settings.py` line 19; `src/keel/cli/app.py` lines 269–271

- Issue: `research_enabled: false` is the default in `.keel/config.yaml`. When research is disabled, `run_awareness_pass()` passes `research=None` to all downstream calls. The current brief shows "offline or no active research" with no indication of whether this is intentional config or an error. The `keel init` output prints a `[dim]` notice, but `keel status` does not.
- Files: `src/keel/config/settings.py` line 19, `.keel/config.yaml` line 2, `src/keel/cli/app.py` lines 269–271, `src/keel/session/service.py` lines 133–135
- Impact: New sessions default to no research. When GSD calls `keel` commands, the research state is invisible unless the user runs `keel init` or checks config manually. Users may incorrectly assume research failed rather than being deliberately disabled (friction point 4).
- Fix approach: Add `research_enabled: <true/false>` to the `current-brief.md` template in `SessionService.write_current_brief()`. Expose it in `keel status` output.

---

## Wrong Entrypoints: keel_scope_guard Uses active_step_id from current.yaml But Plan May Not Match

**Area:** `.claude/hooks/keel_scope_guard.py` lines 138–155; `src/keel/session/service.py` — `advance_step()`

- Issue: The scope guard reads `session.active_plan_id` from `.keel/session/current.yaml` and then loads `keel/discovery/plans/<active_plan_id>.yaml`. If `replan` has been run and a new plan was written but the old `active_plan_id` is still in `current.yaml` (e.g., a crash interrupted `svc.save()`), the scope guard checks against a stale plan. It will either always allow (plan file not found → return 0) or block against wrong paths.
- Files: `.claude/hooks/keel_scope_guard.py` lines 133–155, `src/keel/cli/app.py` lines 458–468 (`plan` command save sequence)
- Impact: After a crash or interrupted replan, all file writes are silently allowed (guard degrades to no-op). This was identified as a friction point (session 2026-03-25: "wrong entrypoints").
- Fix approach: After `replan`, write a transaction-safe update (write new session YAML to a temp file, then atomically rename). Also add a `plan_updated_at` timestamp to `current.yaml` and the plan artifact for the guard to compare.

---

## Alert Volume: Companion Fires Warning Every 2 Seconds While Repo Has Uncommitted Changes

**Area:** `src/keel/session/awareness.py` `run_awareness_pass()` line 626; `src/keel/drift/service.py` `detect_drift()` lines 625–641

- Issue: `KEE-DRF-001` ("Repository changed after the latest scan") fires every time `changed_files` is non-empty. Since `changed_files` is computed from `_changed_files_since(root, since)` where `since` defaults to the last checkpoint time or scan time, and a GSD session typically has persistent uncommitted state, this alert fires on every companion poll cycle (every 2 seconds). The `_write_drift_notification` transition guard prevents duplicate hook interruptions, but `alerts.yaml` still accumulates a `count` on `ALT-ecb57c4ae236` with `last_seen_at` updated every cycle.
- Current evidence: `alerts.yaml` shows `count: 7` for KEE-DRF-001 within minutes, and `count: 5` for KEE-DRF-014.
- Files: `src/keel/drift/service.py` lines 625–641, `src/keel/session/awareness.py` lines 276–319, `src/keel/session/alerts.py` lines 35–47
- Impact: The alerts feed is always noisy when work is in progress. Alert volume fatigue prevents users from noticing new, actionable alerts (friction point 6).
- Fix approach: Introduce a minimum `count` threshold before `KEE-DRF-001` and `KEE-DRF-014` appear in `load_active_alerts()`. Alternatively, do not increment `count` or update `last_seen_at` for these codes if no new files have been added to the `evidence` list since the last alert upsert.

---

## Session State: No File Locking on YAML Writes

**Area:** `src/keel/core/artifacts.py` — `save_yaml()`; concurrent writes from companion + CLI command

- Issue: The companion process (`keel watch`) and any concurrent CLI command (e.g., `keel checkpoint`, `keel advance`) both write to the same session files (`current.yaml`, `alerts.yaml`, `drift-memory.yaml`). There is no file locking or atomic rename strategy. On macOS, writes to YAML files are not atomic (write then rename is not used). A concurrent write from companion and a manual `keel checkpoint` call can produce a truncated or partial YAML file.
- Files: `src/keel/core/artifacts.py` (save_yaml implementation), `src/keel/session/awareness.py` line 276, `src/keel/session/service.py` line 29
- Impact: Corrupted `current.yaml` causes `SessionService.load()` to raise a Pydantic validation error or return empty state, which degrades to "no active goal" and disables all drift detection silently.
- Fix approach: Use a write-to-temp-then-rename pattern in `save_yaml()`. On macOS, `os.replace()` is atomic within the same filesystem. This eliminates the window for torn writes.

---

## Report Accumulation: Unbounded Drift / Trace / Validation Report Files

**Area:** `.keel/reports/drift/`, `.keel/reports/trace/`, `.keel/reports/validation/`

- Issue: Every companion poll cycle that detects a repo change writes a new timestamped YAML artifact to these directories. There is no pruning or rotation logic. In a single active session, 13 drift reports accumulated within minutes. At the current 2-second poll rate with active development, these directories will grow to hundreds of files per hour.
- Current evidence: 13 drift reports, 145 trace reports, 143 validation reports already present.
- Files: `src/keel/session/awareness.py` lines 243–265 (`save_artifact` calls), `src/keel/core/artifacts.py` (`save_artifact`)
- Impact: Disk usage grows unboundedly. `load_latest_model()` uses `glob("*.yaml")` and `sorted()` to find the most recent file — this degrades linearly as report counts grow. In large repos with long sessions, this becomes a meaningful startup latency for every awareness pass.
- Fix approach: Implement a `max_reports` config setting (default: 50) and prune oldest reports after saving a new one. Add a `keel clean --reports` command for manual cleanup.

---

## GSD Automated Calls: `keel goal` With No Arguments Triggers Goal Reset

**Area:** `src/keel/cli/app.py` — `goal()` command; GSD phase workflow integration

- Issue: If a GSD workflow script calls `keel goal` without any arguments as part of a phase setup step, it will unconditionally create a new goal artifact with the default `understand` mode and the generic "Understand what really exists..." statement. This replaces the active goal silently (see Goal Silent Reset concern above). The combination of GSD automation + argless `keel goal` is a high-probability footgun.
- Files: `src/keel/cli/app.py` lines 334–425, `src/keel/bridge/gsd.py` lines 76–88
- Impact: The active goal is reset without the user noticing. All downstream drift and validation checks now operate against the wrong goal. Recovery requires knowing the prior `goal-*.yaml` artifact ID.
- Fix approach: When `KEEL_AUTOMATED=1` (or similar env var) is set, make `keel goal` without `--goal-statement` a no-op that prints a warning and exits 0. Document this env var in the GSD integration guide.

---

## Missing Critical Feature: No `keel questions resolve` Command

**Area:** `src/keel/cli/app.py` (command registry); `src/keel/session/service.py`

- Issue: The question lifecycle has `sync_questions` (write) and `load_unresolved_questions` (read) but no resolve path. Questions accumulate indefinitely once written. The only escape is to rerun `keel start` which wipes and regenerates the entire question set.
- Files: `src/keel/cli/app.py` (no resolve command), `src/keel/session/service.py` lines 51–61
- Risk: Permanent KEE-DRF-005 and KEE-VAL-004 findings for any session that has ever had high-priority questions.
- Priority: High

---

## Test Coverage Gaps

**Untested Area: GSD Bridge Parse Failures**
- What's not tested: `read_gsd_state()` and `read_gsd_roadmap()` with malformed or empty `STATE.md`/`ROADMAP.md`. No test covers the silent empty-dict return path.
- Files: `src/keel/bridge/gsd.py`, `tests/` (no bridge test file found)
- Risk: Regex changes or GSD format changes break goal sync silently in production.
- Priority: High

**Untested Area: Concurrent Write Safety**
- What's not tested: Concurrent `save_yaml()` calls from companion and CLI. No integration test exercises the companion + manual command race condition.
- Files: `src/keel/core/artifacts.py`, `src/keel/session/awareness.py`
- Risk: Silent YAML corruption in sessions with an active companion.
- Priority: Medium

**Untested Area: Hook Behavior with Missing Session**
- What's not tested: `keel_scope_guard.py` when `current.yaml` is absent, empty, or corrupt. The guard returns 0 (allow) in all these cases — the test should verify this is intentional.
- Files: `.claude/hooks/keel_scope_guard.py` lines 133–141
- Risk: Guard silently degrades to no-op on first install or after session corruption.
- Priority: Medium

---

*Concerns audit: 2026-03-25*
