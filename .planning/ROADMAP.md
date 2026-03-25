# Roadmap

## Phase 1: Fix Friction Points
**Goal:** Resolve the 6 UX issues from real-world usage so the guardrail layer is trustworthy.

| # | Requirement | Priority |
|---|-------------|----------|
| 1 | REQ-101: Goal silent reset guard | High |
| 2 | REQ-103: Suppress pre-checkpoint alerts | High |
| 3 | REQ-102: Entrypoint scoring with goal keywords | Medium |
| 4 | REQ-104: GSD bridge parse warnings | Medium |

**Must-haves:**
- `keel goal --unresolved-question` appends to existing goal (not overwrites)
- No alerts fire before first checkpoint
- Plan entrypoints weighted by goal text, not just Python file heuristics
- GSD bridge logs parse failures instead of silent empty returns

**Plans:** 2 plans
Plans:
- [ ] 01-01-PLAN.md — Fix REQ-101 (goal TypeError + partial-flag reset) and REQ-103 (suppress KEE-DRF-001 pre-checkpoint)
- [ ] 01-02-PLAN.md — Fix REQ-102 (entrypoint goal/git-hot scoring) and REQ-104 (bridge stderr warnings + first bridge tests)

**Status:** Not started

---

## Phase 2: Companion Hardening
**Goal:** Make the companion reliable enough to run unattended across GSD sessions.

| # | Requirement | Priority |
|---|-------------|----------|
| 1 | REQ-105: Auto-restart on crash | High |
| 2 | REQ-106: Heartbeat format with running field | High |
| 3 | REQ-108: Stale notification cleanup | Medium |

**Must-haves:**
- Companion auto-restarts after crash (max 3 retries with backoff)
- Heartbeat YAML includes `running: true/false` for GSD statusline
- Stale notifications (>30s) silently dropped

**Status:** Not started

---

## Phase 3: GSD Integration Polish
**Goal:** Ensure `keel done` and the scope guard work seamlessly within GSD verify-phase and execute-phase.

| # | Requirement | Priority |
|---|-------------|----------|
| 1 | REQ-107: Structured done-gate output | High |
| 2 | Scope guard respects GSD plan files | Medium |
| 3 | KEEL-STATUS.md always fresh in .planning/ | Medium |

**Must-haves:**
- `keel --json done` returns structured pass/fail with reasons consumable by GSD verify-phase
- Scope guard reads GSD PLAN.md for allowed paths when no KEEL plan exists
- `.planning/KEEL-STATUS.md` updated on every awareness pass (not just brief refresh)

**Status:** Not started

---

## Phase 4: Test & Ship
**Goal:** Full test coverage for new code, clean README, publish.

| # | Requirement | Priority |
|---|-------------|----------|
| 1 | Tests for all Phase 1-3 changes | High |
| 2 | README reflects GSD-first reality | Medium |
| 3 | Clean install path for new users | Medium |

**Must-haves:**
- 380+ tests passing (up from 343)
- README shows GSD as primary, KEEL as invisible companion
- `uv tool install .` + GSD fork install = working setup

**Status:** Not started
