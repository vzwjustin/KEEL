---
description: Keep Claude aligned with KEEL's active alerts, brief, and next step in a KEEL-managed repository.
---

# KEEL Session

Use this skill when working in a repository that uses KEEL for companion-mode state.

## Workflow

1. Read `.keel/session/alerts.yaml` first when it exists, then `.keel/session/current-brief.md`.
2. Run `keel watch --once --mode auto` if the alert feed or brief looks stale.
3. Run `keel next` before starting a new change slice.
4. If current work no longer matches the brief, use `keel checkpoint` or `keel replan`.
5. After a meaningful slice, run `keel validate`, `keel drift --mode auto`, and `keel check`.

## Rules

- Treat active KEEL alerts as the highest-signal short-term warning feed.
- If changed files do not map to the active goal or step, assume drift until proven otherwise.
- Keep out-of-scope items and constraints stable unless KEEL artifacts are updated.
