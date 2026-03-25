# Project State

## Current Position
- **Phase:** 1 — Fix Friction Points
- **Status:** Not started
- **Last Activity:** Project initialized (2026-03-25)

## Decisions
- KEEL is invisible under GSD — no slash commands, no UI
- GSD workflows call `keel` CLI automatically at phase boundaries
- Drift notifications use `AskUserQuestion` for interactive choices
- Companion is silent when no active goal exists
- Notifications fire only on state transitions

## Blockers
None

## Context
- 343 tests passing
- Codebase mapped (TECH.md, ARCH.md, QUALITY.md, CONCERNS.md)
- 6 friction points documented from real kernel monorepo session
