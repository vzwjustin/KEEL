from __future__ import annotations

from datetime import datetime
from typing import Optional

from keel.config import KeelConfig, StrictnessProfile
from keel.core.paths import KeelPaths
from keel.models import (
    ConfidenceLevel,
    DeltaArtifact,
    GoalArtifact,
    GoalMode,
    PlanArtifact,
    QuestionArtifact,
    SeverityLevel,
    ValidationArtifact,
    ValidationFinding,
)


def run_validation(
    *,
    paths: KeelPaths,
    config: KeelConfig,
    goal: Optional[GoalArtifact],
    plan: Optional[PlanArtifact],
    questions: Optional[QuestionArtifact],
    deltas: Optional[list[DeltaArtifact]] = None,
) -> ValidationArtifact:
    findings: list[ValidationFinding] = []
    deltas = deltas or []

    if goal and not goal.success_criteria:
        findings.append(
            ValidationFinding(
                code="KEE-VAL-001",
                message="Active goal has no success criteria.",
                severity=SeverityLevel.ERROR,
                confidence=ConfidenceLevel.DETERMINISTIC,
                suggested_action="Add at least one success criterion with a concrete validation signal.",
                paths=[str(paths.goals_dir)],
            )
        )
    if not plan:
        findings.append(
            ValidationFinding(
                code="KEE-VAL-002",
                message="No active plan exists for the current goal.",
                severity=SeverityLevel.ERROR,
                confidence=ConfidenceLevel.DETERMINISTIC,
                suggested_action="Run `keel plan` or `keel start` to generate a phased plan.",
                paths=[str(paths.plans_dir)],
            )
        )
    behavior_modes = {
        GoalMode.FIX,
        GoalMode.WIRE_UP_INCOMPLETE,
        GoalMode.EXTEND,
        GoalMode.HARDEN,
        GoalMode.ADD_FEATURE,
        GoalMode.SHIP_MVP,
    }
    if goal and goal.mode in behavior_modes and not deltas:
        severity = SeverityLevel.WARNING
        if config.strictness in {StrictnessProfile.STRICT, StrictnessProfile.PARANOID}:
            severity = SeverityLevel.ERROR if config.strictness == StrictnessProfile.STRICT else SeverityLevel.BLOCKER
        findings.append(
            ValidationFinding(
                code="KEE-VAL-003",
                message="Behavior-changing goal has no linked delta artifact.",
                severity=severity,
                confidence=ConfidenceLevel.INFERRED_HIGH,
                suggested_action="Capture the intended behavior change with `keel delta` before implementation expands.",
                paths=[str(paths.deltas_dir)],
            )
        )
    if questions and any(question.priority.value == "high" for question in questions.questions):
        severity = SeverityLevel.WARNING
        if config.strictness in {StrictnessProfile.STRICT, StrictnessProfile.PARANOID}:
            severity = SeverityLevel.ERROR if config.strictness == StrictnessProfile.STRICT else SeverityLevel.BLOCKER
        findings.append(
            ValidationFinding(
                code="KEE-VAL-004",
                message="High-priority unresolved questions remain.",
                severity=severity,
                confidence=ConfidenceLevel.DETERMINISTIC,
                suggested_action="Resolve or consciously defer the high-priority questions before closing the slice.",
                paths=[str(paths.unresolved_questions_file)],
            )
        )

    status = "ok"
    if any(finding.severity in {SeverityLevel.ERROR, SeverityLevel.BLOCKER} for finding in findings):
        status = "error"
    elif findings:
        status = "warning"

    return ValidationArtifact(
        artifact_id=f"validation-{datetime.now().astimezone().strftime('%Y%m%d-%H%M%S')}",
        created_at=datetime.now().astimezone(),
        repo_root=str(paths.root),
        findings=findings,
        status=status,
    )
