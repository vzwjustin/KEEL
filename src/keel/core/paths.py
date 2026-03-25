from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Union


def now_stamp() -> str:
    return datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")


def now_iso() -> str:
    return datetime.now().astimezone().isoformat()


@dataclass(frozen=True)
class KeelPaths:
    root: Path

    @property
    def keel_dir(self) -> Path:
        return self.root / ".keel"

    @property
    def session_dir(self) -> Path:
        return self.keel_dir / "session"

    @property
    def reports_dir(self) -> Path:
        return self.keel_dir / "reports"

    @property
    def research_dir(self) -> Path:
        return self.keel_dir / "research"

    @property
    def prompts_dir(self) -> Path:
        return self.keel_dir / "prompts"

    @property
    def templates_dir(self) -> Path:
        return self.keel_dir / "templates"

    @property
    def config_file(self) -> Path:
        return self.keel_dir / "config.yaml"

    @property
    def glossary_file(self) -> Path:
        return self.keel_dir / "glossary.yaml"

    @property
    def done_gate_file(self) -> Path:
        return self.keel_dir / "done-gate.yaml"

    @property
    def current_file(self) -> Path:
        return self.session_dir / "current.yaml"

    @property
    def current_brief_file(self) -> Path:
        return self.session_dir / "current-brief.md"

    @property
    def checkpoints_file(self) -> Path:
        return self.session_dir / "checkpoints.yaml"

    @property
    def unresolved_questions_file(self) -> Path:
        return self.session_dir / "unresolved-questions.yaml"

    @property
    def decisions_log_file(self) -> Path:
        return self.session_dir / "decisions.log"

    @property
    def companion_file(self) -> Path:
        return self.session_dir / "companion.yaml"

    @property
    def companion_log_file(self) -> Path:
        return self.session_dir / "companion.log"

    @property
    def companion_heartbeat_file(self) -> Path:
        return self.session_dir / "companion-heartbeat.yaml"

    @property
    def drift_memory_file(self) -> Path:
        return self.session_dir / "drift-memory.yaml"

    @property
    def drift_dismissals_file(self) -> Path:
        return self.session_dir / "drift-dismissals.yaml"

    @property
    def alerts_file(self) -> Path:
        return self.session_dir / "alerts.yaml"

    @property
    def pending_notification_file(self) -> Path:
        return self.session_dir / "pending-notification.yaml"

    @property
    def drift_notification_state_file(self) -> Path:
        return self.session_dir / "drift-notification-state.yaml"

    @property
    def artifact_root(self) -> Path:
        return self.root / "keel"

    @property
    def discovery_root(self) -> Path:
        return self.artifact_root / "discovery"

    @property
    def scans_dir(self) -> Path:
        return self.discovery_root / "scans"

    @property
    def baselines_dir(self) -> Path:
        return self.discovery_root / "baselines"

    @property
    def goals_dir(self) -> Path:
        return self.discovery_root / "goals"

    @property
    def questions_dir(self) -> Path:
        return self.discovery_root / "questions"

    @property
    def alignments_dir(self) -> Path:
        return self.discovery_root / "alignments"

    @property
    def plans_dir(self) -> Path:
        return self.discovery_root / "plans"

    @property
    def checkpoints_dir(self) -> Path:
        return self.discovery_root / "checkpoints"

    @property
    def research_artifacts_dir(self) -> Path:
        return self.discovery_root / "research"

    @property
    def specs_root(self) -> Path:
        return self.artifact_root / "specs"

    @property
    def requirements_dir(self) -> Path:
        return self.specs_root / "requirements"

    @property
    def decisions_dir(self) -> Path:
        return self.specs_root / "decisions"

    @property
    def contracts_dir(self) -> Path:
        return self.specs_root / "contracts"

    @property
    def examples_dir(self) -> Path:
        return self.specs_root / "examples"

    @property
    def validation_dir(self) -> Path:
        return self.specs_root / "validation"

    @property
    def deltas_dir(self) -> Path:
        return self.specs_root / "deltas"

    def ensure(self) -> None:
        for directory in [
            self.keel_dir,
            self.session_dir,
            self.reports_dir,
            self.research_dir,
            self.prompts_dir,
            self.templates_dir,
            self.scans_dir,
            self.baselines_dir,
            self.goals_dir,
            self.questions_dir,
            self.alignments_dir,
            self.plans_dir,
            self.checkpoints_dir,
            self.research_artifacts_dir,
            self.requirements_dir,
            self.decisions_dir,
            self.contracts_dir,
            self.examples_dir,
            self.validation_dir,
            self.deltas_dir,
        ]:
            directory.mkdir(parents=True, exist_ok=True)


def resolve_paths(root: Union[Path, str]) -> KeelPaths:
    return KeelPaths(Path(root).resolve())
