from __future__ import annotations

from datetime import datetime
from typing import Optional

from keel.models import (
    BaselineArtifact,
    ConfidenceLevel,
    GoalArtifact,
    GoalMode,
    PriorityLevel,
    QuestionArtifact,
    QuestionItem,
    ResearchArtifact,
    ScanArtifact,
)


def _question(
    index: int,
    question: str,
    why_it_matters: str,
    triggered_by: str,
    unblocks: str,
    priority: PriorityLevel,
    confidence: ConfidenceLevel,
    related_paths: list[str],
) -> QuestionItem:
    return QuestionItem(
        question_id=f"QST-{index:03d}",
        question=question,
        why_it_matters=why_it_matters,
        triggered_by=triggered_by,
        unblocks=unblocks,
        priority=priority,
        confidence=confidence,
        related_paths=related_paths,
    )


def generate_questions(
    *,
    repo_root: str,
    scan: Optional[ScanArtifact],
    baseline: Optional[BaselineArtifact],
    goal: Optional[GoalArtifact],
    research: Optional[ResearchArtifact],
) -> QuestionArtifact:
    questions: list[QuestionItem] = []
    index = 1

    if goal and not goal.success_criteria:
        questions.append(
            _question(
                index,
                "What concrete success criteria will prove this goal is done?",
                "Anti-drift depends on a stable definition of success before implementation moves.",
                "Goal artifact has no success criteria.",
                "Validation, planning, and done-gate checks.",
                PriorityLevel.HIGH,
                ConfidenceLevel.DETERMINISTIC,
                [],
            )
        )
        index += 1

    if baseline:
        for item in baseline.unknowns[:3]:
            questions.append(
                _question(
                    index,
                    f"How should we resolve this unknown: {item.title}?",
                    "This uncertainty sits in the current-state flatline and can distort planning if left implicit.",
                    item.detail,
                    "A safer baseline and more confident next step.",
                    PriorityLevel.HIGH if item.confidence == ConfidenceLevel.UNRESOLVED else PriorityLevel.MEDIUM,
                    item.confidence,
                    item.paths,
                )
            )
            index += 1

    if scan and not scan.tests and goal and goal.mode != GoalMode.UNDERSTAND:
        questions.append(
            _question(
                index,
                "What validation signal should replace or supplement missing tests for this change?",
                "Behavior-changing work without validation mapping is a common drift source.",
                "The scan found no tests, but the goal is not pure understanding.",
                "Plan phase definitions and done checks.",
                PriorityLevel.HIGH,
                ConfidenceLevel.DETERMINISTIC,
                [path for item in (scan.entrypoints[:2] + scan.modules[:2]) for path in item.paths],
            )
        )
        index += 1

    if scan:
        duplicate_configs = [finding for finding in scan.findings if finding.category == "duplicate-config"]
        for finding in duplicate_configs[:2]:
            questions.append(
                _question(
                    index,
                    f"Which config is authoritative for {finding.title.lower()}?",
                    "Conflicting or duplicated config ownership can invalidate both planning and implementation changes.",
                    finding.detail,
                    "Alignment and validation confidence.",
                    PriorityLevel.HIGH,
                    finding.confidence,
                    finding.paths,
                )
            )
            index += 1

    if research and research.status in {"offline", "no-input"}:
        questions.append(
            _question(
                index,
                "Should we proceed without external guidance, or add explicit research sources first?",
                "Research was requested or relevant, but KEEL could not gather enough trustworthy external input.",
                "; ".join(research.unresolved[:2]) or "Research remained unavailable.",
                "The research-vs-repo comparison step.",
                PriorityLevel.MEDIUM,
                ConfidenceLevel.UNRESOLVED,
                [],
            )
        )

    return QuestionArtifact(
        artifact_id=f"questions-{datetime.now().astimezone().strftime('%Y%m%d-%H%M%S')}",
        created_at=datetime.now().astimezone(),
        repo_root=repo_root,
        questions=questions,
    )
