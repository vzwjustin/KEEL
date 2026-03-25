# KEEL

KEEL is a local-first CLI for discovery-first onboarding and anti-drift development in messy real-world repositories.

The current MVP foundation focuses on:

- repository scanning with confidence labels
- current-state baseline generation
- goal capture
- bounded research with honest offline handling
- targeted question generation
- alignment and phased planning
- persistent session state and current brief generation
- early anti-drift validation, traceability, and done checks

Install locally with:

```bash
python3 -m pip install -e .
```

Fastest setup for vibe coders:

```bash
python3 -m pip install -e .
keel install
```

That one command now:

- bootstraps this repo's missing `.codex/` and `.claude/` companion files
- installs Codex skills
- installs Claude Code skills and hook
- installs lightweight repo git hooks without clobbering existing ones
- starts a local KEEL companion in the background for the current repo
- refreshes KEEL awareness and, if it finds an older stale session, tells you to use `keel recover` or `keel replan`
- records its own repo-local bootstrap as a KEEL-managed delta so install does not poison the first drift scan

Run the onboarding flow:

```bash
keel start --goal-mode understand
```

Run the explicit interactive first-run wizard:

```bash
keel wizard
```

Stay aware while coding:

```bash
keel watch
```

Or let the background companion stay on for you:

```bash
keel companion status
```

`keel companion status` now tells you whether the companion is running, whether its heartbeat is still fresh, and when it last saw repo activity.

## Core Commands

- `keel start`
- `keel wizard`
- `keel scan`
- `keel baseline`
- `keel goal`
- `keel research`
- `keel questions`
- `keel align`
- `keel plan`
- `keel next`
- `keel checkpoint`
- `keel watch`
- `keel companion start`
- `keel companion stop`
- `keel companion status`
- `keel validate`
- `keel trace`
- `keel drift`
- `keel recover`
- `keel delta`
- `keel done`
- `keel status`
- `keel check`
- `keel install`

## Example Discovery Workflow

```bash
keel wizard
```

Or non-interactively from Codex/Claude Code:

```bash
keel start \
  --goal-mode understand \
  --success-criterion "Produce a reliable baseline"
keel next
keel questions
keel align
```

## Example Research Workflow

```bash
keel research --enabled --source ./notes/design.md
keel align
```

If research is disabled or offline, KEEL says so explicitly and stores the result as lower-confidence external guidance rather than repo fact.

## Example Enforcement Workflow

```bash
keel delta "Add streaming ingest path" \
  --impacted-path src/my_app \
  --acceptance-criterion "New path handles backpressure"
keel validate
keel drift --mode auto
keel done
```

Or keep KEEL continuously aware in another terminal while you work:

```bash
keel watch --mode auto
```

If you already ran `keel install`, the repo-local companion should already be running:

```bash
keel companion status
```

When drift is real and you want the safest route back:

```bash
keel recover
```

If you have already acknowledged a stale repeated warning such as a drift cluster, you can temporarily dismiss it:

```bash
keel drift --dismiss KEE-DRF-021
```

If the repo does not have a local `.git/hooks` directory, KEEL now says so clearly and falls back to companion-only mode instead of pretending hooks were installed.

## Claude Code Integration

- `keel install` is the default path. It bootstraps this repo's `.claude/settings.json`, Claude hooks, Claude skills, repo git hooks, and the background KEEL companion.
- Repo-local Claude instructions live in [CLAUDE.md](/Users/justinadams/Documents/Keel/CLAUDE.md)
- Claude UI settings live in [.claude/settings.json](/Users/justinadams/Documents/Keel/.claude/settings.json)
- Recommended live awareness loop is automatic after `keel install`
- The Claude status line now falls back through the KEEL CLI if direct Python imports are unavailable
- The Claude plugin marketplace is an advanced distribution option, not the normal setup path

## Codex Integration

- `keel install` bootstraps this repo's [.codex/config.toml](/Users/justinadams/Documents/Keel/.codex/config.toml), installs Codex skills, and starts the KEEL companion
- Repo-local Codex skills live under `.codex/skills/`
- Recommended live awareness loop is automatic after `keel install`

## Known Limitations

- Runtime path inference is heuristic-first and not yet language-parser-backed.
- Research is intentionally conservative and does not assume a hidden web provider.
- Drift detection is already layered, but some signals remain heuristic and should be treated as warnings to investigate, not proofs.
- Repeated weak signals now roll up into drift clusters with a short timeline, but the clustering logic is still heuristic and should be treated as course-correction guidance rather than proof.
