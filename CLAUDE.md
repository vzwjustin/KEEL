# KEEL Agent Guide

This repository is built to be resumed cleanly by both Codex and Claude Code.

## Start Here

Before substantial edits, read:

1. [AGENTS.md](/Users/justinadams/Documents/Keel/AGENTS.md)
2. [WORKLOG.md](/Users/justinadams/Documents/Keel/WORKLOG.md)
3. [TASKS.md](/Users/justinadams/Documents/Keel/TASKS.md)
4. [ARCHITECTURE.md](/Users/justinadams/Documents/Keel/ARCHITECTURE.md)
5. [.keel/session/current-brief.md](/Users/justinadams/Documents/Keel/.keel/session/current-brief.md)

## Operating Rules

- Keep KEEL local-first. Local files and git state are the source of truth.
- Preserve the difference between `repo-fact`, `external-guidance`, `inferred`, and `unresolved`.
- Do not present heuristics as proof.
- Prefer small finished vertical slices over broad scaffolding.
- Update `WORKLOG.md`, `TASKS.md`, and `ARCHITECTURE.md` after meaningful slices.
- Refresh `.keel/session/current-brief.md` whenever the active goal, phase, next step, blockers, or invariants change.
- Treat drift detection as a core product behavior, not an optional report.

## Anti-Drift Expectations

- One active goal should remain locked at a time.
- Changed files should map to the active goal, current plan step, requirement, contract, or delta.
- High-priority unresolved questions should not be silently bypassed.
- Behavior changes, contract changes, and public surface changes should record a delta before done can pass.
- If research suggests a pivot, keep it advisory until explicitly acknowledged in a decision or updated plan.

## Tool-Agnostic Session Files

- Current session state: [.keel/session/current.yaml](/Users/justinadams/Documents/Keel/.keel/session/current.yaml)
- Current brief: [.keel/session/current-brief.md](/Users/justinadams/Documents/Keel/.keel/session/current-brief.md)
- Checkpoints: [.keel/session/checkpoints.yaml](/Users/justinadams/Documents/Keel/.keel/session/checkpoints.yaml)
- Decisions: [.keel/session/decisions.log](/Users/justinadams/Documents/Keel/.keel/session/decisions.log)

## Preferred Build Order

1. discovery and baseline
2. goal, questions, align, and plan
3. session persistence and current brief
4. drift, traceability, and done-gate enforcement
5. research trust and approval guards
6. stronger fixture coverage and e2e verification

## KEEL Drift Interaction

When KEEL injects a drift notification via hooks, always present it to the user
using the `AskUserQuestion` tool with the options KEEL suggests. Never dump raw
KEEL messages as plain text. The user should always get interactive choices.
