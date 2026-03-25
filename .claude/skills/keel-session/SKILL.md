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

## Open Questions — MANDATORY

When the KEEL context includes "Questions to present:", you MUST use the `AskUserQuestion` tool
to present them as selectable options. Do NOT dump questions as plain text.

Format each question with 2-4 concise options. Use the `header` field as a short label (max 12 chars).
After the user selects answers, feed them back to KEEL:
- Goal/success criteria answers: `keel goal --success-criterion "..."`
- Config questions: `keel delta --title "..." --description "..."`
- Deferrals: note in the delta that the question was consciously deferred.

## Rules

- Treat active KEEL alerts as the highest-signal short-term warning feed.
- If changed files do not map to the active goal or step, assume drift until proven otherwise.
- Keep out-of-scope items and constraints stable unless KEEL artifacts are updated.
