from __future__ import annotations

from datetime import datetime
from typing import Optional

from keel.models import (
    AlignmentArtifact,
    AlignmentMismatch,
    BaselineArtifact,
    ConfidenceLevel,
    GoalArtifact,
    GoalMode,
    QuestionArtifact,
    ResearchArtifact,
    ScanArtifact,
    SeverityLevel,
)


def align_context(
    *,
    repo_root: str,
    scan: Optional[ScanArtifact],
    baseline: Optional[BaselineArtifact],
    goal: Optional[GoalArtifact],
    research: Optional[ResearchArtifact],
    questions: Optional[QuestionArtifact],
) -> AlignmentArtifact:
    mismatches: list[AlignmentMismatch] = []
    assumptions: list[str] = []
    unresolved_decisions: list[str] = []

    if goal and not goal.success_criteria:
        mismatches.append(
            AlignmentMismatch(
                mismatch_id="ALN-001",
                summary="Goal lacks success criteria",
                detail="Planning can proceed, but anti-drift enforcement will remain weak until success criteria are explicit.",
                confidence=ConfidenceLevel.DETERMINISTIC,
                severity=SeverityLevel.WARNING,
                evidence=[goal.goal_statement],
            )
        )

    if baseline and baseline.unknowns:
        unresolved_decisions.extend(item.title for item in baseline.unknowns[:4])

    if scan:
        if not scan.entrypoints and goal and goal.mode in {
            GoalMode.DEBUG,
            GoalMode.FIX,
            GoalMode.EXTEND,
            GoalMode.ADD_FEATURE,
        }:
            mismatches.append(
                AlignmentMismatch(
                    mismatch_id="ALN-002",
                    summary="Implementation goal without clear runtime entrypoint",
                    detail="The requested goal likely changes behavior, but scan data did not isolate the runtime path confidently.",
                    confidence=ConfidenceLevel.UNRESOLVED,
                    severity=SeverityLevel.WARNING,
                    evidence=[],
                )
            )
        if len(scan.build_systems) > 1:
            mismatches.append(
                AlignmentMismatch(
                    mismatch_id="ALN-003",
                    summary="More than one build system marker is present",
                    detail="Ownership of build, packaging, or runtime conventions may be split and should be clarified early.",
                    confidence=ConfidenceLevel.INFERRED_MEDIUM,
                    severity=SeverityLevel.WARNING,
                    evidence=[item.name for item in scan.build_systems],
                )
            )
        if not scan.tests and goal and goal.mode not in {GoalMode.UNDERSTAND, GoalMode.VERIFY_CLAIMS}:
            mismatches.append(
                AlignmentMismatch(
                    mismatch_id="ALN-004",
                    summary="Behavior-changing work without tests",
                    detail="KEEL did not find tests, so validation needs an explicit alternative plan.",
                    confidence=ConfidenceLevel.DETERMINISTIC,
                    severity=SeverityLevel.WARNING,
                    evidence=[],
                )
            )

    if research and research.findings and scan and not scan.contracts:
        assumptions.append(
            "External guidance exists, but the repo does not expose obvious contract files in the scanned area."
        )
    if goal:
        assumptions.extend(goal.assumptions)
    if questions:
        unresolved_decisions.extend(question.question for question in questions.questions[:4])

    if unresolved_decisions:
        focus = "Resolve the highest-risk unknowns before deep implementation work."
        confidence_summary = f"Low-to-medium alignment confidence with {len(unresolved_decisions)} unresolved decision points."
    elif mismatches:
        focus = "Stabilize validation and ownership assumptions, then proceed with the plan."
        confidence_summary = f"Medium alignment confidence with {len(mismatches)} mismatches to watch."
    else:
        focus = "Proceed to the current plan step with routine drift checks."
        confidence_summary = "High alignment confidence from current local evidence."

    return AlignmentArtifact(
        artifact_id=f"alignment-{datetime.now().astimezone().strftime('%Y%m%d-%H%M%S')}",
        created_at=datetime.now().astimezone(),
        repo_root=".",
        mismatches=mismatches,
        assumptions=assumptions,
        unresolved_decisions=unresolved_decisions,
        recommended_focus_area=focus,
        confidence_summary=confidence_summary,
    )
