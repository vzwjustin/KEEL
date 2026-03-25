# Requirements

## Validated

- [x] REQ-001: KEEL companion detects drift in real-time (2s polling)
- [x] REQ-002: Scope guard blocks edits outside active plan step
- [x] REQ-003: Done-gate refuses to pass when drift is unresolved
- [x] REQ-004: Checkpoint snapshots repo state
- [x] REQ-005: GSD bridge reads .planning/STATE.md and ROADMAP.md
- [x] REQ-006: Drift notifications use AskUserQuestion for interactive choices
- [x] REQ-007: No goal = silence (companion produces no alerts)
- [x] REQ-008: Notifications fire only on state transitions (new drift codes)

## Active

- [ ] REQ-101: `keel goal` must not silently overwrite existing goal (fix #1)
- [ ] REQ-102: Plan entrypoint selection must weight goal keywords and git-hot files (fix #5)
- [ ] REQ-103: Suppress alerts that fire before first checkpoint exists (fix #6)
- [ ] REQ-104: GSD bridge should log parse warnings instead of silently returning empty dicts
- [ ] REQ-105: Companion auto-restart on crash (currently dies silently)
- [ ] REQ-106: Companion heartbeat format must include `running: true/false` for GSD statusline compatibility
- [ ] REQ-107: `keel done` output should be structured JSON consumable by GSD verify-phase
- [ ] REQ-108: Stale notifications (>30s) silently dropped by hook

## Out of Scope

- UI/statusline (GSD owns)
- Planning/discussion/research (GSD owns)
- Slash commands (removed — GSD calls keel CLI directly)
- Question generation/resolution (removed modules)
