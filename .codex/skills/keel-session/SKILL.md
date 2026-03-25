# KEEL Session

Use this skill when working in a KEEL-managed repository and you need to re-enter the current slice cleanly.

## Workflow

1. Read `.keel/session/alerts.yaml` first when it exists, then `.keel/session/current-brief.md`.
2. Run `keel watch --once --mode auto` if the brief or alert feed looks stale or incomplete.
3. Run `keel next` before starting a new change slice.
4. If current work no longer matches the brief, use `keel checkpoint` or `keel replan`.
5. When staying in the repo for a while, keep `keel watch` running in another terminal.
6. After a meaningful slice, run `keel validate`, `keel drift --mode auto`, and `keel check`.

## Rules

- Treat active KEEL alerts as the highest-signal short-term warning feed.
- If changed files do not map to the active goal or step, assume drift until proven otherwise.
- Keep out-of-scope items and constraints stable unless KEEL artifacts are updated.
