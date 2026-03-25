# TASKS

## Current Slice

- [x] Create repo-local control files and `.keel/` state directories
- [x] Add packaging, CLI entrypoint, and core models
- [x] Implement repo scan with confidence-labeled findings
- [x] Implement baseline, goal, research, questions, align, plan, and next flows
- [x] Implement session persistence and `current-brief.md`
- [x] Implement validation, traceability, drift, delta, done, and status flows
- [x] Add tests and fixture repos
- [x] Update architecture/worklog with actual implementation details

## Must Build Next

- [x] current-brief writer freshness and automatic refresh coverage
- [x] goal lock for every active code change
- [x] changed-files to plan mapper and unmapped-change blocker polish
- [x] unresolved-question blocker tuning by affected path
- [x] delta-required guard default behavior by strictness profile
- [x] repo-fact vs external-guidance schema and trust ranking
- [x] terminology drift detector confidence tuning
- [x] done-gate blocker severity calibration
- [x] checkpoint system risk heuristics
- [x] command execution and path boundary guards

## Near-Term Slices

- [x] Add a continuous awareness loop and one-shot watch mode for hooks and long coding sessions
- [x] Add a repo-local background companion and install-time auto-start path
- [x] Add a drift cluster engine so repeated weak signals roll up into one stronger course-correction warning
- [x] Add `keel recover` so drift can move from detection to explanation and a concrete route back
- [x] Package the reusable Claude Code automation as a real plugin marketplace plus plugin
- [x] Make `keel install` fully own repo-local Claude/Codex setup for vibe coders and demote plugin setup to advanced docs
- [x] Add install-time stale-session handoff so KEEL tells the user to recover or replan immediately
- [x] Tighten setup and recovery UX: self-baseline install changes, fix shipped skill commands, add drift dismissal, and harden Claude status line fallback
- [ ] Improve runtime-path tracing beyond entrypoint heuristics and filename inference
- [ ] Add richer git-aware drift detection beyond working-tree presence checks
- [ ] Expand requirement/contract parsing for stronger traceability and impact mapping
- [ ] Add optional local embeddings or tree-sitter adapters without breaking offline use
- [ ] Add more fixture repos: duplicate IDs, orphan tests, offline research, and contract-drift heavy cases
