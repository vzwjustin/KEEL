# KEEL Drift

Use this skill when you need to sanity-check whether current work is still aligned with the active goal and plan.

## Workflow

1. Run `keel --json drift --mode auto`.
2. Check `.keel/session/alerts.yaml` for collapsed high-signal warnings.
3. Run `keel --json recover` if drift is real or repeated.
4. If the recovery path is accepted, reconcile the matching goal, plan, delta, or spec artifacts.

## What To Look For

- goal drift
- plan drift
- spec drift
- runtime-entrypoint drift
- terminology drift
- session drift
- clustered weak signals becoming a real drift pattern
