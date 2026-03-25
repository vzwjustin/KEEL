# Technology Stack

**Analysis Date:** 2026-03-25

## Languages

**Primary:**
- Python 3.9+ — all CLI, services, models, hooks, and scripts

**Secondary:**
- None. No JS/Node components exist in this repository. The statusline is owned by a separate GSD fork (not in this repo). All Claude Code hooks (`.claude/hooks/`) are Python scripts, not shell or JS.

## Runtime

**Environment:**
- Python 3.9+ (declared minimum via `requires-python = ">=3.9"` in `pyproject.toml`)
- System Python tested at 3.9.6 (`/usr/bin/python3`)
- No `.python-version` or `.nvmrc` file present

**Package Manager:**
- `uv` preferred for installation (`make install` checks for `uv` first)
- Falls back to `pip install --user -e .` if `uv` is not found
- No lockfile present (no `uv.lock` or `requirements.txt`)

## Frameworks

**Core:**
- `typer >= 0.12` — CLI framework; all commands defined in `src/keel/cli/app.py`
- `pydantic >= 2.8` — data validation and artifact model definitions; used pervasively across `src/keel/models/` and `src/keel/config/`
- `rich >= 13.7` — terminal output; `Console`, `Panel` used in `src/keel/reporters/render.py` and `src/keel/cli/app.py`
- `PyYAML >= 6.0` — YAML serialization for all artifact files and session state; used in `src/keel/core/artifacts.py` and `src/keel/config/settings.py`

**Testing:**
- `pytest >= 8.0` — test runner; configured in `pyproject.toml` under `[tool.pytest.ini_options]`
- `typer.testing.CliRunner` — CLI invocation in tests (no extra package; included in typer)
- `unittest.mock.patch` — standard library mocking; used in `tests/test_core.py`

**Build:**
- `setuptools >= 68` with `wheel` — build backend declared in `pyproject.toml`
- Source layout: `src/` layout, package root is `src/keel/`
- Egg-info generated at `src/keel_cli.egg-info/`

## CLI Entry Point

**Registered script:**
- Command name: `keel`
- Entry point: `keel.cli.main:main` (declared in `pyproject.toml` `[project.scripts]`)
- Entrypoint module: `src/keel/cli/main.py` — normalizes `--json` flag, then delegates to `keel.cli.app:app`
- `src/keel/cli/app.py` — defines the full `typer.Typer()` app with all subcommands
- Subcommand group: `companion` registered as a sub-typer via `app.add_typer(companion_app, name="companion")`
- `__main__.py` at `src/keel/__main__.py` enables `python -m keel`

## Key CLI Subcommands

Defined in `src/keel/cli/app.py`:
- `init`, `scan`, `baseline`, `goal`, `plan`, `align`, `questions`, `drift`, `trace`, `validate`, `recover`, `replan`, `done`, `delta`, `install`, `status`
- `companion start`, `companion stop`, `companion status`

## Package Layout

```
src/keel/
├── __init__.py           # version = "0.1.0"
├── __main__.py           # python -m keel support
├── cli/
│   ├── app.py            # all typer commands (~500+ lines)
│   └── main.py           # entrypoint wrapper
├── baseline/             # baseline generation service
├── bridge/
│   └── gsd.py            # GSD integration bridge (reads .planning/STATE.md, ROADMAP.md)
├── config/
│   └── settings.py       # KeelConfig pydantic model, yaml load/save
├── core/
│   ├── artifacts.py      # YAML artifact I/O (save_yaml, load_model, etc.)
│   ├── bootstrap.py      # ensure_project, file scaffolding
│   └── paths.py          # KeelPaths dataclass (all .keel/ path definitions)
├── discovery/            # repository scanner
├── drift/                # drift detection service
├── goal/                 # goal artifact builder
├── models/
│   └── artifacts.py      # all Pydantic models (ScanArtifact, GoalArtifact, etc.)
├── planner/              # plan builder service
├── recover/              # recovery plan builder
├── reporters/
│   └── render.py         # rich Console rendering helpers
├── rules/                # drift error codes catalog
├── session/
│   ├── awareness.py      # repo watch and awareness pass
│   ├── alerts.py         # alert feed management
│   ├── companion.py      # companion subprocess lifecycle (POSIX signals, PID tracking)
│   ├── service.py        # SessionService (load/save current.yaml)
│   └── ui.py             # session display helpers
├── trace/                # trace artifact builder
├── utils/
│   ├── agent_install.py  # Codex/Claude asset installer
│   ├── agent_templates.py# repo-local agent file templates
│   └── text.py           # text utilities
└── validators/           # plan/done-gate validation service
```

## Build and Install Mechanisms

**Install targets** (via `Makefile`):
```bash
make install                # uv tool install . OR pip install --user -e .
make dev-install            # install + install_agent_assets.py
make install-agent-assets   # python3 scripts/install_agent_assets.py
make install-codex-assets   # --codex-only
make install-claude-assets  # --claude-only
make test                   # PYTHONPATH=src python3 -m pytest -q
```

**Agent asset installer:** `scripts/install_agent_assets.py` wraps `keel.utils.agent_install.install_agent_assets()` to:
- Bootstrap `.claude/settings.json`, `.codex/config.toml`, and repo-local hooks
- Install Claude Code slash commands from `.claude/commands/keel/` into `~/.claude/commands/keel/`
- Install Codex skills from `.codex/skills/` into `~/.codex/skills/`
- Install git hooks (`post-checkout`, `post-merge`, `pre-commit`) into `.git/hooks/`
- Start the KEEL companion process

## Test Framework

**Runner:** pytest >= 8.0
**Config:** `pyproject.toml` `[tool.pytest.ini_options]`
- `testpaths = ["tests"]`
- `pythonpath = ["src"]`

**Run command:**
```bash
make test
# or directly:
PYTHONPATH=src python3 -m pytest -q
```

**Test files:** `tests/test_*.py` (14 test modules)
**Fixtures:** `tests/fixtures/messy_repo/` and `tests/fixtures/multi_entry_repo/` — full fixture repos with `.keel/` state for integration tests
**Helper:** `tests/conftest.py` provides `fixture_repo` pytest fixture (copies fixture repos to `tmp_path`) and `keel_bootstrap()` helper that runs init + scan + baseline + goal via `CliRunner`

**No coverage tooling configured** — no `pytest-cov` in dependencies, no coverage thresholds declared.

## Claude Code Integration

**Hook configuration:** `.claude/settings.json`
- `PreToolUse` on `Write|Edit` → `python3 .claude/hooks/keel_scope_guard.py` (3s timeout) — blocks file edits outside active plan scope
- `PostToolUse` on `Write|Edit|Bash` → `python3 .claude/hooks/keel_notify.py` (5s timeout) — notifies KEEL companion of file changes
- Both hooks are pure Python, using only stdlib + optional PyYAML; no Node or shell dependency

**Claude slash commands:** `.claude/commands/keel/` (empty at time of analysis — commands directory exists but contains no `.md` files)

## Codex Integration

**Config:** `.codex/config.toml`
- Path boundary mode: `repo-only`
- Guards: block writes outside repo, require delta for behavior change, warn on unmapped changed files

**Skills:** `.codex/skills/` — installed into `~/.codex/skills/` by the asset installer

## GSD Bridge

`src/keel/bridge/gsd.py` — passive read-only bridge; no GSD package dependency:
- Reads `.planning/STATE.md` to extract current phase
- Reads `.planning/ROADMAP.md` to extract phase goals
- Writes `.planning/KEEL-STATUS.md` with current KEEL brief for GSD agents to consume
- Called from `src/keel/cli/app.py` after any brief refresh

## Artifact Storage Format

All KEEL artifacts stored as YAML files under `keel/discovery/` and `keel/specs/` in the target repo:
- Scans: `keel/discovery/scans/<artifact_id>.yaml`
- Goals: `keel/discovery/goals/<artifact_id>.yaml`
- Plans: `keel/discovery/plans/<artifact_id>.yaml`
- Deltas: `keel/specs/deltas/<artifact_id>.yaml`
- Session state: `.keel/session/current.yaml`
- Config: `.keel/config.yaml`

## Configuration

**Project config:** `.keel/config.yaml` in each managed repo (validated by `KeelConfig` pydantic model in `src/keel/config/settings.py`)
- `strictness`: relaxed | standard | strict | paranoid (default: standard)
- `research_enabled`: bool (default: false)
- `max_scan_files`: int (default: 4000)
- `output_format`: text | json (default: text)

**No environment variables required** for basic operation. All state is file-based.

## External Integrations

None. KEEL is fully local-first. No external APIs, no cloud services, no authentication providers, no database connections. All data lives in files within the target repository's `.keel/` directory.

---

*Stack analysis: 2026-03-25*
