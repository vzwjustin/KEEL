# KEEL Project Instructions

## Purpose

KEEL is a real local-first CLI product. Future sessions should prioritize usable vertical slices over scaffolding and preserve the distinction between deterministic repo facts and inferred conclusions. The repo is tuned for both Codex and Claude Code re-entry, so durable repo files matter more than a giant one-off prompt.

## Working Rules

- Read [WORKLOG.md](/Users/justinadams/Documents/Keel/WORKLOG.md), [TASKS.md](/Users/justinadams/Documents/Keel/TASKS.md), [ARCHITECTURE.md](/Users/justinadams/Documents/Keel/ARCHITECTURE.md), and [.keel/session/current-brief.md](/Users/justinadams/Documents/Keel/.keel/session/current-brief.md) before substantial edits.
- Keep [CLAUDE.md](/Users/justinadams/Documents/Keel/CLAUDE.md) aligned with these repo-local instructions so Claude Code sessions inherit the same guardrails.
- Keep control files current after each meaningful vertical slice.
- Prefer finished end-to-end command flows over dead stubs.
- Never claim a heuristic is proven behavior.
- Confidence labels must remain explicit in scan, baseline, alignment, and drift output.
- Keep the CLI callable from a terminal without requiring MCP, a web UI, or hosted services.
- Use local files and git state as the primary source of truth.

## Slice Priorities

1. discovery and baseline
2. goal, questions, align, and plan
3. session persistence and current brief
4. validation, traceability, drift, and done checks
5. research adapters, exports, and docs polish
6. broader fixture coverage and regression tests
