from __future__ import annotations

from pathlib import Path
from typing import Tuple, Union

from keel.config.settings import KeelConfig, load_config, save_config
from keel.core.artifacts import load_yaml, save_yaml
from keel.core.paths import KeelPaths, resolve_paths
from keel.models import SessionState


DEFAULT_BRIEF = """# Current Brief

- Current goal: not set
- Current phase: not set
- Current step: not set
- Constraints: local-first CLI, no MCP, trust local repo facts
- Unresolved questions: none recorded yet
- Latest decisions: none recorded yet
- Research that matters now: offline by default
- Critical repo facts: repository state not scanned yet
- Done condition for current work: establish the next aligned slice
"""


def ensure_file(path: Path, content: str) -> None:
    if not path.exists():
        path.write_text(content, encoding="utf-8")


def ensure_project(root: Union[Path, str]) -> Tuple[KeelPaths, KeelConfig, SessionState]:
    paths = resolve_paths(root)
    paths.ensure()

    config = load_config(paths.config_file)
    save_config(paths.config_file, config)

    if not paths.current_file.exists():
        save_yaml(paths.current_file, SessionState().model_dump(mode="json"))
    if not paths.checkpoints_file.exists():
        save_yaml(paths.checkpoints_file, {"checkpoints": []})
    if not paths.unresolved_questions_file.exists():
        save_yaml(paths.unresolved_questions_file, {"questions": []})
    if not paths.drift_memory_file.exists():
        save_yaml(paths.drift_memory_file, {"events": []})
    if not paths.drift_dismissals_file.exists():
        save_yaml(paths.drift_dismissals_file, {"dismissals": []})
    if not paths.alerts_file.exists():
        save_yaml(paths.alerts_file, {"alerts": []})

    ensure_file(paths.current_brief_file, DEFAULT_BRIEF)
    ensure_file(paths.decisions_log_file, "")
    ensure_file(paths.glossary_file, "terms: {}\n")
    ensure_file(paths.done_gate_file, "required_checks: []\n")

    session = SessionState.model_validate(load_yaml(paths.current_file))
    return paths, config, session
